from __future__ import annotations

import os, json, time, re, argparse, sqlite3
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

import requests

API = "https://pokeapi.co/api/v2"
CACHE_DIR = Path("cache/pokeapi")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
SLEEP = 0.20  # polite delay

# ---------- DB discovery ----------
def find_db(explicit: Optional[str]) -> Optional[Path]:
    if explicit and Path(explicit).exists():
        return Path(explicit)
    env = os.getenv("MYUU_DB")
    if env and Path(env).exists():
        return Path(env)
    here = Path.cwd()
    script_root = Path(__file__).resolve().parents[1]
    for p in [here/"myuu.db", here/"data"/"myuu.db", script_root/"myuu.db", script_root/"data"/"myuu.db"]:
        if p.exists():
            return p
    # last-resort: search upwards for *.db
    for p in script_root.parent.rglob("*.db"):
        s = str(p).lower()
        if any(bad in s for bad in ("venv", "node_modules", "__pycache__")):
            continue
        return p
    return None

# ---------- HTTP with cache ----------
def cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"

def fetch_json(url: str, key: str) -> Dict[str, Any]:
    cp = cache_path(key)
    if cp.exists():
        return json.loads(cp.read_text(encoding="utf-8"))
    for _ in range(3):
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                data = r.json()
                cp.write_text(json.dumps(data), encoding="utf-8")
                time.sleep(SLEEP)
                return data
        except Exception:
            pass
        time.sleep(SLEEP)
    raise RuntimeError(f"Failed to fetch {url}")

# ---------- schema ----------
DDL = """
CREATE TABLE IF NOT EXISTS item_effects (
  item_name        TEXT PRIMARY KEY COLLATE NOCASE, -- pokeapi slug, e.g. 'leftovers'
  display_name     TEXT,                             -- 'Leftovers'
  pocket           TEXT,                             -- e.g. 'misc'
  category         TEXT,                             -- e.g. 'held-items'
  attributes_json  TEXT,                             -- PokeAPI attributes list
  short_effect     TEXT,                             -- short human text (en)
  effect_text      TEXT,                             -- full human text (en)
  competitive_json TEXT                              -- normalized, structured battle effects
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_item_effects_name ON item_effects(item_name COLLATE NOCASE);
"""

UPSERT = """
INSERT INTO item_effects (item_name, display_name, pocket, category, attributes_json, short_effect, effect_text, competitive_json)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(item_name) DO UPDATE SET
  display_name    = COALESCE(excluded.display_name, display_name),
  pocket          = COALESCE(excluded.pocket, pocket),
  category        = COALESCE(excluded.category, category),
  attributes_json = COALESCE(excluded.attributes_json, attributes_json),
  short_effect    = COALESCE(NULLIF(excluded.short_effect,''), short_effect),
  effect_text     = COALESCE(NULLIF(excluded.effect_text,''), effect_text),
  competitive_json= COALESCE(NULLIF(excluded.competitive_json,''), competitive_json);
"""

