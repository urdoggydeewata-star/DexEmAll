# tools/precache.py
import asyncio
from lib import db
from lib.poke_ingest import ensure_species_and_learnsets

async def run():
    await db.init_schema()
    for pid in range(1, 152):
        e = await ensure_species_and_learnsets(pid)
        print(f"Cached #{e['id']} {e['name']}")
    await db.close()

if __name__ == "__main__":
    asyncio.run(run())
