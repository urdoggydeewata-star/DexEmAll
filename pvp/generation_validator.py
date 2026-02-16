"""
Generation Validator - Validates content availability for PVP battles

Checks if Pokemon, moves, abilities, items, and forms are available in a given generation.
Used to enforce generation restrictions in PVP battles.
"""

from typing import Tuple, Optional, List, Dict, Any
import json

from .generation_data import (
    get_ability_generation,
    get_type_generation,
    get_form_generation,
    is_mechanic_available,
    GENERATION_INFO
)
from .db_pool import get_connection


def validate_pokemon_for_generation(pokemon_name: str, generation: int, db_path: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """
    Check if a Pokemon is available in the given generation.
    
    Args:
        pokemon_name: Name of the Pokemon
        generation: Generation to validate against (1-9)
        db_path: Path to database (kept for compatibility, but uses pool)
    
    Returns:
        (is_valid, error_message)
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT introduced_in, form_name FROM pokedex WHERE name = ? COLLATE NOCASE",
            (pokemon_name,)
        )
        result = cursor.fetchone()
        
        if not result:
            return False, f"Pokemon '{pokemon_name}' not found in database."
        
        introduced_in, form_name = result
        
        # Check if Pokemon itself is from future generation
        if introduced_in > generation:
            gen_info = GENERATION_INFO.get(introduced_in, {})
            return False, f"{pokemon_name.title()} is from {gen_info.get('name', f'Gen {introduced_in}')}, which didn't exist in Gen {generation}!"
        
        # Check if form is from future generation
        if form_name:
            form_gen = get_form_generation(form_name)
            if form_gen > generation:
                return False, f"{pokemon_name.title()} ({form_name}) is from Gen {form_gen}, which didn't exist in Gen {generation}!"
        
        return True, None


def validate_move_for_generation(move_name: str, generation: int, db_path: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """
    Check if a move is available in the given generation.
    
    Args:
        move_name: Name of the move
        generation: Generation to validate against (1-9)
        db_path: Path to database (kept for compatibility, but uses pool)
    
    Returns:
        (is_valid, error_message)
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT introduced_in, type FROM moves WHERE name = ? COLLATE NOCASE",
            (move_name,)
        )
        result = cursor.fetchone()
        
        if not result:
            return False, f"Move '{move_name}' not found in database."
        
        introduced_in, move_type = result
        
        # Check if move is from future generation
        if introduced_in > generation:
            return False, f"{move_name.title()} is from Gen {introduced_in}, which didn't exist in Gen {generation}!"
        
        # Check if move's type is available in this generation
        type_gen = get_type_generation(move_type)
        if type_gen > generation:
            return False, f"{move_name.title()} is a {move_type}-type move, but {move_type} type didn't exist in Gen {generation}!"
        
        return True, None


def validate_ability_for_generation(ability_name: str, generation: int) -> Tuple[bool, Optional[str]]:
    """
    Check if an ability is available in the given generation.
    
    Args:
        ability_name: Name of the ability
        generation: Generation to validate against (1-9)
    
    Returns:
        (is_valid, error_message)
    """
    # Abilities didn't exist before Gen 3
    if generation < 3:
        if ability_name:
            return False, f"Abilities didn't exist in Gen {generation}! They were introduced in Gen 3."
        return True, None
    
    # Check if ability is from future generation
    ability_gen = get_ability_generation(ability_name)
    if ability_gen > generation:
        return False, f"{ability_name.replace('-', ' ').title()} is from Gen {ability_gen}, which didn't exist in Gen {generation}!"
    
    return True, None


def validate_type_for_generation(type_name: str, generation: int) -> Tuple[bool, Optional[str]]:
    """
    Check if a type is available in the given generation.
    
    Args:
        type_name: Name of the type
        generation: Generation to validate against (1-9)
    
    Returns:
        (is_valid, error_message)
    """
    type_gen = get_type_generation(type_name)
    if type_gen > generation:
        return False, f"{type_name} type didn't exist in Gen {generation}! It was introduced in Gen {type_gen}."
    
    return True, None


def validate_team_for_generation(team: List[Dict[str, Any]], generation: int, db_path: Optional[str] = None) -> Tuple[bool, List[str]]:
    """
    Validate an entire team for a given generation.
    
    Args:
        team: List of Pokemon dicts with 'species', 'moves', 'ability', etc.
        generation: Generation to validate against (1-9)
        db_path: Path to database
    
    Returns:
        (is_valid, list_of_errors)
    """
    errors = []
    
    for idx, pokemon in enumerate(team, 1):
        # Convert Row objects to dictionaries if needed
        if not isinstance(pokemon, dict):
            # Check if it's a Row-like object (has keys() method but isn't a dict)
            if hasattr(pokemon, 'keys'):
                try:
                    pokemon = dict(pokemon)
                except (TypeError, ValueError):
                    # If conversion fails, skip this pokemon
                    errors.append(f"Slot {idx}: Invalid team data format")
                    continue
        
        species = pokemon.get('species', 'Unknown')
        
        # Validate Pokemon
        valid, error = validate_pokemon_for_generation(species, generation, db_path)
        if not valid:
            errors.append(f"Slot {idx} ({species}): {error}")
        
        # Validate types
        if 'types' in pokemon:
            types = pokemon['types']
            if isinstance(types, (list, tuple)):
                for poke_type in types:
                    if poke_type:
                        valid, error = validate_type_for_generation(poke_type, generation)
                        if not valid:
                            errors.append(f"Slot {idx} ({species}): {error}")
        
        # Validate ability
        if 'ability' in pokemon and pokemon['ability']:
            valid, error = validate_ability_for_generation(pokemon['ability'], generation)
            if not valid:
                errors.append(f"Slot {idx} ({species}): {error}")
        
        # Validate moves
        if 'moves' in pokemon:
            moves = pokemon['moves']
            if isinstance(moves, list):
                for move in moves:
                    if move:
                        valid, error = validate_move_for_generation(move, generation, db_path)
                        if not valid:
                            errors.append(f"Slot {idx} ({species}): {error}")
    
    return len(errors) == 0, errors


