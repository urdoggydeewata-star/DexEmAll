"""
Binding Move System
Handles binding/trapping moves with generation-specific mechanics.
"""

from typing import Tuple, Optional, List, Any, Dict
import random


def apply_clamp(attacker: Any, defender: Any, move_name: str, field_effects: Any = None, 
                battle_state: Any = None) -> Tuple[bool, List[str], Optional[Dict[str, Any]]]:
    """
    Apply Clamp with full generation-specific mechanics.
    
    Returns: (success, messages, trap_data)
    trap_data contains: {
        "partially_trapped": bool,
        "partial_trap_turns": int,
        "partial_trap_damage": float,
        "clamp_gen": int,
        "clamp_source": str
    }
    
    Generation differences:
    - Gen I: Prevents target from attacking, PP rollover bugs, Defense halving
    - Gen II: 1/16 HP per turn for 2-5 turns, traps target
    - Gen III-IV: Same as Gen II, but Grip Claw makes it 5 turns
    - Gen V: 1/16 HP per turn for 4-5 turns, Grip Claw makes it 7 turns, Binding Band increases to 1/8
    - Gen VI+: 1/8 HP per turn, Binding Band increases to 1/6, Ghost types can't be trapped
    - Gen VIII+: Cannot be selected
    """
    from .generation import get_generation
    generation = get_generation(field_effects=field_effects, battle_state=battle_state)
    
    messages = []
    
    # Gen VIII+: Cannot be selected
    if generation >= 8:
        return False, ["Clamp cannot be selected in this generation!"], None
    
    # Gen VI+: Ghost types cannot be trapped
    if generation >= 6:
        defender_types = [t.strip().title() if t else None for t in getattr(defender, 'types', (None, None))]
        if "Ghost" in defender_types:
            return False, [f"{defender.species} cannot be trapped by Clamp!"], None
    
    # Check for Shed Shell (allows switching even when trapped)
    if hasattr(defender, 'item') and defender.item:
        from .items import normalize_item_name, get_item_effect
        def_item = normalize_item_name(defender.item)
        def_item_data = get_item_effect(def_item)
        if def_item_data.get("allows_switch_when_trapped"):
            # Shed Shell allows switching, but trapping still applies
            pass  # Continue with trapping
    
    # Determine base duration
    if generation == 1:
        # Gen I: 2-5 turns (random)
        base_duration = (2, 5)
    elif generation == 2:
        # Gen II: 2-5 turns
        base_duration = (2, 5)
    elif generation >= 3:
        # Gen III+: 4-5 turns
        base_duration = (4, 5)
    else:
        base_duration = (4, 5)  # Default fallback
    
    # Check for Grip Claw (extends duration)
    duration_multiplier = 1
    grip_claw_active = False
    if hasattr(attacker, 'item') and attacker.item:
        from .items import normalize_item_name, get_item_effect
        from .engine import item_is_active
        if item_is_active(attacker):
            att_item = normalize_item_name(attacker.item)
            att_item_data = get_item_effect(att_item)
            if att_item_data.get("extends_binding_moves"):
                grip_claw_active = True
                gen_specific_gc = att_item_data.get("gen_specific", {})
                if generation >= 4:
                    if "4" in gen_specific_gc and generation == 4:
                        # Gen 4: Always 5 turns
                        base_duration = (5, 5)
                    elif "5+" in gen_specific_gc and generation >= 5:
                        # Gen 5+: Always 7 turns
                        base_duration = (7, 7)
    
    # Roll duration if not fixed by Grip Claw
    if base_duration[0] == base_duration[1]:
        duration = base_duration[0]
    else:
        duration = random.randint(base_duration[0], base_duration[1])
    
    # Determine damage fraction
    if generation <= 5:
        # Gen I-V: 1/16 HP per turn
        damage_fraction = 1/16
    else:
        # Gen VI+: 1/8 HP per turn
        damage_fraction = 1/8
    
    # Check for Binding Band (increases trap damage)
    binding_band_active = False
    if hasattr(attacker, 'item') and attacker.item:
        from .items import normalize_item_name, get_item_effect
        from .engine import item_is_active
        if item_is_active(attacker):
            att_item_bb = normalize_item_name(attacker.item)
            att_item_data_bb = get_item_effect(att_item_bb)
            if att_item_data_bb.get("boosts_binding_moves"):
                binding_band_active = True
                gen_specific_bb = att_item_data_bb.get("gen_specific", {})
                if generation >= 5:
                    if "5" in gen_specific_bb and generation == 5:
                        # Gen 5: 1/8 instead of 1/16
                        damage_fraction = 1/8
                    elif "6+" in gen_specific_bb and generation >= 6:
                        # Gen 6+: 1/6 instead of 1/8
                        if damage_fraction == 1/8:  # Base is already 1/8 in Gen VI+
                            damage_fraction = 1/6
    
    # Gen I special: Prevents target from attacking
    # (This would need to be handled in move execution logic)
    gen_i_prevents_attack = (generation == 1)
    
    # Apply trapping
    defender.partially_trapped = True
    defender.partial_trap_turns = duration
    defender.partial_trap_damage = damage_fraction
    defender.trapped = True  # Also prevents switching
    defender.trap_source = attacker.species
    
    # Store Clamp-specific data
    defender._clamp_data = {
        "generation": generation,
        "prevents_attack": gen_i_prevents_attack,
        "binding_band": binding_band_active,
        "grip_claw": grip_claw_active
    }
    
    # Gen I: Message is different
    if generation == 1:
        messages.append(f"{defender.species} was CLAMPED by {attacker.species}!")
    else:
        messages.append(f"{attacker.species} CLAMPED {defender.species}!")
    
    # Gen II+: Additional message about trapping
    if generation >= 2:
        messages.append(f"{defender.species} can no longer escape!")
    
    trap_data = {
        "partially_trapped": True,
        "partial_trap_turns": duration,
        "partial_trap_damage": damage_fraction,
        "clamp_gen": generation,
        "clamp_source": attacker.species
    }
    
    return True, messages, trap_data


