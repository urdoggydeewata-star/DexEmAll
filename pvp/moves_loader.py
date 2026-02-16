# pvp/moves_loader.py
from __future__ import annotations

import json
from functools import lru_cache
from typing import Dict, Optional, Any

from .db_pool import get_connection

try:
    from lib import db_cache
except ImportError:
    db_cache = None


def _row_to_dict(row) -> Dict[str, Any]:
    meta = {}
    try:
        if row["meta"]:
            meta = json.loads(row["meta"])
    except Exception:
        meta = {}
    
    damage_class = row["damage_class"] or "physical"
    
    # Prefer priority column over meta JSON
    priority_val = 0
    try:
        if "priority" in row.keys() and row["priority"] is not None:
            priority_val = int(row["priority"])
        else:
            priority_val = meta.get("priority", 0)
    except (ValueError, KeyError):
        priority_val = meta.get("priority", 0)
    
    return {
        "id": row["id"],
        "name": row["name"],
        "introduced_in": row["introduced_in"],
        "type": row["type"],                     # e.g. "Fire"
        "power": row["power"],                   # int or None
        "accuracy": row["accuracy"],             # int or None
        "pp": row["pp"],                         # int or None
        "damage_class": damage_class,            # "physical" | "special" | "status"
        "category": damage_class,                # Alias for engine.py compatibility
        "priority": priority_val,                # Priority from column (or meta as fallback)
        "contact": meta.get("makes_contact", False),  # Contact from meta
        "meta": meta,                            # arbitrary flags, e.g. {"makes_contact": true, "priority": 1}
    }

@lru_cache(maxsize=4096)
def _normalize_move_name(name: str) -> str:
    """
    Normalize move name by converting to lowercase and replacing spaces with hyphens.
    Also handles Hidden Power types.
    """
    # Handle non-string inputs (e.g., integers) by converting to string
    if not isinstance(name, str):
        if name is None:
            return ""
        name = str(name)
    
    normalized = name.lower().replace(" ", "-").strip()
    # Hidden Power variants should be normalized to just "hidden-power"
    if normalized.startswith("hidden-power-"):
        return "hidden-power"
    # Some moves in the database don't have hyphens (e.g., "electroweb" not "electro-web")
    # The SQL query uses LOWER(REPLACE(name, ' ', '-')) which removes spaces but doesn't add hyphens
    # So we need to match: if database has "electroweb" (no hyphen), we should search for "electroweb"
    # But if user inputs "Electro Web", we normalize to "electro-web" which won't match
    # Solution: Also try without hyphen for database lookup (handled by SQL query matching)
    return normalized

def _fetch_move_from_db(name: str, generation: Optional[int] = None) -> Optional[Dict[str, Any]]:
    if not name:
        return None
    try:
        # Normalize the move name (spaces to hyphens, lowercase)
        normalized_name = _normalize_move_name(name)
        
        # Use connection pool - connection is automatically returned when done
        with get_connection() as con:
            # First, get the base move data
            # Try with normalized name (with hyphens)
            row = con.execute(
                """
                SELECT * FROM moves
                WHERE LOWER(REPLACE(name, ' ', '-')) = ?
                LIMIT 1
                """,
                (normalized_name,),
            ).fetchone()
            
            if not row:
                normalized_no_hyphen = normalized_name.replace("-", "")
                row = con.execute(
                    """
                    SELECT * FROM moves
                    WHERE LOWER(REPLACE(name, ' ', '-')) = ?
                    LIMIT 1
                    """,
                    (normalized_no_hyphen,),
                ).fetchone()
            
            if not row:
                return None
            
            # Convert to dict first
            move_dict = _row_to_dict(row)
            
            # If generation is provided, try to get generation-specific stats
            if generation is not None:
                gen_row = con.execute(
                    """
                    SELECT pp, power, accuracy, type, damage_class, makes_contact, priority
                    FROM move_generation_stats
                    WHERE move_id = ? AND generation = ?
                    LIMIT 1
                    """,
                    (row["id"], generation),
                ).fetchone()
                
                if gen_row:
                    # Override with generation-specific values (only if not None)
                    if gen_row["pp"] is not None:
                        move_dict["pp"] = gen_row["pp"]
                    if gen_row["power"] is not None:
                        move_dict["power"] = gen_row["power"]
                    if gen_row["accuracy"] is not None:
                        move_dict["accuracy"] = gen_row["accuracy"]
                    if gen_row["type"] is not None:
                        move_dict["type"] = gen_row["type"]
                    if gen_row["damage_class"] is not None:
                        move_dict["damage_class"] = gen_row["damage_class"]
                        # Also update category alias for engine.py compatibility
                        move_dict["category"] = gen_row["damage_class"]
                    if gen_row["makes_contact"] is not None:
                        # Update makes_contact in meta JSON as well
                        move_dict["contact"] = bool(gen_row["makes_contact"])
                        if "meta" in move_dict and isinstance(move_dict["meta"], dict):
                            move_dict["meta"]["makes_contact"] = bool(gen_row["makes_contact"])
                        else:
                            move_dict["meta"] = {"makes_contact": bool(gen_row["makes_contact"])}
                    if gen_row["priority"] is not None:
                        # Override priority from generation-specific stats
                        move_dict["priority"] = gen_row["priority"]
                        # Also update in meta JSON for compatibility
                        if "meta" in move_dict and isinstance(move_dict["meta"], dict):
                            move_dict["meta"]["priority"] = gen_row["priority"]
                        else:
                            move_dict["meta"] = {"priority": gen_row["priority"]}
            
            return move_dict
    except Exception:
        return None

