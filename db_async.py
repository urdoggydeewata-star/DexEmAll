# db_async.py
# Async SQLite helper for your bot

import os
import aiosqlite

# Set MYUU_DB env var if you want a custom path; defaults to myuu.db in the repo
DB_PATH = os.getenv("MYUU_DB", "myuu.db")

async def connect() -> aiosqlite.Connection:
    con = await aiosqlite.connect(DB_PATH)
    con.row_factory = aiosqlite.Row
    await con.execute("PRAGMA foreign_keys = ON;")
    return con

# Optional convenience helpers (used by some examples)
async def get_pokedex_by_id(pid: int):
    async with await connect() as con:
        cur = await con.execute('SELECT * FROM pokedex WHERE id=?', (pid,))
        row = await cur.fetchone()
        await cur.close()
        return dict(row) if row else None

async def get_pokedex_by_name(name: str):
    async with await connect() as con:
        cur = await con.execute('SELECT * FROM pokedex WHERE LOWER(name)=LOWER(?)', (name,))
        row = await cur.fetchone()
        await cur.close()
        return dict(row) if row else None
