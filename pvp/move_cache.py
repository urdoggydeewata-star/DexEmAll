"""
Aggressive move data caching to avoid 300ms+ database queries to Supabase.
Preloads all moves into memory on first access.
"""
from __future__ import annotations
from typing import Dict, Any, Optional
import json

# In-memory cache for all move data
_MOVE_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_LOADED = False

def preload_all_moves():
    """Preload all moves from database into memory cache."""
    global _CACHE_LOADED, _MOVE_CACHE
    
    if _CACHE_LOADED:
        return
    
    print("[Cache] Preloading all moves into memory...")
    from .db_pool import open_conn, close_conn
    
    conn = open_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT name, type, power, accuracy, pp, damage_class, priority, meta,
                   introduced_in, is_contact_move
            FROM moves
        """)
        rows = cur.fetchall()
        cur.close()
        
        for row in rows:
            name_lower = row["name"].lower().replace(" ", "-")
            _MOVE_CACHE[name_lower] = dict(row)
        
        print(f"[Cache] Loaded {len(_MOVE_CACHE)} moves into memory")
        _CACHE_LOADED = True
    finally:
        close_conn(conn)

def get_cached_move(name: str) -> Optional[Dict[str, Any]]:
    """Get move from cache, loading all moves on first access."""
    if not _CACHE_LOADED:
        preload_all_moves()
    
    name_lower = name.lower().replace(" ", "-")
    return _MOVE_CACHE.get(name_lower)

def clear_cache():
    """Clear the cache (useful for testing)."""
    global _CACHE_LOADED, _MOVE_CACHE
    _CACHE_LOADED = False
    _MOVE_CACHE.clear()
