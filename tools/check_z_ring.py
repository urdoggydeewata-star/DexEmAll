"""
Check Z-Ring equipment in database
"""

import sqlite3

DB_PATH = "myuu.db"

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    print("Checking user_equipment table...")
    print("-" * 60)
    
    # Check if table exists
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_equipment'")
    if not cur.fetchone():
        print("❌ user_equipment table does not exist!")
        conn.close()
        return
    
    # Get all users with any gear
    cur = conn.execute("""
        SELECT owner_id, z_gear, dmax_gear, mega_gear, tera_gear 
        FROM user_equipment 
        ORDER BY owner_id
    """)
    rows = cur.fetchall()
    cur.close()
    
    if not rows:
        print("No users found in user_equipment table")
        conn.close()
        return
    
    print(f"Found {len(rows)} users in user_equipment table:\n")
    
    for row in rows:
        owner_id = row["owner_id"]
        z_gear = row["z_gear"]
        dmax_gear = row["dmax_gear"]
        mega_gear = row["mega_gear"]
        tera_gear = row["tera_gear"]
        
        print(f"User ID: {owner_id}")
        print(f"  Z-Ring: {z_gear if z_gear else '(none)'}")
        print(f"  Dynamax Band: {dmax_gear if dmax_gear else '(none)'}")
        print(f"  Mega Gear: {mega_gear if mega_gear else '(none)'}")
        print(f"  Tera Orb: {tera_gear if tera_gear else '(none)'}")
        
        # Check if z_gear exists but is empty string
        if z_gear == "":
            print(f"  ⚠️  WARNING: Z-Ring is empty string (not NULL)!")
        elif z_gear:
            # Check if it's a valid item
            item_cur = conn.execute("SELECT id, name FROM items WHERE id = ?", (z_gear,))
            item_row = item_cur.fetchone()
            item_cur.close()
            if item_row:
                print(f"  OK: Z-Ring item found in items table: {item_row['name']} ({item_row['id']})")
            else:
                print(f"  ⚠️  WARNING: Z-Ring item '{z_gear}' not found in items table!")
        print()
    
    conn.close()

if __name__ == "__main__":
    main()
