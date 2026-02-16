from __future__ import annotations

from typing import Dict, Any, List, Tuple, Optional
from .db_pool import get_connection

try:
    from lib import db_cache
except ImportError:
    db_cache = None


def _table_exists(conn, name: str) -> bool:
    try:
        row = conn.execute(
            "SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = ? LIMIT 1",
            (name,),
        ).fetchone()
        return bool(row)
    except Exception:
        return False

def _species_intro_gen(species: str) -> Optional[int]:
    """
    Lookup a Pokémon's introduced generation from DB if available.
    Expected tables (any of these is fine):
      - species(name TEXT PRIMARY KEY, introduced_gen INTEGER)
      - pokedex(species TEXT, gen INTEGER)
    Returns None if unknown.
    """
    if not species:
        return None
    try:
        with get_connection() as conn:
            if _table_exists(conn, "species"):
                r = conn.execute(
                    "SELECT introduced_gen AS gen FROM species WHERE LOWER(name)=LOWER(?) LIMIT 1",
                    (species,),
                ).fetchone()
                if r and r["gen"]:
                    return int(r["gen"])
            if _table_exists(conn, "pokedex"):
                r = conn.execute(
                    "SELECT gen FROM pokedex WHERE LOWER(species)=LOWER(?) LIMIT 1",
                    (species,),
                ).fetchone()
                if r and r["gen"]:
                    return int(r["gen"])
            return None
    except Exception:
        return None

# ---- Public API ------------------------------------------------------------

def _normalize_move_name(name: str) -> str:
    """
    Normalize move name by converting to lowercase and replacing spaces with hyphens.
    Also handles special cases like Hidden Power types.
    """
    normalized = name.lower().replace(" ", "-").strip()
    if normalized.startswith("hidden-power-"):
        return "hidden-power"
    return normalized

def _validate_move_legality_from_cache(species_id: int, move_name: str, generation: int) -> Optional[Tuple[bool, str]]:
    """Use cached learnsets + moves. Returns (is_legal, msg) or None on cache miss."""
    if not db_cache:
        return None
    norm = _normalize_move_name(move_name)
    moves = db_cache.get_cached_move(norm) or db_cache.get_cached_move(move_name)
    if not moves:
        return None
    intro = moves.get("introduced_in")
    if intro is not None and int(intro) > generation:
        return False, f"Move '{move_name}' not available in Gen {generation}"
    move_id = moves.get("id")
    if move_id is None:
        return None
    ls = db_cache.get_cached_learnsets()
    if not ls:
        return None
    for r in ls:
        if r.get("species_id") != species_id or r.get("move_id") != move_id:
            continue
        g = r.get("generation")
        if g is not None and int(g) == generation:
            return True, ""
    dex = db_cache.get_cached_pokedex(str(species_id))
    if dex and dex.get("evolution"):
        evo = dex.get("evolution")
        if isinstance(evo, str) and "->" in evo:
            parts = [p.strip() for p in evo.split("->")]
            name = (dex.get("name") or "").strip()
            try:
                idx = parts.index(name)
                if idx > 0:
                    pre = parts[idx - 1]
                    pre_row = db_cache.get_cached_pokedex(pre)
                    if pre_row and pre_row.get("id") is not None:
                        pid = int(pre_row["id"])
                        for r in ls:
                            if r.get("species_id") != pid or r.get("move_id") != move_id:
                                continue
                            g = r.get("generation")
                            if g is not None and int(g) == generation:
                                return True, ""
            except (ValueError, IndexError):
                pass
    return False, f"Species cannot learn '{move_name}' in Gen {generation}"

