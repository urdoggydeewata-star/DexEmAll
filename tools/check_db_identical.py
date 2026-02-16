#!/usr/bin/env python3
"""
Check if local SQLite (myuu.db) and Google Cloud PostgreSQL are identical
for selected tables. Compares row counts and content checksums (over common columns).

Usage:
  python -m tools.check_db_identical [--tables a,b,c] [--skip-checksum] [--all] [-v|--verbose]

  --tables a,b,c   Only check these tables (default: migration-relevant set).
  --skip-checksum  Compare row counts only; do not checksum content.
  --all            Check all tables present in both DBs.
  -v, --verbose    On checksum mismatch, print first differing row/column/value.

Requires: myuu.db, DATABASE_URL or POSTGRES_DSN in .env.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

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


def _pg_kw(dsn: str) -> dict:
    return {"statement_cache_size": 0} if ":6432" in (dsn or "") else {}


# Table -> PK columns for ordering. rulesets: use generation when local has no scope.
_TABLE_PKS: dict[str, list[str]] = {
    "items": ["id"],
    "learnsets": ["species_id", "form_name", "move_id", "generation", "method"],
    "moves": ["id"],
    "pokedex": ["id"],
    "pokedex_forms": ["species_id", "form_key"],
    "pokemons": ["id"],
    "rulesets": ["scope"],
}

# Default tables to check (migration-relevant).
_DEFAULT_TABLES = ["moves", "pokedex", "items", "learnsets", "pokedex_forms", "pokemons", "rulesets"]


def _norm_val(v: Any) -> str:
    """Normalize value for hashing (SQLite vs PG type-safe)."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int) and not isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        return str(int(v)) if v == int(v) else repr(v)
    try:
        import decimal
        if isinstance(v, decimal.Decimal):
            f = float(v)
            return str(int(f)) if f == int(f) else repr(f)
    except Exception:
        pass
    if isinstance(v, (dict, list)):
        return json.dumps(v, sort_keys=True)
    if isinstance(v, str) and len(v) > 0 and v.strip().startswith(("{", "[")):
        try:
            return json.dumps(json.loads(v), sort_keys=True)
        except (json.JSONDecodeError, TypeError):
            pass
    # datetime, date, etc.
    if hasattr(v, "isoformat"):
        return getattr(v, "isoformat")()
    return str(v)


def _local_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in cur.fetchall()]


def _local_count(conn: sqlite3.Connection, table: str) -> int:
    cur = conn.execute(f'SELECT COUNT(*) FROM "{table}"')
    return cur.fetchone()[0]


def _local_row_iter(
    conn: sqlite3.Connection,
    table: str,
    cols: list[str],
    order_cols: list[str],
):
    cols_sql = ", ".join(f'"{c}"' for c in cols)
    order_sql = ", ".join(f'"{c}"' for c in order_cols)
    cur = conn.execute(
        f'SELECT {cols_sql} FROM "{table}" ORDER BY {order_sql}'
    )
    for row in cur:
        yield row


