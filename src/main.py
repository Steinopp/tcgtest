# src/main.py
import os, csv, time, warnings, pathlib, requests, json
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from urllib3.exceptions import NotOpenSSLWarning

# --- make relative paths consistent ---
ROOT = pathlib.Path(__file__).resolve().parents[1]
os.chdir(ROOT)

# optional: hide LibreSSL warning noise
warnings.filterwarnings("ignore", category=NotOpenSSLWarning)

# ====== SETTINGS ======
API_KEY = os.getenv("POKEMONTCG_IO_API_KEY") or ""   # or paste your key string here
QUERY   = "supertype:pokemon set.id:sv3"             # which set to fetch
PAGE_SIZE = 40
LIMIT     = 80
# ======================

CATALOG_DIR = pathlib.Path("data/catalog")
IMG_DIR     = CATALOG_DIR / "images"
CSV_PATH    = CATALOG_DIR / "cards.csv"
FAISS_PATH  = CATALOG_DIR / "embeddings.faiss"
IDS_NPY     = CATALOG_DIR / "ids.npy"
META_JSON   = CATALOG_DIR / "id_to_meta.json"

BASE_URL = "https://api.pokemontcg.io/v2/cards"

def make_session(total_retries=5, backoff_factor=0.6, timeout=30):
    s = requests.Session()
    retry = Retry(
        total=total_retries,
        read=total_retries,
        connect=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))

    # default timeout on every request
    orig = s.request
    def _with_timeout(method, url, **kwargs):
        kwargs.setdefault("timeout", timeout)
        return orig(method, url, **kwargs)
    s.request = _with_timeout
    return s

def sync_catalog(query=QUERY, page_size=PAGE_SIZE, limit=LIMIT):
    """Download images + write data/catalog/cards.csv"""
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    sess = make_session()
    headers = {"X-Api-Key": API_KEY} if API_KEY else {}
    rows, seen, total = [], set(), 0
    page = 1

    print(f"[sync] query='{query}', pageSize={page_size}, limit={limit}")
    while total < limit:
        r = sess.get(BASE_URL, params={"q": query, "page": page, "pageSize": page_size}, headers=headers)
        r.raise_for_status()
        batch = r.json().get("data", [])
        if not batch:
            break
        print(f"[sync] page {page}: {len(batch)} cards")
        for d in batch:
            cid = d.get("id")
            if not cid or cid in seen:
                continue
            seen.add(cid)

            name   = d.get("name", "")
            number = d.get("number", "")
            set_id = (d.get("set") or {}).get("id", "unknown")
            hp_raw = d.get("hp")
            try:
                hp = int(hp_raw) if isinstance(hp_raw, str) and hp_raw.isdigit() else (hp_raw if isinstance(hp_raw, int) else "")
            except Exception:
                hp = ""

            img_url = (d.get("images") or {}).get("large") or (d.get("images") or {}).get("small")
            local = IMG_DIR / set_id / (f"{number or cid}.jpg")
            if img_url and not local.exists():
                local.parent.mkdir(parents=True, exist_ok=True)
                with sess.get(img_url, stream=True) as imr:
                    imr.raise_for_status()
                    with open(local, "wb") as f:
                        for chunk in imr.iter_content(8192):
                            if chunk: f.write(chunk)

            rows.append({"id": cid, "name": name, "set": set_id, "number": number, "hp": hp, "image_path": str(local)})
            total += 1
            if total >= limit: break
        page += 1
        time.sleep(0.15)  # be nice to the API

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id","name","set","number","hp","image_path"])
        w.writeheader(); w.writerows(rows)
    print(f"[sync] wrote {len(rows)} rows → {CSV_PATH}")

def build_index_inline():
    """Embed all scans and build FAISS index (no imports needed)."""
    import numpy as np, faiss, torch, open_clip
    from PIL import Image
    import pandas as pd

    df = pd.read_csv(CSV_PATH)
    assert len(df) > 0, "No rows in cards.csv — run sync first."

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, preprocess, _ = open_clip.create_model_and_transforms("ViT-B-16", pretrained="openai")
    model.eval().to(device)

    ids, vecs, meta = [], [], {}
    for _, row in df.iterrows():
        cid = str(row["id"])
        img_path = pathlib.Path(str(row["image_path"]))
        if not img_path.exists():
            print("[skip] missing:", img_path)
            continue

        img = Image.open(img_path).convert("RGB")
        with torch.no_grad():
            x = preprocess(img).unsqueeze(0).to(device)
            z = model.encode_image(x)
            z = z / z.norm(dim=-1, keepdim=True)
            vec = z.squeeze(0).cpu().numpy().astype("float32")

        ids.append(cid); vecs.append(vec)
        meta[cid] = {
            "name": str(row["name"]),
            "set": str(row.get("set","")),
            "number": str(row.get("number","")),
            "hp": int(row["hp"]) if str(row.get("hp","")).isdigit() else None,
            "image_path": str(img_path),
        }

    assert vecs, "No vectors built — check image paths in cards.csv."
    import numpy as np, faiss
    vecs = np.stack(vecs).astype("float32")
    ids_arr = np.array(ids)

    index = faiss.IndexFlatIP(vecs.shape[1])  # cosine via dot on normalized vecs
    index.add(vecs)

    np.save(IDS_NPY, ids_arr)
    with open(META_JSON, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    faiss.write_index(index, str(FAISS_PATH))
    print(f"[index] saved {len(ids_arr)} embeddings → {FAISS_PATH}")

def identify_first_image_inline(topk=5):
    """Load index + model and identify the first catalog image."""
    import numpy as np, faiss, torch, open_clip
    from PIL import Image
    import pandas as pd

    df = pd.read_csv(CSV_PATH)
    assert len(df) > 0
    img_path = pathlib.Path(df.iloc[0]["image_path"])
    print(f"[identify] query image: {img_path}")

    # load index + metadata
    index = faiss.read_index(str(FAISS_PATH))
    ids   = np.load(IDS_NPY)
    meta  = json.loads(open(META_JSON, "r", encoding="utf-8").read())

    # model
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, preprocess, _ = open_clip.create_model_and_transforms("ViT-B-16", pretrained="openai")
    model.eval().to(device)

    qimg = Image.open(img_path).convert("RGB")
    with torch.no_grad():
        x = preprocess(qimg).unsqueeze(0).to(device)
        z = model.encode_image(x)
        z = z / z.norm(dim=-1, keepdim=True)
        qvec = z.cpu().numpy().astype("float32")

    D, I = index.search(qvec, topk)
    D, I = D[0], I[0]
    print("[identify] top results:")
    for d, idx in zip(D, I):
        cid = ids[idx]
        m = meta[cid]
        print(f"  - {cid:>8}  {m['name']:<30} sim={d:.3f}  ({m.get('set','')} {m.get('number','')})")

if __name__ == "__main__":
    sync_catalog(query=QUERY, page_size=PAGE_SIZE, limit=LIMIT)
    build_index_inline()
    identify_first_image_inline(topk=5)