# ---------- competitive mapping (curated) ----------
# These are the things your battle engine can read directly.
CURATED: Dict[str, Dict[str, Any]] = {
    # Regen
    "leftovers":        {"heal_each_turn": {"fraction": [1, 16]}},
    "black-sludge":     {"heal_each_turn": {"fraction": [1, 16], "poison_only": True}, "damage_if_non_poison": {"fraction": [1, 8]}},

    # Choice items
    "choice-band":      {"choice_lock": True, "modifiers": {"atk_mul": [3, 2]}},
    "choice-specs":     {"choice_lock": True, "modifiers": {"spa_mul": [3, 2]}},
    "choice-scarf":     {"choice_lock": True, "modifiers": {"spe_mul": [3, 2]}},

    # General power items
    "life-orb":         {"damage_mul": [13,10], "recoil_maxhp_frac": [1,10]},  # +30% damage, 10% recoil
    "muscle-band":      {"modifiers": {"phys_mul": [11,10]}},                   # ~10% phys
    "wise-glasses":     {"modifiers": {"spec_mul": [11,10]}},                   # ~10% spec
    "assault-vest":     {"modifiers": {"spd_mul": [3,2]}, "block_status_moves": True},
    "eviolite":         {"modifiers": {"def_mul": [3,2], "spd_mul": [3,2]}, "requires_not_fully_evolved": True},

    # Survival
    "focus-sash":       {"survive_fatal_at_full": True},
    "focus-band":       {"chance_survive_fatal": 0.1},

    # Screens extender
    "light-clay":       {"screen_turns_plus": 3},

    # Weather rocks
    "damp-rock":        {"extend_weather": {"weather": "Rain", "turns_plus": 3}},
    "heat-rock":        {"extend_weather": {"weather": "Sun", "turns_plus": 3}},
    "smooth-rock":      {"extend_weather": {"weather": "Sandstorm", "turns_plus": 3}},
    "icy-rock":         {"extend_weather": {"weather": "Hail", "turns_plus": 3}},
    "utility-umbrella": {"ignore_weather_damage": True},

    # Type-boost plates / orbs (sample—engine can apply to all by name prefix)
    "draco-plate":      {"stab_type_boost": {"type": "Dragon", "mul": [6,5]}},
    "charcoal":         {"stab_type_boost": {"type": "Fire",   "mul": [6,5]}},
    "mystic-water":     {"stab_type_boost": {"type": "Water",  "mul": [6,5]}},
    "miracle-seed":     {"stab_type_boost": {"type": "Grass",  "mul": [6,5]}},
    "never-melt-ice":   {"stab_type_boost": {"type": "Ice",    "mul": [6,5]}},
    "magnet":           {"stab_type_boost": {"type": "Electric","mul": [6,5]}},
    "hard-stone":       {"stab_type_boost": {"type": "Rock",   "mul": [6,5]}},
    "black-belt":       {"stab_type_boost": {"type": "Fighting","mul": [6,5]}},
    "silk-scarf":       {"stab_type_boost": {"type": "Normal", "mul": [6,5]}},
    "spell-tag":        {"stab_type_boost": {"type": "Ghost",  "mul": [6,5]}},
    "sharp-beak":       {"stab_type_boost": {"type": "Flying", "mul": [6,5]}},
    "poison-barb":      {"stab_type_boost": {"type": "Poison", "mul": [6,5]}},
    "soft-sand":        {"stab_type_boost": {"type": "Ground", "mul": [6,5]}},
    "metal-coat":       {"stab_type_boost": {"type": "Steel",  "mul": [6,5]}},
    "twisted-spoon":    {"stab_type_boost": {"type": "Psychic","mul": [6,5]}},
    "silver-powder":    {"stab_type_boost": {"type": "Bug",    "mul": [6,5]}},
    "dragon-fang":      {"stab_type_boost": {"type": "Dragon", "mul": [6,5]}},

    # Orbs / terrain / room (examples)
    "iron-ball":        {"modifiers": {"spe_mul": [1,2]}, "grounded": True},
    "flame-orb":        {"self_status": "BRN"},
    "toxic-orb":        {"self_status": "PSN_BAD"},
}

# ---------- text helpers ----------
def get_lang_entry(entries: List[dict], key: str = "effect_entries", lang: str = "en") -> Tuple[str, str]:
    effect = short = ""
    for e in entries:
        if e.get("language", {}).get("name") == lang:
            effect = e.get("effect", "") or effect
            short  = e.get("short_effect", "") or short
    return effect, short

def display_name(slug: str) -> str:
    return slug.replace("-", " ").title()

