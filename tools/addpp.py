
import sqlite3, sys
db=r"C:\Users\adama\OneDrive\Bureau\myuu clone\myuu.db"
con=sqlite3.connect(db); con.row_factory=sqlite3.Row
tables=[r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("Tables:", tables)
if "moves" in tables:
    cols=[r["name"] for r in con.execute("PRAGMA table_info('moves')")]
    print("moves columns:", cols)
else:
    print("No 'moves' table.")
