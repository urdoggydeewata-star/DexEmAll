# tools/wipe_user.py
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "myuu.db"

def wipe(uid: str):
    con = sqlite3.connect(DB.as_posix())
    try:
        con.execute("PRAGMA foreign_keys = ON;")
        # optional: drop admin flag first
        con.execute("DELETE FROM admins WHERE user_id = ?", (uid,))
        # delete the user -> cascades to pokemons, inventory, event_log
        cur = con.execute("DELETE FROM users WHERE user_id = ?", (uid,))
        con.commit()
        print(f"Deleted user {uid}. Rows affected in users: {cur.rowcount}")
    finally:
        con.close()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python tools/wipe_user.py <discord_user_id>")
        sys.exit(1)
    wipe(sys.argv[1])