def check_clamp_attack_prevention(target: Any) -> Tuple[bool, Optional[str]]:
    """
    Check if target is prevented from attacking due to Gen I Clamp.
    Returns: (prevented, message)
    """
    if hasattr(target, '_clamp_data') and target._clamp_data:
        clamp_data = target._clamp_data
        if clamp_data.get("generation") == 1 and clamp_data.get("prevents_attack"):
            return True, f"{target.species} cannot attack while clamped!"
    return False, None


def apply_clamp_end_turn_damage(target: Any, field_effects: Any = None) -> Tuple[int, List[str]]:
    """
    Apply Clamp's end-of-turn damage with generation-specific mechanics.
    Returns: (damage_dealt, messages)
    """
    if not (hasattr(target, 'partially_trapped') and target.partially_trapped):
        return 0, []
    
    if not (hasattr(target, '_clamp_data') and target._clamp_data):
        # Not Clamp, use standard binding move damage
        return 0, []
    
    clamp_data = target._clamp_data
    generation = clamp_data.get("generation", 9)
    damage_fraction = getattr(target, 'partial_trap_damage', 1/8)
    
    # Gen II: Damage is 1/16
    # Gen VI+: Damage is 1/8 (or 1/6 with Binding Band)
    damage = max(1, int(target.max_hp * damage_fraction))
    target.hp = max(0, target.hp - damage)
    
    messages = []
    
    # Gen II: Message format
    if generation == 2:
        messages.append(f"{target.species} is hurt by Clamp! (-{damage} HP)")
    else:
        messages.append(f"{target.species} was CLAMPED by {clamp_data.get('clamp_source', 'the opponent')}!")
    
    messages.append(f"{target.species} is hurt by Clamp! (-{damage} HP)")
    
    # Check if target fainted
    if target.hp <= 0:
        messages.append(f"{target.species} fainted from Clamp!")
    
    return damage, messages


