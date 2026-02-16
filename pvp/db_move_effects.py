"""
Database-Driven Move Effects System
Reads stat changes, status effects, flinch, and confusion from the database.
Uses db_cache when available, then falls back to DB.
"""
import json
from functools import lru_cache
from typing import Dict, List, Tuple, Optional, Any
from .db_pool import get_connection

try:
    from lib import db_cache
except ImportError:
    db_cache = None


def _effects_from_row(r: Dict[str, Any]) -> Dict[str, Any]:
    def _v(k, d=0):
        x = r.get(k)
        return x if x is not None else d
    def _j(k):
        x = r.get(k)
        if not x:
            return []
        try:
            return json.loads(x) if isinstance(x, str) else (x if isinstance(x, list) else [])
        except Exception:
            return []
    return {
        "stat_changes": _j("stat_changes"),
        "inflicts_status": _v("inflicts_status"),
        "status_chance": _v("status_chance"),
        "flinch_chance": _v("flinch_chance"),
        "confusion_chance": _v("confusion_chance"),
        "forces_switch": _v("forces_switch"),
        "traps_opponent": _v("traps_opponent"),
        "sets_leech_seed": _v("sets_leech_seed"),
        "sets_ingrain": _v("sets_ingrain"),
        "sets_aqua_ring": _v("sets_aqua_ring"),
        "destiny_bond": _v("destiny_bond"),
        "perish_song": 1 if _v("perish_song") else 0,
        "healing_wish": _v("healing_wish"),
        "trick": _v("trick"),
        "bestow": _v("bestow"),
        "recycle": _v("recycle"),
        "knock_off": _v("knock_off"),
    }


def _get_move_effects_impl(move_name: str, battle_state: Any = None) -> Dict[str, Any]:
    """Internal implementation: check battle_state cache, then db_cache, then DB."""
    norm = (move_name or "").lower().replace(" ", "-").strip()
    if battle_state and hasattr(battle_state, "get_cached_move"):
        r = battle_state.get_cached_move(move_name) or battle_state.get_cached_move(norm)
        if r:
            row = dict(r) if hasattr(r, "keys") and not isinstance(r, dict) else r
            return _effects_from_row(row)
    if db_cache and norm:
        r = db_cache.get_cached_move(norm) or db_cache.get_cached_move(move_name)
        if r:
            row = dict(r) if hasattr(r, "keys") and not isinstance(r, dict) else r
            return _effects_from_row(row)
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM moves WHERE LOWER(REPLACE(name, ' ', '-')) = ? LIMIT 1",
                (norm,),
            ).fetchone()
            if not row:
                return {}
            r = dict(row) if hasattr(row, "keys") and not isinstance(row, dict) else row
            return _effects_from_row(r)
    except Exception as e:
        print(f"[ERROR] Failed to get move effects for {move_name}: {e}")
        return {}


@lru_cache(maxsize=1024)
def _get_move_effects_cached(move_name: str) -> Dict[str, Any]:
    return _get_move_effects_impl(move_name, None)


def get_move_effects(move_name: str, battle_state: Any = None) -> Dict[str, Any]:
    """
    Get all effects for a move from the database.
    Uses battle_state move cache when provided, then db_cache, then DB.
    Returns a dictionary with stat_changes, inflicts_status, status_chance, etc.
    """
    if battle_state is not None:
        return _get_move_effects_impl(move_name, battle_state)
    return _get_move_effects_cached(move_name)


def apply_stat_changes(mon: Any, stat_changes: List[Dict], is_opponent: bool = False) -> List[str]:
    """
    Apply stat changes to a Pokémon based on database data.
    stat_changes format: [{"stat": "atk", "amount": 2, "target": "self"/"opponent"}]
    Returns list of messages describing the changes.
    """
    messages = []
    
    # Handle case where stat_changes might not be a list
    if not isinstance(stat_changes, list):
        return messages
    
    for change in stat_changes:
        # Handle case where change might not be a dict
        if not isinstance(change, dict):
            continue
        
        stat = change.get("stat")
        amount = change.get("amount", 0)
        target = change.get("target", "self")
        
        # Skip if this change is for the wrong target
        if (target == "opponent" and not is_opponent) or (target == "self" and is_opponent):
            continue
        
        # Handle random stat boost (Acupressure)
        if stat == "random":
            import random
            stat = random.choice(["atk", "defn", "spa", "spd", "spe"])
        
        # Get current stage
        if not hasattr(mon, 'stages'):
            mon.stages = {"atk": 0, "defn": 0, "spa": 0, "spd": 0, "spe": 0, "accuracy": 0, "evasion": 0}
        
        current = mon.stages.get(stat, 0)
        new_stage = max(-6, min(6, current + amount))
        actual_change = new_stage - current
        
        if actual_change == 0:
            if amount > 0:
                messages.append(f"{mon.species}'s {stat.upper()} won't go any higher!")
            else:
                messages.append(f"{mon.species}'s {stat.upper()} won't go any lower!")
        else:
            mon.stages[stat] = new_stage
            
            # Format message
            stat_names = {
                "atk": "Attack",
                "defn": "Defense",
                "spa": "Sp. Atk",
                "spd": "Sp. Def",
                "spe": "Speed",
                "accuracy": "accuracy",
                "evasion": "evasiveness"
            }
            stat_name = stat_names.get(stat, stat)
            
            if abs(actual_change) == 1:
                change_text = "rose" if actual_change > 0 else "fell"
            elif abs(actual_change) == 2:
                change_text = "sharply rose" if actual_change > 0 else "harshly fell"
            elif abs(actual_change) >= 3:
                change_text = "rose drastically" if actual_change > 0 else "fell severely"
            
            messages.append(f"{mon.species}'s {stat_name} {change_text}!")
    
    return messages


