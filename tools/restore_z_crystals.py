"""
Restore standard Z crystals from PokeAPI (no -bag or --bag variants).
Only adds the normal variants needed for PvP.
"""

import sqlite3
import requests
import json

DB_PATH = "myuu.db"

def get_z_crystals_from_pokeapi():
    """Fetch all Z crystal items from PokeAPI."""
    print("Fetching Z crystals from PokeAPI...")
    
    # Get item category for Z-Crystals (category ID 33)
    category_url = "https://pokeapi.co/api/v2/item-category/33/"
    try:
        response = requests.get(category_url, timeout=10)
        if response.status_code != 200:
            print(f"Error fetching category: {response.status_code}")
            return []
        
        category_data = response.json()
        items = category_data.get("items", [])
        
        z_crystals = []
        for item_entry in items:
            item_url = item_entry["url"]
            try:
                item_response = requests.get(item_url, timeout=10)
                if item_response.status_code == 200:
                    item_data = item_response.json()
                    item_id = item_data["name"]  # PokeAPI uses name like "normalium-z"
                    
                    # Skip -bag variants
                    if "-bag" in item_id or "--bag" in item_id:
                        continue
                    
                    item_name = item_data.get("names", [{}])
                    # Find English name
                    eng_name = None
                    for name_entry in item_name:
                        if name_entry.get("language", {}).get("name") == "en":
                            eng_name = name_entry.get("name", "")
                            break
                    
                    z_crystals.append({
                        "id": item_id,
                        "name": eng_name or item_id.replace("-", " ").title(),
                        "url": item_url
                    })
            except Exception as e:
                print(f"Error fetching item {item_url}: {e}")
        
        print(f"Found {len(z_crystals)} Z crystals from PokeAPI")
        return z_crystals
    except Exception as e:
        print(f"Error fetching Z crystals: {e}")
        return []

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    try:
        # Get current Z crystals in DB (standard ones only, no -bag)
        cur = conn.execute("""
            SELECT id, name FROM items 
            WHERE (id LIKE '%-z' OR id LIKE '%-z-%')
            AND id NOT LIKE '%-bag' 
            AND id NOT LIKE '%--bag'
            ORDER BY id
        """)
        current_items = {row["id"]: row["name"] for row in cur.fetchall()}
        
        print(f"\nCurrent standard Z crystals in database: {len(current_items)}")
        for item_id, item_name in sorted(current_items.items()):
            print(f"  {item_id}: {item_name}")
        
        # Fetch Z crystals from PokeAPI
        api_crystals = get_z_crystals_from_pokeapi()
        
        # Always use fallback list to ensure all crystals are added
        print("\nUsing complete Z crystal list...")
        api_crystals = [
            {"id": "normalium-z", "name": "Normalium Z"},
            {"id": "firium-z", "name": "Firium Z"},
            {"id": "waterium-z", "name": "Waterium Z"},
            {"id": "electrium-z", "name": "Electrium Z"},
            {"id": "grassium-z", "name": "Grassium Z"},
            {"id": "icium-z", "name": "Icium Z"},
            {"id": "fightinium-z", "name": "Fightinium Z"},
            {"id": "poisonium-z", "name": "Poisonium Z"},
            {"id": "groundium-z", "name": "Groundium Z"},
            {"id": "flyinium-z", "name": "Flyinium Z"},
            {"id": "psychium-z", "name": "Psychium Z"},
            {"id": "buginium-z", "name": "Buginium Z"},
            {"id": "rockium-z", "name": "Rockium Z"},
            {"id": "ghostium-z", "name": "Ghostium Z"},
            {"id": "dragonium-z", "name": "Dragonium Z"},
            {"id": "darkinium-z", "name": "Darkinium Z"},
            {"id": "steelium-z", "name": "Steelium Z"},
            {"id": "fairium-z", "name": "Fairium Z"},
            # Signature Z crystals
            {"id": "pikanium-z", "name": "Pikanium Z"},
            {"id": "pikashunium-z", "name": "Pikashunium Z"},
            {"id": "aloraichium-z", "name": "Aloraichium Z"},
            {"id": "eevium-z", "name": "Eevium Z"},
            {"id": "snorlium-z", "name": "Snorlium Z"},
            {"id": "mewnium-z", "name": "Mewnium Z"},
            {"id": "decidium-z", "name": "Decidium Z"},
            {"id": "incinium-z", "name": "Incinium Z"},
            {"id": "primarium-z", "name": "Primarium Z"},
            {"id": "lycanium-z", "name": "Lycanium Z"},
            {"id": "mimikium-z", "name": "Mimikium Z"},
            {"id": "kommonium-z", "name": "Kommonium Z"},
            {"id": "tapunium-z", "name": "Tapunium Z"},
            {"id": "solganium-z", "name": "Solganium Z"},
            {"id": "lunalium-z", "name": "Lunalium Z"},
            {"id": "ultranecrozium-z", "name": "Ultranecrozium Z"},
            {"id": "marshadium-z", "name": "Marshadium Z"},
        ]
        
        # Add missing Z crystals (only standard ones)
        print("\n=== Adding missing standard Z crystals ===")
        added_count = 0
        updated_count = 0
        
        for crystal in api_crystals:
            crystal_id = crystal["id"]
            crystal_name = crystal["name"]
            
            # Skip bag variants
            if "-bag" in crystal_id or "--bag" in crystal_id:
                continue
            
            # Check if it exists
            cur = conn.execute("SELECT id, name FROM items WHERE id = ?", (crystal_id,))
            row = cur.fetchone()
            cur.close()
            
            if not row:
                # Insert new item
                conn.execute("""
                    INSERT INTO items (id, name, emoji, icon_url)
                    VALUES (?, ?, NULL, NULL)
                """, (crystal_id, crystal_name))
                print(f"  Added {crystal_id}: {crystal_name}")
                added_count += 1
            else:
                # Update name if different
                if row["name"] != crystal_name:
                    conn.execute("UPDATE items SET name = ? WHERE id = ?", (crystal_name, crystal_id))
                    print(f"  Updated {crystal_id}: {crystal_name} (was: {row['name']})")
                    updated_count += 1
        
        conn.commit()
        
        print(f"\n=== Summary ===")
        print(f"Added new crystals: {added_count}")
        print(f"Updated existing: {updated_count}")
        
        # Show final state
        cur = conn.execute("""
            SELECT id, name FROM items 
            WHERE (id LIKE '%-z' OR id LIKE '%-z-%')
            AND id NOT LIKE '%-bag' 
            AND id NOT LIKE '%--bag'
            ORDER BY id
        """)
        final_items = cur.fetchall()
        print(f"\nFinal standard Z crystals in database: {len(final_items)}")
        for row in final_items:
            print(f"  {row['id']}: {row['name']}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    main()