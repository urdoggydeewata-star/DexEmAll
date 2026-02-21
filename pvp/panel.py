from __future__ import annotations
import asyncio
import json
import random
import time
import os
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any, Tuple
from datetime import datetime, timedelta
import discord
try:
    from PIL import Image as _PILImage, ImageDraw as _PILImageDraw  # type: ignore
except Exception:
    _PILImage = None  # type: ignore
    _PILImageDraw = None  # type: ignore

from .manager import get_manager
from .engine import (
    build_party_from_db,
    apply_move,
    action_priority,
    speed_value,
    Mon,
    reset_rollout,
    item_is_active,
    modify_stages,
    inflict_status,
    can_terastallize,
    can_mega_evolve,
    apply_terastallization,
    revert_terastallization,
    apply_mega_evolution,
    revert_mega_evolution,
    format_species_name,
)
from .abilities import normalize_ability_name, get_ability_effect
from .db_adapter import get_party_for_engine
from .moves_loader import get_move, makes_contact  # <- to fetch base PP and move info
try:
    from lib import db_cache as _lib_db_cache
except ImportError:
    _lib_db_cache = None
try:
    from lib import db as _lib_db
except Exception:
    _lib_db = None
try:
    from lib import register_stats as _register_stats  # type: ignore
except Exception:
    _register_stats = None
from .move_effects import get_move_secondary_effect

# Helper to get move data with battle cache support (no recursion)
def _get_move_with_cache(move_name: str, battle_state: Any = None, generation: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """
    Get move data, using the battle_state's _move_cache if provided.
    This is deliberately kept recursion-safe (does NOT call get_cached_move).
    """
    if not move_name:
        return None

    norm = move_name.lower().replace(" ", "-")

    # Check cache directly
    if battle_state is not None and hasattr(battle_state, "_move_cache"):
        cached = battle_state._move_cache.get(norm) or battle_state._move_cache.get(move_name.lower())
        if cached is not None:
            return cached

    # Fallback to loader
    # IMPORTANT: avoid recursion by calling get_move with battle_state=None here.
    move_data = get_move(move_name, generation=generation, battle_state=None)

    # Write-through to cache for subsequent calls
    if battle_state is not None and hasattr(battle_state, "_move_cache"):
        battle_state._move_cache[norm] = move_data
        battle_state._move_cache[move_name.lower()] = move_data

    return move_data
from .battle_flow import (
    can_pokemon_move, get_available_moves, should_start_charging, execute_charging_turn,
    execute_attack_turn, should_recharge_next_turn, apply_move_restrictions,
    apply_field_effect_move, apply_substitute, handle_protect, handle_max_guard, end_of_turn_cleanup
)
from .advanced_mechanics import clear_special_weather, Substitute
from .move_mechanics import get_move_mechanics
from .z_moves import is_z_crystal, can_use_z_move, get_z_move_name
from .abilities import normalize_ability_name, get_ability_effect
try:
    import db_async
except ImportError:
    db_async = None  # Will handle gracefully if db_async not available

# (Optional GIF renderer; safe no-op if missing)
try:
    from .renderer import render_turn_gif, cleanup_battle_media
except Exception:
    render_turn_gif = None
    def cleanup_battle_media(_): ...

from .panel_capture import (
    _HEALING_ITEMS,
    _BALLS_BASIC,
    _BALL_NAME_ALIASES,
    _normalize_item,
    _normalize_ball_name,
    heal_amount_for_item as _heal_amount_for_item,
    status_bonus as _status_bonus,
    ball_multiplier as _ball_multiplier,
    attempt_capture as _attempt_capture,
)

import lib.rules as _rules

_GEAR_CACHE_TTL = 60.0  # seconds
_gear_cache: Dict[Tuple[str, str, int], Tuple[bool, float]] = {}

def _open_fd_count() -> Optional[int]:
    """Best-effort open file descriptor count (Linux containers)."""
    try:
        # Works on Linux; returns None on Windows/macOS.
        return len(os.listdir("/proc/self/fd"))
    except Exception:
        return None


def _gear_cache_get(kind: str, user_id_str: str, battle_gen: int) -> Optional[bool]:
    key = (kind, user_id_str, battle_gen)
    cached = _gear_cache.get(key)
    if not cached:
        return None
    value, timestamp = cached
    if time.monotonic() - timestamp > _GEAR_CACHE_TTL:
        _gear_cache.pop(key, None)
        return None
    return value


def _gear_cache_set(kind: str, user_id_str: str, battle_gen: int, value: bool) -> None:
    key = (kind, user_id_str, battle_gen)
    _gear_cache[key] = (value, time.monotonic())


def _battle_ui_is_public(st: Optional["BattleState"]) -> bool:
    try:
        if str(getattr(st, "battle_mode", "") or "").strip().lower() == "route":
            return True
        return bool(getattr(st, "public_battle_ui", False))
    except Exception:
        return False


def _battle_ui_ephemeral(st: Optional["BattleState"]) -> bool:
    return not _battle_ui_is_public(st)


def _format_move_name(move_name: str) -> str:
    """Format move name with capitalized first letter."""
    if not move_name:
        return move_name
    # Replace hyphens with spaces, capitalize first letter of each word
    parts = move_name.replace("-", " ").replace("_", " ").split()
    return " ".join(part.capitalize() for part in parts) if parts else move_name.capitalize()

def _format_pokemon_name(mon: Any) -> str:
    """Format Pokémon name with ★ prefix if shiny."""
    if not mon:
        return "Unknown"
    name = format_species_name(mon.species)
    if getattr(mon, 'shiny', False):
        return f"★ {name}"
    return name

def _build_species_display_map(state: "BattleState") -> Dict[str, str]:
    """Create a mapping from raw species identifiers to display-friendly names with ★ for shiny."""
    mapping: Dict[str, str] = {}
    if not state:
        return mapping

    def _register(raw_name: Optional[str], mon: Optional[Any] = None) -> None:
        if not raw_name:
            return
        # Check if this is a shiny Pokémon
        is_shiny = mon and getattr(mon, 'shiny', False)
        display = format_species_name(raw_name)
        if is_shiny:
            display = f"★ {display}"
        variants = {
            raw_name,
            raw_name.lower(),
            raw_name.title(),
        }
        for variant in variants:
            if variant and variant not in mapping:
                mapping[variant] = display

    for roster in (state.p1_team, state.p2_team):
        for mon in roster:
            if not mon:
                continue
            _register(mon.species, mon)
            _register(getattr(mon, "_true_species", None), mon)
            _register(getattr(mon, "_illusion_species", None), mon)

    return mapping


def _append_forced_switch_to_turn_log(st: "BattleState", uid: int, fainted_display: str, new_mon_display: str) -> None:
    """After a faint, update last turn log: remove 'must send out another Pokémon!', add 'X was swapped out fainted!' and 'Trainer sent out Y!'."""
    log = getattr(st, "_last_turn_log", []) or []
    trainer_name = st.p1_name if uid == st.p1_id else st.p2_name
    # Remove "**Trainer** must send out another Pokémon!"
    log = [line for line in log if "must send out another Pokémon" not in line]
    log.append(f"**{fainted_display}** was swapped out fainted!")
    log.append(f"**{trainer_name}** sent out **{new_mon_display}**!")
    st._last_turn_log = log


_AI_THINK_TIMEOUT_MIN = 5.0
_AI_THINK_TIMEOUT_MAX = 10.0
_AI_FORCED_SWITCH_TIMEOUT = 4.0


def _norm_move_key(move_name: Any) -> str:
    return str(move_name or "").strip().lower().replace("_", "-").replace(" ", "-")


def _legal_ai_moves(st: "BattleState", ai_user_id: int) -> List[str]:
    """Return legal move names with PP remaining for AI fallback/validation."""
    active = st._active(ai_user_id)
    out: List[str] = []
    for raw in (st.moves_for(ai_user_id) or []):
        mv = str(raw or "").strip()
        if not mv:
            continue
        try:
            if active is not None and st._pp_left(ai_user_id, mv, active) <= 0:
                continue
        except Exception:
            pass
        out.append(mv)
    return out


def _ai_move_is_zero_effect_damaging(
    st: "BattleState",
    ai_user_id: int,
    move_name: str,
    field_effects: Any,
) -> bool:
    """True if move is damaging and predicted to have zero type effect on target."""
    try:
        ai_mon = st._active(ai_user_id)
        target_mon = st._opp_active(ai_user_id)
        if ai_mon is None or target_mon is None:
            return False
        md = _get_move_with_cache(move_name, battle_state=st, generation=getattr(st, "gen", None)) or {}
        category = str(md.get("category") or md.get("damage_class") or "status").lower()
        power = float(md.get("power") or 0.0)
        if category == "status" or power <= 0:
            return False
        from .engine import type_multiplier
        mult, _ = type_multiplier(md.get("type", "Normal"), target_mon, field_effects=field_effects, user=ai_mon)
        return float(mult) == 0.0
    except Exception:
        return False


def _ai_move_fails_basic_condition(
    st: "BattleState",
    ai_user_id: int,
    move_name: str,
) -> bool:
    """Fast context checks for moves that fail without prerequisites."""
    mv = _norm_move_key(move_name)
    try:
        ai_mon = st._active(ai_user_id)
        target_mon = st._opp_active(ai_user_id)
    except Exception:
        ai_mon = None
        target_mon = None

    if mv in {"dream-eater", "nightmare"}:
        return str(getattr(target_mon, "status", "") or "").lower() != "slp"
    if mv in {"snore", "sleep-talk"}:
        return str(getattr(ai_mon, "status", "") or "").lower() != "slp"
    return False


def _choose_quick_fallback_move(st: "BattleState", ai_user_id: int, field_effects: Any) -> Dict[str, Any]:
    """
    Fast deterministic fallback move picker for AI timeout/error cases.
    Uses lightweight scoring (power/priority/accuracy + context).
    """
    legal_moves = _legal_ai_moves(st, ai_user_id)
    if not legal_moves:
        return {"kind": "move", "value": "Tackle"}

    ai_mon = st._active(ai_user_id)
    target_mon = st._opp_active(ai_user_id)
    ai_hp_pct = 1.0
    if ai_mon and getattr(ai_mon, "max_hp", 0):
        try:
            ai_hp_pct = max(0.0, min(1.0, float(ai_mon.hp) / float(ai_mon.max_hp)))
        except Exception:
            ai_hp_pct = 1.0

    recovery_moves = {
        "recover", "roost", "slack-off", "soft-boiled", "heal-order",
        "strength-sap", "moonlight", "synthesis", "morning-sun", "wish",
    }
    setup_moves = {"swords-dance", "dragon-dance", "calm-mind", "nasty-plot", "quiver-dance", "bulk-up"}

    best_move = legal_moves[0]
    best_score = float("-inf")
    for mv in legal_moves:
        md = _get_move_with_cache(mv, battle_state=st, generation=getattr(st, "gen", None)) or {}
        power = float(md.get("power") or 0.0)
        priority = float(md.get("priority") or 0.0)
        accuracy = float(md.get("accuracy") or 100.0)
        move_key = _norm_move_key(mv)
        category = str(md.get("category") or md.get("damage_class") or "status").lower()
        score = (power * 1.15) + (priority * 38.0) + max(0.0, min(100.0, accuracy)) * 0.12
        if _ai_move_fails_basic_condition(st, ai_user_id, mv):
            score -= 240.0
        if category == "status" and power <= 0:
            score -= 8.0
        if move_key in recovery_moves and ai_hp_pct <= 0.42:
            score += 26.0
        if move_key in setup_moves and ai_hp_pct >= 0.72:
            score += 7.0
        if move_key in setup_moves and ai_hp_pct <= 0.45:
            score -= 18.0

        # Mild preference for STAB in fallback mode.
        try:
            m_type = str(md.get("type") or "").lower()
            ai_types = [str(t).lower() for t in (getattr(ai_mon, "types", None) or [])]
            if m_type and m_type in ai_types and power > 0:
                score += 11.0
        except Exception:
            pass

        # Mild preference for super-effective hit if quickly known.
        if power > 0 and ai_mon is not None and target_mon is not None:
            try:
                from .engine import type_multiplier
                mult, _ = type_multiplier(md.get("type", "Normal"), target_mon, field_effects=field_effects, user=ai_mon)
                if float(mult) == 0.0:
                    # Avoid "no effect" damaging picks unless literally every option is bad.
                    score -= 240.0
                elif float(mult) >= 2.0:
                    score += 14.0
                elif float(mult) < 1.0:
                    score -= 8.0
            except Exception:
                pass

        if score > best_score:
            best_score = score
            best_move = mv
    return {"kind": "move", "value": str(best_move)}


async def _ai_best_switch_with_timeout(st: "BattleState", ai_user_id: int, field_effects: Any, timeout_s: float = _AI_FORCED_SWITCH_TIMEOUT) -> Optional[int]:
    """Compute best switch on a worker thread with timeout."""
    switch_opts = st.switch_options(ai_user_id) or []
    if not switch_opts:
        return None
    try:
        from .ai import _choose_best_switch
        current = st._active(ai_user_id)
        target = st._opp_active(ai_user_id)
        if not current or not target:
            return int(switch_opts[0])

        def _runner() -> Optional[int]:
            try:
                return _choose_best_switch(
                    current_mon=current,
                    target_mon=target,
                    switch_options=switch_opts,
                    battle_state=st,
                    field_effects=field_effects,
                    switching_user_id=ai_user_id,
                )
            except Exception:
                return None

        choice = await asyncio.wait_for(asyncio.to_thread(_runner), timeout=max(0.2, float(timeout_s)))
        if choice is None:
            return int(switch_opts[0])
        c = int(choice)
        return c if c in switch_opts else int(switch_opts[0])
    except Exception:
        return int(switch_opts[0]) if switch_opts else None


def _normalize_ai_choice(st: "BattleState", ai_user_id: int, raw_choice: Any, field_effects: Any) -> Dict[str, Any]:
    """
    Ensure AI choice is legal; invalid choices are converted to legal move fallback.
    This prevents dead turns from malformed AI responses.
    """
    choice = raw_choice if isinstance(raw_choice, dict) else {}
    kind = str(choice.get("kind") or "").strip().lower()
    legal_moves = _legal_ai_moves(st, ai_user_id)
    switch_opts = st.switch_options(ai_user_id) or []

    if kind == "switch":
        try:
            idx = int(choice.get("value"))
            if idx in switch_opts:
                # Validate switch legality against trapping effects.
                from .engine import can_switch_out
                ai_mon = st._active(ai_user_id)
                target_mon = st._opp_active(ai_user_id)
                if ai_mon and target_mon:
                    can_sw, _ = can_switch_out(
                        ai_mon, target_mon, force_switch=False, field_effects=field_effects, battle_state=st
                    )
                    if can_sw:
                        return {"kind": "switch", "value": idx}
        except Exception:
            pass

    if kind == "move":
        mv = str(choice.get("value") or "").strip()
        if mv:
            wanted = _norm_move_key(mv)
            has_non_zero_effect_option = any(
                not _ai_move_is_zero_effect_damaging(st, ai_user_id, lm, field_effects)
                for lm in legal_moves
            )
            has_condition_valid_option = any(
                not _ai_move_fails_basic_condition(st, ai_user_id, lm)
                for lm in legal_moves
            )
            for lm in legal_moves:
                if _norm_move_key(lm) == wanted:
                    # Reject "no effect" damaging move picks when a valid alternative exists.
                    if has_non_zero_effect_option and _ai_move_is_zero_effect_damaging(st, ai_user_id, lm, field_effects):
                        break
                    if has_condition_valid_option and _ai_move_fails_basic_condition(st, ai_user_id, lm):
                        break
                    return {"kind": "move", "value": lm}

    # Fallback to a legal move.
    return _choose_quick_fallback_move(st, ai_user_id, field_effects)


async def _compute_ai_choice_with_timeout(st: "BattleState", ai_user_id: int, field_effects: Any) -> Dict[str, Any]:
    """
    Run full AI on a worker thread with bounded think time.
    AI gets up to 5-10 seconds per decision; timeout/error falls back to legal action.
    """
    legal_moves = _legal_ai_moves(st, ai_user_id)
    if len(legal_moves) == 1:
        return {"kind": "move", "value": legal_moves[0]}

    think_budget = random.uniform(_AI_THINK_TIMEOUT_MIN, _AI_THINK_TIMEOUT_MAX)
    try:
        from .ai import choose_ai_action
    except Exception:
        return _choose_quick_fallback_move(st, ai_user_id, field_effects)

    try:
        raw_choice = await asyncio.wait_for(
            asyncio.to_thread(choose_ai_action, ai_user_id, st, field_effects),
            timeout=think_budget,
        )
        return _normalize_ai_choice(st, ai_user_id, raw_choice, field_effects)
    except asyncio.TimeoutError:
        print(f"[AI] Decision timeout for {ai_user_id} after {think_budget:.2f}s; using fallback action.")
        # On timeout, prefer a defensive switch when under visible pressure.
        try:
            ai_mon = st._active(ai_user_id)
            opp_mon = st._opp_active(ai_user_id)
            if ai_mon and opp_mon:
                hp_ratio = (float(ai_mon.hp) / float(ai_mon.max_hp)) if getattr(ai_mon, "max_hp", 0) else 1.0
                if hp_ratio <= 0.35:
                    sw = await _ai_best_switch_with_timeout(st, ai_user_id, field_effects, timeout_s=2.5)
                    if sw is not None:
                        return {"kind": "switch", "value": int(sw)}
        except Exception:
            pass
        return _choose_quick_fallback_move(st, ai_user_id, field_effects)
    except Exception as e:
        print(f"[AI] Error generating choice for {ai_user_id}: {e}")
        return _choose_quick_fallback_move(st, ai_user_id, field_effects)


def _format_move_name(move_name: str) -> str:
    """Format move name with capitalized first letter."""
    if not move_name:
        return move_name
    # Replace hyphens with spaces, capitalize first letter of each word
    parts = move_name.replace("-", " ").replace("_", " ").split()
    return " ".join(part.capitalize() for part in parts) if parts else move_name.capitalize()

def _format_log_line(text: str, mapping: Dict[str, str]) -> str:
    """Replace raw species references in battle logs with display names."""
    if not text:
        return text
    result = text
    import re
    
    # Replace species names, but skip if the name already has a star (to avoid double stars)
    for raw, display in mapping.items():
        if raw:
            # Check if the name already has a star before it (to avoid double stars)
            # Pattern: look for "★ " or "★" followed by the raw name (case-insensitive)
            # Also check if it's inside ** markers with a star
            star_pattern = re.compile(r'★\s*' + re.escape(raw), re.IGNORECASE)
            if star_pattern.search(result):
                # Name already has a star, skip replacement to avoid double stars
                continue
            # Only replace if there's no star already
            result = result.replace(raw, display)
    
    # Format move names only when they're in "used **move**" or "unleashes **move**" contexts
    # to avoid mangling species names that are also bolded.
    def _format_move_match(match: re.Match) -> str:
        move_name = match.group(1)
        # Skip if it already has a star (to avoid formatting already-formatted names)
        if '?' in move_name:
            return match.group(0)
        formatted = _format_move_name(move_name)
        return match.group(0).replace(move_name, formatted, 1)

    result = re.sub(r'used\s+\*\*([^*]+)\*\*', _format_move_match, result, flags=re.IGNORECASE)
    result = re.sub(r'unleashes\s+\*\*([^*]+)\*\*', _format_move_match, result, flags=re.IGNORECASE)
    return result


# =====================  HELPERS (PP & CHOICE)  =====================

def _base_pp(move_name: str, generation: Optional[int] = None) -> int:
    """Return base PP for a move from your moves DB (fallback 20).
    When generation is set, PP is taken only from move_generation_stats (gen-accurate);
    move_effects gen_specific PP overrides are skipped so gen stats are prioritised."""
    try:
        mv = _get_move_with_cache(move_name, battle_state=None, generation=generation)
        if mv and "pp" in mv and mv["pp"] is not None:
            return int(mv["pp"])
    except Exception:
        pass
    return 20

def _max_pp(move_name: str, generation: Optional[int] = None) -> int:
    """Return max PP for a move in PvP (base PP * 1.6, rounded down, as if 3 PP Ups were used).
    Moves with base PP of 1 remain at 1 (PP Ups don't affect them)."""
    base = _base_pp(move_name, generation=generation)
    if base == 1:
        return 1  # Moves with base PP of 1 cannot be increased
    # Max PP = base PP * 1.6 (3 PP Ups = 20% each = 60% total)
    return int(base * 1.6)


def _norm_pp_move_key(move_name: Any) -> str:
    """Lowercase-hyphen form for moves DB/engine lookups."""
    return str(move_name or "").strip().lower().replace(" ", "-").replace("_", "-")


def _canonical_move_name(move_name: Any) -> str:
    """Title Case with spaces - the single canonical form for PP storage and display.
    Collapses all whitespace so 'Tail  Whip' and 'Tail Whip' match."""
    s = str(move_name or "").strip().lower().replace("_", " ").replace("-", " ")
    if not s:
        return "Tackle"
    return " ".join(s.split()).title()


def _pp_global_max_for_move(move_name: str, generation: Optional[int] = None) -> int:
    try:
        return max(1, int(_max_pp(move_name, generation=generation)))
    except Exception:
        try:
            return max(1, int(_base_pp(move_name, generation=generation)))
        except Exception:
            return 20


def _pp_parse_list(raw: Any, *, count: int, defaults: List[int], lo: int, hi: int) -> List[int]:
    vals = raw
    if isinstance(vals, str):
        try:
            vals = json.loads(vals) if vals else []
        except Exception:
            vals = []
    if not isinstance(vals, (list, tuple)):
        vals = []
    out: List[int] = []
    for i in range(int(count)):
        default_i = int(defaults[i]) if i < len(defaults) else int(defaults[-1] if defaults else lo)
        v = vals[i] if i < len(vals) else default_i
        try:
            n = int(v)
        except Exception:
            n = default_i
        out.append(max(int(lo), min(int(hi), int(n))))
    return out


def _check_dmax_gear_sync(user_id_str: str, battle_gen: int = 8) -> bool:
    """
    Synchronously check if user has Dynamax Band equipped AND it's active for the battle generation.
    Dynamax Band is only active in Gen 8+ battles.
    """
    cached = _gear_cache_get("dmax", user_id_str, battle_gen)
    if cached is not None:
        return cached
    if battle_gen < 8:
        _gear_cache_set("dmax", user_id_str, battle_gen, False)
        return False
    result = False
    try:
        from .db_adapter import _open, _close_conn
        conn = _open()
        try:
            cur = conn.execute(
                "SELECT dmax_gear FROM user_equipment WHERE owner_id=?",
                (user_id_str,)
            )
            row = cur.fetchone()
            cur.close()
            if row:
                # Row supports dictionary-style access
                dmax_gear = row["dmax_gear"] if "dmax_gear" in row.keys() else row[0]
                # Return True only if value is not None and not empty string AND generation matches
                has_gear = bool(dmax_gear) and str(dmax_gear).strip() != ""
                # Dynamax Band is only active in Gen 8+
                result = has_gear and battle_gen >= 8
        finally:
            _close_conn(conn)
    except Exception:
        result = False
    _gear_cache_set("dmax", user_id_str, battle_gen, result)
    return result

def _check_z_gear_sync(user_id_str: str, battle_gen: int = 7) -> bool:
    """
    Synchronously check if user has Z-Ring equipped AND it's active for the battle generation.
    Z-Ring is only active in Gen 7 battles.
    """
    cached = _gear_cache_get("z", user_id_str, battle_gen)
    if cached is not None:
        return cached
    if battle_gen != 7:
        _gear_cache_set("z", user_id_str, battle_gen, False)
        return False
    result = False
    try:
        from .db_adapter import _open, _close_conn
        conn = _open()
        try:
            cur = conn.execute(
                "SELECT z_gear FROM user_equipment WHERE owner_id=?",
                (user_id_str,)
            )
            row = cur.fetchone()
            cur.close()
            if row:
                # Row supports dictionary-style access
                z_gear = row["z_gear"] if "z_gear" in row.keys() else row[0]
                # Return True only if value is not None and not empty string AND generation matches
                has_gear = bool(z_gear) and str(z_gear).strip() != ""
                # Z-Ring is only active in Gen 7
                result = has_gear and battle_gen == 7
        finally:
            _close_conn(conn)
    except Exception:
        result = False
    _gear_cache_set("z", user_id_str, battle_gen, result)
    return result

def _check_mega_gear_sync(user_id_str: str, battle_gen: int = 6) -> bool:
    """
    Check if user has Mega gear equipped and unlocked for the battle generation.
    Mega Evolution is available in Gen 6-7.
    """
    cached = _gear_cache_get("mega", user_id_str, battle_gen)
    if cached is not None:
        return cached
    if battle_gen < 6 or battle_gen > 7:
        _gear_cache_set("mega", user_id_str, battle_gen, False)
        return False
    result = False
    try:
        from .db_adapter import _open, _close_conn
        conn = _open()
        try:
            cur = conn.execute(
                "SELECT mega_gear, mega_unlocked FROM user_equipment WHERE owner_id=?",
                (user_id_str,)
            )
            row = cur.fetchone()
            cur.close()
            if row:
                mega_gear = row["mega_gear"] if "mega_gear" in row.keys() else row[0]
                mega_unlocked = row["mega_unlocked"] if "mega_unlocked" in row.keys() else row[1]
                has_gear = bool(mega_gear) and str(mega_gear).strip() != ""
                unlocked = bool(mega_unlocked)
                result = has_gear and unlocked and _rules.mega_allowed_in_gen(battle_gen)
        finally:
            _close_conn(conn)
    except Exception:
        result = False
    _gear_cache_set("mega", user_id_str, battle_gen, result)
    return result

def _check_tera_gear_sync(user_id_str: str, battle_gen: int = 9) -> bool:
    """
    Synchronously check if user has the Tera Orb equipped AND it's active for the battle generation.
    Tera Orb is only active in Gen 9 battles.
    """
    cached = _gear_cache_get("tera", user_id_str, battle_gen)
    if cached is not None:
        return cached
    if battle_gen < 9:
        _gear_cache_set("tera", user_id_str, battle_gen, False)
        return False
    result = False
    try:
        from .db_adapter import _open, _close_conn
        conn = _open()
        try:
            cur = conn.execute(
                "SELECT tera_gear FROM user_equipment WHERE owner_id=?",
                (user_id_str,)
            )
            row = cur.fetchone()
            cur.close()
            if row:
                tera_gear = row["tera_gear"] if "tera_gear" in row.keys() else row[0]
                has_gear = bool(tera_gear) and str(tera_gear).strip() != ""
                result = has_gear and battle_gen >= 9
        finally:
            _close_conn(conn)
    except Exception:
        result = False
    _gear_cache_set("tera", user_id_str, battle_gen, result)
    return result

def _is_damaging_move(move_name: str) -> bool:
    """Consider a move damaging if it has non-zero power in your DB."""
    try:
        mv = _get_move_with_cache(move_name, battle_state=None, generation=None)
        pw = int(mv.get("power") or 0) if mv else 0
        return pw > 0
    except Exception:
        return False


def _record_last_move(mon: Mon, move_name: str, battle_state: Any = None) -> None:
    """Track the last move name (and its base type) used by a Pokémon."""
    mon.last_move_used = move_name
    # Buffer move-usage counters for /register profiles; flush at battle end.
    try:
        if battle_state is not None:
            owner_raw = getattr(mon, "_owner_id", None)
            mon_id_raw = getattr(mon, "_db_id", None)
            owner_id = str(owner_raw or "")
            mon_id = int(mon_id_raw or 0)
            if mon_id <= 0 and battle_state is not None and owner_id:
                try:
                    owner_uid = int(owner_id)
                except Exception:
                    owner_uid = 0
                if owner_uid > 0:
                    try:
                        team = battle_state.team_for(owner_uid) if hasattr(battle_state, "team_for") else []
                    except Exception:
                        team = []
                    for candidate in team or []:
                        if candidate is mon:
                            try:
                                mon_id = int(getattr(candidate, "_db_id", 0) or 0)
                            except Exception:
                                mon_id = 0
                            break
            should_track = bool(_register_stats is not None and owner_id and mon_id > 0)
            if should_track:
                mv_key = str(move_name or "").strip().lower().replace("_", "-").replace(" ", "-")
                if mv_key and mv_key != "recharge":
                    usage_buf = getattr(battle_state, "_registered_move_usage", None)
                    if not isinstance(usage_buf, dict):
                        usage_buf = {}
                        setattr(battle_state, "_registered_move_usage", usage_buf)
                    key = (owner_id, mon_id)
                    bucket = usage_buf.get(key)
                    if not isinstance(bucket, dict):
                        bucket = {}
                        usage_buf[key] = bucket
                    bucket[mv_key] = int(bucket.get(mv_key, 0) or 0) + 1
    except Exception:
        pass
    try:
        mv = _get_move_with_cache(move_name, battle_state=battle_state, generation=battle_state.gen if battle_state else None)
        if mv:
            mon._last_move_used_type = mv.get("type")
        else:
            mon._last_move_used_type = "Normal" if move_name.lower().replace(" ", "-") == "struggle" else None
    except Exception:
        mon._last_move_used_type = "Normal" if move_name.lower().replace(" ", "-") == "struggle" else None


def _record_registered_ko(atk: Mon, dfn: Mon, battle_state: Any = None) -> None:
    """Buffer KO counters for /register profiles; flushed once in _finish."""
    try:
        if battle_state is None:
            return
        owner_raw = getattr(atk, "_owner_id", None)
        mon_id_raw = getattr(atk, "_db_id", None)
        owner_id = str(owner_raw or "")
        mon_id = int(mon_id_raw or 0)
        if mon_id <= 0 and battle_state is not None and owner_id:
            try:
                owner_uid = int(owner_id)
            except Exception:
                owner_uid = 0
            if owner_uid > 0:
                try:
                    team = battle_state.team_for(owner_uid) if hasattr(battle_state, "team_for") else []
                except Exception:
                    team = []
                for candidate in team or []:
                    if candidate is atk:
                        try:
                            mon_id = int(getattr(candidate, "_db_id", 0) or 0)
                        except Exception:
                            mon_id = 0
                        break
        if not owner_id or mon_id <= 0:
            return
        if _register_stats is None:
            return
        ko_buf = getattr(battle_state, "_registered_ko_stats", None)
        if not isinstance(ko_buf, dict):
            ko_buf = {}
            setattr(battle_state, "_registered_ko_stats", ko_buf)
        key = (owner_id, mon_id)
        rec = ko_buf.get(key)
        if not isinstance(rec, dict):
            rec = {"pokemon_beat": 0, "shinies_killed": 0, "species_kos": {}}
            ko_buf[key] = rec
        rec["pokemon_beat"] = int(rec.get("pokemon_beat", 0) or 0) + 1
        if bool(getattr(dfn, "shiny", False)):
            rec["shinies_killed"] = int(rec.get("shinies_killed", 0) or 0) + 1
        species_kos = rec.get("species_kos")
        if not isinstance(species_kos, dict):
            species_kos = {}
            rec["species_kos"] = species_kos
        defeated_species = str(getattr(dfn, "species", "") or "").strip().lower().replace("_", "-")
        if defeated_species:
            species_kos[defeated_species] = int(species_kos.get(defeated_species, 0) or 0) + 1
    except Exception:
        pass


def _dispatch_award_exp_on_faint_callback(battle_state: Any, fainted_mon: Mon) -> None:
    """Best-effort fire-and-forget hook used by adventure per-faint EXP logic."""
    try:
        faint_cb = getattr(battle_state, "_award_exp_on_faint_callback", None)
        if not callable(faint_cb):
            return
        ret = faint_cb(battle_state, fainted_mon)
        if asyncio.iscoroutine(ret):
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(ret)
            except Exception:
                pass
    except Exception:
        pass

def _has_choice_item(mon: Mon) -> bool:
    """Detect choice item on the active Pokémon (Band/Specs/Scarf)."""
    item = (getattr(mon, "item", None) or "").lower().replace(" ", "-").replace("_", "-")
    return item.startswith("choice-") or "choice " in item

# =====================  BATTLE STATE (real engine under the hood)  =====================
class BattleState:
    def __init__(self, fmt_label: str, gen: int, p1_id: int, p2_id: int,
                 p1_party: List[Mon], p2_party: List[Mon], p1_name: str = None, p2_name: str = None,
                 p1_is_bot: bool = False, p2_is_bot: bool = False, is_dummy_battle: bool = False):
        self.fmt_label = fmt_label
        self.gen = int(gen)
        self.p1_id = int(p1_id)
        self.p2_id = int(p2_id)
        self.is_dummy_battle = bool(is_dummy_battle)
        self.p1_name = p1_name or f"Player {p1_id}"
        self.p2_name = p2_name or f"Player {p2_id}"
        self.p1_is_bot = p1_is_bot
        self.p2_is_bot = p2_is_bot
        self.p1_team: List[Mon] = p1_party[:6]
        self.p2_team: List[Mon] = p2_party[:6]
        for idx, mon in enumerate(self.p1_team):
            if mon is not None:
                setattr(mon, "_battle_slot", idx)
        for idx, mon in enumerate(self.p2_team):
            if mon is not None:
                setattr(mon, "_battle_slot", idx)
        self.p1_active = 0
        self.p2_active = 0
        self.turn = 1
        self.winner: Optional[int] = None
        self.stream_message: Optional[discord.Message] = None  # Stream message for public viewing
        self.streaming_enabled: bool = False  # Whether streaming is enabled
        self.stream_channel: Optional[Any] = None
        self.stream_channel_id: Optional[int] = None
        self._stream_started: bool = False

        # UI per-turn lock (don't confuse with choice lock below)
        self._locked: Dict[int, bool] = {self.p1_id: False, self.p2_id: False}

        # Per-battle PP store by (user_id, team_index) -> move_name -> remaining
        # This ensures each Pokemon has its own PP, even if multiple Pokemon have the same move
        self._pp: Dict[Tuple[int, int], Dict[str, int]] = {}

        # Choice lock: user_id -> move name the user is locked into. None if free.
        self._choice_locked: Dict[int, Optional[str]] = {self.p1_id: None, self.p2_id: None}
        
        # Field effects (weather, terrain, trick room, etc.)
        from .advanced_mechanics import FieldEffects, SideEffects
        self.field: FieldEffects = FieldEffects(generation=self.gen)
        self.p1_side: SideEffects = SideEffects()
        self.p2_side: SideEffects = SideEffects()
        # Track participants for EXP split
        self.p1_participants: set = set()
        self.p2_participants: set = set()
        # /register tracking buffers (flushed once at battle end).
        self._registered_move_usage: Dict[Tuple[str, int], Dict[str, int]] = {}
        self._registered_ko_stats: Dict[Tuple[str, int], Dict[str, Any]] = {}
        # Track money bonuses from Pay Day etc. and Happy Hour flags
        self.money_pool: Dict[int, int] = {self.p1_id: 0, self.p2_id: 0}
        self.happy_hour_used: Dict[int, bool] = {self.p1_id: False, self.p2_id: False}
        
        # Dynamax tracking: track if each player has used Dynamax this battle
        self._dynamax_used: Dict[int, bool] = {self.p1_id: False, self.p2_id: False}
        self._z_move_used: Dict[int, bool] = {self.p1_id: False, self.p2_id: False}
        self._mega_used: Dict[int, bool] = {self.p1_id: False, self.p2_id: False}
        self._tera_used: Dict[int, bool] = {self.p1_id: False, self.p2_id: False}
        self._pending_mega_evolutions: Dict[int, str] = {}  # Store mega evolution choices to apply after switches
        self._pending_healing_wish: Dict[int, bool] = {self.p1_id: False, self.p2_id: False}
        self._pending_lunar_dance: Dict[int, bool] = {self.p1_id: False, self.p2_id: False}

        # Set generation for hazards
        self.p1_side.hazards.generation = self.gen
        self.p2_side.hazards.generation = self.gen
        
        # Roll Missing n0 stats, types, abilities, and moves at battle start
        from .engine import _roll_missing_n0_stats, _roll_missing_n0_type, _roll_missing_n0_ability, _roll_missing_n0_moves, _calc_hp, _calc_stat
        for mon in self.p1_team + self.p2_team:
            if mon:
                species_lower = (mon.species or "").lower().strip()
                species_name_lower = getattr(mon, 'species_name', "").lower().strip() if hasattr(mon, 'species_name') else ""
                is_missing_n0 = (
                    species_lower in ["missing n0", "missing no", "missing no.", "missingno", "missingno.", "missing n0.", "missing no."] or
                    species_name_lower in ["missing n0", "missing no", "missing no.", "missingno", "missingno.", "missing n0.", "missing no."] or
                    ("missing" in species_lower and ("n0" in species_lower or "no" in species_lower)) or
                    ("missing" in species_name_lower and ("n0" in species_name_lower or "no" in species_name_lower))
                )
                
                if is_missing_n0:
                    # Roll random stats, type, ability, and moves for Missing n0 at battle start
                    rolled_base = _roll_missing_n0_stats()
                    rolled_types = _roll_missing_n0_type()
                    rolled_ability = _roll_missing_n0_ability()
                    rolled_moves = _roll_missing_n0_moves()
                    
                    # Update base stats
                    mon.base = rolled_base
                    
                    # Recalculate stats with new base stats
                    level = mon.level
                    nmods = {"atk": 1.0, "defn": 1.0, "spa": 1.0, "spd": 1.0, "spe": 1.0}
                    if mon.nature_name:
                        from .engine import NATURES
                        nmods = NATURES.get(mon.nature_name.title(), nmods)
                    mon.stats = {
                        "atk": _calc_stat(rolled_base["atk"], mon.ivs["atk"], mon.evs["atk"], level, nmods["atk"]),
                        "defn": _calc_stat(rolled_base["defn"], mon.ivs["defn"], mon.evs["defn"], level, nmods["defn"]),
                        "spa": _calc_stat(rolled_base["spa"], mon.ivs["spa"], mon.evs["spa"], level, nmods["spa"]),
                        "spd": _calc_stat(rolled_base["spd"], mon.ivs["spd"], mon.evs["spd"], level, nmods["spd"]),
                        "spe": _calc_stat(rolled_base["spe"], mon.ivs["spe"], mon.evs["spe"], level, nmods["spe"]),
                    }
                    # Recalculate HP and derived fields
                    old_max_hp = mon.max_hp
                    mon.max_hp = _calc_hp(rolled_base["hp"], mon.ivs["hp"], mon.evs["hp"], level)
                    if old_max_hp > 0:
                        hp_ratio = mon.hp / old_max_hp
                        mon.hp = max(1, int(mon.max_hp * hp_ratio))
                    else:
                        mon.hp = mon.max_hp
                    # Update types, ability, moves, and form
                    mon.types = rolled_types
                    mon._mega_original_types = rolled_types
                    mon._tera_original_types = rolled_types
                    mon.ability = rolled_ability
                    mon.moves = rolled_moves
                    type_to_form = {
                        "Normal": "n1",
                        "Ice": "n2",
                        "Rock": "n3",
                        "Steel": "n4",
                        "Psychic": "n5",
                        "Dragon": "n6",
                        "Dark": "n7",
                        "Fairy": "n8",
                    }
                    if rolled_types and rolled_types[0].title() in type_to_form:
                        mon.form = type_to_form[rolled_types[0].title()]
        # Mark initial actives as participants
        try:
            self._mark_participant(self.p1_id)
            self._mark_participant(self.p2_id)
        except Exception:
            pass

    def _mark_participant(self, uid: int) -> None:
        mon = self._active(uid)
        if not mon:
            return
        dbid = getattr(mon, "_db_id", None)
        if uid == self.p1_id:
            self.p1_participants.add(dbid or mon.species)
        else:
            self.p2_participants.add(dbid or mon.species)
        
        # Initialize forms for all Pokémon
        from .engine import check_form_change, on_switch_in
        for mon in self.p1_team + self.p2_team:
            if mon:
                check_form_change(mon, triggered_by="turn_start", field_effects=self.field, battle_state=self)
        
        # Initialize Illusion ability (Zoroark disguises as last party member)
        self._setup_illusion()
        
        # Trigger on-switch-in abilities for starting Pokemon (Imposter, Intimidate, weather, etc.)
        # This happens AFTER Illusion setup so Imposter transforms into the real opponent
        p1_active_mon = self._active(self.p1_id)
        p2_active_mon = self._active(self.p2_id)
        
        # P1's starting Pokemon switches in
        switch_msgs_p1 = on_switch_in(p1_active_mon, p2_active_mon, self.field)
        # Check form changes on switch-in (Schooling, etc.)
        form_msg_p1 = check_form_change(p1_active_mon, triggered_by="on_switch_in", field_effects=self.field, battle_state=self)
        if form_msg_p1:
            switch_msgs_p1.append(f"  {form_msg_p1}")
        
        # P2's starting Pokemon switches in
        switch_msgs_p2 = on_switch_in(p2_active_mon, p1_active_mon, self.field)
        # Check form changes on switch-in (Schooling, etc.)
        form_msg_p2 = check_form_change(p2_active_mon, triggered_by="on_switch_in", field_effects=self.field, battle_state=self)
        if form_msg_p2:
            switch_msgs_p2.append(f"  {form_msg_p2}")
        
        # Store pre-battle messages for display
        self._pre_battle_messages = switch_msgs_p1 + switch_msgs_p2
        
        self._initialize_max_pp()
        self._move_cache: Dict[str, Optional[Dict[str, Any]]] = {}
        self._original_items: Dict[int, Dict[int, Optional[str]]] = {
            self.p1_id: {},
            self.p2_id: {}
        }
        self._initialize_original_items()

        self._pending_weather_messages: List[str] = []

    def _complete_init(self) -> None:
        """Run deferred DB-heavy init (move cache) after 'Battle Started!' is sent."""
        self._cache_all_moves()

    # ---- helpers ----
    def _active(self, uid: int) -> Mon:
        return self.p1_team[self.p1_active] if uid == self.p1_id else self.p2_team[self.p2_active]
    def _opp_active(self, uid: int) -> Mon:
        return self.p2_team[self.p2_active] if uid == self.p1_id else self.p1_team[self.p1_active]
    def team_for(self, uid: int) -> List[Mon]:
        return self.p1_team if uid == self.p1_id else self.p2_team
    def player_name(self, uid: int) -> str:
        """Get the player name for a given user ID."""
        return self.p1_name if uid == self.p1_id else self.p2_name
    
    def _setup_illusion(self) -> None:
        """Set up Illusion ability for both teams (disguise as last party member)."""
        for team in [self.p1_team, self.p2_team]:
            if not team or len(team) == 0:
                continue
            
            # Check each Pokémon for Illusion ability
            for i, mon in enumerate(team):
                if not mon or not mon.ability:
                    continue
                
                ability = normalize_ability_name(mon.ability)
                if ability == "illusion":
                    # Find last non-fainted Pokémon (excluding self)
                    disguise_target = None
                    for j in range(len(team) - 1, -1, -1):
                        if j != i and team[j] and team[j].hp > 0:
                            disguise_target = team[j]
                            break
                    
                    if disguise_target:
                        # Store disguise info on the Pokémon
                        mon._illusion_active = True
                        mon._illusion_species = disguise_target.species
                        mon._illusion_types = disguise_target.types
                        mon._illusion_form = getattr(disguise_target, 'form', None)
                        mon._true_species = mon.species
                        mon._true_types = mon.types
                        mon._true_form = getattr(mon, 'form', None)
                    else:
                        # No valid target, Illusion doesn't activate
                        mon._illusion_active = False
                elif ability == "masquerade":
                    # Masquerade: Adds first type from last non-fainted Pokémon in team (same logic as Illusion)
                    # Find last non-fainted Pokémon (excluding self)
                    disguise_target = None
                    for j in range(len(team) - 1, -1, -1):
                        if j != i and team[j] and team[j].hp > 0:
                            disguise_target = team[j]
                            break
                    
                    if disguise_target:
                        # Add first type from copied mon as a secondary type
                        copied_type = disguise_target.types[0] if disguise_target.types and disguise_target.types[0] else None
                        if copied_type:
                            # Store original types
                            if not hasattr(mon, '_original_types_masquerade'):
                                mon._original_types_masquerade = list(mon.types) if mon.types else []
                            
                            # Add copied type as secondary type (preserve original first type)
                            current_types = list(mon.types) if mon.types else []
                            original_first_type = current_types[0] if len(current_types) > 0 else None
                            original_second_type = current_types[1] if len(current_types) > 1 else None
                            
                            # Check if copied type is already in the Pokémon's types
                            if copied_type in current_types:
                                # If copied type matches first type, keep it as single type
                                if original_first_type == copied_type:
                                    mon.types = (copied_type, None)
                                # If copied type matches second type, keep original first type only
                                elif original_second_type == copied_type:
                                    mon.types = (original_first_type, None)
                                else:
                                    # Shouldn't happen, but keep original types
                                    mon.types = (original_first_type, original_second_type)
                            else:
                                # Copied type is new, add it as secondary type
                                if original_first_type:
                                    # Keep original first type, add copied type as second type
                                    mon.types = (original_first_type, copied_type)
                                else:
                                    # No original type, just set the copied type as first type
                                    mon.types = (copied_type, None)
                            
                            mon._masquerade_active = True
                            mon._masquerade_copied_type = copied_type
    
    def _get_display_mon(self, mon: Mon) -> Mon:
        """Get the display version of a Pokémon (accounting for Illusion)."""
        if not getattr(mon, '_illusion_active', False):
            return mon
        
        # Create a shallow copy with disguised properties
        display_mon = mon
        if mon._illusion_active:
            # Temporarily override display properties (for UI/rendering only)
            # The actual mon object is unchanged for battle calculations
            pass
        
        return display_mon
    
    def _break_illusion(self, mon: Mon) -> Optional[str]:
        """Break Illusion when Pokémon takes direct damage. Returns message if broken."""
        if not getattr(mon, '_illusion_active', False):
            return None
        
        # Reveal true identity
        mon._illusion_active = False
        true_species = getattr(mon, '_true_species', mon.species)
        disguise_species = getattr(mon, '_illusion_species', '')
        
        if disguise_species:
            return f"{disguise_species}'s illusion wore off! It's actually {true_species}!"
        return None

    def _reconcile_special_weather(self, immediate_log: Optional[List[str]] = None) -> None:
        """Ensure special weather states are only active if a source is present."""
        special = getattr(self.field, 'special_weather', None)
        if not special:
            return

        flag_map = {
            "heavy-rain": "sets_heavy_rain",
            "harsh-sunlight": "sets_harsh_sunlight",
            "strong-winds": "sets_strong_winds"
        }
        required_flag = flag_map.get(special)
        if not required_flag:
            return


        # Check all active Pokémon for the required ability
        for mon in [self._active(self.p1_id), self._active(self.p2_id)]:
            if mon and mon.hp > 0 and mon.ability:
                ability_norm = normalize_ability_name(mon.ability)
                ability_data = get_ability_effect(ability_norm)
                if ability_data.get(required_flag):
                    # Keep lock metadata up to date
                    self.field.weather_lock_owner = id(mon)
                    self.field.weather_lock = ability_norm
                    return

        cleared = clear_special_weather(self.field)
        if cleared:
            message_map = {
                "heavy-rain": "The heavy rain disappeared!",
                "harsh-sunlight": "The extremely harsh sunlight faded!",
                "strong-winds": "The mysterious strong winds dissipated!"
            }
            msg = message_map.get(cleared, "The special weather faded.")
            if immediate_log is not None:
                immediate_log.append(msg)
            else:
                self._pending_weather_messages.append(msg)

    # ---- PP/Choice internals ----
    def _get_mon_key(self, uid: int, mon: Optional[Mon] = None) -> Tuple[int, int]:
        """Get the (user_id, team_index) key for a Pokemon.
        If mon is provided, finds its index in the team. Otherwise uses active Pokemon."""
        if mon is None:
            mon = self._active(uid)
        
        team = self.team_for(uid)
        slot = getattr(mon, "_battle_slot", None)
        if isinstance(slot, int) and 0 <= slot < len(team):
            team_index = int(slot)
        else:
            team_index = -1
            for i, cand in enumerate(team):
                if cand is mon:
                    team_index = i
                    break
            if team_index < 0:
                # Fallback: use active index if mon not found
                team_index = self.p1_active if uid == self.p1_id else self.p2_active
        
        return (uid, team_index)
    
    def _ensure_pp_loaded(self, uid: int, mon: Optional[Mon] = None) -> None:
        """Ensure PP dictionary has entries for a Pokemon's four moves.
        Transformed Pokemon (Transform/Imposter) get 5 PP per move."""
        if mon is None:
            mon = self._active(uid)
        
        moves = (mon.moves or ["Tackle"])[:4] if mon.moves else ["Tackle"]
        key = self._get_mon_key(uid, mon)
        
        if key not in self._pp:
            self._pp[key] = {}
        
        store = self._pp[key]
        
        # Check if this Pokemon transformed (Transform move or Imposter ability)
        is_transformed = getattr(mon, '_transformed', False) or getattr(mon, '_imposter_transformed', False)
        
        for m in moves:
            canonical = _canonical_move_name(m)
            if canonical not in store:
                if is_transformed:
                    # Transformed Pokemon get 5 PP per move (or max if less than 5)
                    base_pp = _base_pp(m, generation=self.gen)
                    loaded_pp = min(5, base_pp) if base_pp < 5 else 5
                else:
                    # Normal Pokemon start with their base PP (database value). DB overrides (moves_pp) may replace this.
                    loaded_pp = _base_pp(m, generation=self.gen)
                store[canonical] = loaded_pp

    def _pp_left(self, uid: int, move_name: str, mon: Optional[Mon] = None) -> int:
        """Get remaining PP for a move. If mon is None, uses active Pokemon."""
        # Dummy battles (/dummy): only the dummy side (negative ID) gets infinite PP.
        if self.is_dummy_battle:
            if uid < 0:
                return 999
        self._ensure_pp_loaded(uid, mon)
        key = self._get_mon_key(uid, mon)
        store = self._pp.get(key, {}) or {}
        canonical = _canonical_move_name(move_name)
        left = store.get(canonical) or store.get(move_name)
        if left is None:
            norm_name = _norm_pp_move_key(move_name)
            left = store.get(norm_name)
            if left is None:
                for raw_key, raw_val in store.items():
                    if _norm_pp_move_key(raw_key) == norm_name or _canonical_move_name(raw_key) == canonical:
                        left = raw_val
                        break
        try:
            return int(left) if left is not None else int(_base_pp(move_name, generation=self.gen))
        except Exception:
            return int(_base_pp(move_name, generation=self.gen))

    def _spend_pp(self, uid: int, move_name: str, target: Any = None, move_data: Any = None, mon: Optional[Mon] = None) -> None:
        """
        Spend PP for a move. Handles Pressure ability (extra PP cost).
        
        Args:
            uid: User ID of the Pokemon using the move
            move_name: Name of the move being used
            target: Target Pokemon (for Pressure check)
            move_data: Move data dict (for target code check)
            mon: The Pokemon using the move (if None, uses active Pokemon)
        """
        if move_name.lower() == "struggle":
            return  # Struggle has no PP
        
        # Dummy battles: only dummy side gets infinite PP
        if self.is_dummy_battle and uid < 0:
            return  # Don't spend PP for dummy opponent
        
        if mon is None:
            mon = self._active(uid)
        
        self._ensure_pp_loaded(uid, mon)
        key = self._get_mon_key(uid, mon)
        if key not in self._pp:
            self._pp[key] = {}
        store = self._pp[key]
        canonical = _canonical_move_name(move_name)
        resolved_key = canonical if canonical in store else move_name if move_name in store else None
        if resolved_key is None:
            norm_name = _norm_pp_move_key(move_name)
            resolved_key = norm_name if norm_name in store else canonical
            for raw_key in store.keys():
                if _norm_pp_move_key(raw_key) == norm_name or _canonical_move_name(raw_key) == canonical:
                    resolved_key = raw_key
                    break
        left = store.get(resolved_key)
        if left is None:
            left = _base_pp(move_name, generation=self.gen)
        
        # Calculate PP cost (1 normally, 2+ if Pressure is active)
        pp_cost = 1
        
        # Coercion: Opponent with Coercion adds 1 extra PP cost
        opponent_uid_coercion = self.p2_id if uid == self.p1_id else self.p1_id
        active_opponent_coercion = self._active(opponent_uid_coercion)
        if active_opponent_coercion and active_opponent_coercion.hp > 0:
            from .abilities import normalize_ability_name, get_ability_effect
            opponent_ability_coercion = normalize_ability_name(active_opponent_coercion.ability or "")
            opponent_ability_data_coercion = get_ability_effect(opponent_ability_coercion)
            if opponent_ability_data_coercion.get("steals_pp_on_opponent_move"):
                # Coercion adds 1 extra PP cost
                pp_cost += 1
        
        # Check for Pressure ability on opponents
        # Pressure: When a move targets a Pokemon with Pressure, it uses 1 extra PP
        # Applies even if move misses, is blocked, or is ineffective
        if move_data:
            from .abilities import normalize_ability_name, get_ability_effect
            generation = getattr(self.field, 'generation', 9) if hasattr(self, 'field') else 9
            move_target = move_data.get("target", "").lower()
            move_name_lower = move_name.lower().replace(" ", "-")
            
            # Get opponent team to check for Pressure
            opponent_team = self.p2_team if uid == self.p1_id else self.p1_team
            
            # Count how many opponents have Pressure that would be affected
            pressure_count = 0
            
            # Check all opponents for Pressure (Gen V+ only checks opponents, Gen III-IV checks all)
            for opponent in opponent_team:
                if opponent and opponent.hp > 0:
                    opponent_ability = normalize_ability_name(opponent.ability or "")
                    opponent_ability_data = get_ability_effect(opponent_ability)
                    
                    if opponent_ability_data.get("pressure"):
                        # Check if this move would target this opponent
                        applies_to_this_opponent = False
                        
                        field_target_codes = {"all", "all-pokemon", "all-other-pokemon", "field", "entire-field"}
                        
                        # Gen V+: Special cases - Imprison and Snatch are self-targeting but still affected
                        special_self_targeting = {"imprison", "snatch"} if generation >= 5 else set()
                        is_special_self_targeting = move_name_lower in special_self_targeting
                        
                        # Apply Pressure if:
                        # 1. Move targets the Pokemon directly (and this is the target)
                        if move_target in {"selected-pokemon", "selected-pokemon-me-first"}:
                            if target == opponent:
                                applies_to_this_opponent = True
                        
                        # 2. Move targets the field (Rain Dance, etc.) - always applies
                        elif move_target in field_target_codes:
                            applies_to_this_opponent = True
                        
                        # 3. Move targets all opponents - applies to all opponents
                        elif move_target in {"all-opponents", "opponent-side"}:
                            applies_to_this_opponent = True
                        
                        # 4. Special self-targeting moves (Imprison, Snatch in Gen V+)
                        elif is_special_self_targeting:
                            applies_to_this_opponent = True
                        
                        # 5. Gen III-IV: Also affects moves targeting allies or all other Pokemon
                        elif generation < 5 and move_target in {"all-other-pokemon", "ally-side"}:
                            applies_to_this_opponent = True
                        
                        # Gen V+: Special case for Spikes, Stealth Rock, Toxic Spikes (but not Sticky Web)
                        if generation >= 5:
                            hazard_moves = {"spikes", "stealth-rock", "toxic-spikes"}
                            if move_name_lower in hazard_moves:
                                applies_to_this_opponent = True
                        
                        # Gen V+: Tera Blast is affected even if Pressure Pokemon is not the target
                        if generation >= 5 and move_name_lower == "tera-blast":
                            applies_to_this_opponent = True
                        
                        if applies_to_this_opponent:
                            pressure_count += 1
            
            # Each Pokemon with Pressure adds 1 extra PP
            if pressure_count > 0:
                pp_cost = 1 + pressure_count
        
        # Spend PP (can't go below 0). Store under canonical form only.
        new_left = max(0, int(left) - int(pp_cost))
        store[canonical] = new_left
        if resolved_key != canonical:
            store[resolved_key] = new_left  # Update old key if we looked up via different format
    
    def _initialize_max_pp(self) -> None:
        """Initialize all moves with max PP for PVP battles."""
        for uid in [self.p1_id, self.p2_id]:
            team = self.team_for(uid)
            for mon in team:
                if mon:
                    # Ensure key is a tuple (user_id, team_index)
                    key = self._get_mon_key(int(uid), mon)
                    if key not in self._pp:
                        self._pp[key] = {}
                    # Ensure moves is a list of strings
                    if not mon.moves or not isinstance(mon.moves, list):
                        moves = ["Tackle"]
                    else:
                        # Filter to only string moves (safety check)
                        moves = [str(m) for m in mon.moves[:4] if m and isinstance(m, (str, int))]
                        if not moves:
                            moves = ["Tackle"]
                    for move in moves:
                        move_str = str(move) if move else "Tackle"
                        canonical = _canonical_move_name(move_str)
                        # Use base PP as starting pool; it will be overridden by stored moves_pp if available.
                        start_pp = _base_pp(move_str, generation=self.gen)
                        self._pp[key][canonical] = start_pp
    
    def _cache_all_moves(self) -> None:
        """Pre-cache all move data for all Pokémon in the battle. Uses db_cache when available, then DB."""
        from .moves_loader import _normalize_move_name, _row_to_dict
        import copy
        import json

        all_moves = set()
        for mon in self.p1_team + self.p2_team:
            if mon and mon.moves:
                for move in mon.moves:
                    if move and isinstance(move, (str, int)):
                        move_str = str(move).strip()
                        if move_str:
                            all_moves.add(move_str)
        all_moves.add("Struggle")
        all_moves.add("Tackle")

        gen_by_move_id: Dict[Any, Any] = {}
        if _lib_db_cache and self.gen is not None:
            gs = _lib_db_cache.get_cached_move_generation_stats()
            if gs:
                for r in gs:
                    mid, gen = r.get("move_id"), r.get("generation")
                    if mid is not None and gen == self.gen:
                        gen_by_move_id[mid] = r

        def _apply_gen(move_dict: Dict[str, Any], gen_row: Dict) -> None:
            if gen_row.get("pp") is not None:
                move_dict["pp"] = gen_row["pp"]
            if gen_row.get("power") is not None:
                move_dict["power"] = gen_row["power"]
            if gen_row.get("accuracy") is not None:
                move_dict["accuracy"] = gen_row["accuracy"]
            if gen_row.get("type") is not None:
                move_dict["type"] = gen_row["type"]
            if gen_row.get("damage_class") is not None:
                move_dict["damage_class"] = gen_row["damage_class"]
                move_dict["category"] = gen_row["damage_class"]
            meta = move_dict.get("meta") or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            if gen_row.get("makes_contact") is not None:
                move_dict["contact"] = bool(gen_row["makes_contact"])
                meta["makes_contact"] = bool(gen_row["makes_contact"])
            if gen_row.get("priority") is not None:
                move_dict["priority"] = gen_row["priority"]
                meta["priority"] = gen_row["priority"]
            move_dict["meta"] = meta

        missing: set = set()
        for move in all_moves:
            norm = _normalize_move_name(move)
            base = None
            if _lib_db_cache:
                base = _lib_db_cache.get_cached_move(norm) or _lib_db_cache.get_cached_move(move)
            if base is not None:
                d = copy.deepcopy(base) if isinstance(base, dict) else dict(base)
                if isinstance(d.get("meta"), str):
                    try:
                        d["meta"] = json.loads(d["meta"])
                    except Exception:
                        d["meta"] = {}
                gen_row = gen_by_move_id.get(d.get("id")) if self.gen is not None else None
                if gen_row:
                    _apply_gen(d, gen_row)
                name = d.get("name") or move
                self._move_cache[name.lower()] = d
                self._move_cache[norm] = d
                self._move_cache[name.replace(" ", "-").lower()] = d
                self._move_cache[name.replace("-", " ").lower()] = d
                continue
            missing.add(norm)

        if not missing:
            for move in all_moves:
                norm = _normalize_move_name(move)
                if norm not in self._move_cache and move.lower() not in self._move_cache:
                    self._move_cache[norm] = None
                    self._move_cache[move.lower()] = None
            return

        from .db_pool import get_connection
        norm_list = [_normalize_move_name(m) for m in all_moves]
        to_fetch = [n for n in norm_list if n not in self._move_cache]
        to_fetch = list(dict.fromkeys(to_fetch))
        db_gen_by_move_id: Dict[Any, Any] = {}

        with get_connection() as con:
            if to_fetch:
                ph = ",".join(["?"] * len(to_fetch))
                rows = con.execute(
                    f"SELECT * FROM moves WHERE LOWER(REPLACE(name, ' ', '-')) IN ({ph})",
                    tuple(to_fetch),
                ).fetchall()
                if self.gen is not None and rows:
                    move_ids = [r["id"] for r in rows]
                    ph2 = ", ".join(["(?, ?)"] * len(move_ids))
                    params = [x for mid in move_ids for x in (mid, self.gen)]
                    gen_rows = con.execute(
                        f"""SELECT move_id, pp, power, accuracy, type, damage_class, makes_contact, priority
                            FROM move_generation_stats WHERE (move_id, generation) IN ({ph2})""",
                        params,
                    ).fetchall()
                    for gr in gen_rows:
                        db_gen_by_move_id[gr["move_id"]] = gr
                gen_lookup = {**gen_by_move_id, **db_gen_by_move_id}
                for row in rows:
                    move_dict = _row_to_dict(row)
                    move_name = row["name"]
                    normalized_name = _normalize_move_name(move_name)
                    gen_row = gen_lookup.get(row["id"]) if self.gen else None
                    if gen_row:
                        _apply_gen(move_dict, gen_row)
                    self._move_cache[move_name.lower()] = move_dict
                    self._move_cache[normalized_name] = move_dict
                    self._move_cache[move_name.replace(" ", "-").lower()] = move_dict
                    self._move_cache[move_name.replace("-", " ").lower()] = move_dict

        for move in all_moves:
            norm = _normalize_move_name(move)
            if norm not in self._move_cache and move.lower() not in self._move_cache:
                self._move_cache[norm] = None
                self._move_cache[move.lower()] = None
    
    def get_cached_move(self, move_name: str) -> Optional[Dict[str, Any]]:
        """Get move data from battle cache, falling back to database if not cached."""
        if not move_name or not isinstance(move_name, str):
            return None
        
        # Try to get from cache first
        normalized = move_name.lower().replace(" ", "-")
        cached = self._move_cache.get(normalized) or self._move_cache.get(move_name.lower())
        
        if cached is not None:
            return cached
        
        # If not in cache (shouldn't happen for moves in battle, but handle gracefully)
        # Use the cache-aware helper (recursion-safe) to fetch and store.
        move_data = _get_move_with_cache(move_name, battle_state=self, generation=self.gen)
        # Cache it for future use
        if move_data:
            self._move_cache[normalized] = move_data
            self._move_cache[move_name.lower()] = move_data
        else:
            self._move_cache[normalized] = None
            self._move_cache[move_name.lower()] = None
        
        return move_data
    
    def _initialize_original_items(self) -> None:
        """Store original items for all Pokémon in both teams (for restoration after battle)."""
        for team, team_id in [(self.p1_team, self.p1_id), (self.p2_team, self.p2_id)]:
            for i, mon in enumerate(team):
                if mon:
                    # Store original item (None if no item)
                    self._original_items[team_id][i] = getattr(mon, 'item', None)
    
    def restore_items(self) -> None:
        """Restore all original items to Pokémon after battle ends."""
        for team, team_id in [(self.p1_team, self.p1_id), (self.p2_team, self.p2_id)]:
            for i, mon in enumerate(team):
                if mon and i in self._original_items[team_id]:
                    # Restore original item (even if it was None)
                    mon.item = self._original_items[team_id][i]
                    # Also clean up any temporary battle storage
                    if hasattr(mon, '_original_item_battle'):
                        delattr(mon, '_original_item_battle')
                    if hasattr(mon, '_consumed_item'):
                        delattr(mon, '_consumed_item')
                    if hasattr(mon, '_last_consumed_berry'):
                        delattr(mon, '_last_consumed_berry')

    def restore_terastallization(self) -> None:
        """Revert Terastallization state for all Pokémon."""
        for team in (self.p1_team, self.p2_team):
            for mon in team:
                if mon:
                    revert_terastallization(mon)

    def restore_mega_evolution(self) -> None:
        """Revert Mega Evolution state for all Pokémon."""
        for team in (self.p1_team, self.p2_team):
            for mon in team:
                if mon:
                    revert_mega_evolution(mon)

    def restore_abilities(self) -> None:
        """Restore battle-temporary ability changes (e.g., Trace, Mummy) to original ability."""
        for team in (self.p1_team, self.p2_team):
            for mon in team:
                if mon is None:
                    continue
                original_ability = getattr(mon, "_original_ability", None)
                if original_ability:
                    mon.ability = original_ability
                # Reset Trace one-switch activation flag so next battle starts clean.
                if hasattr(mon, "_trace_activated_this_switch"):
                    try:
                        delattr(mon, "_trace_activated_this_switch")
                    except Exception:
                        pass

    def _choice_move(self, uid: int) -> Optional[str]:
        return self._choice_locked.get(uid)

    def _set_choice_lock_if_needed(self, uid: int, move_name: str) -> None:
        """If holding a Choice item OR has Gorilla Tactics, lock to that move (any move, not just damaging)."""
        mon = self._active(uid)
        # Don't lock if item was just received this turn (Trick/Switcheroo delay)
        has_choice_item = _has_choice_item(mon) and not getattr(mon, '_item_just_received', False)
        
        # Check for Gorilla Tactics ability (also locks moves like Choice items)
        has_gorilla_tactics = False
        if hasattr(mon, 'ability') and mon.ability:
            ability = normalize_ability_name(mon.ability)
            ability_data = get_ability_effect(ability)
            if ability_data.get("choice_lock"):
                has_gorilla_tactics = True
        
        if has_choice_item or has_gorilla_tactics:
            self._choice_locked[uid] = move_name

    def _clear_choice_lock_on_switch(self, uid: int) -> None:
        self._choice_locked[uid] = None
    
    def _apply_pending_switch_effects(self, uid: int, mon: Mon) -> List[str]:
        messages: List[str] = []
        if not mon:
            return messages
        
        if self._pending_healing_wish.get(uid):
            healed = mon.max_hp - mon.hp
            if healed > 0:
                mon.hp = mon.max_hp
                messages.append(f"{mon.species} was rejuvenated by the healing wish! (+{healed} HP)")
            if mon.status:
                mon.status = None
                messages.append(f"{mon.species}'s status was cured by the healing wish!")
            self._pending_healing_wish[uid] = False
        
        if self._pending_lunar_dance.get(uid):
            healed = mon.max_hp - mon.hp
            if healed > 0:
                mon.hp = mon.max_hp
                messages.append(f"{mon.species} was healed by the mystical lunar dance! (+{healed} HP)")
            if mon.status:
                mon.status = None
                messages.append(f"{mon.species}'s status was cured by the lunar dance!")
            try:
                self._ensure_pp_loaded(uid, mon)
                key = self._get_mon_key(uid, mon)
                moves = (mon.moves or ["Tackle"])[:4] if mon.moves else ["Tackle"]
                if key not in self._pp:
                    self._pp[key] = {}
                for move in moves:
                    self._pp[key][_canonical_move_name(move)] = _max_pp(move, generation=self.gen)
                messages.append(f"{mon.species}'s moves had their PP restored!")
            except Exception:
                pass
            self._pending_lunar_dance[uid] = False
        
        return messages
    
    def _clear_choice_lock_on_dynamax(self, uid: int) -> None:
        """Clear Choice lock when Dynamax activates (Dynamax bypasses Choice restrictions)."""
        self._choice_locked[uid] = None

    def _apply_protection_counter_effect(
        self,
        defender: Mon,
        attacker: Mon,
        attacker_id: int,
        move_name: str,
        log: List[str]
    ) -> None:
        """Apply King's Shield / Spiky Shield backlash when a contact move is blocked."""
        protection_move = getattr(defender, '_protection_move', None)
        if not protection_move:
            return

        # Winter's Aegis special Fire move handling (not contact-dependent)
        if protection_move == "winters-aegis":
            move_data = _get_move_with_cache(move_name, battle_state=self, generation=self.gen)
            move_type = (move_data.get("type") or "Normal").title() if move_data else "Normal"
            if move_type == "Fire":
                # Fire moves melt the shield, activating Water Sport and making move unusable until switch
                # Gen 8+: Water Sport cannot be activated (move is banned)
                defender._winters_aegis_melted = True
                if self.gen < 8:
                    # Activate Water Sport effect (Gen 3-7 only)
                    # Gen 3-4: Until switch, Gen 5+: 5 turns
                    self.field.water_sport = True
                    if self.gen <= 4:
                        self.field.water_sport_turns = 0  # 0 = infinite (until switch)
                        self.field.water_sport_user = id(defender)  # Track user for switch check
                    else:
                        self.field.water_sport_turns = 5
                        self.field.water_sport_user = None
                    log.append(f"The fire melted {defender.species}'s Winter's Aegis!")
                    log.append(f"Water Sport was activated!")
                else:
                    # Gen 8+: Just melt the shield, don't activate Water Sport
                    log.append(f"The fire melted {defender.species}'s Winter's Aegis!")
                return

        # Use makes_contact function for accurate detection
        is_contact_move = makes_contact(move_name, battle_state=self, generation=self.gen)
        if not is_contact_move:
            return

        ability = normalize_ability_name(getattr(attacker, 'ability', "") or "")
        ability_data = get_ability_effect(ability)
        if ability_data.get("contact_moves_dont_make_contact"):
            return

        generation = getattr(self.field, 'generation', 9)

        if protection_move == "kings-shield":
            # Gen VI-VII: -2 Attack; Gen VIII: -1. Contact multistrike: drop applies only once per move.
            if getattr(attacker, '_kings_shield_atk_drop_applied_this_turn', False):
                pass  # Already applied this turn (e.g. multistrike contact move)
            else:
                drop_stage = -2 if generation <= 7 else -1
                drop_msgs = modify_stages(attacker, {"atk": drop_stage}, caused_by_opponent=True, field_effects=self.field)
                if drop_msgs:
                    for drop_msg in drop_msgs:
                        log.append(drop_msg)
                    attacker._stats_lowered_this_turn = True
                    attacker._kings_shield_atk_drop_applied_this_turn = True
        elif protection_move == "spiky-shield":
            if ability_data.get("no_indirect_damage"):
                return
            damage = max(1, attacker.max_hp // 8)
            old_hp = attacker.hp
            attacker.hp = max(0, attacker.hp - damage)
            actual_damage = old_hp - attacker.hp
            if actual_damage > 0:
                log.append(f"{attacker.species} was hurt by the spikes! (-{actual_damage} HP)")
                if attacker.hp <= 0:
                    log.append(f"**{attacker.species}** fainted!")
                    self._reconcile_special_weather(immediate_log=log)
                    from .engine import release_octolock
                    release_octolock(attacker)
                    team = self.team_for(attacker_id)
                    alive_count = sum(1 for mon in team if mon and mon.hp > 0)
                    if alive_count == 0:
                        self.winner = self.p2_id if attacker_id == self.p1_id else self.p1_id
        elif protection_move == "baneful-bunker":
            if inflict_status(attacker, "psn", attacker=defender, field_effects=self.field):
                log.append(f"{attacker.species} was poisoned by the bunker!")
        elif protection_move == "burning-bulwark":
            if inflict_status(attacker, "brn", attacker=defender, field_effects=self.field):
                log.append(f"{attacker.species} was burned by the bulwark!")
        elif protection_move == "silk-trap":
            drop_msgs = modify_stages(attacker, {"spe": -1}, caused_by_opponent=True, field_effects=self.field)
            if drop_msgs:
                for drop_msg in drop_msgs:
                    log.append(drop_msg)
                attacker._stats_lowered_this_turn = True
        elif protection_move == "obstruct":
            drop_msgs = modify_stages(attacker, {"defn": -2}, caused_by_opponent=True, field_effects=self.field)
            if drop_msgs:
                for drop_msg in drop_msgs:
                    log.append(drop_msg)
                attacker._stats_lowered_this_turn = True
        elif protection_move == "winters-aegis":
            # Winter's Aegis: Contact moves lower opponent's Speed by 1
            drop_msgs = modify_stages(attacker, {"spe": -1}, caused_by_opponent=True, field_effects=self.field)
            if drop_msgs:
                for drop_msg in drop_msgs:
                    log.append(drop_msg)
                attacker._stats_lowered_this_turn = True

    def _execute_move_action(
        self,
        uid: int,
        act: Dict[str, Any],
        atk_choice: Dict[str, Any],
        dfn_choice: Dict[str, Any],
        log: List[str],
        *,
        order: Optional[List[int]] = None,
        actions: Optional[Dict[int, Dict[str, Any]]] = None,
        index: Optional[int] = None,
        remaining_move_actions: Optional[int] = None,
        defender_override: Optional[Any] = None
    ) -> None:
        if act.get("_processed"):
            return

        atk = self._active(uid)
        dfn = defender_override if defender_override is not None else self._opp_active(uid)
        setattr(atk, '_player_id', uid)

        if atk.hp <= 0 or (dfn and dfn.hp <= 0):
            act["_processed"] = True
            return

        atk_side = self.p1_side if uid == self.p1_id else self.p2_side
        dfn_side = self.p2_side if uid == self.p1_id else self.p1_side

        # Get the move name early to check if it's Sleep Talk or Snore
        is_attack_turn, charged_move = execute_attack_turn(atk)
        if is_attack_turn and charged_move:
            chosen = str(charged_move) if charged_move else "Tackle"
        else:
            # Ensure chosen is always a string (handle case where value might be a dict)
            move_value = act.get("value")
            if isinstance(move_value, dict):
                # If it's a dict, extract the name
                chosen = str(move_value.get("name", move_value.get("value", "Tackle")))
            elif move_value:
                chosen = str(move_value)
            else:
                chosen = "Tackle"

        can_move_result, move_reason = can_pokemon_move(atk, self.field, move_name=chosen)
        pending_block_reason: Optional[str] = None
        if not can_move_result:
            reason_lower = (move_reason or "").lower()
            if "frozen" in reason_lower:
                pending_block_reason = move_reason
            else:
                atk_name = _format_pokemon_name(atk)
                log.append(f"**{atk_name}:** {move_reason}")
                reset_rollout(atk)
                act["_processed"] = True
                return
        elif move_reason:
            atk_name = _format_pokemon_name(atk)
            log.append(f"**{atk_name}:** {move_reason}")

        if is_attack_turn and charged_move:
            log.append(f"**{atk.species} unleashes {chosen}!**")

        rollout_locked_move = getattr(atk, 'rollout_move', None)
        if rollout_locked_move and getattr(atk, 'rollout_turns_remaining', 0) > 0:
            forced_move_name = rollout_locked_move.replace("-", " ").title()
            if self._pp_left(uid, forced_move_name) > 0:
                chosen = forced_move_name
            else:
                chosen = "Struggle"
                reset_rollout(atk)

        if hasattr(atk, 'rampage_move') and atk.rampage_move and hasattr(atk, 'rampage_turns_remaining') and atk.rampage_turns_remaining > 0:
            rampage_move_name = atk.rampage_move.replace("-", " ").title()
            if self._pp_left(uid, rampage_move_name) > 0:
                chosen = rampage_move_name
            else:
                chosen = "Struggle"
        elif locked := self._choice_move(uid):
            if self._pp_left(uid, locked) > 0:
                chosen = locked
            else:
                chosen = "Struggle"

        if chosen.lower() != "struggle" and self._pp_left(uid, chosen) <= 0:
            chosen = "Struggle"
            reset_rollout(atk)

        move_lower = chosen.lower().replace(" ", "-")
        
        # === EARLY TAUNT CHECK: Block status moves if taunted (check before any other processing) ===
        taunt_pending = getattr(atk, "_taunt_pending", False)
        is_taunted = (atk.taunted and (atk.taunt_turns > 0 or taunt_pending)) or taunt_pending
        is_z_move = atk_choice.get("z_move") or getattr(atk, '_is_z_move', False)
        
        if is_taunted and not is_z_move and move_lower != "struggle":
            move_data_early = _get_move_with_cache(chosen, battle_state=self, generation=self.gen)
            move_effect_early = get_move_secondary_effect(chosen) or {}
            move_category_early = ""
            move_power_raw_early = None
            if move_data_early:
                move_category_early = (move_data_early.get("damage_class") or move_data_early.get("category") or "").lower()
                if "power" in move_data_early:
                    move_power_raw_early = move_data_early.get("power")
            move_power_val_early = move_power_raw_early if isinstance(move_power_raw_early, (int, float)) else 0
            variable_power_early = bool(move_effect_early.get("variable_power"))
            is_status_move_early = move_category_early == "status" or (move_power_val_early <= 0 and not variable_power_early)
            
            # Gen V+: Me First is not affected by Taunt
            is_me_first_early = move_lower == "me-first"
            from .generation import get_generation
            generation_early = get_generation(field_effects=self.field) if hasattr(self, 'field') else 9
            
            if is_status_move_early and not (generation_early >= 5 and is_me_first_early):
                atk_name = _format_pokemon_name(atk)
                move_name = _format_move_name(chosen)
                log.append(f"**{atk_name}** used **{move_name}**!\nBut it failed!")
                atk._moved_this_turn = True
                atk._last_move_failed = True
                if taunt_pending:
                    atk._taunt_pending = False
                    if hasattr(atk, "_taunt_applied_turn"):
                        atk._taunt_applied_turn = None
                act["_processed"] = True
                return
        
        move_data = _get_move_with_cache(chosen, battle_state=self, generation=self.gen)
        effect_data = get_move_secondary_effect(move_lower)

        if pending_block_reason and not can_move_result:
            effect_data = get_move_secondary_effect(chosen)
            if effect_data.get("thaws_user") and getattr(atk, 'status', None) == "frz":
                atk.status = None
                log.append(f"**{atk.species}:** thawed out!")
                can_move_result = True
                pending_block_reason = None
            else:
                log.append(f"**{atk.species}:** {pending_block_reason}")
                reset_rollout(atk)
                act["_processed"] = True
                return

        # Get target for Pressure check (move_data already retrieved above)
        target = dfn if dfn else (self._active(self.p2_id) if uid == self.p1_id else self._active(self.p1_id))
        self._spend_pp(uid, chosen, target=target, move_data=move_data)

        if chosen.lower() != "struggle":
            self._set_choice_lock_if_needed(uid, chosen)

        if remaining_move_actions is None:
            if order is not None and actions is not None and index is not None:
                remaining_move_actions = sum(1 for j in range(index + 1, len(order))
                                             if actions.get(order[j], {}).get("kind") == "move")
            else:
                remaining_move_actions = 0

        is_moving_last = (remaining_move_actions == 0)

        if move_lower == "max-guard":
            success, guard_msg = handle_max_guard(atk, self.field, is_moving_last)
            atk_name = _format_pokemon_name(atk)
            move_name = _format_move_name(chosen)
            log.append(f"**{atk_name}** used **{move_name}**!")
            log.append(f"  {guard_msg}")
            _record_last_move(atk, chosen, battle_state=self)
            reset_rollout(atk)
            act["_processed"] = True
            return

        if move_lower in {"protect", "detect", "spiky-shield", "baneful-bunker", "kings-shield", "obstruct", "winters-aegis", "silk-trap", "burning-bulwark"}:
            protected, protect_msg = handle_protect(atk, chosen, self.field, is_moving_last)
            atk_name = _format_pokemon_name(atk)
            move_name = _format_move_name(chosen)
            log.append(f"**{atk_name}** used **{move_name}**!")
            log.append(protect_msg)
            if protected:
                # Z-Protect: Reset all lowered stats
                if move_lower == "protect":
                    is_z_move = atk_choice.get("z_move", False) or getattr(atk, '_is_z_move', False)
                    if is_z_move:
                        from .engine import modify_stages
                        stat_resets = {}
                        for stat in ["atk", "defn", "spa", "spd", "spe", "accuracy", "evasion"]:
                            if atk.stages.get(stat, 0) < 0:
                                stat_resets[stat] = -atk.stages.get(stat, 0)
                        if stat_resets:
                            z_msgs = modify_stages(atk, stat_resets, caused_by_opponent=False, field_effects=self.field)
                            for z_msg in z_msgs:
                                log.append(f"  {z_msg}")
                # Z-Detect: +1 Evasion
                elif move_lower == "detect":
                    is_z_move = atk_choice.get("z_move", False) or getattr(atk, '_is_z_move', False)
                    if is_z_move:
                        from .engine import modify_stages
                        z_msgs_detect = modify_stages(atk, {"evasion": 1}, caused_by_opponent=False, field_effects=self.field)
                        for z_msg in z_msgs_detect:
                            log.append(f"  {z_msg}")
                _record_last_move(atk, chosen, battle_state=self)
                reset_rollout(atk)
                act["_processed"] = True
                return
            else:
                atk.consecutive_protects = 0
        elif move_lower == "endure":
            from .battle_flow import handle_endure
            success, endure_msg = handle_endure(atk, self.field, is_moving_last)
            
            # Z-Endure: Reset all lowered stats
            is_z_move = atk_choice.get("z_move", False) or getattr(atk, '_is_z_move', False)
            if is_z_move:
                from .engine import modify_stages
                stat_resets = {}
                for stat in ["atk", "defn", "spa", "spd", "spe", "accuracy", "evasion"]:
                    if atk.stages.get(stat, 0) < 0:
                        stat_resets[stat] = -atk.stages.get(stat, 0)
                if stat_resets:
                    z_msgs = modify_stages(atk, stat_resets, caused_by_opponent=False, field_effects=self.field)
                    for z_msg in z_msgs:
                        log.append(f"  {z_msg}")
            atk_name = _format_pokemon_name(atk)
            move_name = _format_move_name(chosen)
            log.append(f"**{atk_name}** used **{move_name}**!")
            log.append(f"  {endure_msg}")
            _record_last_move(atk, chosen, battle_state=self)
            act["_processed"] = True
            return
        else:
            if move_lower not in {"protect", "detect"}:
                atk.consecutive_protects = 0

        if dfn and dfn.protected_this_turn:
            # === Z-MOVES: Deal 25% damage through protection (damaging) or apply Z-Power effect (status) ===
            is_z_move = atk_choice.get("z_move", False) or getattr(atk, '_is_z_move', False)
            if is_z_move:
                # Check if this is a damaging or status Z-Move
                # Use top-level get_move import (don't shadow)
                move_data = _get_move_with_cache(chosen, battle_state=self, generation=self.gen if hasattr(self, 'gen') else None)
                is_damaging_z_move = move_data and move_data.get("category") != "status" if move_data else True
                
                if is_damaging_z_move:
                    # Damaging Z-Move: Deal 25% damage through protection
                    # Mark the move to deal reduced damage
                    atk._z_move_vs_protection = True
                    atk_name = _format_pokemon_name(atk)
                    move_name = _format_move_name(chosen)
                    log.append(f"**{atk_name}** used **{move_name}**!")
                    dfn_name = _format_pokemon_name(dfn)
                    log.append(f"{dfn_name} protected itself, but the Z-Move broke through!")
                    # Continue to execute the move (damage will be reduced later)
                else:
                    # Status Z-Move: Apply Z-Power effect even if blocked
                    # Z-Power effects are applied in apply_move, so we continue
                    atk_name = _format_pokemon_name(atk)
                    move_name = _format_move_name(chosen)
                    log.append(f"**{atk_name}** used **{move_name}**!")
                    dfn_name = _format_pokemon_name(dfn)
                    log.append(f"But {dfn_name} protected itself!")
                    # Status Z-Moves still apply their Z-Power effect even when blocked
                    # This is handled in apply_move in engine.py
                    # Continue to execute so Z-Power effect can be applied
            
            move_effect = get_move_secondary_effect(chosen)
            move_data = _get_move_with_cache(chosen, battle_state=self, generation=self.gen)
            makes_contact: bool = False
            if move_data:
                makes_contact = bool(move_data.get("makes_contact") or move_data.get("contact"))
            attacker_ability_norm = normalize_ability_name(atk.ability or "")
            attacker_ability_data = get_ability_effect(attacker_ability_norm)
            ability_bypass = (
                not getattr(atk, '_ability_suppressed', False)
                and attacker_ability_data.get("contact_ignores_protect")
                and makes_contact
            )
            # === NULLSCAPE (Normal): Ignores Protect ===
            nullscape_type_protect = None
            if hasattr(atk, '_battle_state') and atk._battle_state:
                from .engine import _get_nullscape_type
                nullscape_type_protect = _get_nullscape_type(atk, atk._battle_state)
            if nullscape_type_protect == "Normal":
                ability_bypass = True  # Normal Nullscape bypasses Protect
                bypasses_protect = True
            
            bypasses_protect = move_effect.get("ignores_protect", False) or ability_bypass
            removes_protection = move_effect.get("removes_protection", False)
            
            # Max Guard protects against additional moves that regular Protect doesn't
            # Moves that Max Guard blocks (but regular Protect doesn't):
            # Block, Flower Shield, Gear Up, Magnetic Flux, Phantom Force, Psych Up,
            # Shadow Force, Teatime, Transform
            max_guard_protected_moves = {
                "block", "flower-shield", "gear-up", "magnetic-flux",
                "phantom-force", "psych-up", "shadow-force", "teatime", "transform"
            }
            is_max_guard = getattr(dfn, 'max_guard_active', False)
            is_max_guard_protected_move = move_lower in max_guard_protected_moves
            
            # Z-Moves bypass protection but with 25% damage (for damaging) or apply Z-Power (for status)
            # So skip the normal protection blocking logic if it's a Z-Move
            if not is_z_move:
                # Determine if protection blocks the move:
                # 1. Max Guard blocks max_guard_protected_moves even if they have ignores_protect=True
                # 2. Regular Protect doesn't block max_guard_protected_moves
                # 3. Moves with ignores_protect=True bypass regular Protect (unless blocked by Max Guard rule #1)
                if is_max_guard and is_max_guard_protected_move:
                    # Max Guard blocks these specific moves even if they normally ignore protect
                    atk_name = _format_pokemon_name(atk)
                    move_name = _format_move_name(chosen)
                    log.append(f"**{atk_name}** used **{move_name}**!")
                    dfn_name = _format_pokemon_name(dfn)
                    log.append(f"But {dfn_name} protected itself!")
                    # Apply protection counter effects (King's Shield, Spiky Shield, Winter's Aegis, etc.)
                    self._apply_protection_counter_effect(dfn, atk, uid, chosen, log)
                    # High Jump Kick / Jump Kick: Crash damage when blocked by Protect
                    move_lower_crash = chosen.lower().replace(" ", "-")
                    if move_lower_crash in ["high-jump-kick", "jump-kick"]:
                        from .engine import apply_jump_kick_crash
                        crash_msg = apply_jump_kick_crash(atk, dfn, chosen, {"miss": False, "immune": False}, self.field)
                        if crash_msg:
                            log.append(crash_msg)
                    if getattr(atk, 'rampage_move', None):
                        generation = getattr(self.field, 'generation', 9)
                        if generation >= 5:
                            from .engine import disrupt_rampage
                            disrupt_rampage(atk, self.field, reason="protect")
                    _record_last_move(atk, chosen, battle_state=self)
                    reset_rollout(atk)
                    act["_processed"] = True
                    return
                elif ability_bypass and is_max_guard:
                    if not is_z_move:
                        atk_name = _format_pokemon_name(atk)
                        move_name = _format_move_name(chosen)
                        log.append(f"**{atk_name}** used **{move_name}**!")
                    dfn_name = _format_pokemon_name(dfn)
                    log.append(f"But {dfn_name} protected itself!")
                    # Apply protection counter effects (King's Shield, Spiky Shield, Winter's Aegis, etc.)
                    self._apply_protection_counter_effect(dfn, atk, uid, chosen, log)
                    # High Jump Kick / Jump Kick: Crash damage when blocked by Protect
                    move_lower_crash = chosen.lower().replace(" ", "-")
                    if move_lower_crash in ["high-jump-kick", "jump-kick"]:
                        from .engine import apply_jump_kick_crash
                        crash_msg = apply_jump_kick_crash(atk, dfn, chosen, {"miss": False, "immune": False}, self.field)
                        if crash_msg:
                            log.append(crash_msg)
                    if getattr(atk, 'rampage_move', None):
                        generation = getattr(self.field, 'generation', 9)
                        if generation >= 5:
                            from .engine import disrupt_rampage
                            disrupt_rampage(atk, self.field, reason="protect")
                    _record_last_move(atk, chosen, battle_state=self)
                    reset_rollout(atk)
                    act["_processed"] = True
                    return
                elif bypasses_protect:
                    # Move with ignores_protect bypasses regular Protect
                    # Special handling for Max Guard:
                    # - G-Max One Blow and G-Max Rapid Flow: bypass Max Guard (deal full damage)
                    # - Feint: bypass Max Guard (deal full damage) but does NOT remove protection
                    is_max_guard_bypass_move = move_lower in ["g-max-one-blow", "g-max-rapid-flow", "feint"]
                    
                    if not is_z_move:  # Already logged for Z-Moves above
                        atk_name = _format_pokemon_name(atk)
                        move_name = _format_move_name(chosen)
                        log.append(f"**{atk_name}** used **{move_name}**!")
                    
                    if is_max_guard and is_max_guard_bypass_move:
                        # G-Max One Blow, G-Max Rapid Flow, and Feint deal full damage through Max Guard
                        atk_name = _format_pokemon_name(atk)
                        log.append(f"{atk_name} broke through Max Guard!")
                        # Feint does NOT remove Max Guard protection (unlike other protection-breaking moves)
                        if move_lower != "feint" and removes_protection:
                            dfn.protected_this_turn = False
                            dfn.max_guard_active = False
                            dfn_name = _format_pokemon_name(dfn)
                            log.append(f"{dfn_name}'s protection vanished!")
                    else:
                        # Regular protection bypass
                        atk_name = _format_pokemon_name(atk)
                        log.append(f"{atk_name} broke through the protection!")
                        if removes_protection:
                            dfn.protected_this_turn = False
                            dfn.max_guard_active = False
                            dfn_name = _format_pokemon_name(dfn)
                            log.append(f"{dfn_name}'s protection vanished!")
                elif is_max_guard_protected_move and not is_max_guard:
                    # Max Guard protected move vs regular Protect: bypasses
                    if not is_z_move:  # Already logged for Z-Moves above
                        atk_name = _format_pokemon_name(atk)
                        move_name = _format_move_name(chosen)
                        log.append(f"**{atk_name}** used **{move_name}**!")
                    atk_name = _format_pokemon_name(atk)
                    log.append(f"{atk_name} broke through the protection!")
                    if removes_protection:
                        dfn.protected_this_turn = False
                        dfn.max_guard_active = False
                        dfn_name = _format_pokemon_name(dfn)
                        log.append(f"{dfn_name}'s protection vanished!")
                else:
                    # Protection blocks the move
                    if not is_z_move:  # Already logged for Z-Moves above
                        atk_name = _format_pokemon_name(atk)
                        move_name = _format_move_name(chosen)
                        log.append(f"**{atk_name}** used **{move_name}**!")
                    dfn_name = _format_pokemon_name(dfn)
                    log.append(f"But {dfn_name} protected itself!")
                    # Apply protection counter effects (King's Shield, Spiky Shield, Winter's Aegis, etc.)
                    self._apply_protection_counter_effect(dfn, atk, uid, chosen, log)
                    # High Jump Kick / Jump Kick: Crash damage when blocked by Protect
                    move_lower_crash = chosen.lower().replace(" ", "-")
                    if move_lower_crash in ["high-jump-kick", "jump-kick"]:
                        from .engine import apply_jump_kick_crash
                        crash_msg = apply_jump_kick_crash(atk, dfn, chosen, {"miss": False, "immune": False}, self.field)
                        if crash_msg:
                            log.append(crash_msg)
                    if getattr(atk, 'rampage_move', None):
                        generation = getattr(self.field, 'generation', 9)
                        if generation >= 5:
                            from .engine import disrupt_rampage
                            disrupt_rampage(atk, self.field, reason="protect")
                    _record_last_move(atk, chosen, battle_state=self)
                    reset_rollout(atk)
                    act["_processed"] = True
                    return

        if move_lower == "substitute":
            success, sub_msg = apply_substitute(atk)
            log.append(f"{sub_msg}")
            _record_last_move(atk, chosen, battle_state=self)
            act["_processed"] = True
            return

        hazard_moves = {"stealth-rock": "stealth-rock", "spikes": "spikes",
                         "toxic-spikes": "toxic-spikes", "sticky-web": "sticky-web"}
        if move_lower in hazard_moves:
            from .hazards import set_hazard
            opponent_side = dfn_side
            success, hazard_msg = set_hazard(opponent_side.hazards, hazard_moves[move_lower], self.gen)
            atk_name = _format_pokemon_name(atk)
            move_name = _format_move_name(chosen)
            log.append(f"**{atk_name}** used **{move_name}**!")
            log.append(f"  {hazard_msg}")
            if move_lower == "stealth-rock" and hasattr(atk, '_is_z_move') and atk._is_z_move:
                from .engine import modify_stages
                z_msgs = modify_stages(atk, {"defn": 1}, caused_by_opponent=False, field_effects=self.field)
                for z_msg in z_msgs:
                    log.append(f"  {z_msg}")
            _record_last_move(atk, chosen, battle_state=self)
            act["_processed"] = True
            return

        weather_moves = {"rain-dance": "rain", "sunny-day": "sun", "sandstorm": "sandstorm",
                         "hail": "hail", "snowscape": "snow"}
        if move_lower in weather_moves:
            generation = getattr(self, 'gen', 9)
            special_weather = getattr(self.field, 'special_weather', None)
            # Desolate Land (harsh-sunlight) and Primordial Sea (heavy-rain) prevent weather moves from working
            # Only Primordial Sea can override Desolate Land, and only Desolate Land can override Primordial Sea
            if special_weather in {"heavy-rain", "harsh-sunlight", "strong-winds"}:
                atk_name = _format_pokemon_name(atk)
                move_name = _format_move_name(chosen)
                log.append(f"**{atk_name}** used **{move_name}**!")
                if special_weather == "heavy-rain":
                    fail_text = "  But the heavy rain made the move fail!"
                elif special_weather == "harsh-sunlight":
                    fail_text = "  But the extremely harsh sunlight made the move fail!"
                else:  # strong-winds
                    fail_text = "  But the mysterious air current made the move fail!"
                log.append(fail_text)
                atk._last_move_failed = True
                _record_last_move(atk, chosen, battle_state=self)
                act["_processed"] = True
                return

            target_weather = weather_moves[move_lower]
            if target_weather == "sandstorm" and generation == 2 and self.field.weather == "sandstorm":
                atk_name = _format_pokemon_name(atk)
                move_name = _format_move_name(chosen)
                log.append(f"**{atk_name}** used **{move_name}**!")
                log.append("  But there was no change to the weather!")
                atk._last_move_failed = True
                _record_last_move(atk, chosen, battle_state=self)
                act["_processed"] = True
                return

            if generation >= 3 and self.field.weather == target_weather and not special_weather:
                atk_name = _format_pokemon_name(atk)
                move_name = _format_move_name(chosen)
                log.append(f"**{atk_name}** used **{move_name}**!")
                log.append("  But the weather didn't change!")
                atk._last_move_failed = True
                _record_last_move(atk, chosen, battle_state=self)
                act["_processed"] = True
                return

            # Clear special weather BEFORE setting regular weather to prevent Desolate Land from activating
            # Special weather abilities (Desolate Land, Primordial Sea) should NOT activate from weather moves
            self.field.special_weather = None
            self.field.heavy_rain = False
            self.field.harsh_sunlight = False
            self.field.weather_lock = None
            self.field.weather_lock_owner = None
            self.field.weather = target_weather

            from .items import get_item_effect, normalize_item_name
            weather_duration = 5
            if generation >= 4 and getattr(atk, 'item', None):
                item_data = get_item_effect(normalize_item_name(atk.item))
                if item_data.get("extends_weather") == target_weather:
                    weather_duration = 8

            self.field.weather_turns = weather_duration
            if target_weather == "sandstorm" and generation == 2:
                self.field.sandstorm_damage_turns = 4
            
            # Z-Weather moves: +1 Speed (user) for Sandstorm, Rain Dance, Sunny Day, Hail
            if move_lower in ["sandstorm", "rain-dance", "sunny-day", "hail"]:
                is_z_move = atk_choice.get("z_move", False) or getattr(atk, '_is_z_move', False)
                if is_z_move:
                    from .engine import modify_stages
                    z_msgs_weather = modify_stages(atk, {"spe": 1}, caused_by_opponent=False, field_effects=self.field)
                    for z_msg in z_msgs_weather:
                        log.append(f"  {z_msg}")
            
            if target_weather == "sandstorm":
                if generation == 2:
                    self.field.sandstorm_damage_turns = 4
            else:
                self.field.sandstorm_damage_turns = 0
            weather_names = {"rain": "Rain", "sun": "Harsh sunlight", "sandstorm": "Sandstorm",
                             "hail": "Hail", "snow": "Snow"}
            atk_name = _format_pokemon_name(atk)
            move_name = _format_move_name(chosen)
            log.append(f"**{atk_name}** used **{move_name}**!")
            log.append(f"  {weather_names[target_weather]} started!")
            _record_last_move(atk, chosen, battle_state=self)
            act["_processed"] = True
            return

        terrain_moves = {"electric-terrain": "electric", "grassy-terrain": "grassy",
                         "misty-terrain": "misty", "psychic-terrain": "psychic"}
        if move_lower in terrain_moves:
            self.field.terrain = terrain_moves[move_lower]
            from .items import get_item_effect, normalize_item_name
            terrain_duration = 5
            if getattr(atk, 'item', None):
                item_data = get_item_effect(normalize_item_name(atk.item))
                if item_data.get("extends_terrain"):
                    terrain_duration = 8

            self.field.terrain_turns = terrain_duration
            terrain_names = {"electric": "Electric Terrain", "grassy": "Grassy Terrain",
                             "misty": "Misty Terrain", "psychic": "Psychic Terrain"}
            atk_name = _format_pokemon_name(atk)
            move_name = _format_move_name(chosen)
            log.append(f"**{atk_name}** used **{move_name}**!")
            log.append(f"  {terrain_names[terrain_moves[move_lower]]} activated!")
            _record_last_move(atk, chosen, battle_state=self)
            act["_processed"] = True
            return

        field_effect_moves = {
            "reflect", "light-screen", "aurora-veil", "tailwind", "trick-room",
            "magic-room", "wonder-room", "gravity", "mist"
        }
        if move_lower in field_effect_moves:
            field_msgs = apply_field_effect_move(chosen, self.field, atk_side, uid == self.p1_id, atk, self)
            atk_name = _format_pokemon_name(atk)
            move_name = _format_move_name(chosen)
            log.append(f"**{atk_name}** used **{move_name}**!")
            for msg in field_msgs:
                log.append(f"  {msg}")
            _record_last_move(atk, chosen, battle_state=self)
            act["_processed"] = True
            return

        from .engine import check_form_change
        form_msg = check_form_change(atk, triggered_by="before_move", move_used=chosen, field_effects=self.field, battle_state=self)
        if form_msg:
            log.append(f"  {form_msg}")

        from .engine import action_priority, is_priority_blocked
        from .advanced_moves import get_metronome_move
        
        # For Metronome, determine the called move's priority before checking priority blocking
        if move_lower == "metronome":
            selected_move, _ = get_metronome_move(field_effects=self.field, battle_state=self)
            if selected_move:
                # Store the called move for later use in apply_move
                atk._metronome_called_move = selected_move
                # Use the called move's priority for priority checks
                move_priority = action_priority(selected_move, atk, self.field, self)
            else:
                move_priority = action_priority(chosen, atk, self.field, self)
        else:
            move_priority = action_priority(chosen, atk, self.field, self)
        
        attacker_ability = normalize_ability_name(atk.ability or "")
        from .abilities import get_ability_effect as get_atk_ability
        attacker_ability_data = get_atk_ability(attacker_ability)
        ignores_abilities = attacker_ability_data.get("ignores_opponent_abilities", False)

        center_mon = None
        opponent_uid = self.p2_id if uid == self.p1_id else self.p1_id
        try:
            opp_active = self._active(opponent_uid)
        except Exception:
            opp_active = dfn
        candidates = []
        if opp_active:
            candidates.append(opp_active)
        # Check if defender override differs (e.g., forced target)
        if dfn and dfn is not opp_active:
            candidates.append(dfn)
        for candidate in candidates:
            if candidate and candidate.hp > 0 and getattr(candidate, 'center_of_attention', False):
                center_mon = candidate
                break

        if center_mon and center_mon is not dfn:
            should_redirect = True

            if effect_data and effect_data.get("ignores_redirection"):
                should_redirect = False
            if attacker_ability_data.get("ignores_redirection"):
                should_redirect = False

            target_code = (move_data or {}).get("target")
            single_target_codes = {
                None,
                "selected-pokemon",
                "selected-pokemon-me-first",
                "random-opponent",
                "selected-pokemon-or-user",
                "selected-pokemon-and-user"
            }
            non_redirect_codes = {
                "user",
                "user-or-ally",
                "user-and-allies",
                "ally",
                "allies",
                "ally-side",
                "user-side",
                "foe-side",
                "all-opponents",
                "opponents-field",
                "entire-field",
                "all-other-pokemon"
            }
            if target_code in non_redirect_codes:
                should_redirect = False
            elif target_code not in single_target_codes:
                should_redirect = False

            center_source = getattr(center_mon, '_center_of_attention_source', None)
            if should_redirect and center_source == "rage-powder":
                from .generation import get_generation
                generation = get_generation(field_effects=self.field)
                immune_to_powder = False

                if attacker_ability_data.get("powder_immunity"):
                    immune_to_powder = True

                if item_is_active(atk) and getattr(atk, 'item', None):
                    from .items import normalize_item_name, get_item_effect
                    item_data = get_item_effect(normalize_item_name(atk.item))
                    if item_data.get("powder_immunity"):
                        immune_to_powder = True

                attacker_types = [t for t in getattr(atk, 'types', ()) if t]
                if generation >= 6 and any(t.strip().title() == "Grass" for t in attacker_types):
                    immune_to_powder = True

                if immune_to_powder:
                    should_redirect = False

            if should_redirect:
                dfn = center_mon

        is_blocked, block_msg = False, None
        if not ignores_abilities:
            is_blocked, block_msg = is_priority_blocked(
                atk,
                dfn,
                chosen,
                move_priority,
                defender_side=dfn_side,
                field_effects=self.field
            )

        move_result = ""
        if is_blocked and block_msg:
            atk_name = _format_pokemon_name(atk)
            move_name = _format_move_name(chosen)
            log.append(f"**{atk_name}** used **{move_name}**!")
            log.append(block_msg)
            atk._moved_this_turn = True
        else:
            # Check Taunt - block status moves if taunted (including same-turn via _taunt_pending)
            taunt_pending = getattr(atk, "_taunt_pending", False)
            # Check if taunted: either has taunt_turns > 0, or has _taunt_pending flag (same-turn)
            is_taunted = (atk.taunted and (atk.taunt_turns > 0 or taunt_pending)) or taunt_pending
            should_block = is_taunted and not (
                atk_choice.get("z_move") or getattr(atk, '_is_z_move', False)
            )

            if should_block:
                move_data = _get_move_with_cache(chosen, battle_state=self, generation=self.gen)
                move_effect = get_move_secondary_effect(chosen) or {}
                move_category = ""
                move_power_raw = None
                if move_data:
                    move_category = (move_data.get("damage_class") or move_data.get("category") or "").lower()
                    if "power" in move_data:
                        move_power_raw = move_data.get("power")
                move_power_val = move_power_raw if isinstance(move_power_raw, (int, float)) else 0
                variable_power = bool(move_effect.get("variable_power"))
                is_status_move = move_category == "status" or (move_power_val <= 0 and not variable_power)
                
                # Gen V+: Me First is not affected by Taunt
                move_lower = chosen.lower().replace(" ", "-")
                is_me_first = move_lower == "me-first"
                from .generation import get_generation
                generation = get_generation(field_effects=self.field) if hasattr(self, 'field') else 9
                
                if is_status_move and move_lower != "struggle" and not (generation >= 5 and is_me_first):
                    atk_name = _format_pokemon_name(atk)
                    move_name = _format_move_name(chosen)
                    log.append(f"**{atk_name}** used **{move_name}**!\nBut it failed!")
                    atk._moved_this_turn = True
                    atk._last_move_failed = True
                    if taunt_pending:
                        atk._taunt_pending = False
                        if hasattr(atk, "_taunt_applied_turn"):
                            atk._taunt_applied_turn = None
                    return
            analytic_bonus = is_moving_last
            if normalize_ability_name(getattr(atk, 'ability', '') or "") == "analytic":
                if dfn_choice and dfn_choice.get("kind") == "switch":
                    analytic_bonus = True
            move_result = apply_move(atk, dfn, chosen, self.field, dfn_side, atk_choice, dfn_choice, self, analytic_bonus)
            if move_result is None:
                move_result = ""
            if not isinstance(move_result, str):
                move_result = str(move_result)
            atk._moved_this_turn = True
            if move_lower != "laser-focus" and getattr(atk, '_laser_focus_pending', False):
                atk._laser_focus_pending = False
                atk.laser_focus_turns = 0
            
            # Ensure the move usage line is present for results that omit it (e.g., "It doesn't affect...")
            if move_result and "** used **" not in move_result:
                atk_name = _format_pokemon_name(atk)
                move_name = _format_move_name(chosen)
                log.append(f"**{atk_name}** used **{move_name}**!")
            elif not move_result:
                atk_name = _format_pokemon_name(atk)
                move_name = _format_move_name(chosen)
                log.append(f"**{atk_name}** used **{move_name}**!")

            # Split multi-line messages so each line appears separately in the log
            if move_result and move_result.strip():
                if "\n" in move_result:
                    for line in move_result.split("\n"):
                        if line.strip():  # Only add non-empty lines
                            log.append(line)
                else:
                    log.append(move_result)
            
            # Check if this was a Z-Move and update the log message to show Z-Move name
            if atk_choice.get("z_move") and hasattr(atk, '_z_move_name'):
                z_move_name = atk._z_move_name
                # Replace the move name in the log message
                import re
                # The log entry we just added is at the end
                if log and f"**{atk.species}** used **" in log[-1]:
                    # Format Z-Move name (replace hyphens with spaces, title case)
                    formatted_z_name = z_move_name.replace("-", " ").title()
                    log[-1] = re.sub(
                        r'(\*\*[^*]+\*\* used \*\*)[^*]+(\*\*)',
                        f'\\1{formatted_z_name}\\2',
                        log[-1],
                        count=1
                    )
            
            # === Z-MOVE USAGE TRACKING ===
            # Mark Z-Move as used if this was a Z-Move
            is_z_move = atk_choice.get("z_move", False) or getattr(atk, '_is_z_move', False)
            if is_z_move:
                self._z_move_used[uid] = True
            
            # === MAX MOVE SIDE EFFECTS ===
            # Apply Max Move side effects (weather, terrain, stat changes) after Max Move hits
            if hasattr(atk, '_is_max_move') and atk._is_max_move:
                from .max_moves import get_max_move_side_effect
                # Use top-level get_move import (don't shadow)
                from .engine import modify_stages
                from .generation import get_generation
                
                # Get the original move to determine type
                original_move = getattr(atk, '_original_move_name_max', chosen)
                # Use the same type determination logic as in apply_move (accounts for type changes)
                from .max_moves import get_actual_move_type_for_max_move
                move_type = get_actual_move_type_for_max_move(original_move, atk, self.field)
                max_effect = get_max_move_side_effect(move_type)
                
                if max_effect:
                        generation = get_generation(field_effects=self.field)
                        
                        # Weather effects (Max Flare, Max Geyser, Max Rockfall, etc.)
                        if "weather" in max_effect:
                            weather_type = max_effect["weather"]
                            turns = max_effect.get("turns", 5)
                            
                            # Check for weather-extending items
                            if atk.item:
                                from .items import normalize_item_name, get_item_effect
                                item_data = get_item_effect(normalize_item_name(atk.item))
                                extends_weather = item_data.get("extends_weather")
                                
                                # Max Flare: 8 turns if Heat Rock is held
                                if weather_type == "sun" and extends_weather == "sun":
                                    turns = 8
                                # Max Geyser: 8 turns if Damp Rock is held
                                elif weather_type == "rain" and extends_weather == "rain":
                                    turns = 8
                                # Max Rockfall: 8 turns if Smooth Rock is held
                                elif weather_type == "sandstorm" and extends_weather == "sandstorm":
                                    turns = 8
                                # Max Hailstorm: 8 turns if Icy Rock is held
                                elif weather_type == "hail" and extends_weather == "hail":
                                    turns = 8
                            
                            # Set weather similar to weather-setting moves
                            self.field.weather = weather_type
                            self.field.special_weather = None
                            self.field.heavy_rain = False
                            self.field.harsh_sunlight = False
                            self.field.weather_lock = None
                            self.field.weather_lock_owner = None
                            self.field.weather_turns = turns
                            weather_names = {
                                "sun": "harsh sunlight",
                                "rain": "rain",
                                "hail": "hail",
                                "sandstorm": "a sandstorm"
                            }
                            weather_display = weather_names.get(weather_type, weather_type)
                            log.append(f"The {weather_display} started!")
                        
                        # Terrain effects (Max Lightning, Max Overgrowth, etc.)
                        elif "terrain" in max_effect:
                            terrain_type = max_effect["terrain"]
                            turns = max_effect.get("turns", 5)
                            
                            # Max Lightning and Max Overgrowth: 8 turns if Terrain Extender is held
                            if atk.item:
                                from .items import normalize_item_name, get_item_effect
                                item_data = get_item_effect(normalize_item_name(atk.item))
                                if item_data.get("extends_terrain"):
                                    turns = 8
                            
                            self.field.terrain = terrain_type
                            self.field.terrain_turns = turns
                            terrain_names = {
                                "electric": "Electric Terrain",
                                "grassy": "Grassy Terrain",
                                "misty": "Misty Terrain",
                                "psychic": "Psychic Terrain"
                            }
                            terrain_display = terrain_names.get(terrain_type, terrain_type)
                            log.append(f"{terrain_display} was set!")
                        
                        # Stat boosts for team (Max Knuckle, Max Ooze, Max Airstream, Max Quake, etc.)
                        elif "stat_boost_team" in max_effect:
                            stat_changes = max_effect["stat_boost_team"]
                            # Apply to user only (no doubles)
                            msgs = modify_stages(atk, stat_changes, caused_by_opponent=False, field_effects=self.field)
                            for msg in msgs:
                                log.append(msg)
                        
                        # Stat drops for opponent (Max Flutterby, Max Phantasm, Max Strike, etc.)
                        elif "stat_lower_opponent" in max_effect and dfn:
                            stat_changes = max_effect["stat_lower_opponent"]
                            # Apply to target only (no doubles - target and its ally would be affected in doubles)
                            msgs = modify_stages(dfn, {k: -v for k, v in stat_changes.items()}, caused_by_opponent=True, field_effects=self.field)
                            for msg in msgs:
                                log.append(msg)

        if dfn is not None and "lost" in move_result.lower() and "health" in move_result.lower():
            illusion_msg = self._break_illusion(dfn)
            if illusion_msg:
                log.append(f"**{illusion_msg}**")

        form_msg = check_form_change(dfn, triggered_by="after_damage", field_effects=self.field, battle_state=self) if dfn else None
        if form_msg:
            log.append(f"  {form_msg}")
        form_msg = check_form_change(atk, triggered_by="after_damage", field_effects=self.field, battle_state=self)
        if form_msg:
            log.append(f"  {form_msg}")

        # === G-MAX MOVE EFFECTS ===
        # Apply G-Max Move special effects after damage
        if hasattr(atk, '_is_max_move') and atk._is_max_move and atk.is_gigantamax:
            from .max_moves import get_gmax_move_effect
            from .engine import modify_stages
            from .db_move_effects import apply_status_effect
            
            original_move = getattr(atk, '_original_move_name_max', chosen)
            gmax_effect = get_gmax_move_effect(original_move, atk.species)
            move_name_lower = chosen.lower().replace(" ", "-")
            
            if gmax_effect:
                effect_type = gmax_effect.get("effect")
                
                # G-Max Wildfire: Residual damage for 4 turns to non-Fire-type foes
                if "wildfire" in move_name_lower:
                    opponent_uid = self.p2_id if uid == self.p1_id else self.p1_id
                    opponent_team = self.team_for(opponent_uid)
                    for opponent_mon in opponent_team:
                        if opponent_mon and opponent_mon.hp > 0:
                            # Check if opponent is Fire-type
                            is_fire_type = "Fire" in (opponent_mon.types or [])
                            if not is_fire_type:
                                opponent_mon._gmax_wildfire_active = True
                                opponent_mon._gmax_wildfire_turns = 4
                                log.append(f"  {opponent_mon.species} was caught in the wildfire!")
                
                # G-Max Befuddle: Causes poison, paralysis, or sleep to all opponents
                elif "befuddle" in move_name_lower:
                    opponent_uid = self.p2_id if uid == self.p1_id else self.p1_id
                    opponent_team = self.team_for(opponent_uid)
                    for opponent_mon in opponent_team:
                        if opponent_mon and opponent_mon.hp > 0:
                            # Random status: poison, paralysis, or sleep
                            status_choice = random.choice(["psn", "par", "slp"])
                            success, status_msg = apply_status_effect(opponent_mon, status_choice, atk, field_effects=self.field)
                            if success and status_msg:
                                log.append(f"  {status_msg}")
                
                # G-Max Volt Crash: Paralyzes all opponents
                elif "volt-crash" in move_name_lower or "voltcrash" in move_name_lower:
                    opponent_uid = self.p2_id if uid == self.p1_id else self.p1_id
                    opponent_team = self.team_for(opponent_uid)
                    for opponent_mon in opponent_team:
                        if opponent_mon and opponent_mon.hp > 0:
                            success, status_msg = apply_status_effect(opponent_mon, "par", atk, field_effects=self.field)
                            if success and status_msg:
                                log.append(f"  {status_msg}")
                
                # G-Max Gold Rush: Confuses opponent and scatters coins
                elif "gold-rush" in move_name_lower or "goldrush" in move_name_lower:
                    if dfn and dfn.hp > 0:
                        # Confuse target
                        if not getattr(dfn, 'confused', False):
                            dfn.confused = True
                            dfn.confusion_turns = random.randint(1, 4)
                            dfn._confusion_applied_this_turn = True
                            log.append(f"  {dfn.species} became confused!")
                        # Track coins (increases with consecutive uses: 100×, 200×, 300× level)
                        if not hasattr(self, '_gmax_gold_rush_coins'):
                            self._gmax_gold_rush_coins = 0
                        if not hasattr(self, '_gmax_gold_rush_uses'):
                            self._gmax_gold_rush_uses = 0
                        self._gmax_gold_rush_uses += 1
                        # Each use adds 100× level, up to 300× on third use
                        coins_per_use = min(300, 100 * self._gmax_gold_rush_uses) * atk.level
                        self._gmax_gold_rush_coins = min(99999, self._gmax_gold_rush_coins + coins_per_use)
                        log.append(f"  Coins were scattered everywhere!")
                
                # G-Max Chi Strike: Increases user's critical hit rate by one stage
                elif "chi-strike" in move_name_lower or "chistrike" in move_name_lower:
                    # Critical hit rate boost (stacks with Focus Energy)
                    if not hasattr(atk, 'focused_energy_stage'):
                        atk.focused_energy_stage = 0
                    atk.focused_energy_stage += 1
                    log.append(f"  {atk.species}'s critical hit rate rose!")
                
                # G-Max Terror: Prevents targets from switching out
                elif "terror" in move_name_lower:
                    opponent_uid = self.p2_id if uid == self.p1_id else self.p1_id
                    opponent_team = self.team_for(opponent_uid)
                    for opponent_mon in opponent_team:
                        if opponent_mon and opponent_mon.hp > 0:
                            opponent_mon.trapped = True
                            opponent_mon.trapped_by = atk.species
                            log.append(f"  {opponent_mon.species} can no longer escape!")
                
                # G-Max Foam Burst: Lowers all opponents' Speed by two stages
                elif "foam-burst" in move_name_lower or "foamburst" in move_name_lower:
                    opponent_uid = self.p2_id if uid == self.p1_id else self.p1_id
                    opponent_team = self.team_for(opponent_uid)
                    for opponent_mon in opponent_team:
                        if opponent_mon and opponent_mon.hp > 0:
                            msgs = modify_stages(opponent_mon, {"spe": -2}, caused_by_opponent=True, field_effects=self.field)
                            for msg in msgs:
                                log.append(f"  {msg}")
                
                # G-Max Resonance: Sets up Aurora Veil (doesn't require hail, 5 turns, 8 with Light Clay)
                elif "resonance" in move_name_lower:
                    atk_side = self.p1_side if uid == self.p1_id else self.p2_side
                    if not atk_side.aurora_veil:
                        atk_side.aurora_veil = True
                        # Check for Light Clay
                        duration = 5
                        if atk.item:
                            from .items import normalize_item_name, get_item_effect
                            item_data = get_item_effect(normalize_item_name(atk.item))
                            if item_data.get("extends_screens"):
                                duration = 8
                        atk_side.aurora_veil_turns = duration
                        log.append(f"  Aurora Veil raised defenses!")
                    else:
                        log.append(f"  But it failed!")
                
                # G-Max Cuddle: Makes all opponents of opposite gender infatuated
                elif "cuddle" in move_name_lower:
                    opponent_uid = self.p2_id if uid == self.p1_id else self.p1_id
                    opponent_team = self.team_for(opponent_uid)
                    user_gender = getattr(atk, 'gender', None)
                    for opponent_mon in opponent_team:
                        if opponent_mon and opponent_mon.hp > 0:
                            opp_gender = getattr(opponent_mon, 'gender', None)
                            # Infatuate if opposite gender (both must be defined and different)
                            if user_gender is not None and opp_gender is not None and user_gender != opp_gender:
                                if not getattr(opponent_mon, '_infatuated', False):
                                    opponent_mon._infatuated = True
                                    opponent_mon._infatuated_by = atk
                                    log.append(f"  {opponent_mon.species} fell in love!")
                
                # G-Max Replenish: 50% chance to restore consumed Berries
                elif "replenish" in move_name_lower:
                    user_team = self.team_for(uid)
                    restored_any = False
                    for ally in user_team:
                        if ally and ally.hp > 0:
                            # Check if ally has consumed a berry
                            if hasattr(ally, '_last_consumed_berry') and ally._last_consumed_berry and not ally.item:
                                if random.random() < 0.5:  # 50% chance
                                    ally.item = ally._last_consumed_berry
                                    berry_name = ally.item.replace('-', ' ').title()
                                    log.append(f"  {ally.species}'s {berry_name} was restored!")
                                    restored_any = True
                                    delattr(ally, '_last_consumed_berry')
                    if not restored_any:
                        log.append(f"  But it failed!")
                
                # G-Max Malodor: Poisons all Pokémon on target's side
                elif "malodor" in move_name_lower:
                    defender_uid = self.p2_id if uid == self.p1_id else self.p1_id
                    defender_team = self.team_for(defender_uid)
                    for defender_mon in defender_team:
                        if defender_mon and defender_mon.hp > 0:
                            success, status_msg = apply_status_effect(defender_mon, "psn", atk, field_effects=self.field)
                            if success and status_msg:
                                log.append(f"  {status_msg}")
                
                # G-Max Meltdown: Subjects target and allies to Torment for 3 turns
                elif "meltdown" in move_name_lower:
                    defender_uid = self.p2_id if uid == self.p1_id else self.p1_id
                    defender_team = self.team_for(defender_uid)
                    for defender_mon in defender_team:
                        if defender_mon and defender_mon.hp > 0:
                            defender_mon.tormented = True
                            defender_mon.torment_turns = 3
                            log.append(f"  {defender_mon.species} was subjected to torment!")
                
                # G-Max Wind Rage: Removes screens, entry hazards, and terrains from target's side
                elif "wind-rage" in move_name_lower or "windrage" in move_name_lower:
                    defender_uid = self.p2_id if uid == self.p1_id else self.p1_id
                    defender_side = self.p1_side if defender_uid == self.p1_id else self.p2_side
                    removed_effects = []
                    
                    # Remove screens
                    if defender_side.reflect:
                        defender_side.reflect = False
                        defender_side.reflect_turns = 0
                        removed_effects.append("Reflect")
                    if defender_side.light_screen:
                        defender_side.light_screen = False
                        defender_side.light_screen_turns = 0
                        removed_effects.append("Light Screen")
                    if defender_side.aurora_veil:
                        defender_side.aurora_veil = False
                        defender_side.aurora_veil_turns = 0
                        removed_effects.append("Aurora Veil")
                    
                    # Remove entry hazards
                    if hasattr(defender_side, 'hazards'):
                        hazards_removed = []
                        if defender_side.hazards.spikes > 0:
                            defender_side.hazards.spikes = 0
                            hazards_removed.append("Spikes")
                        if defender_side.hazards.stealth_rock:
                            defender_side.hazards.stealth_rock = False
                            hazards_removed.append("Stealth Rock")
                        if defender_side.hazards.toxic_spikes > 0:
                            defender_side.hazards.toxic_spikes = 0
                            hazards_removed.append("Toxic Spikes")
                        if defender_side.hazards.sticky_web:
                            defender_side.hazards.sticky_web = False
                            hazards_removed.append("Sticky Web")
                        if hazards_removed:
                            removed_effects.extend(hazards_removed)
                    
                    # Remove terrain
                    if self.field.terrain:
                        terrain_names = {
                            "electric": "Electric Terrain",
                            "grassy": "Grassy Terrain",
                            "misty": "Misty Terrain",
                            "psychic": "Psychic Terrain"
                        }
                        terrain_name = terrain_names.get(self.field.terrain, self.field.terrain)
                        removed_effects.append(terrain_name)
                        self.field.terrain = None
                        self.field.terrain_turns = 0
                    
                    if removed_effects:
                        log.append(f"  {', '.join(removed_effects)} were blown away!")
                    else:
                        log.append(f"  But it failed!")
                
                # G-Max Gravitas: Intensifies gravity for 5 turns
                elif "gravitas" in move_name_lower:
                    if not self.field.gravity:
                        self.field.gravity = True
                        self.field.gravity_turns = 5
                        log.append(f"  Gravity intensified!")
                    else:
                        log.append(f"  But it failed!")
                
                # G-Max Stonesurge: Creates Stealth Rock on target's side
                elif "stonesurge" in move_name_lower:
                    defender_uid = self.p2_id if uid == self.p1_id else self.p1_id
                    defender_side = self.p1_side if defender_uid == self.p1_id else self.p2_side
                    if not defender_side.hazards.stealth_rock:
                        defender_side.hazards.stealth_rock = True
                        log.append(f"  **Stealth Rock** scattered sharp rocks around the opposing team!")
                    else:
                        log.append(f"  But it failed!")
                
                # G-Max Volcalith: Residual damage for 4 turns to non-Rock-type foes (1/6 max HP)
                elif "volcalith" in move_name_lower:
                    opponent_uid = self.p2_id if uid == self.p1_id else self.p1_id
                    opponent_team = self.team_for(opponent_uid)
                    for opponent_mon in opponent_team:
                        if opponent_mon and opponent_mon.hp > 0:
                            # Check if opponent is Rock-type
                            is_rock_type = "Rock" in (opponent_mon.types or [])
                            if not is_rock_type:
                                opponent_mon._gmax_volcalith_active = True
                                opponent_mon._gmax_volcalith_turns = 4
                                log.append(f"  {opponent_mon.species} was caught in the volcalith!")
                
                # G-Max Tartness: Reduces targets' evasiveness
                elif "tartness" in move_name_lower:
                    if dfn and dfn.hp > 0:
                        msgs = modify_stages(dfn, {"evasion": -1}, caused_by_opponent=True, field_effects=self.field)
                        for msg in msgs:
                            log.append(f"  {msg}")
                
                # G-Max Sweetness: Heals user and active allies of status conditions
                elif "sweetness" in move_name_lower:
                    user_team = self.team_for(uid)
                    healed_any = False
                    for ally in user_team:
                        if ally and ally.hp > 0:
                            if ally.status:
                                status_name = ally.status.replace("psn", "poison").replace("tox", "badly poisoned").replace("slp", "sleep").replace("par", "paralysis").replace("brn", "burn").replace("frz", "freeze").title()
                                ally.status = None
                                ally.status_turns = 0
                                if hasattr(ally, 'toxic_counter'):
                                    ally.toxic_counter = 0
                                log.append(f"  {ally.species} was cured of its {status_name}!")
                                healed_any = True
                    if not healed_any:
                        log.append(f"  But it failed!")
                
                # G-Max Sandblast: Binds target for 4-5 turns (doesn't end if user switches/faints)
                elif "sandblast" in move_name_lower:
                    if dfn and dfn.hp > 0:
                        duration = random.randint(4, 5)
                        dfn.partially_trapped = True
                        dfn.partial_trap_turns = duration
                        dfn.partial_trap_damage = 1 / 8  # Same as Sand Tomb
                        dfn.trapped = True
                        dfn.trap_source = atk.species
                        dfn._partial_trap_move = "sand-tomb"
                        dfn._gmax_sandblast_active = True  # Flag to prevent ending on user switch/faint
                        log.append(f"  {dfn.species} was trapped in the sandblast!")
                
                # G-Max Stun Shock: Either poisons or paralyzes all adjacent foes (50% chance each, per target)
                elif "stun-shock" in move_name_lower or "stunshock" in move_name_lower:
                    opponent_uid = self.p2_id if uid == self.p1_id else self.p1_id
                    opponent_team = self.team_for(opponent_uid)
                    for opponent_mon in opponent_team:
                        if opponent_mon and opponent_mon.hp > 0:
                            # 50% chance for poison, 50% chance for paralysis
                            status_choice = random.choice(["psn", "par"])
                            success, status_msg = apply_status_effect(opponent_mon, status_choice, atk, field_effects=self.field)
                            if success and status_msg:
                                log.append(f"  {status_msg}")
                
                # G-Max Centiferno: Binds target for 4-5 turns (doesn't end if user switches/faints)
                elif "centiferno" in move_name_lower:
                    if dfn and dfn.hp > 0:
                        duration = random.randint(4, 5)
                        dfn.partially_trapped = True
                        dfn.partial_trap_turns = duration
                        dfn.partial_trap_damage = 1 / 8  # Same as Fire Spin
                        dfn.trapped = True
                        dfn.trap_source = atk.species
                        dfn._partial_trap_move = "fire-spin"
                        dfn._gmax_centiferno_active = True  # Flag to prevent ending on user switch/faint
                        log.append(f"  {dfn.species} was trapped in the centiferno!")
                
                # G-Max Smite: Confuses all opponents
                elif "smite" in move_name_lower:
                    opponent_uid = self.p2_id if uid == self.p1_id else self.p1_id
                    opponent_team = self.team_for(opponent_uid)
                    for opponent_mon in opponent_team:
                        if opponent_mon and opponent_mon.hp > 0:
                            if not getattr(opponent_mon, 'confused', False):
                                opponent_mon.confused = True
                                opponent_mon.confusion_turns = random.randint(1, 4)
                                opponent_mon._confusion_applied_this_turn = True
                                log.append(f"  {opponent_mon.species} became confused!")
                
                # G-Max Snooze: 50% chance to make target drowsy (falls asleep next turn)
                elif "snooze" in move_name_lower:
                    if dfn and dfn.hp > 0:
                        # Check if target already has a non-volatile status condition
                        has_status = dfn.status and dfn.status.lower() in ["psn", "tox", "brn", "par", "slp", "frz", "poison", "toxic", "burn", "paralysis", "sleep", "freeze"]
                        if not has_status:
                            if random.random() < 0.5:  # 50% chance
                                dfn.drowsy_turns = 1
                                dfn.drowsy_source = atk
                                log.append(f"  {dfn.species} became drowsy!")
                            else:
                                log.append(f"  But it failed!")
                        else:
                            log.append(f"  But it failed!")
                
                # G-Max Finale: Heals user and allies by 1/6 of their current maximum HP (including Dynamax HP boost)
                elif "finale" in move_name_lower:
                    user_team = self.team_for(uid)
                    healed_any = False
                    for ally in user_team:
                        if ally and ally.hp > 0:
                            # Use current max_hp (includes Dynamax HP boost if Dynamaxed)
                            heal_amount = max(1, ally.max_hp // 6)
                            old_hp = ally.hp
                            ally.hp = min(ally.max_hp, ally.hp + heal_amount)
                            actual_heal = ally.hp - old_hp
                            if actual_heal > 0:
                                log.append(f"  {ally.species} regained {actual_heal} HP!")
                                healed_any = True
                    if not healed_any:
                        log.append(f"  But it failed!")
                
                # G-Max Steelsurge: Sets Steel Spikes entry hazard on target's side
                elif "steelsurge" in move_name_lower or "steel-surge" in move_name_lower:
                    defender_uid = self.p2_id if uid == self.p1_id else self.p1_id
                    defender_side = self.p1_side if defender_uid == self.p1_id else self.p2_side
                    if not defender_side.hazards.steel_spikes:
                        defender_side.hazards.steel_spikes = True
                        log.append(f"  **Steel Spikes** scattered around the opposing team!")
                    else:
                        log.append(f"  But it failed!")
                
                # G-Max Depletion: Reduces PP of target's last used move by 2 if target has used a move
                elif "depletion" in move_name_lower:
                    if dfn and dfn.hp > 0:
                        last_move = getattr(dfn, 'last_move_used', None)
                        if last_move and last_move.lower() != "struggle":
                            # Get the target's user ID to access their PP
                            defender_uid = self.p2_id if uid == self.p1_id else self.p1_id
                            # Reduce PP by 2
                            self._ensure_pp_loaded(defender_uid, dfn)
                            key = self._get_mon_key(defender_uid, dfn)
                            canonical_move = _canonical_move_name(last_move)
                            store = self._pp.get(key, {})
                            current_pp = store.get(canonical_move) or store.get(last_move) or _max_pp(last_move, generation=self.gen)
                            if current_pp > 0:
                                new_pp = max(0, current_pp - 2)
                                if key not in self._pp:
                                    self._pp[key] = {}
                                self._pp[key][canonical_move] = new_pp
                                log.append(f"  {dfn.species}'s {last_move.replace('-', ' ').title()} lost 2 PP!")
                            else:
                                log.append(f"  But it failed!")
                        else:
                            log.append(f"  But it failed!")
                
                # G-Max Vine Lash: Residual damage for 4 turns to non-Grass-type foes
                elif "vine-lash" in move_name_lower or "vinelash" in move_name_lower:
                    opponent_uid = self.p2_id if uid == self.p1_id else self.p1_id
                    opponent_team = self.team_for(opponent_uid)
                    for opponent_mon in opponent_team:
                        if opponent_mon and opponent_mon.hp > 0:
                            # Check if opponent is Grass-type
                            is_grass_type = "Grass" in (opponent_mon.types or [])
                            if not is_grass_type:
                                opponent_mon._gmax_vine_lash_active = True
                                opponent_mon._gmax_vine_lash_turns = 4
                                log.append(f"  {opponent_mon.species} was caught in the vine lash!")
                
                # G-Max Cannonade: Residual damage for 4 turns to non-Water-type foes
                elif "cannonade" in move_name_lower:
                    opponent_uid = self.p2_id if uid == self.p1_id else self.p1_id
                    opponent_team = self.team_for(opponent_uid)
                    for opponent_mon in opponent_team:
                        if opponent_mon and opponent_mon.hp > 0:
                            # Check if opponent is Water-type
                            is_water_type = "Water" in (opponent_mon.types or [])
                            if not is_water_type:
                                opponent_mon._gmax_cannonade_active = True
                                opponent_mon._gmax_cannonade_turns = 4
                                log.append(f"  {opponent_mon.species} was caught in the cannonade!")
                
                # G-Max Drum Solo: Ignores target's Ability, power is always 160
                elif "drum-solo" in move_name_lower or "drumsolo" in move_name_lower:
                    # Set flag to ignore abilities and override power
                    atk._gmax_ignores_ability = True
                    atk._gmax_fixed_power = 160
                    log.append(f"  {atk.species}'s move ignored {dfn.species if dfn else 'the target'}'s Ability!")
                
                # G-Max Fireball: Ignores ignorable Abilities, power is always 160
                elif "fireball" in move_name_lower:
                    # Set flag to ignore ignorable abilities and override power
                    atk._gmax_ignores_ignorable_abilities = True
                    atk._gmax_fixed_power = 160
                    log.append(f"  {atk.species}'s move ignored the target's Ability!")
                
                # G-Max Hydrosnipe: Ignores target's Ability, power is always 160
                elif "hydrosnipe" in move_name_lower:
                    # Set flag to ignore abilities and override power
                    atk._gmax_ignores_ability = True
                    atk._gmax_fixed_power = 160
                    log.append(f"  {atk.species}'s move ignored {dfn.species if dfn else 'the target'}'s Ability!")
        
        # Clear G-Max ability ignoring flags after move execution
        if hasattr(atk, '_gmax_ignores_ability'):
            delattr(atk, '_gmax_ignores_ability')
        if hasattr(atk, '_gmax_ignores_ignorable_abilities'):
            delattr(atk, '_gmax_ignores_ignorable_abilities')
        if hasattr(atk, '_gmax_fixed_power'):
            delattr(atk, '_gmax_fixed_power')

        # Wake-Up Slap: Wake up sleeping target (if not behind substitute)
        if move_lower == "wake-up-slap" and dfn:
            effect_data = get_move_secondary_effect(move_lower)
            if effect_data.get("wakes_target"):
                has_substitute = getattr(dfn, 'has_substitute', False) or getattr(dfn, '_substitute_hp', 0) > 0
                if dfn.status == "slp" and not has_substitute:
                    dfn.status = None
                    dfn.status_turns = 0
                    log.append(f"  **{dfn.species}** woke up!")

        # Determine if the move connected (hit and had effect)
        # Check move_result for failure indicators
        move_connected = True
        if move_result:
            result_lower = move_result.lower()
            # Check for failure indicators
            if any(phrase in result_lower for phrase in ["but it failed", "missed", "doesn't affect", "no effect", "immune"]):
                move_connected = False
            # Also check if target fainted before the move (wouldn't have connected)
            if dfn and dfn.hp <= 0 and "fainted" in result_lower and "before" in result_lower:
                move_connected = False
        
        move_data = _get_move_with_cache(chosen, battle_state=self, generation=self.gen)
        restriction_msgs = apply_move_restrictions(atk, dfn, chosen, move_data or {"category": "physical"},
                                                  field_effects=self.field, battle_state=self, move_connected=move_connected)
        for msg in restriction_msgs:
            log.append(f"  {msg}")
        
        # Recharge flag is set in engine.py's apply_move function
        # It only sets the flag if the move actually connected and had an effect

        _record_last_move(atk, chosen, battle_state=self)
        if hasattr(atk, '_mirror_move_copied') and atk._mirror_move_copied:
            _record_last_move(atk, atk._mirror_move_copied, battle_state=self)
            delattr(atk, '_mirror_move_copied')

        if dfn is not None and atk is not dfn:
            dfn.last_move_targeted = atk.last_move_used
            dfn.last_move_target_source = atk

        pivot_moves = ["volt-switch", "u-turn", "flip-turn", "parting-shot"]
        # Check if this is a direct pivot move OR if a pivot move was called via Sleep Talk/Metronome
        is_pivot_move = move_lower in pivot_moves
        if not is_pivot_move:
            # Check if Sleep Talk/Metronome called a pivot move
            if move_lower in ["sleep-talk", "metronome"]:
                # Check if the called move was a pivot move
                called_move = getattr(atk, '_metronome_called_move', None) or getattr(atk, '_sleep_talk_called_move', None)
                if called_move:
                    called_move_lower = called_move.lower().replace(" ", "-")
                    if called_move_lower in pivot_moves:
                        is_pivot_move = True
                    else:
                        # Also check move effects for switches_out flag using database
                        from .db_move_effects import get_move_effects
                        called_move_effect = get_move_effects(called_move_lower) or {}
                        # Also check common pivot moves by name
                        if called_move_lower in ["teleport", "chilly-reception", "baton-pass", "shed-tail"]:
                            is_pivot_move = True
                        elif called_move_effect.get("switches_out") or called_move_effect.get("forces_switch"):
                            is_pivot_move = True
        
        if is_pivot_move and atk.hp > 0:
            move_had_effect = "no effect" not in move_result.lower() and "doesn't affect" not in move_result.lower()
            if move_had_effect and not hasattr(atk, '_pivot_switch_pending'):
                atk._pivot_switch_pending = True
        
        # Clear the called move flags after checking for pivot moves
        if hasattr(atk, '_sleep_talk_called_move'):
            delattr(atk, '_sleep_talk_called_move')

        if dfn and dfn.hp > 0 and hasattr(dfn, '_emergency_exit_triggered') and dfn._emergency_exit_triggered:
            dfn._emergency_exit_triggered = False
            dfn._emergency_exit_pending = True
            if hasattr(atk, '_pivot_switch_pending') and atk._pivot_switch_pending:
                atk._pivot_switch_pending = False

        if atk.hp > 0 and hasattr(atk, '_emergency_exit_triggered') and atk._emergency_exit_triggered:
            atk._emergency_exit_triggered = False
            atk._emergency_exit_pending = True

        if dfn and dfn.hp <= 0:
            from .engine import break_jaw_lock, release_octolock
            break_jaw_lock(dfn)
            release_octolock(dfn)
            _record_registered_ko(atk, dfn, battle_state=self)
            _dispatch_award_exp_on_faint_callback(self, dfn)
            log.append(f"**{dfn.species}** fainted!")
            self._reconcile_special_weather(immediate_log=log)
            defender_uid = self.p2_id if uid == self.p1_id else self.p1_id
            defender_party = self.p2_team if defender_uid == self.p2_id else self.p1_team
            for mon in defender_party:
                if mon.hp > 0:
                    mon._fainted_allies += 1

            from .special_moves import check_destiny_bond, check_grudge
            if check_destiny_bond(atk, dfn):
                atk.hp = 0
                log.append(f"**{atk.species}** took its attacker down with it!")
                attacker_party = self.p1_team if uid == self.p1_id else self.p2_team
                for mon in attacker_party:
                    if mon.hp > 0:
                        mon._fainted_allies += 1

            grudge_msg = check_grudge(atk, dfn, chosen)
            if grudge_msg:
                log.append(f"  {grudge_msg}")

            attacker_ability = normalize_ability_name(atk.ability or "")
            attacker_ability_data = get_ability_effect(attacker_ability)
            from .engine import modify_stages
            if "on_ko" in attacker_ability_data and atk.hp > 0:
                on_ko_effect = attacker_ability_data["on_ko"]
                if "stages" in on_ko_effect:
                    stage_msgs = modify_stages(atk, on_ko_effect["stages"])
                    for msg in stage_msgs:
                        log.append(msg)
                elif on_ko_effect.get("boost_highest_stat"):
                    # Beast Boost: Boost highest stat
                    # Bulbapedia: "For determining the highest stat, Beast Boost does not take into account 
                    # stat stages, held items, or reductions due to status conditions"
                    # Use the original calculated stats stored when the Mon was created
                    original_stats = getattr(atk, '_original_calculated_stats', None)
                    if original_stats:
                        stats = {
                            "atk": int(original_stats.get("atk", 0)),
                            "defn": int(original_stats.get("defn", 0)),
                            "spa": int(original_stats.get("spa", 0)),
                            "spd": int(original_stats.get("spd", 0)),
                            "spe": int(original_stats.get("spe", 0))
                        }
                    else:
                        # Fallback to current stats if original not stored
                        stats = {
                            "atk": int(atk.stats.get("atk", 0)),
                            "defn": int(atk.stats.get("defn", 0)),
                            "spa": int(atk.stats.get("spa", 0)),
                            "spd": int(atk.stats.get("spd", 0)),
                            "spe": int(atk.stats.get("spe", 0))
                        }
                    # Find the highest stat value - ensure we're comparing integers
                    highest_value = max(stats.values())
                    # Find all stats with the highest value
                    tied_stats = [stat for stat, value in stats.items() if value == highest_value]
                    # If there's a tie, prioritize: Attack > Defense > Sp. Atk > Sp. Def > Speed
                    if len(tied_stats) > 1:
                        priority_order = ["atk", "defn", "spa", "spd", "spe"]
                        for stat in priority_order:
                            if stat in tied_stats:
                                highest_stat = stat
                                break
                    else:
                        highest_stat = tied_stats[0]
                    stage_msgs = modify_stages(atk, {highest_stat: 1})
                    for msg in stage_msgs:
                        log.append(msg)

            form_msg = check_form_change(atk, triggered_by="after_ko", field_effects=self.field, battle_state=self)
            if form_msg:
                log.append(f"  {form_msg}")

            defending_user_id = self.p2_id if uid == self.p1_id else self.p1_id
            defending_team = self.team_for(defending_user_id)
            alive_count = sum(1 for mon in defending_team if mon and mon.hp > 0)

            if alive_count == 0:
                defending_player = self.player_name(defending_user_id)
                if defending_user_id == self.p2_id and (self.p2_name or "").lower().startswith("wild "):
                    species = (self.p2_name or "").replace("Wild ", "").replace("wild ", "").replace("⭐", "").strip()
                    log.append(f"\nThe wild {species.title() if species else 'Pokémon'} was defeated.")
                else:
                    log.append(f"\n**{defending_player}** has no more Pokémon left!")
                self.winner = uid
            else:
                defending_player = self.player_name(defending_user_id)
                log.append(f"**{defending_player}** must send out another Pokémon!")

        act["_processed"] = True

    def _handle_pursuit_pre_switch(
        self,
        switching_uid: int,
        switch_action: Dict[str, Any],
        opponent_action: Dict[str, Any],
        log: List[str],
        c1: Dict[str, Any],
        c2: Dict[str, Any]
    ) -> None:
        generation = getattr(self, 'gen', 9)
        if generation >= 8:
            return
        if opponent_action.get("kind") != "move":
            return
        move_value = opponent_action.get("value")
        if not move_value or move_value.lower().replace(" ", "-") != "pursuit":
            return

        attacker_uid = self.p2_id if switching_uid == self.p1_id else self.p1_id
        attacker = self._active(attacker_uid)
        defender = self._active(switching_uid)

        if not attacker or attacker.hp <= 0 or not defender or defender.hp <= 0:
            return
        if opponent_action.get("_processed"):
            return

        defender._is_switching = True

        atk_choice = c1 if attacker_uid == self.p1_id else c2
        dfn_choice = c2 if attacker_uid == self.p1_id else c1

        self._execute_move_action(
            attacker_uid,
            opponent_action,
            atk_choice,
            dfn_choice,
            log,
            remaining_move_actions=0,
            defender_override=defender
        )

        if hasattr(defender, '_is_switching'):
            defender._is_switching = False

        if defender.hp <= 0:
            switch_action["kind"] = "noop"
            switch_action["_cancelled"] = True

    # ---- menus ----
    def moves_for(self, uid: int) -> List[str]:
        """Return the set of moves that should be offered in the UI this turn.

        Rules:
        - If Choice-locked and locked move still has PP: show only locked move.
        - If Choice-locked and locked move has 0 PP: show only Struggle (lock remains).
        - Otherwise show all moves with PP > 0; if all 0, show Struggle.
        - Disabled moves are hidden from the UI.
        """
        mon = self._active(uid)
        moves = (mon.moves or ["Tackle"])[:4] if mon.moves else ["Tackle"]
        self._ensure_pp_loaded(uid)

        rollout_move = getattr(mon, 'rollout_move', None)
        if rollout_move and getattr(mon, 'rollout_turns_remaining', 0) > 0:
            forced_name = rollout_move.replace("-", " ").title()
            if self._pp_left(uid, forced_name) > 0:
                return [forced_name]
            return ["Struggle"]

        # Check rampage lock (Outrage, Thrash, Petal Dance)
        if hasattr(mon, 'rampage_move') and mon.rampage_move and hasattr(mon, 'rampage_turns_remaining') and mon.rampage_turns_remaining > 0:
            rampage_move_name = mon.rampage_move.replace("-", " ").title()
            if self._pp_left(uid, rampage_move_name) > 0:
                return [rampage_move_name]
            # Rampage move out of PP -> Struggle only
            return ["Struggle"]
        
        # Check choice item lock
        locked = self._choice_move(uid)
        if locked:
            if self._pp_left(uid, locked) > 0:
                return [locked]
            # locked move is out of PP -> Struggle only, still locked
            return ["Struggle"]

        # Not locked: show moves with PP > 0 and not disabled
        available = []
        for m in moves:
            # Skip disabled moves
            if hasattr(mon, 'disabled_move') and mon.disabled_move:
                if m.lower().replace(" ", "-") == mon.disabled_move.lower().replace(" ", "-"):
                    continue
            
            # Skip moves with 0 PP
            if self._pp_left(uid, m) > 0:
                is_taunted = (
                    (getattr(mon, 'taunted', False) and getattr(mon, 'taunt_turns', 0) > 0)
                    or getattr(mon, '_taunt_pending', False)
                )

                if is_taunted:
                    move_data = _get_move_with_cache(m, battle_state=self, generation=self.gen)
                    move_effect = get_move_secondary_effect(m) or {}
                    move_category = (move_data.get('damage_class') or move_data.get('category') or '').lower() if move_data else ''
                    move_power = move_data.get('power') if move_data else None
                    variable_power = bool(move_effect.get('variable_power'))
                    power_val = move_power if isinstance(move_power, (int, float)) else 0
                    is_status = move_category == 'status' or (power_val <= 0 and not variable_power)
                    if is_status and m.lower().replace(" ", "-") != "struggle":
                        continue
                available.append(m)
        
        return available if available else ["Struggle"]

    def switch_options(self, uid: int) -> List[int]:
        team = self.team_for(uid)
        cur = self.p1_active if uid == self.p1_id else self.p2_active
        mon = self._active(uid)
        if mon and getattr(mon, 'rollout_turns_remaining', 0) > 0:
            return []
        # Prevent switching when locked into a rampage move (Thrash, Outrage, Petal Dance, etc.)
        if mon and getattr(mon, 'rampage_move', None) and getattr(mon, 'rampage_turns_remaining', 0) > 0:
            return []
        return [i for i, mon in enumerate(team) if i != cur and mon.hp > 0]

    # ---- lock / unlock per turn (UI taps) ----
    def is_locked(self, uid: int) -> bool: return bool(self._locked.get(uid))
    def lock(self, uid: int) -> None: self._locked[uid] = True
    def unlock(self, uid: int) -> None: self._locked[uid] = False
    def unlock_both(self) -> None:
        self._locked[self.p1_id] = False
        self._locked[self.p2_id] = False
        # NOTE: choice lock persists across turns; do not clear here.

    # ---- actions ----
    def apply_forfeit(self, who_id: int):
        self.winner = self.p2_id if who_id == self.p1_id else self.p1_id

    def apply_switch(self, uid: int, to_index: int, forced: bool = False):
        """
        Switch out the active Pokemon.
        
        Args:
            uid: User ID
            to_index: Index of Pokemon to switch to
            forced: True if switching in due to previous Pokemon fainting, False for voluntary switch
        
        Returns:
            List of messages to add to the battle log (e.g., Leech Seed damage)
        """
        messages = []
        # Capture the Pokémon switching out for on-switch-out abilities
        switching_out_mon = self._active(uid)
        
        # Apply Leech Seed damage BEFORE clearing it (opponent should be sapped on the turn the user switches)
        if switching_out_mon and hasattr(switching_out_mon, 'leech_seeded') and switching_out_mon.leech_seeded:
            opponent_id = self.p2_id if uid == self.p1_id else self.p1_id
            opponent = self._active(opponent_id)
            
            if opponent:
                # Check for Magic Guard (blocks Leech Seed damage)
                switching_ability = normalize_ability_name(switching_out_mon.ability or "")
                switching_ability_data = get_ability_effect(switching_ability)
                magic_guard_active = switching_ability_data.get("no_indirect_damage", False)
                
                if not magic_guard_active:
                    # Store HP before damage to calculate actual HP drained
                    old_hp = switching_out_mon.hp
                    damage = max(1, switching_out_mon.max_hp // 8)  # 1/8 max HP damage
                    
                    # Apply damage (may cause fainting)
                    # Dummy Magikarp is immortal - never goes below 1 HP
                    if getattr(switching_out_mon, '_is_dummy_magikarp', False):
                        switching_out_mon.hp = max(1, switching_out_mon.hp - damage)
                    else:
                        switching_out_mon.hp = max(0, switching_out_mon.hp - damage)
                    
                    # Calculate actual HP drained (cannot exceed what was available)
                    actual_damage_dealt = old_hp - switching_out_mon.hp
                    
                    # Always show the Leech Seed damage message (original game phrase)
                    if actual_damage_dealt > 0:
                        messages.append(f"{switching_out_mon.species}'s health is sapped by Leech Seed!")
                    
                    # Only heal opponent based on actual HP drained
                    if actual_damage_dealt > 0 and opponent != switching_out_mon and opponent.hp > 0:
                        # Heal based on actual HP drained (not the full damage amount if mon fainted)
                        heal = min(actual_damage_dealt, opponent.max_hp - opponent.hp)
                        if heal > 0:
                            opponent.hp = min(opponent.max_hp, opponent.hp + heal)
        
        # Clear Water Sport and Mud Sport if the user switches out (Gen 3-4 only)
        if switching_out_mon and self.gen <= 4:
            switching_out_id = id(switching_out_mon)
            if hasattr(self.field, 'water_sport_user') and self.field.water_sport_user == switching_out_id:
                self.field.water_sport = False
                self.field.water_sport_turns = 0
                self.field.water_sport_user = None
            if hasattr(self.field, 'mud_sport_user') and self.field.mud_sport_user == switching_out_id:
                self.field.mud_sport = False
                self.field.mud_sport_turns = 0
                self.field.mud_sport_user = None
        
        if switching_out_mon:
            from .engine import break_jaw_lock, release_octolock
            break_jaw_lock(switching_out_mon)
            release_octolock(switching_out_mon)
            if hasattr(switching_out_mon, '_partial_trap_move'):
                delattr(switching_out_mon, '_partial_trap_move')
            
            # Free opponent from partial trap if they were trapped by this Pokemon
            # (Thunder Cage and other partial trapping moves end when user switches out)
            opponent_id = self.p2_id if uid == self.p1_id else self.p1_id
            opponent = self._active(opponent_id)
            if opponent and getattr(opponent, 'partially_trapped', False):
                # Check if opponent was trapped by switching out Pokemon
                trap_source = getattr(opponent, 'trap_source', None)
                if trap_source == switching_out_mon.species:
                    # Free the opponent from the partial trap
                    trap_move = getattr(opponent, '_partial_trap_move', None)
                    opponent.partially_trapped = False
                    opponent.partial_trap_turns = 0
                    opponent.partial_trap_damage = 0.0
                    opponent.trapped = False
                    opponent.trap_source = None
                    if hasattr(opponent, '_partial_trap_move'):
                        delattr(opponent, '_partial_trap_move')
                    # Mark for message display (Thunder Cage specific)
                    if trap_move == "thunder-cage":
                        opponent._thunder_cage_freed = True
        
        # Revert Transform when switching out (Ditto goes back to Ditto)
        pending_weather_msg: Optional[str] = None

        if switching_out_mon:
            # Revert Dynamax when switching out
            if switching_out_mon.dynamaxed:
                from .max_moves import revert_dynamax
                revert_dynamax(switching_out_mon)
            
            from .special_moves import revert_transform
            revert_transform(switching_out_mon)
            
            # Revert Battle Bond transformation (Ash-Greninja → Greninja)
            from .battle_bond_transform import revert_battle_bond_transform
            revert_battle_bond_transform(switching_out_mon)
            
            # Restore original ability if it was changed by Mummy
            if hasattr(switching_out_mon, '_original_ability_before_mummy'):
                switching_out_mon.ability = switching_out_mon._original_ability_before_mummy
                delattr(switching_out_mon, '_original_ability_before_mummy')

            # Restore Mimic-copied move (revert to original Mimic)
            if hasattr(switching_out_mon, '_mimic_original_move') and hasattr(switching_out_mon, '_mimic_original_index'):
                mimic_idx = switching_out_mon._mimic_original_index
                if mimic_idx < len(switching_out_mon.moves):
                    moves_list = list(switching_out_mon.moves)
                    moves_list[mimic_idx] = switching_out_mon._mimic_original_move
                    switching_out_mon.moves = tuple(moves_list) if isinstance(switching_out_mon.moves, tuple) else moves_list
                delattr(switching_out_mon, '_mimic_original_move')
                delattr(switching_out_mon, '_mimic_original_index')

            # Clear Defense Curl flag when leaving the field
            if hasattr(switching_out_mon, '_defense_curl_used'):
                delattr(switching_out_mon, '_defense_curl_used')

            # Clear Autotomize weight reduction flags when leaving the field
            if hasattr(switching_out_mon, '_autotomize_used'):
                delattr(switching_out_mon, '_autotomize_used')
            if hasattr(switching_out_mon, '_weight_before_autotomize'):
                delattr(switching_out_mon, '_weight_before_autotomize')

            if hasattr(switching_out_mon, '_sky_drop_target'):
                target_ref = getattr(switching_out_mon, '_sky_drop_target', None)
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
                delattr(switching_out_mon, '_sky_drop_target')

            if hasattr(switching_out_mon, '_consecutive_ally_switches'):
                delattr(switching_out_mon, '_consecutive_ally_switches')

            if hasattr(switching_out_mon, '_sky_drop_cannot_move'):
                delattr(switching_out_mon, '_sky_drop_cannot_move')
            if hasattr(switching_out_mon, '_sky_drop_lifted'):
                delattr(switching_out_mon, '_sky_drop_lifted')
            if hasattr(switching_out_mon, '_sky_drop_invulnerable'):
                delattr(switching_out_mon, '_sky_drop_invulnerable')
            if hasattr(switching_out_mon, '_sky_drop_prev_invulnerable'):
                delattr(switching_out_mon, '_sky_drop_prev_invulnerable')
            if hasattr(switching_out_mon, '_sky_drop_prev_invulnerable_type'):
                delattr(switching_out_mon, '_sky_drop_prev_invulnerable_type')
            if hasattr(switching_out_mon, '_sky_drop_lifted_by'):
                delattr(switching_out_mon, '_sky_drop_lifted_by')
            if hasattr(switching_out_mon, 'center_of_attention'):
                switching_out_mon.center_of_attention = False
            if hasattr(switching_out_mon, '_center_of_attention_source'):
                delattr(switching_out_mon, '_center_of_attention_source')
            if hasattr(switching_out_mon, '_z_grudge_center'):
                delattr(switching_out_mon, '_z_grudge_center')
            
            # Sleep counter reset on switch (Gen V: resets to original, Gen VI+: does not reset)
            from .generation import get_generation
            generation = get_generation(field_effects=self.field)
            if switching_out_mon.status and switching_out_mon.status.lower() in ["slp", "sleep"]:
                if generation >= 5 and generation < 6:
                    # Gen V: Reset to original sleep counter when switched out
                    original_sleep_turns = getattr(switching_out_mon, '_original_sleep_turns', None)
                    if original_sleep_turns is not None:
                        switching_out_mon.status_turns = original_sleep_turns
                # Gen VI+: Sleep counter does NOT reset when switched out (keep current value)
                # Gen 1-4: Sleep counter does NOT reset when switched out (keep current value)

            if hasattr(switching_out_mon, '_guard_split_original_stats'):
                switching_out_mon.stats["defn"] = switching_out_mon._guard_split_original_stats["defn"]
                switching_out_mon.stats["spd"] = switching_out_mon._guard_split_original_stats["spd"]
                delattr(switching_out_mon, '_guard_split_original_stats')
            if hasattr(switching_out_mon, '_power_split_original_stats'):
                switching_out_mon.stats["atk"] = switching_out_mon._power_split_original_stats["atk"]
                switching_out_mon.stats["spa"] = switching_out_mon._power_split_original_stats["spa"]
                delattr(switching_out_mon, '_power_split_original_stats')

            reset_rollout(switching_out_mon)

            # Clear Focus Energy-style effects on switch-out
            if getattr(switching_out_mon, 'focused_energy', False):
                switching_out_mon.focused_energy = False
            switching_out_mon.focused_energy_stage = 0

            # Clear stored targeting data for Mirror Move interactions
            switching_out_mon.last_move_targeted = None
            switching_out_mon.last_move_target_source = None

            # Clear Bide switch restriction, if any
            if hasattr(switching_out_mon, '_bide_cannot_switch'):
                switching_out_mon._bide_cannot_switch = False

            # If this Pokémon was maintaining special weather (from Primals), clear it now
            owner_id = getattr(self.field, "weather_lock_owner", None)
            special = getattr(self.field, "special_weather", None)
            if special and owner_id == id(switching_out_mon):
                cleared = clear_special_weather(self.field)
                if cleared:
                    pending_weather_msg = {
                        "heavy-rain": "The heavy rain disappeared!",
                        "harsh-sunlight": "The extremely harsh sunlight faded!",
                        "strong-winds": "The mysterious strong winds dissipated!"
                    }.get(cleared, "The special weather faded.")
        
        # Reset stat stages of the Pokémon switching out
        # === NULLSCAPE (Ghost): Non-Ghost Pokémon keep negative stat changes on switch ===
        if switching_out_mon:
            nullscape_type_ghost = None
            from .engine import _get_nullscape_type
            nullscape_type_ghost = _get_nullscape_type(switching_out_mon, self)
            
            if nullscape_type_ghost == "Ghost":
                # Ghost Nullscape: Non-Ghost Pokémon keep negative stat changes
                switching_out_types = [t.strip().title() if t else None for t in switching_out_mon.types]
                if "Ghost" not in switching_out_types:
                    # Keep negative stat stages, only reset positive ones
                    old_stages = switching_out_mon.stages.copy()
                    switching_out_mon.stages = {
                        "atk": min(0, old_stages.get("atk", 0)),
                        "defn": min(0, old_stages.get("defn", 0)),
                        "spa": min(0, old_stages.get("spa", 0)),
                        "spd": min(0, old_stages.get("spd", 0)),
                        "spe": min(0, old_stages.get("spe", 0)),
                        "accuracy": 0,
                        "evasion": 0
                    }
                else:
                    # Ghost types reset normally
                    switching_out_mon.stages = {
                        "atk": 0, "defn": 0, "spa": 0, "spd": 0, "spe": 0, 
                        "accuracy": 0, "evasion": 0
                    }
            else:
                # Normal behavior: reset all stat stages
                switching_out_mon.stages = {
                    "atk": 0, "defn": 0, "spa": 0, "spd": 0, "spe": 0, 
                    "accuracy": 0, "evasion": 0
                }
            # Clear Substitute (doesn't persist on switch)
            switching_out_mon.substitute = None
            # Clear Leech Seed (doesn't persist on switch)
            if hasattr(switching_out_mon, 'leech_seeded') and switching_out_mon.leech_seeded:
                switching_out_mon.leech_seeded = False
            # Clear two-turn move charging state (Fly, Dig, etc.)
            switching_out_mon.charging_move = None
            switching_out_mon.invulnerable = False
            switching_out_mon.invulnerable_type = None
            switching_out_mon.lock_on_target = None
            switching_out_mon.lock_on_turns = 0
            if hasattr(switching_out_mon, '_mind_reader_target'):
                switching_out_mon._mind_reader_target = None
            if hasattr(switching_out_mon, 'laser_focus_turns'):
                switching_out_mon.laser_focus_turns = 0
            if hasattr(switching_out_mon, '_laser_focus_pending'):
                switching_out_mon._laser_focus_pending = False
            if hasattr(switching_out_mon, '_moved_this_turn'):
                switching_out_mon._moved_this_turn = False

            if getattr(switching_out_mon, 'ingrained', False) or getattr(switching_out_mon, '_ingrained', False):
                switching_out_mon.ingrained = False
                if hasattr(switching_out_mon, '_ingrained'):
                    switching_out_mon._ingrained = False
                if hasattr(switching_out_mon, '_ingrain_generation'):
                    delattr(switching_out_mon, '_ingrain_generation')

            if getattr(switching_out_mon, 'drowsy_turns', 0) > 0:
                switching_out_mon.drowsy_turns = 0
                switching_out_mon.drowsy_source = None
                if hasattr(switching_out_mon, '_yawn_generation'):
                    delattr(switching_out_mon, '_yawn_generation')
            if hasattr(switching_out_mon, '_took_damage_this_turn'):
                switching_out_mon._took_damage_this_turn = False
            if hasattr(switching_out_mon, '_mind_reader_active'):
                delattr(switching_out_mon, '_mind_reader_active')
            if hasattr(switching_out_mon, '_mind_reader_user'):
                prev_user = switching_out_mon._mind_reader_user
                if prev_user and getattr(prev_user, 'lock_on_target', None) == switching_out_mon:
                    prev_user.lock_on_target = None
                    prev_user.lock_on_turns = 0
                    if hasattr(prev_user, '_mind_reader_target'):
                        prev_user._mind_reader_target = None
                delattr(switching_out_mon, '_mind_reader_user')
            
            # Clear Foresight flags on switch-out (Gen III+: cannot be Baton Passed)
            # Gen II: Foresight can be Baton Passed, so don't clear if Baton Pass is transferring it
            from .generation import get_generation
            gen_switch = get_generation(field_effects=self.field)
            if gen_switch >= 3:
                # Gen III+: Clear Foresight on switch-out (cannot be Baton Passed)
                if hasattr(switching_out_mon, '_foresight_active'):
                    switching_out_mon._foresight_active = False
                if hasattr(switching_out_mon, '_foresight_ghost_immunity_removed'):
                    switching_out_mon._foresight_ghost_immunity_removed = False
                if hasattr(switching_out_mon, '_foresight_evasion_ignored'):
                    switching_out_mon._foresight_evasion_ignored = False
                if hasattr(switching_out_mon, '_foresight_perfect_acc'):
                    switching_out_mon._foresight_perfect_acc = False
                if hasattr(switching_out_mon, '_foresight_acc_ev_balanced'):
                    switching_out_mon._foresight_acc_ev_balanced = False
            elif gen_switch == 2:
                # Gen II: Only clear if NOT being Baton Passed
                is_baton_pass_foresight = False
                if hasattr(self, '_baton_pass_foresight') and uid in getattr(self, '_baton_pass_foresight', {}):
                    is_baton_pass_foresight = True
                
                if not is_baton_pass_foresight:
                    # Clear Foresight if not being Baton Passed
                    if hasattr(switching_out_mon, '_foresight_active'):
                        switching_out_mon._foresight_active = False
                    if hasattr(switching_out_mon, '_foresight_ghost_immunity_removed'):
                        switching_out_mon._foresight_ghost_immunity_removed = False
                    if hasattr(switching_out_mon, '_foresight_acc_ev_balanced'):
                        switching_out_mon._foresight_acc_ev_balanced = False
            if hasattr(switching_out_mon, 'ability_suppressed'):
                switching_out_mon.ability_suppressed = False
            if hasattr(switching_out_mon, '_ability_suppressed'):
                delattr(switching_out_mon, '_ability_suppressed')
            switching_out_mon.cursed = False
            if hasattr(switching_out_mon, '_cursed_generation'):
                delattr(switching_out_mon, '_cursed_generation')
            if hasattr(switching_out_mon, '_cursed_source'):
                delattr(switching_out_mon, '_cursed_source')
            if hasattr(switching_out_mon, '_tar_shot_active') and switching_out_mon._tar_shot_active:
                switching_out_mon._tar_shot_active = False
            if hasattr(switching_out_mon, '_no_retreat_active') and switching_out_mon._no_retreat_active:
                switching_out_mon._no_retreat_active = False
            
            # Clear Taunt when switching out
            if getattr(switching_out_mon, 'taunted', False):
                switching_out_mon.taunted = False
            if getattr(switching_out_mon, 'taunt_turns', 0) > 0:
                switching_out_mon.taunt_turns = 0
            if hasattr(switching_out_mon, '_taunt_pending'):
                switching_out_mon._taunt_pending = False
        
        if uid == self.p1_id:
            self.p1_active = to_index
            dbid = getattr(self.p1_team[to_index], "_db_id", None) if to_index < len(self.p1_team) else None
            self.p1_participants.add(dbid or self.p1_team[to_index].species)
        else:
            self.p2_active = to_index
            dbid = getattr(self.p2_team[to_index], "_db_id", None) if to_index < len(self.p2_team) else None
            self.p2_participants.add(dbid or self.p2_team[to_index].species)
        
        # Clear lock-on references on other active Pokémon that were targeting the switched-out mon
        for active_mon in (self._active(self.p1_id), self._active(self.p2_id)):
            if active_mon and getattr(active_mon, 'lock_on_target', None) == switching_out_mon:
                active_mon.lock_on_target = None
                active_mon.lock_on_turns = 0
                if hasattr(active_mon, '_mind_reader_target'):
                    active_mon._mind_reader_target = None

        # Reset stat stages and flags of the Pokémon switching in
        new_mon = self._active(uid)
        if new_mon:
            new_mon.stages = {
                "atk": 0, "defn": 0, "spa": 0, "spd": 0, "spe": 0, 
                "accuracy": 0, "evasion": 0
            }
            # Reset Protean/Libero usage flag
            new_mon._protean_used = False
            # Mark that this Pokémon just switched in (for Shadow Tag mechanics)
            new_mon._just_switched_in = True
            # Clear last_move_used when switching in (Mimic needs target to have used a move)
            new_mon.last_move_used = None
            if hasattr(new_mon, '_last_move_used_type'):
                new_mon._last_move_used_type = None

            # Clear residual lock-on/mind reader tracking when arriving
            new_mon.lock_on_target = None
            new_mon.lock_on_turns = 0
            if hasattr(new_mon, '_mind_reader_target'):
                new_mon._mind_reader_target = None
            if hasattr(new_mon, '_mind_reader_active'):
                delattr(new_mon, '_mind_reader_active')
            if hasattr(new_mon, '_mind_reader_user'):
                delattr(new_mon, '_mind_reader_user')
            
            # Clear perish count on normal switch (unless Baton Pass transfers it)
            # Perish count is only cleared if NOT transferring via Baton Pass
            if switching_out_mon and hasattr(switching_out_mon, 'perish_count') and switching_out_mon.perish_count is not None:
                # Check if this is a Baton Pass switch (perish_count will be in volatile_data)
                is_baton_pass = False
                if hasattr(self, '_baton_pass_volatiles') and uid in getattr(self, '_baton_pass_volatiles', {}):
                    volatile_data = self._baton_pass_volatiles.get(uid, {})
                    if 'perish_count' in volatile_data:
                        is_baton_pass = True
                
                # Only clear if NOT Baton Pass (Baton Pass transfers it, normal switch clears it)
                if not is_baton_pass:
                    switching_out_mon.perish_count = None
            
            # Clear Magnet Rise on normal switch (unless Baton Pass transfers it)
            if switching_out_mon and hasattr(switching_out_mon, '_magnet_rise_turns') and getattr(switching_out_mon, '_magnet_rise_turns', 0) > 0:
                # Check if this is a Baton Pass switch (magnet_rise_turns will be in volatile_data)
                is_baton_pass_magnet = False
                if hasattr(self, '_baton_pass_volatiles') and uid in getattr(self, '_baton_pass_volatiles', {}):
                    volatile_data = self._baton_pass_volatiles.get(uid, {})
                    if 'magnet_rise_turns' in volatile_data:
                        is_baton_pass_magnet = True
                
                # Only clear if NOT Baton Pass (Baton Pass transfers it, normal switch clears it)
                if not is_baton_pass_magnet:
                    switching_out_mon._magnet_rise_turns = 0
            
            # Apply Baton Pass transfers (stat stages, substitute, lock-on effects)
            if hasattr(self, '_baton_pass_stages') and uid in getattr(self, '_baton_pass_stages', {}):
                new_mon.stages.update(self._baton_pass_stages.pop(uid, {}))

            if hasattr(self, '_baton_pass_substitute') and uid in getattr(self, '_baton_pass_substitute', {}):
                sub_hp = self._baton_pass_substitute.pop(uid, 0)
                if sub_hp and sub_hp > 0:
                    new_mon.substitute = Substitute(hp=sub_hp, max_hp=sub_hp)

            if hasattr(self, '_baton_pass_lockon_active') and self._baton_pass_lockon_active.pop(uid, False):
                new_mon._mind_reader_active = True

            if hasattr(self, '_baton_pass_lockon_user') and uid in getattr(self, '_baton_pass_lockon_user', {}):
                lock_data = self._baton_pass_lockon_user.pop(uid)
                if lock_data.get("generation", 5) <= 4 and lock_data.get("target"):
                    new_mon.lock_on_target = lock_data["target"]
                    new_mon.lock_on_turns = max(1, lock_data.get("turns", 1))
                    new_mon._mind_reader_target = lock_data["target"]

            if hasattr(self, '_baton_pass_lockon_target') and uid in getattr(self, '_baton_pass_lockon_target', {}):
                target_data = self._baton_pass_lockon_target.pop(uid)
                attacker = target_data.get("attacker")
                if attacker and target_data.get("generation", 5) <= 4:
                    attacker.lock_on_target = new_mon
                    attacker.lock_on_turns = max(1, target_data.get("turns", getattr(attacker, 'lock_on_turns', 1)))
                    attacker._mind_reader_target = new_mon
                    new_mon._mind_reader_user = attacker

            if hasattr(self, '_baton_pass_volatiles') and uid in getattr(self, '_baton_pass_volatiles', {}):
                volatile_data = self._baton_pass_volatiles.pop(uid)

                if volatile_data.get('confused'):
                    new_mon.confused = True
                    new_mon.confusion_turns = max(1, volatile_data.get('confusion_turns', 0))

                if volatile_data.get('focused_energy'):
                    new_mon.focused_energy = True
                    new_mon.focused_energy_stage = volatile_data.get('focused_energy_stage', 0)

                if volatile_data.get('trapped'):
                    new_mon.trapped = True
                    new_mon.trap_source = volatile_data.get('trap_source')
                if volatile_data.get('partially_trapped'):
                    new_mon.partially_trapped = True
                    new_mon.partial_trap_turns = volatile_data.get('partial_trap_turns', 0)
                    new_mon.partial_trap_damage = volatile_data.get('partial_trap_damage', 0.0)

                if volatile_data.get('ability_suppressed'):
                    unsuppressable = {
                        "multitype", "stance-change", "schooling", "comatose",
                        "shields-down", "disguise", "battle-bond", "power-construct",
                        "neutralizing-gas"
                    }
                    ability_norm = (new_mon.ability or "").replace(" ", "-").lower()
                    if ability_norm not in unsuppressable:
                        new_mon.ability_suppressed = True
                        new_mon._ability_suppressed = True

                if volatile_data.get('leech_seeded'):
                    new_mon.leech_seeded = True

                if volatile_data.get('cursed'):
                    new_mon.cursed = True
                    if volatile_data.get('cursed_generation') is not None:
                        new_mon._cursed_generation = volatile_data.get('cursed_generation')
                    if volatile_data.get('cursed_source') is not None:
                        new_mon._cursed_source = volatile_data.get('cursed_source')

                if volatile_data.get('ingrained'):
                    new_mon.ingrained = True
                    new_mon._ingrained = True
                    if volatile_data.get('ingrain_generation') is not None:
                        new_mon._ingrain_generation = volatile_data.get('ingrain_generation')

                if volatile_data.get('aqua_ring'):
                    new_mon.aqua_ring = True

                if 'heal_blocked' in volatile_data:
                    new_mon.heal_blocked = max(volatile_data.get('heal_blocked', 0), getattr(new_mon, 'heal_blocked', 0))

                if 'embargoed' in volatile_data:
                    new_mon.embargoed = max(volatile_data.get('embargoed', 0), getattr(new_mon, 'embargoed', 0))

                if 'perish_count' in volatile_data:
                    new_mon.perish_count = volatile_data.get('perish_count')

                if 'magnet_rise_turns' in volatile_data:
                    new_mon._magnet_rise_turns = volatile_data.get('magnet_rise_turns', 0)

                if 'telekinesis_turns' in volatile_data:
                    is_mega_gengar = False
                    species_lower = (new_mon.species or "").lower()
                    form_lower = str(getattr(new_mon, 'form', '')).lower()
                    if "gengar" in species_lower and "mega" in (species_lower or form_lower):
                        is_mega_gengar = True
                    if not is_mega_gengar:
                        new_mon._telekinesis_turns = volatile_data.get('telekinesis_turns', 0)

                if volatile_data.get('power_trick'):
                    new_mon.stats['atk'], new_mon.stats['defn'] = new_mon.stats['defn'], new_mon.stats['atk']
                    new_mon._power_trick_active = True
            
            # Gen II: Apply Foresight from Baton Pass
            from .generation import get_generation
            gen_switch = get_generation(field_effects=self.field)
            if gen_switch == 2 and hasattr(self, '_baton_pass_foresight') and uid in getattr(self, '_baton_pass_foresight', {}):
                foresight_data = self._baton_pass_foresight.pop(uid)
                # Find the target that should have Foresight
                target_id = foresight_data.get('target_id')
                # Find opponent's active Pokémon
                opponent_id = self.p2_id if uid == self.p1_id else self.p1_id
                opponent = self._active(opponent_id)
                if opponent and id(opponent) == target_id:
                    # Apply Foresight to the same target
                    opponent._foresight_active = True
                    opponent._foresight_ghost_immunity_removed = True
                    if foresight_data.get('acc_ev_balanced', False):
                        opponent._foresight_acc_ev_balanced = True
                        opponent._foresight_user_acc_stage = foresight_data.get('user_acc_stage', 0)
                        opponent._foresight_target_ev_stage = foresight_data.get('target_ev_stage', 0)

            # Reset Paradox ability flags (Quark Drive / Protosynthesis)
            new_mon._paradox_ability_activated = False
            new_mon._paradox_boosted_stat = None
            
            # Mark if this was a forced switch (for abilities like Speed Boost)
            new_mon._forced_switch = forced
            
            # Reset turn counter for Fake Out/First Impression
            from .special_moves import reset_turns_since_switch
            reset_turns_since_switch(new_mon)
            
            # Reset turn-based move counters
            from .advanced_moves import reset_consecutive_counters_on_switch
            reset_consecutive_counters_on_switch(new_mon)

            # Reset stored targeting data
            new_mon.last_move_targeted = None
            new_mon.last_move_target_source = None
            pending_msgs = self._apply_pending_switch_effects(uid, new_mon)
            if pending_msgs:
                new_mon._pending_entry_messages = pending_msgs
        
        # clear choice lock on switch (game behavior)
        self._clear_choice_lock_on_switch(uid)
        
        # Trigger on-switch-out abilities (Regenerator, Natural Cure)
        if switching_out_mon and switching_out_mon.hp > 0:
            ability = normalize_ability_name(switching_out_mon.ability or "")
            ability_data = get_ability_effect(ability)
            
            # Regenerator: Heal 1/3 HP on switch-out
            if ability_data.get("on_switch_out"):
                switch_out_effect = ability_data["on_switch_out"]
                if "heal" in switch_out_effect and switching_out_mon.hp < switching_out_mon.max_hp:
                    heal_percent = switch_out_effect["heal"]
                    heal = max(1, int(switching_out_mon.max_hp * heal_percent))
                    switching_out_mon.hp = min(switching_out_mon.max_hp, switching_out_mon.hp + heal)
                # Natural Cure: Heal status on switch-out
                if switch_out_effect.get("heal_status") and switching_out_mon.status:
                    switching_out_mon.status = None
        
        # === Z-MEMENTO: Heal replacement fully ===
        z_memento_healed = False
        side_effects = self.p1_side if uid == self.p1_id else self.p2_side
        if hasattr(side_effects, '_z_memento_pending') and side_effects._z_memento_pending:
            side_effects._z_memento_pending = False
            new_mon.hp = new_mon.max_hp
            z_memento_healed = True
        
        # === Z-PARTING SHOT: Heal replacement fully ===
        z_parting_shot_healed = False
        if hasattr(side_effects, '_z_parting_shot_pending') and side_effects._z_parting_shot_pending:
            side_effects._z_parting_shot_pending = False
            new_mon.hp = new_mon.max_hp
            z_parting_shot_healed = True
        
        # ensure PP loaded for the new active
        self._ensure_pp_loaded(uid)

        # Reconcile special weather status after the switch
        self._reconcile_special_weather()

        if pending_weather_msg:
            self._pending_weather_messages.append(pending_weather_msg)
        
        # Return messages (e.g., Leech Seed damage)
        return messages

    # ---- order calculation ----
    def _action_order(self, c1: Dict[str, Any], c2: Dict[str, Any]) -> List[int]:
        """Return [first_user_id, second_user_id] using (action kind) > move priority > Speed > coinflip."""
        def rank(uid: int, c: Dict[str, Any]) -> tuple:
            # Higher first: forfeit(4) > switch(3) > throw(2) > move/heal(1) > none(0)
            if c.get("kind") == "forfeit": return (4, 0, 0)
            # Pass side effects and field effects to speed_value for Tailwind and weather abilities
            side = self.p1_side if uid == self.p1_id else self.p2_side
            if c.get("kind") == "switch":  return (3, 0, speed_value(self._active(uid), side, self.field))
            if c.get("kind") == "throw":   return (2, 0, speed_value(self._active(uid), side, self.field))
            if c.get("kind") in ("move", "heal"):
                # Only move choices have a string value; heal has dict value
                move_val = c.get("value")
                move_name = move_val if isinstance(move_val, str) else ""
                pr = action_priority(move_name or "", self._active(uid), self.field, self)
                spd = speed_value(self._active(uid), side, self.field)
                # Trick Room reverses speed order (but not priority)
                if self.field.trick_room:
                    spd = -spd  # Negative speed means slower is faster
                return (1, pr, spd)
            return (0, 0, 0)
        r1, r2 = rank(self.p1_id, c1), rank(self.p2_id, c2)
        if r1 != r2:
            return [self.p1_id, self.p2_id] if r1 > r2 else [self.p2_id, self.p1_id]
        return [self.p1_id, self.p2_id] if random.random() < 0.5 else [self.p2_id, self.p1_id]

    # ---- resolve one turn ----
    def resolve(self, c1: Dict[str, Any], c2: Dict[str, Any], pivot_switch_choice: Optional[Dict[int, int]] = None, start_from_index: int = 0, order_override: Optional[List[int]] = None, actions_override: Optional[Dict[int, Dict[str, Any]]] = None) -> Tuple[List[str], Dict[str, bool], Optional[Dict[str, Any]]]:
        """
        Resolve a turn.
        Returns: (log, pivot_switches, pivot_switch_needed)
        - pivot_switch_needed: None if no pivot switch needed, or dict with 'uid' and 'remaining_order' if switch needed
        - start_from_index: Start processing moves from this index (for continuing after pivot switch)
        - order_override: Use this order instead of calculating it (for continuing after pivot switch)
        - actions_override: Use these actions instead of c1/c2 (for continuing after pivot switch)
        """
        log: List[str] = []
        log_perf = os.getenv("PVP_LOG", "0").lower() in ("1", "true", "yes")
        t0 = time.perf_counter() if log_perf else 0.0
        def _log_resolve() -> None:
            if log_perf:
                t1 = time.perf_counter()
                print(f"[PvP] resolve: {t1 - t0:.4f}s log_lines={len(log)}")

        if self._pending_weather_messages:
            log.extend(self._pending_weather_messages)
            self._pending_weather_messages.clear()

        self._reconcile_special_weather(immediate_log=log)
        
        # === CUSTAP BERRY: Activate at start of turn before move selection ===
        # "At the very start of a turn, before Pokémon can be recalled"
        from .items import get_item_effect, normalize_item_name
        from .engine import item_is_active
        from .generation import get_generation
        generation = get_generation(field_effects=self.field)
        
        for mon in [self._active(self.p1_id), self._active(self.p2_id)]:
            if mon and mon.hp > 0 and item_is_active(mon) and mon.item:
                item_norm = normalize_item_name(mon.item)
                item_data = get_item_effect(item_norm)
                
                if item_norm == "custap-berry" and generation >= 4:
                    # Check HP threshold: 25% normally, 50% with Gluttony
                    hp_ratio = mon.hp / mon.max_hp if mon.max_hp > 0 else 1.0
                    threshold = 0.25  # Default: 25%
                    
                    # Check for Gluttony ability
                    ability = normalize_ability_name(mon.ability or "")
                    ability_data = get_ability_effect(ability)
                    if ability == "gluttony":
                        threshold = 0.5  # Gluttony: 50% threshold
                    
                    if hp_ratio <= threshold:
                        # Activate Custap Berry - allows moving first in priority bracket
                        mon._custap_active = True
                        mon.item = None  # Consume berry
                        log.append(f"{mon.species}'s Custap Berry activated! It's ready to move first!")
        
        # === CLEAR TURN-BASED FLAGS at START of turn ===
        # Clear flags that track events from the previous turn
        for mon in [self._active(self.p1_id), self._active(self.p2_id)]:
            if mon:
                # Clear damage tracking for moves like Avalanche, Revenge, Assurance
                if hasattr(mon, '_took_damage_this_turn'):
                    mon._took_damage_this_turn = False
                # Clear protection flags
                if hasattr(mon, 'protected_this_turn'):
                    mon.protected_this_turn = False
                if hasattr(mon, 'max_guard_active'):
                    mon.max_guard_active = False
                if hasattr(mon, 'endure_active'):
                    mon.endure_active = False
        
        # === TURN-BASED ABILITIES: Process at START of turn ===
        # Slow Start, Truant, etc. need their counters decremented
        from .engine import apply_special_ability_mechanics
        for mon in [self._active(self.p1_id), self._active(self.p2_id)]:
            if mon and mon.hp > 0:
                ability_msgs = apply_special_ability_mechanics(mon, "turn_start", field_effects=self.field)
                for msg in ability_msgs:
                    if msg:  # Only add non-empty messages
                        log.append(f"  {msg}")
        
        # === FORM CHANGE: Check at turn start (HP-based forms like Zen Mode, Schooling, etc.) ===
        from .engine import check_form_change, check_item_based_forme_change
        for mon in [self._active(self.p1_id), self._active(self.p2_id)]:
            if mon and mon.hp > 0:
                # Check ability-based forme changes
                form_msg = check_form_change(mon, triggered_by="turn_start", field_effects=self.field, battle_state=self)
                if form_msg:
                    log.append(f"  {form_msg}")
                
                # Check item-based forme changes
                item_form_msg = check_item_based_forme_change(mon, triggered_by="turn_start")
                if item_form_msg:
                    log.append(f"  {item_form_msg}")
        
        # immediate forfeits
        if c1.get("kind") == "forfeit":
            self.apply_forfeit(self.p1_id)
            log.append(f"**{self.p1_name}** forfeited!")
            _log_resolve()
            return log, {}, None
        if c2.get("kind") == "forfeit": 
            self.apply_forfeit(self.p2_id)
            log.append(f"**{self.p2_name}** forfeited!")
            _log_resolve()
            return log, {}, None
        # switches before moves textually
        # IMPORTANT: Check both players' choices BEFORE processing switches to handle Shadow Tag correctly
        # If opponent with Shadow Tag is switching, allow this switch (switches happen simultaneously)
        p1_wants_to_switch = c1.get("kind") == "switch"
        p2_wants_to_switch = c2.get("kind") == "switch"
        
        if p1_wants_to_switch:
            self._handle_pursuit_pre_switch(self.p1_id, c1, c2, log, c1, c2)
            if c1.get("kind") == "switch":
                old_mon = self._active(self.p1_id)
                old_mon_name = old_mon.species
                opp_mon = self._opp_active(self.p1_id)
                
                # Check if switch is allowed (trapping abilities, etc.)
                # IMPORTANT: Switches happen BEFORE mega evolution, so check opponent's CURRENT ability
                # If opponent is mega evolving this turn, they don't have Shadow Tag yet, so allow switch
                from .engine import can_switch_out
                opponent_ability = normalize_ability_name(opp_mon.ability or "")
                opponent_has_shadow_tag = opponent_ability == "shadow-tag"
                
                # Check if opponent is mega evolving this turn (they chose a move, not a switch)
                # Switches happen BEFORE mega evolution, so if opponent is mega evolving, check their current ability
                opponent_is_mega_evolving = (c2.get("kind") == "move" and 
                                            not getattr(opp_mon, "mega_evolved", False) and
                                            getattr(opp_mon, "can_mega_evolve", False))
                
                # Check if opponent's mega form would have Shadow Tag
                opponent_mega_will_have_shadow_tag = False
                if opponent_is_mega_evolving and opp_mon.mega_evolutions:
                    # Check all possible mega forms to see if any would have Shadow Tag
                    for mega_form, mega_data in opp_mon.mega_evolutions.items():
                        mega_abilities = mega_data.get("abilities")
                        if mega_abilities:
                            if isinstance(mega_abilities, str):
                                try:
                                    import json
                                    mega_abilities = json.loads(mega_abilities)
                                except:
                                    mega_abilities = [mega_abilities]
                            if isinstance(mega_abilities, list):
                                for ab in mega_abilities:
                                    ab_name = ab.get("name") or ab.get("id") if isinstance(ab, dict) else str(ab)
                                    if normalize_ability_name(ab_name) == "shadow-tag":
                                        opponent_mega_will_have_shadow_tag = True
                                        break
                
                # IMPORTANT: Switches happen BEFORE mega evolution and happen simultaneously
                # If opponent is switching, bypass trapping ABILITIES (they only work when Pokémon is on field)
                # But still check trapping MOVES (Mean Look, Spider Web, Block) - these persist
                # If opponent doesn't currently have Shadow Tag, allow switch (switches happen before mega evolution)
                # This handles the case where opponent is about to mega evolve and gain Shadow Tag
                if p2_wants_to_switch:
                    # Opponent is switching, so bypass trapping abilities (switches happen simultaneously)
                    # But still check trapping moves (Mean Look, Spider Web, Block) - these should still block
                    can_switch, switch_reason = can_switch_out(old_mon, opp_mon, force_switch=False, field_effects=self.field, is_pivot_move=False, bypass_shadow_tag=True)
                elif not opponent_has_shadow_tag:
                    # Opponent doesn't have Shadow Tag (regular Gengar, or about to mega evolve)
                    # Switches happen before mega evolution, so allow switch
                    # Still check for other trapping abilities (Arena Trap, Magnet Pull, etc.) and trapping moves
                    can_switch, switch_reason = can_switch_out(old_mon, opp_mon, force_switch=False, field_effects=self.field, is_pivot_move=False, bypass_shadow_tag=True)
                else:
                    # Opponent has Shadow Tag (already mega evolved), check normally
                    can_switch, switch_reason = can_switch_out(old_mon, opp_mon, force_switch=False, field_effects=self.field, is_pivot_move=False)
                
                if not can_switch:
                    log.append(f"**{self.p1_name}** tried to switch out **{_format_pokemon_name(old_mon)}**!")
                    log.append(f"  {switch_reason}")
                    # If switch is blocked, player can still select a move for that turn (all generations)
                    # Clear the choice so player can choose a move instead
                    c1["kind"] = "move"
                    c1["value"] = None  # Clear value so player must choose a move
                    c1["_switch_blocked"] = True  # Mark that switch was attempted but blocked
                    c1["_cancelled"] = True  # Mark as cancelled so turn loop can re-prompt
                else:
                    # Check if old mon had any stat changes
                    had_stat_changes = any(stage != 0 for stage in old_mon.stages.values())
                    
                    # Cancel mega evolution if player is switching (mega only applies if move is selected)
                    if hasattr(self, '_pending_mega_evolutions') and self.p1_id in self._pending_mega_evolutions:
                        del self._pending_mega_evolutions[self.p1_id]
                
                # Check if value is None (user clicked team button but didn't select)
                if c1.get("value") is None:
                    log.append(f"**{self.p1_name}** tried to switch, but no selection was made!")
                    c1["kind"] = "move"
                    c1["_cancelled"] = True
                    _log_resolve()
                    return log, {}, None
                
                switch_messages = self.apply_switch(self.p1_id, int(c1["value"]))
                new_mon = self._active(self.p1_id)
                
                # Add Leech Seed damage messages (if any)
                for msg in switch_messages:
                    log.append(msg)
                
                # Display message if opponent was freed from partial trap
                opp_mon = self._active(self.p2_id)
                if opp_mon and hasattr(opp_mon, '_thunder_cage_freed'):
                    log.append(f"  {opp_mon.species} was freed from the Thunder Cage!")
                    delattr(opp_mon, '_thunder_cage_freed')
                
                old_mon_display = _format_pokemon_name(old_mon)
                new_mon_display = _format_pokemon_name(new_mon)
                
                # Add switch messages FIRST (before abilities, weather, etc.)
                log.append(f"**{self.p1_name}** switched out **{old_mon_display}**!")
                log.append(f"**{self.p1_name}** sent out **{new_mon_display}**!")
                
                # Apply entry hazards (before abilities trigger)
                from .hazards import apply_entry_hazards
                hazard_msgs = apply_entry_hazards(new_mon, self.p1_side.hazards, is_grounded=True, field_effects=self.field, battle_state=self)
                for msg in hazard_msgs:
                    log.append(f"  {msg}")
                pending_msgs = getattr(new_mon, "_pending_entry_messages", None)
                if pending_msgs:
                    for msg in pending_msgs:
                        log.append(f"  {msg}")
                    delattr(new_mon, "_pending_entry_messages")
                
                # Trigger switch-in abilities (Intimidate, weather, etc.)
                from .engine import on_switch_in, check_item_based_forme_change, check_form_change
                ability_msgs = on_switch_in(new_mon, self._opp_active(self.p1_id), self.field)
                for msg in ability_msgs:
                    log.append(msg)
                
                # Check ability-based forme changes on switch-in (Schooling, etc.)
                form_msg = check_form_change(new_mon, triggered_by="on_switch_in", field_effects=self.field, battle_state=self)
                if form_msg:
                    log.append(f"  {form_msg}")
                
                # Check item-based forme changes on switch-in
                item_form_msg = check_item_based_forme_change(new_mon, triggered_by="switch_in")
                if item_form_msg:
                    log.append(f"  {item_form_msg}")
        
        if p2_wants_to_switch:
            self._handle_pursuit_pre_switch(self.p2_id, c2, c1, log, c1, c2)
            if c2.get("kind") == "switch":
                old_mon = self._active(self.p2_id)
                old_mon_name = old_mon.species
                opp_mon = self._opp_active(self.p2_id)
                
                # Check if switch is allowed (trapping abilities, etc.)
                # IMPORTANT: Switches happen BEFORE mega evolution, so check opponent's CURRENT ability
                # If opponent is mega evolving this turn, they don't have Shadow Tag yet, so allow switch
                from .engine import can_switch_out
                opponent_ability = normalize_ability_name(opp_mon.ability or "")
                opponent_has_shadow_tag = opponent_ability == "shadow-tag"
                
                # Check if opponent is mega evolving this turn (they chose a move, not a switch)
                # Switches happen BEFORE mega evolution, so if opponent is mega evolving, check their current ability
                opponent_is_mega_evolving = (c1.get("kind") == "move" and 
                                            not getattr(opp_mon, "mega_evolved", False) and
                                            getattr(opp_mon, "can_mega_evolve", False))
                
                # Check if opponent's mega form would have Shadow Tag
                opponent_mega_will_have_shadow_tag = False
                if opponent_is_mega_evolving and opp_mon.mega_evolutions:
                    # Check all possible mega forms to see if any would have Shadow Tag
                    for mega_form, mega_data in opp_mon.mega_evolutions.items():
                        mega_abilities = mega_data.get("abilities")
                        if mega_abilities:
                            if isinstance(mega_abilities, str):
                                try:
                                    import json
                                    mega_abilities = json.loads(mega_abilities)
                                except:
                                    mega_abilities = [mega_abilities]
                            if isinstance(mega_abilities, list):
                                for ab in mega_abilities:
                                    ab_name = ab.get("name") or ab.get("id") if isinstance(ab, dict) else str(ab)
                                    if normalize_ability_name(ab_name) == "shadow-tag":
                                        opponent_mega_will_have_shadow_tag = True
                                        break
                
                # IMPORTANT: Switches happen BEFORE mega evolution and happen simultaneously
                # If opponent is switching, bypass trapping ABILITIES (they only work when Pokémon is on field)
                # But still check trapping MOVES (Mean Look, Spider Web, Block) - these persist
                # If opponent doesn't currently have Shadow Tag, allow switch (switches happen before mega evolution)
                # This handles the case where opponent is about to mega evolve and gain Shadow Tag
                if p1_wants_to_switch:
                    # Opponent is switching, so bypass trapping abilities (switches happen simultaneously)
                    # But still check trapping moves (Mean Look, Spider Web, Block) - these should still block
                    can_switch, switch_reason = can_switch_out(old_mon, opp_mon, force_switch=False, field_effects=self.field, is_pivot_move=False, bypass_shadow_tag=True)
                elif not opponent_has_shadow_tag:
                    # Opponent doesn't have Shadow Tag (regular Gengar, or about to mega evolve)
                    # Switches happen before mega evolution, so allow switch
                    # Still check for other trapping abilities (Arena Trap, Magnet Pull, etc.) and trapping moves
                    can_switch, switch_reason = can_switch_out(old_mon, opp_mon, force_switch=False, field_effects=self.field, is_pivot_move=False, bypass_shadow_tag=True)
                else:
                    # Opponent has Shadow Tag (already mega evolved), check normally
                    can_switch, switch_reason = can_switch_out(old_mon, opp_mon, force_switch=False, field_effects=self.field, is_pivot_move=False)
                
                if not can_switch:
                    log.append(f"**{self.p2_name}** tried to switch out **{_format_pokemon_name(old_mon)}**!")
                    log.append(f"  {switch_reason}")
                    # If switch is blocked, player can still select a move for that turn (all generations)
                    # Clear the choice so player can choose a move instead
                    c2["kind"] = "move"
                    c2["value"] = None  # Clear value so player must choose a move
                    c2["_switch_blocked"] = True  # Mark that switch was attempted but blocked
                    c2["_cancelled"] = True  # Mark as cancelled so turn loop can re-prompt
                else:
                    # Check if old mon had any stat changes
                    had_stat_changes = any(stage != 0 for stage in old_mon.stages.values())
                    
                    # Cancel mega evolution if player is switching (mega only applies if move is selected)
                    if hasattr(self, '_pending_mega_evolutions') and self.p2_id in self._pending_mega_evolutions:
                        del self._pending_mega_evolutions[self.p2_id]
                    
                    switch_messages = self.apply_switch(self.p2_id, int(c2["value"]))
                    new_mon = self._active(self.p2_id)
                    
                    # Add Leech Seed damage messages (if any)
                    for msg in switch_messages:
                        log.append(msg)
                    
                    # Display message if opponent was freed from partial trap
                    opp_mon = self._active(self.p1_id)
                    if opp_mon and hasattr(opp_mon, '_thunder_cage_freed'):
                        log.append(f"  {opp_mon.species} was freed from the Thunder Cage!")
                        delattr(opp_mon, '_thunder_cage_freed')
                    
                    old_mon_display = _format_pokemon_name(old_mon)
                    new_mon_display = _format_pokemon_name(new_mon)
                    
                    # Add switch messages FIRST (before abilities, weather, etc.)
                    log.append(f"**{self.p2_name}** switched out **{old_mon_display}**!")
                    log.append(f"**{self.p2_name}** sent out **{new_mon_display}**!")
                    
                    # Apply entry hazards (before abilities trigger)
                    from .hazards import apply_entry_hazards
                    hazard_msgs = apply_entry_hazards(new_mon, self.p2_side.hazards, is_grounded=True, field_effects=self.field, battle_state=self)
                    for msg in hazard_msgs:
                        log.append(f"  {msg}")
                    pending_msgs = getattr(new_mon, "_pending_entry_messages", None)
                    if pending_msgs:
                        for msg in pending_msgs:
                            log.append(f"  {msg}")
                        delattr(new_mon, "_pending_entry_messages")
                    
                    # Trigger switch-in abilities (Intimidate, weather, etc.)
                    from .engine import on_switch_in, check_item_based_forme_change
                    ability_msgs = on_switch_in(new_mon, self._opp_active(self.p2_id), self.field)
                    for msg in ability_msgs:
                        log.append(msg)
                    
                    # Check ability-based forme changes on switch-in (Schooling, etc.)
                    form_msg = check_form_change(new_mon, triggered_by="on_switch_in", field_effects=self.field, battle_state=self)
                    if form_msg:
                        log.append(f"  {form_msg}")
                    
                    # Check item-based forme changes on switch-in
                    item_form_msg = check_item_based_forme_change(new_mon, triggered_by="switch_in")
                    if item_form_msg:
                        log.append(f"  {item_form_msg}")

        # === APPLY MEGA EVOLUTION AFTER SWITCHES ===
        # Mega evolution happens after switches but before moves
        # Only apply if the player chose a move (not a switch)
        if hasattr(self, '_pending_mega_evolutions') and self._pending_mega_evolutions:
            for mega_uid, mega_variant in list(self._pending_mega_evolutions.items()):
                # Only apply mega evolution if player chose a move (not a switch)
                player_choice = c1 if mega_uid == self.p1_id else c2
                if player_choice.get("kind") == "move":
                    mega_mon = self._active(mega_uid)
                    if mega_mon and not getattr(mega_mon, 'mega_evolved', False):
                        # Apply mega evolution
                        mega_msg = apply_mega_evolution(mega_mon, mega_variant, state=self, field_effects=self.field, generation=self.gen)
                        self._mega_used[mega_uid] = True
                        log.append(mega_msg)
                        # Trigger ability entry effects for new form
                        try:
                            from .engine import on_switch_in
                            opponent = self._opp_active(mega_uid)
                            ability_msgs = on_switch_in(mega_mon, opponent, self.field)
                            for msg in ability_msgs:
                                log.append(f"  {msg}")
                        except Exception:
                            pass
                # If player switched, mega evolution is cancelled (already removed above, but clear here too)
            # Clear pending mega evolutions
            self._pending_mega_evolutions.clear()

        order = self._action_order(c1, c2)
        actions = {self.p1_id: c1, self.p2_id: c2}

        # Pre-set protection flags for protection moves BEFORE any moves execute
        # This ensures protection is active from the start of the turn, even if moves execute in priority order
        for uid_prep, act_prep in actions.items():
            if act_prep.get("kind") != "move":
                continue
            mon_prep = self._active(uid_prep)
            if not mon_prep:
                continue
            move_name_prep = act_prep.get("value")
            # Handle case where value might be None, integer, or not a string (e.g., from blocked switch)
            if not move_name_prep or not isinstance(move_name_prep, str):
                move_name_prep = "Struggle"
            move_lower_prep = move_name_prep.lower().replace(" ", "-")
            
            # Pre-set protection for protection moves (Protect, Detect, King's Shield, etc.)
            # This ensures protection is active before other moves execute
            protection_moves = {"protect", "detect", "spiky-shield", "baneful-bunker", "kings-shield", "obstruct", "winters-aegis", "silk-trap", "burning-bulwark"}
            if move_lower_prep in protection_moves:
                # Calculate if this move would succeed (check success chance)
                remaining_move_actions_prep = sum(1 for j, other_uid in enumerate(order) 
                                                   if j > order.index(uid_prep) and actions.get(other_uid, {}).get("kind") == "move")
                is_moving_last_prep = (remaining_move_actions_prep == 0)
                
                # Check success chance (same logic as handle_protect)
                from .generation import get_generation
                generation_prep = get_generation(field_effects=self.field) if self.field else 9
                
                # King's Shield and other protection moves fail if moving last
                if is_moving_last_prep:
                    # Will fail - don't set protection
                    pass
                else:
                    # Calculate success chance based on consecutive protects
                    consecutive_protects = getattr(mon_prep, 'consecutive_protects', 0)
                    if generation_prep == 2:
                        if consecutive_protects >= 8:
                            # Will fail
                            pass
                        else:
                            x = 255 / (2 ** consecutive_protects)
                            success_chance = x / 255.0
                            # Pre-set protection if it would succeed (we'll verify when move executes)
                            # This is optimistic - if it fails, handle_protect will clear it
                            mon_prep.protected_this_turn = True
                            mon_prep._protection_move = move_lower_prep
                    elif generation_prep in [3, 4]:
                        if consecutive_protects == 0:
                            mon_prep.protected_this_turn = True
                            mon_prep._protection_move = move_lower_prep
                        else:
                            success_chance = (1.0 / 2.0) ** consecutive_protects
                            success_chance = max(success_chance, 1.0 / 8.0)
                            # Optimistically set - will be cleared if it fails
                            mon_prep.protected_this_turn = True
                            mon_prep._protection_move = move_lower_prep
                    elif generation_prep == 5:
                        success_chance = (1.0 / 2.0) ** consecutive_protects if consecutive_protects > 0 else 1.0
                        # Optimistically set - will be cleared if it fails
                        mon_prep.protected_this_turn = True
                        mon_prep._protection_move = move_lower_prep
                    else:  # Gen VI+
                        success_chance = (1.0 / 3.0) ** consecutive_protects if consecutive_protects > 0 else 1.0
                        # Optimistically set - will be cleared if it fails
                        mon_prep.protected_this_turn = True
                        mon_prep._protection_move = move_lower_prep

        # Pre-set charge states for moves like Shell Trap and Beak Blast
        for uid_prep, act_prep in actions.items():
            if act_prep.get("kind") != "move":
                continue
            mon_prep = self._active(uid_prep)
            if not mon_prep:
                continue
            move_name_prep = act_prep.get("value")
            # Handle case where value might be None, integer, or not a string (e.g., from blocked switch)
            if not move_name_prep or not isinstance(move_name_prep, str):
                move_name_prep = "Struggle"
            move_lower_prep = move_name_prep.lower().replace(" ", "-")

            if move_lower_prep == "shell-trap":
                mon_prep._shell_trap_set = True
                if not hasattr(mon_prep, '_shell_trap_activated'):
                    mon_prep._shell_trap_activated = False
            else:
                if hasattr(mon_prep, '_shell_trap_set'):
                    mon_prep._shell_trap_set = False
                if hasattr(mon_prep, '_shell_trap_activated'):
                    mon_prep._shell_trap_activated = False

            if move_lower_prep == "beak-blast":
                mon_prep._beak_blast_charging = True
            else:
                if hasattr(mon_prep, '_beak_blast_charging'):
                    mon_prep._beak_blast_charging = False

        # Handle pivot switch BEFORE processing remaining moves (if continuing after pivot switch)
        if pivot_switch_choice and start_from_index > 0:
            # We're continuing after a pivot switch - apply the switch now before processing remaining moves
            for pivot_uid, switch_to_index in pivot_switch_choice.items():
                pivot_mon = self._active(pivot_uid)
                if pivot_mon:
                    old_mon = pivot_mon
                    old_mon_display = _format_pokemon_name(old_mon)
                    # Pivot moves bypass trapping (Baton Pass, U-turn, Volt Switch, Flip Turn, Parting Shot)
                    # So we always allow the switch
                    switch_messages = self.apply_switch(pivot_uid, switch_to_index)
                    new_mon = self._active(pivot_uid)
                    new_mon_display = _format_pokemon_name(new_mon)
                    
                    # Add Leech Seed damage messages (if any)
                    for msg in switch_messages:
                        log.append(msg)
                    
                    # Apply entry hazards FIRST (before abilities trigger)
                    from .hazards import apply_entry_hazards
                    side = self.p1_side if pivot_uid == self.p1_id else self.p2_side
                    hazard_msgs = apply_entry_hazards(new_mon, side.hazards, is_grounded=True, field_effects=self.field, battle_state=self)
                    for msg in hazard_msgs:
                        log.append(f"  {msg}")
                    pending_msgs = getattr(new_mon, "_pending_entry_messages", None)
                    if pending_msgs:
                        for msg in pending_msgs:
                            log.append(f"  {msg}")
                        delattr(new_mon, "_pending_entry_messages")
                    
                    # Trigger switch-in abilities (Intimidate, weather, etc.)
                    from pvp.engine import on_switch_in, check_item_based_forme_change
                    opp_mon = self._opp_active(pivot_uid)
                    ability_msgs = on_switch_in(new_mon, opp_mon, self.field)
                    for msg in ability_msgs:
                        log.append(msg)
                    
                    # Check item-based forme changes on switch-in
                    item_form_msg = check_item_based_forme_change(new_mon, triggered_by="switch_in")
                    if item_form_msg:
                        log.append(f"  {item_form_msg}")
                    
                    log.append(f"**{self.p1_name if pivot_uid == self.p1_id else self.p2_name}** switched out **{old_mon_display}**!")
                    log.append(f"**{self.p1_name if pivot_uid == self.p1_id else self.p2_name}** sent out **{new_mon_display}**!")
        
        # Start from the specified index (for continuing after pivot switch)
        for i in range(start_from_index, len(order)):
            if self.winner: break
            uid = order[i]
            act = actions.get(uid, {})
            if act.get("kind") != "move":
                # Handle heal/throw actions (consume turn)
                if act.get("kind") == "heal":
                    mon = self._active(uid)
                    healed = act.get("value", {}).get("healed", 0)
                    item_used = act.get("value", {}).get("item", "item")
                    if mon:
                        mon_name = _format_pokemon_name(mon)
                        log.append(f"**{mon_name}** recovered HP using {item_used.title()} (+{healed} HP).")
                        # Full Restore: clear status and restore all move PP to max
                        if "full restore" in item_used:
                            mon.status = None
                            self._ensure_pp_loaded(uid, mon)
                            key = self._get_mon_key(uid, mon)
                            if key not in self._pp:
                                self._pp[key] = {}
                            store = self._pp[key]
                            for mv in (mon.moves or [])[:4]:
                                if (mv or "").strip().lower() != "struggle":
                                    canonical = _canonical_move_name(mv)
                                    cap = _pp_global_max_for_move(mv, generation=self.gen)
                                    store[canonical] = cap
                            log.append(f"**{mon_name}**'s moves had their PP fully restored!")
                    continue
                if act.get("kind") == "throw":
                    # Only P1 throws at Wild opponent
                    if uid != self.p1_id or not self.p2_name.lower().startswith("wild "):
                        continue
                    mon_target = self._active(self.p2_id)
                    if not mon_target:
                        continue
                    ball_name = act.get("value", {}).get("ball", "poké ball")
                    ball_label = _normalize_ball_name(str(ball_name)).title()
                    try:
                        caught, shakes = _attempt_capture(mon_target, ball_name, self)
                        target_display = _format_pokemon_name(mon_target)
                        if caught:
                            log.append(f"**{self.p1_name}** threw a {ball_label}! It shook {shakes} time(s) and **caught {target_display}!**")
                            self.winner = self.p1_id
                            self._caught_wild_mon = mon_target  # so pokebot can add to team
                            self._caught_ball_name = str(ball_name or "")
                            self._caught_ball_normalized = str(_normalize_ball_name(str(ball_name or "")) or "")
                            try:
                                setattr(mon_target, "_caught_ball_name", str(ball_name or ""))
                            except Exception:
                                pass
                            self._throw_shakes = shakes  # for shake-by-shake embeds
                            # Capture ends the battle; no further actions
                            return log, {}, None
                        else:
                            # Different messages by shake count (battle continues)
                            if shakes == 0:
                                msg = f"**{self.p1_name}** threw a {ball_label}! Oh no! The Pokémon broke free!"
                            elif shakes == 1:
                                msg = f"**{self.p1_name}** threw a {ball_label}! Aww! It appeared to be caught!"
                            elif shakes == 2:
                                msg = f"**{self.p1_name}** threw a {ball_label}! Aargh! Almost had it!"
                            else:  # 3 shakes
                                msg = f"**{self.p1_name}** threw a {ball_label}! Shoot! It was so close, too!"
                            log.append(msg)
                            self._throw_shakes = shakes  # for shake-by-shake embeds
                    except Exception as capture_err:
                        # Do not abort the whole battle when a throw-specific error occurs.
                        print(f"[PvP] Capture resolution error: {capture_err}")
                        self._throw_shakes = 0
                        log.append(f"**{self.p1_name}** threw a {ball_label}! Oh no! The Pokémon broke free!")
                    continue
                continue
            if act.get("_processed"):
                continue
            # Skip move if Emergency Exit is pending (moves shouldn't be shown after Emergency Exit)
            atk_mon = self._active(uid)
            if atk_mon and hasattr(atk_mon, '_emergency_exit_pending') and atk_mon._emergency_exit_pending:
                continue  # Skip this move - Emergency Exit will force a switch
            remaining_move_actions = sum(1 for j in range(i + 1, len(order))
                                         if actions.get(order[j], {}).get("kind") == "move")
            atk_choice = c1 if uid == self.p1_id else c2
            dfn_choice = c2 if uid == self.p1_id else c1
            self._execute_move_action(
                uid,
                act,
                atk_choice,
                dfn_choice,
                log,
                order=order,
                actions=actions,
                index=i,
                remaining_move_actions=remaining_move_actions
            )
            if self.winner:
                break
            
            # === HANDLE PIVOT SWITCHES IMMEDIATELY ===
            # If a pivot move was used and there are more moves to execute, we need to switch
            # If pivot_switch_choice is provided, use it; otherwise, return early to get choice
            if atk_mon and hasattr(atk_mon, '_pivot_switch_pending') and atk_mon._pivot_switch_pending and remaining_move_actions > 0:
                atk_mon._pivot_switch_pending = False  # Clear flag
                
                # Check if we have a switch choice (from previous async handling)
                if pivot_switch_choice and uid in pivot_switch_choice:
                    # We have the choice, apply the switch
                    switch_to_index = pivot_switch_choice[uid]
                    old_mon = atk_mon
                    old_mon_display = _format_pokemon_name(old_mon)
                    
                    # Pivot moves bypass trapping (Baton Pass, U-turn, Volt Switch, Flip Turn, Parting Shot)
                    # So we always allow the switch, but check for logging purposes
                    from .engine import can_switch_out
                    opp_mon = self._opp_active(uid)
                    can_switch, switch_reason = can_switch_out(old_mon, opp_mon, force_switch=False, field_effects=self.field, is_pivot_move=True)
                    # Pivot moves always succeed (they bypass trapping), so apply the switch
                    switch_messages = self.apply_switch(uid, switch_to_index)
                    new_mon = self._active(uid)
                    new_mon_display = _format_pokemon_name(new_mon)
                    
                    # Add Leech Seed damage messages (if any)
                    for msg in switch_messages:
                        log.append(msg)
                    
                    # Add switch messages FIRST (before abilities, weather, etc.)
                    log.append(f"**{self.p1_name if uid == self.p1_id else self.p2_name}** switched out **{old_mon_display}**!")
                    log.append(f"**{self.p1_name if uid == self.p1_id else self.p2_name}** sent out **{new_mon_display}**!")
                    
                    # Apply entry hazards (before abilities trigger)
                    from .hazards import apply_entry_hazards
                    side = self.p1_side if uid == self.p1_id else self.p2_side
                    hazard_msgs = apply_entry_hazards(new_mon, side.hazards, is_grounded=True, field_effects=self.field, battle_state=self)
                    for msg in hazard_msgs:
                        log.append(f"  {msg}")
                    pending_msgs = getattr(new_mon, "_pending_entry_messages", None)
                    if pending_msgs:
                        for msg in pending_msgs:
                            log.append(f"  {msg}")
                        delattr(new_mon, "_pending_entry_messages")
                    
                    # Trigger switch-in abilities (Intimidate, weather, etc.)
                    from pvp.engine import on_switch_in, check_item_based_forme_change
                    opp_mon = self._opp_active(uid)
                    ability_msgs = on_switch_in(new_mon, opp_mon, self.field)
                    for msg in ability_msgs:
                        log.append(msg)
                    
                    # Check item-based forme changes on switch-in
                    item_form_msg = check_item_based_forme_change(new_mon, triggered_by="switch_in")
                    if item_form_msg:
                        log.append(f"  {item_form_msg}")
                    
                    # Update atk_mon reference for next iteration
                    atk_mon = new_mon
                else:
                    # No choice provided - need to pause and get choice from UI
                    # Return early with information about what's needed
                    remaining_order = order[i+1:]  # Remaining moves to execute
                    _log_resolve()
                    return log, {}, {"uid": uid, "remaining_order": remaining_order, "actions": actions, "c1": c1, "c2": c2}
            
            continue
            if act.get("kind") != "move":
                continue
            atk = self._active(uid)
            dfn = self._opp_active(uid)
            setattr(atk, '_player_id', uid)
            
            # Don't attack if attacker is dead or defender is dead
            if atk.hp <= 0:
                continue
            if dfn.hp <= 0:
                continue

            # Get side effects for attacker and defender
            atk_side = self.p1_side if uid == self.p1_id else self.p2_side
            dfn_side = self.p2_side if uid == self.p1_id else self.p1_side
            
            # Get the move name early to check if it's Sleep Talk or Snore
            chosen_move = act.get("value") or "Tackle"
            
            # === ADVANCED MECHANICS: Check if Pokémon can move ===
            can_move_result, move_reason = can_pokemon_move(atk, self.field, move_name=chosen_move)
            pending_block_reason: Optional[str] = None
            if not can_move_result:
                reason_lower = (move_reason or "").lower()
                if "frozen" in reason_lower:
                    pending_block_reason = move_reason
                else:
                    atk_name = _format_pokemon_name(atk)
                    log.append(f"**{atk_name}:** {move_reason}")
                    reset_rollout(atk)
                    continue
            elif move_reason:  # Wake up or thaw message
                atk_name = _format_pokemon_name(atk)
                log.append(f"**{atk_name}:** {move_reason}")
            
            # === ADVANCED MECHANICS: Check if finishing a charging move ===
            is_attack_turn, charged_move = execute_attack_turn(atk)
            if is_attack_turn and charged_move:
                chosen = str(charged_move) if charged_move else "Tackle"
                atk_name = _format_pokemon_name(atk)
                move_name = _format_move_name(chosen)
                log.append(f"**{atk_name} unleashes {move_name}!**")
            else:
                # Check if starting a new charging move
                # Ensure chosen is always a string (handle case where value might be a dict)
                move_value = act.get("value")
                if isinstance(move_value, dict):
                    # If it's a dict, extract the name
                    chosen = str(move_value.get("name", move_value.get("value", "Tackle")))
                elif move_value:
                    chosen = str(move_value)
                else:
                    chosen = "Tackle"
                
            rollout_locked_move = getattr(atk, 'rollout_move', None)
            if rollout_locked_move and getattr(atk, 'rollout_turns_remaining', 0) > 0:
                forced_move_name = rollout_locked_move.replace("-", " ").title()
                if self._pp_left(uid, forced_move_name) > 0:
                    chosen = forced_move_name
                else:
                    chosen = "Struggle"
                    reset_rollout(atk)

            # Enforce rampage lock at resolution time (Outrage, Thrash, Petal Dance)
            if hasattr(atk, 'rampage_move') and atk.rampage_move and hasattr(atk, 'rampage_turns_remaining') and atk.rampage_turns_remaining > 0:
                rampage_move_name = atk.rampage_move.replace("-", " ").title()
                if self._pp_left(uid, rampage_move_name) > 0:
                    chosen = rampage_move_name
                else:
                    chosen = "Struggle"
            
            # Enforce Choice lock at resolution time (safety)
            elif locked := self._choice_move(uid):
                if self._pp_left(uid, locked) > 0:
                    chosen = locked
                else:
                    chosen = "Struggle"

            # If not locked and chosen is out of PP, fallback to Struggle
            if chosen.lower() != "struggle" and self._pp_left(uid, chosen) <= 0:
                chosen = "Struggle"
                reset_rollout(atk)
                
                # === CHARGING MOVES: Handled in engine.py now ===
                # Two-turn moves (Phantom Force, Fly, etc.) are now handled
                # in the apply_move() function in engine.py
                # Old charging system disabled to prevent conflicts

            if pending_block_reason and not can_move_result:
                effect_data = get_move_secondary_effect(chosen)
                if effect_data.get("thaws_user") and getattr(atk, 'status', None) == "frz":
                    atk.status = None
                    log.append(f"**{atk.species}:** thawed out!")
                    can_move_result = True
                    pending_block_reason = None
                else:
                    log.append(f"**{atk.species}:** {pending_block_reason}")
                    reset_rollout(atk)
                    continue

            # Spend PP (no PP for Struggle)
            # Get move data and target for Pressure check (using battle cache)
            move_data = _get_move_with_cache(chosen, battle_state=self, generation=self.gen)
            target = dfn if dfn else (self._active(self.p2_id) if uid == self.p1_id else self._active(self.p1_id))
            self._spend_pp(uid, chosen, target=target, move_data=move_data)

            # Apply Choice lock if needed
            if chosen.lower() != "struggle":
                self._set_choice_lock_if_needed(uid, chosen)

            # === ADVANCED MECHANICS: Check for Protect ===
            move_lower = chosen.lower().replace(" ", "-")
            remaining_move_actions = sum(1 for j in range(i + 1, len(order))
                                        if actions.get(order[j], {}).get("kind") == "move")
            is_moving_last = (remaining_move_actions == 0)
            if move_lower in {"protect", "detect", "spiky-shield", "baneful-bunker", "kings-shield", "obstruct", "winters-aegis", "silk-trap", "burning-bulwark"}:
                protected, protect_msg = handle_protect(atk, chosen, self.field, is_moving_last)
                atk_name = _format_pokemon_name(atk)
                move_name = _format_move_name(chosen)
                log.append(f"**{atk_name}** used **{move_name}**!")
                log.append(protect_msg)
                if protected:
                    # Z-Protect: Reset all lowered stats
                    if move_lower == "protect":
                        is_z_move = atk_choice.get("z_move", False) or getattr(atk, '_is_z_move', False)
                        if is_z_move:
                            from .engine import modify_stages
                            stat_resets = {}
                            for stat in ["atk", "defn", "spa", "spd", "spe", "accuracy", "evasion"]:
                                if atk.stages.get(stat, 0) < 0:
                                    stat_resets[stat] = -atk.stages.get(stat, 0)
                            if stat_resets:
                                z_msgs = modify_stages(atk, stat_resets, caused_by_opponent=False, field_effects=self.field)
                                for z_msg in z_msgs:
                                    log.append(f"  {z_msg}")
                    # Z-Detect: +1 Evasion
                    elif move_lower == "detect":
                        is_z_move = atk_choice.get("z_move", False) or getattr(atk, '_is_z_move', False)
                        if is_z_move:
                            from .engine import modify_stages
                            z_msgs_detect = modify_stages(atk, {"evasion": 1}, caused_by_opponent=False, field_effects=self.field)
                            for z_msg in z_msgs_detect:
                                log.append(f"  {z_msg}")
                    # Update last move used
                    _record_last_move(atk, chosen, battle_state=self)
                    reset_rollout(atk)
                    continue
                else:
                    # Failed protect, reset consecutive counter
                    atk.consecutive_protects = 0
            elif move_lower == "endure":
                from .battle_flow import handle_endure
                success, endure_msg = handle_endure(atk, self.field, is_moving_last)
                atk_name = _format_pokemon_name(atk)
                move_name = _format_move_name(chosen)
                log.append(f"**{atk_name}** used **{move_name}**!")
                log.append(f"  {endure_msg}")
                _record_last_move(atk, chosen, battle_state=self)
                if not success:
                    continue
                else:
                    continue
            else:
                # Reset protect counter if not using protect
                if move_lower not in {"protect", "detect"}:
                    atk.consecutive_protects = 0
            
            # === ADVANCED MECHANICS: Check for Mat Block (protects entire side from damaging moves) ===
            from .advanced_moves import check_mat_block
            move_data_mat = _get_move_with_cache(chosen, battle_state=self, generation=self.gen) or {}
            move_category_mat = (move_data_mat.get("damage_class") or move_data_mat.get("category") or "").lower()
            mat_blocked, mat_msg = check_mat_block(atk, dfn, move_category_mat, dfn_side)
            if mat_blocked:
                atk_name = _format_pokemon_name(atk)
                move_name = _format_move_name(chosen)
                log.append(f"**{atk_name}** used **{move_name}**!")
                log.append(mat_msg)
                atk._last_move_failed = True
                if getattr(atk, 'rampage_move', None):
                    generation = getattr(self.field, 'generation', 9)
                    if generation >= 5:
                        from .engine import disrupt_rampage
                        disrupt_rampage(atk, self.field, reason="protect")
                _record_last_move(atk, chosen, battle_state=self)
                reset_rollout(atk)
                continue
            
            # === ADVANCED MECHANICS: Check if defender is protected ===
            if dfn.protected_this_turn:
                # Check if move bypasses protection (Phantom Force, Shadow Force, Feint)
                move_effect = get_move_secondary_effect(chosen) or {}
                move_data = _get_move_with_cache(chosen, battle_state=self, generation=self.gen)
                makes_contact = False
                if move_data:
                    makes_contact = bool(move_data.get("makes_contact") or move_data.get("contact"))
                attacker_ability_norm = normalize_ability_name(atk.ability or "")
                attacker_ability_data = get_ability_effect(attacker_ability_norm)
                ability_bypass = (
                    not getattr(atk, '_ability_suppressed', False) and
                    attacker_ability_data.get("contact_ignores_protect") and
                    makes_contact
                )
                bypasses_protect = move_effect.get("ignores_protect", False) or ability_bypass
                if not bypasses_protect and move_effect.get("bypasses_standard_protect"):
                    crafty_active = getattr(dfn_side, '_crafty_shield_active', False)
                    if crafty_active and move_effect.get("blocked_by_crafty_shield", False):
                        bypasses_protect = False
                    else:
                        bypasses_protect = True
                
                # Max Guard protects against additional moves that regular Protect doesn't
                max_guard_protected_moves = {
                    "block", "flower-shield", "gear-up", "magnetic-flux",
                    "phantom-force", "psych-up", "shadow-force", "teatime", "transform"
                }
                is_max_guard = getattr(dfn, 'max_guard_active', False)
                is_max_guard_protected_move = move_lower in max_guard_protected_moves
                
                # Determine if protection blocks the move:
                # 1. Max Guard blocks max_guard_protected_moves even if they have ignores_protect=True
                # 2. Regular Protect doesn't block max_guard_protected_moves
                # 3. Moves with ignores_protect=True bypass regular Protect (unless blocked by Max Guard rule #1)
                if is_max_guard and is_max_guard_protected_move:
                    # Max Guard blocks these specific moves even if they normally ignore protect
                    atk_name = _format_pokemon_name(atk)
                    move_name = _format_move_name(chosen)
                    log.append(f"**{atk_name}** used **{move_name}**!")
                    dfn_name = _format_pokemon_name(dfn)
                    log.append(f"But {dfn_name} protected itself!")
                    atk._last_move_failed = True
                    # Apply protection counter effects (King's Shield, Spiky Shield, Winter's Aegis, etc.)
                    self._apply_protection_counter_effect(dfn, atk, uid, chosen, log)
                    if getattr(atk, 'rampage_move', None):
                        generation = getattr(self.field, 'generation', 9)
                        if generation >= 5:
                            from .engine import disrupt_rampage
                            disrupt_rampage(atk, self.field, reason="protect")
                    _record_last_move(atk, chosen, battle_state=self)
                    reset_rollout(atk)
                    continue
                elif ability_bypass and is_max_guard:
                    atk_name = _format_pokemon_name(atk)
                    move_name = _format_move_name(chosen)
                    log.append(f"**{atk_name}** used **{move_name}**!")
                    dfn_name = _format_pokemon_name(dfn)
                    log.append(f"But {dfn_name} protected itself!")
                    atk._last_move_failed = True
                    self._apply_protection_counter_effect(dfn, atk, uid, chosen, log)
                    if getattr(atk, 'rampage_move', None):
                        generation = getattr(self.field, 'generation', 9)
                        if generation >= 5:
                            from .engine import disrupt_rampage
                            disrupt_rampage(atk, self.field, reason="protect")
                    _record_last_move(atk, chosen, battle_state=self)
                    reset_rollout(atk)
                    continue
                elif bypasses_protect:
                    # Move with ignores_protect bypasses regular Protect
                    atk_name = _format_pokemon_name(atk)
                    move_name = _format_move_name(chosen)
                    log.append(f"**{atk_name}** used **{move_name}**!")
                    atk_name = _format_pokemon_name(atk)
                    log.append(f"{atk_name} broke through the protection!")
                elif is_max_guard_protected_move and not is_max_guard:
                    # Max Guard protected move vs regular Protect: bypasses
                    atk_name = _format_pokemon_name(atk)
                    move_name = _format_move_name(chosen)
                    log.append(f"**{atk_name}** used **{move_name}**!")
                    atk_name = _format_pokemon_name(atk)
                    log.append(f"{atk_name} broke through the protection!")
                else:
                    # Protection blocks the move
                    atk_name = _format_pokemon_name(atk)
                    move_name = _format_move_name(chosen)
                    log.append(f"**{atk_name}** used **{move_name}**!")
                    dfn_name = _format_pokemon_name(dfn)
                    log.append(f"But {dfn_name} protected itself!")
                    atk._last_move_failed = True
                    self._apply_protection_counter_effect(dfn, atk, uid, chosen, log)
                    if getattr(atk, 'rampage_move', None):
                        generation = getattr(self.field, 'generation', 9)
                        if generation >= 5:
                            from .engine import disrupt_rampage
                            disrupt_rampage(atk, self.field, reason="protect")
                    _record_last_move(atk, chosen, battle_state=self)
                    reset_rollout(atk)
                    continue
            
            # === ADVANCED MECHANICS: Check for Substitute move ===
            if move_lower == "substitute":
                success, sub_msg = apply_substitute(atk)
                log.append(f"{sub_msg}")
                _record_last_move(atk, chosen, battle_state=self)
                continue
            
            # === HAZARD MOVES ===
            hazard_moves = {"stealth-rock": "stealth-rock", "spikes": "spikes", 
                           "toxic-spikes": "toxic-spikes", "sticky-web": "sticky-web"}
            if move_lower in hazard_moves:
                from .hazards import set_hazard
                # Set hazard on OPPONENT's side
                opponent_side = dfn_side
                success, hazard_msg = set_hazard(opponent_side.hazards, hazard_moves[move_lower], self.gen)
                atk_name = _format_pokemon_name(atk)
                move_name = _format_move_name(chosen)
                log.append(f"**{atk_name}** used **{move_name}**!")
                log.append(f"  {hazard_msg}")
                _record_last_move(atk, chosen, battle_state=self)
                continue
            
            # === WEATHER MOVES ===
            weather_moves = {"rain-dance": "rain", "sunny-day": "sun", "sandstorm": "sandstorm",
                            "hail": "hail", "snowscape": "snow"}
            if move_lower in weather_moves:
                generation = getattr(self, 'gen', 9)
                special_weather = getattr(self.field, 'special_weather', None)
                # Desolate Land (harsh-sunlight) and Primordial Sea (heavy-rain) prevent weather moves from working
                # Only Primordial Sea can override Desolate Land, and only Desolate Land can override Primordial Sea
                if special_weather in {"heavy-rain", "harsh-sunlight", "strong-winds"}:
                    atk_name = _format_pokemon_name(atk)
                    move_name = _format_move_name(chosen)
                    log.append(f"**{atk_name}** used **{move_name}**!")
                    if special_weather == "heavy-rain":
                        fail_text = "  But the heavy rain made the move fail!"
                    elif special_weather == "harsh-sunlight":
                        fail_text = "  But the extremely harsh sunlight made the move fail!"
                    else:  # strong-winds
                        fail_text = "  But the mysterious air current made the move fail!"
                    log.append(fail_text)
                    atk._last_move_failed = True
                    _record_last_move(atk, chosen, battle_state=self)
                    continue

                target_weather = weather_moves[move_lower]
                if target_weather == "sandstorm" and generation == 2 and self.field.weather == "sandstorm":
                    atk_name = _format_pokemon_name(atk)
                    move_name = _format_move_name(chosen)
                    log.append(f"**{atk_name}** used **{move_name}**!")
                    log.append("  But there was no change to the weather!")
                    atk._last_move_failed = True
                    _record_last_move(atk, chosen, battle_state=self)
                    continue

                # Clear special weather BEFORE setting regular weather to prevent Desolate Land from activating
                # Special weather abilities (Desolate Land, Primordial Sea) should NOT activate from weather moves
                self.field.special_weather = None
                self.field.heavy_rain = False
                self.field.harsh_sunlight = False
                self.field.weather_lock = None
                self.field.weather_lock_owner = None
                self.field.weather = target_weather

                # === WEATHER ROCKS: Extend weather from 5 to 8 turns ===
                from .items import get_item_effect, normalize_item_name
                weather_duration = 5  # Default duration for move-induced weather
                if generation >= 4 and atk.item:
                    item_data = get_item_effect(normalize_item_name(atk.item))
                    if item_data.get("extends_weather") == target_weather:
                        weather_duration = 8

                self.field.weather_turns = weather_duration
                if target_weather == "sandstorm" and generation == 2:
                    self.field.sandstorm_damage_turns = 4
                else:
                    self.field.sandstorm_damage_turns = 0
                weather_names = {"rain": "Rain", "sun": "Harsh sunlight", "sandstorm": "Sandstorm",
                                "hail": "Hail", "snow": "Snow"}
                atk_name = _format_pokemon_name(atk)
                move_name = _format_move_name(chosen)
                log.append(f"**{atk_name}** used **{move_name}**!")
                log.append(f"  {weather_names[target_weather]} started!")
                _record_last_move(atk, chosen, battle_state=self)
                continue
            
            # === TERRAIN MOVES ===
            terrain_moves = {"electric-terrain": "electric", "grassy-terrain": "grassy",
                            "misty-terrain": "misty", "psychic-terrain": "psychic"}
            if move_lower in terrain_moves:
                self.field.terrain = terrain_moves[move_lower]
                
                # === TERRAIN EXTENDER: Extends terrain from 5 to 8 turns ===
                from .items import get_item_effect, normalize_item_name
                terrain_duration = 5
                if atk.item:
                    item_data = get_item_effect(normalize_item_name(atk.item))
                    if item_data.get("extends_terrain"):
                        terrain_duration = 8
                
                self.field.terrain_turns = terrain_duration
                terrain_names = {"electric": "Electric Terrain", "grassy": "Grassy Terrain",
                                "misty": "Misty Terrain", "psychic": "Psychic Terrain"}
                atk_name = _format_pokemon_name(atk)
                move_name = _format_move_name(chosen)
                log.append(f"**{atk_name}** used **{move_name}**!")
                log.append(f"  {terrain_names[terrain_moves[move_lower]]} activated!")
                _record_last_move(atk, chosen, battle_state=self)
                continue
            
            # === ADVANCED MECHANICS: Check for field effect moves ===
            field_effect_moves = {
                "reflect", "light-screen", "aurora-veil", "tailwind", "trick-room",
                "magic-room", "wonder-room", "gravity"
            }
            if move_lower in field_effect_moves:
                field_msgs = apply_field_effect_move(chosen, self.field, atk_side, uid == self.p1_id, atk, self)
                atk_name = _format_pokemon_name(atk)
                move_name = _format_move_name(chosen)
                log.append(f"**{atk_name}** used **{move_name}**!")
                for msg in field_msgs:
                    log.append(f"  {msg}")
                _record_last_move(atk, chosen, battle_state=self)
                continue
            
            # === FORM CHANGE: Before move (Aegislash Stance Change) ===
            from .engine import check_form_change
            form_msg = check_form_change(atk, triggered_by="before_move", move_used=chosen, field_effects=self.field, battle_state=self)
            if form_msg:
                log.append(f"  {form_msg}")
            
            # === PRIORITY BLOCKING: Check if priority move is blocked by defender's ability ===
            from .engine import action_priority, is_priority_blocked
            from .advanced_moves import get_metronome_move
            
            # For Metronome, determine the called move's priority before checking priority blocking
            if move_lower == "metronome":
                selected_move, _ = get_metronome_move(field_effects=self.field, battle_state=self)
                if selected_move:
                    # Store the called move for later use in apply_move
                    atk._metronome_called_move = selected_move
                    # Use the called move's priority for priority checks
                    move_priority = action_priority(selected_move, atk, self.field, self)
                else:
                    move_priority = action_priority(chosen, atk, self.field, self)
            else:
                move_priority = action_priority(chosen, atk, self.field, self)
            
            # Check if attacker has Mold Breaker/Turboblaze/Teravolt (ignores blocking abilities)
            attacker_ability = normalize_ability_name(atk.ability or "")
            from .abilities import get_ability_effect as get_atk_ability
            attacker_ability_data = get_atk_ability(attacker_ability)
            ignores_abilities = attacker_ability_data.get("ignores_opponent_abilities", False)
            
            is_blocked, block_msg = False, None
            if not ignores_abilities:
                is_blocked, block_msg = is_priority_blocked(
                    atk,
                    dfn,
                    chosen,
                    move_priority,
                    defender_side=dfn_side,
                    field_effects=self.field
                )
            
            move_result = None  # Initialize move_result
            if is_blocked and block_msg:
                atk_name = _format_pokemon_name(atk)
                move_name = _format_move_name(chosen)
                log.append(f"**{atk_name}** used **{move_name}**!")
                log.append(block_msg)
                # Move fails but PP is still spent (already spent above)
                move_result = f"**{atk_name}** used **{move_name}**!\n{block_msg}"
            else:
                # Execute the move normally
                # Pass choices and battle state for special move handling
                # Map attacker to choice (uid is attacker_id)
                atk_choice = c1 if uid == self.p1_id else c2
                dfn_choice = c2 if uid == self.p1_id else c1
                
                analytic_bonus = is_moving_last
                if normalize_ability_name(getattr(atk, 'ability', '') or "") == "analytic":
                    if dfn_choice and dfn_choice.get("kind") == "switch":
                        analytic_bonus = True
                move_result = apply_move(atk, dfn, chosen, self.field, dfn_side, atk_choice, dfn_choice, self, analytic_bonus)
                if move_lower != "laser-focus" and getattr(atk, '_laser_focus_pending', False):
                    atk._laser_focus_pending = False
                    atk.laser_focus_turns = 0
                log.append(move_result)
                
                # Check if attacker fainted (e.g., from Self-Destruct/Explosion)
                # Only check if not already logged in move_result
                if atk.hp <= 0 and "fainted" not in move_result.lower():
                    log.append(f"**{atk.species}** fainted!")
                
                if atk.hp <= 0:
                    self._reconcile_special_weather(immediate_log=log)
                    
                    # Check if the entire attacking team is defeated
                    attacking_team = self.team_for(uid)
                    alive_count = sum(1 for mon in attacking_team if mon and mon.hp > 0)
                    
                    if alive_count == 0:
                        # Entire team fainted - battle over
                        attacking_player = self.player_name(uid)
                        if uid == self.p2_id and (self.p2_name or "").lower().startswith("wild "):
                            species = (self.p2_name or "").replace("Wild ", "").replace("wild ", "").replace("⭐", "").strip()
                            log.append(f"\nThe wild {species.title() if species else 'Pokémon'} was defeated.")
                        else:
                            log.append(f"\n**{attacking_player}** has no more Pokémon left!")
                        self.winner = self.p2_id if uid == self.p1_id else self.p1_id
            
            # Note: Damage tracking for Counter/Mirror Coat/Metal Burst is now done in engine.py
            
            # === ILLUSION: Break when taking direct damage ===
            # Only break illusion if the move dealt damage
            if "lost" in move_result.lower() and "health" in move_result.lower():
                illusion_msg = self._break_illusion(dfn)
                if illusion_msg:
                    log.append(f"**{illusion_msg}**")
            
            # === FORM CHANGE: After damage (HP-based forms) ===
            form_msg = check_form_change(dfn, triggered_by="after_damage", field_effects=self.field, battle_state=self)
            if form_msg:
                log.append(f"  {form_msg}")
            form_msg = check_form_change(atk, triggered_by="after_damage", field_effects=self.field, battle_state=self)
            if form_msg:
                log.append(f"  {form_msg}")
            
            # === ADVANCED MECHANICS: Apply move restrictions ===
            # Determine if the move connected (hit and had effect)
            move_connected_2 = True
            if move_result:
                result_lower = move_result.lower()
                # Check for failure indicators
                if any(phrase in result_lower for phrase in ["but it failed", "missed", "doesn't affect", "no effect", "immune"]):
                    move_connected_2 = False
                # Also check if target fainted before the move (wouldn't have connected)
                if dfn and dfn.hp <= 0 and "fainted" in result_lower and "before" in result_lower:
                    move_connected_2 = False
            
            restriction_msgs = apply_move_restrictions(atk, dfn, chosen, {"category": "physical"}, 
                                                      field_effects=self.field, battle_state=self, move_connected=move_connected_2)
            for msg in restriction_msgs:
                log.append(f"  {msg}")
            
            # Recharge flag is set in engine.py's apply_move function
            # It only sets the flag if the move actually connected and had an effect
            
            # Update last move used
            _record_last_move(atk, chosen, battle_state=self)
            if hasattr(atk, '_mirror_move_copied') and atk._mirror_move_copied:
                _record_last_move(atk, atk._mirror_move_copied, battle_state=self)
                delattr(atk, '_mirror_move_copied')

            # Record the last move that targeted the defender (for Mirror Move behaviour)
            if dfn is not None and atk is not dfn:
                dfn.last_move_targeted = atk.last_move_used
                dfn.last_move_target_source = atk
            
            # === PIVOT MOVES: Check if attacker should switch immediately ===
            # Volt Switch, U-turn, Flip Turn, Parting Shot cause immediate switch after damage
            # BUT only if the move had an effect (not immune)
            pivot_moves = ["volt-switch", "u-turn", "flip-turn", "parting-shot"]
            if move_lower in pivot_moves and atk.hp > 0:
                # Check if move had no effect (immunity)
                move_had_effect = "no effect" not in move_result.lower() and "doesn't affect" not in move_result.lower()
                
                # Mark for immediate pivot switch only if move connected
                if move_had_effect and not hasattr(atk, '_pivot_switch_pending'):
                    atk._pivot_switch_pending = True
                    # Pivot switches handled at end of turn
            
            # === EMERGENCY EXIT / WIMP OUT: Check if defender needs to switch ===
            if dfn.hp > 0 and hasattr(dfn, '_emergency_exit_triggered') and dfn._emergency_exit_triggered:
                dfn._emergency_exit_triggered = False  # Clear flag
                # Mark for emergency forced switch (will be handled at end of turn like pivot switches)
                dfn._emergency_exit_pending = True
                
                # SPECIAL RULE: If Emergency Exit triggers from U-turn/Volt Switch, 
                # the U-turn user does NOT switch out
                if hasattr(atk, '_pivot_switch_pending') and atk._pivot_switch_pending:
                    atk._pivot_switch_pending = False
            
            # === EMERGENCY EXIT / WIMP OUT: Check if attacker needs to switch (Struggle recoil) ===
            if atk.hp > 0 and hasattr(atk, '_emergency_exit_triggered') and atk._emergency_exit_triggered:
                atk._emergency_exit_triggered = False  # Clear flag
                # Mark for emergency forced switch (will be handled at end of turn like pivot switches)
                atk._emergency_exit_pending = True
            
            # Check if defender fainted
            if dfn.hp <= 0:
                from .engine import release_octolock
                release_octolock(dfn)
                _record_registered_ko(atk, dfn, battle_state=self)
                _dispatch_award_exp_on_faint_callback(self, dfn)
                log.append(f"**{dfn.species}** fainted!")
                self._reconcile_special_weather(immediate_log=log)
                
                # Supreme Overlord: Increment fainted ally counter for all remaining team members
                # Determine defender's UID and party
                defender_uid = self.p2_id if uid == self.p1_id else self.p1_id
                defender_party = self.p2_team if defender_uid == self.p2_id else self.p1_team
                for mon in defender_party:
                    if mon.hp > 0:  # Only increment for alive Pokemon
                        mon._fainted_allies += 1
                
                # === DESTINY BOND: Take down attacker if active ===
                from .special_moves import check_destiny_bond, check_grudge
                if check_destiny_bond(atk, dfn):
                    atk.hp = 0
                    log.append(f"**{atk.species}** took its attacker down with it!")
                    
                    # Supreme Overlord: Also increment for attacker fainting
                    attacker_party = self.p1_team if uid == self.p1_id else self.p2_team
                    for mon in attacker_party:
                        if mon.hp > 0:
                            mon._fainted_allies += 1
                
                # === GRUDGE: Attacker's last move loses all PP ===
                grudge_msg = check_grudge(atk, dfn, chosen)
                if grudge_msg:
                    log.append(f"  {grudge_msg}")
                
                # Trigger on-KO abilities (Moxie, Beast Boost, Chilling Neigh, etc.)
                    from .engine import modify_stages
                attacker_ability = normalize_ability_name(atk.ability or "")
                attacker_ability_data = get_ability_effect(attacker_ability)
                
                if "on_ko" in attacker_ability_data and atk.hp > 0:
                    on_ko_effect = attacker_ability_data["on_ko"]
                    if "stages" in on_ko_effect:
                        stage_msgs = modify_stages(atk, on_ko_effect["stages"])
                        for msg in stage_msgs:
                            log.append(msg)
                    elif on_ko_effect.get("boost_highest_stat"):
                        # Beast Boost: Boost highest stat
                        # Bulbapedia: "For determining the highest stat, Beast Boost does not take into account 
                        # stat stages, held items, or reductions due to status conditions"
                        # Use the original calculated stats stored when the Mon was created
                        original_stats = getattr(atk, '_original_calculated_stats', None)
                        if original_stats:
                            stats = {
                                "atk": int(original_stats.get("atk", 0)),
                                "defn": int(original_stats.get("defn", 0)),
                                "spa": int(original_stats.get("spa", 0)),
                                "spd": int(original_stats.get("spd", 0)),
                                "spe": int(original_stats.get("spe", 0))
                            }
                        else:
                            # Fallback to current stats if original not stored
                            stats = {
                                "atk": int(atk.stats.get("atk", 0)),
                                "defn": int(atk.stats.get("defn", 0)),
                                "spa": int(atk.stats.get("spa", 0)),
                                "spd": int(atk.stats.get("spd", 0)),
                                "spe": int(atk.stats.get("spe", 0))
                            }
                        # Find the highest stat value - ensure we're comparing integers
                        highest_value = max(stats.values())
                        # Find all stats with the highest value
                        tied_stats = [stat for stat, value in stats.items() if value == highest_value]
                        # If there's a tie, prioritize: Attack > Defense > Sp. Atk > Sp. Def > Speed
                        if len(tied_stats) > 1:
                            priority_order = ["atk", "defn", "spa", "spd", "spe"]
                            for stat in priority_order:
                                if stat in tied_stats:
                                    highest_stat = stat
                                    break
                        else:
                            highest_stat = tied_stats[0]
                        
                        stage_msgs = modify_stages(atk, {highest_stat: 1})
                        for msg in stage_msgs:
                            log.append(msg)
                
                # Trigger form changes on KO (Battle Bond, etc.)
                form_msg = check_form_change(atk, triggered_by="after_ko", field_effects=self.field, battle_state=self)
                if form_msg:
                    log.append(f"  {form_msg}")
                
                # Check if the entire team is defeated
                defending_user_id = self.p2_id if uid == self.p1_id else self.p1_id
                defending_team = self.team_for(defending_user_id)
                alive_count = sum(1 for mon in defending_team if mon and mon.hp > 0)
                
                if alive_count == 0:
                    # Entire team fainted - battle over
                    defending_player = self.player_name(defending_user_id)
                    if defending_user_id == self.p2_id and (self.p2_name or "").lower().startswith("wild "):
                        species = (self.p2_name or "").replace("Wild ", "").replace("wild ", "").replace("⭐", "").strip()
                        log.append(f"\nThe wild {species.title() if species else 'Pokémon'} was defeated.")
                    else:
                        log.append(f"\n**{defending_player}** has no more Pokémon left!")
                    self.winner = uid
                else:
                    # Still have Pokémon alive - they must switch next turn
                    defending_player = self.player_name(defending_user_id)
                    log.append(f"**{defending_player}** must send out another Pokémon!")
        
        # End-of-turn status damage (burn, poison, toxic)
        from .engine import apply_status_effects
        
        # Get all active Pokemon for Air Lock/Cloud Nine check
        all_active_mons = [self._active(self.p1_id), self._active(self.p2_id)]
        
        # Apply to Player 1's active Pokémon
        if not self.winner and self._active(self.p1_id).hp > 0:
            p1_mon = self._active(self.p1_id)
            status_msgs = apply_status_effects(p1_mon, self._active(self.p2_id), self.field, all_active_mons)
            for msg in status_msgs:
                log.append(msg)
            
            # Check if died from status
            if p1_mon.hp <= 0:
                from .engine import release_octolock
                release_octolock(p1_mon)
                log.append(f"**{p1_mon.species}** fainted!")
                self._reconcile_special_weather(immediate_log=log)
                p1_team = self.team_for(self.p1_id)
                alive_count = sum(1 for mon in p1_team if mon and mon.hp > 0)
                if alive_count == 0:
                    log.append(f"\n**{self.p1_name}** has no more Pokémon left!")
                    self.winner = self.p2_id
        
        # Apply to Player 2's active Pokémon
        if not self.winner and self._active(self.p2_id).hp > 0:
            p2_mon = self._active(self.p2_id)
            status_msgs = apply_status_effects(p2_mon, self._active(self.p1_id), self.field, all_active_mons)
            for msg in status_msgs:
                log.append(msg)
            
            # Check if died from status
            if p2_mon.hp <= 0:
                from .engine import release_octolock
                release_octolock(p2_mon)
                log.append(f"**{p2_mon.species}** fainted!")
                self._reconcile_special_weather(immediate_log=log)
                p2_team = self.team_for(self.p2_id)
                alive_count = sum(1 for mon in p2_team if mon and mon.hp > 0)
                if alive_count == 0:
                    if (self.p2_name or "").lower().startswith("wild "):
                        species = (self.p2_name or "").replace("Wild ", "").replace("wild ", "").replace("⭐", "").strip()
                        log.append(f"\nThe wild {species.title() if species else 'Pokémon'} was defeated.")
                    else:
                        log.append(f"\n**{self.p2_name}** has no more Pokémon left!")
                    self.winner = self.p1_id
        
        # === ADVANCED MECHANICS: End-of-turn cleanup ===
        # Store current weather/terrain state before decrement
        prev_weather = self.field.weather
        
        # === INCREMENT TURN COUNTERS FOR FAKE OUT/FIRST IMPRESSION (at END of turn) ===
        # Do this BEFORE clearing _just_switched_in flags so we can check if Pokémon just switched in
        # Only increment for Pokémon that were active at the START of the turn
        # Pokémon that switched in this turn should have counter = 0 and stay at 0
        # This ensures Fake Out works on the first turn after switching in
        from .special_moves import increment_turns_since_switch
        for mon in [self._active(self.p1_id), self._active(self.p2_id)]:
            if mon and mon.hp > 0:
                # Check if this Pokémon just switched in this turn using the _just_switched_in flag
                # If they just switched in, don't increment the counter (leave it at 0)
                # If they were active at start of turn, increment the counter
                just_switched_in = getattr(mon, '_just_switched_in', False)
                if not just_switched_in:
                    # Pokémon was active at start of turn, so increment counter
                    increment_turns_since_switch(mon)
                # If just_switched_in is True, counter stays at 0 (will be incremented next turn)
        
        # Clear _just_switched_in flags (Shadow Tag doesn't trap on switch-in turn)
        for mon in [self._active(self.p1_id), self._active(self.p2_id)]:
            if mon and hasattr(mon, '_just_switched_in'):
                mon._just_switched_in = False
        
        prev_weather_turns = self.field.weather_turns
        prev_special = getattr(self.field, 'special_weather', None)
        prev_terrain = self.field.terrain
        prev_terrain_turns = self.field.terrain_turns
        
        # Decrement field effect counters
        self.field.decrement_turns()
        self.p1_side.decrement_turns()
        self.p2_side.decrement_turns()
        
        # Add weather/terrain continuation or stop messages
        current_special = getattr(self.field, 'special_weather', None)
        if prev_special:
            if prev_special == current_special:
                special_continue = {
                    "heavy-rain": "☔ The heavy rain continues to fall!",
                    "harsh-sunlight": "☀️ The extremely harsh sunlight continues to shine!",
                    "strong-winds": "💨 The mysterious strong winds keep blowing!"
                }.get(prev_special, "The special weather persists!")
                log.append(special_continue)
            elif not current_special:
                special_end = {
                    "heavy-rain": "☔ The heavy rain disappeared!",
                    "harsh-sunlight": "☀️ The extremely harsh sunlight faded!",
                    "strong-winds": "💨 The mysterious strong winds dissipated!"
                }.get(prev_special, "The special weather faded.")
                log.append(special_end)
        elif prev_weather and prev_weather == self.field.weather:
            # Weather continues
            weather_msg = {
                "sun": "☀️ The sunlight is strong!",
                "rain": "🌧️ Rain continues to fall!",
                "sandstorm": "🌪️ The sandstorm rages!",
                "sand": "🌪️ The sandstorm rages!",
                "snow": "❄️ Snow continues to fall!",
                "fog": "🌫️ The fog is deep!"
            }.get(prev_weather, f"{prev_weather.title()} continues!")
            log.append(weather_msg)
        elif prev_weather and not self.field.weather:
            weather_stop_msg = {
                "sun": "☀️ The sunlight faded.",
                "rain": "🌧️ The rain stopped.",
                "sandstorm": "🌪️ The sandstorm subsided.",
                "sand": "🌪️ The sandstorm subsided.",
                "snow": "❄️ The snow stopped.",
                "fog": "🌫️ The fog cleared."
            }.get(prev_weather, f"{prev_weather.title()} ended.")
            log.append(weather_stop_msg)
        
        if prev_terrain and prev_terrain == self.field.terrain:
            # Terrain continues
            terrain_msg = {
                "electric": "⚡ Electric Terrain is active!",
                "grassy": "🌿 Grassy Terrain is active!",
                "psychic": "🔮 Psychic Terrain is active!",
                "misty": "✨ Misty Terrain is active!"
            }.get(prev_terrain, f"{prev_terrain.title()} Terrain is active!")
            log.append(terrain_msg)
        elif prev_terrain and not self.field.terrain:
            # Terrain faded
            terrain_stop_msg = {
                "electric": "⚡ The Electric Terrain faded.",
                "grassy": "🌿 The Grassy Terrain faded.",
                "psychic": "🔮 The Psychic Terrain faded.",
                "misty": "✨ The Misty Terrain faded."
            }.get(prev_terrain, f"{prev_terrain.title()} Terrain faded.")
            log.append(terrain_stop_msg)
        
        # === DELAYED EFFECT MOVES ===
        from .special_moves import check_future_attacks, check_and_apply_wish
        
        # Check Future Sight / Doom Desire for both players
        if not self.winner:
            for uid in [self.p1_id, self.p2_id]:
                mon = self._active(uid)
                if mon and mon.hp > 0:
                    attack = check_future_attacks(self, id(mon))
                    if attack:
                        damage, user_name, move_name, extra_msg = attack
                        old_hp = mon.hp
                        mon.hp = max(0, mon.hp - damage)
                        log.append(f"**{mon.species}** took the **{move_name}** attack!")
                        if extra_msg:
                            for line in extra_msg.split("\n"):
                                if line:
                                    log.append(line)
                        
                        if mon.hp <= 0:
                            from .engine import release_octolock
                            release_octolock(mon)
                            log.append(f"**{mon.species}** fainted!")
                            self._reconcile_special_weather(immediate_log=log)
                            # Check if team is wiped
                            team = self.team_for(uid)
                            alive_count = sum(1 for m in team if m and m.hp > 0)
                            if alive_count == 0:
                                self.winner = self.p2_id if uid == self.p1_id else self.p1_id
        
        # Check Wish healing for both players
        if not self.winner:
            for uid in [self.p1_id, self.p2_id]:
                mon = self._active(uid)
                if mon and mon.hp > 0:
                    wish_msg = check_and_apply_wish(self, uid, mon)
                    if wish_msg:
                        log.append(f"  {wish_msg}")
        
        # Cleanup each Pokémon (decrement turn counters, clear flags)
        if not self.winner:
            for uid in [self.p1_id, self.p2_id]:
                mon = self._active(uid)
                if mon and mon.hp > 0:
                    # Debug: Show MissingNo type and ability
                    species_lower = mon.species.lower()
                    if species_lower in ["missing n0", "missing no", "missing no.", "missingno", "missingno.", "missing n0.", "missing no."]:
                        from .engine import _get_nullscape_type
                        nullscape_type = _get_nullscape_type(mon, self)
                        mon_types = [t for t in mon.types if t]
                        type_display = "/".join(mon_types) if mon_types else "Unknown"
                        ability_display = mon.ability or "Unknown"
                        log.append(f"  [DEBUG] MissingNo: Type={type_display}, Nullscape={nullscape_type or 'None'}, Ability={ability_display}")
                    
                    cleanup_msgs = end_of_turn_cleanup(mon, self.field)
                    for msg in cleanup_msgs:
                        log.append(msg)
                    
                    # Check form changes at end of turn (Schooling, etc.)
                    from .engine import check_form_change
                    form_msg = check_form_change(mon, triggered_by="end_of_turn", field_effects=self.field, battle_state=self)
                    if form_msg:
                        log.append(f"  {form_msg}")

        self.turn += 1
        
        # Check which players need to pivot/emergency switch
        pivot_switches = {}
        p1_mon = self._active(self.p1_id)
        p2_mon = self._active(self.p2_id)
        
        # Pivot switches (U-turn, Volt Switch, etc.)
        # Only handle if not already switched during the turn (immediate pivot switches)
        if hasattr(p1_mon, '_pivot_switch_pending') and p1_mon._pivot_switch_pending and p1_mon.hp > 0:
            pivot_switches[self.p1_id] = True
            p1_mon._pivot_switch_pending = False  # Clear flag
        if hasattr(p2_mon, '_pivot_switch_pending') and p2_mon._pivot_switch_pending and p2_mon.hp > 0:
            pivot_switches[self.p2_id] = True
            p2_mon._pivot_switch_pending = False  # Clear flag
        
        # Emergency Exit / Wimp Out forced switches
        # Only activate if the trainer has other Pokemon available
        if hasattr(p1_mon, '_emergency_exit_pending') and p1_mon._emergency_exit_pending and p1_mon.hp > 0:
            # Check if P1 has other Pokemon to switch to
            p1_team = self.team_for(self.p1_id)
            has_other_pokemon = any(m and m.hp > 0 and m != p1_mon for m in p1_team)
            if has_other_pokemon:
                pivot_switches[self.p1_id] = True
            p1_mon._emergency_exit_pending = False  # Clear flag regardless
        
        if hasattr(p2_mon, '_emergency_exit_pending') and p2_mon._emergency_exit_pending and p2_mon.hp > 0:
            # Check if P2 has other Pokemon to switch to
            p2_team = self.team_for(self.p2_id)
            has_other_pokemon = any(m and m.hp > 0 and m != p2_mon for m in p2_team)
            if has_other_pokemon:
                pivot_switches[self.p2_id] = True
            p2_mon._emergency_exit_pending = False  # Clear flag regardless
        
        # Roar/Whirlwind/Circle Throw/Dragon Tail forced switches
        # These force a RANDOM swap, not a player choice
        if hasattr(p1_mon, '_roar_forced_switch') and p1_mon._roar_forced_switch and p1_mon.hp > 0:
            # Check if P1 has other Pokemon to switch to
            p1_team = self.team_for(self.p1_id)
            available_switches = [i for i, m in enumerate(p1_team) if m and m.hp > 0 and m != p1_mon]
            if available_switches:
                # Force random swap immediately
                import random
                random_switch_index = random.choice(available_switches)
                switch_messages = self.apply_switch(self.p1_id, random_switch_index)
                new_mon = self._active(self.p1_id)
                # Add Leech Seed damage messages (if any)
                for msg in switch_messages:
                    log.append(msg)
                log.append(f"**{p1_mon.species}** was forced out! **{new_mon.species}** was sent out!")
                # Trigger on-switch-in abilities
                from pvp.engine import on_switch_in
                opp_mon = self._opp_active(self.p1_id)
                ability_msgs = on_switch_in(new_mon, opp_mon, self.field)
                for msg in ability_msgs:
                    log.append(msg)
            p1_mon._roar_forced_switch = False  # Clear flag regardless
        
        if hasattr(p2_mon, '_roar_forced_switch') and p2_mon._roar_forced_switch and p2_mon.hp > 0:
            # Check if P2 has other Pokemon to switch to
            p2_team = self.team_for(self.p2_id)
            available_switches = [i for i, m in enumerate(p2_team) if m and m.hp > 0 and m != p2_mon]
            if available_switches:
                # Force random swap immediately
                import random
                random_switch_index = random.choice(available_switches)
                switch_messages = self.apply_switch(self.p2_id, random_switch_index)
                new_mon = self._active(self.p2_id)
                # Add Leech Seed damage messages (if any)
                for msg in switch_messages:
                    log.append(msg)
                log.append(f"**{p2_mon.species}** was forced out! **{new_mon.species}** was sent out!")
                # Trigger on-switch-in abilities
                from pvp.engine import on_switch_in
                opp_mon = self._opp_active(self.p2_id)
                ability_msgs = on_switch_in(new_mon, opp_mon, self.field)
                for msg in ability_msgs:
                    log.append(msg)
            p2_mon._roar_forced_switch = False  # Clear flag regardless
        
        # === INCREMENT TURN COUNTERS FOR FAKE OUT/FIRST IMPRESSION (at END of turn) ===
        # Only increment for Pokémon that were active at the START of the turn
        # Pokémon that switched in this turn should have counter = 0 and stay at 0
        # This ensures Fake Out works on the first turn after switching in
        from .special_moves import increment_turns_since_switch
        for mon in [self._active(self.p1_id), self._active(self.p2_id)]:
            if mon and mon.hp > 0:
                # Check if this Pokémon just switched in this turn using the _just_switched_in flag
                # This flag is set when switching in and cleared at end of turn (before this code runs)
                # So we check the counter: if it's 0, they just switched in, so don't increment
                # If it's > 0, they were active at start of turn, so increment
                turns_since_switch = getattr(mon, '_turns_since_switch_in', 0)
                # Only increment if counter is already > 0 (Pokémon was active at start of turn)
                # If counter is 0, it means they just switched in this turn, so leave it at 0
                if turns_since_switch > 0:
                    increment_turns_since_switch(mon)
                # Note: Counter stays at 0 for Pokémon that just switched in
                # On the next turn, if they're still active, counter will be 0, and we'll increment it then
                # Clear item just received flag (Trick/Switcheroo delay ends)
                if hasattr(mon, '_item_just_received'):
                    mon._item_just_received = False
        
        if self._pending_weather_messages:
            log.extend(self._pending_weather_messages)
            self._pending_weather_messages.clear()

        _log_resolve()
        return log, pivot_switches, None  # None indicates no mid-turn pivot switch needed

# ============================  UI HELPERS & VIEWS  ============================

def _hp_bar(cur: int, max_hp: int) -> str:
    """Create a solid HP bar like Discord's progress bar"""
    if max_hp <= 0:
        return "⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛"
    
    pct = max(0.0, min(1.0, cur / max_hp))
    total_blocks = 20  # Total width of the bar
    filled = int(round(pct * total_blocks))
    
    # Create solid bar using block characters
    # Using full block (█) for filled and light shade (░) for empty
    bar = "█" * filled + "░" * (total_blocks - filled)
    
    # Color coding based on HP percentage
    if pct > 0.5:
        color = "🟢"  # Green for healthy
    elif pct > 0.2:
        color = "🟡"  # Yellow for moderate
    else:
        color = "🔴"  # Red for critical
    
    return f"{color} {bar}"

def _hp_bar_simple(cur: int, max_hp: int) -> str:
    """Simple HP bar without emoji prefix for compact display"""
    if max_hp <= 0:
        return "░" * 20
    
    pct = max(0.0, min(1.0, cur / max_hp))
    total_blocks = 20
    filled = int(round(pct * total_blocks))
    
    return "█" * filled + "░" * (total_blocks - filled)

def _field_conditions_text(field) -> str:
    """Generate formatted text showing current weather/terrain/field effects"""
    lines = []
    
    # Weather
    if field.weather:
        special = getattr(field, 'special_weather', None)
        if special == "heavy-rain":
            weather_name = "☔ Heavy Rain"
        elif special == "harsh-sunlight":
            weather_name = "☀️ Extremely Harsh Sunlight"
        elif special == "strong-winds":
            weather_name = "💨 Strong Winds"
        else:
            weather_name = {
                "sun": "☀️ Harsh Sunlight",
                "rain": "🌧️ Rain",
                "sandstorm": "🌪️ Sandstorm",
                "sand": "🌪️ Sandstorm",
                "snow": "❄️ Snow",
                "hail": "❄️ Hail",
                "fog": "🌫️ Fog"
            }.get(field.weather, field.weather.title())
        
        if special in {"heavy-rain", "harsh-sunlight", "strong-winds"}:
            lines.append(f"**Weather:** {weather_name} (indefinite)")
        elif field.weather_turns > 0:
            lines.append(f"**Weather:** {weather_name} ({field.weather_turns} turns left)")
        else:
            lines.append(f"**Weather:** {weather_name} (indefinite)")
    
    # Terrain
    if field.terrain:
        terrain_name = {
            "electric": "⚡ Electric Terrain",
            "grassy": "🌿 Grassy Terrain",
            "psychic": "🔮 Psychic Terrain",
            "misty": "✨ Misty Terrain"
        }.get(field.terrain, field.terrain.title())
        
        lines.append(f"**Terrain:** {terrain_name} ({field.terrain_turns} turns left)")
    
    # Other field effects
    if field.trick_room:
        lines.append(f"**Trick Room** ({field.trick_room_turns} turns left)")
    if field.magic_room:
        lines.append(f"**Magic Room** ({field.magic_room_turns} turns left)")
    if field.wonder_room:
        lines.append(f"**Wonder Room** ({field.wonder_room_turns} turns left)")
    if field.gravity:
        lines.append(f"**Gravity** ({field.gravity_turns} turns left)")
    
    return "\n".join(lines) if lines else ""

def _team_embed(user_id: int, st: BattleState) -> discord.Embed:
    team = st.team_for(user_id)
    active = st.p1_active if user_id == st.p1_id else st.p2_active
    em = discord.Embed(
        title="🎒 Your Team",
        color=discord.Color.blue()
    )
    chunks = []
    for i, m in enumerate(team):
        # Skip if Mon is None (shouldn't happen but defensive)
        if m is None:
            continue
            
        # Format Pokémon name with star for shiny and capitalize
        pokemon_display = _format_pokemon_name(m)
        # Active indicator (different symbol)
        active_mark = "▶️ " if i == active else "　"
        faint = " 💀" if m.hp <= 0 else ""
        
        # Safely get moves
        mv = getattr(m, 'moves', None)
        if mv is None:
            mv = []
        
        # Format moves with Hidden Power type
        move_labels = []
        for move in mv:
            normalized = move.lower().replace(" ", "-").strip()
            if normalized.startswith("hidden-power"):
                from .hidden_power import calculate_hidden_power_type
                hp_type = calculate_hidden_power_type(m.ivs, generation=st.gen)
                move_labels.append(f"HP [{hp_type}]")
            else:
                move_labels.append(move)
        
        # Create HP status
        hp_bar = _hp_bar_simple(m.hp, m.max_hp)
        hp_text = f"**{m.hp}/{m.max_hp} HP**" if m.hp > 0 else "**FNT**"
        
        chunks.append(
            f"{active_mark}**{pokemon_display}** Lv{m.level}{faint}\n"
            f"{hp_bar} {hp_text}\n"
            f"**1.** {move_labels[0] if len(move_labels)>0 else '-'}　**2.** {move_labels[1] if len(move_labels)>1 else '-'}\n"
            f"**3.** {move_labels[2] if len(move_labels)>2 else '-'}　**4.** {move_labels[3] if len(move_labels)>3 else '-'}\n"
        )
    em.description = "\n".join(chunks)
    return em


def _team_switch_embed(user_id: int, st: BattleState, description_override: Optional[str] = None) -> discord.Embed:
    """Build the Swapping UI as a full self-team overview (moves + HP)."""
    team = st.team_for(user_id)
    active_idx = st.p1_active if user_id == st.p1_id else st.p2_active
    switchable = set(st.switch_options(user_id) or [])

    desc = description_override or "Click the name of the Pokémon you wish to swap to."
    em = discord.Embed(
        title="🔄 Swapping",
        description=desc,
        color=discord.Color.dark_grey(),
    )

    chunks: list[str] = []
    for idx, m in enumerate(team):
        if m is None:
            continue
        name = _format_pokemon_name(m)
        hp_bar = _hp_bar_simple(m.hp, m.max_hp)
        hp_text = f"**{m.hp}/{m.max_hp} HP**" if m.hp > 0 else "**FNT**"
        mv = getattr(m, "moves", None) or []
        move_labels = []
        for move in mv:
            norm = move.lower().replace(" ", "-").strip()
            if norm.startswith("hidden-power"):
                from .hidden_power import calculate_hidden_power_type
                hp_type = calculate_hidden_power_type(m.ivs, generation=st.gen)
                move_labels.append(f"HP [{hp_type}]")
            else:
                move_labels.append(move)
        active_mark = "▶️ " if idx == active_idx else "　"
        faint = " 💀" if m.hp <= 0 else ""
        if idx == active_idx:
            status_line = "Current Active"
        elif idx in switchable:
            status_line = "Switchable"
        else:
            status_line = "Not switchable"
        chunks.append(
            f"{active_mark}**{name}** Lv{m.level}{faint} — *{status_line}*\n"
            f"{hp_bar} {hp_text}\n"
            f"**1.** {move_labels[0] if len(move_labels) > 0 else '-'}　**2.** {move_labels[1] if len(move_labels) > 1 else '-'}\n"
            f"**3.** {move_labels[2] if len(move_labels) > 2 else '-'}　**4.** {move_labels[3] if len(move_labels) > 3 else '-'}"
        )

    team_block = "\n\n".join(chunks) if chunks else "—"
    full_desc = f"{desc}\n\n{team_block}".strip()
    if len(full_desc) > 4096:
        full_desc = full_desc[:4093] + "..."
    em.description = full_desc
    return em

def _already_locked_embed(turn_no: int) -> discord.Embed:
    return discord.Embed(
        title="Action already locked",
        description=f"You've already locked your action for **Turn {turn_no}**.",
        color=discord.Color.orange()
    )

class TeamSwitchView(discord.ui.View):
    def __init__(self, user_id: int, state: BattleState,
                 on_done: Callable[[Dict[str, Any], discord.Interaction], Any]):
        super().__init__(timeout=160.0)  # Match turn timer
        self.user_id = user_id
        self.state = state
        self._on_done = on_done
        # One button per switchable Pokémon, labeled with display name (like "Talonflame", "Gastly")
        for idx in state.switch_options(user_id):
            mon = state.team_for(user_id)[idx]
            label = _format_pokemon_name(mon)
            b = _SwitchButton(label=label, idx=idx, on_done=on_done)
            b.row = 0
            self.add_item(b)
        if not self.children:
            self.add_item(discord.ui.Button(label="No switchable Pokémon", disabled=True, style=discord.ButtonStyle.secondary, row=0))

    async def interaction_check(self, itx: discord.Interaction) -> bool:
        if itx.user.id != self.user_id:
            try:
                if itx.response.is_done():
                    await itx.followup.send("this isn't for you", ephemeral=True)
                else:
                    await itx.response.send_message("this isn't for you", ephemeral=True)
            except Exception:
                pass
            return False
        return True
    
    async def on_timeout(self):
        """Called when the view times out."""
        # Disable all buttons
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        # Stop the view to clean up listeners
        self.stop()
    
    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        """Handle interaction errors gracefully."""
        public_ui = _battle_ui_is_public(self.state)
        response_ephemeral = not public_ui
        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    "⚠️ This command has timed out. Please wait for the next turn.",
                    ephemeral=response_ephemeral
                )
            else:
                await interaction.response.send_message(
                    "⚠️ This command has timed out. Please wait for the next turn.",
                    ephemeral=response_ephemeral
                )
        except:
            pass

class _SwitchButton(discord.ui.Button):
    def __init__(self, *, label: str, idx: int,
                 on_done: Callable[[Dict[str, Any], discord.Interaction], Any]):
        super().__init__(label=label, style=discord.ButtonStyle.secondary)
        self.idx = idx
        self._on_done = on_done
    async def callback(self, itx: discord.Interaction):
        view: TeamSwitchView = self.view  # type: ignore
        st = view.state
        response_ephemeral = not _battle_ui_is_public(st)
        if st.is_locked(itx.user.id):
            await itx.response.send_message(embed=_already_locked_embed(st.turn), ephemeral=response_ephemeral)
            return
        # Lock the player BEFORE processing, but unlock on error
        st.lock(itx.user.id)
        try:
            await itx.response.send_message(f"Switching to **{self.label}**.", ephemeral=response_ephemeral)
            await self._on_done({"kind": "switch", "value": self.idx}, itx)
        except Exception as e:
            # If an error occurs, unlock the player so they can try again
            st.unlock(itx.user.id)
            # Try to send an error message if response isn't done yet
            try:
                if not itx.response.is_done():
                    await itx.response.send_message(
                        f"❌ An error occurred. Please try selecting your switch again.",
                        ephemeral=response_ephemeral
                    )
                else:
                    await itx.followup.send(
                        f"❌ An error occurred. Please try selecting your switch again.",
                        ephemeral=response_ephemeral
                    )
            except:
                pass  # If we can't send error message, that's okay
            # Re-raise the exception so it can be logged by the error handler
            raise

class MoveView(discord.ui.View):
    """Row 0: all (allowed) moves; Row 1: Team + extras + Forfeit."""
    def __init__(self, who_id: int, state: BattleState,
                 on_done: Callable[[Dict[str, Any], discord.Interaction], Any],
                 hide_team_button: bool = False,
                 show_bag: bool = False):
        super().__init__(timeout=160.0)  # Slightly longer than turn timer for safety
        self.who_id = who_id
        self.state = state
        self.on_done = on_done
        self.z_move_mode: bool = False  # Track if Z-Move mode is active

        # Row 0 — moves (respect PP & Choice lock)
        self._update_move_buttons()

        # Row 1 — Team + Z-Move (Gen 7 only) + Dynamax (Gen 8+ only) + Bag (optional) + Forfeit
        # Hide team button if switch was blocked (prevents error when user tries to switch again)
        if not hide_team_button:
            t = _TeamButton()
            t.row = 1
            self.add_item(t)
        # Bag button (Heal/Throw) — only for adventure/Wild battles, not ranked PvP
        if show_bag:
            b = _BagButton(self)
            b.row = 1
            self.add_item(b)
        
        # Z-Move button (Gen 7 only, not used yet, has Z-Crystal, and has Z-Ring active)
        if state.gen == 7 and not state._z_move_used.get(who_id, False):
            mon = state._active(who_id)
            if mon and mon.item and is_z_crystal(mon.item):
                    # Check if player has Z-Ring equipped AND active for Gen 7 (synchronous check)
                    has_z_ring = _check_z_gear_sync(str(who_id), battle_gen=state.gen)
                    if has_z_ring:
                        z_btn = _ZMoveButton(self)
                        z_btn.row = 1
                        self.add_item(z_btn)
        
        # Mega Evolution button (Gen 6-7, once per battle, requires Mega gear)
        if 6 <= state.gen <= 7 and not state._mega_used.get(who_id, False):
            mon = state._active(who_id)
            if mon and getattr(mon, "can_mega_evolve", False) and not getattr(mon, "mega_evolved", False):
                if _check_mega_gear_sync(str(who_id), battle_gen=state.gen):
                    m_btn = _MegaButton(self)
                    m_btn.row = 1
                    self.add_item(m_btn)
        
        # Dynamax button (Gen 8+ only, not used yet, with Dynamax Band active)
        if state.gen >= 8 and not state._dynamax_used.get(who_id, False):
            mon = state._active(who_id)
            if mon:
                # Check if this species can Dynamax (Zacian, Zamazenta, Eternatus cannot)
                from .max_moves import can_dynamax_species, can_gigantamax
                if can_dynamax_species(mon.species):
                    # Check if player has Dynamax Band equipped AND active for Gen 8+ (synchronous check)
                    has_dmax_gear = _check_dmax_gear_sync(str(who_id), battle_gen=state.gen)
                    if has_dmax_gear:
                        d_btn = _DynamaxButton(self)
                        # Check if Pokémon can Gigantamax and set label accordingly
                        if can_gigantamax(mon.species, mon):
                            d_btn.label = "Gigantamax"
                        d_btn.row = 1
                        self.add_item(d_btn)
        
        # Terastallize button (Gen 9+ only, once per battle, requires Tera Orb)
        if state.gen >= 9 and not state._tera_used.get(who_id, False):
            mon = state._active(who_id)
            if mon and getattr(mon, "tera_type", None) and not getattr(mon, "terastallized", False):
                if _check_tera_gear_sync(str(who_id), battle_gen=state.gen):
                    t_btn = _TerastallizeButton(self)
                    t_btn.row = 1
                    self.add_item(t_btn)
        
        f = _ForfeitButton(state)
        f.row = 1
        self.add_item(f)
    
    def _update_move_buttons(self):
        """Update move buttons with current Z-Move mode or Dynamax state."""
        # Clear existing move buttons (keep Team/Z-Move/Dynamax/Forfeit)
        to_remove = [item for item in self.children if isinstance(item, _MoveButton)]
        for item in to_remove:
            self.remove_item(item)
        
        # Re-add move buttons with appropriate labels
        mon = self.state._active(self.who_id)
        for mv in self.state.moves_for(self.who_id):
            move_lower = mv.lower()
            z_enabled = False
            button_style = discord.ButtonStyle.primary
            # For adventure battles, use a softer neutral style for moves to match the mockup
            if (self.state.fmt_label or "").lower().startswith("adventure"):
                button_style = discord.ButtonStyle.secondary
            
            if move_lower != "struggle":
                pp_left = self.state._pp_left(self.who_id, mv, mon=mon)
                base_label = self._format_base_move_label(mon, mv, pp_left)
                disabled = pp_left <= 0
            else:
                pp_left = None
                base_label = "Struggle"
                disabled = False
            
            label = base_label
            if self.z_move_mode and move_lower != "struggle" and not disabled:
                can_z, z_label = self._compute_z_move_label(mon, mv, pp_left, base_label)
                if can_z:
                    label = z_label
                    z_enabled = True
                    button_style = discord.ButtonStyle.success
            
            b = _MoveButton(mv, label, self.on_done, z_enabled=z_enabled, style=button_style)
            b.disabled = disabled
            b.row = 0
            self.add_item(b)
    
    def _format_base_move_label(self, mon: Mon, move_name: str, pp_left: int) -> str:
        normalized = move_name.lower().replace(" ", "-").strip()
        
        if normalized.startswith("hidden-power"):
            from .hidden_power import calculate_hidden_power_type
            hp_type = calculate_hidden_power_type(mon.ivs, generation=self.state.gen)
            return f"Hidden Power [{hp_type}] ({pp_left})"
        
        def format_move_name(name: str) -> str:
            return name.replace("-", " ").title()
        
        if mon.dynamaxed:
            from .max_moves import get_max_move_name
            move_data = _get_move_with_cache(move_name, battle_state=self, generation=self.gen)
            if move_data:
                move_type = move_data.get("type", "Normal")
                is_gmax = getattr(mon, "is_gigantamax", False) and self.state.gen >= 8
                max_name = get_max_move_name(move_name, mon.species, move_type, is_gmax)
                return f"{format_move_name(max_name)} ({pp_left})"
        
        return f"{format_move_name(move_name)} ({pp_left})"
    
    def _compute_z_move_label(
        self,
        mon: Mon,
        move_name: str,
        pp_left: int,
        fallback_label: str
    ) -> Tuple[bool, str]:
        can_use, _ = can_use_z_move(self.who_id, mon, move_name, self.state.gen)
        if not can_use:
            return False, fallback_label
        
        move_data = _get_move_with_cache(move_name, battle_state=self, generation=self.gen)
        move_type = move_data.get("type", "Normal") if move_data else "Normal"
        z_name = get_z_move_name(move_name, mon.species, move_type, mon.item)
        return True, f"{z_name} ({pp_left})"
    
    async def on_timeout(self):
        """Called when the view times out."""
        # Disable all buttons
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        # Stop the view to clean up listeners
        self.stop()
    
    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        """Handle interaction errors gracefully."""
        public_ui = _battle_ui_is_public(self.state)
        response_ephemeral = not public_ui
        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    "⚠️ This command has timed out. Please wait for the next turn.",
                    ephemeral=response_ephemeral
                )
            else:
                await interaction.response.send_message(
                    "⚠️ This command has timed out. Please wait for the next turn.",
                    ephemeral=response_ephemeral
                )
        except:
            pass  # Interaction already expired, nothing we can do

    async def interaction_check(self, itx: discord.Interaction) -> bool:
        if itx.user.id != self.who_id:
            try:
                if itx.response.is_done():
                    await itx.followup.send("this isn't for you", ephemeral=True)
                else:
                    await itx.response.send_message("this isn't for you", ephemeral=True)
            except Exception:
                pass
            return False
        return True

class _MoveButton(discord.ui.Button):
    def __init__(
        self,
        move_name: str,
        label: str,
        on_done: Callable[[Dict[str, Any], discord.Interaction], Any],
        *,
        z_enabled: bool = False,
        style: Optional[discord.ButtonStyle] = None,
    ):
        if style is None:
            style = discord.ButtonStyle.primary
        super().__init__(label=label, style=style)
        self._on_done = on_done
        self._move_name = move_name
        self._original_move_name = move_name  # Store original for Z-Move transformation
        self._z_enabled = z_enabled
    
    async def callback(self, itx: discord.Interaction):
        view: MoveView = self.view  # type: ignore
        st = view.state
        response_ephemeral = not _battle_ui_is_public(st)
        if st.is_locked(itx.user.id):
            await itx.response.send_message(embed=_already_locked_embed(st.turn), ephemeral=response_ephemeral)
            return

        # Block if button was for a move now at 0 PP (race condition), unless Struggle
        active_mon = st._active(itx.user.id)
        if self._move_name.lower() != "struggle" and st._pp_left(itx.user.id, self._move_name, mon=active_mon) <= 0:
            await itx.response.send_message(f"**{self._move_name}** has no PP left!", ephemeral=response_ephemeral)
            return

        # If Dynamaxed, moves are automatically Max Moves (no flag needed, detected in engine)
        # If Z-Move mode is active, mark the move as a Z-Move
        move_choice = {"kind": "move", "value": self._move_name}
        if view.z_move_mode and getattr(self, "_z_enabled", False):
            move_choice["z_move"] = True
        
        # Mark participant on move selection
        st._mark_participant(itx.user.id)
        
        # Lock the player BEFORE processing, but unlock on error
        st.lock(itx.user.id)
        try:
            mon = st._active(itx.user.id)
            
            # Determine move display name
            if mon.dynamaxed:
                # Show Max Move name if Dynamaxed
                from .max_moves import get_max_move_name
                # Use top-level get_move import (don't shadow)
                move_data = _get_move_with_cache(self._move_name, battle_state=self, generation=self.gen)
                if move_data:
                    move_type = move_data.get("type", "Normal")
                    is_gmax = mon.is_gigantamax and st.gen >= 8
                    move_display = get_max_move_name(self._move_name, mon.species, move_type, is_gmax)
                else:
                    move_display = self._move_name
            elif view.z_move_mode and move_choice.get("z_move"):
                from .z_moves import get_z_move_name
                # Use top-level get_move import (don't shadow)
                move_data = _get_move_with_cache(self._move_name, battle_state=self, generation=self.gen)
                if move_data:
                    move_type = move_data.get("type", "Normal")
                    move_display = get_z_move_name(self._move_name, mon.species, move_type)
                else:
                    move_display = self._move_name
            else:
                move_display = self._move_name
            
            move_display_text = _format_move_name(str(move_display or self._move_name))
            # Send response and register choice - if either fails, unlock the player
            await itx.response.send_message(f"✅ Move selected: **{move_display_text}**.", ephemeral=response_ephemeral)
            await self._on_done(move_choice, itx)
        except Exception as e:
            # If an error occurs, unlock the player so they can try again
            st.unlock(itx.user.id)
            # Try to send an error message if response isn't done yet
            try:
                if not itx.response.is_done():
                    await itx.response.send_message(
                        f"❌ An error occurred. Please try selecting your move again.",
                        ephemeral=response_ephemeral
                    )
                else:
                    await itx.followup.send(
                        f"❌ An error occurred. Please try selecting your move again.",
                        ephemeral=response_ephemeral
                    )
            except:
                pass  # If we can't send error message, that's okay
            # Re-raise the exception so it can be logged by the error handler
            raise

class _TeamButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Team", style=discord.ButtonStyle.primary)
    async def callback(self, itx: discord.Interaction):
        view: MoveView = self.view  # type: ignore
        st = view.state
        response_ephemeral = not _battle_ui_is_public(st)
        if st.is_locked(itx.user.id):
            await itx.response.send_message(embed=_already_locked_embed(st.turn), ephemeral=response_ephemeral)
            return
        em = _team_switch_embed(itx.user.id, st)
        v = TeamSwitchView(itx.user.id, st, view.on_done)
        await itx.response.send_message(embed=em, ephemeral=response_ephemeral, view=v)

class _ZMoveButton(discord.ui.Button):
    def __init__(self, move_view: 'MoveView'):
        self.move_view = move_view
        # Will be updated in callback based on availability
        super().__init__(label="Z-Move", style=discord.ButtonStyle.success)
        self._update_enabled()
    
    def _update_enabled(self):
        """Update button enabled state based on Z-Move requirements."""
        # Button visibility is now controlled at creation time
        # This method is kept for backward compatibility but button should already be visible
        st = self.move_view.state
        who_id = self.move_view.who_id
        
        # If Z-Move already used, button should have been removed, but double-check
        if st._z_move_used.get(who_id, False):
            self.disabled = True
            return
        
        # Button enabled (will verify Z-Ring in callback)
        self.disabled = False
    
    async def callback(self, itx: discord.Interaction):
        view: MoveView = self.view  # type: ignore
        st = view.state
        response_ephemeral = _battle_ui_ephemeral(st)
        if st.is_locked(itx.user.id):
            await itx.response.send_message(embed=_already_locked_embed(st.turn), ephemeral=response_ephemeral)
            return
        
        # Verify Z-Ring equipment
        user_id_str = str(itx.user.id)
        has_z_ring = False
        
        # Check equipment table for Z-Ring (using sync check since we're in async callback)
        try:
            has_z_ring = _check_z_gear_sync(user_id_str, battle_gen=st.gen)
        except Exception:
            # Fallback: try async check if sync fails
            if db_async:
                try:
                    conn = await db_async.connect()
                    try:
                        cur = await conn.execute(
                            "SELECT z_gear FROM user_equipment WHERE owner_id=?",
                            (user_id_str,)
                        )
                        row = await cur.fetchone()
                        await cur.close()
                        
                        if row:
                            # row supports dictionary-style access: row["z_gear"]
                            z_gear = row["z_gear"] if "z_gear" in row.keys() else (row[0] if len(row) > 0 else None)
                            has_gear = bool(z_gear) and str(z_gear).strip() != ""
                            # Z-Ring is only active in Gen 7
                            has_z_ring = has_gear and st.gen == 7
                    finally:
                        await conn.close()
                except Exception:
                    has_z_ring = False
            else:
                has_z_ring = False
        
        if not has_z_ring:
            # Provide better error message based on the issue
            if st.gen != 7:
                await itx.response.send_message(
                    f"❌ Z-Moves can only be used in Gen 7 battles! This battle is Gen {st.gen}.",
                    ephemeral=response_ephemeral
                )
            else:
                await itx.response.send_message(
                    "❌ You need a Z-Ring equipped to use Z-Moves! Use `/equipgear` to equip one.",
                    ephemeral=response_ephemeral
                )
            return
        
        # Check if Z-Move already used this battle
        if st._z_move_used.get(itx.user.id, False):
            await itx.response.send_message(
                "❌ You've already used a Z-Move this battle!",
                ephemeral=response_ephemeral
            )
            return
        
        # Toggle Z-Move mode
        view.z_move_mode = not view.z_move_mode
        view._update_move_buttons()
        
        # Update button label - show "Cancel" when active, "Z-Move" when inactive
        if view.z_move_mode:
            self.label = "Cancel"
            await itx.response.edit_message(view=view)
            await itx.followup.send("✨ Z-Move mode activated! Move names now show Z-Move names.", ephemeral=response_ephemeral)
        else:
            self.label = "Z-Move"
            await itx.response.edit_message(view=view)
            await itx.followup.send("Z-Move mode deactivated.", ephemeral=response_ephemeral)

class _MegaButton(discord.ui.Button):
    def __init__(self, move_view: 'MoveView'):
        self.move_view = move_view
        super().__init__(label="Mega Evolve", style=discord.ButtonStyle.success)
        self._update_enabled()
    
    def _update_enabled(self):
        st = self.move_view.state
        who_id = self.move_view.who_id
        if st.gen < 6 or st.gen > 7:
            self.disabled = True
            return
        if st._mega_used.get(who_id, False):
            self.disabled = True
            return
        mon = st._active(who_id)
        if not mon or getattr(mon, "mega_evolved", False) or not getattr(mon, "can_mega_evolve", False):
            self.disabled = True
            return
        self.disabled = False
    
    async def callback(self, itx: discord.Interaction):
        view: MoveView = self.view  # type: ignore
        st = view.state
        response_ephemeral = _battle_ui_ephemeral(st)
        await itx.response.defer(ephemeral=response_ephemeral)
        if st.is_locked(itx.user.id):
            await itx.followup.send(embed=_already_locked_embed(st.turn), ephemeral=response_ephemeral)
            return
        if st.gen < 6 or st.gen > 7:
            await itx.followup.send(f"❌ Mega Evolution is not available in Gen {st.gen}.", ephemeral=response_ephemeral)
            return
        if st._mega_used.get(itx.user.id, False):
            await itx.followup.send("❌ You've already Mega Evolved this battle!", ephemeral=response_ephemeral)
            return
        if not _check_mega_gear_sync(str(itx.user.id), battle_gen=st.gen):
            await itx.followup.send(
                "❌ You need your Mega gear equipped and unlocked to Mega Evolve.",
                ephemeral=response_ephemeral
            )
            return
        mon = st._active(itx.user.id)
        if not mon:
            await itx.followup.send("❌ No active Pokémon to Mega Evolve.", ephemeral=response_ephemeral)
            return
        if getattr(mon, "mega_evolved", False):
            await itx.followup.send(f"{mon.species} is already Mega Evolved.", ephemeral=response_ephemeral)
            return
        can, reason, variant = can_mega_evolve(mon, state=st, generation=st.gen)
        if not can or not variant:
            await itx.followup.send(f"❌ {reason or 'Cannot Mega Evolve right now.'}", ephemeral=response_ephemeral)
            return
        # Store mega evolution choice instead of applying immediately
        # Mega evolution will be applied AFTER switches are processed
        if not hasattr(st, '_pending_mega_evolutions'):
            st._pending_mega_evolutions = {}
        st._pending_mega_evolutions[itx.user.id] = variant
        self.disabled = True
        self.label = "Mega Evolved"
        self.style = discord.ButtonStyle.secondary
        view._update_move_buttons()
        # Send confirmation message - remind user they still need to select a move
        mon_name = _format_pokemon_name(mon)
        await itx.followup.send(
            f"✅ {mon_name} will Mega Evolve this turn!\n\n⚠️ **Don't forget to select a move!**",
            ephemeral=response_ephemeral
        )
        try:
            message_obj = await itx.original_response()
            await message_obj.edit(view=view)
        except Exception:
            try:
                await itx.response.edit_message(view=view)
            except Exception:
                pass


class _DynamaxButton(discord.ui.Button):
    def __init__(self, move_view: 'MoveView'):
        self.move_view = move_view
        # Will be updated in callback based on availability
        # Label will be set by caller (either "Dynamax" or "Gigantamax")
        super().__init__(label="Dynamax", style=discord.ButtonStyle.success)
        self._update_enabled()
    
    def _update_enabled(self):
        """Update button enabled state based on Dynamax requirements."""
        st = self.move_view.state
        who_id = self.move_view.who_id
        
        # Check generation (must be Gen 8+)
        if st.gen < 8:
            self.disabled = True
            return
        
        # Note: Gear check is async, so we skip it in _update_enabled
        # It will be checked in the callback instead
        # This is a limitation - button state won't reflect gear until clicked
        
        # Check if player has already used Dynamax this battle
        if st._dynamax_used.get(who_id, False):
            self.disabled = True
            return
        
        # Check if Pokemon is already Dynamaxed
        mon = st._active(who_id)
        if not mon or mon.dynamaxed:
            self.disabled = True
            return
        
        # Check if Pokemon can Dynamax (not Zacian, Zamazenta, Eternatus)
        from .max_moves import can_dynamax
        can_dmax, _ = can_dynamax(mon)
        if not can_dmax:
            self.disabled = True
            return
        
        # Button enabled (gear check happens in callback)
        self.disabled = False
    
    async def callback(self, itx: discord.Interaction):
        # Defer immediately to prevent timeout
        view: MoveView = self.view  # type: ignore
        st = view.state
        response_ephemeral = _battle_ui_ephemeral(st)
        await itx.response.defer(ephemeral=response_ephemeral)
        if st.is_locked(itx.user.id):
            await itx.followup.send(embed=_already_locked_embed(st.turn), ephemeral=response_ephemeral)
            return
        
        mon = st._active(itx.user.id)
        
        # Check if this is a cancel (button label is "Cancel" and Pokemon is Dynamaxed)
        if self.label == "Cancel" and mon.dynamaxed:
            # Revert Dynamax
            from .max_moves import revert_dynamax, can_gigantamax
            revert_dynamax(mon)
            st._dynamax_used[itx.user.id] = False
            # DO NOT lock here - user can still select a move after canceling
            
            # Update button label back to original (either "Dynamax" or "Gigantamax")
            if can_gigantamax(mon.species, mon):
                self.label = "Gigantamax"
            else:
                self.label = "Dynamax"
            view._update_move_buttons()  # Update move button labels
            
            # Edit the message to show updated view
            try:
                message_obj = await itx.original_response() if itx.response.is_done() else None
                if message_obj:
                    await message_obj.edit(view=view)
            except Exception:
                pass  # If we can't edit, that's okay
            
            await itx.followup.send(f"**{mon.species}** returned to normal size!", ephemeral=response_ephemeral)
            return
        
        # Check if already Dynamaxed (shouldn't happen if cancel works)
        if mon.dynamaxed:
            await itx.followup.send(
                f"**{mon.species}** is already Dynamaxed!",
                ephemeral=response_ephemeral
            )
            return
        
        # Check if already used Dynamax this battle
        if st._dynamax_used.get(itx.user.id, False):
            await itx.followup.send(
                "❌ You've already used Dynamax this battle!",
                ephemeral=response_ephemeral
            )
            return
        
        # Check if can Dynamax
        from .max_moves import can_dynamax, apply_dynamax, can_gigantamax
        can_dmax, reason = can_dynamax(mon)
        if not can_dmax:
            await itx.followup.send(
                f"❌ {reason or 'Cannot Dynamax'}",
                ephemeral=response_ephemeral
            )
            return
        
        # Check if player has Dynamax gear equipped
        has_dmax_gear = False
        if db_async:
            try:
                conn = await db_async.connect()
                try:
                    cur = await conn.execute(
                        "SELECT dmax_gear FROM user_equipment WHERE owner_id=?",
                        (str(itx.user.id),)
                    )
                    row = await cur.fetchone()
                    await cur.close()
                    dmax_gear = row[0] if row and len(row) > 0 else None
                    has_dmax_gear = bool(dmax_gear)
                except Exception:
                    has_dmax_gear = False
                finally:
                    await conn.close()
            except Exception:
                has_dmax_gear = False
        
        if not has_dmax_gear:
            await itx.followup.send(
                "❌ You need a Dynamax Band equipped to use Dynamax! Use `/equipgear` to equip one.",
                ephemeral=response_ephemeral
            )
            return
        
        # Activate Dynamax (check for Gigantamax capability - must check both species AND individual flag)
        is_gigantamax = can_gigantamax(mon.species, mon)
        success, message = apply_dynamax(mon, dynamax_level=10, is_gigantamax=is_gigantamax)
        
        if success:
            st._dynamax_used[itx.user.id] = True
            # DO NOT lock here - user still needs to select a move
            
            # Clear Choice lock (Dynamax bypasses Choice restrictions)
            st._clear_choice_lock_on_dynamax(itx.user.id)
            
            # Update button label to "Cancel" when active
            self.label = "Cancel"
            view._update_move_buttons()  # Update move button labels to show Max Moves
            
            # Edit the message to show updated view
            try:
                message_obj = await itx.original_response()
                if message_obj:
                    await message_obj.edit(view=view)
            except Exception:
                pass  # If we can't edit, that's okay
            
            await itx.followup.send(f"🔴 **{message}**", ephemeral=response_ephemeral)
        else:
            await itx.followup.send(
                f"❌ {message}",
                ephemeral=response_ephemeral
            )

class _TerastallizeButton(discord.ui.Button):
    def __init__(self, move_view: 'MoveView'):
        self.move_view = move_view
        super().__init__(label="Terastallize", style=discord.ButtonStyle.success)
        self._update_enabled()
    
    def _update_enabled(self):
        st = self.move_view.state
        mon = st._active(self.move_view.who_id)
        if not mon or getattr(mon, "terastallized", False):
            self.disabled = True
            return
        if not getattr(mon, "tera_type", None):
            self.disabled = True
            return
        if st._tera_used.get(self.move_view.who_id, False):
            self.disabled = True
            return
        if st.gen < 9:
            self.disabled = True
            return
        if not _check_tera_gear_sync(str(self.move_view.who_id), battle_gen=st.gen):
            self.disabled = True
    
    async def callback(self, itx: discord.Interaction):
        view: MoveView = self.view  # type: ignore
        st = view.state
        response_ephemeral = _battle_ui_ephemeral(st)
        await itx.response.defer(ephemeral=response_ephemeral)
        if st.is_locked(itx.user.id):
            await itx.followup.send(embed=_already_locked_embed(st.turn), ephemeral=response_ephemeral)
            return
        
        mon = st._active(itx.user.id)
        if not mon:
            await itx.followup.send("❌ No active Pokémon to Terastallize.", ephemeral=response_ephemeral)
            return
        
        if getattr(mon, "terastallized", False):
            await itx.followup.send(f"❌ **{mon.species}** is already Terastallized!", ephemeral=response_ephemeral)
            return
        
        if st._tera_used.get(itx.user.id, False):
            await itx.followup.send("❌ You've already Terastallized this battle!", ephemeral=response_ephemeral)
            return
        
        can_tera, reason = can_terastallize(mon)
        if not can_tera:
            await itx.followup.send(f"❌ {reason or 'Cannot Terastallize'}", ephemeral=response_ephemeral)
            return
        
        has_tera_gear = _check_tera_gear_sync(str(itx.user.id), battle_gen=st.gen)
        if not has_tera_gear and db_async:
            try:
                conn = await db_async.connect()
                try:
                    cur = await conn.execute(
                        "SELECT tera_gear FROM user_equipment WHERE owner_id=?",
                        (str(itx.user.id),)
                    )
                    row = await cur.fetchone()
                    await cur.close()
                    tera_gear = row[0] if row and len(row) > 0 else None
                    has_tera_gear = bool(tera_gear)
                except Exception:
                    has_tera_gear = False
                finally:
                    await conn.close()
            except Exception:
                has_tera_gear = False
        
        if not has_tera_gear:
            await itx.followup.send(
                "❌ You need a Tera Orb equipped to Terastallize! Use `/equipgear` to equip one.",
                ephemeral=response_ephemeral
            )
            return
        
        success, message = apply_terastallization(mon, state=st, field_effects=st.field)
        if success:
            st._tera_used[itx.user.id] = True
            self.disabled = True
            self.style = discord.ButtonStyle.secondary
            self.label = "Terastallized"
            view._update_move_buttons()
            try:
                message_obj = await itx.original_response()
                if message_obj:
                    await message_obj.edit(view=view)
            except Exception:
                pass
            await itx.followup.send(f"✨ **{message}**", ephemeral=response_ephemeral)
        else:
            await itx.followup.send(f"❌ {message}", ephemeral=response_ephemeral)

class _ForfeitButton(discord.ui.Button):
    def __init__(self, state: BattleState):
        label = "Forfeit"
        if state.p2_name.lower().startswith("wild "):
            label = "Run"
        super().__init__(label=label, style=discord.ButtonStyle.danger)
        self.state = state
    async def callback(self, itx: discord.Interaction):
        view: MoveView = self.view  # type: ignore
        st = view.state
        response_ephemeral = _battle_ui_ephemeral(st)
        # Forfeit always works, even if already locked
        # (Don't check is_locked - allow forfeit anytime)
        if not st.is_locked(itx.user.id):
            st.lock(itx.user.id)  # Lock only if not already locked
        if st.p2_name.lower().startswith("wild "):
            mon = st._active(itx.user.id)
            species = (mon.species or "Pokémon").replace("-", " ").title() if mon else "Pokémon"
            emb = discord.Embed(
                title="You got away safely!",
                description=f"{species} fled the battle successfully!",
                color=0x5865F2,
            )
            await itx.response.send_message(embed=emb, ephemeral=response_ephemeral)
        else:
            await itx.response.send_message("🏳️ You forfeited the battle.", ephemeral=response_ephemeral)
        await view.on_done({"kind": "forfeit", "value": None}, itx)


class _BagLikeView(discord.ui.View):
    """Bag embed + Heal and Throw ball buttons (same content as /bag, buttons underneath)."""
    def __init__(self, move_view: "MoveView", is_wild: bool):
        super().__init__(timeout=60)
        self.move_view = move_view
        self.is_wild = is_wild
        heal_btn = discord.ui.Button(label="Heal", style=discord.ButtonStyle.success)
        heal_btn.callback = self._on_heal
        self.add_item(heal_btn)
        if is_wild:
            throw_btn = discord.ui.Button(label="Throw ball", style=discord.ButtonStyle.primary)
            throw_btn.callback = self._on_throw
            self.add_item(throw_btn)

    async def _on_heal(self, itx: discord.Interaction):
        view: MoveView = self.move_view
        st = view.state
        response_ephemeral = _battle_ui_ephemeral(st)
        if st.is_locked(itx.user.id):
            await itx.response.send_message(embed=_already_locked_embed(st.turn), ephemeral=response_ephemeral)
            return
        healing_items = await _fetch_user_items(itx.user.id, list(_HEALING_ITEMS.keys()))
        if not healing_items:
            return await itx.response.send_message("No healing items in your bag.", ephemeral=response_ephemeral)
        menu = _BagAllItemsView(view, healing_items, None, False)
        await itx.response.send_message("Choose an item to heal with:", ephemeral=response_ephemeral, view=menu)

    async def _on_throw(self, itx: discord.Interaction):
        view: MoveView = self.move_view
        st = view.state
        response_ephemeral = _battle_ui_ephemeral(st)
        if st.is_locked(itx.user.id):
            await itx.response.send_message(embed=_already_locked_embed(st.turn), ephemeral=response_ephemeral)
            return
        if not st.p2_name.lower().startswith("wild "):
            return await itx.response.send_message("You can't throw Poké Balls at a trainer's Pokémon.", ephemeral=response_ephemeral)
        ball_items = await _fetch_user_items(itx.user.id, list(_BALLS_BASIC.keys()))
        if not ball_items:
            return await itx.response.send_message("No Poké Balls in your bag.", ephemeral=response_ephemeral)
        menu = _BagAllItemsView(view, {}, ball_items, True)
        await itx.response.send_message("Choose a ball to throw:", ephemeral=response_ephemeral, view=menu)


class _BagButton(discord.ui.Button):
    def __init__(self, move_view: "MoveView"):
        super().__init__(label="Bag", style=discord.ButtonStyle.primary)
        self.move_view = move_view

    async def callback(self, itx: discord.Interaction):
        view: MoveView = self.view  # type: ignore
        st = view.state
        response_ephemeral = _battle_ui_ephemeral(st)
        if view.state.is_locked(itx.user.id):
            await itx.response.send_message(embed=_already_locked_embed(view.state.turn), ephemeral=response_ephemeral)
            return
        builder = getattr(st, "_bag_embed_builder", None)
        if builder is not None:
            try:
                embed, files = await builder(1)
                bag_view = _BagLikeView(self.move_view, st.p2_name.lower().startswith("wild "))
                try:
                    await itx.response.send_message(embed=embed, view=bag_view, files=files or [], ephemeral=response_ephemeral)
                finally:
                    if files:
                        for f in files:
                            try:
                                f.close()
                            except Exception:
                                pass
            except Exception as e:
                print(f"[PvP] Bag embed builder error: {e}")
                builder = None
        if builder is None:
            healing_items = await _fetch_user_items(itx.user.id, list(_HEALING_ITEMS.keys()))
            is_wild = st.p2_name.lower().startswith("wild ")
            ball_items: Optional[dict[str, int]] = await _fetch_user_items(itx.user.id, list(_BALLS_BASIC.keys())) if is_wild else None
            if not healing_items and not (is_wild and ball_items):
                msg = "No healing items or Poké Balls in your bag." if is_wild else "No healing items in your bag."
                return await itx.response.send_message(msg, ephemeral=response_ephemeral)
            menu = _BagAllItemsView(self.move_view, healing_items, ball_items if is_wild else None, is_wild)
            await itx.response.send_message("📦 Your bag:", ephemeral=response_ephemeral, view=menu)


class _BagAllItemsView(discord.ui.View):
    """Single bag view: healing items and (if wild) balls as dropdowns."""

    def __init__(self, move_view: "MoveView", healing_items: dict[str, int], ball_items: Optional[dict[str, int]], is_wild: bool):
        super().__init__(timeout=60)
        self.move_view = move_view
        self.is_wild = is_wild
        if healing_items:
            options = [discord.SelectOption(label=f"{k.replace('_', ' ').title()} (x{qty})", value=k) for k, qty in healing_items.items()]
            sel = discord.ui.Select(placeholder="Heal with...", options=options[:25], custom_id="bag_heal")
            sel.callback = self._on_heal_select
            self.add_item(sel)
        if is_wild and ball_items:
            options = [discord.SelectOption(label=f"{k.replace('_', ' ').title()} (x{qty})", value=k) for k, qty in ball_items.items()]
            sel = discord.ui.Select(placeholder="Throw ball...", options=options[:25], custom_id="bag_throw")
            sel.callback = self._on_throw_select
            self.add_item(sel)

    async def _on_heal_select(self, itx: discord.Interaction):
        mv = self.move_view
        st = mv.state
        response_ephemeral = _battle_ui_ephemeral(st)
        if st.is_locked(itx.user.id):
            await itx.response.send_message(embed=_already_locked_embed(st.turn), ephemeral=response_ephemeral)
            return
        item_key = (itx.data or {}).get("values", [None])[0]  # type: ignore
        if not item_key:
            return await itx.response.send_message("Invalid selection.", ephemeral=response_ephemeral)
        await itx.response.defer(ephemeral=response_ephemeral, thinking=False)
        st.lock(itx.user.id)
        heal_amt = _heal_amount_for_item(item_key)
        mon = st._active(itx.user.id)
        if not mon:
            return await itx.followup.send("No active Pokémon.", ephemeral=response_ephemeral)
        from .engine import _calc_hp
        current_max = _calc_hp(mon.base["hp"], mon.ivs["hp"], mon.evs["hp"], mon.level)
        if (mon.species or "").strip().lower() == "shedinja":
            current_max = 1
        mon.max_hp = current_max
        before = mon.hp
        target = mon.max_hp if heal_amt is None else min(mon.max_hp, mon.hp + heal_amt)
        mon.hp = target
        await _consume_item(itx.user.id, item_key, 1)
        if heal_amt is None and "full" in item_key.lower() and "restore" in item_key.lower():
            mon.status = None
        await mv.on_done({"kind": "heal", "value": {"item": item_key, "healed": target - before}}, itx)

    async def _on_throw_select(self, itx: discord.Interaction):
        mv = self.move_view
        st = mv.state
        response_ephemeral = _battle_ui_ephemeral(st)
        if st.is_locked(itx.user.id):
            await itx.response.send_message(embed=_already_locked_embed(st.turn), ephemeral=response_ephemeral)
            return
        if not st.p2_name.lower().startswith("wild "):
            return await itx.response.send_message("You can't throw Poké Balls at a trainer's Pokémon.", ephemeral=response_ephemeral)
        ball_key = (itx.data or {}).get("values", [None])[0]  # type: ignore
        if not ball_key:
            return await itx.response.send_message("Invalid selection.", ephemeral=response_ephemeral)
        st._last_throw_ball = ball_key
        st._last_throw_uid = itx.user.id
        await itx.response.defer(ephemeral=response_ephemeral, thinking=False)
        st.lock(itx.user.id)
        await _consume_item(itx.user.id, ball_key, 1)
        await mv.on_done({"kind": "throw", "value": {"ball": ball_key}}, itx)


async def _fetch_user_items(user_id: int, wanted: list[str]) -> dict:
    """Fetch items from bag, merging quantities by canonical ID (timer_ball + timer-ball -> one entry)."""
    wanted_norm: dict[str, str] = {}
    for w in wanted:
        n = _normalize_item(w)
        wanted_norm[n] = w
        wanted_norm[n.replace(" ", "")] = w
    # merged: norm_key -> (item_id_for_consume, total_qty) - prefer item_id with higher qty for _consume_item
    merged: dict[str, tuple[str, int, int]] = {}  # norm -> (best_item_id, best_single_qty, total_qty)
    try:
        import lib.db as db
    except ImportError:
        return {}
    async with db.session() as conn:
        cur = await conn.execute(
            "SELECT item_id, qty FROM user_items WHERE owner_id=? AND qty>0",
            (str(user_id),),
        )
        rows = await cur.fetchall()
        await cur.close()
        for row in rows:
            name = _normalize_item(row["item_id"])
            if name in wanted_norm or name.replace(" ", "") in wanted_norm:
                qty = int(row["qty"] or 0)
                item_id = str(row["item_id"] or "")
                if name not in merged:
                    merged[name] = (item_id, qty, qty)
                else:
                    _, _, tot = merged[name]
                    # Prefer item_id from row with higher qty for _consume_item (consume from fullest stack)
                    prev_id, prev_single, _ = merged[name]
                    best_id = item_id if qty > prev_single else prev_id
                    best_single = max(qty, prev_single)
                    merged[name] = (best_id, best_single, tot + qty)
    return {item_id: total for _k, (item_id, _single, total) in merged.items()}


class _HealSelectView(discord.ui.View):
    def __init__(self, move_view: "MoveView", items: dict[str, int]):
        super().__init__(timeout=60)
        self.move_view = move_view
        for key, qty in items.items():
            label = f"{key.title()} (x{qty})"
            btn = discord.ui.Button(label=label, style=discord.ButtonStyle.success)
            btn.callback = self._make_cb(key)
            self.add_item(btn)

    def _make_cb(self, item_key: str):
        async def _cb(itx: discord.Interaction):
            mv = self.move_view
            st = mv.state
            response_ephemeral = _battle_ui_ephemeral(st)
            if st.is_locked(itx.user.id):
                await itx.response.send_message(embed=_already_locked_embed(st.turn), ephemeral=response_ephemeral)
                return
            await itx.response.defer(ephemeral=response_ephemeral, thinking=False)
            st.lock(itx.user.id)
            heal_amt = _heal_amount_for_item(item_key)
            mon = st._active(itx.user.id)
            if not mon:
                return await itx.followup.send("No active Pokémon.", ephemeral=response_ephemeral)
            # Recalculate current max HP from level and stats so heal uses up-to-date max (e.g. after level-up)
            from .engine import _calc_hp
            current_max = _calc_hp(mon.base["hp"], mon.ivs["hp"], mon.evs["hp"], mon.level)
            if (mon.species or "").strip().lower() == "shedinja":
                current_max = 1
            mon.max_hp = current_max
            before = mon.hp
            target = mon.max_hp if heal_amt is None else min(mon.max_hp, mon.hp + heal_amt)
            mon.hp = target
            # Consume item from DB
            await _consume_item(itx.user.id, item_key, 1)
            # Clear status if Full Restore
            if heal_amt is None and "full" in item_key.lower() and "restore" in item_key.lower():
                mon.status = None
            await mv.on_done({"kind": "heal", "value": {"item": item_key, "healed": target - before}}, itx)
        return _cb


class _BallSelectView(discord.ui.View):
    def __init__(self, move_view: "MoveView", items: dict[str, int]):
        super().__init__(timeout=60)
        self.move_view = move_view
        for key, qty in items.items():
            label = f"{key.title()} (x{qty})"
            btn = discord.ui.Button(label=label, style=discord.ButtonStyle.primary)
            btn.callback = self._make_cb(key)
            self.add_item(btn)

    def _make_cb(self, ball_key: str):
        async def _cb(itx: discord.Interaction):
            mv = self.move_view
            st = mv.state
            response_ephemeral = _battle_ui_ephemeral(st)
            if st.is_locked(itx.user.id):
                await itx.response.send_message(embed=_already_locked_embed(st.turn), ephemeral=response_ephemeral)
                return
            if not st.p2_name.lower().startswith("wild "):
                return await itx.response.send_message("You can't throw Poké Balls at a trainer’s Pokémon.", ephemeral=response_ephemeral)
            st._last_throw_ball = ball_key
            st._last_throw_uid = itx.user.id
            await itx.response.defer(ephemeral=response_ephemeral, thinking=False)
            st.lock(itx.user.id)
            await _consume_item(itx.user.id, ball_key, 1)
            await mv.on_done({"kind": "throw", "value": {"ball": ball_key}}, itx)
        return _cb


async def _consume_item(user_id: int, item_key: str, amount: int = 1):
    """Consume amount of item from user's bag. item_key should be the actual item_id (e.g. poke_ball)."""
    try:
        import lib.db as db
    except ImportError:
        return
    async with db.session() as conn:
        # Match item_id (case-insensitive; user selection now passes actual item_id from _fetch_user_items)
        await conn.execute(
            "UPDATE user_items SET qty = GREATEST(0, qty - ?) WHERE owner_id=? AND LOWER(item_id)=LOWER(?) AND qty>=?",
            (amount, str(user_id), item_key, amount),
        )
        await conn.commit()
        db.invalidate_bag_cache(str(user_id))

# =========================  TURN PANELS & FLOW (no thread)  =========================

async def _get_exp_pct_for_mon(exp: Optional[int], exp_group: str, level: int) -> Optional[float]:
    """Return EXP bar fill fraction 0.0–1.0 from exp_requirements (Gen III+). None if no exp or level 100."""
    if exp is None or level >= 100:
        return 1.0 if level >= 100 else None
    try:
        import lib.db as db
    except ImportError:
        return None
    key = exp_group.strip().lower().replace(" ", "_")
    if _lib_db_cache and getattr(_lib_db_cache, "get_cached_exp_requirements", None):
        try:
            rows = _lib_db_cache.get_cached_exp_requirements()
            if rows:
                exp_at_level = exp_at_next = None
                for r in rows:
                    g = str(r.get("group_code") or "").strip().lower().replace(" ", "_")
                    if g != key:
                        continue
                    lvl = int(r.get("level") or 0)
                    total = int(r.get("exp_total") or 0)
                    if lvl == level:
                        exp_at_level = total
                    if lvl == level + 1:
                        exp_at_next = total
                if exp_at_level is not None and exp_at_next is not None and exp_at_next > exp_at_level:
                    pct = (int(exp) - exp_at_level) / (exp_at_next - exp_at_level)
                    return max(0.0, min(1.0, pct))
                if exp_at_level is not None and exp_at_next is not None:
                    return 1.0
                return None
        except Exception:
            pass
    try:
        async with db.session() as conn:
            cur = await conn.execute(
                "SELECT exp_total FROM exp_requirements WHERE group_code = ? AND level = ?",
                (key, level),
            )
            cur_at = await cur.fetchone()
            await cur.close()
            cur = await conn.execute(
                "SELECT exp_total FROM exp_requirements WHERE group_code = ? AND level = ?",
                (key, level + 1),
            )
            cur_next = await cur.fetchone()
            await cur.close()
        if not cur_at or cur_next is None:
            return None
        exp_at_level = int(cur_at["exp_total"])
        exp_at_next = int(cur_next["exp_total"])
        if exp_at_next <= exp_at_level:
            return 1.0
        pct = (int(exp) - exp_at_level) / (exp_at_next - exp_at_level)
        return max(0.0, min(1.0, pct))
    except Exception:
        return None


def _normalize_gender_for_display(gender: Optional[str]) -> Optional[str]:
    """Return 'male', 'female', or None (genderless) for renderer gender icon."""
    if not gender:
        return None
    g = str(gender).strip().lower()
    if g in ("male", "m"):
        return "male"
    if g in ("female", "f"):
        return "female"
    return None


def _resolve_fallback_sprite_path(
    species: str,
    *,
    gen: int,
    perspective: str,
    shiny: bool,
    female: bool,
    form: Optional[str] = None,
) -> Optional[Path]:
    """
    Resolve a best-effort sprite path for static fallback panel rendering.
    Prefers normal sprite lookup, then explicit icon.png fallback.
    """
    try:
        from .sprites import find_sprite, BASE_SPRITES_DIR, _norm_species
    except Exception:
        return None

    # Try standard lookup first (static preferred to avoid GIF decode cost).
    try:
        p = find_sprite(
            species,
            gen=gen,
            perspective=perspective,
            shiny=shiny,
            female=female,
            prefer_animated=False,
            form=form,
        )
        if p is not None:
            pp = Path(p)
            if pp.exists() and pp.stat().st_size > 0:
                return pp
    except Exception:
        pass
    try:
        p = find_sprite(
            species,
            gen=gen,
            perspective=perspective,
            shiny=shiny,
            female=female,
            prefer_animated=True,
            form=form,
        )
        if p is not None:
            pp = Path(p)
            if pp.exists() and pp.stat().st_size > 0:
                return pp
    except Exception:
        pass

    # Hard fallback to icon.png in form/base folder.
    try:
        base_species = _norm_species(species)
        cands: List[Path] = []
        if form:
            norm_form = _norm_species(form)
            if norm_form.startswith(f"{base_species}-"):
                folder = norm_form
            else:
                folder = f"{base_species}-{norm_form}"
            cands.append(BASE_SPRITES_DIR / folder / "icon.png")
        cands.append(BASE_SPRITES_DIR / base_species / "icon.png")
        for c in cands:
            if c.exists() and c.stat().st_size > 0:
                return c
    except Exception:
        pass
    return None


def _fallback_static_panel_file(
    st: "BattleState",
    for_user_id: int,
    *,
    hide_hp_text: bool = False,
    filename_prefix: str = "battle-panel",
) -> Optional[discord.File]:
    """
    Last-resort static image for player/stream panels when GIF rendering fails.
    Prevents text-only battles when animated/front-back assets are unavailable.
    """
    if _PILImage is None or _PILImageDraw is None:
        return None
    me = st._active(for_user_id)
    opp = st._opp_active(for_user_id)
    if me is None or opp is None:
        return None

    try:
        W, H = 512, 384
        img = _PILImage.new("RGBA", (W, H), (55, 68, 88, 255))
        draw = _PILImageDraw.Draw(img)
        # Simple arena fallback background.
        draw.rectangle((0, 0, W, int(H * 0.56)), fill=(86, 90, 103, 255))
        draw.rectangle((0, int(H * 0.56), W, H), fill=(196, 171, 134, 255))
        draw.ellipse((W // 2 - 90, int(H * 0.56) - 30, W // 2 + 90, int(H * 0.56) + 26), fill=(228, 206, 164, 255))

        # Resolve display species/forms similarly to panel render path.
        my_species = getattr(me, "_illusion_species", me.species) if getattr(me, "_illusion_active", False) else me.species
        opp_species = getattr(opp, "_illusion_species", opp.species) if getattr(opp, "_illusion_active", False) else opp.species
        my_form = getattr(me, "_illusion_form", None) if getattr(me, "_illusion_active", False) else getattr(me, "form", None)
        opp_form = getattr(opp, "_illusion_form", None) if getattr(opp, "_illusion_active", False) else getattr(opp, "form", None)

        my_path = _resolve_fallback_sprite_path(
            my_species,
            gen=st.gen,
            perspective="back",
            shiny=bool(getattr(me, "shiny", False)),
            female=(getattr(me, "gender", None) == "F"),
            form=my_form,
        )
        opp_path = _resolve_fallback_sprite_path(
            opp_species,
            gen=st.gen,
            perspective="front",
            shiny=bool(getattr(opp, "shiny", False)),
            female=(getattr(opp, "gender", None) == "F"),
            form=opp_form,
        )

        def _load_sprite(path: Optional[Path], max_size: tuple[int, int]) -> Optional[Any]:
            if path is None:
                return None
            try:
                src = _PILImage.open(str(path))
                if bool(getattr(src, "is_animated", False)):
                    try:
                        src.seek(0)
                    except Exception:
                        pass
                spr = src.convert("RGBA")
                try:
                    res = _PILImage.Resampling.NEAREST
                except Exception:
                    res = _PILImage.NEAREST
                # Upscale tiny icon sprites so fallback panel still shows visible mons.
                w, h = spr.size
                if w > 0 and h > 0:
                    max_w = max(1, int(max_size[0]))
                    max_h = max(1, int(max_size[1]))
                    scale = min(max_w / float(w), max_h / float(h))
                    if scale != 1.0:
                        nw = max(1, int(round(w * scale)))
                        nh = max(1, int(round(h * scale)))
                        spr = spr.resize((nw, nh), resample=res)
                return spr
            except Exception:
                return None

        my_sprite = _load_sprite(my_path, (176, 176))
        opp_sprite = _load_sprite(opp_path, (156, 156))

        if my_sprite is not None:
            mx = max(12, int(W * 0.12))
            my = max(120, int(H * 0.52) - my_sprite.height // 2)
            img.alpha_composite(my_sprite, dest=(mx, my))
        if opp_sprite is not None:
            ox = min(W - opp_sprite.width - 14, int(W * 0.66))
            oy = max(52, int(H * 0.22) - opp_sprite.height // 2)
            img.alpha_composite(opp_sprite, dest=(ox, oy))

        def _hp_pct(mon: Any) -> float:
            try:
                return max(0.0, min(1.0, float(mon.hp) / max(1.0, float(mon.max_hp))))
            except Exception:
                return 0.0

        def _hp_bar(x: int, y: int, pct: float, color: tuple[int, int, int, int]) -> None:
            draw.rectangle((x, y, x + 150, y + 12), fill=(45, 45, 45, 230))
            draw.rectangle((x + 1, y + 1, x + 149, y + 11), fill=(190, 190, 190, 210))
            fill_w = max(0, min(148, int(round(148 * pct))))
            if fill_w > 0:
                draw.rectangle((x + 1, y + 1, x + 1 + fill_w, y + 11), fill=color)

        me_name = _format_pokemon_name(me)
        opp_name = _format_pokemon_name(opp)
        draw.text((18, H - 58), me_name, fill=(241, 241, 241, 255))
        draw.text((W - 180, 18), opp_name, fill=(241, 241, 241, 255))
        _hp_bar(18, H - 40, _hp_pct(me), (95, 198, 94, 255))
        _hp_bar(W - 180, 36, _hp_pct(opp), (95, 198, 94, 255))
        if not hide_hp_text:
            try:
                draw.text((18, H - 24), f"{int(me.hp)}/{int(me.max_hp)}", fill=(230, 230, 230, 255))
                draw.text((W - 180, 50), f"{int(opp.hp)}/{int(opp.max_hp)}", fill=(230, 230, 230, 255))
            except Exception:
                pass

        buf = BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        pov = "p1" if for_user_id == st.p1_id else "p2"
        return discord.File(buf, filename=f"{filename_prefix}_{int(st.turn)}_{pov}.png")
    except Exception:
        return None


async def _render_gif_for_panel(st: BattleState, for_user_id: int, hide_hp_text: bool = False) -> Optional[Tuple[discord.File, 'Path']]:
    """Render GIF for a player panel and return (discord.File, Path). Returns None if rendering fails.
    The Path is returned so the caller can delete it after sending to Discord."""
    if not render_turn_gif:
        return None
    
    import traceback
    try:
        import asyncio
        from pathlib import Path
        me = st._active(for_user_id)
        opp = st._opp_active(for_user_id)
        if not me or not opp:
            return None
        pov = "p1" if for_user_id == st.p1_id else "p2"

        # Count alive Pokémon on each team
        my_team = st.team_for(for_user_id)
        opp_team = st.team_for(st.p2_id if for_user_id == st.p1_id else st.p1_id)
        is_wild_opponent = (st.p2_name or "").lower().startswith("wild ") if for_user_id == st.p1_id else (st.p1_name or "").lower().startswith("wild ")
        my_team_alive = sum(1 for m in my_team if m and m.hp > 0)
        opp_team_alive = sum(1 for m in opp_team if m and m.hp > 0) if not is_wild_opponent else 0
        
        # Get display species and forms (accounting for Illusion, Mega Evolution, and Gigantamax)
        my_display_species = getattr(me, '_illusion_species', me.species) if getattr(me, '_illusion_active', False) else me.species
        # Only use mega form if actually mega evolved, otherwise use original form
        if getattr(me, '_illusion_active', False):
            my_base_form = getattr(me, '_illusion_form', None)
        elif getattr(me, 'mega_evolved', False):
            my_base_form = getattr(me, "form", None)  # Use mega form
        else:
            # Not mega evolved - use original form, but skip if current form is a mega form
            current_form = getattr(me, "form", None)
            if current_form and "mega" in str(current_form).lower():
                # Form is set to mega form but hasn't mega evolved - use original or None
                my_base_form = getattr(me, '_mega_original_form', None)
            else:
                # For dynamic form changes (like Schooling), prioritize current form over original
                # Only use _mega_original_form if current_form is None
                my_base_form = current_form if current_form is not None else getattr(me, '_mega_original_form', None)
        if getattr(me, 'is_gigantamax', False) and getattr(me, 'dynamaxed', False):
            my_display_form = "gmax" if not my_base_form else f"{my_base_form}-gmax"
        else:
            my_display_form = my_base_form
        
        opp_display_species = getattr(opp, '_illusion_species', opp.species) if getattr(opp, '_illusion_active', False) else opp.species
        # Only use mega form if actually mega evolved, otherwise use original form
        if getattr(opp, '_illusion_active', False):
            opp_base_form = getattr(opp, '_illusion_form', None)
        elif getattr(opp, 'mega_evolved', False):
            opp_base_form = getattr(opp, "form", None)  # Use mega form
        else:
            # Not mega evolved - use original form, but skip if current form is a mega form
            current_form = getattr(opp, "form", None)
            if current_form and "mega" in str(current_form).lower():
                # Form is set to mega form but hasn't mega evolved - use original or None
                opp_base_form = getattr(opp, '_mega_original_form', None)
            else:
                # For dynamic form changes (like Schooling), prioritize current form over original
                # Only use _mega_original_form if current_form is None
                opp_base_form = current_form if current_form is not None else getattr(opp, '_mega_original_form', None)
        if getattr(opp, 'is_gigantamax', False) and getattr(opp, 'dynamaxed', False):
            opp_display_form = "gmax" if not opp_base_form else f"{opp_base_form}-gmax"
        else:
            opp_display_form = opp_base_form
        
        # Check for Substitute
        my_has_sub = bool(getattr(me, 'substitute', None))
        opp_has_sub = bool(getattr(opp, 'substitute', None))
        
        # Get status conditions
        my_status = getattr(me, 'status', None)
        opp_status = getattr(opp, 'status', None)
        
        # Get status conditions for all party members (for Pokéball colors)
        my_team_statuses = [getattr(m, 'status', None) if m else None for m in my_team]
        opp_team_statuses = [getattr(m, 'status', None) if m else None for m in opp_team]
        
        # Get HP values for all party members (for Pokéball colors - grey when fainted)
        my_team_hp = [(getattr(m, 'hp', 0), getattr(m, 'max_hp', 0)) if m else (0, 0) for m in my_team]
        opp_team_hp = [(getattr(m, 'hp', 0), getattr(m, 'max_hp', 0)) if m else (0, 0) for m in opp_team]
        
        # Get transformation states
        my_mega_evolved = bool(getattr(me, 'mega_evolved', False))
        my_dynamaxed = bool(getattr(me, 'dynamaxed', False))
        my_primal_reversion = None
        # Check for Primal Reversion by form or species name
        if getattr(me, 'form', None) == "primal" or "primal" in me.species.lower():
            # Check if it's Groudon or Kyogre
            if "groudon" in me.species.lower():
                my_primal_reversion = "Groudon"
            elif "kyogre" in me.species.lower():
                my_primal_reversion = "Kyogre"
        
        opp_mega_evolved = bool(getattr(opp, 'mega_evolved', False))
        opp_dynamaxed = bool(getattr(opp, 'dynamaxed', False))
        opp_primal_reversion = None
        # Check for Primal Reversion by form or species name
        if getattr(opp, 'form', None) == "primal" or "primal" in opp.species.lower():
            # Check if it's Groudon or Kyogre
            if "groudon" in opp.species.lower():
                opp_primal_reversion = "Groudon"
            elif "kyogre" in opp.species.lower():
                opp_primal_reversion = "Kyogre"
        
        # Check if Nullscape is active (only check ACTIVE Pokemon on the field, not all in party)
        nullscape_active = False
        from .engine import _get_nullscape_type
        # _get_nullscape_type with battle_state only checks active Pokemon
        nullscape_type_check = _get_nullscape_type(None, st)
        if nullscape_type_check:
            nullscape_active = True
        
        bg_key = getattr(st, "fmt_key", None)
        # EXP bar: fraction 0.0–1.0 for current level (Gen III+ exp_requirements)
        my_exp_pct = await _get_exp_pct_for_mon(
            getattr(me, "_exp", None),
            getattr(me, "_exp_group", "medium_fast"),
            me.level,
        )
        # Run GIF rendering in thread pool
        gif = await asyncio.to_thread(
            render_turn_gif,
            battle_id=f"{st.p1_id}_{st.p2_id}", 
            turn=st.turn, 
            pov=pov,
            gen=st.gen, 
            my_species=my_display_species, 
            my_shiny=bool(getattr(me, "shiny", False)),
            my_female=(me.gender == "F"),
            my_level=me.level,
            my_hp_current=me.hp,
            my_hp_max=me.max_hp,
            my_team_alive=my_team_alive,
            my_team_total=len(my_team),
            my_form=my_display_form,
            my_has_substitute=my_has_sub,
            my_status=my_status,
            my_mega_evolved=my_mega_evolved,
            my_dynamaxed=my_dynamaxed,
            my_primal_reversion=my_primal_reversion,
            opp_species=opp_display_species,
            opp_shiny=bool(getattr(opp, "shiny", False)),
            opp_female=(opp.gender == "F"),
            opp_level=opp.level,
            opp_hp_current=opp.hp,
            opp_hp_max=opp.max_hp,
            opp_team_alive=opp_team_alive,
            opp_team_total=0 if is_wild_opponent else len(opp_team),
            opp_form=opp_display_form,
            opp_has_substitute=opp_has_sub,
            opp_status=opp_status,
            opp_mega_evolved=opp_mega_evolved,
            opp_dynamaxed=opp_dynamaxed,
            opp_primal_reversion=opp_primal_reversion,
            opp_gender=_normalize_gender_for_display(getattr(opp, "gender", None)),
            hide_hp_text=hide_hp_text,
            nullscape_active=nullscape_active,
            my_team_statuses=my_team_statuses,
            opp_team_statuses=[] if is_wild_opponent else opp_team_statuses,
            my_team_hp=my_team_hp,
            opp_team_hp=[] if is_wild_opponent else opp_team_hp,
            bg_key=bg_key,
            my_exp_pct=my_exp_pct,
        )
        if gif:
            # render_turn_gif returns an in-memory BytesIO buffer (preferred)
            gif_path = None
            if isinstance(gif, BytesIO):
                filename = f"turn{st.turn}_{pov}.gif"
                file_obj = discord.File(gif, filename=filename)
                return (file_obj, None)
            if isinstance(gif, (bytes, bytearray)):
                filename = f"turn{st.turn}_{pov}.gif"
                file_obj = discord.File(BytesIO(gif), filename=filename)
                return (file_obj, None)
            if isinstance(gif, Path) and gif.exists():
                gif_path = gif
            elif hasattr(gif, 'exists') and gif.exists():
                # Fallback: try to convert to Path
                gif_path = Path(gif) if isinstance(gif, (str, Path)) else Path(gif.name) if hasattr(gif, 'name') else None
            
            # Ensure the file has .gif extension and return as tuple
            if gif_path and gif_path.exists():
                # Make sure filename has .gif extension
                filename = gif_path.name
                if not filename.lower().endswith('.gif'):
                    filename = f"{gif_path.stem}.gif"
                # Open file and return both File object and path
                file_obj = discord.File(gif_path, filename=filename)
                return (file_obj, gif_path)
    except Exception as e:
        traceback.print_exc()
        print(f"[Panel] _render_gif_for_panel failed: {e}")
    return None

async def _send_stream_panel(
    channel: discord.TextChannel,
    st: BattleState,
    turn_summary: Optional[str] = None,
    gif_file: Optional[Any] = None,
    force_no_summary: bool = False,
):
    """Send or update the stream panel (P1 view, no buttons)"""
    def _safe_int(v: Any, default: int) -> int:
        try:
            return int(v)
        except Exception:
            return int(default)

    turn_no = 0
    try:
        turn_no = int(getattr(st, "turn", 0) or 0)
    except Exception:
        turn_no = 0
    turn_label = max(1, turn_no - 1) if turn_no > 0 else 1

    summary_text = ""
    if not force_no_summary:
        # Prefer per-turn summary payload, fallback to cached turn log.
        summary_text = str(turn_summary or "").strip()
        if not summary_text:
            try:
                cached_lines = [
                    str(line).strip()
                    for line in (getattr(st, "_last_turn_log", []) or [])
                    if str(line).strip()
                ]
                if cached_lines:
                    summary_text = "\n".join(cached_lines).strip()
            except Exception:
                summary_text = ""
        if len(summary_text) > 3000:
            summary_text = "...\n" + summary_text[-2800:]
        if not summary_text:
            summary_text = "No significant actions this turn."

    # Get active Pokémon for title formatting.
    p1_active = st._active(st.p1_id)
    p2_active = st._active(st.p2_id)
    p1_display = _format_pokemon_name(p1_active) if p1_active else "Pokémon"
    p2_display = _format_pokemon_name(p2_active) if p2_active else "Pokémon"

    if force_no_summary:
        embed = discord.Embed(
            title="⚔️ Battle Stream Started",
            description=f"Turn {turn_label} • {getattr(st, 'fmt_label', 'Battle')} (Gen {getattr(st, 'gen', '?')})",
            color=discord.Color.purple(),
        )
    else:
        embed = discord.Embed(
            title=f"⚔️ Turn {turn_label} Summary",
            description=summary_text if summary_text else "No significant actions this turn.",
            color=discord.Color.blurple(),
        )

        # Keep stream public-safe: include status rows but hide HP values/bars.
        embed.add_field(
            name=f"Your {p1_display}",
            value="HP hidden on stream",
            inline=False,
        )
        embed.add_field(
            name=f"Opponent's {p2_display}",
            value="HP hidden on stream",
            inline=False,
        )

        field_text = _field_conditions_text(st.field)
        if field_text:
            embed.add_field(name="🌍 Field Conditions", value=field_text, inline=False)
    
    # Handle gif_file - it might be:
    # - (discord.File, Path)  (preferred; caller rendered already)
    # - discord.File
    # - Path/str (legacy)
    file = None
    gif_path_to_cleanup: Optional[Path] = None

    if gif_file:
        if isinstance(gif_file, tuple) and len(gif_file) == 2:
            # New format: (discord.File, Path)
            file, gif_path_to_cleanup = gif_file
        elif isinstance(gif_file, discord.File):
            # Already a discord.File, use it directly
            file = gif_file
        elif isinstance(gif_file, (Path, str)):
            file_path = Path(gif_file)
            if file_path.exists():
                # Ensure filename has .gif extension
                filename = file_path.name
                if not filename.lower().endswith('.gif'):
                    filename = f"{file_path.stem}.gif"
                file = discord.File(file_path, filename=filename)
                gif_path_to_cleanup = file_path
    if not file and render_turn_gif:
        # Render with hide_hp_text=True for streaming (always hide HP)
        render_result = await _render_gif_for_panel(st, st.p1_id, hide_hp_text=True)
        if render_result:
            # render_result is now a tuple: (discord.File, Path)
            file, gif_path_to_cleanup = render_result
    if not file:
        # Final fallback: static panel image so stream never becomes text-only.
        file = _fallback_static_panel_file(st, st.p1_id, hide_hp_text=True, filename_prefix="stream-panel")
    
    if file:
        embed.set_image(url=f"attachment://{file.filename}")
    
    # Ensure embed has content (Discord requires at least embed or file)
    if not embed.title and not embed.description and not embed.fields and not embed.image:
        embed.description = "Battle in progress..."
    
    # Final safety check: ensure we have at least embed or file
    if not embed.title and not embed.description and not embed.fields and not embed.image and not file:
        embed.description = "Battle in progress..."
    
    msg = None
    try:
        # Keep per-turn stream history: send one message each turn with
        # both image and turn-by-turn summary text (legacy behavior).
        send_kwargs: Dict[str, Any] = {"embed": embed}
        if file is not None:
            send_kwargs["file"] = file
            try:
                msg = await channel.send(**send_kwargs)
            except Exception as file_err:
                # Fallback to embed-only stream message if attachment upload fails.
                print(f"[Stream] Attachment send failed; retrying embed-only: {file_err}")
                send_kwargs.pop("file", None)
                msg = await channel.send(**send_kwargs)
        else:
            msg = await channel.send(**send_kwargs)
        return msg
    except Exception as e:
        print(f"[Stream] Error sending stream: {e}")
        try:
            fallback = f"📺 Stream update • Turn {getattr(st, 'turn', '?')} • {getattr(st, 'fmt_label', 'Battle')}"
            if summary_text and not force_no_summary:
                txt = str(summary_text).strip()
                if len(txt) > 1200:
                    txt = "...\n" + txt[-1000:]
                fallback += f"\n{txt}"
            return await channel.send(fallback)
        except Exception as fallback_err:
            print(f"[Stream] Text fallback failed: {fallback_err}")
        return None
    finally:
        # Close stream attachment and best-effort cleanup of legacy render path.
        if file is not None:
            try:
                file.close()
            except Exception:
                pass
        if gif_path_to_cleanup is not None:
            try:
                if gif_path_to_cleanup.exists():
                    gif_path_to_cleanup.unlink(missing_ok=True)
            except Exception:
                pass


async def _resolve_stream_channel(
    st: BattleState,
    p1_itx: Optional[discord.Interaction],
    p2_itx: Optional[discord.Interaction],
) -> Optional[Any]:
    """
    Resolve a stable channel object for stream posts.
    Prefers the channel captured at battle start, then interaction channels,
    then cache/fetch via stored channel ID.
    """
    ch = getattr(st, "stream_channel", None)
    if ch is not None and hasattr(ch, "send"):
        return ch

    for itx in (p1_itx, p2_itx):
        try:
            c = getattr(itx, "channel", None)
            if c is not None and hasattr(c, "send"):
                st.stream_channel = c
                st.stream_channel_id = getattr(c, "id", None)
                return c
        except Exception:
            continue

    channel_id = getattr(st, "stream_channel_id", None)
    if not channel_id:
        return None

    client = None
    for itx in (p1_itx, p2_itx):
        client = getattr(itx, "client", None)
        if client is not None:
            break
    if client is None:
        return None

    try:
        c = client.get_channel(int(channel_id))
        if c is not None and hasattr(c, "send"):
            st.stream_channel = c
            return c
    except Exception:
        pass

    try:
        c = await client.fetch_channel(int(channel_id))
        if c is not None and hasattr(c, "send"):
            st.stream_channel = c
            return c
    except Exception:
        pass
    return None


# Helper function to safely send messages that handles webhook token expiration
async def safe_send_message(itx: discord.Interaction, content: str = None, embed: discord.Embed = None, 
                           file: discord.File = None, ephemeral: bool = True, view: discord.ui.View = None):
    """
    Safely send a message via interaction, handling webhook token expiration.
    Interaction tokens expire after 15 minutes, so we fall back to channel.send() if expired.
    """
    if not itx or not hasattr(itx, 'user'):
        return None
    
    # Route/adventure wrappers can force public messages for this interaction.
    if ephemeral and bool(getattr(itx, "_force_public_battle_messages", False)):
        ephemeral = False

    # Check if interaction token is expired (15 minutes = 900 seconds)
    INTERACTION_TOKEN_EXPIRY = 900  # 15 minutes in seconds
    try:
        # Check if interaction was created more than 15 minutes ago
        # Discord interactions have a created_at timestamp
        if hasattr(itx, 'created_at'):
            from datetime import timezone
            age = (datetime.now(timezone.utc) - itx.created_at).total_seconds()
            is_expired = age > INTERACTION_TOKEN_EXPIRY
        else:
            # Fallback: assume expired if we can't determine age
            is_expired = False
        
        # Try to use followup if not expired
        if not is_expired and hasattr(itx, 'followup') and hasattr(itx.followup, 'send'):
            try:
                kwargs = {}
                if content:
                    kwargs['content'] = content
                if embed:
                    kwargs['embed'] = embed
                if file:
                    kwargs['file'] = file
                if view:
                    kwargs['view'] = view
                kwargs['ephemeral'] = ephemeral
                
                return await itx.followup.send(**kwargs)
            except (discord.errors.NotFound, discord.errors.HTTPException) as e:
                # Webhook expired (401 Unauthorized or 404 Not Found)
                error_str = str(e)
                if "401" in error_str or "50027" in error_str or "Unauthorized" in error_str or "Invalid Webhook Token" in error_str:
                    is_expired = True
                else:
                    raise
        
        # If expired or followup failed, use channel.send() with mention
        if is_expired and hasattr(itx, 'channel') and itx.channel:
            # Build message with mention
            message_parts = []
            if content:
                message_parts.append(content)
            elif embed:
                # For embeds, mention the user first
                message_parts.append(f"<@{itx.user.id}>")
            
            # Send via channel
            send_kwargs = {}
            if embed:
                send_kwargs['embed'] = embed
            if file:
                send_kwargs['file'] = file
            if view:
                send_kwargs['view'] = view
            
            if message_parts:
                send_kwargs['content'] = '\n'.join(message_parts)
            
            return await itx.channel.send(**send_kwargs)
        
    except Exception as e:
        # Log error but don't fail
        print(f"[PvP] Error sending message to {itx.user.id}: {e}")
        return None
    
    return None


async def _send_player_panel(itx: discord.Interaction, st: BattleState, for_user_id: int, view: Optional[discord.ui.View], gif_file: Optional[discord.File] = None, extra_lines: Optional[List[str]] = None):
    # Safety check: don't send panel without a view (user wouldn't be able to interact)
    if view is None:
        return
    
    me = st._active(for_user_id)
    opp = st._opp_active(for_user_id)
    
    # Build description (no HP bars/text - they're visible in the GIF)
    desc_parts = []
    fmt_label = st.fmt_label or "Battle"
    me_display = _format_pokemon_name(me)
    opp_display = _format_pokemon_name(opp)

    # Adventure-style richer text (Myuu-style: Vs. header, trainer challenge, Go!, abilities)
    # me_display/opp_display use _format_pokemon_name (★ for shiny) - same star as elsewhere in PvP
    if fmt_label.lower().startswith("adventure"):
        # Wild encounter: "A wild LvX Y appeared!" then "Go! [your mon]!" (shiny ★ in me_display)
        if st.p2_name.lower().startswith("wild "):
            desc_parts.append(f"A wild **Lv{opp.level} {opp_display}** appeared!")
            desc_parts.append(f"Go! **{me_display}**!")
            if extra_lines:
                # Filter out any perks/XP boost lines; keep ability activations etc.
                desc_parts.extend(
                    line for line in extra_lines
                    if line and "perks" not in line.lower() and "xp boost" not in line.lower() and "ribbon" not in line.lower()
                )
        else:
            # Trainer/rival: challenge line, optional quote, then Go! [player mon], then ability activations
            trainer_challenge = getattr(st, "trainer_challenge", None) or f"{st.p2_name} is ready to take on your challenge!"
            desc_parts.append(trainer_challenge)
            trainer_quote = getattr(st, "trainer_quote", None)
            if trainer_quote:
                desc_parts.append(f"*{trainer_quote}*")
            desc_parts.append(f"Go! **{me_display}**!")
            if extra_lines:
                desc_parts.extend(extra_lines)

        # Pre-battle aura/intimidate/Trace/etc messages (only if not already in extra_lines)
        if not extra_lines:
            pre_msgs = getattr(st, "_pre_battle_messages", []) or []
            if pre_msgs:
                formatted = [_format_log_line(msg, _build_species_display_map(st)) for msg in pre_msgs]
                desc_parts.append("\n".join(formatted))

        # Field conditions
        field_text = _field_conditions_text(st.field)
        if field_text:
            desc_parts.append(field_text)

        # Instruction line
        desc_parts.append("Click a move button or another option below to act.")

        # Title: "Pokémon Vs. Pokémon" (dynamic names in use)
        embed = discord.Embed(
            title=f"**{me_display}** Vs. **{opp_display}**",
            description="\n\n".join([p for p in desc_parts if p])
        )
    else:
        # Default compact description
        if extra_lines:
            desc_parts.extend(extra_lines)
        field_text = _field_conditions_text(st.field)
        if field_text:
            desc_parts.append(field_text)
        description_text = "\n".join(desc_parts) if desc_parts else "Battle in progress..."
        embed = discord.Embed(
            title=f"**{me_display}** vs **{opp_display}**",
            description=description_text
        )
    
    # Use provided GIF file or render if not provided (fallback)
    file = None
    gif_path_to_cleanup = None
    from pathlib import Path
    
    if gif_file:
        # gif_file might be a tuple (discord.File, Path) or legacy types
        if isinstance(gif_file, tuple) and len(gif_file) == 2:
            # New format: (discord.File, Path)
            file, gif_path_to_cleanup = gif_file
        elif isinstance(gif_file, discord.File):
            # Legacy: already a discord.File, use it directly
            file = gif_file
        elif isinstance(gif_file, (Path, str)):
            # Legacy: Path or string
            file_path = Path(gif_file)
            if file_path.exists():
                file = discord.File(file_path, filename=file_path.name)
                gif_path_to_cleanup = file_path
            else:
                # Debug: file path doesn't exist
                print(f"[Panel] Warning: GIF file path doesn't exist: {file_path}")
    
    if not file and render_turn_gif:
        render_result = await _render_gif_for_panel(st, for_user_id)
        if render_result:
            # render_result is now a tuple: (discord.File, Path)
            file, gif_path_to_cleanup = render_result
        else:
            # Debug: render returned None (rendering failed or disabled)
            if render_turn_gif is None:
                print(f"[Panel] Info: render_turn_gif is None (import failed or disabled)")
            else:
                print(f"[Panel] Info: _render_gif_for_panel returned None (rendering failed)")
    if not file:
        # Final fallback: static image so PvP panel still shows visual state.
        file = _fallback_static_panel_file(st, for_user_id, hide_hp_text=False, filename_prefix="battle-panel")
    
    # Set image in embed if we have a file
    if file:
        embed.set_image(url=f"attachment://{file.filename}")
    
    # Ensure embed has content (Discord requires at least embed or file)
    # If embed is empty (no title, description, fields, image), add a fallback
    if not embed.title and not embed.description and not embed.fields and not embed.image:
        embed.description = "Battle in progress..."
    
    # Route battles can opt into public (non-ephemeral) panels.
    # Only pass file and view if they're not None (Discord library tries to call to_dict() on None objects)
    send_kwargs = {"embed": embed, "ephemeral": (not _battle_ui_is_public(st))}
    if file is not None:
        send_kwargs["file"] = file
    if view is not None:
        send_kwargs["view"] = view
    
    # Final safety check: ensure we have at least embed or file
    if not embed.title and not embed.description and not embed.fields and not embed.image and not file:
        embed.description = "Battle in progress..."
    
    try:
        if not itx.response.is_done():
            await itx.response.send_message(**send_kwargs)
        else:
            await itx.followup.send(**send_kwargs)
    finally:
        # Close file handle only. Do not delete GIF here — cleanup at battle end via cleanup_battle_media.
        if file:
            try:
                file.close()
            except Exception:
                pass


async def _load_pp_state_for_user(st: BattleState, uid: int) -> None:
    """Hydrate in-battle PP from DB moves_pp for a single user."""
    if _lib_db is None or int(uid) <= 0:
        return
    team = st.team_for(uid)
    async with _lib_db.session() as conn:
        for mon in team:
            db_id = getattr(mon, "_db_id", None)
            if not db_id:
                continue
            try:
                cur = await conn.execute(
                    "SELECT moves, moves_pp, moves_pp_min, moves_pp_max FROM pokemons WHERE id=? LIMIT 1",
                    (int(db_id),),
                )
            except Exception:
                cur = await conn.execute(
                    "SELECT moves, moves_pp FROM pokemons WHERE id=? LIMIT 1",
                    (int(db_id),),
                )
            row = await cur.fetchone()
            await cur.close()
            if not row:
                continue
            try:
                moves = json.loads(row["moves"]) if row.get("moves") else []
            except Exception:
                moves = []
            raw_pp = row.get("moves_pp")
            raw_pp_min = row.get("moves_pp_min")
            raw_pp_max = row.get("moves_pp_max")
            st._ensure_pp_loaded(uid, mon)
            key = st._get_mon_key(uid, mon)
            if key not in st._pp:
                st._pp[key] = {}
            store = st._pp[key]
            if moves:
                move_keys = [_norm_pp_move_key(mv) for mv in moves]
                base_caps = [max(1, int(_base_pp(mv, generation=st.gen))) for mv in move_keys]
                global_caps = [_pp_global_max_for_move(mv, generation=st.gen) for mv in move_keys]
                max_caps = _pp_parse_list(raw_pp_max, count=len(move_keys), defaults=base_caps, lo=1, hi=999)
                min_caps = _pp_parse_list(raw_pp_min, count=len(move_keys), defaults=[0] * len(move_keys), lo=0, hi=999)
                # Missing current PP should start from base PP, not boosted max PP.
                pps = _pp_parse_list(raw_pp, count=len(move_keys), defaults=base_caps, lo=0, hi=999)
                for i in range(len(move_keys)):
                    max_caps[i] = max(base_caps[i], min(max_caps[i], global_caps[i]))
                    min_caps[i] = max(0, min(min_caps[i], max_caps[i]))
                    pps[i] = max(min_caps[i], min(pps[i], max_caps[i]))
                    # When moves_pp_max equals base (no PP Up), clamp loaded PP to at most base
                    if max_caps[i] <= base_caps[i]:
                        pps[i] = min(pps[i], base_caps[i])
                for mv, left_i in zip(moves, pps):
                    canonical = _canonical_move_name(mv)
                    store[canonical] = int(left_i)


async def _save_pp_state_for_user(st: BattleState, uid: int) -> None:
    """Persist in-battle PP back to DB moves_pp for a single user."""
    if _lib_db is None or int(uid) <= 0:
        return
    team = st.team_for(uid)
    async with _lib_db.session() as conn:
        for mon in team:
            db_id = getattr(mon, "_db_id", None)
            if not db_id:
                continue
            key = st._get_mon_key(uid, mon)
            pp_store = st._pp.get(key, {}) or {}
            norm_pp_store: Dict[str, int] = {}
            for raw_key, raw_val in pp_store.items():
                try:
                    norm_pp_store[_norm_pp_move_key(raw_key)] = int(raw_val)
                except Exception:
                    continue
            move_list = (mon.moves or [])[:4]
            row_d: Dict[str, Any] = {}
            try:
                cur = await conn.execute(
                    "SELECT moves_pp, moves_pp_min, moves_pp_max FROM pokemons WHERE id=? LIMIT 1",
                    (int(db_id),),
                )
                bounds_row = await cur.fetchone()
                await cur.close()
                if bounds_row:
                    row_d = dict(bounds_row) if hasattr(bounds_row, "keys") else {}
            except Exception:
                row_d = {}
            move_keys = [_norm_pp_move_key(mv) for mv in move_list]
            base_caps = [max(1, int(_base_pp(mv, generation=st.gen))) for mv in move_keys]
            global_caps = [_pp_global_max_for_move(mv, generation=st.gen) for mv in move_keys]
            max_caps = _pp_parse_list(row_d.get("moves_pp_max"), count=len(move_keys), defaults=base_caps, lo=1, hi=999)
            min_caps = _pp_parse_list(row_d.get("moves_pp_min"), count=len(move_keys), defaults=[0] * len(move_keys), lo=0, hi=999)
            stored_pps = _pp_parse_list(row_d.get("moves_pp"), count=len(move_keys), defaults=base_caps, lo=0, hi=999)
            for i in range(len(move_keys)):
                max_caps[i] = max(base_caps[i], min(max_caps[i], global_caps[i]))
                min_caps[i] = max(0, min(min_caps[i], max_caps[i]))
                stored_pps[i] = max(min_caps[i], min(stored_pps[i], max_caps[i]))
            moves_pp: List[int] = []
            for i, mv in enumerate(move_list):
                cap_i = max_caps[i] if i < len(max_caps) else _pp_global_max_for_move(mv, generation=st.gen)
                min_i = min_caps[i] if i < len(min_caps) else 0
                stored_i = stored_pps[i] if i < len(stored_pps) else max(1, int(_base_pp(mv, generation=st.gen)))
                canonical = _canonical_move_name(mv)
                left = pp_store.get(canonical) or pp_store.get(mv)
                if left is None:
                    left = pp_store.get(_norm_pp_move_key(mv))
                if left is None:
                    left = norm_pp_store.get(_norm_pp_move_key(mv))
                if left is None:
                    for raw_key, raw_val in (pp_store or {}).items():
                        if _canonical_move_name(raw_key) == canonical:
                            left = raw_val
                            break
                try:
                    left_i = int(left) if left is not None else int(stored_i)
                except Exception:
                    left_i = int(stored_i)
                # When max cap equals base (no PP Up), clamp to at most base
                base_i = base_caps[i] if i < len(base_caps) else max(1, int(_base_pp(mv, generation=st.gen)))
                if max_caps[i] <= base_i:
                    left_i = min(left_i, base_i)
                moves_pp.append(max(int(min_i), min(int(left_i), int(cap_i))))
            try:
                await conn.execute(
                    "UPDATE pokemons SET moves_pp=?, moves_pp_min=?, moves_pp_max=? WHERE id=?",
                    (
                        json.dumps(moves_pp, ensure_ascii=False),
                        json.dumps(min_caps, ensure_ascii=False),
                        json.dumps(max_caps, ensure_ascii=False),
                        int(db_id),
                    ),
                )
            except Exception:
                await conn.execute(
                    "UPDATE pokemons SET moves_pp=? WHERE id=?",
                    (json.dumps(moves_pp, ensure_ascii=False), int(db_id)),
                )
        await conn.commit()
    try:
        _lib_db.invalidate_pokemons_cache(str(uid))
    except Exception:
        pass


async def _load_pp_state_for_battle(st: BattleState) -> None:
    for uid in (st.p1_id, st.p2_id):
        await _load_pp_state_for_user(st, uid)


async def _save_pp_state_for_battle(st: BattleState) -> None:
    for uid in (st.p1_id, st.p2_id):
        await _save_pp_state_for_user(st, uid)

async def _finish(st: BattleState, p1_itx: discord.Interaction, p2_itx: discord.Interaction, *, room_id: Optional[int]):
    # Clean up all battle GIF files for this battle
    try:
        battle_id = f"{st.p1_id}_{st.p2_id}"
        cleanup_battle_media(battle_id)
    except Exception as e:
        print(f"[PvP] Error cleaning up battle media: {e}")
    
    # Helper to safely send followup messages (handles both real and bot interactions)
    async def safe_followup_send(itx, embed, ephemeral=True):
        try:
            if hasattr(itx, 'followup') and hasattr(itx.followup, 'send'):
                await itx.followup.send(embed=embed, ephemeral=ephemeral)
        except Exception:
            pass  # Silently ignore errors for bot interactions

    # Flush per-battle /register tracking buffers.
    try:
        if _register_stats is not None:
            await _register_stats.flush_battle_state(st)
    except Exception:
        pass

    # For Adventure format send a single consolidated end panel (Myuu-style)
    fmt = getattr(st, "fmt_label", "") or ""
    is_adventure_like = fmt.lower().startswith("adventure") or fmt.lower() == "rival"
    # Persist move PP at battle end for non-Adventure battles.
    # Adventure/Rival persistence is handled by pokebot's PvE wrapper.
    if not is_adventure_like:
        try:
            await _save_pp_state_for_battle(st)
        except Exception:
            pass
    if is_adventure_like:
        # Adventure wild + trainer/rival: single combined embed sent from pokebot (battle ended + outcome + EXP/level-ups + money)
        pass
    else:
        last_log = list(getattr(st, "_last_turn_log", []) or [])
        last_log_text = "\n".join(last_log) if last_log else ""
        if st.winner == st.p1_id:
            winner_embed = discord.Embed(
                title="🏆 VICTORY!",
                description=f"You defeated your opponent in **{st.turn - 1} turns**!",
                color=discord.Color.gold()
            )
            loser_embed = discord.Embed(
                title="💔 DEFEAT",
                description=f"You were defeated after **{st.turn - 1} turns**.",
                color=discord.Color.dark_gray()
            )
            if last_log_text:
                winner_embed.add_field(name="", value=last_log_text, inline=False)
                loser_embed.add_field(name="", value=last_log_text, inline=False)
            await safe_followup_send(p1_itx, winner_embed)
            await safe_followup_send(p2_itx, loser_embed)
        elif st.winner == st.p2_id:
            winner_embed = discord.Embed(
                title="🏆 VICTORY!",
                description=f"You defeated your opponent in **{st.turn - 1} turns**!",
                color=discord.Color.gold()
            )
            loser_embed = discord.Embed(
                title="💔 DEFEAT",
                description=f"You were defeated after **{st.turn - 1} turns**.",
                color=discord.Color.dark_gray()
            )
            if last_log_text:
                winner_embed.add_field(name="", value=last_log_text, inline=False)
                loser_embed.add_field(name="", value=last_log_text, inline=False)
            await safe_followup_send(p2_itx, winner_embed)
            await safe_followup_send(p1_itx, loser_embed)
        else:
            end_embed = discord.Embed(
                title="⚔️ Battle Ended",
                description="The match has concluded.",
                color=discord.Color.light_gray()
            )
            if last_log_text:
                end_embed.add_field(name="", value=last_log_text, inline=False)
            await safe_followup_send(p1_itx, end_embed)
            await safe_followup_send(p2_itx, end_embed)
    # Save Missing n0's rolled stats, types, ability, and form to database
    conn = None
    try:
        from pvp.db_adapter import _open, _close_conn
        import json
        conn = _open()
        
        # Check both teams for Missing n0
        for team in [st.p1_team, st.p2_team]:
            for mon in team:
                if not mon:
                    continue
                species_lower = (mon.species or "").lower().strip()
                is_missing_n0 = (
                    species_lower in ["missing n0", "missing no", "missing no.", "missingno", "missingno.", "missing n0.", "missing no."] or
                    ("missing" in species_lower and ("n0" in species_lower or "no" in species_lower))
                )
                
                if is_missing_n0:
                    # Get the Pokemon's ID from the database
                    # We need to match by owner_id and team_slot or find by some identifier
                    # Since we don't have direct ID mapping, we'll need to find it another way
                    # For now, let's try to find by species and owner (we'll need to track IDs)
                    # Actually, we need to get the mon_id - let's check if it's stored on the Mon object
                    mon_id = getattr(mon, '_db_id', None)
                    if not mon_id:
                        # Try to find by owner and team slot
                        owner_id = None
                        if mon in st.p1_team:
                            owner_id = str(st.p1_id)
                        elif mon in st.p2_team:
                            owner_id = str(st.p2_id)
                        
                        if owner_id:
                            # Find the Pokemon by owner and species
                            cur = conn.execute("""
                                SELECT id FROM pokemons 
                                WHERE owner_id = ? AND LOWER(species) = LOWER(?)
                                LIMIT 1
                            """, (owner_id, mon.species))
                            row = cur.fetchone()
                            if row:
                                mon_id = row["id"]
                    
                    if mon_id:
                        # Save calculated stats (base + EVs/IVs/nature/level), ability, and form to database
                        # The database columns store calculated stats, not base stats
                        form_value = getattr(mon, 'form', None) or ""
                        
                        # Get calculated stats (already computed with EVs/IVs/nature/level in BattleState.__init__)
                        calculated_hp = mon.max_hp  # HP is stored as max_hp
                        calculated_atk = mon.stats.get("atk", 0)
                        calculated_def = mon.stats.get("defn", 0)  # defn -> def in DB
                        calculated_spa = mon.stats.get("spa", 0)
                        calculated_spd = mon.stats.get("spd", 0)
                        calculated_spe = mon.stats.get("spe", 0)
                        
                        # Update calculated stats (hp, atk, def, spa, spd, spe), ability, form, and moves in database
                        # Save moves as JSON string
                        moves_json = json.dumps(mon.moves if mon.moves else [], ensure_ascii=False)
                        try:
                            conn.execute("""
                                UPDATE pokemons 
                                SET hp = ?, atk = ?, def = ?, spa = ?, spd = ?, spe = ?,
                                    ability = ?, form = ?, moves = ?
                                WHERE id = ?
                            """, (
                                calculated_hp,
                                calculated_atk,
                                calculated_def,
                                calculated_spa,
                                calculated_spd,
                                calculated_spe,
                                mon.ability or "",
                                form_value,
                                moves_json,
                                mon_id
                            ))
                            conn.commit()
                            types_list = [t for t in mon.types if t]
                            try:
                                import lib.db as _db
                                _db.invalidate_pokemons_cache(owner_id)
                            except Exception:
                                pass
                        except Exception as update_error:
                            print(f"[Missing n0] Error updating database: {update_error}")
                            import traceback
                            traceback.print_exc()
                            try:
                                conn.rollback()
                            except Exception:
                                pass
    except Exception as e:
        print(f"[Missing n0] Error saving to database: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn is not None:
            try:
                from pvp.db_adapter import _close_conn
                _close_conn(conn)
            except Exception:
                pass
    
    # Restore original items to all Pokémon (temporary battle modifications are cleared)
    try:
        st.restore_items()
    except Exception:
        pass
    try:
        st.restore_terastallization()
    except Exception:
        pass
    try:
        st.restore_mega_evolution()
    except Exception:
        pass
    try:
        st.restore_abilities()
    except Exception:
        pass
    
    # Clean up battle media
    try: 
        cleanup_battle_media(f"{st.p1_id}_{st.p2_id}")
    except Exception: 
        pass
    
    # Remove from battle manager (critical - prevents "still in battle" bug)
    try:
        bm = get_manager()
        if room_id is not None:
            room = bm.get(room_id)
            if room:
                print(f"[PvP] Removing room {room_id} for users {st.p1_id} and {st.p2_id}")
                bm.remove(room)
            else:
                print(f"[PvP] Warning: Room {room_id} not found in manager")
        else:
            # Fallback: try to remove by user ID
            print(f"[PvP] Warning: No room_id provided, trying to remove by user ID")
            p1_room = bm.for_user(st.p1_id)
            if p1_room:
                bm.remove(p1_room)
            p2_room = bm.for_user(st.p2_id)
            if p2_room and p2_room != p1_room:
                bm.remove(p2_room)
    except Exception as e:
        print(f"[PvP] Error removing from battle manager: {e}")
        import traceback
        traceback.print_exc()

async def _turn_loop(st: BattleState, p1_itx: discord.Interaction, p2_itx: discord.Interaction, *, room_id: Optional[int], award_money_callback: Optional[Any] = None):
    # Timer settings (matching Pokémon Showdown casual battles)
    TURN_TIMER = 150.0  # 150 seconds = 2.5 minutes per turn
    
    st.unlock_both()
    fmt_key = (getattr(st, "fmt_label", "") or "").strip().lower()
    is_adventure_like = fmt_key.startswith("adventure") or fmt_key == "rival"
    panel_ephemeral = not _battle_ui_is_public(st)
    # Ensure PP is loaded from stored moves_pp in battle modes that don't
    # already preload/snapshot PP via the Adventure wrapper.
    if not is_adventure_like and not bool(getattr(st, "_pp_persist_loaded", False)):
        try:
            await _load_pp_state_for_battle(st)
        except Exception:
            pass
        try:
            st._pp_persist_loaded = True
        except Exception:
            pass
    
    if not getattr(st, '_battle_start_announced', False):
        # No separate "battle started" embed; we'll include pre-battle info in the first panel.
        st._battle_start_announced = True
        st._complete_init()
        # Stream kickoff: first public post should be image-only (no turn summary text).
        # Later stream updates include per-turn summaries.
        if st.streaming_enabled and not getattr(st, "_stream_started", False):
            st._stream_started = True
            try:
                stream_channel = await _resolve_stream_channel(st, p1_itx, p2_itx)
                if stream_channel is not None:
                    render_result = None
                    try:
                        render_result = await _render_gif_for_panel(st, st.p1_id, hide_hp_text=True)
                    except Exception as render_err:
                        print(f"[Stream] Initial stream pre-render failed: {render_err}")
                        render_result = None
                    try:
                        msg = await _send_stream_panel(
                            stream_channel,
                            st,
                            None,
                            render_result,
                            force_no_summary=True,
                        )
                        if msg is not None:
                            st._last_stream_message = msg
                            st._stream_initial_sent = True
                    except Exception as send_err:
                        print(f"[Stream] Initial stream send failed: {send_err}")
            except Exception as init_err:
                print(f"[Stream] Initial stream setup failed: {init_err}")

    # Preload registered-mon cache once so per-move tracking stays O(1).
    if not bool(getattr(st, "_register_cache_ready", False)):
        try:
            if _register_stats is not None:
                await _register_stats.seed_battle_registration_cache(st)
            else:
                st._registered_mon_ids = {}
                st._register_cache_ready = True
        except Exception:
            try:
                st._registered_mon_ids = {}
                st._register_cache_ready = True
            except Exception:
                pass

    # Check if active Pokémon are fainted - FORCE MANUAL SWITCH
    p1_active_mon = st._active(st.p1_id)
    p2_active_mon = st._active(st.p2_id)
    
    # Handle forced switches with user selection
    p1_choice: Optional[Dict[str, Any]] = None
    p2_choice: Optional[Dict[str, Any]] = None
    p1_timed_out: bool = False
    p2_timed_out: bool = False
    ev1 = asyncio.Event(); ev2 = asyncio.Event()

    async def done1(choice: Dict[str, Any], itx: discord.Interaction):
        nonlocal p1_choice
        p1_choice = choice; ev1.set()

    async def done2(choice: Dict[str, Any], itx: discord.Interaction):
        nonlocal p2_choice
        p2_choice = choice; ev2.set()

    # Force P1 to switch if their active is fainted
    if p1_active_mon.hp <= 0:
        switch_opts = st.switch_options(st.p1_id)
        if switch_opts:
            if len(switch_opts) == 1:
                # Only one Pokémon left - auto-switch
                p1_fainted_display = _format_pokemon_name(p1_active_mon)
                st.apply_switch(st.p1_id, switch_opts[0])
                new_mon = st._active(st.p1_id)
                p1_new_display = _format_pokemon_name(new_mon)
                # Update last turn log: "X was swapped out fainted!" and "Trainer sent out Y!"
                _append_forced_switch_to_turn_log(st, st.p1_id, p1_fainted_display, p1_new_display)
                # Trigger on-switch-in abilities for forced switch
                from pvp.engine import on_switch_in
                opp_mon = st._opp_active(st.p1_id)
                ability_msgs = on_switch_in(new_mon, opp_mon, st.field)
                desc = f"**{p1_fainted_display}** was swapped out fainted!\n**{st.p1_name}** sent out **{p1_new_display}**!"
                if ability_msgs:
                    desc += "\n\n" + "\n".join(ability_msgs)
                await safe_send_message(
                    p1_itx,
                    embed=discord.Embed(
                        title=f"**{p1_new_display}** Vs. **{_format_pokemon_name(opp_mon)}**",
                        description=desc,
                        color=discord.Color.orange()
                    ),
                    ephemeral=panel_ephemeral
                )
            else:
                # Multiple options - if bot, use AI logic to pick best switch; if human, show UI
                if st.p1_is_bot:
                    opp_mon = st._opp_active(st.p1_id)
                    chosen_switch = await _ai_best_switch_with_timeout(
                        st,
                        st.p1_id,
                        st.field,
                        timeout_s=_AI_FORCED_SWITCH_TIMEOUT,
                    )
                    if chosen_switch is None or chosen_switch not in switch_opts:
                        chosen_switch = switch_opts[0]
                    
                    p1_fainted_display = _format_pokemon_name(p1_active_mon)
                    st.apply_switch(st.p1_id, chosen_switch)
                    new_mon = st._active(st.p1_id)
                    p1_new_display = _format_pokemon_name(new_mon)
                    _append_forced_switch_to_turn_log(st, st.p1_id, p1_fainted_display, p1_new_display)
                    from pvp.engine import on_switch_in
                    opp_mon = st._opp_active(st.p1_id)
                    ability_msgs = on_switch_in(new_mon, opp_mon, st.field)
                    p1_choice = {"kind": "switch", "value": chosen_switch}
                    ev1.set()
                else:
                    # Human: show team UI for selection (Swapping style: two panels + name buttons)
                    p1_fainted_display = _format_pokemon_name(p1_active_mon)
                    em = _team_switch_embed(
                        st.p1_id, st,
                        description_override=f"Your **{p1_fainted_display}** fainted! Select a Pokémon to send out.\n\nClick the name of the Pokémon you wish to swap to.",
                    )
                    em.color = discord.Color.red()
                    v = TeamSwitchView(st.p1_id, st, done1)
                    await p1_itx.followup.send(embed=em, ephemeral=panel_ephemeral, view=v)
                    await ev1.wait()  # Wait for P1 to choose
                    if p1_choice and p1_choice.get("kind") == "switch":
                        p1_fainted_display = _format_pokemon_name(p1_active_mon)
                        st.apply_switch(st.p1_id, int(p1_choice["value"]))
                        new_mon = st._active(st.p1_id)
                        p1_new_display = _format_pokemon_name(new_mon)
                        _append_forced_switch_to_turn_log(st, st.p1_id, p1_fainted_display, p1_new_display)
                        from pvp.engine import on_switch_in
                        opp_mon = st._opp_active(st.p1_id)
                        ability_msgs = on_switch_in(new_mon, opp_mon, st.field)
        # Reset for normal turn selection AND unlock the player who just switched
        p1_choice = None
        ev1.clear()
        st._locked[st.p1_id] = False  # Unlock after forced switch
    
    # Force P2 to switch if their active is fainted
    if p2_active_mon.hp <= 0:
        switch_opts = st.switch_options(st.p2_id)
        if switch_opts:
            if len(switch_opts) == 1:
                # Only one Pokémon left - auto-switch
                p2_fainted_display = _format_pokemon_name(p2_active_mon)
                st.apply_switch(st.p2_id, switch_opts[0])
                new_mon = st._active(st.p2_id)
                p2_new_display = _format_pokemon_name(new_mon)
                _append_forced_switch_to_turn_log(st, st.p2_id, p2_fainted_display, p2_new_display)
                from pvp.engine import on_switch_in
                opp_mon = st._opp_active(st.p2_id)
                ability_msgs = on_switch_in(new_mon, opp_mon, st.field)
                desc = f"**{p2_fainted_display}** was swapped out fainted!\n**{st.p2_name}** sent out **{p2_new_display}**!"
                if ability_msgs:
                    desc += "\n\n" + "\n".join(ability_msgs)
                p1_mon = st._active(st.p1_id)
                await safe_send_message(
                    p2_itx,
                    embed=discord.Embed(
                        title=f"**{_format_pokemon_name(p1_mon)}** Vs. **{p2_new_display}**",
                        description=desc,
                        color=discord.Color.orange()
                    ),
                    ephemeral=panel_ephemeral
                )
            else:
                # Multiple options - if bot, use AI logic to pick best switch; if human, show UI
                if st.p2_is_bot:
                    opp_mon = st._opp_active(st.p2_id)
                    chosen_switch = await _ai_best_switch_with_timeout(
                        st,
                        st.p2_id,
                        st.field,
                        timeout_s=_AI_FORCED_SWITCH_TIMEOUT,
                    )
                    if chosen_switch is None or chosen_switch not in switch_opts:
                        chosen_switch = switch_opts[0]
                    
                    p2_fainted_display = _format_pokemon_name(p2_active_mon)
                    st.apply_switch(st.p2_id, chosen_switch)
                    new_mon = st._active(st.p2_id)
                    p2_new_display = _format_pokemon_name(new_mon)
                    _append_forced_switch_to_turn_log(st, st.p2_id, p2_fainted_display, p2_new_display)
                    from pvp.engine import on_switch_in
                    opp_mon = st._opp_active(st.p2_id)
                    ability_msgs = on_switch_in(new_mon, opp_mon, st.field)
                    p2_choice = {"kind": "switch", "value": chosen_switch}
                    ev2.set()
                else:
                    # Human: show team UI for selection (Swapping style: two panels + name buttons)
                    p2_fainted_display = _format_pokemon_name(p2_active_mon)
                    em = _team_switch_embed(
                        st.p2_id, st,
                        description_override=f"Your **{p2_fainted_display}** fainted! Select a Pokémon to send out.\n\nClick the name of the Pokémon you wish to swap to.",
                    )
                    em.color = discord.Color.red()
                    v = TeamSwitchView(st.p2_id, st, done2)
                    await p2_itx.followup.send(embed=em, ephemeral=panel_ephemeral, view=v)
                    await ev2.wait()  # Wait for P2 to choose
                    if p2_choice and p2_choice.get("kind") == "switch":
                        p2_fainted_display = _format_pokemon_name(p2_active_mon)
                        st.apply_switch(st.p2_id, int(p2_choice["value"]))
                        new_mon = st._active(st.p2_id)
                        p2_new_display = _format_pokemon_name(new_mon)
                        _append_forced_switch_to_turn_log(st, st.p2_id, p2_fainted_display, p2_new_display)
                        from pvp.engine import on_switch_in
                        opp_mon = st._opp_active(st.p2_id)
                        ability_msgs = on_switch_in(new_mon, opp_mon, st.field)
        # Reset for normal turn selection AND unlock the player who just switched
        p2_choice = None
        ev2.clear()
        st._locked[st.p2_id] = False  # Unlock after forced switch
    
    # Auto-execute for charging turns, recharge turns, and other forced moves
    p1_active = st._active(st.p1_id)
    p2_active = st._active(st.p2_id)
    
    # Check if P1 must recharge (Hyper Beam, etc.) - similar to charging moves
    if hasattr(p1_active, 'recharging_move') and p1_active.recharging_move:
        p1_choice = {"kind": "move", "value": "recharge"}  # Force recharge turn
        await safe_send_message(
            p1_itx,
            embed=discord.Embed(
                title="⚡ Recharging...",
                description=f"**{p1_active.species}** must recharge after using **{p1_active.recharging_move}**!",
                color=discord.Color.orange()
            ),
            ephemeral=panel_ephemeral
        )
        ev1.set()
    
    # Check if P1 is charging a move (Fly, Dig, Solar Beam, etc.)
    elif hasattr(p1_active, 'charging_move') and p1_active.charging_move:
        p1_choice = {"kind": "move", "value": p1_active.charging_move}
        await safe_send_message(
            p1_itx,
            embed=discord.Embed(
                title="⚡ Executing Move...",
                description=f"**{p1_active.species}** is finishing **{p1_active.charging_move}**!",
                color=discord.Color.blue()
            ),
            ephemeral=panel_ephemeral
        )
        ev1.set()
    
    # Check if P2 must recharge (Hyper Beam, etc.) - similar to charging moves
    if hasattr(p2_active, 'recharging_move') and p2_active.recharging_move:
        p2_choice = {"kind": "move", "value": "recharge"}  # Force recharge turn
        await safe_send_message(
            p2_itx,
            embed=discord.Embed(
                title="⚡ Recharging...",
                description=f"**{p2_active.species}** must recharge after using **{p2_active.recharging_move}**!",
                color=discord.Color.orange()
            ),
            ephemeral=panel_ephemeral
        )
        ev2.set()
    
    # Check if P2 is charging a move
    elif hasattr(p2_active, 'charging_move') and p2_active.charging_move:
        p2_choice = {"kind": "move", "value": p2_active.charging_move}
        await safe_send_message(
            p2_itx,
            embed=discord.Embed(
                title="⚡ Executing Move...",
                description=f"**{p2_active.species}** is finishing **{p2_active.charging_move}**!",
                color=discord.Color.blue()
            ),
            ephemeral=panel_ephemeral
        )
        ev2.set()

    # Check for bot players and auto-generate their choices
    if st.p1_is_bot and not ev1.is_set():
        p1_choice = await _compute_ai_choice_with_timeout(st, st.p1_id, st.field)
        ev1.set()
    
    if st.p2_is_bot and not ev2.is_set():
        p2_choice = await _compute_ai_choice_with_timeout(st, st.p2_id, st.field)
        ev2.set()
    
    # Only show move selection UI if players haven't auto-executed and aren't bots
    if not ev1.is_set() or not ev2.is_set():
        show_bag = getattr(st, "fmt_label", "") == "Adventure"
        v1 = MoveView(st.p1_id, st, done1, show_bag=show_bag) if not ev1.is_set() and not st.p1_is_bot else None
        v2 = MoveView(st.p2_id, st, done2, show_bag=show_bag) if not ev2.is_set() and not st.p2_is_bot else None

        async def _render_and_send(uid: int, view: Any, itx: Any) -> None:
            gif = await _render_gif_for_panel(st, uid)
            extra = None
            if st.turn == 1:
                pre_msgs = getattr(st, "_pre_battle_messages", []) or []
                species_display_map = _build_species_display_map(st)
                extra = [_format_log_line(msg, species_display_map) for msg in pre_msgs] if pre_msgs else None
            await _send_player_panel(itx, st, uid, view, gif, extra_lines=extra)

        send_tasks = []
        if v1:
            send_tasks.append(_render_and_send(st.p1_id, v1, p1_itx))
        if v2:
            send_tasks.append(_render_and_send(st.p2_id, v2, p2_itx))
        if send_tasks:
            await asyncio.gather(*send_tasks)

    # Wait for both players with timeout, but exit immediately on forfeit
    start_time = asyncio.get_event_loop().time()
    while not (ev1.is_set() and ev2.is_set()):
        # Check if either player forfeited - exit immediately
        if p1_choice and p1_choice.get("kind") == "forfeit":
            break
        if p2_choice and p2_choice.get("kind") == "forfeit":
            break
        
        # Check for timeout
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed >= TURN_TIMER:
            # Timeout - handle below
            if not ev1.is_set():
                p1_timed_out = True
                p1_choice = {"kind": "forfeit"}
            if not ev2.is_set():
                p2_timed_out = True
                p2_choice = {"kind": "forfeit"}
            break
        
        # Wait a short time for events
        try:
            # Create tasks so we can cancel them properly
            task1 = asyncio.create_task(ev1.wait())
            task2 = asyncio.create_task(ev2.wait())
            done, pending = await asyncio.wait_for(
                asyncio.wait({task1, task2}, return_when=asyncio.FIRST_COMPLETED),
                timeout=min(0.5, TURN_TIMER - elapsed)
            )
            # Cancel any pending tasks to avoid warnings
            for task in pending:
                task.cancel()
        except asyncio.TimeoutError:
            # Cancel both tasks on timeout
            if not ev1.is_set():
                task1.cancel()
            if not ev2.is_set():
                task2.cancel()
    
    # Safety net: if a bot somehow didn't lock an action (rare edge case), pick one now
    if st.p1_is_bot and not ev1.is_set():
        p1_choice = await _compute_ai_choice_with_timeout(st, st.p1_id, st.field)
        ev1.set()
    if st.p2_is_bot and not ev2.is_set():
        p2_choice = await _compute_ai_choice_with_timeout(st, st.p2_id, st.field)
        ev2.set()

    # Send timeout messages if needed
    # Check if interactions are still valid before sending (webhook tokens expire after 15 minutes)
    try:
        if p1_timed_out:
            try:
                # Check if interaction is still valid by checking if it's expired
                if not p1_itx.response.is_done():
                    # Interaction hasn't been responded to yet, use response instead
                    await p1_itx.response.send_message(
                        embed=discord.Embed(
                            title="⏱️ Time's Up!",
                            description=f"You took too long to make your move (>{int(TURN_TIMER)}s). You have been auto-forfeited.",
                            color=discord.Color.red()
                        ),
                        ephemeral=panel_ephemeral
                    )
                else:
                    # Use safe_send_message to handle webhook expiration
                    await safe_send_message(
                        p1_itx,
                        embed=discord.Embed(
                            title="⏱️ Time's Up!",
                            description=f"You took too long to make your move (>{int(TURN_TIMER)}s). You have been auto-forfeited.",
                            color=discord.Color.red()
                        ),
                        ephemeral=panel_ephemeral
                    )
            except Exception as e:
                # Log errors but don't fail
                print(f"[PvP] Error sending timeout message to P1: {e}")
        
        if p2_timed_out:
            try:
                # Check if interaction is still valid by checking if it's expired
                if not p2_itx.response.is_done():
                    # Interaction hasn't been responded to yet, use response instead
                    await p2_itx.response.send_message(
                        embed=discord.Embed(
                            title="⏱️ Time's Up!",
                            description=f"You took too long to make your move (>{int(TURN_TIMER)}s). You have been auto-forfeited.",
                            color=discord.Color.red()
                        ),
                        ephemeral=panel_ephemeral
                    )
                else:
                    # Use safe_send_message to handle webhook expiration
                    await safe_send_message(
                        p2_itx,
                        embed=discord.Embed(
                            title="⏱️ Time's Up!",
                            description=f"You took too long to make your move (>{int(TURN_TIMER)}s). You have been auto-forfeited.",
                            color=discord.Color.red()
                        ),
                        ephemeral=panel_ephemeral
                    )
            except Exception as e:
                # Log errors but don't fail
                print(f"[PvP] Error sending timeout message to P2: {e}")
    except Exception as e:
        print(f"[PvP] Error sending timeout messages: {e}")

    # early forfeits (including timeouts)
    if p1_choice and p1_choice.get("kind") == "forfeit":
        if (st.p2_name or "").lower().startswith("wild "):
            st._p1_ran_away = True  # so pokebot skips "wild battle ended" embed (user already got "You got away safely!")
            # Replace last stream panel with run-away message so we don't show the previous turn summary
            last_msg = getattr(st, "_last_stream_message", None)
            if last_msg is not None:
                try:
                    mon = st._active(st.p1_id)
                    species = (mon.species or "Pokémon").replace("-", " ").title() if mon else "Pokémon"
                    flee_embed = discord.Embed(
                        title="You got away safely!",
                        description=f"{species} fled the battle successfully!",
                        color=0x5865F2,
                    )
                    await last_msg.edit(embed=flee_embed, attachments=[])
                except Exception as e:
                    print(f"[PvP] Error editing stream message on run away: {e}")
                st._last_stream_message = None
        st.apply_forfeit(st.p1_id)
        try:
            if p1_timed_out:
                try:
                    if not p2_itx.response.is_done():
                        await p2_itx.response.send_message(f"🏳️ Your opponent timed out! You win by forfeit.", ephemeral=panel_ephemeral)
                    else:
                        await safe_send_message(p2_itx, content="🏳️ Your opponent timed out! You win by forfeit.", ephemeral=panel_ephemeral)
                except (discord.errors.NotFound, discord.errors.HTTPException):
                    # Webhook expired - silently ignore
                    pass
                except Exception as e:
                    print(f"[PvP] Error notifying P2 of timeout: {e}")
        except Exception as e:
            print(f"[PvP] Error notifying P2 of timeout: {e}")
        # Always call finish to clean up, even if notification fails
        try:
            return await _finish(st, p1_itx, p2_itx, room_id=room_id)
        except Exception as e:
            print(f"[PvP] Error in _finish after P1 forfeit: {e}")
            # Force cleanup even if finish fails
            try:
                bm = get_manager()
                if room_id:
                    room = bm.get(room_id)
                    if room:
                        bm.remove(room)
                # Cleanup battle media even if finish failed
                battle_id = f"{st.p1_id}_{st.p2_id}"
                cleanup_battle_media(battle_id)
            except:
                pass
            return
    if p2_choice and p2_choice.get("kind") == "forfeit":
        st.apply_forfeit(st.p2_id)
        try:
            if p2_timed_out:
                try:
                    if not p1_itx.response.is_done():
                        await p1_itx.response.send_message(f"🏳️ Your opponent timed out! You win by forfeit.", ephemeral=panel_ephemeral)
                    else:
                        await safe_send_message(p1_itx, content="🏳️ Your opponent timed out! You win by forfeit.", ephemeral=panel_ephemeral)
                except (discord.errors.NotFound, discord.errors.HTTPException):
                    # Webhook expired - silently ignore
                    pass
                except Exception as e:
                    print(f"[PvP] Error notifying P1 of timeout: {e}")
        except Exception as e:
            print(f"[PvP] Error notifying P1 of timeout: {e}")
        # Always call finish to clean up, even if notification fails
        try:
            return await _finish(st, p1_itx, p2_itx, room_id=room_id)
        except Exception as e:
            print(f"[PvP] Error in _finish after P2 forfeit: {e}")
            # Force cleanup even if finish fails
            try:
                bm = get_manager()
                if room_id:
                    room = bm.get(room_id)
                    if room:
                        bm.remove(room)
                # Cleanup battle media even if finish failed
                battle_id = f"{st.p1_id}_{st.p2_id}"
                cleanup_battle_media(battle_id)
            except:
                pass
            return

    # Check for blocked switches before resolving - if blocked, re-prompt player to choose a move
    if p1_choice and p1_choice.get("kind") == "switch":
        p1_mon = st._active(st.p1_id)
        p2_mon = st._active(st.p2_id)
        if p1_mon and p2_mon:
            from .engine import can_switch_out
            from .abilities import normalize_ability_name
            
            # Check if opponent has Shadow Tag (current ability, not future mega ability)
            opponent_ability = normalize_ability_name(p2_mon.ability or "")
            opponent_has_shadow_tag = opponent_ability == "shadow-tag"
            
            # Check if opponent is switching
            p2_wants_to_switch = p2_choice and p2_choice.get("kind") == "switch"
            
            # IMPORTANT: Switches happen BEFORE mega evolution and happen simultaneously
            # If opponent is switching, bypass trapping ABILITIES (they only work when Pokémon is on field)
            # But still check trapping MOVES (Mean Look, Spider Web, Block) - these persist
            if p2_wants_to_switch:
                # Opponent is switching, so bypass trapping abilities (switches happen simultaneously)
                # But still check trapping moves (Mean Look, Spider Web, Block) - these should still block
                can_switch, switch_reason = can_switch_out(p1_mon, p2_mon, force_switch=False, field_effects=st.field, is_pivot_move=False, bypass_shadow_tag=True)
            elif not opponent_has_shadow_tag:
                # Opponent doesn't have Shadow Tag, bypass Shadow Tag but check other trapping abilities and moves
                can_switch, switch_reason = can_switch_out(p1_mon, p2_mon, force_switch=False, field_effects=st.field, is_pivot_move=False, bypass_shadow_tag=True)
            else:
                # Opponent has Shadow Tag, check normally
                can_switch, switch_reason = can_switch_out(p1_mon, p2_mon, force_switch=False, field_effects=st.field, is_pivot_move=False)
            
            if not can_switch:
                # Switch is blocked. Bots should auto-pick a move; humans get re-prompted UI.
                st.unlock(st.p1_id)
                p1_mon_display = _format_pokemon_name(p1_mon)
                if st.p1_is_bot:
                    p1_choice = _choose_quick_fallback_move(st, st.p1_id, st.field)
                    ev1.set()
                else:
                    await safe_send_message(
                        p1_itx,
                        embed=discord.Embed(
                            title="🚫 Switch Blocked!",
                            description=f"You tried to switch out **{p1_mon_display}**!\n{switch_reason}\n\nPlease choose a move instead.",
                            color=discord.Color.orange()
                        ),
                        ephemeral=panel_ephemeral
                    )
                    # Clear choice and reset event to allow new choice
                    p1_choice = None
                    ev1.clear()
                    # Show move selection UI again (hide team button since switch was blocked)
                    v1 = MoveView(st.p1_id, st, done1, hide_team_button=True)
                    render_result = await _render_gif_for_panel(st, st.p1_id)
                    await _send_player_panel(p1_itx, st, st.p1_id, v1, render_result)
                    # Wait for new choice
                    start_time = asyncio.get_event_loop().time()
                    while not ev1.is_set():
                        elapsed = asyncio.get_event_loop().time() - start_time
                        if elapsed >= TURN_TIMER:
                            p1_timed_out = True
                            p1_choice = {"kind": "forfeit"}
                            break
                        try:
                            await asyncio.wait_for(ev1.wait(), timeout=min(0.5, TURN_TIMER - elapsed))
                        except asyncio.TimeoutError:
                            continue
    
    if p2_choice and p2_choice.get("kind") == "switch":
        p1_mon = st._active(st.p1_id)
        p2_mon = st._active(st.p2_id)
        if p1_mon and p2_mon:
            from .engine import can_switch_out
            from .abilities import normalize_ability_name
            
            # Check if opponent has Shadow Tag (current ability, not future mega ability)
            opponent_ability = normalize_ability_name(p1_mon.ability or "")
            opponent_has_shadow_tag = opponent_ability == "shadow-tag"
            
            # Check if opponent is switching
            p1_wants_to_switch = p1_choice and p1_choice.get("kind") == "switch"
            
            # IMPORTANT: Switches happen BEFORE mega evolution and happen simultaneously
            # If opponent is switching, bypass trapping ABILITIES (they only work when Pokémon is on field)
            # But still check trapping MOVES (Mean Look, Spider Web, Block) - these persist
            if p1_wants_to_switch:
                # Opponent is switching, so bypass trapping abilities (switches happen simultaneously)
                # But still check trapping moves (Mean Look, Spider Web, Block) - these should still block
                can_switch, switch_reason = can_switch_out(p2_mon, p1_mon, force_switch=False, field_effects=st.field, is_pivot_move=False, bypass_shadow_tag=True)
            elif not opponent_has_shadow_tag:
                # Opponent doesn't have Shadow Tag, bypass Shadow Tag but check other trapping abilities and moves
                can_switch, switch_reason = can_switch_out(p2_mon, p1_mon, force_switch=False, field_effects=st.field, is_pivot_move=False, bypass_shadow_tag=True)
            else:
                # Opponent has Shadow Tag, check normally
                can_switch, switch_reason = can_switch_out(p2_mon, p1_mon, force_switch=False, field_effects=st.field, is_pivot_move=False)
            
            if not can_switch:
                # Switch is blocked. Bots should auto-pick a move; humans get re-prompted UI.
                st.unlock(st.p2_id)
                p2_mon_display = _format_pokemon_name(p2_mon)
                if st.p2_is_bot:
                    p2_choice = _choose_quick_fallback_move(st, st.p2_id, st.field)
                    ev2.set()
                else:
                    await safe_send_message(
                        p2_itx,
                        embed=discord.Embed(
                            title="🚫 Switch Blocked!",
                            description=f"You tried to switch out **{p2_mon_display}**!\n{switch_reason}\n\nPlease choose a move instead.",
                            color=discord.Color.orange()
                        ),
                        ephemeral=panel_ephemeral
                    )
                    # Clear choice and reset event to allow new choice
                    p2_choice = None
                    ev2.clear()
                    # Show move selection UI again (hide team button since switch was blocked)
                    v2 = MoveView(st.p2_id, st, done2, hide_team_button=True)
                    render_result = await _render_gif_for_panel(st, st.p2_id)
                    await _send_player_panel(p2_itx, st, st.p2_id, v2, render_result)
                    # Wait for new choice
                    start_time = asyncio.get_event_loop().time()
                    while not ev2.is_set():
                        elapsed = asyncio.get_event_loop().time() - start_time
                        if elapsed >= TURN_TIMER:
                            p2_timed_out = True
                            p2_choice = {"kind": "forfeit"}
                            break
                        try:
                            await asyncio.wait_for(ev2.wait(), timeout=min(0.5, TURN_TIMER - elapsed))
                        except asyncio.TimeoutError:
                            continue
    
    # Check for forfeits after handling blocked switches (before resolve)
    if p1_choice and p1_choice.get("kind") == "forfeit":
        st.apply_forfeit(st.p1_id)
        try:
            if p1_timed_out:
                try:
                    if not p2_itx.response.is_done():
                        await p2_itx.response.send_message(f"🏳️ Your opponent timed out! You win by forfeit.", ephemeral=panel_ephemeral)
                    else:
                        await safe_send_message(p2_itx, content="🏳️ Your opponent timed out! You win by forfeit.", ephemeral=panel_ephemeral)
                except (discord.errors.NotFound, discord.errors.HTTPException):
                    # Webhook expired - silently ignore
                    pass
                except Exception as e:
                    print(f"[PvP] Error notifying P2 of timeout: {e}")
        except Exception as e:
            print(f"[PvP] Error notifying P2 of timeout: {e}")
        try:
            return await _finish(st, p1_itx, p2_itx, room_id=room_id)
        except Exception as e:
            print(f"[PvP] Error in _finish after P1 forfeit: {e}")
            try:
                bm = get_manager()
                if room_id:
                    room = bm.get(room_id)
                    if room:
                        bm.remove(room)
                # Cleanup battle media even if finish failed
                battle_id = f"{st.p1_id}_{st.p2_id}"
                cleanup_battle_media(battle_id)
            except:
                pass
            return
    if p2_choice and p2_choice.get("kind") == "forfeit":
        st.apply_forfeit(st.p2_id)
        try:
            if p2_timed_out:
                try:
                    if not p1_itx.response.is_done():
                        await p1_itx.response.send_message(f"🏳️ Your opponent timed out! You win by forfeit.", ephemeral=panel_ephemeral)
                    else:
                        await safe_send_message(p1_itx, content="🏳️ Your opponent timed out! You win by forfeit.", ephemeral=panel_ephemeral)
                except (discord.errors.NotFound, discord.errors.HTTPException):
                    # Webhook expired - silently ignore
                    pass
                except Exception as e:
                    print(f"[PvP] Error notifying P1 of timeout: {e}")
        except Exception as e:
            print(f"[PvP] Error notifying P1 of timeout: {e}")
        try:
            return await _finish(st, p1_itx, p2_itx, room_id=room_id)
        except Exception as e:
            print(f"[PvP] Error in _finish after P2 forfeit: {e}")
            try:
                bm = get_manager()
                if room_id:
                    room = bm.get(room_id)
                    if room:
                        bm.remove(room)
                # Cleanup battle media even if finish failed
                battle_id = f"{st.p1_id}_{st.p2_id}"
                cleanup_battle_media(battle_id)
            except:
                pass
            return

    # resolve via engine (damage, accuracy, priority+speed, contact)
    resolve_result = st.resolve(p1_choice or {}, p2_choice or {})
    if len(resolve_result) == 3 and resolve_result[2] is not None:
        # Pivot switch needed mid-turn - handle it
        turn_log, pivot_switches, pivot_info = resolve_result
        pivot_uid = pivot_info["uid"]
        remaining_order = pivot_info["remaining_order"]
        actions = pivot_info["actions"]
        c1 = pivot_info["c1"]
        c2 = pivot_info["c2"]
        
        # Show team selection UI for the player who used the pivot move
        # Ensure they're unlocked so they can make the switch choice
        st.unlock(pivot_uid)
        pivot_itx = p1_itx if pivot_uid == st.p1_id else p2_itx
        switch_opts = st.switch_options(pivot_uid)
        
        if switch_opts:
            if len(switch_opts) == 1:
                # Only one option - auto-switch
                pivot_switch_choice = {pivot_uid: switch_opts[0]}
            else:
                # Multiple options - show UI
                ev = asyncio.Event()
                pivot_choice_dict = {}
                
                async def done_pivot(choice: Dict[str, Any], itx: discord.Interaction):
                    nonlocal pivot_choice_dict
                    if choice.get("kind") == "switch":
                        pivot_choice_dict[pivot_uid] = int(choice["value"])
                    # Lock the player after they make their choice
                    st.lock(pivot_uid)
                    ev.set()
                
                em = _team_switch_embed(
                    pivot_uid, st,
                    description_override="Select a Pokémon to switch to.\n\nClick the name of the Pokémon you wish to swap to.",
                )
                em.color = discord.Color.blue()
                v = TeamSwitchView(pivot_uid, st, done_pivot)
                await pivot_itx.followup.send(embed=em, ephemeral=panel_ephemeral, view=v)
                
                # Wait for choice (with timeout)
                try:
                    await asyncio.wait_for(ev.wait(), timeout=TURN_TIMER)
                except asyncio.TimeoutError:
                    # Timeout - auto-switch to first available
                    pivot_choice_dict = {pivot_uid: switch_opts[0]}
                    st.lock(pivot_uid)  # Lock after timeout too
                
                pivot_switch_choice = pivot_choice_dict if pivot_choice_dict else {pivot_uid: switch_opts[0]}
            
            # Apply the switch BEFORE continuing the turn
            if pivot_uid in pivot_switch_choice:
                switch_to_index = pivot_switch_choice[pivot_uid]
                old_mon = st._active(pivot_uid)
                old_mon_display = _format_pokemon_name(old_mon)
                
                switch_messages = st.apply_switch(pivot_uid, switch_to_index)
                new_mon = st._active(pivot_uid)
                new_mon_display = _format_pokemon_name(new_mon)
                
                # Add Leech Seed damage messages (if any)
                for msg in switch_messages:
                    turn_log.append(msg)
                
                # Add switch messages FIRST (before abilities, weather, etc.)
                turn_log.append(f"**{st.p1_name if pivot_uid == st.p1_id else st.p2_name}** switched out **{old_mon_display}**!")
                turn_log.append(f"**{st.p1_name if pivot_uid == st.p1_id else st.p2_name}** sent out **{new_mon_display}**!")
                
                # Apply entry hazards (before abilities trigger)
                from .hazards import apply_entry_hazards
                side = st.p1_side if pivot_uid == st.p1_id else st.p2_side
                hazard_msgs = apply_entry_hazards(new_mon, side.hazards, is_grounded=True, field_effects=st.field, battle_state=st)
                for msg in hazard_msgs:
                    turn_log.append(f"  {msg}")
                pending_msgs = getattr(new_mon, "_pending_entry_messages", None)
                if pending_msgs:
                    for msg in pending_msgs:
                        turn_log.append(f"  {msg}")
                    delattr(new_mon, "_pending_entry_messages")
                
                # Trigger switch-in abilities (Intimidate, weather, etc.)
                from pvp.engine import on_switch_in, check_item_based_forme_change
                opp_mon = st._opp_active(pivot_uid)
                ability_msgs = on_switch_in(new_mon, opp_mon, st.field)
                for msg in ability_msgs:
                    turn_log.append(msg)
                
                # Check item-based forme changes on switch-in
                item_form_msg = check_item_based_forme_change(new_mon, triggered_by="switch_in")
                if item_form_msg:
                    turn_log.append(f"  {item_form_msg}")
            
            # Continue the turn with the remaining moves
            continue_result = st.resolve(
                c1, c2, pivot_switch_choice=None, start_from_index=0, order_override=remaining_order, actions_override=actions
            )
            if len(continue_result) == 3:
                continue_log, continue_pivot_switches, _ = continue_result
            else:
                continue_log, continue_pivot_switches = continue_result
            turn_log.extend(continue_log)
            pivot_switches.update(continue_pivot_switches)
        else:
            # No switch options - continue without switch
            continue_result = st.resolve(c1, c2, pivot_switch_choice={})
            if len(continue_result) == 3:
                continue_log, continue_pivot_switches, _ = continue_result
            else:
                continue_log, continue_pivot_switches = continue_result
            turn_log.extend(continue_log)
            pivot_switches.update(continue_pivot_switches)
    else:
        # Normal resolution
        if len(resolve_result) == 3:
            turn_log, pivot_switches, _ = resolve_result
        else:
            turn_log, pivot_switches = resolve_result

    species_display_map = _build_species_display_map(st)
    formatted_turn_log = [_format_log_line(line, species_display_map) for line in turn_log]
    if not formatted_turn_log:
        try:
            last_log = [
                _format_log_line(line, species_display_map)
                for line in (getattr(st, "_last_turn_log", []) or [])
                if str(line).strip()
            ]
            formatted_turn_log = last_log if last_log else ["No significant actions this turn."]
        except Exception:
            formatted_turn_log = ["No significant actions this turn."]
    formatted_turn_text = "\n".join(str(x) for x in formatted_turn_log if str(x).strip()).strip()
    if len(formatted_turn_text) > 3500:
        formatted_turn_text = "...\n" + formatted_turn_text[-3400:]
    if not formatted_turn_text:
        formatted_turn_text = "No significant actions this turn."
    
    # Add current Pokemon HP status
    p1_mon = st._active(st.p1_id)
    p2_mon = st._active(st.p2_id)
    
    # Create HP bars with color indicators
    p1_hp_bar = _hp_bar(p1_mon.hp, p1_mon.max_hp)
    p2_hp_bar = _hp_bar(p2_mon.hp, p2_mon.max_hp)
    
    # Try to get sprite for the attacking Pokémon
    from .sprites import find_sprite
    
    # Determine which Pokémon attacked first (for sprite display)
    p1_acted_first = False
    if p1_choice and p2_choice:
        if p1_choice.get("kind") == "move" and p2_choice.get("kind") == "move":
            from .engine import action_priority, speed_value
            p1_pr = action_priority(p1_choice.get("value", ""), p1_mon, st.field, st)
            p2_pr = action_priority(p2_choice.get("value", ""), p2_mon, st.field, st)
            if p1_pr > p2_pr or (p1_pr == p2_pr and speed_value(p1_mon, field_effects=st.field) >= speed_value(p2_mon, field_effects=st.field)):
                p1_acted_first = True
    
    # Build P1's turn summary with sprite
    p1_display_turn = _format_pokemon_name(p1_mon)
    p2_display_turn = _format_pokemon_name(p2_mon)
    fmt = (getattr(st, "fmt_label", "") or "").lower()
    is_adventure = fmt.startswith("adventure")
    is_wild = (st.p2_name or "").lower().startswith("wild ")
    battle_ended = getattr(st, "winner", None) is not None
    if is_adventure and is_wild and battle_ended:
        turn_title = "Wild battle has ended!"
    elif is_adventure:
        turn_title = f"**{p1_display_turn}** Vs. **{p2_display_turn}**"
    else:
        turn_title = f"⚔️ Turn {st.turn - 1} Summary"
    turn_embed = discord.Embed(
        title=turn_title,
        description=formatted_turn_text,
        color=discord.Color.blue()
    )
    
    # Try to attach sprite of the attacking Pokémon (or substitute if active)
    sprite_file = None
    if p1_choice and p1_choice.get("kind") == "move":
        # Check if substitute is active
        if hasattr(p1_mon, 'substitute') and p1_mon.substitute:
            sprite_path = find_sprite(
                "substitute",
                gen=st.gen,
                perspective="front",
                shiny=False,
                female=False,
                prefer_animated=False,  # Use static for embed thumbnail
                form=None
            )
        else:
            sprite_path = find_sprite(
                p1_mon.species,
                gen=st.gen,
                perspective="front",
                shiny=getattr(p1_mon, "shiny", False),
                female=(p1_mon.gender == "F"),
                prefer_animated=False,  # Use static for embed thumbnail
                form=getattr(p1_mon, "form", None)
            )
        if sprite_path and sprite_path.exists():
            try:
                sprite_file = discord.File(sprite_path, filename=f"{p1_mon.species}_sprite.png")
                turn_embed.set_thumbnail(url=f"attachment://{p1_mon.species}_sprite.png")
            except:
                sprite_file = None
    
    p1_display_name = _format_pokemon_name(p1_mon)
    p2_display_name = _format_pokemon_name(p2_mon)

    turn_embed.add_field(
        name=f"Your {p1_display_name}",
        value=f"{p1_hp_bar}",
        inline=False
    )
    turn_embed.add_field(
        name=f"Opponent's {p2_display_name}",
        value=f"{p2_hp_bar}",
        inline=False
    )
    
    # Add field conditions if any
    field_text = _field_conditions_text(st.field)
    if field_text:
        turn_embed.add_field(
            name="🌍 Field Conditions",
            value=field_text,
            inline=False
        )
    
    # Build P2's turn summary with sprite (prepare in parallel)
    turn_embed2 = discord.Embed(
        title=turn_title,
        description=formatted_turn_text,
        color=discord.Color.red()
    )
    
    # Try to attach sprite of their attacking Pokémon (or substitute if active)
    sprite_file2 = None
    if p2_choice and p2_choice.get("kind") == "move":
        # Check if substitute is active
        if hasattr(p2_mon, 'substitute') and p2_mon.substitute:
            sprite_path2 = find_sprite(
                "substitute",
                gen=st.gen,
                perspective="front",
                shiny=False,
                female=False,
                prefer_animated=False,
                form=None
            )
        else:
            sprite_path2 = find_sprite(
                p2_mon.species,
                gen=st.gen,
                perspective="front",
                shiny=getattr(p2_mon, "shiny", False),
                female=(p2_mon.gender == "F"),
                prefer_animated=False,
                form=getattr(p2_mon, "form", None)
            )
        if sprite_path2 and sprite_path2.exists():
            try:
                sprite_file2 = discord.File(sprite_path2, filename=f"{p2_mon.species}_sprite.png")
                turn_embed2.set_thumbnail(url=f"attachment://{p2_mon.species}_sprite.png")
            except:
                sprite_file2 = None
    
    turn_embed2.add_field(
        name=f"Your {p2_display_name}",
        value=f"{p2_hp_bar}\n**{p2_mon.hp}/{p2_mon.max_hp} HP**",
        inline=False
    )
    turn_embed2.add_field(
        name=f"Opponent's {p1_display_name}",
        value=f"{p1_hp_bar}\n**{p1_mon.hp}/{p1_mon.max_hp} HP**",
        inline=False
    )
    
    # Add field conditions if any
    field_text2 = _field_conditions_text(st.field)
    if field_text2:
        turn_embed2.add_field(
            name="🌍 Field Conditions",
            value=field_text2,
            inline=False
        )
    
    # Persist last turn log for end-of-battle summary
    st._last_turn_log = formatted_turn_log

    # Helper functions for parallel sending
    async def send_p1_summary():
        # When battle ended: one big combined embed from _finish (or pokebot for wild); skip separate turn message
        if battle_ended:
            return
        try:
            if sprite_file:
                await safe_send_message(p1_itx, embed=turn_embed, file=sprite_file, ephemeral=panel_ephemeral)
            else:
                await safe_send_message(p1_itx, embed=turn_embed, ephemeral=panel_ephemeral)
        finally:
            if sprite_file:
                try:
                    sprite_file.close()
                except:
                    pass
    
    async def send_p2_summary():
        if battle_ended:
            return
        try:
            if sprite_file2:
                await safe_send_message(p2_itx, embed=turn_embed2, file=sprite_file2, ephemeral=panel_ephemeral)
            else:
                await safe_send_message(p2_itx, embed=turn_embed2, ephemeral=panel_ephemeral)
        finally:
            if sprite_file2:
                try:
                    sprite_file2.close()
                except:
                    pass
    
    async def send_stream_update():
        """Send stream panel update in background (non-blocking for players)"""
        if not st.streaming_enabled:
            return
        stream_channel = await _resolve_stream_channel(st, p1_itx, p2_itx)
        if stream_channel is None:
            return
        # Serialize stream rendering/edits so updates stay in order per battle.
        stream_lock = getattr(st, "_stream_update_lock", None)
        if stream_lock is None:
            stream_lock = asyncio.Lock()
            st._stream_update_lock = stream_lock
        try:
            async with stream_lock:
                try:
                    turn_no = int(getattr(st, "turn", 0) or 0)
                except Exception:
                    turn_no = 0

                # Turn 1 must be stream image-only (no summary). Kickoff post is handled
                # at battle start; if that failed, retry once here with no summary.
                if turn_no <= 1:
                    if not bool(getattr(st, "_stream_initial_sent", False)):
                        render_result = None
                        try:
                            render_result = await _render_gif_for_panel(st, st.p1_id, hide_hp_text=True)
                        except Exception as e:
                            print(f"[Stream] Turn-1 stream pre-render failed: {e}")
                            render_result = None
                        msg = await _send_stream_panel(
                            stream_channel,
                            st,
                            None,
                            render_result,
                            force_no_summary=True,
                        )
                        if msg is not None:
                            st._last_stream_message = msg
                            st._stream_initial_sent = True
                    return

                # Keep public stream summary text aligned with the private turn summary text.
                summary_payload = str(formatted_turn_text or "").strip()
                if not summary_payload:
                    summary_payload = "No significant actions this turn."

                # Let _send_stream_panel handle rendering/fallback internally so a render
                # hiccup does not suppress the public summary message.
                render_result = None
                try:
                    render_result = await _render_gif_for_panel(st, st.p1_id, hide_hp_text=True)
                except Exception as e:
                    print(f"[Stream] Stream pre-render failed: {e}")
                    render_result = None

                msg = await _send_stream_panel(stream_channel, st, summary_payload, render_result)
                if msg is not None:
                    st._last_stream_message = msg
                else:
                    # Last-resort keepalive so stream never appears "dead".
                    try:
                        fallback = f"📺 Stream update • Turn {getattr(st, 'turn', '?')}"
                        if summary_payload:
                            txt = summary_payload[-1400:] if len(summary_payload) > 1400 else summary_payload
                            fallback += f"\n{txt}"
                        await stream_channel.send(fallback)
                    except Exception:
                        pass
        except Exception as e:
            print(f"[Stream] Error updating stream: {e}")

    # Send player summaries first, then await stream send to avoid dropped updates.
    await asyncio.gather(send_p1_summary(), send_p2_summary())
    await send_stream_update()

    if st.winner:
        if award_money_callback:
            try:
                await award_money_callback(st)
            except Exception as e:
                print(f"[PvP] award_money_callback error: {e}")
        return await _finish(st, p1_itx, p2_itx, room_id=room_id)

    # === HANDLE PIVOT MOVE SWITCHES (Volt Switch, U-turn, Flip Turn) ===
    # These happen AFTER the turn is fully resolved, but BEFORE the next turn starts
    # IMPORTANT: When both players use pivot moves, both must be prompted simultaneously
    if pivot_switches:
        # Track if we need to wait for choices
        p1_pivot_choice: Optional[Dict[str, Any]] = None
        p2_pivot_choice: Optional[Dict[str, Any]] = None
        ev1 = asyncio.Event()
        ev2 = asyncio.Event()

        async def done1(choice: Dict[str, Any], itx: discord.Interaction):
            nonlocal p1_pivot_choice
            p1_pivot_choice = choice
            ev1.set()

        async def done2(choice: Dict[str, Any], itx: discord.Interaction):
            nonlocal p2_pivot_choice
            p2_pivot_choice = choice
            ev2.set()
        
        # Send prompts to BOTH players simultaneously if both need to switch
        p1_needs_switch = st.p1_id in pivot_switches
        p2_needs_switch = st.p2_id in pivot_switches
        
        # List of tasks to wait for
        wait_tasks = []
        
        # Handle P1 pivot switch
        if p1_needs_switch:
            # Unlock P1 temporarily for pivot switch selection
            st.unlock(st.p1_id)
            
            switch_opts = st.switch_options(st.p1_id)
            if switch_opts:
                if len(switch_opts) == 1:
                    # Only one Pokémon available - auto-switch
                    st.apply_switch(st.p1_id, switch_opts[0])
                    # Trigger on-switch-in abilities for pivot switch
                    from pvp.engine import on_switch_in
                    new_mon = st._active(st.p1_id)
                    opp_mon = st._opp_active(st.p1_id)
                    ability_msgs = on_switch_in(new_mon, opp_mon, st.field)
                    await safe_send_message(
                        p1_itx,
                        embed=discord.Embed(
                            title="🔄 Pivot Switch",
                            description=f"{st._active(st.p1_id).species} was sent out!",
                            color=discord.Color.blue()
                        ),
                        ephemeral=panel_ephemeral
                    )
                else:
                    # Multiple options - show team UI for selection
                    em = _team_switch_embed(
                        st.p1_id, st,
                        description_override="Select a Pokémon to switch to.\n\nClick the name of the Pokémon you wish to swap to.",
                    )
                    em.color = discord.Color.blue()
                    v = TeamSwitchView(st.p1_id, st, done1)
                    await p1_itx.followup.send(embed=em, ephemeral=panel_ephemeral, view=v)
                    wait_tasks.append(asyncio.create_task(ev1.wait()))
        
        # Handle P2 pivot switch
        if p2_needs_switch:
            # Unlock P2 temporarily for pivot switch selection
            st.unlock(st.p2_id)
            
            switch_opts = st.switch_options(st.p2_id)
            if switch_opts:
                if len(switch_opts) == 1:
                    # Only one Pokémon available - auto-switch
                    st.apply_switch(st.p2_id, switch_opts[0])
                    # Trigger on-switch-in abilities for pivot switch
                    from pvp.engine import on_switch_in
                    new_mon = st._active(st.p2_id)
                    opp_mon = st._opp_active(st.p2_id)
                    ability_msgs = on_switch_in(new_mon, opp_mon, st.field)
                    await safe_send_message(
                        p2_itx,
                        embed=discord.Embed(
                            title="🔄 Pivot Switch",
                            description=f"{st._active(st.p2_id).species} was sent out!",
                            color=discord.Color.blue()
                        ),
                        ephemeral=panel_ephemeral
                    )
                else:
                    # Multiple options - show team UI for selection
                    em = _team_switch_embed(
                        st.p2_id, st,
                        description_override="Select a Pokémon to switch to.\n\nClick the name of the Pokémon you wish to swap to.",
                    )
                    em.color = discord.Color.blue()
                    v = TeamSwitchView(st.p2_id, st, done2)
                    await p2_itx.followup.send(embed=em, ephemeral=panel_ephemeral, view=v)
                    wait_tasks.append(asyncio.create_task(ev2.wait()))
        
        # Wait for ALL choices simultaneously (if any tasks to wait for)
        if wait_tasks:
            await asyncio.gather(*wait_tasks)
        
        # Process P1 choice
        if p1_needs_switch and p1_pivot_choice and p1_pivot_choice.get("kind") == "switch":
            st.apply_switch(st.p1_id, int(p1_pivot_choice["value"]))
            # Trigger on-switch-in abilities for pivot switch
            from pvp.engine import on_switch_in
            new_mon = st._active(st.p1_id)
            opp_mon = st._opp_active(st.p1_id)
            ability_msgs = on_switch_in(new_mon, opp_mon, st.field)
            # Add ability messages to next turn's log (will be shown at start of next turn)
        
        # Process P2 choice
        if p2_needs_switch and p2_pivot_choice and p2_pivot_choice.get("kind") == "switch":
            st.apply_switch(st.p2_id, int(p2_pivot_choice["value"]))
            # Trigger on-switch-in abilities for pivot switch
            from pvp.engine import on_switch_in
            new_mon = st._active(st.p2_id)
            opp_mon = st._opp_active(st.p2_id)
            ability_msgs = on_switch_in(new_mon, opp_mon, st.field)
            # Add ability messages to next turn's log (will be shown at start of next turn)

    await _turn_loop(st, p1_itx, p2_itx, room_id=room_id)

# ============================  ACCEPT PROMPT (public)  ============================

class StreamButton(discord.ui.Button):
    """Button to enable streaming for the battle"""
    def __init__(self):
        super().__init__(label="📺 Stream Battle", style=discord.ButtonStyle.secondary)
    
    async def callback(self, itx: discord.Interaction):
        view: AcceptView = self.view
        if view.streaming_enabled:
            await itx.response.send_message("Streaming is already enabled for this battle.", ephemeral=True)
            return
        
        view.streaming_enabled = True
        
        # Edit the challenge embed to show streaming status
        if view.challenge_message:
            try:
                embed = view.challenge_message.embeds[0] if view.challenge_message.embeds else None
                if embed:
                    # Get current status and append streaming status
                    current_status = ""
                    if len(embed.fields) > 2:
                        current_status = embed.fields[2].value
                    
                    # Build new status with all statuses
                    status_parts = []
                    if current_status and "📺" not in current_status:
                        status_parts.append(current_status)
                    status_parts.append("📺 Battle will be streamed")
                    
                    embed.set_field_at(2, name="Status", value="\n".join(status_parts))
                    await view.challenge_message.edit(embed=embed, view=view)
            except Exception as e:
                print(f"[Stream] Error editing challenge message: {e}")
        
        await itx.response.send_message("✅ Battle streaming enabled! The stream will start when the battle begins.", ephemeral=True)

class AcceptView(discord.ui.View):
    """Public challenge prompt → launches a battle with ephemeral per-user panels (NO THREAD)."""
    def __init__(self, challenger_id: int, opponent_id: int, fmt_key: str, generation: int = None, *, fmt_label: Optional[str] = None, timeout: Optional[float] = 180, room_id: Optional[int] = None, p1_is_bot: bool = False, p2_is_bot: bool = False):
        super().__init__(timeout=timeout)
        self.challenger_id = int(challenger_id)
        self.opponent_id = int(opponent_id)
        self.fmt_key = fmt_key
        self.generation = generation
        self.fmt_label = fmt_label or fmt_key.upper()
        self.accepted: Dict[int, bool] = {}
        self._last_itx: Dict[int, discord.Interaction] = {}
        self.room_id: Optional[int] = room_id
        self.declined: bool = False
        self.battle_started: bool = False  # Prevent double-start
        self.streaming_enabled: bool = False
        self.challenge_message: Optional[discord.Message] = None
        self.p1_is_bot = p1_is_bot
        self.p2_is_bot = p2_is_bot

        # Add Stream button
        self.add_item(StreamButton())

    def _is_participant(self, uid: int) -> bool:
        return uid in (self.challenger_id, self.opponent_id)
    
    async def on_timeout(self):
        """Called when view times out - clean up battle room and clear any primed team cache."""
        if self.room_id and not self.declined and len(self.accepted) < 2:
            bm = get_manager()
            room = bm.get(self.room_id)
            if room:
                bm.remove(room)
        if _lib_db_cache is not None:
            _lib_db_cache.clear_battle_party_cache()
        self.stop()

    async def _start_if_ready(self, itx: discord.Interaction):
        if self.p2_is_bot and self.opponent_id not in self.accepted:
            self.accepted[self.opponent_id] = True

        if not (self.challenger_id in self.accepted and self.opponent_id in self.accepted):
            return
        if self.battle_started:
            return
        self.battle_started = True

        try:
            channel = itx.channel
            fmt_label = getattr(self, "fmt_label", None) or self.fmt_key.upper()
            gen = self.generation if self.generation is not None else 9
            p1_is_bot = getattr(self, "p1_is_bot", False)
            p2_is_bot = getattr(self, "p2_is_bot", False)

            # Recovery guard: if stream button state desynced after message edits/restarts,
            # infer it from the challenge status text.
            if not self.streaming_enabled and self.challenge_message and getattr(self.challenge_message, "embeds", None):
                try:
                    emb0 = self.challenge_message.embeds[0]
                    status_text = ""
                    if emb0 and len(getattr(emb0, "fields", [])) > 2:
                        status_text = str(emb0.fields[2].value or "")
                    if "battle will be streamed" in status_text.lower() or "📺" in status_text:
                        self.streaming_enabled = True
                except Exception:
                    pass

            if p2_is_bot:
                from .ai import generate_bot_team
                p1_party, p2_party = await asyncio.gather(
                    build_party_from_db(self.challenger_id, set_level=100, heal=True),
                    generate_bot_team(self.fmt_key, gen),
                )
            else:
                p1_party, p2_party = await asyncio.gather(
                    build_party_from_db(self.challenger_id, set_level=100, heal=True),
                    build_party_from_db(self.opponent_id, set_level=100, heal=True),
                )

            if not p1_party or not p2_party:
                await channel.send("Could not load one or both teams.")
                self.stop()
                return

            opponent_visibility = "AI" if p2_is_bot else f"<@{self.opponent_id}>"
            if self.streaming_enabled:
                await channel.send(
                    f"**The battle has commenced!** <@{self.challenger_id}> and {opponent_visibility} will see the private panels.\n"
                    f"📺 **Battle stream is ON** — public stream updates will be posted in this channel.\n"
                    f"Format: **{fmt_label}** (Gen {gen})"
                )
            else:
                await channel.send(
                    f"**The battle has commenced!** Only <@{self.challenger_id}> and {opponent_visibility} will see the panels.\n"
                    f"Format: **{fmt_label}** (Gen {gen})"
                )

            p1_itx = self._last_itx.get(self.challenger_id) or itx
            p2_itx = self._last_itx.get(self.opponent_id) or (itx if not p2_is_bot else None)
            p1_name = p1_itx.user.display_name if hasattr(p1_itx.user, 'display_name') else p1_itx.user.name
            p2_name = "AI Opponent" if p2_is_bot else (p2_itx.user.display_name if p2_itx and hasattr(p2_itx.user, 'display_name') else (p2_itx.user.name if p2_itx else f"Player {self.opponent_id}"))
            
            st = BattleState(fmt_label, gen, self.challenger_id, self.opponent_id, p1_party, p2_party, p1_name, p2_name, p1_is_bot=p1_is_bot, p2_is_bot=p2_is_bot)
            st.streaming_enabled = self.streaming_enabled
            # Persist stream destination so updates don't depend on a single interaction object.
            st.stream_channel = channel
            st.stream_channel_id = getattr(channel, "id", None)
            
            # For bot players, create a dummy interaction
            if p2_is_bot and not p2_itx:
                # Create a minimal interaction-like object for bot
                class BotInteraction:
                    def __init__(self, user_id):
                        self.user = type('User', (), {'id': user_id, 'display_name': 'AI Opponent', 'name': 'AI'})()
                        self.channel = itx.channel
                        self.guild_id = itx.guild_id
                        # Create a mock followup object that supports .send() as an async function
                        class MockFollowup:
                            async def send(self, *args, **kwargs):
                                # Just silently succeed - bot doesn't need to see messages
                                return None
                        self._followup = MockFollowup()
                    
                    @property
                    def followup(self):
                        return self._followup
                
                p2_itx = BotInteraction(self.opponent_id)
            
            await _turn_loop(st, p1_itx, p2_itx, room_id=self.room_id)
            self.stop()
        except Exception as e:
            fdc = _open_fd_count()
            if fdc is not None:
                print(f"[PvP] Open file descriptors: {fdc}")
            print(f"[PvP] Battle start error: {e}")
            import traceback
            traceback.print_exc()
            try:
                await channel.send(f"⚠️ Battle failed to start: {str(e)}")
            except Exception:
                pass
            self.stop()
        finally:
            if _lib_db_cache is not None:
                _lib_db_cache.clear_battle_party_cache()

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept(self, itx: discord.Interaction, _btn: discord.ui.Button):
        if self.declined:
            await itx.response.send_message("❌ This challenge was declined.", ephemeral=True)
            return
        if not self._is_participant(itx.user.id):
            await itx.response.send_message("You're not part of this battle.", ephemeral=True)
            return
        if itx.user.id in self.accepted:
            await itx.response.send_message("You already accepted!", ephemeral=True)
            return

        try:
            await itx.response.defer(ephemeral=True)
        except Exception:
            return

        self.accepted[itx.user.id] = True
        self._last_itx[itx.user.id] = itx

        try:
            await get_party_for_engine(itx.user.id, save_to_battle_cache=True)
        except Exception:
            pass

        try:
            original_message = itx.message
            if original_message and original_message.embeds:
                embed = original_message.embeds[0]
                current_status = ""
                if len(embed.fields) > 2:
                    current_status = embed.fields[2].value
                status_parts = []
                if current_status:
                    for line in current_status.split("\n"):
                        if line.strip() and "accepted" not in line.lower() and "starting" not in line.lower():
                            status_parts.append(line)
                if len(self.accepted) == 1:
                    accepter = "<@" + str(itx.user.id) + ">"
                    status_parts.append(f"✅ {accepter} accepted! Waiting for opponent...")
                    embed.set_field_at(2, name="Status", value="\n".join(status_parts))
                    await original_message.edit(embed=embed)
                    await itx.followup.send("✅ Accepted! Waiting for opponent...", ephemeral=True)
                elif len(self.accepted) == 2:
                    status_parts.append("✅ Both players accepted! Starting battle...")
                    embed.set_field_at(2, name="Status", value="\n".join(status_parts))
                    embed.color = discord.Color.green()
                    await original_message.edit(embed=embed, view=None)
                    await itx.followup.send("⚔️ Battle starting!", ephemeral=True)
                else:
                    await itx.followup.send("✅ Accepted!", ephemeral=True)
            else:
                await itx.followup.send("✅ Accepted!", ephemeral=True)
        except Exception:
            try:
                await itx.followup.send("✅ Accepted!", ephemeral=True)
            except Exception:
                pass

        await self._start_if_ready(itx)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline(self, itx: discord.Interaction, _btn: discord.ui.Button):
        if not self._is_participant(itx.user.id):
            await itx.response.send_message("You're not part of this battle.", ephemeral=True)
            return
            
        self.declined = True

        if _lib_db_cache is not None:
            _lib_db_cache.clear_battle_party_cache()

        # Update the embed and remove buttons
        try:
            original_message = itx.message
            if original_message and original_message.embeds:
                embed = original_message.embeds[0]
                embed.set_field_at(2, name="Status", value=f"❌ <@{itx.user.id}> declined the challenge.")
                embed.color = discord.Color.red()
                await original_message.edit(embed=embed, view=None)  # Remove buttons
        except Exception:
            pass

        await itx.response.send_message("❌ Challenge declined.", ephemeral=True)

        if self.room_id:
            bm = get_manager()
            room = bm.get(self.room_id)
            if room:
                bm.remove(room)

        self.stop()
