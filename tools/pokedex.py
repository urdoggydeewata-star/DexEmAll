# tools/extend_pokedex_from_pokeapi.py
from __future__ import annotations
import os, re, json, time, argparse, sqlite3
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import requests

API = "https://pokeapi.co/api/v2"
CACHE_DIR = Path("cache/pokeapi"); CACHE_DIR.mkdir(parents=True, exist_ok=True)
SLEEP = 0.2

GEN_MAP = {
    "generation-i":1,"generation-ii":2,"generation-iii":3,"generation-iv":4,
    "generation-v":5,"generation-vi":6,"generation-vii":7,"generation-viii":8,"generation-ix":9
}

DEX_DDL = """
CREATE TABLE IF NOT EXISTS dex_species (
  species        TEXT PRIMARY KEY COLLATE NOCASE,
  display_name   TEXT,
  gen            INTEGER,
  type1          TEXT,
  type2          TEXT,
  base_hp        INTEGER,
  base_atk       INTEGER,
  base_def       INTEGER,
  base_spa       INTEGER,
  base_spd       INTEGER,
  base_spe       INTEGER,
  abilities_json TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_dex_species_name ON dex_species(species COLLATE NOCASE);
"""

POKEDEX_DDL = """
CREATE TABLE IF NOT EXISTS pokedex (
  name           TEXT PRIMARY KEY COLLATE NOCASE,
  introduced_in  INTEGER,
  types          TEXT,   -- JSON array
  stats          TEXT,   -- JSON object {hp,atk,def,spa,spd,spe}
  abilities      TEXT    -- JSON array
);
"""

UPSERT_DEX = """
INSERT INTO dex_species (species, display_name, gen, type1, type2,
  base_hp, base_atk, base_def, base_spa, base_spd, base_spe, abilities_json)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(species) DO UPDATE SET
  display_name=COALESCE(excluded.display_name, display_name),
  gen=COALESCE(excluded.gen, gen),
  type1=COALESCE(excluded.type1, type1),
  type2=COALESCE(excluded.type2, type2),
  base_hp=COALESCE(excluded.base_hp, base_hp),
  base_atk=COALESCE(excluded.base_atk, base_atk),
  base_def=COALESCE(excluded.base_def, base_def),
  base_spa=COALESCE(excluded.base_spa, base_spa),
  base_spd=COALESCE(excluded.base_spd, base_spd),
  base_spe=COALESCE(excluded.base_spe, base_spe),
  abilities_json=COALESCE(excluded.abilities_json, abilities_json);
"""

UPSERT_POKEDEX = """
INSERT INTO pokedex (name, introduced_in, types, stats, abilities)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(name) DO UPDATE SET
  introduced_in = COALESCE(pokedex.introduced_in, excluded.introduced_in),
  types         = CASE WHEN pokedex.types IS NULL OR pokedex.types='' THEN excluded.types ELSE pokedex.types END,
  stats         = CASE WHEN pokedex.stats IS NULL OR pokedex.stats='' THEN excluded.stats ELSE pokedex.stats END,
  abilities     = CASE WHEN pokedex.abilities IS NULL OR pokedex.abilities='' THEN excluded.abilities ELSE pokedex.abilities END;
"""

def find_db(explicit: Optional[str]) -> Optional[Path]:
    if explicit and Path(explicit).exists(): return Path(explicit)
    env = os.getenv("MYUU_DB")
    if env and Path(env).exists(): return Path(env)
    here = Path.cwd()
    for p in [here/"myuu.db", here/"data"/"myuu.db", Path(__file__).resolve().parents[1]/"myuu.db"]:
        if p.exists(): return p
    # last-resort: search upwards for *.db
    root = Path(__file__).resolve().parents[2]
    for p in root.rglob("*.db"):
        if "venv" in str(p).lower() or "node_modules" in str(p).lower(): continue
        return p
    return None

def cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"

def fetch_json(url: str, key: str) -> Dict[str, Any]:
    cp = cache_path(key)
    if cp.exists(): return json.loads(cp.read_text(encoding="utf-8"))
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

def species_index() -> List[str]:
    data = fetch_json(f"{API}/pokemon-species?limit=20000", "species-index")
    return [e["name"] for e in data.get("results", [])]

def slugify(name: str) -> str:
    s = name.strip().lower().replace("♀","-f").replace("♂","-m").replace("é","e")
    s = s.replace(".", "").replace("'", ""); s = re.sub(r"[:!?\u200d]", "", s)
    s = re.sub(r"\s+","-", s)
    return s

