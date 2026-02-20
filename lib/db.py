# lib/db.py
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import datetime as dt
from contextlib import asynccontextmanager
from typing import Optional, Sequence, List, Dict, Any, Tuple, List
import re
from .market_catalog import resolve_market_key as _catalog_resolve_market_key

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_env = _ROOT / ".env"
if _env.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env)
    except ImportError:
        pass

# Performance-oriented defaults (can be overridden by real env vars).
os.environ.setdefault("DB_AUTO_TASK_SESSION", "1")
os.environ.setdefault("DB_POOL_ACQUIRE_TIMEOUT", "12")
os.environ.setdefault("DB_POOL_ACQUIRE_RETRIES", "2")

# Import caching module
try:
    from . import db_cache
    _CACHE_ENABLED = True
except ImportError:
    _CACHE_ENABLED = False

# Use cloud PostgreSQL only. DATABASE_URL or POSTGRES_DSN must be set in .env.
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL or POSTGRES_DSN must be set (e.g. in .env) to use the cloud database. "
        "Add: DATABASE_URL=postgresql://user:pass@host:port/dbname"
    )
from . import pg_aiosqlite as aiosqlite
DB_IS_POSTGRES = True

# ---------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------
ROOT = _ROOT
SCHEMA_PATH = ROOT / "db" / "schema_pg.sql"

# DB access rule (see DATABASE_CONTEXT_EVERYTHING.md): use async with session() as conn:
# for all DB work; never bare connect() without guaranteed close.

# ---------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------
async def connect() -> aiosqlite.Connection:
    """
    Open a new async connection to the cloud PostgreSQL database.
    Each call creates a new connection to avoid blocking.
    Callers should close the connection when done, or use it as a context manager.

    OPTIMIZED FOR MAXIMUM CONCURRENCY - Multiple users can access simultaneously.
    """
    return await aiosqlite.connect()


async def warm_pool(n: Optional[int] = None) -> Optional[int]:
    """
    Warm the asyncpg pool (if supported by the backend). Returns number warmed or None.
    """
    warm = getattr(aiosqlite, "warm_pool", None)
    if warm is None:
        return None
    return await warm(n)


@asynccontextmanager
async def session() -> aiosqlite.Connection:
    """
    Reuse a single connection for multiple queries within this async context.
    Falls back to a normal connection if the backend doesn't support sessions.
    """
    sess = getattr(aiosqlite, "session", None)
    if sess is not None:
        async with sess() as conn:
            yield conn
        return

    conn = await connect()
    try:
        yield conn
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def close() -> None:
    """No-op for compatibility. Connections should be closed by callers."""
    pass


# ---------- meta helpers that work with an EXISTING connection ----------
async def _table_exists(conn: aiosqlite.Connection, table: str) -> bool:
    cur = await conn.execute(
        "SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = $1 LIMIT 1",
        (table,),
    )
    row = await cur.fetchone()
    await cur.close()
    return row is not None

async def _column_exists(conn: aiosqlite.Connection, table: str, column: str) -> bool:
    cur = await conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = $1 AND column_name = $2",
        (table, column)
    )
    row = await cur.fetchone()
    await cur.close()
    return row is not None
# ---------------------------------------------------------------------
# Schema init & migrations
# ---------------------------------------------------------------------
async def migrate_monsters_to_pokemons() -> None:
    """No-op: PostgreSQL schema uses pokemons from the start."""
    return


async def ensure_pokemon_stat_columns() -> None:
    """PostgreSQL schema is managed via schema_pg.sql; no per-column migration needed."""
    return


async def ensure_schema_migrations() -> None:
    """
    Safe, idempotent migrations the bot expects:
      - items.emoji / items.icon_url
      - users.starter
      - user_meta table (owner_id, money, bag_pages)
      - user_items
      - adventure_state table
    """
    conn = await connect()
    try:
        create_sql = {
            "adventure_state": """
                CREATE TABLE IF NOT EXISTS adventure_state (
                  owner_id TEXT PRIMARY KEY,
                  data     JSONB,
                  FOREIGN KEY (owner_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
            """,
            "team_presets": """
                CREATE TABLE IF NOT EXISTS team_presets (
                  owner_id TEXT NOT NULL,
                  preset_name TEXT NOT NULL,
                  team_data JSONB NOT NULL,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  PRIMARY KEY (owner_id, preset_name),
                  FOREIGN KEY (owner_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
            """,
            "beta_claims": """
                CREATE TABLE IF NOT EXISTS beta_claims (
                  message_id BIGINT PRIMARY KEY
                )
            """,
        }
        for table, stmt in create_sql.items():
            try:
                if not await _table_exists(conn, table):
                    await conn.execute(stmt)
            except Exception as e:
                if "permission denied" in str(e).lower():
                    print(f"[ensure_schema_migrations] Skipped creating {table}: {e}")
                else:
                    raise
    finally:
        try:
            await conn.close()
        except Exception:
            pass