def validate_move_legality(species_id: int, move_name: str, generation: int) -> Tuple[bool, str]:
    """
    Check if a Pokémon can learn a specific move in a given generation.
    Returns (is_legal, error_message)
    """
    normalized_move = _normalize_move_name(move_name)
    cached = _validate_move_legality_from_cache(species_id, move_name, generation)
    if cached is not None:
        return cached
    try:
        with get_connection() as conn:
            # Check if move exists in this generation
            move_row = conn.execute("""
                SELECT id, name FROM moves 
                WHERE LOWER(REPLACE(name, ' ', '-')) = ? AND introduced_in <= ?
            """, (normalized_move, generation)).fetchone()
            
            if not move_row:
                return False, f"Move '{move_name}' not available in Gen {generation}"
            
            move_id = move_row["id"]
            
            # Check if species can learn this move in this generation
            learnset_row = conn.execute("""
                SELECT method FROM learnsets 
                WHERE species_id = ? AND move_id = ? AND generation = ?
            """, (species_id, move_id, generation)).fetchone()
            
            if learnset_row:
                return True, ""
            
            # If not found, check pre-evolutions for egg moves
            # Get the evolution chain for this species
            species_row = conn.execute("""
                SELECT name, evolution FROM pokedex 
                WHERE id = ?
            """, (species_id,)).fetchone()
            
            if species_row and species_row["evolution"]:
                # Parse evolution string (e.g., "yamask -> cofagrigus")
                evo_chain = species_row["evolution"]
                parts = [p.strip() for p in evo_chain.split("->")]
                current_name = species_row["name"]
                
                # Find pre-evolution (the name before current in the chain)
                try:
                    current_index = parts.index(current_name)
                    if current_index > 0:
                        pre_evo_name = parts[current_index - 1]
                        
                        # Get pre-evolution's species_id
                        pre_evo_row = conn.execute("""
                            SELECT id FROM pokedex WHERE name = ?
                        """, (pre_evo_name,)).fetchone()
                        
                        if pre_evo_row:
                            pre_evo_id = pre_evo_row["id"]
                            
                            # Check if pre-evolution can learn this move (especially egg moves)
                            pre_evo_learnset = conn.execute("""
                                SELECT method FROM learnsets 
                                WHERE species_id = ? AND move_id = ? AND generation = ?
                            """, (pre_evo_id, move_id, generation)).fetchone()
                            
                            if pre_evo_learnset:
                                return True, ""  # Pre-evolution can learn it, so evolved form can too
                except (ValueError, IndexError):
                    pass  # Current species not found in evolution chain or is first
            
            return False, f"Species cannot learn '{move_name}' in Gen {generation}"
            
    except Exception as e:
        print(f"[DEBUG] Move legality check DB error: {e}")
        return True, ""  # Skip validation on DB error

def validate_team_moves(team: List[Dict[str, Any]], generation: int) -> Tuple[bool, List[str]]:
    """
    Validate that all Pokémon can learn their moves in the specified generation.
    Returns (is_valid, error_messages)
    """
    problems = []
    
    for mon in team:
        # Convert Row objects to dictionaries if needed
        if hasattr(mon, 'keys') and not isinstance(mon, dict):
            mon = dict(mon)
        species = mon.get("species", "")
        species_id = mon.get("species_id")  # This is the pokedex ID
        
        if not species_id:
            continue  # Skip if no species ID
        
        moves = mon.get("moves", [])
        for move in moves:
            if not move or not isinstance(move, str):
                continue
            
            is_legal, error = validate_move_legality(species_id, move, generation)
            if not is_legal:
                problems.append(f"{species}: {error}")
    
    return len(problems) == 0, problems

