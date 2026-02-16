"""
Advanced Battle Mechanics for PvP System
Handles:
- Multi-turn moves (charging, semi-invulnerable, recharge)
- Move restrictions (Encore, Disable, Taunt, Torment)
- Substitute mechanic
- Protect/Detect
- Field effects (Reflect, Light Screen, Tailwind, Trick Room, etc.)
- Accuracy/Evasion calculations
- Critical hit stages
- Trapping moves
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Set
import random

# ===================== MULTI-TURN MOVE DATA =====================

# Semi-invulnerable moves (turn 1: charging, turn 2: attack)
SEMI_INVULNERABLE_MOVES = {
    "fly": {"invulnerable_type": "flying", "hits_turn": 2},
    "dig": {"invulnerable_type": "underground", "hits_turn": 2},
    "dive": {"invulnerable_type": "underwater", "hits_turn": 2},
    "bounce": {"invulnerable_type": "flying", "hits_turn": 2},
    "phantom-force": {"invulnerable_type": "shadow", "hits_turn": 2},
    "shadow-force": {"invulnerable_type": "shadow", "hits_turn": 2},
    "sky-drop": {"invulnerable_type": "flying", "hits_turn": 2},
}

# Charging moves (turn 1: charge, turn 2: attack)
CHARGING_MOVES = {
    "solar-beam": {"charge_turn": 1, "attack_turn": 2, "skip_charge_in_sun": True},
    "solar-blade": {"charge_turn": 1, "attack_turn": 2, "skip_charge_in_sun": True},
    "skull-bash": {"charge_turn": 1, "attack_turn": 2, "boost_on_charge": {"defn": 1}},
    "razor-wind": {"charge_turn": 1, "attack_turn": 2},
    "sky-attack": {"charge_turn": 1, "attack_turn": 2, "high_crit": True},
    "freeze-shock": {"charge_turn": 1, "attack_turn": 2},
    "ice-burn": {"charge_turn": 1, "attack_turn": 2},
    "geomancy": {"charge_turn": 1, "attack_turn": 2, "boost_on_charge": {"spa": 2, "spd": 2, "spe": 2}},
    "meteor-beam": {"charge_turn": 1, "attack_turn": 2, "boost_on_charge": {"spa": 1}},
}

# Recharge moves (turn 1: attack, turn 2: recharge/can't move)
RECHARGE_MOVES = {
    "hyper-beam", "giga-impact", "blast-burn", "frenzy-plant", "hydro-cannon",
    "rock-wrecker", "roar-of-time", "prismatic-laser", "eternabeam"
}

# Partial trapping moves (damage over 4-5 turns, target trapped)
PARTIAL_TRAPPING_MOVES = {
    "bind": {"damage_fraction": 1/8, "duration": (4, 5)},
    "wrap": {"damage_fraction": 1/8, "duration": (4, 5)},
    "fire-spin": {"damage_fraction": 1/8, "duration": (4, 5)},
    "whirlpool": {"damage_fraction": 1/8, "duration": (4, 5)},
    "sand-tomb": {"damage_fraction": 1/8, "duration": (4, 5)},
    "clamp": {"damage_fraction": 1/8, "duration": (4, 5), "has_special_logic": True},  # Has generation-specific logic
    "magma-storm": {"damage_fraction": 1/8, "duration": (4, 5)},
    "infestation": {"damage_fraction": 1/8, "duration": (4, 5)},
    "snap-trap": {"damage_fraction": 1/8, "duration": (4, 5), "ghost_immunity": True},
    "thunder-cage": {"damage_fraction": 1/8, "duration": (4, 5)},
}

# Trapping moves (prevent switching, but no damage over time)
TRAPPING_MOVES = {
    "block", "mean-look", "spider-web", "fairy-lock", "anchor-shot",
    "spirit-shackle", "jaw-lock", "octolock", "no-retreat"
}

# ===================== MOVE RESTRICTIONS =====================

@dataclass
class MoveRestrictions:
    """Tracks move restrictions on a Pokémon"""
    # Encore: forced to use the same move
    encored_move: Optional[str] = None
    encore_turns: int = 0
    
    # Disable: one move is disabled
    disabled_move: Optional[str] = None
    disable_turns: int = 0
    
    # Taunt: can only use damaging moves
    taunted: bool = False
    taunt_turns: int = 0
    
    # Torment: can't use the same move twice in a row
    tormented: bool = False
    last_move_used: Optional[str] = None
    
    # Trapped: can't switch
    trapped: bool = False
    trap_source: Optional[str] = None
    
    # Partial trapping (Bind, Wrap, etc.)
    partially_trapped: bool = False
    partial_trap_turns: int = 0
    partial_trap_damage: float = 0.0
    
    # Can't move (recharging, flinching, etc.)
    must_recharge: bool = False
    flinched: bool = False
    
    # Rampage moves (Outrage, Thrash, Petal Dance)
    rampage_move: Optional[str] = None
    rampage_turns_remaining: int = 0
    
    def decrement_turns(self):
        """Called at end of turn to decrement all turn counters"""
        if self.encore_turns > 0:
            self.encore_turns -= 1
            if self.encore_turns == 0:
                self.encored_move = None
        
        if self.disable_turns > 0:
            self.disable_turns -= 1
            if self.disable_turns == 0:
                self.disabled_move = None
        
        if self.taunt_turns > 0:
            self.taunt_turns -= 1
            if self.taunt_turns == 0:
                self.taunted = False
        
        if self.partial_trap_turns > 0:
            self.partial_trap_turns -= 1
            if self.partial_trap_turns == 0:
                self.partially_trapped = False
        
        if self.rampage_turns_remaining > 0:
            self.rampage_turns_remaining -= 1
            if self.rampage_turns_remaining == 0:
                self.rampage_move = None
                self.partial_trap_damage = 0.0
        
        # Flinch and recharge are always cleared at end of turn
        self.flinched = False
        self.must_recharge = False

# ===================== FIELD EFFECTS =====================

@dataclass
class FieldEffects:
    """Tracks field-wide effects and side-specific screens"""
    # Generation (for generation-specific mechanics)
    generation: int = 9  # Default to Gen 9
    
    # Weather (already handled in hazards.py, but we track it here too)
    weather: Optional[str] = None  # "sun", "rain", "sandstorm", "snow", "fog"
    weather_turns: int = 0  # 0 = infinite (Gen 9 ability-induced weather)
    sandstorm_damage_turns: int = 0  # Gen II: sandstorm only damages on first four turns
    special_weather: Optional[str] = None  # "heavy-rain", "harsh-sunlight", "strong-winds"
    heavy_rain: bool = False
    harsh_sunlight: bool = False
    
    # Terrain (already handled in hazards.py)
    terrain: Optional[str] = None  # "electric", "grassy", "psychic", "misty"
    terrain_turns: int = 5
    # Secret Power environment: "building", "plain", "sand", "cave", "rock", "tall_grass", "long_grass", "pond_water", "sea_water", "underwater"
    environment: Optional[str] = None

    # Uproar (prevents sleep for all grounded Pokémon)
    uproar_turns: int = 0
    uproar_source: Optional[str] = None
    
    # Trick Room (reverses speed order)
    trick_room: bool = False
    trick_room_turns: int = 0
    
    # Magic Room (suppresses held items)
    magic_room: bool = False
    magic_room_turns: int = 0
    
    # Wonder Room (swaps Defense and Special Defense)
    wonder_room: bool = False
    wonder_room_turns: int = 0
    
    # Gravity (grounds all Pokémon, boosts accuracy)
    gravity: bool = False
    gravity_turns: int = 0
    
    # Water Sport (weakens Fire moves)
    water_sport: bool = False
    water_sport_turns: int = 0
    water_sport_user: Optional[int] = None  # For Gen 3-4: track user to clear on switch
    
    # Mud Sport (weakens Electric moves)
    mud_sport: bool = False
    mud_sport_turns: int = 0
    mud_sport_user: Optional[int] = None  # For Gen 3-4: track user to clear on switch
    
    # Fairy Lock (prevents switching for next turn)
    fairy_lock_pending: bool = False
    fairy_lock_active: bool = False
    # Special weather tracking (Primordial Sea, Desolate Land, Delta Stream)
    weather_lock: Optional[str] = None  # Ability currently locking weather
    weather_lock_owner: Optional[int] = None  # id(mon) currently locking weather
    special_weather_order: Dict[str, int] = field(default_factory=dict)
    weather_activation_counter: int = 0
    
    def decrement_turns(self):
        """Called at end of turn"""
        if self.weather_turns > 0:
            self.weather_turns -= 1
            if self.weather_turns == 0:
                self.weather = None
                self.special_weather = None
                self.heavy_rain = False
                self.harsh_sunlight = False
                self.weather_lock = None
                self.weather_lock_owner = None
                self.sandstorm_damage_turns = 0
        elif self.weather != "sandstorm":
            # Reset Gen II tracking if weather became indefinite or cleared elsewhere
            self.sandstorm_damage_turns = 0

        if self.weather == "sandstorm" and self.sandstorm_damage_turns > 0:
            self.sandstorm_damage_turns -= 1
        
        if self.terrain_turns > 0:
            self.terrain_turns -= 1
            if self.terrain_turns == 0:
                self.terrain = None
        
        if self.fairy_lock_pending:
            self.fairy_lock_pending = False
            self.fairy_lock_active = True
        elif self.fairy_lock_active:
            self.fairy_lock_active = False

        if self.uproar_turns > 0:
            self.uproar_turns -= 1
            if self.uproar_turns == 0:
                self.uproar_source = None
        
        if self.trick_room_turns > 0:
            self.trick_room_turns -= 1
            if self.trick_room_turns == 0:
                self.trick_room = False
        
        if self.magic_room_turns > 0:
            self.magic_room_turns -= 1
            if self.magic_room_turns == 0:
                self.magic_room = False
        
        if self.wonder_room_turns > 0:
            self.wonder_room_turns -= 1
            if self.wonder_room_turns == 0:
                self.wonder_room = False
        
        if self.gravity_turns > 0:
            self.gravity_turns -= 1
            if self.gravity_turns == 0:
                self.gravity = False
        
        # Water Sport: Gen 5+ lasts 5 turns, Gen 3-4 ends on switch (handled separately)
        if self.water_sport and self.water_sport_turns > 0:
            self.water_sport_turns -= 1
            if self.water_sport_turns == 0:
                self.water_sport = False
                self.water_sport_user = None
        
        # Mud Sport: Gen 5+ lasts 5 turns, Gen 3-4 ends on switch (handled separately)
        if self.mud_sport and self.mud_sport_turns > 0:
            self.mud_sport_turns -= 1
            if self.mud_sport_turns == 0:
                self.mud_sport = False
                self.mud_sport_user = None

@dataclass
class SideEffects:
    """Side-specific effects (per player)"""
    # Screens
    reflect: bool = False
    reflect_turns: int = 0
    
    light_screen: bool = False
    light_screen_turns: int = 0
    
    aurora_veil: bool = False
    aurora_veil_turns: int = 0
    
    # Speed control
    tailwind: bool = False
    tailwind_turns: int = 0
    
    # Other side effects
    mist: bool = False
    mist_turns: int = 0
    
    safeguard: bool = False
    safeguard_turns: int = 0
    
    lucky_chant: bool = False
    lucky_chant_turns: int = 0
    
    # Hazards - initialized lazily in __post_init__
    hazards: Any = None  # Will be HazardState object
    
    def __post_init__(self):
        """Initialize hazards if not already set"""
        if self.hazards is None:
            from .hazards import HazardState
            self.hazards = HazardState()
    
    def decrement_turns(self):
        """Called at end of turn"""
        if self.reflect_turns > 0:
            self.reflect_turns -= 1
            if self.reflect_turns == 0:
                self.reflect = False
        
        if self.light_screen_turns > 0:
            self.light_screen_turns -= 1
            if self.light_screen_turns == 0:
                self.light_screen = False
        
        if self.aurora_veil_turns > 0:
            self.aurora_veil_turns -= 1
            if self.aurora_veil_turns == 0:
                self.aurora_veil = False
        
        if self.tailwind_turns > 0:
            self.tailwind_turns -= 1
            if self.tailwind_turns == 0:
                self.tailwind = False
        
        if self.mist_turns > 0:
            self.mist_turns -= 1
            if self.mist_turns == 0:
                self.mist = False
        
        if self.safeguard_turns > 0:
            self.safeguard_turns -= 1
            if self.safeguard_turns == 0:
                self.safeguard = False
        
        if self.lucky_chant_turns > 0:
            self.lucky_chant_turns -= 1
            if self.lucky_chant_turns == 0:
                self.lucky_chant = False

# ===================== SUBSTITUTE =====================

@dataclass
class Substitute:
    """Substitute for a Pokémon (takes damage in place of the real Pokémon)"""
    hp: int
    max_hp: int
    immortal: bool = False  # If True, substitute cannot be broken
    
    def is_alive(self) -> bool:
        return self.hp > 0 or self.immortal
    
    def take_damage(self, dmg: int) -> Tuple[int, bool]:
        """
        Apply damage to substitute.
        Returns: (actual_damage_dealt, substitute_broke)
        """
        if self.immortal:
            # Immortal substitute takes damage but never breaks
            actual = dmg
            return actual, False
        
        actual = min(dmg, self.hp)
        self.hp -= actual
        broke = self.hp <= 0
        return actual, broke
    
    def __bool__(self) -> bool:
        """Allow substitute to be used in boolean context (checks if still alive)"""
        return self.is_alive()

# ===================== PROTECT MECHANICS =====================

@dataclass
class ProtectState:
    """Tracks consecutive Protect usage for accuracy drop"""
    consecutive_protects: int = 0
    
    def get_protect_accuracy(self) -> float:
        """
        Protect accuracy drops by 1/3 each consecutive use:
        1st: 100%, 2nd: 66.67%, 3rd: 44.44%, 4th: 29.63%, etc.
        """
        if self.consecutive_protects == 0:
            return 1.0
        return (1.0 / 3.0) ** self.consecutive_protects
    
    def protect_succeeded(self):
        """Increment counter on successful Protect"""
        self.consecutive_protects += 1
    
    def protect_failed_or_other_move(self):
        """Reset counter if Protect failed or another move was used"""
        self.consecutive_protects = 0

# ===================== CRITICAL HIT STAGES =====================

# Moves with increased crit ratios
HIGH_CRIT_MOVES = {
    "slash", "razor-leaf", "crabhammer", "karate-chop", "stone-edge",
    "shadow-claw", "poison-tail", "leaf-blade", "psycho-cut", "cross-poison",
    "spacial-rend", "attack-order", "air-cutter", "aeroblast", "frost-breath",
    "storm-throw", "surging-strikes", "wicked-blow"
}

# Abilities that boost crit chance
CRIT_BOOST_ABILITIES = {
    "super-luck": 1,  # +1 stage
    "sniper": 0,  # doesn't boost chance, just damage (handled elsewhere)
}

# Items that boost crit chance
CRIT_BOOST_ITEMS = {
    "scope-lens": 1,
    "razor-claw": 1,
    "lucky-punch": 2,  # Chansey only
    "stick": 2,  # Farfetch'd only
    "leek": 2,  # Farfetch'd/Sirfetch'd only
}

def calculate_crit_chance(move_name: str, ability: Optional[str], item: Optional[str], 
                         species: str, *, focus_stage: int = 0, generation: int = 9) -> float:
    """
    Calculate critical hit chance based on move, ability, item, and status.
    Returns a probability from 0.0 to 1.0.
    
    Crit stages:
    Stage 0: 1/24 (~4.17%)
    Stage 1: 1/8 (12.5%)
    Stage 2: 1/2 (50%)
    Stage 3+: 100%
    """
    stage = 0
    
    # Move boosts
    move_norm = move_name.lower().replace(" ", "-")
    if move_norm in HIGH_CRIT_MOVES:
        stage += 1
    if move_norm in {"sky-attack"}:  # Extra high crit
        stage += 1
    
    # Ability boosts
    if ability:
        ability_norm = ability.lower().replace(" ", "-").replace("_", "-")
        stage += CRIT_BOOST_ABILITIES.get(ability_norm, 0)
    
    # Item boosts
    if item:
        item_norm = item.lower().replace(" ", "-").replace("_", "-")
        item_boost = CRIT_BOOST_ITEMS.get(item_norm, 0)
        
        # Check species-specific items
        if item_norm == "lucky-punch" and "chansey" in species.lower():
            stage += item_boost
        elif item_norm in {"stick", "leek"}:
            # Leek works for Farfetch'd, Farfetch'd-Galar, and Sirfetch'd
            species_lower = species.lower()
            if "farfetch" in species_lower or "sirfetch" in species_lower:
                stage += item_boost
        elif item_norm in {"scope-lens", "razor-claw"}:
            stage += item_boost
    
    # Focused Energy / Dire Hit
    if focus_stage:
        stage += focus_stage
    
    # Convert stage to probability
    if stage >= 3:
        prob = 1.0
    elif stage == 2:
        prob = 0.5
    elif stage == 1:
        prob = 0.125
    else:
        prob = 1.0 / 24.0

    return prob

# ===================== ACCURACY/EVASION CALCULATION =====================

def calculate_accuracy(
    base_accuracy: int,
    attacker_accuracy_stage: int,
    target_evasion_stage: int,
    field_effects: FieldEffects,
    attacker_ability: Optional[str] = None,
    target_ability: Optional[str] = None,
    move_name: Optional[str] = None,
    target: Optional[Any] = None
) -> float:
    """
    Calculate final accuracy for a move.
    
    Args:
        base_accuracy: Move's base accuracy (0-100, or 0 for never-miss moves)
        attacker_accuracy_stage: Attacker's accuracy stage (-6 to +6)
        target_evasion_stage: Target's evasion stage (-6 to +6)
        field_effects: Field effects (for Gravity)
        attacker_ability: Attacker's ability (for No Guard, Compound Eyes, etc.)
        target_ability: Target's ability (for Sand Veil, Snow Cloak, Tangled Feet, etc.)
    
    Returns:
        Final accuracy as a decimal (0.0 to 1.0+)
    """
    # Never-miss moves
    if base_accuracy == 0:
        return 1.0
    
    # No Guard / Deadlock makes all moves hit
    if attacker_ability:
        ability_norm = attacker_ability.lower().replace(" ", "-").replace("_", "-")
        if ability_norm in ["no-guard", "deadlock"]:
            return 1.0
    if target_ability:
        ability_norm = target_ability.lower().replace(" ", "-").replace("_", "-")
        if ability_norm in ["no-guard", "deadlock"]:
            return 1.0
    
    # Start with base accuracy
    accuracy = base_accuracy / 100.0 if base_accuracy > 0 else 1.0
    
    # Mind's Eye / Keen Eye Gen 7+: Ignore target's evasion boosts
    if attacker_ability:
        from .abilities import normalize_ability_name, get_ability_effect
        from .generation import get_generation
        
        ability_norm = normalize_ability_name(attacker_ability)
        ability_data = get_ability_effect(ability_norm)
        
        if ability_data.get("ignores_evasion"):
            generation = get_generation(field_effects=field_effects)
            
            # Keen Eye: Gen 7+ only
            # Mind's Eye: All gens (9+)
            is_minds_eye = (ability_norm == "minds-eye")
            is_keen_eye = (ability_norm == "keen-eye")
            
            if is_minds_eye or (is_keen_eye and generation >= 7):
                target_evasion_stage = 0
    
    # Foresight: Ignore target's evasion stat stages (generation-specific)
    if target and hasattr(target, '_foresight_evasion_ignored') and target._foresight_evasion_ignored:
        from .generation import get_generation
        gen_foresight = get_generation(field_effects=field_effects)
        if gen_foresight == 4:
            # Gen IV: Only ignore if evasion > 0 (already checked when setting flag)
            if target.stages.get("evasion", 0) > 0:
                target_evasion_stage = 0
        else:
            # Gen III, V+: Always ignore evasion changes
            target_evasion_stage = 0
    
    # Foresight Gen II: If user's accuracy < target's evasion, both treated as 0
    if target and hasattr(target, '_foresight_acc_ev_balanced') and target._foresight_acc_ev_balanced:
        attacker_accuracy_stage = 0
        target_evasion_stage = 0
    
    # Apply accuracy stage multiplier
    # Stage multipliers: -6=3/9, -5=3/8, -4=3/7, -3=3/6, -2=3/5, -1=3/4, 0=1, +1=4/3, +2=5/3, +3=6/3, +4=7/3, +5=8/3, +6=9/3
    acc_stage_mult = {
        -6: 3/9, -5: 3/8, -4: 3/7, -3: 3/6, -2: 3/5, -1: 3/4,
        0: 1.0,
        1: 4/3, 2: 5/3, 3: 6/3, 4: 7/3, 5: 8/3, 6: 9/3
    }
    
    # Net stage is accuracy - evasion
    net_stage = attacker_accuracy_stage - target_evasion_stage
    net_stage = max(-6, min(6, net_stage))
    
    accuracy *= acc_stage_mult[net_stage]
    
    # Gravity boosts accuracy by 5/3
    if field_effects.gravity:
        accuracy *= 5/3
    
    # Compound Eyes boosts accuracy by 5325/4096 (≈1.3x), Gen 5+
    # Does not affect OHKO moves (Fissure, Horn Drill, Guillotine, Sheer Cold)
    if attacker_ability:
        ability_norm = attacker_ability.lower().replace(" ", "-").replace("_", "-")
        if ability_norm == "compound-eyes" and move_name:
            move_normalized = move_name.lower().replace(" ", "-")
            ohko_moves = {"fissure", "horn-drill", "guillotine", "sheer-cold"}
            if move_normalized not in ohko_moves:
                accuracy *= 5325 / 4096  # Exact Gen 5+ multiplier
        elif ability_norm == "hustle":  # Hustle lowers accuracy of physical moves
            # (This should be checked per-move category in actual implementation)
            pass
    
    # Victory Star boosts accuracy by 1.1x
    if attacker_ability:
        ability_norm = attacker_ability.lower().replace(" ", "-").replace("_", "-")
        if ability_norm == "victory-star":
            accuracy *= 1.1
    
    # Target abilities that boost evasion
    if target_ability:
        ability_norm = target_ability.lower().replace(" ", "-").replace("_", "-")
        # Sand Veil in sandstorm, Snow Cloak in snow
        if ability_norm == "sand-veil" and field_effects.weather in {"sand", "sandstorm"}:
            accuracy *= 0.8
        elif ability_norm == "snow-cloak" and field_effects.weather in {"snow", "hail"}:
            accuracy *= 0.8
        elif ability_norm == "tangled-feet" and target:
            # Tangled Feet: Halves accuracy when target is confused (Gen 4+)
            if getattr(target, 'confused', False):
                accuracy *= 0.5
    
    return min(1.0, accuracy)

def does_move_hit(
    base_accuracy: int,
    attacker_accuracy_stage: int,
    target_evasion_stage: int,
    field_effects: FieldEffects,
    attacker_ability: Optional[str] = None,
    target_ability: Optional[str] = None,
    move_name: Optional[str] = None,
    target: Optional[Any] = None
) -> Tuple[bool, float]:
    """
    Determine if a move hits.
    Returns: (hit: bool, accuracy_used: float)
    """
    accuracy = calculate_accuracy(
        base_accuracy,
        attacker_accuracy_stage,
        target_evasion_stage,
        field_effects,
        attacker_ability,
        target_ability,
        move_name=move_name,
        target=target
    )
    
    roll = random.random()
    return (roll < accuracy, accuracy)

# ===================== WEATHER & TERRAIN EFFECTS ON MOVES =====================

def apply_weather_move_effects(move_name: str, weather: Optional[str], 
                               move_data: Dict[str, Any],
                               special_weather: Optional[str] = None) -> Dict[str, Any]:
    """
    Modify move properties based on weather.
    Returns modified move_data dict.
    """
    move_norm = move_name.lower().replace(" ", "-")
    modified = move_data.copy()
    
    if special_weather == "heavy-rain":
        weather = "rain"
    elif special_weather == "harsh-sunlight":
        weather = "sun"
    
    if weather == "rain":
        # Thunder/Hurricane never miss in rain
        if move_norm in {"thunder", "hurricane"}:
            modified["accuracy"] = 0  # 0 = never miss
        
        # Water moves boosted by 1.5x
        if move_data.get("type", "").lower() == "water":
            modified["power"] = int((move_data.get("power", 0) or 0) * 1.5)
        
        # Fire moves halved
        if move_data.get("type", "").lower() == "fire":
            modified["power"] = int((move_data.get("power", 0) or 0) * 0.5)
        
        # Solar Beam halved power
        if move_norm in {"solar-beam", "solar-blade"}:
            modified["power"] = int((move_data.get("power", 0) or 0) * 0.5)
    
    elif weather == "sun":
        # Fire moves boosted by 1.5x
        if move_data.get("type", "").lower() == "fire":
            modified["power"] = int((move_data.get("power", 0) or 0) * 1.5)
        
        # Water moves halved
        if move_data.get("type", "").lower() == "water":
            modified["power"] = int((move_data.get("power", 0) or 0) * 0.5)
        
        # Thunder/Hurricane accuracy lowered to 50%
        if move_norm in {"thunder", "hurricane"}:
            modified["accuracy"] = 50
    
    elif weather == "snow":
        # Blizzard never misses in snow
        if move_norm == "blizzard":
            modified["accuracy"] = 0  # 0 = never miss
    
    return modified

def apply_terrain_move_effects(move_type: str, terrain: Optional[str],
                               is_grounded: bool, power: int,
                               *, generation: int = 9) -> int:
    """
    Apply terrain damage boosts to moves.
    Returns modified power.
    """
    if not is_grounded or not terrain:
        return power
    
    boost = 1.0
    move_type_lower = move_type.lower()
    
    if terrain == "electric" and move_type_lower == "electric":
        # Gen 7: 50% boost (1.5x), Gen 8+: 30% boost (1.3x)
        boost = 1.5 if generation <= 7 else 1.3
    elif terrain == "grassy" and move_type_lower == "grass":
        # Gen 7: 50% boost (1.5x), Gen 8+: 30% boost (1.3x)
        boost = 1.5 if generation <= 7 else 1.3
    elif terrain == "psychic" and move_type_lower == "psychic":
        # Gen 7: 50% boost (1.5x), Gen 8+: 30% boost (1.3x)
        boost = 1.5 if generation <= 7 else 1.3
    elif terrain == "misty" and move_type_lower == "dragon":
        boost = 0.5
    
    return int(power * boost)


def apply_special_weather(field_effects: FieldEffects, special_weather: str,
                          *, ability: Optional[str] = None,
                          source_id: Optional[int] = None, battle_state: Any = None) -> Tuple[bool, Optional[str]]:
    """Apply a special weather state such as heavy rain or harsh sunlight.

    Returns (changed, message) where changed is True if the special weather changed,
    and message is an error message if weather was blocked (e.g., by Nullscape).
    """
    if not field_effects:
        return False, None

    # === NULLSCAPE: Blocks all weather (acts like primal weather) ===
    from .engine import _get_nullscape_type
    nullscape_type = _get_nullscape_type(battle_state=battle_state)
    if nullscape_type:
        # Nullscape is active - block weather
        return False, "Normal weather does not exist in this desolate place."

    previous = field_effects.special_weather
    field_effects.special_weather = special_weather
    field_effects.weather_lock = ability
    field_effects.weather_lock_owner = source_id
    field_effects.weather_turns = 0

    if special_weather == "heavy-rain":
        field_effects.weather = "rain"
        field_effects.heavy_rain = True
        field_effects.harsh_sunlight = False
    elif special_weather == "harsh-sunlight":
        field_effects.weather = "sun"
        field_effects.harsh_sunlight = True
        field_effects.heavy_rain = False
    elif special_weather == "strong-winds":
        # Delta Stream unique weather type
        field_effects.weather = "strong-winds"
        field_effects.heavy_rain = False
        field_effects.harsh_sunlight = False

    # Special weathers suppress standard duration logic
    return previous != special_weather, None


def clear_special_weather(field_effects: FieldEffects) -> Optional[str]:
    """Clear any special weather that is currently active.

    Returns the previous special weather identifier if one was cleared.
    """
    if not field_effects or not field_effects.special_weather:
        return None

    previous = field_effects.special_weather
    special_to_base = {
        "heavy-rain": "rain",
        "harsh-sunlight": "sun",
        "strong-winds": "strong-winds"
    }

    # Reset special weather flags & locks
    field_effects.special_weather = None
    field_effects.heavy_rain = False
    field_effects.harsh_sunlight = False
    field_effects.weather_lock = None
    field_effects.weather_lock_owner = None

    base_weather = special_to_base.get(previous)
    if field_effects.weather == base_weather:
        field_effects.weather = None
    field_effects.weather_turns = 0

    return previous


