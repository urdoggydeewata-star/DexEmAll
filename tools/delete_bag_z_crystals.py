"""
Delete all Z crystal items with -bag or --bag suffixes.
"""

import sqlite3

DB_PATH = "myuu.db"

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    try:
        # Find all bag variants
        cur = conn.execute("""
            SELECT id, name FROM items 
            WHERE (id LIKE '%-bag' OR id LIKE '%--bag')
            AND (id LIKE '%-z-%' OR id LIKE '%-z')
        """)
        bag_items = cur.fetchall()
        
        print(f"Found {len(bag_items)} bag variant Z crystals:")
        for row in bag_items:
            print(f"  {row['id']}: {row['name']}")
        
        if not bag_items:
            print("\nNo bag variant Z crystals found!")
            return
        
        # Delete from user_items
        deleted_user_items = 0
        for row in bag_items:
            cur = conn.execute("SELECT COUNT(*) FROM user_items WHERE item_id = ?", (row["id"],))
            count = cur.fetchone()[0]
            if count > 0:
                conn.execute("DELETE FROM user_items WHERE item_id = ?", (row["id"],))
                deleted_user_items += count
                print(f"  Deleted {count} user_items entries for {row['id']}")
        
        # Delete from pokemons held_item
        deleted_held_items = 0
        for row in bag_items:
            cur = conn.execute("SELECT COUNT(*) FROM pokemons WHERE held_item = ?", (row["id"],))
            count = cur.fetchone()[0]
            if count > 0:
                conn.execute("UPDATE pokemons SET held_item = NULL WHERE held_item = ?", (row["id"],))
                deleted_held_items += count
                print(f"  Removed {count} held_item references for {row['id']}")
        
        # Delete from items table
        for row in bag_items:
            conn.execute("DELETE FROM items WHERE id = ?", (row["id"],))
        
        conn.commit()
        
        print(f"\n=== Summary ===")
        print(f"Deleted {len(bag_items)} bag variant Z crystals")
        print(f"Removed {deleted_user_items} user_items entries")
        print(f"Removed {deleted_held_items} held_item references")
        
        # Show remaining standard Z crystals
        cur = conn.execute("""
            SELECT id, name FROM items 
            WHERE (id LIKE '%-z' OR id LIKE '%-z-%')
            AND id NOT LIKE '%-bag' 
            AND id NOT LIKE '%--bag'
            ORDER BY id
        """)
        remaining = cur.fetchall()
        print(f"\nRemaining standard Z crystals: {len(remaining)}")
        for row in remaining[:20]:  # Show first 20
            print(f"  {row['id']}: {row['name']}")
        if len(remaining) > 20:
            print(f"  ... and {len(remaining) - 20} more")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    main()











