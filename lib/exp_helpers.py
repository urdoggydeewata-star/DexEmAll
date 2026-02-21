"""Experience and growth rate helpers."""
from __future__ import annotations

_VALID_EXP_GROUPS = frozenset({"erratic", "fast", "medium_fast", "medium_slow", "slow", "fluctuating"})


def normalize_growth_rate_to_exp_group(growth_rate: str | None) -> str:
    """Map pokedex.growth_rate to exp_group code."""
    if not growth_rate or not str(growth_rate).strip():
        return "medium_fast"
    s = str(growth_rate).strip().lower().replace(" ", "_").replace("-", "_")
    return s if s in _VALID_EXP_GROUPS else "medium_fast"


async def get_exp_group_for_species(conn, species: str) -> str:
    """Get exp_group for species from pokedex.growth_rate."""
    if not species or not str(species).strip():
        return "medium_fast"
    try:
        cur = await conn.execute(
            "SELECT growth_rate FROM pokedex WHERE LOWER(name) = LOWER(?) OR LOWER(REPLACE(name,' ','-')) = LOWER(?) LIMIT 1",
            (str(species).strip(), str(species).strip().replace(" ", "-")),
        )
        row = await cur.fetchone()
        await cur.close()
        if row and row.get("growth_rate") is not None:
            return normalize_growth_rate_to_exp_group(str(row["growth_rate"]))
    except Exception:
        pass
    return "medium_fast"


async def get_exp_total_for_level(conn, exp_group: str, level: int) -> int:
    """Return exp_total from exp_requirements for (exp_group, level)."""
    try:
        from lib import db_cache
        if db_cache is not None:
            rows = db_cache.get_cached_exp_requirements()
            if rows:
                key = exp_group.strip().lower().replace(" ", "_")
                for r in rows:
                    if str(r.get("group_code") or "").strip().lower().replace(" ", "_") == key and int(r.get("level") or 0) == level:
                        v = r.get("exp_total")
                        return int(v) if v is not None else 0
    except Exception:
        pass
    try:
        cur = await conn.execute(
            "SELECT exp_total FROM exp_requirements WHERE group_code = ? AND level = ? LIMIT 1",
            (exp_group.strip().lower().replace(" ", "_"), level),
        )
        row = await cur.fetchone()
        await cur.close()
        return int(row["exp_total"]) if row and row.get("exp_total") is not None else 0
    except Exception:
        return 0
