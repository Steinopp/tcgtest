import os, time, json
from pokemontcgsdk import RestClient, Card, Set, restclient
import requests

API_KEY = os.getenv("POKEMONTCG_IO_API_KEY")
if API_KEY:
    RestClient.configure(API_KEY)

def decode_sdk_error(e) -> str:
    # The SDK sometimes stores the HTTP body as bytes in e.args[0]
    if hasattr(e, "args") and e.args:
        body = e.args[0]
        if isinstance(body, (bytes, bytearray)):
            try:
                return body.decode("utf-8", "ignore")
            except Exception:
                return "<binary body>"
        return str(body)
    return str(e)

def safe_where(**kwargs):
    tries, delay = 4, 0.5
    last = None
    for i in range(tries):
        try:
            return Card.where(**kwargs)
        except restclient.PokemonTcgException as e:
            print(f"[warn] SDK where() failed (try {i+1}/{tries}): {decode_sdk_error(e)[:200]}")
            last = e
            time.sleep(delay); delay *= 2
    raise last

def http_where(q, page=1, pageSize=50):
    url = "https://api.pokemontcg.io/v2/cards"
    headers = {"X-Api-Key": API_KEY} if API_KEY else {}
    r = requests.get(url, params={"q": q, "page": page, "pageSize": pageSize}, headers=headers, timeout=15)
    r.raise_for_status()
    data = r.json().get("data", [])
    # Return lightweight dicts (id, name) to prove it works
    return [{"id": d.get("id"), "name": d.get("name")} for d in data]

# 1) Known card by ID (this worked for you)
c = Card.find("sv3-86")
print(c.id, c.name, c.hp, c.images)

# 2) Narrow query first (set + number) to reduce server load
QUERY_EXACT = 'set.id:sv3 number:86 supertype:pokemon'
try:
    cards_exact = safe_where(q=QUERY_EXACT, page=1, pageSize=10)
    print("Exact query via SDK:", [(x.id, x.name) for x in cards_exact])
except Exception:
    # Fallback to raw HTTP
    data = http_where(QUERY_EXACT, page=1, pageSize=10)
    print("Exact query via HTTP:", data)

# 3) Name query (still narrow). If SDK 504s, fallback will kick in.
QUERY_NAME = 'name:"Gardevoir ex" supertype:pokemon'
try:
    cards = safe_where(q=QUERY_NAME, page=1, pageSize=25)
    print("Name query via SDK:", [(x.id, x.name) for x in cards[:5]])
except Exception:
    data = http_where(QUERY_NAME, page=1, pageSize=25)
    print("Name query via HTTP:", data[:5])
