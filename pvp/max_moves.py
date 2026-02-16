"""
Dynamax/Gigantamax System for Generation 8+

Dynamax allows Pokemon to transform for 3 turns:
- HP increases based on Dynamax Level (50% at L0, +5% per level up to 100% at L10)
- Moves become Max Moves
- Cannot switch (unless forced by Emergency Exit/Eject Button/etc.)
- Only one Pokemon per team can Dynamax per battle
- Activates at start of turn (before moves)

Gigantamax is a special form of Dynamax for specific Pokemon:
- Same effects as Dynamax
- One move becomes a unique G-Max Move

Cannot Dynamax: Zacian, Zamazenta, Eternatus (and Pokemon transformed into them)
"""

from typing import Dict, Optional, Tuple, Any, List

# Max Move names by type
MAX_MOVE_NAMES = {
    "Normal": "Max Strike",
    "Fire": "Max Flare",
    "Water": "Max Geyser",
    "Electric": "Max Lightning",
    "Grass": "Max Overgrowth",
    "Ice": "Max Hailstorm",
    "Fighting": "Max Knuckle",
    "Poison": "Max Ooze",
    "Ground": "Max Quake",
    "Flying": "Max Airstream",
    "Psychic": "Max Mindstorm",
    "Bug": "Max Flutterby",
    "Rock": "Max Rockfall",
    "Ghost": "Max Phantasm",
    "Dragon": "Max Wyrmwind",
    "Dark": "Max Darkness",
    "Steel": "Max Steelspike",
    "Fairy": "Max Starfall",
}

# Gigantamax-capable Pokemon and their G-Max Moves
# Format: species_normalized: {base_move_normalized: {"name": G-Max Move name, "effect": effect description}}
GIGANTAMAX_MOVES = {
    "charizard": {"fire-blast": {"name": "G-Max Wildfire", "effect": "damage_and_trap"}},
    "butterfree": {"giga-drain": {"name": "G-Max Befuddle", "effect": "status_and_confuse"}},
    "pikachu": {"volttackle": {"name": "G-Max Volt Crash", "effect": "paralyze_all"}},
    "meowth": {"hyper-beam": {"name": "G-Max Gold Rush", "effect": "coins_and_confuse"}},
    "machamp": {"close-combat": {"name": "G-Max Chi Strike", "effect": "crit_rate"}},
    "gengar": {"shadow-ball": {"name": "G-Max Terror", "effect": "prevents_escape"}},
    "kingler": {"crabhammer": {"name": "G-Max Foam Burst", "effect": "lower_speed"}},
    "lapras": {"ice-beam": {"name": "G-Max Resonance", "effect": "aurora_veil"}},
    "eevee": {"last-resort": {"name": "G-Max Cuddle", "effect": "infatuate"}},
    "snorlax": {"body-slam": {"name": "G-Max Replenish", "effect": "restore_berry"}},
    "garbodor": {"sludge-bomb": {"name": "G-Max Malodor", "effect": "poison_all"}},
    "melmetal": {"double-iron-bash": {"name": "G-Max Meltdown", "effect": "disable_last_move"}},
    "rillaboom": {"drum-beating": {"name": "G-Max Drum Solo", "effect": "ignores_abilities"}},
    "cinderace": {"pyro-ball": {"name": "G-Max Fireball", "effect": "double_damage_grass"}},
    "inteleon": {"snipe-shot": {"name": "G-Max Hydrosnipe", "effect": "ignores_abilities"}},
    "corviknight": {"brave-bird": {"name": "G-Max Wind Rage", "effect": "removes_terrain_screens"}},
    "orbeetle": {"psychic": {"name": "G-Max Gravitas", "effect": "sets_gravity"}},
    "drednaw": {"rock-tomb": {"name": "G-Max Stonesurge", "effect": "sets_stealth_rock"}},
    "coalossal": {"tar-shot": {"name": "G-Max Volcalith", "effect": "residual_damage"}},
    "flapple": {"grav-apple": {"name": "G-Max Tartness", "effect": "lower_evasion"}},
    "appletun": {"apple-acid": {"name": "G-Max Sweetness", "effect": "heals_allies"}},
    "sandaconda": {"sand-tomb": {"name": "G-Max Sandblast", "effect": "residual_damage"}},
    "toxtricity": {"overdrive": {"name": "G-Max Stun Shock", "effect": "paralyze_or_poison"}},
    "centiskorch": {"fire-lash": {"name": "G-Max Centiferno", "effect": "residual_damage"}},
    "hatterene": {"dazzling-gleam": {"name": "G-Max Smite", "effect": "confuse_all"}},
    "grimmsnarl": {"spirit-break": {"name": "G-Max Snooze", "effect": "yawn"}},
    "alcremie": {"decorate": {"name": "G-Max Finale", "effect": "heals_allies"}},
    "copperajah": {"iron-head": {"name": "G-Max Steelsurge", "effect": "sets_steel_spikes"}},
    "duraludon": {"flash-cannon": {"name": "G-Max Depletion", "effect": "pp_reduction"}},
    "urshifu-single-strike": {"wicked-blow": {"name": "G-Max One Blow", "effect": "ignore_protect"}},
    "urshifu-rapid-strike": {"surging-strikes": {"name": "G-Max Rapid Flow", "effect": "ignore_protect"}},
    "venusaur": {"vine-whip": {"name": "G-Max Vine Lash", "effect": "residual_damage"}},
    "blastoise": {"water-gun": {"name": "G-Max Cannonade", "effect": "residual_damage"}},
    "urshifu": {"wicked-blow": {"name": "G-Max One Blow", "effect": "ignore_protect"}},  # Catch-all
}

