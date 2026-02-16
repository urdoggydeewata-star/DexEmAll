"""
Fix the typo in Spectral Thief move name in the database.
Changes "spectrial-thief" to "spectral-thief" in pokemons.moves JSON.
"""

import sqlite3
import json

DB_PATH = "myuu.db"

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    print("Fixing Spectral Thief typo in pokemons table...")
    print("-" * 60)
    
    # Get all pokemons with moves containing the typo
    cur = conn.execute("SELECT id, owner_id, moves FROM pokemons WHERE moves LIKE '%spectrial%' COLLATE NOCASE")
    rows = cur.fetchall()
    cur.close()
    
    if not rows:
        print("No pokemons found with 'spectrial-thief' typo")
        conn.close()
        return
    
    print(f"Found {len(rows)} pokemons with the typo:")
    
    fixed_count = 0
    for row in rows:
        moves_json = row["moves"]
        try:
            moves = json.loads(moves_json) if moves_json else []
        except:
            print(f"  Pokemon ID {row['id']}: Failed to parse moves JSON")
            continue
        
        # Check and fix typo in moves list
        fixed = False
        new_moves = []
        for move in moves:
            move_str = str(move).lower().replace(" ", "-").strip()
            if "spectrial" in move_str:
                # Replace with correct spelling
                fixed_move = move_str.replace("spectrial", "spectral")
                new_moves.append(fixed_move)
                fixed = True
                print(f"  Pokemon ID {row['id']}: Fixed '{move}' -> '{fixed_move}'")
            else:
                new_moves.append(move)
        
        if fixed:
            # Update the moves JSON
            new_moves_json = json.dumps(new_moves, ensure_ascii=False)
            conn.execute(
                "UPDATE pokemons SET moves = ? WHERE id = ?",
                (new_moves_json, row["id"])
            )
            fixed_count += 1
    
    conn.commit()
    
    print(f"\n=== Summary ===")
    print(f"Fixed {fixed_count} pokemons")
    
    conn.close()

if __name__ == "__main__":
    main()











