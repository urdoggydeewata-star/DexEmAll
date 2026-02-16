"""
Fill missing `tera_type` values in the pokemons table.

For each Pokémon without a Tera Type, pick one uniformly from its
species' native types (matching in-game default rolls) and update the DB.
"""
from __future__ import annotations

import asyncio
import json
import random
import sys
from pathlib import Path
from typing import Iterable, Optional

# Ensure project root is on sys.path so `lib.db` resolves even when run directly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib import db


def _normalize_type(value: object) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip().lower()
    return s or None


def _extract_types(raw: object) -> list[str]:
    if raw is None:
        return []

    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = [raw]
    else:
        parsed = raw

    types: list[str] = []
    if isinstance(parsed, str):
        parsed = [parsed]
    if isinstance(parsed, Iterable):
        for item in parsed:
            norm = _normalize_type(item)
            if norm and norm not in types:
                types.append(norm)
    return types


def _roll_tera_type(types: Iterable[str]) -> Optional[str]:
    pool = [t for t in types if t]
    if not pool:
        return None
    return random.choice(pool)


async def fill_missing_tera_types() -> None:
    conn = await db.connect()
    cur = await conn.execute(
        """
        SELECT p.id, p.owner_id, p.species, p.tera_type, pd.types AS species_types
        FROM pokemons AS p
        LEFT JOIN pokedex AS pd ON LOWER(pd.name) = LOWER(p.species)
        WHERE COALESCE(p.tera_type, '') = ''
        """
    )
    rows = await cur.fetchall()
    await cur.close()

    if not rows:
        print("No Pokémon with missing tera_type.")
        return

    updated = 0
    skipped = 0

    for row in rows:
        types = _extract_types(row["species_types"])
        tera_type = _roll_tera_type(types)
        if not tera_type:
            skipped += 1
            print(
                f"Skipping {row['species']} (owner {row['owner_id']} id {row['id']}): "
                "no species types found."
            )
            continue

        await conn.execute(
            "UPDATE pokemons SET tera_type=? WHERE id=?",
            (tera_type, row["id"]),
        )
        updated += 1
        print(
            f"Set tera_type='{tera_type}' for {row['species']} "
            f"(owner {row['owner_id']} id {row['id']})"
        )

    if updated:
        await conn.commit()

    print(f"Completed. Updated {updated} Pokémon. Skipped {skipped}.")


if __name__ == "__main__":
    asyncio.run(fill_missing_tera_types())

