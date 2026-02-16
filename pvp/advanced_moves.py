"""
Advanced Move Mechanics
Handles all special move mechanics that don't fit in standard move effects
Implements 83+ missing mechanics for full competitive accuracy
"""
from typing import Dict, Any, List, Optional, Tuple, Set
import random

from .abilities import normalize_ability_name, get_ability_effect


# ============================================================================
# FRIENDSHIP-BASED MOVES
# ============================================================================

def calculate_return_power(friendship: int, *, generation: Optional[int] = None) -> int:
    """Return power scales with friendship; Gen II permits 0 power."""
    base = int(friendship / 2.5)
    if generation is not None and generation <= 2:
        return max(0, base)
    return max(1, base)


def calculate_frustration_power(friendship: int, *, generation: Optional[int] = None) -> int:
    """Frustration power scales inversely with friendship; Gen II permits 0 power."""
    base = int((255 - friendship) / 2.5)
    if generation is not None and generation <= 2:
        return max(0, base)
    return max(1, base)


# ============================================================================
# LOW HP POWER MOVES (Flail, Reversal)
# ============================================================================

def calculate_low_hp_power(
    current_hp: int,
    max_hp: int,
    move_name: Optional[str] = None,
    field_effects: Any = None
) -> int:
    """
    Flail / Reversal: Power increases as HP decreases
    Power tiers:
    - > 68.75% HP: 20 power
    - > 35.42% HP: 40 power
    - > 20.83% HP: 80 power
    - > 10.42% HP: 100 power
    - > 4.17% HP: 150 power
    - ≤ 4.17% HP: 200 power
    """
    if max_hp == 0:
        return 20

    hp_percent = (current_hp / max_hp) * 100

    generation = None
    try:
        from .generation import get_generation
        generation = get_generation(field_effects=field_effects)
    except Exception:
        generation = None

    if generation == 4:
        tiers = [
            (67.2, 20),
            (34.4, 40),
            (20.3, 80),
            (9.4, 100),
            (3.1, 150),
        ]
    else:
        tiers = [
            (68.75, 20),
            (35.42, 40),
            (20.83, 80),
            (10.42, 100),
            (4.17, 150),
        ]

    for threshold, power in tiers:
        if hp_percent > threshold:
            return power

    return 200


# ============================================================================
# WEATHER-AFFECTED ACCURACY
# ============================================================================

def check_weather_accuracy(move_name: str, weather: Optional[str], user_types: Tuple[str, Optional[str]]) -> Optional[int]:
    """
    Returns modified accuracy if weather affects this move, None otherwise
    
    Thunder/Hurricane: Never miss in rain (100% accuracy override), 50% in sun
    Blizzard: Never miss in snow/hail (100% accuracy override)
    Toxic: Never miss for Poison-type users (100% accuracy override)
    """
    move = move_name.lower()
    
    # Thunder / Hurricane in rain/sun
    if move in ["thunder", "hurricane"]:
        if weather == "rain":
            return 100  # Never miss
        elif weather == "sun":
            return 50  # 50% accuracy
    
    # Blizzard in snow/hail
    if move == "blizzard":
        if weather in ["snow", "hail"]:
            return 100  # Never miss
    
    # Toxic for Poison types
    if move == "toxic":
        if "Poison" in user_types:
            return 100  # Never miss
    
    return None  # No weather effect on accuracy


# ============================================================================
# WEATHER-AFFECTED POWER
# ============================================================================

