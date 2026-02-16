#!/usr/bin/env python3
"""
Add columns that exist only in local SQLite (myuu.db) to Google Cloud PostgreSQL,
then backfill from local.

Usage:
  python -m tools.migrate_local_schema_to_cloud [--dry-run] [--no-backfill] [--backfill-only]

  --dry-run       Print ALTERs and backfill plan only; do not execute.
  --no-backfill   Add columns only; do not copy data from local.
  --backfill-only Run backfill only (no ALTERs). Use after adding columns manually.
  --tables a,b,c   Only alter/backfill these tables (e.g. --tables moves,pokedex).

Requires: myuu.db, DATABASE_URL/POSTGRES_DSN in .env.

Workflow:
  1. python -m tools.compare_db_schemas   # inspect diff
  2. python -m tools.migrate_local_schema_to_cloud --dry-run
  3. python -m tools.migrate_local_schema_to_cloud   # add columns + backfill
  4. python -m tools.cache_everything     # optional: refresh cache

Note: Cloud DB user must have ALTER privilege on affected tables (or be table owner).
      If you hit InsufficientPrivilegeError, run migrations as a superuser/owner.
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


def _sqlite_type_to_pg(raw: str) -> str:
    raw = (raw or "").strip().upper()
    if not raw:
        return "TEXT"
    if raw in ("INTEGER", "INT", "BIGINT", "SMALLINT"):
        return "INTEGER"
    if raw == "REAL" or raw.startswith("FLOAT"):
        return "DOUBLE PRECISION"
    if raw in ("TEXT", "VARCHAR", "CHAR") or raw.startswith("VARCHAR(") or raw.startswith("CHAR("):
        return "TEXT"
    if raw in ("BLOB",):
        return "TEXT"
    if raw in ("BOOL", "BOOLEAN"):
        return "BOOLEAN"
    return "TEXT"


def _get_local_schema_raw(path: Path) -> dict[str, list[dict[str, Any]]]:
    """{table: [{name, type_raw, notnull}, ...]}."""
    out: dict[str, list[dict[str, Any]]] = {}
    conn = sqlite3.connect(path)
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    tables = [r[0] for r in cur.fetchall()]
    for t in tables:
        cur = conn.execute(f"PRAGMA table_info({t})")
        out[t] = [
            {"name": r[1], "type_raw": (r[2] or "TEXT").strip(), "notnull": bool(r[3])}
            for r in cur.fetchall()
        ]
    conn.close()
    return out


def _pg_connect_kw(dsn: str) -> dict:
    """Options for asyncpg.connect when using pgbouncer (e.g. port 6432)."""
    if ":6432" in (dsn or ""):
        return {"statement_cache_size": 0}
    return {}


async def _get_pg_columns(dsn: str) -> dict[str, set[str]]:
    """{table: set(column_names)}."""
    import asyncpg
    out: dict[str, set[str]] = {}
    conn = await asyncpg.connect(dsn, **_pg_connect_kw(dsn))
    try:
        rows = await conn.fetch("""
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position
        """)
        for r in rows:
            t = r["table_name"]
            if t not in out:
                out[t] = set()
            out[t].add(r["column_name"])
    finally:
        await conn.close()
    return out


# PKs for backfill: table -> list of PK column names (order matters for matching).
_TABLE_PKS: dict[str, list[str]] = {
    "items": ["id"],
    "learnsets": ["species_id", "form_name", "move_id", "generation", "method"],
    "moves": ["id"],
    "pokedex": ["id"],
    "pokedex_forms": ["species_id", "form_key"],
    "pokemons": ["id"],
    "rulesets": ["scope"],  # cloud uses scope; local may differ – we only add columns
}

# Columns we backfill when using --backfill-only (after manual ALTERs).
# Must exist in both local and cloud.
_BACKFILL_ONLY_COLUMNS: dict[str, list[str]] = {
    "items": ["introduced_in"],
    "learnsets": ["move_introduced_in"],
    "moves": [
        "is_recoil_move", "is_drain_move", "is_multi_hit", "is_charge_move",
        "is_semi_invulnerable", "is_recharge_move", "is_ohko_move", "is_fixed_damage",
        "is_variable_power", "is_sound_move", "is_contact_move", "is_punch_move",
        "is_bite_move", "is_pulse_move", "is_bullet_move", "target", "effect_category",
        "stat_changes", "inflicts_status", "status_chance", "flinch_chance",
        "confusion_chance", "forces_switch", "traps_opponent", "sets_leech_seed",
        "sets_ingrain", "sets_aqua_ring", "destiny_bond", "perish_song", "healing_wish",
        "trick", "bestow", "recycle", "knock_off", "crash_damage", "priority",
    ],
    "pokedex": [
        "is_legendary", "is_mythical", "is_baby", "is_default", "color", "genus",
        "hatch_counter", "base_friendship", "evolution_chain_id", "has_mega_form",
        "has_dynamax_form", "has_gigantamax_form", "forms", "evolved_from",
    ],
    "pokedex_forms": [
        "introduced_in", "sprites", "base_experience", "height_m", "weight_kg",
        "is_default", "form_name", "is_mega", "base_happiness", "capture_rate",
        "egg_groups", "growth_rate", "ev_yield", "gender_ratio", "flavor", "color",
        "is_legendary", "is_mythical", "is_baby", "evolution_chain_id",
    ],
    "pokemons": ["is_mega", "mega_stone", "is_gigantamax"],
    "rulesets": ["name", "rules_json", "updated_at_utc"],
}


def _parse_tables_arg() -> set[str] | None:
    for a in sys.argv:
        if a.startswith("--tables="):
            return {x.strip() for x in a.split("=", 1)[1].split(",") if x.strip()}
    return None


def _pk_tuple(row: Any, pk: list[str]) -> tuple:
    """Normalize PK values to a comparable tuple (SQLite vs PG type-safe)."""
    out = []
    for p in pk:
        try:
            v = row[p]
        except (KeyError, TypeError):
            v = None
        if v is None:
            out.append("")
        elif isinstance(v, (int, float)):
            out.append(str(int(v)))
        else:
            out.append(str(v))
    return tuple(out)


async def _add_columns_and_backfill(
    dsn: str,
    local_path: Path,
    dry_run: bool,
    no_backfill: bool,
    backfill_only: bool = False,
    tables_filter: set[str] | None = None,
) -> None:
    import asyncpg

    local_raw = _get_local_schema_raw(local_path)
    pg_cols = await _get_pg_columns(dsn)
    alters: list[tuple[str, str, str, str]] = []
    backfill_map: dict[str, list[str]] = {}

    if backfill_only:
        for t, want_cols in _BACKFILL_ONLY_COLUMNS.items():
            if tables_filter and t not in tables_filter:
                continue
            if t not in pg_cols or t not in local_raw:
                continue
            cloud_set = pg_cols[t]
            local_set = {c["name"] for c in local_raw[t]}
            ok = [c for c in want_cols if c in cloud_set and c in local_set]
            if ok:
                backfill_map[t] = ok
    else:
        for t, lcols in local_raw.items():
            if tables_filter and t not in tables_filter:
                continue
            if t not in pg_cols:
                continue
            cloud_set = pg_cols[t]
            for c in lcols:
                if c["name"] in cloud_set:
                    continue
                pg_type = _sqlite_type_to_pg(c["type_raw"])
                default = " DEFAULT NULL" if not c["notnull"] else ""
                alters.append((t, c["name"], pg_type, default))
                if t not in backfill_map:
                    backfill_map[t] = []
                if c["name"] not in backfill_map[t]:
                    backfill_map[t].append(c["name"])

    if dry_run:
        print("--- DRY RUN: would run ---\n")
        if not backfill_only:
            for t, col, pg_type, default in alters:
                print(f"ALTER TABLE {t} ADD COLUMN {col} {pg_type}{default};")
        if not no_backfill and backfill_map:
            print("\n--- Backfill (local -> cloud) ---")
            for t, cols in backfill_map.items():
                pk = _TABLE_PKS.get(t, ["id"])
                print(f"  {t}: UPDATE cloud from local using PK {pk}, new cols {cols}")
        return

    conn = await asyncpg.connect(dsn, **_pg_connect_kw(dsn))
    try:
        if not backfill_only:
            for t, col, pg_type, default in alters:
                sql = f'ALTER TABLE "{t}" ADD COLUMN "{col}" {pg_type}{default}'
                try:
                    await conn.execute(sql)
                    print(f"  + {t}.{col}")
                except Exception as e:
                    if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                        print(f"  (skip {t}.{col}: already exists)")
                    else:
                        raise

        if no_backfill or not backfill_map:
            return

        _BATCH = 500
        _PROGRESS_EVERY = 10  # log progress every N batches
        sqlite_conn = sqlite3.connect(local_path)
        sqlite_conn.row_factory = sqlite3.Row
        try:
            for t, new_cols in backfill_map.items():
                pk = list(_TABLE_PKS.get(t) or [])
                if not pk:
                    print(f"  (skip backfill {t}: no PK mapping)")
                    continue
                local_cols = {x["name"] for x in local_raw.get(t, [])}
                if t == "rulesets" and "scope" not in local_cols and "generation" in local_cols:
                    pk = ["generation"]
                missing = [p for p in pk if p not in local_cols]
                if missing:
                    print(f"  (skip backfill {t}: local missing PK cols {missing})")
                    continue
                sentinel = new_cols[0]
                pk_list = ", ".join(f'"{p}"' for p in pk)
                try:
                    existing = await conn.fetch(
                        f'SELECT {pk_list} FROM "{t}" WHERE "{sentinel}" IS NOT NULL'
                    )
                    done_pks = {_pk_tuple(r, pk) for r in existing}
                except Exception as ex:
                    print(f"  (warning: {t} could not fetch already-filled PKs: {ex})")
                    done_pks = set()
                cols = list(pk) + list(new_cols)
                col_list = ", ".join(f'"{c}"' for c in cols)
                cur = sqlite_conn.execute(f'SELECT {col_list} FROM "{t}"')
                all_rows = cur.fetchall()
                rows = [r for r in all_rows if _pk_tuple(r, pk) not in done_pks]
                skipped_done = len(all_rows) - len(rows)
                # Skip rows where local has all new cols NULL (nothing to transfer)
                def _has_any_data(row: Any, cols: list[str]) -> bool:
                    for c in cols:
                        try:
                            v = row[c]
                        except (KeyError, TypeError):
                            continue
                        if v is None:
                            continue
                        if isinstance(v, str) and not v.strip():
                            continue
                        return True
                    return False
                rows = [r for r in rows if _has_any_data(r, new_cols)]
                skipped_nodata = len(all_rows) - len(rows) - skipped_done
                skipped = skipped_done + skipped_nodata
                if not rows:
                    parts = [f"{skipped_done} already in cloud"]
                    if skipped_nodata:
                        parts.append(f"{skipped_nodata} no local data")
                    print(f"  {t}: 0 rows to backfill ({', '.join(parts)})")
                    continue
                parts = [f"{skipped_done} already in cloud"]
                if skipped_nodata:
                    parts.append(f"{skipped_nodata} no local data")
                print(f"  {t}: {len(rows)} rows to backfill ({', '.join(parts)})")
                set_clause = ", ".join(f'"{c}" = v."{c}"' for c in new_cols)
                where_clause = " AND ".join(f'm."{p}" = v."{p}"' for p in pk)
                ncols = len(pk) + len(new_cols)
                total = 0
                num_batches = (len(rows) + _BATCH - 1) // _BATCH
                for b, i in enumerate(range(0, len(rows), _BATCH)):
                    chunk = rows[i : i + _BATCH]
                    placeholders = []
                    params: list[Any] = []
                    for r in chunk:
                        placeholders.append(
                            "(" + ", ".join(f"${len(params) + 1 + j}" for j in range(ncols)) + ")"
                        )
                        for c in pk:
                            params.append(r[c])
                        for c in new_cols:
                            params.append(r[c])
                    vals = ", ".join(placeholders)
                    col_names = ", ".join(f'"{c}"' for c in pk + new_cols)
                    sql = f'UPDATE "{t}" AS m SET {set_clause} FROM (VALUES {vals}) AS v({col_names}) WHERE {where_clause}'
                    try:
                        await conn.execute(sql, *params)
                    except Exception as e:
                        for row in chunk:
                            pk_vals = [row[p] for p in pk]
                            updates = ", ".join(f'"{c}" = ${j+1}' for j, c in enumerate(new_cols))
                            where = " AND ".join(f'"{p}" = ${len(new_cols)+1+j}' for j, p in enumerate(pk))
                            params1 = [row[c] for c in new_cols] + pk_vals
                            sql1 = f'UPDATE "{t}" SET {updates} WHERE {where}'
                            try:
                                await conn.execute(sql1, *params1)
                                total += 1
                            except Exception as e1:
                                print(f"  warning: {t} backfill row {pk_vals}: {e1}")
                        if (b + 1) % _PROGRESS_EVERY == 0 or b + 1 == num_batches:
                            print(f"    -> {total}/{len(rows)} rows")
                        continue
                    total += len(chunk)
                    if (b + 1) % _PROGRESS_EVERY == 0 or b + 1 == num_batches:
                        print(f"    -> {total}/{len(rows)} rows")
                print(f"  backfilled {t}: {total} rows" + (f" ({skipped} skipped)" if skipped else ""))
        finally:
            sqlite_conn.close()
    finally:
        await conn.close()


def main() -> None:
    dry = "--dry-run" in sys.argv
    no_bf = "--no-backfill" in sys.argv
    bf_only = "--backfill-only" in sys.argv
    if bf_only:
        no_bf = False
    local_path = _find_sqlite()
    dsn = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN")

    if not local_path:
        print("Local myuu.db not found.")
        sys.exit(1)
    if not dsn:
        print("DATABASE_URL / POSTGRES_DSN not set.")
        sys.exit(1)

    tables_filter = _parse_tables_arg()
    if bf_only:
        print("Backfill only (local -> cloud)")
    else:
        print("Migration: add local-only columns to cloud + backfill")
    if tables_filter:
        print(f"  Tables: {', '.join(sorted(tables_filter))}")
    print(f"  Local: {local_path}")
    print(f"  Cloud: {dsn.split('@')[-1] if '@' in dsn else '(hidden)'}")
    print()

    import asyncio
    asyncio.run(_add_columns_and_backfill(dsn, local_path, dry, no_bf, bf_only, tables_filter))
    print("Done.")


if __name__ == "__main__":
    main()
