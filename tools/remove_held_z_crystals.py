"""Script to remove Z crystal items with -held suffix from database."""
import sqlite3
from pathlib import Path
import sys
import os

# Add parent directory to path to import db_async
sys.path.insert(0, str(Path(__file__).parent.parent))

def find_db():
    """Find the database file."""
    candidates = ['myuu.db', '../myuu.db', '../../myuu.db', 'data/myuu.db']
    for path in candidates:
        full_path = Path(__file__).parent.parent / path
        if full_path.exists():
            return str(full_path)
    # Fall back to current directory
    return 'myuu.db'

def main():
    db_path = find_db()
    print(f"Connecting to database: {db_path}")
    
    if not Path(db_path).exists():
        print(f"Error: Database file not found at {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    # Find all items with -held or --held suffix
    cur = conn.execute("""
        SELECT id FROM items 
        WHERE id LIKE '%-held' OR id LIKE '%--held'
    """)
    items = [row[0] for row in cur.fetchall()]
    
    if not items:
        print("No Z crystal items with -held suffix found.")
        conn.close()
        return
    
    print(f"\nFound {len(items)} items with -held suffix:")
    for item in items:
        print(f"  - {item}")
    
    # Check if any Pokemon are holding these items
    placeholders = ','.join(['?'] * len(items))
    cur = conn.execute(f"""
        SELECT COUNT(*) as count, held_item
        FROM pokemons 
        WHERE held_item IN ({placeholders})
        GROUP BY held_item
    """, items)
    pokemon_holding = cur.fetchall()
    
    if pokemon_holding:
        print(f"\nWARNING: Found {sum(row['count'] for row in pokemon_holding)} Pokemon holding these items:")
        for row in pokemon_holding:
            print(f"  - {row['held_item']}: {row['count']} Pokemon")
        
        # Replace with non-held versions
        print("\nReplacing held items with non-held versions...")
        for item_id in items:
            # Remove -held or --held suffix
            new_id = item_id.replace('--held', '').replace('-held', '')
            
            # Check if the non-held version exists
            cur = conn.execute("SELECT id FROM items WHERE id = ?", (new_id,))
            if cur.fetchone():
                # Update Pokemon holding the -held version to use the non-held version
                conn.execute("""
                    UPDATE pokemons 
                    SET held_item = ? 
                    WHERE held_item = ?
                """, (new_id, item_id))
                print(f"  [OK] Updated {item_id} -> {new_id}")
            else:
                print(f"  [WARN] {new_id} does not exist, removing item from Pokemon")
                conn.execute("""
                    UPDATE pokemons 
                    SET held_item = NULL 
                    WHERE held_item = ?
                """, (item_id,))
        
        conn.commit()
    
    # Delete from user_items
    print("\nDeleting from user_items...")
    cur = conn.execute(f"""
        DELETE FROM user_items 
        WHERE item_id IN ({placeholders})
    """, items)
    deleted_items = cur.rowcount
    print(f"  [OK] Deleted {deleted_items} entries from user_items")
    
    # Delete from items table
    print("\nDeleting from items table...")
    cur = conn.execute(f"""
        DELETE FROM items 
        WHERE id IN ({placeholders})
    """, items)
    deleted_items = cur.rowcount
    print(f"  [OK] Deleted {deleted_items} items from items table")
    
    conn.commit()
    conn.close()
    
    print("\n[DONE] All -held Z crystal items have been removed.")

if __name__ == "__main__":
    main()

