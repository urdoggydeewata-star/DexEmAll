"""
Database query caching layer to reduce database load and improve performance.
Caches frequently accessed data like Pokémon species, moves, and items.
Also caches full-table dumps for learnsets, pokedex_forms, rulesets, etc.
"""
from __future__ import annotations
from typing import Dict, Any, Optional, List, Union
import time
from functools import lru_cache

# Global caches with TTL (Time To Live)
_POKEDEX_CACHE: Dict[str, tuple[Dict[str, Any], float]] = {}  # key -> (data, expiry_time)
_MOVE_CACHE: Dict[str, tuple[Dict[str, Any], float]] = {}
_ITEM_CACHE: Dict[str, tuple[Dict[str, Any], float]] = {}

# Full-table caches: table_name -> (data, expiry). data = list[dict] or dict for config.
_STATIC_TABLES: Dict[str, tuple[Union[List[Dict[str, Any]], Dict[str, str]], float]] = {}

# Per-owner pokemons list cache: owner_id (str) -> (list of pokemon dicts, expiry).
# Invalidated whenever pokemons table is written for that owner.
_POKEMONS_CACHE: Dict[str, tuple[List[Dict[str, Any]], float]] = {}

# Per-owner bag (user_items) cache: owner_id (str) -> (list of item dicts with item_id, qty, name, emoji, icon_url, expiry).
# Invalidated whenever user_items is written for that owner.
_BAG_CACHE: Dict[str, tuple[List[Dict[str, Any]], float]] = {}

# Per-owner adventure state cache: owner_id (str) -> (state dict, expiry). Updated on save.
_ADVENTURE_CACHE: Dict[str, tuple[Dict[str, Any], float]] = {}

# Per-owner party cache: owner_id (str) -> (list of mon_data dicts for engine, expiry). Invalidated when pokemons change.
_PARTY_CACHE: Dict[str, tuple[List[Dict[str, Any]], float]] = {}

# Per-owner TM Machine cache: owner_id (str) -> (list of {item_id, qty} for tm-%/hm-%, expiry). Invalidated when user_items tm/hm change.
_TM_MACHINE_CACHE: Dict[str, tuple[List[Dict[str, Any]], float]] = {}

# Battle-scoped party cache: user_id -> list of party dicts (from get_party_for_engine).
# Set at battle start, cleared at battle end. Never use global/persistent pokemons cache.
_BATTLE_PARTY_CACHE: Dict[int, List[Dict[str, Any]]] = {}

# Cache TTL in seconds (5 minutes for most data, 1 hour for static data)
CACHE_TTL_POKEDEX = 300  # 5 minutes
CACHE_TTL_MOVES = 3600   # 1 hour (moves rarely change)
CACHE_TTL_ITEMS = 3600   # 1 hour (items rarely change)
CACHE_TTL_STATIC = 3600  # 1 hour for learnsets, forms, rules, etc.
CACHE_TTL_POKEMONS = 300  # 5 minutes per owner
CACHE_TTL_BAG = 300  # 5 minutes per owner
CACHE_TTL_ADVENTURE = 300  # 5 minutes per owner
CACHE_TTL_PARTY = 300  # 5 minutes per owner
CACHE_TTL_TM_MACHINE = 300  # 5 minutes per owner

def _get_cache_key(name_or_id: str) -> str:
    """Normalize cache key."""
    return str(name_or_id).lower().strip()

def _is_expired(expiry_time: float) -> bool:
    """Check if cache entry is expired."""
    return time.time() > expiry_time

def get_cached_pokedex(name_or_id: str) -> Optional[Dict[str, Any]]:
    """Get Pokémon data from cache."""
    key = _get_cache_key(name_or_id)
    if key in _POKEDEX_CACHE:
        data, expiry = _POKEDEX_CACHE[key]
        if not _is_expired(expiry):
            return data
        else:
            # Expired, remove it
            del _POKEDEX_CACHE[key]
    return None

def set_cached_pokedex(name_or_id: str, data: Dict[str, Any], ttl: float = CACHE_TTL_POKEDEX) -> None:
    """Cache Pokémon data."""
    key = _get_cache_key(name_or_id)
    expiry = time.time() + ttl
    _POKEDEX_CACHE[key] = (data, expiry)

def get_cached_move(name: str) -> Optional[Dict[str, Any]]:
    """Get move data from cache."""
    key = _get_cache_key(name)
    if key in _MOVE_CACHE:
        data, expiry = _MOVE_CACHE[key]
        if not _is_expired(expiry):
            return data
        else:
            del _MOVE_CACHE[key]
    return None