def can_inflict_status(target: Any, status: str, user: Any = None, field_effects: Any = None,
                      from_ability: str = None, target_side: Any = None) -> Tuple[bool, Optional[str]]:
    move_used_norm = ""
    if user is not None and hasattr(user, '_move_being_used') and user._move_being_used:
        move_used_norm = user._move_being_used.lower().replace(" ", "-")

    from .generation import get_generation
    from .abilities import normalize_ability_name, get_ability_effect

    generation = get_generation(field_effects=field_effects)
    target_ability = normalize_ability_name(getattr(target, 'ability', '') or "")
    ability_data = get_ability_effect(target_ability) if target_ability else {}

    # Safeguard protection
    if target_side and getattr(target_side, "safeguard", False):
        bypass = False
        if user is not None and user is not target:
            from .abilities import normalize_ability_name, get_ability_effect
            ability_name = normalize_ability_name(getattr(user, 'ability', '') or "")
            ability_data = get_ability_effect(ability_name)
            if ability_data.get("ignores_screens_substitutes"):
                if generation >= 6:
                    bypass = True
        if not bypass:
            return False, f"{target.species} is protected by Safeguard!"

    """
    Check if a status can be inflicted on a target.
    Returns (can_inflict, reason_if_not)
    
    Args:
        target: The Pokémon to inflict status on
        status: The status to inflict (slp, par, brn, frz, psn, tox)
        user: The user of the move (optional)
        field_effects: Field effects (optional, for weather checks)
        from_ability: The ability causing the status (optional, for generation-specific checks like Static)
    """
    # Check if target already has a status
    # Valid status conditions: "par", "brn", "slp", "frz", "psn", "tox", "sleep", "paralyze", "burn", "freeze", "poison", "toxic"
    # Only consider it as "has a status" if it's a valid status string, not just any truthy value
    valid_statuses = {"par", "brn", "slp", "frz", "psn", "tox", "sleep", "paralyze", "burn", "freeze", "poison", "toxic"}
    current_status = getattr(target, 'status', None)
    # Only check if status exists AND is a valid status (not empty string or None)
    has_valid_status = False
    if current_status:
        status_normalized = str(current_status).lower().strip()
        if status_normalized and status_normalized in valid_statuses:
            has_valid_status = True
    
    if has_valid_status:
        return False, f"{target.species} already has a status condition!"
    
    # === ABILITY STATUS IMMUNITY ===
    if target_ability:
        if "status_immunity" in ability_data:
            immunity_list = ability_data["status_immunity"]
            
            # Check for full immunity (Comatose, Purifying Salt)
            if immunity_list == "all":
                ability_name = target.ability.replace("-", " ").title()
                return False, f"{target.species}'s {ability_name} prevents status conditions!"
            
            # Check specific status immunity
            if isinstance(immunity_list, list) and status in immunity_list:
                ability_name = target.ability.replace("-", " ").title()
                status_names = {
                    "psn": "poison", "tox": "poison", 
                    "par": "paralysis", 
                    "brn": "burn",
                    "frz": "freeze",
                    "slp": "sleep"
                }
                status_readable = status_names.get(status, "that status")
                return False, f"{target.species}'s {ability_name} prevents {status_readable}!"
        
        # Leaf Guard: Prevents status in harsh sunlight
        if ability_data.get("status_immunity_in_sun"):
            weather = getattr(field_effects, 'weather', None) if field_effects else None
            if weather == "sun":
                return False, f"{target.species}'s Leaf Guard prevents status conditions in harsh sunlight!"
    
    # Type immunities
    if status in ["par", "paralysis"]:
        types = [getattr(target, 'type1', None), getattr(target, 'type2', None)]

        if generation >= 6 and "Electric" in types:
            return False, f"{target.species} is immune to paralysis!"
        
        # Gen 3: Static CAN paralyze Ground types (exception to normal immunity)
        # Gen 4+: Ground types are immune to paralysis from contact abilities
        if from_ability == "static":
            if generation >= 4 and "Ground" in [getattr(target, 'type1', None), getattr(target, 'type2', None)]:
                return False, f"{target.species} is immune to paralysis!"
            # Gen 3: Ground types CAN be paralyzed by Static (no check needed, allow it)
        
        if move_used_norm == "lick" and "Ghost" in types:
            if generation == 1:
                return False, f"It doesn't affect {target.species}!"
        elif move_used_norm == "glare" and "Ghost" in types and 2 <= generation <= 3:
            return False, f"It doesn't affect {target.species}!"
    
    elif status in ["psn", "poison", "tox", "toxic"]:
        # Poison and Steel types can't be poisoned
        types = [getattr(target, 'type1', None), getattr(target, 'type2', None)]
        if "Poison" in types or "Steel" in types:
            return False, f"{target.species} is immune to poison!"
        
        # Pastel Veil: Prevents poisoning
        if target_ability == "pastel-veil":
            return False, f"{target.species}'s Pastel Veil prevents poisoning!"
    
    elif status in ["brn", "burn"]:
        # Thermal Exchange: Prevents burn (Gen 9+)
        if target_ability == "thermal-exchange":
            if generation >= 9:
                return False, f"{target.species}'s Thermal Exchange prevents burns!"
        
        # Fire types can't be burned
        if "Fire" in [getattr(target, 'type1', None), getattr(target, 'type2', None)]:
            return False, f"{target.species} is immune to burn!"
    
    elif status in ["frz", "freeze"]:
        # Ice types can't be frozen
        if "Ice" in [getattr(target, 'type1', None), getattr(target, 'type2', None)]:
            return False, f"{target.species} is immune to freeze!"
    
    elif status in ["slp", "sleep"]:
        # Spore/Cotton Spore: Gen VI+ Grass types are immune, Overcoat immunity, Safety Goggles immunity
        if user:
            # Get move name from user
            move_name_norm = ""
            if hasattr(user, '_move_being_used'):
                move_name_norm = user._move_being_used.lower().replace(" ", "-")
            elif hasattr(user, 'last_move_used'):
                move_name_norm = user.last_move_used.lower().replace(" ", "-")
            
            if move_name_norm == "spore":
                generation_spore = get_generation(field_effects=field_effects) if field_effects else 9
                if generation_spore >= 6:
                    # Check if target is Grass type
                    types = [getattr(target, 'type1', None), getattr(target, 'type2', None)]
                    if "Grass" in types:
                        return False, f"{target.species} is immune to Spore!"
                    # Check Overcoat
                    if target_ability == "overcoat":
                        return False, f"{target.species}'s Overcoat prevents Spore!"
                    # Safety Goggles check would be in item effects (handled elsewhere)
        
        # Terrain effects: Electric Terrain and Misty Terrain prevent sleep for grounded Pokémon
        if field_effects:
            terrain = getattr(field_effects, 'terrain', None)
            if terrain in ["electric", "misty"]:
                from .engine import is_grounded
                if is_grounded(target, field_gravity=getattr(field_effects, 'gravity', False)):
                    terrain_name = "Electric" if terrain == "electric" else "Misty"
                    return False, f"{terrain_name} Terrain prevents sleep!"
    
    # Misty Terrain: Prevents all non-volatile status conditions for grounded Pokémon (Gen 7+)
    # Note: Confusion is handled separately in can_inflict_confusion, but Misty Terrain also blocks it
    if field_effects:
        terrain = getattr(field_effects, 'terrain', None)
        if terrain == "misty":
            from .engine import is_grounded
            from .generation import get_generation
            gen_check = get_generation(field_effects=field_effects)
            if gen_check >= 7:  # Misty Terrain status prevention is Gen 7+
                if is_grounded(target, field_gravity=getattr(field_effects, 'gravity', False)):
                    return False, "Misty Terrain prevents status conditions!"
    
    return True, None


