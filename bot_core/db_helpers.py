"""DB schema helpers, transaction utilities, and wipe functions. Used by pokebot."""
from __future__ import annotations

from typing import Any

import lib.db as db

try:
    from lib import db_cache
except ImportError:
    db_cache = None  # type: ignore

try:
    from tools.cache_everything import warm_cache
except ImportError:
    warm_cache = None  # type: ignore


async def count_rows(conn: Any, table: str, where_sql: str = "", args: tuple = ()) -> int:
    """Count rows in a table with optional WHERE clause."""
    cur = await conn.execute(f"SELECT COUNT(*) AS c FROM {table} {where_sql}".strip(), args)
    row = await cur.fetchone()
    await cur.close()
    return int(row["c"] if row else 0)


_PG_POKEMONS_COLS_OK = False


async def ensure_pg_pokemons_columns(conn: Any) -> None:
    """Ensure optional PG columns exist on pokemons table."""
    global _PG_POKEMONS_COLS_OK
    if _PG_POKEMONS_COLS_OK or not getattr(db, "DB_IS_POSTGRES", False):
        return
    try:
        await conn.execute("ALTER TABLE pokemons ADD COLUMN IF NOT EXISTS hp_now INTEGER")
        await conn.execute("ALTER TABLE pokemons ADD COLUMN IF NOT EXISTS moves_pp JSONB")
        await conn.execute("ALTER TABLE pokemons ADD COLUMN IF NOT EXISTS moves_pp_min JSONB")
        await conn.execute("ALTER TABLE pokemons ADD COLUMN IF NOT EXISTS moves_pp_max JSONB")
        await conn.execute("ALTER TABLE pokemons ADD COLUMN IF NOT EXISTS shiny INTEGER NOT NULL DEFAULT 0")
        await conn.execute("ALTER TABLE pokemons ADD COLUMN IF NOT EXISTS is_hidden_ability INTEGER NOT NULL DEFAULT 0")
        await conn.execute("ALTER TABLE pokemons ADD COLUMN IF NOT EXISTS status TEXT")
        _PG_POKEMONS_COLS_OK = True
    except Exception:
        pass


async def pg_pokemons_column_flags(conn: Any) -> dict:
    """Return existence flags for optional PG columns on pokemons."""
    flags = {
        "hp_now": True,
        "moves_pp": True,
        "moves_pp_min": False,
        "moves_pp_max": False,
        "shiny": True,
        "is_hidden_ability": True,
    }
    if not getattr(db, "DB_IS_POSTGRES", False):
        return flags
    for col in ["hp_now", "moves_pp", "moves_pp_min", "moves_pp_max", "shiny", "is_hidden_ability"]:
        try:
            flags[col] = await db._column_exists(conn, "pokemons", col)
        except Exception:
            flags[col] = col in ("hp_now", "moves_pp", "shiny", "is_hidden_ability")
    return flags


async def tx_begin(conn: Any) -> None:
    """Begin transaction."""
    await conn.execute("BEGIN")


async def tx_commit(conn: Any) -> None:
    """Commit transaction."""
    if getattr(db, "DB_IS_POSTGRES", False):
        await conn.execute("COMMIT")
    else:
        await conn.commit()


async def tx_rollback(conn: Any) -> None:
    """Rollback transaction."""
    if getattr(db, "DB_IS_POSTGRES", False):
        await conn.execute("ROLLBACK")
    else:
        await conn.rollback()


async def wipe_user(conn: Any, uid: str) -> dict:
    """Remove all data for one user. Returns count stats."""
    stats = {
        "pokemons": await count_rows(conn, "pokemons", "WHERE owner_id=?", (uid,)),
        "user_items": await count_rows(conn, "user_items", "WHERE owner_id=?", (uid,)),
        "user_equipment": await count_rows(conn, "user_equipment", "WHERE owner_id=?", (uid,)),
        "user_boxes": await count_rows(conn, "user_boxes", "WHERE owner_id=?", (uid,)),
        "user_meta": await count_rows(conn, "user_meta", "WHERE owner_id=?", (uid,)),
        "user_rulesets": await count_rows(conn, "user_rulesets", "WHERE user_id=?", (uid,)),
        "event_log": await count_rows(conn, "event_log", "WHERE user_id=?", (uid,)),
        "users": await count_rows(conn, "users", "WHERE user_id=?", (uid,)),
    }
    await tx_begin(conn)
    try:
        if not getattr(db, "DB_IS_POSTGRES", False):
            await conn.execute("PRAGMA foreign_keys = ON")
        await conn.execute("DELETE FROM pokemons WHERE owner_id=?", (uid,))
        await conn.execute("DELETE FROM user_items WHERE owner_id=?", (uid,))
        await conn.execute("DELETE FROM user_equipment WHERE owner_id=?", (uid,))
        await conn.execute("DELETE FROM user_boxes WHERE owner_id=?", (uid,))
        await conn.execute("DELETE FROM user_meta WHERE owner_id=?", (uid,))
        await conn.execute("DELETE FROM user_rulesets WHERE user_id=?", (uid,))
        await conn.execute("DELETE FROM event_log WHERE user_id=?", (uid,))
        await conn.execute("DELETE FROM users WHERE user_id=?", (uid,))
        await tx_commit(conn)
        db.invalidate_pokemons_cache(uid)
        db.invalidate_bag_cache(uid)
    except Exception:
        await tx_rollback(conn)
        raise
    return stats


async def recache_after_wipe() -> None:
    """Clear and warm caches after a wipe."""
    try:
        if db_cache is not None:
            db_cache.clear_cache()
        if warm_cache is not None:
            await warm_cache()
    except Exception:
        pass


async def wipe_all(conn: Any) -> dict:
    """Delete ALL player data. Returns count stats."""
    stats = {
        "pokemons": await count_rows(conn, "pokemons"),
        "user_items": await count_rows(conn, "user_items"),
        "user_equipment": await count_rows(conn, "user_equipment"),
        "user_boxes": await count_rows(conn, "user_boxes"),
        "user_meta": await count_rows(conn, "user_meta"),
        "user_rulesets": await count_rows(conn, "user_rulesets"),
        "users": await count_rows(conn, "users"),
    }
    await tx_begin(conn)
    try:
        await conn.execute("DELETE FROM pokemons")
        await conn.execute("DELETE FROM user_items")
        await conn.execute("DELETE FROM user_equipment")
        await conn.execute("DELETE FROM user_boxes")
        await conn.execute("DELETE FROM user_meta")
        await conn.execute("DELETE FROM user_rulesets")
        await conn.execute("DELETE FROM users")
        await tx_commit(conn)
        db.clear_all_pokemons_cache()
        db.clear_all_bag_cache()
    except Exception:
        await tx_rollback(conn)
        raise
    return stats
