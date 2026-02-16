"""
Special Move Implementations
Handles all moves that require custom logic beyond standard damage calculation.
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple
import random

from .abilities import normalize_ability_name, get_ability_effect
from .generation import get_generation
from .items import get_item_effect, normalize_item_name

def check_fake_out_family(move_name: str, user: Any, battle_state: Any) -> Tuple[bool, Optional[str]]:
    """
    Check if Fake Out/First Impression can be used.
    These moves only work on the first turn after switching in.
    When a Pokémon switches out and back in, the counter is reset, allowing Fake Out to work again.
    
    Returns: (can_use, failure_message)
    """
    move_lower = move_name.lower().replace(" ", "-")
    
    if move_lower in ["fake-out", "first-impression", "mat-block"]:
        # Check if this is the first turn since the Pokémon entered battle
        # Initialize to 0 if not set (should be set when switching in, but ensure it exists)
        if not hasattr(user, '_turns_since_switch_in'):
            user._turns_since_switch_in = 0
        
        # Fake Out works only when counter is exactly 0 (the turn the Pokémon switches in)
        # Counter is reset to 0 when switching in, then incremented at end of turn
        turns_since_switch = getattr(user, '_turns_since_switch_in', 0)
        if turns_since_switch > 0:
            return False, f"But it failed! {move_name} only works on the first turn!"
        
        return True, None
    
    return True, None

def check_sucker_punch(move_name: str, user: Any, target: Any, target_choice: Optional[Dict]) -> Tuple[bool, Optional[str]]:
    """
    Check if Sucker Punch can be used.
    Only works if the target is about to use a damaging move.
    
    Returns: (can_use, failure_message)
    """
    move_lower = move_name.lower().replace(" ", "-")
    
    if move_lower == "sucker-punch":
        # Check if target is using a damaging move
        if not target_choice or target_choice.get("kind") != "move":
            return False, f"But it failed! {target.species} isn't attacking!"
        
        # Check if target's move is damaging
        target_move = target_choice.get("value", "")
        from .moves_loader import get_move
        target_move_data = get_move(target_move)
        
        if not target_move_data or target_move_data.get("category") == "status" or target_move_data.get("power", 0) <= 0:
            return False, f"But it failed! {target.species} isn't attacking!"
        
        return True, None
    
    return True, None

def apply_counter_family(move_name: str, user: Any, target: Any, field_effects: Any = None, battle_state: Any = None) -> Tuple[int, str]:
    """
    Handle Counter, Mirror Coat, and Metal Burst with generation-specific mechanics.
    Returns damage dealt to attacker.
    
    Returns: (damage, message)
    """
    move_lower = move_name.lower().replace(" ", "-")
    
    if move_lower not in ["counter", "mirror-coat", "metal-burst"]:
        return 0, ""
    
    from .generation import get_generation
    from .moves_loader import load_move
    generation = get_generation(field_effects=field_effects, battle_state=battle_state) if field_effects or battle_state else 9
    
    # Check if user was hit this turn (or previous turn)
    # Counter checks the damage the USER (Counter user) took from the opponent
    last_damage_taken = getattr(user, '_last_damage_taken', 0)
    last_damage_category = getattr(user, '_last_damage_category', None)
    last_move_type = getattr(user, '_last_move_type_hit_by', None)
    # Get last move that hit the user (for Counter checking)
    last_move_name = getattr(user, '_last_move_that_hit', None)
    if not last_move_name:
        # Fallback to last_move_used if _last_move_that_hit not available
        last_move_name = getattr(user, 'last_move_used', None)
    
    # Gen I: Counter always fails if called by Metronome
    if generation == 1 and move_lower == "counter":
        if hasattr(user, '_metronome_called') and getattr(user, '_metronome_called', False):
            return 0, f"But it failed!"
    
    # Gen I: If both Pokémon use Counter, both fail
    if generation == 1 and move_lower == "counter" and battle_state:
        # Check if target also used Counter this turn
        target_choice = getattr(target, '_current_choice', None)
        if target_choice:
            target_move = target_choice.get("move", "")
            if target_move and target_move.lower().replace(" ", "-") == "counter":
                return 0, f"But it failed!"
    
    # Counter: Generation-specific mechanics
    if move_lower == "counter":
        # Gen I: Only counters Normal/Fighting-type moves (not category-based)
        if generation == 1:
            # Gen I: Check if last move's power is 0 (should fail)
            if last_move_name:
                last_move_data = load_move(last_move_name)
                if last_move_data:
                    last_move_power = last_move_data.get("power", 0)
                    if last_move_power == 0:
                        return 0, f"But it failed!"
            
            # Gen I: Check if last move did no damage (unless it's a status move that doesn't reset damage data)
            if last_damage_taken <= 0:
                # Status moves that don't reset damage data (can still be countered)
                non_reset_moves = [
                    "conversion", "haze", "whirlwind", "roar", "teleport", "mist",
                    "focus-energy", "supersonic", "confuse-ray", "recover", "softboiled",
                    "rest", "transform", "light-screen", "reflect", "poison-powder",
                    "toxic", "poison-gas", "stun-spore", "thunder-wave", "glare",
                    "substitute", "mimic", "leech-seed", "splash"
                ]
                if last_move_name:
                    last_move_lower = last_move_name.lower().replace(" ", "-")
                    if last_move_lower not in non_reset_moves:
                        return 0, f"But it failed!"
                else:
                    return 0, f"But it failed!"
            
            # Gen I: Check if move type is Normal or Fighting
            if not last_move_type or last_move_type not in ["Normal", "Fighting"]:
                return 0, f"But it failed!"
            
            # Gen I: Cannot counter Counter
            if last_move_name and last_move_name.lower().replace(" ", "-") == "counter":
                return 0, f"But it failed!"
            
            # Gen I: Type ignored (can hit Ghost-types)
            damage = last_damage_taken * 2
            return damage, f"**{user.species}** countered with double the damage!"
        
        # Gen II: Counters all physical moves, Ghost immunity
        elif generation == 2:
            if last_damage_taken <= 0:
                return 0, f"But it failed!"
            
            if last_damage_category != "physical":
                return 0, f"But it failed!"
            
            # Gen II: Cannot counter a move that hit a substitute
            if hasattr(user, '_last_damage_hit_substitute') and getattr(user, '_last_damage_hit_substitute', False):
                return 0, f"But it failed!"
            
            # Ghost immunity check
            target_types = [t.strip().title() if t else None for t in getattr(target, 'types', (None, None))]
            if "Ghost" in target_types:
                return 0, f"It doesn't affect {target.species}..."
            
            # Gen II: Can counter Hidden Power regardless of type
            # Gen II: Can counter Beat Up despite being Dark-type
            # Gen II: Can counter OHKO moves if they missed (for maximum damage)
            damage = last_damage_taken * 2
            return damage, f"**{user.species}** countered with double the damage!"
        
        # Gen III+: Counters all physical moves
        else:
            # Check if we have damage category info - if None, try to infer from move
            if last_damage_category is None and last_move_name:
                # Try to get category from the move that hit
                from .moves_loader import load_move
                last_move_data = load_move(last_move_name)
                if last_move_data:
                    last_damage_category = last_move_data.get("damage_class", "physical")
                    # Hidden Power is special in Gen 4+
                    if "hidden-power" in last_move_name.lower().replace(" ", "-"):
                        gen_hp = get_generation(field_effects=field_effects, battle_state=battle_state)
                        last_damage_category = "special" if gen_hp >= 4 else "physical"
            
            if last_damage_category != "physical":
                # Gen III+: "But it failed!" message
                return 0, f"But it failed!"
            
            # Gen III: In Double Battles, hits last opponent that dealt physical damage
            # (This is handled by tracking which opponent hit in damage calculation)
            
            # Gen IV+: Cannot counter Hidden Power (now special)
            if generation >= 4:
                if last_move_name and "hidden-power" in last_move_name.lower().replace(" ", "-"):
                    return 0, f"But it failed!"
            
            # Gen V+: If hit by physical attack that deals 0 damage, Counter becomes 1 BP physical move
            if generation >= 5 and last_damage_taken == 0 and last_damage_category == "physical":
                # Counter becomes a physical move with 1 base power
                # For simplicity, use a fixed 1 damage (as per specification)
                damage = 1
                return damage, f"**{user.species}** countered!"
            
            if last_damage_taken <= 0:
                return 0, f"But it failed!"
            
            damage = last_damage_taken * 2
            return damage, f"**{user.species}** countered with double the damage!"
    
    # Mirror Coat: Returns special damage at 2x
    elif move_lower == "mirror-coat":
        # Gen II-III: Cannot be activated by Hidden Power (regardless of actual type)
        if generation <= 3:
            if last_move_name and "hidden-power" in last_move_name.lower().replace(" ", "-"):
                return 0, f"But it failed!"
        # Gen IV+: Hidden Power can activate Mirror Coat
        elif generation >= 4:
            if not last_move_type or last_move_type == "Dark":
                # Dark immunity (Gen II+)
                if generation >= 2:
                    target_types = [t.strip().title() if t else None for t in getattr(target, 'types', (None, None))]
                    if "Dark" in target_types:
                        return 0, f"It doesn't affect {target.species}..."
        
        if last_damage_category != "special":
            return 0, f"But it failed!"
        
        damage = last_damage_taken * 2
        
        # Gen V+: If hit by 0 damage special move, Mirror Coat becomes 1 BP move
        if generation >= 5 and last_damage_taken == 0:
            damage = 1
            return damage, f"**{user.species}** reflected!"
        
        return damage, f"**{user.species}** reflected the special attack!"
    
    # Metal Burst: Returns last damage at 1.5x
    elif move_lower == "metal-burst":
        damage = int(last_damage_taken * 1.5)
        return damage, f"**{user.species}** unleashed its rage!"
    
    return 0, ""

def apply_endeavor(user: Any, target: Any) -> Tuple[int, str]:
    """
    Endeavor: Sets target's HP equal to user's HP.
    
    Returns: (damage, message)
    """
    if user.hp >= target.hp:
        return 0, "But it failed!"
    
    damage = target.hp - user.hp
    return damage, f"**{user.species}** brought {target.species} down to its level!"

def apply_super_fang(target: Any, field_effects: Any = None) -> Tuple[int, str]:
    """
    Super Fang: Halves the target's current HP.
    
    Returns: (damage, message)
    """
    from .generation import get_generation

    generation = get_generation(field_effects=field_effects) if field_effects else 9
    target_types = [t.strip().title() if t else None for t in getattr(target, 'types', (None, None))]

    if generation >= 2 and "Ghost" in target_types:
        return 0, f"It doesn't affect {target.species}..."

    damage = max(1, target.hp // 2)
    return damage, f"**Super Fang** cut {target.species}'s HP in half!"

def apply_pain_split(user: Any, target: Any, *, generation: int = 9) -> Tuple[int, int, str]:
    """Average HP totals between battlers and report the delta."""
    total_hp = user.hp + target.hp
    average_hp = total_hp // 2

    user_change = average_hp - user.hp
    target_change = average_hp - target.hp

    if user_change == 0 and target_change == 0:
        return 0, 0, "But it failed!"

    return user_change, target_change, f"**{user.species}** and **{target.species}** shared their pain!"

def apply_final_gambit(user: Any) -> Tuple[int, str]:
    """
    Final Gambit: User faints, deals damage equal to its HP.
    
    Returns: (damage, message)
    """
    damage = user.hp
    user.hp = 0
    return damage, f"**{user.species}** sacrificed itself!"

def check_explosion_family(move_name: str, user: Any) -> Tuple[bool, Optional[str]]:
    """
    Check if Explosion/Self-Destruct can be used (blocked by Damp).
    
    Returns: (can_use, failure_message)
    """
    move_lower = move_name.lower().replace(" ", "-")
    
    if move_lower in ["explosion", "self-destruct"]:
        # User will faint after using this move
        # This is handled in apply_move after damage calculation
        return True, None
    
    return True, None

def apply_transform(user: Any, target: Any) -> str:
    """
    Transform: Copy target's species, stats, types, moves, and ability.
    All copied moves have 5 PP each.
    Original data is stored and can be reverted when switching out.
    
    Returns: message, or a failure message if conditions are not met.
    """
    if target is None or getattr(target, "hp", 0) <= 0:
        return "But it failed!"
    if hasattr(target, "substitute") and target.substitute:
        return "But it failed! (Target is protected by a substitute)"
    if getattr(user, "_illusion_active", False):
        return "But it failed! (User is disguised)"
    if getattr(target, "_illusion_active", False):
        return "But it failed! (Target is disguised)"
    if getattr(user, "terastallized", False) and getattr(user, "_tera_is_stellar", False):
        return "But it failed! (Stellar-form Pokémon cannot Transform!)"
    if getattr(target, "terastallized", False) and getattr(target, "_tera_is_stellar", False):
        return "But it failed! (Stellar-form Pokémon cannot be copied!)"
    
    # Store original HP and species for message
    original_hp = user.hp
    original_max_hp = user.max_hp
    original_species = user.species
    
    # Copy target's stats (but keep HP)
    user.species = target.species
    user.types = tuple(target.types)  # Copy types tuple
    user.ability = target.ability
    user.stats = dict(target.stats)
    user.moves = list(target.moves)
    user.weight_kg = target.weight_kg  # Copy weight for Heavy Slam, etc.
    # Copy form if present
    if hasattr(target, 'form'):
        user.form = target.form
    
    # Keep HP but adjust max HP
    hp_ratio = original_hp / original_max_hp if original_max_hp > 0 else 1.0
    user.max_hp = target.max_hp
    user.hp = max(1, int(user.max_hp * hp_ratio))
    
    # Reset stat stages to match target
    user.stages = dict(target.stages)
    
    # Set transform flag (used for PP restriction in panel.py)
    user._transformed = True
    
    return f"**{original_species}** transformed into **{target.species}**!"


def revert_transform(mon: Any) -> bool:
    """
    Revert a transformed Pokémon back to its original form.
    Used when switching out.
    
    Returns: True if reverted, False if not transformed
    """
    if not getattr(mon, '_transformed', False):
        return False
    
    # Only revert if we have original data stored
    if not mon._original_species:
        return False
    
    # Keep current HP and max_hp (don't revert those)
    current_hp = mon.hp
    current_max_hp = mon.max_hp
    
    # Revert to original data
    mon.species = mon._original_species
    mon.types = tuple(mon._original_types)
    mon.ability = mon._original_ability
    mon.stats = dict(mon._original_stats)
    mon.moves = list(mon._original_moves)
    mon.weight_kg = mon._original_weight
    mon.form = mon._original_form
    
    # Restore HP ratio but use original max_hp
    # Actually, keep current HP values for consistency
    mon.hp = current_hp
    mon.max_hp = current_max_hp
    
    # Clear transform flag
    mon._transformed = False
    mon._imposter_transformed = False  # Also clear Imposter flag
    
    # Reset stat stages to 0
    mon.stages = {"atk": 0, "defn": 0, "spa": 0, "spd": 0, "spe": 0, "accuracy": 0, "evasion": 0}
    
    return True

def _resolve_owner_id(battle_state: Any, user_id_hint: int, mon: Any) -> int:
    """Map a mon instance to its trainer id if available."""
    if not battle_state:
        return user_id_hint
    try:
        team_for = getattr(battle_state, "team_for")
        p1_id = getattr(battle_state, "p1_id", None)
        p2_id = getattr(battle_state, "p2_id", None)
        if team_for and p1_id is not None and p2_id is not None:
            for candidate in (p1_id, p2_id):
                try:
                    team = team_for(candidate)
                except Exception:
                    continue
                if team and any(member is mon for member in team):
                    return candidate
    except Exception:
        pass
    return user_id_hint


def setup_wish(user: Any, user_id: int, battle_state: Any) -> str:
    """
    Wish: Heals the user (or replacement) at the end of next turn.
    
    Generation differences:
    - Gen III: Heals half of recipient's max HP
    - Gen IV: Healing happens before switch-in for KO'd Pokémon
    - Gen V+: Heals half of user's max HP (not recipient's)
    
    Returns: message
    """
    from .generation import get_generation
    
    if not hasattr(battle_state, '_wish_healing'):
        battle_state._wish_healing = {}
    
    generation = get_generation(battle_state=battle_state) if battle_state else 9
    
    # Gen III: Heal half of recipient's max HP
    # Gen V+: Heal half of user's max HP
    if generation <= 4:
        # Gen III-IV: Store recipient-based healing (will calculate when healing)
        heal_amount = None  # Will use recipient's HP when healing
    else:
        # Gen V+: Use user's max HP
        heal_amount = user.max_hp // 2
    
    owner_id = _resolve_owner_id(battle_state, user_id, user)
    # Clean up stale entry under previous key if we remapped
    if owner_id != user_id:
        battle_state._wish_healing.pop(user_id, None)
    battle_state._wish_healing[owner_id] = {
        'turns_left': 2,
        'heal_amount': heal_amount,  # None for Gen III-IV (uses recipient), value for Gen V+ (uses user)
        'user_name': user.species,
        'generation': generation  # Store generation for healing calculation
    }
    
    return f"**{user.species}** made a wish!"

def apply_trick_switcheroo(user: Any, target: Any) -> str:
    """
    Trick/Switcheroo: Swap held items with generation-aware restrictions.
    Item effects are delayed until the next turn.
    
    Returns: message
    """
    user_item = user.item
    target_item = target.item
    
    # Fails if target is protected by Substitute
    substitute_obj = getattr(target, 'substitute', None)
    if substitute_obj:
        return "But it failed! The substitute blocked the swap!"
    
    # Sticky Hold (or similar) prevents item removal
    target_ability_norm = normalize_ability_name(getattr(target, 'ability', '') or "")
    target_ability_data = get_ability_effect(target_ability_norm)
    if target_ability_data.get("item_cannot_be_removed"):
        ability_label = (target.ability or target_ability_norm or "Ability").replace("-", " ").title()
        return f"But it failed! {target.species}'s {ability_label} prevents item swaps!"
    
    def _titleize(item_name: str) -> str:
        return item_name.replace("-", " ").title()
    
    def _cannot_swap(holder: Any, item: Optional[str], other: Any) -> Optional[str]:
        if not item:
            return None
        
        norm = normalize_item_name(item)
        item_data = get_item_effect(norm)
        holder_species = (getattr(holder, 'species', '') or "").lower()
        other_species = (getattr(other, 'species', '') or "").lower()
        item_label = _titleize(norm)
        
        # Explicit untrickable flag
        if item_data.get("untrickable"):
            return f"But it failed! {holder.species}'s {item_label} can't be swapped!"
        
        # Mail items
        if norm.endswith("-mail"):
            return f"But it failed! {holder.species} is holding {item_label}!"
        
        # Z-Crystals
        if norm.endswith("-z"):
            return f"But it failed! Z-Crystals can't be exchanged!"
        
        # Mega Stones
        if item_data.get("mega_stone"):
            return f"But it failed! {item_label} is a Mega Stone!"
        
        # Drives (Genesect)
        if norm.endswith("-drive"):
            return "But it failed! Drives can't be swapped!"
        
        # Memories (Silvally)
        if norm.endswith("-memory") and ("silvally" in holder_species or "silvally" in other_species):
            return "But it failed! Memories can't be swapped!"
        
        # Plates (Arceus holding or receiving)
        if norm.endswith("-plate") and ("arceus" in holder_species or "arceus" in other_species):
            return "But it failed! Plates can't be swapped with Arceus!"
        
        # Griseous / Colored Orbs
        if norm in {"griseous-orb"} and ("giratina" in holder_species or "giratina" in other_species):
            return "But it failed! The Griseous Orb can't be exchanged!"
        if norm in {"red-orb", "blue-orb"}:
            return "But it failed! Primal Orbs can't be swapped!"
        
        # Rusted Sword/Shield
        if norm in {"rusted-sword", "rusted-shield"} and (
            "zacian" in holder_species or "zacian" in other_species or
            "zamazenta" in holder_species or "zamazenta" in other_species
        ):
            return f"But it failed! {item_label} can't be swapped!"
        
        # Booster Energy (Paradox Pokémon)
        if norm == "booster-energy":
            return "But it failed! Booster Energy can't be swapped!"
        
        # Ogerpon masks
        if norm in {"wellspring-mask", "hearthflame-mask", "cornerstone-mask"}:
            return "But it failed! Ogerpon's masks can't be swapped!"
        
        return None
    
    # Check item restrictions on both Pokémon
    reason = _cannot_swap(user, user_item, target)
    if reason:
        return reason
    reason = _cannot_swap(target, target_item, user)
    if reason:
        return reason
    
    # Swap items
    user.item = target_item
    target.item = user_item
    
    # Clear choice lock if user lost a choice item
    if user_item and hasattr(user, '_player_id'):
        from .items import normalize_item_name, get_item_effect
        user_item_norm = normalize_item_name(user_item)
        user_item_data = get_item_effect(user_item_norm)
        if user_item_data.get("choice_locks_move"):
            # Clear choice lock from user (they lost the choice item)
            if hasattr(user, '_battle_state') and user._battle_state:
                user._battle_state._choice_locked[user._player_id] = None
    
    # Clear choice lock if target lost a choice item
    if target_item and hasattr(target, '_player_id'):
        from .items import normalize_item_name, get_item_effect
        target_item_norm = normalize_item_name(target_item)
        target_item_data = get_item_effect(target_item_norm)
        if target_item_data.get("choice_locks_move"):
            # Clear choice lock from target (they lost the choice item)
            if hasattr(target, '_battle_state') and target._battle_state:
                target._battle_state._choice_locked[target._player_id] = None
    
    # Mark items as just received (effects activate next turn)
    if target_item:
        user._item_just_received = True
    if user_item:
        target._item_just_received = True
    
    if user_item and target_item:
        return f"**{user.species}** swapped **{user_item}** for **{target_item}**!"
    elif user_item:
        return f"**{user.species}** gave **{user_item}** to **{target.species}**!"
    elif target_item:
        return f"**{user.species}** took **{target_item}** from **{target.species}**!"
    else:
        return "But it failed! Neither Pokémon is holding an item!"

def apply_knock_off(target: Any) -> Tuple[float, str]:
    """
    Knock Off: Remove target's item and boost damage by 1.5x if successful.
    
    Returns: (damage_multiplier, message)
    """
    if target.item:
        item_name = target.item
        target.item = None
        return 1.5, f"\n**{target.species}** lost its **{item_name}**!"
    
    return 1.0, ""

def apply_acrobatics(user: Any) -> float:
    """
    Acrobatics: Double power if user has no item.
    
    Returns: power_multiplier
    """
    if not user.item:
        return 2.0
    return 1.0

def apply_fling(user: Any, target: Any, field_effects: Any = None, battle_state: Any = None) -> Tuple[int, str, Optional[str]]:
    """
    Fling: Throw held item at target. Power and effect vary by item.
    
    Returns: (power, message, item_effect_message)
    - power: The base power of Fling (will be used in damage calculation)
    - message: Main message about the fling
    - item_effect_message: Message about special item effects (berries, status, etc.)
    
    The item is consumed (only in battle, not permanently).
    """
    from .generation import get_generation
    
    generation = get_generation(field_effects=field_effects, battle_state=battle_state)
    
    # === FAILURE CHECKS ===
    if not user.item:
        return 0, "But it failed! No item to fling!", None
    
    item = normalize_item_name(user.item)
    item_lower = item.lower().replace(" ", "-")
    
    # Check for Embargo (prevents Fling usage)
    if hasattr(user, 'embargoed') and getattr(user, 'embargoed', 0) > 0:
        return 0, "But it failed! (Embargo prevents item usage)", None
    
    # Check for Klutz (Gen V+ prevents Fling)
    user_ability = normalize_ability_name(user.ability or "")
    user_ability_data = get_ability_effect(user_ability)
    if user_ability_data.get("prevents_item_usage") and generation >= 5:
        return 0, "But it failed! (Klutz prevents item usage)", None
    
    # Check for Magic Room (prevents Fling usage)
    if field_effects and getattr(field_effects, 'magic_room', False):
        return 0, "But it failed! (Magic Room prevents item usage)", None
    
    # === ITEMS THAT CANNOT BE FLUNG ===
    # TM, Apricorn, Gem, Poké Ball, Mail, Z-Crystal, Ability Capsule, Ability Patch, Festival Ticket
    # Red Orb, Blue Orb, Rusted Sword, Rusted Shield
    invalid_items = {
        # TMs and TRs (will be handled separately for TRs)
        # Apricorns
        "red-apricorn", "yellow-apricorn", "green-apricorn", "blue-apricorn", "pink-apricorn", 
        "white-apricorn", "black-apricorn",
        # Gems (all type gems)
        "normal-gem", "fire-gem", "water-gem", "electric-gem", "grass-gem", "ice-gem",
        "fighting-gem", "poison-gem", "ground-gem", "flying-gem", "psychic-gem", "bug-gem",
        "rock-gem", "ghost-gem", "dragon-gem", "dark-gem", "steel-gem", "fairy-gem",
        # Poké Balls
        "poke-ball", "great-ball", "ultra-ball", "master-ball", "safari-ball", "net-ball",
        "dive-ball", "nest-ball", "repeat-ball", "timer-ball", "luxury-ball", "premier-ball",
        "dusk-ball", "heal-ball", "quick-ball", "cherish-ball", "park-ball", "sport-ball",
        "dream-ball", "beast-ball", "level-ball", "lure-ball", "moon-ball", "friend-ball",
        "love-ball", "heavy-ball", "fast-ball", "competition-ball",
        # Mail
        "air-mail", "bloom-mail", "brick-mail", "bubble-mail", "flame-mail", "grass-mail",
        "heart-mail", "mosaic-mail", "ocean-mail", "snow-mail", "space-mail", "steel-mail",
        "tunnel-mail",
        # Z-Crystals
        "z-crystal", "normalium-z", "firium-z", "waterium-z", "electrium-z", "grassium-z",
        "icium-z", "fightinium-z", "poisonium-z", "groundium-z", "flyinium-z", "psychium-z",
        "buginium-z", "rockium-z", "ghostium-z", "dragonium-z", "darkinium-z", "steelium-z",
        "fairium-z",
        # Other invalid items
        "ability-capsule", "ability-patch", "festival-ticket",
        "red-orb", "blue-orb", "rusted-sword", "rusted-shield"
    }
    
    if item_lower in invalid_items:
        return 0, "But it failed! (Cannot fling this item)", None
    
    # Check for Giratina holding Griseous Orb
    if item_lower in ["griseous-orb", "griseous-core", "griseous"]:
        species_lower = (user.species or "").lower()
        if species_lower == "giratina":
            return 0, "But it failed! (Giratina cannot fling Griseous Orb)", None
    
    # Check for Arceus holding a plate
    if item_lower.endswith("-plate") or item_lower in ["fist-plate", "sky-plate", "toxic-plate", "earth-plate", 
                                                         "stone-plate", "insect-plate", "spooky-plate", "iron-plate",
                                                         "flame-plate", "splash-plate", "meadow-plate", "zap-plate",
                                                         "mind-plate", "icicle-plate", "dread-plate", "pixie-plate"]:
        species_lower = (user.species or "").lower()
        if species_lower == "arceus":
            return 0, "But it failed! (Arceus cannot fling plates)", None
    
    # Check for Genesect holding a drive
    if item_lower in ["burn-drive", "chill-drive", "douse-drive", "shock-drive"]:
        species_lower = (user.species or "").lower()
        if species_lower == "genesect":
            return 0, "But it failed! (Genesect cannot fling drives)", None
    
    # Check for Silvally holding a memory
    if item_lower.endswith("-memory") or item_lower in ["fire-memory", "water-memory", "electric-memory",
                                                          "grass-memory", "ice-memory", "fighting-memory",
                                                          "poison-memory", "ground-memory", "flying-memory",
                                                          "psychic-memory", "bug-memory", "rock-memory",
                                                          "ghost-memory", "dragon-memory", "dark-memory",
                                                          "steel-memory", "fairy-memory"]:
        species_lower = (user.species or "").lower()
        if species_lower == "silvally":
            return 0, "But it failed! (Silvally cannot fling memories)", None
    
    # Check for Pokémon holding a Mega Stone that allows it to Mega Evolve
    if item_lower.endswith("-ite") or item_lower.endswith("-ite-x") or item_lower.endswith("-ite-y"):
        # Check if this Pokémon can Mega Evolve with this stone
        species_lower = (user.species or "").lower()
        form = getattr(user, 'form', None)
        # Basic check: if the stone matches the species, it can't be flung
        stone_base = item_lower.replace("-ite", "").replace("-ite-x", "").replace("-ite-y", "")
        if stone_base in species_lower or species_lower in stone_base:
            return 0, "But it failed! (Cannot fling Mega Stone)", None
    
    # Check for Protosynthesis/Quark Drive holding Booster Energy
    if item_lower == "booster-energy":
        if user_ability in ["protosynthesis", "quark-drive"]:
            return 0, "But it failed! (Cannot fling Booster Energy with Protosynthesis/Quark Drive)", None
    
    # Check for Ogerpon holding masks
    if item_lower in ["cornerstone-mask", "wellspring-mask", "hearthflame-mask"]:
        species_lower = (user.species or "").lower()
        if species_lower == "ogerpon":
            return 0, "But it failed! (Ogerpon cannot fling masks)", None
    
    # === STORE ORIGINAL ITEM (before consuming) ===
    # Store original item name for messages and restoration after battle
    original_item_name = user.item
    if not hasattr(user, '_original_item'):
        user._original_item = original_item_name
    
    # === ITEM POWER TABLE ===
    # Power 10: All Berries, all Incenses, all Mints, all Nectars, all Scarves, all Sweets
    # Power 10 items (common items)
    power_10_items = {
        # Berries (all berries are power 10)
        "cheri-berry", "chesto-berry", "pecha-berry", "rawst-berry", "aspear-berry",
        "leppa-berry", "oran-berry", "persim-berry", "lum-berry", "sitrus-berry",
        "figy-berry", "wiki-berry", "mago-berry", "aguav-berry", "iapapa-berry",
        "razz-berry", "bluk-berry", "nanab-berry", "wepear-berry", "pinap-berry",
        "pomeg-berry", "kelpsy-berry", "qualot-berry", "hondew-berry", "grepa-berry",
        "tamato-berry", "cornn-berry", "magost-berry", "rabuta-berry", "nomel-berry",
        "spelon-berry", "pamtre-berry", "watmel-berry", "durin-berry", "belue-berry",
        "occa-berry", "passho-berry", "wacan-berry", "rindo-berry", "yache-berry",
        "chople-berry", "kebia-berry", "shuca-berry", "coba-berry", "payapa-berry",
        "tanga-berry", "charti-berry", "kasib-berry", "haban-berry", "colbur-berry",
        "babiri-berry", "chilan-berry", "roseli-berry", "liechi-berry", "ganlon-berry",
        "salac-berry", "petaya-berry", "apicot-berry", "lansat-berry", "starf-berry",
        "enigma-berry", "micle-berry", "custap-berry", "jaboca-berry", "rowap-berry",
        "kee-berry", "maranga-berry", "kee-berry", "maranga-berry",
        # Incenses
        "sea-incense", "lax-incense", "odd-incense", "rock-incense", "wave-incense",
        "rose-incense", "pure-incense", "luck-incense", "full-incense",
        # Mints (all mints)
        "lonely-mint", "adamant-mint", "naughty-mint", "brave-mint", "bold-mint",
        "impish-mint", "lax-mint", "relaxed-mint", "modest-mint", "mild-mint",
        "rash-mint", "quiet-mint", "calm-mint", "gentle-mint", "careful-mint",
        "sassy-mint", "timid-mint", "hasty-mint", "jolly-mint", "naive-mint",
        "serious-mint",
        # Nectars
        "red-nectar", "yellow-nectar", "pink-nectar", "purple-nectar",
        # Scarves
        "red-scarf", "blue-scarf", "pink-scarf", "green-scarf", "yellow-scarf",
        # Sweets
        "strawberry-sweet", "berry-sweet", "love-sweet", "star-sweet", "clover-sweet",
        "flower-sweet", "ribbon-sweet",
        # Other power 10 items
        "air-balloon", "big-root", "bright-powder", "choice-band", "choice-scarf",
        "choice-specs", "destiny-knot", "discount-coupon", "electric-seed", "expert-belt",
        "fairy-feather", "focus-band", "focus-sash", "grassy-seed", "lagging-tail",
        "leftovers", "mental-herb", "metal-powder", "misty-seed", "muscle-band",
        "power-herb", "psychic-seed", "quick-powder", "reaper-cloth", "red-card",
        "ring-target", "shed-shell", "silk-scarf", "silver-powder", "smooth-rock",
        "soft-sand", "soothe-bell", "white-herb", "wide-lens", "wise-glasses",
        "zoom-lens",
        # Food items
        "bread", "coconut-milk", "fresh-cream", "fried-food", "fruit-bunch",
        "instant-noodles", "mixed-mushrooms", "pack-of-potatoes", "packaged-curry",
        "pasta", "precooked-burger", "pungent-root", "salad-mix", "sausages",
        "smoke-poke-tail"
    }
    
    # Power 20: All Feathers
    power_20_items = {
        "health-feather", "muscle-feather", "resist-feather", "genius-feather",
        "clever-feather", "swift-feather",
        "boiled-egg", "fancy-apple", "large-leek", "moomoo-cheese"
    }
    
    # Power 30: All status condition healing items (besides Berries), all Potions, all herbal medicine,
    # all drinks, all Vitamins, all Shards, all Mulches, all battle items, all Flutes, all Exp. Candy, all Tera Shards
    power_30_items = {
        # Potions and healing items
        "potion", "super-potion", "hyper-potion", "max-potion", "full-restore",
        "full-heal", "revive", "max-revive", "ether", "max-ether", "elixir", "max-elixir",
        # Herbal medicine
        "antidote", "burn-heal", "ice-heal", "awakening", "paralyze-heal",
        # Drinks
        "fresh-water", "soda-pop", "lemonade", "moomoo-milk",
        # Vitamins
        "hp-up", "protein", "iron", "calcium", "zinc", "carbos",
        # Shards
        "red-shard", "blue-shard", "green-shard", "yellow-shard",
        # Mulches
        "growth-mulch", "damp-mulch", "stable-mulch", "gooey-mulch",
        # Battle items
        "x-attack", "x-defense", "x-sp-atk", "x-sp-def", "x-speed", "x-accuracy",
        "dire-hit", "guard-spec", "x-accuracy",
        # Flutes
        "blue-flute", "yellow-flute", "red-flute", "white-flute", "black-flute",
        # Exp. Candy
        "exp-candy-xs", "exp-candy-s", "exp-candy-m", "exp-candy-l", "exp-candy-xl",
        # Tera Shards
        "tera-shard", "normal-tera-shard", "fire-tera-shard", "water-tera-shard",
        "electric-tera-shard", "grass-tera-shard", "ice-tera-shard", "fighting-tera-shard",
        "poison-tera-shard", "ground-tera-shard", "flying-tera-shard", "psychic-tera-shard",
        "bug-tera-shard", "rock-tera-shard", "ghost-tera-shard", "dragon-tera-shard",
        "dark-tera-shard", "steel-tera-shard", "fairy-tera-shard",
        # Other power 30 items
        "ability-shield", "absorb-bulb", "adrenaline-orb", "amulet-coin", "armorite-ore",
        "auspicious-armor", "balm-mushroom", "berry-juice", "big-bamboo-shoot", "big-malasada",
        "big-mushroom", "big-nugget", "big-pearl", "binding-band", "black-belt", "black-glasses",
        "black-sludge", "booster-energy", "bottle-cap", "casteliacone", "cell-battery",
        "charcoal", "cleanse-tag", "clear-amulet", "comet-shard", "covert-cloak",
        "deep-sea-scale", "dynamax-candy", "eject-button", "escape-rope", "everstone",
        "fire-stone", "flame-orb", "float-stone", "fluffy-tail", "galarica-cuff",
        "galarica-twig", "galarica-wreath", "gold-bottle-cap", "heart-scale", "honey",
        "ice-stone", "kings-rock", "lava-cookie", "leaders-crest", "leaf-stone",
        "life-orb", "light-ball", "light-clay", "loaded-dice", "lucky-egg",
        "luminous-moss", "lumiose-galette", "magnet", "malicious-armor", "max-honey",
        "max-mushrooms", "max-revive", "metal-coat", "metronome", "miracle-seed",
        "mirror-herb", "moon-stone", "mystic-water", "never-melt-ice", "nugget",
        "old-gateau", "pass-orb", "pearl-string", "pearl", "poke-doll", "poke-toy",
        "prism-scale", "protective-pads", "punching-glove", "rare-candy", "razor-fang",
        "relic-band", "relic-copper", "relic-crown", "relic-gold", "relic-silver",
        "relic-statue", "relic-vase", "revive", "sacred-ash", "scope-lens",
        "shalour-sable", "shell-bell", "shoal-salt", "shoal-shell", "smoke-ball",
        "snowball", "soul-dew", "spell-tag", "star-piece", "strange-souvenir",
        "stardust", "sun-stone", "sweet-apple", "sweet-heart", "syrupy-apple",
        "tart-apple", "thunder-stone", "tiny-bamboo-shoot", "tiny-mushroom", "toxic-orb",
        "throat-spray", "twisted-spoon", "upgrade", "water-stone", "brittle-bones"
    }
    
    # Power 40
    power_40_items = {
        "eviolite", "icy-rock", "lucky-punch"
    }
    
    # Power 50: All Memories
    power_50_items = {
        "dubious-disc", "eject-pack", "sharp-beak", "wishing-piece",
        "gigantamix", "spice-mix"
    }
    # Add all memories
    for mem_type in ["fire", "water", "electric", "grass", "ice", "fighting", "poison",
                     "ground", "flying", "psychic", "bug", "rock", "ghost", "dragon",
                     "dark", "steel", "fairy"]:
        power_50_items.add(f"{mem_type}-memory")
    
    # Power 60
    power_60_items = {
        "adamant-orb", "cornerstone-mask", "damp-rock", "griseous-orb",
        "hearthflame-mask", "heat-rock", "leek", "lustrous-orb", "macho-brace",
        "rocky-helmet", "terrain-extender", "utility-umbrella", "wellspring-mask"
    }
    
    # Power 70: All Drives, all Power items
    power_70_items = {
        "dragon-fang", "poison-barb"
    }
    # Add all drives
    for drive in ["burn-drive", "chill-drive", "douse-drive", "shock-drive"]:
        power_70_items.add(drive)
    # Add all power items
    for stat in ["hp", "atk", "def", "spa", "spd", "spe"]:
        power_70_items.add(f"power-{stat}")
        power_70_items.add(f"power-{stat}-weight")
        power_70_items.add(f"power-{stat}-bracer")
        power_70_items.add(f"power-{stat}-belt")
        power_70_items.add(f"power-{stat}-lens")
        power_70_items.add(f"power-{stat}-band")
        power_70_items.add(f"power-{stat}-anklet")
    
    # Power 80: All Mega Stones
    power_80_items = {
        "assault-vest", "blunder-policy", "chipped-pot", "cracked-pot", "dawn-stone",
        "dusk-stone", "electirizer", "heavy-duty-boots", "magmarizer", "masterpiece-teacup",
        "odd-keystone", "oval-stone", "protector", "quick-claw", "razor-claw",
        "sachet", "safety-goggles", "shiny-stone", "sticky-barb", "tin-of-beans",
        "unremarkable-teacup", "weakness-policy", "whipped-dream",
        "bachs-food-tin", "bobs-food-tin"
    }
    # Add all mega stones (they end with -ite)
    # This will be handled dynamically
    
    # Power 90: All Plates
    power_90_items = {
        "deep-sea-tooth", "grip-claw", "thick-club"
    }
    # Add all plates
    for plate_type in ["fist", "sky", "toxic", "earth", "stone", "insect", "spooky", "iron",
                       "flame", "splash", "meadow", "zap", "mind", "icicle", "dread", "pixie"]:
        power_90_items.add(f"{plate_type}-plate")
    
    # Power 100: All Fossils
    power_100_items = {
        "hard-stone", "rare-bone", "room-service"
    }
    # Add all fossils
    fossil_items = [
        "helix-fossil", "dome-fossil", "old-amber", "root-fossil", "claw-fossil",
        "skull-fossil", "armor-fossil", "cover-fossil", "plume-fossil", "jaw-fossil",
        "sail-fossil", "fossilized-bird", "fossilized-dino", "fossilized-drake", "fossilized-fish"
    ]
    for fossil in fossil_items:
        power_100_items.add(fossil)
    
    # Power 130
    power_130_items = {
        "iron-ball", "big-nugget"  # Gen VIII-IX Big Nugget is 130, Gen V-VII is 10
    }
    
    # Determine power based on item
    power = 30  # Default power
    if item_lower in power_10_items:
        power = 10
    elif item_lower in power_20_items:
        power = 20
    elif item_lower in power_30_items:
        power = 30
    elif item_lower in power_40_items:
        power = 40
    elif item_lower in power_50_items:
        power = 50
    elif item_lower in power_60_items:
        power = 60
    elif item_lower in power_70_items:
        power = 70
    elif item_lower in power_80_items or item_lower.endswith("-ite") or item_lower.endswith("-ite-x") or item_lower.endswith("-ite-y"):
        power = 80
    elif item_lower in power_90_items or item_lower.endswith("-plate"):
        power = 90
    elif item_lower in power_100_items:
        power = 100
    elif item_lower in power_130_items:
        power = 130
    elif item_lower == "big-nugget" and generation >= 8:
        power = 130
    elif item_lower == "big-nugget" and generation <= 7:
        power = 10
    
    # === TR (Technical Record) HANDLING ===
    # If item is a TR, power equals the TR's move power (or 10 if status/variable power)
    if item_lower.startswith("tr") or "technical-record" in item_lower:
        # TODO: Implement TR power lookup from database
        # For now, default to 10 for TRs
        power = 10
    
    # === ITEM POWER BOOSTS ===
    # Items that boost move power also boost Fling's power
    item_data = get_item_effect(item)
    original_power = power
    
    # Life Orb: Boosts damage (but doesn't cause recoil when used with Fling)
    if item_lower == "life-orb":
        if generation <= 3:
            power = int(power * 1.3)
        else:
            power = int(power * (5324 / 4096))  # Exact Gen 5+ calculation
    
    # Type-enhancing items (Black Glasses, Charcoal, etc.): Boost matching type moves
    # Note: Fling is Dark-type, so only Dark-boosting items apply
    if item_data.get("type_enhancing"):
        boost_type = item_data.get("boost_type", "")
        if boost_type == "Dark":  # Fling is Dark-type
            if generation <= 3:
                power = int(power * 1.1)
            else:
                power = int(power * 1.2)
    
    # Expert Belt: Boosts super-effective moves (applied in damage calculation, not here)
    # Muscle Band: Boosts physical moves (Fling is physical)
    if item_data.get("physical_boost"):
        power = int(power * item_data["physical_boost"])
    
    # Wise Glasses: Boosts special moves (Fling is physical, so doesn't apply)
    
    # === SPECIAL ITEM EFFECTS ===
    item_effect_msg = None
    berry_activated = False
    
    # Berries: Activate for target (even if usual trigger condition not satisfied)
    if "berry" in item_lower:
        berry_activated = True
        # Berry effects will be handled after damage calculation
        # Store berry info for later activation
        target._flung_berry = item
        target._flung_berry_user = user.species
    
    # Flame Orb: Burns target
    if item_lower == "flame-orb":
        from .db_move_effects import can_inflict_status
        # Apply status to TARGET (not user)
        can_inflict, reason = can_inflict_status(target, "brn", user, field_effects)
        if can_inflict:
            # Directly apply status to TARGET (not user)
            target.status = "brn"
            item_effect_msg = f"{target.species} was **burned** by {user.species}'s {original_item_name.replace('-', ' ').title()}!"
        else:
            item_effect_msg = None  # Status cannot be inflicted
    
    # Toxic Orb: Badly poisons target
    elif item_lower == "toxic-orb":
        from .db_move_effects import apply_status_effect, can_inflict_status
        # Apply status to TARGET (not user) - make absolutely sure we're using target
        # Check if status can be inflicted on target
        can_inflict, reason = can_inflict_status(target, "tox", user, field_effects)
        if can_inflict:
            # Directly apply status to TARGET (not user)
            target.status = "tox"
            target.toxic_counter = 1
            item_effect_msg = f"{target.species} was **badly poisoned** by {user.species}'s {original_item_name.replace('-', ' ').title()}!"
        else:
            item_effect_msg = None  # Status cannot be inflicted
    
    # Light Ball: Paralyzes target
    elif item_lower == "light-ball":
        from .db_move_effects import can_inflict_status
        # Apply status to TARGET (not user)
        can_inflict, reason = can_inflict_status(target, "par", user, field_effects)
        if can_inflict:
            # Directly apply status to TARGET (not user)
            target.status = "par"
            item_effect_msg = f"{target.species} was **paralyzed** by {user.species}'s {original_item_name.replace('-', ' ').title()}!"
        else:
            item_effect_msg = None  # Status cannot be inflicted
    
    # King's Rock / Razor Fang: Causes flinch (handled in damage calculation)
    elif item_lower in ["kings-rock", "razor-fang"]:
        # Flinch will be handled in damage calculation
        target._flung_flinch_item = True
    
    # Mental Herb: Cures mental effects (Gen IV+)
    elif item_lower == "mental-herb":
        if generation >= 4:
            cured = False
            if hasattr(target, 'disabled_move') and target.disabled_move:
                target.disabled_move = None
                target.disable_turns = 0
                cured = True
            if hasattr(target, 'tormented') and target.tormented:
                target.tormented = False
                cured = True
            if hasattr(target, 'encored') and target.encored:
                target.encored = False
                target.encore_turns = 0
                cured = True
            if hasattr(target, 'heal_blocked') and getattr(target, 'heal_blocked', 0) > 0:
                target.heal_blocked = 0
                cured = True
            if hasattr(target, 'infatuated') and target.infatuated:
                target.infatuated = False
                cured = True
            if cured:
                item_effect_msg = f"{target.species}'s Mental Herb cured its mental status!"
    
    # White Herb: Restores lowered stats
    elif item_lower == "white-herb":
        from .engine import modify_stages
        stat_resets = {}
        for stat in ["atk", "defn", "spa", "spd", "spe", "accuracy", "evasion"]:
            if hasattr(target, 'stages') and target.stages.get(stat, 0) < 0:
                stat_resets[stat] = -target.stages.get(stat, 0)
        if stat_resets:
            reset_msgs = modify_stages(target, stat_resets, caused_by_opponent=False, field_effects=field_effects)
            if reset_msgs:
                item_effect_msg = "\n".join(reset_msgs)
    
    # Poison Barb: Poisons target
    elif item_lower == "poison-barb":
        from .db_move_effects import can_inflict_status
        # Apply status to TARGET (not user)
        can_inflict, reason = can_inflict_status(target, "psn", user, field_effects)
        if can_inflict:
            # Directly apply status to TARGET (not user)
            target.status = "psn"
            item_effect_msg = f"{target.species} was **poisoned** by {user.species}'s {original_item_name.replace('-', ' ').title()}!"
        else:
            item_effect_msg = None  # Status cannot be inflicted
    
    # === CONSUME ITEM (only in battle, not permanently) ===
    # Item already stored in _original_item above
    user.item = None  # Consume item in battle
    
    # === GENERATION IV EMBARGO CHECK ===
    # Gen IV: If target has Embargo and item has special effect, effect doesn't activate
    if generation == 4 and hasattr(target, 'embargoed') and getattr(target, 'embargoed', 0) > 0:
        if item_effect_msg:
            item_effect_msg = None  # Effect doesn't activate
    
    main_msg = f"**{user.species}** flung its {original_item_name.replace('-', ' ').title()}!"
    
    return power, main_msg, item_effect_msg

def apply_baton_pass(user: Any, user_id: int, battle_state: Any) -> str:
    """
    Baton Pass: Pass stat changes to the next Pokémon.
    
    Returns: message
    """
    from .generation import get_generation
    generation = getattr(battle_state, 'gen', None)
    if generation is None:
        # Fall back to field-based generation lookup if available
        try:
            generation = get_generation(field_effects=getattr(battle_state, 'field', None))
        except Exception:
            generation = 9
    else:
        generation = int(generation)

    if not hasattr(battle_state, '_baton_pass_stages'):
        battle_state._baton_pass_stages = {}

    owner_id = _resolve_owner_id(battle_state, user_id, user)

    # Remove stale keys if remapping
    if owner_id != user_id:
        battle_state._baton_pass_stages.pop(user_id, None)
        if hasattr(battle_state, '_baton_pass_substitute'):
            getattr(battle_state, '_baton_pass_substitute').pop(user_id, None)
        if hasattr(battle_state, '_baton_pass_lockon_active'):
            getattr(battle_state, '_baton_pass_lockon_active').pop(user_id, None)
        if hasattr(battle_state, '_baton_pass_lockon_user'):
            getattr(battle_state, '_baton_pass_lockon_user').pop(user_id, None)
        if hasattr(battle_state, '_baton_pass_lockon_target'):
            getattr(battle_state, '_baton_pass_lockon_target').pop(user_id, None)
        if hasattr(battle_state, '_baton_pass_volatiles'):
            getattr(battle_state, '_baton_pass_volatiles').pop(user_id, None)

    # Store current stat stages
    battle_state._baton_pass_stages[owner_id] = dict(user.stages)
    
    # Also store volatile status (Substitute HP, etc.)
    substitute_obj = getattr(user, 'substitute', None)
    if substitute_obj:
        if not hasattr(battle_state, '_baton_pass_substitute'):
            battle_state._baton_pass_substitute = {}
        battle_state._baton_pass_substitute[owner_id] = getattr(substitute_obj, 'hp', 0)

    # Store Lock-On / Mind Reader effects for older generations (Gen II-IV)
    if generation <= 4:
        # Gen II: effect is target-based flag
        if generation == 2 and getattr(user, '_mind_reader_active', False):
            if not hasattr(battle_state, '_baton_pass_lockon_active'):
                battle_state._baton_pass_lockon_active = {}
            battle_state._baton_pass_lockon_active[owner_id] = True
        
        # Gen III-IV: user-side Lock-On data
        if generation >= 3 and getattr(user, 'lock_on_target', None):
            if not hasattr(battle_state, '_baton_pass_lockon_user'):
                battle_state._baton_pass_lockon_user = {}
            battle_state._baton_pass_lockon_user[owner_id] = {
                "target": user.lock_on_target,
                "turns": getattr(user, 'lock_on_turns', 0),
                "generation": generation
            }
        
        # Gen III-IV (and Gen II for completeness): target-side baton pass
        if hasattr(user, '_mind_reader_user') and user._mind_reader_user:
            if not hasattr(battle_state, '_baton_pass_lockon_target'):
                battle_state._baton_pass_lockon_target = {}
            attacker = user._mind_reader_user
            battle_state._baton_pass_lockon_target[owner_id] = {
                "attacker": attacker,
                "turns": getattr(attacker, 'lock_on_turns', 0),
                "generation": generation
            }
        
        # Clear temporary lock-on attributes on the outgoing user to avoid lingering references
        if generation == 2 and getattr(user, '_mind_reader_active', False):
            user._mind_reader_active = False
    
    # Collect additional volatile effects to transfer
    volatile_data: Dict[str, Any] = {}

    if getattr(user, 'confused', False):
        volatile_data['confused'] = True
        volatile_data['confusion_turns'] = getattr(user, 'confusion_turns', 0)
        user.confused = False
        user.confusion_turns = 0

    if getattr(user, 'focused_energy', False) or getattr(user, 'focused_energy_stage', 0) > 0:
        volatile_data['focused_energy'] = True
        volatile_data['focused_energy_stage'] = getattr(user, 'focused_energy_stage', 0)
        user.focused_energy = False
        user.focused_energy_stage = 0

    if getattr(user, 'trapped', False):
        volatile_data['trapped'] = True
        volatile_data['trap_source'] = getattr(user, 'trap_source', None)
        user.trapped = False
        user.trap_source = None

    if getattr(user, 'partially_trapped', False):
        volatile_data['partially_trapped'] = True
        volatile_data['partial_trap_turns'] = getattr(user, 'partial_trap_turns', 0)
        volatile_data['partial_trap_damage'] = getattr(user, 'partial_trap_damage', 0.0)
        user.partially_trapped = False
        user.partial_trap_turns = 0
        user.partial_trap_damage = 0.0

    ability_suppressed = getattr(user, 'ability_suppressed', False) or getattr(user, '_ability_suppressed', False)
    if ability_suppressed:
        volatile_data['ability_suppressed'] = True
        if hasattr(user, 'ability_suppressed'):
            user.ability_suppressed = False
        if hasattr(user, '_ability_suppressed'):
            delattr(user, '_ability_suppressed')

    if getattr(user, 'leech_seeded', False):
        volatile_data['leech_seeded'] = True
        user.leech_seeded = False

    if getattr(user, 'cursed', False):
        volatile_data['cursed'] = True
        volatile_data['cursed_generation'] = getattr(user, '_cursed_generation', None)
        volatile_data['cursed_source'] = getattr(user, '_cursed_source', None)
        user.cursed = False
        if hasattr(user, '_cursed_generation'):
            delattr(user, '_cursed_generation')
        if hasattr(user, '_cursed_source'):
            delattr(user, '_cursed_source')

    if getattr(user, 'ingrained', False) or getattr(user, '_ingrained', False):
        volatile_data['ingrained'] = True
        if hasattr(user, '_ingrain_generation'):
            volatile_data['ingrain_generation'] = getattr(user, '_ingrain_generation', None)
        user.ingrained = False
        if hasattr(user, '_ingrained'):
            user._ingrained = False
        if hasattr(user, '_ingrain_generation'):
            delattr(user, '_ingrain_generation')

    if getattr(user, 'aqua_ring', False):
        volatile_data['aqua_ring'] = True
        user.aqua_ring = False

    if getattr(user, 'heal_blocked', 0) > 0:
        volatile_data['heal_blocked'] = getattr(user, 'heal_blocked', 0)
        user.heal_blocked = 0

    if getattr(user, 'embargoed', 0) > 0:
        volatile_data['embargoed'] = getattr(user, 'embargoed', 0)
        user.embargoed = 0

    if getattr(user, 'perish_count', None) is not None:
        volatile_data['perish_count'] = user.perish_count
        user.perish_count = None

    if getattr(user, '_magnet_rise_turns', 0) > 0:
        volatile_data['magnet_rise_turns'] = getattr(user, '_magnet_rise_turns', 0)
        user._magnet_rise_turns = 0

    if getattr(user, '_telekinesis_turns', 0) > 0:
        volatile_data['telekinesis_turns'] = getattr(user, '_telekinesis_turns', 0)
        user._telekinesis_turns = 0

    if getattr(user, '_power_trick_active', False):
        volatile_data['power_trick'] = True
        # Revert the user's stats back on switch-out
        user.stats['atk'], user.stats['defn'] = user.stats['defn'], user.stats['atk']
        user._power_trick_active = False

    # Gen II: Foresight can be Baton Passed (target-based effect)
    if generation == 2:
        # Check if target has Foresight active (user used Foresight on target)
        # We need to find the target that has Foresight from this user
        if battle_state:
            opponent_id = battle_state.p2_id if owner_id == battle_state.p1_id else battle_state.p1_id
            opponent = battle_state._active(opponent_id)
            if opponent and hasattr(opponent, '_foresight_active') and opponent._foresight_active:
                # Store Foresight data for transfer
                if not hasattr(battle_state, '_baton_pass_foresight'):
                    battle_state._baton_pass_foresight = {}
                battle_state._baton_pass_foresight[owner_id] = {
                    'target_id': id(opponent),
                    'acc_ev_balanced': getattr(opponent, '_foresight_acc_ev_balanced', False),
                    'user_acc_stage': getattr(opponent, '_foresight_user_acc_stage', 0),
                    'target_ev_stage': getattr(opponent, '_foresight_target_ev_stage', 0)
                }

    if volatile_data:
        if not hasattr(battle_state, '_baton_pass_volatiles'):
            battle_state._baton_pass_volatiles = {}
        battle_state._baton_pass_volatiles[owner_id] = volatile_data
    elif hasattr(battle_state, '_baton_pass_volatiles'):
        battle_state._baton_pass_volatiles.pop(owner_id, None)

    # If user was trapping the opponent, free them upon passing
    # Exception: G-Max Sandblast and G-Max Centiferno persist even if user switches out
    try:
        if hasattr(battle_state, '_opp_active') and owner_id in (getattr(battle_state, 'p1_id', None), getattr(battle_state, 'p2_id', None)):
            opponent_id = battle_state.p2_id if owner_id == battle_state.p1_id else battle_state.p1_id
            opponent = battle_state._active(opponent_id)
            if opponent and getattr(opponent, 'trapped', False) and getattr(opponent, 'trap_source', None) == user.species:
                # G-Max Sandblast and G-Max Centiferno don't end when user switches out
                is_gmax_persistent_trap = getattr(opponent, '_gmax_sandblast_active', False) or getattr(opponent, '_gmax_centiferno_active', False)
                if not is_gmax_persistent_trap:
                    opponent.trapped = False
                    opponent.trap_source = None
                    opponent.partially_trapped = False
                    opponent.partial_trap_turns = 0
                    opponent.partial_trap_damage = 0.0
    except Exception:
        pass

    return f"**{user.species}** passed its boosts!"

def apply_spectral_thief(user: Any, target: Any) -> str:
    """
    Spectral Thief: Steal target's stat boosts.
    
    Returns: message
    """
    stolen_any = False
    messages = []
    
    for stat, stage in target.stages.items():
        if stage > 0:
            user.stages[stat] = min(6, user.stages.get(stat, 0) + stage)
            target.stages[stat] = 0
            stolen_any = True
    
    if stolen_any:
        return f"**{user.species}** stole **{target.species}**'s stat boosts!"
    
    return ""

def apply_topsy_turvy(target: Any) -> str:
    """
    Topsy-Turvy: Invert all of target's stat changes.
    
    Returns: message
    """
    for stat in target.stages:
        target.stages[stat] = -target.stages[stat]
    
    return f"**{target.species}**'s stat changes were inverted!"

def apply_power_trick(user: Any) -> str:
    """
    Power Trick: Swap user's Attack and Defense stats.
    
    Returns: message
    """
    atk = user.stats['atk']
    defn = user.stats['defn']
    
    user.stats['atk'] = defn
    user.stats['defn'] = atk
    
    # Set flag to prevent stacking
    user._power_trick_active = not getattr(user, '_power_trick_active', False)
    
    return f"**{user.species}** swapped its Attack and Defense!"

def apply_guard_swap(user: Any, target: Any) -> str:
    """
    Guard Swap: Swap Defense and Special Defense stat stages.
    
    Returns: message
    """
    user_defn = user.stages.get('defn', 0)
    user_spd = user.stages.get('spd', 0)
    target_defn = target.stages.get('defn', 0)
    target_spd = target.stages.get('spd', 0)
    
    user.stages['defn'] = target_defn
    user.stages['spd'] = target_spd
    target.stages['defn'] = user_defn
    target.stages['spd'] = user_spd
    
    return f"**{user.species}** and **{target.species}** swapped their defensive boosts!"


def apply_guard_split(user: Any, target: Any) -> str:
    """
    Guard Split: Average user and target Defense/Special Defense stats.
    """
    if not hasattr(user, '_guard_split_original_stats'):
        user._guard_split_original_stats = {"defn": user.stats.get("defn", 1), "spd": user.stats.get("spd", 1)}
    if not hasattr(target, '_guard_split_original_stats'):
        target._guard_split_original_stats = {"defn": target.stats.get("defn", 1), "spd": target.stats.get("spd", 1)}
    
    user_def = user.stats.get("defn", 1)
    user_spd = user.stats.get("spd", 1)
    target_def = target.stats.get("defn", 1)
    target_spd = target.stats.get("spd", 1)
    
    new_def = max(1, (user_def + target_def) // 2)
    new_spd = max(1, (user_spd + target_spd) // 2)
    
    user.stats["defn"] = new_def
    user.stats["spd"] = new_spd
    target.stats["defn"] = new_def
    target.stats["spd"] = new_spd
    
    return f"{user.species} shared its guard with {target.species}!"


def apply_power_split(user: Any, target: Any) -> str:
    """
    Power Split: Average user and target Attack/Special Attack stats.
    """
    if not hasattr(user, '_power_split_original_stats'):
        user._power_split_original_stats = {"atk": user.stats.get("atk", 1), "spa": user.stats.get("spa", 1)}
    if not hasattr(target, '_power_split_original_stats'):
        target._power_split_original_stats = {"atk": target.stats.get("atk", 1), "spa": target.stats.get("spa", 1)}
    
    user_atk = user.stats.get("atk", 1)
    user_spa = user.stats.get("spa", 1)
    target_atk = target.stats.get("atk", 1)
    target_spa = target.stats.get("spa", 1)
    
    new_atk = max(1, (user_atk + target_atk) // 2)
    new_spa = max(1, (user_spa + target_spa) // 2)
    
    user.stats["atk"] = new_atk
    user.stats["spa"] = new_spa
    target.stats["atk"] = new_atk
    target.stats["spa"] = new_spa
    
    return f"{user.species} shared its power with {target.species}!"


def apply_power_swap(user: Any, target: Any) -> str:
    """
    Power Swap: Swap Attack and Special Attack stat stages.
    
    Returns: message
    """
    user_atk = user.stages.get('atk', 0)
    user_spa = user.stages.get('spa', 0)
    target_atk = target.stages.get('atk', 0)
    target_spa = target.stages.get('spa', 0)
    
    user.stages['atk'] = target_atk
    user.stages['spa'] = target_spa
    target.stages['atk'] = user_atk
    target.stages['spa'] = user_spa
    
    return f"**{user.species}** and **{target.species}** swapped their offensive boosts!"

def apply_speed_swap(user: Any, target: Any) -> str:
    """
    Speed Swap: Swap Speed stats (base stats, not stages).
    
    Returns: message
    """
    user_spe = user.stats['spe']
    target_spe = target.stats['spe']
    
    user.stats['spe'] = target_spe
    target.stats['spe'] = user_spe
    
    return f"**{user.species}** and **{target.species}** swapped their Speed stats!"

def apply_heart_swap(user: Any, target: Any) -> str:
    """
    Heart Swap: Swap ALL stat stages.
    
    Returns: message
    """
    user_stages = dict(user.stages)
    target_stages = dict(target.stages)
    
    user.stages = target_stages
    target.stages = user_stages
    
    return f"**{user.species}** and **{target.species}** swapped all their stat changes!"

# Store last damage for Counter/Mirror Coat/Metal Burst
def track_damage_taken(mon: Any, damage: int, category: str):
    """Track damage taken this turn for counter moves."""
    mon._last_damage_taken = damage
    mon._last_damage_category = category

def increment_turns_since_switch(mon: Any):
    """Increment turn counter for Fake Out family."""
    if not hasattr(mon, '_turns_since_switch_in'):
        mon._turns_since_switch_in = 0
    mon._turns_since_switch_in += 1

def reset_turns_since_switch(mon: Any):
    """Reset turn counter when switching in.
    This ensures Fake Out/First Impression can be used again when a Pokémon switches back in.
    Also resets Winter's Aegis melted status.
    """
    if mon:
        mon._turns_since_switch_in = 0
        # Reset per-switch Intimidate guard so it can trigger again next time it enters.
        mon._intimidate_activated_this_switch = False
        # Reset Winter's Aegis melted status when switching in
        if hasattr(mon, '_winters_aegis_melted'):
            delattr(mon, '_winters_aegis_melted')

def calculate_weight_based_power(move_name: str, target_weight_kg: float) -> int:
    """
    Calculate power for weight-based moves (Low Kick, Grass Knot).
    
    Returns: power based on target's weight
    """
    move_lower = move_name.lower().replace(" ", "-")
    
    if move_lower not in ["low-kick", "grass-knot"]:
        return 0
    
    # Power tiers based on weight (in kg)
    if target_weight_kg < 10.0:
        return 20
    elif target_weight_kg < 25.0:
        return 40
    elif target_weight_kg < 50.0:
        return 60
    elif target_weight_kg < 100.0:
        return 80
    elif target_weight_kg < 200.0:
        return 100
    else:
        return 120

def apply_psywave(user_level: int) -> Tuple[int, str]:
    """
    Psywave: Random damage between 0.5x and 1.5x user's level.
    
    Returns: (damage, message)
    """
    import random
    multiplier = random.uniform(0.5, 1.5)
    damage = max(1, int(user_level * multiplier))
    return damage, f"Psywave dealt random damage!"

def apply_magnitude(user: Any, target: Any) -> Tuple[int, int, str]:
    """
    Magnitude: Random power and damage.
    
    Returns: (magnitude_level, power, message)
    """
    import random
    
    # Magnitude distribution (gen 3+)
    roll = random.random()
    if roll < 0.05:  # 5%
        magnitude = 4
        power = 10
    elif roll < 0.15:  # 10%
        magnitude = 5
        power = 30
    elif roll < 0.35:  # 20%
        magnitude = 6
        power = 50
    elif roll < 0.65:  # 30%
        magnitude = 7
        power = 70
    elif roll < 0.85:  # 20%
        magnitude = 8
        power = 90
    elif roll < 0.95:  # 10%
        magnitude = 9
        power = 110
    else:  # 5%
        magnitude = 10
        power = 150
    
    return magnitude, power, f"Magnitude {magnitude}!"

def apply_present(user: Any, target: Any, *, generation: int = 9) -> Tuple[int, bool, str, bool]:
    """
    Present: Random damage or heal.
    Probabilities (from image):
    - 40%: 40 base power damage
    - 30%: 80 base power damage
    - 10%: 120 base power damage
    - 20%: Heal 1/4 of target's max HP
    
    Returns: (value, is_heal, message, succeeded)
    """
    import random

    roll = random.random()
    if roll < 0.4:
        return 40, False, "Present dealt damage!", True
    if roll < 0.7:
        return 80, False, "Present dealt damage!", True
    if roll < 0.8:
        return 120, False, "Present dealt massive damage!", True
    
    # 20% chance to heal 1/4 of target's max HP
    heal_amount = max(1, target.max_hp // 4)
    
    # Gen II: 20% chance to heal even at full HP (with different message)
    if generation == 2 and target.hp >= target.max_hp:
        # 20% of the 20% heal chance = 4% total chance to "heal" full HP Pokémon
        return heal_amount, True, "It couldn't receive the gift!", False
    
    # Gen III-IV: No effect if would heal full HP Pokémon
    if 3 <= generation <= 4 and target.hp >= target.max_hp:
        return heal_amount, True, "But it failed!", False
    
    return heal_amount, True, f"Present healed {target.species}!", True

def apply_trump_card(remaining_pp: int) -> int:
    """
    Trump Card: Power based on remaining PP.
    
    Returns: power
    """
    if remaining_pp == 0:
        return 200
    elif remaining_pp == 1:
        return 80
    elif remaining_pp == 2:
        return 60
    elif remaining_pp == 3:
        return 50
    else:
        return 40

def setup_future_sight(user: Any, target: Any, move_name: str, battle_state: Any, target_id: int) -> str:
    """Schedule Future Sight/Doom Desire to strike in the future."""
    if not hasattr(battle_state, '_future_attacks'):
        battle_state._future_attacks = {}

    if target_id in battle_state._future_attacks:
        existing = battle_state._future_attacks[target_id]
        if existing and existing.get('turns_left', 0) > 0:
            return "But it failed!"

    generation = get_generation(battle_state=battle_state)
    move_lower = move_name.lower().replace(" ", "-")
    if move_lower not in {"future-sight", "doom-desire"}:
        move_lower = "future-sight"

    # Doom Desire: Generation-specific damage calculation
    move_type: Optional[str]
    base_damage = 0
    use_attack_stat = False
    use_defense_stat = False
    
    if move_lower == "doom-desire":
        if generation == 3:
            # Gen III: Uses Attack and Defense at selection time, typeless
            move_type = None
            use_attack_stat = True
            use_defense_stat = True
            # Store user's Attack and target's Defense at selection time
            user_atk_at_selection = user.stats.get('atk', 0)
            target_def_at_selection = target.stats.get('defn', 0) if target else 0
            # Simplified damage calculation (would use proper formula with level, etc.)
            base_damage = int(user_atk_at_selection * 1.5)  # Approximate 120 BP
        elif generation == 4:
            # Gen IV: Uses Special Attack and Special Defense at selection time, typeless
            move_type = None
            # Store user's SpA and target's SpD at selection time
            user_spa_at_selection = user.stats.get('spa', 0)
            target_spd_at_selection = target.stats.get('spd', 0) if target else 0
            base_damage = int(user_spa_at_selection * 1.5)  # Approximate 120 BP
        elif generation >= 5:
            # Gen V+: Uses Special Attack at hit time, Steel-type, affected by type effectiveness
            move_type = "Steel"
            # Will be recalculated at hit time
            base_damage = int(user.stats.get('spa', 0) * 2.0)  # 140 BP base
            user_types = tuple(t.strip().title() if t else None for t in getattr(user, 'types', (None, None)))
            if "Steel" in user_types:
                base_damage = int(base_damage * 1.5)
    else:
        # Future Sight: Generation-specific mechanics
        if generation >= 5:
            # Gen V+: Psychic-type, calculated at hit time
            move_type = "Psychic"
            base_damage = int(user.stats.get('spa', 0) * 2.0)  # Will be recalculated at hit time
        user_types = tuple(t.strip().title() if t else None for t in getattr(user, 'types', (None, None)))
        if move_type and any(t == move_type for t in user_types):
            base_damage = int(base_damage * 1.5)
        else:
            # Gen II-IV: Typeless, uses stats at selection time
            move_type = None
            # Store user's SpA and target's SpD at selection time
            user_spa_at_selection = user.stats.get('spa', 0)
            target_spd_at_selection = target.stats.get('spd', 0) if target else 0
            # Calculate base damage using stats at selection time (80 BP in Gen II-IV)
            # This is a simplified calculation - actual damage uses proper formula with level
            base_damage = int(user_spa_at_selection * 1.6)  # Approximate 80 BP

    # Future Sight/Doom Desire: Hits 2 turns later (on turn 3)
    # Turn 1: Use move (turns_left = 2, skip decrement this turn)
    # Turn 2: Wait (turns_left = 1 after decrement)
    # Turn 3: Hit (turns_left = 0 after decrement)
    battle_state._future_attacks[target_id] = {
        'turns_left': 2,  # Hits 2 turns later
        'setup_turn': True,  # Flag to skip decrement on setup turn
        'damage': base_damage,
        'user_name': user.species,
        'move_name': move_name,
        'generation': generation,
        'move_type': move_type,
        'user_ref': user,
        'user_types': tuple(t.strip().title() if t else None for t in getattr(user, 'types', (None, None))),
        'target_ref': target if target else None,
        'calc_at_selection': generation <= 4,  # Both Future Sight and Doom Desire use stats at selection in Gen II-IV
        'use_attack_stat': use_attack_stat,
        'use_defense_stat': use_defense_stat
    }

    return f"{user.species} foresaw an attack!"


def _future_sight_multiplier(move_type: Optional[str], generation: int, target_types: List[str]) -> float:
    if move_type == "Psychic":
        multiplier = 1.0
        for t in target_types:
            if t == "Dark":
                return 0.0
            if t in {"Fighting", "Poison"}:
                multiplier *= 2.0
            elif t in {"Psychic", "Steel"}:
                multiplier *= 0.5
        return multiplier
    if move_type == "Steel":
        multiplier = 1.0
        for t in target_types:
            if t in {"Rock", "Ice", "Fairy"}:
                multiplier *= 2.0
            elif t in {"Fire", "Water", "Electric", "Steel"}:
                multiplier *= 0.5
        return multiplier
    return 1.0


def check_future_attacks(battle_state: Any, target_id: int) -> Optional[Tuple[int, str, str, Optional[str]]]:
    """
    Check and apply future attacks (Future Sight, Doom Desire).
    
    Returns: (damage, user_name, move_name) or None
    """
    if not hasattr(battle_state, '_future_attacks'):
        return None
    
    if target_id not in battle_state._future_attacks:
        return None
    
    attack = battle_state._future_attacks[target_id]
    
    # Skip decrement on the turn Future Sight is set up
    if attack.get('setup_turn', False):
        attack['setup_turn'] = False  # Clear flag after first check
    else:
        attack['turns_left'] -= 1
    
    if attack['turns_left'] <= 0:
        generation = attack.get('generation', 9)
        move_type = attack.get('move_type')
        user_name = attack.get('user_name', "")
        move_name = attack.get('move_name', "Future Sight")
        user_ref = attack.get('user_ref')

        calc_at_selection = attack.get('calc_at_selection', False)
        move_name_lower = attack.get('move_name', "").lower().replace(" ", "-")
        is_doom_desire = move_name_lower == "doom-desire"
        
        if is_doom_desire and generation >= 5:
            # Gen V+: Calculate damage at hit time using current stats
            if user_ref is not None and hasattr(user_ref, 'stats'):
                base_damage = int(user_ref.stats.get('spa', 0) * 2.0)  # 140 BP
                user_types = attack.get('user_types') or tuple(t.strip().title() if t else None for t in getattr(user_ref, 'types', (None, None)))
                if move_type == "Steel" and "Steel" in user_types:
                    base_damage = int(base_damage * 1.5)
        elif calc_at_selection:
            # Gen II-IV: Use stored damage from selection time (typeless, no type effectiveness)
            base_damage = attack.get('damage', 0)
        elif generation >= 5:
            # Future Sight Gen V+: Calculate at hit time
            if user_ref is not None and hasattr(user_ref, 'stats'):
                # Gen V: 100 BP, Gen VI+: 120 BP
                gen_fs = attack.get('generation', 9)
                if gen_fs == 5:
                    base_damage = int(user_ref.stats.get('spa', 0) * 2.0)  # 100 BP
                else:
                    base_damage = int(user_ref.stats.get('spa', 0) * 2.4)  # 120 BP
                user_types = attack.get('user_types') or tuple(t.strip().title() if t else None for t in getattr(user_ref, 'types', (None, None)))
                if move_type and any(t == move_type for t in user_types):
                    base_damage = int(base_damage * 1.5)
        else:
            # Gen II-IV Future Sight: Use stored damage
            base_damage = attack.get('damage', 0)

        target = None
        if hasattr(battle_state, '_active'):
            for uid in [battle_state.p1_id, battle_state.p2_id]:
                mon = battle_state._active(uid)
                if mon and id(mon) == target_id:
                    target = mon
                    break

        extra_msgs: List[str] = []
        multiplier = 1.0
        
        # Doom Desire Gen III-IV: Typeless, not affected by type effectiveness, can hit Wonder Guard
        if is_doom_desire and generation <= 4:
            # Typeless damage, no type effectiveness
            multiplier = 1.0
            # Cannot be protected by protection moves (already checked)
            # Can hit Wonder Guard (no immunity check needed)
        elif target is not None:
            target_types = [t.strip().title() for t in getattr(target, 'types', (None, None)) if t]
            
            if is_doom_desire and generation >= 5:
                # Gen V+: Steel-type, affected by type effectiveness
                multiplier = _future_sight_multiplier(move_type, generation, target_types)
            else:
                # Future Sight
                multiplier = _future_sight_multiplier(move_type, generation, target_types)

            if move_type == "Psychic" and multiplier == 0.0:
                extra_msgs.append(f"It doesn't affect {target.species}...")
            
            if move_type == "Steel" and multiplier == 0.0:
                extra_msgs.append(f"It doesn't affect {target.species}...")

            ability = normalize_ability_name(getattr(target, 'ability', '') or "")
            # Gen V+: Wonder Guard blocks Doom Desire if not super effective
            if is_doom_desire and generation >= 5:
                if ability == "wonder-guard" and multiplier <= 1.0:
                    multiplier = 0.0
                    extra_msgs.append(f"{target.species}'s Wonder Guard protected it!")
            elif ability == "wonder-guard" and multiplier <= 1.0:
                multiplier = 0.0
                extra_msgs.append(f"{target.species}'s Wonder Guard protected it!")
            
            if multiplier > 1.0:
                extra_msgs.append("It's super effective!")
            elif 0.0 < multiplier < 1.0:
                extra_msgs.append("It's not very effective...")

        damage = int(base_damage * multiplier)

        del battle_state._future_attacks[target_id]
        extra_msg = "\n".join(extra_msgs) if extra_msgs else None
        return (damage, user_name, move_name, extra_msg)
    
    return None

def check_and_apply_wish(battle_state: Any, user_id: int, mon: Any) -> Optional[str]:
    """
    Check and apply Wish healing at end of turn.
    
    Generation differences:
    - Gen III: Heals half of recipient's max HP
    - Gen V+: Heals half of user's max HP
    
    Returns: message or None
    """
    if not hasattr(battle_state, '_wish_healing'):
        return None
    
    if user_id not in battle_state._wish_healing:
        return None
    
    wish = battle_state._wish_healing[user_id]
    generation = wish.get('generation', 9)
    
    # Gen III: Use recipient's max HP
    # Gen V+: Use stored heal_amount (user's max HP / 2)
    if generation <= 4:
        heal_amount = mon.max_hp // 2  # Gen III-IV: Use recipient's HP
    else:
        heal_amount = wish.get('heal_amount', mon.max_hp // 2)  # Gen V+: Use stored amount (user's HP)
    wish['turns_left'] -= 1
    
    if wish['turns_left'] <= 0:
        # Wish activates!
        # Gen III: Use recipient's max HP
        # Gen V+: Use stored heal_amount (user's max HP / 2)
        if generation <= 4:
            heal_amount = mon.max_hp // 2  # Gen III-IV: Use recipient's HP
        else:
            heal_amount = wish.get('heal_amount', mon.max_hp // 2)  # Gen V+: Use stored amount
        user_name = wish['user_name']
        
        old_hp = mon.hp
        mon.hp = min(mon.max_hp, mon.hp + heal_amount)
        actual_heal = mon.hp - old_hp
        
        del battle_state._wish_healing[user_id]
        
        if actual_heal > 0:
            return f"**{user_name}'s** wish came true! {mon.species} restored {actual_heal} HP!"
        else:
            return f"**{user_name}'s** wish came true, but {mon.species} is already at full HP!"
    
    return None

def apply_destiny_bond(user: Any) -> str:
    """
    Destiny Bond: User is ready to take down attacker if KO'd.
    
    Returns: message
    """
    user._destiny_bond_active = True
    return f"**{user.species}** is trying to take its foe down with it!"

def check_destiny_bond(attacker: Any, defender: Any) -> bool:
    """
    Check if Destiny Bond should trigger (defender fainted with Destiny Bond active).
    
    Returns: True if attacker should faint
    Note: Dynamax Pokemon are immune to Destiny Bond.
    """
    if defender.hp <= 0 and getattr(defender, '_destiny_bond_active', False):
        # Dynamax Pokemon are immune to Destiny Bond
        if attacker.dynamaxed:
            return False
        return True
    return False

def apply_grudge(user: Any) -> str:
    """
    Grudge: If user faints, attacker's last move loses all PP.
    
    Returns: message
    """
    user._grudge_active = True
    return f"**{user.species}** wants its target to bear a grudge!"

def check_grudge(attacker: Any, defender: Any, last_move_used: str) -> Optional[str]:
    """
    Check if Grudge should trigger (defender fainted with Grudge active).
    
    Returns: message or None
    """
    if defender.hp <= 0 and getattr(defender, '_grudge_active', False):
        # In a full implementation, this would set the move's PP to 0
        # For now, just return a message
        return f"**{attacker.species}'s {last_move_used}** lost all its PP due to Grudge!"
    return None

def check_pre_move_damage(mon: Any) -> bool:
    """
    Check if Pokémon took damage before using its move this turn.
    Used for Focus Punch, Shell Trap, Beak Blast.
    
    Returns: True if damage was taken
    """
    return getattr(mon, '_took_damage_this_turn', False)

def set_pre_move_damage(mon: Any, took_damage: bool):
    """Set flag for pre-move damage tracking."""
    mon._took_damage_this_turn = took_damage

def reset_pre_move_damage(mon: Any):
    """Reset pre-move damage flag at turn start."""
    mon._took_damage_this_turn = False

def apply_conversion(user: Any, target: Any = None, field_effects: Any = None) -> str:
    """
    Conversion: Generation-specific type-changing mechanics.
    
    Gen I: Changes user's type to target's current type(s)
    Gen II-IV: Changes user's type to match one of user's moves (not matching current types)
    Gen V: Can be stolen by Snatch; can use Curse (Ghost-type)
    Gen VI-VII: Changes user's type to match first move slot
    Gen VIII: Banned initially (1.0-1.1.1), then same as Gen VI-VII
    
    Returns: message
    """
    from .generation import get_generation
    from .moves_loader import get_move
    
    generation = get_generation(field_effects=field_effects)
    
    # Gen VIII ban check (versions 1.0-1.1.1) - handled in move bans, assume usable here
    
    if generation == 1:
        # Gen I: Change to target's current type(s)
        if not target:
            return "But it failed!"
        target_types = tuple(t.strip().title() if t else None for t in target.types)
        if any(t == "Stellar" for t in target_types if t):
            return "But it failed!"
        user.types = target.types
        if target.types[1]:
            return f"**{user.species}** transformed into the {target.types[0]}/{target.types[1]} type!"
        else:
            return f"**{user.species}** transformed into the {target.types[0]} type!"
    
    elif 2 <= generation <= 7:
        # Gen II-VII: Change to match one of user's moves
        if not user.moves or len(user.moves) == 0:
            return "But it failed!"
        
        current_types = [t.strip().title() if t else None for t in getattr(user, 'types', (None, None))]
        
        # Find a move whose type doesn't match current types
        for move_name in user.moves:
            move_data = get_move(move_name)
            if not move_data:
                continue
            
            move_type = move_data.get("type", "Normal")
            if move_type.strip().title() == "Stellar":
                continue
            # Skip if move type matches any current type
            if move_type in current_types:
                continue
            
            # Skip Curse in Gen II-IV (??? type issue)
            if 2 <= generation <= 4 and move_name.lower() == "curse":
                continue
            
            # Gen V+: Curse is Ghost-type, can be used
            user.types = (move_type, None)
            return f"**{user.species}** transformed into the {move_type} type!"
        
        # All moves match current types - fails
        return "But it failed!"
    
    else:
        # Gen VIII+: Change to first move slot type
        if not user.moves or len(user.moves) == 0:
            return "But it failed!"
        
        first_move = user.moves[0]
        move_data = get_move(first_move)
        
        if not move_data:
            return "But it failed!"
        
        move_type = move_data.get("type", "Normal")
        if move_type.strip().title() == "Stellar":
            return "But it failed!"
        user.types = (move_type, None)
        
        # Z-Conversion: +1 to all stats
        if hasattr(user, '_is_z_move') and user._is_z_move:
            from .engine import modify_stages
            msgs = modify_stages(user, {"atk": 1, "defn": 1, "spa": 1, "spd": 1, "spe": 1}, caused_by_opponent=False, field_effects=field_effects)
            main_msg = f"**{user.species}** transformed into the {move_type} type!"
            for msg in msgs:
                main_msg += f"\n{msg}"
            return main_msg
        
        return f"**{user.species}** transformed into the {move_type} type!"

def apply_reflect_type(user: Any, target: Any) -> str:
    """
    Reflect Type: Change user's type to match target's types.
    
    Returns: message
    """
    target_types = tuple(t.strip().title() if t else None for t in target.types)
    if any(t == "Stellar" for t in target_types if t):
        return f"But it failed! ({target.species}'s type can't be mimicked!)"
    user.types = target.types
    
    if target.types[1]:
        return f"**{user.species}** became {target.types[0]}/{target.types[1]} type!"
    else:
        return f"**{user.species}** became {target.types[0]} type!"

def apply_forests_curse(target: Any) -> str:
    """
    Forest's Curse: Add Grass type to target.
    
    Returns: message
    """
    # Check if already has Grass type
    if "Grass" in target.types:
        return "But it failed!"
    
    # If mono-type, add as second type
    if not target.types[1]:
        target.types = (target.types[0], "Grass")
        return f"**{target.species}** gained the Grass type!"
    
    # If dual-type, store third type (rare case, game handles specially)
    if not hasattr(target, '_third_type'):
        target._third_type = "Grass"
        return f"**{target.species}** gained the Grass type!"
    
    return "But it failed!"

def apply_trick_or_treat_move(target: Any) -> str:
    """
    Trick-or-Treat: Add Ghost type to target.
    
    Returns: message
    """
    # Check if already has Ghost type
    if "Ghost" in target.types:
        return "But it failed!"
    
    # If mono-type, add as second type
    if not target.types[1]:
        target.types = (target.types[0], "Ghost")
        return f"**{target.species}** gained the Ghost type!"
    
    # If dual-type, store third type (rare case)
    if not hasattr(target, '_third_type'):
        target._third_type = "Ghost"
        return f"**{target.species}** gained the Ghost type!"
    
    return "But it failed!"

def apply_substitute(user: Any, field_effects: Any = None) -> str:
    """
    Substitute: Creates a substitute with HP cost.
    
    Gen I: Substitute HP is 1 higher than HP lost
    Gen II+: Substitute HP equals HP lost
    Gen II+: Fails if user doesn't have more than 25% HP left
    
    Returns: message
    """
    from .advanced_mechanics import Substitute
    from .generation import get_generation
    
    # Check if already has substitute
    if hasattr(user, 'substitute') and user.substitute:
        return "But it failed!"
    
    # Calculate HP cost (25% of max HP, rounded down)
    hp_cost = max(1, int(user.max_hp * 0.25))
    
    # Gen II+: Substitute fails if user doesn't have more than 25% HP left
    generation = get_generation(field_effects=field_effects)
    if generation >= 2:
        if user.hp <= hp_cost:
            return "But it failed!"
    
    # Gen I glitch: In handheld games, if user has exactly 25% HP, it creates substitute and immediately faints
    # In Stadium, Substitute fails if user has exactly 25% HP
    if generation == 1:
        if user.hp == hp_cost:
            # Handheld glitch: Create substitute and faint
            user.hp = 0
            substitute_hp = hp_cost + 1  # Gen I: +1 HP
            user.substitute = Substitute(hp=substitute_hp, max_hp=substitute_hp)
            return f"{user.species} made a substitute!\n{user.species} fainted from the cost!"
        elif user.hp < hp_cost:
            return "But it failed!"  # Stadium behavior: fail if less than 25%
    
    # Pay HP cost
    user.hp = max(0, user.hp - hp_cost)
    
    # Calculate substitute HP
    if generation == 1:
        # Gen I: Substitute HP is 1 higher than HP lost
        substitute_hp = hp_cost + 1
    else:
        # Gen II+: Substitute HP equals HP lost
        substitute_hp = hp_cost
    
    # Create substitute
    user.substitute = Substitute(hp=substitute_hp, max_hp=substitute_hp)
    
    msg = f"{user.species} made a substitute!"
    if user.hp <= 0:
        msg += f"\n{user.species} fainted from the cost!"
    
    # Z-Substitute: Reset all lowered stats
    if hasattr(user, '_is_z_move') and user._is_z_move:
        from .engine import modify_stages
        stat_resets = {}
        for stat in ["atk", "defn", "spa", "spd", "spe", "accuracy", "evasion"]:
            if user.stages.get(stat, 0) < 0:
                stat_resets[stat] = -user.stages.get(stat, 0)
        if stat_resets:
            msgs = modify_stages(user, stat_resets, caused_by_opponent=False, field_effects=field_effects)
            for m in msgs:
                msg += f"\n{m}"
    
    return msg

def apply_tri_attack_effects(user: Any, target: Any, move_name: str, dmg: int, field_effects: Any = None) -> List[str]:
    """
    Tri Attack: Random status effect and Gen II thawing.
    
    Gen I: No status effect
    Gen II+: 20% chance of burn/freeze/paralysis with generation-specific type immunities
    Gen II: 1/3 chance to thaw frozen targets
    
    Returns: list of messages
    """
    from .generation import get_generation
    from .db_move_effects import can_inflict_status
    
    messages = []
    generation = get_generation(field_effects=field_effects)
    move_lower = move_name.lower().replace(" ", "-")
    
    if move_lower != "tri-attack":
        return messages
    
    # Gen II: Thawing effect
    if dmg > 0 and generation == 2:
        target_was_frozen = (target.status and target.status.lower() in ["frz", "freeze"])
        if target_was_frozen:
            if random.random() < (1.0 / 3.0):
                target.status = None
                messages.append(f"{target.species} thawed out!")
    
    # Random status effect (Gen II+)
    if generation == 1:
        return messages  # Gen I: No status effect
    
    # Check for random status (20% chance)
    if random.random() < 0.2:
        # Check if target already has status
        valid_statuses = {"par", "brn", "slp", "frz", "psn", "tox", "sleep", "paralyze", "burn", "freeze", "poison", "toxic"}
        current_status = getattr(target, 'status', None)
        if current_status and str(current_status).lower().strip() in valid_statuses:
            return messages
        
        # Randomly select a status
        status_options = ["brn", "frz", "par"]
        status_to_inflict = random.choice(status_options)
        
        # Check type immunities (generation-specific)
        defender_types = [t.strip().title() if t else None for t in getattr(target, 'types', (None, None))]
        
        is_blocked = False
        if status_to_inflict == "par":
            if generation >= 6 and "Electric" in defender_types:
                is_blocked = True
        elif status_to_inflict == "brn":
            if generation >= 3 and "Fire" in defender_types:
                is_blocked = True
        elif status_to_inflict == "frz":
            if generation >= 3 and "Ice" in defender_types:
                is_blocked = True
        
        if not is_blocked:
            can_apply, reason = can_inflict_status(target, status_to_inflict, user=user, field_effects=field_effects)
            if can_apply:
                target.status = status_to_inflict
                status_names = {
                    "par": "paralyzed",
                    "brn": "burned",
                    "frz": "frozen"
                }
                messages.append(f"{target.species} was **{status_names.get(status_to_inflict, 'affected')}**!")
    
    return messages