def apply_whirlpool(attacker: Any, defender: Any, field_effects: Any = None,
                    battle_state: Any = None) -> Tuple[bool, List[str], Optional[Dict[str, Any]]]:
    """Apply Whirlpool with generation-accurate trapping behaviour."""
    from .generation import get_generation

    generation = get_generation(field_effects=field_effects, battle_state=battle_state)
    messages: List[str] = []

    # Gen VI+: Ghost-types are immune to being trapped by Whirlpool
    if generation >= 6:
        defender_types = [t.strip().title() if t else None for t in getattr(defender, 'types', (None, None))]
        if "Ghost" in defender_types:
            return False, [f"{defender.species} slipped free of the vortex!"], None

    # Determine trap duration based on generation (Grip Claw handles in selection below)
    if generation <= 4:
        base_duration = (2, 5)
    else:
        base_duration = (4, 5)

    # Grip Claw: fixed duration depending on generation
    duration = None
    if hasattr(attacker, 'item') and attacker.item:
        from .items import normalize_item_name, get_item_effect
        from .engine import item_is_active
        if item_is_active(attacker):
            att_item = normalize_item_name(attacker.item)
            att_item_data = get_item_effect(att_item)
            if att_item_data.get("extends_binding_moves"):
                gen_specific = att_item_data.get("gen_specific", {})
                if generation == 4 and "4" in gen_specific:
                    duration = 5
                elif generation >= 5 and "5+" in gen_specific:
                    duration = 7
    if duration is None:
        import random
        duration = random.randint(*base_duration)

    # Determine residual damage fraction
    if generation >= 6:
        damage_fraction = 1 / 8
    else:
        damage_fraction = 1 / 16

    # Binding Band boost (Gen V onward increases residual damage)
    if hasattr(attacker, 'item') and attacker.item:
        from .items import normalize_item_name, get_item_effect
        from .engine import item_is_active
        if item_is_active(attacker):
            att_item = normalize_item_name(attacker.item)
            att_item_data = get_item_effect(att_item)
            if att_item_data.get("boosts_binding_moves"):
                gen_specific_bb = att_item_data.get("gen_specific", {})
                if generation == 5 and "5" in gen_specific_bb:
                    damage_fraction = 1 / 8
                elif generation >= 6 and "6+" in gen_specific_bb:
                    damage_fraction = 1 / 6

    defender.partially_trapped = True
    defender.partial_trap_turns = duration
    defender.partial_trap_damage = damage_fraction
    defender.trapped = True
    defender.trap_source = attacker.species
    defender._partial_trap_move = "whirlpool"

    if generation == 2:
        messages.append(f"{defender.species} was trapped!")
    else:
        messages.append(f"{defender.species} was trapped in the vortex!")

    messages.append(f"{defender.species} can no longer escape!")

    trap_data = {
        "partially_trapped": True,
        "partial_trap_turns": duration,
        "partial_trap_damage": damage_fraction,
        "whirlpool_gen": generation,
        "whirlpool_source": attacker.species
    }

    return True, messages, trap_data


