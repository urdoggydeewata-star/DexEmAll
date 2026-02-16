#!/usr/bin/env python3
"""
Verify that migration backfill (local SQLite -> cloud PostgreSQL) completed successfully.
Compares row counts and sample data for key tables/columns.

Usage:
  python -m tools.verify_migration

Run after: python -m tools.migrate_local_schema_to_cloud   (add columns + backfill)
Requires: myuu.db, DATABASE_URL or POSTGRES_DSN in .env.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    _e = ROOT / ".env"
    if _e.exists():
        with open(_e, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                if len(v) >= 2 and (v[0] == v[-1] == '"' or v[0] == v[-1] == "'"):
                    v = v[1:-1]
                os.environ.setdefault(k, v)


def _find_sqlite() -> Path | None:
    for p in [ROOT / "myuu.db", Path.cwd() / "myuu.db", ROOT / "data" / "myuu.db"]:
        if p.exists():
            return p
    env = os.getenv("MYUU_DB")
    if env and Path(env).exists():
        return Path(env)
    return None


def _pg_connect_kw(dsn: str) -> dict:
    if ":6432" in (dsn or ""):
        return {"statement_cache_size": 0}
    return {}


# Tables we care about, with a "signature" new column to verify backfill.
# (table, pk_col, check_column) – we compare COUNT(*) and COUNT(check_column IS NOT NULL).
_VERIFY: list[tuple[str, str, str]] = [
    ("moves", "id", "priority"),
    ("pokedex", "id", "is_legendary"),
    ("items", "id", "introduced_in"),
    ("learnsets", "species_id", "move_introduced_in"),
    ("pokedex_forms", "species_id", "introduced_in"),
    ("pokemons", "id", "is_mega"),
    ("rulesets", "scope", "name"),
]


def _local_count(conn: sqlite3.Connection, table: str) -> int:
    cur = conn.execute(f'SELECT COUNT(*) FROM "{table}"')
    return cur.fetchone()[0]


def _local_nonnull_count(conn: sqlite3.Connection, table: str, col: str) -> int:
    try:
        cur = conn.execute(f'SELECT COUNT(*) FROM "{table}" WHERE "{col}" IS NOT NULL')
        return cur.fetchone()[0]
    except sqlite3.OperationalError:
        return -1


def _local_sample(conn: sqlite3.Connection, table: str, pk: str, col: str, n: int = 3) -> list[tuple]:
    try:
        cur = conn.execute(
            f'SELECT "{pk}", "{col}" FROM "{table}" WHERE "{col}" IS NOT NULL ORDER BY "{pk}" LIMIT {n}'
        )
        return cur.fetchall()
    except sqlite3.OperationalError:
        return []


async def _pg_count(conn, table: str) -> int:
    row = await conn.fetchrow(f'SELECT COUNT(*) AS c FROM "{table}"')
    return row["c"] if row else 0


async def _pg_nonnull_count(conn, table: str, col: str) -> int:
    try:
        row = await conn.fetchrow(
            f'SELECT COUNT(*) AS c FROM "{table}" WHERE "{col}" IS NOT NULL'
        )
        return row["c"] if row else 0
    except Exception:
        return -1


async def _pg_sample(conn, table: str, pk: str, col: str, n: int = 3) -> list[tuple]:
    try:
        rows = await conn.fetch(
            f'SELECT "{pk}", "{col}" FROM "{table}" WHERE "{col}" IS NOT NULL ORDER BY "{pk}" LIMIT {n}'
        )
        return [(r[pk], r[col]) for r in rows]
    except Exception:
        return []


async def _run() -> None:
    import asyncpg

    local_path = _find_sqlite()
    dsn = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN")
    if not local_path:
        print("Local myuu.db not found.")
        sys.exit(1)
    if not dsn:
        print("DATABASE_URL / POSTGRES_DSN not set.")
        sys.exit(1)

    print("Verify migration: local vs cloud")
    print(f"  Local: {local_path}")
    print(f"  Cloud: {dsn.split('@')[-1] if '@' in dsn else '(hidden)'}\n")

    local_conn = sqlite3.connect(local_path)
    pg_conn = await asyncpg.connect(dsn, **_pg_connect_kw(dsn))
    all_ok = True

    try:
        print(f"{'Table':<18} {'Local rows':>10} {'Cloud rows':>10} {'Local NN':>10} {'Cloud NN':>10}  Status")
        print("-" * 72)

        for table, pk, col in _VERIFY:
            lr = _local_count(local_conn, table)
            cr = await _pg_count(pg_conn, table)
            ln = _local_nonnull_count(local_conn, table, col)
            cn = await _pg_nonnull_count(pg_conn, table, col)

            if ln == -1 or cn == -1:
                status = "skip (no col)"
            elif lr != cr:
                status = "ROW COUNT MISMATCH"
                all_ok = False
            elif ln != cn and ln > 0:
                status = f"NN MISMATCH (local {ln} vs cloud {cn})"
                all_ok = False
            elif ln == 0 and cn == 0:
                status = "ok (no data)"
            else:
                status = "ok"

            print(f"{table:<18} {lr:>10} {cr:>10} {ln:>10} {cn:>10}  {status}")

        print()
        # Spot-check a few rows: moves.priority, pokedex.is_legendary
        print("Spot-check (local vs cloud sample):")
        for table, pk, col in [("moves", "id", "priority"), ("pokedex", "id", "is_legendary")]:
            ls = _local_sample(local_conn, table, pk, col, 3)
            ps = await _pg_sample(pg_conn, table, pk, col, 3)
            if not ls and not ps:
                print(f"  {table}.{col}: no non-null rows")
                continue
            match = True
            for i, (lp, lv) in enumerate(ls):
                if i >= len(ps):
                    match = False
                    break
                pp, pv = ps[i]
                if lp != pp or lv != pv:
                    match = False
                    break
            if len(ps) != len(ls):
                match = False
            s = "ok" if match else "MISMATCH"
            if not match:
                all_ok = False
            print(f"  {table}.{col}: {s}")
            if ls:
                print(f"    local  sample: {ls[:3]}")
            if ps:
                print(f"    cloud  sample: {[(p, v) for p, v in ps[:3]]}")
    finally:
        local_conn.close()
        await pg_conn.close()

    print()
    if all_ok:
        print("Verification passed.")
    else:
        print("Verification FAILED — review mismatches above.")
        sys.exit(1)


def main() -> None:
    import asyncio
    asyncio.run(_run())


if __name__ == "__main__":
    main()