def set_cached_move(name: str, data: Dict[str, Any], ttl: float = CACHE_TTL_MOVES) -> None:
    """Cache move data."""
    key = _get_cache_key(name)
    expiry = time.time() + ttl
    _MOVE_CACHE[key] = (data, expiry)

def get_cached_item(item_id: str) -> Optional[Dict[str, Any]]:
    """Get item data from cache."""
    key = _get_cache_key(item_id)
    if key in _ITEM_CACHE:
        data, expiry = _ITEM_CACHE[key]
        if not _is_expired(expiry):
            return data
        else:
            del _ITEM_CACHE[key]
    return None

def set_cached_item(item_id: str, data: Dict[str, Any], ttl: float = CACHE_TTL_ITEMS) -> None:
    """Cache item data."""
    key = _get_cache_key(item_id)
    expiry = time.time() + ttl
    _ITEM_CACHE[key] = (data, expiry)

def get_cached_pokemons(owner_id: str) -> Optional[List[Dict[str, Any]]]:
    """Get cached list of pokemons for an owner. None if missing or expired."""
    key = str(owner_id).strip()
    if key in _POKEMONS_CACHE:
        data, expiry = _POKEMONS_CACHE[key]
        if not _is_expired(expiry):
            return data
        del _POKEMONS_CACHE[key]
    return None


def set_cached_pokemons(owner_id: str, data: List[Dict[str, Any]], ttl: float = CACHE_TTL_POKEMONS) -> None:
    """Cache list of pokemons for an owner."""
    key = str(owner_id).strip()
    expiry = time.time() + ttl
    _POKEMONS_CACHE[key] = (data, expiry)


def invalidate_pokemons(owner_id: str) -> None:
    """Remove cached pokemons for an owner (call after DB write so next read refills from DB)."""
    key = str(owner_id).strip()
    _POKEMONS_CACHE.pop(key, None)
    _PARTY_CACHE.pop(key, None)  # party is derived from pokemons


def clear_all_pokemons_cache() -> None:
    """Clear all per-owner pokemons caches (e.g. after full table wipe)."""
    _POKEMONS_CACHE.clear()


def get_cached_bag(owner_id: str) -> Optional[List[Dict[str, Any]]]:
    """Get cached bag (list of item dicts: item_id, qty, name, emoji, icon_url) for an owner. None if missing or expired."""
    key = str(owner_id).strip()
    if key in _BAG_CACHE:
        data, expiry = _BAG_CACHE[key]
        if not _is_expired(expiry):
            return data
        del _BAG_CACHE[key]
    return None


def set_cached_bag(owner_id: str, data: List[Dict[str, Any]], ttl: float = CACHE_TTL_BAG) -> None:
    """Cache bag (list of item dicts) for an owner."""
    key = str(owner_id).strip()
    expiry = time.time() + ttl
    _BAG_CACHE[key] = (data, expiry)


def invalidate_bag(owner_id: str) -> None:
    """Remove cached bag for an owner (call after user_items write so next read refills from DB)."""
    _BAG_CACHE.pop(str(owner_id).strip(), None)


def get_cached_tm_machine(owner_id: str) -> Optional[List[Dict[str, Any]]]:
    """Get cached TM Machine list (item_id, qty) for tm-%/hm-% items. None if missing or expired."""
    key = str(owner_id).strip()
    if key in _TM_MACHINE_CACHE:
        data, expiry = _TM_MACHINE_CACHE[key]
        if not _is_expired(expiry):
            return data
        del _TM_MACHINE_CACHE[key]
    return None


def set_cached_tm_machine(owner_id: str, data: List[Dict[str, Any]], ttl: float = CACHE_TTL_TM_MACHINE) -> None:
    """Cache TM Machine list for an owner."""
    key = str(owner_id).strip()
    _TM_MACHINE_CACHE[key] = (data, time.time() + ttl)


def invalidate_tm_machine(owner_id: str) -> None:
    """Remove cached TM Machine for an owner (call after giving/using a TM/HM)."""
    _TM_MACHINE_CACHE.pop(str(owner_id).strip(), None)


def clear_all_bag_cache() -> None:
    """Clear all per-owner bag caches (e.g. after full table wipe)."""
    _BAG_CACHE.clear()


def get_cached_adventure_state(owner_id: str) -> Optional[Dict[str, Any]]:
    """Get cached adventure state for an owner. None if missing or expired."""
    key = str(owner_id).strip()
    if key in _ADVENTURE_CACHE:
        data, expiry = _ADVENTURE_CACHE[key]
        if not _is_expired(expiry):
            return data
        del _ADVENTURE_CACHE[key]
    return None