# Max Move power calculation
def get_max_move_power(base_move: Dict[str, Any]) -> int:
    """
    Calculate Max Move power from base move.
    
    Formula (official):
    - If base power >= 10: floor(base power × 1.5), capped at 130
    - If base power < 10: base power + 70, capped at 130
    - Special case: If base power is None or invalid, default to 90
    """
    base_power_raw = base_move.get("power")
    
    # Handle None power from database
    if base_power_raw is None:
        # Default to 90 for moves with missing power data
        return 90
    
    base_power = int(base_power_raw) if base_power_raw is not None else 0
    
    if base_power >= 10:
        # 1.5x formula, rounded down (int() truncates towards 0, which is floor for positive numbers)
        max_power = int(base_power * 1.5)
    else:
        # For moves with power < 10, add 70
        max_power = base_power + 70
    
    # Cap at 130 (official maximum)
    return min(max_power, 130)


def get_actual_move_type_for_max_move(base_move_name: str, user: Any, field_effects: Any = None) -> str:
    """
    Determine the actual type of a move for Max Move conversion.
    Accounts for:
    - Multi-Attack/Techno Blast with Memory/Drive
    - Weather Ball type changes
    - Terrain Pulse type changes
    - -ate abilities (Aerilate, Galvanize, Pixilate, Refrigerate)
    
    Returns the actual type that should be used for Max Move determination.
    """
    from .advanced_moves import get_weather_ball_type, get_terrain_pulse_type, get_multi_attack_type, get_techno_blast_type
    from .abilities import normalize_ability_name, get_ability_effect
    from .moves_loader import get_move
    
    normalized_move = base_move_name.lower().replace(" ", "-")
    move_data = get_move(base_move_name)
    if not move_data:
        return "Normal"
    
    move_type = move_data.get("type", "Normal")
    
    # Check for type-changing moves first
    if normalized_move == "multi-attack":
        new_type = get_multi_attack_type(user.item)
        if new_type != "Normal":
            return new_type
    elif normalized_move == "techno-blast":
        new_type = get_techno_blast_type(user.item)
        if new_type != "Normal":
            return new_type
    elif normalized_move == "weather-ball":
        if field_effects and hasattr(field_effects, 'weather'):
            weather = field_effects.weather
            new_type = get_weather_ball_type(weather)
            if new_type != "Normal":
                return new_type
    elif normalized_move == "terrain-pulse":
        if field_effects and hasattr(field_effects, 'terrain'):
            terrain = field_effects.terrain
            new_type = get_terrain_pulse_type(terrain)
            if new_type != "Normal":
                return new_type
    
    # Check for -ate abilities (only affect Normal-type moves)
    if move_type == "Normal":
        user_ability = normalize_ability_name(user.ability or "")
        user_ability_data = get_ability_effect(user_ability)
        converts_to = user_ability_data.get("converts_normal_to")
        if converts_to:
            return converts_to
    
    return move_type


def get_max_move_name(base_move_name: str, pokemon_species: str, move_type: str, is_gigantamax: bool = False) -> str:
    """
    Get the Max Move or G-Max Move name for a given base move.
    
    Args:
        base_move_name: The original move name
        pokemon_species: The Pokemon species
        move_type: The type of the move
        is_gigantamax: Whether the Pokemon is Gigantamaxed
    
    Returns:
        The Max Move or G-Max Move name
    """
    base_normalized = base_move_name.lower().replace(" ", "-").strip()
    species_normalized = pokemon_species.lower().replace(" ", "-").strip()
    
    # Check for G-Max Moves first (only if Gigantamaxed)
    if is_gigantamax and species_normalized in GIGANTAMAX_MOVES:
        if base_normalized in GIGANTAMAX_MOVES[species_normalized]:
            gmax_data = GIGANTAMAX_MOVES[species_normalized][base_normalized]
            return gmax_data.get("name", base_move_name)
    
    # Regular Max Move based on type
    move_type_lower = move_type.lower() if move_type else "normal"
    max_move_name = MAX_MOVE_NAMES.get(move_type.title(), "Max Strike")
    
    # If Gigantamaxed but no specific G-Max move, prefix with "G-Max" instead of "Max"
    if is_gigantamax:
        # Replace "Max" with "G-Max" for regular Max Moves when Gigantamaxed
        if max_move_name.startswith("Max "):
            return "G-Max " + max_move_name[4:]  # "Max Strike" -> "G-Max Strike"
        elif max_move_name.startswith("Max"):
            return "G-Max" + max_move_name[3:]  # Handle "MaxStrike" (unlikely but safe)
        return "G-Max " + max_move_name  # Fallback
    
    return max_move_name


