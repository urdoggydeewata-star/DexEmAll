"""
Comprehensive data caching to eliminate 300ms Supabase queries.
Preloads moves, species, abilities, and formats into memory on startup.
"""
from __future__ import annotations
from typing import Dict, Any, Optional, List
import json

# Global caches
_MOVE_CACHE: Dict[str, Dict[str, Any]] = {}
_SPECIES_CACHE: Dict[str, Dict[str, Any]] = {}
_FORMAT_CACHE: Dict[str, Any] = {}
_ABILITY_CACHE: Dict[str, Any] = {}
_CACHE_LOADED = False

def preload_all_data():
    """Preload ALL game data into memory (moves, species, formats, etc.)"""
    global _CACHE_LOADED
    
    if _CACHE_LOADED:
        return
    
    print("[CACHE] Preloading all game data into memory...")
    print("[CACHE] This will take 10-15 seconds but makes the bot INSTANT afterwards!")
    
    from .db_pool import open_conn, close_conn
    import time
    
    start = time.time()
    conn = open_conn()
    try:
        # Preload moves
        print("[CACHE] Loading moves...")
        cur = conn.cursor()
        cur.execute("SELECT * FROM moves")
        move_rows = cur.fetchall()
        cur.close()
        
        for row in move_rows:
            name_lower = row["name"].lower().replace(" ", "-")
            _MOVE_CACHE[name_lower] = dict(row)
        print(f"[CACHE] ✓ Loaded {len(_MOVE_CACHE)} moves")
        
        # Preload species
        print("[CACHE] Loading species...")
        cur = conn.cursor()
        cur.execute("SELECT * FROM pokedex")
        species_rows = cur.fetchall()
        cur.close()
        
        for row in species_rows:
            name_lower = row["name"].lower()
            _SPECIES_CACHE[name_lower] = dict(row)
            if row.get("id"):
                _SPECIES_CACHE[str(row["id"])] = dict(row)
        print(f"[CACHE] ✓ Loaded {len(species_rows)} species")
        
        # Preload formats
        print("[CACHE] Loading format rules...")
        cur = conn.cursor()
        cur.execute("SELECT * FROM pvp_format_rules")
        format_rows = cur.fetchall()
        cur.close()
        
        for row in format_rows:
            fmt_key = row.get("format_key") or row.get("key")
            if not fmt_key:
                continue
            if fmt_key not in _FORMAT_CACHE:
                _FORMAT_CACHE[fmt_key] = {}
            gen = row.get("generation", 9)
            _FORMAT_CACHE[fmt_key][gen] = dict(row)
        print(f"[CACHE] ✓ Loaded {len(format_rows)} format rules")
        
        elapsed = time.time() - start
        print(f"[CACHE] ✓✓✓ ALL DATA CACHED in {elapsed:.1f}s - Bot is now INSTANT! ✓✓✓")
        _CACHE_LOADED = True
    finally:
        close_conn(conn)

def get_cached_move(name: str) -> Optional[Dict[str, Any]]:
    """Get move from cache."""
    name_lower = name.lower().replace(" ", "-")
    return _MOVE_CACHE.get(name_lower)

def get_cached_species(name_or_id: str) -> Optional[Dict[str, Any]]:
    """Get species from cache."""
    key = name_or_id.lower() if not name_or_id.isdigit() else name_or_id
    return _SPECIES_CACHE.get(key)

def get_cached_format(fmt_key: str, gen: int) -> Optional[Dict[str, Any]]:
    """Get format rules from cache."""
    if fmt_key in _FORMAT_CACHE and gen in _FORMAT_CACHE[fmt_key]:
        return _FORMAT_CACHE[fmt_key][gen]
    return None

def is_loaded() -> bool:
    """Check if cache is loaded."""
    return _CACHE_LOADED