def apply_bind(attacker: Any, defender: Any, move_name: str, field_effects: Any = None, 
               battle_state: Any = None) -> Tuple[bool, List[str], Optional[Dict[str, Any]]]:
    """
    Apply Bind with full generation-specific mechanics.
    
    Returns: (success, messages, trap_data)
    
    Generation differences:
    - Gen I: Prevents target from attacking, 2-5 turns (75% accuracy)
    - Gen II+: Traps target, deals 1/16 HP per turn for 2-5 turns (85% Gen V+, 75% Gen I-IV)
    - Gen V+: 4-5 turns, Binding Band increases to 1/8, Grip Claw makes 7 turns
    - Gen VI+: 1/8 HP per turn, Binding Band increases to 1/6
    """
    from .generation import get_generation
    generation = get_generation(field_effects=field_effects, battle_state=battle_state)
    
    messages = []
    
    # Gen VI+: Ghost types cannot be trapped
    if generation >= 6:
        defender_types = [t.strip().title() if t else None for t in getattr(defender, 'types', (None, None))]
        if "Ghost" in defender_types:
            return False, [f"{defender.species} cannot be trapped by Bind!"], None
    
    # Determine base duration
    if generation == 1:
        # Gen I: 2-5 turns
        base_duration = (2, 5)
    elif generation >= 5:
        # Gen V+: 4-5 turns
        base_duration = (4, 5)
    else:
        # Gen II-IV: 2-5 turns
        base_duration = (2, 5)
    
    # Check for Grip Claw
    duration = None
    if hasattr(attacker, 'item') and attacker.item:
        from .items import normalize_item_name, get_item_effect
        from .engine import item_is_active
        if item_is_active(attacker):
            att_item = normalize_item_name(attacker.item)
            att_item_data = get_item_effect(att_item)
            if att_item_data.get("extends_binding_moves"):
                gen_specific = att_item_data.get("gen_specific", {})
                if generation == 4 and "4" in gen_specific:
                    duration = 5
                elif generation >= 5 and "5+" in gen_specific:
                    duration = 7
    
    if duration is None:
        import random
        duration = random.randint(*base_duration)
    
    # Determine damage fraction
    if generation <= 5:
        damage_fraction = 1/16
    else:
        damage_fraction = 1/8
    
    # Check for Binding Band
    if hasattr(attacker, 'item') and attacker.item:
        from .items import normalize_item_name, get_item_effect
        from .engine import item_is_active
        if item_is_active(attacker):
            att_item_bb = normalize_item_name(attacker.item)
            att_item_data_bb = get_item_effect(att_item_bb)
            if att_item_data_bb.get("boosts_binding_moves"):
                gen_specific_bb = att_item_data_bb.get("gen_specific", {})
                if generation == 5 and "5" in gen_specific_bb:
                    damage_fraction = 1/8
                elif generation >= 6 and "6+" in gen_specific_bb:
                    damage_fraction = 1/6
    
    # Apply trapping
    defender.partially_trapped = True
    defender.partial_trap_turns = duration
    defender.partial_trap_damage = damage_fraction
    defender.trapped = True
    defender.trap_source = attacker.species
    
    # Store Bind-specific data
    defender._bind_data = {
        "generation": generation,
        "prevents_attack": (generation == 1),
        "binding_band": (damage_fraction > 1/16),
        "grip_claw": (duration == 5 or duration == 7)
    }
    
    # Generation-specific messages
    if generation == 1:
        messages.append(f"{defender.species} was BOUND by {attacker.species}!")
    elif generation == 2:
        messages.append(f"{attacker.species} used Bind on {defender.species}!")
    else:
        messages.append(f"{defender.species} was squeezed by {attacker.species}'s Bind!")
    
    if generation >= 2:
        messages.append(f"{defender.species} can no longer escape!")
    
    trap_data = {
        "partially_trapped": True,
        "partial_trap_turns": duration,
        "partial_trap_damage": damage_fraction,
        "bind_gen": generation,
        "bind_source": attacker.species
    }
    
    return True, messages, trap_data


def apply_wrap(attacker: Any, defender: Any, move_name: str, field_effects: Any = None, 
               battle_state: Any = None) -> Tuple[bool, List[str], Optional[Dict[str, Any]]]:
    """
    Apply Wrap with full generation-specific mechanics.
    
    Returns: (success, messages, trap_data)
    
    Generation differences:
    - Gen I: Prevents target from attacking, 2-5 turns (85% accuracy)
    - Gen II+: Traps target, deals 1/16 HP per turn for 2-5 turns (90% Gen V+, 85% Gen I-IV)
    - Gen V+: 4-5 turns, Binding Band increases to 1/8, Grip Claw makes 7 turns
    - Gen VI+: 1/8 HP per turn, Binding Band increases to 1/6
    """
    from .generation import get_generation
    generation = get_generation(field_effects=field_effects, battle_state=battle_state)
    
    messages = []
    
    # Gen II+: Ghost types cannot be trapped
    if generation >= 2:
        defender_types = [t.strip().title() if t else None for t in getattr(defender, 'types', (None, None))]
        if "Ghost" in defender_types:
            return False, [f"{defender.species} cannot be trapped by Wrap!"], None
    
    # Determine base duration
    if generation == 1:
        base_duration = (2, 5)
    elif generation >= 5:
        base_duration = (4, 5)
    else:
        base_duration = (2, 5)
    
    # Check for Grip Claw
    duration = None
    if hasattr(attacker, 'item') and attacker.item:
        from .items import normalize_item_name, get_item_effect
        from .engine import item_is_active
        if item_is_active(attacker):
            att_item = normalize_item_name(attacker.item)
            att_item_data = get_item_effect(att_item)
            if att_item_data.get("extends_binding_moves"):
                gen_specific = att_item_data.get("gen_specific", {})
                if generation == 4 and "4" in gen_specific:
                    duration = 5
                elif generation >= 5 and "5+" in gen_specific:
                    duration = 7
    
    if duration is None:
        import random
        duration = random.randint(*base_duration)
    
    # Determine damage fraction
    if generation <= 5:
        damage_fraction = 1/16
    else:
        damage_fraction = 1/8
    
    # Check for Binding Band
    if hasattr(attacker, 'item') and attacker.item:
        from .items import normalize_item_name, get_item_effect
        from .engine import item_is_active
        if item_is_active(attacker):
            att_item_bb = normalize_item_name(attacker.item)
            att_item_data_bb = get_item_effect(att_item_bb)
            if att_item_data_bb.get("boosts_binding_moves"):
                gen_specific_bb = att_item_data_bb.get("gen_specific", {})
                if generation == 5 and "5" in gen_specific_bb:
                    damage_fraction = 1/8
                elif generation >= 6 and "6+" in gen_specific_bb:
                    damage_fraction = 1/6
    
    # Apply trapping
    defender.partially_trapped = True
    defender.partial_trap_turns = duration
    defender.partial_trap_damage = damage_fraction
    defender.trapped = True
    defender.trap_source = attacker.species
    
    # Store Wrap-specific data
    defender._wrap_data = {
        "generation": generation,
        "prevents_attack": (generation == 1),
        "binding_band": (damage_fraction > 1/16),
        "grip_claw": (duration == 5 or duration == 7)
    }
    
    # Generation-specific messages
    if generation == 1:
        messages.append(f"{defender.species} was WRAPPED by {attacker.species}!")
    elif generation == 2:
        messages.append(f"Enemy {defender.species} was WRAPPED by {attacker.species}!")
    elif generation == 3:
        messages.append(f"Wild/Foe {defender.species} was WRAPPED by {attacker.species}!")
    else:
        messages.append(f"The wild/foe's {defender.species} was wrapped by {attacker.species}!")
    
    if generation >= 2:
        messages.append(f"{defender.species} can no longer escape!")
    
    trap_data = {
        "partially_trapped": True,
        "partial_trap_turns": duration,
        "partial_trap_damage": damage_fraction,
        "wrap_gen": generation,
        "wrap_source": attacker.species
    }
    
    return True, messages, trap_data