def can_gigantamax(pokemon_species: str, mon: Any = None) -> bool:
    """
    Check if a Pokemon species can Gigantamax AND if the individual Pokemon has the Gigantamax Factor.
    
    Args:
        pokemon_species: The Pokemon species name
        mon: The Mon object (optional, to check individual Gigantamax factor)
    
    Returns:
        True if the species can Gigantamax and the individual has the factor.
    """
    species_normalized = pokemon_species.lower().replace(" ", "-").strip()
    
    # First, check if the species is generally capable of Gigantamax
    species_capable = species_normalized in GIGANTAMAX_MOVES
    
    # If the species is capable, check if the individual Pokemon has the Gigantamax factor
    if species_capable and mon:
        return getattr(mon, 'can_gigantamax', False)
    
    return species_capable


def get_gmax_move_effect(base_move_name: str, pokemon_species: str) -> Optional[Dict[str, Any]]:
    """
    Get the special effect for a G-Max Move.
    
    Returns:
        Effect dict or None if not a G-Max Move
    """
    base_normalized = base_move_name.lower().replace(" ", "-").strip()
    species_normalized = pokemon_species.lower().replace(" ", "-").strip()
    
    if species_normalized in GIGANTAMAX_MOVES:
        if base_normalized in GIGANTAMAX_MOVES[species_normalized]:
            gmax_data = GIGANTAMAX_MOVES[species_normalized][base_normalized]
            return gmax_data
    return None


# Max Move side effects by type
# Format: move_type: {effect_type: effect_data}
MAX_MOVE_EFFECTS = {
    "Fire": {"weather": "sun", "turns": 5},  # Max Flare
    "Water": {"weather": "rain", "turns": 5},  # Max Geyser
    "Electric": {"terrain": "electric", "turns": 5},  # Max Lightning
    "Grass": {"terrain": "grassy", "turns": 5},  # Max Overgrowth
    "Ice": {"weather": "hail", "turns": 5},  # Max Hailstorm
    "Fighting": {"stat_boost_team": {"atk": 1}},  # Max Knuckle
    "Poison": {"stat_boost_team": {"spa": 1}},  # Max Ooze
    "Ground": {"stat_boost_team": {"spd": 1}},  # Max Quake
    "Flying": {"stat_boost_team": {"spe": 1}},  # Max Airstream
    "Psychic": {"terrain": "psychic", "turns": 5},  # Max Mindstorm
    "Bug": {"stat_lower_opponent": {"spa": 1}},  # Max Flutterby
    "Rock": {"weather": "sandstorm", "turns": 5},  # Max Rockfall
    "Ghost": {"stat_lower_opponent": {"defn": 1}},  # Max Phantasm
    "Dragon": {"stat_lower_opponent": {"atk": 1}},  # Max Wyrmwind
    "Dark": {"stat_lower_opponent": {"spd": 1}},  # Max Darkness
    "Steel": {"stat_boost_team": {"defn": 1}},  # Max Steelspike
    "Fairy": {"terrain": "misty", "turns": 5},  # Max Starfall
    "Normal": {"stat_lower_opponent": {"spe": 1}},  # Max Strike
}


def get_max_move_side_effect(move_type: str) -> Optional[Dict[str, Any]]:
    """
    Get the side effect for a Max Move based on its type.
    
    Returns:
        Effect dict with weather/terrain/stat changes, or None
    """
    return MAX_MOVE_EFFECTS.get(move_type)


def can_dynamax_species(pokemon_species: str) -> bool:
    """
    Check if a Pokemon species can Dynamax (by species name only).
    
    Args:
        pokemon_species: The Pokemon species name
    
    Returns:
        True if the species can Dynamax
    """
    species_lower = pokemon_species.lower()
    # Cannot Dynamax: Zacian, Zamazenta, Eternatus
    if "zacian" in species_lower or "zamazenta" in species_lower or "eternatus" in species_lower:
        return False
    return True


