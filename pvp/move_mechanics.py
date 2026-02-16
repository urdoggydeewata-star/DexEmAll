"""
Move Mechanics System - Database-Driven
Loads move properties directly from database for accurate implementation.
Uses db_cache when available, then falls back to DB.
"""
from typing import Dict, Any, Optional, Tuple
from importlib import import_module
from functools import lru_cache
from .db_pool import get_connection

try:
    from lib import db_cache
except ImportError:
    db_cache = None

def _mechanics_from_move(r: Dict[str, Any]) -> Dict[str, Any]:
    import json
    meta = {}
    if r.get("meta"):
        try:
            m = r["meta"]
            meta = json.loads(m) if isinstance(m, str) else (m or {})
        except Exception:
            pass
    def _b(k):
        return bool(r.get(k))
    return {
        "name": r.get("name"),
        "type": r.get("type"),
        "power": r.get("power"),
        "accuracy": r.get("accuracy"),
        "pp": r.get("pp"),
        "damage_class": r.get("damage_class"),
        "is_recoil_move": _b("is_recoil_move"),
        "is_drain_move": _b("is_drain_move"),
        "is_multi_hit": _b("is_multi_hit"),
        "is_charge_move": _b("is_charge_move"),
        "is_semi_invulnerable": _b("is_semi_invulnerable"),
        "is_recharge_move": _b("is_recharge_move"),
        "is_ohko_move": _b("is_ohko_move"),
        "is_fixed_damage": _b("is_fixed_damage"),
        "is_variable_power": _b("is_variable_power"),
        "is_sound_move": _b("is_sound_move"),
        "is_contact_move": _b("is_contact_move"),
        "is_punch_move": _b("is_punch_move"),
        "is_bite_move": _b("is_bite_move"),
        "is_pulse_move": _b("is_pulse_move"),
        "is_bullet_move": _b("is_bullet_move"),
        "crash_damage": _b("crash_damage"),
        "meta": meta,
    }


def _get_move_mechanics_impl(move_name: str, battle_state: Any = None) -> Optional[Dict[str, Any]]:
    if not move_name:
        return None
    normalized = move_name.lower().replace(' ', '-').strip()
    if not normalized:
        return None
    if normalized == 'struggle':
        return {
            'name': 'struggle', 'type': 'Typeless', 'power': 50, 'accuracy': None, 'pp': 1,
            'damage_class': 'physical', 'is_recoil_move': True, 'is_drain_move': False,
            'is_multi_hit': False, 'is_charge_move': False, 'is_semi_invulnerable': False,
            'is_recharge_move': False, 'is_ohko_move': False, 'is_fixed_damage': False,
            'is_variable_power': False, 'is_sound_move': False, 'is_contact_move': False,
            'is_punch_move': False, 'is_bite_move': False, 'is_pulse_move': False,
            'is_bullet_move': False, 'crash_damage': False, 'meta': {},
        }
    if battle_state and hasattr(battle_state, "get_cached_move"):
        r = battle_state.get_cached_move(move_name) or battle_state.get_cached_move(normalized)
        if r:
            row = dict(r) if hasattr(r, "keys") and not isinstance(r, dict) else r
            return _mechanics_from_move(row)
    if db_cache:
        r = db_cache.get_cached_move(normalized) or db_cache.get_cached_move(move_name)
        if r:
            row = dict(r) if hasattr(r, "keys") and not isinstance(r, dict) else r
            return _mechanics_from_move(row)
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM moves WHERE LOWER(REPLACE(name, ' ', '-')) = ? LIMIT 1",
                (normalized,)
            ).fetchone()
            if not row:
                return None
            r = dict(row) if hasattr(row, "keys") and not isinstance(row, dict) else row
            return _mechanics_from_move(r)
    except Exception:
        return None


@lru_cache(maxsize=1024)
def _get_move_mechanics_cached(move_name: str) -> Optional[Dict[str, Any]]:
    return _get_move_mechanics_impl(move_name, None)


def get_move_mechanics(move_name: str, battle_state: Any = None) -> Optional[Dict[str, Any]]:
    """
    Get move mechanics from database.
    Uses battle_state move cache when provided, then db_cache, then DB.
    """
    if battle_state is not None:
        return _get_move_mechanics_impl(move_name, battle_state)
    return _get_move_mechanics_cached(move_name)