# ---- public API --------------------------------------------------------------

def _apply_gen_overrides_from_cache(move_dict: Dict[str, Any], generation: int) -> Dict[str, Any]:
    """Apply generation-specific overrides from cached move_generation_stats. Mutates move_dict."""
    if not db_cache or generation is None:
        return move_dict
    stats_list = db_cache.get_cached_move_generation_stats()
    if not stats_list:
        return move_dict
    move_id = move_dict.get("id")
    if move_id is None:
        return move_dict
    gen_row = None
    for r in stats_list:
        if r.get("move_id") == move_id and r.get("generation") == generation:
            gen_row = r
            break
    if not gen_row:
        return move_dict
    if gen_row.get("pp") is not None:
        move_dict["pp"] = gen_row["pp"]
    if gen_row.get("power") is not None:
        move_dict["power"] = gen_row["power"]
    if gen_row.get("accuracy") is not None:
        move_dict["accuracy"] = gen_row["accuracy"]
    if gen_row.get("type") is not None:
        move_dict["type"] = gen_row["type"]
    if gen_row.get("damage_class") is not None:
        move_dict["damage_class"] = gen_row["damage_class"]
        move_dict["category"] = gen_row["damage_class"]
    meta = move_dict.get("meta") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}
    if gen_row.get("makes_contact") is not None:
        b = bool(gen_row["makes_contact"])
        move_dict["contact"] = b
        meta["makes_contact"] = b
    if gen_row.get("priority") is not None:
        move_dict["priority"] = gen_row["priority"]
        meta["priority"] = gen_row["priority"]
    move_dict["meta"] = meta
    return move_dict


def get_move(name: str, generation: Optional[int] = None, battle_state: Any = None) -> Optional[Dict[str, Any]]:
    """
    Fetch a move from the DB by name (case-insensitive).
    If generation is provided, uses generation-specific stats from move_generation_stats table.
    If battle_state is provided and has a move cache, uses the cached data instead of querying DB.
    Otherwise checks db_cache (warm cache), then DB.
    Returns a dict with keys:
      id, name, introduced_in, type, power, accuracy, pp, damage_class, meta(dict)
    or None if not found.
    """
    # 1) BattleState move cache (battle-scoped, gen-specific)
    if battle_state and hasattr(battle_state, "get_cached_move"):
        c = battle_state.get_cached_move(name)
        if c is not None:
            return c

    # 2) Global db_cache (warm cache) + optional gen overrides from cached move_generation_stats
    norm = _normalize_move_name(name) if name else ""
    if db_cache and norm:
        base = db_cache.get_cached_move(norm) or db_cache.get_cached_move(name)
        if base is not None:
            import copy
            out = copy.deepcopy(base) if isinstance(base, dict) else dict(base)
            if "meta" in out and out["meta"] is not None and isinstance(out["meta"], str):
                try:
                    out["meta"] = json.loads(out["meta"])
                except Exception:
                    out["meta"] = {}
            elif not out.get("meta"):
                out["meta"] = {}
            if generation is not None:
                _apply_gen_overrides_from_cache(out, generation)
            return out

    return _fetch_move_from_db(name, generation)

