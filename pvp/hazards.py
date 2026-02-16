"""
Entry Hazards System (Generation-Specific Logic)
Stealth Rock, Spikes, Toxic Spikes, Sticky Web

Weather uses Gen 9 logic for all generations (infinite duration without item).
"""
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass, field


@dataclass
class HazardState:
    """Tracks hazards on each side of the field"""
    stealth_rock: bool = False
    spikes: int = 0  # 0-3 layers
    toxic_spikes: int = 0  # 0-2 layers
    sticky_web: bool = False
    steel_spikes: bool = False  # G-Max Steelsurge
    generation: int = 9  # Track which generation rules to use
    
    def clear_all(self):
        """Clear all hazards (Rapid Spin, Defog, Court Change)"""
        self.stealth_rock = False
        self.spikes = 0
        self.toxic_spikes = 0
        self.sticky_web = False
        self.steel_spikes = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "stealth_rock": self.stealth_rock,
            "spikes": self.spikes,
            "toxic_spikes": self.toxic_spikes,
            "sticky_web": self.sticky_web,
            "steel_spikes": self.steel_spikes
        }


def apply_entry_hazards(mon: Any, hazards: HazardState, is_grounded: bool = True, field_effects: Any = None, battle_state: Any = None) -> List[str]:
    """
    Apply entry hazards when a Pokémon switches in.
    Returns list of messages describing damage/effects.
    
    Generation-Specific Logic:
    
    STEALTH ROCK:
    - Gen 4+: Type-based damage (0.5x, 1x, 2x, 4x)
    - Gen 1-3: Not available
    
    SPIKES:
    - Gen 2: 1/8 max HP (1 layer only)
    - Gen 3+: 1/8, 1/6, 1/4 max HP (1-3 layers)
    - Gen 1: Not available
    
    TOXIC SPIKES:
    - Gen 4+: Poison (1 layer) or Badly Poison (2 layers)
    - Gen 1-3: Not available
    
    STICKY WEB:
    - Gen 6+: Lower Speed by 1 stage
    - Gen 1-5: Not available
    
    WEATHER (All Gens use Gen 9 Logic):
    - Infinite duration without item
    - Can be overwritten by other weather
    - Stopped by Cloud Nine/Air Lock abilities
    """
    messages = []
    gen = hazards.generation
    
    # === HEAVY-DUTY BOOTS: Ignore all entry hazards ===
    from .items import get_item_effect, normalize_item_name
    if mon.item:
        item_data = get_item_effect(normalize_item_name(mon.item))
        if item_data.get("hazard_immunity"):
            messages.append(f"{mon.species}'s **Heavy-Duty Boots** protected it from hazards!")
            return messages
    
    # Check if Pokémon is grounded (not Flying type, no Levitate, no Air Balloon, no Magnet Rise)
    from .abilities import normalize_ability_name, get_ability_effect
    from .advanced_mechanics import FieldEffects
    
    ability = normalize_ability_name(mon.ability or "")
    ability_data = get_ability_effect(ability)
    
    # Flying types and Levitate ignore ground-based hazards
    mon_types = [t.strip().title() if t else None for t in mon.types]
    is_flying = "Flying" in mon_types
    has_levitate = ability == "levitate"
    has_air_balloon = getattr(mon, 'item', None) and normalize_item_name(mon.item) == "air-balloon"
    
    # Check Magnet Rise (makes ungrounded)
    has_magnet_rise = hasattr(mon, '_magnet_rise_active') and getattr(mon, '_magnet_rise_active', False)
    
    # Gravity grounds all Pokémon
    gravity_active = False
    if field_effects and isinstance(field_effects, FieldEffects):
        gravity_active = getattr(field_effects, 'gravity', False)
    
    # Iron Ball grounds Flying/Levitate (Gen IV+)
    has_iron_ball = False
    if mon.item:
        item_norm = normalize_item_name(mon.item)
        if item_norm == "iron-ball":
            has_iron_ball = True
    
    # Earthbound: Grounds all Flying types and Levitate Pokémon on the field
    has_earthbound = False
    # Check if the mon itself has Earthbound
    if ability_data.get("grounds_self_and_opponent"):
        has_earthbound = True
    # Check if any other Pokémon on the field (active or in teams) has Earthbound
    elif battle_state:
        all_mons_eb_hazards = []
        # Check active Pokémon on field
        if hasattr(battle_state, '_active'):
            try:
                p1_active_mon = battle_state._active(battle_state.p1_id) if hasattr(battle_state, 'p1_id') else None
                p2_active_mon = battle_state._active(battle_state.p2_id) if hasattr(battle_state, 'p2_id') else None
                if p1_active_mon and p1_active_mon.hp > 0:
                    all_mons_eb_hazards.append(p1_active_mon)
                if p2_active_mon and p2_active_mon.hp > 0:
                    all_mons_eb_hazards.append(p2_active_mon)
            except:
                pass
        # Also check all team members (in case active isn't available)
        if hasattr(battle_state, 'p1_team'):
            all_mons_eb_hazards.extend([m for m in battle_state.p1_team if m and m.hp > 0 and m not in all_mons_eb_hazards])
        if hasattr(battle_state, 'p2_team'):
            all_mons_eb_hazards.extend([m for m in battle_state.p2_team if m and m.hp > 0 and m not in all_mons_eb_hazards])
        
        for other_mon in all_mons_eb_hazards:
            if other_mon and other_mon != mon and other_mon.ability:
                other_ab_norm = normalize_ability_name(other_mon.ability)
                other_ab_data = get_ability_effect(other_ab_norm)
                if other_ab_data.get("grounds_self_and_opponent"):
                    has_earthbound = True
                    break
    
    # Determine if grounded (considering all factors)
    if is_flying or has_levitate or has_air_balloon:
        # Flying/Levitate/Air Balloon are ungrounded by default
        is_grounded = False
        # But Gravity, Iron Ball, or Earthbound can ground them
        if gravity_active or has_iron_ball or has_earthbound:
            is_grounded = True
    elif has_magnet_rise:
        # Magnet Rise makes ungrounded
        is_grounded = False
        # But Gravity or Earthbound can ground even with Magnet Rise
        if gravity_active or has_earthbound:
            is_grounded = True
    # else: is_grounded remains as passed (True by default)
    # Note: Earthbound also grounds the user itself, so if mon has Earthbound, it's always grounded
    if ability_data.get("grounds_self_and_opponent"):
        is_grounded = True
    
    # Magic Guard ignores all indirect damage
    magic_guard = ability == "magic-guard"
    
    # ========== STEALTH ROCK (GEN 4+) ==========
    if gen >= 4 and hazards.stealth_rock and not magic_guard:
        # Calculate type effectiveness
        rock_effectiveness = _get_stealth_rock_multiplier(mon_types)
        
        if rock_effectiveness > 0:
            # Ensure max_hp is valid (fallback to hp if max_hp not set)
            max_hp = getattr(mon, 'max_hp', None) or getattr(mon, 'hp', None) or 100
            if max_hp <= 0:
                max_hp = 100  # Fallback to prevent issues
            
            damage = int(max_hp * rock_effectiveness)
            damage = max(1, damage)  # Minimum 1 HP damage
            old_hp = mon.hp
            mon.hp = max(0, mon.hp - damage)
            
            messages.append(f"**Stealth Rock** hit {mon.species}!\n└ **{damage}** damage")
    
    # ========== SPIKES (GEN 2+, GROUNDED ONLY) ==========
    if gen >= 2 and hazards.spikes > 0 and is_grounded and not magic_guard:
        # Gen 2: 1/8 max HP (1 layer only)
        # Gen 3+: 1/8, 1/6, 1/4 for 1, 2, 3 layers
        if gen == 2:
            damage_ratio = 0.125
        else:
            damage_ratios = {1: 0.125, 2: 0.1667, 3: 0.25}
            damage_ratio = damage_ratios.get(hazards.spikes, 0.125)
        
        damage = max(1, int(mon.max_hp * damage_ratio))
        old_hp = mon.hp
        mon.hp = max(0, mon.hp - damage)
        
        layer_text = f"{hazards.spikes} layer{'s' if hazards.spikes > 1 else ''}"
        messages.append(f"**Spikes** damaged {mon.species}! ({layer_text})\n└ **{damage}** damage")
    
    # ========== TOXIC SPIKES (GEN 4+, GROUNDED ONLY) ==========
    if gen >= 4 and hazards.toxic_spikes > 0:
        # Use the is_grounded value already calculated above (includes all factors)
        if not is_grounded:
            return messages  # Not grounded, skip Toxic Spikes
        
        # Poison types absorb Toxic Spikes (must be grounded)
        if "Poison" in mon_types and is_grounded:
            # Gen V-VII: Air Balloon prevents absorption unless Gravity
            can_absorb = True
            if gen >= 5:
                if has_air_balloon and not gravity_active:
                        can_absorb = False
            
            if can_absorb:
                hazards.toxic_spikes = 0
                messages.append(f"{mon.species} absorbed the **Toxic Spikes**!")
                return messages
        
        # Steel types are immune to poison
        # Flying types are immune (unless grounded by Iron Ball/Gravity)
        if "Steel" not in mon_types and is_grounded:
            # Immunity ability check
            ability_data = get_ability_effect(ability)
            immune_to_poison = False
            
            # Immunity ability (Gen IV: Immunity only)
            if "status_immunity" in ability_data:
                immunity_list = ability_data["status_immunity"]
                if immunity_list == "all" or "psn" in immunity_list or "tox" in immunity_list:
                    immune_to_poison = True
            
            # Gen IV: Leaf Guard (during intense sunlight) also prevents
            if gen == 4:
                if ability == "leaf-guard":
                    if field_effects and isinstance(field_effects, FieldEffects):
                        if getattr(field_effects, 'weather', None) == "sun":
                            immune_to_poison = True
            
            # Gen V+: Comatose prevents poisoning
            if gen >= 5:
                if ability == "comatose":
                    immune_to_poison = True
            
            # Magic Guard: Gen V+ prevents poison damage but not status
            if gen >= 5 and ability == "magic-guard":
                # Magic Guard prevents damage but NOT the status effect itself
                # But we should still apply the status for display purposes
                pass
            
            if not immune_to_poison and not mon.status:
                if hazards.toxic_spikes == 1:
                    mon.status = "psn"
                    messages.append(f"{mon.species} was **poisoned** by Toxic Spikes!")
                else:  # 2 layers
                    mon.status = "tox"
                    mon.toxic_counter = 0
                    messages.append(f"{mon.species} was **badly poisoned** by Toxic Spikes!")
            elif immune_to_poison:
                ability_name = (mon.ability or ability).replace("-", " ").title()
                messages.append(f"{mon.species}'s {ability_name} prevented the poison!")
    
    # ========== STICKY WEB (GEN 6+, GROUNDED ONLY) ==========
    if gen >= 6 and hazards.sticky_web and is_grounded:
        # Lower Speed by 1 stage (unless Clear Body, etc.)
        ability_data = get_ability_effect(ability)
        protected_from_stat_drops = False
        
        if ability_data.get("stat_drop_immunity"):
            stat_immunity = ability_data["stat_drop_immunity"]
            if stat_immunity is True or "spe" in stat_immunity:
                protected_from_stat_drops = True
                ability_name = (mon.ability or ability).replace("-", " ").title()
                messages.append(f"{mon.species}'s {ability_name} prevents stat reduction!")
        
        if not protected_from_stat_drops:
            old_stage = mon.stages.get("spe", 0)
            mon.stages["spe"] = max(-6, old_stage - 1)
            if mon.stages["spe"] < old_stage:
                messages.append(f"**Sticky Web** lowered {mon.species}'s Speed!")
    
    # ========== STEEL SPIKES (G-MAX STEELSURGE, GEN 8+) ==========
    if gen >= 8 and hazards.steel_spikes and not magic_guard:
        # Calculate Steel type effectiveness against the target's types
        multiplier = _get_steel_spikes_multiplier(mon_types)
        
        if multiplier > 0:
            # Base damage is 12.5% (0.125) of max HP at 1x effectiveness
            # Damage scales with type effectiveness: 0.25x → 3.125%, 0.5x → 6.25%, 1x → 12.5%, 2x → 25%, 4x → 50%
            damage_ratio = multiplier * 0.125
            damage = max(1, int(mon.max_hp * damage_ratio))  # Minimum 1 HP damage
            old_hp = mon.hp
            mon.hp = max(0, mon.hp - damage)
            
            messages.append(f"**Steel Spikes** hit {mon.species}!\n└ **{damage}** damage")
    
    return messages