def can_inflict_confusion(target: Any, field_effects: Any = None) -> Tuple[bool, Optional[str]]:
    """
    Check if confusion can be inflicted on a target.
    Returns (can_inflict, reason_if_not)
    """
    # Check if already confused
    if hasattr(target, 'confused') and target.confused:
        return False, f"{target.species} is already confused!"
    
    # Check for Own Tempo (confusion immunity)
    if hasattr(target, 'ability') and target.ability:
        from .abilities import normalize_ability_name, get_ability_effect
        ability = normalize_ability_name(target.ability)
        ability_data = get_ability_effect(ability)
        if ability_data.get("confusion_immunity"):
            ability_name = target.ability.replace("-", " ").title()
            return False, f"{target.species}'s {ability_name} prevents confusion!"
    
    # Misty Terrain: Prevents confusion for grounded Pokémon (Gen 7+)
    if field_effects:
        terrain = getattr(field_effects, 'terrain', None)
        if terrain == "misty":
            from .engine import is_grounded
            from .generation import get_generation
            gen_check = get_generation(field_effects=field_effects)
            if gen_check >= 7:  # Misty Terrain confusion prevention is Gen 7+
                if is_grounded(target, field_gravity=getattr(field_effects, 'gravity', False)):
                    return False, "Misty Terrain prevents confusion!"
    
    return True, None


def apply_confusion(target: Any, *, target_side: Any = None, user: Any = None, field_effects: Any = None) -> Tuple[bool, str]:
    """
    Apply confusion to a target.
    Returns (success, message)
    """
    # Check if confusion can be inflicted
    can_inflict, reason = can_inflict_confusion(target, field_effects=field_effects)
    if not can_inflict:
        return False, reason

    if target_side and getattr(target_side, "safeguard", False):
        bypass = False
        if user is not None and user is not target:
            from .abilities import normalize_ability_name, get_ability_effect
            ability_norm = normalize_ability_name(getattr(user, 'ability', '') or "")
            ability_data = get_ability_effect(ability_norm)
            if ability_data.get("ignores_screens_substitutes"):
                from .generation import get_generation
                generation = get_generation(field_effects=field_effects)
                if generation >= 6:
                    bypass = True
        if not bypass:
            return False, f"{target.species} is protected by Safeguard!"
    
    # Inflict confusion (1-4 turns, random)
    import random
    target.confused = True
    target.confusion_turns = random.randint(1, 4)
    # Mark that confusion was applied this turn - don't decrement until next turn
    target._confusion_applied_this_turn = True
    
    msg = f"{target.species} became **confused**!"
    
    # Check for Persim Berry or Lum Berry
    target_item = (target.item or "").lower().replace(" ", "-")
    if target_item in ["persim-berry", "lum-berry"]:
        target.confused = False
        target.confusion_turns = 0
        target._last_consumed_berry = target.item  # Store for Harvest
        target.item = None  # Consume berry
        berry_name = "Persim Berry" if target_item == "persim-berry" else "Lum Berry"
        msg += f"\n{target.species}'s {berry_name} cured its confusion!"
        
        # Cheek Pouch: Restore 33% HP after berry effect
        from .abilities import normalize_ability_name, get_ability_effect
        if hasattr(target, 'ability') and target.ability:
            ability = normalize_ability_name(target.ability)
            ability_data = get_ability_effect(ability)
            if "berry_heal_bonus" in ability_data:
                extra_heal = int(target.max_hp * ability_data["berry_heal_bonus"])
                target.hp = min(target.max_hp, target.hp + extra_heal)
                msg += f"\n{target.species}'s Cheek Pouch restored {extra_heal} HP!"
    
    return True, msg


