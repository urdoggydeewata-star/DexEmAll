"""
Update move PP values by generation using PokeAPI.
Only includes main series games (excludes Let's Go, BDSP, etc.)
"""
import sqlite3
import json
import requests
import time
from typing import Dict, Optional, Set
from pathlib import Path

# PokeAPI base URL
POKEAPI_BASE = "https://pokeapi.co/api/v2"

# Main series version groups only (excludes spin-offs)
MAIN_SERIES_VERSION_GROUPS = {
    "red-blue": 1,
    "yellow": 1,
    "gold-silver": 2,
    "crystal": 2,
    "ruby-sapphire": 3,
    "emerald": 3,
    "firered-leafgreen": 3,
    "diamond-pearl": 4,
    "platinum": 4,
    "heartgold-soulsilver": 4,
    "black-white": 5,
    "black-2-white-2": 5,
    "x-y": 6,
    "omega-ruby-alpha-sapphire": 6,
    "sun-moon": 7,
    "ultra-sun-ultra-moon": 7,
    "sword-shield": 8,
    "scarlet-violet": 9,
}

def find_db() -> Path:
    """Find the database file"""
    candidates = ['myuu.db', '../myuu.db', '../../myuu.db']
    for path in candidates:
        p = Path(path)
        if p.exists():
            return p
    return Path('myuu.db')

def get_version_group_generation(version_group_name: str) -> Optional[int]:
    """Get generation number for a version group (main series only)"""
    return MAIN_SERIES_VERSION_GROUPS.get(version_group_name)

def fetch_move_data(move_name: str) -> Optional[Dict]:
    """Fetch move data from PokeAPI"""
    url = f"{POKEAPI_BASE}/move/{move_name.lower().replace(' ', '-')}/"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            print(f"  Move '{move_name}' not found in PokeAPI")
            return None
        else:
            print(f"  Error fetching '{move_name}': HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"  Exception fetching '{move_name}': {e}")
        return None

def extract_generation_stats(move_data: Dict) -> Dict[int, Dict[str, Optional[int]]]:
    """
    Extract move stats (PP, power, accuracy) per generation from PokeAPI move data.
    Returns dict mapping generation -> {pp: int, power: int, accuracy: int}
    
    PokeAPI structure:
    - Current stats are for the latest generation (Gen 9)
    - `past_values` contains changes at specific version groups
    - We work backwards from Gen 9, applying changes as we go
    """
    generation_stats = {}
    
    # Current stats (latest generation, usually 9)
    current_pp = move_data.get("pp")
    current_power = move_data.get("power")
    current_accuracy = move_data.get("accuracy")
    
    # Start with current stats for Gen 9
    generation_stats[9] = {
        "pp": current_pp,
        "power": current_power,
        "accuracy": current_accuracy
    }
    
    # Past values contain historical stat changes
    # These are version groups where the values changed FROM the previous values
    past_values = move_data.get("past_values", [])
    
    # Build list of (generation, stats_dict) changes from past_values
    # Sort by generation descending (newest first)
    changes = []
    for past_value in past_values:
        version_group = past_value.get("version_group", {})
        version_group_name = version_group.get("name", "")
        generation = get_version_group_generation(version_group_name)
        
        if generation is None:
            continue  # Skip spin-offs
        
        stats = {
            "pp": past_value.get("pp"),
            "power": past_value.get("power"),
            "accuracy": past_value.get("accuracy")
        }
        
        # Only add if at least one stat is present
        if any(v is not None for v in stats.values()):
            changes.append((generation, stats))
    
    # Sort changes by generation (newest first)
    changes.sort(reverse=True, key=lambda x: x[0])
    
    # Fill in all generations working backwards from Gen 9
    # Start with current stats
    current_stats = {
        "pp": current_pp,
        "power": current_power,
        "accuracy": current_accuracy
    }
    
    # Process each generation from 9 down to 1
    change_idx = 0
    for gen in range(9, 0, -1):
        # Check if we have a change at this generation
        if change_idx < len(changes) and changes[change_idx][0] == gen:
            # Update stats with values from this change (only non-None values)
            change_stats = changes[change_idx][1]
            for key in ["pp", "power", "accuracy"]:
                if change_stats.get(key) is not None:
                    current_stats[key] = change_stats[key]
            change_idx += 1
        
        # Set stats for this generation (copy the dict)
        generation_stats[gen] = {
            "pp": current_stats.get("pp"),
            "power": current_stats.get("power"),
            "accuracy": current_stats.get("accuracy")
        }
    
    return generation_stats

def create_generation_stats_table(conn: sqlite3.Connection):
    """Create table for generation-specific move stats (PP, power, accuracy)"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS move_generation_stats (
            move_id INTEGER NOT NULL,
            generation INTEGER NOT NULL,
            pp INTEGER,
            power INTEGER,
            accuracy INTEGER,
            PRIMARY KEY (move_id, generation),
            FOREIGN KEY (move_id) REFERENCES moves(id) ON DELETE CASCADE
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_move_gen_stats_move ON move_generation_stats(move_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_move_gen_stats_gen ON move_generation_stats(generation)")
    conn.commit()

def update_move_generation_stats():
    """Main function to update move stats (PP, power, accuracy) by generation"""
    db_path = find_db()
    print(f"Opening database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    # Create table
    print("Creating move_generation_stats table...")
    create_generation_stats_table(conn)
    
    # Get all moves from database
    print("Fetching moves from database...")
    moves = conn.execute("SELECT id, name FROM moves ORDER BY id").fetchall()
    print(f"Found {len(moves)} moves to process")
    
    # Track statistics
    updated = 0
    skipped = 0
    errors = 0
    
    for i, move_row in enumerate(moves, 1):
        move_id = move_row["id"]
        move_name = move_row["name"]
        
        print(f"[{i}/{len(moves)}] Processing {move_name}...")
        
        # Fetch from PokeAPI
        move_data = fetch_move_data(move_name)
        if move_data is None:
            skipped += 1
            time.sleep(0.5)  # Rate limiting
            continue
        
        # Extract generation-specific stats (PP, power, accuracy)
        generation_stats = extract_generation_stats(move_data)
        
        if not generation_stats:
            print(f"  No generation stats data found")
            skipped += 1
            time.sleep(0.5)
            continue
        
        # Insert/update stats for each generation
        try:
            for generation, stats in generation_stats.items():
                conn.execute("""
                    INSERT OR REPLACE INTO move_generation_stats 
                    (move_id, generation, pp, power, accuracy)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    move_id,
                    generation,
                    stats.get("pp"),
                    stats.get("power"),
                    stats.get("accuracy")
                ))
            
            conn.commit()
            print(f"  Updated stats for generations: {sorted(generation_stats.keys())}")
            updated += 1
        except Exception as e:
            print(f"  Error updating database: {e}")
            errors += 1
            conn.rollback()
        
        # Rate limiting (be nice to PokeAPI)
        time.sleep(0.5)
    
    conn.close()
    
    print("\n" + "="*60)
    print(f"Update complete!")
    print(f"  Updated: {updated} moves")
    print(f"  Skipped: {skipped} moves")
    print(f"  Errors: {errors} moves")
    print("="*60)

if __name__ == "__main__":
    update_move_generation_stats()