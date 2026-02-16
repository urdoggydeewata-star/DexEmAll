#!/usr/bin/env python3
"""
Sync rulesets from local SQLite (myuu.db) to Google Cloud PostgreSQL.
Updates name, rules_json, updated_at_utc in cloud for each generation.

Local rulesets has (generation, name, rules_json, updated_at_utc).
Cloud rulesets is matched by generation; all cloud rows with that generation
are updated from the single local row.

Usage:
  python -m tools.fix_rulesets_cloud [--dry-run]

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


def _pg_kw(dsn: str) -> dict:
    return {"statement_cache_size": 0} if ":6432" in (dsn or "") else {}


async def _run(dry_run: bool) -> None:
    import asyncpg

    local_path = _find_sqlite()
    dsn = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN")
    if not local_path:
        print("Local myuu.db not found.")
        sys.exit(1)
    if not dsn:
        print("DATABASE_URL / POSTGRES_DSN not set.")
        sys.exit(1)

    print("Fix rulesets: local -> cloud")
    print(f"  Local: {local_path}")
    print(f"  Cloud: {dsn.split('@')[-1] if '@' in dsn else '(hidden)'}")
    if dry_run:
        print("  [DRY RUN]")
    print()

    local = sqlite3.connect(local_path)
    local.row_factory = sqlite3.Row
    cur = local.execute(
        'SELECT generation, name, rules_json, updated_at_utc FROM rulesets ORDER BY generation'
    )
    rows = cur.fetchall()
    local.close()

    if not rows:
        print("No rulesets rows in local.")
        return

    if dry_run:
        print(f"Would update {len(rows)} generation(s) in cloud:")
        for r in rows:
            print(f"  gen={r['generation']} name={r['name']!r}")
        return

    pg = await asyncpg.connect(dsn, **_pg_kw(dsn))
    updated = 0
    try:
        for r in rows:
            gen = r["generation"]
            name = r["name"]
            rules_json = r["rules_json"]
            updated_at = r["updated_at_utc"]
            result = await pg.execute(
                """UPDATE rulesets SET name = $1, rules_json = $2, updated_at_utc = $3
                   WHERE generation = $4""",
                name, rules_json, updated_at, gen,
            )
            # result is like "UPDATE 1" or "UPDATE 3"
            n = int(result.split()[-1]) if result else 0
            updated += n
            if n:
                print(f"  gen={gen}: updated {n} row(s)")
    finally:
        await pg.close()

    print(f"\nDone. Updated {updated} cloud row(s) from {len(rows)} local row(s).")


def main() -> None:
    import asyncio
    dry = "--dry-run" in sys.argv
    asyncio.run(_run(dry))


if __name__ == "__main__":
    main()