def _get_steel_spikes_multiplier(types: List[Optional[str]]) -> float:
    """
    Calculate Steel Spikes damage multiplier based on Steel type effectiveness.
    Returns type effectiveness multiplier.
    
    Uses the engine's TYPE_MULT for accurate type effectiveness calculation.
    """
    # Import TYPE_MULT from engine to use the actual type chart
    from .engine import TYPE_MULT
    
    # Calculate Steel type effectiveness against the target's types
    multiplier = 1.0
    for type_name in types:
        if type_name:
            # Normalize type name to title case to match TYPE_MULT keys
            type_name_normalized = type_name.strip().title()
            # Get effectiveness: Steel attacking the target type
            effectiveness = TYPE_MULT.get(("Steel", type_name_normalized), 1.0)
            multiplier *= effectiveness
    
    return multiplier


def _get_stealth_rock_multiplier(types: List[Optional[str]]) -> float:
    """
    Calculate Stealth Rock damage multiplier based on Rock type effectiveness.
    Returns fraction of max HP to take as damage.
    
    Base: 1/8 (0.125)
    0.25x → 1/32 (0.03125)
    0.5x  → 1/16 (0.0625)
    1x    → 1/8  (0.125)
    2x    → 1/4  (0.25)
    4x    → 1/2  (0.5)
    
    Uses the engine's TYPE_MULT for accurate type effectiveness calculation.
    """
    # Import TYPE_MULT from engine to use the actual type chart
    from .engine import TYPE_MULT
    
    # Calculate Rock type effectiveness against the target's types
    multiplier = 1.0
    has_valid_type = False
    for type_name in types:
        if type_name:
            has_valid_type = True
            try:
                # Normalize type name to title case to match TYPE_MULT keys
                type_name_normalized = type_name.strip().title()
                # Get effectiveness: Rock attacking the target type
                effectiveness = TYPE_MULT.get(("Rock", type_name_normalized), 1.0)
                multiplier *= effectiveness
            except (AttributeError, TypeError, KeyError):
                # If type lookup fails, assume 1x effectiveness
                pass
    
    # If no valid types found, default to 1x effectiveness (1/8 damage)
    if not has_valid_type:
        multiplier = 1.0
    
    # Convert type effectiveness multiplier to damage fraction
    # Base damage is 1/8 (0.125) of max HP at 1x effectiveness
    # 4x → 0.5, 2x → 0.25, 1x → 0.125, 0.5x → 0.0625, 0.25x → 0.03125
    return multiplier * 0.125


