#!/usr/bin/env python3
"""
Show differences between local SQLite (myuu.db) and Google Cloud PostgreSQL.
Reports: row counts, rows only in local, only in cloud, and column-level diffs
for rows present in both.

By default, timestamp columns (created_at, updated_at_utc, added_at) are
ignored—time-format / timezone differences are treated as normal.

Usage:
  python -m tools.diff_local_cloud [--tables a,b,c] [--all] [--max-diffs N]
    [--ignore-cols col1,col2] [--show-timestamps]

  --tables a,b,c     Only diff these tables (default: all common tables).
  --all              Same; diff all tables present in both DBs.
  --max-diffs N      Max rows to show for "only in local/cloud" and "differ"
                     (default 15). Use 0 for no limit.
  --ignore-cols c,s  Comma-separated columns to exclude from diff.
  --show-timestamps  Include created_at, updated_at_utc, added_at in diff
                     (default: ignore them).

Requires: myuu.db, DATABASE_URL or POSTGRES_DSN in .env.
"""

from __future__ import annotations

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


# Table -> PK columns (must exist in both local and cloud). Used for matching rows.
_TABLE_PKS: dict[str, list[str]] = {
    "admins": ["user_id"],
    "config": ["key"],
    "event_log": ["id"],
    "format_rules": ["format", "gen"],
    "generations": ["id"],
    "gigantamax": ["id"],
    "item_effects": ["item_name"],
    "items": ["id"],
    "learnsets": ["species_id", "form_name", "move_id", "generation", "method"],
    "mega_evolution": ["id"],
    "mega_forms": ["base_species_id", "mega_species_id"],
    "move_generation_stats": ["move_id", "generation"],
    "moves": ["id"],
    "pokedex": ["id"],
    "pokedex_forms": ["species_id", "form_key"],
    "pokemons": ["id"],
    "primal_reversion": ["id"],
    "pvp_format_rules": ["format_key", "generation"],
    "pvp_formats": ["key"],
    "rulesets": ["scope"],
    "team_presets": ["owner_id", "preset_name"],
    "user_boxes": ["owner_id", "box_no"],
    "user_equipment": ["owner_id"],
    "user_items": ["owner_id", "item_id"],
    "user_meta": ["owner_id"],
    "user_rulesets": ["user_id"],
    "users": ["user_id"],
}


def _norm_val(v: Any) -> str:
    """Normalize value for comparison (SQLite vs PG type-safe)."""
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
    if hasattr(v, "isoformat"):
        return getattr(v, "isoformat")()
    return str(v)


def _pk_tuple(row: dict[str, Any], pk: list[str]) -> tuple[str, ...]:
    """Normalize PK values to comparable tuple."""
    out = []
    for c in pk:
        v = row.get(c)
        if v is None:
            out.append("")
        elif isinstance(v, (int, float)):
            out.append(str(int(v)))
        else:
            out.append(str(v).strip())
    return tuple(out)


def _local_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in cur.fetchall()]


def _local_count(conn: sqlite3.Connection, table: str) -> int:
    cur = conn.execute(f'SELECT COUNT(*) FROM "{table}"')
    return cur.fetchone()[0]


def _local_rows_dict(
    conn: sqlite3.Connection,
    table: str,
    cols: list[str],
    order_cols: list[str],
) -> list[dict[str, Any]]:
    cols_sql = ", ".join(f'"{c}"' for c in cols)
    order_sql = ", ".join(f'"{c}"' for c in order_cols)
    cur = conn.execute(
        f'SELECT {cols_sql} FROM "{table}" ORDER BY {order_sql}'
    )
    rows = cur.fetchall()
    return [dict(zip(cols, r)) for r in rows]