@lru_cache(maxsize=1024)
def get_move_cached(name: str) -> Optional[Dict[str, Any]]:
    """
    Cached version of get_move for when generation is not needed.
    Use this for backwards compatibility.
    """
    return _fetch_move_from_db(name, None)

# Legacy alias for older code that still imports load_move
def load_move(name: str, generation: Optional[int] = None, battle_state: Any = None) -> Optional[Dict[str, Any]]:
    return get_move(name, generation, battle_state)

def get_move_pp(name: str, default: int = 20, generation: Optional[int] = None) -> int:
    m = get_move(name, generation)
    try:
        return int(m.get("pp")) if m and m.get("pp") is not None else default
    except Exception:
        return default

def get_move_power(name: str, default: int = 0, generation: Optional[int] = None) -> int:
    m = get_move(name, generation)
    try:
        return int(m.get("power")) if m and m.get("power") is not None else default
    except Exception:
        return default

def get_move_accuracy(name: str, default: int = 100, generation: Optional[int] = None) -> int:
    m = get_move(name, generation)
    try:
        return int(m.get("accuracy")) if m and m.get("accuracy") is not None else default
    except Exception:
        return default

def get_move_priority(name: str, default: int = 0) -> int:
    m = get_move(name)
    if not m:
        return default
    meta = m.get("meta") or {}
    try:
        return int(meta.get("priority", default))
    except Exception:
        return default