async def _pg_columns(conn, table: str) -> list[str]:
    rows = await conn.fetch("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1
        ORDER BY ordinal_position
    """, table)
    return [r["column_name"] for r in rows]


async def _pg_count(conn, table: str) -> int:
    row = await conn.fetchrow(f'SELECT COUNT(*) AS c FROM "{table}"')
    return row["c"] if row else 0


async def _pg_row_iter(conn, table: str, cols: list[str], order_cols: list[str]):
    cols_sql = ", ".join(f'"{c}"' for c in cols)
    order_sql = ", ".join(f'"{c}"' for c in order_cols)
    rows = await conn.fetch(
        f'SELECT {cols_sql} FROM "{table}" ORDER BY {order_sql}'
    )
    for r in rows:
        yield tuple(r[c] for c in cols)


def _checksum(row_iter, col_count: int) -> str:
    h = hashlib.sha256()
    for row in row_iter:
        parts = [_norm_val(row[i]) for i in range(col_count)]
        h.update(json.dumps(parts, ensure_ascii=False).encode("utf-8"))
    return h.hexdigest()


def _resolve_pk(table: str, local_cols: set[str], pg_cols: set[str]) -> list[str]:
    pk = _TABLE_PKS.get(table) or ["id"]
    if table == "rulesets" and "scope" not in local_cols and "generation" in local_cols:
        pk = ["generation"]
    # Use only PK columns that exist in both.
    return [c for c in pk if c in local_cols and c in pg_cols]


def _first_diff(
    local_conn: sqlite3.Connection,
    table: str,
    common_cols: list[str],
    order_cols: list[str],
    pg_rows: list[tuple],
) -> tuple[int, int, str, str, str] | None:
    """Return (row_idx, col_idx, col_name, local_norm, cloud_norm) for first diff, else None."""
    n = len(common_cols)
    local_iter = _local_row_iter(local_conn, table, common_cols, order_cols)
    for idx, (lrow, prow) in enumerate(zip(local_iter, pg_rows)):
        for j in range(n):
            ln = _norm_val(lrow[j])
            pn = _norm_val(prow[j])
            if ln != pn:
                return (idx, j, common_cols[j], ln[:120], pn[:120])
    return None


def _parse_args() -> tuple[set[str] | None, bool, bool, bool]:
    tables: set[str] | None = None
    skip_checksum = "--skip-checksum" in sys.argv
    all_tables = "--all" in sys.argv
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    for a in sys.argv:
        if a.startswith("--tables="):
            tables = {x.strip() for x in a.split("=", 1)[1].split(",") if x.strip()}
            break
    if all_tables and tables is None:
        tables = None
    elif not all_tables and tables is None:
        tables = set(_DEFAULT_TABLES)
    return tables, skip_checksum, all_tables, verbose


async def _run() -> None:
    import asyncpg

    tables_filter, skip_checksum, use_all, verbose = _parse_args()

    local_path = _find_sqlite()
    dsn = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN")
    if not local_path:
        print("Local myuu.db not found.")
        sys.exit(1)
    if not dsn:
        print("DATABASE_URL / POSTGRES_DSN not set.")
        sys.exit(1)

    print("Check DB identical: local vs cloud")
    print(f"  Local: {local_path}")
    print(f"  Cloud: {dsn.split('@')[-1] if '@' in dsn else '(hidden)'}")
    if skip_checksum:
        print("  Mode: row counts only")
    if verbose:
        print("  Verbose: show first diff on checksum mismatch")
    if use_all:
        print("  Mode: all common tables")
    elif tables_filter:
        print(f"  Tables: {', '.join(sorted(tables_filter))}")
    print()

    local = sqlite3.connect(local_path)
    pg = await asyncpg.connect(dsn, **_pg_kw(dsn))

    # Discover tables
    local_tables = set()
    cur = local.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    for r in cur.fetchall():
        local_tables.add(r[0])
    pg_tables = set()
    rows = await pg.fetch("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
    """)
    for r in rows:
        pg_tables.add(r["table_name"])
    common = sorted(local_tables & pg_tables)

    if use_all:
        to_check = common
    elif tables_filter:
        to_check = sorted(tables_filter & set(common))
        missing = tables_filter - set(common)
        if missing:
            print(f"  Skipping (not in both DBs): {', '.join(sorted(missing))}\n")
    else:
        to_check = sorted(set(_DEFAULT_TABLES) & set(common))

    if not to_check:
        print("No tables to check.")
        local.close()
        await pg.close()
        return

    print(f"{'Table':<18} {'Local N':>10} {'Cloud N':>10}  {'Checksum':<12}  Status")
    print("-" * 60)
    all_ok = True

    try:
        for table in to_check:
            lcols = set(_local_columns(local, table))
            pcols = set(await _pg_columns(pg, table))
            common_cols = sorted(lcols & pcols)
            if not common_cols:
                print(f"{table:<18} {'—':>10} {'—':>10}  {'—':<12}  skip (no common cols)")
                continue

            order_cols = _resolve_pk(table, lcols, pcols)
            if not order_cols:
                print(f"{table:<18} {'—':>10} {'—':>10}  {'—':<12}  skip (no common PK)")
                continue

            lc = _local_count(local, table)
            cc = await _pg_count(pg, table)
            row_ok = lc == cc

            if not row_ok:
                print(f"{table:<18} {lc:>10} {cc:>10}  {'—':<12}  ROW COUNT MISMATCH")
                all_ok = False
                continue

            if skip_checksum:
                print(f"{table:<18} {lc:>10} {cc:>10}  {'—':<12}  ok (count)")
                continue

            lh = _checksum(
                _local_row_iter(local, table, common_cols, order_cols),
                len(common_cols),
            )
            prows = [r async for r in _pg_row_iter(pg, table, common_cols, order_cols)]
            ph = _checksum(iter(prows), len(common_cols))
            chk_ok = lh == ph
            chk_str = "match" if chk_ok else "DIFF"
            if not chk_ok:
                all_ok = False
            status = "ok" if chk_ok else "CHECKSUM MISMATCH"
            print(f"{table:<18} {lc:>10} {cc:>10}  {chk_str:<12}  {status}")
            if not chk_ok and verbose and prows:
                diff = _first_diff(local, table, common_cols, order_cols, prows)
                if diff:
                    ri, cj, col, ln, pn = diff
                    print(f"    First diff row={ri} col={col!r}: local {ln!r} vs cloud {pn!r}")
    finally:
        local.close()
        await pg.close()

    print()
    if all_ok:
        print("Databases are IDENTICAL for checked tables.")
    else:
        print("Databases DIFFER — review mismatches above.")
        sys.exit(1)


def main() -> None:
    import asyncio
    asyncio.run(_run())


if __name__ == "__main__":
    main()