async def _pg_columns(conn, table: str) -> list[str]:
    r = await conn.fetch("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1
        ORDER BY ordinal_position
    """, table)
    return [x["column_name"] for x in r]


async def _pg_count(conn, table: str) -> int:
    row = await conn.fetchrow(f'SELECT COUNT(*) AS c FROM "{table}"')
    return row["c"] if row else 0


async def _pg_rows_dict(conn, table: str, cols: list[str], order_cols: list[str]) -> list[dict[str, Any]]:
    cols_sql = ", ".join(f'"{c}"' for c in cols)
    order_sql = ", ".join(f'"{c}"' for c in order_cols)
    rows = await conn.fetch(
        f'SELECT {cols_sql} FROM "{table}" ORDER BY {order_sql}'
    )
    return [dict(zip(cols, (r[c] for c in cols))) for r in rows]


def _resolve_pk(table: str, local_cols: set[str], pg_cols: set[str]) -> list[str]:
    pk = _TABLE_PKS.get(table) or ["id"]
    if table == "rulesets" and "scope" not in local_cols and "generation" in local_cols:
        pk = ["generation"]
    return [c for c in pk if c in local_cols and c in pg_cols]


def _trunc(s: str, n: int = 60) -> str:
    s = str(s)
    return s if len(s) <= n else s[: n - 3] + "..."


# Timestamp columns ignored by default (format/TZ diffs are normal).
_DEFAULT_IGNORE_TIMESTAMPS = {"created_at", "updated_at_utc", "added_at"}


def _parse_args() -> tuple[set[str] | None, bool, int, set[str]]:
    tables: set[str] | None = None
    use_all = "--all" in sys.argv
    max_diffs = 15
    ignore_cols: set[str] = set()
    show_timestamps = "--show-timestamps" in sys.argv
    for a in sys.argv:
        if a.startswith("--tables="):
            tables = {x.strip() for x in a.split("=", 1)[1].split(",") if x.strip()}
        elif a.startswith("--max-diffs="):
            try:
                max_diffs = max(0, int(a.split("=", 1)[1]))
            except ValueError:
                pass
        elif a.startswith("--ignore-cols="):
            ignore_cols = {x.strip() for x in a.split("=", 1)[1].split(",") if x.strip()}
    if not show_timestamps:
        ignore_cols = ignore_cols | _DEFAULT_IGNORE_TIMESTAMPS
    return tables, use_all, max_diffs, ignore_cols


async def _run() -> None:
    import asyncpg

    tables_filter, use_all, max_diffs, ignore_cols = _parse_args()

    local_path = _find_sqlite()
    dsn = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN")
    if not local_path:
        print("Local myuu.db not found.")
        sys.exit(1)
    if not dsn:
        print("DATABASE_URL / POSTGRES_DSN not set.")
        sys.exit(1)

    print("Diff: local (SQLite) vs cloud (PostgreSQL)")
    print(f"  Local: {local_path}")
    print(f"  Cloud: {dsn.split('@')[-1] if '@' in dsn else '(hidden)'}")
    print(f"  Max diffs per section: {max_diffs if max_diffs else 'unlimited'}")
    if ignore_cols:
        print(f"  Ignore cols (timestamp etc.): {', '.join(sorted(ignore_cols))}")
    print()

    local = sqlite3.connect(local_path)
    local.row_factory = sqlite3.Row
    pg = await asyncpg.connect(dsn, **_pg_kw(dsn))

    local_tables = set()
    for r in local.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall():
        local_tables.add(r[0])
    pg_tables = set()
    for r in await pg.fetch("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
    """):
        pg_tables.add(r["table_name"])
    common = sorted(local_tables & pg_tables)

    if tables_filter:
        to_diff = sorted(tables_filter & set(common))
        missing = tables_filter - set(common)
        if missing:
            print(f"  Skipping (not in both DBs): {', '.join(sorted(missing))}\n")
    else:
        to_diff = common

    identical_tables: list[str] = []
    differ_tables: list[str] = []
    skip_tables: list[str] = []

    for table in to_diff:
        lcols = set(_local_columns(local, table))
        pcols = set(await _pg_columns(pg, table))
        common_cols = sorted(lcols & pcols)
        if not common_cols:
            lc = _local_count(local, table)
            cc = await _pg_count(pg, table)
            skip_tables.append(table)
            print(f"=== {table} ===")
            print(f"  Local rows: {lc}  |  Cloud rows: {cc}")
            print("  skip: no common columns")
            print("  local cols: " + ", ".join(sorted(lcols)))
            print("  cloud cols: " + ", ".join(sorted(pcols)))
            print()
            continue

        order_cols = _resolve_pk(table, lcols, pcols)
        if not order_cols:
            lc = _local_count(local, table)
            cc = await _pg_count(pg, table)
            skip_tables.append(table)
            print(f"=== {table} ===")
            print(f"  Local rows: {lc}  |  Cloud rows: {cc}")
            print("  skip: no common PK (add table to _TABLE_PKS in this script)")
            print("  local cols: " + ", ".join(sorted(lcols)))
            print("  cloud cols: " + ", ".join(sorted(pcols)))
            print()
            continue

        lc = _local_count(local, table)
        cc = await _pg_count(pg, table)
        lrows = _local_rows_dict(local, table, common_cols, order_cols)
        prows = await _pg_rows_dict(pg, table, common_cols, order_cols)

        lmap = {_pk_tuple(r, order_cols): r for r in lrows}
        pmap = {_pk_tuple(r, order_cols): r for r in prows}
        lkeys = set(lmap)
        pkeys = set(pmap)

        only_local = sorted(lkeys - pkeys)
        only_cloud = sorted(pkeys - lkeys)
        both_keys = lkeys & pkeys
        diff_cols = [c for c in common_cols if c not in ignore_cols]
        diffs: list[tuple[tuple[str, ...], list[tuple[str, str, str]]]] = []
        for k in both_keys:
            lr, pr = lmap[k], pmap[k]
            col_diffs: list[tuple[str, str, str]] = []
            for c in diff_cols:
                ln = _norm_val(lr[c])
                pn = _norm_val(pr[c])
                if ln != pn:
                    col_diffs.append((c, _trunc(ln, 80), _trunc(pn, 80)))
            if col_diffs:
                diffs.append((k, col_diffs))

        identical = lc == cc and not only_local and not only_cloud and not diffs
        if identical:
            identical_tables.append(table)
        else:
            differ_tables.append(table)
        print(f"=== {table} ===")
        print(f"  Local rows: {lc}  |  Cloud rows: {cc}")
        if identical:
            print("  IDENTICAL")
            print()
            continue

        pk_label = ", ".join(order_cols)
        if only_local:
            n = len(only_local)
            show = only_local[: max_diffs] if max_diffs else only_local
            print(f"  Only in LOCAL: {n} row(s)")
            for k in show:
                print(f"    PK ({pk_label}): {k}")
            if max_diffs and n > max_diffs:
                print(f"    ... and {n - max_diffs} more")
        if only_cloud:
            n = len(only_cloud)
            show = only_cloud[: max_diffs] if max_diffs else only_cloud
            print(f"  Only in CLOUD: {n} row(s)")
            for k in show:
                print(f"    PK ({pk_label}): {k}")
            if max_diffs and n > max_diffs:
                print(f"    ... and {n - max_diffs} more")
        if diffs:
            n = len(diffs)
            show = diffs[: max_diffs] if max_diffs else diffs
            print(f"  In BOTH but DIFFER: {n} row(s)")
            for k, col_diffs in show:
                print(f"    PK ({pk_label}): {k}")
                for col, lv, pv in col_diffs:
                    print(f"      {col}:  local {lv!r}  vs  cloud {pv!r}")
            if max_diffs and n > max_diffs:
                print(f"    ... and {n - max_diffs} more rows with diffs")
        print()

    local.close()
    await pg.close()

    print("---")
    print(f"Summary: {len(identical_tables)} identical, {len(differ_tables)} differ, {len(skip_tables)} skipped")
    if differ_tables:
        print(f"  Differ: {', '.join(differ_tables)}")
    if skip_tables:
        print(f"  Skip:   {', '.join(skip_tables)}")
    print("Done.")


def main() -> None:
    import asyncio
    asyncio.run(_run())


if __name__ == "__main__":
    main()