def set_cached_adventure_state(owner_id: str, state: Dict[str, Any], ttl: float = CACHE_TTL_ADVENTURE) -> None:
    """Cache adventure state for an owner (updated on save so next read is fast)."""
    key = str(owner_id).strip()
    expiry = time.time() + ttl
    _ADVENTURE_CACHE[key] = (state, expiry)


def get_cached_party(owner_id: str) -> Optional[List[Dict[str, Any]]]:
    """Get cached party (list of mon_data dicts for engine) for an owner. None if missing or expired."""
    key = str(owner_id).strip()
    if key in _PARTY_CACHE:
        data, expiry = _PARTY_CACHE[key]
        if not _is_expired(expiry):
            return data
        del _PARTY_CACHE[key]
    return None


def set_cached_party(owner_id: str, data: List[Dict[str, Any]], ttl: float = CACHE_TTL_PARTY) -> None:
    """Cache party (engine mon_data list) for an owner."""
    key = str(owner_id).strip()
    expiry = time.time() + ttl
    _PARTY_CACHE[key] = (data, expiry)


def invalidate_party(owner_id: str) -> None:
    """Remove cached party for an owner (call when pokemons change so next get_party refetches)."""
    _PARTY_CACHE.pop(str(owner_id).strip(), None)


def set_battle_party_cached(user_id: int, data: List[Dict[str, Any]]) -> None:
    """Store party data for a user for the current battle only. Cleared at battle end."""
    _BATTLE_PARTY_CACHE[int(user_id)] = data


def get_battle_party_cached(user_id: int) -> Optional[List[Dict[str, Any]]]:
    """Return cached party for user if set (battle-scoped). None otherwise."""
    return _BATTLE_PARTY_CACHE.get(int(user_id))


def clear_battle_party_cache() -> None:
    """Clear all battle-scoped party cache. Call when a battle ends."""
    _BATTLE_PARTY_CACHE.clear()


def get_all_cached_items() -> list:
    """Return unique item dicts from cache (dedupe by id). Empty if cache unused."""
    now = time.time()
    seen: set[str] = set()
    out = []
    for (data, expiry) in _ITEM_CACHE.values():
        if now > expiry:
            continue
        iid = (data.get("id") or "").strip()
        if not iid or iid in seen:
            continue
        seen.add(iid)
        out.append(data)
    return out


# -----------------------------------------------------------------------------
# Full-table caches (learnsets, pokedex_forms, rulesets, config, etc.)
# -----------------------------------------------------------------------------

def set_cached_table(name: str, data: Union[List[Dict[str, Any]], Dict[str, str]], ttl: float = CACHE_TTL_STATIC) -> None:
    """Store a full-table dump. data = list[dict] or dict (for config)."""
    expiry = time.time() + ttl
    _STATIC_TABLES[name] = (data, expiry)


def get_cached_table(name: str) -> Optional[Union[List[Dict[str, Any]], Dict[str, str]]]:
    """Return cached table data (list[dict] or dict) or None if missing/expired."""
    if name not in _STATIC_TABLES:
        return None
    data, expiry = _STATIC_TABLES[name]
    if time.time() > expiry:
        del _STATIC_TABLES[name]
        return None
    return data


def get_cached_learnsets() -> Optional[List[Dict[str, Any]]]:
    """Cached learnsets table (list of rows)."""
    out = get_cached_table("learnsets")
    return out if isinstance(out, list) else None


def get_cached_exp_requirements() -> Optional[List[Dict[str, Any]]]:
    """Cached exp_requirements table (list of rows: group_code, level, exp_total)."""
    out = get_cached_table("exp_requirements")
    return out if isinstance(out, list) else None


def get_cached_pokedex_forms() -> Optional[List[Dict[str, Any]]]:
    """Cached pokedex_forms table."""
    out = get_cached_table("pokedex_forms")
    return out if isinstance(out, list) else None


def get_cached_rulesets() -> Optional[List[Dict[str, Any]]]:
    """Cached rulesets table."""
    out = get_cached_table("rulesets")
    return out if isinstance(out, list) else None


def get_cached_config() -> Optional[Dict[str, str]]:
    """Cached config table (key -> value)."""
    out = get_cached_table("config")
    return out if isinstance(out, dict) else None


def get_cached_format_rules() -> Optional[List[Dict[str, Any]]]:
    """Cached format_rules table."""
    out = get_cached_table("format_rules")
    return out if isinstance(out, list) else None


