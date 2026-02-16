#!/usr/bin/env python3
"""
Compare schema (tables + columns) between local SQLite (myuu.db) and Google Cloud PostgreSQL.

Usage:
  python -m tools.compare_db_schemas

Requires:
  - myuu.db (local SQLite) in project root or MYUU_DB
  - DATABASE_URL or POSTGRES_DSN in .env for Google Cloud PostgreSQL
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

# Project root
ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    _env = ROOT / ".env"
    if _env.exists():
        with open(_env, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if len(v) >= 2 and ((v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'"))):
                        v = v[1:-1]
                    os.environ.setdefault(k, v)

# Resolve local SQLite path
def _find_sqlite() -> Path | None:
    for p in [ROOT / "myuu.db", Path.cwd() / "myuu.db", ROOT / "data" / "myuu.db"]:
        if p.exists():
            return p
    env = os.getenv("MYUU_DB")
    if env and Path(env).exists():
        return Path(env)
    return None


def _normalize_type(t: str, dialect: str) -> str:
    """Normalize type for comparison (INT vs INTEGER, etc.)."""
    if not t:
        return ""
    t = t.upper().strip()
    # SQLite: INTEGER, TEXT, REAL, BLOB
    # PG: INTEGER, BIGINT, SMALLINT, TEXT, VARCHAR(n), BOOLEAN, JSONB, etc.
    m = {
        "INT": "INTEGER",
        "INTEGER": "INTEGER",
        "BIGINT": "INTEGER",
        "SMALLINT": "INTEGER",
        "TEXT": "TEXT",
        "VARCHAR": "TEXT",
        "CHARACTER VARYING": "TEXT",
        "REAL": "REAL",
        "DOUBLE PRECISION": "REAL",
        "FLOAT": "REAL",
        "BOOL": "BOOLEAN",
        "BOOLEAN": "BOOLEAN",
        "JSON": "JSON",
        "JSONB": "JSON",
        "BLOB": "BLOB",
        "SERIAL": "INTEGER",
        "BIGSERIAL": "INTEGER",
    }
    for k, v in m.items():
        if t == k or t.startswith(k + "("):
            return v
    return t


def get_sqlite_schema(path: Path) -> dict[str, list[dict[str, Any]]]:
    """Return {table: [{name, type, notnull, pk}, ...]}."""
    out: dict[str, list[dict[str, Any]]] = {}
    conn = sqlite3.connect(path)
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    tables = [r[0] for r in cur.fetchall()]
    for t in tables:
        cur = conn.execute(f"PRAGMA table_info({t})")
        rows = cur.fetchall()
        # cid, name, type, notnull, dflt_value, pk
        out[t] = [
            {
                "name": r[1],
                "type": _normalize_type(r[2] or "", "sqlite"),
                "notnull": bool(r[3]),
                "pk": bool(r[5]),
            }
            for r in rows
        ]
    conn.close()
    return out


def get_pg_schema(dsn: str) -> dict[str, list[dict[str, Any]]]:
    """Return {table: [{name, type, notnull, pk}, ...]}."""
    try:
        import asyncpg
    except ImportError:
        print("asyncpg not installed. pip install asyncpg")
        sys.exit(1)

    out: dict[str, list[dict[str, Any]]] = {}

    async def run():
        conn = await asyncpg.connect(dsn)
        try:
            rows = await conn.fetch("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """)
            tables = [r["table_name"] for r in rows]
            for t in tables:
                cols = await conn.fetch("""
                    SELECT c.column_name AS name,
                           c.data_type AS data_type,
                           c.udt_name AS udt_name,
                           c.is_nullable = 'NO' AS notnull,
                           EXISTS (
                               SELECT 1 FROM information_schema.table_constraints tc
                               JOIN information_schema.key_column_usage kcu
                                    ON tc.constraint_name = kcu.constraint_name
                                    AND tc.table_schema = kcu.table_schema
                               WHERE tc.table_schema = 'public' AND tc.table_name = $1
                                 AND tc.constraint_type = 'PRIMARY KEY'
                                 AND kcu.column_name = c.column_name
                           ) AS pk
                    FROM information_schema.columns c
                    WHERE c.table_schema = 'public' AND c.table_name = $1
                    ORDER BY c.ordinal_position
                """, t)
                out[t] = []
                for r in cols:
                    dt = r["data_type"] or ""
                    ut = (r["udt_name"] or "").lower()
                    if ut in ("varchar", "char", "bpchar"):
                        dt = "TEXT"
                    elif ut in ("int4", "int8", "int2", "serial", "bigserial"):
                        dt = "INTEGER"
                    elif ut == "bool":
                        dt = "BOOLEAN"
                    elif ut in ("jsonb", "json"):
                        dt = "JSON"
                    out[t].append({
                        "name": r["name"],
                        "type": _normalize_type(dt, "pg"),
                        "notnull": bool(r["notnull"]),
                        "pk": bool(r["pk"]),
                    })
        finally:
            await conn.close()

    import asyncio
    asyncio.run(run())
    return out