def apply_fire_spin(attacker: Any, defender: Any, move_name: str, field_effects: Any = None,
                    battle_state: Any = None) -> Tuple[bool, List[str], Optional[Dict[str, Any]]]:
    """
    Apply Fire Spin with full generation-specific mechanics.
    
    Returns: (success, messages, trap_data)
    
    Generation differences:
    - Gen I: Power 15, Accuracy 70%, 2-5 turns, prevents target from attacking, no trap damage message
    - Gen II: 1/16 HP per turn for 2-5 turns, does not prevent attack, traps target
    - Gen III-IV: 1/16 HP per turn, Grip Claw makes it 5 turns, affected by King's Rock
    - Gen V: Power 35, Accuracy 85%, 4-5 turns, Grip Claw makes it 7 turns, Binding Band increases to 1/8
    - Gen VI+: 1/8 HP per turn, Binding Band increases to 1/6, Ghost types can't be trapped
    """
    from .generation import get_generation
    generation = get_generation(field_effects=field_effects, battle_state=battle_state)
    
    messages = []
    
    # Gen VI+: Ghost types cannot be trapped
    if generation >= 6:
        defender_types = [t.strip().title() if t else None for t in getattr(defender, 'types', (None, None))]
        if "Ghost" in defender_types:
            return False, [f"{defender.species} cannot be trapped by Fire Spin!"], None
    
    # Determine trap duration and damage
    from .items import normalize_item_name, get_item_effect
    
    # Base duration based on generation
    if generation == 1:
        duration = random.choice([2, 3, 4, 5])  # 2-5 turns with specific distribution
        damage_fraction = 0.0  # Gen I: No trap damage, prevents attack instead
    elif generation == 2:
        duration = random.randint(2, 5)
        damage_fraction = 1/16
    elif generation <= 4:
        duration = random.randint(2, 5)
        damage_fraction = 1/16
        # Grip Claw: Makes it always 5 turns
        if attacker.item:
            att_item = normalize_item_name(attacker.item)
            att_item_data = get_item_effect(att_item)
            if att_item_data.get("fixes_trap_duration"):
                duration = 5
    elif generation == 5:
        duration = random.randint(4, 5)
        damage_fraction = 1/16
        # Grip Claw: Makes it always 7 turns
        if attacker.item:
            att_item = normalize_item_name(attacker.item)
            att_item_data = get_item_effect(att_item)
            if att_item_data.get("fixes_trap_duration"):
                duration = 7
        # Binding Band: Increases damage to 1/8
        if attacker.item:
            att_item = normalize_item_name(attacker.item)
            att_item_data = get_item_effect(att_item)
            if att_item_data.get("increases_trap_damage"):
                damage_fraction = 1/8
    else:  # Gen VI+
        duration = random.randint(4, 5)
        damage_fraction = 1/8  # Base is 1/8 in Gen VI+
        # Binding Band: Increases to 1/6
        if attacker.item:
            att_item = normalize_item_name(attacker.item)
            att_item_data = get_item_effect(att_item)
            if att_item_data.get("increases_trap_damage"):
                damage_fraction = 1/6
    
    # Apply trapping
    defender.partially_trapped = True
    defender.partial_trap_turns = duration
    defender.partial_trap_damage = damage_fraction
    defender.trapped = True
    defender.trap_source = attacker.species
    
    # Gen I: Store data for attack prevention
    if generation == 1:
        defender._fire_spin_data = {
            "generation": generation,
            "prevents_attack": True,
            "source": attacker.species
        }
        messages.append(f"{defender.species} was trapped!")
        messages.append(f"{defender.species}'s attack continues!")
    elif generation == 2:
        messages.append(f"{defender.species} was trapped!")
    else:
        messages.append(f"{defender.species} was trapped in the fiery vortex!" if generation >= 5 else f"{defender.species} was trapped in the vortex!")
    
    trap_data = {
        "partially_trapped": True,
        "partial_trap_turns": duration,
        "partial_trap_damage": damage_fraction,
        "fire_spin_gen": generation,
        "fire_spin_source": attacker.species
    }
    
    return True, messages, trap_data