def can_apply_flinch(target: Any, field_effects: Any = None, is_from_move: bool = True) -> Tuple[bool, Optional[str]]:
    """
    Check if a flinch can be applied to a target.
    Returns (can_flinch, reason_if_not)
    
    Generation differences:
    - Gen 2: Sleeping/Frozen Pokemon can't flinch from moves (but CAN from King's Rock)
    - Gen 3+: Sleeping/Frozen Pokemon can flinch
    - Gen 9+: Covert Cloak grants immunity
    """
    # Check if target has Inner Focus or similar flinch immunity
    if hasattr(target, 'ability') and target.ability:
        from .abilities import normalize_ability_name, get_ability_effect
        ability = normalize_ability_name(target.ability)
        ability_data = get_ability_effect(ability)
        if ability_data.get("flinch_immunity"):
            ability_name = target.ability.replace("-", " ").title()
            return False, f"{target.species}'s {ability_name} prevents flinching!"
        
        # Shield Dust: Blocks flinching from moves (not items like King's Rock)
        if ability_data.get("secondary_effect_immunity") and is_from_move:
            ability_name = target.ability.replace("-", " ").title()
            return False, f"{target.species}'s {ability_name} prevents flinching!"
    
    # Gen 9+: Covert Cloak blocks flinching
    from .generation import get_generation
    generation = get_generation(field_effects=field_effects)
    
    if generation >= 9 and hasattr(target, 'item') and target.item:
        from .items import get_item_effect, normalize_item_name
        item_data = get_item_effect(normalize_item_name(target.item))
        if item_data.get("flinch_immunity"):
            return False, f"{target.species}'s Covert Cloak prevents flinching!"
    
    # Gen 2: Sleeping/Frozen Pokemon can't flinch from moves (but CAN from King's Rock)
    if generation == 2 and is_from_move and hasattr(target, 'status') and target.status:
        status = target.status.lower()
        if status in ["slp", "sleep", "frz", "freeze"]:
            return False, None  # Silent failure
    
    return True, None


def apply_flinch(attacker: Any, target: Any, move_has_flinch: bool, flinch_chance: float, 
                 field_effects: Any = None, is_multistrike: bool = False, 
                 is_final_strike: bool = True, serene_grace: bool = False,
                 move_name: Optional[str] = None) -> Tuple[bool, str]:
    """
    Apply flinch to a target with generation-aware logic.
    Returns (success, message)
    
    Generation differences:
    - Gen 2: King's Rock 12%, only final strike of multistrike
    - Gen 3-4: King's Rock/Razor Fang 10%, each strike independent
    - Gen 5-8: Stench 10%, King's Rock/Razor Fang only on non-flinch moves
    - Gen 9+: Covert Cloak immunity
    """
    from .generation import get_generation
    generation = get_generation(field_effects=field_effects)
    
    # Determine if flinch can be applied
    is_from_move = move_has_flinch
    can_flinch, reason = can_apply_flinch(target, field_effects, is_from_move)
    
    if not can_flinch:
        return False, reason or ""
    
    # Calculate final flinch chance
    final_flinch_chance = 0.0
    
    # Move's base flinch chance
    move_name_lower = move_name.lower().replace(" ", "-") if move_name else ""

    if move_has_flinch:
        final_flinch_chance = flinch_chance
        # In Gen 5+, King's Rock doesn't add flinch if move already has it
        # So we skip King's Rock check if move already has flinch (Gen 5+)
        skip_kings_rock = (generation >= 5)
    else:
        skip_kings_rock = False

    if move_name_lower == "pursuit" and 3 <= generation <= 4:
        skip_kings_rock = True
    if move_name_lower == "dragon-breath" and generation <= 2:
        skip_kings_rock = True
    if move_name_lower == "twister" and generation >= 5:
        skip_kings_rock = True

    # Giga Drain: King's Rock interactions change between generations
    if move_name_lower == "giga-drain":
        if 3 <= generation <= 4:
            skip_kings_rock = True
        elif generation >= 5:
            skip_kings_rock = False
    
    # === KING'S ROCK / RAZOR FANG: Add flinch chance (generation-specific) ===
    # Only check if move doesn't already have flinch (or in earlier gens where it can add to existing)
    if not skip_kings_rock and hasattr(attacker, 'item') and attacker.item:
        from .items import get_item_effect, normalize_item_name
        from .engine import item_is_active
        if item_is_active(attacker):
            item_norm = normalize_item_name(attacker.item)
            item_data = get_item_effect(item_norm)
            
            if item_data.get("adds_flinch"):
                min_gen = item_data.get("min_gen", 2)
                if generation >= min_gen:
                    gen_specific = item_data.get("gen_specific", {})
                    
                    # Check Sheer Force negation (Gen 5+)
                    has_sheer_force = False
                    if generation >= 5 and hasattr(attacker, 'ability') and attacker.ability:
                        from .abilities import normalize_ability_name, get_ability_effect
                        ability_kr = normalize_ability_name(attacker.ability)
                        ability_data_kr = get_ability_effect(ability_kr)
                        if ability_data_kr.get("removes_secondary_effects"):
                            has_sheer_force = True
                    
                    if item_data.get("gen_specific", {}).get("5+", {}).get("sheer_force_negates") and has_sheer_force:
                        pass  # Don't add flinch
                    else:
                        # Gen 2: King's Rock only (no Razor Fang), 30/256 (11.71875%) chance, only final hit of multistrike
                        if generation == 2 and "2" in gen_specific:
                            gen2_data = gen_specific["2"]
                            if item_norm == "kings-rock":
                                # Only on final hit of multistrike moves
                                if gen2_data.get("final_hit_only"):
                                    if not is_multistrike or is_final_strike:
                                        final_flinch_chance = gen2_data.get("flinch_chance", 30/256)
                                else:
                                    final_flinch_chance = gen2_data.get("flinch_chance", 30/256)
                        
                        # Gen 3-4: King's Rock/Razor Fang (10% each hit, not affected by Serene Grace)
                        elif 3 <= generation <= 4 and "3-4" in gen_specific:
                            gen34_data = gen_specific["3-4"]
                            # Each hit independent check
                            final_flinch_chance = gen34_data.get("flinch_chance", 0.1)
                            # Note: Serene Grace doesn't affect it in Gen 3-4
                        
                        # Gen 5+: King's Rock/Razor Fang on ALL attacking moves without flinch
                        elif generation >= 5 and "5+" in gen_specific:
                            gen5_data = gen_specific["5+"]
                            # Only if move doesn't already have flinch (already checked via skip_kings_rock)
                            # Exception: Waterfall is not affected by King's Rock in Gen V+ (even though it has flinch)
                            # This is already handled by skip_kings_rock = True when move_has_flinch = True
                            if gen5_data.get("all_attacking_moves"):
                                final_flinch_chance = gen5_data.get("flinch_chance", 0.1)
                                # Serene Grace will double it later (if applicable)
    
    # Gen 5-8: Stench ability (only if move doesn't already have flinch)
    if 5 <= generation <= 8:
        if final_flinch_chance == 0.0 and hasattr(attacker, 'ability') and attacker.ability and not move_has_flinch:
            from .abilities import normalize_ability_name, get_ability_effect
            ability_stench = normalize_ability_name(attacker.ability)
            ability_data_stench = get_ability_effect(ability_stench)
            if "flinch_chance_boost" in ability_data_stench:
                final_flinch_chance = ability_data_stench["flinch_chance_boost"]
    
    # Gen 9+: Stench ability (only if move doesn't already have flinch)
    elif generation >= 9:
        if final_flinch_chance == 0.0 and hasattr(attacker, 'ability') and attacker.ability and not move_has_flinch:
            from .abilities import normalize_ability_name, get_ability_effect
            ability_stench = normalize_ability_name(attacker.ability)
            ability_data_stench = get_ability_effect(ability_stench)
            if "flinch_chance_boost" in ability_data_stench:
                final_flinch_chance = ability_data_stench["flinch_chance_boost"]
    
    # Serene Grace: Double flinch chance (Gen 5+)
    if serene_grace and generation >= 5:
        final_flinch_chance *= 2.0
    
    # Cap at 100%
    final_flinch_chance = min(1.0, final_flinch_chance)
    
    # Roll for flinch
    if final_flinch_chance > 0:
        import random
        if random.random() < final_flinch_chance:
            target.flinched = True
            
            # Steadfast: +1 Speed when flinched (Gen 4+)
            if hasattr(target, 'ability') and target.ability:
                from .abilities import normalize_ability_name
                target_ability = normalize_ability_name(target.ability)
                if target_ability == "steadfast" and generation >= 4:
                    old_stage = target.stages.get("spe", 0)
                    if old_stage < 6:
                        target.stages["spe"] = old_stage + 1
                        return True, f"**{target.species}** flinched!\n{target.species}'s Steadfast raised its Speed!"
            
            return True, f"**{target.species}** flinched!"
    
    return False, ""