def main() -> None:
    local_path = _find_sqlite()
    dsn = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN")

    if not local_path:
        print("Local SQLite: myuu.db not found.")
        sys.exit(1)
    if not dsn:
        print("Google Cloud Postgres: DATABASE_URL / POSTGRES_DSN not set.")
        sys.exit(1)

    print("Fetching schemas...")
    local = get_sqlite_schema(local_path)
    try:
        cloud = get_pg_schema(dsn)
    except Exception as e:
        print(f"Failed to connect to Postgres: {e}")
        sys.exit(1)

    local_tables = set(local)
    cloud_tables = set(cloud)

    only_local = sorted(local_tables - cloud_tables)
    only_cloud = sorted(cloud_tables - local_tables)
    common = sorted(local_tables & cloud_tables)

    print()
    print("=" * 70)
    print("LOCAL (SQLite) vs GOOGLE CLOUD (PostgreSQL) SCHEMA DIFF")
    print("=" * 70)
    print(f"Local DB:  {local_path}")
    print(f"Cloud DSN: {dsn.split('@')[-1] if '@' in dsn else '(hidden)'}")
    print()

    if only_local:
        print("--- Tables ONLY in LOCAL (missing in cloud) ---")
        for t in only_local:
            cols = [c["name"] for c in local[t]]
            print(f"  {t}: {cols}")
        print()

    if only_cloud:
        print("--- Tables ONLY in CLOUD (missing locally) ---")
        for t in only_cloud:
            cols = [c["name"] for c in cloud[t]]
            print(f"  {t}: {cols}")
        print()

    print("--- COMMON TABLES: column differences ---")
    for t in common:
        lcols = {c["name"]: c for c in local[t]}
        ccols = {c["name"]: c for c in cloud[t]}
        only_l = sorted(set(lcols) - set(ccols))
        only_c = sorted(set(ccols) - set(lcols))
        type_diff = []
        for n in sorted(set(lcols) & set(ccols)):
            lc, cc = lcols[n], ccols[n]
            if lc["type"] != cc["type"] or lc["notnull"] != cc["notnull"]:
                type_diff.append((n, lc["type"], cc["type"], lc["notnull"], cc["notnull"]))
        if not (only_l or only_c or type_diff):
            continue
        print(f"\n  [{t}]")
        if only_l:
            print(f"    Only in LOCAL:  {only_l}")
        if only_c:
            print(f"    Only in CLOUD:  {only_c}")
        for n, lt, ct, ln, cn in type_diff:
            nn = " NOT NULL" if ln else ""
            cc = " NOT NULL" if cn else ""
            print(f"    Type diff '{n}': local {lt}{nn}  vs  cloud {ct}{cc}")

    print()
    print("Done.")


if __name__ == "__main__":
    main()
