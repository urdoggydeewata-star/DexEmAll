#!/usr/bin/env python3
"""
Sync local SQLite (myuu.db) -> Google Cloud PostgreSQL so cloud matches local.
Updates differing rows, inserts rows only in local, optionally deletes rows only in cloud.

Default tables: pokedex, pokedex_forms, team_presets (the ones that typically differ).

Usage:
  python -m tools.sync_local_to_cloud [--tables a,b,c] [--dry-run] [--no-delete]

  --tables a,b,c  Only sync these tables (default: pokedex, pokedex_forms, team_presets).
  --dry-run       Print planned changes only; do not write to cloud.
  --no-delete     Do not delete cloud-only rows (only UPDATE + INSERT).

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


_DEFAULT_TABLES = ["pokedex", "pokedex_forms", "team_presets"]
_IGNORE_COLS = {"created_at", "updated_at_utc", "added_at"}

_TABLE_PKS: dict[str, list[str]] = {
    "pokedex": ["id"],
    "pokedex_forms": ["species_id", "form_key"],
    "team_presets": ["owner_id", "preset_name"],
}

# Cloud columns that are JSONB (we pass JSON-serializable values).
_PG_JSONB: set[tuple[str, str]] = {
    ("pokedex", "evolution"), ("pokedex", "types"), ("pokedex", "stats"),
    ("pokedex", "abilities"), ("pokedex", "sprites"), ("pokedex", "egg_groups"),
    ("pokedex", "ev_yield"), ("pokedex", "gender_ratio"),
    ("pokedex_forms", "stats"), ("pokedex_forms", "types"), ("pokedex_forms", "abilities"),
    ("team_presets", "team_data"),
}

# Cloud BOOLEAN columns: normalize ''/None -> None, '0'/0 -> False, '1'/1 -> True.
_PG_BOOL: set[tuple[str, str]] = {
    ("pokedex", "is_fully_evolved"),
    ("pokedex_forms", "is_battle_only"),
}


def _pk_tuple(row: dict[str, Any], pk: list[str]) -> tuple[str, ...]:
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


def _to_pg_val(table: str, col: str, v: Any) -> Any:
    if (table, col) in _PG_BOOL:
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return None
        if v is True or v == "1" or v == 1 or (isinstance(v, str) and v.strip().lower() in ("1", "true", "yes")):
            return True
        return False
    if v is None:
        return None
    if (table, col) in _PG_JSONB:
        if isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=False)
        if isinstance(v, str):
            s = v.strip()
            if s.startswith("{") or s.startswith("["):
                try:
                    return json.dumps(json.loads(s), ensure_ascii=False)
                except json.JSONDecodeError:
                    pass
            return json.dumps(s, ensure_ascii=False)
        return json.dumps(str(v), ensure_ascii=False)
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v
    return str(v)


def _local_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in cur.fetchall()]


def _local_rows_dict(
    conn: sqlite3.Connection,
    table: str,
    cols: list[str],
    order_cols: list[str],
) -> list[dict[str, Any]]:
    cols_sql = ", ".join(f'"{c}"' for c in cols)
    order_sql = ", ".join(f'"{c}"' for c in order_cols)
    cur = conn.execute(f'SELECT {cols_sql} FROM "{table}" ORDER BY {order_sql}')
    return [dict(zip(cols, r)) for r in cur.fetchall()]


async def _pg_columns(conn, table: str) -> list[str]:
    r = await conn.fetch("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1
        ORDER BY ordinal_position
    """, table)
    return [x["column_name"] for x in r]


async def _pg_rows_dict(conn, table: str, cols: list[str], order_cols: list[str]) -> list[dict[str, Any]]:
    cols_sql = ", ".join(f'"{c}"' for c in cols)
    order_sql = ", ".join(f'"{c}"' for c in order_cols)
    rows = await conn.fetch(
        f'SELECT {cols_sql} FROM "{table}" ORDER BY {order_sql}'
    )
    return [dict(zip(cols, (r[c] for c in cols))) for r in rows]


def _resolve_pk(table: str, local_cols: set[str], pg_cols: set[str]) -> list[str]:
    pk = _TABLE_PKS.get(table) or ["id"]
    return [c for c in pk if c in local_cols and c in pg_cols]


def _parse_args() -> tuple[set[str], bool, bool]:
    tables = set(_DEFAULT_TABLES)
    dry_run = "--dry-run" in sys.argv
    no_delete = "--no-delete" in sys.argv
    for a in sys.argv:
        if a.startswith("--tables="):
            tables = {x.strip() for x in a.split("=", 1)[1].split(",") if x.strip()}
            break
    return tables, dry_run, no_delete