def apply_status_effect(target: Any, status: str, user: Any = None, field_effects: Any = None,
                       target_side: Any = None) -> Tuple[bool, str]:
    """
    Apply a status effect to a target.
    Returns (success, message)
    
    Args:
        target: The Pokémon to inflict status on
        status: The status to inflict
        user: The user of the move (optional)
        field_effects: Field effects (optional, for weather checks)
    """
    # Check if status can be inflicted
    can_inflict, reason = can_inflict_status(target, status, user, field_effects, target_side=target_side)
    
    if not can_inflict:
        return False, reason
    
    # Inflict the status
    target.status = status
    
    if status in ["slp", "sleep"]:
        import random
        from .generation import get_generation
        
        # Get generation for sleep duration
        generation = get_generation(field_effects=field_effects)
        
        # Check if this is from Rest
        # Gen I: Sleep 2 turns (counting the turn when Rest is used), wake on 3rd turn, attack on 4th turn
        # Gen II-VIII: Sleep 3 turns (counting the turn when Rest is used), attack on 4th turn (same turn it wakes up)
        # The user is unable to use moves while asleep for 2 turns AFTER the turn when Rest is used
        is_from_rest = getattr(target, '_sleep_from_rest', False)
        if is_from_rest:
            if generation == 1:
                sleep_turns = 2  # Gen 1 Rest: 2 turns (wake on 3rd, attack on 4th)
            else:
                sleep_turns = 3  # Gen 2+ Rest: 3 turns (wake and attack on 4th)
            # Clear the flag
            if hasattr(target, '_sleep_from_rest'):
                delattr(target, '_sleep_from_rest')
        else:
            # Generation-specific sleep duration (random sleep from moves)
            if generation == 1:
                sleep_turns = random.randint(1, 7)  # Gen 1: 1-7 turns
            elif generation == 2:
                sleep_turns = random.randint(2, 8)  # Gen 2: 2-8 turns
            elif generation == 3 or generation == 4:
                sleep_turns = random.randint(2, 5)  # Gen 3-4: 2-5 turns
            else:  # Gen 5+
                # Gen 5+: 2-4 turns (equal chance for each)
                sleep_turns = random.choice([2, 3, 4])
            
            # Early Bird: Halve sleep duration (rounded down, minimum 1)
            from .abilities import normalize_ability_name, get_ability_effect
            if hasattr(target, 'ability') and target.ability:
                ability = normalize_ability_name(target.ability)
                ability_data = get_ability_effect(ability)
                if ability_data.get("sleep_duration_halved"):
                    sleep_turns = max(1, sleep_turns // 2)
        
        target.status_turns = sleep_turns
        # Store original sleep turns for Gen V reset on switch
        target._original_sleep_turns = sleep_turns
        # Mark that sleep was applied this turn
        # For Rest (self-inflicted): sleep counter starts immediately (decrements this turn)
        # For other moves (opponent-inflicted): sleep counter starts NEXT turn (don't decrement this turn)
        # Use is_from_rest (stored before flag deletion) instead of checking the flag again
        if not is_from_rest:
            # Opponent-inflicted sleep: don't decrement on the turn it's applied
            target._sleep_applied_this_turn = True
        # Rest: _sleep_applied_this_turn is NOT set, so it will decrement immediately
    elif status in ["tox", "toxic"]:
        target.toxic_counter = 1  # Toxic damage counter
    
    # Status names for messages
    status_names = {
        "par": "paralyzed",
        "brn": "burned",
        "psn": "poisoned",
        "tox": "badly poisoned",
        "frz": "frozen",
        "slp": "fell asleep"
    }
    
    # Sleep uses different message format (no "was")
    if status in ["slp", "sleep"]:
        msg = f"{target.species} **{status_names.get(status, 'fell asleep')}**!"
    else:
        msg = f"{target.species} was **{status_names.get(status, 'affected')}**!"
    
    # === CHECK FOR STATUS-CURING BERRIES ===
    target_item = (target.item or "").lower().replace(" ", "-")
    berry_cures = {
        "cheri-berry": ["par", "paralysis"],
        "chesto-berry": ["slp", "sleep"],
        "pecha-berry": ["psn", "poison", "tox", "toxic"],
        "rawst-berry": ["brn", "burn"],
        "aspear-berry": ["frz", "freeze"],
        "lum-berry": ["par", "brn", "psn", "tox", "frz", "slp", "paralysis", "burn", "poison", "toxic", "freeze", "sleep"]
    }
    
    # Check if the Pokémon has a berry that cures this status
    if target_item in berry_cures:
        if status in berry_cures[target_item]:
            # Cure the status immediately
            target.status = None
            target._last_consumed_berry = target.item  # Store for Harvest
            target.item = None  # Consume the berry
            berry_names = {
                "cheri-berry": "Cheri Berry",
                "chesto-berry": "Chesto Berry",
                "pecha-berry": "Pecha Berry",
                "rawst-berry": "Rawst Berry",
                "aspear-berry": "Aspear Berry",
                "lum-berry": "Lum Berry"
            }
            msg += f"\n{target.species}'s {berry_names.get(target_item, target_item)} cured its status!"
            
            # Cheek Pouch: Restore 33% HP after berry effect
            from .abilities import normalize_ability_name, get_ability_effect
            if hasattr(target, 'ability') and target.ability:
                ability = normalize_ability_name(target.ability)
                ability_data = get_ability_effect(ability)
                if "berry_heal_bonus" in ability_data:
                    extra_heal = int(target.max_hp * ability_data["berry_heal_bonus"])
                    target.hp = min(target.max_hp, target.hp + extra_heal)
                    msg += f"\n{target.species}'s Cheek Pouch restored {extra_heal} HP!"
    
    return True, msg


def check_and_consume_hp_berries(mon: Any) -> Optional[str]:
    """
    Check if a Pokémon should consume an HP-restoring berry.
    Returns a message if a berry was consumed, None otherwise.
    """
    if not mon.item or mon.hp <= 0 or mon.hp == mon.max_hp:
        return None
    
    mon_item = (mon.item or "").lower().replace(" ", "-")
    
    # Check if Pokémon has Cheek Pouch or Ripen ability
    from .abilities import normalize_ability_name, get_ability_effect
    has_cheek_pouch = False
    cheek_pouch_bonus = 0
    berry_multiplier = 1.0  # Ripen doubles berry effects
    
    if hasattr(mon, 'ability') and mon.ability:
        ability = normalize_ability_name(mon.ability)
        ability_data = get_ability_effect(ability)
        if "berry_heal_bonus" in ability_data:
            has_cheek_pouch = True
            cheek_pouch_bonus = ability_data["berry_heal_bonus"]
        if "berry_effect_mult" in ability_data:
            berry_multiplier = ability_data["berry_effect_mult"]  # 2.0 for Ripen
    
    # === SITRUS BERRY: Restores 25% HP when below 50% HP ===
    if mon_item == "sitrus-berry" and mon.hp <= mon.max_hp // 2:
        heal = int(mon.max_hp * 0.25 * berry_multiplier)  # Doubled by Ripen
        mon.hp = min(mon.max_hp, mon.hp + heal)
        mon._last_consumed_berry = mon.item  # Store for Harvest
        mon.item = None  # Consume berry
        msg = f"{mon.species}'s Sitrus Berry restored {heal} HP!"
        
        # Cheek Pouch: Restore additional 33% HP after berry effect
        if has_cheek_pouch:
            extra_heal = int(mon.max_hp * cheek_pouch_bonus)
            mon.hp = min(mon.max_hp, mon.hp + extra_heal)
            msg += f"\n{mon.species}'s Cheek Pouch restored {extra_heal} more HP!"
        
        return msg
    
    # === ORAN BERRY: Restores 10 HP when below 50% HP ===
    if mon_item == "oran-berry" and mon.hp <= mon.max_hp // 2:
        heal = int(10 * berry_multiplier)  # Doubled by Ripen
        actual_heal = min(heal, mon.max_hp - mon.hp)
        mon.hp = min(mon.max_hp, mon.hp + actual_heal)
        mon._last_consumed_berry = mon.item  # Store for Harvest
        mon.item = None  # Consume berry
        msg = f"{mon.species}'s Oran Berry restored {actual_heal} HP!"
        
        # Cheek Pouch: Restore additional 33% HP after berry effect
        if has_cheek_pouch:
            extra_heal = int(mon.max_hp * cheek_pouch_bonus)
            mon.hp = min(mon.max_hp, mon.hp + extra_heal)
            msg += f"\n{mon.species}'s Cheek Pouch restored {extra_heal} more HP!"
        
        return msg
    
    # === FIGY/WIKI/MAGO/AGUAV/IAPAPA (confusion berries with gen-based amounts) ===
    # Gen 3-6: Heal 1/8 at <= 1/2 HP; causes confusion if nature dislikes flavor
    # Gen 7: Heal 1/2 at <= 1/4 HP (Gluttony: 1/2 at 1/2 HP)
    # Gen 8+: Heal 1/3 at <= 1/4 HP (Ripen doubles to 2/3; Gluttony raises threshold)
    if mon_item in {"figy-berry", "wiki-berry", "mago-berry", "aguav-berry", "iapapa-berry"}:
        # Determine generation
        from .generation import get_generation
        generation = get_generation()
        # Threshold (default per gen), allow Gluttony override via berry_threshold ability flag
        if generation <= 6:
            threshold = mon.max_hp // 2
            heal_ratio = 1/8
        elif generation == 7:
            threshold = mon.max_hp // 4
            heal_ratio = 1/2
        else:  # gen 8+
            threshold = mon.max_hp // 4
            heal_ratio = 1/3
        # Gluttony/other overrides
        if hasattr(mon, 'ability') and mon.ability:
            from .abilities import normalize_ability_name, get_ability_effect
            ability = normalize_ability_name(mon.ability)
            ability_data = get_ability_effect(ability)
            if ability_data.get("berry_threshold"):
                threshold = int(mon.max_hp * ability_data["berry_threshold"])  # e.g., 0.5
        if mon.hp <= threshold:
            heal = int(mon.max_hp * heal_ratio * berry_multiplier)
            actual_heal = min(heal, mon.max_hp - mon.hp)
            if actual_heal > 0:
                mon.hp = min(mon.max_hp, mon.hp + actual_heal)
            mon._last_consumed_berry = mon.item
            mon.item = None
            berry_display = mon_item.replace('-', ' ').title()
            msg = f"{mon.species}'s {berry_display} restored {actual_heal} HP!"
            # Confusion if nature dislikes the flavor (only if healed and nature exists)
            nature = getattr(mon, 'nature_name', None)
            if nature:
                nature = nature.lower().replace(' ', '-')
                lower_map = {
                    # Natures that lower Attack
                    "atk": {"bold", "timid", "modest", "calm"},
                    # Natures that lower Defense
                    "defn": {"lonely", "mild", "hasty", "gentle"},
                    # Natures that lower Sp. Atk
                    "spa": {"adamant", "jolly", "impish", "careful"},
                    # Natures that lower Sp. Def
                    "spd": {"naughty", "rash", "naive", "lax"},
                    # Natures that lower Speed
                    "spe": {"brave", "quiet", "relaxed", "sassy"},
                }
                # Map berry to stat key stored in items.py
                berry_to_stat = {
                    "figy-berry": "atk",
                    "wiki-berry": "spa",
                    "mago-berry": "spe",
                    "aguav-berry": "spd",
                    "iapapa-berry": "defn",
                }
                stat_key = berry_to_stat.get(mon_item)
                if stat_key and nature in lower_map.get(stat_key, set()):
                    # Inflict confusion (only if not already confused)
                    if not getattr(mon, 'confused', False):
                        mon.confused = True
                        # 1-4 turns typical; we can set 1-4 randomly
                        import random
                        mon.confusion_turns = random.randint(1, 4)
                        mon._confusion_applied_this_turn = True
                        msg += f"\n{mon.species} became confused!"
            # Cheek Pouch: extra heal
            if has_cheek_pouch:
                extra_heal = int(mon.max_hp * cheek_pouch_bonus)
                mon.hp = min(mon.max_hp, mon.hp + extra_heal)
                msg += f"\n{mon.species}'s Cheek Pouch restored {extra_heal} more HP!"
            return msg

    # === CUSTAP BERRY: Move first in priority bracket (consumed at low HP) ===
    if mon_item == "custap-berry":
        # Threshold defaults to 25% HP; Gluttony raises to 50% via berry_threshold already handled
        threshold = mon.max_hp // 4
        from .abilities import normalize_ability_name, get_ability_effect
        if hasattr(mon, 'ability') and mon.ability:
            ability = normalize_ability_name(mon.ability)
            ability_data = get_ability_effect(ability)
            if ability_data.get("berry_threshold"):
                threshold = int(mon.max_hp * ability_data["berry_threshold"])  # e.g., 0.5
        if mon.hp <= threshold:
            mon._last_consumed_berry = mon.item
            mon.item = None
            # Flag consumed effect for turn ordering
            setattr(mon, "_custap_active", True)
            msg = f"{mon.species} used its Custap Berry to move first!"
            return msg

    # === LANSAT BERRY: +2 crit stages at low HP (not doubled by Ripen) ===
    if mon_item == "lansat-berry":
        threshold = mon.max_hp // 4
        from .abilities import normalize_ability_name, get_ability_effect
        if hasattr(mon, 'ability') and mon.ability:
            ability = normalize_ability_name(mon.ability)
            ability_data = get_ability_effect(ability)
            if ability_data.get("berry_threshold"):
                threshold = int(mon.max_hp * ability_data["berry_threshold"])  # e.g., 0.5
        if mon.hp <= threshold:
            mon._last_consumed_berry = mon.item
            mon.item = None
            # Reuse focused_energy flag to represent +2 crit stages
            mon.focused_energy = True
            msg = f"{mon.species}'s Lansat Berry sharply raised its critical-hit ratio!"
            # Cheek Pouch bonus heal if present
            if has_cheek_pouch:
                extra_heal = int(mon.max_hp * cheek_pouch_bonus)
                mon.hp = min(mon.max_hp, mon.hp + extra_heal)
                msg += f"\n{mon.species}'s Cheek Pouch restored {extra_heal} HP!"
            return msg

    # === PINCH BERRIES: Boost stats when HP < 25% (or 50% with Gluttony) ===
    pinch_berries = {
        "liechi-berry": "atk",  # Boosts Attack
        "petaya-berry": "spa",  # Boosts Sp. Atk
        "salac-berry": "spe",   # Boosts Speed
        "ganlon-berry": "defn", # Boosts Defense
        "apicot-berry": "spd",  # Boosts Sp. Def
        "lansat-berry": "crit", # Raises critical hit ratio (special handling)
        "starf-berry": "random", # Raises random stat sharply (special handling)
        "micle-berry": "accuracy", # Raises accuracy (special handling)
        "custap-berry": "priority", # Priority boost (special handling in move selection)
    }
    
    # Check for Gluttony ability (eats berries at 50% instead of 25%)
    berry_threshold = mon.max_hp // 4  # Default: 25%
    if hasattr(mon, 'ability') and mon.ability:
        from .abilities import normalize_ability_name, get_ability_effect
        ability = normalize_ability_name(mon.ability)
        ability_data = get_ability_effect(ability)
        if ability_data.get("berry_threshold"):
            berry_threshold = int(mon.max_hp * ability_data["berry_threshold"])
    
    if mon_item in pinch_berries and mon.hp <= berry_threshold:
        stat = pinch_berries[mon_item]
        berry_display = mon_item.replace('-', ' ').title()
        # Special handling for Micle and Starf
        if stat == "accuracy":
            # Micle Berry: boost next move accuracy
            from .generation import get_generation
            generation = get_generation()
            mon._last_consumed_berry = mon.item
            mon.item = None
            # Mark boost active; apply in accuracy check and then clear
            mon._micle_active = True
            mon._micle_multiplier = (4915 / 4096) if generation >= 5 else 1.2
            msg = f"{mon.species}'s {berry_display} raised its accuracy!"
            if has_cheek_pouch:
                extra_heal = int(mon.max_hp * cheek_pouch_bonus)
                mon.hp = min(mon.max_hp, mon.hp + extra_heal)
                msg += f"\n{mon.species}'s Cheek Pouch restored {extra_heal} HP!"
            return msg
        if stat == "random":
            # Starf Berry: randomly raise one stat by 2 (or 4 with Ripen)
            import random
            stats_pool = ["atk", "defn", "spa", "spd", "spe"]
            chosen = random.choice(stats_pool)
            if not hasattr(mon, 'stages'):
                mon.stages = {"atk": 0, "defn": 0, "spa": 0, "spd": 0, "spe": 0, "accuracy": 0, "evasion": 0}
            boost_amount = 4 if berry_multiplier > 1.0 else 2
            old_stage = mon.stages.get(chosen, 0)
            mon.stages[chosen] = min(6, old_stage + boost_amount)
            mon._last_consumed_berry = mon.item
            mon.item = None
            stat_names = {"atk": "Attack", "defn": "Defense", "spa": "Sp. Atk", "spd": "Sp. Def", "spe": "Speed"}
            msg = f"{mon.species}'s {berry_display} sharply raised its {stat_names[chosen]}!"
            if has_cheek_pouch:
                extra_heal = int(mon.max_hp * cheek_pouch_bonus)
                mon.hp = min(mon.max_hp, mon.hp + extra_heal)
                msg += f"\n{mon.species}'s Cheek Pouch restored {extra_heal} HP!"
            return msg
        # Standard pinch berry stat raise
        if not hasattr(mon, 'stages'):
            mon.stages = {"atk": 0, "defn": 0, "spa": 0, "spd": 0, "spe": 0, "accuracy": 0, "evasion": 0}
        if mon.stages[stat] < 6:
            stat_boost = 1
            if berry_multiplier > 1.0 and mon_item != "lansat-berry":
                stat_boost = int(1 * berry_multiplier)
            mon.stages[stat] = min(6, mon.stages[stat] + stat_boost)
            mon._last_consumed_berry = mon.item
            mon.item = None
            stat_names = {"atk": "Attack", "defn": "Defense", "spa": "Sp. Atk", "spd": "Sp. Def", "spe": "Speed"}
            if stat_boost >= 2:
                msg = f"{mon.species}'s {berry_display} sharply raised its {stat_names[stat]}!"
            else:
                msg = f"{mon.species}'s {berry_display} raised its {stat_names[stat]}!"
            if has_cheek_pouch:
                extra_heal = int(mon.max_hp * cheek_pouch_bonus)
                mon.hp = min(mon.max_hp, mon.hp + extra_heal)
                msg += f"\n{mon.species}'s Cheek Pouch restored {extra_heal} HP!"
            return msg
    
    return None


def get_berry_effect(berry_name: str) -> Dict[str, Any]:
    """
    Get the effects of a berry for use with moves like Bug Bite and Pluck.
    Returns a dictionary with berry effect data.
    """
    berry_name = berry_name.lower().replace(" ", "-")
    
    # HP-restoring berries
    hp_berries = {
        "oran-berry": {"restores_hp": True, "heal_amount": 10},
        "sitrus-berry": {"restores_hp": True, "heal_amount": 0.25},  # 25% max HP
        "figy-berry": {"restores_hp": True, "heal_amount": 0.33},
        "wiki-berry": {"restores_hp": True, "heal_amount": 0.33},
        "mago-berry": {"restores_hp": True, "heal_amount": 0.33},
        "aguav-berry": {"restores_hp": True, "heal_amount": 0.33},
        "iapapa-berry": {"restores_hp": True, "heal_amount": 0.33},
    }
    
    # Status-curing berries
    status_berries = {
        "cheri-berry": {"cures_status": "par"},
        "chesto-berry": {"cures_status": "slp"},
        "pecha-berry": {"cures_status": "psn"},
        "rawst-berry": {"cures_status": "brn"},
        "aspear-berry": {"cures_status": "frz"},
        "persim-berry": {"cures_status": "confusion"},
        "lum-berry": {"cures_status": "any"},
    }
    
    # Check both dictionaries
    if berry_name in hp_berries:
        return hp_berries[berry_name]
    elif berry_name in status_berries:
        return status_berries[berry_name]
    else:
        return {}