def get_generation_restrictions(generation: int) -> Dict[str, Any]:
    """
    Get a summary of what's restricted in a given generation.
    
    Args:
        generation: Generation (1-9)
    
    Returns:
        Dict with restriction information
    """
    gen_info = GENERATION_INFO.get(generation, {})
    
    restrictions = {
        "generation": generation,
        "name": gen_info.get("name", f"Generation {generation}"),
        "games": gen_info.get("games", []),
        "region": gen_info.get("region", "Unknown"),
        "max_pokemon": gen_info.get("pokemon_count", 0),
        "available_types": [t for t, g in [
            ("Normal", 1), ("Fire", 1), ("Water", 1), ("Electric", 1), ("Grass", 1),
            ("Ice", 1), ("Fighting", 1), ("Poison", 1), ("Ground", 1), ("Flying", 1),
            ("Psychic", 1), ("Bug", 1), ("Rock", 1), ("Ghost", 1), ("Dragon", 1),
            ("Dark", 2), ("Steel", 2), ("Fairy", 6)
        ] if g <= generation],
        "abilities_available": generation >= 3,
        "held_items_available": generation >= 2,
        "double_battles_available": generation >= 3,
        "physical_special_split": generation >= 4,
        "mega_evolution_available": generation >= 6,
        "z_moves_available": generation >= 7,
        "dynamax_available": generation >= 8,
        "terastallization_available": generation >= 9,
    }
    
    return restrictions


def format_generation_summary(generation: int) -> str:
    """
    Format a human-readable summary of generation restrictions.
    
    Args:
        generation: Generation (1-9)
    
    Returns:
        Formatted string
    """
    restrictions = get_generation_restrictions(generation)
    
    lines = [
        f"**{restrictions['name']}**",
        f"Region: {restrictions['region']}",
        f"Games: {', '.join(restrictions['games'])}",
        f"Pokemon: Up to #{restrictions['max_pokemon']}",
        f"",
        f"**Available Features:**",
    ]
    
    if restrictions['abilities_available']:
        lines.append("✅ Abilities")
    else:
        lines.append("❌ Abilities (introduced Gen 3)")
    
    if restrictions['held_items_available']:
        lines.append("✅ Held Items")
    else:
        lines.append("❌ Held Items (introduced Gen 2)")
    
    if restrictions['physical_special_split']:
        lines.append("✅ Physical/Special Split")
    else:
        lines.append("❌ Physical/Special Split (introduced Gen 4)")
    
    lines.append(f"")
    lines.append(f"**Available Types:**")
    lines.append(", ".join(restrictions['available_types']))
    
    if generation < 2:
        lines.append("")
        lines.append("⚠️ Dark and Steel types not available")
    if generation < 6:
        lines.append("⚠️ Fairy type not available")
    
    return "\n".join(lines)


# ============================================================================
# QUICK VALIDATION FUNCTIONS
# ============================================================================

def can_use_abilities(generation: int) -> bool:
    """Check if abilities are available in this generation."""
    return generation >= 3

def can_use_held_items(generation: int) -> bool:
    """Check if held items are available in this generation."""
    return generation >= 2

def can_use_mega_evolution(generation: int) -> bool:
    """Check if Mega Evolution is available in this generation."""
    return generation >= 6

def can_use_z_moves(generation: int) -> bool:
    """Check if Z-Moves are available in this generation."""
    return generation >= 7

def can_use_dynamax(generation: int) -> bool:
    """Check if Dynamax is available in this generation."""
    return generation >= 8

def can_use_terastallization(generation: int) -> bool:
    """Check if Terastallization is available in this generation."""
    return generation >= 9

def has_physical_special_split(generation: int) -> bool:
    """Check if physical/special split exists in this generation."""
    return generation >= 4

def get_critical_hit_multiplier(generation: int) -> float:
    """Get the critical hit multiplier for this generation."""
    if generation <= 5:
        return 2.0
    else:
        return 1.5

def get_paralysis_speed_multiplier(generation: int) -> float:
    """Get the paralysis speed reduction for this generation."""
    if generation <= 6:
        return 0.25  # 75% reduction
    else:
        return 0.50  # 50% reduction

def get_burn_damage_fraction(generation: int) -> float:
    """Get the burn damage per turn for this generation."""
    if generation <= 6:
        return 1/8
    else:
        return 1/16