def calculate_ohko_damage(attacker_level: int, defender_level: int, move_name: str, field_effects: Any = None, attacker: Any = None, defender: Any = None) -> Tuple[bool, str]:
    """
    Calculate OHKO move success with generation-specific mechanics.
    Returns (success, message)
    
    Generation differences:
    - Gen I (Horn Drill): Fixed 65535 damage, 30% accuracy, fails if target Speed > user Speed
    - Gen II (Horn Drill): Accuracy = ((Level_user - Level_target) × 2 + 76) / 256 × 100%, affected by acc/eva
    - Gen III+ (OHKO moves): Accuracy = 30% + (Level_user - Level_target)%, NOT affected by acc/eva
    """
    import random
    from .generation import get_generation
    
    generation = get_generation(field_effects=field_effects) if field_effects else 9
    move_lower = move_name.lower().replace(" ", "-")
    
    # Horn Drill: Generation-specific mechanics
    if move_lower == "horn-drill":
        # Gen I: Speed check - fails if target Speed > user Speed
        if generation == 1:
            if attacker and defender:
                user_speed = getattr(attacker, 'stats', {}).get("spe", 0)
                target_speed = getattr(defender, 'stats', {}).get("spe", 0)
                if target_speed > user_speed:
                    return False, "It failed! (target is faster)"
            
            # Gen I: 30% base accuracy
            if random.random() * 100 < 30:
                return True, "It's a one-hit KO!"
            else:
                return False, "It failed!"
        
        # Gen II: Formula: ((Level_user - Level_target) × 2 + 76) / 256 × 100%
        elif generation == 2:
            # OHKO moves fail if target is higher level
            if defender_level > attacker_level:
                return False, "It failed! (target is higher level)"
            
            # Gen II formula: ((Level_user - Level_target) × 2 + 76) / 256 × 100%
            level_diff = attacker_level - defender_level
            accuracy_raw = ((level_diff * 2) + 76) / 256 * 100
            
            # Cap at 100% if user is 90+ levels higher
            if level_diff >= 90:
                accuracy_raw = 100.0
            
            # Gen II: Affected by accuracy and evasion stats
            # For now, use base accuracy (full implementation would check acc/eva stages)
            if random.random() * 100 < accuracy_raw:
                return True, "It's a one-hit KO!"
            else:
                return False, "It failed!"
        
        # Gen III+: Standard formula (not affected by acc/eva)
        else:
            # OHKO moves fail if target is higher level
            if defender_level > attacker_level:
                return False, "It failed! (target is higher level)"
            
            # Gen III+: Accuracy = 30% + (Level_user - Level_target)%
            # NOT affected by accuracy/evasion stats
            accuracy = 30 + (attacker_level - defender_level)
            
            # Cap at 100% if user is 70+ levels higher (Gen III+)
            if accuracy > 100:
                accuracy = 100
            
            # Roll for hit
            if random.random() * 100 < accuracy:
                return True, "It's a one-hit KO!"
            else:
                return False, "It failed!"
    
    # Fissure: Generation-specific mechanics
    if move_lower == "fissure":
        # Gen I: Fixed 65535 damage, 30% accuracy, Speed check
        if generation == 1:
            if attacker and defender:
                def _effective_speed(mon_obj):
                    try:
                        engine_mod = import_module("pvp.engine")
                        getter = getattr(engine_mod, "get_effective_stat", None)
                    except Exception:
                        getter = None
                    if getter:
                        return getter(mon_obj, "spe")
                    return getattr(mon_obj, "stats", {}).get("spe", 0)

                user_speed = _effective_speed(attacker)
                target_speed = _effective_speed(defender)
                if target_speed > user_speed:
                    return False, "It failed! (target is faster)"
            
            # Gen I: 30% base accuracy, affected by type immunities
            if random.random() * 100 < 30:
                return True, "It's a one-hit KO!"
            else:
                return False, "It failed!"
        
        # Gen II: Formula: ((Level_user - Level_target) × 2 + 76) / 256 × 100%, affected by acc/eva
        elif generation == 2:
            if defender_level > attacker_level:
                return False, "It failed! (target is higher level)"
            
            # Gen II formula: ((Level_user - Level_target) × 2 + 76) / 256 × 100%
            level_diff = attacker_level - defender_level
            accuracy_raw = ((level_diff * 2) + 76) / 256 * 100
            
            # Cap at 100% if user is 90+ levels higher
            if level_diff >= 90:
                accuracy_raw = 100.0
            
            # Gen II: Affected by accuracy and evasion stats (not fully implemented here)
            if random.random() * 100 < accuracy_raw:
                return True, "It's a one-hit KO!"
            else:
                return False, "It failed!"
        
        # Gen III+: Standard formula (not affected by acc/eva, cannot hit semi-invulnerable, fails vs Dynamax)
        else:
            if defender_level > attacker_level:
                return False, "It failed! (target is higher level)"
            
            # Check for Dynamax (Gen VIII+)
            if generation >= 8 and defender and hasattr(defender, 'dynamaxed') and defender.dynamaxed:
                return False, "It failed! (Dynamax immunity)"
            
            # Check for semi-invulnerable (Fly, Dig, etc.)
            if defender and hasattr(defender, 'invulnerable') and defender.invulnerable:
                return False, "It failed! (target is invulnerable)"
            
            # Gen III+: Accuracy = 30% + (Level_user - Level_target)%
            # NOT affected by accuracy/evasion stats
            accuracy = 30 + (attacker_level - defender_level)
            
            # Cap at 100% if user is 70+ levels higher
            if accuracy > 100:
                accuracy = 100
            
            if random.random() * 100 < accuracy:
                return True, "It's a one-hit KO!"
            else:
                return False, "It failed!"
    
    # Other OHKO moves (Guillotine, Sheer Cold)
    # OHKO moves fail if target is higher level
    if defender_level > attacker_level:
        return False, "It failed! (target is higher level)"
    
    # Gen III+: Standard formula (not affected by acc/eva)
    accuracy = 30 + (attacker_level - defender_level)
    
    # Cap at 100%
    if accuracy > 100:
        accuracy = 100
    
    # Sheer Cold: Generation-specific mechanics
    if move_lower == 'sheer-cold' and attacker and defender:
        from .generation import get_generation
        gen_sc = get_generation(field_effects=field_effects) if field_effects else 9
        
        attacker_types = [t.strip().title() if t else None for t in getattr(attacker, 'types', (None, None))]
        defender_types = [t.strip().title() if t else None for t in getattr(defender, 'types', (None, None))]
        
        # Gen VII+: Ice-type Pokémon are immune to Sheer Cold
        if gen_sc >= 7:
            if "Ice" in defender_types:
                return False, "It doesn't affect Ice-type Pokémon!"
            
            # Gen VII+: Base accuracy is 20% if user is NOT Ice-type, 30% if Ice-type
            if "Ice" not in attacker_types:
                # Non-Ice user: 20% base instead of 30%
                accuracy = 20 + (attacker_level - defender_level)
                # Cap at 100% if user is 80+ levels higher (for 20% base)
                if accuracy > 100:
                    accuracy = 100
            else:
                # Ice-type user: Normal 30% base
                accuracy = 30 + (attacker_level - defender_level)
                # Cap at 100% if user is 70+ levels higher
                if accuracy > 100:
                    accuracy = 100
            
            if random.random() * 100 < accuracy:
                return True, "It's a one-hit KO!"
            else:
                return False, "It failed!"
    
    # Roll for hit (Gen III-VI for Sheer Cold, or other OHKO moves)
    if random.random() * 100 < accuracy:
        return True, "It's a one-hit KO!"
    else:
        return False, "It failed!"


