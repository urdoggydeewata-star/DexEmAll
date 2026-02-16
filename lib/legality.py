from .rules import rules_for
from . import db

def species_allowed(entry: dict, gen: int) -> bool:
    r = rules_for(gen)
    if entry.get("introduced_in") and entry["introduced_in"] > gen:
        return False
    name = entry["name"]
    if "-alola" in name and not r.allow_alolan: return False
    if "-galar" in name and not r.allow_galarian: return False
    if "-hisui" in name and not r.allow_hisuian: return False
    if "-paldea" in name and not r.allow_paldean: return False
    return True


def _legal_moves_from_cache(species_id: int, gen: int):
    """Build legal_moves-style rows from cached learnsets + moves. Returns [] if cache miss."""
    try:
        from . import db_cache
    except ImportError:
        return []
    learnsets = db_cache.get_cached_learnsets()
    if not learnsets:
        return []
    seen: set[tuple[int, str, int]] = set()
    out = []
    for ls in learnsets:
        if ls.get("species_id") != species_id:
            continue
        g = ls.get("generation")
        if g is None or int(g) > gen:
            continue
        move_id = ls.get("move_id")
        if move_id is None:
            continue
        method = str(ls.get("method") or "")
        lv = ls.get("level_learned")
        lv = -1 if lv is None else int(lv)
        key = (int(move_id), method, lv)
        if key in seen:
            continue
        seen.add(key)
        m = db_cache.get_cached_move(str(move_id))
        if not m:
            continue
        out.append({
            "name": m.get("name") or "",
            "type": m.get("type"),
            "damage_class": m.get("damage_class"),
            "power": m.get("power"),
            "accuracy": m.get("accuracy"),
            "pp": m.get("pp"),
            "method": method,
            "level_learned": lv,
            "introduced_in": m.get("introduced_in"),
        })
    return out


async def legal_moves(species_id: int, gen: int):
    # returns list of dict rows for moves legal up to that generation
    rows = _legal_moves_from_cache(species_id, gen)
    if rows:
        return rows
    conn = await db.connect()
    try:
        cur = await conn.execute("""
          SELECT m.name, m.type, m.damage_class, m.power, m.accuracy, m.pp,
                 ls.method, COALESCE(ls.level_learned, -1) AS level_learned, m.introduced_in
          FROM learnsets ls
          JOIN moves m ON m.id = ls.move_id
          WHERE ls.species_id = ? AND ls.generation <= ?
          GROUP BY m.id, ls.method, COALESCE(ls.level_learned, -1), m.name, m.type, m.damage_class, m.power, m.accuracy, m.pp, m.introduced_in
        """, (species_id, gen))
        rows = [dict(r) for r in await cur.fetchall()]
        await cur.close()
        return rows
    finally:
        await conn.close()