def disp(name: str) -> str:
    return name.replace("-"," ").title()

def parse_gen(spec: Dict[str,Any]) -> Optional[int]:
    g = spec.get("generation") or {}
    return GEN_MAP.get(g.get("name"))

def parse_types(poke: Dict[str,Any]) -> Tuple[Optional[str], Optional[str], List[str]]:
    t1=t2=None; arr=[]
    for t in poke.get("types", []):
        nm=t["type"]["name"].replace("-"," ").title()
        arr.append(nm)
        if t["slot"]==1: t1=nm
        elif t["slot"]==2: t2=nm
    return t1, t2, arr

def parse_stats(poke: Dict[str,Any]) -> Dict[str,int]:
    m = {"hp":None,"atk":None,"def":None,"spa":None,"spd":None,"spe":None}
    d = {"hp":"hp","attack":"atk","defense":"def","special-attack":"spa","special-defense":"spd","speed":"spe"}
    for s in poke.get("stats", []):
        k = d.get(s["stat"]["name"]); 
        if k: m[k] = int(s["base_stat"])
    return m

def parse_abilities(poke: Dict[str,Any]) -> List[str]:
    vals=[]
    for a in poke.get("abilities", []):
        vals.append(a["ability"]["name"].replace("-"," ").title())
    return vals

def ensure_tables(con: sqlite3.Connection):
    for stmt in filter(None, DEX_DDL.split(";")):
        con.execute(stmt.strip())
    for stmt in filter(None, POKEDEX_DDL.split(";")):
        con.execute(stmt.strip())

def main():
    ap = argparse.ArgumentParser(description="Extend/complete pokedex + dex_species using PokeAPI.")
    ap.add_argument("--db", type=str, help="Path to myuu.db")
    ap.add_argument("--gen", type=int, help="Only ingest this generation (1..9)")
    args = ap.parse_args()

    dbp = find_db(args.db)
    if not dbp: raise SystemExit("❌ Could not find myuu.db. Use --db or set MYUU_DB.")
    print("🔗 DB:", dbp)

    con = sqlite3.connect(dbp); con.row_factory = sqlite3.Row
    with con:
        ensure_tables(con)
        idx = species_index()
        upserted_dex = upserted_pok = 0

        # existing names in pokedex to avoid refetch unless needed
        existing = { (r["name"] or "").strip().lower()
                     for r in con.execute("SELECT name FROM pokedex").fetchall() }

        for raw in idx:
            # species filter by gen after fetching species detail
            try:
                spec = fetch_json(f"{API}/pokemon-species/{raw}", f"species-{raw}")
            except Exception as e:
                print(f"⚠️ skip {raw}: species fetch failed ({e})"); continue
            gen = parse_gen(spec)
            if args.gen and gen != args.gen:
                continue

            # find default variety for /pokemon
            def_poke = None
            for v in spec.get("varieties", []):
                if v.get("is_default"): def_poke = v["pokemon"]["name"]; break
            if not def_poke: def_poke = raw

            try:
                poke = fetch_json(f"{API}/pokemon/{def_poke}", f"pokemon-{def_poke}")
            except Exception as e:
                print(f"⚠️ skip {raw}: pokemon fetch failed ({e})"); continue

            t1, t2, tarr = parse_types(poke)
            stats = parse_stats(poke)
            abilities = parse_abilities(poke)

            # Upsert dex_species (normalized)
            con.execute(UPSERT_DEX, (
                raw, disp(raw), gen, t1, t2,
                stats["hp"], stats["atk"], stats["def"], stats["spa"], stats["spd"], stats["spe"],
                json.dumps(abilities, ensure_ascii=False)
            ))
            upserted_dex += 1

            # Upsert pokedex (compat) — do not overwrite non-empty fields
            types_json = json.dumps(tarr, ensure_ascii=False)
            stats_json = json.dumps(stats, ensure_ascii=False)
            abilities_json = json.dumps(abilities, ensure_ascii=False)

            con.execute(UPSERT_POKEDEX, (
                raw, gen, types_json, stats_json, abilities_json
            ))
            upserted_pok += 1

            if (upserted_dex % 100) == 0:
                print(f"…upserted {upserted_dex} species")

    # small report
    with con:
        dex_count = con.execute("SELECT COUNT(*) AS n FROM dex_species").fetchone()["n"]
        pok_count = con.execute("SELECT COUNT(*) AS n FROM pokedex").fetchone()["n"]
    print(f"✅ Done. dex_species: {dex_count} rows • pokedex: {pok_count} rows")

if __name__ == "__main__":
    main()