def get_cached_mega_forms() -> Optional[List[Dict[str, Any]]]:
    """Cached mega_forms table."""
    out = get_cached_table("mega_forms")
    return out if isinstance(out, list) else None


def get_cached_mega_evolution() -> Optional[List[Dict[str, Any]]]:
    """Cached mega_evolution table."""
    out = get_cached_table("mega_evolution")
    return out if isinstance(out, list) else None


def get_cached_move_generation_stats() -> Optional[List[Dict[str, Any]]]:
    """Cached move_generation_stats table."""
    out = get_cached_table("move_generation_stats")
    return out if isinstance(out, list) else None


def get_cached_gigantamax() -> Optional[List[Dict[str, Any]]]:
    """Cached gigantamax table."""
    out = get_cached_table("gigantamax")
    return out if isinstance(out, list) else None


def get_cached_item_effects() -> Optional[List[Dict[str, Any]]]:
    """Cached item_effects table."""
    out = get_cached_table("item_effects")
    return out if isinstance(out, list) else None


def get_cached_items_table() -> Optional[List[Dict[str, Any]]]:
    """Cached items table (list of rows)."""
    out = get_cached_table("items")
    return out if isinstance(out, list) else None


def get_cached_pvp_formats() -> Optional[List[Dict[str, Any]]]:
    """Cached pvp_formats table."""
    out = get_cached_table("pvp_formats")
    return out if isinstance(out, list) else None


def get_cached_pvp_format_rules() -> Optional[List[Dict[str, Any]]]:
    """Cached pvp_format_rules table."""
    out = get_cached_table("pvp_format_rules")
    return out if isinstance(out, list) else None


def invalidate_pokedex(name_or_id: str) -> None:
    """Remove one pokedex entry from cache (call after DB write so next read refills from DB)."""
    key = _get_cache_key(name_or_id)
    _POKEDEX_CACHE.pop(key, None)


def invalidate_move(name: str) -> None:
    """Remove one move from cache (call after DB write)."""
    key = _get_cache_key(name)
    _MOVE_CACHE.pop(key, None)


def invalidate_item(item_id: str) -> None:
    """Remove one item from cache (call after DB write)."""
    key = _get_cache_key(item_id)
    _ITEM_CACHE.pop(key, None)


def invalidate_cached_table(table_name: str) -> None:
    """Remove a full-table cache entry (e.g. 'learnsets', 'pokedex_forms'). Call after writing to that table."""
    _STATIC_TABLES.pop(table_name, None)


def clear_cache() -> None:
    """Clear all caches (including battle-scoped party cache)."""
    global _POKEDEX_CACHE, _MOVE_CACHE, _ITEM_CACHE, _STATIC_TABLES, _POKEMONS_CACHE, _BAG_CACHE, _ADVENTURE_CACHE, _PARTY_CACHE, _BATTLE_PARTY_CACHE, _TM_MACHINE_CACHE
    _POKEDEX_CACHE.clear()
    _MOVE_CACHE.clear()
    _ITEM_CACHE.clear()
    _STATIC_TABLES.clear()
    _POKEMONS_CACHE.clear()
    _BAG_CACHE.clear()
    _ADVENTURE_CACHE.clear()
    _PARTY_CACHE.clear()
    _BATTLE_PARTY_CACHE.clear()
    _TM_MACHINE_CACHE.clear()


def get_cache_stats() -> Dict[str, int]:
    """Get cache statistics."""
    now = time.time()
    pokedex_count = sum(1 for _, expiry in _POKEDEX_CACHE.values() if now <= expiry)
    move_count = sum(1 for _, expiry in _MOVE_CACHE.values() if now <= expiry)
    item_count = sum(1 for _, expiry in _ITEM_CACHE.values() if now <= expiry)
    static_count = sum(1 for _, expiry in _STATIC_TABLES.values() if now <= expiry)
    pokemons_count = sum(1 for _, expiry in _POKEMONS_CACHE.values() if now <= expiry)
    bag_count = sum(1 for _, expiry in _BAG_CACHE.values() if now <= expiry)
    adventure_count = sum(1 for _, expiry in _ADVENTURE_CACHE.values() if now <= expiry)
    party_count = sum(1 for _, expiry in _PARTY_CACHE.values() if now <= expiry)
    return {
        "pokedex": pokedex_count,
        "moves": move_count,
        "items": item_count,
        "static_tables": static_count,
        "pokemons": pokemons_count,
        "bag": bag_count,
        "adventure": adventure_count,
        "party": party_count,
        "total": pokedex_count + move_count + item_count + static_count + pokemons_count + bag_count + adventure_count + party_count
    }