def set_hazard(hazards: HazardState, hazard_type: str, generation: int) -> Tuple[bool, str]:
    """
    Set a hazard. Returns (success, message).
    
    Generation-Specific Limits:
    - Stealth Rock: Gen 4+ (Single layer)
    - Spikes: Gen 2 (1 layer), Gen 3+ (Up to 3 layers)
    - Toxic Spikes: Gen 4+ (Up to 2 layers)
    - Sticky Web: Gen 6+ (Single layer)
    """
    gen = generation
    
    if hazard_type == "stealth-rock":
        if gen < 4:
            return False, "Stealth Rock is not available in this generation!"
        if hazards.stealth_rock:
            return False, "Stealth Rock is already set!"
        hazards.stealth_rock = True
        return True, "**Stealth Rock** scattered sharp rocks around the opposing team!"
    
    elif hazard_type == "spikes":
        if gen < 2:
            return False, "Spikes are not available in this generation!"
        
        max_layers = 1 if gen == 2 else 3
        if hazards.spikes >= max_layers:
            return False, f"Spikes are maxed out ({max_layers} layer{'s' if max_layers > 1 else ''})!"
        
        hazards.spikes += 1
        if gen == 2:
            return True, "**Spikes** scattered around the opposing team!"
        else:
            return True, f"**Spikes** scattered around the opposing team! (Layer {hazards.spikes}/3)"
    
    elif hazard_type == "toxic-spikes":
        if gen < 4:
            return False, "Toxic Spikes are not available in this generation!"
        if hazards.toxic_spikes >= 2:
            return False, "Toxic Spikes are maxed out (2 layers)!"
        hazards.toxic_spikes += 1
        return True, f"**Toxic Spikes** scattered around the opposing team! (Layer {hazards.toxic_spikes}/2)"
    
    elif hazard_type == "sticky-web":
        if gen < 6:
            return False, "Sticky Web is not available in this generation!"
        if hazards.sticky_web:
            return False, "Sticky Web is already set!"
        hazards.sticky_web = True
        return True, "**Sticky Web** spread across the opposing team!"
    
    return False, f"Unknown hazard type: {hazard_type}"