def apply_magma_storm(attacker: Any, defender: Any, field_effects: Any = None,
                      battle_state: Any = None) -> Tuple[bool, List[str], Optional[Dict[str, Any]]]:
    """
    Apply Magma Storm with generation-accurate trapping behaviour.
    """
    from .generation import get_generation
    generation = get_generation(field_effects=field_effects, battle_state=battle_state)
    messages: List[str] = []
    
    # Gen VI+: Ghost types cannot be trapped
    if generation >= 6:
        defender_types = [t.strip().title() if t else None for t in getattr(defender, 'types', (None, None))]
        if "Ghost" in defender_types:
            return False, [f"{defender.species} slipped free of the magma storm!"], None
    
    # Determine duration
    base_duration = (2, 5) if generation == 4 else (4, 5)
    duration = None
    
    if hasattr(attacker, 'item') and attacker.item:
        from .items import normalize_item_name, get_item_effect
        from .engine import item_is_active
        if item_is_active(attacker):
            att_item = normalize_item_name(attacker.item)
            att_item_data = get_item_effect(att_item)
            if att_item_data.get("extends_binding_moves"):
                gen_specific = att_item_data.get("gen_specific", {})
                if generation == 4 and "4" in gen_specific:
                    duration = gen_specific["4"].get("binding_turns", 5)
                elif generation >= 5:
                    duration = gen_specific.get("5+", {}).get("binding_turns", 7)
    if duration is None:
        duration = random.randint(*base_duration)
    
    # Determine damage fraction
    damage_fraction = 1 / 16 if generation <= 5 else 1 / 8
    if hasattr(attacker, 'item') and attacker.item:
        from .items import normalize_item_name, get_item_effect
        from .engine import item_is_active
        if item_is_active(attacker):
            att_item = normalize_item_name(attacker.item)
            att_item_data = get_item_effect(att_item)
            if att_item_data.get("boosts_binding_moves"):
                if generation == 5:
                    damage_fraction = 1 / 8
                elif generation >= 6:
                    damage_fraction = 1 / 6
    
    defender.partially_trapped = True
    defender.partial_trap_turns = duration
    defender.partial_trap_damage = damage_fraction
    defender.trapped = True
    defender.trap_source = attacker.species
    
    if generation == 4:
        messages.append(f"{defender.species} was trapped by the swirling magma!")
    else:
        messages.append(f"{defender.species} was trapped by the raging magma!")
    messages.append(f"{defender.species} can no longer escape!")
    
    trap_data = {
        "partially_trapped": True,
        "partial_trap_turns": duration,
        "partial_trap_damage": damage_fraction,
        "magma_storm_gen": generation,
        "magma_storm_source": attacker.species
    }
    
    return True, messages, trap_data