def calculate_fixed_damage(move_name: str, user_level: int, user_hp: int = 0, target_hp: int = 0, user: Any = None) -> Optional[int]:
    """
    Calculate fixed damage for moves like Dragon Rage, Sonic Boom, etc.
    Returns damage amount or None if not a fixed damage move.
    
    Args:
        move_name: Name of the move
        user_level: User's level
        user_hp: User's current HP
        target_hp: Target's current HP
        user: User Pokemon object (for generation context, optional)
    """
    move_lower = move_name.lower().replace(' ', '-')
    
    # Exact fixed damage moves
    if move_lower == 'dragon-rage':
        return 40
    elif move_lower == 'sonic-boom':
        return 20
    
    # Level-based damage
    elif move_lower in ['night-shade', 'seismic-toss']:
        return user_level
    
    # Psywave: Generation-specific random damage formulas
    elif move_lower == 'psywave':
        import random
        from .generation import get_generation
        # Get generation from context if available, otherwise default to 9
        generation_psy = getattr(user, '_generation_context', 9) if user and hasattr(user, '_generation_context') else 9
        
        if generation_psy == 1:
            # Gen I: Random between 1 and 1.5x level (player), 0 and 1.5x level (opponent)
            # For simplicity, use 1-1.5x (minimum 1 to avoid desync)
            damage = max(1, int(user_level * random.uniform(1.0, 1.5)))
            return damage
        elif generation_psy == 2:
            # Gen II: Random between 1 HP and 1.5x level (rounded down), always at least 1
            damage = max(1, int(user_level * random.uniform(1.0, 1.5)))
            return damage
        elif generation_psy <= 4:
            # Gen III-IV: ⌊Level × (10r + 50) / 100⌋, where r is 0-10
            r = random.randint(0, 10)
            damage = (user_level * (10 * r + 50)) // 100
            return max(1, damage)  # At least 1 HP
        elif generation_psy == 5:
            # Gen V: ⌊Level × (r + 50) / 100⌋, where r is 0-100
            r = random.randint(0, 100)
            damage = (user_level * (r + 50)) // 100
            return max(1, damage)  # At least 1 HP
        else:
            # Gen VI-VII: Same formula as Gen V (banned Gen VIII+)
            r = random.randint(0, 100)
            damage = (user_level * (r + 50)) // 100
            return max(1, damage)  # At least 1 HP
    
    # Super Fang: Half of target's current HP
    elif move_lower == 'super-fang':
        return max(1, target_hp // 2)
    
    # Final Gambit: Equal to user's current HP (user faints)
    elif move_lower == 'final-gambit':
        return user_hp
    
    # Endeavor: Reduces target HP to match user's HP
    elif move_lower == 'endeavor':
        if target_hp > user_hp:
            return target_hp - user_hp
        return 0  # Fails if user HP >= target HP
    
    return None


def calculate_recoil_damage(move_name: str, damage_dealt: int, user_max_hp: int, field_effects: Any = None) -> int:
    """
    Calculate recoil damage from recoil moves.
    Returns recoil damage amount.
    
    Struggle has generation-specific recoil:
    - Gen I: 1/2 of damage dealt
    - Gen II-III: 1/4 of damage dealt
    - Gen IV+: 1/4 of user's max HP (rounded down, minimum 1)
    - Gen V+: Standard rounding applies
    """
    move_lower = move_name.lower().replace(' ', '-')
    
    # Struggle: Generation-specific recoil
    if move_lower == 'struggle':
        from .generation import get_generation
        generation = get_generation(field_effects=field_effects) if field_effects else 9
        
        if generation == 1:
            # Gen I: 1/2 of damage dealt
            return max(1, damage_dealt // 2)
        elif generation <= 3:
            # Gen II-III: 1/4 of damage dealt
            return max(1, damage_dealt // 4)
        else:
            # Gen IV+: 1/4 of user's max HP
            # Gen IV: Rounded down, minimum 1
            # Gen V+: Standard rounding (e.g., 201 HP = 50, 202-203 HP = 51)
            if generation == 4:
                recoil = user_max_hp // 4
                return max(1, recoil)
            else:
                # Gen V+: Standard rounding
                recoil = (user_max_hp * 25 + 50) // 100  # Standard rounding: (HP * 25 + 50) / 100
                return max(1, recoil)
    
    # Generation-specific recoil calculations
    from .generation import get_generation
    generation = get_generation(field_effects=field_effects) if field_effects else 9
    
    # Take Down: 1/4 Gen I+, but Gen I has special conditions
    if move_lower == 'take-down':
        # Gen I: No recoil on KO or substitute break (handled separately)
        # Gen II+: Always 1/4
        return max(1, damage_dealt // 4)
    
    # Double-Edge: Gen I-II 1/4, Gen III+ 1/3
    if move_lower == 'double-edge':
        if generation <= 2:
            # Gen I: No recoil on KO or substitute break (handled separately)
            # Gen II: Recoil even on substitute break
            return max(1, damage_dealt // 4)
        else:
            # Gen III+: 1/3
            return max(1, damage_dealt // 3)
    
    # Brave Bird: 1/3 of damage dealt (33%)
    if move_lower == 'brave-bird':
        return max(1, damage_dealt // 3)
    
    # Most recoil moves: 1/4 of damage dealt (25%)
    recoil_quarter = {
        'submission', 'volt-tackle', 
        'flare-blitz', 'wild-charge', 'wood-hammer',
        'head-charge', 'wave-crash'
    }
    
    # High recoil: 1/2 of damage dealt (50%)
    recoil_half = {
        'head-smash', 'light-of-ruin'
    }
    
    # Special: Based on max HP
    if move_lower in ['mind-blown', 'steel-beam']:
        return user_max_hp // 2  # 1/2 max HP
    elif move_lower == 'chloroblast':
        return user_max_hp // 2  # 1/2 max HP
    
    # High Jump Kick / Jump Kick: If miss, take 1/2 max HP
    # (This is handled separately in accuracy check)
    
    # Standard recoil calculations
    if move_lower in recoil_half:
        return max(1, damage_dealt // 2)
    elif move_lower in recoil_quarter:
        return max(1, damage_dealt // 4)
    else:
        # Default: 1/3 of damage dealt (33%)
        return max(1, damage_dealt // 3)


def calculate_drain_healing(move_name: str, damage_dealt: int) -> int:
    """
    Calculate HP recovered from drain moves.
    Returns healing amount.
    """
    move_lower = move_name.lower().replace(' ', '-')
    
    # Most drain moves: 50% of damage
    drain_50_percent = {
        'absorb', 'mega-drain', 'giga-drain', 'drain-punch', 'leech-life',
        'draining-kiss', 'horn-leech', 'parabolic-charge'
    }
    
    # Dream Eater: 50% (but only works on sleeping targets)
    # Special case: If damage is 1 HP, heal 1 HP (not 0)
    if move_lower == 'dream-eater':
        if damage_dealt == 1:
            return 1  # Special case: 1 HP damage = 1 HP healed
        return max(1, damage_dealt // 2) if damage_dealt > 0 else 0
    
    # Strength Sap: Heals equal to target's Attack stat (handled separately)
    
    # Default: 50% of damage dealt
    if move_lower == 'oblivion-wing':
        return max(1, (damage_dealt * 3) // 4) if damage_dealt > 0 else 0
    
    if move_lower in drain_50_percent:
        return max(1, damage_dealt // 2) if damage_dealt > 0 else 0
    
    # Big Root boosts healing by 30% (handled in item effects)
    return max(1, damage_dealt // 2) if damage_dealt > 0 else 0


def get_multi_hit_count(move_name: str, meta: Dict[str, Any], user_ability: str = None, field_effects: Any = None, user: Any = None) -> int:
    """
    Determine how many times a multi-hit move hits.
    Returns number of hits.
    
    Skill Link (Gen 4+): Multistrike moves with variable hits always hit max times.
    Ash-Greninja (Battle Bond): Water Shuriken always hits 3 times.
    """
    import random
    
    # Get generation
    from .generation import get_generation
    generation = get_generation(field_effects=field_effects) if field_effects else 9
    
    # Specific moves with known hit counts
    move_lower = move_name.lower().replace(' ', '-')
    
    # Ash-Greninja (Battle Bond): Water Shuriken always hits 3 times
    if move_lower == "water-shuriken" and user:
        # Check if user is Ash-Greninja (Battle Bond form)
        species_lower = getattr(user, 'species', '').lower()
        form = getattr(user, 'form', None)
        # Check for Ash-Greninja: form == "ash" or species contains "battle-bond" or "ash"
        if (species_lower == "greninja" and (form == "ash" or form == "battle-bond")) or "battle-bond" in species_lower or (species_lower == "greninja" and "ash" in str(form).lower()):
            return 3
    
    # Check for Skill Link ability
    has_skill_link = False
    if user_ability:
        from .abilities import normalize_ability_name
        ability_norm = normalize_ability_name(user_ability)
        has_skill_link = (ability_norm == "skill-link")
    
    # Check meta data first
    min_hits = meta.get('min_hits')
    max_hits = meta.get('max_hits')
    
    if min_hits and max_hits:
        if min_hits == max_hits:
            # Fixed number of hits (e.g., Double Kick = 2)
            return min_hits
        else:
            # Variable hits (e.g., Fury Attack = 2-5)
            if has_skill_link and generation >= 4:
                # Skill Link: Always hit maximum
                return max_hits
            # Normal distribution: 35% for 2, 35% for 3, 15% for 4, 15% for 5
            roll = random.random()
            if roll < 0.35:
                return min_hits
            elif roll < 0.70:
                return min_hits + 1
            elif roll < 0.85:
                return min_hits + 2
            else:
                return max_hits
    
    # Always 2 hits
    two_hit_moves = {
        'double-kick', 'double-slap', 'bonemerang', 'double-iron-bash',
        'dual-chop', 'dual-wingbeat', 'dragon-darts', 'gear-grind', 'twineedle'
    }
    
    # Always 3 hits
    three_hit_moves = {
        'triple-kick', 'triple-axel', 'surging-strikes'
    }
    
    # 2-5 hits
    two_to_five_moves = {
        'fury-attack', 'fury-swipes', 'comet-punch', 'pin-missile',
        'spike-cannon', 'icicle-spear', 'rock-blast', 'tail-slap',
        'bullet-seed', 'bone-rush', 'arm-thrust', 'barrage', 'water-shuriken',
        'scale-shot'
    }
    
    if move_lower in two_hit_moves:
        return 2
    elif move_lower in three_hit_moves:
        # Skill Link: Triple Kick and Triple Axel always hit 3 times
        return 3
    elif move_lower in two_to_five_moves:
        # Skill Link: Always hit 5 times (Gen 4+)
        if has_skill_link and generation >= 4:
            return 5
        
        # Arm Thrust: Generation-specific probabilities
        if move_lower == "arm-thrust":
            if generation <= 4:
                # Gen III-IV: 37.5% for 2, 37.5% for 3, 12.5% for 4, 12.5% for 5
                roll = random.random()
                if roll < 0.375:
                    return 2
                elif roll < 0.75:
                    return 3
                elif roll < 0.875:
                    return 4
                else:
                    return 5
            else:
                # Gen V+: 35% for 2, 35% for 3, 15% for 4, 15% for 5
                roll = random.random()
                if roll < 0.35:
                    return 2
                elif roll < 0.70:
                    return 3
                elif roll < 0.85:
                    return 4
                else:
                    return 5
        
        # Fury Attack: Generation-specific probabilities
        if move_lower == "fury-attack":
            if generation == 1:
                # Gen I: 37.5% for 2, 37.5% for 3, 12.5% for 4, 12.5% for 5
                roll = random.random()
                if roll < 0.375:
                    return 2
                elif roll < 0.75:
                    return 3
                elif roll < 0.875:
                    return 4
                else:
                    return 5
            elif generation >= 5:
                # Gen V+: 35% for 2, 35% for 3, 15% for 4, 15% for 5
                roll = random.random()
                if roll < 0.35:
                    return 2
                elif roll < 0.70:
                    return 3
                elif roll < 0.85:
                    return 4
                else:
                    return 5
            else:
                # Gen II-IV: 37.5% for 2, 37.5% for 3, 12.5% for 4, 12.5% for 5
                roll = random.random()
                if roll < 0.375:
                    return 2
                elif roll < 0.75:
                    return 3
                elif roll < 0.875:
                    return 4
                else:
                    return 5
        
        # Fury Swipes: Generation-specific probabilities
        if move_lower == "fury-swipes":
            if generation == 1:
                # Gen I: 37.5% for 2, 37.5% for 3, 12.5% for 4, 12.5% for 5
                roll = random.random()
                if roll < 0.375:
                    return 2
                elif roll < 0.75:
                    return 3
                elif roll < 0.875:
                    return 4
                else:
                    return 5
            elif generation >= 5:
                # Gen V+: 35% for 2, 35% for 3, 15% for 4, 15% for 5
                roll = random.random()
                if roll < 0.35:
                    return 2
                elif roll < 0.70:
                    return 3
                elif roll < 0.85:
                    return 4
                else:
                    return 5
            else:
                # Gen II-IV: 37.5% for 2, 37.5% for 3, 12.5% for 4, 12.5% for 5
                roll = random.random()
                if roll < 0.375:
                    return 2
                elif roll < 0.75:
                    return 3
                elif roll < 0.875:
                    return 4
                else:
                    return 5
        
        # Bone Rush: Generation-specific probabilities
        if move_lower == "bone-rush":
            if generation >= 5:
                # Gen V+: 35% for 2, 35% for 3, 15% for 4, 15% for 5
                roll = random.random()
                if roll < 0.35:
                    return 2
                elif roll < 0.70:
                    return 3
                elif roll < 0.85:
                    return 4
                else:
                    return 5
            else:
                # Gen II-IV: 37.5% for 2, 37.5% for 3, 12.5% for 4, 12.5% for 5
                roll = random.random()
                if roll < 0.375:
                    return 2
                elif roll < 0.75:
                    return 3
                elif roll < 0.875:
                    return 4
                else:
                    return 5
        
        # Barrage: Generation-specific probabilities (same as Spike Cannon)
        if move_lower == "barrage":
            if generation == 1:
                # Gen I: 37.5% for 2, 37.5% for 3, 12.5% for 4, 12.5% for 5
                roll = random.random()
                if roll < 0.375:
                    return 2
                elif roll < 0.75:
                    return 3
                elif roll < 0.875:
                    return 4
                else:
                    return 5
            elif 5 <= generation <= 7:
                # Gen V-VII: 35% for 2, 35% for 3, 15% for 4, 15% for 5
                roll = random.random()
                if roll < 0.35:
                    return 2
                elif roll < 0.70:
                    return 3
                elif roll < 0.85:
                    return 4
                else:
                    return 5
            else:
                # Gen II-IV and Gen VIII+: Use standard distribution
                roll = random.random()
                if roll < 0.35:
                    return 2
                elif roll < 0.70:
                    return 3
                elif roll < 0.85:
                    return 4
                else:
                    return 5
        
        # Spike Cannon: Generation-specific probabilities
        if move_lower == "spike-cannon":
            if generation == 1:
                # Gen I: 37.5% for 2, 37.5% for 3, 12.5% for 4, 12.5% for 5
                roll = random.random()
                if roll < 0.375:
                    return 2
                elif roll < 0.75:
                    return 3
                elif roll < 0.875:
                    return 4
                else:
                    return 5
            elif 5 <= generation <= 7:
                # Gen V-VII: 35% for 2, 35% for 3, 15% for 4, 15% for 5
                roll = random.random()
                if roll < 0.35:
                    return 2
                elif roll < 0.70:
                    return 3
                elif roll < 0.85:
                    return 4
                else:
                    return 5
            else:
                # Gen II-IV and Gen VIII+: Use standard distribution
                roll = random.random()
                if roll < 0.35:
                    return 2
                elif roll < 0.70:
                    return 3
                elif roll < 0.85:
                    return 4
                else:
                    return 5
        else:
            # Other 2-5 hit moves: Standard distribution (Gen V-VII probabilities)
            roll = random.random()
            if roll < 0.35:
                return 2
            elif roll < 0.70:
                return 3
            elif roll < 0.85:
                return 4
            else:
                return 5
    
    # Population Bomb: 1-10 hits (90% accuracy per hit)
    if move_lower == 'population-bomb':
        # Skill Link: Always hit 10 times
        if has_skill_link:
            return 10
        hits = 0
        for _ in range(10):
            if random.random() < 0.9:
                hits += 1
            else:
                break
        return max(1, hits)
    
    # Default
    return 1

