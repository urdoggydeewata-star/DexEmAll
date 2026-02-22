"""
Battle Flow Functions
Handles the execution flow for moves, including multi-turn moves, restrictions, and special mechanics.
"""

from __future__ import annotations
from typing import List, Optional, Tuple, Any, Dict
import random

from .engine import reset_rollout, modify_stages, is_weather_negated, release_octolock
from .abilities import normalize_ability_name
from .moves_loader import load_move
from .move_effects import get_move_secondary_effect

def can_pokemon_move(mon: Any, field_effects: Any = None, move_name: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """
    Check if a Pokémon can move this turn.
    Returns: (can_move, reason_if_cant)
    
    Now includes generation-aware confusion self-hit checks.
    
    Args:
        mon: The Pokémon attempting to move
        field_effects: Field effects for generation checks
        move_name: Optional move name being attempted (for Sleep Talk/Snore exceptions)
    """
    from .generation import get_generation
    from .engine import disrupt_rampage, check_confusion_self_hit
    generation = get_generation(field_effects=field_effects)
    
    def _release_sky_drop(mon_obj: Any) -> None:
        if hasattr(mon_obj, '_sky_drop_target'):
            target_ref = getattr(mon_obj, '_sky_drop_target', None)
            if target_ref:
                if getattr(target_ref, '_sky_drop_lifted', False):
                    target_ref._sky_drop_lifted = False
                if getattr(target_ref, '_sky_drop_invulnerable', False):
                    prev_invuln = getattr(target_ref, '_sky_drop_prev_invulnerable', False)
                    prev_type = getattr(target_ref, '_sky_drop_prev_invulnerable_type', None)
                    target_ref.invulnerable = prev_invuln
                    target_ref.invulnerable_type = prev_type
                    delattr(target_ref, '_sky_drop_invulnerable')
                    if hasattr(target_ref, '_sky_drop_prev_invulnerable'):
                        delattr(target_ref, '_sky_drop_prev_invulnerable')
                    if hasattr(target_ref, '_sky_drop_prev_invulnerable_type'):
                        delattr(target_ref, '_sky_drop_prev_invulnerable_type')
                if hasattr(target_ref, '_sky_drop_cannot_move'):
                    delattr(target_ref, '_sky_drop_cannot_move')
                if hasattr(target_ref, '_sky_drop_lifted_by'):
                    delattr(target_ref, '_sky_drop_lifted_by')
            delattr(mon_obj, '_sky_drop_target')

    # Check recharge
    if mon.must_recharge:
        reset_rollout(mon)
        _release_sky_drop(mon)
        return False, f"{mon.species} must recharge!"
    
    # Check flinch (Dynamax Pokemon are immune to flinching)
    if mon.flinched and not mon.dynamaxed:
        if getattr(mon, 'rampage_move', None) and generation >= 5:
            disrupt_rampage(mon, field_effects, reason="flinch")
        reset_rollout(mon)
        _release_sky_drop(mon)
        return False, f"{mon.species} flinched and couldn't move!"
    
    # Check confusion (must be checked BEFORE status conditions)
    if hasattr(mon, 'confused') and mon.confused:
        hit_self, damage, message = check_confusion_self_hit(mon, field_effects)
        
        if hit_self:
            # Pokémon hits itself in confusion
            mon.hp = max(0, mon.hp - damage)
            disrupt_rampage(mon, field_effects, reason="confusion")
            reset_rollout(mon)
            _release_sky_drop(mon)
            return False, message
        # else: Pokémon snapped out of confusion or successfully used its move
        # Continue to check other conditions
    
    # Check if currently invulnerable/charging
    if mon.invulnerable and mon.charging_turn > 0:
        # Pokémon is in the air/underground/etc., will attack next turn
        return True, None
    
    if getattr(mon, '_sky_drop_cannot_move', False):
        return False, f"{mon.species} is trapped in the air and can't move!"
    
    # Check status conditions (sleep, freeze, paralysis chance)
    if mon.status == "slp":
        # Check if this is the turn the Pokémon fell asleep
        # If _sleep_applied_this_turn flag is set, don't decrement yet
        sleep_applied_this_turn = getattr(mon, '_sleep_applied_this_turn', False)
        if not sleep_applied_this_turn:
            # Decrement sleep turns at the START of the turn (before move check)
            if mon.status_turns > 0:
                mon.status_turns -= 1
        
        # NOTE: Do NOT clear the flag here - it should only be cleared at end of turn
        # Clearing it immediately would allow decrementing if can_pokemon_move is called again
        
        # Check if Pokémon should wake up this turn
        # Don't wake up if sleep was just applied this turn
        if not sleep_applied_this_turn and mon.status_turns == 0:
            # Gen I: Cannot move on the turn it wakes up (except from Rest which has special handling)
            if generation == 1 and getattr(mon, '_gen1_rest_skip_turns', 0) > 0:
                mon._gen1_rest_skip_turns -= 1
                if mon._gen1_rest_skip_turns == 0:
                    mon.status = None  # Wake up after skip turn
                    if hasattr(mon, '_gen1_rest_skip_turns'):
                        delattr(mon, '_gen1_rest_skip_turns')
                    return True, f"{mon.species} woke up!"
                else:
                    return False, f"{mon.species} is fast asleep!"
            else:
                # Gen II+: Wake up and can move this turn
                mon.status = None
                if hasattr(mon, '_gen1_rest_skip_turns'):
                    delattr(mon, '_gen1_rest_skip_turns')
                return True, f"{mon.species} woke up!"
        
        # Still asleep - check if move is Sleep Talk or Snore
        if move_name:
            move_lower = move_name.lower().replace(" ", "-")
            if move_lower in ["sleep-talk", "snore"]:
                # Allow Sleep Talk and Snore even when asleep
                return True, None
        
        # Block other moves while asleep
        if getattr(mon, 'rampage_move', None) and generation >= 5:
            disrupt_rampage(mon, field_effects, reason="sleep")
        reset_rollout(mon)
        _release_sky_drop(mon)
        return False, f"{mon.species} is fast asleep!"
    
    if mon.status == "frz":
        # 20% chance to thaw
        if random.random() < 0.2:
            mon.status = None
            return True, f"{mon.species} thawed out!"
        if getattr(mon, 'rampage_move', None) and generation >= 5:
            disrupt_rampage(mon, field_effects, reason="freeze")
        reset_rollout(mon)
        _release_sky_drop(mon)
        return False, f"{mon.species} is frozen solid!"
    
    # Gen I: Check if prevented from attacking by Clamp or Fire Spin
    if hasattr(mon, '_clamp_data') and mon._clamp_data:
        clamp_data = mon._clamp_data
        if clamp_data.get("generation") == 1 and clamp_data.get("prevents_attack"):
            reset_rollout(mon)
            _release_sky_drop(mon)
            return False, f"{mon.species} cannot attack while clamped!"
    
    if hasattr(mon, '_fire_spin_data') and mon._fire_spin_data:
        fire_spin_data = mon._fire_spin_data
        if fire_spin_data.get("generation") == 1 and fire_spin_data.get("prevents_attack"):
            reset_rollout(mon)
            _release_sky_drop(mon)
            return False, f"{mon.species} cannot attack while trapped in Fire Spin!"
    
    if mon.status == "par":
        # 25% chance to be fully paralyzed
        if random.random() < 0.25:
            if getattr(mon, 'rampage_move', None) and generation in (2, 5, 6, 7, 8, 9):
                disrupt_rampage(mon, field_effects, reason="paralysis")
            reset_rollout(mon)
            _release_sky_drop(mon)
            return False, f"**{mon.species}** is paralyzed! It can't move!"
    
    return True, None

def get_available_moves(mon: Any, pp_store: Dict[str, int], z_move_mode: bool = False) -> List[str]:
    """
    Get list of moves the Pokémon can currently use.
    Takes into account Encore, Disable, Taunt, Torment, Choice lock, and PP.
    Returns list of move names.
    
    Args:
        mon: The Pokémon
        pp_store: Dictionary of move names to remaining PP
        z_move_mode: If True, Z-Moves bypass Taunt, Torment, Disable, Encore restrictions
    """
    available = []
    
    # === Z-MOVES: Bypass Encore, Disable, Taunt, Torment, Imprison ===
    # Note: Z-Moves ignore these restrictions, but can only be selected if base move is available
    # If forced to Struggle (e.g., Taunt + only status moves), Z-Moves cannot be selected
    
    # === DYNAMAX: Immune to Encore, Disable, Torment, Instruct ===
    # Dynamax Pokemon are immune to these restrictions
    is_dynamaxed = getattr(mon, 'dynamaxed', False)
    
    # PP lookup uses canonical move names for consistency
    def _pp_for(move: str) -> int:
        from .panel import _pp_get_from_store
        v = _pp_get_from_store(pp_store, move)
        return int(v) if v is not None else 0

    # Check Encore first (highest priority restriction)
    if mon.encored_move and mon.encore_turns > 0 and not is_dynamaxed:
        # Z-Moves bypass Encore
        if not z_move_mode:
            if _pp_for(mon.encored_move) > 0:
                return [mon.encored_move]
            mon.encored_move = None
            mon.encore_turns = 0
        # If Z-Move mode, ignore Encore and continue to check all moves
    
    # Check all moves
    for move in mon.moves:
        # Skip disabled moves (unless Z-Move mode or Dynamaxed)
        if mon.disabled_move and move.lower() == mon.disabled_move.lower():
            if not z_move_mode and not is_dynamaxed:
                continue  # Skip disabled move
            # Z-Moves and Dynamax bypass Disable, so include it
        
        # Check Taunt (can't use status moves) - Z-Moves bypass Taunt, Dynamax immune
        # Gen VII+: Status Z-Moves bypass Taunt, but Max Guard is prevented by Taunt
        if mon.taunted and mon.taunt_turns > 0 and not z_move_mode and not is_dynamaxed:
            mv_data = load_move(move)
            move_category = ""
            move_power_raw = None
            if mv_data:
                move_category = (mv_data.get("damage_class") or mv_data.get("category") or "").lower()
                if "power" in mv_data:
                    move_power_raw = mv_data.get("power")
            if isinstance(move_power_raw, (int, float)):
                move_power_value = move_power_raw
            else:
                move_power_value = 0
            variable_power = bool((get_move_secondary_effect(move) or {}).get("variable_power"))
            is_status_move = move_category == "status" or (move_power_value <= 0 and not variable_power)
            
            # Gen VII+: Max Guard is prevented by Taunt even though it's a status move
            move_lower = move.lower().replace(" ", "-")
            is_max_guard = move_lower == "max-guard"
            
            if is_status_move or is_max_guard:
                continue
        
        # Check Torment (can't use same move twice in a row) - Z-Moves bypass Torment, Dynamax immune
        if mon.tormented and mon.last_move_used and move.lower() == mon.last_move_used.lower():
            if not z_move_mode and not is_dynamaxed:
                continue  # Skip tormented move
            # Z-Moves and Dynamax bypass Torment, so include it
        
        # Check Imprison (if opponent knows this move, can't use it)
        # Z-Moves bypass Imprison
        if not z_move_mode and not is_dynamaxed:
            # Check if any opponent has Imprison active
            # In a full battle system, we'd check all opponents
            # For now, we'll check if there's an imprisoning flag on battle state
            # This is simplified - full implementation would check all opponents
            if hasattr(mon, 'imprisoning') and mon.imprisoning:
                # This mon is imprisoning others, not checking itself
                pass
            # Note: Full Imprison check requires checking opponents' imprisoned movesets
            # For now, assume the restriction is applied elsewhere if imprisoning is active
        
        # Check PP
        if _pp_for(move) > 0:
            available.append(move)
    
    # If no moves available, return Struggle
    # Note: If Z-Move mode is active and all moves are blocked by restrictions,
    # Z-Moves can still be used (they bypass the restrictions)
    # But if forced to Struggle (e.g., Taunt + only status moves), cannot use Z-Moves
    if not available:
        # Check if we're forced to Struggle due to Taunt + only status moves
        if mon.taunted and mon.taunt_turns > 0:
            # Check if any moves exist (ignoring restrictions)
            has_any_moves = False
            for move in mon.moves:
                mv_data = load_move(move)
                if mv_data and mv_data.get("category") != "status" and mv_data.get("power", 0) > 0:
                    has_any_moves = True
                    break
            # If has damaging moves but all blocked by restrictions, Z-Moves can be used
            if has_any_moves and z_move_mode:
                # Return all moves (Z-Moves bypass restrictions)
                # But we still need to check PP
                z_available = []
                for move in mon.moves:
                    if _pp_for(move) > 0:
                        z_available.append(move)
                if z_available:
                    return z_available
        return ["Struggle"]
    
    return available

def should_start_charging(move_name: str, field_effects: Any) -> Tuple[bool, Optional[str]]:
    """
    Check if a move needs charging and if charging can be skipped.
    Returns: (needs_charging, skip_reason)
    """
    from .advanced_mechanics import CHARGING_MOVES, SEMI_INVULNERABLE_MOVES
    
    move_norm = move_name.lower().replace(" ", "-")
    
    # Semi-invulnerable moves (Fly, Dig, etc.)
    if move_norm in SEMI_INVULNERABLE_MOVES:
        return True, None
    
    # Charging moves (Solar Beam, etc.)
    if move_norm in CHARGING_MOVES:
        charge_data = CHARGING_MOVES[move_norm]
        
        # Check weather skip conditions
        if charge_data.get("skip_charge_in_sun") and hasattr(field_effects, 'weather') and field_effects.weather == "sun":
            return False, "The sunlight is strong!"
        
        return True, None
    
    return False, None

def execute_charging_turn(mon: Any, move_name: str, field_effects: Any = None) -> str:
    """
    Execute the charging turn of a multi-turn move.
    Returns message string.
    """
    from .advanced_mechanics import CHARGING_MOVES, SEMI_INVULNERABLE_MOVES
    
    move_norm = move_name.lower().replace(" ", "-")
    
    # Semi-invulnerable moves
    if move_norm in SEMI_INVULNERABLE_MOVES:
        data = SEMI_INVULNERABLE_MOVES[move_norm]
        mon.charging_move = move_name
        mon.charging_turn = 1
        mon.invulnerable = True
        mon.invulnerable_type = data["invulnerable_type"]
        
        messages = {
            "flying": f"{mon.species} flew up high!",
            "underground": f"{mon.species} burrowed underground!",
            "underwater": f"{mon.species} dove underwater!",
            "shadow": f"{mon.species} vanished instantly!",
        }
        return messages.get(data["invulnerable_type"], f"{mon.species} is charging {move_name}!")
    
    # Charging moves
    if move_norm in CHARGING_MOVES:
        data = CHARGING_MOVES[move_norm]
        
        # === POWER HERB: Skip charge turn ===
        from .items import get_item_effect, normalize_item_name
        skip_charge = False
        if mon.item:
            item_data = get_item_effect(normalize_item_name(mon.item))
            if item_data.get("skip_charge_turn"):
                skip_charge = True
                mon.item = None  # Consume Power Herb
        
        if skip_charge:
            return f"{mon.species} used its **Power Herb** to skip charging!"
        
        # Normal charge behavior
        mon.charging_move = move_name
        mon.charging_turn = 1
        
        # Apply stat boosts on charge (Skull Bash, Geomancy, etc.)
        messages = [f"{mon.species} is charging {move_name}!"]
        if "boost_on_charge" in data:
            # Gen I: Skull Bash does not boost Defense on charge turn
            from .generation import get_generation
            generation_charge = get_generation(field_effects=field_effects)
            if move_norm == "skull-bash" and generation_charge == 1:
                # Gen I: No Defense boost
                pass
            else:
                boost_msgs = modify_stages(mon, data["boost_on_charge"], field_effects=field_effects)
                messages.extend(boost_msgs)
        
        return "\n".join(messages)
    
    return f"{mon.species} is preparing {move_name}!"

def execute_attack_turn(mon: Any) -> Tuple[bool, Optional[str]]:
    """
    Check if this is the attack turn of a charging move.
    Returns: (is_attack_turn, move_to_execute)
    """
    if mon.charging_move and mon.charging_turn == 1:
        # Attack on turn 2
        move_to_use = mon.charging_move
        # Clear charging state
        mon.charging_move = None
        mon.charging_turn = 0
        mon.invulnerable = False
        mon.invulnerable_type = None
        return True, move_to_use
    
    return False, None

def should_recharge_next_turn(move_name: str) -> bool:
    """Check if a move requires recharging next turn (Hyper Beam, etc.)"""
    from .advanced_mechanics import RECHARGE_MOVES
    move_norm = move_name.lower().replace(" ", "-")
    return move_norm in RECHARGE_MOVES

def apply_move_restrictions(attacker: Any, defender: Any, move_name: str, move_data: Dict[str, Any], field_effects: Any = None, battle_state: Any = None, move_connected: bool = True) -> List[str]:
    """
    Apply move effects that cause restrictions (Encore, Disable, Taunt, Torment, Trapping).
    Returns list of messages.
    
    Args:
        move_connected: Whether the move successfully connected (hit and had effect). Defaults to True for backward compatibility.
    """
    from .advanced_mechanics import TRAPPING_MOVES, PARTIAL_TRAPPING_MOVES
    from .move_effects import get_move_secondary_effect
    
    messages = []
    move_norm = move_name.lower().replace(" ", "-")
    
    # Helper function to check for Aroma Veil protection
    def has_aroma_veil_protection(mon):
        """Check if a Pokemon is protected by Aroma Veil (its own or an ally's)"""
        from .abilities import normalize_ability_name, get_ability_effect
        ability = normalize_ability_name(mon.ability or "")
        ability_data = get_ability_effect(ability)
        if ability_data.get("team_mental_move_immunity"):
            return True
        # TODO: Check allies in double/triple battles
        return False
    
    # Check for Encore
    if move_norm == "encore":
        from .generation import get_generation
        generation = get_generation(field_effects=field_effects)

        def _encore_duration(gen: int) -> int:
            if gen == 2:
                return random.randint(2, 6)
            if gen == 3:
                return random.randint(2, 6)
            if gen == 4:
                return random.randint(3, 7)
            return 3

        if has_aroma_veil_protection(defender):
            messages.append(f"{defender.species}'s Aroma Veil prevents Encore!")
        else:
            last_move = getattr(defender, 'last_move_used', None)
            if not last_move:
                messages.append("But it failed!")
            else:
                last_move_norm = last_move.lower().replace(" ", "-")
                disallowed = {
                    "transform", "mimic", "sketch", "mirror-move", "encore", "struggle"
                }
                if generation == 2:
                    disallowed.update({"sleep-talk", "metronome"})

                if last_move_norm in disallowed:
                    messages.append("But it failed!")
                elif getattr(defender, '_shell_trap_set', False):
                    messages.append(f"But it failed! {defender.species} is waiting to spring a Shell Trap!")
                else:
                    defender.encored_move = last_move
                    defender.encore_turns = _encore_duration(generation)
                    messages.append(f"{defender.species} got an Encore!")

                    from .items import get_item_effect, normalize_item_name
                    if defender.item:
                        item_data = get_item_effect(normalize_item_name(defender.item))
                        if item_data.get("cures_mental_effects"):
                            defender.encored_move = None
                            defender.encore_turns = 0
                            defender.item = None
                            messages.append(f"{defender.species}'s **Mental Herb** snapped it out of the Encore!")
    
    # Check for Disable
    if move_norm == "disable":
        from .generation import get_generation
        gen_disable = get_generation(battle_state=battle_state)
        
        if has_aroma_veil_protection(defender):
            messages.append(f"{defender.species}'s Aroma Veil prevents Disable!")
        else:
            # Gen I: Disable randomly selects from moves with PP > 0
            if gen_disable == 1:
                moves_with_pp = []
                if hasattr(defender, 'moves') and defender.moves:
                    # Check which moves have PP (simplified - assume all have PP if moves exist)
                    moves_with_pp = [m for m in defender.moves if m.lower().replace(" ", "-") != "struggle"]
                
                if not moves_with_pp:
                    messages.append(f"But it failed!")
                else:
                    selected_move = random.choice(moves_with_pp)
                    defender.disabled_move = selected_move
                    # Gen I: 0-7 turns (only count turns with action)
                    defender.disable_turns = random.randint(0, 7)
                    messages.append(f"{defender.species}'s {selected_move} was disabled!")
            
            # Gen II+: Disable the last move used
            else:
                if not defender.last_move_used or defender.last_move_used.lower().replace(" ", "-") == "struggle":
                    messages.append(f"But it failed!")
                elif hasattr(defender, 'disabled_move') and defender.disabled_move:
                    messages.append(f"But it failed! (A move is already disabled)")
                else:
                    defender.disabled_move = defender.last_move_used
                    
                    # Gen II: 2-8 turns, Gen III-IV: 2-5 turns, Gen IV: 4-7 turns, Gen V+: 4 turns
                    if gen_disable == 2:
                        defender.disable_turns = random.randint(2, 8)
                    elif gen_disable == 3:
                        defender.disable_turns = random.randint(2, 5)
                    elif gen_disable == 4:
                        defender.disable_turns = random.randint(4, 7)
                    else:
                        # Gen V+: Fixed 4 turns
                        defender.disable_turns = 4
                    
                    messages.append(f"{defender.species}'s {defender.last_move_used} was disabled!")
                    
                    # === MENTAL HERB: Cure move restrictions (Gen III+) ===
                    if gen_disable >= 3:
                        from .items import get_item_effect, normalize_item_name
                        if defender.item:
                            item_data = get_item_effect(normalize_item_name(defender.item))
                            if item_data.get("cures_mental_effects"):
                                defender.disabled_move = None
                                defender.disable_turns = 0
                                defender.item = None
                                messages.append(f"{defender.species}'s **Mental Herb** snapped it out of Disable!")
    
    # Check for Torment
    if move_norm == "torment":
        if has_aroma_veil_protection(defender):
            messages.append(f"{defender.species}'s Aroma Veil prevents Torment!")
        else:
            from .generation import get_generation
            generation = get_generation(field_effects=field_effects)

            # Check for Magic Coat reflection (using gen_specific flag)
            from .move_effects import get_move_secondary_effect
            move_effect_torment = get_move_secondary_effect("torment")
            gen_specific_torment = move_effect_torment.get("gen_specific", {}) if move_effect_torment else {}
            reflected_by_magic_coat_torment = None
            if gen_specific_torment:
                def _match_gen_torment(spec: str, gen: int) -> bool:
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
                for spec, overrides in gen_specific_torment.items():
                    if isinstance(overrides, dict) and "reflected_by_magic_coat" in overrides:
                        if _match_gen_torment(str(spec), generation):
                            reflected_by_magic_coat_torment = overrides.get("reflected_by_magic_coat")
                            break
            if reflected_by_magic_coat_torment is True and getattr(defender, 'magic_coat', False):
                defender.magic_coat = False
                attacker.tormented = True
                messages.append(f"{defender.species}'s Magic Coat bounced the torment back onto {attacker.species}!")
            else:
                defender.tormented = True
                messages.append(f"{defender.species} was subjected to torment!")
    
    # Check for trapping moves
    # Only apply trapping if the move connected (hit and had effect)
    if move_norm in TRAPPING_MOVES and move_connected:
        defender.trapped = True
        defender.trap_source = attacker.species
        messages.append(f"{defender.species} can no longer escape!")
    
    # Check for partial trapping moves (Bind, Wrap, etc.)
    # Only apply trapping if the move connected (hit and had effect)
    if move_norm in PARTIAL_TRAPPING_MOVES and move_connected:
        data = PARTIAL_TRAPPING_MOVES[move_norm]
        
        # Clamp has special generation-specific logic
        if move_norm == "clamp":
            from .binding_moves import apply_clamp
            from .generation import get_generation
            
            success, clamp_msgs, trap_data = apply_clamp(
                attacker, defender, move_name, 
                field_effects=field_effects, battle_state=battle_state
            )
            
            if success:
                messages.extend(clamp_msgs)
            else:
                messages.extend(clamp_msgs)
        elif move_norm == "whirlpool":
            from .binding_moves import apply_whirlpool
            success, whirl_msgs, trap_data = apply_whirlpool(
                attacker,
                defender,
                field_effects=field_effects,
                battle_state=battle_state
            )
            messages.extend(whirl_msgs)
        elif move_norm == "bind":
            from .binding_moves import apply_bind
            success, bind_msgs, trap_data = apply_bind(
                attacker,
                defender,
                move_name,
                field_effects=field_effects,
                battle_state=battle_state
            )
            if success:
                messages.extend(bind_msgs)
            else:
                messages.extend(bind_msgs)
        elif move_norm == "wrap":
            from .binding_moves import apply_wrap
            success, wrap_msgs, trap_data = apply_wrap(
                attacker,
                defender,
                move_name,
                field_effects=field_effects,
                battle_state=battle_state
            )
            if success:
                messages.extend(wrap_msgs)
            else:
                messages.extend(wrap_msgs)
        elif move_norm == "fire-spin":
            from .binding_moves import apply_fire_spin
            from .generation import get_generation
            generation = get_generation(field_effects=field_effects, battle_state=battle_state)
            success, fire_msgs, trap_data = apply_fire_spin(
                attacker,
                defender,
                move_name,
                field_effects=field_effects,
                battle_state=battle_state
            )
            if success:
                messages.extend(fire_msgs)
            else:
                messages.extend(fire_msgs)
        elif move_norm == "magma-storm":
            from .binding_moves import apply_magma_storm
            success, magma_msgs, trap_data = apply_magma_storm(
                attacker,
                defender,
                field_effects=field_effects,
                battle_state=battle_state
            )
            messages.extend(magma_msgs)
        else:
            from .generation import get_generation
            from .items import normalize_item_name, get_item_effect
            from .engine import item_is_active

            generation = get_generation(field_effects=field_effects, battle_state=battle_state)

            # Check if defender has a substitute or if substitute was just broken
            # Trapping moves don't trap if substitute is present or was just broken
            has_substitute = hasattr(defender, 'substitute') and defender.substitute
            substitute_still_alive = False
            if has_substitute:
                from .advanced_mechanics import Substitute
                if isinstance(defender.substitute, Substitute):
                    substitute_still_alive = defender.substitute.is_alive()
                else:
                    # Fallback: check if substitute has hp > 0
                    substitute_still_alive = getattr(defender.substitute, 'hp', 0) > 0
            
            # Don't trap if substitute is present or was just broken (substitute exists but is dead)
            if has_substitute:
                # Substitute was present - don't trap (whether it's still alive or just broke)
                return messages

            ghost_immunity = data.get("ghost_immunity", False)
            if ghost_immunity:
                defender_types = [t.strip().title() if t else None for t in getattr(defender, 'types', (None, None))]
                if "Ghost" in defender_types:
                    messages.append(f"{defender.species} slipped free of the trap!")
                    return messages

            duration_range = data.get("duration", (4, 5))
            if isinstance(duration_range, (list, tuple)) and len(duration_range) == 2:
                min_turns, max_turns = duration_range
                if min_turns == max_turns:
                    duration = min_turns
                else:
                    duration = random.randint(min_turns, max_turns)
            else:
                duration = 4

            damage_fraction = data.get("damage_fraction", 1 / 8)

            # Grip Claw extends duration
            if item_is_active(attacker) and getattr(attacker, "item", None):
                att_item = normalize_item_name(attacker.item)
                att_item_data = get_item_effect(att_item)
                if att_item_data.get("extends_binding_moves"):
                    fixed_turns = None
                    if generation == 4:
                        fixed_turns = att_item_data.get("gen_specific", {}).get("4", {}).get("binding_turns")
                    elif generation >= 5:
                        fixed_turns = att_item_data.get("gen_specific", {}).get("5+", {}).get("binding_turns")
                    if fixed_turns:
                        duration = fixed_turns

                # Binding Band increases damage
                if att_item_data.get("boosts_binding_moves"):
                    gen_data = att_item_data.get("gen_specific", {})
                    if generation == 5:
                        damage_fraction = gen_data.get("5", {}).get("binding_damage", damage_fraction)
                    elif generation >= 6:
                        damage_fraction = gen_data.get("6+", {}).get("binding_damage", damage_fraction)

            # Check if target is already trapped by the same move
            already_trapped = (defender.partially_trapped and 
                             getattr(defender, '_partial_trap_move', None) == move_norm and
                             defender.partial_trap_turns > 0)
            
            defender.partially_trapped = True
            # Only reset trap turns if not already trapped by the same move
            if not already_trapped:
                defender.partial_trap_turns = duration
                defender.partial_trap_damage = damage_fraction
            defender.trapped = True
            defender.trap_source = attacker.species
            defender._partial_trap_move = move_norm
            # Mark that trap was set this turn (prevents damage on same turn)
            defender._trap_set_this_turn = True

            # Only show trap message if it's a new trap (not already trapped)
            if not already_trapped:
                trap_message_templates = {
                    "snap-trap": "{defender} was ensnared by the Snap Trap!",
                    "thunder-cage": "{defender} was trapped in a Thunder Cage!"
                }
                message_template = trap_message_templates.get(move_norm)
                if message_template:
                    messages.append(message_template.format(defender=defender.species))
                else:
                    messages.append(f"{defender.species} was trapped by {move_name}!")
    
    return messages

def _get_screen_duration(mon: Any, field_effects: Any = None) -> int:
    """Determine screen duration, considering generation and Light Clay."""
    from .generation import get_generation
    generation = get_generation(field_effects=field_effects)
    # Gen 1: Screens persist indefinitely until removed manually
    if generation <= 1:
        return 0
    from .items import get_item_effect, normalize_item_name
    if mon and mon.item:
        item_data = get_item_effect(normalize_item_name(mon.item))
        if item_data.get("extends_screens"):
            return 8
    return 5

def apply_field_effect_move(move_name: str, field_effects: Any, side_effects: Any, user_side: bool,
                            user_mon: Any = None, battle_state: Any = None) -> List[str]:
    """
    Apply field effect moves (Reflect, Light Screen, Tailwind, Trick Room, etc.).
    Returns list of messages.
    """
    messages = []
    move_norm = move_name.lower().replace(" ", "-")
    
    # Reflect
    if move_norm == "reflect":
        if not side_effects.reflect:
            side_effects.reflect = True
            side_effects.reflect_turns = _get_screen_duration(user_mon, field_effects)
            messages.append("Reflect raised physical defense!")
        else:
            messages.append("But it failed!")
    
    # Light Screen
    elif move_norm == "light-screen":
        if not side_effects.light_screen:
            side_effects.light_screen = True
            side_effects.light_screen_turns = _get_screen_duration(user_mon, field_effects)
            messages.append("Light Screen raised special defense!")
        else:
            messages.append("But it failed!")
    
    # Aurora Veil (requires snow/hail)
    elif move_norm == "aurora-veil":
        current_weather = getattr(field_effects, 'weather', None) if field_effects else None
        weather_ok = current_weather in ["snow", "hail"]
        weather_negated = False
        if weather_ok and battle_state:
            active_candidates = []
            try:
                active_candidates.append(battle_state._active(battle_state.p1_id))
            except Exception:
                pass
            try:
                active_candidates.append(battle_state._active(battle_state.p2_id))
            except Exception:
                pass
            for partner_attr in ["p1_partner", "p2_partner"]:
                partner_mon = getattr(battle_state, partner_attr, None)
                if partner_mon:
                    active_candidates.append(partner_mon)
            active_mons = [mon for mon in active_candidates if mon]
            if active_mons:
                weather_negated = is_weather_negated(active_mons)
        if weather_ok and not weather_negated:
            if not side_effects.aurora_veil:
                side_effects.aurora_veil = True
                side_effects.aurora_veil_turns = _get_screen_duration(user_mon, field_effects)
                messages.append("Aurora Veil raised defenses!")
            else:
                messages.append("But it failed!")
        else:
            if weather_negated:
                messages.append("But it failed! (Weather effects are negated)")
            else:
                messages.append("But it failed! (Aurora Veil requires snow or hail)")
    
    # Tailwind
    elif move_norm == "tailwind":
        if not side_effects.tailwind:
            side_effects.tailwind = True
            side_effects.tailwind_turns = 4
            messages.append("The tailwind blew from behind!")
        else:
            messages.append("But it failed!")
    
    # Safeguard
    elif move_norm == "safeguard":
        if not side_effects.safeguard:
            duration = _get_screen_duration(user_mon, field_effects)
            side_effects.safeguard = True
            side_effects.safeguard_turns = duration if duration > 0 else 5
            messages.append("A mystical veil surrounds the team!")
        else:
            messages.append("But it failed!")
    
    # Trick Room
    elif move_norm == "trick-room":
        z_messages: List[str] = []
        if user_mon is not None and hasattr(user_mon, '_is_z_move') and user_mon._is_z_move:
            z_messages = modify_stages(user_mon, {"accuracy": 1}, caused_by_opponent=False, field_effects=field_effects)
        
        if not field_effects.trick_room:
            field_effects.trick_room = True
            field_effects.trick_room_turns = 5
            messages.append("The dimensions were twisted!")
        else:
            # Trick Room can be ended early by using it again
            field_effects.trick_room = False
            field_effects.trick_room_turns = 0
            messages.append("The twisted dimensions returned to normal!")
        
        messages.extend(z_messages)
    
    # Magic Room
    elif move_norm == "magic-room":
        z_messages: List[str] = []
        if user_mon is not None and hasattr(user_mon, '_is_z_move') and user_mon._is_z_move:
            z_messages = modify_stages(user_mon, {"spd": 1}, caused_by_opponent=False, field_effects=field_effects)
        if not field_effects.magic_room:
            field_effects.magic_room = True
            field_effects.magic_room_turns = 5
            messages.append("It created a bizarre area in which items can't be used!")
        else:
            field_effects.magic_room = False
            field_effects.magic_room_turns = 0
            messages.append("The area returned to normal!")
        messages.extend(z_messages)
    
    # Wonder Room
    elif move_norm == "wonder-room":
        z_messages: List[str] = []
        if user_mon is not None and hasattr(user_mon, '_is_z_move') and user_mon._is_z_move:
            z_messages = modify_stages(user_mon, {"spd": 1}, caused_by_opponent=False, field_effects=field_effects)
        if not field_effects.wonder_room:
            field_effects.wonder_room = True
            field_effects.wonder_room_turns = 5
            messages.append("It created a bizarre area in which Defense and Sp. Def stats are swapped!")
        else:
            field_effects.wonder_room = False
            field_effects.wonder_room_turns = 0
            messages.append("The area returned to normal!")
        messages.extend(z_messages)
    
    # Gravity
    elif move_norm == "gravity":
        if not field_effects.gravity:
            field_effects.gravity = True
            field_effects.gravity_turns = 5
            messages.append("Gravity intensified!")
        else:
            messages.append("But it failed!")
    
    # Mist
    elif move_norm == "mist":
        from .generation import get_generation
        gen_mist = get_generation(field_effects=field_effects) if field_effects else 9
        
        # Gen I: Fails if already active
        if gen_mist == 1:
            if hasattr(side_effects, 'mist') and side_effects.mist:
                messages.append("But it failed!")
            else:
                side_effects.mist = True  # Lasts until switch out
                messages.append("Mist shrouded the team!")
        # Gen II: Cannot be Hazed
        elif gen_mist == 2:
            side_effects.mist = True
            messages.append("Mist shrouded the team!")
        # Gen III+: Side effect, 5 turns
        else:
            if not hasattr(side_effects, 'mist') or not side_effects.mist:
                side_effects.mist = True
                side_effects.mist_turns = 5
                messages.append("Mist shrouded the team!")
            else:
                messages.append("But it failed!")
    
    return messages

def apply_substitute(user: Any) -> Tuple[bool, str]:
    """
    Create a substitute for the user.
    Returns: (success, message)
    """
    if user.substitute and user.substitute.is_alive():
        return False, f"{user.species} already has a substitute!"
    
    # Substitute costs 25% of max HP
    cost = user.max_hp // 4
    if user.hp <= cost:
        return False, f"{user.species} doesn't have enough HP for a substitute!"
    
    from .advanced_mechanics import Substitute
    user.hp -= cost
    user.substitute = Substitute(hp=cost, max_hp=cost)
    return True, f"{user.species} created a substitute!"

def handle_protect(user: Any, move_name: str, field_effects: Any = None, is_moving_last: bool = False) -> Tuple[bool, str]:
    """
    Handle Protect/Detect with generation-specific success rate and priority.
    Returns: (protected, message)
    """
    move_norm = move_name.lower().replace(" ", "-")
    if move_norm not in {"protect", "detect", "spiky-shield", "baneful-bunker", "kings-shield", "obstruct", "winters-aegis", "silk-trap", "burning-bulwark"}:
        return False, ""
    
    # Winter's Aegis: Cannot be used if it was melted by Fire
    if move_norm == "winters-aegis" and getattr(user, '_winters_aegis_melted', False):
        return False, f"{user.species}'s Winter's Aegis was melted and cannot be used!"
    
    # King's Shield, Protect, Detect, etc.: Fail if user goes last in the turn
    # According to Bulbapedia: "If the user goes last in the turn, the move will fail."
    if is_moving_last:
        user.consecutive_protects = 0  # Reset on failure
        return False, f"{user.species} failed to protect itself! (moved last)"
    
    from .generation import get_generation
    generation = get_generation(field_effects=field_effects) if field_effects else 9
    
    # Gen II: Detect fails if user is behind a substitute
    if generation == 2 and move_norm == "detect":
        if hasattr(user, 'substitute') and user.substitute:
            user.consecutive_protects = 0  # Reset on failure
            return False, f"{user.species} failed to protect itself! (behind substitute)"
    
    # Generation-specific success rate calculation
    if generation == 2:
        # Gen II: x/255 where x starts at 255 and is halved per successive use
        # After 8 successive uses, always fails
        if user.consecutive_protects >= 8:
            user.consecutive_protects = 0  # Reset on failure
            return False, f"{user.species} failed to protect itself!"
        
        x = 255 / (2 ** user.consecutive_protects)
        success_chance = x / 255.0
    elif generation in [3, 4]:
        # Gen III-IV: 1/2 after each use, with lower bound of 1/8
        # Gen III has a bug that makes it erratic after 1/8 (not implementing bug)
        if user.consecutive_protects == 0:
            success_chance = 1.0
        else:
            success_chance = (1.0 / 2.0) ** user.consecutive_protects
            success_chance = max(success_chance, 1.0 / 8.0)  # Lower bound 1/8
    elif generation == 5:
        # Gen V: 1/2 after each use
        success_chance = (1.0 / 2.0) ** user.consecutive_protects if user.consecutive_protects > 0 else 1.0
    else:  # Gen VI+
        # Gen VI+: 1/3 after each use
        success_chance = (1.0 / 3.0) ** user.consecutive_protects if user.consecutive_protects > 0 else 1.0
    
    if random.random() < success_chance:
        user.protected_this_turn = True
        user.consecutive_protects += 1
        user._protection_move = move_norm
        return True, f"{user.species} protected itself!"
    else:
        user.consecutive_protects = 0  # Reset on failure
        # Clear protection flag if it was pre-set but the move failed
        user.protected_this_turn = False
        if hasattr(user, '_protection_move'):
            delattr(user, '_protection_move')
        return False, f"{user.species} failed to protect itself!"


def handle_endure(user: Any, field_effects: Any = None, is_moving_last: bool = False) -> Tuple[bool, str]:
    """Handle Endure success chance and activation."""
    from .generation import get_generation
    generation = get_generation(field_effects=field_effects) if field_effects else 9

    # Gen III-IV: Endure fails if the user moves last
    if is_moving_last and generation in (3, 4):
        user.consecutive_protects = 0
        user.endure_active = False
        user._last_move_failed = True
        return False, "But it failed!"

    # Determine success chance (shared counter with Protect)
    if generation == 2:
        if user.consecutive_protects >= 8:
            user.consecutive_protects = 0
            user.endure_active = False
            user._last_move_failed = True
            return False, "But it failed!"
        x = 255 / (2 ** user.consecutive_protects)
        success_chance = x / 255.0
    elif generation in [3, 4]:
        if user.consecutive_protects == 0:
            success_chance = 1.0
        else:
            success_chance = (1.0 / 2.0) ** user.consecutive_protects
            success_chance = max(success_chance, 1.0 / 8.0)
    elif generation == 5:
        success_chance = (1.0 / 2.0) ** user.consecutive_protects if user.consecutive_protects > 0 else 1.0
    else:
        success_chance = (1.0 / 3.0) ** user.consecutive_protects if user.consecutive_protects > 0 else 1.0

    if random.random() < success_chance:
        user.endure_active = True
        user.consecutive_protects += 1
        return True, f"{user.species} braced itself!"

    user.consecutive_protects = 0
    user.endure_active = False
    user._last_move_failed = True
    return False, "But it failed!"


def handle_max_guard(user: Any, field_effects: Any = None, is_moving_last: bool = False) -> Tuple[bool, str]:
    """Handle Max Guard success chance and activation."""
    import random
    from .generation import get_generation

    if is_moving_last:
        user.consecutive_protects = 0
        user.max_guard_active = False
        user.protected_this_turn = False
        user._last_move_failed = True
        return False, "But it failed! (Moving last)"

    generation = get_generation(field_effects=field_effects) if field_effects else 8

    # Max Guard shares the Protect counter (Gen VIII mechanics)
    if user.consecutive_protects == 0:
        success_chance = 1.0
    elif generation == 5:
        success_chance = (1.0 / 2.0) ** user.consecutive_protects
    else:
        success_chance = (1.0 / 3.0) ** user.consecutive_protects

    if random.random() < success_chance:
        user.protected_this_turn = True
        user.max_guard_active = True
        user.consecutive_protects += 1
        user._protection_move = "max-guard"
        return True, "Max Guard protected it from harm!"

    user.consecutive_protects = 0
    user.max_guard_active = False
    user.protected_this_turn = False
    user._last_move_failed = True
    if hasattr(user, '_protection_move'):
        delattr(user, '_protection_move')
    return False, "But it failed!"

def end_of_turn_cleanup(mon: Any, field_effects: Any) -> List[str]:
    """
    Cleanup at end of turn: decrement counters, restore temporary state changes.
    
    Handles:
    - Roost type restoration (Flying type returns)
    - Other temporary state changes
    """
    messages = []

    if hasattr(mon, '_moved_this_turn'):
        mon._moved_this_turn = False
    if hasattr(mon, '_stats_lowered_this_turn'):
        mon._stats_lowered_this_turn = False
    if hasattr(mon, '_kings_shield_atk_drop_applied_this_turn'):
        mon._kings_shield_atk_drop_applied_this_turn = False
    if hasattr(mon, '_stats_raised_this_turn'):
        mon._stats_raised_this_turn = False
    if getattr(mon, "mega_evolved", False) and not getattr(mon, "_mega_speed_applied", False):
        mon._mega_speed_applied = True
    
    # Roost: Restore Flying type at end of turn (Gen IV+)
    if hasattr(mon, '_roost_type_removed') and mon._roost_type_removed:
        if hasattr(mon, '_original_types_roost'):
            mon.types = mon._original_types_roost
            mon._roost_type_removed = False
            delattr(mon, '_original_types_roost')
    
    # Gen IV: Clear Flying type ignore flag
    if hasattr(mon, '_roost_flying_ignored'):
        delattr(mon, '_roost_flying_ignored')
    
    # Decrement Encore
    if mon.encore_turns > 0:
        mon.encore_turns -= 1
        if mon.encore_turns == 0:
            mon.encored_move = None
            messages.append(f"{mon.species}'s Encore ended!")
    
    # Clear Endure at end of turn
    if hasattr(mon, 'endure_active') and mon.endure_active:
        mon.endure_active = False

    if hasattr(mon, '_protection_move'):
        delattr(mon, '_protection_move')

    # Decrement Disable
    if mon.disable_turns > 0:
        mon.disable_turns -= 1
        if mon.disable_turns == 0:
            move_name = mon.disabled_move  # Save before clearing
            mon.disabled_move = None
            if move_name:
                messages.append(f"{mon.species}'s {move_name} is no longer disabled!")
    
    # Decrement Magnet Rise
    if hasattr(mon, '_magnet_rise_turns') and mon._magnet_rise_turns > 0:
        mon._magnet_rise_turns -= 1
        if mon._magnet_rise_turns == 0:
            messages.append(f"{mon.species}'s Magnet Rise ended!")
    
    # Decrement Taunt
    if mon.taunt_turns > 0:
        mon.taunt_turns -= 1
        if mon.taunt_turns == 0:
            mon.taunted = False
            messages.append(f"{mon.species}'s taunt wore off!")
            if hasattr(mon, "_taunt_pending"):
                mon._taunt_pending = False
            if hasattr(mon, "_taunt_applied_turn"):
                mon._taunt_applied_turn = None
    
    # Partial trapping damage
    # Only apply damage if trap was set on a previous turn (not the turn it was set)
    # Check if trap was just set this turn by checking if _trap_set_this_turn flag exists
    trap_just_set = getattr(mon, '_trap_set_this_turn', False)
    if mon.partially_trapped and mon.partial_trap_turns > 0 and not trap_just_set:
        # Check if this is Clamp (has special logic)
        if hasattr(mon, '_clamp_data') and mon._clamp_data:
            from .binding_moves import apply_clamp_end_turn_damage
            clamp_damage, clamp_msgs = apply_clamp_end_turn_damage(mon, field_effects)
            messages.extend(clamp_msgs)
            # Decrement turns after applying damage
            mon.partial_trap_turns -= 1
        else:
            # Standard binding move damage
            mon.partial_trap_turns -= 1
            trap_dmg = max(1, int(mon.max_hp * mon.partial_trap_damage))
            mon.hp = max(0, mon.hp - trap_dmg)
            trap_move = getattr(mon, '_partial_trap_move', None)
            damage_templates = {
                "snap-trap": "{defender} was squeezed by the Snap Trap! (-{damage} HP)",
                "thunder-cage": "{defender} was shocked by the Thunder Cage! (-{damage} HP)"
            }
            if trap_move and trap_move in damage_templates:
                messages.append(damage_templates[trap_move].format(defender=mon.species, damage=trap_dmg))
            else:
                messages.append(f"{mon.species} is hurt by the trap! (-{trap_dmg} HP)")
        
    # Clear the flag after checking (trap will apply damage on next turn)
    if hasattr(mon, '_trap_set_this_turn'):
        delattr(mon, '_trap_set_this_turn')
    
    # Clear sleep flag at end of turn (so it can decrement on next turn)
    # This ensures sleep applied this turn doesn't get decremented until next turn
    if hasattr(mon, '_sleep_applied_this_turn'):
        mon._sleep_applied_this_turn = False
    
    # Check if trap ended (only if trap was active and turns reached 0)
    if mon.partially_trapped and mon.partial_trap_turns == 0:
            mon.partially_trapped = False
            mon.partial_trap_damage = 0.0
            mon.trapped = False
            mon.trap_source = None
            trap_move = getattr(mon, '_partial_trap_move', None)
            if hasattr(mon, '_clamp_data'):
                delattr(mon, '_clamp_data')
            release_templates = {
                "snap-trap": "{defender} escaped the Snap Trap!",
                "thunder-cage": "{defender} was freed from the Thunder Cage!"
            }
            if trap_move and trap_move in release_templates:
                messages.append(release_templates[trap_move].format(defender=mon.species))
            else:
                messages.append(f"{mon.species} was freed from the trap!")
            if hasattr(mon, '_partial_trap_move'):
                delattr(mon, '_partial_trap_move')
    
    # Rampage moves (Outrage, Thrash, Petal Dance)
    if hasattr(mon, 'rampage_turns_remaining') and mon.rampage_turns_remaining > 0:
        mon.rampage_turns_remaining -= 1
        if mon.rampage_turns_remaining == 0:
            # Rampage ends - confuse the user
            # Gen II: Only confuses if fully executed (disruption check handled elsewhere)
            # Gen V-VII: Always confuses even if disrupted on final turn
            rampage_name = getattr(mon, 'rampage_move', '')
            mon.rampage_move = None
            if hasattr(mon, '_outrage_power_override'):
                delattr(mon, '_outrage_power_override')
            
            # Apply confusion after rampage ends
            from .generation import get_generation
            generation = getattr(mon, '_rampage_generation', None)
            if generation is None:
                generation = get_generation(field_effects=field_effects)
            disrupted = getattr(mon, '_rampage_disrupted', False)
            force_confuse = False
            suppress_confuse = False
            if disrupted:
                if generation >= 5:
                    force_confuse = getattr(mon, '_rampage_disrupted_final_turn', False)
                    suppress_confuse = not force_confuse
                else:
                    suppress_confuse = True
            if not suppress_confuse and (force_confuse or not mon.status or mon.status.lower() not in ["sleep", "freeze"]):
                mon.confused = True
                mon.confusion_turns = random.randint(1, 4)
                mon._confusion_applied_this_turn = True
                messages.append(f"**{mon.species}** became confused due to fatigue!")
            for attr in ("_rampage_disrupted", "_rampage_disrupted_final_turn", "_rampage_disrupted_reason"):
                if hasattr(mon, attr):
                    delattr(mon, attr)
            if hasattr(mon, '_rampage_generation'):
                delattr(mon, '_rampage_generation')
    
    # Octolock stat reduction
    octolock_source = getattr(mon, '_octolocked_by', None)
    if octolock_source:
        if mon.hp <= 0 or getattr(octolock_source, '_octolock_target', None) is not mon or octolock_source.hp <= 0:
            release_octolock(mon)
        else:
            drop_values = getattr(mon, '_octolock_stat_drop', None) or {"defn": -1, "spd": -1}
            drop_msgs = modify_stages(mon, drop_values, caused_by_opponent=True, field_effects=field_effects)
            if drop_msgs:
                messages.extend(drop_msgs)
                mon._stats_lowered_this_turn = True
            mon._octolock_turns = getattr(mon, '_octolock_turns', 0) + 1

    # Telekinesis duration
    if hasattr(mon, '_telekinesis_turns') and mon._telekinesis_turns > 0:
        mon._telekinesis_turns -= 1
        if mon._telekinesis_turns <= 0:
            mon._telekinesis_turns = 0
            if hasattr(mon, '_telekinesis_source'):
                delattr(mon, '_telekinesis_source')
            messages.append(f"{mon.species} returned to the ground!")
    
    # Mind Reader / Lock-On duration handling
    if hasattr(mon, 'lock_on_turns') and mon.lock_on_turns > 0:
        mon.lock_on_turns -= 1
        if mon.lock_on_turns <= 0:
            mon.lock_on_turns = 0
            mon.lock_on_target = None
            if hasattr(mon, '_mind_reader_target'):
                mon._mind_reader_target = None

    if hasattr(mon, 'laser_focus_turns') and mon.laser_focus_turns > 0:
        mon.laser_focus_turns -= 1
        if mon.laser_focus_turns <= 0:
            mon.laser_focus_turns = 0
            if hasattr(mon, '_laser_focus_pending'):
                mon._laser_focus_pending = False

    # Yawn drowsiness handling
    if getattr(mon, 'drowsy_turns', 0) > 0:
        if mon.hp <= 0:
            mon.drowsy_turns = 0
            mon.drowsy_source = None
            if hasattr(mon, '_yawn_generation'):
                delattr(mon, '_yawn_generation')
        else:
            mon.drowsy_turns = max(0, mon.drowsy_turns - 1)
            if mon.drowsy_turns == 0:
                from .generation import get_generation
                from .abilities import normalize_ability_name, get_ability_effect
                from .advanced_moves import is_grounded
                from .db_move_effects import apply_status_effect

                generation = getattr(mon, '_yawn_generation', None)
                if generation is None:
                    generation = get_generation(field_effects=field_effects)

                ability_key = normalize_ability_name(getattr(mon, 'ability', '') or "")
                ability_data = get_ability_effect(ability_key)
                ability_name = (mon.ability or ability_key or "Ability").replace('-', ' ').title()

                blocked_reason = None
                temporary_block = False

                if mon.status:
                    mon.drowsy_turns = 0
                    mon.drowsy_source = None
                    if hasattr(mon, '_yawn_generation'):
                        delattr(mon, '_yawn_generation')
                else:
                    status_immunity = ability_data.get("status_immunity")
                    if status_immunity == "all" or (isinstance(status_immunity, list) and "slp" in status_immunity):
                        blocked_reason = f"{mon.species}'s {ability_name} keeps it awake!"
                    elif ability_key in ["insomnia", "vital-spirit", "comatose", "purifying-salt"]:
                        blocked_reason = f"{mon.species}'s {ability_name} keeps it awake!"
                    else:
                        # Leaf Guard in harsh sunlight
                        if ability_key == "leaf-guard" and generation >= 5 and field_effects:
                            if getattr(field_effects, 'weather', None) == "sun" or getattr(field_effects, 'harsh_sunlight', False) or getattr(field_effects, 'special_weather', None) == "harsh-sunlight":
                                blocked_reason = f"{mon.species}'s {ability_name} kept it from falling asleep!"
                                temporary_block = True

                        # Sweet Veil / Flower Veil style protections (approximated on holder)
                        if not blocked_reason and ability_data.get("team_sleep_immunity"):
                            blocked_reason = f"{mon.species}'s {ability_name} kept it awake!"
                            temporary_block = True
                        if not blocked_reason and ability_data.get("protects_grass_types") and "Grass" in [t for t in mon.types if t]:
                            blocked_reason = f"{mon.species}'s {ability_name} protected it from sleep!"
                            temporary_block = True

                        # Terrain-based prevention
                        if not blocked_reason and field_effects:
                            terrain = getattr(field_effects, 'terrain', None)
                            if terrain in ["electric", "misty"] and is_grounded(mon, field_gravity=getattr(field_effects, 'gravity', False)):
                                terrain_name = "Electric" if terrain == "electric" else "Misty"
                                blocked_reason = f"{terrain_name} Terrain kept {mon.species} awake!"
                                temporary_block = True

                        # Uproar (Gen V onwards)
                        if not blocked_reason and field_effects and getattr(field_effects, 'uproar_turns', 0) > 0 and ability_key != "soundproof":
                            if generation >= 5:
                                source_name = getattr(field_effects, 'uproar_source', None)
                                if source_name:
                                    blocked_reason = f"The uproar from {source_name} kept {mon.species} awake!"
                                else:
                                    blocked_reason = f"An uproar kept {mon.species} awake!"
                                temporary_block = True

                        # Flower Veil ally-style coverage from user side (approximate via Purifying Salt etc handled above)

                    if blocked_reason:
                        if temporary_block:
                            mon.drowsy_turns = 1
                        else:
                            mon.drowsy_turns = 0
                            mon.drowsy_source = None
                            if hasattr(mon, '_yawn_generation'):
                                delattr(mon, '_yawn_generation')
                        messages.append(blocked_reason)
                    else:
                        success, sleep_msg = apply_status_effect(mon, "slp", None, field_effects=field_effects)
                        mon.drowsy_turns = 0
                        mon.drowsy_source = None
                        if hasattr(mon, '_yawn_generation'):
                            delattr(mon, '_yawn_generation')
                        if sleep_msg:
                            messages.append(sleep_msg)

    # Clear temporary flags
    mon.flinched = False
    mon.must_recharge = False
    mon.protected_this_turn = False
    mon.max_guard_active = False
    
    # === DYNAMAX: Decrement turn counter ===
    if mon.dynamaxed and mon.dynamax_turns_remaining > 0:
        mon.dynamax_turns_remaining -= 1
        if mon.dynamax_turns_remaining == 0:
            from .max_moves import revert_dynamax
            revert_dynamax(mon)
            messages.append(f"{mon.species} returned to normal!")
    
    if hasattr(mon, '_took_damage_this_turn'):
        mon._took_damage_this_turn = False

    # Clear Mirror Armor reflection flag
    if hasattr(mon, '_mirror_armor_reflected_this_turn'):
        mon._mirror_armor_reflected_this_turn = False
    
    if hasattr(mon, 'center_of_attention'):
        mon.center_of_attention = False
        if hasattr(mon, '_center_of_attention_source'):
            delattr(mon, '_center_of_attention_source')
    if hasattr(mon, '_z_grudge_center'):
        delattr(mon, '_z_grudge_center')
    
    if hasattr(mon, '_sky_drop_cannot_move') and not getattr(mon, '_sky_drop_lifted_by', None):
        delattr(mon, '_sky_drop_cannot_move')
    if hasattr(mon, '_sky_drop_lifted') and not getattr(mon, '_sky_drop_lifted_by', None):
        delattr(mon, '_sky_drop_lifted')
    if hasattr(mon, '_sky_drop_invulnerable') and not getattr(mon, '_sky_drop_lifted_by', None):
        delattr(mon, '_sky_drop_invulnerable')
        if hasattr(mon, '_sky_drop_prev_invulnerable'):
            delattr(mon, '_sky_drop_prev_invulnerable')
        if hasattr(mon, '_sky_drop_prev_invulnerable_type'):
            delattr(mon, '_sky_drop_prev_invulnerable_type')
    if hasattr(mon, '_sky_drop_target'):
        target_ref = getattr(mon, '_sky_drop_target', None)
        if target_ref:
            if getattr(target_ref, '_sky_drop_lifted', False):
                target_ref._sky_drop_lifted = False
            if getattr(target_ref, '_sky_drop_invulnerable', False):
                prev_invuln = getattr(target_ref, '_sky_drop_prev_invulnerable', False)
                prev_type = getattr(target_ref, '_sky_drop_prev_invulnerable_type', None)
                target_ref.invulnerable = prev_invuln
                target_ref.invulnerable_type = prev_type
                delattr(target_ref, '_sky_drop_invulnerable')
                if hasattr(target_ref, '_sky_drop_prev_invulnerable'):
                    delattr(target_ref, '_sky_drop_prev_invulnerable')
                if hasattr(target_ref, '_sky_drop_prev_invulnerable_type'):
                    delattr(target_ref, '_sky_drop_prev_invulnerable_type')
            if hasattr(target_ref, '_sky_drop_cannot_move'):
                delattr(target_ref, '_sky_drop_cannot_move')
            if hasattr(target_ref, '_sky_drop_lifted_by'):
                delattr(target_ref, '_sky_drop_lifted_by')
        delattr(mon, '_sky_drop_target')
    
    return messages