# Comprehensive list of contact moves (fallback if database doesn't have contact flag)
_CONTACT_MOVES = {
    # Normal
    "pound", "karate-chop", "double-slap", "comet-punch", "mega-punch", "scratch",
    "vise-grip", "guillotine", "cut", "slam", "double-kick", "mega-kick",
    "jump-kick", "rolling-kick", "headbutt", "horn-attack", "fury-attack",
    "horn-drill", "tackle", "body-slam", "wrap", "take-down", "thrash",
    "double-edge", "strength", "quick-attack", "rage", "bide", "skull-bash",
    "constrict", "dizzy-punch", "fury-swipes", "hyper-fang", "super-fang",
    "slash", "struggle", "flail", "false-swipe", "return", "frustration",
    "rapid-spin", "facade", "smelling-salts", "endeavor", "crush-claw",
    "last-resort", "giga-impact", "rock-climb", "double-hit", "crush-grip",
    "retaliate", "chip-away", "hold-back", "catastropika", "pulverizing-pancake",
    "veevee-volley", "body-press", "steel-roller", "raging-bull", "hyper-drill",
    # Fighting
    "submission", "low-kick", "counter", "seismic-toss", "high-jump-kick",
    "triple-kick", "dynamic-punch", "vital-throw", "cross-chop", "focus-punch",
    "superpower", "revenge", "brick-break", "arm-thrust", "sky-uppercut",
    "wake-up-slap", "hammer-arm", "close-combat", "force-palm", "drain-punch",
    "power-up-punch", "storm-throw", "low-sweep", "circle-throw", "sacred-sword",
    "flying-press", "thunderous-kick", "axe-kick", "collision-course", "upper-hand",
    # Flying
    "wing-attack", "fly", "peck", "drill-peck", "bounce", "pluck", "brave-bird",
    "aerial-ace", "dragon-ascent", "floaty-fall", "dual-wingbeat",
    # Poison
    "poison-fang", "poison-tail", "poison-jab", "cross-poison", "dire-claw",
    "mortal-spin",
    # Ground
    "dig", "high-horsepower", "stomping-tantrum", "headlong-rush",
    # Rock
    "rock-smash", "head-smash", "accelerock", "stone-axe", "mighty-cleave",
    # Bug
    "leech-life", "fury-cutter", "megahorn", "x-scissor", "bug-bite", "lunge",
    "first-impression", "fell-stinger", "steamroller", "skitter-smack", "pounce",
    # Ghost
    "lick", "shadow-punch", "shadow-claw", "shadow-sneak", "shadow-force",
    "phantom-force", "spectral-thief", "rage-fist",
    # Steel
    "iron-tail", "metal-claw", "steel-wing", "meteor-mash", "iron-head",
    "gyro-ball", "bullet-punch", "gear-grind", "anchor-shot", "smart-strike",
    "dragon-hammer", "sunsteel-strike", "double-iron-bash", "behemoth-blade",
    "behemoth-bash", "steel-roller", "hard-press", "spin-out",
    # Fire
    "fire-punch", "flame-wheel", "blaze-kick", "flare-blitz", "fire-fang",
    "flame-charge", "heat-crash", "v-create", "fire-lash", "sizzly-slide",
    "bitter-blade", "temper-flare",
    # Water
    "waterfall", "crabhammer", "dive", "aqua-tail", "razor-shell", "aqua-jet",
    "liquidation", "fishious-rend", "flip-turn", "surging-strikes", "triple-dive",
    "wave-crash", "jet-punch", "aqua-step",
    # Grass
    "vine-whip", "petal-dance", "needle-arm", "leaf-blade", "power-whip",
    "wood-hammer", "horn-leech", "solar-blade", "trop-kick", "branch-poke",
    "grassy-glide", "trailblaze",
    # Electric
    "thunder-punch", "spark", "volt-tackle", "thunder-fang", "wild-charge",
    "bolt-strike", "nuzzle", "zing-zap", "plasma-fists", "zippy-zap",
    "bolt-beak", "double-shock", "supercell-slam",
    # Psychic
    "zen-headbutt", "heart-stamp", "psychic-fangs", "psyshield-bash", "psyblade",
    # Ice
    "ice-punch", "ice-ball", "ice-fang", "avalanche", "ice-hammer", "triple-axel",
    "ice-spinner",
    # Dragon
    "outrage", "dragon-claw", "dragon-rush", "dragon-tail", "dual-chop",
    "dragon-ascent", "breaking-swipe", "glaive-rush",
    # Dark
    "bite", "feint-attack", "pursuit", "crunch", "knock-off", "payback",
    "assurance", "punishment", "sucker-punch", "night-slash", "foul-play",
    "darkest-lariat", "throat-chop", "brutal-swing", "malicious-moonsault",
    "power-trip", "lash-out", "wicked-blow", "ceaseless-edge", "kowtow-cleave",
    "comeuppance",
    # Fairy
    "draining-kiss", "play-rough", "spirit-break", "let's-snuggle-forever",
    # Special contact moves (rare)
    "trump-card", "wring-out", "grass-knot", "infestation", "electro-drift",
    # Shadow (XD/Colosseum)
    "shadow-blitz", "shadow-break", "shadow-end", "shadow-rush",
}

@lru_cache(maxsize=4096)
def makes_contact(name: str, battle_state: Any = None, generation: Optional[int] = None) -> bool:
    """
    Check if a move makes contact.
    First checks database, then falls back to hardcoded list.
    """
    if not name:
        return False
    
    # Normalize move name
    normalized = _normalize_move_name(name)
    
    # Check battle cache / db_cache first to avoid DB calls
    m = None
    if battle_state is not None:
        m = get_move(name, generation=generation, battle_state=battle_state)
    if m is None and db_cache is not None:
        m = db_cache.get_cached_move(normalized) or db_cache.get_cached_move(name)
    if m is None:
        m = get_move(name, generation=generation, battle_state=battle_state)
    if m:
        meta = m.get("meta") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        if isinstance(meta, dict) and meta.get("makes_contact", False):
            return True
        # Also check the contact field directly (for backwards compatibility)
        if m.get("contact") == 1 or m.get("contact") is True:
            return True
    
    # Fallback to hardcoded list
    return normalized in _CONTACT_MOVES
