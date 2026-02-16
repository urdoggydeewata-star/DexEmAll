"""Script to remove Z crystal items with -bag suffix from database and update references."""
import sqlite3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

def find_db():
    """Find the database file."""
    candidates = ['myuu.db', '../myuu.db', '../../myuu.db', 'data/myuu.db']
    for path in candidates:
        full_path = Path(__file__).parent.parent / path
        if full_path.exists():
            return str(full_path)
    return 'myuu.db'

def main():
    db_path = find_db()
    print(f"Connecting to database: {db_path}")
    
    if not Path(db_path).exists():
        print(f"Error: Database file not found at {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    # Find all items with -bag or --bag suffix that are Z crystals
    cur = conn.execute("""
        SELECT id FROM items 
        WHERE (id LIKE '%-bag' OR id LIKE '%--bag')
        AND (id LIKE '%-z-%' OR id LIKE '%z--bag' OR id LIKE '%z-bag')
    """)
    items = [row[0] for row in cur.fetchall()]
    
    if not items:
        print("No Z crystal items with -bag suffix found.")
        conn.close()
        return
    
    print(f"\nFound {len(items)} Z crystal items with -bag suffix:")
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
        
        # Replace with non-bag versions
        print("\nReplacing bag items with non-bag versions...")
        for item_id in items:
            # Remove -bag or --bag suffix
            new_id = item_id.replace('--bag', '').replace('-bag', '')
            
            # Check if the non-bag version exists
            cur = conn.execute("SELECT id FROM items WHERE id = ?", (new_id,))
            if cur.fetchone():
                # Update Pokemon holding the -bag version to use the non-bag version
                conn.execute("""
                    UPDATE pokemons 
                    SET held_item = ? 
                    WHERE held_item = ?
                """, (new_id, item_id))
                print(f"  [OK] Updated {item_id} -> {new_id}")
            else:
                print(f"  [WARN] {new_id} does not exist, creating it...")
                # Create the non-bag version by copying from bag version
                cur = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,))
                old_item = cur.fetchone()
                if old_item:
                    # Insert new item with non-bag id
                    conn.execute("""
                        INSERT INTO items (id, name, emoji, icon_url, category, description, price, sell_price)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        new_id,
                        old_item.get('name', new_id),
                        old_item.get('emoji'),
                        old_item.get('icon_url'),
                        old_item.get('category'),
                        old_item.get('description'),
                        old_item.get('price'),
                        old_item.get('sell_price')
                    ))
                    # Update Pokemon to use new item
                    conn.execute("""
                        UPDATE pokemons 
                        SET held_item = ? 
                        WHERE held_item = ?
                    """, (new_id, item_id))
                    print(f"  [OK] Created {new_id} and updated Pokemon")
                else:
                    print(f"  [WARN] Could not find original item data, removing from Pokemon")
                    conn.execute("""
                        UPDATE pokemons 
                        SET held_item = NULL 
                        WHERE held_item = ?
                    """, (item_id,))
        
        conn.commit()
    
    # Check user_items and merge quantities
    print("\nMerging user_items quantities...")
    for item_id in items:
        new_id = item_id.replace('--bag', '').replace('-bag', '')
        # Get quantities for both versions
        cur = conn.execute("""
            SELECT owner_id, SUM(qty) as total_qty
            FROM user_items
            WHERE item_id IN (?, ?)
            GROUP BY owner_id
        """, (item_id, new_id))
        merged_items = cur.fetchall()
        
        for row in merged_items:
            owner_id = row['owner_id']
            total_qty = row['total_qty']
            
            # Delete both old entries
            conn.execute("DELETE FROM user_items WHERE owner_id = ? AND item_id IN (?, ?)", 
                        (owner_id, item_id, new_id))
            # Insert merged quantity
            conn.execute("""
                INSERT INTO user_items (owner_id, item_id, qty)
                VALUES (?, ?, ?)
            """, (owner_id, new_id, total_qty))
        
        print(f"  [OK] Merged quantities for {new_id}")
    
    conn.commit()
    
    # Delete from user_items (any remaining)
    print("\nDeleting remaining bag items from user_items...")
    cur = conn.execute(f"""
        DELETE FROM user_items 
        WHERE item_id IN ({placeholders})
    """, items)
    deleted_items = cur.rowcount
    print(f"  [OK] Deleted {deleted_items} entries from user_items")
    
    # Delete from items table
    print("\nDeleting bag items from items table...")
    cur = conn.execute(f"""
        DELETE FROM items 
        WHERE id IN ({placeholders})
    """, items)
    deleted_items = cur.rowcount
    print(f"  [OK] Deleted {deleted_items} items from items table")
    
    conn.commit()
    conn.close()
    
    print("\n[DONE] All -bag Z crystal items have been removed and merged.")

if __name__ == "__main__":
    main()