async def _run() -> None:
    import asyncpg

    tables_filter, dry_run, no_delete = _parse_args()

    local_path = _find_sqlite()
    dsn = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN")
    if not local_path:
        print("Local myuu.db not found.")
        sys.exit(1)
    if not dsn:
        print("DATABASE_URL / POSTGRES_DSN not set.")
        sys.exit(1)

    print("Sync local -> cloud")
    print(f"  Local: {local_path}")
    print(f"  Cloud: {dsn.split('@')[-1] if '@' in dsn else '(hidden)'}")
    print(f"  Tables: {', '.join(sorted(tables_filter))}")
    if dry_run:
        print("  [DRY RUN]")
    if no_delete:
        print("  [NO DELETE]")
    print()

    local = sqlite3.connect(local_path)
    local.row_factory = sqlite3.Row
    pg = await asyncpg.connect(dsn, **_pg_kw(dsn))

    total_upd, total_ins, total_del = 0, 0, 0

    try:
        for table in sorted(tables_filter):
            lcols = set(_local_columns(local, table))
            pcols = set(await _pg_columns(pg, table))
            common = sorted(lcols & pcols)
            if not common:
                print(f"[{table}] skip: no common columns")
                continue
            order_cols = _resolve_pk(table, lcols, pcols)
            if not order_cols:
                print(f"[{table}] skip: no common PK")
                continue
            sync_cols = [c for c in common if c not in _IGNORE_COLS]
            if not sync_cols:
                print(f"[{table}] skip: no columns to sync (all ignored)")
                continue

            lrows = _local_rows_dict(local, table, common, order_cols)
            prows = await _pg_rows_dict(pg, table, common, order_cols)
            lmap = {_pk_tuple(r, order_cols): r for r in lrows}
            pmap = {_pk_tuple(r, order_cols): r for r in prows}
            lkeys = set(lmap)
            pkeys = set(pmap)
            only_local = sorted(lkeys - pkeys)
            only_cloud = sorted(pkeys - lkeys)
            both = lkeys & pkeys

            # UPDATE rows in both: overwrite cloud with local for sync_cols
            upd = 0
            for k in both:
                lr = lmap[k]
                if dry_run:
                    upd += 1
                    continue
                set_args: list[Any] = [_to_pg_val(table, c, lr[c]) for c in sync_cols]
                where_args: list[Any] = [
                    lr[c] if isinstance(lr[c], (int, float)) and not isinstance(lr[c], bool) else str(lr[c])
                    for c in order_cols
                ]
                n = len(sync_cols)
                set_clause = ", ".join(f'"{c}" = ${i+1}' for i, c in enumerate(sync_cols))
                where_clause = " AND ".join(f'"{c}" = ${n + 1 + i}' for i, c in enumerate(order_cols))
                await pg.execute(f'UPDATE "{table}" SET {set_clause} WHERE {where_clause}', *set_args, *where_args)
                upd += 1
            if upd:
                print(f"[{table}] updated {upd} row(s)")
                total_upd += upd

            # INSERT only-in-local
            ins = 0
            for k in only_local:
                lr = lmap[k]
                if dry_run:
                    ins += 1
                    continue
                vals: list[Any] = []
                for c in common:
                    v = lr[c]
                    if (table, c) in _PG_JSONB or (table, c) in _PG_BOOL:
                        vals.append(_to_pg_val(table, c, v))
                    elif v is None:
                        vals.append(None)
                    elif isinstance(v, (int, float, bool)):
                        vals.append(v)
                    else:
                        vals.append(str(v))
                col_list = ", ".join(f'"{c}"' for c in common)
                ph = ", ".join(f"${i+1}" for i in range(len(common)))
                pk_list = ", ".join(f'"{c}"' for c in order_cols)
                update_set = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in common if c not in order_cols)
                if update_set:
                    sql = f'INSERT INTO "{table}" ({col_list}) VALUES ({ph}) ON CONFLICT ({pk_list}) DO UPDATE SET {update_set}'
                else:
                    sql = f'INSERT INTO "{table}" ({col_list}) VALUES ({ph}) ON CONFLICT ({pk_list}) DO NOTHING'
                await pg.execute(sql, *vals)
                ins += 1
            if ins:
                print(f"[{table}] inserted {ins} row(s)")
                total_ins += ins

            # DELETE only-in-cloud
            if not no_delete and only_cloud:
                del_n = len(only_cloud)
                if dry_run:
                    print(f"[{table}] would delete {del_n} cloud-only row(s)")
                    total_del += del_n
                else:
                    for k in only_cloud:
                        pr = pmap[k]
                        where_clause = " AND ".join(f'"{c}" = ${i+1}' for i, c in enumerate(order_cols))
                        args = [pr[c] if isinstance(pr[c], (int, float)) and not isinstance(pr[c], bool) else str(pr[c]) for c in order_cols]
                        await pg.execute(f'DELETE FROM "{table}" WHERE {where_clause}', *args)
                    print(f"[{table}] deleted {del_n} cloud-only row(s)")
                    total_del += del_n
    finally:
        local.close()
        await pg.close()

    print()
    print(f"Done. Updated {total_upd}, inserted {total_ins}, deleted {total_del}.")


def main() -> None:
    import asyncio
    asyncio.run(_run())


if __name__ == "__main__":
    main()
