# src/sync_catalog.py
import os, time, csv, argparse, pathlib, requests

API_KEY = os.getenv("POKEMONTCG_IO_API_KEY")  # set this in your shell if you haven't
BASE_URL = "https://api.pokemontcg.io/v2/cards"

OUT_DIR = pathlib.Path("data/catalog")
IMG_DIR = OUT_DIR / "images"
CSV_PATH = OUT_DIR / "cards.csv"

def fetch_page(q, page, pageSize, retries=4):
    headers = {"X-Api-Key": API_KEY} if API_KEY else {}
    backoff = 0.5
    for i in range(retries):
        try:
            r = requests.get(
                BASE_URL,
                params={"q": q, "page": page, "pageSize": pageSize},
                headers=headers,
                timeout=20,
            )
            r.raise_for_status()
            return r.json().get("data", [])
        except requests.RequestException as e:
            if i == retries - 1: raise
            time.sleep(backoff); backoff *= 2

def download(url, dest, retries=3):
    dest.parent.mkdir(parents=True, exist_ok=True)
    backoff = 0.5
    for i in range(retries):
        try:
            with requests.get(url, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(8192):
                        if chunk:
                            f.write(chunk)
            return True
        except requests.RequestException:
            if i == retries - 1: return False
            time.sleep(backoff); backoff *= 2

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="supertype:pokemon set.id:sv3",
                        help="API query, e.g. 'supertype:pokemon set.id:sv3'")
    parser.add_argument("--pageSize", type=int, default=200)
    parser.add_argument("--limit", type=int, default=400, help="max cards to pull (safety)")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    rows, seen, total = [], set(), 0
    page = 1
    while total < args.limit:
        batch = fetch_page(args.query, page, args.pageSize)
        if not batch:
            break
        print(f"Page {page}: {len(batch)}")
        for d in batch:
            cid = d.get("id")
            if not cid or cid in seen:
                continue
            seen.add(cid)

            name = d.get("name", "")
            number = d.get("number", "")
            set_obj = d.get("set") or {}
            set_id = set_obj.get("id", "")
            hp_raw = d.get("hp")
            try:
                hp = int(hp_raw) if isinstance(hp_raw, str) and hp_raw.isdigit() else (hp_raw if isinstance(hp_raw, int) else "")
            except Exception:
                hp = ""

            img_url = (d.get("images") or {}).get("large") or (d.get("images") or {}).get("small")
            local = IMG_DIR / (set_id or "unknown") / (f"{number or cid}.jpg")
            if img_url and not local.exists():
                ok = download(img_url, local)
                if not ok:
                    print("  [skip] download failed:", img_url)
                    continue

            rows.append({
                "id": cid, "name": name, "set": set_id, "number": number,
                "hp": hp, "image_path": str(local)
            })
            total += 1
            if total >= args.limit: break
        page += 1
        time.sleep(0.15)  # gentle on the API

    # write CSV
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id","name","set","number","hp","image_path"])
        w.writeheader(); w.writerows(rows)

    print(f"Wrote {len(rows)} rows → {CSV_PATH}")

if __name__ == "__main__":
    main()