def calculate_weather_power(move_name: str, base_power: int, weather: Optional[str]) -> int:
    """
    Adjust power based on weather conditions
    
    Solar Beam/Blade: Half power in rain/sand/snow (not sun)
    Weather Ball: Double power and type change in weather
    """
    move = move_name.lower()
    
    # Solar Beam/Blade
    if move in ["solar-beam", "solar-blade"]:
        if weather in ["rain", "sand", "sandstorm", "snow"]:
            return max(1, base_power // 2)
    
    # Weather Ball
    if move == "weather-ball":
        if weather in ["sun", "rain", "sand", "sandstorm", "snow", "hail"]:
            return 100  # Doubles from 50 to 100
    
    return base_power


def get_weather_ball_type(weather: Optional[str]) -> str:
    """
    Get Weather Ball's type based on current weather
    Returns "Normal" if no weather
    """
    if weather == "rain":
        return "Water"
    elif weather == "sun":
        return "Fire"
    elif weather in ["sand", "sandstorm"]:
        return "Rock"
    elif weather in ["snow", "hail"]:
        return "Ice"
    else:
        return "Normal"


# ============================================================================
# TERRAIN-BASED MOVES
# ============================================================================

def calculate_terrain_power(move_name: str, base_power: int, terrain: Optional[str]) -> int:
    """
    Adjust power based on terrain
    
    Rising Voltage: 2x power on Electric Terrain
    Terrain Pulse: 2x power (from 50 to 100) on any terrain
    Earthquake: Halved power in Grassy Terrain (Gen VI+)
    """
    move = move_name.lower()
    
    if move == "rising-voltage" and terrain == "electric":
        return base_power * 2
    
    if move == "terrain-pulse" and terrain in ["electric", "grassy", "psychic", "misty"]:
        return 100  # Doubles from 50
    
    # Earthquake: Halved in Grassy Terrain (Gen VI+)
    if move == "earthquake" and terrain == "grassy":
        return max(1, base_power // 2)
    
    return base_power


def get_terrain_pulse_type(terrain: Optional[str]) -> str:
    """
    Get Terrain Pulse's type based on current terrain
    Returns "Normal" if no terrain
    """
    if terrain == "electric":
        return "Electric"
    elif terrain == "grassy":
        return "Grass"
    elif terrain == "psychic":
        return "Psychic"
    elif terrain == "misty":
        return "Fairy"
    else:
        return "Normal"


def check_steel_roller_terrain(terrain: Optional[str]) -> bool:
    """
    Steel Roller fails if there's no terrain
    Returns True if move can proceed, False if it fails
    """
    return terrain is not None


# ============================================================================
# USER-TYPE-BASED MOVES
# ============================================================================

def get_revelation_dance_type(user_types: Tuple[str, Optional[str]]) -> str:
    """
    Revelation Dance: Type matches user's current primary type.
    If the primary type is unavailable, fall back to secondary.
    If the user is typeless, the move becomes Typeless.
    """
    primary = user_types[0] if len(user_types) > 0 else None
    secondary = user_types[1] if len(user_types) > 1 else None
    if primary:
        return primary
    if secondary:
        return secondary
    return "Typeless"


def get_judgment_type(user_item: Optional[str]) -> str:
    """
    Judgment: Type based on Plate held
    Returns "Normal" if no plate or unknown plate
    """
    plate_types = {
        "draco-plate": "Dragon",
        "dread-plate": "Dark",
        "earth-plate": "Ground",
        "fist-plate": "Fighting",
        "flame-plate": "Fire",
        "icicle-plate": "Ice",
        "insect-plate": "Bug",
        "iron-plate": "Steel",
        "meadow-plate": "Grass",
        "mind-plate": "Psychic",
        "pixie-plate": "Fairy",
        "sky-plate": "Flying",
        "splash-plate": "Water",
        "spooky-plate": "Ghost",
        "stone-plate": "Rock",
        "toxic-plate": "Poison",
        "zap-plate": "Electric",
    }
    return plate_types.get(user_item, "Normal")


def get_multi_attack_type(user_item: Optional[str]) -> str:
    """
    Multi-Attack: Type based on Memory held
    Returns "Normal" if no memory
    """
    memory_types = {
        "bug-memory": "Bug",
        "dark-memory": "Dark",
        "dragon-memory": "Dragon",
        "electric-memory": "Electric",
        "fairy-memory": "Fairy",
        "fighting-memory": "Fighting",
        "fire-memory": "Fire",
        "flying-memory": "Flying",
        "ghost-memory": "Ghost",
        "grass-memory": "Grass",
        "ground-memory": "Ground",
        "ice-memory": "Ice",
        "poison-memory": "Poison",
        "psychic-memory": "Psychic",
        "rock-memory": "Rock",
        "steel-memory": "Steel",
        "water-memory": "Water",
    }
    return memory_types.get(user_item, "Normal")


def get_techno_blast_type(user_item: Optional[str]) -> str:
    """
    Techno Blast: Type based on Drive held
    Returns "Normal" if no drive
    """
    drive_types = {
        "burn-drive": "Fire",
        "chill-drive": "Ice",
        "douse-drive": "Water",
        "shock-drive": "Electric",
    }
    return drive_types.get(user_item, "Normal")


# ============================================================================
# INVULNERABILITY BYPASS & SPECIAL INTERACTIONS
# ============================================================================

def can_hit_invulnerable(move_name: str, target_invulnerable_type: Optional[str]) -> bool:
    """
    Check if a move can hit during semi-invulnerability
    
    Thunder/Hurricane/Gust/Twister/Sky Uppercut: Hit during Fly/Bounce
    Earthquake/Magnitude: Hit during Dig
    Surf/Whirlpool: Hit during Dive
    """
    move = move_name.lower()
    
    if target_invulnerable_type == "flying":
        return move in ["thunder", "hurricane", "gust", "twister", "sky-uppercut"]
    elif target_invulnerable_type == "underground":
        return move in ["earthquake", "magnitude"]
    elif target_invulnerable_type == "underwater":
        return move in ["surf", "whirlpool"]
    
    return False


def get_invulnerability_power_boost(move_name: str, target_invulnerable_type: Optional[str], generation: int = 9) -> float:
    """
    Get power multiplier for moves hitting invulnerable targets
    
    Gust/Twister: 2x power against Fly/Bounce
    """
    move = move_name.lower()
    
    if target_invulnerable_type == "flying" and move in ["gust", "twister"]:
        if move == "twister" and generation <= 1:
            return 1.0
        return 2.0
    if target_invulnerable_type == "underwater" and move in ["whirlpool"]:
        return 2.0
    
    return 1.0


def get_minimize_power_boost(move_name: str, target_minimized: bool) -> float:
    """
    Get power multiplier for moves against minimized targets
    
    Stomp, Steamroller, Body Slam, Dragon Rush, Heat Crash, Heavy Slam, Flying Press: 2x power
    """
    if not target_minimized:
        return 1.0
    
    move = move_name.lower()
    minimize_boosted = [
        "stomp", "steamroller", "body-slam", "dragon-rush",
        "heat-crash", "heavy-slam", "flying-press", "malicious-moonsault"
    ]
    
    if move in minimize_boosted:
        return 2.0
    
    return 1.0


# ============================================================================
# ALWAYS-CRIT MOVES
# ============================================================================

def is_always_crit_move(move_name: str) -> bool:
    """
    Check if move always lands critical hits
    
    Frost Breath, Storm Throw, Surging Strikes, Wicked Blow
    """
    move = move_name.lower()
    return move in ["frost-breath", "storm-throw", "surging-strikes", "wicked-blow"]


# ============================================================================
# PP-BASED POWER (Trump Card)
# ============================================================================

def calculate_trump_card_power(remaining_pp: int) -> int:
    """
    Trump Card: Power based on remaining PP
    - 4+ PP: 40 power
    - 3 PP: 50 power
    - 2 PP: 60 power
    - 1 PP: 80 power
    - 0 PP: 200 power
    """
    if remaining_pp >= 4:
        return 40
    elif remaining_pp == 3:
        return 50
    elif remaining_pp == 2:
        return 60
    elif remaining_pp == 1:
        return 80
    else:
        return 200


# ============================================================================
# TURN-BASED POWER INCREASES
# ============================================================================

def calculate_fury_cutter_power(consecutive_hits: int) -> int:
    """
    Fury Cutter: Power doubles each consecutive hit
    Base 40 -> 80 -> 160 -> 160 (caps at 160)
    """
    power = 40 * (2 ** consecutive_hits)
    return min(160, power)


def calculate_echoed_voice_power(consecutive_turns: int) -> int:
    """
    Echoed Voice: Power increases each consecutive turn
    Base 40 -> 80 -> 120 -> 160 -> 200 (caps at 200)
    """
    power = 40 + (40 * consecutive_turns)
    return min(200, power)


# ============================================================================
# SPITE (PP REDUCTION)
# ============================================================================

def apply_spite(user: Any, target: Any, battle_state: Any = None, field_effects: Any = None) -> str:
    """
    Spite: Reduces the PP of the target's last move.
    
    Generation-specific behavior:
    - Gen II: Reduces PP by 2-5 randomly, fails against Metronome
    - Gen III: Fails if target move has exactly 1 PP, works on Metronome
    - Gen IV: Always reduces by exactly 4
    - Gen V+: Can be reflected with Magic Coat
    
    Returns message
    """
    from .generation import get_generation
    from .abilities import normalize_ability_name
    
    if not battle_state:
        return f"{user.species}'s Spite failed!"
    
    generation = get_generation(field_effects=field_effects) if field_effects else 9
    
    # Gen V+: Check for Magic Coat reflection
    if generation >= 5:
        target_ability = normalize_ability_name(target.ability or "") if hasattr(target, 'ability') else ""
        if target_ability == "magic-bounce":
            # Magic Bounce reflects Spite back
            user_id = getattr(battle_state, 'p1_id', 0) if user in getattr(battle_state, 'p1_team', []) else getattr(battle_state, 'p2_id', 0)
            target_id = getattr(battle_state, 'p2_id', 0) if target in getattr(battle_state, 'p2_team', []) else getattr(battle_state, 'p1_id', 0)
            # Apply Spite to user instead
            user_last_move = getattr(user, 'last_move_used', None) or getattr(user, '_last_move', None)
            if user_last_move:
                # Reduce user's PP instead
                current_pp = battle_state._pp_left(user_id, user_last_move)
                if current_pp > 0:
                    if generation >= 4:
                        reduction = min(4, current_pp)
                    else:
                        reduction = random.randint(2, 5) if generation == 2 else min(random.randint(2, 5), current_pp)
                    battle_state._pp[user_id][user_last_move] = max(0, current_pp - reduction)
                    return f"{target.species}'s Magic Bounce reflected Spite back!\n{user.species}'s {user_last_move} lost {reduction} PP!"
            return f"{target.species}'s Magic Bounce reflected Spite back, but it failed!"
    
    # Get target's last move
    target_last_move = getattr(target, 'last_move_used', None) or getattr(target, '_last_move', None)
    
    if not target_last_move or target_last_move.lower() == "struggle":
        return f"{user.species}'s Spite failed!"
    
    # Gen II: Metronome special case - always fails
    if generation == 2:
        if target_last_move.lower() == "metronome":
            return f"{user.species}'s Spite failed!"
    
    # Get target's user_id for PP access
    target_id = getattr(battle_state, 'p2_id', 0) if target in getattr(battle_state, 'p2_team', []) else getattr(battle_state, 'p1_id', 0)
    current_pp = battle_state._pp_left(target_id, target_last_move)
    
    if current_pp == 0:
        return f"{user.species}'s Spite failed! {target.species}'s {target_last_move} has no PP left!"
    
    # Gen III: Fails if target move has exactly 1 PP
    if generation == 3 and current_pp == 1:
        return f"{user.species}'s Spite failed! {target.species}'s {target_last_move} has only 1 PP left!"
    
    # Determine PP reduction
    if generation >= 4:
        reduction = min(4, current_pp)
    else:  # Gen II-III
        reduction = random.randint(2, 5)
        reduction = min(reduction, current_pp)
    
    # Reduce PP
    battle_state._pp[target_id][target_last_move] = max(0, current_pp - reduction)
    
    # Generation-specific message format
    if generation == 2:
        return f"{target.species}'s {target_last_move} was reduced by {reduction}!"
    elif generation == 3:
        return f"Reduced {target.species}'s {target_last_move} by {reduction}!"
    elif generation >= 4:
        return f"It reduced the PP of {target.species}'s {target_last_move} by {reduction}!"
    else:
        return f"{target.species}'s {target_last_move} lost {reduction} PP!"


# ============================================================================
# SPECIAL REQUIREMENT MOVES
# ============================================================================


# ============================================================================
# NATURAL GIFT
# ============================================================================

def get_natural_gift_data(user_item: Optional[str]) -> Tuple[str, int]:
    """
    Natural Gift: Type and power based on berry held
    Returns (type, power) tuple
    Returns ("Normal", 1) if no berry or unknown berry
    """
    berry_data = {
        # Type-resist berries
        "chilan-berry": ("Normal", 80),
        "occa-berry": ("Fire", 80),
        "passho-berry": ("Water", 80),
        "wacan-berry": ("Electric", 80),
        "rindo-berry": ("Grass", 80),
        "yache-berry": ("Ice", 80),
        "chople-berry": ("Fighting", 80),
        "kebia-berry": ("Poison", 80),
        "shuca-berry": ("Ground", 80),
        "coba-berry": ("Flying", 80),
        "payapa-berry": ("Psychic", 80),
        "tanga-berry": ("Bug", 80),
        "charti-berry": ("Rock", 80),
        "kasib-berry": ("Ghost", 80),
        "haban-berry": ("Dragon", 80),
        "colbur-berry": ("Dark", 80),
        "babiri-berry": ("Steel", 80),
        "roseli-berry": ("Fairy", 80),
        # Stat berries
        "liechi-berry": ("Grass", 100),
        "ganlon-berry": ("Ice", 100),
        "salac-berry": ("Fighting", 100),
        "petaya-berry": ("Poison", 100),
        "apicot-berry": ("Ground", 100),
        "lansat-berry": ("Flying", 100),
        "starf-berry": ("Psychic", 100),
        # Status berries
        "cheri-berry": ("Fire", 80),
        "chesto-berry": ("Water", 80),
        "pecha-berry": ("Electric", 80),
        "rawst-berry": ("Grass", 80),
        "aspear-berry": ("Ice", 80),
        "leppa-berry": ("Fighting", 80),
        "oran-berry": ("Poison", 80),
        "persim-berry": ("Ground", 80),
        "lum-berry": ("Flying", 80),
        # Pinch berries
        "sitrus-berry": ("Psychic", 80),
        "figy-berry": ("Bug", 80),
        "wiki-berry": ("Rock", 80),
        "mago-berry": ("Ghost", 80),
        "aguav-berry": ("Dragon", 80),
        "iapapa-berry": ("Dark", 80),
    }
    
    if user_item and user_item in berry_data:
        return berry_data[user_item]
    
    return ("Normal", 1)  # Fails if no berry


# ============================================================================
# TYPE-CHANGING MOVES
# ============================================================================

def apply_soak(target: Any) -> str:
    """
    Soak: Changes target to pure Water type
    Returns message
    """
    target.types = ("Water", None)
    return f"{target.species} transformed into the Water type!"


def apply_magic_powder(target: Any, user: Any = None) -> str:
    """
    Magic Powder: Changes target to pure Psychic type
    Returns message
    """
    if target is None or getattr(target, "hp", 0) <= 0:
        if user and hasattr(user, "_last_move_failed"):
            user._last_move_failed = True
        return "But it failed!"
    
    if hasattr(target, "substitute") and target.substitute:
        if user and hasattr(user, "_last_move_failed"):
            user._last_move_failed = True
        return f"But it failed! ({target.species} is protected by its substitute!)"
    
    if getattr(target, "terastallized", False):
        if user and hasattr(user, "_last_move_failed"):
            user._last_move_failed = True
        return f"But it failed! ({target.species} is Terastallized!)"
    
    from .abilities import normalize_ability_name
    ability_norm = normalize_ability_name(target.ability or "")
    if ability_norm == "rks-system":
        if user and hasattr(user, "_last_move_failed"):
            user._last_move_failed = True
        return f"But it failed! ({target.species}'s RKS System prevents it!)"
    
    # Already pure Psychic-type
    t1, t2 = target.types
    t1 = t1.strip().title() if t1 else None
    t2 = t2.strip().title() if t2 else None
    if t1 == "Psychic" and (t2 is None or t2 == "Psychic"):
        if user and hasattr(user, "_last_move_failed"):
            user._last_move_failed = True
        return f"But it failed! ({target.species} is already pure Psychic-type!)"
    
    target.types = ("Psychic", None)
    return f"{target.species} transformed into the Psychic type!"


def apply_telekinesis(user: Any, target: Any, field_effects: Any = None) -> Tuple[bool, str]:
    """
    Telekinesis: Lift the target into the air for 3 turns.
    Returns (success, message)
    """
    from .generation import get_generation
    from .items import normalize_item_name

    if target is None or getattr(target, "hp", 0) <= 0:
        return False, "But it failed!"

    generation = get_generation(field_effects=field_effects)
    if generation >= 8:
        return False, "But it failed! (Cannot be selected in this generation)"

    if getattr(field_effects, "gravity", False):
        return False, "But gravity intensified!"

    if hasattr(target, "substitute") and target.substitute:
        return False, f"{target.species}'s substitute blocked the move!"

    if getattr(target, "_telekinesis_turns", 0) > 0:
        return False, f"But {target.species} is already floating!"

    if getattr(target, '_ingrained', False) or getattr(target, 'ingrained', False):
        return False, f"But it failed! ({target.species} anchored itself with its roots!)"

    if target.item:
        item_name = normalize_item_name(target.item)
        if item_name == "iron-ball":
            return False, f"But it failed! ({target.species} is too heavy to be lifted!)"

    target._telekinesis_turns = 3
    target._telekinesis_source = user.species
    if hasattr(target, "_grounded"):
        target._grounded = False
    return True, f"{target.species} was lifted with telekinesis!"


def apply_conversion_2(
    user: Any,
    generation: int,
    last_move_type: Optional[str] = None,
    target: Any = None,
    field_effects: Any = None
) -> Tuple[bool, str]:
    """Generation-aware Conversion 2 handler."""

    resist_map = {
        "Normal": ["Rock", "Steel"],
        "Fire": ["Fire", "Water", "Rock", "Dragon"],
        "Water": ["Water", "Grass", "Dragon"],
        "Electric": ["Electric", "Grass", "Dragon", "Ground"],
        "Grass": ["Fire", "Grass", "Poison", "Flying", "Bug", "Dragon", "Steel"],
        "Ice": ["Fire", "Water", "Ice", "Steel"],
        "Fighting": ["Poison", "Flying", "Psychic", "Bug", "Fairy"],
        "Poison": ["Poison", "Ground", "Rock", "Ghost"],
        "Ground": ["Grass", "Bug", "Flying"],
        "Flying": ["Electric", "Rock", "Steel"],
        "Psychic": ["Psychic", "Steel"],
        "Bug": ["Fire", "Fighting", "Poison", "Flying", "Ghost", "Steel", "Fairy"],
        "Rock": ["Fighting", "Ground", "Steel"],
        "Ghost": ["Dark"],
        "Dragon": ["Steel", "Fairy"],
        "Dark": ["Fighting", "Dark", "Fairy"],
        "Steel": ["Fire", "Water", "Electric", "Steel"],
        "Fairy": ["Fire", "Poison", "Steel"],
        "???": ["Ghost"],
    }

    # Gen II-IV: Uses last move that hit the user
    # Gen V+: Uses last move used by target (including status moves)
    if generation >= 5:
        if target is not None:
            move_type = getattr(target, "_last_move_used_type", None)
            # If no type found, try last_move_used and look it up
            if not move_type:
                last_move_name = getattr(target, "last_move_used", None)
                if last_move_name:
                    from .moves_loader import get_move
                    move_data = get_move(last_move_name)
                    if move_data:
                        move_type = move_data.get("type")
    else:
        # Gen II-IV: Uses last damaging move that hit the user
        move_type = last_move_type
        # Gen IV: Normalize affects type consideration
        if generation >= 4 and move_type:
            # Would need to check if move was affected by Normalize
            # Simplified: assume normal type handling
            pass

    if not move_type:
        return False, "But it failed!"

    move_type = str(move_type).strip().title()

    # Gen IX: Fails if last move was Stellar-type
    if generation >= 9 and move_type == "Stellar":
        return False, "But it failed!"

    # Struggle is considered Normal-type for Conversion 2
    if move_type == "Struggle":
        move_type = "Normal"
    
    # Gen IV: Normalize affects type consideration
    if generation == 4 and move_type == "Normal":
        # Would need to track if move was Normalized - simplified for now
        pass

    resist_types = resist_map.get(move_type)
    if not resist_types:
        return False, "But it failed!"

    available_types = list(resist_types)
    current_types = {t.strip().title() if t else None for t in user.types if t}
    current_types = {t for t in current_types if t}

    # Gen II-III: Can change to any resist/immune type (can match current types)
    # Gen IV+: Cannot change to current types
    if generation >= 4:
        available_types = [t for t in available_types if t not in current_types]
        if not available_types:
            return False, "But it failed!"
    
    # Gen V+: Inverse Battle support (would need field_effects check)
    # For now, using standard resist_map

    new_type = random.choice(available_types)
    user.types = (new_type, None)
    return True, f"{user.species} transformed into the {new_type} type!"
# ============================================================================
# ABILITY-CHANGING MOVES
# ============================================================================

def apply_skill_swap(user: Any, target: Any) -> str:
    """
    Skill Swap: Swaps abilities between user and target
    Returns message
    """
    from .abilities import normalize_ability_name
    
    user_ability = user.ability
    target_ability = target.ability
    
    # Check for unswappable abilities
    unswappable = [
        "multitype", "stance-change", "schooling", "comatose", "shields-down",
        "disguise", "battle-bond", "power-construct", "ice-face", "gulp-missile",
        "neutralizing-gas", "hunger-switch", "wonder-guard", "illusion"
    ]
    
    if user_ability in unswappable or target_ability in unswappable:
        return "But it failed!"
    
    # Clear Slow Start effects when ability is swapped
    user_ability_norm = normalize_ability_name(user_ability or "")
    target_ability_norm = normalize_ability_name(target_ability or "")
    
    if user_ability_norm == "slow-start" and hasattr(user, '_slow_start_turns'):
        delattr(user, '_slow_start_turns')
    if target_ability_norm == "slow-start" and hasattr(target, '_slow_start_turns'):
        delattr(target, '_slow_start_turns')
    
    user.ability = target_ability
    target.ability = user_ability
    
    return f"{user.species} swapped abilities with {target.species}!"


def apply_role_play(user: Any, target: Any) -> str:
    """
    Role Play: User copies target's ability
    Returns message
    """
    # Check for uncopyable abilities
    uncopyable = [
        "multitype", "stance-change", "schooling", "comatose", "shields-down",
        "disguise", "battle-bond", "power-construct", "ice-face", "gulp-missile",
        "neutralizing-gas", "hunger-switch", "wonder-guard", "illusion", "trace",
        "forecast", "flower-gift", "imposter", "power-of-alchemy", "receiver"
    ]
    
    if target.ability in uncopyable:
        return "But it failed!"
    
    user.ability = target.ability
    return f"{user.species} copied {target.species}'s {target.ability}!"


def apply_worry_seed(target: Any, field_effects: Any = None, generation: int = 9) -> str:
    """
    Worry Seed: Changes target's ability to Insomnia with generation-specific mechanics.
    
    Generation-specific mechanics:
    - Gen IV: No display of previous ability, works on Insomnia, fails on Griseous Orb
    - Gen V+: Displays previous ability, fails on Insomnia, works on Griseous Orb
    - Gen V+: Can affect Hunger Switch
    
    Returns message
    """
    from .generation import get_generation
    from .abilities import normalize_ability_name
    from .items import normalize_item_name, get_item_effect
    
    if generation is None or generation == 9:
        generation = get_generation(field_effects=field_effects) if field_effects else 9
    
    # Normalize abilities for comparison
    target_ability_norm = normalize_ability_name(target.ability or "")
    
    # Check for unchangeable abilities (all generations)
    unchangeable = [
        "multitype", "stance-change", "schooling", "comatose", "shields-down",
        "disguise", "rks-system", "battle-bond", "power-construct", "ice-face",
        "gulp-missile", "as-one", "zero-to-hero", "commander"
    ]
    
    # Gen IV: Can work on Insomnia
    # Gen V+: Fails if target already has Insomnia
    if generation >= 5:
        if target_ability_norm == "insomnia":
            return "But it failed! (Target already has Insomnia)"
    
    if target_ability_norm in unchangeable:
        return "But it failed!"
    
    # Check for Griseous Orb (Gen IV only: fails, Gen V+: works)
    if target.item:
        target_item_norm = normalize_item_name(target.item)
        if target_item_norm == "griseous-orb":
            if generation == 4:
                return "But it failed! (Griseous Orb prevents it)"
            # Gen V+: Works normally
    
    # Store original ability for display (Gen V+)
    original_ability = target.ability
    
    # Clear Slow Start effects when ability is replaced
    if target_ability_norm == "slow-start" and hasattr(target, '_slow_start_turns'):
        delattr(target, '_slow_start_turns')
    
    # Change ability to Insomnia
    target.ability = "Insomnia"
    
    # Wake up if sleeping
    if hasattr(target, 'status') and target.status in ["slp", "sleep"]:
        target.status = None
        if hasattr(target, 'status_turns'):
            target.status_turns = 0
    
    # Gen V+: Display previous ability
    if generation >= 5:
        original_name = (original_ability or "Unknown").replace("-", " ").title()
        return f"{target.species}'s ability changed from {original_name} to Insomnia!"
    else:
        # Gen IV: No display
        return f"{target.species}'s ability became Insomnia!"


def apply_simple_beam(target: Any) -> str:
    """
    Simple Beam: Changes target's ability to Simple
    Returns message
    """
    # Check for unchangeable abilities
    unchangeable = [
        "multitype", "stance-change", "schooling", "comatose", "shields-down",
        "disguise", "battle-bond", "power-construct", "truant"
    ]
    
    if target.ability in unchangeable:
        return "But it failed!"
    
    target.ability = "simple"
    return f"{target.species}'s ability became Simple!"


def apply_entrainment(user: Any, target: Any) -> str:
    """
    Entrainment: Changes target's ability to match user's
    Returns message
    """
    # Check for untransferable/unchangeable abilities
    untransferable = [
        "multitype", "stance-change", "schooling", "comatose", "shields-down",
        "disguise", "battle-bond", "power-construct", "ice-face", "gulp-missile",
        "neutralizing-gas", "hunger-switch", "wonder-guard", "illusion", "trace",
        "forecast", "flower-gift", "imposter", "power-of-alchemy", "receiver", "truant"
    ]
    
    if user.ability in untransferable or target.ability in untransferable:
        return "But it failed!"
    
    target.ability = user.ability
    return f"{target.species}'s ability became {user.ability}!"


def apply_gastro_acid(target: Any) -> str:
    """
    Gastro Acid: Suppresses target's ability
    Returns message
    """
    # Check for unsuppressable abilities
    unsuppressable = [
        "multitype", "stance-change", "schooling", "comatose", "shields-down",
        "disguise", "battle-bond", "power-construct", "neutralizing-gas"
    ]
    
    if target.ability in unsuppressable:
        return "But it failed!"
    
    # Set suppression flag
    if not hasattr(target, "_ability_suppressed"):
        target._ability_suppressed = True
    
    return f"{target.species}'s ability was suppressed!"


# ============================================================================
# PLEDGE COMBOS
# ============================================================================

def check_pledge_combo(user_move: str, partner_move: Optional[str]) -> Optional[Tuple[str, int, str]]:
    """
    Check for Pledge move combo
    Returns (field_effect, duration, message) if combo, None otherwise
    
    Fire + Grass = Fire field (damages non-Fire types)
    Water + Fire = Rainbow (doubles secondary effect chance)
    Grass + Water = Swamp (quarters Speed)
    """
    user = user_move.lower()
    partner = partner_move.lower() if partner_move else None
    
    if not partner:
        return None
    
    # Fire + Grass = Fire field
    if (user == "fire-pledge" and partner == "grass-pledge") or \
       (user == "grass-pledge" and partner == "fire-pledge"):
        return ("fire_field", 4, "A sea of fire enveloped the opposing team!")
    
    # Water + Fire = Rainbow
    if (user == "water-pledge" and partner == "fire-pledge") or \
       (user == "fire-pledge" and partner == "water-pledge"):
        return ("rainbow", 4, "A rainbow appeared in the sky!")
    
    # Grass + Water = Swamp
    if (user == "grass-pledge" and partner == "water-pledge") or \
       (user == "water-pledge" and partner == "grass-pledge"):
        return ("swamp", 4, "A swamp enveloped the opposing team!")
    
    return None


# ============================================================================
# PROTECT VARIANTS
# ============================================================================

def check_crafty_shield_block(move_category: str) -> bool:
    """
    Crafty Shield: Blocks status moves
    Returns True if blocked
    """
    return move_category == "Status"


def check_quick_guard_block(move_priority: int) -> bool:
    """
    Quick Guard: Blocks priority moves (priority > 0)
    Returns True if blocked
    """
    return move_priority > 0


def check_wide_guard_block(move_target: str) -> bool:
    """
    Wide Guard: Blocks moves that hit multiple targets
    Returns True if blocked
    """
    # In singles, this is less relevant, but checks for spread moves
    multi_target = ["all-opponents", "all-other-pokemon", "all-pokemon"]
    return move_target in multi_target


# ============================================================================
# FUSION MOVES
# ============================================================================

def check_fusion_boost(user_move: str, partner_move: Optional[str]) -> float:
    """
    Fusion Flare/Bolt: Power increases if partner used the opposite move this turn
    
    Fusion Flare boosted by Fusion Bolt (and vice versa)
    Returns power multiplier (2.0 if boosted, 1.0 otherwise)
    """
    user = user_move.lower()
    partner = partner_move.lower() if partner_move else None
    
    if not partner:
        return 1.0
    
    if (user == "fusion-flare" and partner == "fusion-bolt") or \
       (user == "fusion-bolt" and partner == "fusion-flare"):
        return 2.0
    
    return 1.0


# ============================================================================
# FORME-CHANGE MOVES
# ============================================================================

def apply_relic_song(user: Any) -> str:
    """
    Relic Song: Meloetta changes between Aria and Pirouette forme
    Returns message
    """
    if user.species.lower() != "meloetta":
        return ""
    
    # Toggle form
    if user.form == "pirouette":
        user.form = "aria"
        # Update stats and type (would need form data from database)
        return f"{user.species} changed to Aria Forme!"
    else:
        user.form = "pirouette"
        # Update stats and type
        return f"{user.species} changed to Pirouette Forme!"


def _should_exclude_assist_move(move_name: str, *, generation: int) -> bool:
    name = move_name.lower().replace(" ", "-")
    base_exclusions = {
        "assist", "baneful-bunker", "beak-blast", "belch", "bestow",
        "chatter", "copycat", "counter", "covet", "destiny-bond",
        "detect", "endure", "feint", "focus-punch", "follow-me",
        "helping-hand", "king's-shield", "mat-block", "me-first",
        "metronome", "mimic", "mirror-coat", "mirror-move", "nature-power",
        "protect", "rage-powder", "sketch", "sleep-talk", "snatch", "baton-pass",
        "spiky-shield", "struggle", "switcheroo", "thief", "transform", "trick"
    }
    if name in base_exclusions:
        return True

    if generation >= 6:
        semi_invulnerable = {"astonish", "bounce", "dig", "dive", "fly", "phantom-force", "shadow-force", "sky-drop"}
        if name in semi_invulnerable:
            return True
        switching_moves = {
            "baton-pass", "circle-throw", "dragon-tail", "flip-turn", "parting-shot",
            "roar", "teleport", "u-turn", "volt-switch", "whirlwind"
        }
        if name in switching_moves:
            return True

    if generation >= 8 and name == "assist":
        return True

    return False
    """
    Copycat: Copies the last move used by any Pokémon
    Returns the move to use, or None if it fails
    """
    if not last_move_used:
        return None
    
    # Uncopyable moves
    uncopyable = [
        "assist", "baneful-bunker", "beak-blast", "belch", "bestow", "celebrate",
        "chatter", "copycat", "counter", "covet", "destiny-bond", "detect",
        "endure", "feint", "focus-punch", "follow-me", "helping-hand", "hold-hands",
        "king's-shield", "mat-block", "me-first", "metronome", "mimic", "mirror-coat",
        "mirror-move", "nature-power", "protect", "rage-powder", "sketch", "sleep-talk",
        "snatch", "spiky-shield", "struggle", "switcheroo", "thief", "transform", "trick"
    ]
    
    if last_move_used.lower() in uncopyable:
        return None
    
    return last_move_used


def apply_mirror_move(last_move_used_on_user: Optional[str]) -> Optional[str]:
    """
    Mirror Move: Uses the last move used on the user
    Returns the move to use, or None if it fails
    """
    if not last_move_used_on_user:
        return None
    
    # Uncopyable moves (similar to Copycat)
    uncopyable = [
        "assist", "copycat", "counter", "covet", "destiny-bond", "detect",
        "endure", "feint", "focus-punch", "follow-me", "helping-hand", "metronome",
        "mimic", "mirror-coat", "mirror-move", "protect", "sketch", "sleep-talk",
        "snatch", "struggle", "switcheroo", "thief", "transform", "trick"
    ]
    
    if last_move_used_on_user.lower() in uncopyable:
        return None
    
    return last_move_used_on_user


def apply_mimic(target_last_move: Optional[str], user: Any, target: Any = None, field_effects: Any = None, battle_state: Any = None) -> Tuple[bool, str]:
    """
    Mimic: Temporarily replaces Mimic with the target's last used move
    Returns (success, message)
    
    Generation differences:
    - Gen I: Can copy all moves (except Struggle), uses Mimic's PP. In link battles, copies randomly.
    - Gen II: Copies last move, move gets 5 PP. Cannot copy Sketch, Transform, Struggle, Metronome, or moves user knows.
    - Gen III+: Bypasses accuracy, fails on Shadow moves. Cannot copy Mimic, Sketch.
    - Gen IV: Can copy Transform, fails on Chatter. Copies Me First, not the move called by Me First.
    - Gen V+: Move gets max PP, cannot copy Transform/Z-Moves/Max Moves.
    """
    from .generation import get_generation
    from .moves_loader import get_move
    
    if not target_last_move:
        return False, "But it failed!"
    
    generation = get_generation(field_effects=field_effects, battle_state=battle_state) if field_effects or battle_state else 9
    
    # Normalize move name
    target_move_norm = target_last_move.lower().replace(" ", "-").strip()
    
    # Gen IV+: If target used Me First, copy Me First, not the move it called
    if generation >= 4:
        if hasattr(target, '_me_first_called_move') and target._me_first_called_move:
            # Me First was used - copy Me First itself, not the called move
            target_move_norm = "me-first"
            target_last_move = "Me First"
    
    # Uncopyable moves (consistent across generations)
    uncopyable = ["chatter", "struggle"]
    
    # Generation-specific restrictions
    if generation == 1:
        # Gen I: Can copy all moves except Struggle (no Mimic/Sketch/Transform restrictions)
        # In link battles, it copies randomly (we'll use last move as fallback)
        if target_move_norm == "struggle":
            return False, "But it failed!"
    elif generation == 2:
        # Gen II: Cannot copy Sketch, Transform, Struggle, Metronome, or moves user knows
        uncopyable.extend(["sketch", "transform", "metronome"])
        if target_move_norm in uncopyable:
            return False, "But it failed!"
        # Check if user already knows the move
        user_moves = [m.lower().replace(" ", "-").strip() for m in getattr(user, 'moves', [])]
        if target_move_norm in user_moves:
            return False, "But it failed!"
    elif generation == 3:
        # Gen III: Cannot copy Shadow moves, Mimic, Sketch
        uncopyable.extend(["mimic", "sketch"])
        if target_move_norm in uncopyable:
            return False, "But it failed!"
        # Shadow moves check (would need shadow move detection - skip for now)
    elif generation == 4:
        # Gen IV: Can copy Transform (glitch possible but we'll allow it), fails on Chatter
        uncopyable.extend(["mimic", "sketch"])
        if target_move_norm in uncopyable:
            return False, "But it failed!"
    else:
        # Gen V+: Cannot copy Transform, Z-Moves, Max Moves, Mimic, Sketch
        uncopyable.extend(["mimic", "sketch", "transform"])
        if target_move_norm in uncopyable:
            return False, "But it failed!"
        # Check if it's a Z-Move or Max Move
        if target_move_norm.endswith("-z") or "max-" in target_move_norm or "g-max-" in target_move_norm:
            return False, "But it failed!"
    
    # Find Mimic in user's moveset
    user_moves_list = list(getattr(user, 'moves', []))
    mimic_idx = None
    for i, move in enumerate(user_moves_list):
        if move.lower().replace(" ", "-").strip() == "mimic":
            mimic_idx = i
            break
    
    if mimic_idx is None:
        return False, "But it failed!"
    
    # Store original Mimic move for restoration on switch out
    if not hasattr(user, '_mimic_original_move'):
        user._mimic_original_move = user_moves_list[mimic_idx]
        user._mimic_original_index = mimic_idx
    
    # Replace Mimic with the copied move
    user_moves_list[mimic_idx] = target_last_move
    user.moves = tuple(user_moves_list) if isinstance(user.moves, tuple) else user_moves_list
    
    # Handle PP based on generation
    if battle_state and hasattr(battle_state, '_pp'):
        user_id = getattr(user, '_player_id', None)
        if user_id:
            # Ensure user_id exists in _pp dictionary
            if user_id not in battle_state._pp:
                battle_state._pp[user_id] = {}
            
            # Get Mimic's current PP (Gen I uses Mimic's PP)
            mimic_pp = battle_state._pp.get(user_id, {}).get("Mimic", 0)
            
            if generation == 1:
                # Gen I: Copied move uses Mimic's PP
                battle_state._pp[user_id][target_last_move] = mimic_pp
            elif generation <= 4:
                # Gen II-IV: Copied move gets 5 PP
                battle_state._pp[user_id][target_last_move] = 5
            else:
                # Gen V+: Copied move gets max PP
                move_data = get_move(target_last_move)
                max_pp = move_data.get("pp", 5) if move_data else 5
                battle_state._pp[user_id][target_last_move] = max_pp
    
    return True, f"{user.species} learned {target_last_move}!"


def apply_sketch(target_last_move: Optional[str], user: Any, target: Any = None, field_effects: Any = None, battle_state: Any = None) -> Optional[str]:
    """
    Sketch: PERMANENTLY replaces Sketch with the target's last used move
    Returns message
    
    Generation-specific behavior:
    - Gen II: Can only copy moves that existed in Gen I
    - Gen III-VII: Can copy most moves (except uncopyable list)
    - Gen VIII+: Cannot be selected in battle
    
    Note: This needs database update to persist
    """
    from .generation import get_generation
    
    if not target_last_move:
        return "But it failed!"
    
    generation = get_generation(field_effects=field_effects) if field_effects else 9
    
    # Gen VIII+: Sketch cannot be selected (shouldn't reach here but safety check)
    if generation >= 8:
        return "But it failed! (Sketch cannot be selected in this generation)"
    
    # Uncopyable moves (consistent across generations)
    uncopyable = [
        "chatter", "sketch", "struggle"
    ]
    
    # Gen II: Additional restrictions - can only copy Gen I moves
    if generation == 2:
        # Gen II-only moves that can't be copied
        gen_ii_only = [
            "curse", "spikes", "protect", "detect", "endure", "rollout", "swagger",
            "attract", "sleep-talk", "heal-bell", "return", "frustration", "present",
            "safeguard", "pain-split", "sacred-fire", "magnitude", "dynamic-punch",
            "megahorn", "dragonbreath", "baton-pass", "encore", "pursuit", "rapid-spin",
            "sweet-scent", "iron-tail", "metal-claw", "vital-throw", "morning-sun",
            "synthesis", "moonlight", "hidden-power", "cross-chop", "twister", "rain-dance",
            "sunny-day", "crunch", "mirror-coat", "psych-up", "extremespeed", "ancient-power",
            "shadow-ball", "future-sight", "rock-smash", "whirlpool", "beat-up"
        ]
        if target_last_move.lower() in gen_ii_only:
            uncopyable.append(target_last_move.lower())
    
    if target_last_move.lower() in uncopyable:
        return "But it failed!"
    
    # Replace Sketch in user's moves permanently
    if "sketch" in [m.lower() for m in user.moves]:
        idx = [m.lower() for m in user.moves].index("sketch")
        user.moves[idx] = target_last_move
        # Mark for database update
        if not hasattr(user, "_sketched_moves"):
            user._sketched_moves = {}
        user._sketched_moves[idx] = target_last_move
    
    return f"{user.species} sketched {target_last_move}!"


def apply_me_first(target_chosen_move: Optional[str], user_speed: int, target_speed: int, 
                  target_choice: Optional[Dict] = None, generation: int = 9) -> Optional[Tuple[str, float]]:
    """
    Me First: Uses the target's chosen damaging move with 1.5x power, but only if user is faster
    and target hasn't moved yet.
    
    Generation-specific mechanics:
    - Gen IV-VI: Choice locks into Me First (not the copied move)
    - Gen V: Succeeds if target uses Me First (status move)
    - Gen VII: Special Choice lock handling for consecutively executed moves
    - Gen VIII+: Banned
    
    Returns (move_to_use, power_multiplier) or None if it fails
    """
    if generation >= 8:
        return None  # Banned in Gen VIII+
    
    if not target_chosen_move:
        return None
    
    # Gen V+: Succeeds if target uses Me First (even though it's a status move)
    if generation >= 5 and target_chosen_move.lower().replace(" ", "-") == "me-first":
        return (target_chosen_move, 1.5)
    
    # Check if target's move is damaging
    from .moves_loader import get_move
    target_move_data = get_move(target_chosen_move)
    if not target_move_data:
        return None
    
    # Only works on damaging moves (not status moves)
    if target_move_data.get("category") == "status" or target_move_data.get("power", 0) <= 0:
        return None
    
    # Must be faster (speed check is done in calling code)
    if user_speed <= target_speed:
        return None
    
    # Check if target has already moved this turn
    if target_choice:
        # If target already executed, Me First fails (Gen IV-VI logic)
        if target_choice.get("_executed", False):
            return None
    
    # Return move with 1.5x power multiplier
    return (target_chosen_move, 1.5)


# ============================================================================
# STOCKPILE FAMILY
# ============================================================================

def _ensure_stockpile_state(user: Any) -> None:
    if not hasattr(user, "_stockpile"):
        user._stockpile = 0
    if not hasattr(user, "_stockpile_def_boosts"):
        user._stockpile_def_boosts = 0
    if not hasattr(user, "_stockpile_spd_boosts"):
        user._stockpile_spd_boosts = 0


def _release_stockpile_boosts(user: Any, generation: int) -> None:
    ability = normalize_ability_name(getattr(user, "ability", "") or "")

    def _adjust(stat_key: str, stored_boosts_attr: str) -> None:
        boosts = getattr(user, stored_boosts_attr, 0)
        if boosts <= 0:
            setattr(user, stored_boosts_attr, 0)
            return

        current = user.stages.get(stat_key, 0)
        if generation >= 5:
            if ability == "contrary":
                new_stage = min(6, current + boosts)
            elif ability == "simple":
                new_stage = max(-6, current - (2 * boosts))
            else:
                new_stage = max(-6, current - boosts)
        else:
            new_stage = max(-6, current - boosts)

        user.stages[stat_key] = new_stage
        setattr(user, stored_boosts_attr, 0)

    _adjust("defn", "_stockpile_def_boosts")
    _adjust("spd", "_stockpile_spd_boosts")


def apply_stockpile(user: Any, generation: int = 9) -> str:
    """
    Stockpile: Store energy (max 3 stocks), +1 Def and +1 SpD per stock
    Returns message
    """
    _ensure_stockpile_state(user)

    if user._stockpile >= 3:
        return f"{user.species} can't stockpile any more!"
    
    user._stockpile += 1
    if generation >= 4:
        current_def = user.stages.get("defn", 0)
        current_spd = user.stages.get("spd", 0)

        def_delta = 0
        spd_delta = 0

        if current_def < 6:
            def_delta = min(1, 6 - current_def)
            user.stages["defn"] = current_def + def_delta

        if current_spd < 6:
            spd_delta = min(1, 6 - current_spd)
            user.stages["spd"] = current_spd + spd_delta

        user._stockpile_def_boosts += def_delta
        user._stockpile_spd_boosts += spd_delta
    
    return f"{user.species} stockpiled {user._stockpile}!"


def apply_spit_up(user: Any, generation: int = 9) -> Tuple[int, str]:
    """
    Spit Up: Release stored energy for damage
    
    Gen III: Power 100, multiplied by stockpile count
    Gen IV+: Power = 100 * stockpile count
    
    Gen III: Cannot crit, no random factor
    Gen IV+: Can crit, still no random factor
    Gen V+: Can crit, has random factor, shows stat changes
    
    Returns (power, message)
    """
    _ensure_stockpile_state(user)

    if user._stockpile == 0:
        return (0, f"{user.species} failed to spit up!")
    
    stocks = user._stockpile
    user._stockpile = 0
    
    if generation >= 4:
        _release_stockpile_boosts(user, generation)
    
    # Power calculation: Gen III multiplies damage, Gen IV+ multiplies power
    # But both result in same final calculation, so just use power
    power = stocks * 100
    
    return (power, f"{user.species} released its stockpiled energy!")


def apply_swallow(user: Any, generation: int = 9) -> Tuple[int, str]:
    """
    Swallow: Release stored energy to heal
    1 stock: 25% heal, 2 stocks: 50% heal, 3 stocks: 100% heal
    Returns (heal_amount, message)
    """
    _ensure_stockpile_state(user)

    if user._stockpile == 0:
        return (0, f"{user.species} failed to swallow!")
    
    heal_percent = {1: 0.25, 2: 0.50, 3: 1.0}
    heal_amount = int(user.max_hp * heal_percent.get(user._stockpile, 0.25))
    
    stocks = user._stockpile
    user._stockpile = 0
    if generation >= 4:
        _release_stockpile_boosts(user, generation)
    
    user.hp = min(user.max_hp, user.hp + heal_amount)
    
    return (heal_amount, f"{user.species} swallowed its stockpiled energy and restored HP!")


# ============================================================================
# GROUNDING MOVES
# ============================================================================

def apply_smack_down(target: Any) -> str:
    """
    Smack Down: Grounds the target, removing Flying type/Levitate immunity
    Gen V+: Also removes Magnet Rise
    Returns message
    """
    if not hasattr(target, "_grounded"):
        target._grounded = True
    target._grounded = True
    if hasattr(target, "_telekinesis_turns") and target._telekinesis_turns > 0:
        target._telekinesis_turns = 0
    # Gen V+: Remove Magnet Rise (removed_by_smack_down_thousand_arrows)
    if hasattr(target, "_magnet_rise_turns") and getattr(target, "_magnet_rise_turns", 0) > 0:
        target._magnet_rise_turns = 0
    return f"{target.species} fell straight down!"


def apply_thousand_arrows(target: Any) -> str:
    """
    Thousand Arrows: Hits Flying types and grounds them
    Gen V+: Also removes Magnet Rise
    Returns message
    """
    if not hasattr(target, "_grounded"):
        target._grounded = True
    target._grounded = True
    if hasattr(target, "_telekinesis_turns") and target._telekinesis_turns > 0:
        target._telekinesis_turns = 0
    # Gen V+: Remove Magnet Rise (removed_by_smack_down_thousand_arrows)
    if hasattr(target, "_magnet_rise_turns") and getattr(target, "_magnet_rise_turns", 0) > 0:
        target._magnet_rise_turns = 0
    return f"{target.species} fell straight down!"


def is_grounded(mon: Any, field_gravity: bool = False) -> bool:
    """
    Check if a Pokémon is grounded (affected by Ground moves)
    Considers Flying type, Levitate ability, Magnet Rise, Telekinesis, Gravity, Smack Down, etc.
    """
    # Gravity grounds everything
    if field_gravity:
        return True
    
    # Smack Down/Thousand Arrows
    if hasattr(mon, "_grounded") and mon._grounded:
        return True
    
    # Iron Ball grounds
    if mon.item == "iron-ball":
        return True
    
    # Ingrain grounds
    if hasattr(mon, "_ingrained") and mon._ingrained:
        return True
    
    # Flying type or Levitate makes ungrounded
    if "Flying" in mon.types or mon.ability == "levitate":
        return False
    
    # Magnet Rise makes ungrounded
    if hasattr(mon, "_magnet_rise_turns") and mon._magnet_rise_turns > 0:
        return False
    
    # Telekinesis makes ungrounded
    if hasattr(mon, "_telekinesis_turns") and mon._telekinesis_turns > 0:
        return False
    
    # Air Balloon makes ungrounded (until popped)
    if mon.item == "air-balloon" and not hasattr(mon, "_balloon_popped"):
        return False
    
    return True


# ============================================================================
# TURN-BASED POWER MOVES
# ============================================================================

def handle_fury_cutter(user, move_name: str, hit: bool) -> int:
    """
    Fury Cutter: Power doubles each consecutive hit (20 -> 40 -> 80 -> 160 max)
    Resets on miss or using a different move
    """
    move_lower = move_name.lower().replace(" ", "-")
    
    if move_lower == "fury-cutter":
        if hit:
            # Increment consecutive hits
            user.consecutive_move_hits = min(user.consecutive_move_hits + 1, 4)  # Cap at 4 (160 power)
            power = 20 * (2 ** (user.consecutive_move_hits - 1))
            return power
        else:
            # Reset on miss
            user.consecutive_move_hits = 0
            return 20
    else:
        # Different move - reset counter
        user.consecutive_move_hits = 0
        return 0


def handle_echoed_voice(user, move_name: str) -> int:
    """
    Echoed Voice: Power increases each consecutive turn (40 -> 80 -> 120 -> 160 -> 200 max)
    Resets if user doesn't use it this turn
    """
    move_lower = move_name.lower().replace(" ", "-")
    
    if move_lower == "echoed-voice":
        # Increment consecutive uses
        user.echoed_voice_turns = min(user.echoed_voice_turns + 1, 5)  # Cap at 5 (200 power)
        power = 40 * user.echoed_voice_turns
        return power
    else:
        # Different move - reset counter
        user.echoed_voice_turns = 0
        return 0


def reset_consecutive_counters_on_switch(mon: Any) -> None:
    """
    Reset consecutive move counters when a Pokémon switches in.
    This includes counters for moves like Outrage, Thrash, Petal Dance, etc.
    """
    if not mon:
        return
    
    # Reset rampage move counters
    if hasattr(mon, '_rampage_turns'):
        mon._rampage_turns = 0
    if hasattr(mon, '_rampage_move'):
        mon._rampage_move = None
    
    # Reset other consecutive counters
    if hasattr(mon, '_consecutive_moves'):
        mon._consecutive_moves = 0
    if hasattr(mon, '_outrage_turns'):
        mon._outrage_turns = 0
    
    # Reset turn-based power move counters
    if hasattr(mon, 'consecutive_move_hits'):
        mon.consecutive_move_hits = 0
    if hasattr(mon, 'echoed_voice_turns'):
        mon.echoed_voice_turns = 0

    try:
        from .engine import reset_rollout
        reset_rollout(mon)
    except Exception:
        pass


# ============================================================================
# SPECIAL REQUIREMENT MOVES
# ============================================================================

def can_use_last_resort(user: Any) -> Tuple[bool, str]:
    """
    Last Resort: Can only be used if all other moves have been used at least once
    """
    # Get all moves except Last Resort
    other_moves = [m for m in user.moves if m.lower().replace(" ", "-") != "last-resort"]
    
    if not other_moves:
        return False, "Last Resort failed! (No other moves)"
    
    # Check if all other moves have been used
    moves_used = getattr(user, "_moves_used_this_battle", [])
    
    for move in other_moves:
        move_norm = move.lower().replace(" ", "-")
        if move_norm not in moves_used:
            return False, f"Last Resort failed! ({move} hasn't been used yet)"
    
    return True, ""


def can_use_belch(user: Any) -> Tuple[bool, str]:
    """
    Belch: Can only be used if the user has consumed a Berry this battle
    """
    if not getattr(user, "_consumed_berry", False):
        return False, "Belch failed! (No Berry consumed)"
    return True, ""


def calculate_natural_gift_power_type(berry: str) -> Tuple[int, str]:
    """
    Natural Gift: Power and type depend on held Berry
    Returns (power, type)
    """
    # Berry type and power mapping
    BERRY_DATA = {
        # Pinch Berries (activate at 25% HP)
        "cheri-berry": (80, "Fire"),
        "chesto-berry": (80, "Water"),
        "pecha-berry": (80, "Electric"),
        "rawst-berry": (80, "Grass"),
        "aspear-berry": (80, "Ice"),
        "leppa-berry": (80, "Fighting"),
        "oran-berry": (80, "Poison"),
        "persim-berry": (80, "Ground"),
        "lum-berry": (80, "Flying"),
        "sitrus-berry": (80, "Psychic"),
        "figy-berry": (80, "Bug"),
        "wiki-berry": (80, "Rock"),
        "mago-berry": (80, "Ghost"),
        "aguav-berry": (80, "Dragon"),
        "iapapa-berry": (80, "Dark"),
        "liechi-berry": (100, "Grass"),
        "ganlon-berry": (100, "Ice"),
        "salac-berry": (100, "Fighting"),
        "petaya-berry": (100, "Poison"),
        "apicot-berry": (100, "Ground"),
        "lansat-berry": (100, "Flying"),
        "starf-berry": (100, "Psychic"),
        "enigma-berry": (100, "Bug"),
        "micle-berry": (100, "Rock"),
        "custap-berry": (100, "Ghost"),
        "jaboca-berry": (100, "Dragon"),
        "rowap-berry": (100, "Dark"),
        "kee-berry": (100, "Fairy"),
        "maranga-berry": (100, "Steel"),
    }
    
    berry_norm = berry.lower().replace(" ", "-") if berry else ""
    return BERRY_DATA.get(berry_norm, (80, "Normal"))


def handle_natural_gift(user) -> Tuple[bool, int, str, str]:
    """
    Natural Gift: Consumes Berry and uses its power/type
    Returns (success, power, type, message)
    """
    if not user.item or "berry" not in user.item.lower():
        return False, 0, "Normal", "Natural Gift failed! (No Berry held)"
    
    power, move_type = calculate_natural_gift_power_type(user.item)
    berry_name = user.item.replace("-", " ").title()
    
    # Consume the Berry
    user.item = None
    
    return True, power, move_type, f"Natural Gift consumed {berry_name}!"


def can_use_stuff_cheeks(user) -> Tuple[bool, str]:
    """
    Stuff Cheeks: Can only be used if holding a Berry
    Consumes Berry and raises Defense by 2 stages
    """
    if not user.item or "berry" not in user.item.lower():
        return False, "Stuff Cheeks failed! (No Berry held)"
    return True, ""


def consume_held_berry(mon, *, announce: bool = True) -> Tuple[bool, Optional[str], List[str]]:
    """
    Force a Pokémon to consume its held Berry and apply its effects.
    Returns (consumed, berry_name, messages).
    """
    from .items import normalize_item_name, get_item_effect
    
    if not mon.item or "berry" not in mon.item.lower():
        return False, None, []
    
    berry_id = normalize_item_name(mon.item)
    item_data = get_item_effect(berry_id)
    if not item_data or not item_data.get("berry"):
        return False, None, []
    
    berry_display = mon.item.replace("-", " ").title()
    ability_norm = normalize_ability_name(mon.ability or "")
    ability_data = get_ability_effect(ability_norm)
    ripen_multiplier = ability_data.get("berry_effect_mult", 1.0)
    cheek_pouch_bonus = ability_data.get("berry_heal_bonus", 0.0)
    has_cheek_pouch = cheek_pouch_bonus > 0
    
    messages: List[str] = []
    if announce:
        messages.append(f"{mon.species} ate its {berry_display}!")
    
    consumed_berry = mon.item
    mon._last_consumed_berry = consumed_berry
    mon.item = None
    mon._consumed_berry = True
    
    from .engine import modify_stages
    
    # HP restoration
    if "heals_hp_percent" in item_data:
        heal_ratio = item_data["heals_hp_percent"] * ripen_multiplier
        heal_amount = int(mon.max_hp * heal_ratio)
        actual_heal = min(heal_amount, mon.max_hp - mon.hp)
        if actual_heal > 0:
            mon.hp = min(mon.max_hp, mon.hp + actual_heal)
            messages.append(f"{mon.species} restored {actual_heal} HP!")
    elif "heals_hp" in item_data:
        heal_amount = int(item_data["heals_hp"] * ripen_multiplier)
        actual_heal = min(heal_amount, mon.max_hp - mon.hp)
        if actual_heal > 0:
            mon.hp = min(mon.max_hp, mon.hp + actual_heal)
            messages.append(f"{mon.species} restored {actual_heal} HP!")
    
    # Status healing
    heals_status = item_data.get("heals_status")
    if heals_status:
        cured = False
        if heals_status == "all":
            if getattr(mon, "status", None):
                mon.status = None
                mon.status_turns = 0
                cured = True
            if getattr(mon, "confused", False):
                mon.confused = False
                mon.confusion_turns = 0
                cured = True
        elif heals_status == "confusion":
            if getattr(mon, "confused", False):
                mon.confused = False
                mon.confusion_turns = 0
                cured = True
        else:
            status_lower = (getattr(mon, "status", None) or "").lower()
            if status_lower in {heals_status, heals_status.lower()}:
                mon.status = None
                mon.status_turns = 0
                cured = True
        if cured:
            messages.append(f"{mon.species}'s status was cured!")
    
    # Confusion if wrong nature (FIGY/WIKI etc.)
    wrong_stat = item_data.get("confuses_if_wrong_nature")
    if wrong_stat:
        nature = getattr(mon, "nature_name", None)
        if nature:
            lowered_stats = {
                "atk": {"bold", "timid", "modest", "calm"},
                "defn": {"lonely", "mild", "hasty", "gentle"},
                "spa": {"adamant", "jolly", "impish", "careful"},
                "spd": {"naughty", "rash", "naive", "lax"},
                "spe": {"brave", "quiet", "relaxed", "sassy"},
            }
            nature_key = nature.lower().replace(" ", "-")
            if nature_key in lowered_stats.get(wrong_stat, set()) and not getattr(mon, "confused", False):
                mon.confused = True
                mon.confusion_turns = random.randint(1, 4)
                mon._confusion_applied_this_turn = True
                messages.append(f"{mon.species} became confused!")
    
    # Stat boosts (Liechi, Salac, etc.)
    stat_boosts = item_data.get("boost_stat_at_pinch")
    if stat_boosts:
        adjusted = {stat: int(max(1, change * ripen_multiplier)) for stat, change in stat_boosts.items()}
        boost_msgs = modify_stages(mon, adjusted, caused_by_opponent=False)
        messages.extend(boost_msgs)
    
    # Critical-hit boost (Lansat)
    if "crit_boost_at_pinch" in item_data:
        stages = int(max(1, item_data["crit_boost_at_pinch"] * ripen_multiplier))
        mon.focused_energy = True
        mon.focused_energy_stage = max(mon.focused_energy_stage, stages)
        messages.append(f"{mon.species}'s critical-hit ratio rose sharply!")
    
    # Accuracy boost (Micle)
    if item_data.get("accuracy_boost_at_pinch"):
        from .generation import get_generation
        generation = get_generation()
        mon._micle_active = True
        base_mult = (4915 / 4096) if generation >= 5 else 1.2
        mon._micle_multiplier = base_mult * ripen_multiplier
        messages.append(f"{mon.species}'s accuracy rose!")
    
    # Priority boost (Custap)
    if item_data.get("priority_boost_at_pinch"):
        mon._custap_active = True
        messages.append(f"{mon.species} braced itself to move first!")
    
    # Random stat boost (Starf)
    if "random_stat_boost_at_pinch" in item_data:
        stats_pool = ["atk", "defn", "spa", "spd", "spe"]
        chosen = random.choice(stats_pool)
        boost_amount = int(max(1, item_data["random_stat_boost_at_pinch"] * ripen_multiplier))
        boost_msgs = modify_stages(mon, {chosen: boost_amount}, caused_by_opponent=False)
        messages.extend(boost_msgs)
    
    # Cheek Pouch bonus healing
    if has_cheek_pouch:
        extra_heal = int(mon.max_hp * cheek_pouch_bonus)
        if extra_heal > 0:
            actual_bonus = min(extra_heal, mon.max_hp - mon.hp)
            if actual_bonus > 0:
                mon.hp = min(mon.max_hp, mon.hp + actual_bonus)
                messages.append(f"{mon.species}'s Cheek Pouch restored {actual_bonus} HP!")
    
    return True, berry_display, messages


def handle_stuff_cheeks(user) -> str:
    """
    Stuff Cheeks: Consume Berry, apply its effects immediately, and raise Defense by 2 stages.
    """
    from .engine import modify_stages
    consumed, berry_name, berry_messages = consume_held_berry(user, announce=False)
    if not consumed or not berry_name:
        if hasattr(user, "_last_move_failed"):
            user._last_move_failed = True
        return "But it failed! (No Berry held)"
    
    messages = [f"Stuffed itself with {berry_name}!"]
    messages.extend(berry_messages)
    
    stage_messages = modify_stages(user, {"defn": 2}, caused_by_opponent=False)
    messages.extend(stage_messages)
    
    if len(messages) == 1:
        messages.append("But nothing happened!")
    
    return "\n".join(messages)


def apply_teatime(user: Any, battle_state: Any = None, *, opponent: Any = None) -> List[str]:
    """
    Teatime: All Pokémon on the field consume their held berries.
    Returns list of log messages.
    """
    mons: List[Any] = []
    seen: Set[int] = set()
    
    def _add_mon(mon_obj: Any) -> None:
        if mon_obj and getattr(mon_obj, "hp", 0) > 0:
            mon_id = id(mon_obj)
            if mon_id not in seen:
                seen.add(mon_id)
                mons.append(mon_obj)
    
    _add_mon(user)
    if opponent:
        _add_mon(opponent)
    
    if battle_state:
        try:
            active_p1 = battle_state._active(battle_state.p1_id)
            active_p2 = battle_state._active(battle_state.p2_id)
            _add_mon(active_p1)
            _add_mon(active_p2)
        except Exception:
            pass
    elif hasattr(user, "_battle_state"):
        bs = getattr(user, "_battle_state")
        if bs:
            try:
                active_p1 = bs._active(bs.p1_id)
                active_p2 = bs._active(bs.p2_id)
                _add_mon(active_p1)
                _add_mon(active_p2)
            except Exception:
                pass
    
    messages: List[str] = []
    any_consumed = False
    for mon in mons:
        consumed, _, berry_msgs = consume_held_berry(mon, announce=True)
        if consumed:
            any_consumed = True
            messages.extend(berry_msgs)
    
    if not any_consumed:
        messages.append("But nothing happened!")
    
    return messages

# ============================================================================
# RANDOM MOVE SELECTION
# ============================================================================

def get_metronome_move(*, field_effects: Any = None, battle_state: Any = None) -> Tuple[str, str]:
    """
    Metronome: Select a random move from a large pool
    Excludes certain moves (Metronome itself, signature Z-moves, etc.)
    
    Returns: (selected_move, message)
    """
    # List of common damaging and status moves (simplified pool)
    METRONOME_POOL = [
        "thunderbolt", "flamethrower", "ice-beam", "surf", "earthquake",
        "psychic", "shadow-ball", "energy-ball", "focus-blast", "dragon-pulse",
        "hyper-beam", "fire-blast", "thunder", "blizzard", "hydro-pump",
        "solar-beam", "giga-drain", "leech-seed", "toxic", "will-o-wisp",
        "thunder-wave", "swords-dance", "nasty-plot", "calm-mind", "dragon-dance",
        "protect", "substitute", "recover", "roost", "rest",
        "close-combat", "outrage", "stone-edge", "iron-head", "u-turn",
        "volt-switch", "scald", "ice-shard", "aqua-jet", "mach-punch",
        "extreme-speed", "sucker-punch", "bullet-punch", "shadow-sneak",
        "brave-bird", "flare-blitz", "wood-hammer", "head-smash",
        "explosion", "self-destruct", "perish-song", "memento",
        "stealth-rock", "spikes", "toxic-spikes", "sticky-web",
        "light-screen", "reflect", "aurora-veil", "trick-room",
        "fake-out", "taunt", "encore", "yawn", "sleep-powder",
        "stun-spore", "confuse-ray", "swagger", "charm", "growl"
    ]
    
    selected_move = random.choice(METRONOME_POOL)
    move_display = selected_move.replace("-", " ").title()
    return selected_move, f"Metronome called **{move_display}**!"


_GRAVITY_BLOCKED_MOVES = {
    "bounce", "fly", "high-jump-kick", "jump-kick", "magnet-rise",
    "sky-drop", "splash", "telekinesis"
}

_HEAL_BLOCK_FAIL_MOVES = {
    "heal-order", "milk-drink", "morning-sun", "moonlight", "recover",
    "rest", "roost", "shore-up", "slack-off", "soft-boiled", "softboiled",
    "strength-sap", "synthesis", "swallow", "wish"
}


def get_assist_move(user: Any, *, battle_state: Any = None, field_effects: Any = None) -> Tuple[Optional[str], str]:
    """Select a move for Assist, honoring generation-specific eligibility rules."""
    from .generation import get_generation

    battle_state = battle_state or getattr(user, '_battle_state', None)
    field_effects = field_effects or getattr(user, '_field_effects', None)

    try:
        generation = get_generation(field_effects=field_effects, battle_state=battle_state)
    except Exception:
        generation = 9

    if generation >= 8:
        return None, "Assist failed! (Assist cannot be selected in this generation)"

    gravity_active = generation == 4 and bool(getattr(field_effects, 'gravity', False))
    heal_blocked = generation == 4 and getattr(user, 'heal_blocked', 0) > 0

    def _resolve_owner_id(state: Any, mon: Any) -> Optional[int]:
        if not state:
            return None
        try:
            if mon in state.team_for(state.p1_id):
                return state.p1_id
            if mon in state.team_for(state.p2_id):
                return state.p2_id
        except Exception:
            return None
        return None

    owner_id = _resolve_owner_id(battle_state, user)

    party_members: List[Any] = []
    if owner_id is not None and battle_state:
        try:
            party_members = [mon for mon in battle_state.team_for(owner_id) if mon is not None and mon is not user]
        except Exception:
            party_members = []

    if not party_members:
        pseudo_party = getattr(user, '_assist_party', None)
        if isinstance(pseudo_party, list):
            party_members = [ally for ally in pseudo_party if ally is not None]

    candidate_moves: List[str] = []

    for ally in party_members:
        if ally is None:
            continue

        if getattr(ally, 'is_egg', False) and generation != 5:
            continue

        moves_source = list(getattr(ally, 'moves', []) or [])

        if generation <= 4:
            original_moves = getattr(ally, '_original_moves', None)
            if original_moves:
                moves_source = list(original_moves)

        for move_name in moves_source:
            if not move_name:
                continue
            normalized = move_name.lower().replace(" ", "-")

            if _should_exclude_assist_move(move_name, generation=generation):
                continue

            if gravity_active and normalized in _GRAVITY_BLOCKED_MOVES:
                continue

            if heal_blocked and normalized in _HEAL_BLOCK_FAIL_MOVES:
                continue

            candidate_moves.append(move_name)

    if not candidate_moves:
        return None, "Assist failed! (No eligible moves)"

    selected_move = random.choice(candidate_moves)
    return selected_move, f"Assist chose {selected_move}!"


def get_sleep_talk_move(user, *, field_effects: Any = None, battle_state: Any = None) -> Tuple[Optional[str], str]:
    """Select a move for Sleep Talk, honoring generation and ability rules."""
    from .generation import get_generation
    from .abilities import normalize_ability_name, get_ability_effect

    generation = get_generation(field_effects=field_effects)

    ability = normalize_ability_name(getattr(user, 'ability', '') or "")
    ability_data = get_ability_effect(ability)

    is_asleep = getattr(user, 'status', None) == "slp" or ability_data.get("always_asleep")
    if not is_asleep:
        return None, "Sleep Talk failed!"

    excluded = {
        "assist", "beak-blast", "belch", "bide", "celebrate", "chatter", "copycat",
        "focus-punch", "me-first", "metronome", "mimic", "mirror-move", "nature-power",
        "shadow-force", "shell-trap", "sketch", "sleep-talk", "snore", "uproar"
    }

    available_moves = [m for m in (user.moves or []) if m and m.lower().replace(" ", "-") not in excluded]

    if not available_moves:
        return None, "Sleep Talk failed! (No valid moves)"

    selected_move = random.choice(available_moves)

    # Gen II: Sleep Talk fails if the called move has 0 PP remaining
    if generation == 2 and battle_state and hasattr(battle_state, '_pp_left'):
        user_id = getattr(user, '_player_id', getattr(user, 'id', None))
        if user_id is not None:
            try:
                pp_left = battle_state._pp_left(user_id, selected_move)
            except Exception:
                pp_left = 1
            if pp_left <= 0:
                return None, f"Sleep Talk failed! ({selected_move} is out of PP)"

    return selected_move, f"Sleep Talk used {selected_move}!"


# ============================================================================
# MOVE COPYING
# ============================================================================

def get_copycat_move(battle_state) -> Tuple[Optional[str], str]:
    """
    Copycat: Use the last move used by any Pokémon with generation-specific mechanics.
    
    Generation-specific mechanics:
    - Gen IV: Calling move counted (not called move), invalid if status prevented, charging, recharging, Bide final
    - Gen V-VI: Called move counted (not calling move), status prevention doesn't invalidate
    - Gen VII+: Fails on Z-Moves, copies base move from Max Moves
    
    Returns (move_name, message) or (None, fail_message)
    """
    from .generation import get_generation
    
    if not battle_state:
        return None, "Copycat failed! (No battle state)"
    
    generation = get_generation(battle_state=battle_state)
    
    # Get last move used (tracking depends on generation)
    last_move = getattr(battle_state, '_last_move_used', None)
    
    # Gen VII+: Fail on Z-Moves
    if generation >= 7:
        if last_move and hasattr(battle_state, '_last_move_was_z_move'):
            if getattr(battle_state, '_last_move_was_z_move', False):
                return None, "Copycat failed! (Cannot copy Z-Moves)"
        
        # Gen VII+: Copy base move from Max Moves
        if last_move and hasattr(battle_state, '_last_move_was_max_move'):
            if getattr(battle_state, '_last_move_was_max_move', False):
                base_move = getattr(battle_state, '_last_max_move_base', None)
                if base_move:
                    last_move = base_move
    
    if not last_move:
        return None, "Copycat failed! (No move to copy)"
    
    # Comprehensive list of uncopyable moves (from image table)
    uncopyable = [
        "assist", "baneful-bunker", "beak-blast", "belch", "bestow", "celebrate",
        "chatter", "copycat", "counter", "covet", "destiny-bond", "detect",
        "dynamax-cannon", "endure", "feint", "focus-punch", "follow-me", "helping-hand",
        "hold-hands", "king's-shield", "mat-block", "me-first", "metronome", "mimic",
        "mirror-coat", "mirror-move", "nature-power", "protect", "rage-powder", "roar",
        "sketch", "sleep-talk", "snatch", "spiky-shield", "struggle", "switcheroo",
        "thief", "transform", "trick", "whirlwind"
    ]
    
    # Generation-specific uncopyable moves
    normalized_move = last_move.lower().replace(" ", "-")
    
    if generation >= 6:
        # Gen VI+: Roar and Whirlwind cannot be copied
        if normalized_move in ["roar", "whirlwind"]:
            return None, f"Copycat failed! ({last_move} cannot be copied)"
    else:
        # Gen IV-V: Roar and Whirlwind CAN be copied
        pass
    
    if generation >= 5:
        # Gen V+: Transform cannot be copied
        if normalized_move == "transform":
            return None, f"Copycat failed! ({last_move} cannot be copied)"
    else:
        # Gen IV: Transform CAN be copied
        pass
    
    if normalized_move in uncopyable:
        return None, f"Copycat failed! ({last_move} cannot be copied)"
    
    # Gen IV: Check if move was invalidated by status prevention, charging, etc.
    if generation == 4:
        if hasattr(battle_state, '_last_move_invalidated'):
            if getattr(battle_state, '_last_move_invalidated', False):
                return None, "Copycat failed! (Last move was invalidated)"
    
    return last_move, f"Copycat copied {last_move}!"


def get_mirror_move(user: Any, target: Any, *, generation: int,
                    battle_state: Any = None) -> Tuple[Optional[str], str]:
    """
    Mirror Move: Copy the appropriate move based on generation rules.
    Returns (move_name, message) or (None, failure_message).
    """
    from .move_effects import get_move_secondary_effect

    uncopyable = {
        "mirror-move", "copycat", "metronome", "sketch", "transform"
    }

    # Check generation-specific copied_by_mirror_move flags from move_effects
    # This will be checked later for the specific move

    active_mons: List[Any] = []
    if battle_state:
        try:
            active_mons = [battle_state._active(battle_state.p1_id),
                           battle_state._active(battle_state.p2_id)]
        except Exception:
            active_mons = []
    active_mons = [mon for mon in active_mons if mon is not None]

    if generation >= 7:
        # Gen 7: copy the selected Pokémon's last move regardless of target
        if active_mons and target not in active_mons:
            return None, "Mirror Move failed! (Target is not on the field)"

        last_move = getattr(target, 'last_move_used', None)
        if not last_move:
            return None, "Mirror Move failed! (Target hasn't used a move)"

        normalized = last_move.lower().replace(" ", "-")
        if normalized in uncopyable:
            return None, f"Mirror Move failed! ({last_move} cannot be mirrored)"
        
        # Check generation-specific copied_by_mirror_move flag
        move_effect = get_move_secondary_effect(normalized)
        if move_effect:
            gen_specific = move_effect.get("gen_specific", {})
            if gen_specific:
                # Helper to check if generation matches a spec (e.g., "1-3", "4+", "5")
                def _match_gen(spec: str, gen: int) -> bool:
                    spec = (spec or "").strip()
                    if not spec:
                        return False
                    if spec.endswith('+'):
                        try:
                            return gen >= int(spec[:-1])
                        except ValueError:
                            return False
                    if '-' in spec:
                        try:
                            start_str, end_str = spec.split('-', 1)
                            start = int(start_str)
                            end = int(end_str)
                            return start <= gen <= end
                        except ValueError:
                            return False
                    try:
                        return gen == int(spec)
                    except ValueError:
                        return False
                
                # Check each gen_specific entry for copied_by_mirror_move
                copied_by_mirror = None
                for spec, overrides in gen_specific.items():
                    if isinstance(overrides, dict) and "copied_by_mirror_move" in overrides:
                        if _match_gen(str(spec), generation):
                            copied_by_mirror = overrides.get("copied_by_mirror_move")
                            break
                
                if copied_by_mirror is False:
                    return None, f"Mirror Move failed! ({last_move} cannot be mirrored in this generation)"
                # If True, allow copying (continue below)

        return last_move, f"Mirror Move copied {last_move}!"

    # Gen 1-6: copy the last move targeted at the user by a Pokémon still on the field
    if generation == 2 and getattr(user, '_transformed', False):
        return None, "Mirror Move failed! (Transform prevents it in this generation)"
    recorded_move = getattr(user, 'last_move_targeted', None)
    source = getattr(user, 'last_move_target_source', None)

    if not recorded_move or source is None:
        return None, "Mirror Move failed! (No move was aimed at the user)"

    if source is user:
        return None, "Mirror Move failed! (Cannot copy self-targeted moves)"

    if active_mons and source not in active_mons:
        return None, "Mirror Move failed! (Original user left the field)"

    normalized = recorded_move.lower().replace(" ", "-")
    if normalized in uncopyable:
        return None, f"Mirror Move failed! ({recorded_move} cannot be mirrored)"
    
    # Check generation-specific copied_by_mirror_move flag
    move_effect = get_move_secondary_effect(normalized)
    if move_effect:
        gen_specific = move_effect.get("gen_specific", {})
        if gen_specific:
            # Helper to check if generation matches a spec (e.g., "1-3", "4+", "5")
            def _match_gen(spec: str, gen: int) -> bool:
                spec = (spec or "").strip()
                if not spec:
                    return False
                if spec.endswith('+'):
                    try:
                        return gen >= int(spec[:-1])
                    except ValueError:
                        return False
                if '-' in spec:
                    try:
                        start_str, end_str = spec.split('-', 1)
                        start = int(start_str)
                        end = int(end_str)
                        return start <= gen <= end
                    except ValueError:
                        return False
                try:
                    return gen == int(spec)
                except ValueError:
                    return False
            
            # Check each gen_specific entry for copied_by_mirror_move
            copied_by_mirror = None
            for spec, overrides in gen_specific.items():
                if isinstance(overrides, dict) and "copied_by_mirror_move" in overrides:
                    if _match_gen(str(spec), generation):
                        copied_by_mirror = overrides.get("copied_by_mirror_move")
                        break
            
            if copied_by_mirror is False:
                return None, f"Mirror Move failed! ({recorded_move} cannot be mirrored in this generation)"
            # If True, allow copying (continue below)

    return recorded_move, f"Mirror Move copied {recorded_move}!"






# ============================================================================
# PROTECT VARIANTS
# ============================================================================

def apply_mat_block(user, turn_number: int) -> Tuple[bool, str]:
    """
    Mat Block: Protects user's side from damaging moves (only works on first turn out)
    Returns (success, message)
    """
    # Mat Block only works on the first turn after the Pokémon enters the field
    # _turns_since_switch_in is 0 on the turn it switches in, 1 on the next turn, etc.
    turns_since_switch = getattr(user, '_turns_since_switch_in', 99)
    
    if turns_since_switch != 0:
        return False, "Mat Block failed! (Can only be used on the first turn)"
    
    # Set protection flag on the user's side (affects all Pokémon on that side)
    user._mat_block_active = True
    # Also set on the side object if available
    if hasattr(user, '_side') and user._side:
        user._side._mat_block_active = True
    
    return True, f"{user.species} intends to flip up a mat!"


def check_mat_block(attacker, defender, move_category: str, defender_side: Any = None) -> Tuple[bool, str]:
    """
    Check if Mat Block protects from the incoming move
    Mat Block protects all Pokémon on the user's side from damaging moves
    Returns (blocked, message)
    """
    # Check if Mat Block is active on the defender's side
    mat_block_active = False
    if defender_side and hasattr(defender_side, '_mat_block_active'):
        mat_block_active = defender_side._mat_block_active
    elif hasattr(defender, '_mat_block_active'):
        mat_block_active = defender._mat_block_active
    
    if not mat_block_active:
        return False, ""
    
    # Mat Block only blocks damaging moves (physical and special)
    if move_category in ["physical", "special"]:
        return True, f"Mat Block protected {defender.species}!"
    
    return False, ""


def apply_crafty_shield(user_side) -> Tuple[bool, str]:
    """
    Crafty Shield: Protects user's side from status moves for this turn
    Returns (success, message)
    """
    user_side._crafty_shield_active = True
    return True, "Crafty Shield protected the team from status moves!"


def check_crafty_shield(attacker_side, defender_side, move_category: str) -> Tuple[bool, str]:
    """
    Check if Crafty Shield protects from the incoming move
    Returns (blocked, message)
    """
    if not hasattr(defender_side, '_crafty_shield_active') or not defender_side._crafty_shield_active:
        return False, ""
    
    # Crafty Shield only blocks status moves
    if move_category == "status":
        return True, "Crafty Shield protected from the status move!"
    
    return False, ""


def apply_quick_guard(
    user,
    user_side,
    field_effects: Optional[Any] = None,
    battle_state: Optional[Any] = None
) -> Tuple[bool, str]:
    """
    Quick Guard: Protects user's side from priority moves for this turn
    Returns (success, message)
    """
    from .generation import get_generation
    import random

    if not user_side:
        return False, "But it failed!"

    generation = get_generation(
        field_effects=field_effects,
        battle_state=battle_state
    ) if (field_effects or battle_state) else 9

    # Gen VII+: Always succeeds and no longer shares Protect counter
    if generation >= 7 or getattr(user, '_quick_guard_always_succeeds', False):
        user_side._quick_guard_active = True
        user.consecutive_protects = 0
        return True, "Quick Guard protected the team from priority moves!"

    # Gen V-VI: Shares Protect success counter (1 -> 1/2 -> 1/4 ...)
    success_chance = 1.0 if getattr(user, 'consecutive_protects', 0) == 0 else (1.0 / 2.0) ** user.consecutive_protects

    if random.random() < success_chance:
        user_side._quick_guard_active = True
        user.consecutive_protects = getattr(user, 'consecutive_protects', 0) + 1
        return True, "Quick Guard protected the team from priority moves!"

    # Failure resets counter
    user.consecutive_protects = 0
    return False, "But it failed!"


def check_quick_guard(attacker_side, defender_side, move_priority: int) -> Tuple[bool, str]:
    """
    Check if Quick Guard protects from the incoming move
    Returns (blocked, message)
    """
    if not hasattr(defender_side, '_quick_guard_active') or not defender_side._quick_guard_active:
        return False, ""
    
    # Quick Guard only blocks priority moves (priority > 0)
    if move_priority > 0:
        return True, "Quick Guard protected from the priority move!"
    
    return False, ""


def apply_wide_guard(user, user_side, field_effects=None) -> Tuple[bool, str]:
    """
    Wide Guard: Protects user's side from spread moves for this turn
    Returns (success, message)
    """
    from .generation import get_generation
    import random

    generation = get_generation(field_effects=field_effects)

    # Gen VII+: Always succeeds and no longer shares Protect counter
    if generation >= 7:
        user_side._wide_guard_active = True
        user.consecutive_protects = 0
        return True, "Wide Guard protected the team from spread moves!"

    # Gen V-VI: Shares Protect success counter (1 -> 1/2 -> 1/4 ...)
    success_chance = 1.0 if getattr(user, 'consecutive_protects', 0) == 0 else (1.0 / 2.0) ** user.consecutive_protects

    if random.random() < success_chance:
        user_side._wide_guard_active = True
        user.consecutive_protects = getattr(user, 'consecutive_protects', 0) + 1
        return True, "Wide Guard protected the team from spread moves!"

    # Failure resets counter
    user.consecutive_protects = 0
    return False, "But it failed!"


def check_wide_guard(attacker_side, defender_side, move_target: str) -> Tuple[bool, str]:
    """
    Check if Wide Guard protects from the incoming move
    Returns (blocked, message)
    """
    if not hasattr(defender_side, '_wide_guard_active') or not defender_side._wide_guard_active:
        return False, ""
    
    # Wide Guard blocks moves that hit multiple targets
    spread_targets = ["all-opponents", "all-other-pokemon", "entire-field"]
    if move_target in spread_targets:
        return True, "Wide Guard protected from the spread move!"
    
    return False, ""


def clear_protection_flags(side):
    """Clear all protection flags at the end of turn"""
    if hasattr(side, '_crafty_shield_active'):
        side._crafty_shield_active = False
    if hasattr(side, '_quick_guard_active'):
        side._quick_guard_active = False
    if hasattr(side, '_wide_guard_active'):
        side._wide_guard_active = False
    if hasattr(side, '_mat_block_active'):
        side._mat_block_active = False


def clear_mat_block(mon):
    """Clear Mat Block flag at the end of turn"""
    if hasattr(mon, '_mat_block_active'):
        mon._mat_block_active = False


# ============================================================================
# PRE-MOVE DAMAGE MOVES (Focus Punch, Shell Trap, Beak Blast)
# ============================================================================

def setup_focus_punch(user) -> str:
    """
    Focus Punch: Set up the charge, will fail if user takes damage before executing
    """
    user._focus_punch_charging = True
    user._took_damage_before_punch = False
    return f"{user.species} is tightening its focus!"


def check_focus_punch_interrupt(user) -> Tuple[bool, str]:
    """
    Check if Focus Punch was interrupted by damage
    Returns (interrupted, message)
    """
    if not hasattr(user, '_focus_punch_charging') or not user._focus_punch_charging:
        return False, ""
    
    if getattr(user, '_took_damage_before_punch', False):
        user._focus_punch_charging = False
        return True, f"{user.species} lost its focus!"
    
    user._focus_punch_charging = False
    return False, ""


def setup_shell_trap(user) -> str:
    """
    Shell Trap: Set trap, will activate if user takes physical damage
    """
    user._shell_trap_set = True
    user._shell_trap_activated = False
    return f"{user.species} set a shell trap!"


def check_shell_trap_trigger(defender, attacker, move_category: str) -> str:
    """
    Check if Shell Trap is triggered by physical damage
    Returns damage/message if triggered
    """
    if not hasattr(defender, '_shell_trap_set') or not defender._shell_trap_set:
        return ""
    
    if move_category == "physical" and attacker.hp > 0:
        defender._shell_trap_activated = True
        # Calculate Shell Trap damage (base 150 Fire-type special move)
        # Simplified - would need full damage calculation
        return f"{defender.species}'s Shell Trap activated!"
    
    return ""


def setup_beak_blast(user) -> str:
    """
    Beak Blast: Charges, will burn attacker if hit by contact move
    """
    user._beak_blast_charging = True
    return f"{user.species} started heating up its beak!"


def check_beak_blast_burn(defender, attacker, is_contact: bool) -> str:
    """
    Check if Beak Blast burns the attacker
    Returns message if burn applied
    """
    if not hasattr(defender, '_beak_blast_charging') or not defender._beak_blast_charging:
        return ""
    
    if is_contact and not attacker.status and attacker.hp > 0:
        # Check if Fire-type (immune to burn)
        if "Fire" not in [t for t in attacker.types if t]:
            attacker.status = "brn"
            defender._beak_blast_charging = False
            return f"{attacker.species} was burned by the heated beak!"
    
    return ""


def clear_charge_moves(mon):
    """Clear all charge move flags after execution"""
    if hasattr(mon, '_focus_punch_charging'):
        mon._focus_punch_charging = False
    if hasattr(mon, '_took_damage_before_punch'):
        mon._took_damage_before_punch = False
    if hasattr(mon, '_shell_trap_set'):
        mon._shell_trap_set = False
    if hasattr(mon, '_shell_trap_activated'):
        mon._shell_trap_activated = False
    if hasattr(mon, '_beak_blast_charging'):
        mon._beak_blast_charging = False


# ============================================================================
# FUSION MOVES
# ============================================================================

def check_fusion_boost(move_name: str, battle_state) -> Tuple[bool, str]:
    """
    Fusion Flare / Fusion Bolt: Check if the counterpart was used this turn
    Returns (boosted, message)
    """
    move_lower = move_name.lower().replace(" ", "-")
    
    if move_lower == "fusion-flare":
        # Check if Fusion Bolt was used this turn
        if getattr(battle_state, '_fusion_bolt_used_this_turn', False):
            return True, "The move was powered up by Fusion Bolt!"
    
    elif move_lower == "fusion-bolt":
        # Check if Fusion Flare was used this turn
        if getattr(battle_state, '_fusion_flare_used_this_turn', False):
            return True, "The move was powered up by Fusion Flare!"
    
    return False, ""


def mark_fusion_move_used(move_name: str, battle_state):
    """Mark that a fusion move was used this turn"""
    move_lower = move_name.lower().replace(" ", "-")
    
    if move_lower == "fusion-flare":
        battle_state._fusion_flare_used_this_turn = True
    elif move_lower == "fusion-bolt":
        battle_state._fusion_bolt_used_this_turn = True


def clear_fusion_flags(battle_state):
    """Clear fusion move flags at the end of turn"""
    if hasattr(battle_state, '_fusion_flare_used_this_turn'):
        battle_state._fusion_flare_used_this_turn = False
    if hasattr(battle_state, '_fusion_bolt_used_this_turn'):
        battle_state._fusion_bolt_used_this_turn = False


# ============================================================================
# FORME-CHANGE MOVES
# ============================================================================

def apply_relic_song(user) -> Tuple[bool, str]:
    """
    Relic Song: Switches Meloetta between Aria and Pirouette Forme
    Returns (success, message)
    
    Aria (default): Normal/Psychic - High SpA/SpD (77/77/77/128/128/90)
    Pirouette: Normal/Fighting - High Atk/Spe (77/128/90/77/77/128)
    """
    if user.species.lower() not in ["meloetta", "meloetta-aria", "meloetta-pirouette"]:
        return False, "Relic Song failed! (Not Meloetta)"
    
    # Switch forme
    if "pirouette" in user.species.lower():
        # Switch to Aria Forme (from Pirouette)
        user.species = "Meloetta"
        user.types = ["Normal", "Psychic"]
        user.form = "aria"  # Update form for sprite rendering
        
        # Update stats to Aria stats (SpA/SpD focused)
        # Using the level and nature already on the user
        from .engine import _calc_stat
        nature_mods = {
            "atk": 1.0, "defn": 1.0, "spa": 1.0, "spd": 1.0, "spe": 1.0
        }
        # Get nature mods from user.nature_name if available
        if hasattr(user, 'nature_name'):
            from .engine import NATURES
            nature_mods = NATURES.get(user.nature_name, {"atk": 1.0, "defn": 1.0, "spa": 1.0, "spd": 1.0, "spe": 1.0})
        
        # Recalculate stats with Aria base stats
        aria_base = {"atk": 77, "defn": 77, "spa": 128, "spd": 128, "spe": 90}
        user.stats["atk"] = _calc_stat(aria_base["atk"], user.ivs.get("atk", 31), user.evs.get("atk", 0), user.level, nature_mods.get("atk", 1.0))
        user.stats["defn"] = _calc_stat(aria_base["defn"], user.ivs.get("defn", 31), user.evs.get("defn", 0), user.level, nature_mods.get("defn", 1.0))
        user.stats["spa"] = _calc_stat(aria_base["spa"], user.ivs.get("spa", 31), user.evs.get("spa", 0), user.level, nature_mods.get("spa", 1.0))
        user.stats["spd"] = _calc_stat(aria_base["spd"], user.ivs.get("spd", 31), user.evs.get("spd", 0), user.level, nature_mods.get("spd", 1.0))
        user.stats["spe"] = _calc_stat(aria_base["spe"], user.ivs.get("spe", 31), user.evs.get("spe", 0), user.level, nature_mods.get("spe", 1.0))
        
        return True, f"Meloetta changed to Aria Forme!"
    else:
        # Switch to Pirouette Forme (from Aria)
        user.species = "Meloetta-Pirouette"
        user.types = ["Normal", "Fighting"]
        user.form = "pirouette"  # Update form for sprite rendering
        
        # Update stats to Pirouette stats (Atk/Spe focused)
        from .engine import _calc_stat
        nature_mods = {
            "atk": 1.0, "defn": 1.0, "spa": 1.0, "spd": 1.0, "spe": 1.0
        }
        if hasattr(user, 'nature_name'):
            from .engine import NATURES
            nature_mods = NATURES.get(user.nature_name, {"atk": 1.0, "defn": 1.0, "spa": 1.0, "spd": 1.0, "spe": 1.0})
        
        # Recalculate stats with Pirouette base stats
        pirouette_base = {"atk": 128, "defn": 90, "spa": 77, "spd": 77, "spe": 128}
        user.stats["atk"] = _calc_stat(pirouette_base["atk"], user.ivs.get("atk", 31), user.evs.get("atk", 0), user.level, nature_mods.get("atk", 1.0))
        user.stats["defn"] = _calc_stat(pirouette_base["defn"], user.ivs.get("defn", 31), user.evs.get("defn", 0), user.level, nature_mods.get("defn", 1.0))
        user.stats["spa"] = _calc_stat(pirouette_base["spa"], user.ivs.get("spa", 31), user.evs.get("spa", 0), user.level, nature_mods.get("spa", 1.0))
        user.stats["spd"] = _calc_stat(pirouette_base["spd"], user.ivs.get("spd", 31), user.evs.get("spd", 0), user.level, nature_mods.get("spd", 1.0))
        user.stats["spe"] = _calc_stat(pirouette_base["spe"], user.ivs.get("spe", 31), user.evs.get("spe", 0), user.level, nature_mods.get("spe", 1.0))
        
        return True, f"Meloetta changed to Pirouette Forme!"


# ============================================================================
# BEAT UP
# ============================================================================

def calculate_beat_up_damage(user: Any, target: Any, battle_state: Any, field_effects: Any = None) -> Tuple[List[Tuple[int, str]], int]:
    """
    Calculate Beat Up damage with generation-specific mechanics.
    
    Generation II:
    - Each conscious party member (no status) attacks independently
    - Base power 10 per strike (typeless)
    - Uses each party member's Attack and level
    - Ignores stat changes, no STAB
    
    Generation III-IV:
    - Similar to Gen II but can attack partner in Double Battles
    - Ignores Wonder Guard (typeless)
    
    Generation V+:
    - Uses only user's Attack stat (affected by stat boosts)
    - Power = (BaseAttack / 10) + 5 per strike
    - STAB applies (Dark-type)
    - Affected by Technician
    
    Returns: (list of (damage, attacker_name), total_damage)
    """
    from .generation import get_generation
    
    generation = get_generation(field_effects=field_effects)
    strikes = []
    total_damage = 0
    
    # Get user's team
    if not battle_state:
        return strikes, 0
    
    # Determine which team the user belongs to
    user_team = None
    for team_id in [battle_state.p1_id, battle_state.p2_id]:
        team = battle_state.team_for(team_id)
        if user in team:
            user_team = team
            break
    
    if not user_team:
        return strikes, 0
    
    # Get eligible party members (conscious, no status for Gen II-IV)
    eligible_members = []
    
    if generation <= 4:
        # Gen II-IV: Each conscious party member without status
        for member in user_team:
            if member and member.hp > 0:
                if generation == 2:
                    # Gen II: No status
                    if not member.status or member.status in ["none", None]:
                        eligible_members.append(member)
                else:
                    # Gen III-IV: No non-volatile status
                    if not member.status or member.status in ["none", None]:
                        eligible_members.append(member)
    else:
        # Gen V+: Only use user's stats, but need count of eligible members
        eligible_members = [m for m in user_team if m and m.hp > 0]
        # For power calculation, we'll use the count
    
    if not eligible_members:
        return strikes, 0
    
    # Calculate damage for each strike
    if generation <= 4:
        # Gen II-IV: Each member attacks with base power 10, using their own stats
        for member in eligible_members:
            # Gen II: Base power 10, typeless
            # Use member's base Attack (ignoring stat stages)
            from .engine import get_base_stat, calculate_stat
            member_atk_base = get_base_stat(member, "atk")
            target_def_base = get_base_stat(target, "def")
            
            # Damage calculation (simplified - uses base stats)
            # Formula: (((2 * Level / 5 + 2) * Power * A / D) / 50) + 2
            # But Beat Up ignores stat changes, so use base stats
            level_factor = ((2 * member.level // 5) + 2)
            power = 10
            damage = ((level_factor * power * member_atk_base // target_def_base) // 50) + 2
            
            # Apply random factor (0.85-1.0)
            damage = int(damage * random.uniform(0.85, 1.0))
            
            strikes.append((damage, member.species))
            total_damage += damage
            
    else:
        # Gen V+: Use user's Attack, power based on party member base Attack
        for member in eligible_members:
            # Power = (BaseAttack / 10) + 5
            from .engine import get_base_stat
            member_base_atk = get_base_stat(member, "atk")
            power = (member_base_atk // 10) + 5
            
            # Use user's Attack stat (with stat boosts)
            from .engine import get_effective_stat
            user_atk = get_effective_stat(user, "atk")
            target_def = get_effective_stat(target, "def")
            
            # Standard damage calculation with user's boosted stats
            level_factor = ((2 * user.level // 5) + 2)
            damage = ((level_factor * power * user_atk // target_def) // 50) + 2
            
            # Apply random factor
            damage = int(damage * random.uniform(0.85, 1.0))
            
            strikes.append((damage, member.species))
            total_damage += damage
    
    return strikes, total_damage


# ============================================================================
# FOCUS PUNCH
# ============================================================================

def setup_focus_punch(user: Any, field_effects: Any = None) -> str:
    """
    Setup Focus Punch charging phase.
    User focuses, then executes at priority -3 unless hit.
    """
    from .generation import get_generation
    generation = get_generation(field_effects=field_effects)
    
    user._focusing = True
    user._focus_punch_priority = -3
    
    if generation <= 4:
        return f"{user.species} is tightening its focus!"
    else:
        return ""  # Gen V+: No message


def check_focus_punch_fail(user: Any, field_effects: Any = None) -> Tuple[bool, Optional[str]]:
    """
    Check if Focus Punch should fail due to taking damage.
    Returns: (should_fail, message)
    """
    if not getattr(user, '_focusing', False):
        return False, None
    
    # Check if user took damage this turn (but not from status moves or substitute)
    if hasattr(user, '_took_damage_this_turn') and user._took_damage_this_turn:
        # Check if damage was from substitute (shouldn't break focus)
        if hasattr(user, '_substitute_damage_only') and user._substitute_damage_only:
            return False, None
        
        from .generation import get_generation
        generation = get_generation(field_effects=field_effects)
        
        if generation <= 4:
            return True, f"{user.species} lost its focus and couldn't move!"
        else:
            return True, f"{user.species} lost its focus!"
    
    return False, None