def validate_team(team: List[Dict[str, Any]], rules: Dict[str, Any], generation: int = 9) -> Tuple[bool, List[str]]:
    """
    Validate a team (list of mons) against a rules dict (from formats.py).
    Team item schema expected (as produced by get_active_team):
      { species, item, moves[list[str]], is_shiny, is_female, level, hp, ... }
    Returns (ok, problems[])
    """
    problems: List[str] = []
    if not team:
        return False, ["No Pokémon in team."]
    
    # Ensure all team members are dictionaries (convert Row objects)
    team = [
        dict(mon) if not isinstance(mon, dict) and hasattr(mon, 'keys') else mon
        for mon in team
    ]

    # Species Clause (no duplicate base species) — optional, only if true
    clauses = rules.get("clauses") or {}
    if clauses.get("species"):
        seen = {}
        for mon in team:
            # Convert Row objects to dictionaries if needed
            if not isinstance(mon, dict):
                # Check if it's a Row-like object (has keys() method but isn't a dict)
                if hasattr(mon, 'keys'):
                    try:
                        mon = dict(mon)
                    except (TypeError, ValueError):
                        # If conversion fails, try to access as dict anyway
                        pass
            sp = (mon.get("species") or "").strip()
            if not sp:
                continue
            base = sp  # if you store formes separately, consider normalizing here
            seen[base] = seen.get(base, 0) + 1
        dups = [s for s, n in seen.items() if n > 1]
        if dups:
            problems.append(f"Species Clause: duplicates not allowed ({', '.join(dups)}).")

    # === FULL GENERATION RESTRICTION ===
    # Import generation validator
    try:
        from .generation_validator import (
            validate_pokemon_for_generation,
            validate_move_for_generation,
            validate_ability_for_generation,
            validate_type_for_generation
        )
        
        # Validate each Pokemon against generation
        for idx, mon in enumerate(team, 1):
            # Convert Row objects to dictionaries if needed
            if hasattr(mon, 'keys') and not isinstance(mon, dict):
                mon = dict(mon)
            sp = (mon.get("species") or "").strip()
            if not sp:
                continue
            
            # Validate Pokemon
            valid, error = validate_pokemon_for_generation(sp, generation)
            if not valid:
                problems.append(f"Slot {idx} ({sp}): {error}")
            
            # Validate types (check if types exist in this generation)
            types = mon.get("types", [])
            if types:
                for poke_type in types:
                    if poke_type:
                        valid, error = validate_type_for_generation(poke_type, generation)
                        if not valid:
                            problems.append(f"Slot {idx} ({sp}): {error}")
            
            # Validate ability
            ability = (mon.get("ability") or "").strip()
            if ability:
                valid, error = validate_ability_for_generation(ability, generation)
                if not valid:
                    problems.append(f"Slot {idx} ({sp}): {error}")
            
            # Validate moves (generation check)
            moves = mon.get("moves", [])
            for move in moves:
                if move and isinstance(move, str):
                    valid, error = validate_move_for_generation(move, generation)
                    if not valid:
                        problems.append(f"Slot {idx} ({sp}): {error}")
    
    except ImportError:
        # Fallback to old validation if generation_validator not available
        max_gen = int(rules.get("max_mon_gen", 9))
        for mon in team:
            # Convert Row objects to dictionaries if needed
            if not isinstance(mon, dict):
                # Check if it's a Row-like object (has keys() method but isn't a dict)
                if hasattr(mon, 'keys'):
                    try:
                        mon = dict(mon)
                    except (TypeError, ValueError):
                        # If conversion fails, try to access as dict anyway
                        pass
            sp = (mon.get("species") or "").strip()
            g = _species_intro_gen(sp)
            if g is not None and g > max_gen:
                problems.append(f"{sp}: introduced in Gen {g}, not allowed in Gen {max_gen} OU.")

    # Species bans
    banned_species = {s.lower(): True for s in rules.get("species_bans", [])}
    for mon in team:
        # Convert Row objects to dictionaries if needed
        if hasattr(mon, 'keys') and not isinstance(mon, dict):
            mon = dict(mon)
        sp = (mon.get("species") or "").strip()
        if sp and sp.lower() in banned_species:
            problems.append(f"{sp}: banned in this format.")

    # Move bans
    banned_moves = {m.lower(): True for m in rules.get("move_bans", [])}
    if banned_moves:
        for mon in team:
            # Convert Row objects to dictionaries if needed
            if not isinstance(mon, dict):
                # Check if it's a Row-like object (has keys() method but isn't a dict)
                if hasattr(mon, 'keys'):
                    try:
                        mon = dict(mon)
                    except (TypeError, ValueError):
                        # If conversion fails, try to access as dict anyway
                        pass
            for mv in (mon.get("moves") or []):
                if isinstance(mv, str) and mv.lower() in banned_moves:
                    problems.append(f"{mon.get('species','?')}: move '{mv}' is banned.")

    # Item bans
    banned_items = {i.lower(): True for i in rules.get("item_bans", [])}
    if banned_items:
        for mon in team:
            # Convert Row objects to dictionaries if needed
            if not isinstance(mon, dict):
                # Check if it's a Row-like object (has keys() method but isn't a dict)
                if hasattr(mon, 'keys'):
                    try:
                        mon = dict(mon)
                    except (TypeError, ValueError):
                        # If conversion fails, try to access as dict anyway
                        pass
            it = (mon.get("item") or "").strip()
            if it and it.lower() in banned_items:
                problems.append(f"{mon.get('species','?')}: item '{it}' is banned.")

    # Ability bans (only if you store abilities; skip silently otherwise)
    banned_abilities = {a.lower(): True for a in rules.get("ability_bans", [])}
    if banned_abilities:
        for mon in team:
            # Convert Row objects to dictionaries if needed
            if not isinstance(mon, dict):
                # Check if it's a Row-like object (has keys() method but isn't a dict)
                if hasattr(mon, 'keys'):
                    try:
                        mon = dict(mon)
                    except (TypeError, ValueError):
                        # If conversion fails, try to access as dict anyway
                        pass
            ab = (mon.get("ability") or "").strip()
            if ab and ab.lower() in banned_abilities:
                problems.append(f"{mon.get('species','?')}: ability '{ab}' is banned.")

    # Move legality checking
    move_valid, move_errors = validate_team_moves(team, generation)
    if not move_valid:
        problems.extend(move_errors)

    return (len(problems) == 0), problems