# crude heuristics to add structured info if not curated
def heuristics(slug: str, effect_text: str, short_effect: str) -> Dict[str, Any] | None:
    txt = f"{effect_text} {short_effect}".lower()

    # type-boost 20% pattern
    m = re.search(r"power of .* (.+?)-type moves .* (10|20|30)%", txt)
    if m:
        t = m.group(1).strip().replace(" ", "-").replace("-type", "").title()
        pct = int(m.group(2))
        num = 10 + pct  # 10% -> 11/10, 20% -> 6/5, 30% -> 13/10 (we’ll map below)
        fr = {10: [11,10], 20: [6,5], 30: [13,10]}[pct]
        return {"stab_type_boost": {"type": t, "mul": fr}}

    if "recovers hp every turn" in txt or "restores the holder's hp every turn" in txt:
        return {"heal_each_turn": {"fraction": [1, 16]}}

    if "boosts holder's attack but allows only the use of one move" in txt or "only the use of one move" in txt:
        return {"choice_lock": True, "modifiers": {"atk_mul": [3,2]}}

    if "special attack" in txt and "only the use of one move" in txt:
        return {"choice_lock": True, "modifiers": {"spa_mul": [3,2]}}

    if "speed" in txt and "only the use of one move" in txt:
        return {"choice_lock": True, "modifiers": {"spe_mul": [3,2]}}

    if "survive" in txt and "1 hp" in txt and ("full hp" in txt or "full-health" in txt):
        return {"survive_fatal_at_full": True}

    if "increases the power of moves" in txt and "but at the cost of some hp" in txt:
        return {"damage_mul": [13,10], "recoil_maxhp_frac": [1,10]}

    return None

# ---------- ingest ----------
def seed_items(dbp: Path, only_new: bool = False) -> Tuple[int, int]:
    con = sqlite3.connect(dbp); con.row_factory = sqlite3.Row
    with con:
        # ensure table
        for stmt in filter(None, DDL.split(";")):
            con.execute(stmt.strip())

        # index of all items
        items_idx = fetch_json(f"{API}/item?limit=20000", "items-index")
        results = items_idx.get("results", [])

        updated = 0
        total = 0

        # get existing keys if only_new is desired
        existing = set()
        if only_new:
            for r in con.execute("SELECT item_name FROM item_effects").fetchall():
                existing.add((r["item_name"] or "").lower())

        for i, ent in enumerate(results, 1):
            slug = ent["name"]  # pokeapi slug
            if only_new and slug in existing:
                continue

            try:
                item = fetch_json(f"{API}/item/{slug}", f"item-{slug}")
            except Exception as e:
                print(f"⚠️  skip {slug}: fetch failed ({e})")
                continue

            # human text
            effect_text, short_effect = get_lang_entry(item.get("effect_entries", []))
            pocket = (item.get("pocket", {}) or {}).get("name")
            category = (item.get("category", {}) or {}).get("name")
            attributes = [a["name"] for a in item.get("attributes", [])]

            comp = CURATED.get(slug)
            if not comp:
                comp = heuristics(slug, effect_text, short_effect)

            con.execute(
                UPSERT,
                (
                    slug,
                    display_name(slug),
                    pocket,
                    category,
                    json.dumps(attributes, ensure_ascii=False),
                    short_effect or "",
                    effect_text or "",
                    json.dumps(comp, ensure_ascii=False) if comp else "",
                ),
            )
            updated += 1
            total += 1
            if updated % 100 == 0:
                print(f"…upserted {updated} items")

    return updated, total

def main():
    ap = argparse.ArgumentParser(description="Seed/Update item_effects table from PokeAPI.")
    ap.add_argument("--db", type=str, help="Path to myuu.db (overrides auto-detect)")
    ap.add_argument("--only-new", action="store_true", help="Skip rows that already exist")
    args = ap.parse_args()

    dbp = find_db(args.db)
    if not dbp:
        raise SystemExit("❌ Could not find myuu.db. Use --db or set MYUU_DB.")
    print("🔗 DB:", dbp)

    upserted, total = seed_items(dbp, only_new=args.only_new)
    with sqlite3.connect(dbp) as con:
        n = con.execute("SELECT COUNT(*) FROM item_effects").fetchone()[0]
    print(f"✅ Done. Upserted {upserted} rows. item_effects now has {n} items.")

if __name__ == "__main__":
    main()