def can_dynamax(pokemon: Any, dynamax_level: int = 10) -> Tuple[bool, Optional[str]]:
    """
    Check if a Pokemon can Dynamax.
    
    Args:
        pokemon: The Pokemon Mon object
        dynamax_level: Dynamax Level (0-10, affects HP boost)
    
    Returns:
        (can_dynamax, reason_if_no)
    """
    # Cannot Dynamax: Zacian, Zamazenta, Eternatus
    species_lower = pokemon.species.lower()
    if "zacian" in species_lower or "zamazenta" in species_lower or "eternatus" in species_lower:
        return False, "This Pokemon cannot Dynamax"
    
    # Check if transformed into Zacian/Zamazenta/Eternatus
    if hasattr(pokemon, '_transformed') and pokemon._transformed:
        if hasattr(pokemon, '_original_species'):
            # Check if transformed into forbidden species
            if pokemon._original_species:
                orig_lower = pokemon._original_species.lower()
                if "zacian" in orig_lower or "zamazenta" in orig_lower or "eternatus" in orig_lower:
                    return False, "Cannot Dynamax when transformed into this Pokemon"
    
    return True, None


def calculate_dynamax_hp_boost(dynamax_level: int) -> float:
    """
    Calculate HP multiplier from Dynamax Level.
    
    Level 0: 1.5x (50% increase)
    Level 1-10: +5% per level up to 2.0x (100% increase at L10)
    """
    return 1.5 + (dynamax_level * 0.05)


def apply_dynamax(pokemon: Any, dynamax_level: int = 10, is_gigantamax: bool = False) -> Tuple[bool, str]:
    """
    Apply Dynamax transformation to a Pokemon.
    
    Args:
        pokemon: The Pokemon Mon object
        dynamax_level: Dynamax Level (0-10)
        is_gigantamax: Whether this is Gigantamax (vs regular Dynamax)
    
    Returns:
        (success, message)
    """
    can_dmax, reason = can_dynamax(pokemon, dynamax_level)
    if not can_dmax:
        return False, reason or "Cannot Dynamax"
    
    # Store original HP values (for percentage-based effects)
    if pokemon._original_max_hp is None:
        pokemon._original_max_hp = pokemon.max_hp
        pokemon._original_hp = pokemon.hp
    
    # Calculate HP multiplier
    hp_multiplier = calculate_dynamax_hp_boost(dynamax_level)
    
    # Calculate new HP values (maintain percentage)
    original_hp_percent = pokemon.hp / pokemon.max_hp if pokemon.max_hp > 0 else 1.0
    new_max_hp = int(pokemon.max_hp * hp_multiplier)
    new_hp = max(1, int(new_max_hp * original_hp_percent))
    
    # Round up if HP is not whole number
    if new_hp < new_max_hp * original_hp_percent:
        new_hp = int(new_max_hp * original_hp_percent) + 1
        new_hp = min(new_hp, new_max_hp)
    
    # Apply Dynamax
    pokemon.dynamaxed = True
    pokemon.dynamax_turns_remaining = 3
    pokemon.is_gigantamax = is_gigantamax
    pokemon.max_hp = new_max_hp
    pokemon.hp = new_hp
    
    # Clear Choice lock (Dynamax bypasses Choice restrictions)
    # This will be handled in panel.py's _clear_choice_lock_on_dynamax
    
    form_text = "Gigantamax" if is_gigantamax else "Dynamax"
    return True, f"{pokemon.species} {form_text.lower()}ed!"


def revert_dynamax(pokemon: Any) -> None:
    """
    Revert a Pokemon from Dynamax/Gigantamax.
    
    Adjusts HP to maintain percentage.
    """
    if not pokemon.dynamaxed or pokemon._original_max_hp is None:
        return
    
    # Calculate current HP percentage
    current_hp_percent = pokemon.hp / pokemon.max_hp if pokemon.max_hp > 0 else 1.0
    
    # Restore original HP values
    new_hp = max(1, int(pokemon._original_max_hp * current_hp_percent))
    # Round up if needed
    if new_hp < pokemon._original_max_hp * current_hp_percent:
        new_hp = int(pokemon._original_max_hp * current_hp_percent) + 1
        new_hp = min(new_hp, pokemon._original_max_hp)
    
    pokemon.max_hp = pokemon._original_max_hp
    pokemon.hp = new_hp
    pokemon.dynamaxed = False
    pokemon.dynamax_turns_remaining = 0
    pokemon.is_gigantamax = False
    pokemon._original_max_hp = None
    pokemon._original_hp = None


def get_non_dynamax_hp(pokemon: Any) -> int:
    """Get the Pokemon's HP as if it were not Dynamaxed (for percentage calculations)."""
    if pokemon._original_max_hp is not None:
        return pokemon._original_max_hp
    return pokemon.max_hp

