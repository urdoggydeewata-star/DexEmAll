import os, json, time, pathlib, requests

ROOT = pathlib.Path(__file__).resolve().parents[1]  # project root
OUT_DIR = ROOT / "assets" / "item_icons"
OUT_DIR.mkdir(parents=True, exist_ok=True)

INDEX_JSON = OUT_DIR / "items_index.json"
API_BASE   = "https://pokeapi.co/api/v2"

def get(url):
    for i in range(5):
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 503):  # rate-limited, retry
            time.sleep(1.5 + i)
            continue
        r.raise_for_status()
    raise RuntimeError(f"Failed GET {url}")

def main():
    # 1) list all items
    items = []
    url = f"{API_BASE}/item?limit=2000"
    data = get(url)
    items.extend(data["results"])
    # (PokeAPI has < 2000 items; if you want to be super-safe, follow 'next'.)
    print(f"Found {len(items)} items")

    # 2) fetch each item details & download its sprite
    index = {}
    for i, it in enumerate(items, 1):
        try:
            d = get(it["url"])
            ident = d["name"]                 # canonical id (e.g. "poke_ball")
            sprite = (d.get("sprites") or {}).get("default")
            # Some categories don’t have a sprite → skip cleanly
            if not sprite:
                print(f"[{i}/{len(items)}] {ident:30}  (no sprite)")
                continue

            # Save icon as <id>.png
            png = requests.get(sprite, timeout=30)
            png.raise_for_status()
            out_path = OUT_DIR / f"{ident}.png"
            with open(out_path, "wb") as f:
                f.write(png.content)

            # Put a bit of metadata into the index
            index[ident] = {
                "name": ident,
                "sprite_url": sprite,
                "local_path": f"assets/item_icons/{ident}.png"
            }
            print(f"[{i}/{len(items)}] {ident:30}  ✔")
            time.sleep(0.05)  # be nice to their API/CDN
        except Exception as e:
            print(f"[{i}/{len(items)}] {it['name']}: ERROR {e}")

    with open(INDEX_JSON, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    print(f"\nSaved {len(index)} icons → {OUT_DIR}")
    print(f"Wrote index → {INDEX_JSON}")

if __name__ == "__main__":
    main()