def clear_hazards(hazards: HazardState, move_name: str) -> str:
    """
    Clear hazards with Rapid Spin or Defog.
    Returns message describing what was cleared.
    """
    had_hazards = hazards.stealth_rock or hazards.spikes > 0 or hazards.toxic_spikes > 0 or hazards.sticky_web or hazards.steel_spikes
    
    if not had_hazards:
        return ""
    
    cleared = []
    if hazards.stealth_rock:
        cleared.append("Stealth Rock")
    if hazards.spikes > 0:
        cleared.append(f"Spikes (x{hazards.spikes})")
    if hazards.toxic_spikes > 0:
        cleared.append(f"Toxic Spikes (x{hazards.toxic_spikes})")
    if hazards.sticky_web:
        cleared.append("Sticky Web")
    if hazards.steel_spikes:
        cleared.append("Steel Spikes")
    
    hazards.clear_all()
    
    if move_name.lower() == "rapid-spin":
        return f"**Rapid Spin** cleared: {', '.join(cleared)}!"
    elif move_name.lower() == "defog":
        return f"**Defog** cleared: {', '.join(cleared)}!"
    else:
        return f"Hazards cleared: {', '.join(cleared)}!"


def get_hazard_summary(hazards: HazardState) -> str:
    """Get a summary of active hazards for display."""
    active = []
    if hazards.stealth_rock:
        active.append("🪨 Stealth Rock")
    if hazards.spikes > 0:
        active.append(f"📍 Spikes x{hazards.spikes}")
    if hazards.toxic_spikes > 0:
        active.append(f"☠️ Toxic Spikes x{hazards.toxic_spikes}")
    if hazards.sticky_web:
        active.append("🕸️ Sticky Web")
    if hazards.steel_spikes:
        active.append("⚙️ Steel Spikes")
    
    if not active:
        return "No hazards"
    return " | ".join(active)
