"""
Pokémon Battle AI System
Based on Run and Bun (1.07) AI document by Croven

The AI calculates a score for every move and chooses the highest scoring move.
If multiple moves have the same score, it randomly selects between them.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Tuple, Any
import random
import math
import json

from .engine import Mon, get_move, damage, type_multiplier, stab, get_generation, speed_value, can_switch_out
# PP helper for PvP bot scoring; keep scoped import to avoid cycles
try:
    from .panel import _max_pp
except Exception:
    _max_pp = lambda move_name, generation=9: 20
from .abilities import normalize_ability_name, get_ability_effect
from .moves_loader import get_move as load_move
from .move_effects import get_move_secondary_effect
from .generation import get_generation as get_gen

# Global battle analysis cache (per battle)
_battle_analysis: Dict[int, Dict[str, Any]] = {}


def calculate_move_score(
    user: Mon,
    target: Mon,
    move_name: str,
    battle_state: Any,
    field_effects: Any,
    user_side: Any,
    target_side: Any,
    is_double_battle: bool = False,
    is_highest_damage: bool = False
) -> float:
    """
    Calculate AI score for a move based on Run and Bun AI logic.
    
    Returns:
        Score for the move (higher is better)
    """
    move_lower = move_name.lower().replace(" ", "-")
    move_data = get_move(move_name)
    
    if not move_data:
        return -20  # Unknown move, never use
    
    # Check if move is useless (already set hazards, status already applied, etc.)
    if _is_move_useless(user, target, move_name, move_data, battle_state, field_effects, target_side):
        return -20
    
    # Get move category and power
    move_category = (move_data.get("category") or move_data.get("damage_class") or "status").lower()
    move_power = move_data.get("power", 0) or 0
    
    # Default score for non-attacking moves
    if move_category == "status" or move_power <= 0:
        base_score = 6.0
    else:
        base_score = 0.0
    
    # Calculate damage for attacking moves
    if move_category != "status" and move_power > 0:
        base_score = _score_damaging_move(
            user, target, move_name, move_data, battle_state, field_effects, user_side, target_side, is_highest_damage
        )
    
    # Apply special move scoring (additive bonuses)
    special_score = _score_special_move(
        user, target, move_name, move_lower, move_data, battle_state, field_effects, 
        user_side, target_side, is_double_battle
    )
    
    # Apply general improvements (PP management, type effectiveness, synergy, etc.)
    general_bonus = _calculate_general_bonuses(
        user, target, move_name, move_lower, move_data, battle_state, field_effects, user_side, target_side
    )
    
    return base_score + special_score + general_bonus


def _is_move_useless(
    user: Mon,
    target: Mon,
    move_name: str,
    move_data: Dict[str, Any],
    battle_state: Any,
    field_effects: Any,
    target_side: Any
) -> bool:
    """Check if a move is useless (already set, status already applied, etc.)"""
    move_lower = move_name.lower().replace(" ", "-")
    
    # Stealth Rock already set
    if move_lower == "stealth-rock":
        if target_side and getattr(target_side, 'stealth_rock', False):
            return True
    
    # Spikes already at max (3 layers)
    if move_lower in ["spikes", "toxic-spikes"]:
        if target_side:
            if move_lower == "spikes" and getattr(target_side, 'spikes', 0) >= 3:
                return True
            if move_lower == "toxic-spikes" and getattr(target_side, 'toxic_spikes', 0) >= 2:
                return True
    
    # Sticky Web already set
    if move_lower == "sticky-web":
        if target_side and getattr(target_side, 'sticky_web', False):
            return True
    
    # Status already applied
    if move_lower in ["thunder-wave", "stun-spore", "glare", "nuzzle"]:
        if target.status == "par":
            return True
    
    if move_lower in ["will-o-wisp"]:
        if target.status == "brn":
            return True
    
    if move_lower in ["toxic"]:
        if target.status in ["psn", "tox"]:
            return True
    
    # Trick Room already active
    if move_lower == "trick-room":
        if field_effects and getattr(field_effects, 'trick_room', False):
            return True
    
    # Terrain already active
    if move_lower in ["electric-terrain", "grassy-terrain", "psychic-terrain", "misty-terrain"]:
        terrain_map = {
            "electric-terrain": "electric",
            "grassy-terrain": "grassy",
            "psychic-terrain": "psychic",
            "misty-terrain": "misty"
        }
        if field_effects and getattr(field_effects, 'terrain', None) == terrain_map.get(move_lower):
            return True
    
    # Recovery at full HP
    if move_lower in ["recover", "slack-off", "heal-order", "soft-boiled", "roost", "strength-sap", 
                      "morning-sun", "synthesis", "moonlight", "rest"]:
        if user.hp >= user.max_hp:
            return True
    
    # Encore on already Encored target
    if move_lower == "encore":
        if getattr(target, 'encored_move', None) and getattr(target, 'encore_turns', 0) > 0:
            return True
        # First turn out - no move to encore
        if getattr(target, '_just_switched_in', False):
            return True
    
    # Imprison - check if target has common moves
    if move_lower == "imprison":
        user_moves = set((user.moves or []))
        target_moves = set((target.moves or []))
        if not user_moves.intersection(target_moves):
            return True
    
    return False


def _score_damaging_move(
    user: Mon,
    target: Mon,
    move_name: str,
    move_data: Dict[str, Any],
    battle_state: Any,
    field_effects: Any,
    user_side: Any,
    target_side: Any,
    is_highest_damage: bool = False
) -> float:
    """
    Score a damaging move. Returns base score (highest damaging move gets +6/+8).
    Kill bonuses are handled separately.
    """
    move_lower = move_name.lower().replace(" ", "-")
    
    # Special moves that don't get normal damage scoring
    special_damaging_moves = {
        "explosion", "self-destruct", "misty-explosion", "final-gambit",
        "relic-song", "rollout", "meteor-beam",
        "whirlpool", "fire-spin", "sand-tomb", "magma-storm", "infestation",
        "bind", "wrap", "clamp", "future-sight"
    }
    
    if move_lower in special_damaging_moves:
        # These moves have their own scoring logic
        return 0.0
    
    # Calculate damage
    try:
        dmg, meta, _ = damage(
            user, target, move_name, field_effects, target_side, user_side, is_moving_last=False
        )
    except Exception:
        dmg = 0
    
    # Check if this kills
    kills = dmg >= target.hp
    
    # Get user speed
    user_speed = getattr(user, 'stats', {}).get('spe', 0) or 0
    target_speed = getattr(target, 'stats', {}).get('spe', 0) or 0
    
    # Check if user is faster (AI sees speed ties as faster)
    is_faster = user_speed >= target_speed
    
    # Check move priority
    move_priority = move_data.get("priority", 0) or 0
    has_priority = move_priority > 0
    
    # Base score: +6 (80%) or +8 (20%) for highest damaging move
    if is_highest_damage:
        base_score = 6.0 if random.random() < 0.8 else 8.0
    else:
        base_score = 0.0  # Not highest damage, no base bonus
    
    # Kill bonuses
    if kills:
        if is_faster or (has_priority and not is_faster):
            base_score += 6.0  # Fast kill
        else:
            base_score += 3.0  # Slow kill
        
        # Moxie/Beast Boost/Chilling Neigh/Grim Neigh bonus
        user_ability = normalize_ability_name(user.ability or "")
        ability_data = get_ability_effect(user_ability)
        if ability_data.get("attack_boost_on_ko") or ability_data.get("spa_boost_on_ko"):
            base_score += 1.0
    
    # High crit + Super Effective bonus
    move_effect = get_move_secondary_effect(move_lower)
    if move_effect and move_effect.get("high_crit_chance"):
        move_type = move_data.get("type", "Normal")
        type_mult, _ = type_multiplier(move_type, target, field_effects=field_effects, user=user)
        if type_mult >= 2.0:  # Super effective
            if random.random() < 0.5:
                base_score += 1.0
    
    return base_score


def _score_special_move(
    user: Mon,
    target: Mon,
    move_name: str,
    move_lower: str,
    move_data: Dict[str, Any],
    battle_state: Any,
    field_effects: Any,
    user_side: Any,
    target_side: Any,
    is_double_battle: bool
) -> float:
    """Score special moves with their unique AI logic. Returns additive bonus."""
    score = 0.0
    
    # Priority moves when AI is dead to target and slower
    if move_lower in ["quick-attack", "extreme-speed", "mach-punch", "vacuum-wave", 
                      "bullet-punch", "aqua-jet", "ice-shard", "shadow-sneak", "sucker-punch",
                      "accelerock", "water-shuriken", "first-impression", "fake-out"]:
        user_speed = getattr(user, 'stats', {}).get('spe', 0) or 0
        target_speed = getattr(target, 'stats', {}).get('spe', 0) or 0
        move_priority = move_data.get("priority", 0) or 0
        
        if move_priority > 0 and user_speed < target_speed:
            # Check if user dies to target
            try:
                # Estimate if target can KO user
                target_moves = target.moves or []
                can_ko = False
                for t_move in target_moves[:4]:
                    try:
                        t_dmg, _, _ = damage(target, user, t_move, field_effects, user_side, target_side)
                        if t_dmg >= user.hp:
                            can_ko = True
                            break
                    except Exception:
                        continue
                
                if can_ko:
                    score += 11.0
            except Exception:
                pass
    
    # Stealth Rock
    if move_lower == "stealth-rock":
        is_first_turn = getattr(user, '_just_switched_in', False) or getattr(battle_state, 'turn', 1) == 1
        if is_first_turn:
            score += 2.0 if random.random() < 0.75 else 1.0
        else:
            score += 0.0 if random.random() < 0.75 else 1.0
    
    # Spikes / Toxic Spikes
    if move_lower in ["spikes", "toxic-spikes"]:
        is_first_turn = getattr(user, '_just_switched_in', False) or getattr(battle_state, 'turn', 1) == 1
        if is_first_turn:
            score += 2.0 if random.random() < 0.75 else 1.0
        else:
            score += 0.0 if random.random() < 0.75 else 1.0
        
        # Lower score if already set
        if target_side:
            if move_lower == "spikes" and getattr(target_side, 'spikes', 0) > 0:
                score -= 1.0
            if move_lower == "toxic-spikes" and getattr(target_side, 'toxic_spikes', 0) > 0:
                score -= 1.0
    
    # Sticky Web
    if move_lower == "sticky-web":
        is_first_turn = getattr(user, '_just_switched_in', False) or getattr(battle_state, 'turn', 1) == 1
        if is_first_turn:
            score += 3.0 if random.random() < 0.75 else 6.0
        else:
            score += 0.0 if random.random() < 0.75 else 3.0
    
    # Protect / King's Shield
    if move_lower in ["protect", "kings-shield"]:
        # Base +6 already applied
        # Check for status conditions
        if user.status in ["psn", "tox", "brn"] or getattr(user, 'cursed', False) or \
           getattr(user, 'infatuated', False) or getattr(user, '_perish_song_turns', 0) > 0 or \
           getattr(user, 'leech_seeded', False) or getattr(user, '_yawn_turns', 0) > 0:
            score -= 2.0
        
        if target.status in ["psn", "tox", "brn"] or getattr(target, 'cursed', False) or \
           getattr(target, 'infatuated', False) or getattr(target, '_perish_song_turns', 0) > 0 or \
           getattr(target, 'leech_seeded', False) or getattr(target, '_yawn_turns', 0) > 0:
            score += 1.0
        
        # First turn out penalty
        if getattr(user, '_just_switched_in', False) and not is_double_battle:
            score -= 1.0
        
        # Protect spam prevention
        if getattr(user, '_last_move', None) == "Protect":
            if random.random() < 0.5:
                score = -20.0  # Never use
        if getattr(user, '_protect_count', 0) >= 2:
            score = -20.0  # Never use
    
    # Setup moves (Dragon Dance, Swords Dance, etc.)
    if move_lower in ["dragon-dance", "swords-dance", "howl", "bulk-up", "calm-mind", 
                      "nasty-plot", "tail-glow", "work-up", "quiver-dance", "coil",
                      "hone-claws", "shift-gear", "shell-smash", "belly-drum"]:
        score += _score_setup_move(user, target, move_lower, move_data, battle_state, field_effects)
    
    # Recovery moves
    if move_lower in ["recover", "slack-off", "heal-order", "soft-boiled", "roost", "strength-sap"]:
        score += _score_recovery_move(user, target, move_lower, battle_state, field_effects)
    
    # Rest
    if move_lower == "rest":
        score += _score_rest(user, target, battle_state, field_effects)
    
    # Status moves
    if move_lower in ["thunder-wave", "stun-spore", "glare", "nuzzle"]:
        score += _score_paralysis_move(user, target, battle_state, field_effects)
    
    if move_lower == "will-o-wisp":
        score += _score_willowisp(user, target, battle_state, field_effects)
    
    if move_lower == "toxic":
        score += _score_toxic(user, target, battle_state, field_effects)
    
    # Trapping moves (Whirlpool, Fire Spin, etc.)
    if move_lower in ["whirlpool", "fire-spin", "sand-tomb", "magma-storm", "infestation", 
                      "bind", "wrap", "clamp", "snap-trap", "thunder-cage"]:
        # +6 (80%) or +8 (20%) - treated as normal damaging moves
        # But they don't get highest damage bonus, so we give them base score
        if move_category != "status" and move_power > 0:
            # Already scored as damaging move, but add trapping bonus
            score += 0.0  # Trapping is already factored into damage
        else:
            score = 6.0 if random.random() < 0.8 else 8.0
    
    # Speed reduction moves (Icy Wind, Electroweb, Rock Tomb, Mud Shot, Low Sweep)
    if move_lower in ["icy-wind", "electroweb", "rock-tomb", "mud-shot", "low-sweep"]:
        if move_category != "status" and move_power > 0:
            # If this is highest damaging move, it already got +6/+8
            # Otherwise, apply speed reduction bonus
            user_speed = getattr(user, 'stats', {}).get('spe', 0) or 0
            target_speed = getattr(target, 'stats', {}).get('spe', 0) or 0
            
            # Check for Contrary, Clear Body, White Smoke
            target_ability = normalize_ability_name(target.ability or "")
            has_immunity = target_ability in ["contrary", "clear-body", "white-smoke"]
            
            if not has_immunity and user_speed < target_speed:
                score += 6.0
            else:
                score += 5.0
    
    # Attack/SpAtk reduction moves (Trop Kick, Skitter Smack, etc.)
    if move_lower in ["trop-kick", "skitter-smack", "struggle-bug", "snarl", "mystical-fire"]:
        if move_category != "status" and move_power > 0:
            # If this is highest damaging move, it already got +6/+8
            # Otherwise, apply stat reduction bonus
            target_ability = normalize_ability_name(target.ability or "")
            has_immunity = target_ability in ["contrary", "clear-body", "white-smoke"]
            
            # Check if target has moves of corresponding split
            target_moves = target.moves or []
            has_corresponding_move = False
            stat_type = "atk" if "atk" in move_lower or move_lower in ["trop-kick"] else "spa"
            
            for t_move in target_moves[:4]:
                t_move_data = get_move(t_move)
                if t_move_data:
                    t_category = (t_move_data.get("category") or t_move_data.get("damage_class") or "").lower()
                    if stat_type == "atk" and t_category == "physical":
                        has_corresponding_move = True
                        break
                    elif stat_type == "spa" and t_category == "special":
                        has_corresponding_move = True
                        break
            
            if not has_immunity and has_corresponding_move:
                score += 6.0
            else:
                score += 5.0
    
    # Future Sight
    if move_lower == "future-sight":
        user_speed = getattr(user, 'stats', {}).get('spe', 0) or 0
        target_speed = getattr(target, 'stats', {}).get('spe', 0) or 0
        
        # Check if user dies to target
        try:
            target_moves = target.moves or []
            can_ko = False
            for t_move in target_moves[:4]:
                try:
                    t_dmg, _, _ = damage(target, user, t_move, field_effects, None, None)
                    if t_dmg >= user.hp:
                        can_ko = True
                        break
                except Exception:
                    continue
            
            if user_speed > target_speed and can_ko:
                score = 8.0
            else:
                score = 6.0
        except Exception:
            score = 6.0
    
    # Relic Song
    if move_lower == "relic-song":
        # Check if in base form or Pirouette form
        # For now, assume base form (can be improved with form detection)
        if not getattr(user, 'form', None) or "pirouette" not in (user.form or "").lower():
            score += 10.0
        else:
            score = -20.0  # Never use in Pirouette form
    
    # Sucker Punch
    if move_lower == "sucker-punch":
        if getattr(user, '_last_move', None) == "Sucker Punch":
            if random.random() < 0.5:
                score = -20.0  # 50% chance to never use
    
    # Pursuit
    if move_lower == "pursuit":
        try:
            # Check if can KO
            dmg, _, _ = damage(user, target, move_name, field_effects, target_side, user_side)
            if dmg >= target.hp:
                score += 10.0
            else:
                hp_percent = target.hp / target.max_hp if target.max_hp > 0 else 1.0
                if hp_percent < 0.2:
                    score += 10.0
                elif hp_percent < 0.4:
                    if random.random() < 0.5:
                        score += 8.0
            
            # Bonus if faster
            user_speed = getattr(user, 'stats', {}).get('spe', 0) or 0
            target_speed = getattr(target, 'stats', {}).get('spe', 0) or 0
            if user_speed > target_speed:
                score += 3.0
        except Exception:
            pass
    
    # Rollout
    if move_lower == "rollout":
        score = 7.0  # Always +7
    
    # Fake Out
    if move_lower == "fake-out":
        # Check if first turn out and target doesn't have Shield Dust/Inner Focus
        if getattr(user, '_just_switched_in', False):
            target_ability = normalize_ability_name(target.ability or "")
            if target_ability not in ["shield-dust", "inner-focus"]:
                score += 3.0  # +9 total
    
    # Trick Room
    if move_lower == "trick-room":
        if field_effects and getattr(field_effects, 'trick_room', False):
            score = -20.0  # Never use if already active
        else:
            user_speed = getattr(user, 'stats', {}).get('spe', 0) or 0
            target_speed = getattr(target, 'stats', {}).get('spe', 0) or 0
            if user_speed < target_speed:
                score += 4.0  # +10 total
            else:
                score -= 1.0  # +5 total
    
    # Tailwind
    if move_lower == "tailwind":
        user_speed = getattr(user, 'stats', {}).get('spe', 0) or 0
        target_speed = getattr(target, 'stats', {}).get('spe', 0) or 0
        if user_speed < target_speed:
            score += 3.0  # +9 total
        else:
            score -= 1.0  # +5 total
    
    # Substitute
    if move_lower == "substitute":
        # Check if target is asleep
        if target.status == "slp":
            score += 2.0
        
        # Check if target is Leech Seeded and user is faster
        if getattr(target, 'leech_seeded', False):
            user_speed = getattr(user, 'stats', {}).get('spe', 0) or 0
            target_speed = getattr(target, 'stats', {}).get('spe', 0) or 0
            if user_speed > target_speed:
                score += 2.0
        
        # Random -1 penalty
        if random.random() < 0.5:
            score -= 1.0
        
        # Check for sound-based moves
        target_moves = target.moves or []
        has_sound_move = False
        sound_moves = ["hyper-voice", "boomburst", "bug-buzz", "chatter", "echoed-voice",
                       "grass-whistle", "heal-bell", "perish-song", "roar", "round",
                       "screech", "sing", "snarl", "supersonic", "uproar"]
        for t_move in target_moves[:4]:
            if t_move.lower() in sound_moves:
                has_sound_move = True
                break
        
        if has_sound_move:
            score -= 8.0
        
        # Never use if at 50% HP or lower, or target has Infiltrator
        hp_percent = user.hp / user.max_hp if user.max_hp > 0 else 1.0
        target_ability = normalize_ability_name(target.ability or "")
        if hp_percent <= 0.5 or target_ability == "infiltrator":
            score = -20.0
    
    # Explosion / Self-Destruct / Misty Explosion / Memento
    if move_lower in ["explosion", "self-destruct", "misty-explosion", "memento"]:
        hp_percent = user.hp / user.max_hp if user.max_hp > 0 else 1.0
        
        if move_lower == "memento":
            if hp_percent < 0.1:
                score += 10.0  # +16 total
            elif hp_percent < 0.33:
                score += 8.0 if random.random() < 0.7 else 0.0  # +14 or +6
            elif hp_percent < 0.66:
                score += 7.0 if random.random() < 0.5 else 0.0  # +13 or +6
            else:
                score += 7.0 if random.random() < 0.05 else 0.0  # +13 or +6
            
            # Never use if last mon
            # (This check would need battle_state to know if it's last mon)
        else:
            # Explosion, Self-Destruct, Misty Explosion
            if hp_percent < 0.1:
                score += 4.0  # +10 total
            elif hp_percent < 0.33:
                score += 2.0 if random.random() < 0.7 else -6.0  # +8 or +0
            elif hp_percent < 0.66:
                score += 1.0 if random.random() < 0.5 else -6.0  # +7 or +0
            else:
                score += 1.0 if random.random() < 0.05 else -6.0  # +7 or +0
    
    # Yawn and sleep moves
    if move_lower in ["yawn", "dark-void", "grasswhistle", "sing", "hypnosis", "sleep-powder", "spore"]:
        # Base +6
        if random.random() < 0.25:  # 25% of the time
            # Check if target can be put to sleep
            can_sleep = (target.status is None or target.status == "") and \
                       not getattr(target, 'safeguard', False) and \
                       normalize_ability_name(target.ability or "") not in ["insomnia", "vital-spirit", "sweet-veil"]
            
            if can_sleep:
                score += 1.0
                
                # Check for Dream Eater / Nightmare
                user_moves = user.moves or []
                has_dream_eater = "dream-eater" in [m.lower() for m in user_moves]
                has_nightmare = "nightmare" in [m.lower() for m in user_moves]
                target_moves = target.moves or []
                has_snore = "snore" in [m.lower() for m in target_moves]
                has_sleep_talk = "sleep-talk" in [m.lower() for m in target_moves]
                
                if (has_dream_eater or has_nightmare) and not (has_snore or has_sleep_talk):
                    score += 1.0
                
                # Check for Hex
                user_has_hex = "hex" in [m.lower() for m in user_moves]
                if user_has_hex:
                    score += 1.0
    
    # Taunt
    if move_lower == "taunt":
        # Check if target has Trick Room and TR is not active
        target_moves = target.moves or []
        has_trick_room = "trick-room" in [m.lower() for m in target_moves]
        tr_active = field_effects and getattr(field_effects, 'trick_room', False)
        
        if has_trick_room and not tr_active:
            score += 3.0  # +9 total
        else:
            # Check for Defog, Aurora Veil active, and user is faster
            has_defog = "defog" in [m.lower() for m in target_moves]
            aurora_veil_active = user_side and getattr(user_side, 'aurora_veil', False)
            user_speed = getattr(user, 'stats', {}).get('spe', 0) or 0
            target_speed = getattr(target, 'stats', {}).get('spe', 0) or 0
            
            if has_defog and aurora_veil_active and user_speed > target_speed:
                score += 3.0  # +9 total
            else:
                score -= 1.0  # +5 total
    
    # Encore
    if move_lower == "encore":
        user_speed = getattr(user, 'stats', {}).get('spe', 0) or 0
        target_speed = getattr(target, 'stats', {}).get('spe', 0) or 0
        
        # Check if Encore is encouraged (target's last move is non-damaging)
        target_last_move = getattr(target, 'last_move_used', None)
        if target_last_move:
            target_last_move_data = get_move(target_last_move)
            if target_last_move_data:
                last_move_category = (target_last_move_data.get("category") or target_last_move_data.get("damage_class") or "").lower()
                last_move_power = target_last_move_data.get("power", 0) or 0
                
                if last_move_category == "status" or last_move_power <= 0:
                    # Encore is encouraged
                    if user_speed > target_speed:
                        score += 1.0  # +7 total
                    else:
                        score += 0.0 if random.random() < 0.5 else -1.0  # +6 or +5
                else:
                    score -= 1.0  # +5 total
            else:
                score -= 1.0
        else:
            score -= 1.0
    
    # Trick / Switcheroo
    if move_lower in ["trick", "switcheroo"]:
        if user.item:
            item_lower = user.item.lower()
            if "toxic-orb" in item_lower or "flame-orb" in item_lower or "black-sludge" in item_lower:
                score += 0.0 if random.random() < 0.5 else 1.0  # +6 or +7
            elif "iron-ball" in item_lower or "lagging-tail" in item_lower or "sticky-barb" in item_lower:
                score += 1.0  # +7 total
            else:
                score -= 1.0  # +5 total
        else:
            score -= 1.0
    
    # Agility / Rock Polish / Autotomize
    if move_lower in ["agility", "rock-polish", "autotomize"]:
        user_speed = getattr(user, 'stats', {}).get('spe', 0) or 0
        target_speed = getattr(target, 'stats', {}).get('spe', 0) or 0
        if user_speed < target_speed:
            score += 1.0  # +7 total
        else:
            score = -20.0  # Never use
    
    # Tail Glow / Nasty Plot / Work Up
    if move_lower in ["tail-glow", "nasty-plot", "work-up"]:
        # Similar to offensive setup
        if target.status == "slp" or target.status == "frz" or \
           getattr(target, 'recharging_move', None) or getattr(target, 'truant', False):
            score += 3.0
        else:
            # Check if target can 3HKO
            try:
                target_moves = target.moves or []
                can_3hko = False
                for t_move in target_moves[:4]:
                    try:
                        t_dmg, _, _ = damage(target, user, t_move, field_effects, None, None)
                        if t_dmg >= user.max_hp / 3:
                            can_3hko = True
                            break
                    except Exception:
                        continue
                
                if not can_3hko:
                    score += 1.0
                    user_speed = getattr(user, 'stats', {}).get('spe', 0) or 0
                    target_speed = getattr(target, 'stats', {}).get('spe', 0) or 0
                    if user_speed > target_speed:
                        score += 1.0
            except Exception:
                pass
            
            # Penalty if slower and 2HKO'd
            user_speed = getattr(user, 'stats', {}).get('spe', 0) or 0
            target_speed = getattr(target, 'stats', {}).get('spe', 0) or 0
            if user_speed < target_speed:
                try:
                    target_moves = target.moves or []
                    can_2hko = False
                    for t_move in target_moves[:4]:
                        try:
                            t_dmg, _, _ = damage(target, user, t_move, field_effects, None, None)
                            if t_dmg >= user.max_hp / 2:
                                can_2hko = True
                                break
                        except Exception:
                            continue
                    
                    if can_2hko:
                        score -= 5.0
                except Exception:
                    pass
        
        # Penalty if already at +2 SpAtk or higher
        spa_stage = getattr(user, 'stages', {}).get('spa', 0) or 0
        if spa_stage >= 2:
            score -= 1.0
    
    # Focus Energy / Laser Focus
    if move_lower in ["focus-energy", "laser-focus"]:
        user_ability = normalize_ability_name(user.ability or "")
        has_super_luck = user_ability == "super-luck"
        has_sniper = user_ability == "sniper"
        has_scope_lens = user.item and "scope-lens" in (user.item or "").lower()
        
        # Check for high crit moves
        user_moves = user.moves or []
        has_high_crit = False
        for m in user_moves[:4]:
            move_effect = get_move_secondary_effect(m.lower())
            if move_effect and move_effect.get("high_crit_chance"):
                has_high_crit = True
                break
        
        if has_super_luck or has_sniper or has_scope_lens or has_high_crit:
            score += 1.0  # +7 total
        else:
            score += 0.0  # +6 total
        
        # Never use if target has Shell Armor or Battle Armor
        target_ability = normalize_ability_name(target.ability or "")
        if target_ability in ["shell-armor", "battle-armor"]:
            score = -20.0
    
    # Meteor Beam
    if move_lower == "meteor-beam":
        if user.item and "power-herb" in user.item.lower():
            score += 3.0  # +9 total
        else:
            score = -20.0  # Never use
    
    # Destiny Bond
    if move_lower == "destiny-bond":
        user_speed = getattr(user, 'stats', {}).get('spe', 0) or 0
        target_speed = getattr(target, 'stats', {}).get('spe', 0) or 0
        
        # Check if user dies to target
        try:
            target_moves = target.moves or []
            can_ko = False
            for t_move in target_moves[:4]:
                try:
                    t_dmg, _, _ = damage(target, user, t_move, field_effects, None, None)
                    if t_dmg >= user.hp:
                        can_ko = True
                        break
                except Exception:
                    continue
            
            if user_speed > target_speed and can_ko:
                score += 1.0 if random.random() < 0.81 else 0.0  # +7 or +6
            else:
                score += -1.0 if random.random() < 0.5 else 0.0  # +5 or +6
        except Exception:
            score += 0.0
    
    # Counter / Mirror Coat
    if move_lower in ["counter", "mirror-coat"]:
        # Check if target can KO user
        try:
            target_moves = target.moves or []
            can_ko = False
            only_corresponding_split = True
            
            for t_move in target_moves[:4]:
                t_move_data = get_move(t_move)
                if t_move_data:
                    t_category = (t_move_data.get("category") or t_move_data.get("damage_class") or "").lower()
                    t_power = t_move_data.get("power", 0) or 0
                    
                    if t_power > 0:
                        if move_lower == "counter" and t_category != "physical":
                            only_corresponding_split = False
                        elif move_lower == "mirror-coat" and t_category != "special":
                            only_corresponding_split = False
                        
                        t_dmg, _, _ = damage(target, user, t_move, field_effects, None, None)
                        if t_dmg >= user.hp:
                            can_ko = True
            # Check for Sturdy/Sash
            has_sturdy = False
            user_ability = normalize_ability_name(user.ability or "")
            if user_ability == "sturdy" and user.hp == user.max_hp:
                has_sturdy = True
            
            has_sash = False
            if user.item and "focus-sash" in user.item.lower():
                has_sash = True
            
            if can_ko and (has_sturdy or has_sash) and user.hp == user.max_hp and only_corresponding_split:
                score += 2.0
            
            if not can_ko and only_corresponding_split:
                score += 2.0 if random.random() < 0.8 else 0.0
            
            # Penalty if faster
            user_speed = getattr(user, 'stats', {}).get('spe', 0) or 0
            target_speed = getattr(target, 'stats', {}).get('spe', 0) or 0
            if user_speed > target_speed:
                if random.random() < 0.25:
                    score -= 1.0
            
            # Penalty if target has status moves
            target_moves = target.moves or []
            has_status = False
            for t_move in target_moves[:4]:
                t_move_data = get_move(t_move)
                if t_move_data:
                    t_category = (t_move_data.get("category") or t_move_data.get("damage_class") or "").lower()
                    t_power = t_move_data.get("power", 0) or 0
                    if t_category == "status" or t_power <= 0:
                        has_status = True
                        break
            
            if has_status:
                if random.random() < 0.25:
                    score -= 1.0
        except Exception:
            pass
    
    # Terrain moves
    if move_lower in ["electric-terrain", "grassy-terrain", "psychic-terrain", "misty-terrain"]:
        has_terrain_extender = user.item and "terrain-extender" in user.item.lower()
        if has_terrain_extender:
            score += 3.0  # +9 total
        else:
            score += 2.0  # +8 total
    
    # Light Screen / Reflect
    if move_lower in ["light-screen", "reflect"]:
        # Check if target has corresponding moves
        target_moves = target.moves or []
        has_corresponding = False
        for t_move in target_moves[:4]:
            t_move_data = get_move(t_move)
            if t_move_data:
                t_category = (t_move_data.get("category") or t_move_data.get("damage_class") or "").lower()
                t_power = t_move_data.get("power", 0) or 0
                if t_power > 0:
                    if move_lower == "reflect" and t_category == "physical":
                        has_corresponding = True
                        break
                    elif move_lower == "light-screen" and t_category == "special":
                        has_corresponding = True
                        break
        
        if has_corresponding:
            has_light_clay = user.item and "light-clay" in user.item.lower()
            if has_light_clay:
                score += 2.0  # +8 total
            else:
                score += 1.0 if random.random() < 0.5 else 0.0  # +7 or +6
    
    return score


def _calculate_general_bonuses(
    user: Mon,
    target: Mon,
    move_name: str,
    move_lower: str,
    move_data: Dict[str, Any],
    battle_state: Any,
    field_effects: Any,
    user_side: Any,
    target_side: Any
) -> float:
    """
    Calculate general bonuses that apply to all moves:
    - PP management (prefer moves with more PP)
    - Type effectiveness bonus
    - Weather/terrain synergy
    - Ability/item synergy
    - Status condition management
    - Win condition evaluation
    """
    bonus = 0.0
    move_category = (move_data.get("category") or move_data.get("damage_class") or "status").lower()
    move_power = int(move_data.get("power", 0) or 0)
    
    # === PP Management ===
    # Prefer moves with more PP remaining (but don't penalize too heavily)
    try:
        if hasattr(battle_state, '_pp_left'):
            pp_remaining = battle_state._pp_left(battle_state.p1_id if user == battle_state._active(battle_state.p1_id) else battle_state.p2_id, move_name, user)
            max_pp = move_data.get("pp", 5) or 5
            
            if max_pp > 0:
                pp_percent = pp_remaining / max_pp
                if pp_percent < 0.25:  # Very low PP
                    bonus -= 2.0
                elif pp_percent < 0.5:  # Low PP
                    bonus -= 1.0
                elif pp_percent > 0.75:  # High PP
                    bonus += 0.5
    except Exception:
        pass
    
    # === Type Effectiveness Bonus ===
    # Prioritize super-effective moves more
    if move_data.get("power", 0) > 0:
        try:
            move_type = move_data.get("type", "Normal")
            type_mult, _ = type_multiplier(move_type, target, field_effects=field_effects, user=user)
            
            if type_mult >= 2.0:  # Super effective
                bonus += 1.5
            elif type_mult >= 4.0:  # Double super effective
                bonus += 3.0
            elif type_mult <= 0.5:  # Not very effective
                bonus -= 1.0
            elif type_mult <= 0.25:  # Double not very effective
                bonus -= 2.5
            elif type_mult == 0.0:  # Immune
                bonus -= 5.0
        except Exception:
            pass
    
    # === Weather Synergy ===
    weather = getattr(field_effects, 'weather', None) if field_effects else None
    move_type = move_data.get("type", "Normal")
    
    if weather == "sun":
        if move_type in ["Fire"]:
            bonus += 0.5  # Fire moves boosted in sun
        elif move_type in ["Water"]:
            bonus -= 0.5  # Water moves weakened in sun
    elif weather == "rain":
        if move_type in ["Water"]:
            bonus += 0.5  # Water moves boosted in rain
        elif move_type in ["Fire"]:
            bonus -= 0.5  # Fire moves weakened in rain
    elif weather == "hail":
        if move_type in ["Ice"]:
            bonus += 0.5  # Ice moves boosted in hail
    elif weather == "sandstorm":
        # Sandstorm doesn't boost moves, but Rock types get SpDef boost
        if move_type in ["Rock", "Ground", "Steel"]:
            bonus += 0.3
    
    # === Terrain Synergy ===
    terrain = getattr(field_effects, 'terrain', None) if field_effects else None
    
    if terrain == "electric":
        if move_type == "Electric" and move_data.get("power", 0) > 0:
            # Electric moves boosted on Electric Terrain
            bonus += 0.5
    elif terrain == "grassy":
        if move_type == "Grass" and move_data.get("power", 0) > 0:
            # Grass moves boosted on Grassy Terrain
            bonus += 0.5
    elif terrain == "psychic":
        if move_type == "Psychic" and move_data.get("power", 0) > 0:
            # Psychic moves boosted on Psychic Terrain
            bonus += 0.5
    elif terrain == "misty":
        if move_type == "Dragon" and move_data.get("power", 0) > 0:
            # Dragon moves weakened on Misty Terrain
            bonus -= 1.0
    
    # === Ability Synergy ===
    user_ability = normalize_ability_name(user.ability or "")
    ability_data = get_ability_effect(user_ability)
    
    # Adaptability - STAB bonus
    if user_ability == "adaptability":
        user_types = user.types or []
        if move_type in [t.title() for t in user_types]:
            bonus += 0.5  # STAB is stronger with Adaptability
    
    # Technician - low power moves
    if user_ability == "technician":
        if move_power <= 60:
            bonus += 0.5
    
    # Strong Jaw - bite moves
    if user_ability == "strong-jaw":
        bite_moves = ["bite", "crunch", "fire-fang", "ice-fang", "thunder-fang", "poison-fang", "psychic-fangs"]
        if move_lower in bite_moves:
            bonus += 0.5
    
    # Mega Launcher - pulse moves
    if user_ability == "mega-launcher":
        pulse_moves = ["aura-sphere", "dark-pulse", "dragon-pulse", "water-pulse", "origin-pulse"]
        if move_lower in pulse_moves:
            bonus += 0.5
    
    # === Item Synergy ===
    if user.item:
        item_lower = user.item.lower()
        
        # Type-boosting items
        if move_type == "Fire" and "charcoal" in item_lower:
            bonus += 0.5
        elif move_type == "Water" and "mystic-water" in item_lower:
            bonus += 0.5
        elif move_type == "Grass" and "miracle-seed" in item_lower:
            bonus += 0.5
        elif move_type == "Electric" and "magnet" in item_lower:
            bonus += 0.5
        elif move_type == "Ice" and "never-melt-ice" in item_lower:
            bonus += 0.5
        elif move_type == "Fighting" and "black-belt" in item_lower:
            bonus += 0.5
        elif move_type == "Poison" and "poison-barb" in item_lower:
            bonus += 0.5
        elif move_type == "Ground" and "soft-sand" in item_lower:
            bonus += 0.5
        elif move_type == "Flying" and "sharp-beak" in item_lower:
            bonus += 0.5
        elif move_type == "Psychic" and "twisted-spoon" in item_lower:
            bonus += 0.5
        elif move_type == "Bug" and "silver-powder" in item_lower:
            bonus += 0.5
        elif move_type == "Rock" and "hard-stone" in item_lower:
            bonus += 0.5
        elif move_type == "Ghost" and "spell-tag" in item_lower:
            bonus += 0.5
        elif move_type == "Dragon" and "dragon-scale" in item_lower:
            bonus += 0.5
        elif move_type == "Dark" and "black-glasses" in item_lower:
            bonus += 0.5
        elif move_type == "Steel" and "metal-coat" in item_lower:
            bonus += 0.5
        elif move_type == "Fairy" and "pixie-plate" in item_lower:
            bonus += 0.5
    
    # === Status Condition Management ===
    # If user is badly poisoned, prioritize moves that can end the battle quickly
    if user.status == "tox":
        if move_data.get("power", 0) > 0:
            # Prefer high-damage moves to end battle faster
            if move_power >= 100:
                bonus += 1.0
            elif move_power >= 80:
                bonus += 0.5
    
    # If user is burned, prefer special moves (physical moves are weakened)
    if user.status == "brn":
        if move_category == "physical" and move_power > 0:
            bonus -= 0.5
        elif move_category == "special" and move_power > 0:
            bonus += 0.5
    
    # If user is paralyzed, prefer priority moves
    if user.status == "par":
        move_priority = move_data.get("priority", 0) or 0
        if move_priority > 0:
            bonus += 1.0
    
    # === Win Condition Evaluation ===
    # If target is low HP, prioritize finishing moves
    target_hp_percent = target.hp / target.max_hp if target.max_hp > 0 else 1.0
    if target_hp_percent < 0.25:  # Target is in KO range
        if move_data.get("power", 0) > 0:
            # Prefer moves that can finish
            try:
                dmg, _, _ = damage(user, target, move_name, field_effects, target_side, user_side, is_moving_last=False)
                if dmg >= target.hp:
                    bonus += 2.0  # This move can KO
            except Exception:
                pass
    
    # If user is low HP and has recovery, prefer recovery
    user_hp_percent = user.hp / user.max_hp if user.max_hp > 0 else 1.0
    if user_hp_percent < 0.3:
        if move_lower in ["recover", "slack-off", "heal-order", "soft-boiled", "roost", "rest"]:
            bonus += 1.0
    
    # === STAB Bonus (already in damage calc, but add small extra) ===
    user_types = user.types or []
    if move_type in [t.title() for t in user_types]:
        bonus += 0.3  # Small STAB preference bonus
    
    # === Accuracy Consideration ===
    # Slightly prefer more accurate moves
    move_accuracy = move_data.get("accuracy", 100) or 100
    if move_accuracy >= 100:
        bonus += 0.2
    elif move_accuracy < 70:
        bonus -= 0.5  # Penalize low accuracy moves
    
    # === Choice Item Consideration ===
    # If locked into a move by Choice item, that move gets a small bonus
    # (AI should prefer using the locked move)
    try:
        if hasattr(battle_state, '_choice_locked'):
            locked_move = battle_state._choice_locked.get(
                battle_state.p1_id if user == battle_state._active(battle_state.p1_id) else battle_state.p2_id
            )
            if locked_move and locked_move.lower() == move_lower:
                bonus += 1.0  # Prefer the locked move
    except Exception:
        pass
    
    # === Opponent Prediction ===
    # If opponent is likely to switch (low HP, bad matchup), prefer moves that punish switches
    target_hp_percent = target.hp / target.max_hp if target.max_hp > 0 else 1.0
    if target_hp_percent < 0.3:
        # Opponent might switch - prefer Pursuit or moves that hit hard
        if move_lower == "pursuit":
            bonus += 2.0
        elif move_data.get("power", 0) >= 100:
            bonus += 0.5  # High power moves to finish
    
    # === Momentum Consideration ===
    # If user has stat boosts, prefer moves that capitalize on them
    user_stages = getattr(user, 'stages', {}) or {}
    atk_stage = user_stages.get('atk', 0) or 0
    spa_stage = user_stages.get('spa', 0) or 0
    
    if atk_stage > 0 and move_category == "physical" and move_power > 0:
        bonus += min(atk_stage * 0.3, 1.0)  # Up to +1.0 for high attack boosts
    if spa_stage > 0 and move_category == "special" and move_power > 0:
        bonus += min(spa_stage * 0.3, 1.0)  # Up to +1.0 for high special attack boosts
    
    # === Hazard Control ===
    # If opponent has hazards up and user is low HP, prioritize Defog/Rapid Spin
    if move_lower in ["defog", "rapid-spin"]:
        user_hp_percent = user.hp / user.max_hp if user.max_hp > 0 else 1.0
        has_hazards = False
        if user_side:
            has_hazards = (
                getattr(user_side, 'stealth_rock', False) or
                getattr(user_side, 'spikes', 0) > 0 or
                getattr(user_side, 'toxic_spikes', 0) > 0 or
                getattr(user_side, 'sticky_web', False)
            )
        
        if has_hazards and user_hp_percent < 0.5:
            bonus += 2.0  # Important to remove hazards when low HP
        elif has_hazards:
            bonus += 1.0  # Still good to remove hazards
    
    # === Move Power Consideration ===
    # Prefer higher power moves (if not already highest damage)
    if move_power > 0:
        if move_power >= 100:
            bonus += 0.3
        elif move_power >= 80:
            bonus += 0.2
        elif move_power < 40:
            bonus -= 0.3
    
    # === Set Identification ===
    # Try to identify opponent's set type and adjust strategy
    target_moves = target.moves or []
    physical_moves = 0
    special_moves = 0
    status_moves = 0
    
    for t_move in target_moves[:4]:
        t_move_data = get_move(t_move)
        if t_move_data:
            t_category = (t_move_data.get("category") or t_move_data.get("damage_class") or "status").lower()
            t_power = t_move_data.get("power", 0) or 0
            if t_category == "physical" and t_power > 0:
                physical_moves += 1
            elif t_category == "special" and t_power > 0:
                special_moves += 1
            elif t_category == "status" or t_power <= 0:
                status_moves += 1
    
    # If opponent is physical attacker, prefer physical walls/setup
    if physical_moves >= 2 and special_moves == 0:
        if move_lower in ["reflect", "iron-defense", "cotton-guard"]:
            bonus += 1.0
    # If opponent is special attacker, prefer special walls/setup
    elif special_moves >= 2 and physical_moves == 0:
        if move_lower in ["light-screen", "amnesia", "calm-mind"]:
            bonus += 1.0
    
    # === Entry Hazard Timing ===
    # Prefer setting hazards early in battle (first few turns)
    if move_lower in ["stealth-rock", "spikes", "toxic-spikes", "sticky-web"]:
        try:
            current_turn = getattr(battle_state, 'turn', 1)
            if current_turn <= 3:
                bonus += 1.0  # Early game - good time for hazards
        except Exception:
            pass
    
    # === Pivot Moves (U-turn, Volt Switch, Flip Turn) ===
    # Use pivot moves when user is in a bad matchup or low HP
    if move_lower in ["u-turn", "volt-switch", "flip-turn", "parting-shot"]:
        user_hp_percent = user.hp / user.max_hp if user.max_hp > 0 else 1.0
        
        # Check if user is in bad matchup
        user_types = user.types or []
        target_types = target.types or []
        bad_matchup = False
        
        for u_type in user_types:
            for t_type in target_types:
                try:
                    type_mult, _ = type_multiplier(t_type, user, field_effects=field_effects, user=target)
                    if type_mult >= 2.0:
                        bad_matchup = True
                        break
                except Exception:
                    pass
            if bad_matchup:
                break
        
        if bad_matchup or user_hp_percent < 0.4:
            bonus += 2.0  # Good time to pivot out
        elif user_hp_percent < 0.6:
            bonus += 1.0
    
    # === Phazing Moves (Roar, Whirlwind, Dragon Tail, Circle Throw) ===
    # Use phazing when opponent has stat boosts or when we have hazards
    if move_lower in ["roar", "whirlwind", "dragon-tail", "circle-throw"]:
        target_stages = getattr(target, 'stages', {}) or {}
        has_boosts = any((target_stages.get(stat, 0) or 0) > 0 for stat in ['atk', 'spa', 'def', 'spd', 'spe'])
        
        # Check if we have hazards
        has_hazards = False
        if target_side:
            has_hazards = (
                getattr(target_side, 'stealth_rock', False) or
                getattr(target_side, 'spikes', 0) > 0 or
                getattr(target_side, 'toxic_spikes', 0) > 0
            )
        
        if has_boosts:
            bonus += 2.0  # Phaze out boosted opponent
        elif has_hazards:
            bonus += 1.5  # Phaze to rack up hazard damage
    
    # === Protect Stalling ===
    # Use Protect to stall for weather/status damage or Perish Song
    if move_lower in ["protect", "detect", "kings-shield", "spiky-shield"]:
        # Check for Perish Song
        if getattr(user, '_perish_song_turns', 0) > 0:
            bonus += 1.0  # Stall for Perish Song
        
        # Check for weather damage
        weather = getattr(field_effects, 'weather', None) if field_effects else None
        if weather in ["hail", "sandstorm"]:
            # Check if target is immune
            target_types = target.types or []
            is_immune = False
            if weather == "hail" and "Ice" in target_types:
                is_immune = True
            elif weather == "sandstorm" and ("Rock" in target_types or "Ground" in target_types or "Steel" in target_types):
                is_immune = True
            
            if not is_immune:
                bonus += 0.5  # Stall for weather damage
        
        # Check for status damage
        if target.status in ["psn", "tox", "brn"]:
            bonus += 0.5  # Stall for status damage
    
    # === Substitute Timing ===
    # Better Substitute usage - prefer when opponent can't break it
    if move_lower == "substitute":
        # Check if opponent can break sub in one hit
        try:
            target_moves = target.moves or []
            can_break_sub = False
            for t_move in target_moves[:4]:
                try:
                    t_dmg, _, _ = damage(target, user, t_move, field_effects, target_side, user_side)
                    if t_dmg >= user.max_hp / 4:  # Sub has 25% HP
                        can_break_sub = True
                        break
                except Exception:
                    continue
            
            if not can_break_sub:
                bonus += 1.5  # Opponent can't break sub easily
        except Exception:
            pass
    
    # === Endgame Optimization ===
    # Different strategy when it's 1v1 or when we're ahead/behind
    try:
        # Count remaining Pokemon
        ai_user_id = battle_state.p1_id if user == battle_state._active(battle_state.p1_id) else battle_state.p2_id
        opp_user_id = battle_state.p2_id if ai_user_id == battle_state.p1_id else battle_state.p1_id
        
        ai_team = battle_state.team_for(ai_user_id)
        opp_team = battle_state.team_for(opp_user_id)
        
        ai_alive = sum(1 for m in ai_team if m and m.hp > 0)
        opp_alive = sum(1 for m in opp_team if m and m.hp > 0)
        
        # If we're ahead (more Pokemon), play more conservatively
        if ai_alive > opp_alive:
            if move_lower in ["explosion", "self-destruct", "memento"]:
                bonus -= 3.0  # Don't sacrifice when ahead
            if move_data.get("power", 0) > 0:
                bonus += 0.3  # Prefer safe damage
        
        # If we're behind, play more aggressively
        elif ai_alive < opp_alive:
            if move_lower in ["explosion", "self-destruct"]:
                bonus += 1.0  # More willing to sacrifice when behind
            if move_data.get("power", 0) >= 100:
                bonus += 0.5  # Prefer high-power moves
        
        # If it's 1v1, prioritize winning moves
        if ai_alive == 1 and opp_alive == 1:
            # Prefer moves that can KO
            if move_data.get("power", 0) > 0:
                try:
                    dmg, _, _ = damage(user, target, move_name, field_effects, target_side, user_side)
                    if dmg >= target.hp:
                        bonus += 3.0  # This can win the game!
                except Exception:
                    pass
    except Exception:
        pass
    
    # === Critical Hit Consideration ===
    # Factor in crit chances for high-power moves
    if move_data.get("power", 0) > 0:
        move_effect = get_move_secondary_effect(move_lower)
        has_high_crit = move_effect and move_effect.get("high_crit_chance")
        user_ability = normalize_ability_name(user.ability or "")
        
        if has_high_crit or user_ability in ["super-luck", "sniper"]:
            # Crits ignore stat drops and screens, so these moves are more valuable
            bonus += 0.5
    
    # === Speed Tier Awareness ===
    # Prefer moves that help with speed control
    user_speed = getattr(user, 'stats', {}).get('spe', 0) or 0
    target_speed = getattr(target, 'stats', {}).get('spe', 0) or 0
    
    # If we're slower, prioritize speed control moves
    if user_speed < target_speed:
        if move_lower in ["icy-wind", "electroweb", "rock-tomb", "mud-shot", "low-sweep", "thunder-wave", "stun-spore", "glare"]:
            bonus += 1.0  # Speed control is important
    
    # === Taunt Timing ===
    # Use Taunt on setup Pokemon or support Pokemon
    if move_lower == "taunt":
        target_moves = target.moves or []
        setup_moves = ["swords-dance", "dragon-dance", "calm-mind", "nasty-plot", "bulk-up", "quiver-dance"]
        support_moves = ["recover", "slack-off", "soft-boiled", "wish", "heal-bell", "aromatherapy"]
        
        has_setup = any(m.lower() in setup_moves for m in target_moves)
        has_support = any(m.lower() in support_moves for m in target_moves)
        
        if has_setup or has_support:
            bonus += 1.5  # Taunt is valuable here
    
    # === Encore Timing ===
    # Better Encore usage - prefer when opponent just used a status move
    if move_lower == "encore":
        target_last_move = getattr(target, 'last_move_used', None)
        if target_last_move:
            target_last_move_data = get_move(target_last_move)
            if target_last_move_data:
                last_category = (target_last_move_data.get("category") or target_last_move_data.get("damage_class") or "").lower()
                last_power = target_last_move_data.get("power", 0) or 0
                
                # Encore is very valuable if they just used a setup move
                setup_moves = ["swords-dance", "dragon-dance", "calm-mind", "nasty-plot", "bulk-up", 
                              "quiver-dance", "shell-smash", "belly-drum", "geomancy"]
                if target_last_move.lower() in setup_moves:
                    bonus += 3.0  # Huge value to Encore a setup move
                elif last_category == "status" or last_power <= 0:
                    bonus += 1.0  # Good to Encore status moves
    
    # === Trick/Switcheroo Timing ===
    # Use Trick to give opponent bad items or take good items
    if move_lower in ["trick", "switcheroo"]:
        # Check if opponent has a good item we want
        if target.item:
            target_item_lower = target.item.lower()
            good_items = ["leftovers", "black-sludge", "life-orb", "choice-band", "choice-specs", "choice-scarf"]
            if target_item_lower in good_items:
                bonus += 2.0  # Steal their good item!
        
        # Check if we have a bad item to give
        if user.item:
            user_item_lower = user.item.lower()
            bad_items = ["toxic-orb", "flame-orb", "iron-ball", "lagging-tail", "sticky-barb"]
            if user_item_lower in bad_items:
                bonus += 1.5  # Give them our bad item!
    
    # === Terrain/Weather Control ===
    # Set terrain/weather when it benefits our team more
    if move_lower in ["sunny-day", "rain-dance", "sandstorm", "hail"]:
        # Check if we have Pokemon that benefit
        try:
            ai_user_id = battle_state.p1_id if user == battle_state._active(battle_state.p1_id) else battle_state.p2_id
            ai_team = battle_state.team_for(ai_user_id)
            
            weather_benefit = 0
            for team_mon in ai_team:
                if team_mon and team_mon.hp > 0:
                    team_types = team_mon.types or []
                    team_ability = normalize_ability_name(team_mon.ability or "")
                    
                    if move_lower == "sunny-day":
                        if "Fire" in team_types or team_ability == "solar-power" or team_ability == "chlorophyll":
                            weather_benefit += 1
                    elif move_lower == "rain-dance":
                        if "Water" in team_types or team_ability == "swift-swim" or team_ability == "hydration":
                            weather_benefit += 1
                    elif move_lower == "sandstorm":
                        if team_ability == "sand-rush" or team_ability == "sand-force" or "Rock" in team_types:
                            weather_benefit += 1
            
            if weather_benefit > 0:
                bonus += min(weather_benefit * 0.5, 2.0)  # Up to +2.0 for team synergy
        except Exception:
            pass
    
    # === Opponent Threat Assessment ===
    # Calculate what opponent can do to us and adjust strategy
    try:
        target_moves = target.moves or []
        max_opponent_damage = 0
        can_opponent_ko = False
        can_opponent_2hko = False
        
        for t_move in target_moves[:4]:
            try:
                t_dmg, _, _ = damage(target, user, t_move, field_effects, user_side, target_side)
                max_opponent_damage = max(max_opponent_damage, t_dmg)
                if t_dmg >= user.hp:
                    can_opponent_ko = True
                if t_dmg >= user.max_hp / 2:
                    can_opponent_2hko = True
            except Exception:
                continue
        
        # If opponent can KO us, prioritize survival moves
        if can_opponent_ko:
            if move_lower in ["protect", "detect", "kings-shield"]:
                bonus += 2.0  # Protect to survive
            if move_lower in ["substitute"]:
                # Check if sub can save us
                if user.hp > user.max_hp / 4:
                    bonus += 1.5
            # Prefer priority moves to hit first
            move_priority = move_data.get("priority", 0) or 0
            if move_priority > 0 and move_data.get("power", 0) > 0:
                bonus += 1.5
        
        # If opponent can 2HKO and we're slower, be more careful
        if can_opponent_2hko:
            user_speed = getattr(user, 'stats', {}).get('spe', 0) or 0
            target_speed = getattr(target, 'stats', {}).get('spe', 0) or 0
            if user_speed < target_speed:
                # Prefer recovery or setup that helps us survive
                if move_lower in ["recover", "slack-off", "roost", "rest"]:
                    bonus += 1.0
                if move_lower in ["bulk-up", "calm-mind", "iron-defense", "amnesia"]:
                    bonus += 0.5
    except Exception:
        pass
    
    # === Sweeper Detection ===
    # Detect if opponent is setting up to sweep and counter it
    target_stages = getattr(target, 'stages', {}) or {}
    target_has_boosts = any((target_stages.get(stat, 0) or 0) > 0 for stat in ['atk', 'spa', 'spe'])
    
    if target_has_boosts:
        # Opponent is setting up - prioritize countering
        if move_lower in ["roar", "whirlwind", "dragon-tail", "circle-throw", "haze", "clear-smog"]:
            bonus += 2.5  # Very important to stop setup
        if move_lower == "taunt":
            bonus += 1.5  # Prevent further setup
        if move_lower in ["encore"]:
            bonus += 2.0  # Lock them into setup move
        # Prefer high-damage moves to KO before they sweep
        if move_data.get("power", 0) >= 100:
            bonus += 1.0
    
    # === Wall Breaking ===
    # Use wall-breaking moves when opponent is defensive
    target_def = getattr(target, 'stats', {}).get('def', 0) or 0
    target_spd = getattr(target, 'stats', {}).get('spd', 0) or 0
    target_hp = target.max_hp
    
    # Check if opponent is a wall (high HP + high defenses)
    is_wall = target_hp >= 100 and (target_def >= 100 or target_spd >= 100)
    
    if is_wall:
        # Prefer moves that ignore defenses or have high base power
        if move_lower in ["close-combat", "head-smash", "brave-bird", "wood-hammer", "flare-blitz"]:
            bonus += 1.0  # High power moves
        if move_lower in ["psyshock", "psystrike", "secret-sword"]:
            bonus += 1.5  # Hits defense instead of special defense
        if move_lower in ["toxic"]:
            bonus += 1.0  # Toxic is good vs walls
    
    # === Status Spreading ===
    # When to spread status vs attack
    target_moves = target.moves or []
    target_has_recovery = any(m.lower() in ["recover", "slack-off", "soft-boiled", "roost", "rest", "wish"] for m in target_moves)
    target_has_setup = any(m.lower() in ["swords-dance", "dragon-dance", "calm-mind", "nasty-plot", "bulk-up"] for m in target_moves)
    
    # If opponent has recovery/setup, status is more valuable
    if target_has_recovery or target_has_setup:
        if move_lower in ["toxic", "will-o-wisp", "thunder-wave"]:
            bonus += 1.0
    
    # === Hazard Stacking ===
    # When to stack multiple hazards
    if move_lower in ["spikes", "toxic-spikes"]:
        try:
            current_spikes = getattr(target_side, 'spikes', 0) if target_side else 0
            current_toxic = getattr(target_side, 'toxic_spikes', 0) if target_side else 0
            
            # Prefer stacking if we already have some hazards
            if move_lower == "spikes" and current_spikes > 0 and current_spikes < 3:
                bonus += 1.0  # Stack spikes
            if move_lower == "toxic-spikes" and current_toxic > 0 and current_toxic < 2:
                bonus += 1.0  # Stack toxic spikes
        except Exception:
            pass
    
    # === Weather Wars ===
    # Better weather control - remove opponent's weather if it hurts us
    weather = getattr(field_effects, 'weather', None) if field_effects else None
    
    if move_lower in ["rain-dance", "sunny-day", "sandstorm", "hail"]:
        # Check if current weather hurts our team
        ai_user_id = battle_state.p1_id if user == battle_state._active(battle_state.p1_id) else battle_state.p2_id
        ai_team = battle_state.team_for(ai_user_id)
        
        weather_hurts = 0
        for team_mon in ai_team:
            if team_mon and team_mon.hp > 0:
                team_types = team_mon.types or []
                # Hail/Sandstorm damage
                if weather in ["hail", "sandstorm"]:
                    if weather == "hail" and "Ice" not in team_types:
                        weather_hurts += 1
                    elif weather == "sandstorm" and "Rock" not in team_types and "Ground" not in team_types and "Steel" not in team_types:
                        weather_hurts += 1
        
        if weather_hurts > 2:  # Weather hurts most of our team
            bonus += 1.5  # Change weather to help us
    
    # === Terrain Wars ===
    # Better terrain control
    terrain = getattr(field_effects, 'terrain', None) if field_effects else None
    
    if move_lower in ["electric-terrain", "grassy-terrain", "psychic-terrain", "misty-terrain"]:
        # If opponent's terrain is active and hurts us, change it
        if terrain:
            # Misty Terrain blocks status - if we want to status, change it
            if terrain == "misty" and move_lower in ["toxic", "will-o-wisp", "thunder-wave"]:
                # Actually, we want to change terrain first, so this move gets bonus
                if move_lower != "misty-terrain":
                    bonus += 1.0
    
    # === Ability Prediction ===
    # Predict opponent's ability and play around it
    target_ability = normalize_ability_name(target.ability or "")
    
    # Play around common abilities
    if target_ability == "rough-skin" or target_ability == "iron-barbs":
        # Avoid contact moves
        move_effect = get_move_secondary_effect(move_lower)
        if move_effect and move_effect.get("makes_contact"):
            bonus -= 1.0  # Penalize contact moves
    
    if target_ability == "static":
        # Avoid contact moves that could paralyze us
        move_effect = get_move_secondary_effect(move_lower)
        if move_effect and move_effect.get("makes_contact"):
            if move_category == "physical":
                bonus -= 0.5
    
    if target_ability == "flame-body":
        # Avoid contact moves that could burn us
        move_effect = get_move_secondary_effect(move_lower)
        if move_effect and move_effect.get("makes_contact"):
            if move_category == "physical":
                bonus -= 0.5
    
    if target_ability == "magic-bounce":
        # Don't use status moves that can be bounced
        if move_lower in ["stealth-rock", "spikes", "toxic-spikes", "sticky-web", "toxic", "will-o-wisp", "thunder-wave"]:
            bonus -= 3.0  # Heavy penalty - will bounce back
    
    if target_ability == "flash-fire":
        # Don't use Fire moves (they'll be immune and get boost)
        if move_type == "Fire":
            bonus -= 2.0
    
    if target_ability == "levitate":
        # Ground moves won't work
        if move_type == "Ground":
            bonus -= 2.0
    
    # === Item Prediction ===
    # Predict opponent's item and play around it
    if target.item:
        target_item_lower = target.item.lower()
        
        if "leftovers" in target_item_lower or "black-sludge" in target_item_lower:
            # They're healing - prefer moves that can KO or status
            if move_data.get("power", 0) >= 100:
                bonus += 0.5
            if move_lower in ["toxic", "will-o-wisp"]:
                bonus += 0.5
        
        if "focus-sash" in target_item_lower:
            # They have Sash - prefer multi-hit moves or moves that can break it
            if move_lower in ["icicle-spear", "bullet-seed", "arm-thrust", "double-hit"]:
                bonus += 1.0
        
        if "choice" in target_item_lower:
            # They're locked into a move - we can predict and counter
            # This is already handled in move prediction, but we can be more aggressive
            bonus += 0.3
    
    # === Win Condition Planning ===
    # Plan for specific win conditions
    try:
        ai_user_id = battle_state.p1_id if user == battle_state._active(battle_state.p1_id) else battle_state.p2_id
        opp_user_id = battle_state.p2_id if ai_user_id == battle_state.p1_id else battle_state.p1_id
        
        ai_team = battle_state.team_for(ai_user_id)
        opp_team = battle_state.team_for(opp_user_id)
        
        ai_alive = sum(1 for m in ai_team if m and m.hp > 0)
        opp_alive = sum(1 for m in opp_team if m and m.hp > 0)
        
        # If we have a setup sweeper and opponent is weakened, prioritize setup
        if ai_alive >= 2 and opp_alive <= 2:
            # Late game - setup can win
            if move_lower in ["swords-dance", "dragon-dance", "calm-mind", "nasty-plot", "quiver-dance"]:
                bonus += 1.0
        
        # If opponent has one Pokemon left and it's low HP, prioritize finishing
        if opp_alive == 1:
            target_hp_percent = target.hp / target.max_hp if target.max_hp > 0 else 1.0
            if target_hp_percent < 0.5:
                if move_data.get("power", 0) > 0:
                    try:
                        dmg, _, _ = damage(user, target, move_name, field_effects, target_side, user_side)
                        if dmg >= target.hp:
                            bonus += 2.0  # This can win!
                    except Exception:
                        pass
    except Exception:
        pass
    
    # === Resource Management ===
    # Better PP and HP management
    try:
        if hasattr(battle_state, '_pp_left'):
            pp_remaining = battle_state._pp_left(
                battle_state.p1_id if user == battle_state._active(battle_state.p1_id) else battle_state.p2_id,
                move_name, user
            )
            
            # If this is our last PP for a good move, be more careful
            if pp_remaining == 1:
                # Only use if it's really important
                if move_data.get("power", 0) >= 100 or move_lower in ["recover", "rest"]:
                    bonus += 0.0  # OK to use
                else:
                    bonus -= 1.0  # Save it
    except Exception:
        pass
    
    # === Priority Move Usage ===
    # Better use of priority when needed
    move_priority = move_data.get("priority", 0) or 0
    
    if move_priority > 0:
        # Use priority when we're slower and opponent can KO
        user_speed = getattr(user, 'stats', {}).get('spe', 0) or 0
        target_speed = getattr(target, 'stats', {}).get('spe', 0) or 0
        
        if user_speed < target_speed:
            try:
                target_moves = target.moves or []
                can_ko = False
                for t_move in target_moves[:4]:
                    try:
                        t_dmg, _, _ = damage(target, user, t_move, field_effects, user_side, target_side)
                        if t_dmg >= user.hp:
                            can_ko = True
                            break
                    except Exception:
                        continue
                
                if can_ko:
                    bonus += 2.0  # Priority is very valuable here
            except Exception:
                pass
    
    # === Move Sequencing ===
    # Plan multi-turn strategies
    user_last_move = getattr(user, 'last_move_used', None)
    
    # If we just set up, prefer attacking moves
    if user_last_move and user_last_move.lower() in ["swords-dance", "dragon-dance", "calm-mind", "nasty-plot"]:
        if move_data.get("power", 0) > 0:
            bonus += 1.0  # Capitalize on setup
    
    # If we just used a pivot move, we're probably switching anyway
    if user_last_move and user_last_move.lower() in ["u-turn", "volt-switch", "flip-turn"]:
        # Pivot moves already handled, but we can consider this
        pass
    
    # === Bluffing / Unpredictability ===
    # Sometimes use unexpected moves (small random factor)
    # This makes AI less predictable
    if random.random() < 0.05:  # 5% chance
        # Small random bonus/penalty to add unpredictability
        bonus += random.uniform(-0.5, 0.5)
    
    # === 1. Team Preview Analysis ===
    bonus += _team_preview_bonus(user, target, move_name, move_lower, move_data, battle_state, field_effects)
    
    # === 2. Move Prediction ===
    bonus += _move_prediction_bonus(user, target, move_name, move_lower, move_data, battle_state, field_effects, user_side, target_side)
    
    # === 3. Sacrifice Plays ===
    bonus += _sacrifice_play_bonus(user, target, move_name, move_lower, move_data, battle_state, field_effects)
    
    # === 4. Momentum Tracking ===
    bonus += _momentum_tracking_bonus(user, target, move_name, move_lower, move_data, battle_state, field_effects)
    
    # === 5. Type Chart Mastery ===
    bonus += _type_chart_mastery_bonus(user, target, move_name, move_lower, move_data, battle_state, field_effects)
    
    # === 6. Speed Tier Awareness ===
    bonus += _speed_tier_bonus(user, target, move_name, move_lower, move_data, battle_state, field_effects)
    
    # === 7. Set Scouting ===
    bonus += _set_scouting_bonus(user, target, move_name, move_lower, move_data, battle_state, field_effects)
    
    # === 8. Win Condition Identification ===
    bonus += _win_condition_bonus(user, target, move_name, move_lower, move_data, battle_state, field_effects, user_side, target_side)
    
    # === 9. Switch Prediction ===
    bonus += _switch_prediction_bonus(user, target, move_name, move_lower, move_data, battle_state, field_effects)
    
    # === 10. Status Synergy ===
    bonus += _status_synergy_bonus(user, target, move_name, move_lower, move_data, battle_state, field_effects)
    
    # === 11. Hazard Removal Timing ===
    bonus += _hazard_removal_timing_bonus(user, target, move_name, move_lower, move_data, battle_state, field_effects, user_side, target_side)
    
    # === 12. Losing Position Recovery ===
    bonus += _losing_position_bonus(user, target, move_name, move_lower, move_data, battle_state, field_effects)
    
    # === 13. Lead Matchup Analysis ===
    bonus += _lead_matchup_bonus(user, target, move_name, move_lower, move_data, battle_state, field_effects)
    
    # === 14. Mid-Game Transitions ===
    bonus += _mid_game_transition_bonus(user, target, move_name, move_lower, move_data, battle_state, field_effects)
    
    # === 15. Conditional Move Usage ===
    bonus += _conditional_move_bonus(user, target, move_name, move_lower, move_data, battle_state, field_effects)
    
    # === 16. Team Synergy ===
    bonus += _team_synergy_bonus(user, target, move_name, move_lower, move_data, battle_state, field_effects)
    
    # === 17. Meta Knowledge ===
    bonus += _meta_knowledge_bonus(user, target, move_name, move_lower, move_data, battle_state, field_effects)
    
    # === 18. Turn Order Prediction ===
    bonus += _turn_order_prediction_bonus(user, target, move_name, move_lower, move_data, battle_state, field_effects, user_side, target_side)
    
    # === 19. Clutch Plays ===
    bonus += _clutch_play_bonus(user, target, move_name, move_lower, move_data, battle_state, field_effects, user_side, target_side)
    
    # === 20. Damage Range Calculation ===
    bonus += _damage_range_bonus(user, target, move_name, move_lower, move_data, battle_state, field_effects, user_side, target_side)
    
    return bonus


def _score_setup_move(
    user: Mon,
    target: Mon,
    move_lower: str,
    move_data: Dict[str, Any],
    battle_state: Any,
    field_effects: Any
) -> float:
    """Score setup moves (Dragon Dance, Swords Dance, etc.)"""
    score = 0.0
    
    # Never setup if target can KO user (unless Sturdy/Sash)
    try:
        target_moves = target.moves or []
        can_ko = False
        for t_move in target_moves[:4]:
            try:
                t_dmg, _, _ = damage(target, user, t_move, field_effects, None, None)
                if t_dmg >= user.hp:
                    can_ko = True
                    break
            except Exception:
                continue
        
        if can_ko:
            # Check for Sturdy/Sash
            has_sturdy = False
            user_ability = normalize_ability_name(user.ability or "")
            if user_ability == "sturdy" and user.hp == user.max_hp:
                has_sturdy = True
            
            has_sash = False
            if user.item and "focus-sash" in user.item.lower():
                has_sash = True
            
            if not has_sturdy and not has_sash:
                return -20.0  # Never setup
    except Exception:
        pass
    
    # Never setup against Unaware (except Power-up Punch, Swords Dance, Howl)
    target_ability = normalize_ability_name(target.ability or "")
    if target_ability == "unaware":
        if move_lower not in ["power-up-punch", "swords-dance", "howl"]:
            return -20.0
    
    # Offensive setup (Dragon Dance, Swords Dance, etc.)
    offensive_setup = ["dragon-dance", "swords-dance", "howl", "shift-gear", "hone-claws"]
    if move_lower in offensive_setup:
        # Check if target is incapacitated
        if target.status == "slp" or target.status == "frz" or \
           getattr(target, 'recharging_move', None) or getattr(target, 'truant', False):
            score += 3.0
        else:
            # Check if target can 3HKO
            try:
                target_moves = target.moves or []
                can_3hko = False
                for t_move in target_moves[:4]:
                    try:
                        t_dmg, _, _ = damage(target, user, t_move, field_effects, None, None)
                        if t_dmg >= user.max_hp / 3:
                            can_3hko = True
                            break
                    except Exception:
                        continue
                
                if not can_3hko:
                    score += 1.0
                    # Check if faster
                    user_speed = getattr(user, 'stats', {}).get('spe', 0) or 0
                    target_speed = getattr(target, 'stats', {}).get('spe', 0) or 0
                    if user_speed > target_speed:
                        score += 1.0
            except Exception:
                pass
            
            # Penalty if slower and 2HKO'd
            user_speed = getattr(user, 'stats', {}).get('spe', 0) or 0
            target_speed = getattr(target, 'stats', {}).get('spe', 0) or 0
            if user_speed < target_speed:
                try:
                    target_moves = target.moves or []
                    can_2hko = False
                    for t_move in target_moves[:4]:
                        try:
                            t_dmg, _, _ = damage(target, user, t_move, field_effects, None, None)
                            if t_dmg >= user.max_hp / 2:
                                can_2hko = True
                                break
                        except Exception:
                            continue
                    
                    if can_2hko:
                        score -= 5.0
                except Exception:
                    pass
        
        # Penalty if already at +2 Atk or higher
        atk_stage = getattr(user, 'stages', {}).get('atk', 0) or 0
        if atk_stage >= 2:
            score -= 1.0
    
    # Special setup moves (Shell Smash, Belly Drum, etc.)
    if move_lower == "shell-smash":
        if target.status == "slp" or target.status == "frz" or getattr(target, 'recharging_move', None):
            score += 3.0
        
        # Check if target can KO after Shell Smash
        try:
            target_moves = target.moves or []
            can_ko_after = False
            for t_move in target_moves[:4]:
                try:
                    # Estimate damage after Shell Smash (defenses drop)
                    t_dmg, _, _ = damage(target, user, t_move, field_effects, None, None)
                    # Rough estimate: damage increases by ~1.5x after defense drop
                    if t_dmg * 1.5 >= user.hp:
                        can_ko_after = True
                        break
                except Exception:
                    continue
            
            if can_ko_after:
                score -= 2.0
            else:
                score += 2.0
        except Exception:
            pass
        
        # Never use if already boosted
        atk_stage = getattr(user, 'stages', {}).get('atk', 0) or 0
        spa_stage = getattr(user, 'stages', {}).get('spa', 0) or 0
        if atk_stage >= 1 or spa_stage >= 6 or atk_stage >= 6:
            return -20.0
    
    if move_lower == "belly-drum":
        if target.status == "slp" or target.status == "frz" or getattr(target, 'recharging_move', None):
            score += 3.0
        else:
            # Check if target can KO after Belly Drum
            try:
                target_moves = target.moves or []
                can_ko_after = False
                for t_move in target_moves[:4]:
                    try:
                        t_dmg, _, _ = damage(target, user, t_move, field_effects, None, None)
                        # After Belly Drum, user is at 50% HP
                        if t_dmg >= user.max_hp / 2:
                            can_ko_after = True
                            break
                    except Exception:
                        continue
                
                if not can_ko_after:
                    score += 2.0
                else:
                    score -= 4.0
            except Exception:
                pass
    
    return score


def _score_recovery_move(
    user: Mon,
    target: Mon,
    move_lower: str,
    battle_state: Any,
    field_effects: Any
) -> float:
    """Score recovery moves. Returns additive bonus."""
    # Check if AI should recover (see EXTRA DETAILS section)
    should_recover = _should_ai_recover(user, target, move_lower, battle_state, field_effects)
    
    if should_recover:
        return 1.0  # +7 total (6 base + 1)
    else:
        return -1.0  # +5 total (6 base - 1)
    
    # Penalty if at 85%+ HP
    hp_percent = user.hp / user.max_hp if user.max_hp > 0 else 1.0
    if hp_percent >= 0.85:
        return -6.0  # Heavy penalty


def _should_ai_recover(
    user: Mon,
    target: Mon,
    move_lower: str,
    battle_state: Any,
    field_effects: Any
) -> bool:
    """
    Determine if AI should use a recovery move.
    Based on EXTRA DETAILS section of Run and Bun AI document.
    """
    # Recovery percentage
    if move_lower in ["recover", "slack-off", "heal-order", "roost", "strength-sap"]:
        recovery_percent = 0.5
    elif move_lower in ["morning-sun", "synthesis", "moonlight"]:
        # Check if sun is active
        weather = getattr(field_effects, 'weather', None) if field_effects else None
        if weather == "sun":
            recovery_percent = 0.67
        else:
            recovery_percent = 0.5
    else:
        recovery_percent = 0.5
    
    heal_amount = user.max_hp * recovery_percent
    
    # Never recover if Toxic'd
    if user.status in ["tox", "psn"]:
        return False
    
    # Never recover if target does more damage than would be healed
    try:
        target_moves = target.moves or []
        max_damage = 0
        for t_move in target_moves[:4]:
            try:
                t_dmg, _, _ = damage(target, user, t_move, field_effects, None, None)
                max_damage = max(max_damage, t_dmg)
            except Exception:
                continue
        
        if max_damage >= heal_amount:
            return False
    except Exception:
        pass
    
    # Speed comparison
    user_speed = getattr(user, 'stats', {}).get('spe', 0) or 0
    target_speed = getattr(target, 'stats', {}).get('spe', 0) or 0
    is_faster = user_speed >= target_speed
    
    if is_faster:
        # Check if target can KO, but not after recovery
        try:
            target_moves = target.moves or []
            can_ko = False
            can_ko_after = False
            for t_move in target_moves[:4]:
                try:
                    t_dmg, _, _ = damage(target, user, t_move, field_effects, None, None)
                    if t_dmg >= user.hp:
                        can_ko = True
                    if t_dmg >= (user.hp + heal_amount):
                        can_ko_after = True
                except Exception:
                    continue
            
            if can_ko and not can_ko_after:
                return True
            
            if not can_ko:
                hp_percent = user.hp / user.max_hp if user.max_hp > 0 else 1.0
                if 0.4 < hp_percent < 0.66:
                    return random.random() < 0.5
                if hp_percent <= 0.4:
                    return True
        except Exception:
            pass
    else:
        # Slower
        hp_percent = user.hp / user.max_hp if user.max_hp > 0 else 1.0
        if hp_percent <= 0.7:
            return random.random() < 0.75
        if hp_percent <= 0.5:
            return True
    
    return False


def _score_rest(
    user: Mon,
    target: Mon,
    battle_state: Any,
    field_effects: Any
) -> float:
    """Score Rest move."""
    should_recover = _should_ai_recover(user, target, "rest", battle_state, field_effects)
    
    if should_recover:
        # Check for sleep-curing items/abilities
        has_sleep_cure = False
        if user.item:
            item_lower = user.item.lower()
            if "lum-berry" in item_lower or "chesto-berry" in item_lower:
                has_sleep_cure = True
        
        user_ability = normalize_ability_name(user.ability or "")
        if user_ability in ["shed-skin", "early-bird"]:
            has_sleep_cure = True
        
        if user_ability == "hydration":
            weather = getattr(field_effects, 'weather', None) if field_effects else None
            if weather == "rain":
                has_sleep_cure = True
        
        # Check for Sleep Talk / Snore
        user_moves = user.moves or []
        has_sleep_talk = "sleep-talk" in [m.lower() for m in user_moves]
        has_snore = "snore" in [m.lower() for m in user_moves]
        
        if has_sleep_cure or has_sleep_talk or has_snore:
            return 2.0  # +8 total
        else:
            return 1.0  # +7 total
    else:
        return -1.0  # +5 total


def _score_paralysis_move(
    user: Mon,
    target: Mon,
    battle_state: Any,
    field_effects: Any
) -> float:
    """Score paralysis moves (Thunder Wave, Stun Spore, etc.)"""
    score = 0.0
    
    user_speed = getattr(user, 'stats', {}).get('spe', 0) or 0
    target_speed = getattr(target, 'stats', {}).get('spe', 0) or 0
    
    # Check conditions for +8
    condition_met = False
    
    # Target is faster but slower after paralysis (1/4 speed)
    if target_speed > user_speed and target_speed / 4 <= user_speed:
        condition_met = True
    
    # AI has Hex or flinch move
    user_moves = user.moves or []
    user_has_hex = "hex" in [m.lower() for m in user_moves]
    user_has_flinch = any(get_move(m) and get_move(m).get("secondary_effect_chance") for m in user_moves)
    
    if user_has_hex or user_has_flinch:
        condition_met = True
    
    # Target is infatuated or confused
    if getattr(target, 'infatuated', False) or getattr(target, 'confused', False):
        condition_met = True
    
    if condition_met:
        score += 2.0  # +8 total
    else:
        score += 1.0  # +7 total
    
    # Random -1 penalty
    if random.random() < 0.5:
        score -= 1.0
    
    return score


def _score_willowisp(
    user: Mon,
    target: Mon,
    battle_state: Any,
    field_effects: Any
) -> float:
    """Score Will-O-Wisp."""
    score = 0.0
    
    # ~37% of the time, check conditions
    if random.random() < 0.37:
        # Check if target has physical moves
        target_moves = target.moves or []
        has_physical = False
        for t_move in target_moves[:4]:
            move_data = get_move(t_move)
            if move_data:
                category = (move_data.get("category") or move_data.get("damage_class") or "").lower()
                if category == "physical":
                    has_physical = True
                    break
        
        if has_physical:
            score += 1.0
        
        # Check for Hex
        user_moves = user.moves or []
        user_has_hex = "hex" in [m.lower() for m in user_moves]
        # Also check partner in doubles (not implemented here)
        
        if user_has_hex:
            score += 1.0
    
    return score


def _score_toxic(
    user: Mon,
    target: Mon,
    battle_state: Any,
    field_effects: Any
) -> float:
    """Score Toxic move."""
    score = 0.0
    
    # ~38% of the time, if AI cannot KO target
    if random.random() < 0.38:
        # Check if target can be poisoned and is above 20% HP
        hp_percent = target.hp / target.max_hp if target.max_hp > 0 else 1.0
        
        if hp_percent > 0.2:
            # Check if target has no damaging moves
            target_moves = target.moves or []
            has_damaging = False
            for t_move in target_moves[:4]:
                move_data = get_move(t_move)
                if move_data:
                    power = move_data.get("power", 0) or 0
                    if power > 0:
                        has_damaging = True
                        break
            
            if not has_damaging:
                score += 1.0
            
            # Check for Hex, Venom Drench, Merciless
            user_moves = user.moves or []
            user_has_hex = "hex" in [m.lower() for m in user_moves]
            user_has_venom_drench = "venom-drench" in [m.lower() for m in user_moves]
            user_ability = normalize_ability_name(user.ability or "")
            has_merciless = user_ability == "merciless"
            
            if user_has_hex or user_has_venom_drench or has_merciless:
                score += 2.0
            else:
                score += 1.0
    
    return score


def _get_sides_for_user(ai_user_id: int, battle_state: Any) -> Tuple[Any, Any]:
    """Return (user_side, target_side) for the acting AI user."""
    if ai_user_id == getattr(battle_state, "p1_id", None):
        return getattr(battle_state, "p1_side", None), getattr(battle_state, "p2_side", None)
    return getattr(battle_state, "p2_side", None), getattr(battle_state, "p1_side", None)


def _safe_damage_estimate(
    attacker: Mon,
    defender: Mon,
    move_name: str,
    field_effects: Any,
    defender_side: Any = None,
    attacker_side: Any = None,
) -> int:
    """Best-effort damage estimate; never raises."""
    try:
        dmg, _, _ = damage(
            attacker,
            defender,
            move_name,
            field_effects,
            defender_side,
            attacker_side,
            is_moving_last=False,
        )
        return max(0, int(dmg or 0))
    except Exception:
        return 0


def _is_grounded_for_hazards(mon: Mon) -> bool:
    """Simple grounded check for hazard entry scoring."""
    try:
        types = [str(t).lower() for t in (getattr(mon, "types", None) or []) if t]
        if "flying" in types:
            return False
        ability = normalize_ability_name(getattr(mon, "ability", "") or "")
        if ability == "levitate":
            return False
        if getattr(mon, "magnet_rise_turns", 0) > 0:
            return False
        if getattr(mon, "telekinesis_turns", 0) > 0:
            return False
    except Exception:
        pass
    return True


def _hazard_entry_penalty_percent(mon: Mon, side: Any, field_effects: Any, opponent: Optional[Mon] = None) -> float:
    """Approximate HP% penalty/cost when this mon switches in."""
    if side is None:
        return 0.0

    total = 0.0
    # Stealth Rock
    if getattr(side, "stealth_rock", False):
        rock_mult = 1.0
        try:
            rock_mult, _ = type_multiplier("Rock", mon, field_effects=field_effects, user=opponent or mon)
            rock_mult = float(rock_mult)
        except Exception:
            rock_mult = 1.0
        total += 12.5 * max(0.0, rock_mult)

    grounded = _is_grounded_for_hazards(mon)
    if grounded:
        # Spikes
        spikes = int(getattr(side, "spikes", 0) or 0)
        if spikes == 1:
            total += 12.5
        elif spikes == 2:
            total += 16.67
        elif spikes >= 3:
            total += 25.0

        # Toxic Spikes / Sticky Web are not direct HP damage, but still hurt position
        t_spikes = int(getattr(side, "toxic_spikes", 0) or 0)
        if t_spikes > 0:
            mon_types = [str(t).lower() for t in (getattr(mon, "types", None) or []) if t]
            if "poison" in mon_types:
                # Absorbing Toxic Spikes is actually beneficial tempo
                total = max(0.0, total - 2.5)
            elif "steel" not in mon_types:
                total += 8.0
        if bool(getattr(side, "sticky_web", False)):
            total += 4.0

    return max(0.0, total)


def _max_damage_percent(
    attacker: Mon,
    defender: Mon,
    moves: List[str],
    field_effects: Any,
    defender_side: Any = None,
    attacker_side: Any = None,
) -> Tuple[float, Optional[str]]:
    """Return (max_damage_percent_of_defender_hp, move_name)."""
    if not moves:
        return 0.0, None
    defender_hp = max(1, int(getattr(defender, "hp", 1) or 1))
    best_pct = 0.0
    best_move: Optional[str] = None
    for mv in moves[:4]:
        if not mv:
            continue
        dmg = _safe_damage_estimate(attacker, defender, str(mv), field_effects, defender_side, attacker_side)
        pct = (dmg / defender_hp) * 100.0
        if pct > best_pct:
            best_pct = pct
            best_move = str(mv)
    return best_pct, best_move


def _defensive_ability_switch_bonus(switch_mon: Mon, target_move_types: set[str]) -> float:
    """Reward defensive/immunity abilities on switch-in."""
    ability = normalize_ability_name(getattr(switch_mon, "ability", "") or "")
    if not ability:
        return 0.0

    bonus = 0.0
    # Hard immunities / absorptions
    if "Fire" in target_move_types and ability in {"flash-fire", "well-baked-body"}:
        bonus += 6.0
    if "Water" in target_move_types and ability in {"water-absorb", "storm-drain", "dry-skin"}:
        bonus += 6.0
    if "Electric" in target_move_types and ability in {"volt-absorb", "motor-drive", "lightning-rod"}:
        bonus += 6.0
    if "Ground" in target_move_types and ability in {"levitate"}:
        bonus += 5.0
    if "Grass" in target_move_types and ability in {"sap-sipper"}:
        bonus += 5.0

    # Generic useful switch abilities
    if ability in {"intimidate", "regenerator", "natural-cure"}:
        bonus += 2.0
    return bonus


def choose_ai_action(
    ai_user_id: int,
    battle_state: Any,
    field_effects: Any
) -> Dict[str, Any]:
    """
    Choose an action for the AI player with richer tactical evaluation.
    """
    # Check if this is a dummy opponent (negative ID indicates dummy)
    # Also check if the active Pokémon is a dummy Magikarp
    is_dummy = False
    if ai_user_id < 0:
        is_dummy = True
    else:
        # Check active Pokémon
        active_mon = battle_state._active(ai_user_id)
        if active_mon and getattr(active_mon, '_is_dummy_magikarp', False):
            is_dummy = True
    
    # For dummy Magikarp, always use Tackle
    if is_dummy:
        return {"kind": "move", "value": "Tackle"}

    # If we have no active mon data, default to random move
    ai_mon = battle_state._active(ai_user_id)
    target_mon = battle_state._opp_active(ai_user_id)
    if not ai_mon or not target_mon:
        fallback = battle_state.moves_for(ai_user_id) or ["Tackle"]
        return {"kind": "move", "value": str(random.choice(fallback))}

    user_side, target_side = _get_sides_for_user(ai_user_id, battle_state)
    ai_speed = int(speed_value(ai_mon, user_side, field_effects))
    target_speed = int(speed_value(target_mon, target_side, field_effects))
    ai_hp_pct = ai_mon.hp / ai_mon.max_hp if ai_mon.max_hp > 0 else 1.0
    target_hp = max(1, int(target_mon.hp or 1))

    # Track previous AI action to avoid repetitive hard-switch loops.
    analysis = _battle_analysis.setdefault(id(battle_state), {})
    last_action_key = f"last_action_{ai_user_id}"

    # Normalize available moves (must be strings with PP > 0)
    available_moves_raw = battle_state.moves_for(ai_user_id) or []
    available_moves: List[str] = []
    for m in available_moves_raw:
        if isinstance(m, str):
            name = m
        elif isinstance(m, dict):
            name = str(m.get("name") or m.get("value") or "")
        else:
            name = str(m) if m else ""
        if not name:
            continue
        try:
            if battle_state._pp_left(ai_user_id, name, ai_mon) <= 0:
                continue
        except Exception:
            pass
        available_moves.append(name)
    if not available_moves:
        available_moves = ["Tackle"]

    # Precompute rough incoming threat from opponent.
    target_moves = [str(m) for m in (getattr(target_mon, "moves", None) or []) if m]
    max_incoming_pct, _ = _max_damage_percent(
        target_mon, ai_mon, target_moves, field_effects, user_side, target_side
    )
    under_lethal_pressure = max_incoming_pct >= 100.0

    # Precompute raw damage for each move, then identify highest-damage move.
    damage_cache: Dict[str, int] = {}
    for mv in available_moves:
        damage_cache[mv] = _safe_damage_estimate(
            ai_mon, target_mon, mv, field_effects, target_side, user_side
        )
    highest_damage = max(damage_cache.values()) if damage_cache else 0

    # Score all candidate moves.
    scored_moves: List[Tuple[float, str, float, int]] = []  # (score, move, dmg_pct, priority)
    setup_moves = {"swords-dance", "dragon-dance", "calm-mind", "nasty-plot", "quiver-dance", "bulk-up"}
    recovery_moves = {"recover", "roost", "slack-off", "soft-boiled", "heal-order", "strength-sap", "rest"}
    pivot_moves = {"u-turn", "volt-switch", "flip-turn", "parting-shot", "baton-pass"}

    for mv in available_moves:
        mv_data = get_move(mv) or {}
        move_lower = mv.lower().replace(" ", "-")
        category = (mv_data.get("category") or mv_data.get("damage_class") or "status").lower()
        power = int(mv_data.get("power") or 0)
        priority = int(mv_data.get("priority") or 0)
        accuracy = float(mv_data.get("accuracy") or 100.0)
        is_damaging = power > 0 and category != "status"
        dmg = int(damage_cache.get(mv, 0))
        dmg_pct = (dmg / target_hp) * 100.0
        is_highest_damage = bool(is_damaging and dmg >= highest_damage and highest_damage > 0)

        # Base tactical score from the advanced scorer.
        score = calculate_move_score(
            ai_mon,
            target_mon,
            mv,
            battle_state,
            field_effects,
            user_side,
            target_side,
            is_double_battle=False,
            is_highest_damage=is_highest_damage,
        )

        # Reliability/accuracy weighting for all moves.
        score *= max(0.45, min(1.05, (accuracy / 100.0) + 0.05))

        if is_damaging:
            # Damage pressure and KO conversion.
            score += min(12.0, dmg_pct * 0.12)
            if dmg >= target_hp:
                acts_first = priority > 0 or ai_speed >= target_speed
                score += 12.0 if acts_first else 5.0
            elif dmg_pct >= 70.0:
                score += 4.5
            elif dmg_pct <= 8.0:
                score -= 4.0
            # PP conservation for offensive options.
            try:
                pp_left = battle_state._pp_left(ai_user_id, mv, ai_mon)
                max_pp = max(pp_left, _max_pp(mv, generation=getattr(battle_state, "gen", 9)))
                if max_pp > 0 and (pp_left / max_pp) < 0.20:
                    score -= 1.2
            except Exception:
                pass
        else:
            # Under severe pressure, greedier setup is often punished.
            if under_lethal_pressure and move_lower in setup_moves:
                score -= 12.0
            if move_lower in recovery_moves and ai_hp_pct <= 0.45:
                score += 6.0
            if move_lower in pivot_moves and (under_lethal_pressure or highest_damage < max(1, int(target_hp * 0.30))):
                score += 3.5
            if move_lower in setup_moves and not under_lethal_pressure and ai_hp_pct > 0.65:
                score += 2.0

        # Tiny jitter prevents perfectly deterministic bots while keeping best plays dominant.
        score += random.uniform(-0.35, 0.35)
        scored_moves.append((score, mv, dmg_pct, priority))

    if not scored_moves:
        move = str(random.choice(available_moves))
        analysis[last_action_key] = "move"
        analysis[f"last_move_{ai_user_id}"] = move
        return {"kind": "move", "value": move}

    scored_moves.sort(key=lambda x: x[0], reverse=True)
    best_score, best_move, best_dmg_pct, best_prio = scored_moves[0]
    best_dmg = damage_cache.get(best_move, 0)
    can_fast_ko = best_dmg >= target_hp and (best_prio > 0 or ai_speed >= target_speed)

    # Switch decision: only if legal and materially better than best move.
    switch_options = battle_state.switch_options(ai_user_id) or []
    do_switch = False
    best_switch_idx: Optional[int] = None

    if switch_options:
        can_sw, _ = can_switch_out(ai_mon, target_mon, force_switch=False, field_effects=field_effects, battle_state=battle_state)
        if can_sw:
            last_type = getattr(target_mon, "_last_move_used_type", None)
            best_switch_idx, best_switch_score = _choose_best_switch_with_score(
                current_mon=ai_mon,
                target_mon=target_mon,
                switch_options=switch_options,
                battle_state=battle_state,
                field_effects=field_effects,
                switching_user_id=ai_user_id,
                last_move_type=last_type,
            )

            if best_switch_idx is not None:
                # Discourage consecutive hard-switching unless heavily justified.
                margin = 5.5
                if analysis.get(last_action_key) == "switch":
                    margin += 2.5

                meaningful_damage = any(dmg_cache >= target_hp * 0.25 for dmg_cache in damage_cache.values())
                if under_lethal_pressure and not can_fast_ko and best_switch_score >= best_score + margin:
                    do_switch = True
                elif (not meaningful_damage or best_dmg_pct < 22.0) and best_switch_score >= best_score + (margin - 1.5):
                    do_switch = True
                elif ai_hp_pct < 0.33 and best_dmg_pct < 45.0 and best_switch_score >= best_score + (margin - 2.0):
                    do_switch = True

                # If we just switched in and are not in immediate danger, avoid pivot loops.
                if getattr(ai_mon, "_just_switched_in", False) and not under_lethal_pressure and best_dmg_pct >= 30.0:
                    do_switch = False

    if do_switch and best_switch_idx is not None:
        analysis[last_action_key] = "switch"
        return {"kind": "switch", "value": int(best_switch_idx)}

    # Move choice: sample among near-top moves, weighted by score (human-like variety).
    top_band = [m for m in scored_moves if m[0] >= best_score - 1.75]
    if len(top_band) > 1:
        max_s = max(m[0] for m in top_band)
        weights = [math.exp((m[0] - max_s) / 1.8) for m in top_band]
        chosen = random.choices(top_band, weights=weights, k=1)[0]
    else:
        chosen = top_band[0]

    analysis[last_action_key] = "move"
    analysis[f"last_move_{ai_user_id}"] = chosen[1]
    return {"kind": "move", "value": chosen[1]}


def _status_immune(move_name: str, target: Mon) -> bool:
    name = move_name.lower().replace(" ", "-")
    ttypes = [t.lower() for t in (target.types or []) if t]
    status = getattr(target, "status", None)
    if name in ("toxic", "poison-powder", "toxic-spikes"):
        if "steel" in ttypes or "poison" in ttypes:
            return True
    if name in ("will-o-wisp",):
        if "fire" in ttypes:
            return True
    if name in ("thunder-wave",):
        if "ground" in ttypes:
            return True
    if status:
        # already statused
        return True
    return False


def _score_status_or_setup(move_name: str, user: Mon, target: Mon, field_effects: Any, battle_state: Any) -> float:
    """Heuristic for non-damaging moves, with light safety checks."""
    name = move_name.lower().replace(" ", "-")
    hp_pct = target.hp / target.max_hp if target.max_hp > 0 else 1.0
    user_hp_pct = user.hp / user.max_hp if user.max_hp > 0 else 1.0
    # Simple safety: if user is low, avoid greedy setup
    low_hp_risk = user_hp_pct < 0.6
    # Predict last seen target move type to judge risk
    last_type = getattr(target, "_last_move_used_type", None)
    if last_type and user.types:
        try:
            worst_mult = max(type_multiplier(last_type, user, field_effects=field_effects, user=target)[0], 0)
        except Exception:
            worst_mult = 1.0
        unsafe_matchup = worst_mult >= 2.0
    else:
        unsafe_matchup = False

    # Strong boosts
    if name in ("swords-dance", "nasty-plot", "calm-mind", "dragon-dance", "bulk-up", "quiver-dance"):
        if low_hp_risk or unsafe_matchup:
            return 8.0
        return 45.0
    # Accuracy / evasion buffs less valued
    if name in ("double-team", "minimize", "sand-attack", "smokescreen"):
        return 8.0

    # Status moves
    if name in ("toxic", "will-o-wisp", "thunder-wave", "spore", "sleep-powder", "stun-spore"):
        if _status_immune(name, target):
            return 1.0
        # Avoid empowering Guts/Flare Boost/Quick Feet with burn/poison
        t_ability = normalize_ability_name(getattr(target, "ability", "") or "")
        if name in ("toxic", "will-o-wisp") and t_ability in ("guts", "flare-boost", "quick-feet", "magic-guard"):
            return 4.0
        if name in ("toxic", "will-o-wisp") and hp_pct > 0.4:
            return 38.0
        if name in ("thunder-wave", "stun-spore") and hp_pct > 0.25:
            return 30.0
        if name in ("spore", "sleep-powder"):
            return 45.0
        return 12.0

    # Hazards
    if name in ("stealth-rock", "spikes", "toxic-spikes"):
        return 18.0 if hp_pct > 0.6 else 6.0

    # Taunt vs setup walls (simple heuristic: if target has low power moves)
    if name == "taunt":
        t_moves = target.moves or []
        damaging = False
        for m in t_moves[:4]:
            md = get_move(m) or {}
            if int(md.get("power") or 0) > 0:
                damaging = True
                break
        return 25.0 if not damaging else 10.0

    # Default low value
    return 5.0

def _choose_best_switch_with_score(
    current_mon: Mon,
    target_mon: Mon,
    switch_options: List[int],
    battle_state: Any,
    field_effects: Any,
    switching_user_id: Optional[int] = None,
    last_move_type: Optional[str] = None,
) -> Tuple[Optional[int], float]:
    """Return (best_switch_index, switch_score)."""
    if not switch_options:
        return None, -999.0

    # Determine which user is switching
    if switching_user_id is None:
        # Try to infer from current_mon
        if battle_state._active(battle_state.p1_id) == current_mon:
            switching_user_id = battle_state.p1_id
        elif battle_state._active(battle_state.p2_id) == current_mon:
            switching_user_id = battle_state.p2_id
        else:
            # Fallback: assume P1
            switching_user_id = battle_state.p1_id

    best_switch: Optional[int] = None
    best_score = -999.0
    user_side, target_side = _get_sides_for_user(int(switching_user_id), battle_state)

    target_moves = [str(m) for m in (getattr(target_mon, "moves", None) or []) if m]
    target_move_types: set[str] = set()
    for t_move in target_moves[:4]:
        t_move_data = get_move(t_move) or {}
        t_type = t_move_data.get("type")
        if t_type:
            target_move_types.add(str(t_type))
    if not target_move_types:
        target_move_types = {str(t) for t in (getattr(target_mon, "types", None) or []) if t}

    for switch_idx in switch_options:
        switch_mon = battle_state.team_for(switching_user_id)[switch_idx]
        if not switch_mon or switch_mon.hp <= 0:
            continue

        switch_hp_pct = switch_mon.hp / switch_mon.max_hp if switch_mon.max_hp > 0 else 0.0
        if switch_hp_pct <= 0:
            continue

        # Damage race estimates
        max_incoming_pct, _ = _max_damage_percent(
            target_mon,
            switch_mon,
            target_moves,
            field_effects,
            user_side,
            target_side,
        )
        max_outgoing_pct, _ = _max_damage_percent(
            switch_mon,
            target_mon,
            [str(m) for m in (getattr(switch_mon, "moves", None) or []) if m],
            field_effects,
            target_side,
            user_side,
        )

        # Entry risk from hazards
        hazard_penalty = _hazard_entry_penalty_percent(switch_mon, user_side, field_effects, opponent=target_mon)
        post_entry_hp_pct = switch_hp_pct - (hazard_penalty / 100.0)

        score = 0.0
        score += switch_hp_pct * 18.0
        score += max(0.0, 24.0 - (max_incoming_pct * 0.45))
        score += max_outgoing_pct * 0.28
        score -= hazard_penalty * 0.55

        if max_outgoing_pct >= 100.0:
            score += 16.0
        elif max_outgoing_pct >= 70.0:
            score += 7.0
        elif max_outgoing_pct <= 15.0:
            score -= 3.0

        if max_incoming_pct >= 100.0:
            score -= 18.0
        elif max_incoming_pct >= 70.0:
            score -= 8.0

        # Speed edge matters for revenge kills and tempo
        switch_speed = int(speed_value(switch_mon, user_side, field_effects))
        target_speed = int(speed_value(target_mon, target_side, field_effects))
        if switch_speed > target_speed:
            score += 2.5

        # Predict last move: reward resists/immunities, punish weakness
        if last_move_type:
            try:
                lm_mult, _ = type_multiplier(last_move_type, switch_mon, field_effects=field_effects, user=target_mon)
                lm = float(lm_mult)
                if lm == 0.0:
                    score += 8.0
                elif lm <= 0.5:
                    score += 4.0
                elif lm >= 2.0:
                    score -= 6.0
            except Exception:
                pass

        # Defensive ability synergies
        score += _defensive_ability_switch_bonus(switch_mon, target_move_types)

        # Status / post-entry survivability penalty
        status = str(getattr(switch_mon, "status", "") or "").lower()
        if status in {"tox", "psn"}:
            score -= 4.0
        elif status == "brn":
            score -= 1.5
        elif status == "par":
            score -= 1.0
        if post_entry_hp_pct <= 0.2:
            score -= 8.0

        if score > best_score:
            best_score = score
            best_switch = switch_idx

    return best_switch, best_score


def _choose_best_switch(
    current_mon: Mon,
    target_mon: Mon,
    switch_options: List[int],
    battle_state: Any,
    field_effects: Any,
    switching_user_id: Optional[int] = None,
    last_move_type: Optional[str] = None,
) -> Optional[int]:
    """Compatibility wrapper: return only the best switch index."""
    best_switch, _ = _choose_best_switch_with_score(
        current_mon=current_mon,
        target_mon=target_mon,
        switch_options=switch_options,
        battle_state=battle_state,
        field_effects=field_effects,
        switching_user_id=switching_user_id,
        last_move_type=last_move_type,
    )
    return best_switch


def _score_switch(
    ai_user_id: int,
    battle_state: Any,
    field_effects: Any
) -> float:
    """
    Score switching. Returns score (positive = good to switch, negative = bad).
    Based on Run and Bun switch AI logic.
    """
    ai_mon = battle_state._active(ai_user_id)
    target_mon = battle_state._opp_active(ai_user_id)
    
    # Check conditions for switching
    # 1. AI must only be able to use ineffective moves (score <= -5)
    # This is checked in choose_ai_action
    
    # 2. Must have a mon that is either:
    #    - Faster than target and not OHKO'd
    #    - Slower than target and not 2HKO'd
    switch_options = battle_state.switch_options(ai_user_id)
    if not switch_options:
        return -20.0  # No switch options
    
    target_speed = getattr(target_mon, 'stats', {}).get('spe', 0) or 0
    
    viable_switch = False
    for switch_idx in switch_options:
        switch_mon = battle_state.team_for(ai_user_id)[switch_idx]
        if not switch_mon or switch_mon.hp <= 0:
            continue
        
        switch_speed = getattr(switch_mon, 'stats', {}).get('spe', 0) or 0
        
        # Check if faster and not OHKO'd
        if switch_speed > target_speed:
            try:
                target_moves = target_mon.moves or []
                can_ohko = False
                for t_move in target_moves[:4]:
                    try:
                        t_dmg, _, _ = damage(target_mon, switch_mon, t_move, field_effects, None, None)
                        if t_dmg >= switch_mon.hp:
                            can_ohko = True
                            break
                    except Exception:
                        continue
                
                if not can_ohko:
                    viable_switch = True
                    break
            except Exception:
                pass
        
        # Check if slower and not 2HKO'd
        else:
            try:
                target_moves = target_mon.moves or []
                can_2hko = False
                for t_move in target_moves[:4]:
                    try:
                        t_dmg, _, _ = damage(target_mon, switch_mon, t_move, field_effects, None, None)
                        if t_dmg >= switch_mon.max_hp / 2:
                            can_2hko = True
                            break
                    except Exception:
                        continue
                
                if not can_2hko:
                    viable_switch = True
                    break
            except Exception:
                pass
    
    # 3. AI mon must not be below 50% health
    hp_percent = ai_mon.hp / ai_mon.max_hp if ai_mon.max_hp > 0 else 1.0
    if hp_percent < 0.5:
        return -20.0  # Don't switch if already low
    
    if viable_switch:
        return 0.0  # Viable to switch
    else:
        return -20.0  # No viable switch


# ==================== ADDITIONAL AI IMPROVEMENTS ====================

def _team_preview_bonus(
    user: Mon,
    target: Mon,
    move_name: str,
    move_lower: str,
    move_data: Dict[str, Any],
    battle_state: Any,
    field_effects: Any
) -> float:
    """1. Team Preview Analysis - Analyze opponent team and plan accordingly"""
    bonus = 0.0
    
    try:
        # Get battle ID for caching analysis
        battle_id = id(battle_state) if battle_state else 0
        
        if battle_id not in _battle_analysis:
            _battle_analysis[battle_id] = {
                'opponent_team_analyzed': False,
                'opponent_types': set(),
                'opponent_weaknesses': {},
                'opponent_resistances': {},
                'threats_identified': [],
                'revealed_pokemon': set()
            }
        
        analysis = _battle_analysis[battle_id]
        
        # Analyze opponent's team on first turn
        current_turn = getattr(battle_state, 'turn', 1)
        if current_turn == 1 and not analysis['opponent_team_analyzed']:
            try:
                ai_user_id = battle_state.p1_id if user == battle_state._active(battle_state.p1_id) else battle_state.p2_id
                opp_user_id = battle_state.p2_id if ai_user_id == battle_state.p1_id else battle_state.p1_id
                opp_team = battle_state.team_for(opp_user_id)
                
                # Collect all opponent types
                for opp_mon in opp_team:
                    if opp_mon and opp_mon.hp > 0:
                        opp_types = opp_mon.types or []
                        for o_type in opp_types:
                            analysis['opponent_types'].add(o_type.title())
                
                analysis['opponent_team_analyzed'] = True
            except Exception:
                pass
        
        # Track revealed Pokemon
        if target.species not in analysis['revealed_pokemon']:
            analysis['revealed_pokemon'].add(target.species)
            # First time seeing this Pokemon - adjust strategy
            bonus += 0.3
        
        # Prefer moves that hit opponent's common weaknesses
        move_type = move_data.get("type", "Normal")
        if move_type and analysis['opponent_types']:
            # Check if move type is super effective against common opponent types
            for opp_type in analysis['opponent_types']:
                try:
                    type_mult, _ = type_multiplier(move_type, target, field_effects=field_effects, user=user)
                    if type_mult >= 2.0:
                        bonus += 0.5  # Good type coverage
                except Exception:
                    pass
    except Exception:
        pass
    
    return bonus


def _move_prediction_bonus(
    user: Mon,
    target: Mon,
    move_name: str,
    move_lower: str,
    move_data: Dict[str, Any],
    battle_state: Any,
    field_effects: Any,
    user_side: Any,
    target_side: Any
) -> float:
    """2. Move Prediction - Predict opponent moves and counter"""
    bonus = 0.0
    
    try:
        target_moves = target.moves or []
        target_hp_percent = target.hp / target.max_hp if target.max_hp > 0 else 1.0
        target_last_move = getattr(target, 'last_move_used', None)
        
        # Predict opponent's likely move based on situation
        predicted_opponent_move = None
        
        # If opponent is low HP, they might switch or use recovery
        if target_hp_percent < 0.3:
            # They might switch - use Pursuit or high-damage move
            if move_lower == "pursuit":
                bonus += 1.5
            if move_data.get("power", 0) >= 100:
                bonus += 0.5
        
        # If opponent just used a setup move, they'll likely attack next
        if target_last_move:
            setup_moves = ["swords-dance", "dragon-dance", "calm-mind", "nasty-plot", "bulk-up", "quiver-dance"]
            if target_last_move.lower() in setup_moves:
                # They'll attack - use priority or phazing
                move_priority = move_data.get("priority", 0) or 0
                if move_priority > 0:
                    bonus += 1.0
                if move_lower in ["roar", "whirlwind", "haze"]:
                    bonus += 1.5
        
        # If opponent is statused, they might try to cure it
        if target.status:
            # They might switch or use Heal Bell - punish with Pursuit or high damage
            if move_lower == "pursuit":
                bonus += 1.0
    except Exception:
        pass
    
    return bonus


def _sacrifice_play_bonus(
    user: Mon,
    target: Mon,
    move_name: str,
    move_lower: str,
    move_data: Dict[str, Any],
    battle_state: Any,
    field_effects: Any
) -> float:
    """3. Sacrifice Plays - When to sacrifice Pokemon strategically"""
    bonus = 0.0
    
    try:
        ai_user_id = battle_state.p1_id if user == battle_state._active(battle_state.p1_id) else battle_state.p2_id
        opp_user_id = battle_state.p2_id if ai_user_id == battle_state.p1_id else battle_state.p1_id
        
        ai_team = battle_state.team_for(ai_user_id)
        opp_team = battle_state.team_for(opp_user_id)
        
        ai_alive = sum(1 for m in ai_team if m and m.hp > 0)
        opp_alive = sum(1 for m in opp_team if m and m.hp > 0)
        
        user_hp_percent = user.hp / user.max_hp if user.max_hp > 0 else 1.0
        
        # Sacrifice if we're behind and this can help
        if ai_alive < opp_alive and user_hp_percent < 0.5:
            # Explosion/Self-Destruct to take out opponent
            if move_lower in ["explosion", "self-destruct"]:
                try:
                    dmg, _, _ = damage(user, target, move_name, field_effects, None, None)
                    if dmg >= target.hp:
                        bonus += 2.0  # Worth sacrificing to KO
                except Exception:
                    pass
            
            # Memento to weaken opponent for next Pokemon
            if move_lower == "memento":
                bonus += 1.5
        
        # Sacrifice to set hazards if we have good Pokemon left
        if ai_alive >= 2 and user_hp_percent < 0.3:
            if move_lower in ["stealth-rock", "spikes", "sticky-web"]:
                bonus += 1.0  # Set hazards before fainting
    except Exception:
        pass
    
    return bonus


def _momentum_tracking_bonus(
    user: Mon,
    target: Mon,
    move_name: str,
    move_lower: str,
    move_data: Dict[str, Any],
    battle_state: Any,
    field_effects: Any
) -> float:
    """4. Momentum Tracking - Track battle momentum and adjust"""
    bonus = 0.0
    
    try:
        battle_id = id(battle_state) if battle_state else 0
        
        if battle_id not in _battle_analysis:
            _battle_analysis[battle_id] = {}
        
        analysis = _battle_analysis[battle_id]
        
        if 'momentum' not in analysis:
            analysis['momentum'] = 0  # 0 = neutral, positive = winning, negative = losing
            analysis['last_turn_result'] = 'neutral'
        
        # Update momentum based on current state
        ai_user_id = battle_state.p1_id if user == battle_state._active(battle_state.p1_id) else battle_state.p2_id
        opp_user_id = battle_state.p2_id if ai_user_id == battle_state.p1_id else battle_state.p1_id
        
        ai_team = battle_state.team_for(ai_user_id)
        opp_team = battle_state.team_for(opp_user_id)
        
        ai_alive = sum(1 for m in ai_team if m and m.hp > 0)
        opp_alive = sum(1 for m in opp_team if m and m.hp > 0)
        
        # Calculate momentum
        if ai_alive > opp_alive:
            analysis['momentum'] = min(analysis['momentum'] + 1, 5)  # Winning
        elif ai_alive < opp_alive:
            analysis['momentum'] = max(analysis['momentum'] - 1, -5)  # Losing
        else:
            analysis['momentum'] = analysis['momentum'] * 0.9  # Decay towards neutral
        
        # Adjust strategy based on momentum
        if analysis['momentum'] < -2:  # Losing badly
            # Play more aggressively
            if move_data.get("power", 0) >= 100:
                bonus += 1.0
            if move_lower in ["explosion", "self-destruct"]:
                bonus += 0.5
        elif analysis['momentum'] > 2:  # Winning
            # Play more conservatively
            if move_lower in ["explosion", "self-destruct", "memento"]:
                bonus -= 1.0
    except Exception:
        pass
    
    return bonus


def _type_chart_mastery_bonus(
    user: Mon,
    target: Mon,
    move_name: str,
    move_lower: str,
    move_data: Dict[str, Any],
    battle_state: Any,
    field_effects: Any
) -> float:
    """5. Type Chart Mastery - Deep type matchup analysis"""
    bonus = 0.0
    
    try:
        # Analyze type matchups across teams
        ai_user_id = battle_state.p1_id if user == battle_state._active(battle_state.p1_id) else battle_state.p2_id
        opp_user_id = battle_state.p2_id if ai_user_id == battle_state.p1_id else battle_state.p1_id
        
        ai_team = battle_state.team_for(ai_user_id)
        opp_team = battle_state.team_for(opp_user_id)
        
        # Find type weaknesses in opponent's team
        move_type = move_data.get("type", "Normal")
        team_weakness_count = 0
        
        for opp_mon in opp_team:
            if opp_mon and opp_mon.hp > 0:
                try:
                    type_mult, _ = type_multiplier(move_type, opp_mon, field_effects=field_effects, user=user)
                    if type_mult >= 2.0:
                        team_weakness_count += 1
                except Exception:
                    pass
        
        # If move hits multiple opponent Pokemon super-effectively, it's valuable
        if team_weakness_count >= 2:
            bonus += 1.0
        elif team_weakness_count >= 1:
            bonus += 0.5
    except Exception:
        pass
    
    return bonus


def _speed_tier_bonus(
    user: Mon,
    target: Mon,
    move_name: str,
    move_lower: str,
    move_data: Dict[str, Any],
    battle_state: Any,
    field_effects: Any
) -> float:
    """6. Speed Tier Awareness - Know important speed benchmarks"""
    bonus = 0.0
    
    try:
        user_speed = getattr(user, 'stats', {}).get('spe', 0) or 0
        target_speed = getattr(target, 'stats', {}).get('spe', 0) or 0
        
        # Important speed benchmarks (approximate)
        speed_tiers = [100, 110, 120, 130, 140, 150]
        
        # If we're close to a speed tier, prefer speed-boosting moves
        for tier in speed_tiers:
            if user_speed < tier and target_speed >= tier:
                # Opponent is in higher tier - speed control is important
                if move_lower in ["agility", "rock-polish", "thunder-wave", "stun-spore"]:
                    bonus += 1.0
                break
        
        # If we're in a higher tier, capitalize on it
        if user_speed > target_speed:
            # Prefer high-damage moves to take advantage of speed
            if move_data.get("power", 0) >= 80:
                bonus += 0.5
    except Exception:
        pass
    
    return bonus


def _set_scouting_bonus(
    user: Mon,
    target: Mon,
    move_name: str,
    move_lower: str,
    move_data: Dict[str, Any],
    battle_state: Any,
    field_effects: Any
) -> float:
    """7. Set Scouting - Identify opponent set/EVs from damage"""
    bonus = 0.0
    
    try:
        battle_id = id(battle_state) if battle_state else 0
        
        if battle_id not in _battle_analysis:
            _battle_analysis[battle_id] = {}
        
        analysis = _battle_analysis[battle_id]
        
        if 'scouted_sets' not in analysis:
            analysis['scouted_sets'] = {}
        
        # Ensure target_key is a string (hashable)
        target_key = str(getattr(target, 'species', 'unknown'))
        
        # Track damage dealt/taken to identify set
        if target_key not in analysis['scouted_sets']:
            analysis['scouted_sets'][target_key] = {
                'damage_dealt': [],
                'damage_taken': [],
                'speed_comparison': None,
                'estimated_set': None
            }
        
        scout_data = analysis['scouted_sets'][target_key]
        
        # Use scouting info to adjust strategy
        if scout_data['estimated_set']:
            # We've identified the set - adjust accordingly
            if scout_data['estimated_set'] == 'physical':
                # Prefer physical walls
                if move_lower in ["reflect", "iron-defense"]:
                    bonus += 0.5
            elif scout_data['estimated_set'] == 'special':
                # Prefer special walls
                if move_lower in ["light-screen", "amnesia"]:
                    bonus += 0.5
    except Exception:
        pass
    
    return bonus


def _win_condition_bonus(
    user: Mon,
    target: Mon,
    move_name: str,
    move_lower: str,
    move_data: Dict[str, Any],
    battle_state: Any,
    field_effects: Any,
    user_side: Any,
    target_side: Any
) -> float:
    """8. Win Condition Identification - Identify and play towards win condition"""
    bonus = 0.0
    
    try:
        ai_user_id = battle_state.p1_id if user == battle_state._active(battle_state.p1_id) else battle_state.p2_id
        opp_user_id = battle_state.p2_id if ai_user_id == battle_state.p1_id else battle_state.p1_id
        
        ai_team = battle_state.team_for(ai_user_id)
        opp_team = battle_state.team_for(opp_user_id)
        
        ai_alive = sum(1 for m in ai_team if m and m.hp > 0)
        opp_alive = sum(1 for m in opp_team if m and m.hp > 0)
        
        # Identify win condition
        # Check if we have a setup sweeper
        user_stages = getattr(user, 'stages', {}) or {}
        has_setup = any((user_stages.get(stat, 0) or 0) > 0 for stat in ['atk', 'spa', 'spe'])
        
        if has_setup and ai_alive >= 2:
            # Our win condition is to sweep - protect the setup
            if move_data.get("power", 0) > 0:
                bonus += 1.0  # Attack to sweep
            if move_lower in ["protect", "substitute"]:
                bonus += 0.5  # Protect setup
        
        # Check if we have hazards - win condition might be hazard chip
        if target_side:
            has_hazards = (
                getattr(target_side, 'stealth_rock', False) or
                getattr(target_side, 'spikes', 0) > 0 or
                getattr(target_side, 'toxic_spikes', 0) > 0
            )
            
            if has_hazards and opp_alive <= 2:
                # Hazards can win - prefer phazing
                if move_lower in ["roar", "whirlwind", "dragon-tail"]:
                    bonus += 1.5
    except Exception:
        pass
    
    return bonus


def _switch_prediction_bonus(
    user: Mon,
    target: Mon,
    move_name: str,
    move_lower: str,
    move_data: Dict[str, Any],
    battle_state: Any,
    field_effects: Any
) -> float:
    """9. Switch Prediction - Predict opponent switches"""
    bonus = 0.0
    
    try:
        target_hp_percent = target.hp / target.max_hp if target.max_hp > 0 else 1.0
        target_types = target.types or []
        user_types = user.types or []
        
        # Predict switch likelihood
        switch_likely = False
        
        # Low HP = likely to switch
        if target_hp_percent < 0.3:
            switch_likely = True
        
        # Bad type matchup = likely to switch
        for u_type in user_types:
            for t_type in target_types:
                try:
                    type_mult, _ = type_multiplier(u_type, target, field_effects=field_effects, user=user)
                    if type_mult >= 2.0:
                        switch_likely = True
                        break
                except Exception:
                    pass
            if switch_likely:
                break
        
        if switch_likely:
            # Punish predicted switch
            if move_lower == "pursuit":
                bonus += 2.0  # Perfect for predicted switch
            if move_lower in ["stealth-rock", "spikes"]:
                bonus += 1.0  # Set hazards before they switch
            if move_data.get("power", 0) >= 100:
                bonus += 0.5  # High damage to finish
    except Exception:
        pass
    
    return bonus


def _status_synergy_bonus(
    user: Mon,
    target: Mon,
    move_name: str,
    move_lower: str,
    move_data: Dict[str, Any],
    battle_state: Any,
    field_effects: Any
) -> float:
    """10. Status Synergy - Use status moves that combo well"""
    bonus = 0.0
    
    try:
        # Toxic + Protect stalling
        if target.status in ["tox", "psn"]:
            if move_lower in ["protect", "detect", "substitute"]:
                bonus += 1.0  # Stall for toxic damage
        
        # Paralysis + speed control
        if target.status == "par":
            # They're slower now - capitalize
            if move_data.get("power", 0) > 0:
                bonus += 0.5
        
        # Burn + physical wall
        if target.status == "brn":
            # Physical moves are weakened - prefer special
            if move_data.get("category", "").lower() == "special" and move_data.get("power", 0) > 0:
                bonus += 0.5
        
        # If we have Hex, status is more valuable
        user_moves = user.moves or []
        if "hex" in [m.lower() for m in user_moves]:
            if move_lower in ["toxic", "will-o-wisp", "thunder-wave"]:
                bonus += 1.0  # Status enables Hex
    except Exception:
        pass
    
    return bonus


def _hazard_removal_timing_bonus(
    user: Mon,
    target: Mon,
    move_name: str,
    move_lower: str,
    move_data: Dict[str, Any],
    battle_state: Any,
    field_effects: Any,
    user_side: Any,
    target_side: Any
) -> float:
    """11. Hazard Removal Timing - Better timing for Defog/Rapid Spin"""
    bonus = 0.0
    
    try:
        if move_lower in ["defog", "rapid-spin"]:
            # Check if we have hazards on opponent's side
            opp_has_hazards = False
            if target_side:
                opp_has_hazards = (
                    getattr(target_side, 'stealth_rock', False) or
                    getattr(target_side, 'spikes', 0) > 0 or
                    getattr(target_side, 'toxic_spikes', 0) > 0
                )
            
            # Only remove if we don't have hazards (Defog removes both sides)
            if move_lower == "defog":
                if user_side:
                    we_have_hazards = (
                        getattr(user_side, 'stealth_rock', False) or
                        getattr(user_side, 'spikes', 0) > 0
                    )
                    if we_have_hazards:
                        bonus -= 2.0  # Don't remove our own hazards
            
            # Prefer removal when switching in important Pokemon
            ai_user_id = battle_state.p1_id if user == battle_state._active(battle_state.p1_id) else battle_state.p2_id
            ai_team = battle_state.team_for(ai_user_id)
            
            # Check if we have Pokemon that are weak to hazards
            hazard_weak_pokemon = 0
            for team_mon in ai_team:
                if team_mon and team_mon.hp > 0:
                    team_types = team_mon.types or []
                    # Rock types take more from Stealth Rock
                    if "Rock" in team_types or "Ice" in team_types:
                        hazard_weak_pokemon += 1
            
            if hazard_weak_pokemon > 0 and opp_has_hazards:
                bonus += 1.5  # Important to remove
    except Exception:
        pass
    
    return bonus


def _losing_position_bonus(
    user: Mon,
    target: Mon,
    move_name: str,
    move_lower: str,
    move_data: Dict[str, Any],
    battle_state: Any,
    field_effects: Any
) -> float:
    """12. Losing Position Recovery - Better plays when behind"""
    bonus = 0.0
    
    try:
        ai_user_id = battle_state.p1_id if user == battle_state._active(battle_state.p1_id) else battle_state.p2_id
        opp_user_id = battle_state.p2_id if ai_user_id == battle_state.p1_id else battle_state.p1_id
        
        ai_team = battle_state.team_for(ai_user_id)
        opp_team = battle_state.team_for(opp_user_id)
        
        ai_alive = sum(1 for m in ai_team if m and m.hp > 0)
        opp_alive = sum(1 for m in opp_team if m and m.hp > 0)
        
        # If we're significantly behind, make high-risk plays
        if ai_alive < opp_alive - 1:  # Behind by 2+ Pokemon
            # High-risk, high-reward moves
            if move_lower in ["explosion", "self-destruct"]:
                try:
                    dmg, _, _ = damage(user, target, move_name, field_effects, None, None)
                    if dmg >= target.hp:
                        bonus += 2.0  # Worth the risk
                except Exception:
                    pass
            
            # Setup moves become more valuable (need to catch up)
            if move_lower in ["swords-dance", "dragon-dance", "calm-mind", "nasty-plot"]:
                bonus += 1.0
    except Exception:
        pass
    
    return bonus


def _lead_matchup_bonus(
    user: Mon,
    target: Mon,
    move_name: str,
    move_lower: str,
    move_data: Dict[str, Any],
    battle_state: Any,
    field_effects: Any
) -> float:
    """13. Lead Matchup Analysis - Better lead selection and play"""
    bonus = 0.0
    
    try:
        current_turn = getattr(battle_state, 'turn', 1)
        
        # Early game (turns 1-3) - lead strategy
        if current_turn <= 3:
            # Prefer setting hazards early
            if move_lower in ["stealth-rock", "spikes", "sticky-web"]:
                bonus += 1.0
            
            # Prefer scouting moves (U-turn, Volt Switch)
            if move_lower in ["u-turn", "volt-switch", "flip-turn"]:
                bonus += 0.5
            
            # Avoid risky setup early
            if move_lower in ["belly-drum", "shell-smash"]:
                bonus -= 1.0
    except Exception:
        pass
    
    return bonus


def _mid_game_transition_bonus(
    user: Mon,
    target: Mon,
    move_name: str,
    move_lower: str,
    move_data: Dict[str, Any],
    battle_state: Any,
    field_effects: Any
) -> float:
    """14. Mid-Game Transitions - Better phase transitions"""
    bonus = 0.0
    
    try:
        current_turn = getattr(battle_state, 'turn', 1)
        ai_user_id = battle_state.p1_id if user == battle_state._active(battle_state.p1_id) else battle_state.p2_id
        opp_user_id = battle_state.p2_id if ai_user_id == battle_state.p1_id else battle_state.p1_id
        
        ai_team = battle_state.team_for(ai_user_id)
        opp_team = battle_state.team_for(opp_user_id)
        
        ai_alive = sum(1 for m in ai_team if m and m.hp > 0)
        opp_alive = sum(1 for m in opp_team if m and m.hp > 0)
        
        # Early game (turns 1-5)
        if current_turn <= 5:
            # Focus on positioning and hazards
            if move_lower in ["stealth-rock", "spikes", "u-turn", "volt-switch"]:
                bonus += 0.5
        
        # Mid game (turns 6-15)
        elif current_turn <= 15:
            # Start setting up or breaking walls
            if move_lower in ["swords-dance", "dragon-dance", "calm-mind"]:
                bonus += 0.5
            if move_lower in ["close-combat", "head-smash"]:  # Wall breakers
                bonus += 0.5
        
        # Late game (turn 16+)
        else:
            # Focus on winning - prioritize KOs
            if move_data.get("power", 0) > 0:
                try:
                    dmg, _, _ = damage(user, target, move_name, field_effects, None, None)
                    if dmg >= target.hp:
                        bonus += 2.0  # KO moves are critical
                except Exception:
                    pass
    except Exception:
        pass
    
    return bonus


def _conditional_move_bonus(
    user: Mon,
    target: Mon,
    move_name: str,
    move_lower: str,
    move_data: Dict[str, Any],
    battle_state: Any,
    field_effects: Any
) -> float:
    """15. Conditional Move Usage - Better Sleep Talk/Metronome usage"""
    bonus = 0.0
    
    try:
        # Sleep Talk - use when asleep
        if move_lower == "sleep-talk":
            if user.status == "slp":
                bonus += 3.0  # Very valuable when asleep
            else:
                bonus = -20.0  # Useless when not asleep
        
        # Snore - use when asleep
        if move_lower == "snore":
            if user.status == "slp":
                bonus += 2.0
            else:
                bonus -= 2.0
        
        # Metronome - risky but sometimes needed
        if move_lower == "metronome":
            # Only use if we're out of good options
            user_moves = user.moves or []
            good_moves = 0
            for m in user_moves:
                m_data = get_move(m)
                if m_data:
                    m_power = m_data.get("power", 0) or 0
                    if m_power > 0:
                        good_moves += 1
            
            if good_moves <= 1:
                bonus += 1.0  # Desperate situation
            else:
                bonus -= 2.0  # Too risky
    except Exception:
        pass
    
    return bonus


def _team_synergy_bonus(
    user: Mon,
    target: Mon,
    move_name: str,
    move_lower: str,
    move_data: Dict[str, Any],
    battle_state: Any,
    field_effects: Any
) -> float:
    """16. Team Synergy - Consider how Pokemon work together"""
    bonus = 0.0
    
    try:
        ai_user_id = battle_state.p1_id if user == battle_state._active(battle_state.p1_id) else battle_state.p2_id
        ai_team = battle_state.team_for(ai_user_id)
        
        # Weather team synergy
        weather = getattr(field_effects, 'weather', None) if field_effects else None
        
        if weather:
            # Check if team benefits from weather
            weather_benefit_count = 0
            for team_mon in ai_team:
                if team_mon and team_mon.hp > 0:
                    team_types = team_mon.types or []
                    team_ability = normalize_ability_name(team_mon.ability or "")
                    
                    if weather == "sun" and ("Fire" in team_types or team_ability in ["solar-power", "chlorophyll"]):
                        weather_benefit_count += 1
                    elif weather == "rain" and ("Water" in team_types or team_ability in ["swift-swim", "hydration"]):
                        weather_benefit_count += 1
            
            if weather_benefit_count >= 2:
                # Team benefits - maintain weather
                if move_lower in ["sunny-day", "rain-dance"]:
                    bonus += 1.0
        
        # Check for team combos (e.g., Baton Pass chains)
        # This would require tracking previous moves
    except Exception:
        pass
    
    return bonus


def _meta_knowledge_bonus(
    user: Mon,
    target: Mon,
    move_name: str,
    move_lower: str,
    move_data: Dict[str, Any],
    battle_state: Any,
    field_effects: Any
) -> float:
    """17. Meta Knowledge - Common sets and patterns"""
    bonus = 0.0
    
    try:
        # Common Pokemon sets and their typical moves
        common_sets = {
            "garchomp": ["earthquake", "dragon-claw", "stone-edge", "swords-dance"],
            "ferrothorn": ["gyro-ball", "power-whip", "leech-seed", "stealth-rock"],
            "landorus-therian": ["earthquake", "u-turn", "stone-edge", "stealth-rock"],
            "heatran": ["lava-plume", "earth-power", "stealth-rock", "toxic"],
            "rotom-wash": ["hydro-pump", "volt-switch", "will-o-wisp", "pain-split"]
        }
        
        target_species_lower = target.species.lower()
        
        # If opponent matches a common set, predict their moves
        if target_species_lower in common_sets:
            common_moves = common_sets[target_species_lower]
            
            # Counter common moves
            if "stealth-rock" in common_moves:
                # They might set rocks - use Magic Bounce or Taunt
                user_ability = normalize_ability_name(user.ability or "")
                if user_ability == "magic-bounce":
                    bonus += 1.0
                if move_lower == "taunt":
                    bonus += 0.5
            
            # Predict their likely moves and counter
            if "swords-dance" in common_moves:
                # They might setup - use phazing
                if move_lower in ["roar", "whirlwind", "haze"]:
                    bonus += 1.0
    except Exception:
        pass
    
    return bonus


def _turn_order_prediction_bonus(
    user: Mon,
    target: Mon,
    move_name: str,
    move_lower: str,
    move_data: Dict[str, Any],
    battle_state: Any,
    field_effects: Any,
    user_side: Any,
    target_side: Any
) -> float:
    """18. Turn Order Prediction - Predict speed ties and priority"""
    bonus = 0.0
    
    try:
        user_speed = getattr(user, 'stats', {}).get('spe', 0) or 0
        target_speed = getattr(target, 'stats', {}).get('spe', 0) or 0
        
        move_priority = move_data.get("priority", 0) or 0
        target_moves = target.moves or []
        
        # Check if opponent has priority
        opponent_has_priority = False
        for t_move in target_moves[:4]:
            t_move_data = get_move(t_move)
            if t_move_data:
                t_priority = t_move_data.get("priority", 0) or 0
                if t_priority > 0:
                    opponent_has_priority = True
                    break
        
        # Speed tie situation
        if abs(user_speed - target_speed) <= 5:  # Very close speeds
            # In speed ties, priority is very valuable
            if move_priority > 0:
                bonus += 1.5
            # Or use moves that don't depend on speed
            if move_lower in ["protect", "substitute"]:
                bonus += 0.5
        
        # If opponent has priority and we're slower, we need priority too
        if opponent_has_priority and user_speed < target_speed:
            if move_priority > 0:
                bonus += 2.0  # Critical to have priority
    except Exception:
        pass
    
    return bonus


def _clutch_play_bonus(
    user: Mon,
    target: Mon,
    move_name: str,
    move_lower: str,
    move_data: Dict[str, Any],
    battle_state: Any,
    field_effects: Any,
    user_side: Any,
    target_side: Any
) -> float:
    """19. Clutch Plays - High-risk high-reward when needed"""
    bonus = 0.0
    
    try:
        ai_user_id = battle_state.p1_id if user == battle_state._active(battle_state.p1_id) else battle_state.p2_id
        opp_user_id = battle_state.p2_id if ai_user_id == battle_state.p1_id else battle_state.p1_id
        
        ai_team = battle_state.team_for(ai_user_id)
        opp_team = battle_state.team_for(opp_user_id)
        
        ai_alive = sum(1 for m in ai_team if m and m.hp > 0)
        opp_alive = sum(1 for m in opp_team if m and m.hp > 0)
        
        # Critical situation - need clutch play
        is_clutch = False
        
        # Last Pokemon vs last Pokemon
        if ai_alive == 1 and opp_alive == 1:
            is_clutch = True
        
        # Behind and this move can turn the tide
        if ai_alive < opp_alive:
            try:
                if move_data.get("power", 0) > 0:
                    dmg, _, _ = damage(user, target, move_name, field_effects, target_side, user_side)
                    if dmg >= target.hp:
                        is_clutch = True
            except Exception:
                pass
        
        if is_clutch:
            # High-risk moves become more acceptable
            if move_lower in ["explosion", "self-destruct"]:
                try:
                    dmg, _, _ = damage(user, target, move_name, field_effects, target_side, user_side)
                    if dmg >= target.hp:
                        bonus += 3.0  # Worth the risk to win
                except Exception:
                    pass
            
            # Low accuracy high power moves
            move_accuracy = move_data.get("accuracy", 100) or 100
            if move_accuracy < 90 and move_data.get("power", 0) >= 100:
                try:
                    dmg, _, _ = damage(user, target, move_name, field_effects, target_side, user_side)
                    if dmg >= target.hp:
                        bonus += 2.0  # Risk it for the win
                except Exception:
                    pass
    except Exception:
        pass
    
    return bonus


def _damage_range_bonus(
    user: Mon,
    target: Mon,
    move_name: str,
    move_lower: str,
    move_data: Dict[str, Any],
    battle_state: Any,
    field_effects: Any,
    user_side: Any,
    target_side: Any
) -> float:
    """20. Damage Range Calculation - Calculate min/max damage ranges"""
    bonus = 0.0
    
    try:
        if move_data.get("power", 0) > 0:
            # Calculate damage multiple times to get range
            damage_values = []
            for _ in range(5):  # 5 samples
                try:
                    dmg, _, _ = damage(user, target, move_name, field_effects, target_side, user_side, is_moving_last=False)
                    damage_values.append(dmg)
                except Exception:
                    continue
            
            if damage_values:
                min_dmg = min(damage_values)
                max_dmg = max(damage_values)
                avg_dmg = sum(damage_values) / len(damage_values)
                
                # If damage range is consistent (reliable), prefer it
                damage_range = max_dmg - min_dmg
                if damage_range < avg_dmg * 0.2:  # Less than 20% variance
                    bonus += 0.5  # Reliable damage
                
                # If max damage can KO, it's valuable
                if max_dmg >= target.hp:
                    bonus += 1.5
                # If average damage can KO, also valuable
                elif avg_dmg >= target.hp:
                    bonus += 1.0
                # If min damage can KO, very reliable
                elif min_dmg >= target.hp:
                    bonus += 2.0
                
                # Consider crit chance
                move_effect = get_move_secondary_effect(move_lower)
                has_high_crit = move_effect and move_effect.get("high_crit_chance")
                user_ability = normalize_ability_name(user.ability or "")
                
                if has_high_crit or user_ability in ["super-luck", "sniper"]:
                    # Crit damage is higher - factor that in
                    # Rough estimate: crit does 1.5x-2x damage
                    crit_max = max_dmg * 2.0
                    if crit_max >= target.hp:
                        bonus += 0.5  # Crit can KO
    except Exception:
        pass
    
    return bonus


async def generate_bot_team(fmt_key: str, generation: int) -> List[Mon]:
    """
    Generate a competitive bot team for AI battles.
    Creates balanced teams with good type coverage, competitive movesets, and proper EVs/natures.
    Uses the local database instead of PokeAPI.
    """
    from .engine import build_mon, Mon, _normalize_stats_dict, _parse_types, _parse_abilities
    from lib.db import get_pokedex_by_name, connect
    from .db_adapter import get_form_overrides
    from .formats import get_format
    from lib.legality import legal_moves
    import random
    import json
    
    # Helper function to normalize stats to engine format (hp, atk, defn, spa, spd, spe)
    def _normalize_base_stats(stats: dict, default_value: int = 0) -> dict:
        """Convert DB stats into engine format (hp, atk, defn, spa, spd, spe).
        Uses engine's _normalize_stats_dict and ensures all 6 stats are present.
        """
        if not isinstance(stats, dict):
            return {"hp": default_value, "atk": default_value, "defn": default_value, "spa": default_value, "spd": default_value, "spe": default_value}
        normalized = _normalize_stats_dict(stats)
        # Ensure all stats are present (engine format)
        return {
            "hp": normalized.get("hp", default_value),
            "atk": normalized.get("atk", default_value),
            "defn": normalized.get("defn", default_value),
            "spa": normalized.get("spa", default_value),
            "spd": normalized.get("spd", default_value),
            "spe": normalized.get("spe", default_value),
        }
    
    # Get format rules to check for banned Pokémon
    try:
        format_rules = await get_format(fmt_key, generation)
        banned_species = [s.lower() for s in format_rules.rules.get("species_bans", [])]
    except Exception:
        banned_species = []
    
    # Competitive team pools by format (good type coverage and synergy)
    # Format: {species: base_name, form: optional_form_key, moveset: [moves], nature: str, evs: {stat: value}, item: str}
    competitive_teams = {
        "ou": [
            # Balanced OU team
            {"species": "garchomp", "moveset": ["Earthquake", "Dragon Claw", "Stone Edge", "Swords Dance"], 
             "nature": "jolly", "evs": {"attack": 252, "speed": 252, "hp": 4}, "item": "Rocky Helmet"},
            {"species": "gengar", "moveset": ["Shadow Ball", "Sludge Bomb", "Thunderbolt", "Focus Blast"], 
             "nature": "timid", "evs": {"special_attack": 252, "speed": 252, "hp": 4}, "item": "Life Orb"},
            {"species": "ferrothorn", "moveset": ["Power Whip", "Gyro Ball", "Stealth Rock", "Leech Seed"], 
             "nature": "relaxed", "evs": {"hp": 252, "defense": 88, "special_defense": 168}, "item": "Leftovers"},
            {"species": "rotom", "form": "wash", "moveset": ["Volt Switch", "Hydro Pump", "Will-O-Wisp", "Pain Split"], 
             "nature": "bold", "evs": {"hp": 248, "defense": 216, "speed": 44}, "item": "Leftovers"},
            {"species": "heatran", "moveset": ["Lava Plume", "Earth Power", "Stealth Rock", "Toxic"], 
             "nature": "calm", "evs": {"hp": 252, "special_defense": 252, "speed": 4}, "item": "Leftovers"},
            {"species": "landorus", "form": "therian", "moveset": ["Earthquake", "U-turn", "Stealth Rock", "Stone Edge"], 
             "nature": "jolly", "evs": {"attack": 252, "speed": 252, "hp": 4}, "item": "Choice Scarf"},
        ],
        "ubers": [
            # Ubers team
            {"species": "groudon", "moveset": ["Precipice Blades", "Fire Punch", "Stone Edge", "Swords Dance"], 
             "nature": "adamant", "evs": {"attack": 252, "speed": 252, "hp": 4}, "item": "Red Orb"},
            {"species": "kyogre", "moveset": ["Origin Pulse", "Ice Beam", "Thunder", "Calm Mind"], 
             "nature": "modest", "evs": {"special_attack": 252, "speed": 252, "hp": 4}, "item": "Blue Orb"},
            {"species": "rayquaza", "moveset": ["Dragon Ascent", "Earthquake", "Extreme Speed", "Dragon Dance"], 
             "nature": "adamant", "evs": {"attack": 252, "speed": 252, "hp": 4}, "item": None},
            {"species": "arceus", "moveset": ["Judgment", "Earthquake", "Recover", "Calm Mind"], 
             "nature": "timid", "evs": {"special_attack": 252, "speed": 252, "hp": 4}, "item": "Silk Scarf"},
            {"species": "giratina", "form": "origin", "moveset": ["Shadow Ball", "Dragon Pulse", "Aura Sphere", "Defog"], 
             "nature": "modest", "evs": {"special_attack": 252, "speed": 252, "hp": 4}, "item": "Griseous Orb"},
            {"species": "xerneas", "moveset": ["Moonblast", "Thunder", "Focus Blast", "Geomancy"], 
             "nature": "modest", "evs": {"special_attack": 252, "speed": 252, "hp": 4}, "item": "Power Herb"},
        ],
        "testing": [
            # Balanced testing team
            {"species": "garchomp", "moveset": ["Earthquake", "Dragon Claw", "Stone Edge", "Swords Dance"], 
             "nature": "jolly", "evs": {"attack": 252, "speed": 252, "hp": 4}, "item": "Rocky Helmet"},
            {"species": "gengar", "moveset": ["Shadow Ball", "Sludge Bomb", "Thunderbolt", "Focus Blast"], 
             "nature": "timid", "evs": {"special_attack": 252, "speed": 252, "hp": 4}, "item": "Life Orb"},
            {"species": "ferrothorn", "moveset": ["Power Whip", "Gyro Ball", "Stealth Rock", "Leech Seed"], 
             "nature": "relaxed", "evs": {"hp": 252, "defense": 88, "special_defense": 168}, "item": "Leftovers"},
            {"species": "rotom", "form": "wash", "moveset": ["Volt Switch", "Hydro Pump", "Will-O-Wisp", "Pain Split"], 
             "nature": "bold", "evs": {"hp": 248, "defense": 216, "speed": 44}, "item": "Leftovers"},
            {"species": "heatran", "moveset": ["Lava Plume", "Earth Power", "Stealth Rock", "Toxic"], 
             "nature": "calm", "evs": {"hp": 252, "special_defense": 252, "speed": 4}, "item": "Leftovers"},
            {"species": "landorus", "form": "therian", "moveset": ["Earthquake", "U-turn", "Stealth Rock", "Stone Edge"], 
             "nature": "jolly", "evs": {"attack": 252, "speed": 252, "hp": 4}, "item": "Choice Scarf"},
        ],
    }
    
    # Select team pool based on format (fallback to testing)
    team_pool = competitive_teams.get(fmt_key.lower(), competitive_teams["testing"])
    
    # Filter out banned Pokémon
    available_pokemon = [p for p in team_pool if p["species"].lower() not in banned_species]
    
    # If all Pokémon are banned, use fallback
    if not available_pokemon:
        available_pokemon = [
            {"species": "pikachu", "moveset": ["Thunderbolt", "Quick Attack", "Iron Tail", "Thunder"], 
             "nature": "timid", "evs": {"special_attack": 252, "speed": 252, "hp": 4}, "item": "Light Ball"},
        ]
    
    # Select 6 Pokémon (or fewer if not enough available)
    selected_pokemon = random.sample(available_pokemon, min(6, len(available_pokemon)))
    
    team = []
    for pokemon_config in selected_pokemon:
        try:
            species_name = pokemon_config["species"]
            
            # Get form from config if specified
            form_key = pokemon_config.get("form")
            
            # Load from database (not PokeAPI)
            species_entry = await get_pokedex_by_name(species_name)
            if not species_entry:
                print(f"[AI] Species {species_name} not found in database, skipping...")
                continue
            
            species_id = int(species_entry.get("id", 0))
            if not species_id:
                print(f"[AI] Species {species_name} has no ID, skipping...")
                continue
            
            # Parse stats from database
            base_stats_raw = species_entry.get("stats") or {}
            if isinstance(base_stats_raw, str):
                try:
                    base_stats_raw = json.loads(base_stats_raw)
                except Exception:
                    base_stats_raw = {}
            
            # Check for form-specific stats/types/abilities
            form_overrides = None
            if form_key:
                form_overrides = get_form_overrides(species_name, form_key)
                if form_overrides and form_overrides.get("stats"):
                    base_stats_raw = form_overrides["stats"]
            
            # Normalize stats to engine format (hp, atk, defn, spa, spd, spe)
            # For base stats, use 50 as default (reasonable base stat)
            base_stats = _normalize_base_stats(base_stats_raw, default_value=50)
            
            # Parse types
            types_raw = species_entry.get("types") or []
            if isinstance(types_raw, str):
                try:
                    types_raw = json.loads(types_raw)
                except Exception:
                    types_raw = []
            
            # Check for form-specific types
            if form_overrides and form_overrides.get("types"):
                types_raw = form_overrides["types"]
            
            types_tuple = _parse_types(types_raw)
            
            # Parse abilities
            abilities_raw = species_entry.get("abilities") or []
            if isinstance(abilities_raw, str):
                try:
                    abilities_raw = json.loads(abilities_raw)
                except Exception:
                    abilities_raw = []
            
            # Check for form-specific abilities
            if form_overrides and form_overrides.get("abilities"):
                abilities_raw = form_overrides["abilities"]
            
            abilities_list = _parse_abilities(abilities_raw)
            
            # Select ability (prefer non-hidden, but can use hidden)
            ability_name = None
            if abilities_list:
                # Prefer non-hidden abilities
                non_hidden = [a for a in abilities_list if not isinstance(a, dict) or not a.get("is_hidden", False)]
                if non_hidden:
                    ability_name = non_hidden[0] if isinstance(non_hidden[0], str) else non_hidden[0].get("name")
                else:
                    ability_name = abilities_list[0] if isinstance(abilities_list[0], str) else abilities_list[0].get("name")
            
            # Get legal moves for this species
            legal_move_list_raw = await legal_moves(species_id, generation)
            # legal_moves() returns list of dicts, extract move names
            legal_move_list = [str(m.get("name", "")) for m in legal_move_list_raw if m and m.get("name")]
            
            # Use configured moveset, but filter to only legal moves
            # Ensure configured_moves is a list of strings
            configured_moves_raw = pokemon_config.get("moveset", [])
            configured_moves = [str(m) for m in configured_moves_raw if m] if configured_moves_raw else []
            available_moves = [m for m in configured_moves if m in legal_move_list]
            
            # If configured moves aren't available, try to find similar moves
            if not available_moves and legal_move_list:
                # Fallback: select good moves
                available_moves = random.sample(legal_move_list, min(4, len(legal_move_list)))
            elif len(available_moves) < 4 and legal_move_list:
                # Fill remaining slots with legal moves
                remaining = [m for m in legal_move_list if m not in available_moves]
                available_moves.extend(random.sample(remaining, min(4 - len(available_moves), len(remaining))))
            
            if not available_moves:
                available_moves = ["Tackle", "Growl", "Scratch", "Leer"][:4]
            
            # CRITICAL: Ensure all moves are strings (exactly like build_mon expects)
            available_moves = [str(m) for m in available_moves[:4] if m]
            if not available_moves:
                available_moves = ["Tackle"]
            
            # Get EVs and nature from config
            evs_config = pokemon_config.get("evs", {"attack": 252, "speed": 252, "hp": 4})
            # Normalize EVs to engine format (default 0 for missing stats)
            evs = _normalize_base_stats(evs_config, default_value=0)
            nature = pokemon_config.get("nature", "adamant")
            
            # Generate IVs (all 31 for competitive) - ensure all stats present
            ivs = {"hp": 31, "atk": 31, "defn": 31, "spa": 31, "spd": 31, "spe": 31}
            
            # Build dto for build_mon (expects "base", "ivs", "evs" keys)
            # CRITICAL: Ensure moves is exactly like build_mon expects: a list of strings
            # build_mon does: moves=(dto.get("moves") or ["Tackle"])[:4] or ["Tackle"]
            final_moves = available_moves[:4] if available_moves else ["Tackle"]
            # Double-check all moves are strings
            final_moves = [str(m) for m in final_moves if m]
            if not final_moves:
                final_moves = ["Tackle"]
            
            mon_dto = {
                "species": species_entry.get("name") or species_name,
                "types": types_tuple,
                "base": base_stats,  # Base stats in engine format
                "ivs": ivs,
                "evs": evs,
                "nature": nature,
                "ability": ability_name,
                "gender": None,  # Random gender
                "item": pokemon_config.get("item"),
                "moves": final_moves,  # List of strings, exactly like build_mon expects
                "level": 100,
                "hp_now": 100,  # Will be overridden by heal=True
                "is_shiny": False,
                "is_fully_evolved": bool(species_entry.get("is_fully_evolved", True)),
                "weight_kg": float(species_entry.get("weight_kg", 100.0)),
                "friendship": 255,
            }
            
            # Add form if specified
            if form_key:
                mon_dto["form"] = form_key
            
            # Create Mon object
            mon = build_mon(mon_dto, set_level=100, heal=True)
            team.append(mon)
        except Exception as e:
            print(f"[AI] Error generating bot Pokemon {pokemon_config.get('species', 'unknown')}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # Ensure we have at least 1 Pokemon
    if not team:
        # Fallback: create a basic competitive Pokémon
        fallback_configs = [
            {"species": "pikachu", "moveset": ["Thunderbolt", "Quick Attack", "Iron Tail", "Thunder"], 
             "nature": "timid", "evs": {"special_attack": 252, "speed": 252, "hp": 4}, "item": "Light Ball"},
            {"species": "garchomp", "moveset": ["Earthquake", "Dragon Claw", "Stone Edge", "Swords Dance"], 
             "nature": "jolly", "evs": {"attack": 252, "speed": 252, "hp": 4}, "item": None},
            {"species": "gengar", "moveset": ["Shadow Ball", "Sludge Bomb", "Thunderbolt", "Focus Blast"], 
             "nature": "timid", "evs": {"special_attack": 252, "speed": 252, "hp": 4}, "item": None},
        ]
        
        for fallback_config in fallback_configs:
            try:
                species_name = fallback_config["species"]
                
                # Load from database
                species_entry = await get_pokedex_by_name(species_name)
                if not species_entry:
                    continue
                
                species_id = int(species_entry.get("id", 0))
                if not species_id:
                    continue
                
                # Parse stats
                base_stats_raw = species_entry.get("stats") or {}
                if isinstance(base_stats_raw, str):
                    try:
                        base_stats_raw = json.loads(base_stats_raw)
                    except Exception:
                        base_stats_raw = {}
                
                base_stats = _normalize_base_stats(base_stats_raw)
                
                # Parse types
                types_raw = species_entry.get("types") or []
                if isinstance(types_raw, str):
                    try:
                        types_raw = json.loads(types_raw)
                    except Exception:
                        types_raw = []
                types_tuple = _parse_types(types_raw)
                
                # Parse abilities
                abilities_raw = species_entry.get("abilities") or []
                if isinstance(abilities_raw, str):
                    try:
                        abilities_raw = json.loads(abilities_raw)
                    except Exception:
                        abilities_raw = []
                abilities_list = _parse_abilities(abilities_raw)
                
                ability_name = None
                if abilities_list:
                    non_hidden = [a for a in abilities_list if not isinstance(a, dict) or not a.get("is_hidden", False)]
                    if non_hidden:
                        ability_name = non_hidden[0] if isinstance(non_hidden[0], str) else non_hidden[0].get("name")
                    else:
                        ability_name = abilities_list[0] if isinstance(abilities_list[0], str) else abilities_list[0].get("name")
                
                legal_move_list_raw = await legal_moves(species_id, generation)
                # legal_moves() returns list of dicts, extract move names
                legal_move_list = [str(m.get("name", "")) for m in legal_move_list_raw if m and m.get("name")]
                
                # Ensure configured_moves is a list of strings
                configured_moves_raw = fallback_config.get("moveset", [])
                configured_moves = [str(m) for m in configured_moves_raw if m] if configured_moves_raw else []
                available_moves = [m for m in configured_moves if m in legal_move_list]
                
                if not available_moves and legal_move_list:
                    available_moves = random.sample(legal_move_list, min(4, len(legal_move_list)))
                elif len(available_moves) < 4 and legal_move_list:
                    remaining = [m for m in legal_move_list if m not in available_moves]
                    available_moves.extend(random.sample(remaining, min(4 - len(available_moves), len(remaining))))
                
                if not available_moves:
                    available_moves = ["Tackle", "Growl", "Scratch", "Leer"][:4]
                
                # CRITICAL: Ensure all moves are strings (exactly like build_mon expects)
                # build_mon does: moves=(dto.get("moves") or ["Tackle"])[:4] or ["Tackle"]
                final_moves = available_moves[:4] if available_moves else ["Tackle"]
                final_moves = [str(m) for m in final_moves if m]
                if not final_moves:
                    final_moves = ["Tackle"]
                
                evs_config = fallback_config.get("evs", {"attack": 252, "speed": 252, "hp": 4})
                evs = _normalize_base_stats(evs_config, default_value=0)
                nature = fallback_config.get("nature", "adamant")
                ivs = {"hp": 31, "atk": 31, "defn": 31, "spa": 31, "spd": 31, "spe": 31}
                
                mon_dto = {
                    "species": species_entry.get("name") or species_name,
                    "types": types_tuple,
                    "base": base_stats,
                    "ivs": ivs,
                    "evs": evs,
                    "nature": nature,
                    "ability": ability_name,
                    "gender": None,
                    "item": fallback_config.get("item"),
                    "moves": final_moves,  # List of strings, exactly like build_mon expects
                    "level": 100,
                    "hp_now": 100,
                    "is_shiny": False,
                    "is_fully_evolved": bool(species_entry.get("is_fully_evolved", True)),
                    "weight_kg": float(species_entry.get("weight_kg", 100.0)),
                    "friendship": 255,
                }
                
                mon = build_mon(mon_dto, set_level=100, heal=True)
                team.append(mon)
                
                # Only need one fallback Pokémon
                if team:
                    break
            except Exception as e:
                print(f"[AI] Error generating fallback bot Pokemon {fallback_config.get('species', 'unknown')}: {e}")
                continue
    
    return team