async def get_user_gen(user_id: str) -> int:
    conn = await connect()
    try:
        cur = await conn.execute("SELECT generation FROM user_rulesets WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        await cur.close()
        if not row or row[0] is None:
            return 1
        return int(row[0])
    finally:
        try:
            await conn.close()
        except Exception:
            pass

async def set_user_gen(user_id: str, gen: int) -> None:
    gen = max(1, min(9, int(gen)))
    conn = await connect()
    try:
        now = dt.datetime.utcnow()
        await conn.execute("UPDATE user_rulesets SET generation = $1, updated_at_utc = $2 WHERE user_id = $3", (gen, now, user_id))
        await conn.commit()
    finally:
        try:
            await conn.close()
        except Exception:
            pass


def _exp_requirement_rows() -> List[Tuple[str, int, int]]:
    """Yield (group_code, level, exp_total) for Gen III+ exp_requirements; level 1 = 0 for all groups."""
    def erratic(n: int) -> int:
        if n < 50: return n ** 3 * (100 - n) // 50
        if n < 68: return n ** 3 * (150 - n) // 100
        if n < 98: return n ** 3 * (1911 - 10 * n) // 500
        return n ** 3 * (160 - n) // 100
    def fast(n: int) -> int: return 4 * n ** 3 // 5
    def medium_fast(n: int) -> int: return n ** 3
    def medium_slow(n: int) -> int: return int((6 / 5) * n ** 3 - 15 * n ** 2 + 100 * n - 140)
    def slow(n: int) -> int: return 5 * n ** 3 // 4
    def fluctuating(n: int) -> int:
        if n < 15: return n ** 3 * ((n + 1) // 3 + 24) // 50
        if n < 36: return n ** 3 * (n + 14) // 50
        return n ** 3 * ((n // 2) + 32) // 50
    funcs = {"erratic": erratic, "fast": fast, "medium_fast": medium_fast, "medium_slow": medium_slow, "slow": slow, "fluctuating": fluctuating}
    rows: List[Tuple[str, int, int]] = []
    for code, fn in funcs.items():
        for lvl in range(1, 101):
            exp_val = fn(lvl)
            if lvl == 1: exp_val = 0
            elif exp_val < 0: exp_val = 0
            rows.append((code, lvl, exp_val))
    return rows


async def ensure_exp_tables(conn: aiosqlite.Connection) -> None:
    """
    Ensure exp_groups and exp_requirements are seeded (Postgres).
    Same group codes and formulas as schema; level 1 = 0 for all groups.
    """
    try:
        if not await _table_exists(conn, "exp_requirements"):
            return
        cur = await conn.execute("SELECT 1 FROM exp_requirements LIMIT 1")
        row = await cur.fetchone()
        await cur.close()
        if row is not None:
            return
        rows = _exp_requirement_rows()
        for group_code, level, exp_total in rows:
            await conn.execute(
                "INSERT INTO exp_requirements (group_code, level, exp_total) VALUES (?, ?, ?) ON CONFLICT (group_code, level) DO UPDATE SET exp_total = EXCLUDED.exp_total",
                (group_code, level, exp_total),
            )
    except Exception:
        pass


async def init_schema() -> None:
    """
    Initialize schema from schema_pg.sql (cloud PostgreSQL), run migrations, and ensure columns.
    Uses db.session() context manager per DATABASE_CONTEXT_EVERYTHING.md (no connection leak).
    """
    async with session() as conn:
        can_create_schema = True
        try:
            cur = await conn.execute("SELECT has_schema_privilege(current_user,'public','create') AS can_create")
            row = await cur.fetchone()
            await cur.close()
            if row is not None:
                can_create_schema = bool(row.get("can_create", row[0]) if hasattr(row, "get") else row[0])
            else:
                can_create_schema = True
        except Exception:
            can_create_schema = True

        if SCHEMA_PATH.exists() and can_create_schema:
            with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
                schema_sql = f.read()
            statements = [s.strip() for s in schema_sql.split(";") if s.strip() and not s.strip().startswith("--")]
            for statement in statements:
                if statement:
                    try:
                        await conn.execute(statement)
                    except Exception as e:
                        error_str = str(e).lower()
                        if any(phrase in error_str for phrase in [
                            "already exists", "duplicate", "must be owner",
                            "permission denied", "does not exist",
                        ]):
                            pass
                        # else: skip statement, continue with rest
        # legacy → new
        await migrate_monsters_to_pokemons()
        # make sure pokemons has required columns
        await ensure_pokemon_stat_columns()
        # run additive migrations
        await ensure_schema_migrations()
        # ensure PG columns exist even if schema file was partially applied
        try:
            if await _table_exists(conn, "pokemons"):
                if not await _column_exists(conn, "pokemons", "hp_now"):
                    await conn.execute("ALTER TABLE pokemons ADD COLUMN hp_now INTEGER")
                if not await _column_exists(conn, "pokemons", "moves_pp"):
                    await conn.execute("ALTER TABLE pokemons ADD COLUMN moves_pp JSONB")
                if not await _column_exists(conn, "pokemons", "moves_pp_min"):
                    await conn.execute("ALTER TABLE pokemons ADD COLUMN moves_pp_min JSONB")
                if not await _column_exists(conn, "pokemons", "moves_pp_max"):
                    await conn.execute("ALTER TABLE pokemons ADD COLUMN moves_pp_max JSONB")
                if not await _column_exists(conn, "pokemons", "shiny"):
                    await conn.execute("ALTER TABLE pokemons ADD COLUMN shiny INTEGER NOT NULL DEFAULT 0")
                if not await _column_exists(conn, "pokemons", "is_hidden_ability"):
                    await conn.execute("ALTER TABLE pokemons ADD COLUMN is_hidden_ability INTEGER NOT NULL DEFAULT 0")
                if not await _column_exists(conn, "pokemons", "exp"):
                    await conn.execute("ALTER TABLE pokemons ADD COLUMN exp INTEGER NOT NULL DEFAULT 0")
                if not await _column_exists(conn, "pokemons", "exp_group"):
                    await conn.execute("ALTER TABLE pokemons ADD COLUMN exp_group TEXT NOT NULL DEFAULT 'medium_fast'")
        except Exception:
            pass
        # ensure users.user_gender exists for Postgres too
        try:
            if await _table_exists(conn, "users") and not await _column_exists(conn, "users", "user_gender"):
                await conn.execute("ALTER TABLE users ADD COLUMN user_gender TEXT")
        except Exception:
            pass
        await ensure_exp_tables(conn)
        await ensure_shiny_trigger()
        await conn.commit()


# ---------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------
def _parse_currencies(row: Optional[Dict]) -> Dict[str, Any]:
    """Normalize currencies from a user row (currencies column or coins fallback)."""
    if not row:
        return {}
    cur = row.get("currencies")
    if cur is None:
        return {"coins": int(row.get("coins") or 0)}
    if isinstance(cur, str):
        try:
            return json.loads(cur) if cur else {}
        except Exception:
            return {"coins": int(row.get("coins") or 0)}
    return dict(cur) if cur else {}


async def get_user(user_id: str):
    conn = await connect()
    try:
        cur = await conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        await cur.close()
        if row is None:
            return None
        row_dict = dict(row)
        currencies = _parse_currencies(row_dict)
        row_dict["currencies"] = currencies
        row_dict["coins"] = currencies.get("coins", int(row_dict.get("coins") or 0))
        return row_dict
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def create_user(user_id: str):
    conn = await connect()
    try:
        now = dt.datetime.utcnow()
        await conn.execute(
            "INSERT INTO users (user_id, created_at, coins, currencies) VALUES ($1, $2, 0, $3::jsonb) ON CONFLICT (user_id) DO NOTHING",
            (user_id, now, '{"coins": 0}'),
        )
        await conn.commit()
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def count_users() -> int:
    conn = await connect()
    try:
        cur = await conn.execute("SELECT COUNT(*) AS c FROM users")
        row = await cur.fetchone()
        await cur.close()
        return int(row["c"])
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def list_users(limit: int = 20, offset: int = 0):
    conn = await connect()
    try:
        cur = await conn.execute(
            "SELECT * FROM users ORDER BY created_at LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = await cur.fetchall()
        await cur.close()
        out = []
        for r in rows:
            d = dict(r)
            currencies = _parse_currencies(d)
            d["currencies"] = currencies
            d["coins"] = currencies.get("coins", int(d.get("coins") or 0))
            out.append(d)
        return out
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def get_currency(user_id: str, key: str = "coins") -> int:
    """Return one currency amount from user's currencies JSON (default: coins)."""
    conn = await connect()
    try:
        cur = await conn.execute(
            "SELECT currencies, coins FROM users WHERE user_id = ? LIMIT 1",
            (user_id,),
        )
        row = await cur.fetchone()
        await cur.close()
        if not row:
            return 0
        d = dict(row)
        currencies = _parse_currencies(d)
        return int(currencies.get(key, 0))
    finally:
        try:
            await conn.close()
        except Exception:
            pass


def _currency_path(key: str) -> list[str]:
    """Path array for jsonb_set(..., path::text[], ...), e.g. ['coins']."""
    return [str(key or "").strip()]


async def set_currency(user_id: str, key: str, value: int) -> None:
    """Set one currency in user's currencies JSON (e.g. key='coins', value=6000)."""
    conn = await connect()
    try:
        path = _currency_path(key)
        await conn.execute(
            "UPDATE users SET currencies = jsonb_set(COALESCE(NULLIF(currencies::text, 'null')::jsonb, '{}'::jsonb), ?::text[], to_jsonb(?)) WHERE user_id = ?",
            (path, value, user_id),
        )
        await conn.commit()
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def add_currency(user_id: str, key: str, delta: int) -> None:
    """Add to one currency in user's currencies JSON (e.g. key='coins'). Inserts user if missing."""
    conn = await connect()
    try:
        path = _currency_path(key)
        # New user: insert with key=delta; existing: add delta to current
        await conn.execute(
            "INSERT INTO users (user_id, created_at, currencies) VALUES (?, CURRENT_TIMESTAMP, ?::jsonb) "
            "ON CONFLICT (user_id) DO UPDATE SET currencies = jsonb_set(COALESCE(users.currencies, '{}'::jsonb), ?::text[], to_jsonb(COALESCE((users.currencies->>?)::int, 0) + ?))",
            (user_id, json.dumps({key: delta}), path, key, delta),
        )
        await conn.commit()
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def grant_coins(user_id: str, delta: int):
    """Add to user's coins (PokéDollars). Uses currencies JSON."""
    await add_currency(user_id, "coins", delta)


def get_currency_from_row(row: Optional[Dict], key: str = "coins") -> int:
    """Get one currency amount from a user row (currencies JSON or coins fallback)."""
    if not row:
        return 0
    currencies = _parse_currencies(row)
    return int(currencies.get(key, 0))


async def set_currency_conn(conn, user_id: str, key: str, value: int) -> None:
    """Set one currency using existing connection (for use inside transactions)."""
    path = _currency_path(key)
    await conn.execute(
        "UPDATE users SET currencies = jsonb_set(COALESCE(NULLIF(currencies::text, 'null')::jsonb, '{}'::jsonb), ?::text[], to_jsonb(?)) WHERE user_id = ?",
        (path, value, user_id),
    )


async def add_currency_conn(conn, user_id: str, key: str, delta: int) -> None:
    """Add to one currency using existing connection (for use inside transactions)."""
    path = _currency_path(key)
    await conn.execute(
        "UPDATE users SET currencies = jsonb_set(COALESCE(NULLIF(users.currencies::text, 'null')::jsonb, '{}'::jsonb), ?::text[], to_jsonb(COALESCE((users.currencies->>?)::int, 0) + ?)) WHERE user_id = ?",
        (path, key, delta, user_id),
    )


# Admin whitelist (optional) + simple TTL cache
_admin_cache: dict[str, tuple[bool, float]] = {}
_ADMIN_CACHE_TTL = 60.0

async def add_admin(user_id: str) -> None:
    conn = await connect()
    try:
        now = dt.datetime.utcnow()
        await conn.execute(
            "INSERT INTO admins (user_id, added_at) VALUES ($1, $2) ON CONFLICT (user_id) DO NOTHING",
            (user_id, now),
        )
        await conn.commit()
        _admin_cache.clear()
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def remove_admin(user_id: str) -> None:
    conn = await connect()
    try:
        await conn.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        await conn.commit()
        _admin_cache.clear()
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def is_admin(user_id: str) -> bool:
    import time
    now = time.time()
    if user_id in _admin_cache:
        v, exp = _admin_cache[user_id]
        if now <= exp:
            return v
        del _admin_cache[user_id]
    conn = await connect()
    try:
        cur = await conn.execute("SELECT 1 FROM admins WHERE user_id = ? LIMIT 1", (user_id,))
        row = await cur.fetchone()
        await cur.close()
        v = row is not None
        _admin_cache[user_id] = (v, now + _ADMIN_CACHE_TTL)
        return v
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def any_admins() -> bool:
    conn = await connect()
    try:
        cur = await conn.execute("SELECT 1 FROM admins LIMIT 1")
        row = await cur.fetchone()
        await cur.close()
        return row is not None
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def list_admins(limit: int = 100, offset: int = 0):
    conn = await connect()
    try:
        cur = await conn.execute(
            "SELECT user_id, added_at FROM admins ORDER BY added_at LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = await cur.fetchall()
        await cur.close()
        return [dict(r) for r in rows]
    finally:
        try:
            await conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------
# Pokémons
# ---------------------------------------------------------------------
def invalidate_pokemons_cache(owner_id: str) -> None:
    """Invalidate cached pokemons for an owner. Call after any raw SQL that changes pokemons for this owner."""
    if _CACHE_ENABLED and db_cache is not None:
        try:
            db_cache.invalidate_pokemons(owner_id)
        except Exception:
            pass


def clear_all_pokemons_cache() -> None:
    """Clear all per-owner pokemons caches (e.g. after full table wipe)."""
    if _CACHE_ENABLED and db_cache is not None:
        try:
            db_cache.clear_all_pokemons_cache()
        except Exception:
            pass


async def add_pokemon(owner_id: str, species: str, level: int = 5,
                      hp: int = 20, atk: int = 5, def_: int = 5) -> int:
    conn = await connect()
    try:
        cur = await conn.execute(
            "INSERT INTO pokemons (owner_id, species, level, hp, atk, def) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (owner_id, species, level, hp, atk, def_)
        )
        await conn.commit()
        mid = cur.lastrowid
        await cur.close()
        if _CACHE_ENABLED and db_cache is not None:
            try:
                db_cache.invalidate_pokemons(owner_id)
            except Exception:
                pass
        return int(mid)
    finally:
        try:
            await conn.close()
        except Exception:
            pass


# Max rows to cache per owner for list_pokemons (sliced by offset/limit)
_LIST_POKEMONS_CACHE_LIMIT = 2000


async def list_pokemons(owner_id: str, limit: int = 50, offset: int = 0):
    if _CACHE_ENABLED and db_cache is not None:
        try:
            cached = db_cache.get_cached_pokemons(owner_id)
            if cached is not None:
                return cached[offset : offset + limit]
        except Exception:
            pass
    conn = await connect()
    try:
        fetch_limit = min(limit + offset, _LIST_POKEMONS_CACHE_LIMIT)
        cur = await conn.execute(
            "SELECT * FROM pokemons WHERE owner_id=? ORDER BY id LIMIT ? OFFSET ?",
            (owner_id, fetch_limit, 0),
        )
        rows = await cur.fetchall()
        await cur.close()
        out = [dict(r) for r in rows]
        if _CACHE_ENABLED and db_cache is not None and offset == 0:
            try:
                db_cache.set_cached_pokemons(owner_id, out)
            except Exception:
                pass
        return out[offset : offset + limit]
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def get_pokemon(owner_id: str, mon_id: int, *, conn=None) -> Optional[dict]:
    """Fetch full Pokémon row by owner and id. Pass conn from db.session() to reuse connection."""
    if _CACHE_ENABLED and db_cache is not None:
        try:
            cached = db_cache.get_cached_pokemons(owner_id)
            if cached is not None:
                for p in cached:
                    if int(p.get("id")) == int(mon_id):
                        return p
        except Exception:
            pass
    async def _fetch(c):
        cur = await c.execute(
            "SELECT * FROM pokemons WHERE owner_id=? AND id=? LIMIT 1",
            (owner_id, mon_id),
        )
        row = await cur.fetchone()
        await cur.close()
        return dict(row) if row else None

    if conn is not None:
        return await _fetch(conn)
    async with session() as c:
        return await _fetch(c)


async def add_pokemon_with_stats(owner_id: str,
                                 species: str,
                                 level: int,
                                 final_stats: dict,
                                 ivs: dict,
                                 evs: dict,
                                 nature: str,
                                 ability: str,
                                 gender: str,
                                 form: str | None = None,
                                 can_gigantamax: bool = False,
                                 tera_type: str | None = None) -> int:
    """Insert a Pokémon row including full stats + IVs/EVs/nature/ability/gender/form.
    Also sets moves to an empty JSON list so it satisfies NOT NULL.
    """
    conn = await connect()
    try:
        # ensure we always have a valid JSON string for moves on insert
        empty_moves_json = json.dumps([], ensure_ascii=False)

        cur = await conn.execute("""
            INSERT INTO pokemons
              (owner_id, species, level,
               hp, hp_now, atk, def, spa, spd, spe,
               ivs, evs, nature, ability, gender,
               moves, form, can_gigantamax, tera_type)
            VALUES (?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?)
        """, (
            owner_id, species, level,
            int(final_stats["hp"]),
            int(final_stats["hp"]),
            int(final_stats["attack"]),
            int(final_stats["defense"]),
            int(final_stats["special_attack"]),
            int(final_stats["special_defense"]),
            int(final_stats["speed"]),
            json.dumps(ivs, ensure_ascii=False),
            json.dumps(evs, ensure_ascii=False),
            nature,
            ability,
            gender,
            empty_moves_json,  # <-- satisfy NOT NULL
            form,  # <-- form field
            bool(can_gigantamax),  # Postgres BOOLEAN; avoid integer
            tera_type,
        ))
        await conn.commit()
        pid = cur.lastrowid
        await cur.close()
        if _CACHE_ENABLED and db_cache is not None:
            try:
                db_cache.invalidate_pokemons(owner_id)
            except Exception:
                pass
        return int(pid)
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def set_held_item(owner_id: str, mon_id: int, item_id: Optional[str]) -> None:
    conn = await connect()
    try:
        await conn.execute(
            "UPDATE pokemons SET held_item=? WHERE owner_id=? AND id=?",
            (item_id, owner_id, mon_id),
        )
        await conn.commit()
        if _CACHE_ENABLED and db_cache is not None:
            try:
                db_cache.invalidate_pokemons(owner_id)
            except Exception:
                pass
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def set_pokemon_moves(owner_id: str, mon_id: int, moves: Sequence[str] | Sequence[int]) -> None:
    moves = list(moves or [])[:4]
    conn = await connect()
    try:
        # Base PP (no PP Ups) for each move
        base_pps: List[int] = []
        missing: List[Tuple[int, str]] = []
        for i, m in enumerate(moves):
            name = str(m)
            pp_val = None
            try:
                if _CACHE_ENABLED:
                    cached = db_cache.get_cached_move(name) or db_cache.get_cached_move(name.lower()) or db_cache.get_cached_move(name.lower().replace(" ", "-"))
                    if cached and cached.get("pp") is not None:
                        pp_val = int(cached["pp"])
            except Exception:
                pp_val = None
            if pp_val is None:
                missing.append((i, name.lower().replace(" ", "-")))
                base_pps.append(20)
            else:
                base_pps.append(int(pp_val))
        if missing:
            try:
                q_names = [m[1] for m in missing]
                placeholders = ",".join(["?"] * len(q_names))
                cur = await conn.execute(
                    f"SELECT name, pp FROM moves WHERE LOWER(name) IN ({placeholders})",
                    tuple(n.lower() for n in q_names),
                )
                rows = await cur.fetchall(); await cur.close()
                lookup = {}
                for r in rows:
                    row = dict(r) if hasattr(r, "keys") else {"name": r[0], "pp": r[1]}
                    lookup[str(row["name"]).lower()] = row.get("pp")
                for idx, norm in missing:
                    pp_val = lookup.get(norm)
                    if pp_val is not None:
                        base_pps[idx] = int(pp_val)
            except Exception:
                pass

        has_moves_pp = True
        has_moves_pp_min = True
        has_moves_pp_max = True
        try:
            has_moves_pp = await _column_exists(conn, "pokemons", "moves_pp")
        except Exception:
            has_moves_pp = False
        try:
            has_moves_pp_min = await _column_exists(conn, "pokemons", "moves_pp_min")
        except Exception:
            has_moves_pp_min = False
        try:
            has_moves_pp_max = await _column_exists(conn, "pokemons", "moves_pp_max")
        except Exception:
            has_moves_pp_max = False
        min_pps = [0 for _ in base_pps]
        if has_moves_pp:
            if has_moves_pp_min and has_moves_pp_max:
                await conn.execute(
                    "UPDATE pokemons SET moves=?, moves_pp=?, moves_pp_min=?, moves_pp_max=? WHERE owner_id=? AND id=?",
                    (
                        json.dumps(moves, ensure_ascii=False),
                        json.dumps(base_pps, ensure_ascii=False),
                        json.dumps(min_pps, ensure_ascii=False),
                        json.dumps(base_pps, ensure_ascii=False),
                        owner_id,
                        mon_id,
                    ),
                )
            else:
                await conn.execute(
                    "UPDATE pokemons SET moves=?, moves_pp=? WHERE owner_id=? AND id=?",
                    (json.dumps(moves, ensure_ascii=False), json.dumps(base_pps, ensure_ascii=False), owner_id, mon_id),
                )
        else:
            await conn.execute(
                "UPDATE pokemons SET moves=? WHERE owner_id=? AND id=?",
                (json.dumps(moves, ensure_ascii=False), owner_id, mon_id),
            )
        await conn.commit()
        if _CACHE_ENABLED and db_cache is not None:
            try:
                db_cache.invalidate_pokemons(owner_id)
            except Exception:
                pass
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def bump_friendship(owner_id: str, mon_id: int, delta: int, lo: int = 0, hi: int = 255) -> int:
    """Increase/decrease friendship; initialize from species base_happiness if NULL."""
    conn = await connect()
    try:
        cur = await conn.execute("""
            SELECT p.friendship, p.species, COALESCE(pd.base_happiness, 70) AS base_h
            FROM pokemons p
            LEFT JOIN pokedex pd ON LOWER(pd.name) = LOWER(p.species)
            WHERE p.owner_id=? AND p.id=? LIMIT 1
        """, (owner_id, mon_id))
        row = await cur.fetchone(); await cur.close()
        if not row:
            raise ValueError("Pokémon not found")
        cur_val = row["friendship"]
        if cur_val is None:
            cur_val = int(row["base_h"])
        new_val = max(lo, min(hi, int(cur_val) + int(delta)))
        await conn.execute("UPDATE pokemons SET friendship=? WHERE owner_id=? AND id=?", (new_val, owner_id, mon_id))
        await conn.commit()
        if _CACHE_ENABLED and db_cache is not None:
            try:
                db_cache.invalidate_pokemons(owner_id)
            except Exception:
                pass
        return new_val
    finally:
        try:
            await conn.close()
        except Exception:
            pass


# Team helpers
async def next_free_team_slot(owner_id: str) -> Optional[int]:
    conn = await connect()
    try:
        cur = await conn.execute(
            "SELECT team_slot FROM pokemons WHERE owner_id=? AND team_slot BETWEEN 1 AND 6",
            (owner_id,),
        )
        used = {int(r[0]) for r in await cur.fetchall()}
        await cur.close()
        for s in range(1, 7):
            if s not in used:
                return s
        return None
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def set_team_slot(owner_id: str, mon_id: int, slot: Optional[int]) -> None:
    conn = await connect()
    try:
        await conn.execute(
            "UPDATE pokemons SET team_slot=? WHERE owner_id=? AND id=?",
            (slot, owner_id, mon_id),
        )
        await conn.commit()
        if _CACHE_ENABLED and db_cache is not None:
            try:
                db_cache.invalidate_pokemons(owner_id)
            except Exception:
                pass
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def get_team_mon_by_name(owner_id: str, species_name: str) -> Optional[dict]:
    conn = await connect()
    try:
        cur = await conn.execute("""
            SELECT * FROM pokemons
            WHERE owner_id = ?
              AND LOWER(species) = LOWER(?)
              AND team_slot BETWEEN 1 AND 6
            ORDER BY team_slot, id
            LIMIT 1
        """, (owner_id, species_name))
        row = await cur.fetchone(); await cur.close()
        return dict(row) if row else None
    finally:
        try:
            await conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------
# Items & Inventory (old + new schema compatible)
# ---------------------------------------------------------------------
DEFAULT_BAG_PAGES = 6
BAG_ITEMS_PER_PAGE = 24
_BAG_CACHE_LIMIT = 2000  # max rows to cache per owner for get_inventory_page


def _normalize_bag_item_id(item_id: Any) -> str:
    raw = str(item_id or "").strip().lower()
    if not raw:
        return ""
    token = re.sub(r"[\s\-]+", "_", raw)
    token = re.sub(r"[^a-z0-9_]", "", token)
    if not token:
        return raw
    try:
        resolved = _catalog_resolve_market_key(token)
    except Exception:
        resolved = token
    if resolved in {"pokeball", "pok_ball", "poke_ball"}:
        return "poke_ball"
    # PP items often appear in multiple alias styles across old rows.
    if resolved in {"ppmax", "pp_max"}:
        return "pp_max"
    if resolved in {"ppup", "pp_up"}:
        return "pp_up"
    if resolved in {"maxether", "max_ether"}:
        return "max_ether"
    if resolved in {"maxelixir", "max_elixir"}:
        return "max_elixir"
    # Only rewrite when resolver actually mapped an alias.
    if resolved != token:
        return resolved
    return raw


def invalidate_bag_cache(owner_id: str) -> None:
    """Invalidate cached bag for an owner. Call after any raw SQL that changes user_items for this owner."""
    if _CACHE_ENABLED and db_cache is not None:
        try:
            db_cache.invalidate_bag(owner_id)
        except Exception:
            pass


def clear_all_bag_cache() -> None:
    """Clear all per-owner bag caches (e.g. after full table wipe)."""
    if _CACHE_ENABLED and db_cache is not None:
        try:
            db_cache.clear_all_bag_cache()
        except Exception:
            pass


async def get_inventory_page(
    conn: aiosqlite.Connection,
    owner_id: int | str,
    page: int,
    per_page: int = BAG_ITEMS_PER_PAGE
) -> Tuple[List[Dict[str, Any]], int, int]:
    """
    Return (items, max_pages, total_distinct) for the user's bag page.
    Works with BOTH old and new schemas:

      NEW:
        - user_items(owner_id,item_id,qty)
        - items(id,name,emoji,icon_url,...)

      OLD:
        - inventory(owner_id,item_id,qty)
        - items(item_id,name,...)  [no emoji/icon_url guaranteed]
    """
    conn.row_factory = aiosqlite.Row
    uid = str(owner_id)

    # Try cache first (no conn needed for read)
    if _CACHE_ENABLED and db_cache is not None:
        try:
            cached = db_cache.get_cached_bag(uid)
            if cached is not None:
                total_distinct = len(cached)
                total_pages_cap = DEFAULT_BAG_PAGES
                max_pages = max(1, min(total_pages_cap, ((total_distinct + per_page - 1) // per_page) or 1))
                page = max(1, min(page, max_pages))
                offset = (page - 1) * per_page
                items = cached[offset : offset + per_page]
                return items, max_pages, total_distinct
        except Exception:
            pass

    has_user_items = await _table_exists(conn, "user_items")
    has_inventory  = await _table_exists(conn, "inventory")
    if not has_user_items and not has_inventory:
        return [], 1, 0

    # Items table columns
    items_has_id      = await _column_exists(conn, "items", "id")
    items_has_item_id = await _column_exists(conn, "items", "item_id")
    items_has_name    = await _column_exists(conn, "items", "name")
    items_has_emoji   = await _column_exists(conn, "items", "emoji")
    items_has_icon    = await _column_exists(conn, "items", "icon_url")

    # Choose source + join
    if has_user_items:
        bag_table = "user_items"; bag_alias = "ui"
        bag_owner_col = "owner_id"; bag_item_col = "item_id"
        qty_expr = "ui.qty"
        join_on = "items.id = ui.item_id" if items_has_id else "items.item_id = ui.item_id"
        count_from  = "user_items"
        count_where = "owner_id = ? AND qty > 0"
    else:
        bag_table = "inventory"; bag_alias = "i"
        bag_owner_col = "owner_id"; bag_item_col = "item_id"
        qty_expr = "i.qty"
        join_on = "items.item_id = i.item_id"
        count_from  = "inventory"
        count_where = "owner_id = ? AND qty > 0"

    # Build safe SELECT cols
    name_expr = "items.name" if items_has_name else f"{bag_alias}.{bag_item_col}"
    emoji_expr = "items.emoji"    if items_has_emoji else "NULL AS emoji"
    icon_expr  = "items.icon_url" if items_has_icon  else "NULL AS icon_url"

    sql_full = f"""
        SELECT {bag_alias}.{bag_item_col} AS item_id,
               {qty_expr} AS qty,
               COALESCE({name_expr}, {bag_alias}.{bag_item_col}) AS name,
               {emoji_expr},
               {icon_expr}
        FROM {bag_table} {bag_alias}
        LEFT JOIN items ON {join_on}
        WHERE {bag_alias}.{bag_owner_col} = ? AND {qty_expr} > 0
          AND {bag_alias}.{bag_item_col} NOT LIKE 'tm-%' AND {bag_alias}.{bag_item_col} NOT LIKE 'hm-%'
        ORDER BY (name IS NULL), name ASC, {bag_alias}.{bag_item_col} ASC
        LIMIT ? OFFSET 0
    """
    cur = await conn.execute(sql_full, (uid, _BAG_CACHE_LIMIT))
    rows = await cur.fetchall(); await cur.close()

    items_full = [{
        "item_id": r["item_id"],
        "qty": int(r["qty"]),
        "name": r["name"] or r["item_id"],
        "emoji": r["emoji"],
        "icon_url": r["icon_url"],
    } for r in rows]

    if items_full:
        merged: Dict[str, Dict[str, Any]] = {}
        for row in items_full:
            canonical_id = _normalize_bag_item_id(row.get("item_id"))
            if not canonical_id:
                canonical_id = str(row.get("item_id") or "")
            bucket = merged.get(canonical_id)
            if bucket is None:
                bucket = dict(row)
                bucket["item_id"] = canonical_id
                merged[canonical_id] = bucket
            else:
                bucket["qty"] = int(bucket.get("qty") or 0) + int(row.get("qty") or 0)
                # Prefer a readable display name when one side is just raw ID.
                bucket_name = str(bucket.get("name") or "")
                row_name = str(row.get("name") or "")
                if (not bucket_name or bucket_name.lower() == str(bucket.get("item_id") or "").lower()) and row_name:
                    bucket["name"] = row_name
                if not bucket.get("emoji") and row.get("emoji"):
                    bucket["emoji"] = row.get("emoji")
                if not bucket.get("icon_url") and row.get("icon_url"):
                    bucket["icon_url"] = row.get("icon_url")
        items_full = sorted(
            merged.values(),
            key=lambda d: (
                (d.get("name") is None),
                str(d.get("name") or "").lower(),
                str(d.get("item_id") or "").lower(),
            ),
        )

    if _CACHE_ENABLED and db_cache is not None:
        try:
            db_cache.set_cached_bag(uid, items_full)
        except Exception:
            pass

    total_distinct = len(items_full)
    total_pages_cap = DEFAULT_BAG_PAGES
    if await _table_exists(conn, "user_meta"):
        try:
            cur = await conn.execute("SELECT bag_pages FROM user_meta WHERE owner_id = ?", (uid,))
            r = await cur.fetchone(); await cur.close()
            if r and r["bag_pages"] is not None:
                total_pages_cap = int(r["bag_pages"])
        except Exception:
            pass
    max_pages = max(1, min(total_pages_cap, ((total_distinct + per_page - 1) // per_page) or 1))
    page = max(1, min(page, max_pages))
    offset = (page - 1) * per_page
    items = items_full[offset : offset + per_page]
    return items, max_pages, total_distinct


async def give_item(owner_id: str, item_id: str, qty: int) -> int:
    """
    Add (or remove if qty<0) items to a user's bag (user_items).
    Returns the resulting quantity (clamped >= 0).
    """
    conn = await connect()
    try:
        item_id = _normalize_bag_item_id(item_id) or str(item_id or "").strip().lower()
        cur = await conn.execute(
            "SELECT qty FROM user_items WHERE owner_id=? AND item_id=?",
            (owner_id, item_id)
        )
        row = await cur.fetchone()
        await cur.close()

        if row:
            new_qty = max(0, int(row[0]) + int(qty))
            await conn.execute(
                "UPDATE user_items SET qty=? WHERE owner_id=? AND item_id=?",
                (new_qty, owner_id, item_id)
            )
        else:
            new_qty = max(0, int(qty))
            await conn.execute(
                "INSERT INTO user_items (owner_id, item_id, qty) VALUES (?, ?, ?)",
                (owner_id, item_id, new_qty)
            )
        await conn.execute(
            "INSERT INTO user_meta (owner_id) VALUES (?) ON CONFLICT (owner_id) DO NOTHING",
            (owner_id,)
        )
        await conn.commit()
        if _CACHE_ENABLED and db_cache is not None:
            try:
                db_cache.invalidate_bag(owner_id)
                if (str(item_id).lower().startswith("tm-") or str(item_id).lower().startswith("hm-")):
                    db_cache.invalidate_tm_machine(owner_id)
            except Exception:
                pass
        return new_qty
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def upsert_item_master(item_id: str,
                             name: Optional[str] = None,
                             icon_url: Optional[str] = None,
                             emoji: Optional[str] = None) -> None:
    """Create/update an item in master catalog (items.id)."""
    conn = await connect()
    try:
        # items.name is NOT NULL in PostgreSQL; provide name on insert to avoid constraint violation
        name_val = name if name is not None else item_id.replace("-", " ").replace("_", " ").title()
        await conn.execute(
            "INSERT INTO items (id, name) VALUES (?, ?) ON CONFLICT (id) DO NOTHING",
            (item_id, name_val),
        )
        sets, vals = [], []
        if name is not None:
            sets.append("name = ?"); vals.append(name)
        if icon_url is not None:
            sets.append("icon_url = ?"); vals.append(icon_url)
        if emoji is not None:
            sets.append("emoji = ?"); vals.append(emoji)
        if sets:
            vals.append(item_id)
            await conn.execute(
                f"UPDATE items SET {', '.join(sets)} WHERE id = ?",
                tuple(vals)
            )
        await conn.commit()
    finally:
        try:
            await conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------
# Event log
# ---------------------------------------------------------------------
async def log_event(user_id: str, type_: str, payload: dict):
    conn = await connect()
    try:
        now = dt.datetime.utcnow()
        await conn.execute(
            "INSERT INTO event_log (user_id, type, payload, created_at) VALUES ($1, $2, $3, $4)",
            (user_id, type_, json.dumps(payload, ensure_ascii=False), now)
        )
        await conn.commit()
    finally:
        try:
            await conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------
# Pokédex cache (species)
# ---------------------------------------------------------------------
async def get_pokedex_by_name(name: str) -> Optional[dict]:
    # Check cache first
    if _CACHE_ENABLED:
        cached = db_cache.get_cached_pokedex(name)
        if cached is not None:
            return cached
    
    conn = await connect()
    try:
        cur = await conn.execute("SELECT * FROM pokedex WHERE LOWER(name) = LOWER(?) LIMIT 1", (name,))
        row = await cur.fetchone()
        await cur.close()
        result = dict(row) if row else None
        
        # Cache the result
        if _CACHE_ENABLED and result:
            db_cache.set_cached_pokedex(name, result)
            # Also cache by ID if available
            if 'id' in result:
                db_cache.set_cached_pokedex(str(result['id']), result)
        
        return result
    finally:
        await conn.close()


async def get_pokedex_by_id(pid: int) -> Optional[dict]:
    # Check cache first
    if _CACHE_ENABLED:
        cached = db_cache.get_cached_pokedex(str(pid))
        if cached is not None:
            return cached
    
    conn = await connect()
    try:
        cur = await conn.execute("SELECT * FROM pokedex WHERE id = ? LIMIT 1", (pid,))
        row = await cur.fetchone()
        await cur.close()
        result = dict(row) if row else None
        
        # Cache the result
        if _CACHE_ENABLED and result:
            db_cache.set_cached_pokedex(str(pid), result)
            # Also cache by name if available
            if 'name' in result:
                db_cache.set_cached_pokedex(result['name'], result)
        
        return result
    finally:
        await conn.close()


async def upsert_pokedex(e: dict):
    """
    Insert/update one normalized species entry.

    Expected keys in e:
      id, name, introduced_in, types(list), stats(dict),
      abilities(list), sprites(dict), base_experience, height_m, weight_kg,
      base_happiness, capture_rate, egg_groups(list), growth_rate,
      ev_yield(dict), gender_ratio(dict), flavor, evolution(dict)
    """
    conn = await connect()
    try:
        await conn.execute("""
            INSERT INTO pokedex
            (id,name,introduced_in,types,stats,abilities,sprites,base_experience,height_m,weight_kg,
             base_happiness,capture_rate,egg_groups,growth_rate,ev_yield,gender_ratio,flavor,evolution)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              name=excluded.name,
              introduced_in=excluded.introduced_in,
              types=excluded.types,
              stats=excluded.stats,
              abilities=excluded.abilities,
              sprites=excluded.sprites,
              base_experience=excluded.base_experience,
              height_m=excluded.height_m,
              weight_kg=excluded.weight_kg,
              base_happiness=excluded.base_happiness,
              capture_rate=excluded.capture_rate,
              egg_groups=excluded.egg_groups,
              growth_rate=excluded.growth_rate,
              ev_yield=excluded.ev_yield,
              gender_ratio=excluded.gender_ratio,
              flavor=excluded.flavor,
              evolution=excluded.evolution
        """, (
            e["id"], e["name"].lower(), e.get("introduced_in"),
            json.dumps(e["types"], ensure_ascii=False),
            json.dumps(e["stats"], ensure_ascii=False),
            json.dumps(e["abilities"], ensure_ascii=False),
            json.dumps(e["sprites"], ensure_ascii=False),
            e.get("base_experience"),
            e.get("height_m"),
            e.get("weight_kg"),
            e.get("base_happiness"),
            e.get("capture_rate"),
            json.dumps(e.get("egg_groups", []), ensure_ascii=False),
            e.get("growth_rate"),
            json.dumps(e.get("ev_yield", {}), ensure_ascii=False),
            json.dumps(e.get("gender_ratio", {}), ensure_ascii=False),
            e.get("flavor"),
            json.dumps(e.get("evolution", {}), ensure_ascii=False),
        ))
        await conn.commit()
        if _CACHE_ENABLED and db_cache is not None:
            try:
                db_cache.invalidate_pokedex(e.get("name", ""))
                db_cache.invalidate_pokedex(str(e["id"]))
            except Exception:
                pass
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def set_item_emoji(item_id: str, emoji: str | None) -> bool:
    """
    Stores either a Unicode emoji or a custom Discord emoji literal.
    Pass None to clear it.
    """
    conn = await connect()
    try:
        await conn.execute("INSERT INTO items (id) VALUES (?) ON CONFLICT (id) DO NOTHING", (item_id,))
        await conn.execute("UPDATE items SET emoji = ? WHERE id = ?", (emoji, item_id))
        await conn.execute(
            "UPDATE items SET name = COALESCE(NULLIF(name,''), ?) WHERE id = ?",
            (item_id.replace("_", " ").title(), item_id)
        )
        await conn.commit()
        if _CACHE_ENABLED and db_cache is not None:
            try:
                db_cache.invalidate_item(item_id)
            except Exception:
                pass
        return True
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def find_item_id(query: str) -> str | None:
    """
    Try to resolve an item by id or by display name (case/spacing-insensitive).
    Returns the canonical items.id or None if not found.
    """
    q = (query or "").strip()
    if not q:
        return None

    # candidates: as-given, underscored id-ish, and plain spaced title
    import re
    cand_id = re.sub(r"[\s\-]+", "_", q.lower()).strip("_")
    cand_name = re.sub(r"[_\-]+", " ", q).strip().lower()

    conn = await connect()
    try:
        cur = await conn.execute("""
            SELECT id FROM items
            WHERE id = ? OR LOWER(name) = ?
            LIMIT 1
        """, (cand_id, cand_name))
        row = await cur.fetchone(); await cur.close()
        return row["id"] if row else None
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def item_exists(item_id: str) -> bool:
    conn = await connect()
    try:
        cur = await conn.execute("SELECT 1 FROM items WHERE id = ? LIMIT 1", (item_id,))
        row = await cur.fetchone(); await cur.close()
        return bool(row)
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def merge_item_ids(old_id: str, new_id: str) -> int:
    """
    Move all user_items rows from old_id -> new_id, summing quantities.
    Requires both ids to exist in items.
    Returns number of affected owner rows.
    """
    conn = await connect()
    try:
        # ensure target exists
        cur = await conn.execute("SELECT 1 FROM items WHERE id=? LIMIT 1", (new_id,))
        if await cur.fetchone() is None:
            raise ValueError(f"target item id '{new_id}' does not exist")
        await cur.close()

        # if the old id isn't present, nothing to do
        cur = await conn.execute("SELECT 1 FROM items WHERE id=? LIMIT 1", (old_id,))
        if await cur.fetchone() is None:
            await cur.close()
            return 0
        await cur.close()

        # upsert quantities into new_id
        await conn.execute("""
            INSERT INTO user_items (owner_id, item_id, qty)
            SELECT owner_id, ?, SUM(qty)
            FROM user_items
            WHERE item_id = ?
            GROUP BY owner_id
            ON CONFLICT(owner_id, item_id) DO UPDATE SET
                qty = user_items.qty + excluded.qty
        """, (new_id, old_id))

        # get affected owners before delete for cache invalidation
        cur = await conn.execute("SELECT DISTINCT owner_id FROM user_items WHERE item_id = ?", (old_id,))
        affected_owners = [row["owner_id"] for row in await cur.fetchall()]
        await cur.close()
        moved = len(affected_owners)

        await conn.execute("DELETE FROM user_items WHERE item_id = ?", (old_id,))
        # optionally remove the old master row too
        await conn.execute("DELETE FROM items WHERE id = ?", (old_id,))
        await conn.commit()
        if _CACHE_ENABLED and db_cache is not None:
            for oid in affected_owners:
                try:
                    db_cache.invalidate_bag(oid)
                except Exception:
                    pass
        return moved
    finally:
        try:
            await conn.close()
        except Exception:
            pass
def _canon_item_id(s: str) -> str:
    # normalize for duplicate detection (remove underscores/hyphens/spaces)
    return re.sub(r"[_\-\s]+", "", (s or "").lower())

async def find_orphan_user_item_ids() -> list[str]:
    """item_ids referenced in user_items that don't exist in items."""
    conn = await connect()
    try:
        cur = await conn.execute("""
            SELECT DISTINCT ui.item_id
            FROM user_items ui
            LEFT JOIN items it ON it.id = ui.item_id
            WHERE it.id IS NULL
            ORDER BY 1
        """)
        rows = [r[0] for r in await cur.fetchall()]
        await cur.close()
        return rows
    finally:
        try:
            await conn.close()
        except Exception:
            pass

async def find_probable_alias_pairs() -> list[tuple[str,str]]:
    """
    Return pairs of ids in items that look like duplicates
    (same canonical form, different exact id).
    """
    conn = await connect()
    try:
        cur = await conn.execute("SELECT id FROM items")
        ids = [r[0] for r in await cur.fetchall()]
        await cur.close()

        by_canon = {}
        for i in ids:
            by_canon.setdefault(_canon_item_id(i), []).append(i)
        pairs = []
        for canon, group in by_canon.items():
            if len(group) >= 2:
                # propose merging all into the first (longest underscore_form)
                group = sorted(group, key=len)   # shortest first
                target = group[-1]
                for alias in group[:-1]:
                    pairs.append((alias, target))
        return pairs
    finally:
        try:
            await conn.close()
        except Exception:
            pass

async def merge_many(pairs: list[tuple[str,str]]) -> list[tuple[str,str,int]]:
    """
    Merge a list of (old_id, new_id) pairs.
    Returns [(old,new,moved_rows), ...]
    """
    out = []
    for old_id, new_id in pairs:
        moved = await merge_item_ids(old_id, new_id)
        out.append((old_id, new_id, moved))
    return out
# ---------------------------------------------------------------------
# Team Presets
# ---------------------------------------------------------------------

async def save_team_preset(owner_id: str, preset_name: str, team_data: str) -> None:
    """Save a team preset. team_data should be JSON string of the team in Showdown format."""
    conn = await connect()
    try:
        now = dt.datetime.utcnow()
        await conn.execute("""
            INSERT INTO team_presets (owner_id, preset_name, team_data, created_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (owner_id, preset_name) DO UPDATE SET
                team_data = EXCLUDED.team_data,
                created_at = EXCLUDED.created_at
        """, (owner_id, preset_name, team_data, now))
        await conn.commit()
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def get_team_preset(owner_id: str, preset_name: str) -> Optional[str]:
    """Get a team preset's data (Showdown format string)."""
    conn = await connect()
    try:
        cur = await conn.execute("""
            SELECT team_data FROM team_presets
            WHERE owner_id=? AND preset_name=?
        """, (owner_id, preset_name))
        row = await cur.fetchone()
        await cur.close()
        return row["team_data"] if row else None
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def list_team_presets(owner_id: str) -> List[dict]:
    """List all team presets for a user."""
    conn = await connect()
    try:
        cur = await conn.execute("""
            SELECT preset_name, created_at FROM team_presets
            WHERE owner_id=?
            ORDER BY created_at DESC
        """, (owner_id,))
        rows = await cur.fetchall()
        await cur.close()
        return [dict(row) for row in rows]
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def delete_team_preset(owner_id: str, preset_name: str) -> bool:
    """Delete a team preset. Returns True if deleted, False if not found."""
    conn = await connect()
    try:
        cur = await conn.execute("""
            DELETE FROM team_presets
            WHERE owner_id=? AND preset_name=?
        """, (owner_id, preset_name))
        await conn.commit()
        return cur.rowcount > 0
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def ensure_shiny_trigger() -> None:
    """Shiny is handled in application code; no DB trigger for PostgreSQL."""
    return
