#!/usr/bin/env python3
"""
Preload db_cache with pokedex, moves, items, and static tables
(learnsets, pokedex_forms, rulesets, config, format_rules, mega_forms,
move_generation_stats, gigantamax, item_effects, pvp_formats, pvp_format_rules).

Run standalone:
  python tools/cache_everything.py

Or call warm_cache() from the bot at startup:
  from tools.cache_everything import warm_cache
  await warm_cache()
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Load .env before importing db
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from lib import db
from lib import db_cache


def _row_to_dict(row) -> dict | None:
    if hasattr(row, "keys"):
        return dict(row)
    return None


# Static tables to cache (full dump). config -> store as dict key->value; rest -> list[dict].
STATIC_TABLES = [
    "learnsets",
    "pokedex_forms",
    "rulesets",
    "format_rules",
    "mega_forms",
    "mega_evolution",
    "move_generation_stats",
    "gigantamax",
    "item_effects",
    "pvp_formats",
    "pvp_format_rules",
]


async def _load_table(conn, name: str):
    """Load table as list[dict]. Returns [] on error or missing table."""
    try:
        cur = await conn.execute(f"SELECT * FROM {name}")
        rows = await cur.fetchall()
        await cur.close()
        out = []
        for r in rows:
            d = _row_to_dict(r)
            if d:
                out.append(d)
        return out
    except Exception:
        return []


async def _load_config(conn):
    """Load config as dict key -> value."""
    try:
        cur = await conn.execute("SELECT key, value FROM config")
        rows = await cur.fetchall()
        await cur.close()
        out = {}
        for r in rows:
            d = _row_to_dict(r)
            if d and d.get("key") is not None:
                out[str(d["key"])] = str(d.get("value") or "")
        return out
    except Exception:
        return {}


async def warm_cache() -> dict[str, int]:
    """
    Fetch pokedex, moves, items, and static tables; populate db_cache.
    Returns counts: {"pokedex": n, "moves": n, "items": n, "learnsets": n, ...}.

    These caches feed PvP (engine, panel, renderer): moves, move_generation_stats,
    pokedex, pokedex_forms, etc. Reduces DB round-trips when using cloud DB.

    NOTE: We never cache the pokemons table here. Party/team data is cached
    only per battle (at battle start, cleared at battle end) so it stays
    correct when users change teams (e.g. box a Pokémon).
    """
    counts: dict[str, int] = {"pokedex": 0, "moves": 0, "items": 0}
    for t in STATIC_TABLES:
        counts[t] = 0
    counts["config"] = 0

    conn = await db.connect()

    try:
        # Pokedex: cache by id and by name
        cur = await conn.execute("SELECT * FROM pokedex")
        rows = await cur.fetchall()
        await cur.close()
        for row in rows:
            d = _row_to_dict(row)
            if not d:
                continue
            db_cache.set_cached_pokedex(str(d["id"]), d)
            if d.get("name"):
                db_cache.set_cached_pokedex(d["name"], d)
            counts["pokedex"] += 1

        # Moves: cache by name, normalized name, and id (for lookups from moves_loader, db_move_effects, etc.)
        cur = await conn.execute("SELECT * FROM moves")
        rows = await cur.fetchall()
        await cur.close()
        for row in rows:
            d = _row_to_dict(row)
            if not d:
                continue
            name = d.get("name")
            if name:
                db_cache.set_cached_move(name, d)
                norm = name.lower().replace(" ", "-").strip()
                if norm and norm != name:
                    db_cache.set_cached_move(norm, d)
            if d.get("id") is not None:
                db_cache.set_cached_move(str(d["id"]), d)
            counts["moves"] += 1

        # Items: cache by id and by name
        cur = await conn.execute("SELECT * FROM items")
        rows = await cur.fetchall()
        await cur.close()
        items_table = []
        for row in rows:
            d = _row_to_dict(row)
            if not d:
                continue
            items_table.append(d)
            item_id = d.get("id")
            name = d.get("name")
            if item_id:
                db_cache.set_cached_item(str(item_id), d)
            if name and name != item_id:
                db_cache.set_cached_item(name, d)
            counts["items"] += 1
        if items_table:
            db_cache.set_cached_table("items", items_table)

        # Static tables (full dump)
        for name in STATIC_TABLES:
            rows = await _load_table(conn, name)
            if rows:
                db_cache.set_cached_table(name, rows)
                counts[name] = len(rows)

        # Config: key -> value dict
        cfg = await _load_config(conn)
        if cfg:
            db_cache.set_cached_table("config", cfg)
            counts["config"] = len(cfg)

    finally:
        await conn.close()

    return counts


async def main() -> None:
    print("Warming db_cache (pokedex, moves, items, static tables)...")
    counts = await warm_cache()
    stats = db_cache.get_cache_stats()
    print(f"  Pokedex: {counts['pokedex']} species")
    print(f"  Moves:   {counts['moves']}")
    print(f"  Items:   {counts['items']}")
    for t in STATIC_TABLES + ["config"]:
        n = counts.get(t, 0)
        if n:
            print(f"  {t}: {n}")
    print(f"  Cache totals: {stats['total']} entries (pokedex={stats['pokedex']}, moves={stats['moves']}, items={stats['items']}, static_tables={stats.get('static_tables', 0)})")
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
