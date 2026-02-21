from __future__ import annotations
import asyncio
import json
import copy
import json
import math
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple, TYPE_CHECKING

_POKEDEX_FORMS_TABLE_AVAILABLE: Optional[bool] = None


def format_species_name(raw: Optional[str]) -> str:
    """Return a display-friendly Pokémon name (capitalized, hyphenless)."""
    if not raw:
        return "Unknown"
    cleaned = str(raw).replace("_", "-").strip().lower()
    parts = [part.capitalize() for part in cleaned.replace("-", " ").split()]
    return " ".join(parts) if parts else str(raw).strip().title()

from . import special_moves as sm
from .abilities import ABILITY_EFFECTS, get_ability_effect, normalize_ability_name
from .advanced_mechanics import (
    FieldEffects,
    apply_special_weather,
    apply_terrain_move_effects,
    apply_weather_move_effects,
    calculate_crit_chance,
    clear_special_weather,
    does_move_hit,
)
from .advanced_moves import (
    apply_crafty_shield,
    apply_conversion_2,
    apply_entrainment,
    apply_gastro_acid,
    apply_magic_powder,
    apply_mat_block,
    apply_me_first,
    apply_mimic,
    apply_quick_guard,
    apply_relic_song,
    apply_role_play,
    apply_simple_beam,
    apply_skill_swap,
    apply_smack_down,
    apply_sketch,
    apply_soak,
    apply_spit_up,
    apply_spite,
    apply_stockpile,
    apply_swallow,
    apply_teatime,
    apply_telekinesis,
    apply_thousand_arrows,
    apply_wide_guard,
    apply_worry_seed,
    calculate_terrain_power,
    calculate_weather_power,
    can_hit_invulnerable,
    can_use_belch,
    can_use_last_resort,
    check_beak_blast_burn,
    check_crafty_shield,
    check_fusion_boost,
    check_shell_trap_trigger,
    check_weather_accuracy,
    get_assist_move,
    get_copycat_move,
    get_invulnerability_power_boost,
    get_judgment_type,
    get_metronome_move,
    get_mirror_move,
    get_minimize_power_boost,
    get_multi_attack_type,
    get_revelation_dance_type,
    get_sleep_talk_move,
    get_techno_blast_type,
    get_terrain_pulse_type,
    get_weather_ball_type,
    handle_natural_gift,
    handle_stuff_cheeks,
    is_always_crit_move,
    is_grounded,
    setup_focus_punch,
)
from .battle_bond_transform import apply_battle_bond_transform
from .db_adapter import get_form_overrides, get_party_for_engine
from .db_move_effects import (
    apply_stat_changes as db_apply_stat_changes,
    apply_status_effect,
    can_inflict_status,
    check_and_consume_hp_berries,
    get_berry_effect,
    get_move_effects,
)
from .generation import get_generation
from .hazards import clear_hazards
from .hidden_power import calculate_hidden_power_power, calculate_hidden_power_type
from .items import get_item_effect, normalize_item_name
from .max_moves import (
    can_gigantamax,
    get_actual_move_type_for_max_move,
    get_max_move_name,
    get_max_move_power,
    get_non_dynamax_hp,
)
from .move_effects import (
    _get_effective_weight,
    apply_secondary_effect,
    calculate_variable_power,
    get_move_secondary_effect,
    is_status_move,
)
from .move_mechanics import (
    calculate_drain_healing,
    calculate_fixed_damage,
    calculate_ohko_damage,
    calculate_recoil_damage,
    get_move_mechanics,
    get_multi_hit_count,
)
from .moves_loader import get_move, load_move, makes_contact  # <-- uses your DB (power/accuracy/type/category/priority/contact)
from .z_moves import (
    SIGNATURE_Z_MOVES,
    can_use_z_move,
    get_z_move_effect,
    get_z_move_name,
    get_z_move_power,
    is_z_crystal,
)

if TYPE_CHECKING:
    from .panel import BattleState

# ---- type chart (Gen 6+) ----
ALLT = ["Normal","Fire","Water","Electric","Grass","Ice","Fighting","Poison","Ground","Flying","Untyped",
        "Psychic","Bug","Rock","Ghost","Dragon","Dark","Steel","Fairy","Stellar"]
TYPE_MULT: Dict[Tuple[str,str], float] = {(a,b):1.0 for a in ALLT for b in ALLT}
def eff(a,b,x): TYPE_MULT[(a,b)] = x
eff("Normal","Rock",0.5); eff("Normal","Ghost",0.0); eff("Normal","Steel",0.5)
eff("Fire","Fire",0.5); eff("Fire","Water",0.5); eff("Fire","Grass",2); eff("Fire","Ice",2); eff("Fire","Bug",2); eff("Fire","Rock",0.5); eff("Fire","Dragon",0.5); eff("Fire","Steel",2)
eff("Water","Fire",2); eff("Water","Water",0.5); eff("Water","Grass",0.5); eff("Water","Ground",2); eff("Water","Rock",2); eff("Water","Dragon",0.5)
eff("Electric","Water",2); eff("Electric","Electric",0.5); eff("Electric","Grass",0.5); eff("Electric","Ground",0); eff("Electric","Flying",2); eff("Electric","Dragon",0.5)
eff("Grass","Fire",0.5); eff("Grass","Water",2); eff("Grass","Grass",0.5); eff("Grass","Poison",0.5); eff("Grass","Ground",2); eff("Grass","Flying",0.5); eff("Grass","Bug",0.5); eff("Grass","Rock",2); eff("Grass","Dragon",0.5); eff("Grass","Steel",0.5)
eff("Ice","Fire",0.5); eff("Ice","Water",0.5); eff("Ice","Grass",2); eff("Ice","Ground",2); eff("Ice","Flying",2); eff("Ice","Dragon",2); eff("Ice","Steel",0.5)
eff("Fighting","Normal",2); eff("Fighting","Ice",2); eff("Fighting","Rock",2); eff("Fighting","Dark",2); eff("Fighting","Steel",2); eff("Fighting","Poison",0.5); eff("Fighting","Flying",0.5); eff("Fighting","Psychic",0.5); eff("Fighting","Bug",0.5); eff("Fighting","Fairy",0.5); eff("Fighting","Ghost",0.0)
eff("Poison","Grass",2); eff("Poison","Poison",0.5); eff("Poison","Ground",0.5); eff("Poison","Rock",0.5); eff("Poison","Ghost",0.5); eff("Poison","Steel",0); eff("Poison","Fairy",2)
eff("Ground","Fire",2); eff("Ground","Electric",2); eff("Ground","Poison",2); eff("Ground","Rock",2); eff("Ground","Steel",2); eff("Ground","Grass",0.5); eff("Ground","Bug",0.5); eff("Ground","Flying",0)
eff("Flying","Grass",2); eff("Flying","Fighting",2); eff("Flying","Bug",2); eff("Flying","Electric",0.5); eff("Flying","Rock",0.5); eff("Flying","Steel",0.5)
eff("Psychic","Fighting",2); eff("Psychic","Poison",2); eff("Psychic","Psychic",0.5); eff("Psychic","Steel",0.5); eff("Psychic","Dark",0)
eff("Bug","Grass",2); eff("Bug","Psychic",2); eff("Bug","Dark",2); eff("Bug","Fire",0.5); eff("Bug","Fighting",0.5); eff("Bug","Poison",0.5); eff("Bug","Flying",0.5); eff("Bug","Ghost",0.5); eff("Bug","Steel",0.5); eff("Bug","Fairy",0.5)
eff("Rock","Fire",2); eff("Rock","Ice",2); eff("Rock","Flying",2); eff("Rock","Bug",2); eff("Rock","Poison",1); eff("Rock","Fighting",0.5); eff("Rock","Ground",0.5); eff("Rock","Steel",0.5)
eff("Ghost","Psychic",2); eff("Ghost","Ghost",2); eff("Ghost","Dark",0.5); eff("Ghost","Normal",0)
eff("Dragon","Dragon",2); eff("Dragon","Steel",0.5); eff("Dragon","Fairy",0)
eff("Dark","Psychic",2); eff("Dark","Ghost",2); eff("Dark","Fighting",0.5); eff("Dark","Dark",0.5); eff("Dark","Fairy",0.5)
eff("Steel","Ice",2); eff("Steel","Rock",2); eff("Steel","Fairy",2); eff("Steel","Fire",0.5); eff("Steel","Water",0.5); eff("Steel","Electric",0.5); eff("Steel","Steel",0.5)
eff("Fairy","Fighting",2); eff("Fairy","Dragon",2); eff("Fairy","Dark",2); eff("Fairy","Fire",0.5); eff("Fairy","Poison",0.5); eff("Fairy","Steel",0.5)

_MEGA_STONE_SYNONYMS = {
    "lopunnyite": "lopunnite",
    "loppunite": "lopunnite",
}

_MEGA_STONE_DISPLAY_OVERRIDES = {
    "lopunnite": "Lopunnite",
    "lopunnyite": "Lopunnite",
    "loppunite": "Lopunnite",
}

# ---- natures (common set) ----
def _nat(neu=False, up=None, down=None):
    d = dict(atk=1.0, defn=1.0, spa=1.0, spd=1.0, spe=1.0)
    if not neu and up and down: d[up]=1.1; d[down]=0.9
    return d
NATURES: Dict[str, Dict[str, float]] = {
    "Adamant": _nat(up="atk", down="spa"), "Modest": _nat(up="spa", down="atk"),
    "Jolly": _nat(up="spe", down="spa"),   "Timid":  _nat(up="spe", down="atk"),
    "Bold": _nat(up="defn", down="atk"),   "Calm":   _nat(up="spd", down="atk"),
    "Careful": _nat(up="spd", down="spa"),
    "Lonely": _nat(up="atk", down="defn"), "Brave": _nat(up="atk", down="spe"),
    "Naughty": _nat(up="atk", down="spd"), "Impish": _nat(up="defn", down="spa"),
    "Lax": _nat(up="defn", down="spd"), "Relaxed": _nat(up="defn", down="spe"),
    "Mild": _nat(up="spa", down="defn"), "Rash": _nat(up="spa", down="spd"),
    "Quiet": _nat(up="spa", down="spe"), "Gentle": _nat(up="spd", down="defn"),
    "Sassy": _nat(up="spd", down="spe"), "Hasty": _nat(up="spe", down="defn"),
    "Naive": _nat(up="spe", down="spd"),
    "Hardy": _nat(neu=True), "Serious": _nat(neu=True), "Docile": _nat(neu=True),
    "Bashful": _nat(neu=True), "Quirky": _nat(neu=True),
}

@dataclass
class Mon:
    species: str
    level: int
    types: Tuple[str, Optional[str]]
    base: Dict[str,int]
    ivs: Dict[str,int]
    evs: Dict[str,int]
    nature_name: Optional[str] = None
    ability: Optional[str] = None
    item: Optional[str] = None
    shiny: bool = False
    gender: Optional[str] = None
    status: Optional[str] = None
    max_hp: int = 1
    hp: int = 1
    stats: Dict[str,int] = field(default_factory=dict)  # atk/defn/spa/spd/spe
    moves: List[str] = field(default_factory=list)
    status_turns: int = 0  # for sleep/freeze duration
    toxic_counter: int = 0  # for toxic damage progression
    is_fully_evolved: bool = True  # False if can still evolve (for Eviolite)
    weight_kg: float = 0.0  # Weight in kilograms (for Low Kick, Grass Knot, Heavy Slam, Heat Crash)
    friendship: int = 255  # Friendship value (0-255, default max for Return/Frustration)
    capture_rate: int = 45  # Species catch rate used for wild capture rolls
    # Stat stages: -6 to +6 for each stat (accuracy/evasion too)
    stages: Dict[str,int] = field(default_factory=lambda: {
        "atk": 0, "defn": 0, "spa": 0, "spd": 0, "spe": 0, "accuracy": 0, "evasion": 0
    })
    
    # Advanced mechanics (will be initialized in BattleState)
    substitute: Optional[Any] = None  # Substitute object
    must_recharge: bool = False  # For Hyper Beam, etc.
    recharging_move: Optional[str] = None  # Move that requires recharge (similar to charging_move)
    flinched: bool = False  # Flinch this turn
    charging_move: Optional[str] = None  # Move being charged
    charging_turn: int = 0  # Turn counter for charging
    invulnerable: bool = False  # For Fly, Dig, etc.
    invulnerable_type: Optional[str] = None  # "flying", "underground", etc.
    focused_energy: bool = False  # +2 crit stages
    lock_on_target: Optional[Any] = None  # Mind Reader / Lock-On target reference
    lock_on_turns: int = 0  # Turns remaining for perfect accuracy effect
    nightmared: bool = False  # Nightmare status flag
    cursed: bool = False  # Ghost-type Curse flag
    throat_chop_turns: int = 0  # Prevents sound moves (Throat Chop)
    laser_focus_turns: int = 0  # Guaranteed crit window from Laser Focus
    _laser_focus_pending: bool = False  # Whether Laser Focus is awaiting consumption
    
    # Ability-specific flags
    flash_fire_active: bool = False  # Flash Fire boost activated
    _switch_ability_used: bool = False  # Gen 9: Dauntless Shield/Intrepid Sword only once per battle
    _fainted_allies: int = 0  # Supreme Overlord: Count of fainted teammates
    
    # Form changes
    form: Optional[str] = None  # Current form (e.g., "shield", "blade", "disguised", "busted")
    _disguise_broken: bool = False  # Disguise has been busted
    
    # Move restrictions
    encored_move: Optional[str] = None
    encore_turns: int = 0
    disabled_move: Optional[str] = None
    disable_turns: int = 0
    taunted: bool = False
    taunt_turns: int = 0
    tormented: bool = False
    last_move_used: Optional[str] = None
    _last_move_used_type: Optional[str] = None
    
    # Rampage moves (Outrage, Thrash, Petal Dance)
    rampage_move: Optional[str] = None
    rampage_turns_remaining: int = 0
    rollout_move: Optional[str] = None
    rollout_turns_remaining: int = 0
    _rollout_stage: int = 1
    
    _moved_this_turn: bool = False  # Track turn progression for effects like Core Enforcer
    
    # Confusion
    confused: bool = False
    confusion_turns: int = 0
    
    # Drowsiness (Yawn)
    drowsy_turns: int = 0
    drowsy_source: Optional[str] = None
    _yawn_generation: Optional[int] = None
    
    # Trapping
    trapped: bool = False
    trap_source: Optional[str] = None
    partially_trapped: bool = False
    partial_trap_turns: int = 0
    partial_trap_damage: float = 0.0
    jaw_lock_partner: Optional["Mon"] = None
    _jaw_lock_active: bool = False
    _octolock_target: Optional["Mon"] = None
    _octolocked_by: Optional["Mon"] = None
    _octolock_stat_drop: Optional[Dict[str, int]] = None
    _octolock_turns: int = 0
    _tar_shot_active: bool = False
    
    # Protect tracking
    consecutive_protects: int = 0
    protected_this_turn: bool = False
    max_guard_active: bool = False  # Max Guard is active (protects against additional moves)
    endure_active: bool = False
    
    @property
    def display_name(self) -> str:
        return format_species_name(self.species)

    # Dynamax/Gigantamax
    dynamaxed: bool = False  # Is currently Dynamaxed
    dynamax_turns_remaining: int = 0  # Turns remaining (3 turns total)
    is_gigantamax: bool = False  # Is Gigantamax (vs regular Dynamax)
    can_gigantamax: bool = False  # This individual Pokemon can Gigantamax (from database)
    _original_max_hp: Optional[int] = None  # Store original max_hp before Dynamax
    _original_hp: Optional[int] = None  # Store original hp before Dynamax
    
    # Turn-based move tracking (for Fury Cutter, Echoed Voice, etc.)
    consecutive_move_hits: int = 0  # For Fury Cutter (resets on miss/different move)
    echoed_voice_turns: int = 0  # For Echoed Voice (consecutive uses)
    
    # Special requirement tracking
    _moves_used_this_battle: List[str] = field(default_factory=list)  # For Last Resort
    _consumed_berry: bool = False  # For Belch

    # Crit-boost tracking (Focus Energy, Dire Hit)
    focused_energy_stage: int = 0

    # Tracking of incoming moves (for Mirror Move, Counter interactions)
    last_move_targeted: Optional[str] = None
    last_move_target_source: Optional[Any] = None
    
    # Move-specific locks
    _no_retreat_active: bool = False
    
    # Transform tracking - store original data for revert
    _original_species: Optional[str] = None
    _original_types: Optional[Tuple[str, Optional[str]]] = None
    _original_ability: Optional[str] = None
    _original_stats: Optional[Dict[str, int]] = None
    _original_moves: Optional[List[str]] = None
    _original_weight: Optional[float] = None
    _original_form: Optional[str] = None
    _transformed: bool = False  # Is currently transformed
    
    # Terastallization
    tera_type: Optional[str] = None
    terastallized: bool = False
    _tera_original_types: Optional[Tuple[str, Optional[str]]] = None
    _tera_boosted_types: Set[str] = field(default_factory=set)
    _tera_is_stellar: bool = False
    _tera_boost_unlimited: bool = False  # For raid battles / Terapagos Stellar
    _tera_previous_ability: Optional[str] = None
    _tera_sprite_form: Optional[str] = None
    
    # Mega Evolution
    can_mega_evolve: bool = False
    mega_evolutions: Mapping[str, Dict[str, Any]] = field(default_factory=dict)
    mega_evolved: bool = False
    mega_variant: Optional[str] = None
    _mega_original_species: Optional[str] = None
    _mega_original_types: Optional[Tuple[str, Optional[str]]] = None
    _mega_original_ability: Optional[str] = None
    _mega_original_stats: Optional[Dict[str, int]] = None
    _mega_original_base: Optional[Dict[str, int]] = None
    _mega_original_form: Optional[str] = None
    _mega_original_weight: Optional[float] = None
    _mega_original_speed: Optional[int] = None
    _mega_speed_override: Optional[int] = None
    _mega_speed_applied: bool = False
    
    # Store original calculated stats for Beast Boost and similar abilities
    _original_calculated_stats: Optional[Dict[str, int]] = None

    def __post_init__(self):
        """Store original data for Transform revert."""
        if not self._original_species:  # Only store once
            self._original_species = self.species
            self._original_types = tuple(self.types)
            self._original_ability = self.ability
            self._original_stats = dict(self.stats) if self.stats else {}
            self._original_moves = list(self.moves) if self.moves else []
            self._original_weight = self.weight_kg
            self._original_form = self.form
        if not self._tera_original_types:
            self._tera_original_types = tuple(self.types)

# Helper to mark rampage moves (Outrage, Thrash, Petal Dance) as disrupted mid-sequence.
def disrupt_rampage(mon: Mon, field_effects: Any = None, reason: str = "") -> None:
    if not getattr(mon, "rampage_move", None):
        return


    generation = getattr(mon, "_rampage_generation", None)
    if generation is None:
        try:
            generation = get_generation(field_effects=field_effects)
        except Exception:
            generation = 9
    mon._rampage_generation = generation
    mon._rampage_disrupted = True
    mon._rampage_disrupted_reason = reason
    mon._rampage_disrupted_final_turn = getattr(mon, "rampage_turns_remaining", 0) <= 1
    mon.rampage_turns_remaining = 1


def reset_rollout(mon: Mon) -> None:
    """Clear Rollout/Ice Ball locking state and stage tracking."""
    if not hasattr(mon, 'rollout_turns_remaining'):
        return
    mon.rollout_move = None
    mon.rollout_turns_remaining = 0
    mon._rollout_stage = 1


ROLLOUT_MOVES: Set[str] = {"rollout", "ice-ball"}


def handle_rollout_failure(user: Mon, is_rollout_move: bool) -> None:
    """Reset rollout state if the current move fails."""
    if is_rollout_move:
        reset_rollout(user)


def handle_rollout_success(
    user: Mon,
    normalized_move: str,
    is_rollout_move: bool,
    rollout_state_active: bool,
    rollout_stage_current: int,
) -> None:
    """Advance or reset rollout counters when the move succeeds without damage."""
    if not is_rollout_move:
        return
    if not rollout_state_active:
        remaining_turns = 5
        user.rollout_move = normalized_move
    else:
        remaining_turns = max(1, getattr(user, 'rollout_turns_remaining', 1))
    remaining_turns = max(0, remaining_turns - 1)
    user.rollout_turns_remaining = remaining_turns
    if remaining_turns > 0:
        next_stage = min(max(1, rollout_stage_current) + 1, 5)
        user._rollout_stage = next_stage
        user.rollout_move = normalized_move
    else:
        reset_rollout(user)


def apply_jump_kick_crash(
    user: Mon,
    target: Mon,
    move_name: str,
    meta: Optional[Dict[str, Any]],
    field_effects: Any,
) -> str:
    """Apply crash recoil for Jump Kick / High Jump Kick style moves."""
    _bs = getattr(user, "_battle_state", None) or getattr(target, "_battle_state", None)
    mechanics = get_move_mechanics(move_name, _bs)
    if not mechanics or not mechanics.get("crash_damage"):
        return ""

    meta = meta or {}
    generation_crash = get_generation(field_effects=field_effects)
    should_crash = True
    crash = 0

    if generation_crash == 1:
        target_types = [
            t.strip().title() if t else None for t in getattr(target, "types", (None, None))
        ]
        if "Ghost" in target_types:
            should_crash = False

    if not should_crash:
        return ""

    if generation_crash == 1:
        crash = 1
    elif generation_crash == 2:
        if not meta.get("immune", False):
            mv_crash = load_move(move_name)
            if mv_crash:
                est_power = mv_crash.get("power", 100)
                estimated_damage = est_power * getattr(user, "level", 50) // 10
                crash = max(1, estimated_damage // 8)
            else:
                crash = 1
    elif generation_crash == 3:
        mv_crash = load_move(move_name)
        if mv_crash:
            est_power = mv_crash.get("power", 100)
            estimated_damage = est_power * getattr(user, "level", 50) // 10
            crash = max(1, estimated_damage // 2)
        else:
            crash = user.max_hp // 4
    elif generation_crash == 4:
        is_type_immune = meta.get("immune", False)
        if is_type_immune and hasattr(target, "max_hp"):
            crash = target.max_hp // 2
        elif hasattr(target, "max_hp"):
            crash = target.max_hp // 2
        else:
            crash = user.max_hp // 2
    else:
        crash = user.max_hp // 2

    if crash <= 0:
        return ""

    max_hp = max(1, getattr(user, "max_hp", 1))
    percent = max(1, min(100, round((crash / max_hp) * 100)))

    user.hp = max(0, user.hp - crash)
    display_name = user.display_name if hasattr(user, "display_name") else format_species_name(user.species)
    crash_msg = f"\n{display_name} kept going and crashed! (-{percent}%)"
    if user.hp == 0:
        crash_msg += f"\n{display_name} fainted from the crash!"
    return crash_msg


def break_jaw_lock(mon: Mon) -> None:
    """Release Jaw Lock between two Pokémon."""
    if mon is None:
        return
    partner = getattr(mon, "jaw_lock_partner", None)
    if partner is not None and getattr(partner, "jaw_lock_partner", None) is mon:
        partner.jaw_lock_partner = None
        partner._jaw_lock_active = False
        if getattr(partner, "trap_source", None) in {mon.species, "jaw-lock"}:
            partner.trapped = False
            partner.trap_source = None
            if getattr(partner, "trapped_by", None) in {mon.species, "jaw-lock"}:
                partner.trapped_by = None
    mon.jaw_lock_partner = None
    mon._jaw_lock_active = False
    if getattr(mon, "trap_source", None) in {(partner.species if partner else None), "jaw-lock"}:
        mon.trapped = False
        mon.trap_source = None
    if getattr(mon, "trapped_by", None) in {(partner.species if partner else None), "jaw-lock"}:
        mon.trapped_by = None


def release_octolock(mon: Mon) -> None:
    """Release Octolock bindings for a Pokémon (user or target)."""
    if mon is None:
        return
    
    # If mon is the user maintaining an Octolock on a target
    target = getattr(mon, "_octolock_target", None)
    if target is not None and getattr(target, "_octolocked_by", None) is mon:
        target._octolocked_by = None
        target._octolock_stat_drop = None
        if getattr(target, "trap_source", None) == "octolock":
            target.trapped = False
            target.trap_source = None
        if getattr(target, "trapped_by", None) == mon.species:
            target.trapped_by = None
    mon._octolock_target = None
    mon._octolock_stat_drop = None
    
    # If mon is the target currently octolocked by another Pokémon
    locker = getattr(mon, "_octolocked_by", None)
    if locker is not None and getattr(locker, "_octolock_target", None) is mon:
        locker._octolock_target = None
        locker._octolock_stat_drop = None
    mon._octolocked_by = None
    mon._octolock_stat_drop = None
    if getattr(mon, "trap_source", None) == "octolock":
        mon.trapped = False
        mon.trap_source = None
    if getattr(mon, "trapped_by", None) == "octolock":
        mon.trapped_by = None

# ---- Permanent stat formulas: Generation III onward only ----
# HP = floor( ( (2×Base + IV + floor(EV/4)) × Level ) / 100 ) + Level + 10
# OtherStat = floor( ( floor( (2×Base + IV + floor(EV/4)) × Level / 100 ) + 5 ) × Nature )
def _calc_hp(base: int, iv: int, ev: int, level: int) -> int:
    return math.floor(((2*base + iv + math.floor(ev/4)) * level) / 100) + level + 10

def _calc_stat(base: int, iv: int, ev: int, level: int, nature: float) -> int:
    v = math.floor(((2*base + iv + math.floor(ev/4)) * level) / 100) + 5
    return math.floor(v * nature)

def _roll_missing_n0_stats() -> Dict[str, int]:
    """Roll random stats for Missing n0 with sum = 720.
    Ranges: HP 120-200, Atk 90-160, Def 75-145, SpA 90-160, SpD 75-145, Spe 30-150
    """
    # Roll initial stats within ranges
    stats = {
        "hp": random.randint(120, 200),
        "atk": random.randint(90, 160),
        "defn": random.randint(75, 145),
        "spa": random.randint(90, 160),
        "spd": random.randint(75, 145),
        "spe": random.randint(30, 150),
    }
    
    # Calculate current sum and target difference
    current_sum = sum(stats.values())
    target_sum = 720
    diff = target_sum - current_sum
    
    # Adjust stats to reach target sum while staying in ranges
    stat_ranges = {
        "hp": (120, 200),
        "atk": (90, 160),
        "defn": (75, 145),
        "spa": (90, 160),
        "spd": (75, 145),
        "spe": (30, 150),
    }
    
    # If we need to adjust, do it iteratively
    max_iterations = 100
    iteration = 0
    while diff != 0 and iteration < max_iterations:
        iteration += 1
        # Pick a random stat to adjust
        stat_keys = list(stats.keys())
        random.shuffle(stat_keys)
        
        for stat_key in stat_keys:
            if diff == 0:
                break
            
            min_val, max_val = stat_ranges[stat_key]
            current_val = stats[stat_key]
            
            if diff > 0:
                # Need to increase
                increase = min(diff, max_val - current_val)
                if increase > 0:
                    stats[stat_key] += increase
                    diff -= increase
            else:
                # Need to decrease
                decrease = min(abs(diff), current_val - min_val)
                if decrease > 0:
                    stats[stat_key] -= decrease
                    diff += decrease
        
        # Recalculate diff
        current_sum = sum(stats.values())
        diff = target_sum - current_sum
    
    return stats

def _roll_missing_n0_type() -> Tuple[str, Optional[str]]:
    """Roll random type for Missing n0. Returns one of: Normal, Ice, Rock, Steel, Ghost, Untyped."""
    types = ["Normal", "Ice", "Rock", "Steel", "Ghost", "Untyped"]
    rolled_type = random.choice(types)
    return (rolled_type, None)

def _roll_missing_n0_ability() -> str:
    """Roll random ability for Missing n0."""
    abilities = [
        "beast-boost",
        "contrary",
        "clear-body",
        "magic-bounce",
        "mold-breaker",
        "erratic",  # Exclusive ability
        "slow-start",
        "good-as-gold",
        "regenerator",
        # New counter abilities
        "coercion",
        "masquerade",
        "nullscape",
        "deadlock",
        "earthbound",
    ]
    return random.choice(abilities)

def _roll_missing_n0_moves() -> List[str]:
    """Roll random moveset for Missing n0: 1 physical, 1 special, 1 status, 1 hazard."""
    physical_moves = [
        "Bulldoze",
        "Explosion",
        "Stone Edge",
        "Earthquake",
        "Superpower",
        "Rock Slide",
        "Giga Impact",
        "Body Slam",
        "Dynamic Punch",
        "Mega Kick",
        "Seismic Toss",
        "Return",
        "Facade",
        "Avalanche",
        "Double Edge",
        "Power Up Punch",
        "Iron Head",
        "Hammer Arm",
        "Brick Break",
        "Dizzy Punch",
        "Fire Punch",
        "Ice Punch",
        "Gyro Ball",
        "Knock Off",
        "Zen Headbutt",
        "Aerial Ace",
        "Strength",
        "Crunch",
        "Dragon Claw",
        "Outrage",
        "Thrash",
        "Thunder Fang",
        "Fire Fang",
        "Breaking Swipe",
        "Extreme Speed",
        "Bounce",
        "Wild Charge",
        "Scale Shot",
        "U-turn",
        "Shadow Claw",
    ]
    
    special_moves = [
        "Hyper Beam",
        "Thunder",
        "Thunderbolt",
        "Aura Sphere",
        "Ancient Power",
        "Flash Cannon",
        "Zap Cannon",
        "Charge Beam",
        "Icy Wind",
        "Ice Beam",
        "Blizzard",
        "Frost Breath",
        "Earth Power",
        "Power Gem",
        "Dragon Breath",
        "Dragon Energy",
        "Dragon Pulse",
        "Electro Ball",
        "Electro Web",
        "Volt Switch",
        "Thunder Cage",
        "Shock Wave",
        "Rising Voltage",
        "Shadow Ball",
    ]
    
    status_moves = [
        "Curse",
        "Toxic",
        "Sunny Day",
        "Protect",
        "Sandstorm",
        "Rest",
        "Rock Polish",
        "Substitute",
        "Mimic",
        "Swagger",
        "Swords Dance",
        "Thunder Wave",
        "Hail",
        "Amnesia",
        "Calm Mind",
        "Acupressure",
        "Dragon Dance",
        "Magnet Rise",
        "Rain Dance",
        "Agility",
        "Focus Energy",
        "Hypnosis",
    ]
    
    hazard_moves = [
        "Stealth Rock",
        "Spikes",
        "Toxic Spikes",
        "Rapid Spin",
        "Sticky Web",
    ]
    
    # Roll one move from each category
    physical = random.choice(physical_moves)
    special = random.choice(special_moves)
    status = random.choice(status_moves)
    hazard = random.choice(hazard_moves)
    
    # Return as a list of 4 moves
    return [physical, special, status, hazard]


def _normalize_moves_for_pp(moves: Any) -> List[str]:
    """Normalize move names to canonical form (lowercase, hyphens) so PP lookup matches everywhere."""
    if not moves:
        return ["Tackle"]
    out: List[str] = []
    for m in (moves if isinstance(moves, (list, tuple)) else [moves])[:4]:
        s = str(m or "").strip().lower().replace(" ", "-").replace("_", "-")
        if not s:
            s = "tackle"
        out.append(s)
    return out[:4] or ["Tackle"]


def build_mon(dto: Dict[str, Any], *, set_level: int = 100, heal: bool = True) -> Mon:
    """Convert DB row to battle Mon, forcing PvP level and (optionally) full heal."""
    nature_name = dto.get("nature") or ""
    # Case-insensitive nature lookup
    nmods = NATURES.get(nature_name.title()) if nature_name else _nat(neu=True)
    if not nmods:
        nmods = _nat(neu=True)
    level = int(set_level if set_level is not None else dto.get("level", 100))  # OVERRIDE PvP level

    # Note: Missing n0 rolling is now done at battle start in BattleState.__init__
    # This ensures fresh rolls for each battle, not just when loading from database
    base, ivs, evs = dto["base"], dto["ivs"], dto["evs"]
    override_max_hp = dto.get("override_max_hp")
    override_stats = dto.get("override_stats")
    if override_max_hp is not None and isinstance(override_stats, dict) and len(override_stats) >= 5:
        max_hp = int(override_max_hp)
        stats = {
            "atk":  int(override_stats.get("atk", 0)),
            "defn": int(override_stats.get("defn", 0)),
            "spa":  int(override_stats.get("spa", 0)),
            "spd":  int(override_stats.get("spd", 0)),
            "spe":  int(override_stats.get("spe", 0)),
        }
    else:
        max_hp = _calc_hp(base["hp"], ivs["hp"], evs["hp"], level)
        species_name = (dto.get("species") or "").strip().lower()
        if species_name == "shedinja":
            max_hp = 1  # Gen III+: Shedinja's HP is always 1
        stats = {
            "atk":  _calc_stat(base["atk"],  ivs["atk"],  evs["atk"],  level, nmods["atk"]),
            "defn": _calc_stat(base["defn"], ivs["defn"], evs["defn"], level, nmods["defn"]),
            "spa":  _calc_stat(base["spa"],  ivs["spa"],  evs["spa"],  level, nmods["spa"]),
            "spd":  _calc_stat(base["spd"],  ivs["spd"],  evs["spd"],  level, nmods["spd"]),
            "spe":  _calc_stat(base["spe"],  ivs["spe"],  evs["spe"],  level, nmods["spe"]),
        }

    species_name = (dto.get("species") or "").strip().lower()
    if species_name == "shedinja":
        max_hp = 1  # Gen III+: Shedinja's HP is always 1

    hp_now = max_hp if heal else int(dto.get("hp_now", max_hp))
    hp_now = max(1, min(max_hp, hp_now))

    # Restore status from DB (brn/par/psn/slp/frz/tox) - persists across battles until cured
    status_from_dto = dto.get("status")
    status_from_dto = status_from_dto.strip() if isinstance(status_from_dto, str) and status_from_dto else None
    if heal:
        status_from_dto = None  # Full heal clears status
    mon = Mon(
        species=dto["species"], level=level, types=dto["types"], base=base,
        ivs=ivs, evs=evs, nature_name=nature_name, ability=dto.get("ability"),
        item=dto.get("item"), shiny=bool(dto.get("is_shiny")), gender=dto.get("gender"),
        status=status_from_dto, max_hp=max_hp, hp=hp_now, stats=stats,
        moves=_normalize_moves_for_pp(dto.get("moves") or ["Tackle"]),
        is_fully_evolved=bool(dto.get("is_fully_evolved", True)),  # For Eviolite
        weight_kg=float(dto.get("weight_kg", 100.0)),  # Weight for Low Kick/Grass Knot
        friendship=int(dto.get("friendship", 255)),  # Friendship for Return/Frustration
        capture_rate=max(1, min(255, int(float(dto.get("capture_rate", 45) or 45)))),
    )
    # Store original calculated stats for Beast Boost (before any modifications)
    mon._original_calculated_stats = dict(stats)
    # Experience (for EXP bar and level-from-exp); Gen III+ groups: erratic, fast, medium_fast, medium_slow, slow, fluctuating
    exp_val = dto.get("exp")
    mon._exp = int(exp_val) if exp_val is not None else None
    mon._exp_group = (dto.get("exp_group") or "medium_fast").strip().lower().replace(" ", "_") if dto.get("exp_group") else "medium_fast"
    # Set form attribute if present
    if "form" in dto and dto["form"]:
        mon.form = dto["form"]
    # Set can_gigantamax attribute if present (from database)
    if "can_gigantamax" in dto:
        mon.can_gigantamax = bool(dto.get("can_gigantamax", False))
    # Terastallization metadata
    tera_raw = dto.get("tera_type")
    if tera_raw:
        normalized = str(tera_raw).strip()
        if normalized:
            formatted = normalized.replace("_", " ").replace("-", " ").title().replace(" ", "")
            mon.tera_type = formatted
            if mon.tera_type.lower() == "stellar":
                mon._tera_is_stellar = True
                if mon.species.lower().startswith("terapagos"):
                    mon._tera_boost_unlimited = True
    mon._tera_original_types = tuple(mon.types)
    # Mega Evolution metadata
    mega_data = dto.get("mega_evolutions") or {}
    if isinstance(mega_data, dict):
        mon.mega_evolutions = mega_data
    mon.can_mega_evolve = bool(mon.mega_evolutions)
    mon._mega_original_species = mon.species
    mon._mega_original_types = tuple(mon.types)
    mon._mega_original_ability = mon.ability
    mon._mega_original_stats = dict(mon.stats)
    mon._mega_original_base = dict(mon.base)
    mon._mega_original_form = mon.form
    mon._mega_original_weight = mon.weight_kg
    mon._mega_original_speed = mon.stats.get("spe")
    mon._mega_speed_override = None
    # Store database ID for saving Missing n0 stats after battle
    if "id" in dto:
        mon._db_id = dto["id"]
    return mon

# ---- Stat Stages System ----
# Gen I-II: fractions with denominator 100 (negative) or numerator/100 (positive)
# Gen III+: formula 2/(2+N) for negative, (2+N)/2 for positive (Attack, Defense, SpA, SpD, Speed)
STAGE_MULTIPLIERS_GEN1_2 = {
    -6: 25/100, -5: 28/100, -4: 33/100, -3: 40/100, -2: 50/100, -1: 66/100,
    0: 1.0,
    1: 150/100, 2: 200/100, 3: 250/100, 4: 300/100, 5: 350/100, 6: 400/100
}
STAGE_MULTIPLIERS = {
    -6: 2/8, -5: 2/7, -4: 2/6, -3: 2/5, -2: 2/4, -1: 2/3,
    0: 1.0,
    1: 3/2, 2: 4/2, 3: 5/2, 4: 6/2, 5: 7/2, 6: 8/2
}

def get_stage_multiplier(stage: int, generation: Optional[int] = None) -> float:
    """Get the multiplier for a given stat stage (-6 to +6). Gen 1-2 use different fractions than Gen III+."""
    stage = max(-6, min(6, stage))
    if generation is not None and generation <= 2:
        return STAGE_MULTIPLIERS_GEN1_2.get(stage, 1.0)
    return STAGE_MULTIPLIERS.get(stage, 1.0)

# Gen I-II: move accuracy is 0-255. Nominal % → actual (X/256). Table from core series.
NOMINAL_ACCURACY_TO_255 = {
    100: 255, 95: 242, 90: 229, 85: 216, 80: 204, 75: 191, 70: 178, 65: 165,
    60: 153, 55: 140, 50: 127, 30: 76
}

def _nominal_accuracy_to_255(acc: Optional[int]) -> int:
    """Convert nominal accuracy (0-100) to Gen I/II 0-255 scale. Returns 1-255 for valid acc, 255 for None/100."""
    if acc is None or acc <= 0:
        return 255  # never-miss
    if acc in NOMINAL_ACCURACY_TO_255:
        return NOMINAL_ACCURACY_TO_255[acc]
    return max(1, min(255, int(round(acc * 255 / 100))))

def item_is_active(mon: Mon) -> bool:
    """Check if a Mon's held item effects are active (not just received this turn)."""
    if not mon.item:
        return False
    # Items received via Trick/Switcheroo don't activate until next turn
    if getattr(mon, '_item_just_received', False):
        return False
    field_effects = getattr(mon, '_field_effects', None)
    if field_effects and getattr(field_effects, 'magic_room', False):
        return False
    return True


# Cache for unremovable items (mega stones, Z-crystals, etc.)
_UNREMOVABLE_ITEMS_CACHE: Optional[set] = None

def _get_unremovable_items_from_db() -> set:
    """Query database to get all items that cannot be knocked off (mega stones, Z-crystals, etc.)."""
    global _UNREMOVABLE_ITEMS_CACHE
    if _UNREMOVABLE_ITEMS_CACHE is not None:
        return _UNREMOVABLE_ITEMS_CACHE
    
    unremovable = set()
    
    try:
        from .db_pool import get_connection
        from .z_moves import is_z_crystal
        from .items import get_item_effect, normalize_item_name
        
        with get_connection() as conn:
            # Get all items from database
            cur = conn.execute("SELECT id FROM items")
            all_items = [row[0] for row in cur.fetchall()]
            
            for item_id in all_items:
                item_norm = normalize_item_name(item_id)
                item_data = get_item_effect(item_norm)
                
                # Check if it's a mega stone
                if item_data.get("mega_stone"):
                    unremovable.add(item_norm)
                
                # Check if it's a Z-crystal
                if is_z_crystal(item_id):
                    unremovable.add(item_norm)
                
                # Check if marked as unremovable
                if item_data.get("unremovable_in_battle"):
                    unremovable.add(item_norm)
                
                # Check for special items that can't be knocked off
                # Plates (for Arceus)
                if "plate" in item_norm:
                    unremovable.add(item_norm)
                
                # Memories (for Silvally)
                if "memory" in item_norm:
                    unremovable.add(item_norm)
                
                # Drives (for Genesect)
                if item_norm.endswith("-drive"):
                    unremovable.add(item_norm)
                
                # Rusted Sword/Shield (for Zacian/Zamazenta)
                if item_norm in ["rusted-sword", "rusted-shield"]:
                    unremovable.add(item_norm)
                
                # Booster Energy (for Paradox Pokémon, except Koraidon/Miraidon)
                if item_norm == "booster-energy":
                    unremovable.add(item_norm)
                
                # Ogerpon masks
                if item_norm in ["hearthflame-mask", "wellspring-mask", "cornerstone-mask"]:
                    unremovable.add(item_norm)
                
                # Primal Orbs
                if item_norm in ["red-orb", "blue-orb"]:
                    unremovable.add(item_norm)
        
        _UNREMOVABLE_ITEMS_CACHE = unremovable
    except Exception as e:
        # If database query fails, fall back to empty set (will use item_data checks instead)
        print(f"[Warning] Failed to load unremovable items from database: {e}")
        _UNREMOVABLE_ITEMS_CACHE = set()
    
    return _UNREMOVABLE_ITEMS_CACHE

def can_remove_item_from_target(
    target: Mon,
    remover: Optional[Mon] = None,
    *,
    field_effects: Any = None,
    allow_if_target_fainted: bool = False,
    cause: str = ""
) -> Tuple[bool, Optional[str]]:
    """
    Determine whether the target's held item can be removed.
    Returns (can_remove, failure_message).
    """
    if not getattr(target, "item", None):
        return False, None

    generation = get_generation(field_effects=field_effects)
    item_norm = normalize_item_name(target.item)
    item_data = get_item_effect(item_norm)
    target_species_lower = (target.species or "").lower()
    remover_species_lower = (remover.species or "").lower() if remover and getattr(remover, "species", None) else ""

    ability_suppressed = getattr(target, "_ability_suppressed", False)
    target_ability = normalize_ability_name(getattr(target, "ability", "") or "")

    # Sticky Hold prevents item removal unless the target has fainted and removal on faint is allowed
    if (
        target_ability == "sticky-hold"
        and not ability_suppressed
        and (target.hp > 0 or not allow_if_target_fainted)
    ):
        return False, f"{target.species}'s Sticky Hold keeps its item!"

    if target_ability == "multitype" and not ability_suppressed:
        return False, f"{target.species}'s Multitype keeps its item!"
    if target_ability == "rks-system" and not ability_suppressed:
        return False, f"{target.species}'s RKS System keeps its item!"

    # Unremovable items (e.g., Primal Orbs, certain key items)
    if item_data.get("unremovable_in_battle"):
        return False, f"{target.species}'s {target.item} can't be removed!"

    # Gen VI+: Check database for unremovable items (mega stones, Z-crystals, etc.)
    if generation >= 6:
        unremovable_items = _get_unremovable_items_from_db()
        
        # Check if item is in the unremovable list
        if item_norm in unremovable_items:
            # For mega stones, check if target can actually use it
            if item_data.get("mega_stone"):
                mega_holder = item_data.get("mega_stone")
                if mega_holder and mega_holder in target_species_lower:
                    can_mega, _, _ = can_mega_evolve(target, state=None, generation=generation)
                    if can_mega and not getattr(target, "mega_evolved", False):
                        return False, f"{target.species}'s {target.item} can't be removed!"
                else:
                    # Check if target can mega evolve and item matches
                    can_mega, _, _ = can_mega_evolve(target, state=None, generation=generation)
                    if can_mega and not getattr(target, "mega_evolved", False):
                        # Try to match item name to species
                        item_base = item_norm.replace("-ite", "").replace("-x", "").replace("-y", "").replace("-mega", "")
                        species_base = target_species_lower.split("-")[0]
                        if species_base in item_base or item_base.replace("-", "") in species_base:
                            return False, f"{target.species}'s {target.item} can't be removed!"
            
            # Z-Crystals: Cannot be removed from any Pokémon
            from .z_moves import is_z_crystal
            if is_z_crystal(target.item):
                return False, f"{target.species}'s {target.item} can't be removed!"
            
            # Primal Orbs: Check if target can use it
            if item_norm in ["red-orb", "blue-orb"]:
                if ("groudon" in target_species_lower and item_norm == "red-orb") or \
                   ("kyogre" in target_species_lower and item_norm == "blue-orb"):
                    if not getattr(target, "primal_reversion", False):
                        return False, f"{target.species}'s {target.item} can't be removed!"

            # Plates: Cannot be removed if target is Arceus
            if "plate" in item_norm:
                if "arceus" in target_species_lower:
                    return False, f"{target.species}'s {target.item} can't be removed!"

            # Memories: Cannot be removed if target is Silvally
            if "memory" in item_norm:
                if "silvally" in target_species_lower:
                    return False, f"{target.species}'s {target.item} can't be removed!"

            # Drives: Cannot be removed if target is Genesect
            if item_norm.endswith("-drive"):
                if "genesect" in target_species_lower:
                    return False, f"{target.species}'s {target.item} can't be removed!"

            # Rusted Sword/Shield: Cannot be removed if target is Zacian/Zamazenta
            if item_norm == "rusted-sword" and "zacian" in target_species_lower:
                return False, f"{target.species}'s {target.item} can't be removed!"
            if item_norm == "rusted-shield" and "zamazenta" in target_species_lower:
                return False, f"{target.species}'s {target.item} can't be removed!"

            # Booster Energy: Cannot be removed from Paradox Pokémon (except Koraidon/Miraidon)
            if item_norm == "booster-energy":
                paradox_species = {
                    "sandy-shocks", "scream-tail", "brute-bonnet", "flutter-mane",
                    "slither-wing", "great-tusk", "iron-treads", "iron-bundle",
                    "iron-hands", "iron-jugulis", "iron-moth", "iron-thorns",
                    "iron-valiant", "roaring-moon", "iron-leaves", "walking-wake"
                }
                excluded_species = {"koraidon", "miraidon"}
                if (any(name in target_species_lower for name in paradox_species) and 
                    not any(name in target_species_lower for name in excluded_species)):
                    return False, f"{target.species}'s {target.item} can't be removed!"

            # Ogerpon masks: Cannot be removed if target is Ogerpon
            if item_norm in ["hearthflame-mask", "wellspring-mask", "cornerstone-mask"]:
                if "ogerpon" in target_species_lower:
                    return False, f"{target.species}'s {target.item} can't be removed!"

    return True, None

def modify_stages(mon: Mon, changes: Dict[str, int], caused_by_opponent: bool = False, field_effects: Any = None) -> List[str]:
    """
    Modify stat stages and return messages about changes.
    changes = {"atk": +2, "defn": -1, etc.}
    Respects stat drop immunity abilities like Clear Body, Hyper Cutter, etc.
    
    Args:
        mon: Pokemon whose stats to modify
        changes: Dictionary of stat changes
        caused_by_opponent: True if stats are being lowered by an opponent (for Competitive/Defiant)
    """
    messages = []
    
    # === NULLSCAPE (Steel): Immune to stat drops ===
    nullscape_type = _get_nullscape_type(mon, getattr(mon, '_battle_state', None))
    if nullscape_type == "Steel" and caused_by_opponent:
        # Steel Nullscape: Immune to stat drops
        # Check if any stat is being lowered
        if any(change < 0 for change in changes.values()):
            messages.append(f"{mon.species}'s Nullscape prevents stat reduction!")
            return messages  # Block all stat drops
    
    # Check for stat modification abilities
    ability = normalize_ability_name(mon.ability or "")
    ability_data = get_ability_effect(ability)
    stat_drop_immunity = ability_data.get("stat_drop_immunity")
    
    # Contrary: Invert all stat changes
    if ability_data.get("inverts_stat_changes"):
        changes = {stat: -value for stat, value in changes.items()}
        if any(changes.values()):
            ability_name = (mon.ability or ability).replace("-", " ").title()
            messages.append(f"{mon.species}'s {ability_name} reversed stat changes!")
    
    # Simple: Double all stat changes
    if ability_data.get("doubles_stat_changes"):
        changes = {stat: value * 2 for stat, value in changes.items()}
        if any(changes.values()):
            ability_name = (mon.ability or ability).replace("-", " ").title()
            messages.append(f"{mon.species}'s {ability_name} doubled stat changes!")
    
    # Track how many stats were lowered for Defiant/Competitive (activates for EACH stat)
    stats_lowered_count = 0

    stat_aliases = {
        "attack": "atk",
        "atk": "atk",
        "defense": "defn",
        "def": "defn",
        "defn": "defn",
        "special_attack": "spa",
        "special_atk": "spa",
        "sp_attack": "spa",
        "sp_atk": "spa",
        "spatk": "spa",
        "spa": "spa",
        "special_defense": "spd",
        "special_def": "spd",
        "sp_defense": "spd",
        "sp_def": "spd",
        "spdef": "spd",
        "spd": "spd",
        "speed": "spe",
        "spe": "spe",
        "accuracy": "accuracy",
        "acc": "accuracy",
        "evasion": "evasion",
        "evasiveness": "evasion",
        "special": "special",
    }
    # Keep stage storage canonical so stat-changing status moves (e.g. Growl) apply
    # reliably even if upstream data uses alias keys like "attack"/"defense".
    if not isinstance(getattr(mon, "stages", None), dict):
        mon.stages = {}
    for stage_alias, stage_key in stat_aliases.items():
        if stage_alias == stage_key or stage_alias == "special":
            continue
        if stage_alias not in mon.stages:
            continue
        try:
            alias_val = int(mon.stages.get(stage_alias, 0))
        except Exception:
            alias_val = 0
        try:
            base_val = int(mon.stages.get(stage_key, 0))
        except Exception:
            base_val = 0
        mon.stages[stage_key] = base_val + alias_val
        mon.stages.pop(stage_alias, None)
    for stage_key in ("atk", "defn", "spa", "spd", "spe", "accuracy", "evasion"):
        mon.stages.setdefault(stage_key, 0)

    normalized_changes: Dict[str, int] = {}
    for raw_stat, raw_change in dict(changes or {}).items():
        key_raw = str(raw_stat or "").strip().lower().replace(" ", "_").replace("-", "_")
        key = stat_aliases.get(key_raw, key_raw)
        # Gen 1 "special" may appear in data; if no combined stage is tracked,
        # apply to Sp. Atk as the best available canonical fallback.
        if key == "special" and "special" not in mon.stages:
            key = "spa"
        try:
            delta = int(raw_change)
        except Exception:
            continue
        if delta == 0:
            continue
        normalized_changes[key] = int(normalized_changes.get(key, 0)) + delta
    changes = normalized_changes
    
    for stat, change in changes.items():
        if stat not in mon.stages:
            # Debug: This stat key doesn't exist in stages
            print(f"[DEBUG] Stat '{stat}' not found in {mon.species}'s stages dict: {list(mon.stages.keys())}")
            continue
        
        # Check if this stat drop is blocked by ability or item
        # Clear Body, White Smoke, Full Metal Body: Only prevent opponent-caused stat drops, NOT self-inflicted ones
        if change < 0 and stat_drop_immunity and caused_by_opponent:
            # Full immunity (Clear Body, White Smoke, Full Metal Body)
            if stat_drop_immunity is True:
                ability_name = (mon.ability or ability).replace("-", " ").title()
                messages.append(f"{mon.species}'s {ability_name} prevents stat reduction!")
                continue
            # Specific stat immunity (Hyper Cutter, Keen Eye, Big Pecks)
            elif isinstance(stat_drop_immunity, list) and stat in stat_drop_immunity:
                ability_name = (mon.ability or ability).replace("-", " ").title()
                messages.append(f"{mon.species}'s {ability_name} prevents stat reduction!")
                continue
        # Mist: Protects from stat drops (Gen I: opponent status moves only, Gen II+: all opponent moves/abilities, Gen III+: side effect)
        if change < 0 and caused_by_opponent:
            gen_mist = get_generation(field_effects=field_effects) if field_effects else 9
            
            # Check if Mist is active
            mist_active = False
            if field_effects:
                # Gen III+: Side effect (checked via side_effects, which should be passed or on mon)
                if gen_mist >= 3:
                    # Check if mon has side effects reference
                    if hasattr(mon, '_side_effects') and mon._side_effects:
                        if getattr(mon._side_effects, 'mist', False):
                            mist_active = True
                    # Fallback: check via battle_state if available
                    elif hasattr(mon, '_battle_state') and mon._battle_state:
                        try:
                            if hasattr(mon._battle_state, 'p1_id'):
                                p1_active = mon._battle_state._active(mon._battle_state.p1_id)
                                if p1_active == mon:
                                    side_effects = mon._battle_state.p1_side
                                else:
                                    side_effects = mon._battle_state.p2_side
                                if side_effects and getattr(side_effects, 'mist', False):
                                    mist_active = True
                        except:
                            pass
                else:
                    # Gen I-II: Per-Pokemon flag
                    if hasattr(mon, 'mist_protected') and mon.mist_protected:
                        mist_active = True
            
            if mist_active:
                messages.append(f"{mon.species} is protected by Mist!")
                continue
            
            # Clear Amulet: prevents stat drops from opponent's moves/abilities (Gen 9+)
            if item_is_active(mon) and mon.item:
                i_norm = normalize_item_name(mon.item)
                i_data = get_item_effect(i_norm)
                if i_data.get("prevents_stat_drops"):
                    if gen_mist >= 9:
                        messages.append(f"{mon.species}'s Clear Amulet prevents stat reduction!")
                        continue
        
        # Track stat lowering for Defiant/Competitive (counts each stat lowered)
        if change < 0:
            stats_lowered_count += 1
        
        old_stage = mon.stages[stat]
        new_stage = max(-6, min(6, old_stage + change))
        actual_change = new_stage - old_stage
        
        if actual_change == 0:
            if change > 0:
                messages.append(f"{mon.species}'s {stat.upper()} won't go any higher!")
            elif change < 0:
                messages.append(f"{mon.species}'s {stat.upper()} won't go any lower!")
        else:
            mon.stages[stat] = new_stage
            if actual_change > 0:
                mon._stats_raised_this_turn = True
            elif actual_change < 0:
                mon._stats_lowered_this_turn = True
            
            # Format message based on change amount
            stat_name = {
                "atk": "Attack", "defn": "Defense", "spa": "Special Attack",
                "spd": "Special Defense", "spe": "Speed", 
                "accuracy": "Accuracy", "evasion": "Evasiveness"
            }.get(stat, stat.upper())
            
            if actual_change == 1:
                messages.append(f"{mon.species}'s {stat_name} rose!")
            elif actual_change == 2:
                messages.append(f"{mon.species}'s {stat_name} rose sharply!")
            elif actual_change >= 3:
                messages.append(f"{mon.species}'s {stat_name} rose drastically!")
            elif actual_change == -1:
                messages.append(f"{mon.species}'s {stat_name} fell!")
            elif actual_change == -2:
                messages.append(f"{mon.species}'s {stat_name} fell sharply!")
            elif actual_change <= -3:
                messages.append(f"{mon.species}'s {stat_name} fell drastically!")
    
    # === DEFIANT/COMPETITIVE: Boost when stats are lowered BY AN OPPONENT ===
    # Bulbapedia: "Competitive will not activate if the Pokémon with this Ability lowers its own stats"
    # Bulbapedia: "If multiple stats are lowered... Competitive activates for each stat lowered"
    if caused_by_opponent and stats_lowered_count > 0 and ability_data.get("stat_drop_boost"):
        boost_changes = ability_data["stat_drop_boost"]
        
        # Apply boost ONCE for EACH stat lowered
        for _ in range(stats_lowered_count):
            for boost_stat, boost_amount in boost_changes.items():
                if boost_stat in mon.stages:
                    old = mon.stages[boost_stat]
                    mon.stages[boost_stat] = max(-6, min(6, old + boost_amount))
                    actual = mon.stages[boost_stat] - old
                    if actual > 0:
                        ability_name = (mon.ability or ability).replace("-", " ").title()
                        messages.append(f"{mon.species}'s {ability_name} activated!")
                        if actual == 1:
                            messages.append(f"{mon.species}'s {boost_stat.upper()} rose!")
                        elif actual >= 2:
                            messages.append(f"{mon.species}'s {boost_stat.upper()} rose sharply!")
    
    # === WHITE HERB: Reset negative stat changes ===
    if item_is_active(mon):
        item_data = get_item_effect(normalize_item_name(mon.item))
        if item_data.get("resets_negative_stats"):
            has_negative = any(stage < 0 for stage in mon.stages.values())
            if has_negative:
                for stat in list(mon.stages.keys()):
                    if mon.stages[stat] < 0:
                        mon.stages[stat] = 0
                mon.item = None
                messages.append(f"{mon.species}'s **White Herb** restored its stats!")
    
    # === MIRROR HERB: Copy opponent's stat boosts (Gen 9+) ===
    # Triggers when opponent's stats are raised
    if item_is_active(mon) and mon.item:
        item_data_mh = get_item_effect(normalize_item_name(mon.item))
        gen_mh = get_generation(field_effects=field_effects)
        if item_data_mh.get("copies_stat_boosts") and gen_mh >= 9:
            # Check if opponent raised stats (via caused_by_opponent=False and positive changes)
            # This is called from modify_stages, so we need to check opponent's stats
            # Mirror Herb triggers when opponent uses a stat-raising move
            # Note: This will be handled separately when opponent's stats are raised
            pass  # Handled in opponent stat boost check
    
    return messages

def get_effective_stat(mon: Mon, stat: str) -> float:
    """Get the effective stat value including stage modifiers, item boosts, ability modifiers, and form changes."""

    requested_stat = stat
    field_effects = getattr(mon, '_field_effects', None)
    actual_stat = stat

    # Wonder Room swaps the Defense and Special Defense stats
    if field_effects and getattr(field_effects, 'wonder_room', False):
        if stat == "defn":
            actual_stat = "spd"
        elif stat == "spd":
            actual_stat = "defn"

    base_stat = mon.stats.get(actual_stat, 1)
    stage = mon.stages.get(actual_stat, 0)

    # Apply form-based stat modifiers first (affects base stats)
    form_mods = apply_form_stat_modifiers(mon)
    if actual_stat in form_mods:
        base_stat *= form_mods[actual_stat]

    # Apply stat stage multiplier (Gen I-II use different fractions than Gen III+)
    battle_state = getattr(mon, '_battle_state', None)
    generation = get_generation(battle_state=battle_state, field_effects=field_effects)
    multiplier = get_stage_multiplier(stage, generation=generation)
    effective_stat = base_stat * multiplier

    # Apply ability stat multipliers (Huge Power, Pure Power, etc.)
    if mon.ability and not getattr(mon, "_ability_suppressed", False):
        ability_data = get_ability_effect(normalize_ability_name(mon.ability))
        if "stat_mult" in ability_data and actual_stat in ability_data["stat_mult"]:
            effective_stat *= ability_data["stat_mult"][actual_stat]

        # Status-based stat boosts (Guts, Marvel Scale, Toxic Boost, Flare Boost)
        if mon.status:
            if requested_stat == "atk" and ability_data.get("attack_mult_status"):
                effective_stat *= ability_data["attack_mult_status"]
            elif requested_stat == "defn" and ability_data.get("defense_mult_status"):
                effective_stat *= ability_data["defense_mult_status"]
            elif requested_stat == "atk" and ability_data.get("attack_mult_poison") and mon.status in ["psn", "tox"]:
                effective_stat *= ability_data["attack_mult_poison"]
            elif requested_stat == "spa" and ability_data.get("spa_mult_burn") and mon.status == "brn":
                effective_stat *= ability_data["spa_mult_burn"]

        # Quark Drive / Protosynthesis boost
        if hasattr(mon, '_paradox_boosted_stat') and mon._paradox_boosted_stat == requested_stat:
            effective_stat *= 5325 / 4096  # ≈1.3003

        # Torrent/Blaze/Overgrow/Swarm: Gen 5+ boosts Attack/SpA when HP is low
        if "boost_type" in ability_data and requested_stat in ["atk", "spa"]:
            generation = 9
            if hasattr(mon, '_battle_context') and mon._battle_context:
                generation = get_generation(field_effects=mon._battle_context.get('field_effects'))
            if generation >= 5:
                hp_ratio = mon.hp / mon.max_hp if mon.max_hp > 0 else 1.0
                if hp_ratio <= ability_data.get("threshold", 0.33):
                    effective_stat *= ability_data.get("multiplier", 1.5)

        # Slow Start: halve Attack and Speed for 5 turns
        # Note: This is NOT a stat stage change, so it affects Foul Play and Body Press
        ability_norm = normalize_ability_name(mon.ability)
        if ability_norm == "slow-start" and not getattr(mon, "_ability_suppressed", False):
            if not hasattr(mon, '_slow_start_turns'):
                mon._slow_start_turns = 5
            if mon._slow_start_turns > 0 and requested_stat in ["atk", "spe"]:
                effective_stat *= 0.5
        
        # === NULLSCAPE (Ice): 25% speed reduction for non-Ice Pokémon ===
        if requested_stat == "spe":
            nullscape_type_speed = _get_nullscape_type(mon, getattr(mon, '_battle_state', None))
            if nullscape_type_speed == "Ice":
                mon_types = [t.strip().title() if t else None for t in mon.types]
                if "Ice" not in mon_types:
                    effective_stat *= 0.75  # 25% reduction

    # Apply item stat multipliers (Choice Scarf, Assault Vest, Eviolite, etc.)
    if item_is_active(mon):
        item_data = get_item_effect(normalize_item_name(mon.item))

        generation = 9
        if hasattr(mon, '_battle_context') and mon._battle_context:
            generation = get_generation(field_effects=mon._battle_context.get('field_effects'))

        min_gen = item_data.get("min_gen", 1)
        if generation >= min_gen:
            if "gen_specific" in item_data:
                gen_effects = item_data["gen_specific"]
                applied = False
                for gen_range, effects in gen_effects.items():
                    if "-" in gen_range:
                        start, end = gen_range.split("-")
                        if int(start) <= generation <= int(end):
                            if "stat_mult" in effects and actual_stat in effects["stat_mult"]:
                                if "holder" in item_data:
                                    holder_species = item_data["holder"]
                                    if isinstance(holder_species, list):
                                        if mon.species.lower() in [s.lower() for s in holder_species]:
                                            effective_stat *= effects["stat_mult"][actual_stat]
                                            applied = True
                                    elif mon.species.lower() == holder_species.lower():
                                        effective_stat *= effects["stat_mult"][actual_stat]
                                        applied = True
                            break
                    elif "+" in gen_range:
                        start = gen_range.replace("+", "")
                        if generation >= int(start):
                            if "stat_mult" in effects and actual_stat in effects["stat_mult"]:
                                if "holder" in item_data:
                                    holder_species = item_data["holder"]
                                    if isinstance(holder_species, list):
                                        if mon.species.lower() in [s.lower() for s in holder_species]:
                                            effective_stat *= effects["stat_mult"][actual_stat]
                                            applied = True
                                    elif mon.species.lower() == holder_species.lower():
                                        effective_stat *= effects["stat_mult"][actual_stat]
                                        applied = True
                            break
            elif "stat_mult" in item_data and actual_stat in item_data["stat_mult"]:
                if item_data.get("unevolved_only"):
                    if hasattr(mon, 'is_fully_evolved') and not mon.is_fully_evolved:
                        effective_stat *= item_data["stat_mult"][actual_stat]
                elif "holder" in item_data:
                    holder_species = item_data["holder"]
                    if isinstance(holder_species, list):
                        if mon.species.lower() in [s.lower() for s in holder_species]:
                            effective_stat *= item_data["stat_mult"][actual_stat]
                    elif mon.species.lower() == holder_species.lower():
                        effective_stat *= item_data["stat_mult"][actual_stat]
                else:
                    effective_stat *= item_data["stat_mult"][actual_stat]

    # Ruin abilities (Tablets/Sword/Vessel/Beads): lower stat by 25% for all Pokémon except the holder; effect does not stack
    if requested_stat in ("atk", "defn", "spa", "spd"):
        ruin_ability_map = {"atk": "tablets-of-ruin", "defn": "sword-of-ruin", "spa": "vessel-of-ruin", "spd": "beads-of-ruin"}
        ability_name = ruin_ability_map.get(requested_stat)
        if ability_name and battle_state:
            all_mons = []
            if hasattr(battle_state, "p1_party"):
                all_mons.extend([m for m in battle_state.p1_party if m and m.hp > 0])
            if hasattr(battle_state, "p2_party"):
                all_mons.extend([m for m in battle_state.p2_party if m and m.hp > 0])
            for other in all_mons:
                if other is not mon and normalize_ability_name(other.ability or "") == ability_name:
                    effective_stat *= 0.75
                    break

    return effective_stat

def is_weather_negated(all_mons: List[Mon]) -> bool:
    """
    Check if weather effects are negated by Air Lock or Cloud Nine.
    These abilities negate weather effects for ALL Pokemon on the field.
    """
    
    for mon in all_mons:
        if mon and mon.hp > 0:
            ability = normalize_ability_name(mon.ability or "")
            ability_data = get_ability_effect(ability)
            if ability_data.get("weather_negation"):
                return True
    return False

def apply_status_effects(mon: Mon, opponent: Mon = None, field_effects: Any = None, all_mons: List[Mon] = None) -> List[str]:
    """
    Apply status condition effects and passive healing/damage at the end of turn. 
    
    Args:
        mon: The Pokemon to apply effects to
        opponent: The opposing Pokemon (optional)
        field_effects: Field conditions (weather, terrain, etc.)
        all_mons: All Pokemon on the field (for checking Air Lock/Cloud Nine)
    
    Returns list of messages.
    """
    messages = []
    
    # Get generation for generation-specific mechanics
    generation = get_generation(field_effects=field_effects)
    
    # === STATUS-CURING BERRIES (immediate cure at turn processing) ===
    if item_is_active(mon) and mon.item:
        item_norm = normalize_item_name(mon.item)
        item_data = get_item_effect(item_norm)
        cures = item_data.get("heals_status") or item_data.get("cures_status")
        if cures:
            # Normalize status names
            current = (mon.status or "").lower()
            # Cure main status
            should_cure = (cures == "all") or (cures in [current, "psn" if current == "poison" else current])
            # Cure confusion (Persim/Touga)
            if cures == "confusion" and getattr(mon, 'confused', False):
                mon.confused = False
                mon.confusion_turns = 0
                berry_name = mon.item.replace('-', ' ').title()
                mon._last_consumed_berry = mon.item
                mon.item = None
                messages.append(f"{mon.species}'s {berry_name} cured its confusion!")
            elif mon.status and should_cure:
                old = mon.status
                mon.status = None
                berry_name = mon.item.replace('-', ' ').title()
                mon._last_consumed_berry = mon.item
                mon.item = None
                messages.append(f"{mon.species}'s {berry_name} cured its {old}!")

    # === CHECK FOR WEATHER NEGATION (Air Lock / Cloud Nine) ===
    weather_negated = False
    if all_mons:
        weather_negated = is_weather_negated(all_mons)
    
    # === WEATHER-BASED ABILITY EFFECTS ===
    if field_effects and hasattr(field_effects, 'weather') and not weather_negated:
        weather = field_effects.weather
        ability = normalize_ability_name(mon.ability or "")
        ability_data = get_ability_effect(ability)
        
        # Rain Dish, Ice Body - heal 1/16 HP in specific weather
        if "weather_heal" in ability_data and weather in ability_data["weather_heal"]:
            if mon.hp > 0 and mon.hp < mon.max_hp:
                heal_percent = ability_data["weather_heal"][weather]
                heal = max(1, int(mon.max_hp * heal_percent))
                old_hp = mon.hp
                mon.hp = min(mon.max_hp, mon.hp + heal)
                actual_heal = mon.hp - old_hp
                if actual_heal > 0:
                    ability_name = (mon.ability or ability).replace("-", " ").title()
                    messages.append(f"{mon.species}'s {ability_name} restored HP! (+{actual_heal} HP)")
        
        # Dry Skin - heal in rain, damage in sun
        if ability == "dry-skin":
            if weather == "rain" and mon.hp > 0 and mon.hp < mon.max_hp:
                heal = max(1, mon.max_hp // 8)
                old_hp = mon.hp
                mon.hp = min(mon.max_hp, mon.hp + heal)
                actual_heal = mon.hp - old_hp
                if actual_heal > 0:
                    messages.append(f"{mon.species}'s Dry Skin restored HP! (+{actual_heal} HP)")
            elif weather == "sun" and mon.hp > 0:
                damage = max(1, mon.max_hp // 8)
                # Dummy Magikarp is immortal - heals to 999 HP when it reaches 0
                if getattr(mon, '_is_dummy_magikarp', False):
                    mon.hp = max(0, mon.hp - damage)
                    if mon.hp <= 0:
                        mon.hp = 999
                        mon.max_hp = 999
                else:
                    mon.hp = max(0, mon.hp - damage)
                messages.append(f"{mon.species}'s Dry Skin was hurt by the sun! (-{damage} HP)")
                if mon.hp <= 0:
                    messages.append(f"{mon.species} fainted!")
        
        # Solar Power - lose 1/8 HP in sun (SpA boost handled in stat calc)
        if ability == "solar-power" and weather == "sun" and mon.hp > 0:
            damage = max(1, mon.max_hp // 8)
            # Dummy Magikarp is immortal - heals to 999 HP when it reaches 0
            if getattr(mon, '_is_dummy_magikarp', False):
                mon.hp = max(0, mon.hp - damage)
                if mon.hp <= 0:
                    mon.hp = 999
                    mon.max_hp = 999
            else:
                mon.hp = max(0, mon.hp - damage)
            messages.append(f"{mon.species}'s Solar Power drained HP! (-{damage} HP)")
            if mon.hp <= 0:
                messages.append(f"{mon.species} fainted!")
    
    # === TERRAIN-BASED HEALING (Grassy Terrain) ===
    if field_effects and hasattr(field_effects, 'terrain'):
        terrain = field_effects.terrain
        # Grassy Terrain: Heal 1/16 HP per turn if grounded
        if terrain == "grassy" and mon.hp > 0 and mon.hp < mon.max_hp:
            # Check if grounded (not Flying-type, no Levitate, no Air Balloon)
            is_grounded = True
            if "Flying" in mon.types:
                is_grounded = False
            ability = normalize_ability_name(mon.ability or "")
            ability_data = get_ability_effect(ability)
            if "immune_types" in ability_data and "Ground" in ability_data["immune_types"]:
                is_grounded = False
            # Check Air Balloon
            if item_is_active(mon):
                item_data = get_item_effect(normalize_item_name(mon.item))
                if item_data.get("grants_ground_immunity") and not getattr(mon, '_balloon_popped', False):
                    is_grounded = False
            
            if is_grounded:
                heal = max(1, mon.max_hp // 16)
                old_hp = mon.hp
                mon.hp = min(mon.max_hp, mon.hp + heal)
                actual_heal = mon.hp - old_hp
                if actual_heal > 0:
                    messages.append(f"{mon.species} was healed by Grassy Terrain! (+{actual_heal} HP)")
    
    # Check for Magic Guard (prevents all indirect damage)
    ability = normalize_ability_name(mon.ability or "")
    ability_data = get_ability_effect(ability)
    magic_guard_active = ability_data.get("no_indirect_damage", False)
    
    # Ghost-type Curse damage (applies even if user has switched out unless Baton Passed)
    # This is OUTSIDE the status condition block because curse is independent of status
    if getattr(mon, 'cursed', False) and not magic_guard_active:
        ability_curse = normalize_ability_name(mon.ability or "")
        ability_curse_data = get_ability_effect(ability_curse)
        if not ability_curse_data.get("prevents_indirect_damage"):
            curse_damage = max(1, mon.max_hp // 4)
            # Dummy Magikarp is immortal - never goes below 1 HP
            if getattr(mon, '_is_dummy_magikarp', False):
                mon.hp = max(1, mon.hp - curse_damage)
            else:
                mon.hp = max(0, mon.hp - curse_damage)
            messages.append(f"**{mon.species}** is afflicted by the curse!")
            if mon.hp <= 0:
                messages.append(f"**{mon.species}** fainted!")
    
    # Status condition damage
    if mon.status and not magic_guard_active:
        # Normalize status strings
        status = mon.status.lower()
        
        if status in ["slp", "sleep"]:
            # Sleep turns are now decremented at the START of the turn in can_pokemon_move
            # So we just check if still asleep here (for end-of-turn messages)
            # Skip message if sleep was just applied this turn (already said "fell asleep!")
            if not getattr(mon, '_sleep_applied_this_turn', False):
                if mon.status_turns > 0:
                    messages.append(f"{mon.species} is fast asleep!")
                elif mon.status:
                    # Shouldn't happen, but handle edge case
                    messages.append(f"{mon.species} is fast asleep!")
        
        elif status in ["par", "paralysis"]:
            # Paralysis chance to not move is handled in can_move()
            pass
        
        elif status in ["brn", "burn"]:
            # Generation-specific burn damage
            generation = get_generation(field_effects=field_effects)
            
            # Gen 1: 1/16 HP, Gen 2-6: 1/8 HP, Gen 7+: 1/16 HP
            if generation == 1 or generation >= 7:
                damage = max(1, mon.max_hp // 16)
            else:  # Gen 2-6
                damage = max(1, mon.max_hp // 8)
            
            # Heatproof: Halve burn damage
            if ability_data.get("resist_types") and "Fire" in ability_data.get("resist_types", []):
                damage = max(1, damage // 2)
            
            # Dummy Magikarp is immortal - heals to 999 HP when it reaches 0
            if getattr(mon, '_is_dummy_magikarp', False):
                mon.hp = max(0, mon.hp - damage)
                if mon.hp <= 0:
                    mon.hp = 999
                    mon.max_hp = 999
            else:
                mon.hp = max(0, mon.hp - damage)
            messages.append(f"**{mon.species}** was hurt by its burn!")
        
        elif status in ["psn", "poison"]:
            # Generation-specific poison damage
            generation = get_generation(field_effects=field_effects)
            
            # Gen 1: 1/16 HP, Gen 2+: 1/8 HP
            if generation == 1:
                damage = max(1, mon.max_hp // 16)
            else:
                damage = max(1, mon.max_hp // 8)
            
            # Dummy Magikarp is immortal - heals to 999 HP when it reaches 0
            if getattr(mon, '_is_dummy_magikarp', False):
                mon.hp = max(0, mon.hp - damage)
                if mon.hp <= 0:
                    mon.hp = 999
                    mon.max_hp = 999
            else:
                mon.hp = max(0, mon.hp - damage)
            messages.append(f"**{mon.species}** was hurt by poison!")
        
        elif status in ["tox", "toxic"]:
            gen_toxic_dmg = get_generation(field_effects=field_effects)
            
            if not hasattr(mon, 'toxic_counter') or mon.toxic_counter is None:
                mon.toxic_counter = 0
            
            # Gen I: Toxic counter increases with Leech Seed damage (same counter)
            # Gen II+: Toxic is separate from other damage sources
            if gen_toxic_dmg == 1:
                # Gen I: Counter increases each time it takes damage from poison OR Leech Seed
                # Leech Seed damage also uses the same counter
                mon.toxic_counter += 1
            else:
                # Gen II+: Only increases from Toxic damage
                mon.toxic_counter += 1
            
            damage = max(1, (mon.max_hp * mon.toxic_counter) // 16)  # Increasing damage: N/16
            # Dummy Magikarp is immortal - heals to 999 HP when it reaches 0
            if getattr(mon, '_is_dummy_magikarp', False):
                mon.hp = max(0, mon.hp - damage)
                if mon.hp <= 0:
                    mon.hp = 999
                    mon.max_hp = 999
            else:
                mon.hp = max(0, mon.hp - damage)
            messages.append(f"**{mon.species}** was hurt by poison!")
        
        elif status in ["frz", "freeze"]:
            # Generation-specific freeze thaw mechanics
            generation = get_generation(field_effects=field_effects)
            
            # Gen 1: Never thaws naturally
            # Gen 2: 10% chance to thaw
            # Gen 3+: 20% chance to thaw
            if generation == 1:
                # In Gen 1, frozen Pokemon never thaw without external aid
                messages.append(f"{mon.species} is frozen solid!")
            elif generation == 2:
                if random.random() < 0.1:  # 10% chance
                    mon.status = None
                    messages.append(f"{mon.species} thawed out!")
        
        # Nightmare: 1/4 HP damage per turn while asleep
        if hasattr(mon, 'nightmared') and mon.nightmared:
            if mon.status and mon.status.lower() in ["slp", "sleep"]:
                gen_nightmare_dmg = get_generation(field_effects=field_effects)
                
                # Gen II: Damage after action (unless opponent faints)
                # Gen III+: Damage at end of turn (even if opponent faints)
                damage = max(1, mon.max_hp // 4)
                
                # Magic Guard blocks indirect damage
                ability_nightmare = normalize_ability_name(mon.ability or "")
                ability_data_nightmare = get_ability_effect(ability_nightmare)
                if not ability_data_nightmare.get("prevents_indirect_damage"):
                    # Dummy Magikarp is immortal - heals to 999 HP when it reaches 0
                    if getattr(mon, '_is_dummy_magikarp', False):
                        mon.hp = max(0, mon.hp - damage)
                        if mon.hp <= 0:
                            mon.hp = 999
                            mon.max_hp = 999
                    else:
                        mon.hp = max(0, mon.hp - damage)
                    messages.append(f"**{mon.species}** is tormented by a nightmare! (-{damage} HP)")
                    
                    if mon.hp <= 0:
                        messages.append(f"**{mon.species}** fainted!")
            else:
                # Nightmare ends when Pokémon wakes up
                mon.nightmared = False
    
    # Freeze thaw logic (Gen 3+) - separate from Nightmare block
    if mon.status and mon.status.lower() == "frz":
        generation_freeze = get_generation(field_effects=field_effects)
        if generation_freeze >= 3:
            if random.random() < 0.2:  # 20% chance
                mon.status = None
                messages.append(f"{mon.species} thawed out!")
            else:
                messages.append(f"{mon.species} is frozen solid!")
    
    if mon.status and magic_guard_active:
        # Magic Guard blocks status damage but not status effects like sleep/paralysis
        status = mon.status.lower()
        if status in ["slp", "sleep"]:
            # Sleep turns are now decremented at the START of the turn in can_pokemon_move
            # So we just check if still asleep here (for end-of-turn messages)
            # Skip message if sleep was just applied this turn (already said "fell asleep!")
            if not getattr(mon, '_sleep_applied_this_turn', False):
                if mon.status_turns > 0:
                    messages.append(f"{mon.species} is fast asleep!")
                elif mon.status:
                    # Shouldn't happen, but handle edge case
                    messages.append(f"{mon.species} is fast asleep!")
        elif status in ["frz", "freeze"]:
            # Generation-specific freeze thaw mechanics (same as above, but for Magic Guard)
            generation = get_generation(field_effects=field_effects)
            
            if generation == 1:
                messages.append(f"{mon.species} is frozen solid!")
            elif generation == 2:
                if random.random() < 0.1:
                    mon.status = None
                    messages.append(f"{mon.species} thawed out!")
                else:
                    messages.append(f"{mon.species} is frozen solid!")
            else:  # Gen 3+
                if random.random() < 0.2:
                    mon.status = None
                    messages.append(f"{mon.species} thawed out!")
                else:
                    messages.append(f"{mon.species} is frozen solid!")
    
    # G-Max Wildfire: Residual damage for 4 turns to non-Fire-type foes (1/6 max HP)
    if getattr(mon, '_gmax_wildfire_active', False) and mon._gmax_wildfire_turns > 0:
        # Check if Pokemon is Fire-type (immune)
        is_fire_type = "Fire" in (mon.types or [])
        if not is_fire_type and not magic_guard_active:
            damage = max(1, mon.max_hp // 6)  # 1/6 max HP damage
            # Dummy Magikarp is immortal - heals to 999 HP when it reaches 0
            if getattr(mon, '_is_dummy_magikarp', False):
                mon.hp = max(0, mon.hp - damage)
                if mon.hp <= 0:
                    mon.hp = 999
                    mon.max_hp = 999
            else:
                mon.hp = max(0, mon.hp - damage)
            messages.append(f"{mon.species} was hurt by the wildfire! (-{damage} HP)")
            if mon.hp <= 0:
                messages.append(f"{mon.species} fainted!")
        # Decrement turns
        mon._gmax_wildfire_turns -= 1
        if mon._gmax_wildfire_turns <= 0:
            mon._gmax_wildfire_active = False
    
    # G-Max Volcalith: Residual damage for 4 turns to non-Rock-type foes (1/6 max HP)
    if getattr(mon, '_gmax_volcalith_active', False) and mon._gmax_volcalith_turns > 0:
        # Check if Pokemon is Rock-type (immune)
        is_rock_type = "Rock" in (mon.types or [])
        if not is_rock_type and not magic_guard_active:
            damage = max(1, mon.max_hp // 6)  # 1/6 max HP damage
            # Dummy Magikarp is immortal - heals to 999 HP when it reaches 0
            if getattr(mon, '_is_dummy_magikarp', False):
                mon.hp = max(0, mon.hp - damage)
                if mon.hp <= 0:
                    mon.hp = 999
                    mon.max_hp = 999
            else:
                mon.hp = max(0, mon.hp - damage)
            messages.append(f"{mon.species} was hurt by the volcalith! (-{damage} HP)")
            if mon.hp <= 0:
                messages.append(f"{mon.species} fainted!")
        # Decrement turns
        mon._gmax_volcalith_turns -= 1
        if mon._gmax_volcalith_turns <= 0:
            mon._gmax_volcalith_active = False
    
    # G-Max Vine Lash: Residual damage for 4 turns to non-Grass-type foes (1/6 max HP)
    if getattr(mon, '_gmax_vine_lash_active', False) and mon._gmax_vine_lash_turns > 0:
        # Check if Pokemon is Grass-type (immune)
        is_grass_type = "Grass" in (mon.types or [])
        if not is_grass_type and not magic_guard_active:
            damage = max(1, mon.max_hp // 6)  # 1/6 max HP damage
            # Dummy Magikarp is immortal - heals to 999 HP when it reaches 0
            if getattr(mon, '_is_dummy_magikarp', False):
                mon.hp = max(0, mon.hp - damage)
                if mon.hp <= 0:
                    mon.hp = 999
                    mon.max_hp = 999
            else:
                mon.hp = max(0, mon.hp - damage)
            messages.append(f"{mon.species} was hurt by the vine lash! (-{damage} HP)")
            if mon.hp <= 0:
                messages.append(f"{mon.species} fainted!")
        # Decrement turns
        mon._gmax_vine_lash_turns -= 1
        if mon._gmax_vine_lash_turns <= 0:
            mon._gmax_vine_lash_active = False
    
    # G-Max Cannonade: Residual damage for 4 turns to non-Water-type foes (1/6 max HP)
    if getattr(mon, '_gmax_cannonade_active', False) and mon._gmax_cannonade_turns > 0:
        # Check if Pokemon is Water-type (immune)
        is_water_type = "Water" in (mon.types or [])
        if not is_water_type and not magic_guard_active:
            damage = max(1, mon.max_hp // 6)  # 1/6 max HP damage
            # Dummy Magikarp is immortal - heals to 999 HP when it reaches 0
            if getattr(mon, '_is_dummy_magikarp', False):
                mon.hp = max(0, mon.hp - damage)
                if mon.hp <= 0:
                    mon.hp = 999
                    mon.max_hp = 999
            else:
                mon.hp = max(0, mon.hp - damage)
            messages.append(f"{mon.species} was hurt by the cannonade! (-{damage} HP)")
            if mon.hp <= 0:
                messages.append(f"{mon.species} fainted!")
        # Decrement turns
        mon._gmax_cannonade_turns -= 1
        if mon._gmax_cannonade_turns <= 0:
            mon._gmax_cannonade_active = False
    
    # Leech Seed damage (blocked by Magic Guard)
    if hasattr(mon, 'leech_seeded') and mon.leech_seeded and opponent and not magic_guard_active:
        # Store HP before damage to calculate actual HP drained
        old_hp = mon.hp
        damage = max(1, mon.max_hp // 8)  # 1/8 max HP damage
        
        # Apply damage (may cause fainting)
        # Dummy Magikarp is immortal - never goes below 1 HP
        if getattr(mon, '_is_dummy_magikarp', False):
            mon.hp = max(1, mon.hp - damage)
        else:
            mon.hp = max(0, mon.hp - damage)
        
        # Calculate actual HP drained (cannot exceed what was available)
        actual_damage_dealt = old_hp - mon.hp
        
        # Always show the Leech Seed damage message (original game phrase)
        if actual_damage_dealt > 0:
            messages.append(f"{mon.species}'s health is sapped by Leech Seed!")
        
        # Only heal opponent based on actual HP drained
        # If mon fainted, we can still heal based on the HP that was actually drained
        # But ensure we never heal a fainted Pokémon
        if actual_damage_dealt > 0:
            # Ensure opponent is not the fainted mon (safety check)
            if opponent != mon and opponent.hp > 0:
                # Heal based on actual HP drained (not the full damage amount if mon fainted)
                heal = min(actual_damage_dealt, opponent.max_hp - opponent.hp)
                if heal > 0:
                    opponent.hp = min(opponent.max_hp, opponent.hp + heal)
    
    # Ingrain healing
    if hasattr(mon, 'ingrained') and mon.ingrained:
        if getattr(mon, 'heal_blocked', 0) <= 0:
            heal = max(1, mon.max_hp // 16)

            if item_is_active(mon) and mon.item:

                item_norm = normalize_item_name(mon.item)
                item_data = get_item_effect(item_norm)
                if item_data.get("boosts_draining_moves") and "ingrain" in item_data.get("affected_moves", []):
                    gen_now = get_generation(field_effects=field_effects)
                    gen_specific = item_data.get("gen_specific", {})
                    if gen_now <= 4:
                        mult = gen_specific.get("4", {}).get("multiplier", 1.3)
                    else:
                        mult = gen_specific.get("5+", {}).get("multiplier", 5324 / 4096)
                    heal = max(1, int(math.floor(heal * mult)))

        old_hp = mon.hp
        mon.hp = min(mon.max_hp, mon.hp + heal)
        actual_heal = mon.hp - old_hp
        if actual_heal > 0:
            messages.append(f"{mon.species} absorbed nutrients with its roots! (+{actual_heal} HP)")
    
    # Aqua Ring healing
    if hasattr(mon, 'aqua_ring') and mon.aqua_ring:
        heal = max(1, mon.max_hp // 16)  # 1/16 max HP healing
        # Big Root boosts healing
        if mon.item and "big-root" in mon.item.lower().replace(" ", "-"):
            heal = int(heal * 1.3)
        old_hp = mon.hp
        mon.hp = min(mon.max_hp, mon.hp + heal)
        actual_heal = mon.hp - old_hp
        if actual_heal > 0:
            messages.append(f"Aqua Ring restored {mon.species}'s HP! (+{actual_heal} HP)")
    
    # Perish Song countdown
    if hasattr(mon, 'perish_count') and mon.perish_count is not None:
        mon.perish_count -= 1
        if mon.perish_count > 0:
            # Cool countdown messages based on remaining turns
            if mon.perish_count == 3:
                messages.append(f"🎵 **{mon.species}** hears the haunting melody... **3 turns** remain!")
            elif mon.perish_count == 2:
                messages.append(f"🎵 **{mon.species}** feels the song's grip tightening... **2 turns** left!")
            elif mon.perish_count == 1:
                messages.append(f"🎵 **{mon.species}** is consumed by the final verse... **1 turn** remains!")
        else:
            # Dummy Magikarp is immortal - never goes below 1 HP
            if getattr(mon, '_is_dummy_magikarp', False):
                mon.hp = 1
                messages.append(f"💀 **{mon.species}** was claimed by Perish Song! (But it's immortal!)")
            else:
                mon.hp = 0
                messages.append(f"💀 **{mon.species}** was claimed by Perish Song!")
    
    # Confusion countdown
    # Only decrement if confusion was NOT applied this turn (prevents clearing on the turn it's applied)
    if mon.confused and mon.confusion_turns > 0:
        # Check if confusion was just applied this turn
        if not getattr(mon, '_confusion_applied_this_turn', False):
            mon.confusion_turns -= 1
            if mon.confusion_turns <= 0:
                mon.confused = False
                messages.append(f"{mon.species} snapped out of confusion!")
        else:
            # Clear the flag for next turn
            mon._confusion_applied_this_turn = False
    
    # === HELD ITEM PASSIVE EFFECTS ===
    if mon.item and mon.hp > 0:
        item_normalized = mon.item.lower().replace(" ", "-")
        
        # Leftovers: Restores 1/16 max HP each turn
        # Activates on switch-in unless it was a forced switch due to fainting
        if item_normalized == "leftovers":
            just_switched_in = getattr(mon, '_just_switched_in', False)
            was_forced_switch = getattr(mon, '_forced_switch', False)
            
            # Leftovers should activate unless:
            # - Pokémon just switched in AND it was a forced switch due to fainting
            should_skip = just_switched_in and was_forced_switch
            
            if not should_skip:
                heal = max(1, mon.max_hp // 16)
                old_hp = mon.hp
                mon.hp = min(mon.max_hp, mon.hp + heal)
                actual_heal = mon.hp - old_hp
                if actual_heal > 0:
                    messages.append(f"**{mon.species}** restored a little HP using its **Leftovers**!")
        
        # Black Sludge: Heals Poison types, damages others (damage blocked by Magic Guard)
        elif item_normalized == "black-sludge":
            if "Poison" in mon.types:
                # Heal Poison-types
                heal = max(1, mon.max_hp // 16)
                old_hp = mon.hp
                mon.hp = min(mon.max_hp, mon.hp + heal)
                actual_heal = mon.hp - old_hp
                if actual_heal > 0:
                    messages.append(f"{mon.species} restored a little HP with Black Sludge! (+{actual_heal} HP)")
            elif not magic_guard_active:
                # Damage non-Poison types (blocked by Magic Guard)
                damage = max(1, mon.max_hp // 8)
                # Dummy Magikarp is immortal - heals to 999 HP when it reaches 0
                if getattr(mon, '_is_dummy_magikarp', False):
                    mon.hp = max(0, mon.hp - damage)
                    if mon.hp <= 0:
                        mon.hp = 999
                        mon.max_hp = 999
                else:
                    mon.hp = max(0, mon.hp - damage)
                messages.append(f"{mon.species} was hurt by the Black Sludge! (-{damage} HP)")
                if mon.hp <= 0:
                    messages.append(f"{mon.species} fainted from Black Sludge!")
        
        # === FLAME ORB: Burns holder at end of turn (if not already statused) ===
        elif item_normalized == "flame-orb":
            if not mon.status:
                mon.status = "brn"
                messages.append(f"{mon.species} was burned by its Flame Orb!")
        
        # === TOXIC ORB: Badly poisons holder at end of turn (if not already statused) ===
        elif item_normalized == "toxic-orb":
            if not mon.status:
                mon.status = "tox"
                mon.toxic_counter = 0
                messages.append(f"{mon.species} was badly poisoned by its Toxic Orb!")
        
        # === STICKY BARB: Damages holder at end of turn ===
        elif item_normalized == "sticky-barb" and not magic_guard_active:
            damage = max(1, mon.max_hp // 8)
            # Dummy Magikarp is immortal - heals to 999 HP when it reaches 0
            if getattr(mon, '_is_dummy_magikarp', False):
                mon.hp = max(0, mon.hp - damage)
                if mon.hp <= 0:
                    mon.hp = 999
                    mon.max_hp = 999
            else:
                mon.hp = max(0, mon.hp - damage)
            messages.append(f"{mon.species} was hurt by its Sticky Barb! (-{damage} HP)")
            if mon.hp <= 0:
                messages.append(f"{mon.species} fainted from Sticky Barb!")
    
    # === WEATHER DAMAGE (Sandstorm, Hail) ===
    if field_effects and hasattr(field_effects, 'weather') and mon.hp > 0 and not magic_guard_active and not weather_negated:
        weather = field_effects.weather
        
        # === SAFETY GOGGLES: Immune to weather damage (Gen 6+) ===
        weather_damage_immune = False
        if item_is_active(mon) and mon.item:
            mon_item_sg = normalize_item_name(mon.item)
            mon_item_data_sg = get_item_effect(mon_item_sg)
            gen_sg = get_generation(field_effects=field_effects)
            if mon_item_data_sg.get("weather_immunity") and gen_sg >= 6:
                weather_damage_immune = True
        
        if not weather_damage_immune:
            # Sandstorm: Damages non-Rock/Ground/Steel types
            if weather in ["sandstorm", "sand"]:
                immune_types = ["Rock", "Ground", "Steel"]
                is_immune = any(t in immune_types for t in mon.types if t)
                
                # Check for Sand Veil/Rush/Force (sandstorm immunity)
                if not is_immune and ability_data.get("sandstorm_immunity"):
                    is_immune = True
                
                # Gen II: Pokémon using Dig avoid sandstorm damage (regardless of type)
                # Gen III+: Pokémon using Dig or Dive avoid sandstorm damage
                if getattr(mon, 'invulnerable', False):
                    invuln_type = getattr(mon, 'invulnerable_type', None)
                    generation_weather = get_generation(field_effects=field_effects)
                    if invuln_type == "underground" or (invuln_type == "underwater" and generation_weather >= 3):
                        is_immune = True
                
                if not is_immune:
                    generation_weather = get_generation(field_effects=field_effects)

                    damage = 0
                    if generation_weather == 2:
                        sand_turns = getattr(field_effects, 'sandstorm_damage_turns', 0)
                        if sand_turns > 0:
                            damage = max(1, mon.max_hp // 8)
                    else:
                        damage = max(1, mon.max_hp // 16)

                    if damage > 0:
                        # Dummy Magikarp is immortal - never goes below 1 HP
                        if getattr(mon, '_is_dummy_magikarp', False):
                            mon.hp = max(1, mon.hp - damage)
                        else:
                            mon.hp = max(0, mon.hp - damage)
                    messages.append(f"{mon.species} was buffeted by the sandstorm! (-{damage} HP)")
                    if mon.hp <= 0:
                        messages.append(f"{mon.species} fainted from the sandstorm!")
            
            # Hail/Snow: Damages non-Ice types
            elif weather in ["hail", "snow"]:
                immune_types = ["Ice"]
                is_immune = any(t in immune_types for t in mon.types if t)
                
                # Check for Snow Cloak/Ice Body (hail immunity)
                if not is_immune and ability_data.get("hail_immunity"):
                    is_immune = True
                
                if not is_immune:
                    damage = max(1, mon.max_hp // 16)
                    # Dummy Magikarp is immortal - heals to 999 HP when it reaches 0
                    if getattr(mon, '_is_dummy_magikarp', False):
                        mon.hp = max(0, mon.hp - damage)
                        if mon.hp <= 0:
                            mon.hp = 999
                            mon.max_hp = 999
                    else:
                        mon.hp = max(0, mon.hp - damage)
                    weather_name = "hail" if weather == "hail" else "snow"
                    messages.append(f"{mon.species} was buffeted by the {weather_name}! (-{damage} HP)")
                    if mon.hp <= 0:
                        messages.append(f"{mon.species} fainted from the {weather_name}!")
    
    # === END-OF-TURN ABILITY EFFECTS (Shed Skin) ===
    if mon.status and ability_data.get("end_of_turn"):
        end_turn_effect = ability_data["end_of_turn"]
        if end_turn_effect.get("heal_status"):
            # Generation-specific chance for Shed Skin
            # Gen 3: 1/3 (33.33%), Gen 4: 30%, Gen 5+: 1/3 (33.33%)
            generation = get_generation(field_effects=field_effects)
            
            if ability == "shed-skin":
                if generation == 4:
                    chance = 0.30
                else:
                    chance = 1.0 / 3.0  # 33.33%
            else:
                chance = end_turn_effect.get("chance", 1.0)
            
            if random.random() < chance:
                mon.status = None
                ability_name = (mon.ability or ability).replace("-", " ").title()
                messages.append(f"{mon.species}'s {ability_name} healed its status condition!")
    
    # === TURN-BASED ABILITIES ===
    # Speed Boost - +1 Speed each turn
    # Does NOT activate on the turn the Pokemon switched in (but DOES activate if forced in due to fainting)
    if ability == "speed-boost" and mon.hp > 0:
        # Get turns since switch (0 = just switched in this turn)
        turns_since_switch = getattr(mon, '_turns_since_switch_in', 0)
        was_forced_in = getattr(mon, '_forced_switch', False)  # If switched in due to fainting
        
        # Only activate if:
        # - Turn 1+ after switch (not turn 0) OR
        # - Was forced in due to fainting
        if turns_since_switch > 0 or was_forced_in:
            old_stage = mon.stages.get("spe", 0)
            if old_stage < 6:
                mon.stages["spe"] = old_stage + 1
                messages.append(f"{mon.species}'s Speed Boost raised its Speed!")
        
        # Clear forced switch flag after first check
        if was_forced_in:
            mon._forced_switch = False
    
    # Moody - +2 to one random stat, -1 to another
    if ability == "moody" and mon.hp > 0:
        # Gen 5-7: Can affect accuracy/evasion
        # Gen 8+: Only affects battle stats (no accuracy/evasion)
        if generation <= 7:
            boostable_stats = ["atk", "defn", "spa", "spd", "spe", "accuracy", "evasion"]
        else:
            boostable_stats = ["atk", "defn", "spa", "spd", "spe"]
        # Pick random stat to boost
        boost_stat = random.choice(boostable_stats)
        old_boost = mon.stages.get(boost_stat, 0)
        mon.stages[boost_stat] = min(6, old_boost + 2)
        
        # Pick different random stat to lower
        lowerable_stats = [s for s in boostable_stats if s != boost_stat]
        lower_stat = random.choice(lowerable_stats)
        old_lower = mon.stages.get(lower_stat, 0)
        mon.stages[lower_stat] = max(-6, old_lower - 1)
        
        boost_name = boost_stat.upper()
        lower_name = lower_stat.upper()
        messages.append(f"{mon.species}'s Moody sharply raised its {boost_name}!")
        messages.append(f"{mon.species}'s Moody lowered its {lower_name}!")
    
    # Erratic - Missing n0 exclusive: +2 to random stat, -2 to random stat each turn
    # Clears turn by turn (reverses previous turn's changes before applying new ones)
    if ability == "erratic" and mon.hp > 0:
        # Get turns since switch (0 = just switched in this turn, will be incremented to 1 at end of turn)
        turns_since_switch = getattr(mon, '_turns_since_switch_in', 0)
        was_forced_in = getattr(mon, '_forced_switch', False)
        just_switched_in = getattr(mon, '_just_switched_in', False)
        
        # Activate Erratic each turn the Pokémon is active (except on the turn it switches in)
        # Note: turns_since_switch is incremented AFTER apply_status_effects runs (at line 4359 in panel.py)
        # Execution order at END of turn: increment counter (only if not just_switched_in) → clear just_switched_in
        #   - On switch-in turn: just_switched_in = True, counter = 0 → Don't trigger (correct, first turn)
        #     At end of turn: counter stays 0 (not incremented because just_switched_in was True), just_switched_in cleared to False
        #   - On first turn after switch: apply_status_effects runs, just_switched_in = False (cleared at end of previous turn), counter = 0 → Should trigger
        #     At end of turn: counter incremented to 1, just_switched_in stays False
        #   - On subsequent turns: just_switched_in = False, counter > 0 → Trigger
        # The fix: Check if the Pokémon was active at START of turn (not just_switched_in), which means it's at least turn 2
        if (not just_switched_in) or was_forced_in:
            # Battle stats only (no accuracy/evasion)
            battle_stats = ["atk", "defn", "spa", "spd", "spe"]
            
            # Initialize tracking if not exists
            if not hasattr(mon, '_erratic_boost_stat'):
                mon._erratic_boost_stat = None
                mon._erratic_debuff_stat = None
            
            # Clear previous Erratic changes (reverse them)
            if mon._erratic_boost_stat is not None:
                old_boost = mon.stages.get(mon._erratic_boost_stat, 0)
                mon.stages[mon._erratic_boost_stat] = max(-6, min(6, old_boost - 2))
            if mon._erratic_debuff_stat is not None:
                old_debuff = mon.stages.get(mon._erratic_debuff_stat, 0)
                mon.stages[mon._erratic_debuff_stat] = max(-6, min(6, old_debuff + 2))
            
            # Pick random stat to boost (+2)
            boost_stat = random.choice(battle_stats)
            old_boost = mon.stages.get(boost_stat, 0)
            mon.stages[boost_stat] = min(6, old_boost + 2)
            mon._erratic_boost_stat = boost_stat
            
            # Pick different random stat to lower (-2)
            lowerable_stats = [s for s in battle_stats if s != boost_stat]
            lower_stat = random.choice(lowerable_stats)
            old_lower = mon.stages.get(lower_stat, 0)
            mon.stages[lower_stat] = max(-6, old_lower - 2)
            mon._erratic_debuff_stat = lower_stat
            
            boost_name = boost_stat.replace("atk", "Attack").replace("defn", "Defense").replace("spa", "Sp. Atk").replace("spd", "Sp. Def").replace("spe", "Speed").title()
            lower_name = lower_stat.replace("atk", "Attack").replace("defn", "Defense").replace("spa", "Sp. Atk").replace("spd", "Sp. Def").replace("spe", "Speed").title()
            messages.append(f"{mon.species}'s Erratic sharply raised its {boost_name}!")
            messages.append(f"{mon.species}'s Erratic harshly lowered its {lower_name}!")
        
        # Clear forced switch flag after first check
        if was_forced_in:
            mon._forced_switch = False
    
    # Hydration - Heal status in rain (must come before Bad Dreams)
    if ability == "hydration" and mon.status and field_effects:
        if hasattr(field_effects, 'weather') and field_effects.weather == "rain":
            mon.status = None
            mon.status_turns = 0
            mon.toxic_counter = 0
            messages.append(f"{mon.species}'s Hydration healed its status condition!")
    
    # Poison Heal - Heal 1/8 HP if poisoned instead of damage
    if ability == "poison-heal" and mon.status:
        status_lower = mon.status.lower()
        if status_lower in ["psn", "tox", "poison", "badly poisoned"]:
            if mon.hp < mon.max_hp:
                heal = max(1, mon.max_hp // 8)
                old_hp = mon.hp
                mon.hp = min(mon.max_hp, mon.hp + heal)
                actual_heal = mon.hp - old_hp
                if actual_heal > 0:
                    messages.append(f"{mon.species}'s Poison Heal restored HP! (+{actual_heal} HP)")
    
    # Harvest - Restore consumed berry at end of turn (50% chance, 100% in sun)
    if ability == "harvest" and not mon.item and hasattr(mon, '_last_consumed_berry'):
        berry_restore = ability_data.get("berry_restore_chance", {})
        
        # Check for harsh sunlight
        restore_chance = 0.5  # Default 50%
        if field_effects and hasattr(field_effects, 'weather'):
            if field_effects.weather == "sun":
                restore_chance = 1.0  # 100% in harsh sunlight
        
        # Roll for berry restoration
        if random.random() < restore_chance:
            mon.item = mon._last_consumed_berry
            berry_display = mon.item.replace('-', ' ').title()
            messages.append(f"{mon.species}'s Harvest restored its {berry_display}!")
    
    # Bad Dreams - Damage sleeping opponents 1/8 HP (after wake-up abilities like Hydration)
    if ability == "bad-dreams" and opponent and opponent.hp > 0 and opponent.status:
        if opponent.status.lower() in ["slp", "sleep"]:
            opp_ability = normalize_ability_name(opponent.ability or "")
            opp_ability_data = get_ability_effect(opp_ability)
            opp_magic_guard = opp_ability_data.get("no_indirect_damage", False)
            
            if not opp_magic_guard:
                damage = max(1, opponent.max_hp // 8)
                opponent.hp = max(0, opponent.hp - damage)
                messages.append(f"{opponent.species} is tormented by {mon.species}'s Bad Dreams! (-{damage} HP)")
                if opponent.hp <= 0:
                    messages.append(f"{opponent.species} fainted!")
    
    # Harvest - 50% chance to restore Berry (100% in sun)
    if ability == "harvest" and hasattr(mon, '_consumed_berry') and mon._consumed_berry and not mon.item:
        restore_chance = 0.5
        if field_effects and hasattr(field_effects, 'weather') and field_effects.weather == "sun":
            restore_chance = 1.0
        if random.random() < restore_chance:
            mon.item = mon._consumed_berry
            mon._consumed_berry = None
            messages.append(f"{mon.species}'s Harvest restored its {mon.item}!")
    
    # === DUMMY MAGIKARP: Auto-cure all status effects and conditions after 1 turn ===
    # This allows testing status effects - they apply damage, then get cleared
    if getattr(mon, '_is_dummy_magikarp', False):
        # Clear status conditions
        if mon.status:
            mon.status = None
            mon.status_turns = 0
            mon.toxic_counter = 0
            messages.append(f"{mon.species}'s status condition was cleared! (Testing mode)")
        
        # Clear Leech Seed
        if hasattr(mon, 'leech_seeded') and mon.leech_seeded:
            mon.leech_seeded = False
            messages.append(f"{mon.species}'s Leech Seed was removed! (Testing mode)")
        
        # Clear Curse
        if getattr(mon, 'cursed', False):
            mon.cursed = False
            if hasattr(mon, '_cursed_generation'):
                delattr(mon, '_cursed_generation')
            if hasattr(mon, '_cursed_source'):
                delattr(mon, '_cursed_source')
            messages.append(f"{mon.species}'s Curse was removed! (Testing mode)")
        
        # Clear Nightmare
        if getattr(mon, 'nightmared', False):
            mon.nightmared = False
            messages.append(f"{mon.species}'s Nightmare was removed! (Testing mode)")
        
        # Clear confusion
        if getattr(mon, 'confused', False):
            mon.confused = False
            mon.confusion_turns = 0
            messages.append(f"{mon.species} snapped out of confusion! (Testing mode)")
        
        # Clear Perish Song
        if hasattr(mon, 'perish_count') and mon.perish_count is not None:
            mon.perish_count = None
            messages.append(f"{mon.species}'s Perish Song count was cleared! (Testing mode)")
        
        # Clear Ingrain
        if getattr(mon, 'ingrained', False) or getattr(mon, '_ingrained', False):
            mon.ingrained = False
            if hasattr(mon, '_ingrained'):
                mon._ingrained = False
            if hasattr(mon, '_ingrain_generation'):
                delattr(mon, '_ingrain_generation')
            messages.append(f"{mon.species}'s Ingrain was removed! (Testing mode)")
        
        # Clear Aqua Ring
        if getattr(mon, 'aqua_ring', False):
            mon.aqua_ring = False
            messages.append(f"{mon.species}'s Aqua Ring was removed! (Testing mode)")
        
        # Clear Drowsy
        if getattr(mon, 'drowsy_turns', 0) > 0:
            mon.drowsy_turns = 0
            if hasattr(mon, 'drowsy_source'):
                mon.drowsy_source = None
            if hasattr(mon, '_yawn_generation'):
                delattr(mon, '_yawn_generation')
            messages.append(f"{mon.species}'s drowsiness was cleared! (Testing mode)")
    
    return messages

def can_move(mon: Mon) -> bool:
    """Check if Pokémon can move this turn (not asleep, frozen, etc.)"""
    if not mon.status:
        return True
        
    status = mon.status.lower()
    
    if status in ["slp", "sleep"]:
        if mon.status_turns > 0:
            return False
    if status in ["frz", "freeze"]:
        return False
    if status in ["par", "paralysis"]:
        if random.random() < 0.25:  # 25% chance to be fully paralyzed
            return False

    # Gen I Rest wake-up delay: skip the first turn after waking
    if hasattr(mon, '_gen1_rest_skip_turns') and mon._gen1_rest_skip_turns > 0:
        if mon.status not in ["slp", "sleep"]:
            mon._gen1_rest_skip_turns -= 1
            if mon._gen1_rest_skip_turns <= 0:
                delattr(mon, '_gen1_rest_skip_turns')
            return False
    return True

def check_confusion_self_hit(mon: Mon, field_effects: Any = None) -> Tuple[bool, int, str]:
    """
    Check if a confused Pokémon hits itself instead of using its move.
    Returns (hit_self, damage, message)
    
    Generation differences:
        - Gen 1-6: 50% chance to hit self
    - Gen 7+: 33% chance to hit self
    """
    if not mon.confused or mon.confusion_turns <= 0:
        return False, 0, ""
    
    # Check for Own Tempo (confusion immunity)
    ability = normalize_ability_name(mon.ability or "")
    ability_data = get_ability_effect(ability)
    if ability_data.get("confusion_immunity"):
        mon.confused = False
        mon.confusion_turns = 0
        return False, 0, f"{mon.species} snapped out of confusion!"
    
    generation = get_generation(field_effects=field_effects)
    
    # Generation-specific self-hit chance
    if generation <= 6:
        self_hit_chance = 0.5  # 50% in Gen 1-6
    else:
        self_hit_chance = 0.33  # 33% in Gen 7+
    
    if random.random() >= self_hit_chance:
        # Pokémon successfully used its move
        return False, 0, ""
    
    # Pokémon hit itself in confusion!
    # Confusion damage is typeless, uses Attack vs Defense at +0 stages
    # Base power: 40 (Gen 1-6) or 0 (special calculation in Gen 7+, but still ~40 equivalent)
    
    # Gen 3-4: Huge Power/Pure Power affects confusion damage
    # Gen 5+: Huge Power/Pure Power does NOT affect confusion damage
    if generation <= 4:
        # Use ability-modified stats for Gen 3-4
        base_attack = mon.stats.get("atk", 1)
        base_defense = mon.stats.get("defn", 1)
        
        # Apply Huge Power / Pure Power (2x Attack)
        if ability in ["huge-power", "pure-power"]:
            base_attack *= 2
    else:
        # Use base stats without ability modifiers for Gen 5+
        base_attack = mon.stats.get("atk", 1)
        base_defense = mon.stats.get("defn", 1)
    
    # Simplified confusion damage formula (typeless, no STAB, no crit)
    level = mon.level
    power = 40  # Fixed power for confusion
    damage = int(((2 * level / 5 + 2) * power * (base_attack / base_defense) / 50) + 2)
    
    # Apply random factor (0.85-1.0)
    damage = int(damage * (random.random() * 0.15 + 0.85))
    damage = max(1, damage)

    # Silk Scarf boosts confusion self-hit damage in early gens
    # Gen 3: +10%; Gen 4: +20%; Gen 5+: no boost
    silk_boosted = False
    if item_is_active(mon) and mon.item:
        item_norm = normalize_item_name(mon.item)
        if item_norm == "silk-scarf":
            if generation == 3:
                damage = int(damage * 1.1)
                silk_boosted = True
            elif generation == 4:
                damage = int(damage * 1.2)
                silk_boosted = True

    # Do not implement Gen 4 Chilan confusion bug
    
    # Check for items/abilities that prevent self-KO
    # Gen 2: Focus Band can't prevent confusion self-KO
    # Gen 3+: Focus Band can prevent
    # Gen 4+: Focus Sash can prevent
    # Gen 5+: Sturdy can prevent (if at full HP)
    
    will_faint = (mon.hp - damage <= 0)
    prevented_ko = False
    prevention_message = ""
    
    if will_faint:
        if generation >= 5:
            # Sturdy: Prevent OHKO if at full HP
            if ability == "sturdy" and mon.hp == mon.max_hp:
                damage = mon.hp - 1
                prevented_ko = True
                prevention_message = f"{mon.species} endured the hit with Sturdy!"
        
        if not prevented_ko and generation >= 4:
            # Focus Sash: Prevent OHKO if at full HP
            if item_is_active(mon):
                item_data = get_item_effect(normalize_item_name(mon.item))
                if item_data.get("survives_ohko") and mon.hp == mon.max_hp:
                    damage = mon.hp - 1
                    prevented_ko = True
                    prevention_message = f"{mon.species} hung on with its Focus Sash!"
                    mon.item = None  # Consume Focus Sash
        
        if not prevented_ko and generation >= 3:
            # Focus Band: 10% chance to prevent any KO
            if item_is_active(mon):
                item_data = get_item_effect(normalize_item_name(mon.item))
                if item_data.get("survives_ohko_chance") and random.random() < item_data["survives_ohko_chance"]:
                    damage = mon.hp - 1
                    prevented_ko = True
                    prevention_message = f"{mon.species} hung on with its Focus Band!"
    
    # Apply damage
    mon.hp = max(0, mon.hp - damage)
    
    message = f"**{mon.species}** hurt itself in confusion! ({damage} damage)"
    if silk_boosted:
        message += f"\n{mon.species}'s Silk Scarf powered the damage!"
    if prevented_ko:
        message += f"\n{prevention_message}"
    
    return True, damage, message

def get_status_multiplier(mon: Mon, stat: str, field_effects: Any = None) -> float:
    """Get stat multipliers from status conditions (generation-aware)"""
    if not mon.status:
        return 1.0
        
    status = mon.status.lower()
    
    if status in ["brn", "burn"] and stat == "atk":
        return 0.5  # Burn halves Attack
    if status in ["par", "paralysis"] and stat == "spe":
        # Generation-specific paralysis speed reduction
        generation = get_generation(field_effects=field_effects)
        
        # Gen 1-6: 25% speed (75% reduction)
        # Gen 7+: 50% speed (50% reduction)
        if generation <= 6:
            return 0.25
        else:
            return 0.5
    return 1.0

def inflict_status(mon: Mon, status: str, duration: int = 0, attacker: Optional[Mon] = None, field_effects = None) -> bool:
    """Try to inflict a status condition. Returns True if successful."""
    if mon.status:  # Already has a status
        return False
    
    # Check for status immunity abilities
    ability = normalize_ability_name(mon.ability or "")
    ability_data = get_ability_effect(ability)
    
    # Comatose - Cannot be affected by status
    if ability == "comatose":
        return False
    
    # Purifying Salt - Cannot be poisoned
    if ability == "purifying-salt" and status in ["poison", "toxic", "psn", "tox"]:
        return False
    
    # Type immunities
    if status in ["poison", "toxic", "psn", "tox"]:
        # Check Corrosion ability on attacker (can poison Steel/Poison)
        attacker_ability = normalize_ability_name(attacker.ability) if attacker and attacker.ability else ""
        if attacker_ability != "corrosion":
            if "Poison" in mon.types or "Steel" in mon.types:
                return False
    elif status in ["sleep", "slp"]:
        # Check for sleep immunity abilities
        if ability in ["insomnia", "vital-spirit", "comatose"]:
            return False
        if "Grass" in mon.types:  # Some Grass types have immunity
            return False
    elif status in ["burn", "brn"]:
        # Fire types and Water Veil
        if "Fire" in mon.types:
            return False
        if ability in ["water-veil", "water-bubble"]:
            return False
    elif status in ["freeze", "frz"]:
        # Ice types and Magma Armor
        if "Ice" in mon.types:
            return False
        if ability == "magma-armor":
            return False
    elif status in ["paralysis", "par"]:
        # Electric types and Limber
        if "Electric" in mon.types:
            return False
        if ability == "limber":
            return False
    
    # Synchronize - Pass status back to attacker (Gen 3+)
    # Does NOT activate from items (Toxic Orb/Flame Orb), only from moves/abilities
    # Always reveals ability even if it fails
    if ability == "synchronize" and attacker and status in ["poison", "burn", "paralysis", "psn", "brn", "par", "tox", "badly-poisoned"]:
        generation = get_generation(field_effects=field_effects) if field_effects else 3
        
        # Normalize status for comparison
        status_to_inflict = status
        if status in ["psn"]:
            status_to_inflict = "poison"
        elif status in ["brn"]:
            status_to_inflict = "burn"
        elif status in ["par"]:
            status_to_inflict = "paralysis"
        elif status in ["tox", "badly-poisoned"]:
            # Gen 3-4: Badly poison becomes regular poison when passed
            # Gen 5+: Badly poison stays badly poison
            if generation <= 4:
                status_to_inflict = "poison"
            else:
                status_to_inflict = "badly-poisoned"
        
        # Try to inflict status on attacker (may fail due to type immunity, ability, etc.)
        if not attacker.status:
            attacker_ability = normalize_ability_name(attacker.ability or "")
            
            # Check if attacker can receive this status
            can_receive = True
            if status_to_inflict in ["poison", "badly-poisoned"]:
                if "Poison" in attacker.types or "Steel" in attacker.types:
                    can_receive = False
                if attacker_ability in ["immunity", "pastel-veil", "purifying-salt"]:
                    can_receive = False
            elif status_to_inflict == "burn":
                if "Fire" in attacker.types:
                    can_receive = False
                if attacker_ability in ["water-veil", "water-bubble"]:
                    can_receive = False
            elif status_to_inflict == "paralysis":
                if "Electric" in attacker.types:
                    can_receive = False
                if attacker_ability == "limber":
                    can_receive = False
            
            if can_receive:
                attacker.status = status_to_inflict
                attacker.status_turns = 0
                if status_to_inflict == "badly-poisoned":
                    attacker.toxic_counter = 0
    
    mon.status = status
    mon.status_turns = duration
    mon.toxic_counter = 0
    return True

def stab(move_type: str, user: Mon) -> float:
    """
    Calculates STAB taking Terastallization (including Stellar) into account.
    """
    if not move_type:
        return 1.0

    move_type_norm = move_type.strip().title()
    current_types = tuple(
        t.strip().title() for t in user.types if t
    )

    # Determine the ability-based STAB boost (Adaptability, etc.)
    ability = normalize_ability_name(user.ability or "")
    ability_data = get_ability_effect(ability)
    ability_stab = ability_data.get("stab_boost", 1.5)

    original_types_source = user._tera_original_types or user._original_types or user.types
    original_types = tuple(
        t.strip().title() for t in original_types_source if t
    )

    tera_type = _format_type_name(getattr(user, "tera_type", None))
    is_stellar = getattr(user, "_tera_is_stellar", False)

    # Default multiplier with no STAB
    multiplier = 1.0

    if getattr(user, "terastallized", False):
        if is_stellar:
            base = ability_stab if move_type_norm in original_types else 1.0
            unlimited = getattr(user, "_tera_boost_unlimited", False)
            already_used = move_type_norm in user._tera_boosted_types

            if not already_used or unlimited:
                target_multiplier = 2.0 if move_type_norm in original_types else 1.2
                base = max(base, target_multiplier)
                if not unlimited:
                    user._tera_boosted_types.add(move_type_norm)
            multiplier = base
        else:
            if tera_type and move_type_norm == tera_type:
                if ability_stab <= 1.5:
                    multiplier = 2.0
                else:
                    multiplier = ability_stab * 1.125
            elif move_type_norm in original_types:
                multiplier = ability_stab
            else:
                multiplier = 1.0
    else:
        if move_type_norm in current_types or move_type_norm in original_types:
            multiplier = ability_stab

    # === NULLSCAPE (Untyped): All moves become untyped, MissingNo gains STAB, others lose STAB ===
    nullscape_type = _get_nullscape_type(user)
    if nullscape_type == "Untyped":
        # All moves become untyped for STAB purposes
        # MissingNo gains STAB on all moves, others lose STAB
        if user.species.lower() in ["missing n0", "missingno", "missing n0"]:
            # MissingNo gains STAB on all moves (treated as if all moves are its type)
            multiplier = ability_stab
        else:
            # Other Pokémon lose STAB (no bonus)
            multiplier = 1.0
    
    return multiplier

def _get_nullscape_type(mon: Optional[Mon] = None, battle_state: Any = None) -> Optional[str]:
    """
    Check if Nullscape is active and return MissingNo's type.
    Returns None if Nullscape is not active, or the type string if it is.
    Only checks ACTIVE Pokemon on the field, not Pokemon in the party.
    """
    # Check if the provided mon has Nullscape (assumes mon is active if provided)
    if mon:
        ability = normalize_ability_name(mon.ability or "")
        if ability == "nullscape":
            # Get MissingNo's type
            mon_types = [t.strip().title() if t else None for t in mon.types]
            nullscape_type = mon_types[0] if mon_types else None
            return nullscape_type
    
    # Check ACTIVE Pokémon on the field for Nullscape (only active, not all in party)
    if battle_state:
        active_mons = []
        # Check player 1's active Pokemon
        if hasattr(battle_state, 'p1_team') and hasattr(battle_state, 'p1_active'):
            p1_active_idx = battle_state.p1_active
            if 0 <= p1_active_idx < len(battle_state.p1_team):
                p1_active = battle_state.p1_team[p1_active_idx]
                if p1_active and p1_active.hp > 0:
                    active_mons.append(p1_active)
        
        # Check player 2's active Pokemon
        if hasattr(battle_state, 'p2_team') and hasattr(battle_state, 'p2_active'):
            p2_active_idx = battle_state.p2_active
            if 0 <= p2_active_idx < len(battle_state.p2_team):
                p2_active = battle_state.p2_team[p2_active_idx]
                if p2_active and p2_active.hp > 0:
                    active_mons.append(p2_active)
        
        for m in active_mons:
            if m and m.ability:
                ab_norm = normalize_ability_name(m.ability)
                if ab_norm == "nullscape":
                    # Get MissingNo's type
                    m_types = [t.strip().title() if t else None for t in m.types]
                    nullscape_type = m_types[0] if m_types else None
                    return nullscape_type
    
    # Check via battle_state reference on mon (only active Pokemon)
    if mon and hasattr(mon, '_battle_state') and mon._battle_state:
        battle_state_ref = mon._battle_state
        active_mons_ref = []
        
        # Check player 1's active Pokemon
        if hasattr(battle_state_ref, 'p1_team') and hasattr(battle_state_ref, 'p1_active'):
            p1_active_idx = battle_state_ref.p1_active
            if 0 <= p1_active_idx < len(battle_state_ref.p1_team):
                p1_active = battle_state_ref.p1_team[p1_active_idx]
                if p1_active and p1_active.hp > 0:
                    active_mons_ref.append(p1_active)
        
        # Check player 2's active Pokemon
        if hasattr(battle_state_ref, 'p2_team') and hasattr(battle_state_ref, 'p2_active'):
            p2_active_idx = battle_state_ref.p2_active
            if 0 <= p2_active_idx < len(battle_state_ref.p2_team):
                p2_active = battle_state_ref.p2_team[p2_active_idx]
                if p2_active and p2_active.hp > 0:
                    active_mons_ref.append(p2_active)
        
        for m in active_mons_ref:
            if m and m.ability:
                ab_norm = normalize_ability_name(m.ability)
                if ab_norm == "nullscape":
                    # Get MissingNo's type
                    m_types = [t.strip().title() if t else None for t in m.types]
                    nullscape_type = m_types[0] if m_types else None
                    return nullscape_type
    
    return None

def _get_effective_move_type(move_type: str, user: Optional[Mon] = None, battle_state: Any = None) -> str:
    """
    Get the effective move type after Nullscape (Untyped) effect.
    If Nullscape (Untyped) is active, all moves become Untyped.
    """
    nullscape_type = _get_nullscape_type(user, battle_state)
    if nullscape_type == "Untyped":
        return "Untyped"
    return move_type

def type_multiplier(move_type: str, target: Mon, is_contact: bool = False, move_category: str = "physical", generation: int = 9, field_effects: Any = None, user: Mon = None) -> Tuple[float, Optional[str]]:
    """
    Calculate type effectiveness multiplier, considering abilities and generation.
    Returns (multiplier, ability_message)
    
    Generation-specific differences:
        - Gen 1: Ghost immunity to Psychic bugged (was 0x, should be 2x)
    - Gen 2-5: Steel resists Ghost and Dark (0.5x)
    - Gen 6+: Steel doesn't resist Ghost/Dark (1x)
    
    Args:
        field_effects: Optional for getting generation if not passed directly
        user: Optional attacker Mon for checking attacker abilities like Scrappy
    """
    if not move_type:
        return 1.0, None
    
    # Import ability functions at the start
    
    # === NULLSCAPE (Untyped): All moves become Untyped ===
    move_type = _get_effective_move_type(move_type, user, getattr(user, '_battle_state', None))
    
    # Normalize types to title case (Electric, Ground, etc.)
    move_type = move_type.strip().title() if move_type else "Normal"
    # Safely unpack types (handle single-element tuples/lists)
    if not target.types:
        types_tuple = (None, None)
    elif isinstance(target.types, tuple):
        types_tuple = target.types
    elif isinstance(target.types, list):
        types_tuple = tuple(target.types)
    else:
        # Fallback: treat as single type
        types_tuple = (target.types, None)
    
    t1 = types_tuple[0] if len(types_tuple) > 0 else None
    t2 = types_tuple[1] if len(types_tuple) > 1 else None
    t1 = t1.strip().title() if t1 else "Normal"
    t2 = t2.strip().title() if t2 else None
    
    # === AIR BALLOON: Ground immunity until popped ===
    if item_is_active(target):
        item_data = get_item_effect(normalize_item_name(target.item))
        if item_data.get("levitate_effect") and move_type == "Ground":
            # Mark balloon to be popped after this check
            if not hasattr(target, '_balloon_will_pop'):
                target._balloon_will_pop = True
            return 0.0, f"{target.species}'s **Air Balloon** made it immune to Ground!"
    
    # === MAGNET RISE: Ground immunity for 5 turns ===
    if move_type == "Ground" and hasattr(target, '_magnet_rise_turns') and getattr(target, '_magnet_rise_turns', 0) > 0:
        return 0.0, f"{target.species}'s **Magnet Rise** made it immune to Ground!"
    
    # === RING TARGET: Removes type immunities (Gen 5+) ===
    # Makes Ground vulnerable to Electric moves, etc.
    if item_is_active(target):
        target_item_data = get_item_effect(normalize_item_name(target.item))
        if target_item_data.get("removes_type_immunities"):
            gen_rt = get_generation(field_effects=field_effects)
            if gen_rt >= 5:
                # Skip type immunity checks - Ring Target holder can be hit by normally-immune moves
                # (Still calculate effectiveness normally, just don't block at 0x)
                pass
    
    # Check ability immunities (Ring Target doesn't remove ability-based immunities)
    ignore_target_ability = getattr(target, '_ability_temporarily_ignored', False)
    ability = normalize_ability_name(target.ability or "")
    if ignore_target_ability:
        ability = ""
        ability_data = {}
    else:
        ability_data = get_ability_effect(ability)
    
    # Earthbound: Grounds all Pokémon on the field (Flying types, Levitate, and the user itself)
    # Check if any Pokémon on the field has Earthbound (grounds all Flying types and Levitate Pokémon)
    user_ability = normalize_ability_name(user.ability or "") if user else ""
    user_ability_data = get_ability_effect(user_ability) if user else {}
    has_earthbound = False
    if user_ability_data.get("grounds_self_and_opponent"):
        has_earthbound = True
    else:
        # Check if any Pokémon on the field has Earthbound
        if hasattr(user, '_battle_state') and user._battle_state:
            battle_state_eb = user._battle_state
            all_mons_eb = []
            if hasattr(battle_state_eb, 'p1_party'):
                all_mons_eb.extend([m for m in battle_state_eb.p1_party if m and m.hp > 0])
            if hasattr(battle_state_eb, 'p2_party'):
                all_mons_eb.extend([m for m in battle_state_eb.p2_party if m and m.hp > 0])
            for mon in all_mons_eb:
                if mon and mon.ability:
                    mon_ab_norm = normalize_ability_name(mon.ability)
                    mon_ab_data = get_ability_effect(mon_ab_norm)
                    if mon_ab_data.get("grounds_self_and_opponent"):
                        has_earthbound = True
                        break
    
    # Earthbound: Grounds all Flying types and Levitate Pokémon, removing Ground immunity
    # Check if target is Flying type or has Levitate
    if has_earthbound and move_type == "Ground":
        target_types_list = [t.strip().title() if t else None for t in target.types]
        is_target_flying = "Flying" in target_types_list
        target_ability_norm = normalize_ability_name(target.ability or "")
        has_target_levitate = target_ability_norm == "levitate"
        
        # Earthbound grounds Flying types and Levitate Pokémon
        if is_target_flying or has_target_levitate:
            # Target is grounded by Earthbound, so Ground moves can hit
            # (This check happens before the normal immunity check below)
            pass  # Continue to damage calculation
    
    # Type immunity abilities (Levitate, Volt Absorb, etc.)
    if "immune_to" in ability_data:
        if move_type in ability_data["immune_to"]:
            ability_name = (target.ability or ability).replace("-", " ").title()
            
            # Earthbound: Overrides Levitate and Flying type immunity to Ground
            if has_earthbound and move_type == "Ground":
                # Earthbound grounds all Flying types and Levitate Pokémon, so Ground moves can hit
                # Continue to damage calculation instead of returning 0.0
                pass
            else:
                # Flash Fire - Boost Fire moves permanently after being hit by Fire
                if ability == "flash-fire":
                    target.flash_fire_active = True
                    return 0.0, f"{target.species}'s {ability_name} raised its Fire power!"
                
                # Absorb abilities (Volt Absorb, Water Absorb, etc.) - Heal HP
                elif ability_data.get("absorb"):
                    heal_percent = ability_data.get("heal_percent", 0.25)
                    heal_amt = max(1, int(target.max_hp * heal_percent))
                    target.hp = min(target.max_hp, target.hp + heal_amt)
                    return 0.0, f"{target.species}'s {ability_name} absorbed the attack! (+{heal_amt} HP)"
                
                # Boost-on-hit abilities (Sap Sipper, Lightning Rod, Motor Drive, Storm Drain, etc.) - Boost stats
                elif "boost_on_hit_stages" in ability_data:
                    # Lightning Rod / Storm Drain: Gen 3-4 (no boost), Gen 5+ (boost)
                    should_boost = True
                    if ability in ["lightning-rod", "storm-drain"]:
                        generation = get_generation(field_effects=field_effects)
                        if generation <= 4:
                            should_boost = False  # Gen 3-4: Immunity only, no stat boost
                    
                    messages = []
                    if should_boost:
                        boost_stages = ability_data["boost_on_hit_stages"]
                    for stat, amount in boost_stages.items():
                        old_stage = target.stages.get(stat, 0)
                        target.stages[stat] = min(6, old_stage + amount)
                        
                        stat_name = {
                            "atk": "Attack", "defn": "Defense", "spa": "Special Attack",
                            "spd": "Special Defense", "spe": "Speed"
                        }.get(stat, stat.upper())
                        
                        if amount == 2:
                            messages.append(f"{target.species}'s {stat_name} rose sharply!")
                        else:
                            messages.append(f"{target.species}'s {stat_name} rose!")
                    
                    if messages:
                        msg = f"{target.species}'s {ability_name} made it immune!\n" + "\n".join(messages)
                    else:
                        msg = f"{target.species}'s {ability_name} made it immune!"
                    return 0.0, msg
                
                # Standard immunity (Levitate, etc.)
                else:
                    return 0.0, f"{target.species}'s {ability_name} made it immune!"
    
    # Earth Eater - Ground immunity + heal 25% HP
    if ability == "earth-eater" and move_type == "Ground":
        heal_amt = max(1, target.max_hp // 4)
        target.hp = min(target.max_hp, target.hp + heal_amt)
        return 0.0, f"{target.species}'s Earth Eater absorbed the attack! (+{heal_amt} HP)"
    
    # Well-Baked Body - Fire immunity + Def boost
    if ability == "well-baked-body" and move_type == "Fire":
        old_stage = target.stages.get("defn", 0)
        target.stages["defn"] = min(6, old_stage + 2)
        return 0.0, f"{target.species}'s Well-Baked Body sharply raised its Defense!"
    
    # Wind Rider - Wind move immunity + Atk boost (Gen 9+)
    # Same 17 wind moves as Wind Power (excluding Sandstorm)
    wind_moves = [
        "aeroblast", "air-cutter", "bleakwind-storm", "blizzard", "fairy-wind",
        "gust", "heat-wave", "hurricane", "icy-wind", "petal-blizzard",
        "sandsear-storm", "springtide-storm", "tailwind", "twister",
        "whirlwind", "wildbolt-storm"
        # Note: Sandstorm is explicitly NOT included (targets field, not Pokémon)
    ]
    normalized_move = move_type.lower().replace(" ", "-")
    if ability == "wind-rider" and normalized_move in wind_moves:
        old_stage = target.stages.get("atk", 0)
        target.stages["atk"] = min(6, old_stage + 1)
        return 0.0, f"{target.species}'s Wind Rider made it immune and raised its Attack!"
    
    # Good as Gold - Status move immunity
    # (Handled separately in damage function for status moves)
    
    # Minds Eye - Normal and Fighting hit Ghost
    if ability == "minds-eye" and move_type in ["Normal", "Fighting"] and "Ghost" in [t1, t2]:
        # Remove Ghost immunity, make it normally effective
        mult = 1.0
        return mult, f"{target.species} was hit despite being a Ghost type!"
    
    # Foresight/Odor Sleuth - Normal and Fighting hit Ghost (removes Ghost immunity)
    if hasattr(target, '_foresight_ghost_immunity_removed') and target._foresight_ghost_immunity_removed:
        if move_type in ["Normal", "Fighting"] and "Ghost" in [t1, t2]:
            # Remove Ghost immunity, make it normally effective
            mult = 1.0
            # Continue to calculate other type effectiveness (e.g., dual types)
            if t2 and t2 != "Ghost":
                mult *= TYPE_MULT.get((move_type, t2), 1.0)
            return mult, None  # No message (silent bypass)
    
    # Scrappy - Normal and Fighting hit Ghost (Gen 4+)
    if user and user.ability:
        user_ability = normalize_ability_name(user.ability)
        user_ability_data = get_ability_effect(user_ability)
        if user_ability_data.get("hit_ghost_with_normal_fighting") and move_type in ["Normal", "Fighting"] and "Ghost" in [t1, t2]:
            # Remove Ghost immunity, make it normally effective
            mult = 1.0
            # Continue to calculate other type effectiveness (e.g., dual types)
            if t2 and t2 != "Ghost":
                mult *= TYPE_MULT.get((move_type, t2), 1.0)
            return mult, None  # No message (silent bypass)
    
    # Wonder Guard - only super effective moves hit
    if ability == "wonder-guard":
        mult = TYPE_MULT.get((move_type, t1), 1.0)
        if t2:
            mult *= TYPE_MULT.get((move_type, t2), 1.0)
        
        # Check if move bypasses Wonder Guard (generation-specific)
        # Note: Full generation logic handled in damage() function
        # This is just for type effectiveness calculation
        
        if mult <= 1.0:
            return 0.0, f"{target.species}'s Wonder Guard protected it!"
        return mult, None
    
    # Calculate base effectiveness
    # Earthbound: Override Ground vs Flying immunity
    if has_earthbound and move_type == "Ground" and "Flying" in [t1, t2]:
        # Earthbound grounds Flying types, so Ground moves can hit them
        # Calculate effectiveness as if Flying type wasn't present for Ground moves
        # If target is pure Flying, Ground moves are normally effective (1x)
        if t1 == "Flying" and not t2:
            mult = 1.0
        elif t1 == "Flying" and t2:
            # Dual type with Flying primary: use the other type's effectiveness
            mult = TYPE_MULT.get((move_type, t2), 1.0)
        elif t2 == "Flying":
            # Flying is secondary type: use primary type's effectiveness
            mult = TYPE_MULT.get((move_type, t1), 1.0)
        else:
            # Shouldn't happen, but fallback
            mult = TYPE_MULT.get((move_type, t1), 1.0)
            if t2:
                mult *= TYPE_MULT.get((move_type, t2), 1.0)
    else:
        mult = TYPE_MULT.get((move_type, t1), 1.0)
        if t2: 
            mult *= TYPE_MULT.get((move_type, t2), 1.0)
    
    # === RING TARGET: Removes type immunities (Gen 5+) ===
    # If mult would be 0 (immune), Ring Target makes it 1x instead
    has_ring_target_rt = False
    if item_is_active(target):
        rt_item_data = get_item_effect(normalize_item_name(target.item))
        if rt_item_data.get("removes_type_immunities"):
            gen_rt_check = get_generation(field_effects=field_effects)
            if gen_rt_check >= 5:
                has_ring_target_rt = True
    
    if mult == 0.0 and has_ring_target_rt:
        mult = 1.0  # Ring Target removes immunity, makes it neutral
    
    # === GENERATION-SPECIFIC TYPE CHART MODIFIERS ===
    
    # Gen 1: Type chart differences
    if generation == 1:
        # Gen 1: Ice was neutral (1x) against Fire (not 0.5x)
        if move_type == "Ice" and "Fire" in [t1, t2]:
            # Override: remove the 0.5x resistance, make it 1x
            if t1 == "Fire":
                mult /= TYPE_MULT.get((move_type, t1), 1.0)  # Divide out the 0.5x
                mult *= 1.0  # Apply 1x instead
            if t2 == "Fire":
                mult /= TYPE_MULT.get((move_type, t2), 1.0)  # Divide out the 0.5x
                mult *= 1.0  # Apply 1x instead
        
        # Gen 1: Bug was super-effective (2x) against Poison (not 0.5x)
        if move_type == "Bug" and "Poison" in [t1, t2]:
            # Override: remove the 0.5x resistance, make it 2x
            if t1 == "Poison":
                mult /= TYPE_MULT.get((move_type, t1), 1.0)  # Divide out the 0.5x
                mult *= 2.0  # Apply 2x instead
            if t2 == "Poison":
                mult /= TYPE_MULT.get((move_type, t2), 1.0)  # Divide out the 0.5x
                mult *= 2.0  # Apply 2x instead
        
        # Gen 1: Poison was super-effective (2x) against Bug (not 0.5x)
        if move_type == "Poison" and "Bug" in [t1, t2]:
            # Override: remove the 0.5x resistance, make it 2x
            if t1 == "Bug":
                mult /= TYPE_MULT.get((move_type, t1), 1.0)  # Divide out the 0.5x
                mult *= 2.0  # Apply 2x instead
            if t2 == "Bug":
                mult /= TYPE_MULT.get((move_type, t2), 1.0)  # Divide out the 0.5x
                mult *= 2.0  # Apply 2x instead
        
        # Gen 1: Ghost immunity to Psychic bug (Ghost moves didn't affect Psychic)
        # This was a bug - Ghost should be super-effective against Psychic
        if move_type == "Ghost" and "Psychic" in [t1, t2]:
            # Override to 0x (the bug made it immune)
            mult = 0.0
    
    # Gen 2-5: Steel resists Ghost and Dark (removed in Gen 6)
    if generation >= 2 and generation <= 5:
        if "Steel" in [t1, t2]:
            if move_type in ["Ghost", "Dark"]:
                # Apply 0.5x resistance for each Steel typing
                if t1 == "Steel":
                    mult *= 0.5
                if t2 == "Steel":
                    mult *= 0.5
    
    # === TYPE EFFECTIVENESS EXCEPTIONS ===
    # These moves have special type interactions that override the normal type chart
    # (handled outside this function, but noted here for reference)
    
    # Resistance abilities
    if "resist_types" in ability_data:
        resist_types = ability_data["resist_types"]
        resist_mult = ability_data.get("multiplier", 0.5)
        
        # Thick Fat, Heatproof, etc.
        if move_type in resist_types:
            mult *= resist_mult
        
        # Fluffy - resists contact moves
        if "Physical" in resist_types and move_category == "physical" and is_contact:
            mult *= resist_mult
        
        # Ice Scales - resists special moves
        if "special" in ability_data.get("resist_category", []) and move_category == "special":
            mult *= resist_mult
    
    # Weakness modifiers
    if "weak_to" in ability_data:
        if move_type in ability_data["weak_to"]:
            mult *= ability_data.get("weak_mult", 2.0)
    
    # Dry Skin - weak to Fire
    if ability == "dry-skin" and move_type == "Fire":
        mult *= ability_data.get("weak_to_fire", 1.25)
    
    # Fluffy - double Fire damage
    if ability == "fluffy" and move_type == "Fire":
        mult *= 2.0

    if getattr(target, '_tar_shot_active', False) and move_type == "Fire":
        mult *= 2.0
    
    return mult, None

def _crit_multiplier(move_name: str, ability: Optional[str], item: Optional[str], 
                     species: str, focused_energy_stage: int = 0, generation: int = 9) -> Tuple[float, bool]:
    """
    Calculate critical hit with proper stages and generation-specific multipliers.
    Returns: (multiplier, is_crit)
    
    Generation-specific critical hit damage:
        - Gen 1-5: 2.0x damage
        - Gen 6+: 1.5x damage
    """
    
    crit_chance = calculate_crit_chance(move_name, ability, item, species,
                                        focus_stage=focused_energy_stage,
                                        generation=generation)
    is_crit = random.random() < crit_chance
    
    if is_crit:
        # Gen 1-5: 2x, Gen 6+: 1.5x
        crit_mult = 2.0 if generation <= 5 else 1.5
    else:
        crit_mult = 1.0
    
    return (crit_mult, is_crit)

def _accuracy_check(
    acc: int,
    attacker: Mon,
    target: Mon,
    field_effects: Any = None,
    move_category: str = "physical",
    move_name: str = "",
    *,
    ignores_target_ability: bool = False
) -> bool:
    """
    Check if move hits with accuracy/evasion stages, including item and ability boosts.
    Gen I-II: Accuracy_modified = Accuracy_move × Accuracy_user × Evasion_target - BrightPowder (1-255); R 0-255; hit if R < Accuracy_modified (Gen II: if 255 then guaranteed hit).
    Gen III+: Accuracy_move × AdjustedStages × Modifier; R 1-100 or decimal roll.
    """
    original_acc = acc  # For Gen I-II we use base move accuracy in 0-255 formula
    move_lower_norm = move_name.lower().replace(" ", "-") if move_name else ""
    
    # Toxic: Gen VI+ Poison types never miss (even vs semi-invulnerable)
    if move_lower_norm == "toxic":
        gen_toxic_acc = get_generation(field_effects=field_effects)
        if gen_toxic_acc >= 6:
            user_types = [t.strip().title() if t else None for t in getattr(attacker, 'types', (None, None))]
            if "Poison" in user_types:
                # Poison-type Toxic never misses (bypasses accuracy and semi-invulnerable)
                # Note: Toxic sure-hit glitch (fixed in 1.3.1) - we'll implement the fixed version
                acc = None  # Never miss
                # Message will be added in apply_move if needed
    
    # === WEATHER & TYPE-AFFECTED ACCURACY ===
    # Check for weather/type-based accuracy modifiers (Thunder, Hurricane, Blizzard, Toxic)
    weather = getattr(field_effects, 'weather', None) if field_effects else None
    weather_acc = check_weather_accuracy(move_name, weather, attacker.types)
    if weather_acc is not None:
        acc = weather_acc  # Override accuracy
    
    # Telekinesis: target is easier to hit (except OHKO moves or if semi-invulnerable)
    if getattr(target, '_telekinesis_turns', 0) > 0 and not getattr(target, 'invulnerable', False):
        ohko_moves = {"fissure", "horn-drill", "guillotine", "sheer-cold"}
        if move_lower_norm not in ohko_moves:
            return True

    # === Z-MOVES: Always hit (bypass accuracy) unless semi-invulnerable ===
    if hasattr(attacker, '_is_z_move') and attacker._is_z_move:
        # Check if target is semi-invulnerable (Dig, Fly, Dive, etc.)
        # Semi-invulnerable check is handled elsewhere, but we still need to check accuracy
        # Z-Moves always pass accuracy checks
        return True
    
    # Handle None accuracy (treat as never-miss)
    if acc is None or acc <= 0:  # Never-miss moves
        return True
    
    if field_effects is None:
        field_effects = FieldEffects()
    generation = get_generation(field_effects=field_effects)

    if move_lower_norm == "pursuit" and getattr(target, '_is_switching', False) and generation >= 3:
        return True
    
    if move_lower_norm == "psych-up" and generation <= 2:
        return True
    
    # === MICLE BERRY: Next move accuracy boost ===
    if hasattr(attacker, '_micle_active') and attacker._micle_active:
        mult = getattr(attacker, '_micle_multiplier', 1.2)
        try:
            acc = int(acc * mult) if acc is not None else acc
        except Exception:
            pass
        # Clear once used
        attacker._micle_active = False
        if hasattr(attacker, '_micle_multiplier'):
            delattr(attacker, '_micle_multiplier')

    # Minimize accuracy bypass (Gen 6+): certain moves always hit minimized targets
    if generation >= 6 and hasattr(target, '_minimized') and target._minimized:
        meff_acc = get_move_secondary_effect(move_name)
        if meff_acc.get('always_hits_minimize'):
            return True
        if meff_acc.get('doubled_minimize'):
            return True

    # === ABILITY CHECKS ===
    attacker_ability = normalize_ability_name(attacker.ability or "")
    attacker_ability_data = get_ability_effect(attacker_ability)
    
    # No Guard: All moves always hit (both attacker and target)
    target_ability = normalize_ability_name(target.ability or "")
    if ignores_target_ability:
        target_ability = ""
        target_ability_data = {}
    else:
        target_ability_data = get_ability_effect(target_ability)
    if attacker_ability_data.get("perfect_accuracy") or target_ability_data.get("perfect_accuracy"):
        return True
    
    # Wonder Skin: Status moves become 50% accurate
    if target_ability == "wonder-skin" and move_category == "status":
        acc = 50
    
    if move_lower_norm == "vital-throw":
        return True

    # === GEN I-II: 0-255 accuracy formula and R 0-255 roll ===
    if generation <= 2:
        base_acc = acc  # Already weather-overridden / Wonder Skin if applicable
        if base_acc is None or base_acc <= 0:
            return True
        # Gen II Mind Reader: guaranteed hit (consume effect)
        if generation == 2 and getattr(target, "_mind_reader_active", False):
            target._mind_reader_active = False
            if hasattr(target, "_mind_reader_user"):
                delattr(target, "_mind_reader_user")
            if hasattr(target, "_mind_reader_source"):
                delattr(target, "_mind_reader_source")
            if move_lower_norm not in ["earthquake", "fissure", "magnitude"]:
                return True
        acc_move_255 = _nominal_accuracy_to_255(base_acc)
        acc_stage = attacker.stages.get("accuracy", 0)
        eva_stage = target.stages.get("evasion", 0)
        # Gen II: if user's accuracy stage < target's evasion stage, both treated as 0
        if generation == 2 and acc_stage < eva_stage:
            acc_stage = 0
            eva_stage = 0
        acc_user_mult = get_stage_multiplier(acc_stage, generation=generation)
        eva_target_mult = get_stage_multiplier(eva_stage, generation=generation)
        bright_powder = 0
        if generation == 2 and item_is_active(target) and normalize_item_name(target.item) == "bright-powder":
            bright_powder = 20
        accuracy_modified = int(acc_move_255 * acc_user_mult * eva_target_mult) - bright_powder
        accuracy_modified = max(1, min(255, accuracy_modified))
        # 100% accuracy (255 on 0–255 scale): guaranteed hit in both Gen I and Gen II
        if accuracy_modified >= 255:
            return True
        R = random.randint(0, 255)
        return R < accuracy_modified

    # Compound Eyes: +30% accuracy
    if attacker_ability_data.get("accuracy_mult"):
        acc = int(acc * attacker_ability_data["accuracy_mult"])
    
    # Hustle: -20% accuracy for physical moves
    if attacker_ability_data.get("accuracy_mult_physical") and move_category == "physical":
        acc = int(acc * attacker_ability_data["accuracy_mult_physical"])
    
    # === ACCURACY ITEMS ===
    # Wide Lens: +10% accuracy
    if item_is_active(attacker):
        item_data = get_item_effect(normalize_item_name(attacker.item))
        if "accuracy_mult" in item_data:
            acc = int(acc * item_data["accuracy_mult"])
        # Zoom Lens: +20% accuracy if moving after target
        elif "accuracy_boost_when_slower" in item_data:
            attacker_speed = _speed_value(attacker, None)
            target_speed = _speed_value(target, None)
            if attacker_speed < target_speed:
                acc = int(acc * item_data["accuracy_boost_when_slower"])
    
    # === BRIGHT POWDER / LAX INCENSE: Reduce opponent accuracy (generation-specific) ===
    if item_is_active(target):
        t_item_norm = normalize_item_name(target.item)
        t_item_data = get_item_effect(t_item_norm)
        gen_bp = generation
        
        # Bright Powder: Gen 2 (20/256 miss chance), Gen 3+ (0.9 multiplier)
        if t_item_norm == "bright-powder":
            min_gen = t_item_data.get("min_gen", 2)
            if gen_bp >= min_gen:
                gen_specific_bp = t_item_data.get("gen_specific", {})
                if gen_bp == 2 and "2" in gen_specific_bp:
                    # Gen 2: Additional 20/256 miss chance (handled separately in accuracy calculation)
                    # This is an additional roll after normal accuracy check
                    miss_chance = gen_specific_bp["2"].get("accuracy_miss_chance", 20/256)
                    # Store for later check (will need to add a secondary check)
                    # For now, approximate by reducing accuracy more
                    acc = int(acc * (1.0 - miss_chance))
                elif gen_bp >= 3 and "3+" in gen_specific_bp:
                    # Gen 3+: Multiply accuracy by 0.9
                    acc_mult = gen_specific_bp["3+"].get("accuracy_multiplier", 0.9)
                    acc = int(acc * acc_mult)
        
        # Lax Incense: Gen 3 (0.95 multiplier), Gen 4+ (0.9 multiplier)
        elif t_item_norm == "lax-incense":
            min_gen = t_item_data.get("min_gen", 3)
            if gen_bp >= min_gen:
                gen_specific_li = t_item_data.get("gen_specific", {})
                if gen_bp == 3 and "3" in gen_specific_li:
                    # Gen 3: Multiply accuracy by 0.95
                    acc_mult = gen_specific_li["3"].get("accuracy_multiplier", 0.95)
                    acc = int(acc * acc_mult)
                elif gen_bp >= 4 and "4+" in gen_specific_li:
                    # Gen 4+: Multiply accuracy by 0.9
                    acc_mult = gen_specific_li["4+"].get("accuracy_multiplier", 0.9)
                    acc = int(acc * acc_mult)
        
        # Fallback for items using old format
        elif "opponent_accuracy_reduction" in t_item_data:
            acc = int(acc * t_item_data["opponent_accuracy_reduction"])
    
    # === MIND READER / LOCK-ON & NIGHTMARE ACCURACY ===

    # Conversion 2 Gen V+: ignores accuracy (fails only on semi-invulnerable handled elsewhere)
    if move_lower_norm == "conversion-2" and generation >= 5:
        return True

    # Nightmare generation-specific accuracy handling
    if move_lower_norm == "nightmare":
        if generation == 2:
            acc = None  # Bypass accuracy (still fails on semi-invulnerable targets)
        elif generation >= 4:
            acc = 100
    
    # Gen II: Mind Reader attached to target (any attacker benefits)
    if generation == 2:
        if hasattr(target, '_mind_reader_active') and target._mind_reader_active:
            # Consume effect regardless of outcome
            target._mind_reader_active = False
            if hasattr(target, '_mind_reader_user'):
                target._mind_reader_user = None
            if hasattr(target, '_mind_reader_source'):
                target._mind_reader_source = None
            # Earthquake, Fissure, Magnitude still miss Fly in Gen II
            if move_lower_norm not in ["earthquake", "fissure", "magnitude"]:
                return True  # Mind Reader ensures hit
    
    # Gen III+: User-specific Mind Reader/Lock-On
    if generation >= 3:
        if hasattr(attacker, 'lock_on_target') and attacker.lock_on_target == target:
            if hasattr(attacker, 'lock_on_turns') and attacker.lock_on_turns > 0:
                # Gen IV bug with protection (NOT implementing bug per user request)
                attacker.lock_on_turns = 0
                attacker.lock_on_target = None
                if hasattr(attacker, '_mind_reader_target'):
                    attacker._mind_reader_target = None
                if hasattr(target, '_mind_reader_user') and target._mind_reader_user == attacker:
                    target._mind_reader_user = None
                return True  # Mind Reader/Lock-On ensures hit
    
    # Snow Cloak / Sand Veil: Reduce accuracy in respective weather
    if field_effects:
        target_ability = normalize_ability_name(target.ability or "")
        if ignores_target_ability:
            target_ability = ""
        if ignores_target_ability:
            target_ability = ""
        weather = getattr(field_effects, 'weather', None)
        
        # Snow Cloak: Reduces accuracy in hail/snow
        if target_ability == "snow-cloak" and weather in ["hail", "snow"]:
            generation = get_generation(field_effects=field_effects)
            if generation == 4:
                acc = int(acc * 0.8)  # 4/5 = 0.8
            else:
                acc = int(acc * 3277 / 4096)  # Gen 5+: More precise multiplier
        
        # Sand Veil: Reduces accuracy in sandstorm
        elif target_ability == "sand-veil" and weather == "sandstorm":
            generation = get_generation(field_effects=field_effects)
            if generation == 4:
                acc = int(acc * 0.8)  # 4/5 = 0.8
            else:
                acc = int(acc * 3277 / 4096)  # Gen 5+: More precise multiplier
    
    # Foresight Gen IV+: Perfect accuracy (always hits unless semi-invulnerable)
    if hasattr(target, '_foresight_perfect_acc') and target._foresight_perfect_acc:
        # Check if target is semi-invulnerable (handled elsewhere, but we still need to check accuracy)
        # For now, return True (semi-invulnerable check happens before accuracy)
        return True

    # === GEN III-IV: Accuracy_move × AdjustedStages × Modifier; R 1-100, hit if R <= Accuracy_modified ===
    # acc already has Modifier applied (Compound Eyes, Hustle, items, Bright Powder, Lax Incense, Sand Veil, Snow Cloak, etc.)
    if generation in (3, 4):
        net_stage = max(-6, min(6, attacker.stages.get("accuracy", 0) - target.stages.get("evasion", 0)))
        adj_stage_mult = get_stage_multiplier(net_stage, generation=generation)
        accuracy_modified = acc * adj_stage_mult
        if accuracy_modified >= 100:
            return True
        acc_mod_int = min(100, max(1, int(round(accuracy_modified))))
        R = random.randint(1, 100)
        return R <= acc_mod_int

    hit, accuracy_used = does_move_hit(
        acc,
        attacker.stages.get("accuracy", 0),
        target.stages.get("evasion", 0),
        field_effects,
        attacker.ability,
        target.ability,
        move_name=move_name,
        target=target
    )
    return hit

def _speed_value(m: Mon, side_effects: Any = None, field_effects: Any = None) -> int:
    """
    Calculate effective speed including item boosts, status conditions, Tailwind, and weather abilities.
    Accounts for Swift Swim, Chlorophyll, Sand Rush, Slush Rush, Unburden, etc.
    """
    # Custap Berry: if active, move first within priority bracket. Simulate via huge Speed.
    if getattr(m, '_custap_active', False):
        return 10**9
    
    # Get base speed with item boosts (Choice Scarf, etc.) and stat stages
    base_speed = get_effective_stat(m, "spe")
    generation = get_generation(field_effects=field_effects)
    if getattr(m, "mega_evolved", False) and generation <= 6 and not getattr(m, "_mega_speed_applied", False):
        if m._mega_speed_override is not None:
            base_speed = m._mega_speed_override
    speed = base_speed
    
    # Unburden: 2x Speed when item is consumed/lost
    ability = normalize_ability_name(m.ability or "")
    if ability == "unburden":
        # Check if Unburden boost is active (item was consumed/lost)
        if getattr(m, '_unburden_active', False):
            speed *= 2
    
    # Paralysis halves speed (unless Quick Feet in Gen 5+)
    if m.status == "par":
        ability_data = get_ability_effect(ability)
        negates_para_penalty = ability_data.get("paralysis_speed_penalty_negation", False)
        
        # Quick Feet: Gen 3-4 (doesn't negate), Gen 5+ (negates)
        if negates_para_penalty and ability == "quick-feet":
            generation = get_generation(field_effects=field_effects)
            if generation <= 4:
                negates_para_penalty = False  # Gen 3-4: Quick Feet doesn't negate paralysis penalty
        
        if not negates_para_penalty:
            speed = speed * 0.5
    
    # Quick Feet: 1.5x Speed when statused
    if m.status:
        ability = normalize_ability_name(m.ability or "")
        ability_data = get_ability_effect(ability)
        speed_mult_status = ability_data.get("speed_mult_status", 1.0)
        if speed_mult_status > 1.0:
            speed = speed * speed_mult_status
    
    # Weather-based speed boosts (Swift Swim, Chlorophyll, Sand Rush, Slush Rush)
    if field_effects and m.ability:
        ability = normalize_ability_name(m.ability)
        ability_data = get_ability_effect(ability)
        
        weather_mult = ability_data.get("speed_mult")
        required_weather = ability_data.get("weather")
        
        if weather_mult and required_weather:
            current_weather = getattr(field_effects, 'weather', None)
            # Normalize weather names (hail/snow are interchangeable)
            if current_weather == "snow":
                current_weather = "hail"
            if required_weather == "snow":
                required_weather = "hail"
            
            if current_weather == required_weather:
                speed = speed * weather_mult
        
        # Surge Surfer: 2x Speed in Electric Terrain (Gen 7+)
        if ability == "surge-surfer" and generation >= 7:
            current_terrain = getattr(field_effects, 'terrain', None)
            if current_terrain == "electric":
                speed = speed * 2.0
    
    # Tailwind doubles speed
    if side_effects and hasattr(side_effects, 'tailwind') and side_effects.tailwind:
        speed = speed * 2.0
    
    return int(speed)

def _contact_side_effects(attacker: Mon, defender: Mon, move_obj: Dict[str, Any], field_effects: Any = None,
                          attacker_side: Any = None, defender_side: Any = None, damage_dealt: int = 0) -> List[str]:
    """Apply all contact effects from abilities and items.
    
    Args:
        damage_dealt: Amount of damage dealt by the move (for Gen 3-4 Rough Skin check)
    """
    out: List[str] = []
    
    # Check contact flag - be more lenient with different formats
    contact_flag = move_obj.get("contact", 0)
    # Accept both 1 (int) and True (bool) as contact
    if contact_flag != 1 and contact_flag is not True:
        return out

    if getattr(defender, '_endure_skip_contact', False):
        return out

    # === PROTECTIVE PADS / PUNCHING GLOVE: Ignore all contact effects ===
    if item_is_active(attacker):
        item_data = get_item_effect(normalize_item_name(attacker.item))
        if item_data.get("no_contact_effects") or item_data.get("prevents_contact"):
            return out  # Skip all contact effects
    
    # === STORE DEFENDER'S ITEM EARLY (for Rocky Helmet with Knock Off) ===
    # Store item name early so Rocky Helmet can trigger even if item is removed by Knock Off
    defender_item_normalized = (defender.item or "").lower().replace(" ", "-") if defender.item else ""
    
    # === ABILITY-BASED CONTACT EFFECTS ===
    ability = normalize_ability_name(defender.ability or "")
    
    # Check if ability is suppressed (e.g., by Neutralizing Gas)
    if getattr(defender, "_ability_suppressed", False):
        return out
    
    ability_data = get_ability_effect(ability)
    
    # === IRON BARBS: Handle first (always trigger if conditions met) ===
    # Process Iron Barbs separately to ensure it always triggers when it should
    # Check both normalized and original ability name to be safe
    # Iron Barbs triggers even if the defender faints (defender.hp <= 0)
    defender_ability_raw = (defender.ability or "").lower().replace(" ", "-").strip()
    if (ability == "iron-barbs" or defender_ability_raw == "iron-barbs" or defender_ability_raw == "ironbarbs"):
        if attacker.hp > 0:  # Only check attacker is alive, defender can be fainted
            damage_percent = 0.125  # Always 1/8
            chip = max(1, int(attacker.max_hp * damage_percent))
            attacker.hp = max(0, attacker.hp - chip)
            # ALWAYS add message when Iron Barbs triggers - no conditions
            ability_name = (defender.ability or ability or "Iron Barbs").replace("-", " ").title()
            iron_barbs_msg = f"{attacker.species} was hurt by {ability_name}!"
            out.append(iron_barbs_msg)
    
    if ability_data and "on_contact" in ability_data:
        contact_effect = ability_data["on_contact"]
        
        # Rough Skin: Works the same as Iron Barbs (Gen 3-4: 1/16, only if damage dealt; Gen 5+: 1/8, even if 0 damage)
        # Rough Skin triggers even if the defender faints (defender.hp <= 0), same as Iron Barbs
        if ability == "rough-skin" and "damage" in contact_effect:
            generation = get_generation(field_effects=field_effects)
            if generation <= 4:
                if damage_dealt > 0 and attacker.hp > 0:  # Only check attacker is alive, defender can be fainted
                    damage_percent = 0.0625  # 1/16 in Gen 3-4
                    chip = max(1, int(attacker.max_hp * damage_percent))
                    attacker.hp = max(0, attacker.hp - chip)
                    ability_name = (defender.ability or ability).replace("-", " ").title()
                    out.append(f"{attacker.species} was hurt by {ability_name}!")
            else:
                # Gen 5+: Always triggers, even if 0 damage (but only if attacker has HP, defender can be fainted)
                if attacker.hp > 0:  # Only check attacker is alive, defender can be fainted
                    damage_percent = 0.125  # 1/8 in Gen 5+
                    chip = max(1, int(attacker.max_hp * damage_percent))
                    attacker.hp = max(0, attacker.hp - chip)
                    ability_name = (defender.ability or ability).replace("-", " ").title()
                    out.append(f"{attacker.species} was hurt by {ability_name}!")
    
    # On-contact status effects (Static, Flame Body, Poison Point, etc.)
    # Check if ability_data exists and has on_contact
    if ability_data and "on_contact" in ability_data and attacker.hp > 0:
        contact_effect = ability_data["on_contact"]
        chance = contact_effect.get("chance", 1.0)
        
        # Effect Spore: Gen 3-4 (10%), Gen 5+ (30%)
        if ability == "effect-spore":
            generation = get_generation(field_effects=field_effects)
            if generation <= 4:
                chance = 0.1  # Gen 3-4: 10%
            else:
                chance = 0.3  # Gen 5+: 30%
        
        # Poison Point: Gen 3 (33.33%), Gen 4+ (30%)
        if ability == "poison-point":
            generation = get_generation(field_effects=field_effects)
            if generation == 3:
                chance = 1/3  # Gen 3: 33.33%
            else:
                chance = 0.3  # Gen 4+: 30%
        
        # Static: Gen 3 (33.33%), Gen 4+ (30%)
        if ability == "static":
            generation = get_generation(field_effects=field_effects)
            if generation == 3:
                chance = 1/3  # Gen 3: 33.33%
            else:
                chance = 0.3  # Gen 4+: 30%
        
        # Gen 6+: Effect Spore is blocked by Grass-type, Overcoat, or Safety Goggles
        effect_spore_blocked = False
        if ability == "effect-spore":
            # Check if attacker is Grass-type
            if "Grass" in attacker.types:
                effect_spore_blocked = True
            
            # Check for Overcoat ability
            attacker_ability = normalize_ability_name(attacker.ability or "")
            if attacker_ability == "overcoat":
                effect_spore_blocked = True
            
            # Check for Safety Goggles item
            if item_is_active(attacker):
                attacker_item_data = get_item_effect(normalize_item_name(attacker.item))
                if attacker_item_data.get("powder_immunity"):
                    effect_spore_blocked = True
        
        # Status infliction (Static, Flame Body, Poison Point, Effect Spore, Cute Charm) - requires chance roll
        if not effect_spore_blocked and random.random() < chance:
            if "status" in contact_effect:
                status_list = contact_effect["status"]
                if not isinstance(status_list, list):
                    status_list = [status_list]
                
                # Effect Spore: random status from list
                status_to_apply = random.choice(status_list) if len(status_list) > 1 else status_list[0]
                
                # Check if attacker can be affected
                if not attacker.status and status_to_apply not in ["infatuated"]:
                    can_apply, block_reason = can_inflict_status(
                        attacker,
                        status_to_apply,
                        field_effects=field_effects,
                        from_ability=ability,
                        target_side=attacker_side
                    )
                    if can_apply:
                        attacker.status = status_to_apply
                        ability_name = (defender.ability or ability).replace("-", " ").title()
                        status_names = {"par": "paralyzed", "brn": "burned", "psn": "poisoned", "slp": "put to sleep"}
                        status_msg = status_names.get(status_to_apply, "affected")
                        out.append(f"{attacker.species} was {status_msg} by {ability_name}!")
                    elif block_reason:
                        out.append(block_reason)
            
            # Ability change (Mummy, Wandering Spirit)
            elif "change_ability" in contact_effect:
                new_ability = contact_effect["change_ability"]
                
                # List of abilities immune to Mummy (Bulbapedia)
                immune_abilities = [
                    "as-one", "battle-bond", "comatose", "commander", "disguise",
                    "gulp-missile", "ice-face", "lingering-aroma", "multitype",
                    "power-construct", "rks-system", "schooling", "shields-down",
                    "stance-change", "zen-mode", "zero-to-hero", "mummy"
                ]
                
                attacker_ability_norm = normalize_ability_name(attacker.ability or "")
                if attacker_ability_norm not in immune_abilities:
                    # Store original ability for restoration on switch-out
                    if not hasattr(attacker, '_original_ability_before_mummy'):
                        attacker._original_ability_before_mummy = attacker.ability
                    attacker.ability = new_ability
                    ability_name = (defender.ability or ability).replace("-", " ").title()
                    out.append(f"{attacker.species}'s Ability became {ability_name} because of {defender.species}'s {ability_name}!")
    
    # On-contact stat changes (Gooey, Tangling Hair)
    if "on_contact_stages" in ability_data and attacker.hp > 0:
        stage_effect = ability_data["on_contact_stages"]
        stage_msgs = modify_stages(attacker, {k: v for k, v in stage_effect.items() if k != "target"})
        for msg in stage_msgs:
            out.append(msg)
    
    # === ROCKY HELMET ===
    # Use the stored item name (from before Knock Off removes it) so Rocky Helmet triggers even if removed by Knock Off
    # Rocky Helmet triggers even if the defender faints (defender.hp <= 0)
    if defender_item_normalized == "rocky-helmet" and attacker.hp > 0:
        chip = max(1, attacker.max_hp // 6)
        attacker.hp = max(0, attacker.hp - chip)
        out.append(f"{attacker.species} was hurt by Rocky Helmet! (-{chip} HP)")
    
    # === STICKY BARB: Transfer on contact (Gen 4+) ===
    # Transfers even with Knock Off, happens after all other contact effects
    if item_is_active(defender) and defender.item:
        def_item_sticky = normalize_item_name(defender.item)
        def_item_data_sticky = get_item_effect(def_item_sticky)
        gen_sticky = get_generation(field_effects=field_effects)
        if def_item_data_sticky.get("can_transfer") and gen_sticky >= 4:
            # Transfer Sticky Barb to attacker (if attacker has no item)
            if not attacker.item:
                attacker.item = defender.item
                defender.item = None
                out.append(f"{attacker.species} was stuck by {defender.species}'s Sticky Barb!")

    return out

def damage(user: Mon, target: Mon, move_name: str, field_effects: Any = None, target_side: Any = None,
           user_side: Any = None, is_moving_last: bool = False, parental_bond_multiplier: float = 1.0) -> Tuple[int, Dict[str, Any], List[str]]:
    """
    Return (damage, meta, extra_log). Handles accuracy, STAB, effectiveness, crit, random.
    
    Args:
        user: Pokemon using the move
        target: Pokemon being targeted
        move_name: Name of the move
        field_effects: Field conditions
        target_side: Target's side effects
        is_moving_last: Whether user is moving last this turn (for Analytic)
        parental_bond_multiplier: Damage multiplier for Parental Bond second hit (0.5 Gen 6, 0.25 Gen 7+)
    """
    # Clear one-turn Custap boost if present (benefit applies to ordering only)
    if hasattr(user, '_custap_active') and user._custap_active:
        user._custap_active = False
    
    # Check if this is a Z-Move or Max Move - if so, use original move name for database lookup
    # Z-Move names like "Never-Ending Nightmare" may not exist in DB or have NULL power
    # Max Move names like "Max Lightning" may not exist in DB or have wrong type
    actual_move_name = move_name
    max_move_type = None
    if hasattr(user, '_is_z_move') and user._is_z_move:
        # Use the original move name for database lookup, not the Z-Move name
        actual_move_name = getattr(user, '_original_move_name', move_name)
    elif hasattr(user, '_is_max_move') and user._is_max_move:
        # Use the original move name for database lookup, not the Max Move name
        actual_move_name = getattr(user, '_original_move_name_max', move_name)
        # Get the Max Move type from the Max Move name
        from .max_moves import MAX_MOVE_NAMES
        move_name_normalized = move_name.replace("-", " ").title()
        for move_type, max_move_name in MAX_MOVE_NAMES.items():
            if max_move_name == move_name_normalized or max_move_name.replace(" ", "-").lower() == move_name.lower():
                max_move_type = move_type
                break
        # If not found in MAX_MOVE_NAMES, try to get from original move
        if not max_move_type and actual_move_name != move_name:
            max_move_type = get_actual_move_type_for_max_move(actual_move_name, user, field_effects)
    
    # BattleState for move cache (avoid DB round-trips when possible)
    battle_state_ctx = getattr(user, "_battle_state", None) or getattr(target, "_battle_state", None)
    # Get generation for generation-specific stats
    generation_for_stats = get_generation(field_effects=field_effects)
    mv = load_move(actual_move_name, generation=generation_for_stats, battle_state=battle_state_ctx)
    if not mv:
        # Move not found in database - return 0 damage
        return 0, {"failed": True}, [f"Move {actual_move_name} not found in database!"]
    
    # Get move type early (used for weather and ability checks)
    move_type_for_weather = mv.get("type", "Normal")
    
    # === GENERATION-SPECIFIC MOVE BANS ===
    generation_check = get_generation(field_effects=field_effects)
    move_lower_ban = move_name.lower().replace(" ", "-")

    secondary_effect_data = get_move_secondary_effect(move_name)
    move_effect_main = get_move_effects(move_name, battle_state_ctx) or {}

    if move_effect_main.get("fails_if_no_terrain"):
        terrain_active = field_effects and getattr(field_effects, "terrain", None)
        if not terrain_active:
            if hasattr(user, "_last_move_failed"):
                user._last_move_failed = True
            return 0, {"failed": True}, ["But it failed! (There was no terrain!)"]

    target_item_before = getattr(target, "item", None)

    generation_override = getattr(battle_state_ctx, "gen", None)
    if generation_override is None:
        generation_override = getattr(user, "_generation_context", None)
    if generation_override is None and target is not None:
        generation_override = getattr(target, "_generation_context", None)
    if generation_override is not None:
        generation_check = generation_override
        try:
            user._generation_context = generation_override
            if target is not None:
                target._generation_context = generation_override
            if battle_state_ctx and getattr(battle_state_ctx, "gen", None) != generation_override:
                battle_state_ctx.gen = generation_override
        except Exception:
            pass
    if move_effect_main.get("fails_if_no_item"):
        if not target_item_before:
            if hasattr(user, "_last_move_failed"):
                user._last_move_failed = True
            return 0, {"failed": True}, [f"But it failed! ({target.species} has no held item!)"]
    ignores_target_ability = bool(
        secondary_effect_data.get("ignores_ability") or move_effect_main.get("ignores_ability")
    )
    if secondary_effect_data.get("thaws_user") and getattr(user, 'status', None) == "frz":
        user.status = None
        log.append(f"{user.species} thawed out!")
    
    # Gen VIII+: Egg Bomb, Bone Club, Clamp, Spike Cannon, Constrict, Kinesis, Barrage, Dizzy Punch, Bubble (Sword/Shield), Flash, Psywave, Sharpen, Conversion 2 (initial), Aeroblast (initial), Feint Attack, Foresight, and Lovely Kiss (initial) cannot be selected
    # Note: Bonemerang, Hyper Fang banned in Gen VIII 1.0-1.1.1, then usable from 1.2.0+
    # Bonemerang also banned in Gen IX
    if generation_check >= 8:
        banned_moves_gen8 = [
            "egg-bomb", "bone-club", "clamp", "spike-cannon", "constrict", "kinesis",
            "barrage", "dizzy-punch", "bubble", "flash", "psywave", "sharpen",
            "conversion-2", "feint-attack", "foresight", "pursuit", "hidden-power",
            "smelling-salts", "assist", "dragon-rage", "steamroller", "breakneck-blitz"
        ]
        if move_lower_ban in banned_moves_gen8:
            return 0, {"banned": True}, [f"**{move_name}** cannot be selected in this generation!"]
    
    # Gen VIII+: Jump Kick, Rolling Kick, Twineedle, Sonic Boom, Meditate, Rage cannot be selected
    if generation_check >= 8:
        if move_lower_ban in ["jump-kick", "rolling-kick", "twineedle", "sonic-boom", "meditate", "rage"]:
            return 0, {"banned": True}, [f"**{move_name}** cannot be selected in this generation!"]
    
    # Gen IX: Skull Bash, Spore, Lovely Kiss, Bonemerang, Hyper Fang, Vital Throw, Aeroblast (initial), Mind Reader, Hail, and Magic Coat cannot be selected
    if generation_check >= 9:
        if move_lower_ban in ["skull-bash", "spore", "lovely-kiss", "bonemerang", "hyper-fang", "vital-throw", "hail", "mind-reader", "magic-coat", "dual-chop", "gear-grind", "head-charge", "searing-shot", "leaf-tornado", "kings-shield"]:
            return 0, {"banned": True}, [f"**{move_name}** cannot be selected in this generation!"]
    
    # All generation-specific stats (power, accuracy, PP, type, category, contact, priority) 
    # are now retrieved from the database via load_move() with generation parameter above.
    # No hardcoded overrides needed - database has all the correct values per generation.

    # Assault Vest: block status moves
    if mv and mv.get("category") == "status" and item_is_active(user) and user.item:
        u_item = normalize_item_name(user.item)
        u_data = get_item_effect(u_item)
        if u_data.get("blocks_status_moves"):
            return f"**{user.species}** tried to use **{move_name}**, but the Assault Vest prevents status moves!"
    log: List[str] = []
    
    # === INVULNERABILITY CHECK (Fly, Dig, Dive, Bounce, Phantom Force, Shadow Force) ===
    if hasattr(target, 'invulnerable') and target.invulnerable:
        # No Guard: Bypasses invulnerability (both user and target)
        user_ability = normalize_ability_name(user.ability or "")
        target_ability = normalize_ability_name(target.ability or "")
        user_ability_data = get_ability_effect(user_ability)
        if ignores_target_ability:
            target_ability = ""
            target_ability_data = {}
        else:
            target_ability_data = get_ability_effect(target_ability)
        
        no_guard_active = user_ability_data.get("perfect_accuracy") or target_ability_data.get("perfect_accuracy")
        
        if not no_guard_active:
            # Some moves can hit invulnerable targets
            move_lower = move_name.lower().replace(" ", "-")
            can_hit_invuln = {
                "thunder": ["flying"],  # Thunder hits during Fly/Bounce
                "twister": ["flying"],  # Twister hits during Fly/Bounce
                "gust": ["flying"],     # Gust hits during Fly/Bounce
                "sky-uppercut": ["flying"],  # Sky Uppercut hits during Fly/Bounce
                "smack-down": ["flying"],  # Smack Down hits during Fly/Bounce
                "hurricane": ["flying"],  # Hurricane hits during Fly/Bounce
                "earthquake": ["underground"],  # Earthquake hits during Dig
                "magnitude": ["underground"],  # Magnitude hits during Dig
                "fissure": ["underground"],  # Fissure hits during Dig
                "surf": ["underwater"],  # Surf hits during Dive
                "whirlpool": ["underwater"],  # Whirlpool hits during Dive
                "swift": ["flying", "underground", "underwater"] if generation_check == 1 else []  # Gen I: Can hit semi-invulnerable, Gen II+: Cannot
            }
            
            invuln_type = getattr(target, 'invulnerable_type', None)
            can_hit_types = can_hit_invuln.get(move_lower, [])
            
            if invuln_type not in can_hit_types:
                # Move misses invulnerable target
                invuln_msgs = {
                    "flying": f"{target.species} is flying too high!",
                    "underground": f"{target.species} is underground!",
                    "underwater": f"{target.species} is underwater!",
                    "vanished": f"{target.species} can't be hit!",
                    "charging": f"{target.species} is preparing!"
                }
                miss_msg = invuln_msgs.get(invuln_type, "But it failed!")
                log.append(miss_msg)
                if generation_check >= 5 and getattr(user, 'rampage_move', None):
                    disrupt_rampage(user, field_effects, reason="invulnerable")
                return 0, {"miss": True, "invulnerable": True}, log

    # Fallback if move not found in database
    if not mv:
        mv = {
            "type": "Normal",
            "category": "physical",
            "power": 40,
            "accuracy": 100,
            "priority": 0,
            "contact": True
        }

    # Normalize move name early (used throughout function)
    normalized_move = move_name.lower().replace(" ", "-").strip()
    target_ability = normalize_ability_name(target.ability or "")
    target_ability_data = get_ability_effect(target_ability)

    if mv is not None and normalized_move == "tera-blast":
        mv["_stellar_tera_blast"] = False
        if getattr(user, "terastallized", False) and getattr(user, "tera_type", None):
            tera_type = _format_type_name(user.tera_type) or mv.get("type", "Normal")
            mv["type"] = tera_type
            atk_stat = get_effective_stat(user, "atk")
            spa_stat = get_effective_stat(user, "spa")
            if atk_stat > spa_stat:
                mv["category"] = "physical"
            else:
                mv["category"] = "special"
            if getattr(user, "_tera_is_stellar", False):
                mv["_stellar_tera_blast"] = True
                mv["power"] = max(mv.get("power", 80), 100)
        else:
            mv["category"] = mv.get("category") or "special"
    elif mv is not None:
        mv["_stellar_tera_blast"] = False

    is_rollout_move = normalized_move in ROLLOUT_MOVES
    rollout_state_active = False
    rollout_stage_current = 1
    if is_rollout_move:
        existing_rollout_move = getattr(user, 'rollout_move', None)
        if existing_rollout_move == normalized_move and getattr(user, 'rollout_turns_remaining', 0) > 0:
            rollout_state_active = True
            rollout_stage_current = max(1, min(getattr(user, '_rollout_stage', 1), 5))
        else:
            rollout_stage_current = 1

    if normalized_move == "giga-drain":
        if generation_check == 2 and hasattr(target, 'substitute') and target.substitute:
            log.append(f"**{user.species}** used **{move_name}**!")
            log.append("But it failed!")
            user._last_move_failed = True
            move_type = mv.get("type", "Grass") if mv else "Grass"
            return 0, {"miss": True, "type": move_type}, log
        # === Z-MOVES: Ignore Heal Block ===
        is_z_move_giga = hasattr(user, '_is_z_move') and user._is_z_move
        if generation_check >= 6 and hasattr(user, 'heal_blocked') and getattr(user, 'heal_blocked', 0) > 0 and not is_z_move_giga:
            log.append(f"**{user.species}** used **{move_name}**!")
            log.append(f"But it failed due to Heal Block!")
            user._last_move_failed = True
            move_type = mv.get("type", "Grass") if mv else "Grass"
            move_category = mv.get("category", "special") if mv else "special"
            return 0, {"failed": True, "type": move_type, "category": move_category}, log
    if target_ability_data.get("ball_bomb_immunity"):
        is_ball_bomb_move = (
            "ball" in normalized_move or
            "bomb" in normalized_move or
            "bullet" in normalized_move or
            normalized_move in {
                "aura-sphere", "focus-blast", "barrage", "egg-bomb",
                "shadow-ball", "sludge-bomb", "seed-bomb", "weather-ball",
                "energy-ball", "gyro-ball", "ice-ball", "mist-ball",
                "magnet-bomb", "mud-bomb", "octazooka", "rock-wrecker", "zap-cannon",
                "flame-burst"
            }
        )
        if is_ball_bomb_move:
            ability_display = (target.ability or target_ability).replace("-", " ").title()
            if generation_check >= 5 and getattr(user, 'rampage_move', None):
                disrupt_rampage(user, field_effects, reason="ball-bomb-immunity")
            return 0, {"immune": True, "type": mv.get("type", "Normal")}, [f"{target.species}'s {ability_display} blocked the attack!"]

    special_weather = getattr(field_effects, 'special_weather', None) if field_effects else None

    # Load move mechanics from database
    mechanics = get_move_mechanics(move_name, battle_state_ctx)

    # Special weather interactions (Primordial Sea / Desolate Land)
    move_type = (mv.get("type") or "Normal") if mv else "Normal"
    move_category = (mv.get("category") or "").lower() if mv else ""
    if special_weather in {"heavy-rain", "harsh-sunlight"} and move_category != "status":
        # Check if any active Pokemon negates weather effects (Air Lock / Cloud Nine)
        weather_negated = is_weather_negated([m for m in [user, target] if m])
        if not weather_negated:
            if special_weather == "heavy-rain" and move_type.lower() == "fire":
                log.append("The Fire-type attack fizzled out in the heavy rain!")
                user._last_move_failed = True
                if generation_check >= 5:
                    disrupt_rampage(user, field_effects, reason="weather")
                return 0, {"failed": True, "type": move_type}, log
            if special_weather == "harsh-sunlight" and move_type.lower() == "water":
                log.append("The Water-type attack evaporated in the extremely harsh sunlight!")
                user._last_move_failed = True
                if generation_check >= 5:
                    disrupt_rampage(user, field_effects, reason="weather")
                return 0, {"failed": True, "type": move_type}, log
    
    # === OHKO MOVES ===
    # Dynamax Pokemon are immune to OHKO moves
    if mechanics and mechanics['is_ohko_move']:
        if target.dynamaxed:
            log.append(f"{target.species}'s Dynamax prevented an OHKO!")
            return 0, {"immune": True, "type": mv.get("type", "Normal")}, log
        
        # Sturdy: Gen 3-4 (blocks OHKO moves), Gen 5+ (doesn't block OHKO, but survives at 1 HP)
        if target_ability == "sturdy":
            generation = get_generation(field_effects=field_effects)
            if generation <= 4:
                # Gen 3-4: Sturdy grants OHKO immunity
                log.append(f"{target.species}'s Sturdy prevents OHKO!")
                return 0, {"immune": True, "type": mv.get("type", "Normal")}, log
        
        success, message = calculate_ohko_damage(user.level, target.level, move_name, field_effects=field_effects, attacker=user, defender=target)
        if success:
            log.append(message)
            # Gen I Horn Drill: Fixed 65535 damage (effectively instant KO)
            if generation_check == 1 and move_lower == "horn-drill":
                return 65535, {"ohko": True, "type": mv.get("type", "Normal"), "crit": False, "fixed_damage": True}, log
            # Gen II Horn Drill: Damage equal to target's current HP
            elif generation_check == 2 and move_lower == "horn-drill":
                return target.hp, {"ohko": True, "type": mv.get("type", "Normal"), "crit": False}, log
            # Other OHKO moves: Return damage equal to target's current HP (instant KO)
            else:
                return target.hp, {"ohko": True, "type": mv.get("type", "Normal"), "crit": False}, log
        else:
            log.append(message)
            return 0, {"miss": True, **mv}, log
    
    # === FLAME WHEEL: Thaw user if frozen ===
    if normalized_move == "flame-wheel":
        if user.status and user.status.lower() in ["frz", "freeze"]:
            user.status = None
            log.append(f"{user.species} thawed out!")
    
    # === FIXED DAMAGE MOVES ===
    if mechanics and mechanics['is_fixed_damage'] and not mechanics['is_variable_power']:
        # Set generation context for Psywave generation-specific calculation
        if move_name.lower().replace(" ", "-") == "psywave":
            user._generation_context = generation_check
        fixed_dmg = calculate_fixed_damage(move_name, user.level, user.hp, target.hp, user=user)
        if fixed_dmg is not None:
            # Gen 1 special-case: Night Shade ignores type immunities
            move_norm = move_name.lower().replace(" ", "-")
            gen = get_generation(field_effects=field_effects)
            if move_norm == "night-shade" and gen == 1:
                return fixed_dmg, {"fixed": True, "type": mv.get("type", "Normal")}, log
            # Fixed damage ignores type effectiveness, but not immunities (unless Ring Target)
            # Gen I: Sonic Boom and Seismic Toss not affected by type immunities
            mult, _ = type_multiplier(mv.get("type", "Normal"), target, user=user, field_effects=field_effects)
            # Ring Target removes type immunities
            has_ring_target = False
            if item_is_active(target) and target.item:
                rt_item = normalize_item_name(target.item)
                rt_data = get_item_effect(rt_item)
                gen_rt2 = get_generation(field_effects=field_effects)
                if rt_data.get("removes_type_immunities") and gen_rt2 >= 5:
                    has_ring_target = True
            
            # Gen I: Sonic Boom and Seismic Toss bypass type immunities
            if move_norm == "sonic-boom" and generation_check == 1:
                # Gen I Sonic Boom can hit Ghost-types
                pass  # Skip immunity check
            elif move_norm == "seismic-toss" and generation_check == 1:
                # Gen I Seismic Toss can hit Ghost-types
                pass  # Skip immunity check
            elif mult == 0 and not has_ring_target:
                if generation_check >= 5 and getattr(user, 'rampage_move', None):
                    disrupt_rampage(user, field_effects, reason="fixed-immunity")
                return 0, {"immune": True, "type": mv.get("type", "Normal")}, log
            return fixed_dmg, {"fixed": True, "type": mv.get("type", "Normal")}, log

    # Handle Hidden Power - set type based on user's IVs
    # normalized_move already defined above
    if normalized_move.startswith("hidden-power"):
        hp_type = calculate_hidden_power_type(user.ivs, generation=generation_check)
        hp_power = calculate_hidden_power_power(user.ivs, generation=generation_check)
        mv = mv.copy()  # Don't mutate the cached move
        mv["type"] = hp_type
        mv["power"] = hp_power

        if generation_check >= 4:
            mv["category"] = "special"
        else:
            physical_types = {"Normal", "Fighting", "Flying", "Ground", "Rock", "Bug", "Ghost", "Poison", "Steel"}
            mv["category"] = "physical" if hp_type in physical_types else "special"

        if hp_type == "Fire" and generation_check >= 4 and getattr(user, 'status', None) in {"frz", "freeze"}:
            user.status = None
            user.status_turns = 0
            log.append(f"{user.species} thawed out!")

        # Hidden Power type is kept secret to opponents for fairness
        # (Players can see their own HP type in their move buttons)
    
    # Handle Natural Gift - set power and type based on consumed Berry
    if normalized_move == "natural-gift":
        if hasattr(user, '_natural_gift_power') and hasattr(user, '_natural_gift_type'):
            mv = mv.copy()
            mv["power"] = user._natural_gift_power
            mv["type"] = user._natural_gift_type
            if hasattr(user, '_natural_gift_msg'):
                log.append(user._natural_gift_msg)
                # Clean up temporary attributes
                delattr(user, '_natural_gift_msg')
            delattr(user, '_natural_gift_power')
            delattr(user, '_natural_gift_type')
    
    if normalized_move == "ancient-power":
        if generation_check == 3:
            if not mv.get("contact", False):
                mv = mv.copy()
            mv["contact"] = True
        else:
            if mv.get("contact", False):
                mv = mv.copy()
                mv["contact"] = False

    if normalized_move == "fake-out":
        if generation_check <= 3:
            if mv.get("contact", False):
                mv = mv.copy()
                mv["contact"] = False
        else:
            if not mv.get("contact", False):
                mv = mv.copy()
                mv["contact"] = True
    
    # === STRUGGLE: Generation-specific type and accuracy ===
    if normalized_move == "struggle":
        gen_struggle = get_generation(field_effects=field_effects)
        
        # Type: Gen I = Normal-type, Gen II+ = Typeless
        if gen_struggle == 1:
            mv = mv.copy()
            mv["type"] = "Normal"
        else:
            mv = mv.copy()
            mv["type"] = "Typeless"  # Typeless (ignores type effectiveness)
        
        # Accuracy: Gen IV+ bypasses accuracy checks
        if gen_struggle >= 4:
            mv = mv.copy()
            mv["accuracy"] = None  # None = bypasses accuracy checks (always hits unless semi-invulnerable)
    
    # === TYPE-CHANGING MOVES ===
    
    weather = getattr(field_effects, 'weather', None) if field_effects else None
    terrain = getattr(field_effects, 'terrain', None) if field_effects else None
    
    # Weather Ball: Type changes based on weather
    if normalized_move == "weather-ball":
        new_type = get_weather_ball_type(weather)
        if new_type != "Normal":
            mv = mv.copy()
            mv["type"] = new_type
            log.append(f"Weather Ball became {new_type}-type!")
    
    # Terrain Pulse: Type changes based on terrain
    elif normalized_move == "terrain-pulse":
        new_type = get_terrain_pulse_type(terrain)
        if new_type != "Normal":
            mv = mv.copy()
            mv["type"] = new_type
            log.append(f"Terrain Pulse became {new_type}-type!")
    
    # Revelation Dance: Type matches user's primary type
    elif normalized_move == "revelation-dance":
        new_type = get_revelation_dance_type(user.types)
        mv = mv.copy()
        mv["type"] = new_type
        log.append(f"Revelation Dance became {new_type}-type!")
    
    # Judgment: Type based on Plate held
    elif normalized_move == "judgment":
        new_type = get_judgment_type(user.item)
        if new_type != "Normal":
            mv = mv.copy()
            mv["type"] = new_type
            log.append(f"Judgment became {new_type}-type from {user.item}!")
    
    # Multi-Attack: Type based on Memory held
    elif normalized_move == "multi-attack":
        new_type = get_multi_attack_type(user.item)
        if new_type != "Normal":
            mv = mv.copy()
            mv["type"] = new_type
            log.append(f"Multi-Attack became {new_type}-type from {user.item}!")
    
    # Bite: Normal-type Gen I, Dark-type Gen II+
    elif normalized_move == "bite":
        if generation_check == 1:
            # Gen I: Normal-type
            if mv.get("type", "Dark") != "Normal":
                mv = mv.copy()
                mv["type"] = "Normal"
        elif generation_check <= 3:
            # Gen II-III: Dark-type, special category
            if mv.get("type", "Normal") != "Dark":
                mv = mv.copy()
                mv["type"] = "Dark"
                mv["category"] = "special"
        else:
            # Gen IV+: Dark-type, physical category
            if mv.get("type", "Normal") != "Dark":
                mv = mv.copy()
                mv["type"] = "Dark"
                mv["category"] = "physical"
    
    # Sweet Kiss: Normal-type Gen II-V, Fairy-type Gen VI+
    elif normalized_move == "sweet-kiss":
        if generation_check >= 6:
            if mv.get("type", "Normal") != "Fairy":
                mv = mv.copy()
                mv["type"] = "Fairy"
        else:
            if mv.get("type", "Fairy") != "Normal":
                mv = mv.copy()
                mv["type"] = "Normal"
    
    # Moonlight: Fairy-type Gen VI+
    elif normalized_move == "moonlight":
        if generation_check >= 6:
            if mv and mv.get("type", "Normal") != "Fairy":
                mv = mv.copy()
                mv["type"] = "Fairy"

    # Charm and Feint Attack type/contact changes are now handled by the database
    # via move_generation_stats table - no manual overrides needed
    
    # Techno Blast: Type based on Drive held
    elif normalized_move == "techno-blast":
        new_type = get_techno_blast_type(user.item)
        if new_type != "Normal":
            mv = mv.copy()
            mv["type"] = new_type
            log.append(f"Techno Blast became {new_type}-type from {user.item}!")

    # Get ability data early (needed for type conversion)
    user_ability = normalize_ability_name(user.ability or "")
    user_ability_data = get_ability_effect(user_ability)
    
    # Apply type-converting abilities
    original_type = mv.get("type", "Normal")
    was_converted_by_ability = False  # Track if ability converted the type (for power boost later)
    
    # === NULLSCAPE (Untyped): Prevents type-converting abilities ===
    nullscape_type = _get_nullscape_type(user, getattr(user, '_battle_state', None))
    nullscape_blocks_conversion = (nullscape_type == "Untyped")
    
    # === NULLSCAPE (Untyped): All moves become Untyped (applied FIRST, before ability conversions) ===
    if nullscape_type == "Untyped":
        mv = mv.copy()  # Don't mutate cached move
        mv["type"] = "Untyped"
        was_converted_by_ability = False  # Reset since Nullscape overrides ability conversions
        # Skip all ability-based conversions below
    
    # === ELECTRIFY: Applied BEFORE ability conversions ===
    # If user has been electrified by opponent's Electrify, their move becomes Electric-type
    # Electrify takes priority and prevents ability-based conversions AND power boosts
    elif hasattr(user, 'electrified') and user.electrified:
        mv = mv.copy()  # Don't mutate cached move
        mv["type"] = "Electric"
        user.electrified = False  # Clear after use
        log.append(f"{user.species}'s move became Electric-type due to Electrify!")
        # Skip ability-based conversions (Aerilate, etc.) if Electrified
    # Normalize: All moves become Normal (blocked by Nullscape Untyped)
    elif not nullscape_blocks_conversion and user_ability_data.get("converts_all_to"):
        new_type = user_ability_data["converts_all_to"]
        if original_type != new_type:
            mv = mv.copy()  # Don't mutate cached move
            mv["type"] = new_type
            was_converted_by_ability = True
            log.append(f"{user.species}'s Normalize turned {move_name} into a Normal-type move!")
    # Pixilate, Aerilate, Refrigerate, Galvanize: Normal → specific type (blocked by Nullscape Untyped)
    elif not nullscape_blocks_conversion and original_type == "Normal" and user_ability_data.get("converts_normal_to"):
        new_type = user_ability_data["converts_normal_to"]
        mv = mv.copy()  # Don't mutate cached move
        mv["type"] = new_type
        was_converted_by_ability = True
        log.append(f"{user.species}'s {user.ability.replace('-', ' ').title()} turned {move_name} into a {new_type}-type move!")
    # Liquid Voice: Sound → Water (blocked by Nullscape Untyped)
    elif not nullscape_blocks_conversion and user_ability_data.get("sound_moves_become_water"):
        # Check if this is a sound move
        mechanics = get_move_mechanics(move_name, battle_state_ctx)
        if mechanics and mechanics.get('is_sound_move'):
            mv = mv.copy()  # Don't mutate cached move
            mv["type"] = "Water"
            was_converted_by_ability = True
            log.append(f"{user.species}'s Liquid Voice turned {move_name} into a Water-type move!")
    elif nullscape_blocks_conversion:
        # Nullscape blocks ability conversions (already handled above)
        pass
    
    # Apply weather/terrain modifications to move data
    if field_effects:
        # Utility Umbrella: holder unaffected by rain/sun effects
        weather_arg = getattr(field_effects, 'weather', None)
        if item_is_active(user) and user.item:
            u_item = normalize_item_name(user.item)
            u_data = get_item_effect(u_item)
            if u_data.get("negates_rain_sun") and weather_arg in ("rain", "sun"):
                weather_arg = None
        mv = apply_weather_move_effects(move_name, weather_arg, mv, special_weather=special_weather)

    # Apply Defense Curl bonus to Rollout/Ice Ball (double power while active)
    # normalized_move already defined above
    if normalized_move in ["rollout", "ice-ball"] and getattr(user, "_defense_curl_used", False):
        if mv.get("power") and mv.get("power") > 0:
            mv = mv.copy()
            mv["power"] = int(mv["power"] * 2)

    if is_rollout_move and mv and mv.get("power"):
        stage_multiplier = 2 ** (max(1, rollout_stage_current) - 1)
        if stage_multiplier > 1:
            mv = mv.copy()
            mv["power"] = int((mv.get("power") or 0) * stage_multiplier)

    # Pain Split, Rock Tomb, Meteor Mash, Last Resort, and all other generation-specific stats
    # are now handled by the database via move_generation_stats table - no manual overrides needed
    
    # Sucker Punch: Generation-specific power
    if normalized_move == "sucker-punch" and mv:
        gen_sp = get_generation(field_effects=field_effects)
        mv = mv.copy()
        if gen_sp in (4, 5, 6):
            mv["power"] = 80
        elif gen_sp >= 7:
            mv["power"] = 70
    
    # Aura Sphere: Generation-specific power
    if normalized_move == "aura-sphere" and mv:
        gen_as = get_generation(field_effects=field_effects)
        mv = mv.copy()
        if gen_as in (4, 5):
            mv["power"] = 90
        elif gen_as >= 6:
            mv["power"] = 80
    
    # Overheat: Gen III makes contact
    if normalized_move == "overheat" and generation_check == 3:
        if mv:
            mv = mv.copy()
            mv["contact"] = True
    
    # Needle Arm: Gen III Minimize double damage
    if normalized_move == "needle-arm" and generation_check == 3:
        if hasattr(target, '_minimized') and target._minimized:
            if mv:
                mv = mv.copy()
                mv["power"] = int((mv.get("power") or 0) * 2)
    
    # Bullet Seed: Generation-specific power and category
    if normalized_move == "bullet-seed" and mv:
        gen_bs = get_generation(field_effects=field_effects)
        mv = mv.copy()
        if gen_bs == 3:
            mv["power"] = 10
            mv["category"] = "special"
        elif gen_bs == 4:
            mv["power"] = 10
            mv["category"] = "physical"
        elif gen_bs >= 5:
            mv["power"] = 25
            mv["category"] = "physical"
    
    # Icicle Spear: Generation-specific power and category
    if normalized_move == "icicle-spear" and mv:
        gen_is = get_generation(field_effects=field_effects)
        mv = mv.copy()
        if gen_is == 3:
            mv["power"] = 10
            mv["category"] = "special"
        elif gen_is == 4:
            mv["power"] = 10
            mv["category"] = "physical"
        elif gen_is >= 5:
            mv["power"] = 25
            mv["category"] = "physical"
    
    # Rock Blast: Generation-specific accuracy
    if normalized_move == "rock-blast" and mv:
        gen_rb = get_generation(field_effects=field_effects)
        mv = mv.copy()
        if gen_rb in (3, 4):
            mv["accuracy"] = 80
        elif gen_rb >= 5:
            mv["accuracy"] = 90
    
    # Volt Tackle: Generation-specific category and paralysis
    if normalized_move == "volt-tackle" and mv:
        gen_vt = get_generation(field_effects=field_effects)
        mv = mv.copy()
        if gen_vt == 3:
            mv["category"] = "special"
        elif gen_vt >= 4:
            mv["category"] = "physical"
    
    # Leaf Blade: Generation-specific power
    if normalized_move == "leaf-blade" and mv:
        gen_lb = get_generation(field_effects=field_effects)
        mv = mv.copy()
        if gen_lb == 3:
            mv["power"] = 70
        elif gen_lb >= 4:
            mv["power"] = 90
    
    # Generation-specific bans
    if normalized_move in ["water-sport"] and generation_check >= 8:
        log.append(f"{move_name} cannot be used in Generation {generation_check}!")
        if generation_check >= 5 and getattr(user, 'rampage_move', None):
            disrupt_rampage(user, field_effects, reason="banned")
        handle_rollout_failure(user, is_rollout_move)
        return 0, {"banned": True, "type": mv.get("type", "Normal")}, log
    
    # Psycho Boost: Generation-specific bans
    if normalized_move == "psycho-boost" and generation_check in (8, 9):
        if generation_check == 9:
            # Gen IX: Check version (unbanned from v3.0.0, but we'll treat as banned for now)
            log.append(f"{move_name} cannot be used in Generation 9!")
        else:
            log.append(f"{move_name} cannot be used in Generation {generation_check}!")
        if generation_check >= 5 and getattr(user, 'rampage_move', None):
            disrupt_rampage(user, field_effects, reason="banned")
        handle_rollout_failure(user, is_rollout_move)
        return 0, {"banned": True, "type": mv.get("type", "Normal")}, log
    
    # Miracle Eye: Gen VIII+ banned
    if normalized_move == "miracle-eye" and generation_check >= 8:
        log.append(f"{move_name} cannot be used in Generation {generation_check}!")
        if generation_check >= 5 and getattr(user, 'rampage_move', None):
            disrupt_rampage(user, field_effects, reason="banned")
        handle_rollout_failure(user, is_rollout_move)
        return 0, {"banned": True, "type": mv.get("type", "Normal")}, log

    # Accuracy / status moves
    power = mv.get("power")
    variable_power_flag = bool(secondary_effect_data.get("variable_power"))
    if not variable_power_flag and (mv.get("category") == "status" or (power is not None and power <= 0) or power is None):
        # Good as Gold - Immune to status moves
        target_ability = normalize_ability_name(target.ability or "")
        if target_ability == "good-as-gold":
            log.append(f"{target.species}'s Good as Gold protected it from the status move!")
            if generation_check >= 5 and getattr(user, 'rampage_move', None):
                disrupt_rampage(user, field_effects, reason="good-as-gold")
            return 0, {"immune": True, "type": mv.get("type", "Normal")}, log
        return 0, {"status": True, "type": mv.get("type", "Normal"), "category": mv.get("category", "status"), "priority": mv.get("priority", 0), "contact": mv.get("contact", False)}, log
    
    # === INVULNERABILITY CHECK ===
    # Check if target is invulnerable and if this move can hit them
    if hasattr(target, 'invulnerable') and target.invulnerable:
        target_invuln_type = getattr(target, 'invulnerable_type', None)
        if not can_hit_invulnerable(normalized_move, target_invuln_type):
            log.append(f"{target.species} avoided the attack!")
            if generation_check >= 5 and getattr(user, 'rampage_move', None):
                disrupt_rampage(user, field_effects, reason="invulnerable")
            handle_rollout_failure(user, is_rollout_move)
            return 0, {"miss": True, **mv}, log
    
    accuracy = mv.get("accuracy")
    # Struggle Gen IV+: Bypasses accuracy checks (accuracy = None)
    if accuracy is None:
        # Bypass accuracy check (always hits unless semi-invulnerable, which is checked above)
        pass  # Continue to damage calculation
    elif not _accuracy_check(
        accuracy if accuracy is not None else 100,
        user,
        target,
        field_effects,
        mv.get("category", "physical"),
        move_name,
        ignores_target_ability=ignores_target_ability,
    ):
        # === BLUNDER POLICY: +2 Speed when move misses due to accuracy (Gen 8+) ===
        if item_is_active(user) and user.item:
            u_item_bp = normalize_item_name(user.item)
            u_item_data_bp = get_item_effect(u_item_bp)
            gen_bp = get_generation(field_effects=field_effects)
            if u_item_data_bp.get("boost_on_miss") and gen_bp >= 8:
                excludes = u_item_data_bp.get("excludes", [])
                should_boost = True
                
                # Check exclusions: OHKO moves, Triple Kick early miss, semi-invulnerable miss
                normalized_move_bp = move_name.lower().replace(" ", "-")
                ohko_moves = ["fissure", "guillotine", "horn-drill", "sheer-cold"]
                if "ohko_moves" in excludes and normalized_move_bp in ohko_moves:
                    should_boost = False
                
                if "semi_invulnerable_miss" in excludes:
                    if hasattr(target, 'invulnerable') and target.invulnerable:
                        should_boost = False
                
                if should_boost:
                    boosts = u_item_data_bp.get("boost_on_miss", {})
                    for stat, amount in boosts.items():
                        old_stage = user.stages.get(stat, 0)
                        user.stages[stat] = min(6, old_stage + amount)
                    user.item = None  # Consume Blunder Policy
                    log.append("The attack missed!")
                    log.append(f"{user.species}'s Blunder Policy raised its Speed!")
                    if generation_check >= 5 and getattr(user, 'rampage_move', None):
                        disrupt_rampage(user, field_effects, reason="accuracy-miss")
                    handle_rollout_failure(user, is_rollout_move)
                    return 0, {"miss": True, **mv}, log
        
        log.append("The attack missed!")
        handle_rollout_failure(user, is_rollout_move)
        return 0, {"miss": True, **mv}, log

    # Beak Blast and Shell Trap reactive effects (apply before damage calculation)
    # Use makes_contact for accurate detection (has fallback list)
    is_contact_now = makes_contact(move_name, battle_state=battle_state_ctx, generation=generation_for_stats)
    # Update mv if contact flag is missing
    if is_contact_now and not mv.get("contact"):
        mv = mv.copy() if mv else {}
        mv["contact"] = 1
    if is_contact_now and getattr(target, '_beak_blast_charging', False):
        burn_msg = check_beak_blast_burn(target, user, True)
        if burn_msg:
            log.append(burn_msg)
    if getattr(target, '_shell_trap_set', False):
        shell_msg = check_shell_trap_trigger(target, user, (mv.get("category") or "").lower())
        if shell_msg:
            log.append(shell_msg)

    # === DISGUISE (Mimikyu) ===
    # Blocks the first damaging hit completely
    target_ability = normalize_ability_name(target.ability or "")
    if ignores_target_ability:
        target_ability = ""
    if target_ability == "disguise" and not target._disguise_broken and "mimikyu" in target.species.lower():
        target._disguise_broken = True
        target.form = "busted"
        # Take 1/8 HP recoil from disguise breaking
        recoil_dmg = max(1, target.max_hp // 8)
        target.hp = max(0, target.hp - recoil_dmg)
        log.append(f"{target.species}'s disguise was busted!")
        handle_rollout_success(
            user,
            normalized_move,
            is_rollout_move,
            rollout_state_active,
            rollout_stage_current,
        )
        return 0, {"disguise_blocked": True, "type": mv.get("type", "Normal")}, log
    
    # === ICE FACE (Eiscue) ===
    # Blocks the first physical hit
    if target_ability == "ice-face" and target.form == "ice" and mv.get("category") == "physical" and "eiscue" in target.species.lower():
        target.form = "noice"
        log.append(f"{target.species}'s Ice Face was broken!")
        handle_rollout_success(
            user,
            normalized_move,
            is_rollout_move,
            rollout_state_active,
            rollout_stage_current,
        )
        return 0, {"ice_face_blocked": True, "type": mv.get("type", "Normal")}, log

    # Get generation for crit damage calculation
    generation = get_generation(field_effects=field_effects)

    # === FLAIL/REVERSAL GEN II: No crit, no random variation ===
    if normalized_move in ["flail", "reversal"] and generation == 2:
        # Gen II Flail/Reversal: No crit, no random variation
        crit = 1.0
        is_crit = False
        user._flail_gen2_no_random = True  # Flag to skip random variation
    # Crit with proper stages
    # Check for always-crit moves first
    else:
        if is_always_crit_move(normalized_move):
            # Gen 1-5: 2x, Gen 6+: 1.5x
            crit = 2.0 if generation <= 5 else 1.5
            is_crit = True
            log.append(f"A critical hit!")
        else:
                if getattr(user, 'laser_focus_turns', 0) > 0 and getattr(user, '_laser_focus_pending', False):
                    crit = 2.0 if generation <= 5 else 1.5
                    is_crit = True
                    log.append(f"{user.species}'s Laser Focus ensured a critical hit!")
                    user._laser_focus_pending = False
                    user.laser_focus_turns = 0
                else:
                    crit, is_crit = _crit_multiplier(
                        move_name,
                        user.ability,
                        user.item,
                        user.species,
                        user.focused_energy_stage,
                        generation
                    )
    
    # Battle Armor / Shell Armor: Prevent critical hits
    if is_crit:
        target_ability = normalize_ability_name(target.ability or "")
        if ignores_target_ability:
            target_ability = ""
            target_ability_data = {}
        else:
            target_ability_data = get_ability_effect(target_ability)
        if target_ability_data.get("crit_immunity"):
            crit, is_crit = 1.0, False
            ability_name = target.ability.replace("-", " ").title() if target.ability else "Unknown"
            log.append(f"{target.species}'s {ability_name} prevented the critical hit!")
    
    # Sniper: 1.5x critical hit damage
    # Gen 4: 3x total (2x → 3x), Gen 5: 3x total (2x → 3x), Gen 6+: 2.25x total (1.5x → 2.25x)
    if is_crit and user_ability == "sniper":
        crit *= 1.5
        log.append(f"{user.species}'s Sniper boosted the critical hit!")

    lvl = user.level
    # Use effective stats (base stats * stage multipliers)
    # Unaware: Ignore opponent's stat stages
    target_ability = normalize_ability_name(target.ability or "")
    if ignores_target_ability:
        target_ability = ""
        target_ability_data = {}
    else:
        target_ability_data = get_ability_effect(target_ability)
    
    # === SPECIAL STAT CALCULATIONS ===
    # normalized_move already defined above
    
    if mv.get("category") == "physical":
        # Body Press: Uses Defense instead of Attack
        if normalized_move == "body-press":
            A = get_effective_stat(user, "defn")  # Use Defense, not Attack
            log.append(f"{user.species} used its Defense stat for the attack!")
            # Slow Start halves effective Attack stat for Body Press (not a stat stage change)
            user_ability_norm = normalize_ability_name(user.ability or "")
            if user_ability_norm == "slow-start" and not getattr(user, "_ability_suppressed", False):
                if hasattr(user, '_slow_start_turns') and user._slow_start_turns > 0:
                    A *= 0.5
        # Foul Play: Uses target's Attack instead of user's
        elif normalized_move == "foul-play":
            A = get_effective_stat(target, "atk")  # Use target's Attack
            # Tablets of Ruin: Foul Play damage is not reduced if the move user is the only one with Tablets of Ruin
            if user_ability == "tablets-of-ruin":
                battle_state_fp = getattr(user, "_battle_state", None)
                if battle_state_fp:
                    all_mons_fp = []
                    if hasattr(battle_state_fp, "p1_party"):
                        all_mons_fp.extend([m for m in battle_state_fp.p1_party if m and m.hp > 0])
                    if hasattr(battle_state_fp, "p2_party"):
                        all_mons_fp.extend([m for m in battle_state_fp.p2_party if m and m.hp > 0])
                    only_user_has_tablets = sum(1 for m in all_mons_fp if normalize_ability_name(m.ability or "") == "tablets-of-ruin") == 1
                    if only_user_has_tablets:
                        A *= 4 / 3  # Undo Tablets of Ruin reduction for Foul Play damage
            log.append(f"{user.species} turned the target's power against it!")
            # Slow Start halves effective Attack stat for Foul Play (not a stat stage change)
            user_ability_norm = normalize_ability_name(user.ability or "")
            if user_ability_norm == "slow-start" and not getattr(user, "_ability_suppressed", False):
                if hasattr(user, '_slow_start_turns') and user._slow_start_turns > 0:
                    A *= 0.5
        else:
            A = get_effective_stat(user, "atk")
        # If attacker has Unaware, ignore defender's defensive stages
        if user_ability_data.get("ignores_stat_changes"):
            D_base = target.stats.get("defn", 1)
            form_mods = apply_form_stat_modifiers(target)
            if "defn" in form_mods:
                D_base *= form_mods["defn"]
            D = D_base  # No stage multiplier
            # Still apply ability/item modifiers
            if not ignores_target_ability and target.ability:
                target_ab_data = get_ability_effect(normalize_ability_name(target.ability))
                if "stat_mult" in target_ab_data and "defn" in target_ab_data["stat_mult"]:
                    D *= target_ab_data["stat_mult"]["defn"]
            if item_is_active(target):
                item_data = get_item_effect(normalize_item_name(target.item))
                if "stat_mult" in item_data and "defn" in item_data["stat_mult"]:
                    if not item_data.get("unevolved_only") or (hasattr(target, 'is_fully_evolved') and not target.is_fully_evolved):
                        D *= item_data["stat_mult"]["defn"]
        else:
            D = get_effective_stat(target, "defn")
        if normalized_move in ["self-destruct", "explosion"] and generation_check <= 4:
            D = max(1, D * 0.5)
        
        # Grass Pelt: 1.5x Defense in Grassy Terrain
        if field_effects and hasattr(field_effects, 'terrain') and field_effects.terrain == "grassy":
            target_ability = normalize_ability_name(target.ability or "")
            target_ability_data = get_ability_effect(target_ability)
            if target_ability_data.get("defense_boost_in_grassy"):
                D *= target_ability_data["defense_boost_in_grassy"]
                log.append(f"{target.species}'s Grass Pelt boosted its Defense!")
    else:
        A = get_effective_stat(user, "spa")
        
        # Slow Start: Special case for Z-Moves with typed Z-Crystal based on special moves
        # If user holds a typed Z-Crystal and uses a Z-Move based on a special move, Slow Start reduces SpA
        user_ability_norm = normalize_ability_name(user.ability or "")
        if user_ability_norm == "slow-start" and not getattr(user, "_ability_suppressed", False):
            if hasattr(user, '_is_z_move') and user._is_z_move:
                # Check if user holds a typed Z-Crystal (not Z-Power Ring or generic)
                if user.item:
                    from .z_moves import normalize_crystal_name, Z_CRYSTAL_TYPES
                    item_norm = normalize_crystal_name(user.item)
                    # Check if it's a typed Z-Crystal (not signature crystals like pikanium-z, eevium-z, etc.)
                    if item_norm in Z_CRYSTAL_TYPES:
                        # Check if the move is special category
                        if mv.get("category") == "special":
                            # Slow Start reduces SpA for this Z-Move only
                            if hasattr(user, '_slow_start_turns') and user._slow_start_turns > 0:
                                A *= 0.5
        
        # Hadron Engine: 1.33x SpA in Electric Terrain (5461/4096 ≈ 1.333)
        if field_effects and hasattr(field_effects, 'terrain') and field_effects.terrain == "electric":
            if user_ability_data.get("stat_mult_terrain"):
                terrain_boost = user_ability_data["stat_mult_terrain"]
                required_terrain = terrain_boost.get("terrain")
                if required_terrain == "electric" and "spa" in terrain_boost:
                    A *= terrain_boost["spa"]
                    log.append(f"{user.species}'s Hadron Engine boosted its Sp. Atk!")
        special_def_stat = "spd"
        if normalized_move in {"psyshock", "psystrike", "secret-sword"}:
            special_def_stat = "defn"
        if user_ability_data.get("ignores_stat_changes"):
            D_base = target.stats.get(special_def_stat, 1)
            form_mods = apply_form_stat_modifiers(target)
            if special_def_stat in form_mods:
                D_base *= form_mods[special_def_stat]
            D = D_base
            if not ignores_target_ability and target.ability:
                target_ab_data = get_ability_effect(normalize_ability_name(target.ability))
                if "stat_mult" in target_ab_data and special_def_stat in target_ab_data["stat_mult"]:
                    D *= target_ab_data["stat_mult"][special_def_stat]
            if item_is_active(target):
                item_data = get_item_effect(normalize_item_name(target.item))
                if "stat_mult" in item_data and special_def_stat in item_data["stat_mult"]:
                    if not item_data.get("unevolved_only") or (hasattr(target, 'is_fully_evolved') and not target.is_fully_evolved):
                        D *= item_data["stat_mult"][special_def_stat]
        else:
            D = get_effective_stat(target, special_def_stat)
    
        # Sandstorm: Gen IV+ Rock-types gain 1.5x Special Defense
        if field_effects:
            current_weather = getattr(field_effects, 'weather', None)
            if current_weather == "sandstorm" and "Rock" in [t for t in target.types if t]:
                generation_spd = get_generation(field_effects=field_effects)
                if generation_spd >= 4:
                    D *= 1.5
                    log.append(f"{target.species}'s Special Defense rose in the sandstorm!")
    
    # Gorilla Tactics: 1.5x Attack (applied here for damage calculation)
    if user_ability_data.get("attack_mult") and mv.get("category") == "physical":
        A *= user_ability_data["attack_mult"]
    
    # Apply status modifiers (burn halves physical attack, unless Guts or Facade)
    if user.status == "burn" and mv.get("category") == "physical":
        # Gen VI+: Facade ignores burn's Attack penalty
        # Gen III-V: Facade still has burn's Attack penalty applied (unless Guts)
        generation_facade = get_generation(field_effects=field_effects)
        
        # Check if this is Facade
        is_facade = normalized_move == "facade"
        
        # Guts negates burn's Attack penalty
        # Facade (Gen VI+) also negates burn's Attack penalty
        if is_facade and generation_facade >= 6:
            pass  # Facade ignores burn penalty in Gen VI+
        elif not user_ability_data.get("burn_attack_penalty_negation"):
            A = A * 0.5
    
    # Gen I critical: ignore all stat modifiers — use unmodified Attack/Defense (or Special)
    # Per formula: "For a critical hit, all modifiers are ignored, and the unmodified Attack or Special stat is used."
    generation_for_crit = get_generation(field_effects=field_effects)
    if generation_for_crit == 1 and is_crit:
        form_user = apply_form_stat_modifiers(user)
        form_target = apply_form_stat_modifiers(target)
        if mv.get("category") == "physical":
            A = user.stats.get("atk", 1) * form_user.get("atk", 1)
            D = target.stats.get("defn", 1) * form_target.get("defn", 1)
        else:
            A = user.stats.get("spa", 1) * form_user.get("spa", 1)
            D = target.stats.get("spd", 1) * form_target.get("spd", 1)
        A = max(1, A)
        D = max(1, D)
    # Gen II critical: defender's stat stages ignored (D unmodified); attacker's A unmodified only if defender's stage >= attacker's
    elif generation_for_crit == 2 and is_crit:
        form_target = apply_form_stat_modifiers(target)
        if mv.get("category") == "physical":
            def_stat = "defn"
            atk_stat = "atk"
        else:
            def_stat = "spd"
            atk_stat = "spa"
        D = target.stats.get(def_stat, 1) * form_target.get(def_stat, 1)
        D = max(1, D)
        target_def_stage = target.stages.get(def_stat, 0)
        user_atk_stage = user.stages.get(atk_stat, 0)
        if target_def_stage >= user_atk_stage:
            form_user = apply_form_stat_modifiers(user)
            A = user.stats.get(atk_stat, 1) * form_user.get(atk_stat, 1)
            A = max(1, A)
    
    # Get power - handle None from database
    P_raw = mv.get("power")
    if P_raw is None:
        # If power is None in database, check if it's a status move
        if mv.get("category") == "status" or mv.get("damage_class") == "status":
            P = 0  # Status moves have 0 power
        else:
            P = 40  # Default for damaging moves with missing power
    else:
        P = int(P_raw)
    
    # === Z-MOVE POWER MODIFICATION ===
    # Check if this is a Z-Move (passed via user context or move metadata)
    if hasattr(user, '_is_z_move') and user._is_z_move:
        original_move = getattr(user, '_original_move_name', move_name)
        original_move_data = load_move(original_move)
        
        # If load_move failed (e.g., due to typo), try to get move data another way
        if not original_move_data or not original_move_data.get("power"):
            original_move_data = get_move(original_move)
        
        if original_move_data:
            z_power = get_z_move_power(original_move_data, original_move, user.species)
            if z_power is not None:
                P = int(z_power)
                log.append(f"Z-Power boosted the move!")
    
    # === MAX MOVE POWER MODIFICATION ===
    # Check if this is a Max Move (from Dynamax)
    if hasattr(user, '_is_max_move') and user._is_max_move:
        # Check for fixed-power G-Max moves first (G-Max Drum Solo, G-Max Fireball, G-Max Hydrosnipe)
        if hasattr(user, '_gmax_fixed_power') and user._gmax_fixed_power:
            P = int(user._gmax_fixed_power)
            log.append(f"G-Max Power boosted the move!")
        else:
            original_move = getattr(user, '_original_move_name_max', move_name)
            original_move_data = load_move(original_move)
            if original_move_data:
                max_power = get_max_move_power(original_move_data)
                if max_power is not None:
                    P = int(max_power)
                log.append(f"Max Power boosted the move!")
    
    # === FLING POWER OVERRIDE ===
    # Fling's power is determined by the held item (calculated in apply_move)
    if move_lower_ban == "fling" and hasattr(user, '_fling_power_override'):
        P = int(user._fling_power_override)
        log.append(f"Fling's power is {P} (based on held item)")
    
    # Generation-specific power overrides
    if move_lower_ban == "outrage":
        if hasattr(user, '_outrage_power_override'):
            override = user._outrage_power_override
            if override is not None:
                P = int(override)
        elif hasattr(user, '_petal_dance_power_override'):
            override = user._petal_dance_power_override
            if override is not None:
                P = int(override)
    
    # Ash-Greninja (Battle Bond): Water Shuriken has 20 base power per hit (instead of 15)
    if move_lower_ban == "water-shuriken":
        species_lower = getattr(user, 'species', '').lower()
        form = getattr(user, 'form', None)
        # Check if user is Ash-Greninja (Battle Bond form)
        if (species_lower == "greninja" and (form == "ash" or form == "battle-bond")) or "battle-bond" in species_lower or (species_lower == "greninja" and "ash" in str(form).lower()):
            P = 20  # Ash-Greninja's Water Shuriken has 20 base power per hit
    
    # Deadlock: Adds BP based on half miss rate
    if user_ability_data.get("adds_bp_based_on_miss_rate"):
        # Calculate miss rate: (100 - accuracy) / 100
        base_accuracy = mv.get("accuracy", 100)
        if base_accuracy is not None and base_accuracy > 0:
            miss_rate = (100 - base_accuracy) / 100.0
            bp_boost = int(miss_rate * 0.5 * 100)  # Half miss rate as BP boost
            if bp_boost > 0:
                P += bp_boost
                log.append(f"{user.species}'s Deadlock added {bp_boost} BP based on miss rate!")
    
    # Earthbound: Boosts Ground-type move power against grounded Pokémon
    # Check if any Pokémon on the field has Earthbound (grounds all Flying types and Levitate)
    has_earthbound_for_boost = False
    if user_ability_data.get("boosts_ground_move_power"):
        has_earthbound_for_boost = True
    else:
        # Check if any Pokémon on the field has Earthbound
        if hasattr(user, '_battle_state') and user._battle_state:
            battle_state_eb_boost = user._battle_state
            all_mons_eb_boost = []
            if hasattr(battle_state_eb_boost, 'p1_party'):
                all_mons_eb_boost.extend([m for m in battle_state_eb_boost.p1_party if m and m.hp > 0])
            if hasattr(battle_state_eb_boost, 'p2_party'):
                all_mons_eb_boost.extend([m for m in battle_state_eb_boost.p2_party if m and m.hp > 0])
            for mon in all_mons_eb_boost:
                if mon and mon.ability:
                    mon_ab_norm_boost = normalize_ability_name(mon.ability)
                    mon_ab_data_boost = get_ability_effect(mon_ab_norm_boost)
                    if mon_ab_data_boost.get("boosts_ground_move_power"):
                        has_earthbound_for_boost = True
                        break
    
    if has_earthbound_for_boost and move_type_for_weather == "Ground":
        # Earthbound grounds all Flying types and Levitate Pokémon
        # So all Pokémon are considered grounded for the power boost (except Air Balloon)
        target_has_air_balloon = False
        if item_is_active(target) and target.item:
            item_data_ab = get_item_effect(normalize_item_name(target.item))
            if item_data_ab.get("levitate_effect"):
                target_has_air_balloon = True
        
        # Earthbound grounds Flying types and Levitate, so they're all considered grounded
        # Only Air Balloon prevents grounding
        if not target_has_air_balloon:
            # Boost Ground move power (1.5x) against all grounded targets
            P = int(P * 1.5)
            log.append(f"{user.species}'s Earthbound boosted the Ground move's power!")
    
    # Calculate variable power for moves like Gyro Ball, Heavy Slam, etc.
    P = calculate_variable_power(move_name, user, target, P, field_effects=field_effects)
    # Ensure P is still an int after variable power calculation
    if P is None:
        P = 40
    P = int(P)
    
    # === WEATHER & TERRAIN POWER MODIFICATIONS ===
    weather = getattr(field_effects, 'weather', None) if field_effects else None
    terrain = getattr(field_effects, 'terrain', None) if field_effects else None
    
    # Load power effect data (used throughout power calculations)
    power_effect_data = get_move_secondary_effect(move_name)
    
    P = calculate_weather_power(normalized_move, P, weather)
    P = calculate_terrain_power(normalized_move, P, terrain)
    
    # Water Sport - weaken Fire moves (Gen 3-7 only)
    if field_effects and hasattr(field_effects, 'water_sport') and field_effects.water_sport:
        generation_ws = get_generation(field_effects=field_effects)
        if generation_ws < 8 and mv.get("type", "Normal") == "Fire":
            if generation_ws <= 4:
                # Gen III-IV: 50% reduction (power is halved)
                P = int(P * 0.5)
                log.append(f"Water Sport weakened {move_name}!")
            elif generation_ws == 5:
                # Gen V: 67% reduction (power is reduced to 33% of original, or 1352/4096)
                # This means the multiplier is approximately 0.33, but we use exact calculation
                P = int((P * 1352) / 4096)
                log.append(f"Water Sport weakened {move_name}!")
            else:
                # Gen VI-VII: 50% reduction (power is halved)
                P = int(P * 0.5)
                log.append(f"Water Sport weakened {move_name}!")
    
    # Mud Sport - weaken Electric moves (Gen 3-7 only)
    if field_effects and hasattr(field_effects, 'mud_sport') and field_effects.mud_sport:
        generation_ms = get_generation(field_effects=field_effects)
        if generation_ms < 8 and mv.get("type", "Normal") == "Electric":
            # Gen III-IV: 50% reduction, Gen V+: 50% reduction
            P = int(P * 0.5)
            log.append(f"Mud Sport weakened {move_name}!")
    
    # Weather Ball - doubled in any weather except strong winds
    if normalized_move == "weather-ball" and weather:
        # Strong winds (special weather) does NOT double Weather Ball
        special_weather = getattr(field_effects, 'special_weather', None) if field_effects else None
        if special_weather != "strong-winds" and weather not in ["none", None, ""]:
            P = int(P * 2)
            log.append(f"{move_name}'s power doubled in {weather}!")
    
    # Terrain Pulse - doubled in any terrain
    if power_effect_data.get("doubled_in_terrain") and terrain:
        P = int(P * 2)
        log.append(f"{move_name}'s power doubled in {terrain} terrain!")
    
    # === INVULNERABILITY INTERACTION ===
    # Gust, Twister: 2x power vs Fly/Bounce
    if hasattr(target, 'invulnerable_type') and target.invulnerable_type:
        invuln_mult = get_invulnerability_power_boost(normalized_move, target.invulnerable_type, generation_check)
        if invuln_mult > 1.0:
            P = int(P * invuln_mult)
            invuln_messages = {
                "flying": "hit the airborne target for double damage!",
                "underwater": "churned up the water for double damage!",
                "underground": "shook the ground for double damage!"
            }
            invuln_msg = invuln_messages.get(target.invulnerable_type, "struck for extra damage!")
            log.append(f"{move_name} {invuln_msg}")
    
    # === MINIMIZE INTERACTION ===
    # Stomp, Body Slam, etc.: 2x power vs minimized
    if hasattr(target, '_minimized') and target._minimized:
        minimize_mult = get_minimize_power_boost(normalized_move, True)
        if minimize_mult > 1.0:
            P = int(P * minimize_mult)
            log.append(f"{move_name} dealt double damage to the tiny target!")
    
    # === SPECIAL MOVE POWER MODIFICATIONS ===
    move_lower = normalized_move = move_name.lower().replace(" ", "-")
    move_effect = get_move_secondary_effect(move_name) or {}
    move_effect_main = get_move_effects(move_name, battle_state_ctx) or {}
    
    user._move_being_used = move_lower

    def _resolve_owner_id(mon: Mon) -> int:
        if not battle_state:
            return id(mon)
        try:
            if mon in battle_state.team_for(battle_state.p1_id):
                return battle_state.p1_id
            if mon in battle_state.team_for(battle_state.p2_id):
                return battle_state.p2_id
        except Exception:
            pass
        return id(mon)
    
    # Acrobatics: 2x power if user has no item
    if move_lower == "acrobatics" or power_effect_data.get("doubled_no_item"):
        if not user.item:
            P = int(P * 2)
            log.append(f"{move_name}'s power doubled without an item!")
    
    # Knock Off: 1.5x power if target has an item that can be removed (item removal handled after damage)
    if move_lower == "knock-off" or power_effect_data.get("boosted_if_item"):
        if item_is_active(target):
            # Check if the item can actually be removed (Mega Stones, Z-Crystals, etc. can't be removed)
            can_remove, _ = can_remove_item_from_target(
                target,
                user,
                field_effects=field_effects,
                allow_if_target_fainted=False,
                cause="knock-off"
            )
            if can_remove:
                P = int(P * 1.5)
                log.append(f"{move_name}'s power increased!")
    
    # Fusion Moves: 2x power if counterpart was used this turn
    if move_lower in ["fusion-flare", "fusion-bolt"]:
        # Get battle_state from somewhere (would need to be passed in)
        # For now, check if attribute exists on user
        battle_state = getattr(user, '_battle_state', None)
        if battle_state:
            is_boosted, boost_msg = check_fusion_boost(move_name, battle_state)
            if is_boosted:
                P = int(P * 2)
                log.append(boost_msg)
    
    # ===== ADDITIONAL POWER MODIFIERS (MISSING MECHANICS) =====
    # power_effect_data already loaded above
    
    # Facade: 2x power if USER has status (poisoned, paralyzed, or burned)
    # Hex: 2x power if target has status (handled separately)
    if power_effect_data.get("doubled_if_status") and normalized_move == "facade":
        if user.status in ["psn", "tox", "par", "brn"]:
            P = int(P * 2)
            log.append(f"{move_name}'s power doubled due to {user.species}'s status condition!")
    
    # Hex: 2x power if target has status (different from Facade)
    if power_effect_data.get("doubled_if_status") and normalized_move == "hex" and target.status:
        P = int(P * 2)
        log.append(f"{move_name}'s power doubled due to the status condition!")
    
    # Barb Barrage: 2x power if target is poisoned
    if power_effect_data.get("doubled_if_poisoned") and target.status in ["psn", "tox"]:
        P = int(P * 2)
        log.append(f"{move_name}'s power doubled from poison!")
    
    # Smelling Salts: 2x power if target is paralyzed
    if power_effect_data.get("doubled_if_paralyzed") and target.status == "par":
        P = int(P * 2)
        log.append(f"{move_name}'s power doubled from paralysis!")
    
    # Wake-Up Slap: 2x power if target is asleep or has Comatose (but not if behind substitute)
    if normalized_move == "wake-up-slap":
        is_sleeping = target.status == "slp"
        has_comatose = normalize_ability_name(target.ability or "") == "comatose"
        has_substitute = getattr(target, 'has_substitute', False) or getattr(target, '_substitute_hp', 0) > 0
        
        # Only double if (sleeping or Comatose) AND not behind substitute
        if (is_sleeping or has_comatose) and not has_substitute:
            P = int(P * 2)
            if is_sleeping:
                log.append(f"{move_name}'s power doubled against the sleeping target!")
            elif has_comatose:
                log.append(f"{move_name}'s power doubled against the Comatose target!")
    
    # Bolt Beak, Fishious Rend: 2x power if user moves first
    if power_effect_data.get("doubled_if_move_first"):
        # Check if target has moved this turn (would need to be tracked in battle state)
        if not hasattr(target, '_moved_this_turn') or not target._moved_this_turn:
            P = int(P * 2)
            log.append(f"{move_name}'s power doubled from moving first!")
    
    # Pursuit: 2x power if target is switching
    if power_effect_data.get("doubled_if_switching"):
        if hasattr(target, '_is_switching') and target._is_switching:
            P = int(P * 2)
            log.append(f"{move_name}'s power doubled against the fleeing Pokémon!")
    
    # Me First: 1.5x power boost to copied move
    if hasattr(user, '_me_first_active') and user._me_first_active:
        power_mult = getattr(user, '_me_first_power_mult', 1.5)
        P = int(P * power_mult)
        log.append(f"Me First boosted {move_name}'s power!")
    
    # Brine: 2x power if target is at or below 50% HP
    if normalized_move == "brine":
        hp_percent = target.hp / target.max_hp if target.max_hp > 0 else 1.0
        if hp_percent <= 0.5:
            P = int(P * 2)
            log.append(f"{move_name}'s power doubled against the weakened target!")
    
    # Assurance: 2x power if target took damage this turn (Gen IV+)
    if normalized_move == "assurance":
        # Gen IV-V: Base power 50, Gen VI+: Base power 60 (handled in move data)
        if hasattr(target, '_took_damage_this_turn') and target._took_damage_this_turn:
            P = int(P * 2)
            log.append(f"{move_name}'s power doubled!")
    
    # Payback: 2x power if user moves after target (Gen IV: also if target switches/uses item)
    if normalized_move == "payback":
        gen_pb = get_generation(field_effects=field_effects)
        should_double = False
        
        # Always doubles if user moves after target
        if hasattr(target, '_moved_this_turn') and target._moved_this_turn:
            should_double = True
            log.append(f"{move_name}'s power doubled from moving second!")
        # Gen IV only: Also doubles if target switches out or uses item
        elif gen_pb == 4:
            if hasattr(target, '_switched_this_turn') and target._switched_this_turn:
                should_double = True
                log.append(f"{move_name}'s power doubled from the switch!")
            elif hasattr(target, '_used_item_this_turn') and target._used_item_this_turn:
                should_double = True
                log.append(f"{move_name}'s power doubled from the item use!")
        
        if should_double:
            P = int(P * 2)
    
    # Temper Flare: 2x power if previous move failed
    if power_effect_data.get("doubled_if_failed_last"):
        if hasattr(user, '_last_move_failed') and user._last_move_failed:
            P = int(P * 2)
            log.append(f"{move_name}'s power doubled from the previous failure!")
    
    # Retaliate: 2x power if ally fainted last turn
    if power_effect_data.get("doubled_if_ally_fainted"):
        if hasattr(user, '_ally_fainted_last_turn') and user._ally_fainted_last_turn:
            P = int(P * 2)
            log.append(f"{move_name}'s power doubled for revenge!")
    
    # Lash Out: 2x power if user's stats were lowered this turn
    if power_effect_data.get("doubled_if_stats_lowered"):
        if hasattr(user, '_stats_lowered_this_turn') and user._stats_lowered_this_turn:
            P = int(P * 2)
            log.append(f"{move_name}'s power doubled from frustration!")
    
    # Stomp, Steam Roller: 2x power vs Minimize
    if power_effect_data.get("doubled_minimize"):
        if hasattr(target, '_minimized') and target._minimized:
            P = int(P * 2)
            log.append(f"{move_name} stomped the tiny target!")
    
    # Gust, Twister: 2x power vs Fly/Bounce/Sky Drop
    if power_effect_data.get("doubled_fly_bounce_sky_drop"):
        if hasattr(target, 'invulnerable_type') and target.invulnerable_type in ["fly", "bounce", "sky-drop"]:
            P = int(P * 2)
            log.append(f"{move_name} struck the airborne target!")
    
    # Dynamax Cannon, Behemoth Blade: 2x vs Dynamax
    # For Gen V+, this goes in "other" multiplier, not Power
    generation_power = get_generation(field_effects=field_effects)
    if power_effect_data.get("doubled_vs_dynamax"):
        if hasattr(target, 'dynamaxed') and target.dynamaxed:
            if generation_power <= 4:
                # Gen I-IV: Apply to Power
                P = int(P * 2)
                # Gen V+: Applied in "other" multiplier below
                log.append(f"{move_name}'s power doubled against the Dynamax Pokémon!")
    
    # Rising Voltage: 2x in Electric Terrain (if grounded)
    if power_effect_data.get("doubled_in_electric_terrain") and terrain == "electric":
        # Check if target is grounded
        is_grounded = True
        if "Flying" in [t for t in target.types if t]:
            is_grounded = False
        if target.ability and "levitate" in target.ability.lower():
            is_grounded = False
        if is_grounded:
            P = int(P * 2)
            log.append(f"{move_name}'s power doubled in Electric Terrain!")
    
    # Collision Course, Electro Drift: 5461/4096 if super effective
    # For Gen V+, this goes in "other" multiplier, not Power
    if power_effect_data.get("boosted_super_effective"):
        mult, _ = type_multiplier(mv.get("type", "Normal"), target, user=user)
        if mult > 1.0:
            if generation_power <= 4:
                # Gen I-IV: Apply to Power (approximate 1.33x)
                P = int(P * 1.33)
                # Gen V+: Applied in "other" multiplier as 5461/4096 below
                log.append(f"{move_name} surged with extra power!")
    
    # Hydro Steam: NOT weakened by sun (would need special handling in weather calc)
    if power_effect_data.get("boosted_in_sun") and weather == "sun":
        P = int(P * 1.5)
        log.append(f"{move_name} was boosted by the harsh sunlight!")
    
    # Psyblade: 1.5x in Electric Terrain
    if power_effect_data.get("boosted_in_electric_terrain") and terrain == "electric":
        P = int(P * 1.5)
        log.append(f"{move_name} was boosted by Electric Terrain!")
    
    # Expanding Force: 1.5x in Psychic Terrain (and hits both foes in doubles)
    if power_effect_data.get("boosted_in_terrain"):
        boost_terrain = power_effect_data["boosted_in_terrain"]
        if terrain == boost_terrain:
            P = int(P * 1.5)
            log.append(f"{move_name} was boosted by the terrain!")
    
    # Misty Explosion: 1.5x in Misty Terrain (Gen VIII+)
    if move_lower == "misty-explosion" and terrain == "misty":
        generation_check = get_generation(field_effects=field_effects)
        if generation_check >= 8:
            P = int(P * 1.5)
            log.append(f"{move_name} was boosted by Misty Terrain!")
    
    # Stored Power: 20 base power + 20 per positive stat stage
    if power_effect_data.get("power_per_boost"):
        if hasattr(user, 'stages'):
            total_boosts = sum(max(0, stage) for stage in user.stages.values())
            P = 20 + (20 * total_boosts)
            log.append(f"{move_name}'s power is {P} from stat boosts!")
    
    # Punishment: 60 base power + 20 per positive stat stage on target
    if power_effect_data.get("power_per_boost_target"):
        if hasattr(target, 'stages'):
            total_boosts = sum(max(0, stage) for stage in target.stages.values())
            P = 60 + (20 * total_boosts)
            if P > 200:
                P = 200  # Max 200
            log.append(f"{move_name}'s power is {P} from opponent's boosts!")
    
    # Rage Fist: 50 base power + 50 per hit taken
    if power_effect_data.get("power_per_hit_taken"):
        hits_taken = getattr(user, '_hits_taken', 0)
        P = 50 + (50 * hits_taken)
        log.append(f"{move_name}'s power is {P} from rage!")
    
    # Rage Gen II: Damage multiplier based on counter
    if move_lower_ban == "rage" and hasattr(user, '_rage_counter'):
        gen_rage_power = get_generation(field_effects=field_effects)
        if gen_rage_power == 2:
            rage_multiplier = getattr(user, '_rage_counter', 1)
            P = int(P * rage_multiplier)
            log.append(f"Rage's power multiplied by {rage_multiplier}!")
    
    # Last Respects: 50 base power + 50 per fainted party member
    if power_effect_data.get("power_per_faint"):
        fainted_count = getattr(user, '_fainted_allies', 0)
        P = 50 + (50 * fainted_count)
        log.append(f"{move_name}'s power is {P} from fallen allies!")
    
    # Apply terrain power modifications
    if field_effects:
        # Check if target is grounded (not Flying-type, no Levitate, no Air Balloon)
        is_grounded = True
        if "Flying" in [t for t in target.types if t]:
            is_grounded = False
        if target.ability and "levitate" in target.ability.lower():
            is_grounded = False
        if target.item and "air-balloon" in target.item.lower().replace(" ", "-"):
            is_grounded = False
        
        terrain_generation = get_generation(field_effects=field_effects)
        P = apply_terrain_move_effects(
            mv.get("type", "Normal"),
            getattr(field_effects, 'terrain', None),
            is_grounded,
            P,
            generation=terrain_generation
        )

    # Apply ability damage boosts (Overgrow, Blaze, Torrent, Swarm, Iron Fist, Strong Jaw, etc.)
    # Note: Stat multipliers like Huge Power are now handled in get_effective_stat()
    ability_mult = 1.0
    user_ability = normalize_ability_name(user.ability or "")
    ability_data = ABILITY_EFFECTS.get(user_ability, {})
    
    # Flash Fire - 1.5x Fire moves after being hit by Fire
    # NOTE: For Gen III-IV, Flash Fire is applied in the generation-specific formula, not here
    # For Gen V+, Flash Fire is applied here as part of ability_mult
    generation_ff = get_generation(field_effects=field_effects)
    if user.flash_fire_active and mv.get("type", "Normal") == "Fire":
        if generation_ff >= 5:
            # Gen V+: Apply in ability_mult (goes into other_mult)
            ability_mult *= 1.5
            log.append(f"{user.species}'s Flash Fire boosted {move_name}!")
        # Gen III-IV: Applied separately in generation-specific formulas (ff_mult, ff_mult_gen4)
    
    # Solar Power - 1.5x special attack in sun (unaffected by Nullscape, only by Cloud Nine)
    if user_ability == "solar-power" and mv.get("category") == "special":
        current_weather = getattr(field_effects, 'weather', None) if field_effects else None
        if current_weather == "sun":
            # Check for Cloud Nine on field
            has_cloud_nine_solar = False
            if field_effects and hasattr(user, '_battle_state') and user._battle_state:
                battle_state_solar = user._battle_state
                all_mons_solar = []
                if hasattr(battle_state_solar, 'p1_party'):
                    all_mons_solar.extend([m for m in battle_state_solar.p1_party if m and m.hp > 0])
                if hasattr(battle_state_solar, 'p2_party'):
                    all_mons_solar.extend([m for m in battle_state_solar.p2_party if m and m.hp > 0])
                for mon in all_mons_solar:
                    if mon and mon.ability:
                        ab_norm = normalize_ability_name(mon.ability)
                        if ab_norm in ["cloud-nine", "air-lock"]:
                            has_cloud_nine_solar = True
            
            # Solar Power works if weather is active (not disabled by Cloud Nine)
            if not has_cloud_nine_solar:
                ability_mult *= 1.5
                log.append(f"{user.species}'s Solar Power boosted {move_name}!")
    
    # Type-based boosts at low HP (Overgrow, Blaze, Torrent, Swarm)
    # Gen 3-4: Power boost (applied here as ability_mult)
    # Gen 5+: Attack/SpA boost (applied in A/D calculation)
    if "boost_type" in ability_data:
        move_type = mv.get("type", "Normal")
        if move_type.title() == ability_data["boost_type"]:
            hp_ratio = user.hp / user.max_hp if user.max_hp > 0 else 1.0
            if hp_ratio <= ability_data.get("threshold", 0.33):
                # Gen 3-4: Apply as power multiplier
                if generation <= 4:
                    ability_mult *= ability_data.get("multiplier", 1.5)
                # Gen 5+: Applied in get_effective_stat() for Attack/SpA
    
    # Technician: Boosts moves with power ≤60 by 1.5x
    if "low_power_boost" in ability_data:
        threshold = ability_data.get("threshold", 60)
        if P <= threshold:
            # Gen 4: Doesn't boost Struggle or Beat Up
            # Gen 5+: Boosts Struggle and Beat Up
            should_boost = True
            if generation == 4:
                if normalized_move in ["struggle", "beat-up"]:
                    should_boost = False
            
            if should_boost:
                ability_mult *= ability_data["low_power_boost"]
                log.append(f"{user.species}'s Technician boosted {move_name}!")
    
    # Sheer Force: 1.3x boost if move has secondary effects
    # NOTE: This is handled later in the damage calculation (around line 5213)
    # to avoid double application. The later check uses an explicit list of moves.
    # This section is kept for other abilities that boost secondary effect moves.
    if ability_data.get("boost_secondary_effect_moves") and user_ability != "sheer-force":
        # Using top-level import
        effect_data = get_move_secondary_effect(move_name)
        # Check if move is not affected by Sheer Force (e.g., Scale Shot)
        if not effect_data.get("not_affected_by_sheer_force"):
            # Check if move has any secondary effects (status, stat changes, flinch, etc.)
            has_secondary = any(key in effect_data for key in ["status", "stat_drop", "flinch", "confuse"])
            if has_secondary and not effect_data.get("status_move"):
                ability_mult *= ability_data["boost_secondary_effect_moves"]
                log.append(f"{user.species}'s Sheer Force boosted {move_name}!")
    
    # Type conversion boost (Pixilate, Aerilate, Refrigerate, Galvanize)
    # Gen 6: 1.3x (5325/4096)
    # Gen 7+: 1.2x (4915/4096)
    # Only apply if the ability actually converted the move (not if Electrify overrode it)
    if was_converted_by_ability and ability_data.get("converts_normal_to"):
        generation = get_generation(field_effects=field_effects)
        
        if generation <= 6:
            ability_mult *= 1.3  # Gen 6
        else:
            ability_mult *= 1.2  # Gen 7+
    
    # Normalize boost (Gen 7+)
    # Gen 7+: Normal-type moves get 20% boost (4915/4096)
    # This applies to both originally Normal moves AND moves converted by Normalize
    if user_ability_data.get("converts_all_to") == "Normal":
        generation = get_generation(field_effects=field_effects)
        
        if generation >= 7:
            # Check if current move is Normal type (either originally or converted)
            if mv.get("type") == "Normal":
                ability_mult *= 4915 / 4096  # Exact 20% boost
    
    # Weather-based type boosts (Sand Force, etc.) - 1.3x (or 1.2x with Nullscape)
    if ability_data.get("boost_types_weather") and field_effects:
        boost_data = ability_data["boost_types_weather"]
        current_weather = getattr(field_effects, 'weather', None)
        required_weather = boost_data.get("weather")
        boosted_types = boost_data.get("types", [])
        
        # Sand Force: Gen 9+ no longer boosts Rock
        if user_ability == "sand-force":
            generation = get_generation(field_effects=field_effects)
            if generation >= 9 and "Rock" in boosted_types:
                boosted_types = [t for t in boosted_types if t != "Rock"]
        
        if current_weather == required_weather and mv.get("type", "Normal") in boosted_types:
            # Check for Cloud Nine on field
            has_cloud_nine_weather = False
            if hasattr(user, '_battle_state') and user._battle_state:
                battle_state_weather_boost = user._battle_state
                all_mons_weather_boost = []
                if hasattr(battle_state_weather_boost, 'p1_party'):
                    all_mons_weather_boost.extend([m for m in battle_state_weather_boost.p1_party if m and m.hp > 0])
                if hasattr(battle_state_weather_boost, 'p2_party'):
                    all_mons_weather_boost.extend([m for m in battle_state_weather_boost.p2_party if m and m.hp > 0])
                for mon in all_mons_weather_boost:
                    if mon and mon.ability:
                        ab_norm = normalize_ability_name(mon.ability)
                        if ab_norm in ["cloud-nine", "air-lock"]:
                            has_cloud_nine_weather = True
            
            # Weather-based ability boosts work if weather is active (not disabled by Cloud Nine)
            if not has_cloud_nine_weather:
                base_multiplier = boost_data.get("multiplier", 1.3)
                ability_mult *= base_multiplier
                log.append(f"{user.species}'s {user.ability.replace('-', ' ').title()} boosted {move_name}!")
    
    move_mechanics = get_move_mechanics(move_name)
    
    # Throat Chop prevents sound-based moves for two turns
    if getattr(user, 'throat_chop_turns', 0) > 0:
        is_sound_move = False
        if move_mechanics and move_mechanics.get('is_sound_move'):
            is_sound_move = True
        else:
            secondary_data = get_move_secondary_effect(move_name)
            is_sound_move = secondary_data.get("sound_move", False)
        if is_sound_move:
            if hasattr(user, '_last_move_failed'):
                user._last_move_failed = True
            return f"**{user.species}** used **{move_name}**!\nBut it failed! {user.species} can't use sound-based moves!"
    
    # Check move mechanics from database for special interactions
    if move_mechanics:
        # Iron Fist: Boosts punch moves by 20%
        if user_ability == "iron-fist" and move_mechanics['is_punch_move']:
            ability_mult *= 1.2
            log.append(f"{user.species}'s Iron Fist boosted {move_name}!")
        
        # Punching Glove: Boosts punch moves by 10%, stacks with Iron Fist, prevents contact (Gen 9+)
        if item_is_active(user) and user.item:
            u_item_v2 = normalize_item_name(user.item)
            u_item_data_v2 = get_item_effect(u_item_v2)
            gen_pg = get_generation(field_effects=field_effects)
            if u_item_data_v2.get("punch_boost") and move_mechanics.get('is_punch_move') and gen_pg >= 9:
                punch_boost = u_item_data_v2["punch_boost"]
                ability_mult *= punch_boost
                log.append(f"{user.species}'s Punching Glove boosted {move_name}!")
                # Prevents contact (handled in _contact_side_effects)
        
        # Strong Jaw: Boosts bite moves by 50%
        # NOTE: Strong Jaw is also checked later (line ~4472) for Gen 6+ using a move list
        # To avoid double application for Gen 6+, we'll only use the later check
        # (commented out to avoid double application)
        # if user_ability == "strong-jaw" and move_mechanics['is_bite_move']:
        #     ability_mult *= 1.5
        #     log.append(f"{user.species}'s Strong Jaw boosted {move_name}!")
        
        # Mega Launcher: Boosts pulse moves by 50%
        # NOTE: Mega Launcher is also checked later using user_ability_data (line ~4570)
        # To avoid double application, we'll only use the later check which uses a list
        # (commented out to avoid double application)
        # if user_ability == "mega-launcher" and move_mechanics['is_pulse_move']:
        #     ability_mult *= 1.5
        #     log.append(f"{user.species}'s Mega Launcher boosted {move_name}!")
        
        # Soundproof: Immune to sound moves
        # Check if this is a sound move (from move_mechanics OR move_effects)
        is_sound_move_damage = False
        if move_mechanics and move_mechanics.get('is_sound_move'):
            is_sound_move_damage = True
        else:
            secondary_data_soundproof = get_move_secondary_effect(move_name)
            if secondary_data_soundproof.get("sound_move", False):
                is_sound_move_damage = True
        
        if is_sound_move_damage:
            target_ability = normalize_ability_name(target.ability or "")
            if target_ability == "soundproof":
                # Gen VIII+: User is not immune to their own sound moves
                if generation_check >= 8 and target == user:
                    # Gen VIII+: User is affected even with Soundproof
                    pass
                else:
                    # Soundproof blocks sound moves
                    log.append(f"{target.species}'s Soundproof blocked the sound!")
                    if generation_check >= 5:
                        disrupt_rampage(user, field_effects, reason="soundproof")
                    return 0, {"immune": True, "type": mv.get("type", "Normal")}, log
        
        # Bulletproof: Immune to ball and bomb moves (Sludge Bomb, Octazooka, Zap Cannon, Egg Bomb, Shadow Ball, etc.)
        # Gen VII+: Also immune to Rock Blast
        move_lower_bp = move_name.lower().replace(" ", "-")
        is_bomb_move = move_lower_bp in ["egg-bomb", "sludge-bomb", "octazooka", "zap-cannon"]
        is_ball_move = move_lower_bp in ["shadow-ball", "aura-sphere", "focus-blast"]
        is_rock_blast = generation_check >= 7 and move_lower_bp == "rock-blast"
        if target_ability == "bulletproof" and (move_mechanics.get('is_bullet_move') or is_bomb_move or is_ball_move or is_rock_blast):
            log.append(f"{target.species}'s Bulletproof protected it!")
            if generation_check >= 5:
                disrupt_rampage(user, field_effects, reason="bulletproof")
            return 0, {"immune": True, "type": mv.get("type", "Normal")}, log
    
    # === ADDITIONAL DAMAGE BOOSTS ===
    # Analytic: 1.3x (5325/4096) when moving last
    # Gen 5-7: "Moving last" determination uses modified speed (status/items/abilities) for all Pokemon
    # Gen 8+: "Moving last" uses base speed for fainted Pokemon
    # NOTE: Current implementation uses Gen 8+ logic (is_moving_last flag from panel.py)
    # The Gen 5-7 difference only matters in the rare case where a Pokemon faints mid-turn
    if user_ability == "analytic" and is_moving_last:
        ability_mult *= 5325 / 4096  # Exact multiplier ≈ 1.30005
        log.append(f"{user.species}'s Analytic boosted the attack!")
    
    # Stakeout: 2x vs switching foe
    if user_ability == "stakeout":
        # Check if target just switched in this turn
        if getattr(target, '_just_switched_in', False):
            ability_mult *= 2.0
            log.append(f"{user.species}'s Stakeout boosted {move_name}!")
    
    # Neuroforce: 1.25x on super effective hits
    if user_ability == "neuroforce":
        # Will check type effectiveness later
        pass  # Applied after type_mult calculation
    
    # Rivalry: 1.25x same gender, 0.75x opposite gender
    if user_ability == "rivalry" and user.gender and target.gender:
        if user.gender == target.gender:
            ability_mult *= 1.25
            log.append(f"{user.species}'s Rivalry boosted {move_name}!")
        elif user.gender != target.gender:
            ability_mult *= 0.75
            log.append(f"{user.species}'s Rivalry weakened {move_name}!")
    
    # Reckless: 1.2x recoil moves
    if user_ability == "reckless" and move_mechanics and move_mechanics['is_recoil_move']:
        ability_mult *= 1.2
        log.append(f"{user.species}'s Reckless boosted {move_name}!")
    
    # === NULLSCAPE: Type-specific damage boosts ===
    nullscape_type_dmg = _get_nullscape_type(user, getattr(user, '_battle_state', None))
    if nullscape_type_dmg:
        move_type_for_boost = mv.get("type", "Normal")
        move_type_for_boost = move_type_for_boost.strip().title()
        
        # Ice Nullscape: 1.3x Ice moves
        if nullscape_type_dmg == "Ice" and move_type_for_boost == "Ice":
            ability_mult *= 1.3
            log.append(f"Nullscape boosted {move_name}!")
        
        # Rock Nullscape: 1.3x Rock moves
        elif nullscape_type_dmg == "Rock" and move_type_for_boost == "Rock":
            ability_mult *= 1.3
            log.append(f"Nullscape boosted {move_name}!")
        
        # Normal Nullscape: 1.3x Normal moves
        elif nullscape_type_dmg == "Normal" and move_type_for_boost == "Normal":
            ability_mult *= 1.3
            log.append(f"Nullscape boosted {move_name}!")
        
        # Steel Nullscape: 1.3x Steel moves
        elif nullscape_type_dmg == "Steel" and move_type_for_boost == "Steel":
            ability_mult *= 1.3
            log.append(f"Nullscape boosted {move_name}!")
        
        # Ghost Nullscape: 1.3x Ghost moves
        elif nullscape_type_dmg == "Ghost" and move_type_for_boost == "Ghost":
            ability_mult *= 1.3
            log.append(f"Nullscape boosted {move_name}!")
    
    # Punk Rock: 1.3x sound moves, resists sound moves
    if user_ability == "punk-rock" and move_mechanics and move_mechanics['is_sound_move']:
        ability_mult *= 1.3
        log.append(f"{user.species}'s Punk Rock boosted {move_name}!")
    
    # Defeatist: Halve Attack and Sp. Atk below half HP
    if user_ability == "defeatist" and user.hp <= user.max_hp // 2:
        ability_mult *= 0.5
        log.append(f"{user.species}'s Defeatist weakened {move_name}!")
    
    # Sharpness: 1.5x slicing moves
    if user_ability == "sharpness":
        slicing_moves = ["aerial-ace", "air-cutter", "air-slash", "aqua-cutter", "behemoth-blade", "bitter-blade",
                         "ceaseless-edge", "cross-poison", "cut", "fury-cutter", "kowtow-cleave", "leaf-blade",
                         "mighty-cleave", "night-slash", "population-bomb", "psycho-cut", "psyblade", "razor-leaf",
                         "razor-shell", "sacred-sword", "secret-sword", "shadow-claw", "slash", "solar-blade",
                         "stone-axe", "tachyon-cutter", "x-scissor"]
        if normalized_move in slicing_moves:
            ability_mult *= 1.5
            log.append(f"{user.species}'s Sharpness boosted {move_name}!")
    
    # Strong Jaw: 1.5x biting moves (Gen 6+)
    if user_ability == "strong-jaw":
        generation = get_generation(field_effects=field_effects)
        if generation >= 6:
            biting_moves = ["bite", "crunch", "fire-fang", "fishious-rend", "hyper-fang", "ice-fang",
                            "jaw-lock", "poison-fang", "psychic-fangs", "thunder-fang"]
            if normalized_move in biting_moves:
                ability_mult *= 1.5
                log.append(f"{user.species}'s Strong Jaw boosted {move_name}!")
    
    # Tough Claws: ~30% boost for contact moves (Gen 6+)
    if user_ability == "tough-claws":
        generation = get_generation(field_effects=field_effects)
        
        if generation >= 6 and makes_contact(move_name):
            # Use exact multiplier: 5325/4096 ≈ 1.3003
            ability_mult *= 5325 / 4096
            log.append(f"{user.species}'s Tough Claws boosted {move_name}!")
    
    # Sheer Force: ~30% boost to moves with secondary effects (5325/4096 ≈ 1.3003)
    # Secondary effects are removed in move_effects.py
    # This is the PRIMARY Sheer Force check - the earlier check (line ~4998) is skipped for Sheer Force
    if user_ability == "sheer-force":
        # Check if move is not affected by Sheer Force (e.g., Scale Shot)
        effect_data_sf = get_move_secondary_effect(move_name)
        if not effect_data_sf.get("not_affected_by_sheer_force"):
            # Check if move has secondary effects (excluding recoil, stat drops to self, etc.)
            mechanics = get_move_mechanics(move_name, battle_state_ctx)
            has_secondary = False
            
            # Explicit list of moves affected by Sheer Force (based on Bulbapedia)
            sheer_force_moves = [
                # Moves that lower target stats
            "acid", "acid-spray", "air-slash", "ancient-power", "astonish", "aurora-beam", "bite", "blizzard",
            "body-slam", "bone-club", "bounce", "breaking-swipe", "bubble", "bubble-beam", "bug-buzz", "bulldoze",
            "burning-jealousy", "charge-beam", "chilling-water", "confusion", "constrict", "crunch", "crush-claw",
            "dark-pulse", "dragon-breath", "dragon-rush", "dynamic-punch", "earth-power", "ember", "esper-wing",
            "extrasensory", "fake-out", "fire-blast", "fire-fang", "fire-punch", "flame-charge", "flame-wheel",
            "flamethrower", "flare-blitz", "flash-cannon", "focus-blast", "force-palm", "gunk-shot", "headbutt",
            "heat-wave", "hurricane", "ice-beam", "ice-fang", "ice-punch", "icicle-crash", "icy-wind", "iron-head",
            "iron-tail", "lava-plume", "liquidation", "low-sweep", "lunge", "metal-claw", "mud-bomb", "muddy-water",
            "mud-shot", "mud-slap", "mystical-fire", "play-rough", "poison-fang", "poison-jab", "poison-sting",
            "poison-tail", "pounce", "power-up-punch", "psybeam", "psychic", "psychic-noise", "razor-shell",
            "rock-climb", "rock-slide", "rock-smash", "rock-tomb", "sandsear-storm", "scald", "scorching-sands",
            "secret-power", "shadow-ball", "signal-beam", "skitter-smack", "sky-attack", "sludge-bomb", "sludge-wave",
            "snarl", "snore", "steel-wing", "stomp", "stone-axe", "struggle-bug", "throat-chop", "thunder",
            "thunder-fang", "thunderbolt", "thunder-punch", "trailblaze", "twister", "upper-hand", "water-pulse",
            "waterfall", "zap-cannon", "zen-headbutt",
            # Moves that trap or have special effects
                "anchor-shot", "ceaseless-edge", "eerie-spell", "genesis-supernova", "spirit-shackle", "sparkling-aria"
            ]
            
            if normalized_move in sheer_force_moves:
                has_secondary = True
            
            if has_secondary:
                ability_mult *= 5325 / 4096  # Exact multiplier (~1.3003)
                log.append(f"{user.species}'s Sheer Force boosted {move_name}!")
                # Mark that Sheer Force is active for this move
                user._sheer_force_active = True
    
    # Supreme Overlord: 1.1x per fainted ally
    if user_ability == "supreme-overlord":
        # Track fainted allies (should be in battle state)
        fainted_count = getattr(user, '_fainted_allies', 0)
        if fainted_count > 0:
            boost = 1.0 + (0.1 * fainted_count)
            ability_mult *= boost
            log.append(f"{user.species}'s Supreme Overlord boosted {move_name}!")
    
    # Rocky Payload: 1.5x Rock moves
    if user_ability == "rocky-payload" and mv.get("type", "Normal") == "Rock":
        ability_mult *= 1.5
        log.append(f"{user.species}'s Rocky Payload boosted {move_name}!")
    
    # Steelworker: 1.5x Steel moves
    if user_ability == "steelworker" and mv.get("type", "Normal") == "Steel":
        ability_mult *= 1.5
        log.append(f"{user.species}'s Steelworker boosted {move_name}!")
    
    # Dragon's Maw: 1.5x Dragon moves
    if user_ability == "dragons-maw" and mv.get("type", "Normal") == "Dragon":
        ability_mult *= 1.5
        log.append(f"{user.species}'s Dragon's Maw boosted {move_name}!")
    
    # Transistor: Electric move boost (Gen 8: 1.5x, Gen 9: 1.3x)
    if user_ability == "transistor" and mv.get("type", "Normal") == "Electric":
        generation = get_generation(field_effects=field_effects)
        
        if generation <= 8:
            ability_mult *= 1.5  # Gen 8
        else:
            ability_mult *= 5325 / 4096  # Gen 9: ~1.3003
        log.append(f"{user.species}'s Transistor boosted {move_name}!")
    
    # Wind Power / Electromorphosis: Charged state boosts next Electric move
    if mv.get("type", "Normal") == "Electric" and getattr(user, "_charged", False):
        ability_mult *= 2.0  # Charge doubles Electric move power
        user._charged = False  # Consume the charge
        log.append(f"{user.species} used its charge to boost {move_name}!")
    
    # Mega Launcher: 1.5x pulse and aura moves
    if user_ability_data.get("boost_pulse_moves"):
        pulse_moves = ["aura-sphere", "dark-pulse", "dragon-pulse", "heal-pulse", 
                      "origin-pulse", "terrain-pulse", "water-pulse"]
        if normalized_move in pulse_moves:
            ability_mult *= user_ability_data["boost_pulse_moves"]
            log.append(f"{user.species}'s Mega Launcher boosted {move_name}!")
    
    # Merciless: Always crit against poisoned foes (unless Battle Armor/Shell Armor)
    if user_ability == "merciless" and target.status and target.status.lower() in ["psn", "tox", "poison", "badly poisoned"]:
        # Check if target has crit immunity (Battle Armor, Shell Armor, Lucky Chant)
        target_ability = normalize_ability_name(target.ability or "")
        if ignores_target_ability:
            target_ability = ""
            target_ability_data = {}
        else:
            target_ability_data = get_ability_effect(target_ability)
        if not target_ability_data.get("crit_immunity"):
            # Generation-aware crit damage (Gen 1-5: 2x, Gen 6+: 1.5x)
            generation = get_generation(field_effects=field_effects)
            crit = 2.0 if generation <= 5 else 1.5
        is_crit = True
        log.append(f"{user.species}'s Merciless ensured a critical hit!")
    
    # Tinted Lens: 2x on not very effective hits
    # Will be applied after type_mult calculation

    # === HELPER FUNCTION FOR TYPE EFFECTIVENESS (Gen I-III) ===
    def _get_type_effectiveness_gen1(move_type: str, target: Mon, gen: int) -> Tuple[float, float]:
        """Calculate Type1 and Type2 multipliers for Gen I-III formulas."""
        # TYPE_MULT is defined at the top of this file
        t1 = target.types[0].strip().title() if target.types and target.types[0] else "Normal"
        t2 = target.types[1].strip().title() if len(target.types) > 1 and target.types[1] else None
        
        type1_mult = TYPE_MULT.get((move_type, t1), 1.0)
        type2_mult = TYPE_MULT.get((move_type, t2), 1.0) if t2 else 1.0
        
        # Gen 1: Type chart differences
        if gen == 1:
            # Gen 1: Ice was neutral (1x) against Fire (not 0.5x)
            if move_type == "Ice" and t1 == "Fire":
                type1_mult = 1.0
            if move_type == "Ice" and t2 == "Fire":
                type2_mult = 1.0
            
            # Gen 1: Bug was super-effective (2x) against Poison (not 0.5x)
            if move_type == "Bug" and t1 == "Poison":
                type1_mult = 2.0
            if move_type == "Bug" and t2 == "Poison":
                type2_mult = 2.0
            
            # Gen 1: Poison was super-effective (2x) against Bug (not 0.5x)
            if move_type == "Poison" and t1 == "Bug":
                type1_mult = 2.0
            if move_type == "Poison" and t2 == "Bug":
                type2_mult = 2.0
        
        return type1_mult, type2_mult
    
    # === CALCULATE WEATHER MULTIPLIER ===
    # Weather is a multiplier in damage formula (Gen II+), not just a power modifier
    weather = getattr(field_effects, 'weather', None) if field_effects else None
    weather_mult = 1.0
    # move_type_for_weather is already defined earlier (after mv is loaded at line ~3107)
    
    # Check for Cloud Nine / Air Lock (negates weather effects)
    # Check for Cloud Nine / Air Lock (disables weather)
    has_cloud_nine = False
    if field_effects:
        # Check all Pokemon on field for Cloud Nine / Air Lock
        all_mons_weather = []
        if hasattr(user, '_battle_state') and user._battle_state:
            battle_state_weather = user._battle_state
            if hasattr(battle_state_weather, 'p1_party'):
                all_mons_weather.extend([m for m in battle_state_weather.p1_party if m and m.hp > 0])
            if hasattr(battle_state_weather, 'p2_party'):
                all_mons_weather.extend([m for m in battle_state_weather.p2_party if m and m.hp > 0])
        
        for mon in all_mons_weather:
            if mon and mon.ability:
                ab_norm = normalize_ability_name(mon.ability)
                if ab_norm in ["cloud-nine", "air-lock"]:
                    has_cloud_nine = True
    
    # Cloud Nine: When Cloud Nine/Air Lock is active, weather is disabled (1.0x)
    if weather:
        if has_cloud_nine:
            # Cloud Nine disables weather
            weather_boost_mult = 1.0
        else:
            # Normal weather boost
            weather_boost_mult = 1.5
    else:
        weather_boost_mult = 1.0
    
    if weather and not has_cloud_nine:
        # Apply weather effects when weather is active AND Cloud Nine is not disabling it
        
        # Water-type moves: 1.5x in rain, 0.5x in harsh sunlight
        if move_type_for_weather == "Water":
            if weather == "rain":
                weather_mult = weather_boost_mult
            elif weather == "sun":
                weather_mult = 0.5  # Debuff: unchanged
        # Fire-type moves: 1.5x in harsh sunlight, 0.5x in rain
        elif move_type_for_weather == "Fire":
            if weather == "sun":
                weather_mult = weather_boost_mult
            elif weather == "rain":
                weather_mult = 0.5  # Debuff: unchanged
        # SolarBeam: 0.5x in non-clear weather (except harsh sunlight) - debuff unchanged
        elif normalized_move == "solar-beam" or normalized_move == "solarbeam":
            if weather != "sun" and weather not in ["none", None, ""]:
                weather_mult = 0.5  # Debuff: unchanged
        # Hydro Steam: 1.5x in harsh sunlight (Gen 9+)
        elif normalized_move == "hydro-steam" and weather == "sun":
            weather_mult = weather_boost_mult

    # === GENERATION-SPECIFIC DAMAGE FORMULA ===
    # Calculate base damage according to generation-specific formulas
    generation = get_generation(field_effects=field_effects)
    
    # Gen I: Critical is inside base calculation, random 217-255/255
    if generation == 1:
        # Handle A/D > 255: both divided by 4
        A_calc = A
        D_calc = D
        if A_calc > 255 or D_calc > 255:
            A_calc = A_calc // 4
            D_calc = D_calc // 4
        
        # Critical multiplier (2x) applied inside base calculation
        crit_mult = 2.0 if is_crit else 1.0
        
        # Base damage: ((2 × Level × Critical) / 5) + 2) × (Power × A / D) / 50) + 2
        # Note: Gen I formula structure is different - Critical multiplies Level
        base_part1 = math.floor((2 * lvl * crit_mult) / 5) + 2
        base_part2 = math.floor((P * A_calc) / max(1, D_calc))
        core = math.floor((base_part1 * base_part2) / 50) + 2
        
        # Random: 217-255 / 255
        rand_int = random.randint(217, 255)
        rand = rand_int / 255.0
        # If calculated damage is 1, random is always 1
        if core == 1:
            rand = 1.0
    
    # Gen II-V+: Standard formula structure
    else:
        # Base damage: ((2 × Level / 5 + 2) × Power × A / D) / 50 + 2
        core = math.floor(math.floor((2 * lvl) / 5 + 2) * P * A / max(1, D) / 50) + 2
        
        # Random variation
        if generation == 2:
            # Gen II: 217-255 / 255, except Flail/Reversal (always 1)
            if normalized_move in ["flail", "reversal"]:
                rand = 1.0
            else:
                rand_int = random.randint(217, 255)
                rand = rand_int / 255.0
        else:
            # Gen III+: 85-100 / 100
            rand_int = random.randint(85, 100)
            rand = rand_int / 100.0
            # Gen II Flail/Reversal: No random variation (already handled above)
            if normalized_move in ["flail", "reversal"] and generation == 2:
                rand = 1.0
    
    # Get type effectiveness with ability checks
    # Use makes_contact for accurate detection (has fallback list)
    is_contact = makes_contact(move_name)
    # Update mv if contact flag is missing
    if is_contact and not mv.get("contact"):
        mv = mv.copy() if mv else {}
        mv["contact"] = 1
    
    # Long Reach: Contact moves don't make contact
    if is_contact and user_ability_data.get("contact_moves_dont_make_contact"):
        is_contact = False
    
    # Get generation for type chart calculation
    generation = get_generation(field_effects=field_effects)
    
    move_category = mv.get("category", "physical")
    if ignores_target_ability:
        setattr(target, '_ability_temporarily_ignored', True)
    # Calculate type effectiveness - initialize to 1.0 as fallback
    type_mult = 1.0
    ability_msg = None
    try:
        type_mult, ability_msg = type_multiplier(mv.get("type", "Normal"), target, is_contact, move_category, generation, field_effects, user)
    except Exception:
        # Fallback if type_multiplier fails
        type_mult = 1.0
        ability_msg = None
    if ignores_target_ability and hasattr(target, '_ability_temporarily_ignored'):
        delattr(target, '_ability_temporarily_ignored')
    if ability_msg:
        log.append(ability_msg)
    
    # === NULLSCAPE (Rock): Rock types take 0.75x from super effective damage ===
    nullscape_type_rock = _get_nullscape_type(user, getattr(user, '_battle_state', None))
    if nullscape_type_rock == "Rock" and type_mult > 1.0:
        target_types = [t.strip().title() if t else None for t in target.types]
        if "Rock" in target_types:
            type_mult *= 0.75
            log.append(f"{target.species}'s Nullscape reduced super effective damage!")

    if mv.get("type", "Normal").strip().title() == "Stellar":
        if getattr(target, "terastallized", False) and getattr(target, "_tera_is_stellar", False):
            type_mult *= 2.0
            log.append(f"{target.species} is especially vulnerable to Stellar energy!")
    
    # === TYPE EFFECTIVENESS EXCEPTIONS ===
    # Freeze-Dry: Super effective against Water types
    if normalized_move == "freeze-dry":
        if "Water" in target.types:
            type_mult *= 2.0  # Additional 2x multiplier
            log.append(f"{move_name} is super effective against Water!")
    
    # Flying Press: Dual-type effectiveness (Fighting + Flying)
    elif normalized_move == "flying-press":
        # Recalculate with dual typing
        # Safely unpack types (handle single-element tuples/lists)
        if not target.types:
            types_tuple = (None, None)
        elif isinstance(target.types, tuple):
            types_tuple = target.types
        elif isinstance(target.types, list):
            types_tuple = tuple(target.types)
        else:
            # Fallback: treat as single type
            types_tuple = (target.types, None)
        
        t1 = types_tuple[0] if len(types_tuple) > 0 else None
        t2 = types_tuple[1] if len(types_tuple) > 1 else None
        t1 = t1.strip().title() if t1 else "Normal"
        t2 = t2.strip().title() if t2 else None
        
        # Calculate Fighting effectiveness
        mult_fighting = TYPE_MULT.get(("Fighting", t1), 1.0)
        if t2:
            mult_fighting *= TYPE_MULT.get(("Fighting", t2), 1.0)
        
        # Calculate Flying effectiveness
        mult_flying = TYPE_MULT.get(("Flying", t1), 1.0)
        if t2:
            mult_flying *= TYPE_MULT.get(("Flying", t2), 1.0)
        
        # Multiply both together for dual-type effectiveness
        type_mult = mult_fighting * mult_flying
        log.append(f"{move_name} is both Fighting and Flying type!")
    
    # Wonder Guard: Only super-effective moves can hit
    if target_ability_data.get("only_supereffective_hits"):
        generation = get_generation(field_effects=field_effects)
        
        # Check for generation-specific bypasses
        bypass_wonder_guard = False
        
        # Gen 3: Beat Up, Future Sight, Doom Desire bypass (typeless damage)
        if generation == 3 and normalized_move in ["beat-up", "future-sight", "doom-desire"]:
            bypass_wonder_guard = True
            log.append(f"{move_name} bypassed Wonder Guard (Gen 3 typeless)!")
        
        # Gen 4: Fire Fang glitch bypasses Wonder Guard
        elif generation == 4 and normalized_move == "fire-fang":
            bypass_wonder_guard = True
            log.append(f"Fire Fang bypassed Wonder Guard (Gen 4 glitch)!")
        
        # Gen 5+: These moves no longer bypass
        # Fixed damage moves, OHKO moves, counterattacks blocked
        
        # If not bypassed and not super effective, block
        if not bypass_wonder_guard and type_mult < 2.0:
            log.append(f"{target.species}'s Wonder Guard protected it!")
            if generation_check >= 5 and getattr(user, 'rampage_move', None):
                disrupt_rampage(user, field_effects, reason="wonder-guard")
            return 0, {"wonder_guard_blocked": True, "type": mv.get("type", "Normal")}, log
    
    # For Gen V+, these effects go in "other" multiplier, not type_mult/ability_mult
    # For Gen I-IV, apply them to type_mult/ability_mult
    generation_effects = get_generation(field_effects=field_effects)
    
    if generation_effects <= 4:
        # Gen I-IV: Apply to type_mult/ability_mult
        # Multiscale / Shadow Shield - halve damage at full HP
        # G-Max Fireball ignores ignorable abilities
        gmax_ignores_ignorable = getattr(user, '_gmax_ignores_ignorable_abilities', False)
        if not gmax_ignores_ignorable and target_ability_data.get("damage_reduction_full_hp") and target.hp == target.max_hp:
            type_mult *= target_ability_data["damage_reduction_full_hp"]
            log.append(f"{target.species}'s {target.ability or target_ability} reduced the damage!")
    
    # Filter / Solid Rock / Prism Armor - reduce super effective damage
    # G-Max Fireball ignores ignorable abilities
    gmax_ignores_ignorable_gen = getattr(user, '_gmax_ignores_ignorable_abilities', False)
    if not gmax_ignores_ignorable_gen and type_mult >= 2.0 and "super_effective_reduction" in target_ability_data:
        type_mult *= target_ability_data["super_effective_reduction"]
        log.append(f"{target.species}'s {target.ability or target_ability} weakened the attack!")
    
    # Tinted Lens - not very effective becomes normally effective
    if type_mult < 1.0 and user_ability_data.get("not_very_effective_boost"):
        type_mult *= user_ability_data["not_very_effective_boost"]
        log.append(f"{user.species}'s Tinted Lens made the move hit normally!")
    
    # Neuroforce - 1.25x boost on super effective hits
    if type_mult >= 2.0 and user_ability == "neuroforce":
        ability_mult *= 1.25
        log.append(f"{user.species}'s Neuroforce boosted {move_name}!")
    
    # Fluffy - halve damage from contact moves, double from Fire
    if target_ability == "fluffy":
        if is_contact:
            type_mult *= 0.5
            log.append(f"{target.species}'s Fluffy reduced contact damage!")
        if mv.get("type", "Normal") == "Fire":
            type_mult *= 2.0
            log.append(f"{target.species}'s Fluffy doubled Fire damage!")
    
    # Ice Scales - halve special damage
    if target_ability == "ice-scales" and mv.get("category") == "special":
        type_mult *= 0.5
        log.append(f"{target.species}'s Ice Scales reduced special damage!")
    
    # Punk Rock - resist sound moves
    if target_ability == "punk-rock" and move_mechanics and move_mechanics.get('is_sound_move'):
        type_mult *= 0.5
        log.append(f"{target.species}'s Punk Rock reduced sound damage!")
    # Gen V+: These effects are handled in the "other" multiplier calculation below
    
    # Tera Shell - Makes all moves not very effective when at full HP (Gen 9+)
    if target_ability == "tera-shell" and target.hp == target.max_hp and generation >= 9:
        # Only applies to actual damaging moves (not direct damage like Struggle)
        if normalized_move != "struggle" and type_mult != 0:  # Type immunity still applies
            # Override to not very effective (0.5x)
            type_mult = 0.5
            log.append(f"It's not very effective...")
            log.append(f"{target.species}'s Tera Shell made the move not very effective!")
    
    # === DARK AURA / FAIRY AURA / AURA BREAK ===
    # Apply field-wide aura effects from all Pokemon on the field
    # NOTE: Gen 4-7: Mold Breaker/Teravolt/Turboblaze should ignore Dark/Fairy Aura
    # Gen 8+: Mold Breaker no longer ignores Auras (current implementation)
    aura_mult = 1.0
    if hasattr(user, '_battle_state') and user._battle_state:
        # Get all active Pokemon from battle state
        all_mons = []
        battle_state = user._battle_state
        if hasattr(battle_state, 'p1_party'):
            all_mons.extend([m for m in battle_state.p1_party if m and m.hp > 0])
        if hasattr(battle_state, 'p2_party'):
            all_mons.extend([m for m in battle_state.p2_party if m and m.hp > 0])
        
        if all_mons:
            field_effects = get_field_ability_effects(all_mons)
            move_type = mv.get("type", "Normal")
            if move_type == "Dark":
                aura_mult *= field_effects.get("dark_move_mult", 1.0)
                if aura_mult != 1.0:
                    if aura_mult > 1.0:
                        log.append(f"The Dark Aura boosted {move_name}!")
                    else:
                        log.append(f"The Aura Break weakened {move_name}!")
            elif move_type == "Fairy":
                aura_mult *= field_effects.get("fairy_move_mult", 1.0)
                if aura_mult != 1.0:
                    if aura_mult > 1.0:
                        log.append(f"The Fairy Aura boosted {move_name}!")
                    else:
                        log.append(f"The Aura Break weakened {move_name}!")
    
    # === CALCULATE SCREEN MULTIPLIER (needed for Gen III-IV formulas) ===
    # Apply screen modifiers (Reflect, Light Screen, Aurora Veil)
    # Infiltrator: Gen 5-6 (bypasses screens), Gen 7+ (also bypasses Substitute, Mist, Aurora Veil)
    skip_screen_multiplier = normalized_move == "brick-break"
    screen_mult = 1.0
    bypasses_screens = False
    
    # Check for Infiltrator
    user_ability_norm = normalize_ability_name(user.ability or "")
    user_ability_effects = ABILITY_EFFECTS.get(user_ability_norm, {})
    if user_ability_effects.get("ignores_screens_substitutes", False):
        generation_screen = get_generation(field_effects=field_effects)
        # Gen 5+: Infiltrator bypasses Light Screen, Reflect, Safeguard
        # Gen 7+: Also bypasses Aurora Veil (checked below)
        bypasses_screens = True
    
    if target_side and not bypasses_screens and not skip_screen_multiplier:
        # Generation-specific screen multipliers
        gen_screen = get_generation(field_effects=field_effects)
        # Default multipliers
        half = 0.5
        third_exact_gen5 = 2703 / 4096
        third_exact_gen6p = 2732 / 4096
        # Choose multiplier based on generation (doubles/triples precise values in Gen 5+)
        mult_third = half if gen_screen <= 4 else (third_exact_gen5 if gen_screen == 5 else third_exact_gen6p)
        if target_side.aurora_veil:
            screen_mult *= mult_third if gen_screen >= 5 else half
        elif move_category == "physical" and target_side.reflect:
            screen_mult *= mult_third if gen_screen >= 5 else half
        elif move_category == "special" and target_side.light_screen:
            screen_mult *= mult_third if gen_screen >= 5 else half
    elif target_side and bypasses_screens:
        # Infiltrator present - check generation for Aurora Veil
        generation_screen = get_generation(field_effects=field_effects)
        if target_side.aurora_veil and generation_screen <= 6:
            # Gen 5-6: Infiltrator does NOT bypass Aurora Veil (it didn't exist yet anyway)
            screen_mult *= 0.5
    
    # For critical hits, screens don't apply (Gen III+)
    if is_crit and generation >= 3:
        screen_mult = 1.0

    # === INITIALIZE ITEM MULTIPLIER (needed for Gen V+ formula) ===
    # Will be calculated in detail later, but initialize here for Gen V+ "other" multiplier
    item_mult = 1.0
    
    # === GENERATION-SPECIFIC MODIFIER APPLICATION ===
    # Apply modifiers in the correct order per generation
    
    if generation == 1:
        # Gen I: STAB × Type1 × Type2 × random
        # (Critical already applied in base calculation)
        # Type effectiveness is calculated as Type1 × Type2
        type1_mult, type2_mult = _get_type_effectiveness_gen1(mv.get("type", "Normal"), target, generation)
        mod = stab(mv.get("type", "Normal"), user) * type1_mult * type2_mult * rand
    
    elif generation == 2:
        # Gen II: Item × Critical × TK × Weather × Badge × STAB × Type × MoveMod × random × DoubleDmg
        # Item: 1.1 for type-enhancing items, 1 otherwise
        item_mult_gen2 = 1.0
        move_type_gen2 = mv.get("type", "Normal")
        if item_is_active(user):
            item_data_gen2 = get_item_effect(normalize_item_name(user.item))
            if item_data_gen2.get("type_enhancing") and item_data_gen2.get("boost_type") == move_type_gen2:
                item_mult_gen2 = 1.1
        
        # TK: 1, 2, or 3 for Triple Kick
        tk_mult = 1.0
        if normalized_move == "triple-kick":
            tk_hit = getattr(user, '_triple_kick_hit', 1)
            tk_mult = float(tk_hit)
        
        # Badge: 1.125 if player has badge (not in link battles)
        badge_mult = 1.0
        # Note: Badge bonus not applied in link battles - would need battle state to check
        
        # MoveMod: For Rollout, Fury Cutter, Rage
        movemod_mult = 1.0
        if normalized_move == "rollout":
            rollout_count = getattr(user, '_rollout_count', 0)
            defense_curl = 1 if getattr(user, '_defense_curl_active', False) else 0
            movemod_mult = 2 ** (rollout_count + defense_curl)
        elif normalized_move == "fury-cutter":
            fury_count = getattr(user, '_fury_cutter_count', 0)
            movemod_mult = 2 ** fury_count
        elif normalized_move == "rage":
            rage_counter = getattr(user, '_rage_counter', 1)
            movemod_mult = float(rage_counter)
        
        # DoubleDmg: 2 for specific conditions
        doubledmg_mult = 1.0
        if normalized_move == "pursuit" and getattr(target, '_is_switching', False):
            doubledmg_mult = 2.0
        elif normalized_move in ["stomp", "steam-roller"] and getattr(target, '_minimized', False):
            doubledmg_mult = 2.0
        elif normalized_move in ["gust", "twister"] and getattr(target, 'invulnerable_type', None) == "fly":
            doubledmg_mult = 2.0
        elif normalized_move in ["earthquake", "magnitude"] and getattr(target, 'invulnerable_type', None) == "underground":
            doubledmg_mult = 2.0
        
        # Critical: 2x (outside base in Gen II)
        crit_mult_gen2 = 2.0 if is_crit else 1.0
        # Always 1 for Flail, Reversal, Future Sight
        if normalized_move in ["flail", "reversal", "future-sight"]:
            crit_mult_gen2 = 1.0
        
        mod = item_mult_gen2 * crit_mult_gen2 * tk_mult * weather_mult * badge_mult * stab(mv.get("type", "Normal"), user) * type_mult * movemod_mult * rand * doubledmg_mult
    
    elif generation == 3:
        # Gen III: Burn × Screen × Targets × Weather × FF × Stockpile × Critical × DoubleDmg × Charge × HH × STAB × Type1 × Type2 × random
        # Burn: 0.5 if burned and physical (no Guts)
        burn_mult = 1.0
        if user.status == "brn" and move_category == "physical":
            if user_ability != "guts":
                burn_mult = 0.5
        
        # Screen: 0.5 (or 2/3 in doubles, unless only one target)
        # (Already calculated above as screen_mult)
        
        # Targets: 0.5 in doubles if multi-target
        targets_mult = 1.0
        # Would need battle state to check if doubles - defaulting to 1 for now
        
        # FF (Flash Fire): 1.5 if activated
        ff_mult = 1.5 if (user.flash_fire_active and mv.get("type", "Normal") == "Fire") else 1.0
        
        # Stockpile: 1, 2, or 3 for Spit Up
        stockpile_mult = 1.0
        if normalized_move == "spit-up":
            stockpile_count = getattr(user, '_stockpile_count', 0)
            stockpile_mult = float(stockpile_count) if stockpile_count > 0 else 1.0
        
        # Critical: 2x
        crit_mult_gen3 = 2.0 if is_crit else 1.0
        # Always 1 for Future Sight, Doom Desire, Spit Up
        if normalized_move in ["future-sight", "doom-desire", "spit-up"]:
            crit_mult_gen3 = 1.0
        
        # DoubleDmg: 2 for specific conditions
        doubledmg_mult_gen3 = 1.0
        if normalized_move in ["gust", "twister"] and getattr(target, 'invulnerable_type', None) in ["fly", "bounce"]:
            doubledmg_mult_gen3 = 2.0
        elif normalized_move in ["stomp", "needle-arm", "astonish", "extrasensory"] and getattr(target, '_minimized', False):
            doubledmg_mult_gen3 = 2.0
        elif normalized_move in ["surf", "whirlpool"] and getattr(target, 'invulnerable_type', None) == "dive":
            doubledmg_mult_gen3 = 2.0
        elif normalized_move in ["earthquake", "magnitude"] and getattr(target, 'invulnerable_type', None) == "underground":
            doubledmg_mult_gen3 = 2.0
        elif normalized_move == "pursuit" and getattr(target, '_is_switching', False):
            doubledmg_mult_gen3 = 2.0
        elif normalized_move == "facade" and user.status in ["psn", "tox", "brn", "par"]:
            doubledmg_mult_gen3 = 2.0
        elif normalized_move == "smelling-salt" and target.status == "par":
            doubledmg_mult_gen3 = 2.0
        elif normalized_move == "revenge" and getattr(user, '_took_damage_this_turn', False):
            doubledmg_mult_gen3 = 2.0
        elif normalized_move == "weather-ball" and weather and weather != "none":
            doubledmg_mult_gen3 = 2.0
        
        # Charge: 2x for Electric moves
        charge_mult = 2.0 if (mv.get("type", "Normal") == "Electric" and getattr(user, '_charge_active', False)) else 1.0
        
        # HH (Helping Hand): 1.5x in doubles
        hh_mult = 1.5 if getattr(user, '_helping_hand_active', False) else 1.0
        
        # Type effectiveness: Type1 × Type2
        type1_mult_gen3, type2_mult_gen3 = _get_type_effectiveness_gen1(mv.get("type", "Normal"), target, generation)
        if normalized_move in ["struggle", "future-sight", "beat-up", "doom-desire"]:
            type1_mult_gen3 = 1.0
            type2_mult_gen3 = 1.0
        
        mod = burn_mult * screen_mult * targets_mult * weather_mult * ff_mult * stockpile_mult * crit_mult_gen3 * doubledmg_mult_gen3 * charge_mult * hh_mult * stab(mv.get("type", "Normal"), user) * type1_mult_gen3 * type2_mult_gen3 * rand
    
    elif generation == 4:
        # Gen IV: Burn × Screen × Targets × Weather × FF × Critical × Item × First × random × STAB × Type1 × Type2 × SRF × EB × TL × Berry
        # Burn: 0.5 if burned and physical (no Guts)
        burn_mult_gen4 = 1.0
        if user.status == "brn" and move_category == "physical":
            if user_ability != "guts":
                burn_mult_gen4 = 0.5
        
        # Screen: 0.5 (or 2/3 in doubles, unless only one target)
        # (Already calculated above)
        
        # Targets: 0.75 in doubles if multi-target
        targets_mult_gen4 = 1.0
        # Would need battle state to check if doubles
        
        # FF (Flash Fire): 1.5 if activated
        ff_mult_gen4 = 1.5 if (user.flash_fire_active and mv.get("type", "Normal") == "Fire") else 1.0
        
        # Critical: 2x (or 3x with Sniper)
        crit_mult_gen4 = 2.0 if is_crit else 1.0
        if is_crit and user_ability == "sniper":
            crit_mult_gen4 = 3.0
        # Always 1 for Future Sight, Doom Desire
        if normalized_move in ["future-sight", "doom-desire"]:
            crit_mult_gen4 = 1.0
        
        # Item: Life Orb 1.3, Metronome (1 + n/10), or 1
        item_mult_gen4 = 1.0
        if user_item == "life-orb":
            item_mult_gen4 = 1.3
        elif user_item == "metronome" and hasattr(user, '_metronome_consecutive'):
            metronome_n = min(user._metronome_consecutive, 10)
            item_mult_gen4 = 1.0 + (metronome_n / 10.0)
        
        # First: 1.5 for Me First
        first_mult = 1.5 if getattr(user, '_me_first_active', False) else 1.0
        
        # Type effectiveness: Type1 × Type2
        type1_mult_gen4, type2_mult_gen4 = _get_type_effectiveness_gen1(mv.get("type", "Normal"), target, generation)
        if normalized_move in ["struggle", "future-sight", "beat-up", "doom-desire"]:
            type1_mult_gen4 = 1.0
            type2_mult_gen4 = 1.0
        
        # SRF (Solid Rock/Filter): 0.75 if super effective
        srf_mult = 1.0
        if type_mult >= 2.0 and target_ability in ["solid-rock", "filter"]:
            if user_ability not in ["mold-breaker", "turboblaze", "teravolt"]:
                srf_mult = 0.75
        
        # EB (Expert Belt): 1.2 if super effective
        eb_mult = 1.2 if (type_mult >= 2.0 and user_item == "expert-belt") else 1.0
        
        # TL (Tinted Lens): 2x if not very effective
        tl_mult = 2.0 if (type_mult < 1.0 and user_ability == "tinted-lens") else 1.0
        
        # Berry: 0.5 if super effective and holding type-resist berry
        berry_mult = 1.0
        if type_mult >= 2.0 and item_is_active(target):
            target_item_data = get_item_effect(normalize_item_name(target.item))
            if target_item_data.get("type_resist_berry") and target_item_data.get("resist_type") == move_type:
                berry_mult = 0.5
        elif mv.get("type", "Normal") == "Normal" and item_is_active(target):
            target_item_data = get_item_effect(normalize_item_name(target.item))
            if target_item_data.get("chilan_berry"):
                berry_mult = 0.5
        
        mod = burn_mult_gen4 * screen_mult * targets_mult_gen4 * weather_mult * ff_mult_gen4 * crit_mult_gen4 * item_mult_gen4 * first_mult * rand * stab(mv.get("type", "Normal"), user) * type1_mult_gen4 * type2_mult_gen4 * srf_mult * eb_mult * tl_mult * berry_mult
    
    else:
        # Gen V+: Targets × PB × Weather × GlaiveRush × Critical × random × STAB × Type × Burn × other × ZMove × TeraShield
        # Targets: 0.75 (0.5 in Battle Royals)
        targets_mult_gen5 = 1.0
        # Would need battle state to check if multi-target
        
        # PB (Parental Bond): 0.25 (0.5 in Gen VI) for second hit
        pb_mult = parental_bond_multiplier if parental_bond_multiplier != 1.0 else 1.0
        
        # GlaiveRush: 2x if target used Glaive Rush
        glaiverush_mult = 2.0 if getattr(target, '_glaive_rush_active', False) else 1.0
        
        # Critical: 1.5x (2x in Gen V)
        crit_mult_gen5 = 2.0 if (is_crit and generation == 5) else (1.5 if is_crit else 1.0)
        
        # Burn: 0.5 if burned and physical (no Guts), except Facade Gen VI+
        burn_mult_gen5 = 1.0
        if user.status == "brn" and move_category == "physical":
            if user_ability != "guts":
                if normalized_move != "facade" or generation < 6:
                    burn_mult_gen5 = 0.5
        
        # "other" includes all other modifiers (ability_mult, item_mult, etc.)
        # For Gen V+, "other" uses 4096-based calculation: start at 4096, multiply by each effect,
        # round to nearest integer (rounding up at 0.5), then divide by 4096
        other_base = 4096  # Start at 4096 for Gen V+ calculation
        
        user_item_gen5 = (user.item or "").lower().replace(" ", "-")
        move_type_gen5 = mv.get("type", "Normal")
        
        # Helper function for 4096-based rounding (rounding up at 0.5)
        def round_4096(value):
            """Round to nearest integer, rounding up at 0.5"""
            return int(value + 0.5) if value % 1 >= 0.5 else int(value)
        
        # === BEHEMOTH BLADE/BASH/DYNAMAX CANNON: 2x vs Dynamax ===
        if normalized_move in ["behemoth-blade", "behemoth-bash", "dynamax-cannon"]:
            if hasattr(target, 'dynamaxed') and target.dynamaxed:
                other_base = round_4096(other_base * 2.0)
                log.append(f"{move_name}'s power doubled against the Dynamax Pokémon!")
        
        # === COLLISION COURSE/ELECTRO DRIFT: 5461/4096 if super effective ===
        if normalized_move in ["collision-course", "electro-drift"]:
            if type_mult > 1.0:  # Super effective
                other_base = round_4096(other_base * (5461 / 4096))
                log.append(f"{move_name} surged with extra power!")
        
        # === MULTISCALE/SHADOW SHIELD: 0.5x at full HP ===
        # G-Max Fireball ignores ignorable abilities (Multiscale, Friend Guard, etc.)
        gmax_ignores_ignorable = getattr(user, '_gmax_ignores_ignorable_abilities', False)
        if not gmax_ignores_ignorable and target_ability_data.get("damage_reduction_full_hp") and target.hp == target.max_hp:
            other_base = round_4096(other_base * 0.5)
            log.append(f"{target.species}'s {target.ability or target_ability} reduced the damage!")
        
        # === FLUFFY: 0.5x (contact) or 2x (Fire) ===
        if not gmax_ignores_ignorable and target_ability == "fluffy":
            if is_contact:
                other_base = round_4096(other_base * 0.5)
                log.append(f"{target.species}'s Fluffy reduced contact damage!")
            if mv.get("type", "Normal") == "Fire":
                other_base = round_4096(other_base * 2.0)
                log.append(f"{target.species}'s Fluffy doubled Fire damage!")
        
        # === PUNK ROCK: 0.5x (sound) ===
        if not gmax_ignores_ignorable and target_ability == "punk-rock" and move_mechanics and move_mechanics.get('is_sound_move'):
            other_base = round_4096(other_base * 0.5)
            log.append(f"{target.species}'s Punk Rock reduced sound damage!")
        
        # === ICE SCALES: 0.5x (special) ===
        if not gmax_ignores_ignorable and target_ability == "ice-scales" and mv.get("category") == "special":
            other_base = round_4096(other_base * 0.5)
            log.append(f"{target.species}'s Ice Scales reduced special damage!")
        
        # === FRIEND GUARD: 0.75x (if ally has it) ===
        # Would need battle state to check for ally abilities
        # G-Max Fireball ignores this
        
        # === FILTER/PRISM ARMOR/SOLID ROCK: 0.75x (super effective) ===
        if not gmax_ignores_ignorable and type_mult >= 2.0 and "super_effective_reduction" in target_ability_data:
            if target_ability in ["filter", "prism-armor", "solid-rock"]:
                if user_ability not in ["mold-breaker", "turboblaze", "teravolt"]:
                    other_base = round_4096(other_base * 0.75)
                    log.append(f"{target.species}'s {target.ability or target_ability} weakened the attack!")
        
        # === NEUROFORCE: 1.25x (super effective) ===
        if type_mult >= 2.0 and user_ability == "neuroforce":
            other_base = round_4096(other_base * 1.25)
            log.append(f"{user.species}'s Neuroforce boosted {move_name}!")
        
        # === SNIPER: 1.5x (critical) ===
        if is_crit and user_ability == "sniper":
            other_base = round_4096(other_base * 1.5)
            log.append(f"{user.species}'s Sniper boosted the critical hit!")
        
        # === TINTED LENS: 2x (not very effective) ===
        if type_mult < 1.0 and user_ability == "tinted-lens":
            other_base = round_4096(other_base * 2.0)
            log.append(f"{user.species}'s Tinted Lens made the move hit normally!")
        
        # === TYPE-RESIST BERRIES: 0.5x ===
        if item_is_active(target):
            target_item_data = get_item_effect(normalize_item_name(target.item))
            if type_mult >= 2.0:
                if target_item_data.get("type_resist_berry") and target_item_data.get("resist_type") == move_type_gen5:
                    other_base = round_4096(other_base * 0.5)
            elif mv.get("type", "Normal") == "Normal" and target_item_data.get("chilan_berry"):
                other_base = round_4096(other_base * 0.5)
        
        # === EXPERT BELT: 4915/4096 (~1.2) if super effective ===
        if user_item_gen5 == "expert-belt" and type_mult >= 2.0:
            other_base = round_4096(other_base * (4915 / 4096))
            log.append(f"{user.species}'s Expert Belt boosted the attack!")
        
        # === LIFE ORB: 5324/4096 (~1.3) ===
        if user_item_gen5 == "life-orb":
            other_base = round_4096(other_base * (5324 / 4096))
            log.append(f"{user.species}'s Life Orb boosted the attack!")
        
        # === METRONOME: 1 + (819/4096 per consecutive use), max 2 ===
        if item_is_active(user):
            item_data_gen5 = get_item_effect(normalize_item_name(user.item))
            if item_data_gen5.get("consecutive_use_boost") and generation >= 4:
                if not hasattr(user, '_metronome_last_move'):
                    user._metronome_last_move = None
                    user._metronome_consecutive = 0
                same_move_met = (user._metronome_last_move == normalized_move)
                if same_move_met:
                    user._metronome_consecutive += 1
                else:
                    user._metronome_consecutive = 1
                    user._metronome_last_move = normalized_move
                
                if user._metronome_consecutive > 1:
                    # Gen 5+: 1 + (819/4096 * (consecutive - 1)), max 2
                    metronome_mult = 1.0 + ((819 / 4096) * (user._metronome_consecutive - 1))
                    metronome_mult = min(metronome_mult, 2.0)
                    other_base = round_4096(other_base * metronome_mult)
        
        # === TYPE-BOOSTING ITEMS, TYPE GEMS, AND OTHER ITEMS ===
        # (These should also be in "other" but using standard multipliers, not 4096-based)
        # For now, keep them in item_mult_gen5 and multiply into other_base
        item_mult_gen5 = 1.0
        if item_is_active(user):
            item_data_gen5 = get_item_effect(normalize_item_name(user.item))
            min_gen_item = item_data_gen5.get("min_gen", 1)
            max_gen_item = item_data_gen5.get("max_gen", 999)
            can_use_item = (generation >= min_gen_item) and (generation <= max_gen_item)
            
            if can_use_item and user_item_gen5 != "life-orb" and user_item_gen5 != "expert-belt":
                # Type-boosting items
                boost_type_item = item_data_gen5.get("boost_type")
                if boost_type_item and boost_type_item == move_type_gen5:
                    if item_data_gen5.get("type_enhancing"):
                        if generation <= 3:
                            item_mult_gen5 *= 1.1
                        else:
                            item_mult_gen5 *= 1.2
                    else:
                        item_mult_gen5 *= item_data_gen5.get("multiplier", 1.2)
                
                # All-moves multiplier
                all_moves_mult_item = item_data_gen5.get("all_moves_multiplier")
                if all_moves_mult_item:
                    holder_item = item_data_gen5.get("holder")
                    if not holder_item or user.species.lower() == (holder_item if isinstance(holder_item, str) else str(holder_item)).lower():
                        item_mult_gen5 *= all_moves_mult_item
                
                # Type Gems (Gen 5-9) - already handled in power calculation, but need to add to other
                gem_type_item = item_data_gen5.get("gem_type")
                if gem_type_item and gem_type_item == move_type_gen5:
                    mechanics_gem = get_move_mechanics(move_name)
                    ohko_moves_gem = ["fissure", "guillotine", "horn-drill", "sheer-cold"]
                    pledge_moves_gem = ["grass-pledge", "water-pledge", "fire-pledge"]
                    never_consume_gem = ["struggle"] + ohko_moves_gem + pledge_moves_gem
                    can_consume_gem_item = normalized_move not in never_consume_gem
                    
                    fixed_damage_moves_gem = [
                        "dragon-rage", "sonic-boom", "seismic-toss", "night-shade",
                        "counter", "mirror-coat", "metal-burst", "endeavor", "final-gambit",
                        "super-fang", "nature's-madness", "guardian-of-alola", "psywave"
                    ]
                    is_fixed_damage_gem = normalized_move in fixed_damage_moves_gem or (mechanics_gem and mechanics_gem.get('is_fixed_damage'))
                    is_present_gem = normalized_move == "present"
                    
                    if can_consume_gem_item and not is_fixed_damage_gem and not is_present_gem:
                        gem_mult_item = item_data_gen5.get("multiplier", 1.3)
                        if generation <= 5:
                            gem_mult_item = 1.5
                        item_mult_gen5 *= gem_mult_item
        
        # === ABILITY MULTIPLIERS (that aren't already in ability_mult) ===
        # Most abilities are already in ability_mult, but we need to ensure they're not double-counted
        # For Gen V+, ability_mult should only contain abilities that boost damage directly
        # (not ones that modify type_mult or are in "other")
        
        # === FINALIZE OTHER MULTIPLIER ===
        # Multiply by remaining item multipliers and ability multipliers
        # Then convert from 4096-based to final multiplier
        if item_mult_gen5 != 1.0:
            other_base = round_4096(other_base * item_mult_gen5)
        
        if ability_mult != 1.0:
            other_base = round_4096(other_base * ability_mult)
        
        if aura_mult != 1.0:
            other_base = round_4096(other_base * aura_mult)
        
        # Convert from 4096-based to final multiplier
        other_mult = other_base / 4096.0
        
        # ZMove: 0.25 if Z-Move/Max Move and target protected
        zmove_mult = 0.25 if (getattr(user, '_is_z_move', False) or getattr(user, '_is_max_move', False)) and getattr(target, '_protected', False) else 1.0
        
        # TeraShield: Only in Tera Raid Battles
        terashield_mult = 1.0
        
        mod = targets_mult_gen5 * pb_mult * weather_mult * glaiverush_mult * crit_mult_gen5 * rand * stab(mv.get("type", "Normal"), user) * type_mult * burn_mult_gen5 * other_mult * zmove_mult * terashield_mult
    
    # Apply screen modifiers (Reflect, Light Screen, Aurora Veil)
    # Infiltrator: Gen 5-6 (bypasses screens), Gen 7+ (also bypasses Substitute, Mist, Aurora Veil)
    skip_screen_multiplier = normalized_move == "brick-break"
    screen_mult = 1.0
    bypasses_screens = False
    
    # Check for Infiltrator
    user_ability_norm = normalize_ability_name(user.ability or "")
    user_ability_effects = ABILITY_EFFECTS.get(user_ability_norm, {})
    if user_ability_effects.get("ignores_screens_substitutes", False):
        generation = get_generation(field_effects=field_effects)
        # Gen 5+: Infiltrator bypasses Light Screen, Reflect, Safeguard
        # Gen 7+: Also bypasses Aurora Veil (checked below)
        bypasses_screens = True
    
    if target_side and not bypasses_screens and not skip_screen_multiplier:
        # Generation-specific screen multipliers
        gen_screen = get_generation(field_effects=field_effects)
        # Default multipliers
        half = 0.5
        third_exact_gen5 = 2703 / 4096
        third_exact_gen6p = 2732 / 4096
        # Choose multiplier based on generation (doubles/triples precise values in Gen 5+)
        mult_third = half if gen_screen <= 4 else (third_exact_gen5 if gen_screen == 5 else third_exact_gen6p)
        if target_side.aurora_veil:
            screen_mult *= mult_third if gen_screen >= 5 else half
        elif move_category == "physical" and target_side.reflect:
            screen_mult *= mult_third if gen_screen >= 5 else half
        elif move_category == "special" and target_side.light_screen:
            screen_mult *= mult_third if gen_screen >= 5 else half
    elif target_side and bypasses_screens:
        # Infiltrator present - check generation for Aurora Veil
        generation = get_generation(field_effects=field_effects)
        if target_side.aurora_veil and generation <= 6:
            # Gen 5-6: Infiltrator does NOT bypass Aurora Veil (it didn't exist yet anyway)
            screen_mult *= 0.5
    
    # Apply screen multipliers
    # For Gen III-IV, screens are already in the formula, so don't apply again
    # For Gen V+, screens are applied here (not in the formula)
    # For Gen I-II, screens don't exist
    if generation >= 5:
        mod *= screen_mult
    
    # === HELD ITEM DAMAGE MODIFIERS ===
    item_mult = 1.0
    user_item = (user.item or "").lower().replace(" ", "-")
    move_type = mv.get("type", "Normal")
    
    # Life Orb: Generation-specific multiplier (Gen 4: 1.3, Gen 5+: 5324/4096)
    # NOTE: For Gen 5+, Life Orb is already applied in the "other" multiplier above (line 6194)
    # Only apply here for Gen 4 and below
    if user_item == "life-orb":
        if generation == 4:
            item_mult *= 1.3
            log.append(f"{user.species}'s Life Orb boosted the attack!")
        elif generation <= 3:
            # Gen 1-3: Life Orb didn't exist, but handle for custom formats
            item_mult *= 1.3
            log.append(f"{user.species}'s Life Orb boosted the attack!")
        # Gen 5+: Already applied in "other" multiplier (line 6194), don't apply again!
    
    # Expert Belt: 1.2x boost on super effective moves
    # NOTE: For Gen 5+, Expert Belt is already applied in the "other" multiplier above (line 6190)
    # Only apply here for Gen 4 and below
    elif user_item == "expert-belt" and type_mult >= 2.0:
        if generation <= 4:
            item_mult *= 1.2
            log.append(f"{user.species}'s Expert Belt boosted the attack!")
        # Gen 5+: Already applied in "other" multiplier, don't apply again!
    
    # Muscle Band: 1.1x boost on physical moves
    elif user_item == "muscle-band" and move_category == "physical":
        item_mult *= 1.1
    
    # Wise Glasses: 1.1x boost on special moves
    elif user_item == "wise-glasses" and move_category == "special":
        item_mult *= 1.1
    
    # Type-boosting items (including ALL Plates): 1.2x boost for matching type
    # Check item data for boost_type instead of hardcoded list
    if item_is_active(user):
        item_data = get_item_effect(normalize_item_name(user.item))
        
        # Check generation restrictions
        min_gen = item_data.get("min_gen", 1)
        max_gen = item_data.get("max_gen", 999)  # Default to no max
        can_use = (generation >= min_gen) and (generation <= max_gen)
        
        if can_use:
            # Handle generation-specific effects (like Soul Dew Gen 7+)
            if "gen_specific" in item_data:
                gen_effects = item_data["gen_specific"]
                for gen_range, effects in gen_effects.items():
                    should_apply = False
                    
                    if "-" in gen_range:
                        # Range like "3-6"
                        start, end = gen_range.split("-")
                        if int(start) <= generation <= int(end):
                            should_apply = True
                    elif "+" in gen_range:
                        # Range like "7+"
                        start = gen_range.replace("+", "")
                        if generation >= int(start):
                            should_apply = True
                    
                    if should_apply and "boost_types" in effects:
                        # Check if move type matches any of the boost types
                        boost_types = effects["boost_types"]
                        if move_type in boost_types:
                            # Check species-specific holder
                            if "holder" in item_data:
                                holder_species = item_data["holder"]
                                species_match = False
                                if isinstance(holder_species, list):
                                    species_match = user.species.lower() in [s.lower() for s in holder_species]
                                else:
                                    species_match = user.species.lower() == holder_species.lower()
                                
                                if species_match:
                                    item_mult *= effects.get("multiplier", 1.2)
                                    log.append(f"{user.species}'s {user.item.replace('-', ' ').title()} boosted {move_name}!")
                        break
            
            # Standard type-boosting items (single type)
            boost_type = item_data.get("boost_type")
            if boost_type and boost_type == move_type:
                # Type-enhancing items have generation-specific multipliers
                # Gen 2-3: 10% boost (1.1x), Gen 4+: 20% boost (1.2x)
                if item_data.get("type_enhancing"):
                    # Dragon Fang handheld Gen 2 bug: no effect
                    if user_item == "dragon-fang" and generation == 2:
                        item_multiplier = 1.0
                    elif generation <= 3:
                        item_multiplier = 1.1  # 10% boost in Gen 2-3
                    else:
                        item_multiplier = 1.2  # 20% boost in Gen 4+
                else:
                    # Non-type-enhancing items (Plates, Memories) use fixed multiplier
                    item_multiplier = item_data.get("multiplier", 1.2)
                
                item_mult *= item_multiplier
                log.append(f"{user.species}'s {user.item.replace('-', ' ').title()} boosted {move_name}!")

            # All-moves multiplier (e.g., Ogerpon masks)
            all_moves_mult = item_data.get("all_moves_multiplier")
            if all_moves_mult:
                # If species-specific holder specified, enforce it
                holder = item_data.get("holder")
                if not holder or user.species.lower() == (holder if isinstance(holder, str) else str(holder)).lower():
                    item_mult *= all_moves_mult
            
            # === METRONOME: Boost consecutive move usage (Gen 4+) ===
            if item_data.get("consecutive_use_boost") and generation >= 4:
                # normalized_move already defined above
                
                # Initialize tracking if needed
                if not hasattr(user, '_metronome_last_move'):
                    user._metronome_last_move = None
                    user._metronome_consecutive = 0
                
                # Check if this is the same move as last time
                same_move = (user._metronome_last_move == normalized_move)
                
                if same_move:
                    # Increment consecutive counter
                    user._metronome_consecutive += 1
                else:
                    # Different move - reset counter and start tracking
                    user._metronome_consecutive = 1
                    user._metronome_last_move = normalized_move
                
                # Get generation-specific boost data
                gen_data = item_data.get("gen_specific", {})
                boost_mult = 1.0
                
                if generation == 4:
                    # Gen 4: 10% per turn, max 100% (11+ turns)
                    gen4_data = gen_data.get("4", {})
                    boost_per_turn = gen4_data.get("boost_per_turn", 0.1)
                    max_boost = gen4_data.get("max_boost", 2.0)
                    turns_to_max = gen4_data.get("turns_to_max", 11)
                    
                    if user._metronome_consecutive >= turns_to_max:
                        boost_mult = max_boost
                    else:
                        boost_mult = 1.0 + (boost_per_turn * (user._metronome_consecutive - 1))
                else:
                    # Gen 5+: Exact multipliers
                    gen5_data = gen_data.get("5+", {})
                    exact_mults = gen5_data.get("exact_multipliers", {})
                    max_boost = gen5_data.get("max_boost", 2.0)
                    turns_to_max = gen5_data.get("turns_to_max", 6)
                    
                    if user._metronome_consecutive >= turns_to_max:
                        boost_mult = max_boost
                    elif user._metronome_consecutive in exact_mults:
                        boost_mult = exact_mults[user._metronome_consecutive]
                    else:
                        boost_mult = 1.0  # First use: no boost
                
                if boost_mult > 1.0:
                    item_mult *= boost_mult
                    log.append(f"{user.species}'s Metronome boosted {move_name}! (x{user._metronome_consecutive})")
            
            # Multi-type boosting items (Orbs for Dialga/Palkia/Giratina)
            elif "boost_types" in item_data:
                boost_types = item_data["boost_types"]
                if move_type in boost_types:
                    # Check species-specific holder
                    if "holder" in item_data:
                        holder_species = item_data["holder"]
                        species_match = False
                        if isinstance(holder_species, list):
                            species_match = user.species.lower() in [s.lower() for s in holder_species]
                        else:
                            species_match = user.species.lower() == holder_species.lower()
                        
                        if species_match:
                            item_mult *= item_data.get("multiplier", 1.2)
                            log.append(f"{user.species}'s {user.item.replace('-', ' ').title()} boosted {move_name}!")
    
    # === TYPE GEMS (GEN 5-9) ===
    # Gems boost matching type moves by 50% (Gen 5) or 30% (Gen 6+)
    # Consumed after use, not consumed if move misses/fails or is a fixed-damage move
    if item_is_active(user):
        item_data = get_item_effect(normalize_item_name(user.item))
        gem_type = item_data.get("gem_type")
        
        if gem_type and gem_type == move_type:
            # Check if move can trigger gems
            mechanics = get_move_mechanics(move_name, battle_state_ctx)
            
            # Gems are NOT consumed by OHKO moves, Struggle, or Pledge moves
            ohko_moves = ["fissure", "guillotine", "horn-drill", "sheer-cold"]
            pledge_moves = ["grass-pledge", "water-pledge", "fire-pledge"]
            never_consume = ["struggle"] + ohko_moves + pledge_moves
            
            can_consume_gem = normalized_move not in never_consume
            
            # Fixed-damage moves consume gems but don't get boost
            fixed_damage_moves = [
                "dragon-rage", "sonic-boom", "seismic-toss", "night-shade",
                "counter", "mirror-coat", "metal-burst", "endeavor", "final-gambit",
                "super-fang", "nature's-madness", "guardian-of-alola", "psywave"
            ]
            is_fixed_damage = normalized_move in fixed_damage_moves or mechanics.get('is_fixed_damage')
            
            # Present heals sometimes but still consumes gem (healing amount unaffected)
            is_present = normalized_move == "present"
            
            if can_consume_gem and not is_fixed_damage and not is_present:
                # Apply gem boost based on generation
                gem_mult = item_data.get("multiplier", 1.3)  # Default Gen 6+ (1.3x)
                
                # Gen 5: 1.5x boost (50%)
                if generation <= 5:
                    gem_mult = 1.5
                
                item_mult *= gem_mult
                log.append(f"{user.species}'s {gem_type} Gem strengthened {move_name}!")
                
                # Mark gem for consumption (will be consumed after hit confirmation)
                user._gem_to_consume = user.item
            elif can_consume_gem and (is_fixed_damage or is_present):
                # Fixed-damage moves and Present consume gem without boost
                log.append(f"{user.species}'s {gem_type} Gem was consumed!")
                user._gem_to_consume = user.item
    
    # Item multipliers are already included in generation-specific formulas where applicable:
    # Gen I: No items in formula, apply item_mult here
    # Gen II: item_mult_gen2 (1.1 for type-enhancing) is in the formula, don't apply again
    # Gen III: No items in formula, apply item_mult here
    # Gen IV: item_mult_gen4 (Life Orb, Metronome) is in the formula, don't apply again
    # Gen V+: item_mult_gen5 is in the "other" multiplier, don't apply again
    if generation == 1 or generation == 3:
        mod *= item_mult
    
    # Apply Parental Bond multiplier (Gen 6: 0.5x, Gen 7+: 0.25x for second hit)
    # For Gen V+, PB is already included in the formula, so don't multiply again
    if parental_bond_multiplier != 1.0 and generation <= 4:
        mod *= parental_bond_multiplier
    
    # Don't force minimum 1 damage if type is immune (0x multiplier), unless pause Ring Target
    has_ring_target_dmg = False
    if item_is_active(target) and target.item:
        rt_item_dmg = normalize_item_name(target.item)
        rt_data_dmg = get_item_effect(rt_item_dmg)
        gen_rt_dmg = get_generation(field_effects=field_effects)
        if rt_data_dmg.get("removes_type_immunities") and gen_rt_dmg >= 5:
            has_ring_target_dmg = True
    # Ring Target converts 0x to 1x, so damage can apply
    if type_mult == 0 and has_ring_target_dmg:
        type_mult = 1.0  # Treat as neutral for damage calculation
    
    # === FINAL DAMAGE CALCULATION WITH GENERATION-SPECIFIC ROUNDING ===
    if type_mult == 0 and not has_ring_target_dmg:
        dmg = 0
    else:
        # Calculate damage: core * mod
        damage_float = core * mod
        
        # Generation-specific rounding
        if generation <= 4:
            # Gen 1-4: Integer truncation (floor)
            dmg = int(math.floor(damage_float))
        else:
            # Gen 5+: Round to nearest integer, rounding down at 0.5
            dmg = int(round(damage_float - 0.0001))  # Round down at 0.5
        
        # Minimum 1 damage (unless type immune)
        dmg = max(1, dmg)
        
        # === NULLSCAPE (Steel): 10% damage reduction against Steel types ===
        nullscape_type_steel = _get_nullscape_type(user, getattr(user, '_battle_state', None))
        if nullscape_type_steel == "Steel":
            target_types_steel = [t.strip().title() if t else None for t in target.types]
            if "Steel" in target_types_steel:
                dmg = int(dmg * 0.9)  # 10% reduction
                dmg = max(1, dmg)  # Minimum 1 damage

    if dmg > 0 and getattr(target, 'invulnerable', False) and getattr(target, 'invulnerable_type', None) == "underground":
        if normalized_move in ["earthquake", "magnitude"]:
            dmg *= 2
            log.append(f"The attack hit the underground {target.species} for massive damage!")
    
    # Sturdy - Gen 3+: OHKO move immunity; Gen 5+: Also survive OHKO with 1 HP if at full HP
    target_ability = normalize_ability_name(target.ability or "")
    generation = get_generation(field_effects=field_effects)
    
    # Check if attacker has Mold Breaker (ignores Sturdy)
    user_ability = normalize_ability_name(user.ability or "")
    has_mold_breaker = user_ability in ["mold-breaker", "turboblaze", "teravolt"]
    
    if target_ability == "sturdy" and not has_mold_breaker:
        # Gen 3+: Block OHKO moves
        if generation >= 3:
            mechanics = get_move_mechanics(move_name, battle_state_ctx)
            if mechanics and mechanics.get('is_ohko_move'):
                dmg = 0
                log.append(f"{target.species}'s Sturdy protected it from an OHKO move!")
        
        # Gen 5+: Survive with 1 HP if at full HP before the attack
        if generation >= 5 and target.hp == target.max_hp and dmg >= target.hp and dmg > 0:
            dmg = target.hp - 1
            log.append(f"{target.species} endured the hit with Sturdy!")

    # Note: Contact effects are handled in apply_move, not here, to avoid double-triggering
    # for multistrike moves and Parental Bond

    if mv.get("_stellar_tera_blast") and getattr(user, "terastallized", False) and getattr(user, "_tera_is_stellar", False):
        drop_msgs = modify_stages(user, {"atk": -1, "spa": -1}, caused_by_opponent=False, field_effects=field_effects)
        if drop_msgs:
            log.extend(drop_msgs)

    # For Max Moves, use the Max Move type instead of the base move type
    move_type_for_meta = max_move_type if max_move_type else mv.get("type", "Normal")
    meta = {"type": move_type_for_meta, "category": mv.get("category", "physical"), "priority": mv.get("priority", 0), "contact": mv.get("contact", True), "crit": is_crit}
    
    # Store on-hit reactive ability triggers in meta (to be processed in panel.py after HP is updated)
    meta["_on_hit_triggers"] = {
        "damage": dmg,
        "type": mv.get("type", "Normal"),
        "category": mv.get("category", "physical"),
        "is_contact": mv.get("contact", False),
        "is_crit": is_crit,
        "type_mult": type_mult
    }
    
    return dmg, meta, log

# ---------------- Field Effect Abilities (Ruin, Auras, etc.) ----------------

def get_field_ability_effects(all_mons: List[Mon]) -> Dict[str, Any]:
    """
    Calculate global field effects from all Pokémon's abilities.
    Returns dict with stat multipliers and other field effects.
    """
    effects = {
        "atk_mult": 1.0,
        "defn_mult": 1.0,
        "spa_mult": 1.0,
        "spd_mult": 1.0,
        "dark_move_mult": 1.0,
        "fairy_move_mult": 1.0,
        "neutralizing_gas": False,
        "abilities_suppressed": []
    }
    
    # Check for Neutralizing Gas first (suppresses other abilities)
    for mon in all_mons:
        if mon.hp > 0:
            ability = normalize_ability_name(mon.ability or "")
            if ability == "neutralizing-gas":
                effects["neutralizing_gas"] = True
                # Suppress all other abilities
                for other_mon in all_mons:
                    if other_mon != mon and other_mon.ability:
                        effects["abilities_suppressed"].append(normalize_ability_name(other_mon.ability))
                return effects  # Neutralizing Gas takes precedence
    
    # Check for Ruin abilities (stat debuffs). Effect does not stack if multiple have same ability.
    # Actual application is in get_effective_stat (only affects Pokémon other than the ability holder).
    for mon in all_mons:
        if mon.hp > 0:
            ability = normalize_ability_name(mon.ability or "")
            if ability == "tablets-of-ruin" and effects["atk_mult"] == 1.0:
                effects["atk_mult"] = 0.75
            elif ability == "sword-of-ruin" and effects["defn_mult"] == 1.0:
                effects["defn_mult"] = 0.75
            elif ability == "vessel-of-ruin" and effects["spa_mult"] == 1.0:
                effects["spa_mult"] = 0.75
            elif ability == "beads-of-ruin" and effects["spd_mult"] == 1.0:
                effects["spd_mult"] = 0.75
    
    # Check for Aura abilities (move power modifiers)
    aura_break_active = False
    for mon in all_mons:
        if mon.hp > 0:
            ability = normalize_ability_name(mon.ability or "")
            if ability == "aura-break":
                aura_break_active = True
                break
    
    for mon in all_mons:
        if mon.hp > 0:
            ability = normalize_ability_name(mon.ability or "")
            
            # Dark Aura - 1.33x Dark moves (reversed by Aura Break)
            if ability == "dark-aura":
                if aura_break_active:
                    effects["dark_move_mult"] *= 0.75  # Reversed
                else:
                    effects["dark_move_mult"] *= 1.33
            
            # Fairy Aura - 1.33x Fairy moves (reversed by Aura Break)
            elif ability == "fairy-aura":
                if aura_break_active:
                    effects["fairy_move_mult"] *= 0.75  # Reversed
                else:
                    effects["fairy_move_mult"] *= 1.33
    
    return effects

# ---------------- On-Hit Reactive Abilities ----------------

def apply_on_hit_reactive_abilities(attacker: Mon, defender: Mon, trigger_data: Dict[str, Any], battle_state: Any = None) -> List[str]:
    """
    Apply abilities that trigger when a Pokémon is hit or hits an opponent.
    Should be called AFTER damage is dealt and HP is updated.
    Returns list of messages.
    
    Args:
        attacker: The attacking Mon
        defender: The defending Mon
        trigger_data: Dict with damage, is_contact, etc.
        battle_state: Optional BattleState for checking all Pokemon (e.g., for Damp)
    """
    messages = []
    
    # Extract field_effects early to avoid UnboundLocalError
    field_effects = getattr(battle_state, 'field', None) if battle_state else None
    
    damage_dealt = trigger_data.get("damage", 0)
    move_type = trigger_data.get("type", "Normal")
    move_category = trigger_data.get("category", "physical")
    is_contact = trigger_data.get("is_contact", False)
    is_crit = trigger_data.get("is_crit", False)
    type_mult = trigger_data.get("type_mult", 1.0)
    
    defender_ability = normalize_ability_name(defender.ability or "")
    attacker_ability = normalize_ability_name(attacker.ability or "")
    
    # === DEFENDER ON-HIT ABILITIES ===
    if damage_dealt > 0 and defender.hp > 0:
        # Stamina - +1 Def when hit
        if defender_ability == "stamina":
            old_stage = defender.stages.get("defn", 0)
            if old_stage < 6:
                defender.stages["defn"] = old_stage + 1
                messages.append(f"{defender.species}'s Stamina raised its Defense!")
        
        # Thermal Exchange - +1 Atk when hit by Fire move, prevents burn (Gen 9+)
        if defender_ability == "thermal-exchange" and move_type == "Fire":
            generation = get_generation(battle_state=battle_state)
            if generation >= 9:
                old_stage = defender.stages.get("atk", 0)
                if old_stage < 6:
                    defender.stages["atk"] = old_stage + 1
                    messages.append(f"{defender.species}'s Thermal Exchange raised its Attack!")
        
        # Toxic Debris - Sets Toxic Spikes when hit by physical move
        if defender_ability == "toxic-debris" and move_category == "physical":
            # Only activate if not hitting substitute
            if not trigger_data.get("hit_substitute", False):
                # Check Toxic Spikes layers on attacker's side
                if battle_state and hasattr(battle_state, 'get_side_conditions'):
                    # Get attacker's side (opposite of defender)
                    attacker_side = battle_state.get_side_conditions(attacker)
                    toxic_spikes_layers = attacker_side.get('toxic_spikes', 0) if attacker_side else 0
                    
                    # Only set if less than 2 layers
                    if toxic_spikes_layers < 2:
                        if attacker_side is not None:
                            attacker_side['toxic_spikes'] = toxic_spikes_layers + 1
                            messages.append(f"{defender.species}'s Toxic Debris scattered Toxic Spikes!")
        
        # Weak Armor - -1 Def, +Spe when hit by physical move
        # Gen 5-6: +1 Spe, Gen 7+: +2 Spe
        if defender_ability == "weak-armor" and move_category == "physical":
            generation = get_generation(battle_state=battle_state)
            
            old_def = defender.stages.get("defn", 0)
            old_spe = defender.stages.get("spe", 0)
            defender.stages["defn"] = max(-6, old_def - 1)
            
            # Gen 5-6: +1 Spe, Gen 7+: +2 Spe
            spe_boost = 1 if generation <= 6 else 2
            defender.stages["spe"] = min(6, old_spe + spe_boost)
            
            messages.append(f"{defender.species}'s Weak Armor lowered its Defense!")
            if spe_boost == 2:
                messages.append(f"{defender.species}'s Weak Armor sharply raised its Speed!")
            else:
                messages.append(f"{defender.species}'s Weak Armor raised its Speed!")
        
        # Justified - +1 Atk when hit by Dark move
        if defender_ability == "justified" and move_type == "Dark":
            old_stage = defender.stages.get("atk", 0)
            if old_stage < 6:
                defender.stages["atk"] = old_stage + 1
                messages.append(f"{defender.species}'s Justified raised its Attack!")
        
        # Rattled - +1 Spe when hit by Bug/Ghost/Dark
        if defender_ability == "rattled" and move_type in ["Bug", "Ghost", "Dark"]:
            old_stage = defender.stages.get("spe", 0)
            if old_stage < 6:
                defender.stages["spe"] = old_stage + 1
                messages.append(f"{defender.species}'s Rattled raised its Speed!")
        
        # Stamina - +1 Def when hit by any attack (Gen 7+)
        if defender_ability == "stamina" and damage_dealt > 0:
            generation = get_generation(field_effects=field_effects) if hasattr(field_effects, 'generation') else get_generation(battle_state=battle_state)
            if generation >= 7:
                old_stage = defender.stages.get("defn", 0)
                if old_stage < 6:
                    defender.stages["defn"] = old_stage + 1
                    messages.append(f"{defender.species}'s Stamina raised its Defense!")
        
        # Rattled - Gen 8+: Also activates on Intimidate (handled in on_switch_in below)
        
        # Berserk - +1 SpA when HP drops below 50% from a damaging move
        # NOTE: This is handled in apply_move after damage is dealt, not here in reactive abilities
        # This ensures proper HP tracking (before/after) and Sheer Force interaction
        
        # Water Compaction - +2 Def when hit by Water
        if defender_ability == "water-compaction" and move_type == "Water":
            old_stage = defender.stages.get("defn", 0)
            new_stage = min(6, old_stage + 2)
            if new_stage != old_stage:
                defender.stages["defn"] = new_stage
                messages.append(f"{defender.species}'s Water Compaction sharply raised its Defense!")
        
        # Steam Engine - +6 Spe when hit by Fire/Water
        if defender_ability == "steam-engine" and move_type in ["Fire", "Water"]:
            old_stage = defender.stages.get("spe", 0)
            new_stage = min(6, old_stage + 6)
            if new_stage != old_stage:
                defender.stages["spe"] = new_stage
                messages.append(f"{defender.species}'s Steam Engine drastically raised its Speed!")
        
        # Cotton Down - Lower Speed of ALL other Pokémon when hit
        if defender_ability == "cotton-down":
            ability_name = defender.ability.replace("-", " ").title()
            messages.append(f"{defender.species}'s {ability_name}!")
            
            # In singles, only the attacker is affected
            # In doubles/triples, all Pokémon except the defender would be affected
            # For now (singles only), just lower attacker's Speed
            if attacker.hp > 0:
                old_stage = attacker.stages.get("spe", 0)
                if old_stage > -6:
                    attacker.stages["spe"] = old_stage - 1
                    messages.append(f"{attacker.species}'s Speed fell!")
        
        # Rage Gen I: Build Attack when hit (each hit increases Attack by 1 stage, up to +6)
        if hasattr(defender, '_rage_active') and defender._rage_active and damage_dealt > 0:
            gen_rage_hit = get_generation(field_effects=field_effects) if hasattr(field_effects, 'generation') else get_generation(battle_state=battle_state)
            if gen_rage_hit == 1:
                old_stage = defender.stages.get("atk", 0)
                if old_stage < 6:
                    defender.stages["atk"] = old_stage + 1
                    defender._rage_gen1_attack_builds = getattr(defender, '_rage_gen1_attack_builds', 0) + 1
                    messages.append(f"{defender.species}'s rage is building! Attack rose!")
        
        # Rage Gen II: Increase counter when hit (damage multiplier)
        if hasattr(defender, '_rage_counter') and damage_dealt > 0:
            gen_rage_counter = get_generation(field_effects=field_effects) if hasattr(field_effects, 'generation') else get_generation(battle_state=battle_state)
            if gen_rage_counter == 2:
                defender._rage_counter = min(255, getattr(defender, '_rage_counter', 1) + 1)
                messages.append(f"{defender.species}'s rage counter increased to {defender._rage_counter}!")
        
        # Rage Gen III+: Increase Attack when hit (each hit increases Attack by 1 stage)
        if hasattr(defender, '_rage_attack_boost_active') and defender._rage_attack_boost_active and damage_dealt > 0:
            gen_rage_boost = get_generation(field_effects=field_effects) if hasattr(field_effects, 'generation') else get_generation(battle_state=battle_state)
            if gen_rage_boost >= 3:
                old_stage = defender.stages.get("atk", 0)
                if old_stage < 6:
                    defender.stages["atk"] = old_stage + 1
                    messages.append(f"{defender.species}'s rage is building! Attack rose!")
        
        # Gooey / Tangling Hair - Lower attacker's Speed on contact
        if defender_ability in ["gooey", "tangling-hair"] and is_contact and attacker.hp > 0:
            old_stage = attacker.stages.get("spe", 0)
            if old_stage > -6:
                attacker.stages["spe"] = old_stage - 1
                ability_name = defender.ability.replace("-", " ").title()
                messages.append(f"{defender.species}'s {ability_name} lowered {attacker.species}'s Speed!")
        
        # Sand Spit - Set Sandstorm when hit by damaging move
        if defender_ability == "sand-spit" and damage_dealt > 0 and field_effects:
            current_weather = getattr(field_effects, 'weather', None)
            # Only activate if sandstorm is not already active
            if current_weather != "sandstorm":
                field_effects.weather = "sandstorm"
                generation = get_generation(field_effects=field_effects)

                # Default 5 turns (Gen 8+ where Sand Spit exists)
                weather_duration = 5
                
                # Check for Smooth Rock (extends to 8 turns)
                if defender.item:
                    item_data = get_item_effect(normalize_item_name(defender.item))
                    if item_data.get("extends_weather") == "sandstorm":
                        weather_duration = 8

                field_effects.weather_turns = weather_duration
                field_effects.sandstorm_damage_turns = 0
                
            messages.append(f"{defender.species}'s Sand Spit whipped up a sandstorm!")
        
        # Seed Sower - Set Grassy Terrain when hit by damaging move
        if defender_ability == "seed-sower" and damage_dealt > 0 and field_effects:
            current_terrain = getattr(field_effects, 'terrain', None)
            # Only activate if grassy terrain is not already active
            if current_terrain != "grassy":
                field_effects.terrain = "grassy"
                field_effects.terrain_turns = 5  # Default 5 turns
                
                # Check for Terrain Extender (extends to 8 turns)
                if defender.item:
                    item_data = get_item_effect(normalize_item_name(defender.item))
                    if item_data.get("extends_terrain"):
                        field_effects.terrain_turns = 8
                
                messages.append(f"{defender.species}'s Seed Sower covered the field with grass!")
        
        # Color Change - Change type to the type of the move that hit
        if defender_ability == "color-change":
            # Only change if type would actually change
            current_types = (defender.types[0], defender.types[1] if len(defender.types) > 1 else None)
            if move_type not in current_types:
                defender.types = (move_type, None)
                messages.append(f"{defender.species}'s Color Change changed it to {move_type} type!")
    
    # === ATTACKER ON-HIT ABILITIES ===
    # Toxic Chain - 30% chance to badly poison on non-status moves
    if attacker_ability == "toxic-chain" and damage_dealt > 0 and defender.hp > 0:
        # Check if it's a non-status move
        is_status_move = trigger_data.get("is_status_move", False)
        if not is_status_move:
            # 30% chance to badly poison
            if random.random() < 0.3:
                # Check if target can be badly poisoned
                can_poison, reason = can_inflict_status(defender, "tox", field_effects=None)
                if can_poison:
                    defender.status = "tox"
                    defender.toxic_counter = 1  # Start badly poisoned at 1/16
                    messages.append(f"{defender.species} was badly poisoned by {attacker.species}'s Toxic Chain!")
                elif reason:
                    messages.append(reason)
    
    # Helper function to check for Aroma Veil protection
        def has_aroma_veil_protection(mon):
            """Check if a Pokemon is protected by Aroma Veil"""
            ability = normalize_ability_name(mon.ability or "")
            ability_data = get_ability_effect(ability)
            return ability_data.get("team_mental_move_immunity", False)
        
        # Cursed Body - 30% chance to disable move that hit
        # Gen 5: Contact moves only
        # Gen 6+: ANY damaging move
        # Note: Activates even if defender is KOed, but NOT if hit through Substitute
        if defender_ability == "cursed-body":
            generation = get_generation(battle_state=battle_state)
            
            # Gen 5: Only contact moves, Gen 6+: Any damaging move
            can_activate = (generation >= 6) or (generation == 5 and is_contact)
            
            if can_activate and random.random() < 0.3:
                # Aroma Veil: Gen 7+ blocks Cursed Body
                blocked_by_aroma_veil = False
                if generation >= 7 and has_aroma_veil_protection(attacker):
                    blocked_by_aroma_veil = True
                    messages.append(f"{attacker.species}'s Aroma Veil prevents Cursed Body!")
                
                if not blocked_by_aroma_veil:
                    # Dynamax Pokemon are immune to Disable and Cursed Body
                    if not attacker.dynamaxed:
                        messages.append(f"{defender.species}'s Cursed Body disabled {attacker.species}'s move!")
                        # Set flag for panel to process
                        attacker._cursed_body_disabled = True
                    else:
                        messages.append(f"{attacker.species}'s Dynamax prevented Cursed Body!")
        
        # Cute Charm - Infatuate on contact (Gen 3: 33%, Gen 4+: 30%)
        if defender_ability == "cute-charm" and is_contact:
            if defender.gender and attacker.gender and defender.gender != attacker.gender:
                generation = get_generation(battle_state=battle_state)
                
                # Gen 3: 33% (1/3), Gen 4+: 30%
                charm_chance = 0.33 if generation == 3 else 0.3
                
                if random.random() < charm_chance:
                    # Aroma Veil: Gen 7+ blocks Cute Charm infatuation
                    blocked_by_aroma_veil = False
                    if generation >= 7 and has_aroma_veil_protection(attacker):
                        blocked_by_aroma_veil = True
                        messages.append(f"{attacker.species}'s Aroma Veil prevents infatuation!")
                    
                    if not blocked_by_aroma_veil:
                        attacker._infatuated = True
                        messages.append(f"{attacker.species} fell in love with {defender.species}!")
                        
                        # === DESTINY KNOT: Infatuates the infatuator (Gen 3+) ===
                        if item_is_active(defender) and defender.item:
                            def_item_dk = normalize_item_name(defender.item)
                            def_item_data_dk = get_item_effect(def_item_dk)
                            # Get generation from battle_state if available, otherwise default
                            gen_dk2 = 9  # Default
                            if battle_state and hasattr(battle_state, 'field'):
                                gen_dk2 = get_generation(field_effects=battle_state.field)
                            elif hasattr(defender, '_battle_context') and defender._battle_context:
                                gen_dk2 = get_generation(field_effects=defender._battle_context.get('field_effects'))
                            if def_item_data_dk.get("shares_infatuation") and gen_dk2 >= 3:
                                # Infatuate the attacker (source) as well
                                if attacker.gender and defender.gender and attacker.gender != defender.gender:
                                    defender._infatuated = True
                                    messages.append(f"{defender.species} also became infatuated due to its Destiny Knot!")
        
        # Electromorphosis - Get charged when hit by any damaging move
        if defender_ability == "electromorphosis":
            defender._charged = True
            ability_name = defender.ability.replace("-", " ").title()
            messages.append(f"{defender.species}'s {ability_name} charged it with power!")
        
        # Wind Power - Get charged when hit by wind moves
        if defender_ability == "wind-power":
            # List of wind moves (from image, excluding Sandstorm)
            wind_moves = [
                "aeroblast", "air-cutter", "bleakwind-storm", "blizzard", "fairy-wind",
                "gust", "heat-wave", "hurricane", "icy-wind", "petal-blizzard",
                "sandsear-storm", "springtide-storm", "tailwind", "twister",
                "whirlwind", "wildbolt-storm"
                # Note: Sandstorm is explicitly NOT included
            ]
            
            move_name_normalized = trigger_data.get("move_name", "").lower().replace(" ", "-")
            if move_name_normalized in wind_moves:
                defender._charged = True
                move_display = trigger_data.get("move_name", "wind move")
                messages.append(f"Being hit by {move_display} charged {defender.species} with power!")
    
    # === DEFENDER FAINTING ABILITIES ===
    if damage_dealt > 0 and defender.hp <= 0:
        # Innards Out - Deal damage = remaining HP before fainting
        if defender_ability == "innards-out":
            innards_damage = trigger_data.get("hp_before_damage", defender.max_hp) - damage_dealt
            if innards_damage > 0 and attacker.hp > 0:
                attacker.hp = max(0, attacker.hp - innards_damage)
                messages.append(f"{defender.species}'s Innards Out hurt {attacker.species}! (-{innards_damage} HP)")
                if attacker.hp <= 0:
                    messages.append(f"{attacker.species} fainted!")
        
        # Aftermath - 25% damage to attacker on contact KO
        # Blocked by Damp ability (Gen 7+)
        if defender_ability == "aftermath" and is_contact and attacker.hp > 0:
            # Check if any Pokemon on the field has Damp (blocks Aftermath)
            damp_active = False
            if battle_state:
                all_mons = []
                # Get all Pokemon from both teams
                if hasattr(battle_state, 'p1_party'):
                    all_mons.extend([m for m in battle_state.p1_party if m and m.hp > 0])
                if hasattr(battle_state, 'p2_party'):
                    all_mons.extend([m for m in battle_state.p2_party if m and m.hp > 0])
                
                # Check for Damp
                for mon in all_mons:
                    ability = normalize_ability_name(mon.ability or "")
                    if ability == "damp":
                        damp_active = True
                        messages.append(f"{mon.species}'s Damp prevents Aftermath!")
                        break
            
            if not damp_active:
                aftermath_damage = max(1, attacker.max_hp // 4)
                attacker.hp = max(0, attacker.hp - aftermath_damage)
                messages.append(f"{defender.species}'s Aftermath hurt {attacker.species}! (-{aftermath_damage} HP)")
                if attacker.hp <= 0:
                    messages.append(f"{attacker.species} fainted!")
        
        # Perish Body - Set Perish Song on both Pokémon on contact
        # Does NOT activate if:
            # - Attacker already has perish count
        # - Attacker has Protective Pads
        # - Attacker has Long Reach ability
        if defender_ability == "perish-body" and is_contact:
            # Check if attacker already has perish count
            already_has_perish = hasattr(attacker, 'perish_count') and attacker.perish_count is not None
            
            # Check for Protective Pads
            has_protective_pads = False
            if item_is_active(attacker):
                attacker_item_data = get_item_effect(normalize_item_name(attacker.item))
                has_protective_pads = attacker_item_data.get("no_contact_effects", False)
            
            # Check for Long Reach
            attacker_ability_norm = normalize_ability_name(attacker.ability or "")
            attacker_ability_data = get_ability_effect(attacker_ability_norm)
            has_long_reach = attacker_ability_data.get("contact_moves_dont_make_contact", False)
            
            # Only activate if none of the blocking conditions are met
            if not already_has_perish and not has_protective_pads and not has_long_reach:
                attacker.perish_count = 3
                # Initialize defender's perish count if it doesn't exist
                if not hasattr(defender, 'perish_count'):
                    defender.perish_count = None
                defender.perish_count = 3
                messages.append(f"{defender.species}'s Perish Body activated!")
                messages.append(f"Both Pokémon will faint in 3 turns!")
    
    # === ANGER POINT: Special case - can trigger even through Substitute in Gen 4 ===
    # Gen 4: Activates EVEN through Substitute
    # Gen 5+: Does NOT activate through Substitute
    if defender_ability == "anger-point" and is_crit and defender.hp > 0:
        generation = get_generation(battle_state=battle_state)
        
        substitute_blocked = trigger_data.get("substitute_blocked", False)
        
        # Gen 4: Always activate on crit (even through Substitute)
        # Gen 5+: Only activate if Substitute didn't block
        if generation <= 4 or not substitute_blocked:
            defender.stages["atk"] = 6
            messages.append(f"{defender.species}'s Anger Point maxed its Attack!")
    
    # === ATTACKER ON-HIT ABILITIES ===
    if damage_dealt > 0:
        # Pickpocket - Steal attacker's item on contact (if defender has no item)
        if defender_ability == "pickpocket" and is_contact and defender.hp > 0:
            if attacker.item and not defender.item:
                a_item_data = get_item_effect(normalize_item_name(attacker.item))
                if not a_item_data.get("unstealable"):
                    defender.item = attacker.item
                    attacker.item = None
                    messages.append(f"{defender.species} stole {attacker.species}'s {defender.item}!")
        
        # Magician - Steal target's item on hit (if attacker has no item)
        if attacker_ability == "magician" and attacker.hp > 0:
            if defender.item and not attacker.item:
                d_item_data = get_item_effect(normalize_item_name(defender.item))
                # Check if item is unstealable or is a Z-Crystal
                is_z_crystal_item = is_z_crystal(defender.item)
                if not d_item_data.get("unstealable") and not is_z_crystal_item:
                    attacker.item = defender.item
                    defender.item = None
                    messages.append(f"{attacker.species} stole {defender.species}'s {attacker.item}!")
    
    return messages

# ---------------- Public helpers your panel calls ----------------

async def build_party_from_db(user_id: int, *, set_level: int = 100, heal: bool = True) -> List[Mon]:
    """Load user's party and convert to Mon list with battle level override and optional full heal."""
    dtos = await get_party_for_engine(user_id)
    party = []
    for d in dtos[:6]:
        mon = build_mon(d, set_level=set_level, heal=heal)
        # Track owner for EXP outsider bonus
        try:
            mon._owner_id = user_id
        except Exception:
            pass
        party.append(mon)
    if not party:
        party = [build_mon({
            "species":"MissingNo","types":("Normal",None),
            "base":dict(hp=80,atk=80,defn=80,spa=80,spd=80,spe=80),
            "ivs":dict(hp=31,atk=31,defn=31,spa=31,spd=31,spe=31),
            "evs":dict(hp=0,atk=0,defn=0,spa=0,spd=0,spe=0),
            "level":100,"moves":["Tackle"],"is_shiny":False,"gender":None,"hp_now":80
        }, set_level=set_level, heal=heal)]
    return party

def _format_type_name(type_name: Optional[str]) -> Optional[str]:
    if not type_name:
        return None
    formatted = str(type_name).strip()
    if not formatted:
        return None
    formatted = formatted.replace("_", " ").replace("-", " ").title().replace(" ", "")
    return formatted

def _normalize_item_id(value: Optional[str]) -> str:
    if not value:
        return ""
    normalized = str(value).strip().lower().replace(" ", "-").replace("_", "-")
    return _MEGA_STONE_SYNONYMS.get(normalized, normalized)

def _normalize_stats_dict(data: Any) -> Dict[str, int]:
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            return {}
    if not isinstance(data, dict):
        return {}
    mapping = {
        "hp": "hp",
        "attack": "atk",
        "atk": "atk",
        "def": "defn",
        "defense": "defn",
        "special_attack": "spa",
        "sp_attack": "spa",
        "spatk": "spa",
        "spa": "spa",
        "special_defense": "spd",
        "sp_defense": "spd",
        "spdef": "spd",
        "spd": "spd",
        "speed": "spe",
        "spe": "spe"
    }
    out: Dict[str, int] = {}
    for key, value in data.items():
        key_norm = str(key).lower().replace(" ", "_").replace("-", "_")
        mapped = mapping.get(key_norm)
        if mapped:
            try:
                out[mapped] = int(value)
            except Exception:
                continue
    return out

def _parse_types(data: Any) -> Tuple[str, Optional[str]]:
    types: List[str] = []
    raw = data
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = [raw]
    if isinstance(raw, (list, tuple)):
        for entry in raw:
            t = _format_type_name(entry)
            if t and t not in types:
                types.append(t)
    elif raw:
        t = _format_type_name(raw)
        if t:
            types.append(t)
    if not types:
        return ("Normal", None)
    if len(types) == 1:
        return (types[0], None)
    return (types[0], types[1])

def _parse_abilities(data: Any) -> List[str]:
    abilities: List[str] = []
    raw = data
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = [raw]
    if isinstance(raw, dict):
        raw = [raw]
    if isinstance(raw, (list, tuple)):
        for entry in raw:
            if isinstance(entry, dict):
                name = entry.get("name") or entry.get("ability") or entry.get("id")
            else:
                name = entry
            if name:
                abilities.append(str(name).strip().lower().replace(" ", "-"))
    elif raw:
        abilities.append(str(raw).strip().lower().replace(" ", "-"))
    return abilities

def can_terastallize(mon: Optional[Mon]) -> Tuple[bool, Optional[str]]:
    if mon is None:
        return False, "There is no Pokémon to Terastallize."
    if mon.hp <= 0:
        return False, f"{mon.species} is fainted and can't Terastallize."
    if getattr(mon, "terastallized", False):
        return False, f"{mon.species} is already Terastallized."
    if getattr(mon, "tera_type", None) is None or not str(mon.tera_type).strip():
        return False, f"{mon.species} doesn't have a Tera Type."
    if getattr(mon, "dynamaxed", False):
        return False, f"{mon.species} can't Terastallize while Dynamaxed."
    if getattr(mon, "_transformed", False):
        return False, f"{mon.species} can't Terastallize while transformed."
    return True, None

def apply_terastallization(
    mon: Mon,
    *,
    state: Optional["BattleState"] = None,
    field_effects: Any = None
) -> Tuple[bool, str]:
    can_tera, reason = can_terastallize(mon)
    if not can_tera:
        return False, reason or "Cannot Terastallize."

    tera_type = _format_type_name(mon.tera_type)
    if not tera_type:
        return False, f"{mon.species} doesn't have a valid Tera Type."

    mon.tera_type = tera_type
    mon.terastallized = True
    mon._tera_original_types = tuple(mon._tera_original_types or mon.types)
    mon._tera_boosted_types.clear()
    mon._tera_is_stellar = (tera_type.lower() == "stellar")

    # Preserve ability before overrides
    if mon._tera_previous_ability is None:
        mon._tera_previous_ability = mon.ability

    messages: List[str] = []

    # Handle species-specific behaviour (Ogerpon masks, Terapagos)
    species_lower = mon.species.lower()
    form_lower = (mon.form or "").lower()

    if "ogerpon" in species_lower:
        ogerpon_map = {
            "teal-mask": ("embody-aspect-teal", {"spe": 1}, "Speed"),
            "wellspring-mask": ("embody-aspect-wellspring", {"spa": 1}, "Sp. Atk"),
            "hearthflame-mask": ("embody-aspect-hearthflame", {"atk": 1}, "Attack"),
            "cornerstone-mask": ("embody-aspect-cornerstone", {"defn": 1}, "Defense"),
        }
        ability_entry = ogerpon_map.get(form_lower)
        if ability_entry:
            ability_id, stat_delta, stat_name = ability_entry
            mon.ability = ability_id
            stat_msgs = modify_stages(mon, stat_delta, caused_by_opponent=False, field_effects=field_effects)
            messages.extend(stat_msgs)
            messages.append(f"{mon.species}'s Embody Aspect raised its {stat_name}!")
        if not mon._tera_sprite_form:
            mon._tera_sprite_form = mon.form
        if form_lower:
            mon.form = f"{form_lower}-terastal"

    if "terapagos" in species_lower:
        if not mon._tera_sprite_form:
            mon._tera_sprite_form = mon.form
        mon._tera_boost_unlimited = True
        if tera_type.lower() == "stellar":
            mon._tera_is_stellar = True
            mon.form = "stellar-form"

    # Update typing
    if mon._tera_is_stellar:
        # Stellar keeps defensive typing but gains special offensive behaviour
        mon._tera_boosted_types.clear()
    else:
        mon.types = (tera_type, None)

    message = f"{mon.species} Terastallized into the {tera_type} type!"
    if mon._tera_is_stellar:
        message = f"{mon.species} became Stellar and radiates cosmic energy!"

    if messages:
        message += " " + " ".join(messages)

    # Track once-per-type boosts
    mon._tera_boosted_types.clear()

    if state and hasattr(state, "_pending_weather_messages"):
        state._pending_weather_messages.append(message)

    # Reset Choice lock does NOT occur for Terastallization (intentional)
    return True, message

def revert_terastallization(mon: Mon) -> None:
    if not getattr(mon, "terastallized", False):
        return
    mon.terastallized = False
    if mon._tera_original_types:
        restored = [
            t.strip().title() if isinstance(t, str) else t
            for t in mon._tera_original_types
        ]
        if restored:
            if len(restored) == 1:
                mon.types = (restored[0], None)
            else:
                mon.types = (restored[0], restored[1])
    if mon._tera_previous_ability is not None:
        mon.ability = mon._tera_previous_ability
    if mon._tera_sprite_form is not None:
        mon.form = mon._tera_sprite_form
    mon._tera_boosted_types.clear()

def _resolve_mega_variant(mon: Mon, generation: int) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[str]]:
    if not mon.mega_evolutions:
        return None, None, "This Pokémon cannot Mega Evolve."
    item_norm = _normalize_item_id(mon.item)
    moves_norm = [str(m).lower().replace(" ", "-") for m in (mon.moves or [])]
    rayquaza_moves = {"dragon-ascent"}
    candidate_reason: Optional[str] = None
    species_lower = (mon.species or "").strip().lower()
    
    # Check item data to see if it's a mega stone
    item_data = None
    if mon.item:
        item_data = get_item_effect(normalize_item_name(mon.item))
    
    for form, info in mon.mega_evolutions.items():
        data = info or {}
        introduced = data.get("introduced_in")
        if introduced and generation < int(introduced):
            continue
        stone_norm = _normalize_item_id(data.get("mega_stone"))
        # Rayquaza uses Meteorite instead of a mega stone
        if species_lower == "rayquaza":
            # Check if holding Meteorite
            if item_norm == "meteorite":
                # Rayquaza needs Dragon Ascent to mega evolve
                if any(move in moves_norm for move in rayquaza_moves):
                    if not item_norm.endswith("_z"):
                        return form, data, None
                    candidate_reason = "Rayquaza cannot Mega Evolve while holding a Z-Crystal."
                else:
                    candidate_reason = "Rayquaza must know Dragon Ascent to Mega Evolve."
            else:
                candidate_reason = "Rayquaza must hold Meteorite and know Dragon Ascent to Mega Evolve."
            continue  # Skip normal mega stone check for Rayquaza
        if stone_norm:
            # Check if item matches the stone name directly
            if stone_norm == item_norm:
                return form, data, None
            # Check if item is a mega stone for this species (handles charizardite-x/y, etc.)
            if item_data and item_data.get("mega_stone"):
                item_mega_stone = _normalize_item_id(item_data.get("mega_stone"))
                item_form = item_data.get("form")
                # Check if the mega stone matches and form matches (if specified)
                if item_mega_stone == stone_norm:
                    # If form is specified in item data, check if it matches the form key
                    if item_form is None or item_form.lower() == form.lower() or form.lower().endswith(f"-{item_form.lower()}"):
                        return form, data, None
            display_name = _MEGA_STONE_DISPLAY_OVERRIDES.get(stone_norm, stone_norm.replace('-', ' ').title())
            candidate_reason = f"Equip {display_name} to Mega Evolve."
        else:
            # Rayquaza-style Mega
            if any(move in moves_norm for move in rayquaza_moves):
                if not item_norm.endswith("_z"):
                    return form, data, None
                candidate_reason = "Rayquaza cannot Mega Evolve while holding a Z-Crystal."
            else:
                candidate_reason = "Rayquaza must know Dragon Ascent to Mega Evolve."
    if candidate_reason is None:
        candidate_reason = "No compatible Mega Stone held."
    return None, None, candidate_reason

def can_mega_evolve(
    mon: Optional[Mon],
    *,
    state: Optional["BattleState"] = None,
    generation: Optional[int] = None
) -> Tuple[bool, Optional[str], Optional[str]]:
    if mon is None:
        return False, "There is no Pokémon to Mega Evolve.", None
    if mon.hp <= 0:
        return False, f"{mon.species} has fainted and can't Mega Evolve.", None
    battle_gen = generation if generation is not None else getattr(state, "gen", 9)
    if battle_gen < 6:
        return False, "Mega Evolution is not available in this generation.", None
    if battle_gen > 7:
        return False, "Mega Evolution is not allowed in this generation.", None
    if getattr(mon, "mega_evolved", False):
        return False, f"{mon.species} is already Mega Evolved.", None
    if not getattr(mon, "mega_evolutions", None):
        return False, f"{mon.species} cannot Mega Evolve.", None
    if getattr(mon, "dynamaxed", False):
        return False, f"{mon.species} can't Mega Evolve while Dynamaxed.", None
    if getattr(mon, "terastallized", False):
        return False, f"{mon.species} can't Mega Evolve while Terastallized.", None
    if getattr(mon, "_transformed", False):
        return False, f"{mon.species} can't Mega Evolve while transformed.", None
    if getattr(mon, '_sky_drop_cannot_move', False) or getattr(mon, '_sky_drop_lifted', False):
        return False, f"{mon.species} can't Mega Evolve while being held by Sky Drop!", None
    variant, info, reason = _resolve_mega_variant(mon, battle_gen)
    if not variant:
        return False, reason, None
    return True, None, variant

def apply_mega_evolution(
    mon: Mon,
    variant: str,
    *,
    state: Optional["BattleState"] = None,
    field_effects: Any = None,
    generation: Optional[int] = None
) -> str:
    info = mon.mega_evolutions.get(variant, {})
    if not info:
        return f"{mon.species} cannot mega evolve into {variant}!"
    battle_gen = generation if generation is not None else getattr(state, "gen", 9)
    
    # Save current state before applying mega evolution (in case Pokemon was transformed/changed)
    if not mon._mega_original_species:
        mon._mega_original_species = mon.species
    if not mon._mega_original_types:
        mon._mega_original_types = tuple(mon.types)
    if mon._mega_original_ability is None:
        mon._mega_original_ability = mon.ability
    if not mon._mega_original_stats:
        mon._mega_original_stats = dict(mon.stats)
    if not mon._mega_original_base:
        mon._mega_original_base = dict(mon.base)
    if mon._mega_original_form is None:
        mon._mega_original_form = mon.form
    if mon._mega_original_weight is None:
        mon._mega_original_weight = mon.weight_kg
    
    base_name = mon._mega_original_species
    old_speed = mon.stats.get("spe")
    if mon._mega_original_speed is None:
        mon._mega_original_speed = old_speed
    
    stats_override = _normalize_stats_dict(info.get("stats"))
    types_override = _parse_types(info.get("types")) if info.get("types") else None
    ability_list = _parse_abilities(info.get("abilities")) if info.get("abilities") else []
    
    # Set ability FIRST so it's available when recalculating stats (for abilities that affect stat calculation)
    if ability_list:
        mon.ability = ability_list[0]
        # Clear any ability suppression flags when mega evolving
        if hasattr(mon, '_ability_suppressed'):
            mon._ability_suppressed = False
        if hasattr(mon, 'ability_suppressed'):
            mon.ability_suppressed = False
    
    if stats_override:
        # IMPORTANT: Preserve stat stages (boosts/drops) - they are stored in mon.stages and should NOT be reset
        # Only update base stats and recalculate raw stats (before stage modifiers)
        mon.base.update({k: mon.base.get(k, v) if k == "hp" else v for k, v in stats_override.items()})
        nature_mods = NATURES.get(mon.nature_name or "", _nat(neu=True))
        # Recalculate non-HP raw stats (base stats before stage modifiers)
        # Stat stages in mon.stages are preserved and will be applied when calculating effective stats via get_effective_stat
        # The ability (like Pure Power) will be applied in get_effective_stat when calculating damage
        mon.stats["atk"] = _calc_stat(mon.base.get("atk", 0), mon.ivs.get("atk", 0), mon.evs.get("atk", 0), mon.level, nature_mods["atk"])
        mon.stats["defn"] = _calc_stat(mon.base.get("defn", 0), mon.ivs.get("defn", 0), mon.evs.get("defn", 0), mon.level, nature_mods["defn"])
        mon.stats["spa"] = _calc_stat(mon.base.get("spa", 0), mon.ivs.get("spa", 0), mon.evs.get("spa", 0), mon.level, nature_mods["spa"])
        mon.stats["spd"] = _calc_stat(mon.base.get("spd", 0), mon.ivs.get("spd", 0), mon.evs.get("spd", 0), mon.level, nature_mods["spd"])
        mon.stats["spe"] = _calc_stat(mon.base.get("spe", 0), mon.ivs.get("spe", 0), mon.evs.get("spe", 0), mon.level, nature_mods["spe"])
    if types_override:
        mon.types = types_override
    form_key = info.get("form_key") or variant
    mon.form = form_key
    mon.species = variant
    mon.mega_evolved = True
    mon.mega_variant = variant
    if old_speed is not None:
        mon._mega_speed_override = old_speed
    mon._mega_speed_applied = battle_gen >= 7 or old_speed is None
    # Format the mega species name (e.g., "gengar-mega" -> "Gengar Mega")
    mega_name = variant.replace("-", " ").title()
    base_title = str(base_name).replace("-", " ").title()
    message = f"{base_title} Mega Evolved into {mega_name}!"
    # Don't add to _pending_weather_messages - it's already being added to log directly in panel.py
    # if state and hasattr(state, "_pending_weather_messages"):
    #     state._pending_weather_messages.append(message)
    return message

def revert_mega_evolution(mon: Mon) -> None:
    if not getattr(mon, "mega_evolved", False):
        return
    mon.mega_evolved = False
    mon.mega_variant = None
    if mon._mega_original_species:
        mon.species = mon._mega_original_species
    if mon._mega_original_types:
        restored_types = tuple(t for t in mon._mega_original_types)
        mon.types = restored_types
    if mon._mega_original_ability is not None:
        mon.ability = mon._mega_original_ability
    if mon._mega_original_base:
        mon.base.update(mon._mega_original_base)
    if mon._mega_original_stats:
        mon.stats.update(mon._mega_original_stats)
    if mon._mega_original_form is not None:
        mon.form = mon._mega_original_form
    if mon._mega_original_weight is not None:
        mon.weight_kg = mon._mega_original_weight
    mon._mega_speed_override = None
    mon._mega_speed_applied = False
    # IMPORTANT: Preserve stat stages (boosts/drops) - they are NOT reverted
    # Stat stages persist through mega evolution and reversion
def action_priority(move_name: Optional[str], mon: Optional['Mon'] = None, field_effects: Any = None, battle_state: Any = None) -> int:
    """
    Read priority for move-based actions.
    Accounts for ability-based priority boosts (Prankster, Gale Wings, Triage, Quick Draw, Stall, etc.).
    Pass battle_state when available to use move cache and avoid DB round-trips.
    """
    if not move_name:
        return 0
    gen = getattr(battle_state, "gen", None) if battle_state else None
    mv = load_move(move_name, generation=gen, battle_state=battle_state)
    if not mv:
        return 0
    
    base_priority = int(mv.get("priority", 0))
    
    # Generation-specific priority for Protect/Detect and other protection moves
    move_lower = normalized_move = move_name.lower().replace(" ", "-")
    protection_moves = ["protect", "detect", "spiky-shield", "baneful-bunker", "kings-shield", "obstruct", "winters-aegis", "silk-trap", "burning-bulwark"]
    if move_lower in protection_moves and field_effects:
        generation = get_generation(field_effects=field_effects)
        # Gen II-IV: +3 priority, Gen V+: +4 priority
        if generation <= 4:
            base_priority = 3
        else:
            base_priority = 4

    if move_lower == "endure" and field_effects:
        generation = get_generation(field_effects=field_effects)
        if generation == 2:
            base_priority = 2
        elif generation in [3, 4]:
            base_priority = 3
        else:
            base_priority = 4

    if move_lower == "fake-out" and field_effects:
        generation = get_generation(field_effects=field_effects)
        if generation <= 4:
            base_priority = 1
        else:
            base_priority = 3
    
    # Extreme Speed: Gen II-IV: +1 priority, Gen V+: +2 priority
    if move_lower == "extreme-speed" and field_effects:
        generation = get_generation(field_effects=field_effects)
        if generation <= 4:
            base_priority = 1
        else:
            base_priority = 2
    
    # Follow Me: Gen III-IV: +3 priority, Gen VI+: +2 priority
    if move_lower == "follow-me" and field_effects:
        generation = get_generation(field_effects=field_effects)
        if generation <= 4:
            base_priority = 3
        else:
            base_priority = 2
    
    if move_lower == "ally-switch" and field_effects:
        generation = get_generation(field_effects=field_effects)
        if generation <= 6:
            base_priority = 1
        else:
            base_priority = 2

    if move_lower == "revenge" and field_effects:
        generation = get_generation(field_effects=field_effects)
        base_priority = -4 if generation <= 3 else 0
    
    # Check for priority-modifying abilities
    if mon and mon.ability:
        ability = normalize_ability_name(mon.ability)
        ability_data = get_ability_effect(ability)
        
        # Stall - Always move last (set to -5 priority)
        if ability == "stall":
            return -5
        
        # Quick Draw - 30% chance to get +1 priority
        if ability == "quick-draw":
            if random.random() < 0.3:
                base_priority += 1
        
        # Prankster - +1 priority to status moves
        if ability == "prankster" and mv.get("category") == "status":
            base_priority += 1
        
        # Gale Wings - +1 priority to Flying moves (Gen 7+: only at full HP)
        if ability == "gale-wings" and mv.get("type") == "Flying":
            if mon.hp >= mon.max_hp:  # Gen 7+ restriction
                base_priority += 1
        
        # Triage - +3 priority to healing/draining moves
        if ability == "triage":
            # Use move_lower which is already defined above
            
            # Comprehensive list of HP-restoring moves affected by Triage
            triage_moves = [
                # Draining moves (deal damage + restore HP)
                "absorb", "bitter-blade", "drain-punch", "draining-kiss", "dream-eater",
                "giga-drain", "horn-leech", "leech-life", "matcha-gotcha", "mega-drain",
                "oblivion-wing", "parabolic-charge",
                # Status moves that restore HP
                "floral-healing", "heal-order", "heal-pulse", "healing-wish", "lunar-blessing",
                "lunar-dance", "milk-drink", "moonlight", "morning-sun", "purify", "recover",
                "rest", "roost", "shore-up", "slack-off", "soft-boiled", "strength-sap",
                "swallow", "synthesis", "wish"
            ]
            
            # Excluded moves (do NOT get Triage boost)
            excluded_moves = [
                "aqua-ring", "grassy-terrain", "ingrain", "leech-seed", "pain-split",
                "present", "pollen-puff", "revival-blessing"  # Revival Blessing revives, not direct HP restore
            ]
            
            if move_lower in triage_moves and move_lower not in excluded_moves:
                base_priority += 3
        
        # Mycelium Might - Status moves move last but ignore abilities
        if ability == "mycelium-might" and mv.get("category") == "status":
            base_priority = -1  # Moves after most things
            # Ignores abilities flag (handled separately in damage/effect code)
        
        # Check for generic priority_boost in ability data
        priority_boost = ability_data.get("priority_boost", 0)
        if priority_boost and ability not in ["prankster", "gale-wings", "triage", "stall", "quick-draw", "mycelium-might"]:
            should_boost = False
            
            # Move category check
            if ability_data.get("move_category") == mv.get("category"):
                should_boost = True
            
            # Move type check
            if ability_data.get("move_type") == mv.get("type"):
                # Check HP condition if required
                if ability_data.get("full_hp_only"):
                    should_boost = (mon.hp >= mon.max_hp)
                else:
                    should_boost = True
            
            if should_boost:
                base_priority += priority_boost
    
    # Item-based priority effects (Quick Claw, Lagging Tail)
    if mon and mon.item:
        item_norm = normalize_item_name(mon.item)
        item_data = get_item_effect(item_norm)
        # Lagging Tail: moves last in bracket
        if item_data.get("moves_last"):
            return -5
        # Quick Claw: chance to go first in bracket
        if item_norm == "quick-claw":
            gen = get_generation(field_effects=field_effects)
            chance = 0.2
            if gen == 2:
                chance = 60/256
            if random.random() < chance:
                base_priority += 1
    return base_priority

def is_priority_blocked(
    attacker: Mon,
    defender: Mon,
    move_name: str,
    move_priority: int,
    defender_side: Optional[Any] = None,
    field_effects: Optional[Any] = None
) -> Tuple[bool, Optional[str]]:
    """
    Check if priority moves are blocked by defender's ability or terrain.
    Returns (is_blocked, message).
    """
    if move_priority <= 0:
        return False, None
    
    move_name = move_name or ""
    move_norm = move_name.lower().replace(" ", "-")
    defender_ability = normalize_ability_name(defender.ability or "")
    
    # Psychic Terrain: Blocks priority moves for grounded Pokémon
    if field_effects:
        terrain = getattr(field_effects, 'terrain', None)
        if terrain == "psychic":
            # Check if attacker is grounded
            if is_grounded(attacker, field_gravity=getattr(field_effects, 'gravity', False)):
                return True, "Psychic Terrain prevents priority moves!"
    
    # Queenly Majesty, Dazzling, Armor Tail - Block all priority moves
    if defender_ability in ["queenly-majesty", "dazzling", "armor-tail"]:
        ability_name = defender.ability.replace("-", " ").title()
        return True, f"{defender.species}'s {ability_name} protected it from the priority move!"

    # Determine defending side for Quick Guard
    if defender_side is None:
        battle_state = getattr(defender, '_battle_state', None)
        if battle_state:
            try:
                active_p1 = battle_state._active(battle_state.p1_id)
                defender_side = battle_state.p1_side if defender is active_p1 else battle_state.p2_side
            except Exception:
                defender_side = None
    
    if defender_side and getattr(defender_side, '_quick_guard_active', False):
        generation = get_generation(field_effects=field_effects, battle_state=getattr(defender, '_battle_state', None)) if (field_effects or getattr(defender, '_battle_state', None)) else 9
        attacker_ability = normalize_ability_name(attacker.ability or "")
        attacker_ability_data = get_ability_effect(attacker_ability)
        move_data = load_move(move_name) or {}
        is_contact_move = makes_contact(move_name)  # Use makes_contact function for accurate detection
        damage_class = (move_data.get("damage_class") or move_data.get("category") or "").lower()
        base_priority = int(move_data.get("priority", 0) or 0)
        # Gen V: Prankster status priority bypasses Quick Guard if priority added
        if generation == 5 and attacker_ability == "prankster" and damage_class == "status" and move_priority > base_priority:
            return False, None
        # Unseen Fist-style contact bypass
        if attacker_ability_data.get("contact_ignores_protect") and is_contact_move:
            return False, None
        return True, "Quick Guard protected the team from the priority move!"
    
    return False, None

def is_explosion_blocked(all_mons: List[Mon], move_name: str) -> Tuple[bool, Optional[str]]:
    """
    Check if Explosion/Self-Destruct is blocked by Damp ability.
    Returns (is_blocked, message).
    """
    explosion_moves = ["explosion", "self-destruct", "selfdestruct", "mind-blown", "misty-explosion"]
    normalized_move = move_name.lower().replace(" ", "-")
    
    if normalized_move not in explosion_moves:
        return False, None
    
    # Check if any Pokémon on field has Damp
    for mon in all_mons:
        if mon and mon.hp > 0:
            if getattr(mon, '_ability_suppressed', False):
                continue
            ability = normalize_ability_name(mon.ability or "")
            if ability == "damp":
                return True, f"{mon.species}'s Damp prevents {move_name}!"
    
    return False, None

def speed_value(mon: Mon, side_effects: Any = None, field_effects: Any = None) -> int:
    """Expose speed (for panel ordering). Accounts for Tailwind, weather abilities, paralysis, items, etc."""
    return _speed_value(mon, side_effects, field_effects)

def can_switch_out(mon: Mon, opponent: Mon, force_switch: bool = False, field_effects: Any = None, is_pivot_move: bool = False, bypass_shadow_tag: bool = False, battle_state: Any = None) -> Tuple[bool, Optional[str]]:
    """
    Check if a Pokémon can switch out based on trapping abilities.
    Returns (can_switch, message).
    force_switch=True bypasses trapping (e.g., Roar, Whirlwind).
    is_pivot_move=True bypasses trapping (e.g., U-turn, Volt Switch, Baton Pass).
    field_effects=Optional for generation-aware checks (Arena Trap Ghost immunity).
    """
    # Dynamax Pokemon cannot be forced to switch (Roar, Whirlwind, Circle Throw, Dragon Tail)
    if force_switch and mon.dynamaxed:
        return False, f"{mon.species}'s Dynamax prevents it from being forced out!"
    
    # Fairy Lock prevents voluntary switching for one turn (non-Ghost Pokémon)
    if field_effects and getattr(field_effects, 'fairy_lock_active', False) and not force_switch:
        mon_types = [t.strip().title() for t in mon.types if t]
        if "Ghost" not in mon_types:
            return False, f"{mon.species} is locked in by Fairy energy!"
    
    # Check own ability that prevents forced switches (Suction Cups)
    mon_ability = normalize_ability_name(mon.ability or "")
    if mon_ability == "suction-cups" and force_switch:
        # Suction Cups prevents forced switching (Roar, Dragon Tail, etc.)
        # But allows voluntary switching
        return False, f"{mon.species}'s Suction Cups prevents forced switching!"
    
    # Gen 3+: Bide prevents the user from switching out voluntarily
    if getattr(mon, '_bide_active', False):
        gen_bide = get_generation(field_effects=field_effects)
        if gen_bide >= 3:
            return False, f"{mon.species} can't switch out while storing energy!"
    
    # Rampage moves (Thrash, Outrage, Petal Dance, etc.) prevent switching
    if getattr(mon, 'rampage_move', None) and getattr(mon, 'rampage_turns_remaining', 0) > 0:
        rampage_move_name = (mon.rampage_move or "move").replace("-", " ").title()
        return False, f"{mon.species} can't switch out while locked into {rampage_move_name}!"
    
    # Rollout prevents switching
    if getattr(mon, 'rollout_turns_remaining', 0) > 0:
        return False, f"{mon.species} can't switch out while locked into Rollout!"

    ingrained = getattr(mon, 'ingrained', False) or getattr(mon, '_ingrained', False)
    if ingrained:
        gen_ingrain = getattr(mon, '_ingrain_generation', None)
        if gen_ingrain is None:
            gen_ingrain = get_generation(field_effects=field_effects)

        is_ghost = any(t == "Ghost" for t in mon.types if t)

        bypass_trap = False
        if item_is_active(mon) and mon.item:
            item_data = get_item_effect(normalize_item_name(mon.item))
            if item_data.get("ignores_trapping") or item_data.get("ignores_ingrain") or item_data.get("bypasses_trapping"):
                bypass_trap = True

        # Forced switches are still prevented unless an overriding item is present
        if force_switch and not bypass_trap:
            return False, f"{mon.species} anchored itself with roots!"

        if not bypass_trap:
            if gen_ingrain >= 6 and is_ghost:
                pass
            else:
                return False, f"{mon.species} is rooted and can't switch!"

    # Forced switches bypass trapping abilities (but not Suction Cups/Ingrain checks above)
    if force_switch:
        return True, None
    
    # Pivot moves (Baton Pass, U-turn, Volt Switch, Flip Turn, Parting Shot) bypass trapping
    if is_pivot_move:
        return True, None

    if getattr(mon, '_no_retreat_active', False):
        is_ghost = any((t or "").strip().title() == "Ghost" for t in mon.types if t)
        bypass = False
        if item_is_active(mon) and mon.item:
            item_data_nr = get_item_effect(normalize_item_name(mon.item))
            if item_data_nr.get("ignores_trapping") or item_data_nr.get("bypasses_trapping"):
                bypass = True
        if not (is_ghost or bypass):
            return False, f"{mon.species} can't escape!"
    
    # Check opponent's trapping abilities
    # If bypass_shadow_tag is True (opponent is switching), bypass ALL trapping abilities
    # because trapping abilities only work when the Pokémon is on the field
    if not bypass_shadow_tag:
        opponent_ability = normalize_ability_name(opponent.ability or "")
        
        # Shadow Tag - Traps all opponents
        # Gen 3: Traps everyone (including other Shadow Tag)
        # Gen 4+: Doesn't trap other Shadow Tag users
        # If Shadow Tag user just switched in, it doesn't trap this turn
        if opponent_ability == "shadow-tag":
            generation = get_generation(field_effects=field_effects)
            
            # Check if opponent just switched in this turn (Shadow Tag doesn't trap on switch-in turn)
            if getattr(opponent, '_just_switched_in', False):
                return True, None  # Shadow Tag doesn't trap on the turn it switches in
            
            # Check for Shed Shell (bypasses Shadow Tag)
            if item_is_active(mon) and mon.item:
                item_data = get_item_effect(normalize_item_name(mon.item))
                if item_data.get("ignores_trapping") or item_data.get("bypasses_trapping"):
                    return True, None  # Shed Shell allows switching
            
            # Gen VI+: Ghost-types are immune to Shadow Tag
            if generation >= 6:
                mon_types = [t.strip().title() if t else None for t in mon.types if t]
                if "Ghost" in mon_types:
                    return True, None  # Ghost-types are immune
            
            # Gen 3: Traps all opponents
            # Gen 4+: Shadow Tag users are immune to each other
            if generation <= 3:
                return False, f"{opponent.species}'s Shadow Tag prevents {mon.species} from switching!"
            else:
                if mon_ability != "shadow-tag":
                    return False, f"{opponent.species}'s Shadow Tag prevents {mon.species} from switching!"
    
        # Arena Trap - Traps grounded opponents
        if opponent_ability == "arena-trap":
            # Check if mon has Shed Shell (allows switching but not fleeing)
            if item_is_active(mon):
                item_data = get_item_effect(normalize_item_name(mon.item))
                if item_data.get("ignores_trapping"):
                    # Shed Shell bypasses Arena Trap for switching
                    pass  # Allow switch
                else:
                    # Check if mon is grounded (not Flying-type, no Levitate, no Air Balloon, no Magnet Rise)
                    is_grounded = True
                    
                    # Gen 6+: Ghost-types are immune to Arena Trap
                    generation = get_generation(field_effects=field_effects)  # Defaults to 9 if None
                    if generation >= 6 and "Ghost" in [mon.types[0], mon.types[1] if len(mon.types) > 1 else None]:
                        is_grounded = False
                    
                    # Flying-types are immune
                    if "Flying" in [mon.types[0], mon.types[1] if len(mon.types) > 1 else None]:
                        is_grounded = False
                    
                    # Levitate ability makes immune
                    if mon_ability == "levitate":
                        is_grounded = False
                    
                    # Check Air Balloon or Magnet Rise
                    if item_is_active(mon):
                        if item_data.get("grants_ground_immunity") or item_data.get("levitate_effect"):
                            is_grounded = False
                        # Iron Ball: Grounds holder (Gen 4+)
                        if item_data.get("grounds_holder"):
                            gen_ib = get_generation(field_effects=field_effects)
                            if gen_ib >= 4:
                                is_grounded = True  # Force grounded status
                    
                    # Check Magnet Rise status (temporary levitation)
                    if hasattr(mon, 'magnet_rise_turns') and mon.magnet_rise_turns > 0:
                        is_grounded = False
                    
                    if is_grounded:
                        return False, f"{opponent.species}'s Arena Trap prevents {mon.species} from switching!"
        
        
        # Magnet Pull - Traps Steel-types (Gen 6+: Ghost/Steel immune)
        if opponent_ability == "magnet-pull":
            if "Steel" in [mon.types[0], mon.types[1] if len(mon.types) > 1 else None]:
                # Gen 6+: Ghost/Steel dual-types are immune to Magnet Pull
                if "Ghost" not in [mon.types[0], mon.types[1] if len(mon.types) > 1 else None]:
                    return False, f"{opponent.species}'s Magnet Pull prevents {mon.species} from switching!"
    
    # Check for trapping moves (Block, Mean Look, Spider Web, etc.)
    # These moves set trapped=True and trap_source=user.species
    if getattr(mon, 'trapped', False) and getattr(mon, 'trap_source', None):
        trap_source = mon.trap_source
        
        # Check if the trapping Pokémon is still in battle
        # Block and Mean Look only work as long as the user remains in battle
        trap_source_active = False
        if battle_state and trap_source:
            try:
                p1_active = battle_state._active(battle_state.p1_id)
                p2_active = battle_state._active(battle_state.p2_id)
                
                # Check if any active Pokémon matches the trap source
                if hasattr(p1_active, 'species') and p1_active.species == trap_source:
                    trap_source_active = True
                if hasattr(p2_active, 'species') and p2_active.species == trap_source:
                    trap_source_active = True
                
                # Gen V+: If trapper used Baton Pass and switched out, trap is cleared
                generation = get_generation(field_effects=field_effects)
                if generation >= 5 and not trap_source_active:
                    # Trap cleared by Baton Pass (trapper switched out)
                    mon.trapped = False
                    mon.trap_source = None
                    return True, None
            except Exception:
                # If we can't determine, assume trap is active
                trap_source_active = True
        
        # If trap source is still active, check for exceptions
        if trap_source_active or not battle_state:
            # Pivot moves bypass trapping (handled by is_pivot_move parameter)
            if is_pivot_move:
                generation = get_generation(field_effects=field_effects)
                # Baton Pass: Gen V+ clears trap, Gen II-IV transfers trap (both allow switch)
                # U-turn (Gen III+), Volt Switch (Gen V+), Parting Shot (Gen VI+), Flip Turn (Gen VIII+)
                return True, None
            
            # Forced switches (Roar, Whirlwind, Dragon Tail, Circle Throw) bypass trapping
            if force_switch:
                return True, None
            
            # Otherwise, prevent switching
            return False, f"{mon.species} can't escape now!"
        else:
            # Trap source is not active, clear the trap
            mon.trapped = False
            mon.trap_source = None
    
    return True, None

def apply_special_ability_mechanics(mon: Mon, context: str, **kwargs) -> List[str]:
    """
    Apply special ability mechanics that don't fit into other categories.
    Context can be: "turn_start", "move_used", "stat_change", etc.
    Returns list of messages.
    """
    messages = []
    ability = normalize_ability_name(mon.ability or "")
    
    # Slow Start - Half Attack and Speed for 5 turns
    if ability == "slow-start" and not getattr(mon, "_ability_suppressed", False):
        if not hasattr(mon, '_slow_start_turns'):
            mon._slow_start_turns = 5
        if mon._slow_start_turns > 0:
            if context == "turn_start":
                mon._slow_start_turns -= 1
                if mon._slow_start_turns == 0:
                    messages.append(f"{mon.species}'s Slow Start ended!")
    
    # Truant - Can only move every other turn
    if ability == "truant":
        if context == "turn_start":
            mon._truant_turn = not getattr(mon, '_truant_turn', False)
        if context == "can_move" and not getattr(mon, '_truant_turn', True):
            messages.append(f"{mon.species} is loafing around!")
            return messages
    
    # Color Change - Change type to move that hit
    if ability == "color-change" and context == "after_hit":
        move_type = kwargs.get("move_type")
        if move_type and mon.hp > 0:
            mon.types = (move_type, None)
            messages.append(f"{mon.species} changed its type to {move_type}!")
    
    # Opportunist - Copy opponent's stat boosts
    if ability == "opportunist" and context == "opponent_stat_change":
        opponent = kwargs.get("opponent")
        stat_changes = kwargs.get("stat_changes", {})
        if opponent:
            for stat, change in stat_changes.items():
                if change > 0:  # Only copy positive changes
                    old_stage = mon.stages.get(stat, 0)
                    mon.stages[stat] = min(6, max(-6, old_stage + change))
            if stat_changes:
                messages.append(f"{mon.species}'s Opportunist copied the stat changes!")
    
    # Dancer - Copy dance moves
    # NOTE: Dancer is extremely complex (see Bulbapedia):
        # - Copies move after original completes
    # - Can wake from sleep/thaw to copy
    # - Fails if confused/flinched/taunted/locked
    # - Complex targeting rules in doubles
    # - Multiple Dancers move in reverse speed order
    # TODO: Full implementation requires reworking turn resolution
    if ability == "dancer" and context == "move_used":
        move_name = kwargs.get("move_name", "").lower().replace(" ", "-")
        # Complete list from Bulbapedia (Gen 9)
        dance_moves = ["aqua-step", "clangorous-soul", "dragon-dance", "feather-dance", 
                       "fiery-dance", "lunar-dance", "petal-dance", "revelation-dance",
                       "quiver-dance", "swords-dance", "teeter-dance", "victory-dance"]
        if move_name in dance_moves:
            # For now, just log the trigger (full implementation not done)
            messages.append(f"{mon.species}'s Dancer activated! (Note: Move copying not fully implemented)")
            mon._dancer_triggered = True
            mon._dancer_move = move_name
    
    return messages

def on_switch_in(mon: Mon, opponent: Mon, field_effects: Any = None) -> List[str]:
    # Reset Erratic tracking on switch-in (clear previous turn's changes)
    if hasattr(mon, '_erratic_boost_stat') and mon._erratic_boost_stat is not None:
        # Reverse previous boost
        old_boost = mon.stages.get(mon._erratic_boost_stat, 0)
        mon.stages[mon._erratic_boost_stat] = max(-6, min(6, old_boost - 2))
        mon._erratic_boost_stat = None
    if hasattr(mon, '_erratic_debuff_stat') and mon._erratic_debuff_stat is not None:
        # Reverse previous debuff
        old_debuff = mon.stages.get(mon._erratic_debuff_stat, 0)
        mon.stages[mon._erratic_debuff_stat] = max(-6, min(6, old_debuff + 2))
        mon._erratic_debuff_stat = None
    
    # Reset Metronome tracking on switch
    if hasattr(mon, '_metronome_last_move'):
        mon._metronome_last_move = None
        mon._metronome_consecutive = 0
    
    # Reset Slow Start counter on switch-in
    ability_norm = normalize_ability_name(mon.ability or "")
    if ability_norm == "slow-start":
        if hasattr(mon, '_slow_start_turns'):
            delattr(mon, '_slow_start_turns')
    """
    Trigger abilities that activate when a Pokémon switches in.
    Returns list of messages describing what happened.
    
    Gen 9 Logic:
    - Ability weather (Drizzle, Drought, etc.): Infinite duration (-1 turns)
    - Ability terrain: 5 turns (8 with Terrain Extender)
    """
    messages = []
    
    # === BERSERKER GENE: +2 Attack but confuses holder on entry (Gen 2 only) ===
    if item_is_active(mon) and mon.item:
        i_norm_bg = normalize_item_name(mon.item)
        i_data_bg = get_item_effect(i_norm_bg)
        gen_bg = get_generation(field_effects=field_effects)
        if i_data_bg.get("on_entry_boost") and i_data_bg.get("confuses_holder") and gen_bg == 2:
            # Boost Attack
            boost_data = i_data_bg.get("on_entry_boost", {})
            for stat, amount in boost_data.items():
                if stat in mon.stages:
                    old_stage = mon.stages[stat]
                    mon.stages[stat] = min(6, old_stage + amount)
                    stat_name = {"atk": "Attack", "defn": "Defense", "spa": "Sp. Atk", 
                                "spd": "Sp. Def", "spe": "Speed"}.get(stat, stat.upper())
                    messages.append(f"{mon.species}'s Berserker Gene raised its {stat_name}!")
            
            # Confuse holder (1-4 turns)
            confusion_turns = random.randint(1, 4)
            mon.confused = True
            mon.confusion_turns = confusion_turns
            mon._confusion_applied_this_turn = True
            messages.append(f"{mon.species} became confused due to its Berserker Gene!")
            
            # Consume item
            mon.item = None
    
    ability = normalize_ability_name(mon.ability or "")
    ability_data = get_ability_effect(ability)
    
    # === EARTHBOUND: Grounds all Pokémon on the field ===
    if ability_data.get("grounds_self_and_opponent"):
        messages.append("Due to Missing n0's Earthbound, all mons are grounded!")
    
    # === MASQUERADE: Adds type from teammate ===
    if ability == "masquerade" and hasattr(mon, '_masquerade_active') and mon._masquerade_active:
        copied_type = getattr(mon, '_masquerade_copied_type', None)
        if copied_type:
            messages.append(f"Due to Missing n0's Masquerade, it gained the {copied_type} type!")
    
    # === NULLSCAPE: Distorts reality when active ===
    if ability == "nullscape":
        nullscape_type = _get_nullscape_type(mon, getattr(mon, '_battle_state', None))
        if nullscape_type:
            messages.append("Missing n0's Nullscape distorted reality!")
            # Type-specific messages
            if nullscape_type == "Rock":
                messages.append("The land hardened into unbreakable stone!")
            elif nullscape_type == "Ice":
                messages.append("The battlefield was locked in killing cold!")
            elif nullscape_type == "Untyped":
                messages.append("All attributes vanished from the battlefield!")
            elif nullscape_type == "Normal":
                messages.append("Reality stabilized into its purest form!")
            elif nullscape_type == "Steel":
                messages.append("An unyielding steel field took hold!")
            elif nullscape_type == "Ghost":
                messages.append("A lingering curse clung to the battlefield!")

    # === PRIMAL/ORIGIN AUTO-TRANSFORMS (after hazards, before weather) ===
    try:
        generation = get_generation(field_effects=field_effects)
        item_id = (mon.item or "").strip().lower().replace(" ", "-").replace("_", "-")
        species_l = (mon.species or "").strip().lower()

        def _apply_form(form_full_key: str, display_name: str) -> None:
            ov = get_form_overrides(species_l, form_full_key)
            if not ov:
                return
            # Update core battle fields
            # Normalize stats keys
            s = ov.get("stats") or {}
            base_map = {
                "hp": s.get("hp") or s.get("HP"),
                "atk": s.get("atk") or s.get("attack"),
                "defn": s.get("def") or s.get("defense") or s.get("defn"),
                "spa": s.get("spa") or s.get("special_attack") or s.get("special-attack"),
                "spd": s.get("spd") or s.get("special_defense") or s.get("special-defense"),
                "spe": s.get("spe") or s.get("speed"),
            }
            for k, v in base_map.items():
                if v is not None:
                    mon.base[k] = int(v)
            # Types
            t = ov.get("types") or []
            if isinstance(t, list) and t:
                t1 = (t[0] if isinstance(t[0], str) else t[0].get("name")) if len(t) > 0 else None
                t2 = (t[1] if isinstance(t[1], str) else (t[1].get("name") if len(t) > 1 else None)) if len(t) > 1 else None
                mon.types = ((t1 or "Normal").capitalize(), (t2.capitalize() if isinstance(t2, str) else (t2 or None)))
            # Ability (first listed if present)
            ab = ov.get("abilities") or []
            if ab:
                name = ab[0]["name"] if isinstance(ab[0], dict) else str(ab[0])
                mon.ability = name
            # Mark form for renderers
            mon.form = form_full_key.replace(f"{species_l}-", "")
            messages.append(f"**{mon.species} transformed into {display_name}!**")

        # Primal Kyogre/Groudon (Gen 6+)
        if generation >= 6:
            if species_l == "kyogre" and item_id == "blue-orb":
                _apply_form("kyogre-primal", "its Primal Form")
            elif species_l == "groudon" and item_id == "red-orb":
                _apply_form("groudon-primal", "its Primal Form")

        # Origin Giratina (Gen 4+) via Griseous Orb
        if generation >= 4:
            if species_l == "giratina" and item_id in ("griseous-orb", "griseous-core", "griseous"):  # be tolerant
                _apply_form("giratina-origin", "its Origin Forme")

        # Origin Dialga/Palkia (Gen 8+ with PLA items)
        if generation >= 8:
            if species_l == "dialga" and item_id in ("adamant-crystal", "adamant-cristal"):
                _apply_form("dialga-origin", "its Origin Forme")
            if species_l == "palkia" and item_id in ("lustrous-globe", "lustrous-orb"):
                _apply_form("palkia-origin", "its Origin Forme")
    except Exception:
        pass

    # Form changes (e.g., Primal transformations) can update the Ability.
    # Refresh our normalized ability data if the form swap changed it.
    new_ability = normalize_ability_name(mon.ability or "")
    if new_ability != ability:
        ability = new_ability
        ability_data = get_ability_effect(ability)
    
    # === SPECIAL WEATHER ABILITIES ===
    if field_effects:
        ability_name_display = (mon.ability or ability).replace("-", " ").title()
        battle_state_ref = getattr(mon, '_battle_state', None)
        if ability_data.get("sets_heavy_rain"):
            changed, error_msg = apply_special_weather(field_effects, "heavy-rain", ability=ability, source_id=id(mon), battle_state=battle_state_ref)
            if error_msg:
                messages.append(f"**{mon.species}'s {ability_name_display}!**\n{error_msg}")
            else:
                weather_line = "☔ The heavy rain began to fall!" if changed else "☔ The heavy rain continues to fall!"
                messages.append(f"**{mon.species}'s {ability_name_display}!**\n{weather_line}")
        elif ability_data.get("sets_harsh_sunlight"):
            changed, error_msg = apply_special_weather(field_effects, "harsh-sunlight", ability=ability, source_id=id(mon), battle_state=battle_state_ref)
            if error_msg:
                messages.append(f"**{mon.species}'s {ability_name_display}!**\n{error_msg}")
            else:
                weather_line = "☀️ The extremely harsh sunlight blazed!" if changed else "☀️ The extremely harsh sunlight continues to shine!"
                messages.append(f"**{mon.species}'s {ability_name_display}!**\n{weather_line}")
        elif ability_data.get("sets_strong_winds"):
            changed, error_msg = apply_special_weather(field_effects, "strong-winds", ability=ability, source_id=id(mon), battle_state=battle_state_ref)
            if error_msg:
                messages.append(f"**{mon.species}'s {ability_name_display}!**\n{error_msg}")
            else:
                weather_line = "💨 Mysterious strong winds began to blow!" if changed else "💨 The strong winds continue to blow!"
                messages.append(f"**{mon.species}'s {ability_name_display}!**\n{weather_line}")

    # === AIR LOCK / CLOUD NINE: Negate weather effects ===
    if ability_data.get("weather_negation"):
        ability_name = (mon.ability or ability).replace("-", " ").title()
        messages.append(f"**{mon.species}'s {ability_name}!**")
        # Gen 5+ message
        messages.append("The effects of weather disappeared.")
    
    # === TERA SHIFT: Transform to Terastal Form (Gen 9+) ===
    if ability == "tera-shift" and "terapagos" in mon.species.lower():
        generation = get_generation(field_effects=field_effects)
        if generation >= 9 and mon.form != "terastal":
            mon.form = "terastal"
            ability_name = (mon.ability or ability).replace("-", " ").title()
            messages.append(f"**{mon.species}'s {ability_name}!**")
            messages.append(f"{mon.species} transformed into its Terastal Form!")
    
    # === TERAFORM ZERO: Neutralize weather and terrain (Gen 9+, Stellar Form) ===
    if ability == "teraform-zero" and "terapagos" in mon.species.lower():
        generation = get_generation(field_effects=field_effects)
        if generation >= 9 and mon.form == "stellar":
            ability_name = (mon.ability or ability).replace("-", " ").title()
            messages.append(f"**{mon.species}'s {ability_name}!**")
            
            # Neutralize weather
            if field_effects and hasattr(field_effects, 'weather') and field_effects.weather:
                cleared_special = clear_special_weather(field_effects)
                if cleared_special == "heavy-rain":
                    messages.append("The heavy rain disappeared!")
                elif cleared_special == "harsh-sunlight":
                    messages.append("The extremely harsh sunlight faded!")
                elif cleared_special == "strong-winds":
                    messages.append("The mysterious strong winds dissipated!")
                else:
                    messages.append("The weather effects disappeared!")
                field_effects.weather = None
                field_effects.weather_turns = 0
            
            # Neutralize terrain
            if field_effects and hasattr(field_effects, 'terrain') and field_effects.terrain:
                field_effects.terrain = None
                field_effects.terrain_turns = 0
                messages.append("The terrain effects disappeared!")
    
    # === TERAVOLT / TURBOBLAZE: Display aura message ===
    if ability == "teravolt":
        messages.append(f"{mon.species} is radiating a bursting aura!")
    elif ability == "turboblaze":
        messages.append(f"{mon.species} is radiating a blazing aura!")
    
    # === WIND RIDER: +1 Attack when entering battle while Tailwind is active ===
    if ability == "wind-rider" and field_effects:
        if hasattr(field_effects, 'tailwind') and field_effects.tailwind:
            # Check if Tailwind is active for this Pokémon's side
            if mon in field_effects.tailwind:
                old_atk = mon.stages.get("atk", 0)
                if old_atk < 6:
                    mon.stages["atk"] = min(6, old_atk + 1)
                    messages.append(f"{mon.species}'s Wind Rider raised its Attack!")
    
    # === TRACE: Copy adjacent opponent's ability ===
    # Trace activates when switching in, including at battle start
    if ability == "trace" and opponent and hasattr(opponent, 'ability') and opponent.ability:
        generation = get_generation(field_effects=field_effects)
        
        # Check if Trace has already activated for this Pokémon during this switch-in
        # Gen 4: Can only activate once per time on field
        # Gen 5: Must activate immediately or not at all
        # Gen 6+: Can reactivate if gained again via Skill Swap
        already_activated = getattr(mon, '_trace_activated_this_switch', False)
        
        # Gen 6+: Always try to activate, even if gained again
        # Gen 4-5: Only activate once per switch-in
        can_activate = (generation >= 6) or not already_activated
        
        if can_activate and opponent.ability:
            opponent_ability = normalize_ability_name(opponent.ability)
            opponent_ability_data = get_ability_effect(opponent_ability)
            
            # List of abilities that cannot be copied (varies by generation)
            uncopyable = [
                "battle-bond", "comatose", "commander", "disguise", "flower-gift", "forecast",
                "ice-face", "illusion", "imposter", "multitype", "neutralizing-gas",
                "poison-puppeteer", "power-construct", "power-of-alchemy", "receiver",
                "rks-system", "schooling", "shields-down", "stance-change", "trace",
                "wonder-guard", "zen-mode", "zero-to-hero", "as-one",
                "embody-aspect", "gulp-missile", "hunger-switch", "protosynthesis", "quark-drive"
            ]
            
            # Gen 3: Can copy Trace (but it won't activate again), cannot copy Wonder Guard
            if generation == 3:
                uncopyable = ["wonder-guard"]  # Only Wonder Guard in Gen 3
            # Gen 4+: Many more uncopyable abilities
            
            # Check if opponent's ability can be copied
            if opponent_ability not in uncopyable:
                # Gen 3: Can copy any ability except Wonder Guard (including Trace)
                # Check if ability has cannot_be_copied flag
                if generation >= 4 and opponent_ability_data.get("cannot_be_copied"):
                    messages.append(f"{mon.species}'s Trace failed to copy {opponent.species}'s {opponent.ability}!")
                else:
                    # Copy the ability!
                    old_ability = mon.ability
                    mon.ability = opponent.ability
                    mon._trace_activated_this_switch = True
                    
                    ability_display = opponent.ability.replace("-", " ").title()
                    tracer_name = format_species_name(mon.species)
                    target_name = format_species_name(opponent.species)
                    messages.append(f"{tracer_name} traced {target_name}'s {ability_display}!")
                    
                    # Some abilities have on-switch effects that should trigger
                    # (e.g., Intimidate, Download, etc.)
                    # These will be handled by the normal on_switch logic below
            else:
                # Gen 5: If no copyable ability at entry, Trace can't activate later
                if generation == 5:
                    mon._trace_activated_this_switch = True  # Mark as tried
        elif generation == 4 and not opponent.ability:
            # Gen 4: 50% chance to fail in doubles if replacing a fainted Pokémon
            # This is a simplification - the full logic is very complex
            pass
    
    handled_special_weather = ability_data.get("sets_heavy_rain") or ability_data.get("sets_harsh_sunlight") or ability_data.get("sets_strong_winds")

    if "on_switch" in ability_data:
        switch_data = ability_data["on_switch"]
        ability_name = (mon.ability or ability).replace("-", " ").title()
        
        # Stat stage changes (Intimidate, Intrepid Sword, Dauntless Shield)
        if "stages" in switch_data:
            # Intrepid Sword & Dauntless Shield: Gen 8 (every switch), Gen 9+ (once per battle)
            once_per_battle_abilities = ["dauntless-shield", "intrepid-sword"]
            if ability in once_per_battle_abilities:
                generation = get_generation(field_effects=field_effects)
                
                # Gen 8: Activates every switch-in
                # Gen 9+: Only activates once per battle
                should_activate = True
                if generation >= 9:
                    if mon._switch_ability_used:
                        # Already used this battle, skip
                        should_activate = False
                    else:
                        # First time using, mark as used
                        mon._switch_ability_used = True
                
                if should_activate:
                    target_mon = opponent if switch_data.get("target") == "opponent" else mon
                    old_stages = dict(target_mon.stages)
            
                    for stat, change in switch_data["stages"].items():
                        target_mon.stages[stat] = max(-6, min(6, target_mon.stages.get(stat, 0) + change))
                        if target_mon.stages[stat] != old_stages.get(stat, 0):
                            target_name = target_mon.species
                            # Use proper stat name instead of uppercase abbreviation
                            stat_name = {
                                "atk": "Attack", "defn": "Defense", "spa": "Special Attack",
                                "spd": "Special Defense", "spe": "Speed", 
                                "accuracy": "Accuracy", "evasion": "Evasiveness"
                            }.get(stat, stat.title())
                            if change < 0:
                                messages.append(f"**{mon.species}'s {ability_name}!**\n{target_name}'s {stat_name} fell!")
                            else:
                                messages.append(f"**{mon.species}'s {ability_name}!**\n{target_name}'s {stat_name} rose!")
                # else: Skip this activation (Gen 9+ and already used)
            else:
                # Other abilities (Intimidate, etc.) activate every time
                target_mon = opponent if switch_data.get("target") == "opponent" else mon
                old_stages = dict(target_mon.stages)
                
                # Check if this is Intimidate and target has special interactions
                is_intimidate = (ability == "intimidate")
                if is_intimidate:
                    if getattr(mon, "_intimidate_activated_this_switch", False):
                        return messages
                    mon._intimidate_activated_this_switch = True
                target_has_guard_dog = False
                target_has_inner_focus_gen5to7 = False
                
                if is_intimidate and target_mon:
                    generation = get_generation(field_effects=field_effects)
                    
                    target_ability = normalize_ability_name(target_mon.ability or "")
                    target_ability_data = get_ability_effect(target_ability)
                    
                    # Gen 8+: Guard Dog reverses Intimidate
                    if target_ability_data.get("intimidate_immunity_boost"):
                        target_has_guard_dog = True
                    
                    # Gen 5-7: Inner Focus blocks Intimidate (Gen 8+ it doesn't)
                    if 5 <= generation <= 7 and target_ability_data.get("flinch_immunity"):
                        target_has_inner_focus_gen5to7 = True
                    
                    # Gen VIII+: Scrappy also blocks Intimidate
                    if generation >= 8 and target_ability == "scrappy":
                        target_has_inner_focus_gen5to7 = True  # Reuse same flag for simplicity
                    
                    # Gen 8+: Stat drop immunity abilities (Clear Body, Hyper Cutter, White Smoke, etc.) block Intimidate
                    if generation >= 8:
                        stat_drop_immunity = target_ability_data.get("stat_drop_immunity")
                        if stat_drop_immunity:
                            # Full immunity (Clear Body, White Smoke, Full Metal Body) or Attack-specific (Hyper Cutter)
                            if stat_drop_immunity is True or (isinstance(stat_drop_immunity, list) and "atk" in stat_drop_immunity):
                                target_has_inner_focus_gen5to7 = True  # Reuse same flag for simplicity
                        
                        # Gen 8+: Oblivious and Own Tempo also block Intimidate
                        if target_ability in ["oblivious", "own-tempo"]:
                            target_has_inner_focus_gen5to7 = True
                
                # Gen 5-7: Skip Intimidate if target has Inner Focus
                # Gen VIII+: Skip Intimidate if target has Inner Focus, Scrappy, or stat drop immunity abilities
                if is_intimidate and target_has_inner_focus_gen5to7:
                    target_ability_name = (target_mon.ability or "").replace("-", " ").title() if target_mon.ability else "ability"
                    messages.append(f"**{mon.species}'s {ability_name}!**")
                    messages.append(f"{target_mon.species}'s {target_ability_name} prevents intimidation!")
                else:
                    for stat, change in switch_data["stages"].items():
                        # Guard Dog: Reverse Intimidate (turn -1 Attack into +1 Attack)
                        actual_change = change
                        if target_has_guard_dog and is_intimidate and stat == "atk":
                            actual_change = -change  # Reverse the change
                            target_mon.stages[stat] = max(-6, min(6, target_mon.stages.get(stat, 0) + actual_change))
                            if target_mon.stages[stat] != old_stages.get(stat, 0):
                                messages.append(f"**{mon.species}'s {ability_name}!**")
                                messages.append(f"{target_mon.species}'s Guard Dog boosted its Attack!")
                        else:
                            target_mon.stages[stat] = max(-6, min(6, target_mon.stages.get(stat, 0) + change))
                            if target_mon.stages[stat] != old_stages.get(stat, 0):
                                target_name = target_mon.species
                                # Use proper stat name instead of uppercase abbreviation
                                stat_name = {
                                    "atk": "Attack", "defn": "Defense", "spa": "Special Attack",
                                    "spd": "Special Defense", "spe": "Speed", 
                                    "accuracy": "Accuracy", "evasion": "Evasiveness"
                                }.get(stat, stat.title())
                                if change < 0:
                                    messages.append(f"**{mon.species}'s {ability_name}!**\n{target_name}'s {stat_name} fell!")
                                else:
                                    messages.append(f"**{mon.species}'s {ability_name}!**\n{target_name}'s {stat_name} rose!")
                        
                        # Rattled - Gen 8+: Also activates when affected by Intimidate
                        if is_intimidate and target_ability == "rattled" and generation >= 8:
                            old_spe = target_mon.stages.get("spe", 0)
                            if old_spe < 6:
                                target_mon.stages["spe"] = old_spe + 1
                                messages.append(f"{target_mon.species}'s Rattled raised its Speed!")

                    # Adrenaline Orb: activates when Intimidate is present (even if blocked by ability/Mist)
                    if is_intimidate and item_is_active(target_mon):
                        t_item = normalize_item_name(target_mon.item)
                        t_item_data = get_item_effect(t_item)
                        if t_item == "adrenaline-orb" and generation >= t_item_data.get("min_gen", 1):
                            # Check stage limit rule: don't activate if already at -6 Atk (or +6 with Contrary)
                            contrary = target_ability_data.get("inverts_stat_changes", False)
                            atk_stage = target_mon.stages.get("atk", 0)
                            blocked_by_limit = (atk_stage <= -6 and not contrary) or (atk_stage >= 6 and contrary)
                            if not blocked_by_limit:
                                # Apply +1 Speed and consume
                                old = target_mon.stages.get("spe", 0)
                                if old < 6:
                                    target_mon.stages["spe"] = old + 1
                                    messages.append(f"{target_mon.species}'s Adrenaline Orb raised its Speed!")
                                target_mon.item = None
        
        # Download - smart boost based on opponent's defenses
        if switch_data.get("smart_boost"):
            ability_name = (mon.ability or ability).replace("-", " ").title()
            opp_def = get_effective_stat(opponent, "defn")
            opp_spd = get_effective_stat(opponent, "spd")
            if opp_def < opp_spd:
                mon.stages["atk"] = min(6, mon.stages.get("atk", 0) + 1)
                messages.append(f"**{mon.species}'s {ability_name}!**\n{mon.species}'s ATK rose!")
            else:
                mon.stages["spa"] = min(6, mon.stages.get("spa", 0) + 1)
                messages.append(f"**{mon.species}'s {ability_name}!**\n{mon.species}'s SPA rose!")
        
    # Supersweet Syrup: Lower opponent's evasion by 1 stage (once per battle, Gen 9+)
    if ability == "supersweet-syrup" and opponent:
        generation = get_generation(field_effects=field_effects)
        
        if generation >= 9:
            # Check if already used this battle
            if not mon._switch_ability_used:
                # Lower opponent's evasion
                old_evasion = opponent.stages.get("evasion", 0)
                opponent.stages["evasion"] = max(-6, old_evasion - 1)
                
                ability_name = (mon.ability or ability).replace("-", " ").title()
                messages.append(f"**{mon.species}'s {ability_name}!**\n{opponent.species}'s evasiveness harshly fell!")
                
                # Mark as used
                mon._switch_ability_used = True
    
        # Weather abilities (Drizzle, Drought, Sand Stream, Snow Warning)
        # Same as moves: 5 turns (8 with weather rock)
    if "on_switch" in ability_data:
        switch_data = ability_data["on_switch"]
        if "weather" in switch_data and field_effects and not handled_special_weather:
            weather = switch_data["weather"]
            current_weather = getattr(field_effects, 'weather', None)
            was_active = (current_weather == weather)
            
            if not was_active:
                # New weather - activate it
                # Special weather locks (Primordial Sea/Desolate Land/Delta Stream) prevent other weather activations
                # Desolate Land prevents Drought, Drizzle, Sand Stream, and Snow Warning from activating
                # Primordial Sea prevents Drought, Drizzle, Sand Stream, and Snow Warning from activating
                # Only Primordial Sea can override Desolate Land, and only Desolate Land can override Primordial Sea
                special_weather_active = getattr(field_effects, 'special_weather', None)
                if special_weather_active in {"heavy-rain", "harsh-sunlight", "strong-winds"}:
                    messages.append(f"**{mon.species}'s {ability_name}!**\nBut the special weather prevented changes!")
                else:
                    field_effects.weather = weather
                
                    # Weather duration varies by generation
                    generation = get_generation(field_effects=field_effects)
                
                    # Gen 3-5: Permanent weather (infinite)
                    # Gen 6+: 5 turns (8 with Weather Rock)
                    if generation <= 5:
                        weather_duration = -1  # Permanent (infinite)
                    else:
                        # Check for Weather Rocks (Gen 6+)
                        weather_duration = 5  # Default: 5 turns
                        if item_is_active(mon):
                            item_data = get_item_effect(normalize_item_name(mon.item))
                            # Check if the rock extends this specific weather type
                            extends_weather_type = item_data.get("extends_weather")
                            if extends_weather_type == weather:
                                weather_duration = 8

                    field_effects.weather_turns = weather_duration
                    if weather == "sandstorm":
                        # Gen II specific damage window (ability-based sandstorm doesn't exist until Gen III)
                        field_effects.sandstorm_damage_turns = 0
                    ability_name = (mon.ability or ability).replace("-", " ").title()

                    weather_messages = {
                        "rain": "☔ It started to rain!",
                        "sun": "☀️ The sunlight turned harsh!",
                        "sandstorm": "🌪️ A sandstorm kicked up!",
                        "hail": "❄️ It started to hail!"
                    }
                    msg = f"**{mon.species}'s {ability_name}!**\n{weather_messages.get(weather, 'Weather changed!')}"
                    messages.append(msg)
            # If weather was already active, do nothing (don't reset timer)
        elif "weather" in switch_data and not handled_special_weather:
            # Fallback if field_effects not provided (just message)
            weather = switch_data["weather"]
            ability_name = (mon.ability or ability).replace("-", " ").title()
            weather_messages = {
                "rain": "☔ It started to rain!",
                "sun": "☀️ The sunlight turned harsh!",
                "sandstorm": "🌪️ A sandstorm kicked up!",
                "hail": "❄️ It started to hail!"
            }
            messages.append(f"**{mon.species}'s {ability_name}!**\n{weather_messages.get(weather, 'Weather changed!')}")
        
        # Terrain abilities (Electric Surge, Psychic Surge, etc.)
        # Gen 9: 5 turns (8 with Terrain Extender)
        if "terrain" in switch_data and field_effects:
            terrain = switch_data["terrain"]
            was_active = (field_effects.terrain == terrain)
            
            if not was_active:
                # New terrain - activate it
                field_effects.terrain = terrain
                
                # Check for Terrain Extender
                terrain_duration = 5
                if item_is_active(mon):
                    item_data = get_item_effect(normalize_item_name(mon.item))
                    if item_data.get("extends_terrain"):
                        terrain_duration = 8
                
                field_effects.terrain_turns = terrain_duration
                ability_name = (mon.ability or ability).replace("-", " ").title()
                terrain_messages = {
                    "electric": "⚡ Electric Terrain activated!",
                    "psychic": "🔮 Psychic Terrain activated!",
                    "grassy": "🌿 Grassy Terrain activated!",
                    "misty": "🌫️ Misty Terrain activated!"
                }
                messages.append(f"**{mon.species}'s {ability_name}!**\n{terrain_messages.get(terrain, 'Terrain changed!')}")
            # If terrain was already active, do nothing (don't reset timer)
        elif "terrain" in switch_data:
            # Fallback if field_effects not provided (just message)
            terrain = switch_data["terrain"]
            ability_name = (mon.ability or ability).replace("-", " ").title()
            terrain_messages = {
                "electric": "⚡ Electric Terrain activated!",
                "psychic": "🔮 Psychic Terrain activated!",
                "grassy": "🌿 Grassy Terrain activated!",
                "misty": "🌫️ Misty Terrain activated!"
            }
            messages.append(f"**{mon.species}'s {ability_name}!**\n{terrain_messages.get(terrain, 'Terrain changed!')}")
        
        # Trace: Copy opponent's ability
        if switch_data.get("copy_ability") and opponent and opponent.ability:
            opponent_ability = normalize_ability_name(opponent.ability)
            opponent_ability_data = get_ability_effect(opponent_ability)
            
            # Don't copy certain abilities (Illusion, Multitype, Stance Change, etc.)
            uncopyable = ["trace", "imposter", "illusion", "multitype", "stance-change", "power-construct", 
                         "battle-bond", "schooling", "shields-down", "disguise", "gulp-missile", "ice-face",
                         "zen-mode", "forecast", "flower-gift", "wonder-guard"]
            
            if opponent_ability not in uncopyable:
                mon.ability = opponent.ability
                ability_name = opponent.ability.replace("-", " ").title()
                tracer_name = format_species_name(mon.species)
                target_name = format_species_name(opponent.species)
                messages.append(f"{tracer_name} traced {target_name}'s {ability_name}!")
        
        # Imposter: Transform into opponent (silently for surprise factor)
        # Gen 5: Copies stat stages
        # Gen 6+: Does NOT copy stat stages
        if switch_data.get("transform") and opponent and opponent.hp > 0:
            generation = get_generation(field_effects=field_effects)
            
            # Copy stats (but keep own HP)
            original_hp = mon.hp
            original_max_hp = mon.max_hp
            
            mon.stats = dict(opponent.stats)
            
            # Gen 5: Copy stat stages, Gen 6+: Don't copy stat stages
            if generation <= 5:
                mon.stages = dict(opponent.stages)
            else:
                # Gen 6+: Reset to 0 stages (don't copy)
                mon.stages = {stat: 0 for stat in mon.stages}
            
            mon.types = tuple(opponent.types)  # Copy types tuple
            mon.moves = list(opponent.moves)
            mon.ability = opponent.ability  # Transform copies ability
            mon.species = opponent.species  # For display
            mon.weight_kg = opponent.weight_kg  # Copy weight for Heavy Slam, etc.
            # Copy form if present
            if hasattr(opponent, 'form'):
                mon.form = opponent.form
            
            # Keep own HP (scaled to new max HP)
            hp_ratio = original_hp / original_max_hp if original_max_hp > 0 else 1.0
            mon.max_hp = opponent.max_hp
            mon.hp = int(mon.max_hp * hp_ratio)
            
            # Mark that this mon transformed (for PP restriction and revert)
            mon._transformed = True  # Use same flag as Transform move
            mon._imposter_transformed = True  # Keep this for backwards compatibility
            
            # NO MESSAGE - keep it a surprise!
    
    # === ADDITIONAL ON-SWITCH-IN ABILITIES ===
    # Embody Aspect variants
    if ability in ["embody-aspect-cornerstone", "embody-aspect-hearthflame", "embody-aspect-teal", "embody-aspect-wellspring"]:
        ability_name = ability.replace("-", " ").title()
        if ability == "embody-aspect-cornerstone":
            mon.stages["defn"] = min(6, mon.stages.get("defn", 0) + 1)
            messages.append(f"**{mon.species}'s {ability_name}!**\n{mon.species}'s Defense rose!")
        elif ability == "embody-aspect-hearthflame":
            mon.stages["atk"] = min(6, mon.stages.get("atk", 0) + 1)
            messages.append(f"**{mon.species}'s {ability_name}!**\n{mon.species}'s Attack rose!")
        elif ability == "embody-aspect-teal":
            mon.stages["spe"] = min(6, mon.stages.get("spe", 0) + 1)
            messages.append(f"**{mon.species}'s {ability_name}!**\n{mon.species}'s Speed rose!")
        elif ability == "embody-aspect-wellspring":
            mon.stages["spa"] = min(6, mon.stages.get("spa", 0) + 1)
            messages.append(f"**{mon.species}'s {ability_name}!**\n{mon.species}'s Special Attack rose!")
    
    # Screen Cleaner
    if ability == "screen-cleaner" and field_effects:
        ability_name = ability.replace("-", " ").title()
        removed_any = False
        # Remove both sides' screens
        if hasattr(field_effects, 'p1_side') and hasattr(field_effects, 'p2_side'):
            for side in [field_effects.p1_side, field_effects.p2_side]:
                if side.reflect or side.light_screen or side.aurora_veil:
                    side.reflect = False
                    side.light_screen = False
                    side.aurora_veil = False
                    removed_any = True
        if removed_any:
            messages.append(f"**{mon.species}'s {ability_name}!**\nAll screens were removed!")
    
    # Frisk - Reveal opponent's item
    if ability == "frisk" and opponent and opponent.item:
        ability_name = ability.replace("-", " ").title()
        item_name = opponent.item.replace("-", " ").title()
        messages.append(f"**{mon.species}'s {ability_name}!**\n{mon.species} frisked {opponent.species} and found its {item_name}!")
    
    # Forewarn - Reveal opponent's strongest move (by power)
    if ability == "forewarn" and opponent and opponent.moves:
        ability_name = ability.replace("-", " ").title()
        strongest_move = None
        highest_power = 0
        for move_name in opponent.moves:
            mv = load_move(move_name)
            power = mv.get("power", 0) if mv else 0
            if power and power > highest_power:
                highest_power = power
                strongest_move = move_name
        if strongest_move:
            move_display = strongest_move.replace("-", " ").title()
            messages.append(f"**{mon.species}'s {ability_name}!**\n{mon.species} was alerted to {opponent.species}'s {move_display}!")
    
    # === QUARK DRIVE / PROTOSYNTHESIS: Boost highest stat ===
    # Gen 9+ only: Activates on switch-in if terrain/weather or Booster Energy is held
    if ability in ["quark-drive", "protosynthesis"]:
        generation = get_generation(field_effects=field_effects)
        
        if generation >= 9:
            # Check if already boosted this switch-in
            if not hasattr(mon, '_paradox_ability_activated') or not mon._paradox_ability_activated:
                should_activate = False
                source = ""
                consumed_booster = False
                
                # Check for Booster Energy
                if item_is_active(mon):
                    item_data = get_item_effect(normalize_item_name(mon.item))
                    if item_data.get("activates_paradox_ability"):
                        should_activate = True
                        source = "Booster Energy"
                        consumed_booster = True
                
                # Check for terrain/weather (if Booster Energy not present)
                if not should_activate and field_effects:
                    if ability == "quark-drive" and hasattr(field_effects, 'terrain') and field_effects.terrain == "electric":
                        should_activate = True
                        source = "Electric Terrain"
                    elif ability == "protosynthesis" and hasattr(field_effects, 'weather') and field_effects.weather == "sun":
                        should_activate = True
                        source = "harsh sunlight"
                
                if should_activate:
                    # Determine highest base stat (excluding HP)
                    stat_values = {
                        "atk": mon.stats.get("atk", 0),
                        "defn": mon.stats.get("defn", 0),
                        "spa": mon.stats.get("spa", 0),
                        "spd": mon.stats.get("spd", 0),
                        "spe": mon.stats.get("spe", 0)
                    }
                    
                    highest_stat = max(stat_values, key=stat_values.get)
                    highest_value = stat_values[highest_stat]
                    
                    # Mark which stat is boosted
                    mon._paradox_boosted_stat = highest_stat
                    mon._paradox_ability_activated = True
                    
                    # Consume Booster Energy if used
                    if consumed_booster:
                        mon.item = None
                    
                    ability_name = ability.replace("-", " ").title()
                    stat_names = {
                        "atk": "Attack",
                        "defn": "Defense",
                        "spa": "Sp. Atk",
                        "spd": "Sp. Def",
                        "spe": "Speed"
                    }
                    
                    messages.append(f"**{mon.species}'s {ability_name}!**")
                    messages.append(f"{mon.species}'s {stat_names[highest_stat]} was heightened due to {source}!")
    
    # === ROOM SERVICE: Lowers Speed by 1 stage in Trick Room (Gen 8+) ===
    if field_effects and hasattr(field_effects, 'trick_room') and field_effects.trick_room:
        if item_is_active(mon) and mon.item:
            i_norm = normalize_item_name(mon.item)
            i_data = get_item_effect(i_norm)
            gen_rs = get_generation(field_effects=field_effects)
            if i_data.get("lowers_speed_in_trick_room") and gen_rs >= 8:
                # Lower Speed by 1 stage and consume item
                old_spe = mon.stages.get("spe", 0)
                mon.stages["spe"] = max(-6, old_spe - 1)
                mon.item = None  # Consume Room Service
                messages.append(f"{mon.species}'s Room Service lowered its Speed!")
    
    # === TERRAIN SEEDS: Boost stats when terrain is active (Gen 7+) ===
    if field_effects and hasattr(field_effects, 'terrain') and field_effects.terrain:
        if item_is_active(mon) and mon.item:
            i_norm_ts = normalize_item_name(mon.item)
            i_data_ts = get_item_effect(i_norm_ts)
            gen_ts = get_generation(field_effects=field_effects)
            boost_data = i_data_ts.get("boost_on_terrain")
            if boost_data and gen_ts >= 7:
                required_terrain = boost_data.get("terrain")
                if field_effects.terrain == required_terrain:
                    stat_stages = boost_data.get("stages", {})
                    for stat, amount in stat_stages.items():
                        if stat in mon.stages:
                            old_stage = mon.stages[stat]
                            mon.stages[stat] = min(6, old_stage + amount)
                            stat_name = {"defn": "Defense", "spd": "Sp. Def"}.get(stat, stat.upper())
                            messages.append(f"{mon.species}'s {i_norm_ts.replace('-', ' ').title()} raised its {stat_name}!")
                    mon.item = None  # Consume terrain seed
    
    # Anticipation - Warn of super effective moves or OHKO moves
    if ability == "anticipation" and opponent and opponent.moves:
        ability_name = ability.replace("-", " ").title()
        should_shudder = False
        
        # List of OHKO moves
        ohko_moves = ["fissure", "horn-drill", "guillotine", "sheer-cold"]
        
        for move_name in opponent.moves:
            move_lower = move_name.lower().replace(" ", "-")
            
            # Check for OHKO moves
            if move_lower in ohko_moves:
                should_shudder = True
                break
            
            mv = load_move(move_name)
            if mv:
                move_type = mv.get("type", "Normal")
                damage_class = mv.get("damage_class", "status")
                
                # Only check damaging moves
                if damage_class in ["physical", "special"]:
                    # Gen 6+: Hidden Power uses its actual type (calculated from IVs)
                    # For other Pokemon's moves, we can't know their HP type without their IVs
                    # So we skip checking Hidden Power's effectiveness
                    if move_lower == "hidden-power":
                        continue  # Can't determine type without opponent's IVs
                    
                    # Check type effectiveness
                    mult, _ = type_multiplier(move_type, mon, False, damage_class, user=opponent)
                    if mult >= 2.0:  # Super effective
                        should_shudder = True
                    break
        
        if should_shudder:
            messages.append(f"**{mon.species}'s {ability_name}!**\n{mon.species} shuddered!")
    
    # Tera Shift - Transform on entry (Terapagos)
    if ability == "tera-shift":
        ability_name = ability.replace("-", " ").title()
        messages.append(f"**{mon.species}'s {ability_name}!**\n{mon.species} transformed!")
        # Form change logic would go here
    
    # Teraform Zero - Remove terrain and weather
    if ability == "teraform-zero" and field_effects:
        ability_name = ability.replace("-", " ").title()
        removed = []
        if hasattr(field_effects, 'weather') and field_effects.weather:
            field_effects.weather = None
            field_effects.weather_turns = 0
            removed.append("weather")
        if hasattr(field_effects, 'terrain') and field_effects.terrain:
            field_effects.terrain = None
            field_effects.terrain_turns = 0
            removed.append("terrain")
        if removed:
            messages.append(f"**{mon.species}'s {ability_name}!**\nThe {' and '.join(removed)} disappeared!")
    
    return messages

# NOTE: STAT_MOVES dictionary has been moved to pvp/move_effects.py
# All stat-changing moves are now defined in MOVE_SECONDARY_EFFECTS dictionary
# This keeps the codebase clean and centralized

def apply_move(user: Mon, target: Mon, move_name: str, field_effects: Any = None, target_side: Any = None, user_choice: Optional[Dict] = None, target_choice: Optional[Dict] = None, battle_state: Any = None, is_moving_last: bool = False) -> str:
    # Helper function to resolve owner ID for a mon
    def _resolve_owner_id(mon: Mon) -> int:
        if not battle_state:
            return id(mon)
        try:
            if mon in battle_state.team_for(battle_state.p1_id):
                return battle_state.p1_id
            if mon in battle_state.team_for(battle_state.p2_id):
                return battle_state.p2_id
        except Exception:
            pass
        return id(mon)
    """
    Apply a move from user to target.
    Now includes special move handling for Fake Out, Sucker Punch, Counter, Transform, etc.
    
    Args:
        user: The Pokemon using the move
        target: The Pokemon being targeted
        move_name: Name of the move
        field_effects: Field conditions (weather, terrain, etc.)
        target_side: Target's side effects (hazards, screens, etc.)
        user_choice: User's choice dict
        target_choice: Target's choice dict
        battle_state: The BattleState object
        is_moving_last: Whether this Pokemon is moving last this turn (for Analytic)
    """
    # get_move is imported at module level, but local imports inside function shadow it
    # Import here to avoid UnboundLocalError
    from .moves_loader import get_move
    # get_generation is imported at module level, but local imports inside function shadow it
    # Import here to avoid UnboundLocalError
    from .generation import get_generation
    # get_item_effect is imported at module level, but local imports inside function shadow it
    # Import here to avoid UnboundLocalError
    from .items import get_item_effect, normalize_item_name
    
    move_effect_main: Dict[str, Any] = get_move_effects(move_name, battle_state) or {}
    move_effect: Dict[str, Any] = {}
    
    # Get generation for generation-specific stats
    generation_for_move_data = get_generation(field_effects=field_effects, battle_state=battle_state)
    # Initialize move_data early with generation-specific stats (use battle_state move cache when available)
    move_data = get_move(move_name, generation=generation_for_move_data, battle_state=battle_state)
    # Fetch mechanics once and reuse (multi-hit, Parental Bond, recoil/drain) to avoid repeated lookups
    mechanics = get_move_mechanics(move_name, battle_state)
    
    # Normalize move name for checks
    normalized_move_name = move_name.lower().replace(" ", "-").strip()
    move_lower = normalized_move_name
    normalized_move = normalized_move_name  # Alias for compatibility
    
    # === SPECIAL HANDLING FOR DUMMY MAGIKARP ===
    # Dummy Magikarp's Tackle has special behavior:
    # - Always brings target (player's Pokémon) to exactly 50% HP
    # - Fails if target isn't at full HP
    # - Always fails when target has 50% HP (so target stays at 50%)
    if getattr(user, '_is_dummy_magikarp', False) and normalized_move_name == "tackle":
        target_hp_percent = (target.hp / target.max_hp * 100) if target.max_hp > 0 else 0
        
        # Always fail when target has 50% HP (so target stays at 50%)
        if abs(target_hp_percent - 50.0) < 0.1:
            user._last_move_failed = True
            return f"**{user.species}** used **Tackle**!\nBut it failed! ({target.species} is at 50% HP!)"
        
        # Fail if target isn't at full HP
        if target.hp < target.max_hp:
            user._last_move_failed = True
            return f"**{user.species}** used **Tackle**!\nBut it failed! ({target.species} must be at full HP!)"
        
        # Calculate damage to bring target to exactly 50% HP
        target_50_percent_hp = target.max_hp // 2
        
        # Calculate damage needed to bring target to exactly 50% HP
        damage_to_deal = target.hp - target_50_percent_hp
        
        # Apply the damage directly
        old_target_hp = target.hp
        target.hp = max(0, target.hp - damage_to_deal)
        actual_damage = old_target_hp - target.hp
        
        # Build message
        msg = f"**{user.species}** used **Tackle**!"
        if actual_damage > 0:
            msg += f"\n{target.species} took {actual_damage} damage!"
            if target.hp == target_50_percent_hp:
                msg += f"\n{target.species} is now at 50% HP!"
            if target.hp <= 0:
                msg += f"\n{target.species} fainted!"
        else:
            msg += f"\nIt had no effect on {target.species}!"
        
        return msg
    
    # === NULLSCAPE: Move failures based on MissingNo's type ===
    nullscape_type = _get_nullscape_type(user, battle_state)
    if nullscape_type:
        move_type_for_nullscape = (move_data.get("type") or "Normal") if move_data else "Normal"
        move_type_for_nullscape = move_type_for_nullscape.strip().title()
        
        # Ice Nullscape: All Fighting moves fail unless used by Ice type
        if nullscape_type == "Ice" and move_type_for_nullscape == "Fighting":
            user_types = [t.strip().title() if t else None for t in user.types]
            if "Ice" not in user_types:
                user._last_move_failed = True
                return f"**{user.species}** used **{move_name}**!\nThe Fighting-Type attack could not land due to the bitter cold!"
        
        # Rock Nullscape: All Grass moves fail unless used by Rock type
        if nullscape_type == "Rock" and move_type_for_nullscape == "Grass":
            user_types = [t.strip().title() if t else None for t in user.types]
            if "Rock" not in user_types:
                user._last_move_failed = True
                return f"**{user.species}** used **{move_name}**!\nThe Grass-Type attack could not weather the stone!"
        
        # Normal Nullscape: All Ghost moves fail unless used by Normal type
        if nullscape_type == "Normal" and move_type_for_nullscape == "Ghost":
            user_types = [t.strip().title() if t else None for t in user.types]
            if "Normal" not in user_types:
                user._last_move_failed = True
                return f"**{user.species}** used **{move_name}**!\nThe Ghost-Type attack disappeared from reality!"
        
        # Ghost Nullscape: All Normal moves fail unless used by Ghost type
        if nullscape_type == "Ghost" and move_type_for_nullscape == "Normal":
            user_types = [t.strip().title() if t else None for t in user.types]
            if "Ghost" not in user_types:
                user._last_move_failed = True
                return f"**{user.species}** used **{move_name}**!\nThe Normal-Type attack was doomed to fail!"
    
    # Ensure perish_song is set for perish-song move (fallback if database doesn't have it)
    # Database returns 0 or 1, but we need it to be truthy (True or 1)
    if normalized_move_name == "perish-song":
        # Convert database value (0/1) to boolean, or set True if missing
        if move_effect_main.get("perish_song") == 0 or move_effect_main.get("perish_song") is None:
            move_effect_main["perish_song"] = True
        elif move_effect_main.get("perish_song") == 1:
            move_effect_main["perish_song"] = True  # Ensure it's True, not just 1

    # Store battle_state on user for Aura abilities (Dark Aura, Fairy Aura, Aura Break)
    if battle_state:
        user._battle_state = battle_state
        target._battle_state = battle_state
        try:
            active_p1 = battle_state._active(battle_state.p1_id)
            user_side = battle_state.p1_side if user == active_p1 else battle_state.p2_side
        except Exception:
            user_side = None
        generation_check = getattr(battle_state, "gen", None)
    else:
        user_side = None
        generation_check = None
    
    # Prize money hooks: mark Happy Hour and money-generating moves
    user_owner_id = _resolve_owner_id(user)
    if normalized_move_name == "happy-hour" and battle_state and hasattr(battle_state, "happy_hour_used"):
        battle_state.happy_hour_used[user_owner_id] = True
    if normalized_move_name in {"pay-day", "make-it-rain", "g-max-gold-rush"} and battle_state and hasattr(battle_state, "money_pool"):
        if normalized_move_name == "g-max-gold-rush":
            bonus_cash = 100 * max(1, user.level)
        else:
            bonus_cash = 5 * max(1, user.level)
        battle_state.money_pool[user_owner_id] = battle_state.money_pool.get(user_owner_id, 0) + bonus_cash
    
    if field_effects:
        user._field_effects = field_effects
        if target is not None:
            target._field_effects = field_effects
        if generation_check is None:
            gen_from_field = getattr(field_effects, "generation", None)
            if isinstance(gen_from_field, int):
                generation_check = gen_from_field
    
    if generation_check is None:
        generation_check = get_generation(battle_state=battle_state, field_effects=field_effects)
    if battle_state and getattr(battle_state, "gen", None) is None:
        try:
            battle_state.gen = generation_check
        except Exception:
            pass
    
    # === Z-MOVE CHECK ===
    # Check if this move is a Z-Move (from user_choice flag)
    is_z_move = False
    z_move_name = move_name  # Will be transformed if Z-Move
    if user_choice and user_choice.get("z_move"):
        
        generation = get_generation(field_effects=field_effects)
        
        # Only Gen 7 can use Z-Moves
        if generation == 7:
            can_use_z, reason = can_use_z_move(0, user, move_name, generation)
            if not can_use_z:
                if user_choice:
                    user_choice["z_move"] = False
                user._last_move_failed = True
                normalized_for_rollout = move_name.lower().replace(" ", "-").strip()
                handle_rollout_failure(
                    user,
                    normalized_for_rollout in ROLLOUT_MOVES,
                )
                fail_reason = reason or "It wasn't compatible with the Z-Crystal."
                return f"**{user.species}** tried to unleash its Z-Power!\nBut it failed! ({fail_reason})"
            is_z_move = True
            move_data = get_move(move_name, generation=generation_for_move_data, battle_state=battle_state)
            if move_data:
                move_type = move_data.get("type", "Normal")
                z_move_name = get_z_move_name(move_name, user.species, move_type)
    
    # Use Z-Move name if this is a Z-Move
    original_move_name = move_name  # Store original before transformation
    if is_z_move:
        # Store original move info on user for damage calculation
        user._is_z_move = True
        user._original_move_name = original_move_name
        user._z_move_name = z_move_name
        
        # Store category from base move (Z-Moves inherit category from base move)
        # Signature Z-Moves may override category, check that
        species_normalized = user.species.lower().replace(" ", "-").strip()
        base_normalized = original_move_name.lower().replace(" ", "-").strip()
        if species_normalized in SIGNATURE_Z_MOVES and base_normalized in SIGNATURE_Z_MOVES[species_normalized]:
            sig_data = SIGNATURE_Z_MOVES[species_normalized][base_normalized]
            if isinstance(sig_data, dict) and sig_data.get("category"):
                user._z_move_category = sig_data["category"]
            else:
                # Use base move category
                if move_data:
                    user._z_move_category = move_data.get("category", "physical")
                else:
                    user._z_move_category = "physical"
        else:
            # Use base move category
            if move_data:
                user._z_move_category = move_data.get("category", "physical")
            else:
                user._z_move_category = "physical"
        
        move_name = z_move_name
    else:
        # Clear any previous Z-Move flags
        if hasattr(user, '_is_z_move'):
            delattr(user, '_is_z_move')
        if hasattr(user, '_original_move_name'):
            delattr(user, '_original_move_name')
        if hasattr(user, '_z_move_name'):
            delattr(user, '_z_move_name')
        if hasattr(user, '_z_move_category'):
            delattr(user, '_z_move_category')
    
    # === DYNAMAX CHECK: Convert moves to Max Moves ===
    is_max_move = False
    max_move_name = move_name
    original_move_for_max = move_name
    
    if user.dynamaxed:
        
        generation = get_generation(field_effects=field_effects)
        
        # Only Gen 8+ can use Dynamax
        if generation >= 8:
            is_max_move = True
            move_data = get_move(move_name, generation=generation_for_move_data, battle_state=battle_state)
            # Get actual move type accounting for type changes (Multi-Attack, Weather Ball, -ate abilities, etc.)
            move_type = get_actual_move_type_for_max_move(move_name, user, field_effects) if move_data else "Normal"
            is_gmax = user.is_gigantamax and can_gigantamax(user.species, user)
            max_move_name = get_max_move_name(move_name, user.species, move_type, is_gmax)
        else:
            is_max_move = False
            max_move_name = move_name
    
    # Use Max Move name if this is a Max Move
    if is_max_move:
        user._is_max_move = True
        user._original_move_name_max = original_move_for_max
        user._max_move_name = max_move_name
        move_name = max_move_name
    else:
        # Clear any previous Max Move flags
        if hasattr(user, '_is_max_move'):
            delattr(user, '_is_max_move')
        if hasattr(user, '_original_move_name_max'):
            delattr(user, '_original_move_name_max')
        if hasattr(user, '_max_move_name'):
            delattr(user, '_max_move_name')
    
    move_lower = normalized_move = move_name.lower().replace(" ", "-")
    move_effect = get_move_secondary_effect(move_name) or {}
    
    # === DAMAGE-RETURN MOVES (Counter, Mirror Coat, Metal Burst) - CHECK EARLY ===
    # These must be checked BEFORE Taunt/status move blocking since they have 0 power
    # but are not pure status moves - they return damage
    if move_lower in ["counter", "mirror-coat", "metal-burst"]:
        # Store damage tracking before Counter overwrites it (Counter doesn't deal damage through normal flow)
        # But we need to track Counter's damage on the target for future Counter/Mirror Coat uses
        damage_dealt, counter_msg = sm.apply_counter_family(move_name, user, target, field_effects=field_effects, battle_state=battle_state)
        if damage_dealt > 0:
            target.hp = max(0, target.hp - damage_dealt)
            # Track Counter's damage on target for future Counter/Mirror Coat
            target._last_damage_taken = damage_dealt
            target._last_damage_category = "physical"  # Counter is always physical
            target._last_move_that_hit = move_name
            target._last_move_type_hit_by = "Fighting"  # Counter is Fighting-type
            if not hasattr(target, '_last_damage_hit_substitute'):
                target._last_damage_hit_substitute = False
            return f"**{user.species}** used **{move_name}**!\n{counter_msg}\n└ **{damage_dealt}** damage to {target.species}"
        else:
            return f"**{user.species}** used **{move_name}**!\n{counter_msg}"
    
    def _release_sky_drop_state(attacker: Mon, release_target: Optional[Mon] = None) -> None:
        target_ref = release_target or getattr(attacker, '_sky_drop_target', None)
        if not target_ref:
            return

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

        if hasattr(attacker, '_sky_drop_target'):
            delattr(attacker, '_sky_drop_target')
    
    if move_lower != "ally-switch" and hasattr(user, '_consecutive_ally_switches'):
        user._consecutive_ally_switches = 0

    # === TAUNT: Block status moves (including same-turn application) ===
    pending_taunt = getattr(user, "_taunt_pending", False)
    is_taunted = (user.taunted and user.taunt_turns > 0) or pending_taunt

    if not is_z_move and is_taunted:
        normalized_base_move = original_move_name.lower().replace(" ", "-")
        if normalized_base_move != "struggle":
            base_move_data = get_move(normalized_base_move, generation=generation_for_move_data, battle_state=battle_state)
            base_move_effect = get_move_secondary_effect(original_move_name) or {}
            base_category = ""
            base_power_raw: Optional[Any] = None
            if base_move_data:
                base_category = (base_move_data.get("damage_class") or base_move_data.get("category") or "").lower()
                base_power_raw = base_move_data.get("power")
            base_power = base_power_raw if isinstance(base_power_raw, (int, float)) else 0
            variable_power = bool(base_move_effect.get("variable_power"))
            is_status_move = base_category == "status" or (base_power <= 0 and not variable_power)

            # Gen V+: Me First is not affected by Taunt
            is_me_first = normalized_base_move == "me-first"
            generation = get_generation(field_effects=field_effects) if field_effects else 9
            
            if is_status_move and not (generation >= 5 and is_me_first):
                if hasattr(user, "_last_move_failed"):
                    user._last_move_failed = True
                if pending_taunt:
                    user._taunt_pending = False
                    if hasattr(user, "_taunt_applied_turn"):
                        user._taunt_applied_turn = None
                handle_rollout_failure(user, normalized_base_move in ROLLOUT_MOVES)
                user_name = format_species_name(user.species)
                if getattr(user, 'shiny', False):
                    user_name = f"★ {user_name}"
                move_parts = original_move_name.replace("-", " ").replace("_", " ").split()
                formatted_move = " ".join(part.capitalize() for part in move_parts) if move_parts else original_move_name.capitalize()
                return f"**{user_name}** used **{formatted_move}**!\nBut it failed!"

            # Clear pending flag after the first move attempt post-Taunt
            if pending_taunt and hasattr(user, "_taunt_pending"):
                user._taunt_pending = False
        elif pending_taunt and hasattr(user, "_taunt_pending"):
            user._taunt_pending = False

    # Explosion-style moves are blocked by Damp before any other processing
    explosion_blockable_moves = {"explosion", "self-destruct", "selfdestruct", "mind-blown", "misty-explosion"}
    if move_lower in explosion_blockable_moves:
        all_mons_for_damp = []
        if battle_state:
            parties = []
            if hasattr(battle_state, 'p1_party'):
                parties.append(battle_state.p1_party)
            if hasattr(battle_state, 'p2_party'):
                parties.append(battle_state.p2_party)
            for party in parties:
                if party:
                    for mon in party:
                        if mon and mon not in all_mons_for_damp:
                            all_mons_for_damp.append(mon)
        if not all_mons_for_damp:
            for mon in (user, target):
                if mon and mon not in all_mons_for_damp:
                    all_mons_for_damp.append(mon)
        blocked, damp_msg = is_explosion_blocked(all_mons_for_damp, move_name)
        if blocked:
            if hasattr(user, '_last_move_failed'):
                user._last_move_failed = True
            return f"**{user.species}** used **{move_name}**!\n{damp_msg}"
    
    # === SOUNDPROOF: Immune to sound moves ===
    # Check if this is a sound move
    sound_moves = [
        "alluring-voice", "boomburst", "bug-buzz", "chatter", "clanging-scales", "clangorous-soul",
        "clangorous-soulblaze", "confide", "disarming-voice", "echoed-voice", "eerie-spell", "grass-whistle",
        "growl", "heal-bell", "howl", "hyper-voice", "metal-sound", "noble-roar", "overdrive",
        "parting-shot", "perish-song", "psychic-noise", "relic-song", "roar", "round", "screech", "shadow-panic",
        "sing", "snarl", "snore", "sparkling-aria", "supersonic", "torch-song", "uproar"
    ]
    is_sound_move_early = move_lower in sound_moves
    if not is_sound_move_early:
        # Also check move_mechanics and move_effects
        move_mechanics_early = get_move_mechanics(move_name, battle_state)
        if move_mechanics_early and move_mechanics_early.get('is_sound_move'):
            is_sound_move_early = True
        else:
            secondary_effect_early = get_move_secondary_effect(move_name)
            if secondary_effect_early.get("sound_move", False):
                is_sound_move_early = True
    
    if is_sound_move_early and target:
        generation_soundproof = get_generation(field_effects=field_effects, battle_state=battle_state)
        target_ability_soundproof = normalize_ability_name(target.ability or "")
        
        # Gen VIII+: User is not immune to their own sound moves
        # Other Pokémon with Soundproof are still immune
        if target_ability_soundproof == "soundproof":
            if generation_soundproof >= 8 and target == user:
                # Gen VIII+: User is affected even with Soundproof
                pass
            else:
                # Soundproof blocks sound moves
                if hasattr(user, '_last_move_failed'):
                    user._last_move_failed = True
                ability_name = (target.ability or "Soundproof").replace("-", " ").title()
                return f"**{user.species}** used **{move_name}**!\n{target.species}'s {ability_name} blocked the sound!"

    if move_lower == "sky-drop":
        gen_sd = get_generation(field_effects=field_effects, battle_state=battle_state)

        if gen_sd >= 8:
            user._last_move_failed = True
            return f"**{user.species}** used **{move_name}**!\nBut it failed! (Cannot be selected in Gen VIII+)"

        if field_effects and getattr(field_effects, 'gravity', False):
            user._last_move_failed = True
            return f"**{user.species}** used **{move_name}**!\nBut it failed! (Gravity prevents it!)"

        if target is None or target.hp <= 0 or target is user:
            user._last_move_failed = True
            return f"**{user.species}** used **{move_name}**!\nBut it failed!"

        if getattr(target, 'substitute', None):
            user._last_move_failed = True
            return f"**{user.species}** used **{move_name}**!\nBut it failed! (The target is protected by its substitute)"

        if getattr(target, 'invulnerable', False):
            user._last_move_failed = True
            return f"**{user.species}** used **{move_name}**!\nBut it failed!"

        if getattr(target, 'dynamaxed', False):
            user._last_move_failed = True
            return f"**{user.species}** used **{move_name}**!\nBut it failed! (The target is too massive!)"

        if gen_sd >= 6:
            target_weight = _get_effective_weight(target)
            if target_weight >= 200:
                user._last_move_failed = True
                return f"**{user.species}** used **{move_name}**!\nBut it failed! (The target is too heavy!)"

    if move_effect.get("fails_in_gravity") and field_effects and getattr(field_effects, 'gravity', False):
        user._last_move_failed = True
        return f"**{user.species}** used **{move_name}**!\nBut it failed! (Gravity prevents it!)"

    # === SNORE: Only usable while asleep (or with Comatose) ===
    if move_lower == "snore":
        is_asleep_snore = (user.status and user.status.lower() in ["slp", "sleep"])
        has_comatose_snore = False
        user_ability_snore = normalize_ability_name(user.ability or "")
        if user_ability_snore == "comatose":
            has_comatose_snore = True
        
        if not is_asleep_snore and not has_comatose_snore:
            return f"**{user.species}** used **{move_name}**!\nBut it failed! ({user.species} must be asleep)"
    
    # === DREAM EATER: Only works on sleeping targets (or Comatose) (Must be checked BEFORE damage calculation) ===
    if move_lower == "dream-eater":
        # Check Heal Block first (prevents Dream Eater from being used)
        is_z_move_dream = hasattr(user, '_is_z_move') and user._is_z_move
        if hasattr(user, 'heal_blocked') and getattr(user, 'heal_blocked', 0) > 0 and not is_z_move_dream:
            user._last_move_failed = True
            return f"**{user.species}** used **{move_name}**!\nBut it failed! (Heal Block prevents Dream Eater)"
        
        # Check if target is asleep or has Comatose
        is_asleep_dream = (target.status and target.status.lower() in ["slp", "sleep"])
        has_comatose_dream = False
        target_ability_dream = normalize_ability_name(target.ability or "")
        if target_ability_dream == "comatose":
            has_comatose_dream = True
        
        if not is_asleep_dream and not has_comatose_dream:
            user._last_move_failed = True
            return f"**{user.species}** used **{move_name}**!\nBut it failed! (The target must be asleep)"
        
        # Generation-specific substitute checks
        generation_dream = get_generation(field_effects=field_effects, battle_state=battle_state)
        target_has_substitute_dream = hasattr(target, 'substitute') and target.substitute
        
        if target_has_substitute_dream:
            if generation_dream == 1:
                # Gen I: Always miss if substitute (Japanese/Stadium behavior)
                user._last_move_failed = True
                return f"**{user.species}** used **{move_name}**!\nBut it failed! (The target has a substitute)"
            elif generation_dream <= 4:
                # Gen II-IV: Dream Eater fails if substitute
                user._last_move_failed = True
                return f"**{user.species}** used **{move_name}**!\nBut it failed! (The target has a substitute)"
            # Gen V+: Can hit substitute and heal properly (no fail check)
    
    # === CHECK SPECIAL MOVE CONDITIONS ===
    
    # Fake Out / First Impression (only work first turn)
    can_use, fail_msg = sm.check_fake_out_family(move_name, user, battle_state)
    if not can_use:
        return f"**{user.species}** used **{move_name}**!\n{fail_msg}"
    
    # Sucker Punch (only works if target is attacking)
    can_use, fail_msg = sm.check_sucker_punch(move_name, user, target, target_choice)
    if not can_use:
        return f"**{user.species}** used **{move_name}**!\n{fail_msg}"
    
    # High Jump Kick: Gen IV+ cannot be used if Gravity is in effect
    if move_lower == "high-jump-kick":
        generation = get_generation(field_effects=field_effects)
        if generation >= 4:
            if field_effects and getattr(field_effects, 'gravity', False):
                return f"**{user.species}** used **{move_name}**!\nBut it failed! (Gravity prevents High Jump Kick)"
    
    # Jump Kick: Gen IV+ cannot be used if Gravity is in effect, Gen VIII+ banned
    if move_lower == "jump-kick":
        gen_jk = get_generation(field_effects=field_effects, battle_state=battle_state)
        if gen_jk >= 8:
            return f"**{user.species}** used **{move_name}**!\nBut it failed! (Cannot be selected in Gen VIII+)"
        if gen_jk >= 4:
            if field_effects and getattr(field_effects, 'gravity', False):
                return f"**{user.species}** used **{move_name}**!\nBut it failed! (Gravity prevents Jump Kick)"
    
    if move_lower == "burn-up":
        current_types = {t for t in user.types if t}
        if "Fire" not in current_types:
            if hasattr(user, '_last_move_failed'):
                user._last_move_failed = True
            return f"**{user.species}** used **{move_name}**!\nBut it failed!"
    
    # Rolling Kick: Gen VIII+ banned
    if move_lower == "rolling-kick":
        gen_rk = get_generation(field_effects=field_effects, battle_state=battle_state)
        if gen_rk >= 8:
            return f"**{user.species}** used **{move_name}**!\nBut it failed! (Cannot be selected in Gen VIII+)"
    
    # Ice Ball: Gen VIII+ banned
    if move_lower == "ice-ball":
        gen_ib = get_generation(field_effects=field_effects, battle_state=battle_state)
        if gen_ib >= 8:
            return f"**{user.species}** used **{move_name}**!\nBut it failed! (Cannot be selected in Gen VIII+)"
    
    # Needle Arm: Gen VIII+ banned
    if move_lower == "needle-arm":
        gen_na = get_generation(field_effects=field_effects, battle_state=battle_state)
        if gen_na >= 8:
            return f"**{user.species}** used **{move_name}**!\nBut it failed! (Cannot be selected in Gen VIII+)"
    
    # Sky Uppercut: Gen VIII+ banned
    if move_lower == "sky-uppercut":
        gen_su = get_generation(field_effects=field_effects, battle_state=battle_state)
        if gen_su >= 8:
            return f"**{user.species}** used **{move_name}**!\nBut it failed! (Cannot be selected in Gen VIII+)"
    
    # Signal Beam: Gen VIII+ banned
    if move_lower == "signal-beam":
        gen_sb = get_generation(field_effects=field_effects, battle_state=battle_state)
        if gen_sb >= 8:
            return f"**{user.species}** used **{move_name}**!\nBut it failed! (Cannot be selected in Gen VIII+)"
    
    # Silver Wind: Gen VIII+ banned
    if move_lower == "silver-wind":
        gen_sw = get_generation(field_effects=field_effects, battle_state=battle_state)
        if gen_sw >= 8:
            return f"**{user.species}** used **{move_name}**!\nBut it failed! (Cannot be selected in Gen VIII+)"
    
    # Grass Whistle: Gen VIII+ banned
    if move_lower == "grass-whistle":
        gen_gw = get_generation(field_effects=field_effects, battle_state=battle_state)
        if gen_gw >= 8:
            return f"**{user.species}** used **{move_name}**!\nBut it failed! (Cannot be selected in Gen VIII+)"
    
    # Odor Sleuth: Gen VIII+ banned
    if move_lower == "odor-sleuth":
        gen_os = get_generation(field_effects=field_effects, battle_state=battle_state)
        if gen_os >= 8:
            return f"**{user.species}** used **{move_name}**!\nBut it failed! (Cannot be selected in Gen VIII+)"
    
    # Aromatherapy: Gen IX banned
    if move_lower == "aromatherapy":
        gen_at = get_generation(field_effects=field_effects, battle_state=battle_state)
        if gen_at >= 9:
            return f"**{user.species}** used **{move_name}**!\nBut it failed! (Cannot be selected in Gen IX+)"
    
    # === PRANKSTER: Gen 7+ Dark-types are immune to Prankster status moves ===
    user_ability_check = normalize_ability_name(user.ability or "")
    if user_ability_check == "prankster":
        generation = get_generation(field_effects=field_effects)
        
        if generation >= 7:
            # Check if move is a status move
            mv_data = load_move(move_name, generation=generation_for_move_data, battle_state=battle_state)
            if mv_data and mv_data.get("damage_class") == "status":
                # Check if target is Dark-type
                target_types = [target.types[0]]
                if len(target.types) > 1 and target.types[1]:
                    target_types.append(target.types[1])
                
                if "Dark" in target_types:
                    return f"**{user.species}** used **{move_name}**!\nIt doesn't affect the opposing {target.species}..."
    
    # === SPECIAL REQUIREMENT MOVES ===
    
    # Last Resort (must have used all other moves first)
    if move_lower == "last-resort":
        can_use, fail_msg = can_use_last_resort(user)
        if not can_use:
            return f"**{user.species}** used **{move_name}**!\n{fail_msg}"
    
    # Belch (must have consumed a Berry)
    if move_lower == "belch":
        can_use, fail_msg = can_use_belch(user)
        if not can_use:
            return f"**{user.species}** used **{move_name}**!\n{fail_msg}"
    
    # Track move usage for Last Resort
    if not hasattr(user, '_moves_used_this_battle'):
        user._moves_used_this_battle = []
    if move_lower not in user._moves_used_this_battle:
        user._moves_used_this_battle.append(move_lower)
    
    # === ARCEUS PLATE TYPE-CHANGING ===
    # Arceus changes type based on held Plate (permanent, not just during move)
    if "arceus" in user.species.lower() and user.item:
        item_data = get_item_effect(normalize_item_name(user.item))
        
        if item_data.get("arceus") and item_data.get("changes_arceus_type"):
            # Skip PLA-only items (Blank Plate, Legend Plate)
            if item_data.get("legends_arceus"):
                pass  # Skip PLA-only items
            else:
                plate_type = item_data["changes_arceus_type"]
                if plate_type and plate_type not in user.types:
                    # Change Arceus to the Plate's type (once per switch-in)
                    if not hasattr(user, '_plate_type_set'):
                        user.types = (plate_type, None)  # Becomes mono-type
                        user._plate_type_set = True
    
    # === PROTEAN/LIBERO: Change type to move's type (once per switch-in) ===
    user_ability = normalize_ability_name(user.ability or "")
    user_ability_data = ABILITY_EFFECTS.get(user_ability, {})
    
    protean_msg = ""
    if user_ability_data.get("type_change_before_move"):
        generation = get_generation(field_effects=field_effects)
        
        # Gen 8: Always changes type (no restriction)
        # Gen 9+: Only once per switch-in
        can_activate = True
        if generation >= 9:
            if hasattr(user, '_protean_used') and user._protean_used:
                can_activate = False
        
        if can_activate:
            mv_data = load_move(move_name, generation=generation_for_move_data, battle_state=battle_state)
            if mv_data:
                move_type = mv_data.get("type", "Normal")
                # Only change if not already that type
                if move_type not in user.types:
                    user.types = (move_type, None)  # Becomes mono-type
                    ability_display = user.ability.replace("-", " ").title() if user.ability else "Ability"
                    protean_msg = f"**{user.species}'s {ability_display}!**\n{user.species} became {move_type}-type!\n\n"
                    # Mark as used in Gen 9+
                    if generation >= 9:
                        user._protean_used = True
    
    # === Z-MOVES: Bypass Taunt, Disable, Torment, Encore, Imprison, Heal Block ===
    is_z_move = hasattr(user, '_is_z_move') and user._is_z_move
    
    # Z-Moves ignore these restrictions when executing (but restrictions may still prevent selection)
    # Note: If forced to Struggle (e.g., Taunt + only status moves), Z-Moves cannot be used
    
    # === ASSAULT VEST: Blocks status moves (but not Z-Moves) ===
    user_item_data = get_item_effect(user.item or "")
    if user_item_data.get("blocks_status_moves") and not is_z_move:
        mv_data = load_move(move_name, generation=generation_for_move_data, battle_state=battle_state)
        if mv_data and mv_data.get("damage_class") == "status":
            return f"**{user.species}** can't use **{move_name}** while holding Assault Vest!"
    
    # === SAFETY GOGGLES / OVERCOAT: Block powder moves ===
    # Check if move is a powder move
    move_lower = move_name.lower()
    powder_moves = ["spore", "stun-spore", "sleep-powder", "poison-powder", "cotton-spore", "rage-powder", "powder", "magic-powder"]
    is_powder_move = any(pm in move_lower for pm in powder_moves)
    
    if is_powder_move:
        # Determine generation context once
        gen_powder = generation_check
        target_types = [t.strip().title() if t else None for t in getattr(target, 'types', (None, None))]
        target_ability = normalize_ability_name(target.ability or "")
        target_ability_data = get_ability_effect(target_ability)
        
        # Safety Goggles blocks powder moves (Gen 6+)
        if item_is_active(target):
            target_item_data = get_item_effect(normalize_item_name(target.item))
            if target_item_data.get("powder_immunity") and gen_powder >= 6:
                return f"**{target.species}**'s Safety Goggles protected it from {move_name}!"
        
        # Overcoat blocks powder moves (Gen 6+)
        if target_ability_data.get("powder_move_immunity") and gen_powder >= 6:
            ability_name = target.ability.replace("-", " ").title()
            return f"**{target.species}**'s {ability_name} protected it from {move_name}!"
        
        # Generation-specific powder move immunities
        if move_lower == "poison-powder":
            # Gen I: Only Poison immunity
            if gen_powder == 1:
                if "Poison" in target_types:
                    return f"It doesn't affect {target.species}..."
            # Gen II: Poison and Steel immunity
            elif gen_powder == 2:
                if "Poison" in target_types or "Steel" in target_types:
                    return f"It doesn't affect {target.species}..."
            # Gen III-V: Immunity ability blocks
            elif 3 <= gen_powder <= 5:
                if target_ability == "immunity":
                    return f"**{target.species}**'s Immunity prevented poisoning!"
            # Gen VI+: Grass immunity, Overcoat, Safety Goggles (already checked above)
            elif gen_powder >= 6:
                if "Grass" in target_types:
                    return f"It doesn't affect {target.species}..."
        
        elif move_lower == "stun-spore":
            # Gen III-V: Limber blocks
            if 3 <= gen_powder <= 5:
                if target_ability == "limber":
                    return f"**{target.species}**'s Limber prevented paralysis!"
            # Gen VI+: Grass and Electric immunity, Overcoat, Safety Goggles
            elif gen_powder >= 6:
                if "Grass" in target_types or "Electric" in target_types:
                    return f"It doesn't affect {target.species}..."
        
        elif move_lower == "sleep-powder":
            # Gen III-V: Insomnia, Vital Spirit, Sap Sipper block
            if 3 <= gen_powder <= 5:
                if target_ability in ["insomnia", "vital-spirit", "sap-sipper"]:
                    ability_name = target.ability.replace("-", " ").title()
                    return f"**{target.species}**'s {ability_name} prevented sleep!"
            # Gen VI+: Grass immunity, Overcoat, Safety Goggles, Sweet Veil
            elif gen_powder >= 6:
                if "Grass" in target_types:
                    return f"It doesn't affect {target.species}..."
                # Sweet Veil: Team immunity to sleep (handled separately, but check here too)
                if target_ability_data.get("prevents_sleep"):
                    ability_name = target.ability.replace("-", " ").title()
                    return f"**{target.species}**'s {ability_name} prevented sleep!"
        
        # Generic Grass-type immunity for other powder moves (Gen 6+)
        elif gen_powder >= 6 and "Grass" in target_types:
            return f"It doesn't affect {target.species}..."
    
    # === TWO-TURN MOVES (Fly, Dig, Dive, Bounce, Phantom Force, Shadow Force, etc.) ===
    mind_blown_hp_loss = 0
    mind_blown_fainted = False
    skip_standard_recoil = False
    if move_effect.get("mind_blown_hp_loss"):
        skip_standard_recoil = True
        if user.hp > 0:
            ability_norm_mb = normalize_ability_name(user.ability or "")
            ability_suppressed_mb = getattr(user, '_ability_suppressed', False)
            ability_data_mb = get_ability_effect(ability_norm_mb)
            magic_guard_active = ability_data_mb.get("no_indirect_damage", False) and not ability_suppressed_mb
            if not magic_guard_active:
                hp_loss = (user.max_hp + 1) // 2
                hp_loss = min(hp_loss, user.hp)
                if hp_loss > 0:
                    user.hp = max(0, user.hp - hp_loss)
                    mind_blown_hp_loss = hp_loss
                    if user.hp <= 0:
                        mind_blown_fainted = True

    normalized_move = move_name.lower().replace(" ", "-")
    if normalized_move == "recharge":
        if hasattr(user, '_last_move_failed'):
            user._last_move_failed = False
        # Clear recharge state after recharge turn completes (similar to charging_move)
        if hasattr(user, 'recharging_move'):
            user.recharging_move = None
        if hasattr(user, 'must_recharge'):
            user.must_recharge = False
        return f"**{user.species}** must recharge!"

    spectral_thief_msgs: List[str] = []
    pre_move_msgs: List[str] = []
    if move_lower == "spectral-thief" and target and hasattr(target, 'stages'):
        positive_stats = {stat: stage for stat, stage in target.stages.items() if stage > 0}
        if positive_stats:
            for stat, amount in positive_stats.items():
                target.stages[stat] = max(-6, min(6, target.stages[stat] - amount))
            target._stats_lowered_this_turn = True
            spectral_thief_msgs.append(f"{user.species} stole {target.species}'s stat boosts!")
            gain_msgs = modify_stages(user, positive_stats, caused_by_opponent=False, field_effects=field_effects)
            for gain_msg in gain_msgs:
                spectral_thief_msgs.append(gain_msg)
    if move_effect.get("semi_invulnerable"):
        # Check if user is already charging this move
        if user.charging_move == move_lower:
            # Turn 2: Execute the attack
            user.charging_move = None
            user.invulnerable = False
            user.invulnerable_type = None
            if move_lower == "sky-drop":
                release_target = getattr(user, '_sky_drop_target', None) or target
                _release_sky_drop_state(user, release_target)
            # Continue with damage calculation below
        else:
            # === POWER HERB: Skip charge turn for charging moves (Gen 4+) ===
            skip_charge = False
            if item_is_active(user) and user.item:
                u_item_ph = normalize_item_name(user.item)
                u_item_data_ph = get_item_effect(u_item_ph)
                gen_ph = get_generation(field_effects=field_effects)
                if u_item_data_ph.get("skip_charge_turn") and gen_ph >= 4:
                    charging_moves_list = u_item_data_ph.get("charging_moves", [])
                    if move_lower in charging_moves_list:
                        # Check for exceptions (Solar Beam/Blade in sun, Electro Shot in rain)
                        weather = getattr(field_effects, 'weather', None) if field_effects else None
                        if move_lower in ["solar-beam", "solar-blade"] and weather == "sun":
                            # Power Herb not consumed if Solar moves in sun
                            skip_charge = True
                        elif move_lower == "electro-shot" and weather == "rain":
                            # Power Herb not consumed if Electro Shot in rain
                            skip_charge = True
                        else:
                            # Consume Power Herb and skip charge
                            user.item = None
                            skip_charge = True
            
            if skip_charge:
                # Execute immediately without charging
                user.charging_move = None
                user.invulnerable = False
                user.invulnerable_type = None
                # Continue with damage calculation below
            else:
                # Turn 1: Start charging, become invulnerable
                user.charging_move = move_lower
                user.invulnerable = True
                if move_lower == "sky-drop" and target:
                    user._sky_drop_target = target
                    target._sky_drop_lifted = True
                    target._sky_drop_lifted_by = user
                    target._sky_drop_invulnerable = True
                    target._sky_drop_prev_invulnerable = getattr(target, 'invulnerable', False)
                    target._sky_drop_prev_invulnerable_type = getattr(target, 'invulnerable_type', None)
                    target.invulnerable = True
                    target.invulnerable_type = "flying"
                    target._sky_drop_cannot_move = True
            
            # Set invulnerability type based on move
            invuln_types = {
                "fly": "flying",
                "bounce": "flying",
                "sky-drop": "flying",
                "dig": "underground",
                "dive": "underwater",
                "phantom-force": "vanished",
                "shadow-force": "vanished"
            }
            user.invulnerable_type = invuln_types.get(move_lower, "charging")
            
            # Display charging message
            user_name = format_species_name(user.species)
            if getattr(user, 'shiny', False):
                user_name = f"★ {user_name}"
            target_name = format_species_name(target.species)
            if getattr(target, 'shiny', False):
                target_name = f"★ {target_name}"
            charge_msgs = {
                "fly": f"{user_name} flew up high!",
                "bounce": f"{user_name} sprang up!",
                "dig": f"{user_name} burrowed underground!",
                "dive": f"{user_name} dove underwater!",
                "phantom-force": f"{user_name} vanished instantly!",
                "shadow-force": f"{user_name} vanished instantly!",
                "sky-drop": f"{user_name} took {target_name} into the sky!",
                "solar-beam": f"{user_name} absorbed light!",
                "solar-blade": f"{user_name} absorbed light!",
                "razor-wind": f"{user_name} whipped up a whirlwind!",
                "skull-bash": f"{user_name} lowered its head!",
                "sky-attack": f"{user_name} became cloaked in a harsh light!" if generation_check >= 4 else f"{user_name} is glowing!",
                "freeze-shock": f"{user_name} became cloaked in a freezing light!",
                "ice-burn": f"{user_name} became cloaked in freezing air!",
                "geomancy": f"{user_name} is absorbing power!",
                "meteor-beam": f"{user_name} is overflowing with space power!"
            }
            charge_msg = charge_msgs.get(move_lower, f"{user_name} is charging!")
            # Format move name
            move_parts = move_name.replace("-", " ").replace("_", " ").split()
            formatted_move = " ".join(part.capitalize() for part in move_parts) if move_parts else move_name.capitalize()
            return f"**{user_name}** used **{formatted_move}**!\n{charge_msg}"
    
    # === DELAYED EFFECT MOVES (Must be checked BEFORE damage calculation) ===
    # Future Sight / Doom Desire
    if move_lower in ["future-sight", "doom-desire"] and battle_state:
        msg = sm.setup_future_sight(user, target, move_name, battle_state, id(target))
        return f"**{user.species}** used **{move_name}**!\n{msg}"
    
    # === MULTI-HIT MOVES ===
    if mechanics and mechanics['is_multi_hit']:
        hit_count = get_multi_hit_count(move_name, mechanics.get('meta', {}), user.ability, field_effects=field_effects, user=user)
        
        # Loaded Dice: multistrike moves hit at least 4 times (if possible) (Gen 9+)
        if item_is_active(user) and user.item:
            u_item = normalize_item_name(user.item)
            u_item_data = get_item_effect(u_item)
            gen_ld = get_generation(field_effects=field_effects)
            if u_item_data.get("multistrike_min_4") and gen_ld >= 9:
                # Minimum 4 hits if move can hit at least 4 times
                if hit_count >= 2:  # Only affects variable-hit moves (not fixed-hit like Triple Kick)
                    hit_count = max(4, hit_count)
        
        msg = f"**{user.species}** used **{move_name}**!"
        if pre_move_msgs:
            for line in pre_move_msgs:
                msg += f"\n{line}"
        if spectral_thief_msgs:
            for st_msg in spectral_thief_msgs:
                msg += f"\n{st_msg}"
        
        # Store target's HP before multi-hit loop (for damage percentage calculation)
        old_hp = target.hp
        
        total_damage = 0
        actual_hits = 0
        
        # Get move data for contact checks (use battle cache)
        move_obj = load_move(move_name, generation=getattr(battle_state, "gen", None), battle_state=battle_state)
        mechanics_mh = mechanics
        # Ensure move_obj has contact flag (check mechanics if needed)
        if move_obj and move_obj.get("contact", 0) != 1 and mechanics_mh:
            if mechanics_mh.get("is_contact_move", False):
                # Create a copy with contact flag set
                move_obj = move_obj.copy() if move_obj else {}
                move_obj["contact"] = 1
        
        for hit_num in range(hit_count):
            # Each hit can miss independently for Population Bomb
            # Scale Shot continues attacking after breaking a substitute
            dmg, meta, extra = damage(user, target, move_name, field_effects, target_side, user_side, is_moving_last)
            
            # === METRONOME: Reset on unsuccessful use (miss, immunity) ===
            if item_is_active(user) and user.item:
                u_item_mt2 = normalize_item_name(user.item)
                u_item_data_mt2 = get_item_effect(u_item_mt2)
                gen_mt2 = get_generation(field_effects=field_effects)
                if u_item_data_mt2.get("consecutive_use_boost") and gen_mt2 >= 4:
                    if meta.get("miss") or meta.get("immune") or meta.get("invulnerable"):
                        # Reset Metronome on miss/immunity
                        if hasattr(user, '_metronome_last_move'):
                            user._metronome_last_move = None
                            user._metronome_consecutive = 0

            # Minimize vulnerability: double damage for specific moves when target minimized
            if dmg > 0 and hasattr(target, '_minimized') and target._minimized:
                meff = get_move_secondary_effect(move_name)
                if meff.get('doubled_minimize'):
                    dmg *= 2

            # Type-resist berries: halve super effective hit of matching type (Ripen -> quarter)
            if dmg > 0 and item_is_active(target) and target.item:
                t_item = normalize_item_name(target.item)
                t_item_data = get_item_effect(t_item)
                resist_type = t_item_data.get("resist_once")
                if resist_type:
                    # Load move data to get type (use battle cache)
                    move_data = load_move(move_name, generation=getattr(battle_state, "gen", None), battle_state=battle_state)
                    move_t = meta.get("type", move_data.get("type", "Normal") if move_data else "Normal")
                    mult_check, _ = type_multiplier(move_t, target, user=user)
                    # Chilan Berry: halves Normal-type regardless of effectiveness
                    # Gen IV: Activates for Struggle (typeless). Gen V+: Does not activate for Struggle
                    is_chilan = (t_item == "chilan-berry")
                    is_struggle = normalized_move == "struggle"
                    gen_chilan = get_generation(field_effects=field_effects)
                    
                    # Gen IV: Chilan activates for Struggle (even though it's typeless)
                    if is_chilan and is_struggle and gen_chilan == 4:
                        should_apply = True
                    elif is_chilan and move_t == "Normal":
                        should_apply = True
                    else:
                        should_apply = (mult_check >= 2.0 and move_t == resist_type)
                    if should_apply:
                        # Ripen doubles berry effect
                        ripen_mult = 0.5
                        t_ability = normalize_ability_name(target.ability or "")
                        t_ability_data = get_ability_effect(t_ability)
                        if t_ability_data.get("berry_effect_mult"):
                            ripen_mult *= t_ability_data["berry_effect_mult"]  # 0.25 with Ripen
                        dmg = max(1, int(dmg * ripen_mult))
                        target._last_consumed_berry = target.item
                        target.item = None
            
            if meta.get("miss"):
                # Population Bomb and similar moves can miss individual hits
                break
            
            if meta.get("status"):
                # Status moves shouldn't be multi-hit
                continue
            
            # Check for immunity or no effect
            if dmg == 0:
                mult, _ = type_multiplier(meta.get("type", "Normal"), target, user=user)
                if mult == 0 or actual_hits == 0:
                    msg += f"\nIt had **no effect** on {target.species}!"
                    return msg
                break
            
            # Apply damage
            # Dummy Magikarp is immortal - heals to 999 HP when it reaches 0
            old_target_hp_hit = target.hp
            if getattr(target, '_is_dummy_magikarp', False):
                target.hp = max(0, target.hp - dmg)
                if target.hp <= 0:
                    target.hp = 999
                    target.max_hp = 999
            else:
                target.hp = max(0, target.hp - dmg)
            # Track ACTUAL damage dealt (capped by target's remaining HP) for drain moves
            actual_dmg_this_hit = old_target_hp_hit - target.hp
            total_damage += actual_dmg_this_hit
            actual_hits += 1

            if dmg > 0:
                if move_effect.get("thaws_target_on_hit") and getattr(target, 'status', None) in {"frz", "freeze"}:
                    target.status = None
                    target.status_turns = 0
                    msg += f"\n{target.species} thawed out!"
                if move_effect.get("heals_burn"):
                    if getattr(target, 'status', None) in {"brn", "burn"}:
                        target.status = None
                        target.status_turns = 0
                        msg += f"\n{target.species}'s burn was healed!"
                target._took_damage_this_turn = True
            
            # Contact effects after each hit (Static, Flame Body, etc. trigger per hit)
            contact_log = _contact_side_effects(
                attacker=user,
                defender=target,
                move_obj=move_obj,
                field_effects=field_effects,
                attacker_side=user_side,
                defender_side=target_side,
                damage_dealt=dmg
            )
            if contact_log:
                msg += "\n" + "\n".join(contact_log)
            if hasattr(target, '_endure_skip_contact'):
                target._endure_skip_contact = False
            
            # On-hit reactive abilities (Weak Armor, Stamina, etc.) trigger per hit for multi-hit moves
            if dmg > 0:
                trigger_data_hit = {
                    "damage": dmg,
                    "type": meta.get("type", "Normal"),
                    "category": meta.get("category", "physical"),
                    "is_contact": move_obj.get("contact", 0) == 1,
                    "is_crit": meta.get("crit", False),
                    "type_mult": meta.get("type_mult", 1.0),
                    "hit_substitute": meta.get("hit_substitute", False)
                }
                reactive_msgs = apply_on_hit_reactive_abilities(user, target, trigger_data_hit, battle_state)
                if reactive_msgs:
                    msg += "\n" + "\n".join(reactive_msgs)

            # Shell Bell (Gen 3): heal after each strike (1/8 of that hit's damage)
            if item_is_active(user) and user.item:
                if normalize_item_name(user.item) == "shell-bell":
                    generation = get_generation(field_effects=field_effects)
                    if generation == 3 and dmg > 0:
                        heal = max(1, dmg // 8)
                        old_hp_sb = user.hp
                        user.hp = min(user.max_hp, user.hp + heal)
                        actual_heal_sb = user.hp - old_hp_sb
                        if actual_heal_sb > 0:
                            msg += f"\n{user.species}'s Shell Bell restored HP! (+{actual_heal_sb} HP)"
            
            # Stop if target faints
            if target.hp <= 0:
                break
        
        # Enigma Berry (Gen 4+): heal when hit by super effective move
        if dmg > 0 and item_is_active(target) and target.item and target.hp > 0:
            enigma = normalize_item_name(target.item)
            if enigma == "enigma-berry":
                mult_check, _ = type_multiplier(meta.get("type", "Normal"), target, user=user)
                if mult_check >= 2.0:
                    if get_generation(field_effects=field_effects) >= 4:
                        heal = max(1, target.max_hp // 4)
                        old = target.hp
                        target.hp = min(target.max_hp, target.hp + heal)
                        actual = target.hp - old
                        if actual > 0:
                            msg += f"\n{target.species}'s Enigma Berry restored {actual} HP!"
                        target._last_consumed_berry = target.item
                        target.item = None

        # Jaboca, Rowap, Kee, Maranga (on-hit berries)
        if dmg > 0 and item_is_active(target) and target.item and target.hp > 0:
            berr = normalize_item_name(target.item)
            # Determine Ripen multiplier
            ripen_mult = 1.0
            t_ability = normalize_ability_name(target.ability or "")
            t_ability_data = get_ability_effect(t_ability)
            if t_ability_data.get("berry_effect_mult"):
                ripen_mult = t_ability_data["berry_effect_mult"]  # 2.0
            cat = (meta.get("category") or "").lower()
            if berr == "jaboca-berry" and cat == "physical":
                chip = int((target.max_hp / 8) * ripen_mult)
                chip = max(1, chip)
                user.hp = max(0, user.hp - chip)
                msg += f"\n{user.species} was hurt by {target.species}'s Jaboca Berry! (-{chip} HP)"
                target._last_consumed_berry = target.item
                target.item = None
            elif berr == "rowap-berry" and cat == "special":
                chip = int((target.max_hp / 8) * ripen_mult)
                chip = max(1, chip)
                user.hp = max(0, user.hp - chip)
                msg += f"\n{user.species} was hurt by {target.species}'s Rowap Berry! (-{chip} HP)"
                target._last_consumed_berry = target.item
                target.item = None
            elif berr == "kee-berry" and cat == "physical":
                old = target.stages.get("defn", 0)
                boost = 2 if ripen_mult > 1.0 else 1
                target.stages["defn"] = min(6, old + boost)
                msg += f"\n{target.species}'s Kee Berry {'sharply ' if boost>=2 else ''}raised its Defense!"
                target._last_consumed_berry = target.item
                target.item = None
            elif berr == "maranga-berry" and cat == "special":
                old = target.stages.get("spd", 0)
                boost = 2 if ripen_mult > 1.0 else 1
                target.stages["spd"] = min(6, old + boost)
                msg += f"\n{target.species}'s Maranga Berry {'sharply ' if boost>=2 else ''}raised its Sp. Def!"
                target._last_consumed_berry = target.item
                target.item = None

        # Build multi-hit message
        if actual_hits > 0:
            mult, ability_msg = type_multiplier(meta["type"], target, user=user)
            msg += f"\n└ Hit **{actual_hits}** time(s)!"
            
            # Calculate and show damage percentage for multi-hit moves
            actual_hp_lost = old_hp - target.hp
            hp_percent = round((actual_hp_lost / target.max_hp) * 100, 1) if target.max_hp > 0 else 0
            hp_percent = min(hp_percent, 100.0)  # Cap at 100%
            msg += f"\n└ The opposing {target.species} lost {hp_percent}% of its health!"
            
            # Effectiveness
            if mult >= 2.0:
                msg += "\n*It's super effective!*"
            elif mult <= 0.5 and mult > 0:
                msg += "\n*It's not very effective...*"
            
            # === SCALE SHOT: Stat changes after successful hits ===
            # Note: Scale Shot continues attacking after breaking a substitute (handled by loop)
            # Counter will only acknowledge the last strike (handled by _last_damage_taken being overwritten each hit)
            if move_lower == "scale-shot" and actual_hits > 0:
                # Speed +1, Defense -1 (only if move didn't miss entirely)
                scale_shot_msgs = modify_stages(user, {"spe": 1, "defn": -1}, caused_by_opponent=False, field_effects=field_effects)
                if scale_shot_msgs:
                    msg += "\n" + "\n".join(scale_shot_msgs)
            
            # Recoil/drain for multi-hit moves (calculated from total damage)
            # Struggle always has recoil, even if not marked in database
            is_struggle = move_lower == "struggle"
            if (mechanics and mechanics.get('is_recoil_move')) or is_struggle:
                user_ability_norm = normalize_ability_name(user.ability or "")
                if user_ability_norm != "rock-head":
                    old_hp_before_recoil = user.hp
                    recoil = calculate_recoil_damage(move_name, total_damage, user.max_hp, field_effects=field_effects)
                    if recoil > 0:  # Only apply if there's actual recoil damage
                        user.hp = max(0, user.hp - recoil)
                        msg += f"\n└ **{user.species}** was damaged by the recoil!"
                    
                    # === EMERGENCY EXIT from STRUGGLE RECOIL ONLY ===
                    if is_struggle and user.hp > 0:
                        user_ability_data = get_ability_effect(user_ability_norm)
                        if user_ability_data.get("switches_out_at_half_hp"):
                            hp_before_percent = (old_hp_before_recoil / user.max_hp) * 100
                            hp_after_percent = (user.hp / user.max_hp) * 100
                            
                            if hp_before_percent >= 50.0 and hp_after_percent < 50.0:
                                user._emergency_exit_triggered = True
                                ability_name = (user.ability or user_ability_norm).replace("-", " ").title()
                                msg += f"\n**{user.species}'s {ability_name}!**"
            
            if mechanics['is_drain_move']:
                move_lower_drain_mh = move_name.lower().replace(" ", "-")
                generation_drain_mh = get_generation(field_effects=field_effects)
                
                # Note: Dream Eater sleep/substitute/heal_block checks already happened at the beginning
                # Dream Eater is not a multi-hit move, so this section shouldn't be reached for it
                # This is defensive code in case of edge cases
                
                heal = calculate_drain_healing(move_name, total_damage)
                
                # Big Root: 65% for Dream Eater/Leech Life/Absorb/Mega Drain (30% boost = 50% * 1.3 = 65%)
                if user.item and "big-root" in user.item.lower().replace(" ", "-"):
                    generation_big_root = get_generation(field_effects=field_effects)
                    if generation_big_root >= 4:  # Big Root works Gen IV+
                        if move_lower_drain_mh in ["dream-eater", "leech-life", "absorb", "mega-drain"]:
                            heal = int(heal * 1.3)  # 65% total
                        else:
                            heal = int(heal * 1.3)  # Other drain moves also get 30% boost
                
                # Liquid Ooze - reverses drain (damages attacker instead of healing) - Gen III+
                target_ability_mh = normalize_ability_name(target.ability or "")
                target_ability_data_mh = get_ability_effect(target_ability_mh)
                if target_ability_data_mh.get("damages_draining_moves"):
                    if generation_drain_mh >= 3 and heal > 0:
                        user.hp = max(0, user.hp - heal)
                        msg += f"\n{target.species}'s Liquid Ooze damaged {user.species}! (-{heal} HP)"
                        if user.hp <= 0:
                            msg += f"\n{user.species} fainted!"
                else:
                    # Gen VI: Leech Life blocked by Heal Block
                    if move_lower_drain_mh == "leech-life" and generation_drain_mh >= 6:
                        if hasattr(user, 'heal_blocked') and getattr(user, 'heal_blocked', 0) > 0:
                            msg += f"\n{user.species} could not drain HP due to Heal Block!"
                        elif heal > 0:
                            user.hp = min(user.max_hp, user.hp + heal)
                            msg += f"\n{user.species} drained {heal} HP!"
                    elif heal > 0:
                        if getattr(user, 'heal_blocked', 0) == 0:
                            user.hp = min(user.max_hp, user.hp + heal)
                            msg += f"\n{user.species} drained {heal} HP!"
                        else:
                            msg += f"\n{user.species} could not drain HP due to Heal Block!"

            # Shell Bell (Gen 4+): heal once after last strike based on total damage
            if item_is_active(user) and user.item and total_damage > 0:
                if normalize_item_name(user.item) == "shell-bell":
                    generation = get_generation(field_effects=field_effects)
                    # Gen 5+: blocked by Heal Block; skip if Sheer Force boosted
                    if generation >= 5 and getattr(user, 'heal_blocked', 0):
                        pass
                    elif generation >= 5 and getattr(user, '_sheer_force_active', False):
                        pass
                    else:
                        heal = max(1, total_damage // 8)
                        old_hp_sb2 = user.hp
                        user.hp = min(user.max_hp, user.hp + heal)
                        actual_heal_sb2 = user.hp - old_hp_sb2
                        if actual_heal_sb2 > 0:
                            msg += f"\n{user.species}'s Shell Bell restored HP! (+{actual_heal_sb2} HP)"
            
            # Target fainted
            if target.hp <= 0:
                msg += f"\n{target.species} fainted!"
        
        return msg
    
    # === COUNTER/DAMAGE RETURN MOVES ===
    # Metal Burst, Comeuppance - return 1.5x damage received
    move_effect_check = get_move_secondary_effect(move_name)
    if move_effect_check.get("returns_damage"):
        if hasattr(user, '_last_damage_taken') and user._last_damage_taken > 0:
            returned_damage = int(user._last_damage_taken * 1.5)
            target.hp = max(0, target.hp - returned_damage)
            return protean_msg + f"**{user.species}** used **{move_name}**!\n{target.species} took {returned_damage} damage in retaliation!"
        else:
            return protean_msg + f"**{user.species}** used **{move_name}**!\nBut it failed!"
    
    # === PARENTAL BOND CHECK ===
    # Check if user has Parental Bond and move is eligible
    user_ability_pb = normalize_ability_name(user.ability or "")
    parental_bond_active = False
    parental_bond_hits = 1
    
    if user_ability_pb == "parental-bond":
        # Check if move is excluded from Parental Bond
        move_lower_pb = move_name.lower().replace(" ", "-")
        
        # Excluded moves (only strike once)
        excluded_moves = {
            "fling", "self-destruct", "explosion", "final-gambit",
            "uproar", "rollout", "ice-ball", "endeavor"
        }
        
        # Check OHKO moves
        is_ohko = mechanics and mechanics.get('is_ohko_move', False)
        # Check charging moves
        is_charging = mechanics and mechanics.get('is_charge_move', False)
        # Multi-hit already handled above
        
        if (move_lower_pb not in excluded_moves and not is_ohko and not is_charging):
            parental_bond_active = True
            parental_bond_hits = 2
    
    # === SINGLE HIT MOVES (OR PARENTAL BOND DOUBLE HIT) ===
    total_damage_pb = 0
    parental_bond_hit_count = 0
    parental_bond_deferred_recoil = 0  # Accumulate recoil from both hits
    
    for hit_num_pb in range(parental_bond_hits):
        # Determine Parental Bond multiplier for second hit
        pb_multiplier = 1.0
        if parental_bond_active and hit_num_pb == 1:  # Second hit
            generation = get_generation(field_effects=field_effects)
            if generation <= 6:
                pb_multiplier = 0.5  # Gen 6: 50% power
            else:
                pb_multiplier = 0.25  # Gen 7+: 25% power
        
        dmg, meta, extra = damage(user, target, move_name, field_effects, target_side, user_side, is_moving_last, pb_multiplier)
        
        # === METRONOME: Reset on unsuccessful use (miss, immunity, protection) ===
        # Only reset after first hit to avoid double-reset with Parental Bond
        if hit_num_pb == 0:
            if item_is_active(user) and user.item:
                u_item_mt = normalize_item_name(user.item)
                u_item_data_mt = get_item_effect(u_item_mt)
                gen_mt = get_generation(field_effects=field_effects)
                if u_item_data_mt.get("consecutive_use_boost") and gen_mt >= 4:
                    if meta.get("miss") or meta.get("immune") or meta.get("invulnerable"):
                        # Reset Metronome on miss/immunity
                        if hasattr(user, '_metronome_last_move'):
                            user._metronome_last_move = None
                            user._metronome_consecutive = 0
        
        # If first hit misses, don't do second hit
        if hit_num_pb == 0 and parental_bond_active and meta.get("miss"):
            break
        
        # Status moves - only process once even with Parental Bond
        if hit_num_pb == 0 and meta.get("status"):
            break
        
        # Apply damage for each hit (ONLY if Parental Bond is active, otherwise damage is applied later)
        if not meta.get("status") and not meta.get("miss"):
            actual_dmg_pb_hit = dmg  # Default to calculated damage
            if parental_bond_active:
                # For Parental Bond, apply damage immediately for each hit
                # Dummy Magikarp is immortal - heals to 999 HP when it reaches 0
                old_target_hp_pb = target.hp
                if getattr(target, '_is_dummy_magikarp', False):
                    target.hp = max(0, target.hp - dmg)
                    if target.hp <= 0:
                        target.hp = 999
                        target.max_hp = 999
                else:
                    target.hp = max(0, target.hp - dmg)
                # Track ACTUAL damage dealt (capped by target's remaining HP) for drain moves
                actual_dmg_pb_hit = old_target_hp_pb - target.hp
                if dmg > 0:
                    target._took_damage_this_turn = True
                    
                # Contact effects after each Parental Bond hit (Iron Barbs, Static, etc.)
                move_obj_pb = load_move(move_name, generation=getattr(battle_state, "gen", None), battle_state=battle_state)
                is_contact_pb = makes_contact(move_name)
                
                # Ensure move_obj has contact flag if it's a contact move
                if is_contact_pb:
                    if move_obj_pb and move_obj_pb.get("contact", 0) != 1:
                        move_obj_pb = move_obj_pb.copy()
                        move_obj_pb["contact"] = 1
                    elif not move_obj_pb:
                        move_obj_pb = {"contact": 1, "name": move_name}
                
                if is_contact_pb and move_obj_pb:
                    contact_log_pb = _contact_side_effects(
                        attacker=user,
                        defender=target,
                        move_obj=move_obj_pb,
                        field_effects=field_effects,
                        attacker_side=user_side,
                        defender_side=target_side,
                        damage_dealt=actual_dmg_pb_hit
                    )
                    if contact_log_pb:
                        msg += "\n" + "\n".join(contact_log_pb)
                    if hasattr(target, '_endure_skip_contact'):
                        target._endure_skip_contact = False
                        
            total_damage_pb += actual_dmg_pb_hit
            parental_bond_hit_count += 1
            
            # Calculate recoil for this hit but don't apply yet if Parental Bond
            # Struggle always has recoil, even if not marked in database
            if parental_bond_active:
                mechanics_pb = mechanics
                is_struggle_pb = move_name.lower().replace(" ", "-") == "struggle"
                if mechanics_pb and (mechanics_pb['is_recoil_move'] or is_struggle_pb):
                    user_ability_norm_pb = normalize_ability_name(user.ability or "")
                    if user_ability_norm_pb != "rock-head":
                        recoil_this_hit = calculate_recoil_damage(move_name, dmg, user.max_hp, field_effects=field_effects)
                        if recoil_this_hit > 0:
                            parental_bond_deferred_recoil += recoil_this_hit
            
            # Stop if target faints (only relevant for Parental Bond)
            if parental_bond_active and target.hp <= 0:
                break
    
    # If Parental Bond was active, replace dmg with total and mark as handled
    parental_bond_damage_applied = False
    parental_bond_skip_recoil = False
    parental_bond_drain_handled = False  # Track if drain healing was already applied
    if parental_bond_active and parental_bond_hit_count > 1:
        dmg = total_damage_pb
        parental_bond_damage_applied = True  # Don't apply damage again later
        parental_bond_skip_recoil = True  # Don't apply recoil in normal flow (we'll do it after)
        # Handle drain healing for Parental Bond (before regular drain section)
        if mechanics and mechanics.get('is_drain_move'):
            move_lower_drain_pb = move_name.lower().replace(" ", "-")
            generation_drain_pb = get_generation(field_effects=field_effects)
            
            # Dream Eater: Only works on sleeping targets (or Comatose)
            # Note: Sleep/substitute/heal_block checks already happened at the beginning
            # Dream Eater is not typically used with Parental Bond, but handle it defensively
            if move_lower_drain_pb == "dream-eater":
                # Verify target is still asleep (should have been checked at beginning)
                is_asleep = (target.status and target.status.lower() in ["slp", "sleep"])
                has_comatose = normalize_ability_name(target.ability or "") == "comatose"
                if is_asleep or has_comatose:
                    # Only heal if target is asleep and not blocked
                    if getattr(user, 'heal_blocked', 0) == 0:
                        drain_heal_pb = calculate_drain_healing(move_name, total_damage_pb)
                        # Big Root boost (Gen IV+): 65% for Dream Eater (30% boost = 50% * 1.3 = 65%)
                        if user.item and "big-root" in user.item.lower().replace(" ", "-"):
                            if generation_drain_pb >= 4:
                                drain_heal_pb = int(drain_heal_pb * 1.3)
                        
                        # Liquid Ooze check (reverses drain, damages attacker instead) - Gen III+
                        target_ability_pb = normalize_ability_name(target.ability or "")
                        target_ability_data_pb = get_ability_effect(target_ability_pb)
                        if generation_drain_pb >= 3 and target_ability_data_pb.get("damages_draining_moves") and drain_heal_pb > 0:
                            user.hp = max(0, user.hp - drain_heal_pb)
                            msg += f"\n{target.species}'s Liquid Ooze damaged {user.species}! (-{drain_heal_pb} HP)"
                            if user.hp <= 0:
                                msg += f"\n{user.species} fainted!"
                        elif drain_heal_pb > 0:
                            user.hp = min(user.max_hp, user.hp + drain_heal_pb)
                            msg += f"\n{user.species} drained {drain_heal_pb} HP!"
                parental_bond_drain_handled = True
            else:
                # Regular drain moves with Parental Bond
                drain_heal_pb = calculate_drain_healing(move_name, total_damage_pb)
                # Big Root boost
                if user.item and "big-root" in user.item.lower().replace(" ", "-"):
                    if generation_drain_pb >= 4:
                        drain_heal_pb = int(drain_heal_pb * 1.3)
                
                # Liquid Ooze check
                target_ability_pb = normalize_ability_name(target.ability or "")
                target_ability_data_pb = get_ability_effect(target_ability_pb)
                if generation_drain_pb >= 3 and target_ability_data_pb.get("damages_draining_moves") and drain_heal_pb > 0:
                    user.hp = max(0, user.hp - drain_heal_pb)
                    msg += f"\n{target.species}'s Liquid Ooze damaged {user.species}! (-{drain_heal_pb} HP)"
                elif drain_heal_pb > 0:
                    # Heal Block check for Leech Life (Gen VI+)
                    if move_lower_drain_pb == "leech-life" and generation_drain_pb >= 6:
                        if hasattr(user, 'heal_blocked') and getattr(user, 'heal_blocked', 0) > 0:
                            msg += f"\n{user.species} could not drain HP due to Heal Block!"
                        else:
                            user.hp = min(user.max_hp, user.hp + drain_heal_pb)
                            msg += f"\n{user.species} drained {drain_heal_pb} HP!"
                    elif getattr(user, 'heal_blocked', 0) == 0:
                        user.hp = min(user.max_hp, user.hp + drain_heal_pb)
                        msg += f"\n{user.species} drained {drain_heal_pb} HP!"
                parental_bond_drain_handled = True
    
    # Status moves - check if it's a stat-changing move OR status-inflicting move
    # IMPORTANT: Don't apply effects if the move missed!
    if meta.get("status") and not meta.get("miss"):
        move_lower = move_name.lower().replace(" ", "-")
        
        # === SPECIAL STATUS MOVES ===
        
        # Perish Song - handle early before other status moves
        if move_lower == "perish-song" or ("perish" in move_lower and "song" in move_lower):
            # Get all Pokémon on the field
            all_mons = []
            if battle_state:
                try:
                    p1_active = battle_state._active(battle_state.p1_id)
                    p2_active = battle_state._active(battle_state.p2_id)
                    if p1_active and p1_active.hp > 0:
                        all_mons.append(p1_active)
                    if p2_active and p2_active.hp > 0:
                        all_mons.append(p2_active)
                except Exception:
                    # Fallback to user and target if battle_state access fails
                    all_mons = [user]
                    if target and target.hp > 0:
                        all_mons.append(target)
            else:
                # Fallback to user and target if no battle_state
                all_mons = [user]
                if target and target.hp > 0:
                    all_mons.append(target)
            
            # Get generation for Soundproof check
            generation = get_generation(battle_state=battle_state, field_effects=field_effects)
            
            affected_mons = []
            for mon in all_mons:
                # Check if Pokémon already has a perish count
                if hasattr(mon, 'perish_count') and mon.perish_count is not None:
                    continue
                
                # Check Soundproof immunity
                mon_ability = normalize_ability_name(mon.ability or "")
                ability_data = get_ability_effect(mon_ability)
                has_soundproof = ability_data.get("sound_move_immunity", False)
                
                # Gen VIII+: User is not immune to their own Perish Song
                # Other Pokémon with Soundproof are still immune
                if has_soundproof:
                    if generation >= 8 and mon == user:
                        # Gen VIII+: User is affected even with Soundproof
                        pass
                    else:
                        # Soundproof blocks Perish Song for other Pokémon
                        continue
                
                # Set perish count to 4 (starts at 4, decreases at end of turn)
                mon.perish_count = 4
                affected_mons.append(mon)
            
            if affected_mons:
                return f"**{user.species}** used **Perish Song**!\n🎵 A haunting melody echoes across the battlefield... All Pokémon that hear it will faint in **4 turns**!"
            else:
                return f"**{user.species}** used **Perish Song**!\nBut it failed!"
        
        # Transform
        if move_lower == "transform":
            # Good as Gold: Transform fails (though it does not affect the target)
            target_ability_transform = normalize_ability_name(target.ability or "")
            if target_ability_transform == "good-as-gold":
                user._last_move_failed = True
                return f"**{user.species}** used **Transform**!\nBut it failed! ({target.species}'s Good as Gold prevented it!)"
            
            msg = sm.apply_transform(user, target)
            
            # Z-Transform: Restore all HP
            if hasattr(user, '_is_z_move') and user._is_z_move:
                old_hp = user.hp
                user.hp = user.max_hp
                heal_amount = user.hp - old_hp
                return protean_msg + f"**{user.species}** used **Transform**!\n{msg}\n{user.species} regained {heal_amount} HP!"
            
            return protean_msg + f"**{user.species}** used **Transform**!\n{msg}"
        
        # Wish
        if move_lower == "wish" and battle_state:
            # Z-Wish: +1 Special Defense
            if hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs = modify_stages(user, {"spd": 1}, caused_by_opponent=False, field_effects=field_effects)
                main_msg = f"**{user.species}** used **Wish**!"
                for z_msg in z_msgs:
                    main_msg += f"\n{z_msg}"
                # Z-Wish doesn't set up wish healing
                return main_msg
            
            msg = sm.setup_wish(user, _resolve_owner_id(user), battle_state)
            return f"**{user.species}** used **Wish**!\n{msg}"
        
        # Trick / Switcheroo
        if move_lower in ["trick", "switcheroo"]:
            # Z-Trick: +2 Speed (but move fails)
            if hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs = modify_stages(user, {"spe": 2}, caused_by_opponent=False, field_effects=field_effects)
                main_msg = f"**{user.species}** used **{move_name}**!"
                for z_msg in z_msgs:
                    main_msg += f"\n{z_msg}"
                main_msg += "\nBut it failed! (Cannot exchange Z-Crystal)"
                return main_msg
            
            msg = sm.apply_trick_switcheroo(user, target)
            return f"**{user.species}** used **{move_name}**!\n{msg}"
        
        # Yawn
        if move_lower == "yawn":
            generation = get_generation(field_effects=field_effects, battle_state=battle_state)

            if target is None or target.hp <= 0:
                return f"**{user.species}** used **Yawn**!\nBut it failed!"

            fail_reason = None

            if getattr(target, 'invulnerable', False):
                fail_reason = f"{target.species} can't be targeted right now!"
            else:
                # Check if target has a valid status condition
                current_status = getattr(target, 'status', None)
                valid_statuses = {"par", "brn", "slp", "frz", "psn", "tox", "sleep", "paralyze", "burn", "freeze", "poison", "toxic"}
                has_valid_status = False
                if current_status:
                    status_normalized = str(current_status).lower().strip()
                    if status_normalized and status_normalized in valid_statuses:
                        has_valid_status = True
                
                if has_valid_status:
                    fail_reason = f"{target.species} already has a status condition!"
            
            if not fail_reason and getattr(target, 'substitute', None):
                fail_reason = f"{target.species} is protected by its substitute!"
            
            if not fail_reason and getattr(target, 'drowsy_turns', 0) > 0:
                fail_reason = f"{target.species} is already drowsy!"

            ability_target = normalize_ability_name(getattr(target, 'ability', '') or "")
            ability_data_target = get_ability_effect(ability_target)
            ability_name_target = (target.ability or ability_target or "Ability").replace("-", " ").title()

            # Ability-based immunities
            if not fail_reason:
                status_immunity = ability_data_target.get("status_immunity")
                if status_immunity == "all" or (isinstance(status_immunity, list) and "slp" in status_immunity):
                    fail_reason = f"{target.species}'s {ability_name_target} prevents sleep!"
                elif ability_target in ["insomnia", "vital-spirit", "comatose", "purifying-salt"]:
                    fail_reason = f"{target.species}'s {ability_name_target} prevents sleep!"
                elif ability_data_target.get("team_sleep_immunity"):
                    fail_reason = f"{target.species}'s {ability_name_target} keeps it awake!"
                elif ability_data_target.get("protects_grass_types") and "Grass" in [t for t in target.types if t]:
                    fail_reason = f"{target.species}'s {ability_name_target} protects it from sleep!"

            # Leaf Guard in sun
            if not fail_reason and ability_target == "leaf-guard" and generation >= 5:
                if field_effects and (
                    getattr(field_effects, 'weather', None) == "sun" or
                    getattr(field_effects, 'harsh_sunlight', False) or
                    getattr(field_effects, 'special_weather', None) == "harsh-sunlight"
                ):
                    fail_reason = f"{target.species}'s {ability_name_target} blocks status in the sunlight!"

            # Meteor Form Minior (Gen 7+ mechanics apply from Gen V per description)
            if not fail_reason and generation >= 5:
                if target.species and target.species.lower() == "minior":
                    form_name = str(getattr(target, 'form', '')).lower()
                    if form_name and "meteor" in form_name:
                        fail_reason = f"{target.species} is protected by its shell!"

            # Safeguard
            if not fail_reason and target_side and getattr(target_side, 'safeguard', False):
                fail_reason = f"{target.species} is protected by Safeguard!"

            # Terrain effects (Electric/Misty prevent grounded Pokémon from falling asleep)
            if not fail_reason and field_effects:
                terrain = getattr(field_effects, 'terrain', None)
                if terrain in ["electric", "misty"]:
                    if is_grounded(target, field_gravity=getattr(field_effects, 'gravity', False)):
                        terrain_name = "Electric" if terrain == "electric" else "Misty"
                        fail_reason = f"{terrain_name} Terrain prevents sleep!"

            # Uproar (Gen III-IV: fail; Gen V+: allow but note for later)
            uproar_active = bool(field_effects and getattr(field_effects, 'uproar_turns', 0) > 0)
            if not fail_reason and uproar_active and generation <= 4 and ability_target != "soundproof":
                source_name = getattr(field_effects, 'uproar_source', None)
                if source_name:
                    fail_reason = f"The uproar from {source_name} keeps {target.species} awake!"
                else:
                    fail_reason = "An uproar keeps it awake!"

            if fail_reason:
                return f"**{user.species}** used **Yawn**!\nBut it failed! {fail_reason}"

            # Z-Yawn: +1 Speed
            if hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs = modify_stages(user, {"spe": 1}, caused_by_opponent=False, field_effects=field_effects)
                main_msg = f"**{user.species}** used **Yawn**!\n{target.species} grew drowsy!"
                for z_msg in z_msgs:
                    main_msg += f"\n{z_msg}"
                target.drowsy_turns = 2
                target.drowsy_source = user.species
                target._yawn_generation = generation
                return main_msg

            target.drowsy_turns = 2
            target.drowsy_source = user.species
            target._yawn_generation = generation
            return f"**{user.species}** used **Yawn**!\n{target.species} grew drowsy!"
        
        # Fling (power based on held item, consumes item)
        if move_lower == "fling":
            fling_power, fling_msg, item_effect_msg = sm.apply_fling(user, target, field_effects=field_effects, battle_state=battle_state)
            if fling_power == 0:
                # Fling failed
                return f"**{user.species}** used **Fling**!\n{fling_msg}"
            
            # Store power override and item effect message for damage calculation
            user._fling_power_override = fling_power
            user._fling_item_effect_msg = item_effect_msg
            user._fling_berry_activated = getattr(target, '_flung_berry', None) is not None
            user._fling_flinch_item = getattr(target, '_flung_flinch_item', False)
            
            # Continue to damage calculation (Fling will use the power override)
            # The damage function will handle the actual damage calculation
            # After damage, we'll apply special item effects
        
        # Baton Pass
        if move_lower == "baton-pass" and battle_state:
            msg = sm.apply_baton_pass(user, _resolve_owner_id(user), battle_state)
            main_msg = f"**{user.species}** used **Baton Pass**!\n{msg}\n(Switch will occur in panel.py)"
            
            # Z-Baton Pass: Reset all lowered stats (user)
            if hasattr(user, '_is_z_move') and user._is_z_move:
                stat_resets = {}
                for stat in ["atk", "defn", "spa", "spd", "spe", "accuracy", "evasion"]:
                    if user.stages.get(stat, 0) < 0:
                        stat_resets[stat] = -user.stages.get(stat, 0)
                if stat_resets:
                    z_msgs = modify_stages(user, stat_resets, caused_by_opponent=False, field_effects=field_effects)
                    for z_msg in z_msgs:
                        main_msg += f"\n{z_msg}"
            
            return main_msg
        
        # Topsy-Turvy
        if move_lower == "topsy-turvy":
            msg = sm.apply_topsy_turvy(target)
            return f"**{user.species}** used **Topsy-Turvy**!\n{msg}"
        
        # === RANDOM MOVE SELECTION ===
        
        # Metronome
        if move_lower == "metronome":
            generation = get_generation(field_effects=field_effects, battle_state=battle_state)
            
            # Z-Metronome: Selected move becomes its Z-Move (if status move, no Z-Power effect)
            if hasattr(user, '_is_z_move') and user._is_z_move:
                # Check if Metronome already determined the called move (e.g., for priority checks)
                if hasattr(user, '_metronome_called_move') and user._metronome_called_move:
                    selected_move = user._metronome_called_move
                    move_data = get_move(selected_move, generation=generation_for_move_data, battle_state=battle_state)
                    move_display = move_data.get("name", selected_move.replace("-", " ").title()) if move_data else selected_move.replace("-", " ").title()
                    metronome_msg = f"Metronome called **{move_display}**!"
                else:
                    selected_move, metronome_msg = get_metronome_move(field_effects=field_effects, battle_state=battle_state)
                    if not selected_move:
                        return f"**{user.species}** used **Metronome**!\n{metronome_msg}"
                    # Store the called move for consistency
                    user._metronome_called_move = selected_move
                
                # Check if selected move is a status move (status moves don't get Z-Power effect from Z-Metronome)
                selected_move_data = get_move(selected_move, generation=generation_for_move_data, battle_state=battle_state)
                is_status_move = selected_move_data and (selected_move_data.get("category") == "status" or selected_move_data.get("power", 0) <= 0)
                
                # Create a modified user_choice for the called move if it's not a status move
                new_user_choice = user_choice.copy() if user_choice else {}
                if not is_status_move:
                    new_user_choice["z_move"] = True
                
                msg = f"**{user.species}** used **Metronome**!\n{metronome_msg}\n\n"
                
                # Recursively call apply_move with the selected move (with Z-Move flag if applicable)
                recursive_result = apply_move(user, target, selected_move, field_effects, target_side, new_user_choice, target_choice, battle_state)
                
                # Clear the stored called move after execution
                if hasattr(user, '_metronome_called_move'):
                    delattr(user, '_metronome_called_move')
                
                return msg + recursive_result
            
            # Check if Metronome already determined the called move (e.g., for priority checks)
            if hasattr(user, '_metronome_called_move') and user._metronome_called_move:
                selected_move = user._metronome_called_move
                move_data = get_move(selected_move, generation=generation_for_move_data, battle_state=battle_state)
                move_display = move_data.get("name", selected_move.replace("-", " ").title()) if move_data else selected_move.replace("-", " ").title()
                metronome_msg = f"Metronome called **{move_display}**!"
            else:
                selected_move, metronome_msg = get_metronome_move(field_effects=field_effects, battle_state=battle_state)
                if not selected_move:
                    return f"**{user.species}** used **Metronome**!\n{metronome_msg}"
                # Store the called move for consistency
                user._metronome_called_move = selected_move
            
            msg = f"**{user.species}** used **Metronome**!\n{metronome_msg}\n\n"
            
            # Set last move used to the called move (not Metronome itself)
            # This is important for Choice item interactions (Gen V+)
            user._metronome_called_move = selected_move
            
            # Check if the called move has requirements that aren't met (e.g., Aurora Veil requires Hail)
            # Field effect moves need to be checked before execution
            from .battle_flow import apply_field_effect_move
            selected_move_lower = selected_move.lower().replace(" ", "-")
            field_effect_moves = {
                "reflect", "light-screen", "aurora-veil", "tailwind", "trick-room",
                "magic-room", "wonder-room", "gravity", "mist"
            }
            
            # If it's a field effect move, check requirements first
            if selected_move_lower in field_effect_moves:
                # Determine which side this is for
                user_side = None
                if battle_state:
                    try:
                        user_owner_id = _resolve_owner_id(user)
                        if user_owner_id == battle_state.p1_id:
                            user_side = battle_state.p1_side
                        elif user_owner_id == battle_state.p2_id:
                            user_side = battle_state.p2_side
                    except Exception:
                        pass
                
                if user_side:
                    # Check requirements by calling apply_field_effect_move
                    # This will return failure messages if requirements aren't met
                    field_msgs = apply_field_effect_move(selected_move, field_effects, user_side, True, user, battle_state)
                    # If the move failed (e.g., "But it failed!"), return that instead of executing
                    if field_msgs and any("failed" in msg.lower() for msg in field_msgs):
                        return msg + "\n".join(f"  {m}" for m in field_msgs)
                    # If it succeeded, the field effect is already applied, so we can return
                    if field_msgs:
                        return msg + "\n".join(f"  {m}" for m in field_msgs)
            
            # Recursively call apply_move with the selected move
            recursive_result = apply_move(user, target, selected_move, field_effects, target_side, user_choice, target_choice, battle_state)
            
            # Clear the stored called move after execution
            if hasattr(user, '_metronome_called_move'):
                delattr(user, '_metronome_called_move')
            
            # Gen V+: Choice item interaction
            # If Metronome calls a move the user knows and user has Choice item, lock into called move
            # Otherwise, Metronome is the locked move
            if generation >= 5 and hasattr(user, 'item') and user.item:
                if item_is_active(user):
                    u_item = normalize_item_name(user.item)
                    u_data = get_item_effect(u_item)
                    if u_data.get("choice_locks_move"):
                        # Check if user knows the called move
                        user_moves = [m.lower().replace(" ", "-") for m in getattr(user, 'moves', [])]
                        if selected_move.lower().replace(" ", "-") in user_moves:
                            # Lock into called move (will be set by battle_state)
                            if battle_state:
                                battle_state._choice_locked[getattr(user, '_player_id', user.id)] = selected_move
                        # Otherwise, Metronome remains locked
            
            return msg + recursive_result
        
        # Assist
        if move_lower == "assist":
            # Z-Assist: Makes called move a Z-Move if damaging
            if hasattr(user, '_is_z_move') and user._is_z_move:
                selected_move, assist_msg = get_assist_move(
                    user,
                    battle_state=battle_state,
                    field_effects=field_effects
                )
                if not selected_move:
                    return f"**{user.species}** used **Assist**!\n{assist_msg}"
                
                # Check if called move is damaging
                called_move_data = get_move(selected_move, generation=generation_for_move_data, battle_state=battle_state)
                is_damaging = False
                if called_move_data:
                    move_category = called_move_data.get("category", "").lower()
                    move_power = int(called_move_data.get("power") or 0)
                    is_damaging = move_category in ["physical", "special"] or move_power > 0
                
                # If damaging, make it a Z-Move by setting flag and passing z_move in choice
                msg = f"**{user.species}** used **Assist**!\n{assist_msg}\n\n"
                if is_damaging:
                    # Create a choice dict with z_move flag for the recursive call
                    assisted_choice = (user_choice or {}).copy()
                    assisted_choice["z_move"] = True
                    recursive_result = apply_move(user, target, selected_move, field_effects, target_side, assisted_choice, target_choice, battle_state)
                else:
                    # Status move - execute normally without Z-Move
                    recursive_result = apply_move(user, target, selected_move, field_effects, target_side, user_choice, target_choice, battle_state)
                return msg + recursive_result
            
            selected_move, assist_msg = get_assist_move(
                user,
                battle_state=battle_state,
                field_effects=field_effects
            )
            if not selected_move:
                return f"**{user.species}** used **Assist**!\n{assist_msg}"
            msg = f"**{user.species}** used **Assist**!\n{assist_msg}\n\n"
            recursive_result = apply_move(user, target, selected_move, field_effects, target_side, user_choice, target_choice, battle_state)
            return msg + recursive_result
        
        # Sleep Talk
        if move_lower == "sleep-talk":
            selected_move, sleep_talk_msg = get_sleep_talk_move(
                user,
                field_effects=field_effects,
                battle_state=battle_state
            )
            if not selected_move:
                return f"**{user.species}** used **Sleep Talk**!\n{sleep_talk_msg}"
            msg = f"**{user.species}** used **Sleep Talk**!\n{sleep_talk_msg}\n\n"
            previously_sleep_talking = getattr(user, '_using_sleep_talk', False)
            user._using_sleep_talk = True
            # Store the called move so the battle state can check if it's a pivot move
            # Don't clear this immediately - let the battle state check it first
            user._sleep_talk_called_move = selected_move
            try:
                recursive_result = apply_move(
                    user,
                    target,
                    selected_move,
                    field_effects,
                    target_side,
                    user_choice,
                    target_choice,
                    battle_state,
                )
            finally:
                if previously_sleep_talking:
                    user._using_sleep_talk = previously_sleep_talking
                else:
                    if hasattr(user, '_using_sleep_talk'):
                        delattr(user, '_using_sleep_talk')
            # Note: _sleep_talk_called_move will be cleared by the battle state after checking for pivot moves
            return msg + recursive_result
        
        # === MOVE COPYING ===
        
        # Copycat
        if move_lower == "copycat":
            selected_move, copycat_msg = get_copycat_move(battle_state)
            if not selected_move:
                return f"**{user.species}** used **Copycat**!\n{copycat_msg}"
            msg = f"**{user.species}** used **Copycat**!\n{copycat_msg}\n\n"
            recursive_result = apply_move(user, target, selected_move, field_effects, target_side, user_choice, target_choice, battle_state)
            return msg + recursive_result
        
        # Mirror Move
        if move_lower == "mirror-move":
            generation = get_generation(field_effects=field_effects, battle_state=battle_state)
            
            # Gen VIII+: Cannot be selected
            if generation >= 8:
                return f"**{user.species}** used **Mirror Move**!\nBut it failed! (Mirror Move cannot be selected in this generation)"
            
            selected_move, mirror_msg = get_mirror_move(
                user,
                target,
                generation=generation,
                battle_state=battle_state
            )
            if not selected_move:
                return f"**{user.species}** used **Mirror Move**!\n{mirror_msg}"
            
            msg = f"**{user.species}** used **Mirror Move**!\n{mirror_msg}\n\n"
            
            # Z-Mirror Move: +2 Attack, copied move becomes Z-Move (Gen 7)
            if hasattr(user, '_is_z_move') and user._is_z_move:
                msgs = modify_stages(user, {"atk": 2}, caused_by_opponent=False, field_effects=field_effects)
                for m in msgs:
                    msg += f"\n{m}"
                
                # Check if copied move is a status move (status moves don't get Z-Power effect)
                copied_move_data = load_move(selected_move, generation=generation_for_move_data, battle_state=battle_state)
                is_status = copied_move_data and copied_move_data.get("category") == "status"
                
                if not is_status:
                    # Make the copied move a Z-Move
                    user_choice_with_z = user_choice.copy() if user_choice else {}
                    user_choice_with_z["z_move"] = True
                    user_choice_with_z["z_move_from_mirror_move"] = True  # Flag to track origin
            
            # Set last move used to the copied move (not Mirror Move itself)
            user._mirror_move_copied = selected_move
            user.last_move_targeted = None
            user.last_move_target_source = None
            
            # If Z-Mirror Move, pass z_move flag to recursive call
            recursive_user_choice = user_choice
            if hasattr(user, '_is_z_move') and user._is_z_move:
                copied_move_data = load_move(selected_move, generation=generation_for_move_data, battle_state=battle_state)
                is_status = copied_move_data and copied_move_data.get("category") == "status"
                if not is_status:
                    recursive_user_choice = user_choice.copy() if user_choice else {}
                    recursive_user_choice["z_move"] = True
            
            recursive_result = apply_move(user, target, selected_move, field_effects, target_side, recursive_user_choice, target_choice, battle_state)
            return msg + recursive_result
        
        # Mimic
        if move_lower == "mimic":
            generation = get_generation(field_effects=field_effects, battle_state=battle_state)
            
            # Gen II+: Copy target's last used move
            # Gen IV+: If target used Me First, copy Me First itself, not the move it called
            target_last_move = getattr(target, 'last_move_used', None) if hasattr(target, 'last_move_used') else None
            
            # Mimic fails if target hasn't used a move since entering the field
            # Check if target has used a move this battle (not just last_move_used, which might persist)
            if not target_last_move:
                # Also check if target has moved this turn or battle
                # If target just switched in and hasn't used a move, Mimic should fail
                return f"**{user.species}** used **{move_name}**!\nBut it failed!"
            
            # Gen I: In link battles, Mimic copies randomly (we'll use last move as fallback)
            # In NPC/wild battles, it would show moveset - we'll use last move for simplicity
            if generation == 1:
                if not target_last_move:
                    target_last_move = getattr(target, 'last_move_used', None)
                    if not target_last_move:
                        return f"**{user.species}** used **{move_name}**!\nBut it failed!"
            
            # Gen III+: Mimic bypasses accuracy checks (unless target is semi-invulnerable)
            # This is handled by the move execution flow - if we get here, it hit
            
            success, mimic_msg = apply_mimic(target_last_move, user=user, target=target, field_effects=field_effects, battle_state=battle_state)
            
            base_msg = f"**{user.species}** used **{move_name}**!\n{mimic_msg}"
            
            # Z-Mimic: +1 Accuracy (Gen 7)
            if hasattr(user, '_is_z_move') and user._is_z_move:
                msgs = modify_stages(user, {"accuracy": 1}, caused_by_opponent=False, field_effects=field_effects)
                for m in msgs:
                    base_msg += f"\n{m}"
            
            return base_msg
        
        # Sketch
        if move_lower == "sketch":
            # Get target's last move
            target_last_move = getattr(target, 'last_move_used', None) if hasattr(target, 'last_move_used') else None
            sketch_msg = apply_sketch(target_last_move, user, target=target, field_effects=field_effects, battle_state=battle_state)
            if sketch_msg:
                return f"**{user.species}** used **Sketch**!\n{sketch_msg}"
            else:
                return f"**{user.species}** used **Sketch**!\nBut it failed!"
        
        # === PROTECT VARIANTS ===
        
        # Mat Block (first turn only, blocks damaging moves)
        if move_lower == "mat-block":
            success, mat_msg = apply_mat_block(user, getattr(battle_state, 'turn', 1))
            if success:
                return f"**{user.species}** used **Mat Block**!\n{mat_msg}"
            else:
                return f"**{user.species}** used **Mat Block**!\n{mat_msg}"
        
        # Crafty Shield (blocks status moves)
        crafty_target_side = user_side if user_side is not None else target_side
        if move_lower == "crafty-shield" and crafty_target_side:
            success, crafty_msg = apply_crafty_shield(crafty_target_side)
            return f"**{user.species}** used **Crafty Shield**!\n{crafty_msg}"
        
        # Quick Guard (blocks priority moves)
        quick_guard_side = user_side if user_side is not None else target_side
        if move_lower == "quick-guard" and quick_guard_side:
            if is_moving_last:
                user._last_move_failed = True
                user.consecutive_protects = 0
                return f"**{user.species}** used **Quick Guard**!\nBut it failed!"
            success, quick_msg = apply_quick_guard(
                user,
                quick_guard_side,
                field_effects=field_effects,
                battle_state=battle_state
            )
            if success:
                if hasattr(user, '_last_move_failed'):
                    user._last_move_failed = False
            else:
                user._last_move_failed = True
            msg = f"**{user.species}** used **Quick Guard**!\n{quick_msg}"
            if success and hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs = modify_stages(user, {"defn": 1}, caused_by_opponent=False, field_effects=field_effects)
                for z_msg in z_msgs:
                    msg += f"\n{z_msg}"
            return msg
        
        # Wide Guard (blocks spread moves)
        wide_guard_side = user_side if user_side is not None else target_side
        if move_lower == "wide-guard" and wide_guard_side:
            success, wide_msg = apply_wide_guard(user, wide_guard_side, field_effects=field_effects)
            main_msg = f"**{user.species}** used **Wide Guard**!\n{wide_msg}"
            if success and hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs = modify_stages(user, {"defn": 1}, caused_by_opponent=False, field_effects=field_effects)
                for z_msg in z_msgs:
                    main_msg += f"\n{z_msg}"
            return main_msg
        
        # Max Guard (always succeeds, protects against additional moves)
        if move_lower == "max-guard":
            user.protected_this_turn = True
            user.max_guard_active = True
            return f"**{user.species}** used **Max Guard**!\n{user.species} protected itself!"
        
        # === PRE-MOVE DAMAGE MOVES ===
        
        # Focus Punch (charges, fails if hit)
        if move_lower == "focus-punch":
            focus_msg = setup_focus_punch(user, field_effects=field_effects)
            if focus_msg:
                pre_move_msgs.append(focus_msg)
        
        # Shell Trap (sets trap, activates on physical hit)
        if move_lower == "shell-trap":
            pre_move_msgs.append(f"{user.species} set a shell trap!")
            if not getattr(user, '_shell_trap_activated', False):
                user._shell_trap_set = False
                user._shell_trap_activated = False
                shell_fail_msg = f"**{user.species}** used **{move_name}**!\n{user.species} set a shell trap!\nBut it failed!"
                return shell_fail_msg
            user._shell_trap_set = False
            user._shell_trap_activated = False
        
        # Beak Blast (charges, burns on contact before attacking)
        if move_lower == "beak-blast":
            pre_move_msgs.append(f"{user.species} started heating up its beak!")
            if hasattr(user, '_beak_blast_charging'):
                user._beak_blast_charging = False
        
        # Relic Song will be handled after damage is dealt (it's a damaging move)
        # The forme change happens in the damaging section below
        
        # Power Trick
        if move_lower == "power-trick":
            msg = sm.apply_power_trick(user)
            return f"**{user.species}** used **Power Trick**!\n{msg}"
        
        # Guard Swap
        if move_lower == "guard-swap":
            msg = sm.apply_guard_swap(user, target)
            return f"**{user.species}** used **Guard Swap**!\n{msg}"
        
        if move_lower == "guard-split":
            msg = sm.apply_guard_split(user, target)
            result = f"**{user.species}** used **Guard Split**!\n{msg}"
            if hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs = modify_stages(user, {"spe": 1}, caused_by_opponent=False, field_effects=field_effects)
                for z_msg in z_msgs:
                    result += f"\n{z_msg}"
            return result
        
        # Power Swap
        if move_lower == "power-swap":
            msg = sm.apply_power_swap(user, target)
            return f"**{user.species}** used **Power Swap**!\n{msg}"
        
        if move_lower == "power-split":
            msg = sm.apply_power_split(user, target)
            result = f"**{user.species}** used **Power Split**!\n{msg}"
            if hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs = modify_stages(user, {"spe": 1}, caused_by_opponent=False, field_effects=field_effects)
                for z_msg in z_msgs:
                    result += f"\n{z_msg}"
            return result
        
        # Speed Swap
        if move_lower == "speed-swap":
            msg = sm.apply_speed_swap(user, target)
            return f"**{user.species}** used **Speed Swap**!\n{msg}"
        
        # Heart Swap
        if move_lower == "heart-swap":
            msg = sm.apply_heart_swap(user, target)
            return f"**{user.species}** used **Heart Swap**!\n{msg}"
        
        # === TYPE-CHANGING MOVES ===
        
        # Soak
        if move_lower == "soak":
            generation = get_generation(field_effects=field_effects)
            if target is None or getattr(target, "hp", 0) <= 0:
                user._last_move_failed = True
                return f"**{user.species}** used **Soak**!\nBut it failed!"
            if hasattr(target, "substitute") and target.substitute:
                user._last_move_failed = True
                return f"**{user.species}** used **Soak**!\nBut {target.species}'s substitute blocked the move!"
            target_ability = normalize_ability_name(target.ability or "")
            if target_ability in {"multitype", "rks-system"}:
                user._last_move_failed = True
                return f"**{user.species}** used **Soak**!\nBut it failed!"
            if getattr(target, 'terastallized', False):
                user._last_move_failed = True
                return f"**{user.species}** used **Soak**!\nBut it failed!"
            current_types = [t for t in target.types if t]
            if generation >= 6 and len(current_types) == 1 and current_types[0] == "Water":
                user._last_move_failed = True
                return f"**{user.species}** used **Soak**!\nBut it failed!"
            msg = apply_soak(target)
            main_msg = f"**{user.species}** used **Soak**!\n{msg}"
            if hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs = modify_stages(user, {"spa": 1}, caused_by_opponent=False, field_effects=field_effects)
                for z_msg in z_msgs:
                    main_msg += f"\n{z_msg}"
            return main_msg
        
        # Magic Powder
        if move_lower == "magic-powder":
            msg = apply_magic_powder(target, user)
            return f"**{user.species}** used **Magic Powder**!\n{msg}"
        
        if move_lower == "telekinesis":
            success, tele_msg = apply_telekinesis(user, target, field_effects=field_effects)
            if not success:
                user._last_move_failed = True
                return f"**{user.species}** used **Telekinesis**!\n{tele_msg}"
            main_msg = f"**{user.species}** used **Telekinesis**!\n{tele_msg}"
            if hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs = modify_stages(user, {"spa": 1}, caused_by_opponent=False, field_effects=field_effects)
                for z_msg in z_msgs:
                    main_msg += f"\n{z_msg}"
            return main_msg
        
        # Conversion 2
        if move_lower == "conversion-2":
            generation = get_generation(field_effects=field_effects)

            if generation >= 5 and target_side:
                blocked, block_msg = check_crafty_shield(None, target_side, "status")
                if blocked:
                    return f"**{user.species}** used **Conversion 2**!\n{block_msg}"

            last_move_type = getattr(user, '_last_move_type_hit_by', None)
            success, conv_msg = apply_conversion_2(
                user,
                generation,
                last_move_type=last_move_type,
                target=target,
                field_effects=field_effects
            )

            if success:
                # Z-Conversion 2: Restore all HP
                if hasattr(user, '_is_z_move') and user._is_z_move:
                    old_hp = user.hp
                    user.hp = user.max_hp
                    heal_amount = user.hp - old_hp
                    if heal_amount > 0:
                        return f"**{user.species}** used **Conversion 2**!\n{conv_msg}\n{user.species} regained {heal_amount} HP!"
                return f"**{user.species}** used **Conversion 2**!\n{conv_msg}"
            else:
                return f"**{user.species}** used **Conversion 2**!\nBut it failed!"
        
        # Curse (special handling for Ghost types vs non-Ghost)
        if move_lower == "curse":
            generation = get_generation(field_effects=field_effects)
            user_types = [t.strip().title() for t in user.types if t]
            is_ghost_user = "Ghost" in user_types

            if is_ghost_user:
                # Ghost-type Curse
                # Good as Gold: Curse fails and does not deduct HP from the user
                target_ability_curse = normalize_ability_name(target.ability or "")
                if target_ability_curse == "good-as-gold":
                    user._last_move_failed = True
                    return f"**{user.species}** used **Curse**!\nBut it failed! ({target.species}'s Good as Gold prevented it!)"
                
                # NOTE: Ghost-type Curse works on ALL types, including Normal types.
                # It does NOT check type immunity - it's a special status effect.
                if target is None or target.hp <= 0:
                    return f"**{user.species}** used **Curse**!\nBut it failed!"
                if getattr(target, 'cursed', False):
                    return f"**{user.species}** used **Curse**!\nBut it failed! ({target.species} is already cursed)"
                
                # Crafty Shield blocks Curse (Gen VI+)
                if generation >= 6 and target_side:
                    blocked, block_msg = check_crafty_shield(None, target_side, "status")
                    if blocked:
                        return f"**{user.species}** used **Curse**!\n{block_msg}"
                
                # Gen I-IV: Substitute blocks Curse
                if generation <= 4 and hasattr(target, 'substitute') and target.substitute:
                    return f"**{user.species}** used **Curse**!\nBut it failed! ({target.species}'s substitute blocked the curse!)"
                
                # Gen V+: Curse can hit through substitute
                # Check if move would miss (semi-invulnerable)
                if hasattr(target, 'invulnerable') and target.invulnerable:
                    # Move misses, user doesn't lose HP
                    return f"**{user.species}** used **Curse**!\nBut it missed!"

                # Only lose HP if move succeeds
                # Ghost-type Curse works on all types (including Normal) - no type immunity check
                hp_cost = max(1, user.max_hp // 2)
                user.hp = max(0, user.hp - hp_cost)
                target.cursed = True
                target._cursed_generation = generation
                target._cursed_source = user.species

                msg_parts = [f"**{user.species}** used **Curse**!", f"{user.species} cut its own HP and laid a curse on {target.species}!"]
                if user.hp <= 0:
                    msg_parts.append(f"{user.species} fainted!")
                
                # Z-Curse (Ghost): Restore all HP
                if hasattr(user, '_is_z_move') and user._is_z_move:
                    old_hp = user.hp
                    user.hp = user.max_hp
                    heal_amount = user.hp - old_hp
                    if heal_amount > 0:
                        msg_parts.append(f"{user.species} regained {heal_amount} HP!")
                
                return "\n".join(msg_parts)
            else:
                # Non-Ghost Curse fails if no opponents or stats cannot change (Gen II rule)
                if target is None or target.hp <= 0:
                    return f"**{user.species}** used **Curse**!\nBut it failed!"
                if generation == 2:
                    atk_stage = user.stages.get("atk", 0)
                    def_stage = user.stages.get("defn", 0)
                    if atk_stage >= 6 and def_stage >= 6:
                        return f"**{user.species}** used **Curse**!\nBut it failed! ({user.species}'s stats can't go higher)"
                
                # Gen III: Can reduce Speed even if Atk/Def at +6 (but fails if all three maxed)
                if generation >= 3:
                    atk_stage = user.stages.get("atk", 0)
                    def_stage = user.stages.get("defn", 0)
                    spe_stage = user.stages.get("spe", 0)
                    if atk_stage >= 6 and def_stage >= 6 and spe_stage <= -6:
                        return f"**{user.species}** used **Curse**!\nBut it failed! ({user.species}'s stats can't change further)"
                
                # Apply stat changes: -1 Speed, +1 Attack, +1 Defense
                stat_changes = {"spe": -1, "atk": 1, "defn": 1}
                msgs = modify_stages(user, stat_changes, caused_by_opponent=False, field_effects=field_effects)
                
                # Z-Curse (non-Ghost): +1 Attack
                if hasattr(user, '_is_z_move') and user._is_z_move:
                    z_msgs = modify_stages(user, {"atk": 1}, caused_by_opponent=False, field_effects=field_effects)
                    msgs.extend(z_msgs)
                
                return f"**{user.species}** used **Curse**!\n" + "\n".join(msgs)
        
        # Acupressure
        if move_lower == "acupressure":
            generation = get_generation(field_effects=field_effects, battle_state=battle_state)
            
            # Acupressure always targets the user (self) in singles battles
            # In doubles/triples, it can target self or ally, but not opponent
            # For now, we'll implement singles battle behavior (always self)
            acupressure_target = user
            is_targeting_self = True
            
            # In doubles/triples, if target is specified and is an ally, use that
            # But we need to check if target is actually an ally (not opponent)
            # For singles, always use self
            
            # Gen V+: Crafty Shield blocks Acupressure on allies but not on self
            # (This would only matter in doubles/triples)
            if generation >= 5 and target_side and not is_targeting_self:
                blocked, block_msg = check_crafty_shield(None, target_side, "status")
                if blocked:
                    return f"**{user.species}** used **Acupressure**!\n{block_msg}"
            
            # Gen IV: Fails if target has substitute
            # Gen V+: Fails if targeting ally with substitute, but works on self even with substitute
            if generation == 4:
                if hasattr(acupressure_target, 'substitute') and acupressure_target.substitute:
                    return f"**{user.species}** used **Acupressure**!\nBut it failed!"
            elif generation >= 5:
                # Gen V+: Only fails if targeting ally (not self) with substitute
                if not is_targeting_self and hasattr(acupressure_target, 'substitute') and acupressure_target.substitute:
                    return f"**{user.species}** used **Acupressure**!\nBut it failed!"
            
            # Get all possible stats (Attack, Defense, Special Attack, Special Defense, Speed, accuracy, evasion)
            all_stats = ["atk", "defn", "spa", "spd", "spe", "accuracy", "evasion"]
            
            # Find stats that are not maximized (stage < 6)
            if not hasattr(acupressure_target, 'stages'):
                acupressure_target.stages = {"atk": 0, "defn": 0, "spa": 0, "spd": 0, "spe": 0, "accuracy": 0, "evasion": 0}
            
            available_stats = [stat for stat in all_stats if acupressure_target.stages.get(stat, 0) < 6]
            
            # Fails if all stats are maximized
            if not available_stats:
                return f"**{user.species}** used **Acupressure**!\nBut it failed!"
            
            # Choose a random stat from available stats
            # random is already imported at module level
            chosen_stat = random.choice(available_stats)
            
            # Raise the chosen stat by 2 stages
            stat_messages = modify_stages(acupressure_target, {chosen_stat: 2}, caused_by_opponent=False, field_effects=field_effects)
            
            # Format stat name for message
            stat_names = {
                "atk": "Attack",
                "defn": "Defense",
                "spa": "Sp. Atk",
                "spd": "Sp. Def",
                "spe": "Speed",
                "accuracy": "accuracy",
                "evasion": "evasiveness"
            }
            stat_display = stat_names.get(chosen_stat, chosen_stat.upper())
            
            base_msg = f"**{user.species}** used **Acupressure**!"
            if stat_messages:
                base_msg += f"\n{stat_messages[0]}"  # modify_stages returns list of messages
            else:
                base_msg += f"\n{acupressure_target.species}'s {stat_display} sharply rose!"
            
            # Z-Acupressure: +2 critical hit rate
            if hasattr(user, '_is_z_move') and user._is_z_move:
                if not hasattr(user, 'crit_stage'):
                    user.crit_stage = 0
                user.crit_stage = min(3, user.crit_stage + 2)
                base_msg += f"\n{user.species}'s critical-hit ratio was raised!"
            
            return base_msg
        
        # === GROUNDING MOVES ===
        
        # Note: Smack Down and Thousand Arrows are damaging moves, handled below
        # Gravity is a field effect (would need to be in panel.py)
        
        # === ABILITY-CHANGING MOVES ===
        
        # Skill Swap
        if move_lower == "skill-swap":
            # Dynamax/Gigantamax: Skill Swap fails
            if target.dynamaxed or target.gigantamaxed:
                return f"**{user.species}** used **Skill Swap**!\nBut it failed!"
            
            msg = apply_skill_swap(user, target)
            main_msg = f"**{user.species}** used **Skill Swap**!\n{msg}"
            
            # Z-Skill Swap: +1 Speed
            if hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs = modify_stages(user, {"spe": 1}, caused_by_opponent=False, field_effects=field_effects)
                for z_msg in z_msgs:
                    main_msg += f"\n{z_msg}"
            
            return main_msg
        
        # Role Play
        if move_lower == "role-play":
            msg = apply_role_play(user, target)
            main_msg = f"**{user.species}** used **Role Play**!\n{msg}"
            
            # Z-Role Play: +1 Speed
            if hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs = modify_stages(user, {"spe": 1}, caused_by_opponent=False, field_effects=field_effects)
                for z_msg in z_msgs:
                    main_msg += f"\n{z_msg}"
            
            return main_msg
        
        # Worry Seed
        if move_lower == "worry-seed":
            generation = get_generation(field_effects=field_effects, battle_state=battle_state)
            msg = apply_worry_seed(target, field_effects=field_effects, generation=generation)
            return f"**{user.species}** used **Worry Seed**!\n{msg}"
        
        # Simple Beam
        if move_lower == "simple-beam":
            msg = apply_simple_beam(target)
            return f"**{user.species}** used **Simple Beam**!\n{msg}"
        
        # Entrainment
        if move_lower == "entrainment":
            msg = apply_entrainment(user, target)
            return f"**{user.species}** used **Entrainment**!\n{msg}"
        
        # Gastro Acid
        if move_lower == "gastro-acid":
            # Dynamax Pokemon cannot have abilities suppressed
            if target.dynamaxed:
                return f"**{user.species}** used **Gastro Acid**!\nBut it failed!"
            msg = apply_gastro_acid(target)
            return f"**{user.species}** used **Gastro Acid**!\n{msg}"
        
        # Spite
        if move_lower == "spite":
            # Good as Gold: Spite fails and does not reduce the target's previously used move's PP
            target_ability_spite = normalize_ability_name(target.ability or "")
            if target_ability_spite == "good-as-gold":
                user._last_move_failed = True
                return f"**{user.species}** used **Spite**!\nBut it failed! ({target.species}'s Good as Gold prevented it!)"
            
            msg = apply_spite(user, target, battle_state, field_effects)
            
            # Z-Spite: Restore all HP
            if hasattr(user, '_is_z_move') and user._is_z_move:
                old_hp = user.hp
                user.hp = user.max_hp
                heal_amount = user.hp - old_hp
                if heal_amount > 0:
                    return f"**{user.species}** used **Spite**!\n{msg}\n{user.species} regained {heal_amount} HP!"
            
            return f"**{user.species}** used **Spite**!\n{msg}"
        
        # === STOCKPILE FAMILY ===
        
        # Stockpile
        if move_lower == "stockpile":
            # Check if this is Z-Stockpile
            if hasattr(user, '_is_z_move') and user._is_z_move and hasattr(user, '_original_move_name') and user._original_move_name.lower().replace(" ", "-") == "stockpile":
                # Z-Stockpile: Restore all HP
                user.hp = user.max_hp
                return f"**{user.species}** used **{move_name}**!\n{user.species} restored all its HP!"
            msg = apply_stockpile(user, generation=generation_check)
            return f"**{user.species}** used **Stockpile**!\n{msg}"
        
        # Spit Up (damaging move that releases stockpile)
        if move_lower == "spit-up":
            power, msg = apply_spit_up(user, generation=generation_check)
            if power > 0:
                # Deal damage based on stockpile
                target.hp = max(0, target.hp - power)
                return f"**{user.species}** used **Spit Up**!\n{msg}"
            else:
                return f"**{user.species}** used **Spit Up**!\n{msg}"
        
        # Swallow (healing move that releases stockpile)
        if move_lower == "swallow":
            # Check if this is Z-Swallow
            if hasattr(user, '_is_z_move') and user._is_z_move and hasattr(user, '_original_move_name') and user._original_move_name.lower().replace(" ", "-") == "swallow":
                # Z-Swallow: Reset all lowered stats
                stat_resets = {}
                for stat in ["atk", "defn", "spa", "spd", "spe", "accuracy", "evasion"]:
                    if user.stages.get(stat, 0) < 0:
                        stat_resets[stat] = -user.stages.get(stat, 0)  # Amount to raise back to 0
                
                if stat_resets:
                    msgs = modify_stages(user, stat_resets, caused_by_opponent=False, field_effects=field_effects)
                    return f"**{user.species}** used **{move_name}**!\n" + "\n".join(msgs)
                else:
                    return f"**{user.species}** used **{move_name}**!\n{user.species}'s stats were already at their highest!"
            
            # Regular Swallow
            heal_amount, msg = apply_swallow(user, generation=generation_check)
            return f"**{user.species}** used **Swallow**!\n{msg}"
        
        # === BERRY-BASED MOVES ===
        
        # Stuff Cheeks (consume Berry, raise Defense +2)
        if move_lower == "stuff-cheeks":
            msg = handle_stuff_cheeks(user)
            return f"**{user.species}** used **Stuff Cheeks**!\n{msg}"
        
        # Stat-changing moves (Swords Dance, Dragon Dance, Growl, Leer, etc.)
        # Check MOVE_SECONDARY_EFFECTS for all stat-changing moves (from move_effects.py)
        effect_data = get_move_secondary_effect(move_name)
        
        # Handle self-targeting stat boosts
        if effect_data.get("status_move") and "stat_boost" in effect_data:
            main_msg = f"**{user.species}** used **{move_name}**!"

            if move_lower == "no-retreat" and getattr(user, "_no_retreat_active", False):
                user._last_move_failed = True
                return main_msg + "\nBut it failed! (It can't use No Retreat again!)"
            
            # Tail Glow: Generation-specific boost (+2 Gen III-IV, +3 Gen V+)
            if move_lower == "tail-glow":
                gen_tg = get_generation(field_effects=field_effects, battle_state=battle_state)
                
                # Gen VIII: Cannot be selected
                if gen_tg >= 8:
                    return f"**{user.species}** used **{move_name}**!\nBut it failed! (Cannot be selected in Gen VIII+)"
                
                # Z-Tail Glow: Reset all lowered stats
                if hasattr(user, '_is_z_move') and user._is_z_move:
                    stat_resets = {}
                    for stat in ["atk", "defn", "spa", "spd", "spe", "accuracy", "evasion"]:
                        if user.stages.get(stat, 0) < 0:
                            stat_resets[stat] = -user.stages.get(stat, 0)
                    if stat_resets:
                        z_msgs = modify_stages(user, stat_resets, caused_by_opponent=False, field_effects=field_effects)
                        for z_msg in z_msgs:
                            main_msg += f"\n{z_msg}"
                        return main_msg
                
                # Generation-specific boost
                if gen_tg <= 4:
                    boost_amount = 2  # Gen III-IV: +2
                else:
                    boost_amount = 3  # Gen V+: +3
                
                boost_messages = modify_stages(user, {"spa": boost_amount}, caused_by_opponent=False, field_effects=field_effects)
                for msg in boost_messages:
                    main_msg += f"\n{msg}"
                return main_msg
            
            # Howl: Gen VIII+ affects allies (sound move)
            if move_lower == "howl":
                gen_howl = get_generation(field_effects=field_effects)
                
                # Gen VIII+: Sound move, affects allies
                if gen_howl >= 8:
                    # Check Soundproof (allies only, user always affected)
                    # In singles, only affects user (no allies)
                    # In doubles, would affect ally
                    # For now, just affect user in singles
                    user_ability_howl = normalize_ability_name(user.ability or "")
                    user_ability_data_howl = get_ability_effect(user_ability_howl)
                    soundproof_user = user_ability_data_howl.get("sound_move_immunity", False)
                    
                    # User is always affected even with Soundproof (Gen VIII+)
                    stat_boosts_howl = effect_data.get("stat_boost", {"atk": 1})
                    boost_messages_howl = modify_stages(user, stat_boosts_howl, caused_by_opponent=False, field_effects=field_effects)
                    main_msg = f"**{user.species}** used **{move_name}**!"
                    for msg in boost_messages_howl:
                        main_msg += f"\n{msg}"
                    
                    # Z-Howl: +1 Attack (additional stage)
                    if hasattr(user, '_is_z_move') and user._is_z_move:
                        z_msgs_howl = modify_stages(user, {"atk": 1}, caused_by_opponent=False, field_effects=field_effects)
                        for z_msg in z_msgs_howl:
                            main_msg += f"\n{z_msg}"
                    
                    return main_msg
                else:
                    # Gen III-VII: User only (no sound move)
                    stat_boosts_howl = effect_data.get("stat_boost", {"atk": 1})
            
            # Apply stat boosts (these target self)
            stat_boosts = effect_data.get("stat_boost", {})
            
            # Growth: Generation-specific stat boosts and sun interaction
            if move_lower == "growth":
                gen_growth = get_generation(field_effects=field_effects)
                weather = getattr(field_effects, 'weather', None) if field_effects else None
                is_sun = weather == "sun"
                
                # Override stat boosts based on generation
                if gen_growth == 1:
                    # Gen I: Special stat (not Attack/SpA)
                    stat_boosts = {"special": 1}
                elif gen_growth <= 4:
                    # Gen II-IV: +1 SpA
                    stat_boosts = {"spa": 1}
                elif gen_growth >= 5:
                    # Gen V+: +1 Atk, +1 SpA (or +2 each in harsh sunlight)
                    if is_sun:
                        stat_boosts = {"atk": 2, "spa": 2}
                    else:
                        stat_boosts = {"atk": 1, "spa": 1}
            
            boost_messages = modify_stages(user, stat_boosts, caused_by_opponent=False, field_effects=field_effects)
            for msg in boost_messages:
                main_msg += f"\n{msg}"

            if move_lower == "no-retreat":
                user._no_retreat_active = True
                main_msg += f"\n{user.species} can no longer escape!"
            
            # Autotomize: Reduces weight by 100 kg (applied first, before abilities/items)
            if move_lower == "autotomize":
                user._autotomize_used = True
                # Get base weight from species data if available
                base_weight = getattr(user, 'weight_kg', 100.0)
                # Store the original weight before Autotomize if not already stored
                if not hasattr(user, '_weight_before_autotomize'):
                    user._weight_before_autotomize = base_weight
                # Weight reduction is handled in _get_effective_weight function
                # The flag is enough - actual calculation happens when weight is needed
                main_msg += f"\n{user.species} became lighter!"
            
            # Also check for self stat drops (like Shell Smash)
            if "self_stat_drop" in effect_data:
                stat_drops = effect_data["self_stat_drop"]
                drop_messages = modify_stages(user, stat_drops)
                for msg in drop_messages:
                    main_msg += f"\n{msg}"
            
            return main_msg
        
        # Laser Focus - guarantees next move will be a critical hit
        if effect_data.get("next_move_crits"):
            message = f"**{user.species}** used **{move_name}**!\n{user.species} became laser-focused!"
            user.laser_focus_turns = 2
            user._laser_focus_pending = True
            if hasattr(user, '_last_move_failed'):
                user._last_move_failed = False
            return message
        
        # Strength Sap - heal based on target's Attack and lower their Attack
        if effect_data.get("strength_sap"):
            main_msg = f"**{user.species}** used **{move_name}**!"
            
            # Good as Gold: Strength Sap fails and does not reduce the target's Attack nor restore the user's HP
            target_ability_sap = normalize_ability_name(target.ability or "")
            if target_ability_sap == "good-as-gold":
                user._last_move_failed = True
                return main_msg + f"\nBut it failed! ({target.species}'s Good as Gold prevented it!)"
            
            # Heal Block prevents Strength Sap from restoring HP (and the move fails)
            if getattr(user, 'heal_blocked', 0) > 0:
                user._last_move_failed = True
                return main_msg + f"\nBut it failed!"
            
            # If the target's Attack can't drop further, the move fails
            target_stage = target.stages.get("atk", 0)
            if target_stage <= -6:
                user._last_move_failed = True
                return main_msg + f"\nBut it failed!"
            
            # Heal equals the target's current effective Attack stat
            effective_attack = get_effective_stat(target, "atk")
            # Tablets of Ruin: Strength Sap healing is unaffected; use Attack as if Ruin didn't reduce it
            battle_state_sap = getattr(target, "_battle_state", None)
            if battle_state_sap:
                all_mons_sap = []
                if hasattr(battle_state_sap, "p1_party"):
                    all_mons_sap.extend([m for m in battle_state_sap.p1_party if m and m.hp > 0])
                if hasattr(battle_state_sap, "p2_party"):
                    all_mons_sap.extend([m for m in battle_state_sap.p2_party if m and m.hp > 0])
                tablets_holder_other = any(m is not target and normalize_ability_name(m.ability or "") == "tablets-of-ruin" for m in all_mons_sap)
                if tablets_holder_other:
                    effective_attack *= 4 / 3  # Undo Ruin for healing amount
            heal_amount = max(1, int(effective_attack))
            
            # Big Root boosts Strength Sap healing
            if item_is_active(user) and getattr(user, 'item', None):
                
                item_norm = normalize_item_name(user.item)
                item_data = get_item_effect(item_norm)
                if item_data.get("boosts_draining_moves"):
                    affected_moves = item_data.get("affected_moves", [])
                    if move_lower in affected_moves:
                        gen_now = get_generation(field_effects=field_effects)
                        gen_specific = item_data.get("gen_specific", {})
                        if gen_now <= 4:
                            mult = gen_specific.get("4", {}).get("multiplier", 1.3)
                        else:
                            mult = gen_specific.get("5+", {}).get("multiplier", 5324 / 4096)
                        heal_amount = max(1, int(math.floor(heal_amount * mult)))
            
            old_hp = user.hp
            user.hp = min(user.max_hp, user.hp + heal_amount)
            actual_heal = user.hp - old_hp
            if actual_heal > 0:
                main_msg += f"\n{user.species} restored {actual_heal} HP!"
            else:
                main_msg += f"\n{user.species}'s HP is already full!"
            
            # Always attempt to lower the target's Attack, even if Heal Block prevented healing
            attack_drop = effect_data.get("target_stat_drop", {"atk": -1})
            drop_messages = modify_stages(target, attack_drop, caused_by_opponent=True, field_effects=field_effects)
            for drop_msg in drop_messages:
                main_msg += f"\n{drop_msg}"
            if drop_messages:
                target._stats_lowered_this_turn = True
            
            # Z-Strength Sap: +1 Defense to the user
            if hasattr(user, '_is_z_move') and user._is_z_move:
                z_effect = effect_data.get("z_boost_effect", {})
                stat_boost = z_effect.get("stat_boost", {})
                if stat_boost:
                    z_msgs = modify_stages(user, stat_boost, caused_by_opponent=False, field_effects=field_effects)
                    for z_msg in z_msgs:
                        main_msg += f"\n{z_msg}"
            
            if hasattr(user, '_last_move_failed'):
                user._last_move_failed = False
            
            return main_msg
        
        # Handle opponent-targeting stat drops (Growl, Leer, Cotton Spore, etc.)
        if effect_data.get("status_move") and "target_stat_drop" in effect_data:

            main_msg = f"**{user.species}** used **{move_name}**!"
            status_move_id = move_name.lower().replace(" ", "-")

            if effect_data.get("blocked_by_crafty_shield") and target_side:
                blocked, block_msg = check_crafty_shield(user_side, target_side, "status")
                if blocked:
                    if hasattr(user, '_last_move_failed'):
                        user._last_move_failed = True
                    return main_msg + f"\n{block_msg}"

            if getattr(target, 'protected_this_turn', False):
                protection_move = getattr(target, '_protection_move', None)
                standard_protects = {"protect", "detect", "spiky-shield", "baneful-bunker", "kings-shield", "obstruct", "winters-aegis", "silk-trap", "burning-bulwark"}
                bypass = effect_data.get("bypasses_standard_protect", False)
                max_guard_active = getattr(target, 'max_guard_active', False)
                if not (bypass and protection_move in standard_protects and not max_guard_active):
                    if hasattr(user, '_last_move_failed'):
                        user._last_move_failed = True
                    return main_msg + "\nBut it failed!"
            
            # Cotton Spore: Gen VI+ immunities (Grass types, Overcoat, Safety Goggles)
            if status_move_id == "cotton-spore":
                gen_cotton = get_generation(field_effects=field_effects)
                
                if gen_cotton >= 6:
                    target_types = [t.strip().title() if t else None for t in getattr(target, 'types', (None, None))]
                    target_ability_cotton = normalize_ability_name(target.ability or "")
                    target_ability_data_cotton = get_ability_effect(target_ability_cotton)
                    
                    # Check immunities
                    if "Grass" in target_types:
                        return f"**{user.species}** used **{move_name}**!\nIt doesn't affect {target.species}..."
                    if target_ability_data_cotton.get("powder_move_immunity"):
                        ability_name_cotton = (target.ability or target_ability_cotton or "Ability").replace("-", " ").title()
                        return f"**{user.species}** used **{move_name}**!\n{target.species}'s {ability_name_cotton} protects it!"
                    if item_is_active(target) and target.item:
                        t_item_cotton = normalize_item_name(target.item)
                        t_item_data_cotton = get_item_effect(t_item_cotton)
                        if t_item_data_cotton.get("powder_move_immunity"):
                            return f"**{user.species}** used **{move_name}**!\n{target.species}'s {target.item} protects it!"
            
            # Apply stat drops to target (generation-aware for String Shot to avoid
            # double-applying its stage drop in mixed move tables).
            status_gen = get_generation(field_effects=field_effects, battle_state=battle_state)
            stat_drops = effect_data["target_stat_drop"]
            if status_move_id == "string-shot":
                stat_drops = {"spe": -1} if status_gen <= 5 else {"spe": -2}
            drop_messages = modify_stages(target, stat_drops, caused_by_opponent=True, field_effects=field_effects)
            for msg in drop_messages:
                main_msg += f"\n{msg}"
            if drop_messages:
                target._stats_lowered_this_turn = True
            
            if status_move_id == "tar-shot":
                if getattr(target, '_tar_shot_active', False):
                    main_msg += f"\n{target.species} is already covered in tar!"
                elif getattr(target, 'terastallized', False):
                    main_msg += f"\nBut the tar had no effect on {target.species}'s Terastallized form!"
                else:
                    target._tar_shot_active = True
                    main_msg += f"\n{target.species} became more vulnerable to Fire!"
            
            if effect_data.get("removes_item"):
                base_msg = f"**{user.species}** used **{move_name}**!"
                if not target.item:
                    if hasattr(user, '_last_move_failed'):
                        user._last_move_failed = True
                    return base_msg + "\nBut it failed! (The target isn't holding an item!)"

                can_remove, fail_reason = can_remove_item_from_target(
                    target,
                    user,
                    field_effects=field_effects,
                    cause=move_lower
                )
                if not can_remove:
                    if hasattr(user, '_last_move_failed'):
                        user._last_move_failed = True
                    if fail_reason:
                        return base_msg + f"\n{fail_reason}"
                    return base_msg + "\nBut it failed!"

                removed_item = target.item
                target.item = None
                item_display = str(removed_item).replace("-", " ").title()
                return base_msg + f"\n{target.species}'s {item_display} was corroded away!"
            
            # String Shot: base stat drop already applied above
            if status_move_id == "string-shot":
                # Z-String Shot: +1 Speed (user)
                if hasattr(user, '_is_z_move') and user._is_z_move:
                    z_msgs_str = modify_stages(user, {"spe": 1}, caused_by_opponent=False, field_effects=field_effects)
                    for z_msg in z_msgs_str:
                        main_msg += f"\n{z_msg}"
                    return main_msg
                return main_msg
            
            # Z-Cotton Spore: Reset all lowered stats
            if status_move_id == "cotton-spore" and hasattr(user, '_is_z_move') and user._is_z_move:
                stat_resets = {}
                for stat in ["atk", "defn", "spa", "spd", "spe", "accuracy", "evasion"]:
                    if user.stages.get(stat, 0) < 0:
                        stat_resets[stat] = -user.stages.get(stat, 0)
                if stat_resets:
                    z_msgs = modify_stages(user, stat_resets, caused_by_opponent=False, field_effects=field_effects)
                    for z_msg in z_msgs:
                        main_msg += f"\n{z_msg}"
            
            # Z-Scary Face: +1 Speed (user)
            if status_move_id == "scary-face" and hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs_scary = modify_stages(user, {"spe": 1}, caused_by_opponent=False, field_effects=field_effects)
                for z_msg in z_msgs_scary:
                    main_msg += f"\n{z_msg}"
            
            # Z-Charm: +1 Defense (user)
            if status_move_id == "charm" and hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs_charm = modify_stages(user, {"defn": 1}, caused_by_opponent=False, field_effects=field_effects)
                for z_msg in z_msgs_charm:
                    main_msg += f"\n{z_msg}"
            
            # Z-Sweet Scent: +1 Accuracy (user)
            if status_move_id == "sweet-scent" and hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs_ss = modify_stages(user, {"accuracy": 1}, caused_by_opponent=False, field_effects=field_effects)
                for z_msg in z_msgs_ss:
                    main_msg += f"\n{z_msg}"
            
            # Z-Feather Dance: +1 Defense (user)
            if move_lower == "feather-dance" and hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs_fd = modify_stages(user, {"defn": 1}, caused_by_opponent=False, field_effects=field_effects)
                for z_msg in z_msgs_fd:
                    main_msg += f"\n{z_msg}"
            
            # Z-Teeter Dance: +1 Special Attack (user)
            if move_lower == "teeter-dance" and hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs_td = modify_stages(user, {"spa": 1}, caused_by_opponent=False, field_effects=field_effects)
                for z_msg in z_msgs_td:
                    main_msg += f"\n{z_msg}"
            
            # Z-Sand Attack: +1 Evasiveness (user)
            if move_lower == "sand-attack" and hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs_sa = modify_stages(user, {"evasion": 1}, caused_by_opponent=False, field_effects=field_effects)
                for z_msg in z_msgs_sa:
                    main_msg += f"\n{z_msg}"
            
            return main_msg
        
        # ===== NEW MECHANICS IMPLEMENTATION =====
        
        # SIMPLE MECHANICS
        # Splash, Celebrate, Hold Hands - do nothing
        if effect_data.get("does_nothing"):
            move_lower_splash = move_name.lower().replace(" ", "-")
            if move_lower_splash == "splash":
                gen_splash = get_generation(field_effects=field_effects)
                if gen_splash == 1:
                    return f"**{user.species}** used **{move_name}**!\nNo effect!"
                else:
                    return f"**{user.species}** used **{move_name}**!\nBut nothing happened{'!' if gen_splash >= 3 else '.'}"
            
            # Z-Celebrate: Raise all stats by 1 stage each
            if move_lower_splash == "celebrate" and hasattr(user, '_is_z_move') and user._is_z_move:
                z_effects = {"atk": 1, "defn": 1, "spa": 1, "spd": 1, "spe": 1}
                z_msgs = modify_stages(user, z_effects, caused_by_opponent=False, field_effects=field_effects)
                main_msg = f"**{user.species}** used **Z-Celebrate**!"
                for z_msg in z_msgs:
                    main_msg += f"\n{z_msg}"
                return main_msg
            
            # Other "does nothing" moves
            return f"**{user.species}** used **{move_name}**!\nBut nothing happened!"
        
        # False Swipe - leaves target at 1 HP minimum
        if effect_data.get("leaves_1hp"):
            # This is handled in damage calculation section
            pass
        
        # Super Fang, Nature's Madness, Ruination - halve target's HP
        # Uses non-Dynamax HP for calculation (50% of non-Dynamax HP)
        if effect_data.get("halves_hp"):
            # Super Fang: Generation-specific type immunity
            if move_lower == "super-fang":
                gen_sf = get_generation(field_effects=field_effects)
                
                # Gen I: Ignores type immunities
                # Gen II+: Ghost types are immune
                if gen_sf >= 2:
                    target_types = [t.strip().title() if t else None for t in getattr(target, 'types', (None, None))]
                    if "Ghost" in target_types:
                        return f"**{user.species}** used **Super Fang**!\nIt doesn't affect {target.species}..."
            
            # Calculate damage based on non-Dynamax HP
            target_base_max_hp = get_non_dynamax_hp(target)
            damage_dealt_base = max(1, target_base_max_hp // 2)
            
            # Convert to Dynamax HP if target is Dynamaxed
            if target.dynamaxed and target._original_max_hp:
                damage_percent = damage_dealt_base / target._original_max_hp if target._original_max_hp > 0 else 0
                damage_dealt = max(1, int(target.max_hp * damage_percent))
            else:
                damage_dealt = damage_dealt_base
            
            # Dummy Magikarp is immortal - heals to 999 HP when it reaches 0
            if getattr(target, '_is_dummy_magikarp', False):
                target.hp = max(0, target.hp - damage_dealt)
                if target.hp <= 0:
                    target.hp = 999
                    target.max_hp = 999
            else:
                target.hp = max(1, target.hp - damage_dealt)
            return f"**{user.species}** used **{move_name}**!\n{target.species} lost half its HP! ({damage_dealt} damage)"
        
        # Final Gambit - damage equals user's HP, user faints
        if effect_data.get("damage_equals_hp"):
            damage_dealt = user.hp
            user.hp = 0
            target.hp = max(0, target.hp - damage_dealt)
            return f"**{user.species}** used **{move_name}**!\n{user.species} fainted!\n{target.species} took {damage_dealt} damage!"
        
        # Endeavor - reduce target HP to match user's HP
        # Uses non-Dynamax HP for calculation
        if effect_data.get("damage_to_match_hp"):
            user_base_hp = get_non_dynamax_hp(user)
            target_base_hp = get_non_dynamax_hp(target)
            
            # Calculate damage based on non-Dynamax HP
            if target_base_hp > user_base_hp:
                damage_dealt_base = target_base_hp - user_base_hp
                # Convert to Dynamax HP if target is Dynamaxed
                if target.dynamaxed and target._original_max_hp:
                    damage_percent = damage_dealt_base / target._original_max_hp if target._original_max_hp > 0 else 0
                    damage_dealt = max(1, int(target.max_hp * damage_percent))
                else:
                    damage_dealt = damage_dealt_base
                # Dummy Magikarp is immortal - heals to 999 HP when it reaches 0
                if getattr(target, '_is_dummy_magikarp', False):
                    target.hp = max(0, target.hp - damage_dealt)
                    if target.hp <= 0:
                        target.hp = 999
                        target.max_hp = 999
                else:
                    target.hp = max(1, target.hp - damage_dealt)
                return f"**{user.species}** used **{move_name}**!\n{target.species} took {damage_dealt} damage!"
            else:
                return f"**{user.species}** used **{move_name}**!\nBut it failed!"
        
        # FIELD EFFECTS
        # Light Screen, Reflect, Aurora Veil
        if effect_data.get("sets_screen"):
            screen_type = effect_data["sets_screen"]
            
            # Z-Light Screen: +1 Special Defense
            if hasattr(user, '_is_z_move') and user._is_z_move and screen_type == "light-screen":
                msgs = modify_stages(user, {"spd": 1}, caused_by_opponent=False, field_effects=field_effects)
                base_msg = f"**{user.species}** used **{move_name}**!\nLight Screen was set up!"
                for m in msgs:
                    base_msg += f"\n{m}"
                return base_msg
            
            # Z-Reflect: +1 Defense
            if hasattr(user, '_is_z_move') and user._is_z_move and screen_type == "reflect":
                msgs = modify_stages(user, {"defn": 1}, caused_by_opponent=False, field_effects=field_effects)
                base_msg = f"**{user.species}** used **{move_name}**!\nReflect was set up!"
                for m in msgs:
                    base_msg += f"\n{m}"
                return base_msg
            
            duration = effect_data.get("duration", 5)
            # Light Clay extends screens to 8 turns
            if item_is_active(user) and user.item:
                if normalize_item_name(user.item) == "light-clay":
                    duration = 8
            if not hasattr(field_effects, 'screens'):
                field_effects.screens = {}
            field_effects.screens[screen_type] = duration
            screen_names = {
                "light-screen": "Light Screen",
                "reflect": "Reflect",
                "aurora-veil": "Aurora Veil"
            }
            return f"**{user.species}** used **{move_name}**!\n{screen_names.get(screen_type, screen_type)} was set up!"
        
        # Tailwind - doubles Speed for 4 turns
        if effect_data.get("doubles_speed"):
            if not hasattr(field_effects, 'tailwind'):
                field_effects.tailwind = {}
            field_effects.tailwind[user] = effect_data.get("duration", 4)
            
            # Wind Power: Charge Pokémon with Wind Power when Tailwind takes effect
            user_ability = normalize_ability_name(user.ability or "")
            ability_msg = ""
            if user_ability == "wind-power":
                user._charged = True
                ability_msg = f"\nTailwind charged {user.species} with power!"
            
            # Wind Rider: Boost Attack when Tailwind takes effect
            elif user_ability == "wind-rider":
                old_atk = user.stages.get("atk", 0)
                if old_atk < 6:
                    user.stages["atk"] = min(6, old_atk + 1)
                    ability_msg = f"\n{user.species}'s Wind Rider raised its Attack!"
            
            return f"**{user.species}** used **{move_name}**!\nThe Tailwind blew from behind!{ability_msg}"
        
        # Mist - protects stat stages
        if effect_data.get("protects_stats"):
            if not hasattr(field_effects, 'mist'):
                field_effects.mist = {}
            field_effects.mist[user] = effect_data.get("duration", 5)
            return f"**{user.species}** used **{move_name}**!\n{user.species} became shrouded in mist!"
        
        # Safeguard - prevents status conditions
        if effect_data.get("prevents_status"):
            if not hasattr(field_effects, 'safeguard'):
                field_effects.safeguard = {}
            field_effects.safeguard[user] = effect_data.get("duration", 5)
            main_msg = f"**{user.species}** used **{move_name}**!\n{user.species}'s team became cloaked in a mystical veil!"
            
            # Z-Safeguard: +1 Speed (user)
            if hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs = modify_stages(user, {"spe": 1}, caused_by_opponent=False, field_effects=field_effects)
                for z_msg in z_msgs:
                    main_msg += f"\n{z_msg}"
            
            return main_msg
        
        # Lucky Chant - prevents critical hits
        if effect_data.get("prevents_crits"):
            if not hasattr(field_effects, 'lucky_chant'):
                field_effects.lucky_chant = {}
            field_effects.lucky_chant[user] = effect_data.get("duration", 5)
            return f"**{user.species}** used **{move_name}**!\nLucky Chant shielded {user.species}'s team from critical hits!"
        
        # SPECIAL STATUS CONDITIONS
        # Leech Seed
        if effect_data.get("plants_leech_seed"):
            # Good as Gold: Leech Seed fails and does not set the target as seeded
            target_ability_leech = normalize_ability_name(target.ability or "")
            if target_ability_leech == "good-as-gold":
                user._last_move_failed = True
                return f"**{user.species}** used **{move_name}**!\nBut it failed! ({target.species}'s Good as Gold prevented it!)"
            
            if "Grass" in [t.strip().title() for t in target.types if t]:
                return f"**{user.species}** used **{move_name}**!\nIt doesn't affect {target.species}..."
            if hasattr(target, 'leech_seeded') and target.leech_seeded:
                return f"**{user.species}** used **{move_name}**!\n{target.species} is already seeded!"
            target.leech_seeded = True
            return f"**{user.species}** used **{move_name}**!\n{target.species} was seeded!"
        
        # Helper function to check for Aroma Veil protection
        def has_aroma_veil_protection(mon):
            """Check if a Pokemon is protected by Aroma Veil"""
            ability = normalize_ability_name(mon.ability or "")
            ability_data = get_ability_effect(ability)
            return ability_data.get("team_mental_move_immunity", False)
        
        # Taunt - prevents status moves
        if effect_data.get("taunts") or move_lower == "taunt":
            gen_taunt = get_generation(field_effects=field_effects)
            
            # Check for Z-Taunt
            if hasattr(user, '_is_z_move') and user._is_z_move:
                # Z-Taunt: +1 Attack
                z_msgs = modify_stages(user, {"atk": 1}, caused_by_opponent=False, field_effects=field_effects)
                main_msg = f"**{user.species}** used **{move_name}**!"
                for z_msg in z_msgs:
                    main_msg += f"\n{z_msg}"
                # Z-Moves don't prevent status moves, so just apply the boost
                return main_msg
            
            # Check for Magic Coat reflection (using gen_specific flag)
            move_effect_taunt = get_move_secondary_effect(move_name)
            gen_specific_taunt = move_effect_taunt.get("gen_specific", {}) if move_effect_taunt else {}
            reflected_by_magic_coat_taunt = None
            if gen_specific_taunt:
                def _match_gen_taunt(spec: str, gen: int) -> bool:
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
                for spec, overrides in gen_specific_taunt.items():
                    if isinstance(overrides, dict) and "reflected_by_magic_coat" in overrides:
                        if _match_gen_taunt(str(spec), gen_taunt):
                            reflected_by_magic_coat_taunt = overrides.get("reflected_by_magic_coat")
                            break
            if reflected_by_magic_coat_taunt is True and getattr(target, 'magic_coat', False):
                target.magic_coat = False
                # Reflect Taunt back onto user
                user.taunted = True
                # Gen V duration: 3 turns if target (original user) acts first, 4 if user (original target) acts first
                # Since we're reflecting, the original target (now user) acts first, so 3 turns
                user.taunt_turns = 3
                if battle_state:
                    user._taunt_applied_turn = getattr(battle_state, "turn", None)
                else:
                    user._taunt_applied_turn = None
                user._taunt_pending = True
                return f"**{user.species}** used **{move_name}**!\n{target.species}'s Magic Coat bounced the taunt back onto {user.species}!"
            
            # Gen VI+: Oblivious or Aroma Veil prevents Taunt
            if gen_taunt >= 6:
                target_ability_t = normalize_ability_name(target.ability or "")
                if target_ability_t == "oblivious":
                    return f"**{user.species}** used **{move_name}**!\n{target.species}'s Oblivious prevents Taunt!"
                if has_aroma_veil_protection(target):
                    return f"**{user.species}** used **{move_name}**!\n{target.species}'s Aroma Veil prevents Taunt!"
            
            # === MENTAL HERB: Cures mental effects (Gen 5+) ===
            if item_is_active(target) and target.item:
                t_item_mh = normalize_item_name(target.item)
                t_item_data_mh = get_item_effect(t_item_mh)
                if t_item_data_mh.get("cures_mental_effects") and gen_taunt >= 5:
                    target.item = None  # Consume Mental Herb
                    target.taunted = False
                    target.taunt_turns = 0
                    if hasattr(target, "_taunt_applied_turn"):
                        target._taunt_applied_turn = None
                    if hasattr(target, "_taunt_pending"):
                        target._taunt_pending = False
                    return f"**{user.species}** used **{move_name}**!\n{target.species}'s Mental Herb cured its mental status!"
            
            # Apply Taunt
            target.taunted = True
            
            # Generation-specific duration
            if gen_taunt == 3:
                target.taunt_turns = 2  # Gen III: 2 turns
            elif gen_taunt == 4:
                target.taunt_turns = random.randint(3, 5)  # Gen IV: 3-5 turns
            elif gen_taunt >= 5:
                # Gen V+: 3 turns if user acts first, 4 turns if target acts first
                # Determine who acts first by comparing priority and speed
                user_priority = action_priority(move_name, user, field_effects, battle_state)
                user_speed = _speed_value(user, None, field_effects)
                
                # Check target's move priority and speed if available
                target_acts_first = False
                if target_choice and target_choice.get("kind") == "move":
                    target_move = target_choice.get("value", "")
                    target_priority = action_priority(target_move, target, field_effects, battle_state)
                    target_speed = _speed_value(target, None, field_effects)
                    
                    # Compare priority first, then speed
                    if target_priority > user_priority:
                        target_acts_first = True
                    elif target_priority == user_priority:
                        # Same priority, compare speed (accounting for Trick Room)
                        if field_effects and field_effects.trick_room:
                            target_acts_first = (target_speed > user_speed)  # In Trick Room, slower is faster
                        else:
                            target_acts_first = (target_speed > user_speed)
                
                if target_acts_first:
                    target.taunt_turns = 4  # Target acted first: 4 turns
                else:
                    target.taunt_turns = 3  # User acts first: 3 turns
            else:
                target.taunt_turns = 3
            
            # Note: Taunt affects Pokémon behind substitute (unlike most status moves)
            if battle_state:
                target._taunt_applied_turn = getattr(battle_state, "turn", None)
            else:
                target._taunt_applied_turn = None
            target._taunt_pending = True
            user_name = format_species_name(user.species)
            if getattr(user, 'shiny', False):
                user_name = f"★ {user_name}"
            target_name = format_species_name(target.species)
            if getattr(target, 'shiny', False):
                target_name = f"★ {target_name}"
            move_parts = move_name.replace("-", " ").replace("_", " ").split()
            formatted_move = " ".join(part.capitalize() for part in move_parts) if move_parts else move_name.capitalize()
            return f"**{user_name}** used **{formatted_move}**!\n{target_name} fell for the taunt!"
        
        # Encore - forces last move to be used
        if effect_data.get("encores_last_move"):
            # === MENTAL HERB: Cures Encore (Gen 5+) ===
            if item_is_active(target) and target.item:
                t_item_mh2 = normalize_item_name(target.item)
                t_item_data_mh2 = get_item_effect(t_item_mh2)
                gen_mh2 = get_generation(field_effects=field_effects)
                if t_item_data_mh2.get("cures_mental_effects") and gen_mh2 >= 5:
                    target.item = None  # Consume Mental Herb
                    return f"**{user.species}** used **{move_name}**!\n{target.species}'s Mental Herb cured its mental status!"
            if has_aroma_veil_protection(target):
                return f"**{user.species}** used **{move_name}**!\n{target.species}'s Aroma Veil prevents Encore!"
            elif hasattr(target, 'last_move_used') and target.last_move_used:
                last_move_norm = target.last_move_used.lower().replace(" ", "-")
                if last_move_norm == "dynamax-cannon":
                    return f"**{user.species}** used **{move_name}**!\nBut it failed!"
                target.encored = effect_data.get("duration", 3)
                target.encored_move = target.last_move_used
                main_msg = f"**{user.species}** used **{move_name}**!\n{target.species} received an encore!"
                
                # Z-Encore: +1 Speed (user)
                if hasattr(user, '_is_z_move') and user._is_z_move:
                    z_msgs = modify_stages(user, {"spe": 1}, caused_by_opponent=False, field_effects=field_effects)
                    for z_msg in z_msgs:
                        main_msg += f"\n{z_msg}"
                
                return main_msg
            else:
                return f"**{user.species}** used **{move_name}**!\nBut it failed!"
        
        # Disable - disables last move used
        if effect_data.get("disables_last_move"):
            # === MENTAL HERB: Cures Disable (Gen 5+) ===
            if item_is_active(target) and target.item:
                t_item_mh3 = normalize_item_name(target.item)
                t_item_data_mh3 = get_item_effect(t_item_mh3)
                gen_mh3 = get_generation(field_effects=field_effects)
                if t_item_data_mh3.get("cures_mental_effects") and gen_mh3 >= 5:
                    target.item = None  # Consume Mental Herb
                    return f"**{user.species}** used **{move_name}**!\n{target.species}'s Mental Herb cured its mental status!"
            if has_aroma_veil_protection(target):
                return f"**{user.species}** used **{move_name}**!\n{target.species}'s Aroma Veil prevents Disable!"
            elif hasattr(target, 'last_move_used') and target.last_move_used:
                target.disabled_move = target.last_move_used
                target.disable_turns = effect_data.get("duration", 4)  # Fixed: disable_turns not disabled_turns
                return f"**{user.species}** used **{move_name}**!\n{target.species}'s {target.last_move_used} was disabled!"
            else:
                return f"**{user.species}** used **{move_name}**!\nBut it failed!"
        
        # Torment - can't use same move twice in a row
        if effect_data.get("torments"):
            # Check if this is Z-Torment
            if hasattr(user, '_is_z_move') and user._is_z_move and hasattr(user, '_original_move_name') and user._original_move_name.lower().replace(" ", "-") == "torment":
                # Z-Torment: +1 Defense
                msgs = modify_stages(user, {"defn": 1}, caused_by_opponent=False, field_effects=field_effects)
                return f"**{user.species}** used **{move_name}**!\n" + "\n".join(msgs)
            
            # Regular Torment effect
            # === MENTAL HERB: Cures Torment (Gen 5+) ===
            if item_is_active(target) and target.item:
                t_item_mh4 = normalize_item_name(target.item)
                t_item_data_mh4 = get_item_effect(t_item_mh4)
                gen_mh4 = get_generation(field_effects=field_effects)
                if t_item_data_mh4.get("cures_mental_effects") and gen_mh4 >= 5:
                    target.item = None  # Consume Mental Herb
                    return f"**{user.species}** used **{move_name}**!\n{target.species}'s Mental Herb cured its mental status!"
            if has_aroma_veil_protection(target):
                return f"**{user.species}** used **{move_name}**!\n{target.species}'s Aroma Veil prevents Torment!"
            else:
                target.tormented = True
                return f"**{user.species}** used **{move_name}**!\n{target.species} was subjected to torment!"
        
        # Attract/Infatuate
        if effect_data.get("infatuates"):

            generation = get_generation(field_effects=field_effects)

            def _consume_mental_item(mon) -> Optional[str]:
                if not item_is_active(mon) or not mon.item:
                    return None

                item_norm = normalize_item_name(mon.item)
                item_data = get_item_effect(item_norm)
                if item_data.get("cures_mental_effects") and generation >= 3:
                    item_name = mon.item.replace('-', ' ').title()
                    mon.item = None
                    return f"{mon.species}'s {item_name} cured its mental status!"
                return None

            ability = normalize_ability_name(target.ability or "")
            ability_data = get_ability_effect(ability)
            base_msg = f"**{user.species}** used **{move_name}**!"

            if getattr(target, 'infatuated', False):
                return base_msg + "\nBut it failed!"

            # Ability-based immunity (Oblivious, etc.)
            if ability_data.get("infatuation_immunity"):
                herb_msg = _consume_mental_item(target)
                if herb_msg:
                    return base_msg + f"\n{herb_msg}"
                return base_msg + "\nBut it failed!"

            if has_aroma_veil_protection(target):
                herb_msg = _consume_mental_item(target)
                if herb_msg:
                    return base_msg + f"\n{herb_msg}"
                return base_msg + f"\n{target.species}'s Aroma Veil prevents infatuation!"

            # Gender compatibility check
            genders_known = (
                hasattr(user, 'gender')
                and hasattr(target, 'gender')
                and user.gender
                and target.gender
            )
            if not (genders_known and user.gender != target.gender):
                herb_msg = _consume_mental_item(target)
                if herb_msg:
                    return base_msg + f"\n{herb_msg}"
                return base_msg + "\nBut it failed!"

            # Apply infatuation
            target.infatuated = True
            result_msg = base_msg + f"\n{target.species} fell in love!"
                    
            # Destiny Knot reflection (Gen 3+)
            if item_is_active(target) and target.item:

                item_norm = normalize_item_name(target.item)
                item_data = get_item_effect(item_norm)
                if item_data.get("shares_infatuation") and generation >= 3:
                    if genders_known and user.gender != target.gender:
                        user.infatuated = True
                        result_msg += (
                            f"\n{user.species} also became infatuated due to "
                            f"{target.species}'s {target.item.replace('-', ' ').title()}!"
                        )

            # Mental Herb/Egant Berry cure immediately after infatuation
            herb_msg = _consume_mental_item(target)
            if herb_msg:
                target.infatuated = False
                result_msg += f"\n{herb_msg}"
            
            return result_msg
        
        # HEALING MECHANICS
        # Self-heal moves (Recover, Soft-Boiled, Roost, Slack Off, etc.)
        # NOTE: Rest is handled separately in the healing_moves section below
        if effect_data.get("heal") and move_lower != "rest":
            # Z-Recover: Reset all lowered stats
            if hasattr(user, '_is_z_move') and user._is_z_move and move_lower == "recover":
                stat_resets = {}
                for stat in ["atk", "defn", "spa", "spd", "spe", "accuracy", "evasion"]:
                    if user.stages.get(stat, 0) < 0:
                        stat_resets[stat] = -user.stages.get(stat, 0)  # Amount to raise back to 0
                
                if stat_resets:
                    msgs = modify_stages(user, stat_resets, caused_by_opponent=False, field_effects=field_effects)
                    return f"**{user.species}** used **{move_name}**!\n" + "\n".join(msgs)
                else:
                    return f"**{user.species}** used **{move_name}**!\n{user.species}'s stats were already at their highest!"
            
            heal_fraction = effect_data["heal"]
            generation = get_generation(field_effects=field_effects)
            # Recover-specific rounding differences by generation
            if move_lower == "recover":
                raw = user.max_hp * heal_fraction
                if generation <= 4:
                    heal_amount = int(math.floor(raw))  # Gen I-IV: floor 50%
                elif 5 <= generation <= 7:
                    heal_amount = int(math.ceil(raw))   # Gen V-VII: ceil 50%
                else:
                    heal_amount = int(math.floor(raw))  # Gen VIII-IX: standard floor
            # Roost-specific rounding differences by generation
            elif move_lower == "roost":
                raw = user.max_hp * heal_fraction
                if generation == 4:
                    heal_amount = int(math.floor(raw))  # Gen IV: round down
                elif 5 <= generation <= 7:
                    heal_amount = int(math.ceil(raw))    # Gen V-VII: round up
                else:
                    heal_amount = int(user.max_hp * heal_fraction)  # Gen VIII+: standard
            else:
                heal_amount = int(user.max_hp * heal_fraction)
            
            old_hp = user.hp
            user.hp = min(user.max_hp, user.hp + heal_amount)
            actual_heal = user.hp - old_hp
            
            # Roost: Remove Flying type for this turn (Gen IV+)
            roost_type_msg = ""
            if move_lower == "roost" and generation >= 4:
                user_types = [t.strip().title() if t else None for t in getattr(user, 'types', (None, None))]
                is_flying = "Flying" in user_types
                
                if is_flying:
                    # Store original types for restoration
                    if not hasattr(user, '_original_types_roost'):
                        user._original_types_roost = tuple(user.types)
                    
                    # Remove Flying type
                    if len(user_types) == 2 and user_types[1] == "Flying":
                        # Dual-type with Flying as second type
                        user.types = (user_types[0], None)
                        user._roost_type_removed = True
                        roost_type_msg = f"\n{user.species} became {user_types[0]}-type!"
                    elif user_types[0] == "Flying" and (not user_types[1] or user_types[1] is None):
                        # Pure Flying type -> Normal type (Gen V+)
                        if generation >= 5:
                            user.types = ("Normal", None)
                            user._roost_type_removed = True
                            roost_type_msg = f"\n{user.species} became Normal-type!"
                        else:
                            # Gen IV: All attacks normally effective
                            user._roost_flying_ignored = True
                            roost_type_msg = f"\n{user.species}'s Flying type is ignored until the end of the turn!"
                    elif len(user_types) == 2 and user_types[0] == "Flying":
                        # Flying as first type (e.g., Flying/Fire)
                        user.types = (user_types[1], None)
                        user._roost_type_removed = True
                        roost_type_msg = f"\n{user.species} became {user_types[1]}-type!"
            
            return f"**{user.species}** used **{move_name}**!\n{user.species} regained {actual_heal} HP!{roost_type_msg}"
        # Aromatherapy, Heal Bell - heal team status
        if effect_data.get("heals_team_status"):
            generation = get_generation(field_effects=field_effects)
            user_ability_norm = normalize_ability_name(user.ability or "")
            user_ability_data = get_ability_effect(user_ability_norm)
            soundproof_active = user_ability_data.get("sound_move_immunity", False)

            base_msg = f"**{user.species}** used **{move_name}**!"

            if soundproof_active and generation <= 4:
                return base_msg + "\nBut its Soundproof body blocked the chimes!"

            if soundproof_active and generation in [6, 7]:
                return base_msg + "\nBut its Soundproof body blocked the chimes!"

            # Gen VIII+: user is always cured even if Soundproof
            if soundproof_active and generation >= 8:
                user.status = None
                return base_msg + "\nA soothing aroma wafted through the area!"

            user.status = None
            return base_msg + "\nA soothing aroma wafted through the area!"
        
        # Pollen Puff - heal ally, damage enemies
        if effect_data.get("heals_if_ally") and target is not None:
            same_side = user_side is not None and target_side is not None and user_side is target_side
            if same_side:
                base_msg = f"**{user.species}** used **{move_name}**!"
                
                if getattr(user, 'heal_blocked', 0) > 0 or getattr(target, 'heal_blocked', 0) > 0:
                    if hasattr(user, '_last_move_failed'):
                        user._last_move_failed = True
                    return base_msg + "\nBut it failed!"
                
                target_ability_norm = normalize_ability_name(target.ability or "")
                if effect_data.get("blocked_by_telepathy") and target_ability_norm == "telepathy":
                    if hasattr(user, '_last_move_failed'):
                        user._last_move_failed = True
                    ability_name = (target.ability or "Telepathy").replace("-", " ").title()
                    return base_msg + f"\nBut it failed! {target.species}'s {ability_name} protected it!"
                
                if target_ability_norm == "bulletproof":
                    if hasattr(user, '_last_move_failed'):
                        user._last_move_failed = True
                    ability_name = (target.ability or "Bulletproof").replace("-", " ").title()
                    return base_msg + f"\nBut it failed! {target.species}'s {ability_name} protected it!"
                
                if target.hp >= target.max_hp:
                    if hasattr(user, '_last_move_failed'):
                        user._last_move_failed = True
                    return base_msg + "\nBut it failed!"
                
                heal_amount = int(target.max_hp * 0.5)
                old_hp = target.hp
                target.hp = min(target.max_hp, target.hp + heal_amount)
                actual_heal = target.hp - old_hp
                
                if hasattr(user, '_last_move_failed'):
                    user._last_move_failed = False
                
                return base_msg + f"\n{target.species} regained {actual_heal} HP!"
        
        # Heal Pulse / Floral Healing - heal target
        if effect_data.get("heals_target"):
            heal_fraction = effect_data["heals_target"]
            z_effect = effect_data.get("z_boost_effect", {})
            is_z_move = hasattr(user, '_is_z_move') and user._is_z_move
            ignore_heal_block = is_z_move and z_effect.get("ignore_heal_block")
            user_ability_norm = normalize_ability_name(user.ability or "")
            user_ability_data = get_ability_effect(user_ability_norm)
            
            if (getattr(user, 'heal_blocked', 0) > 0 or getattr(target, 'heal_blocked', 0) > 0) and not ignore_heal_block:
                user._last_move_failed = True
                return f"**{user.species}** used **{move_name}**!\nBut it failed!"
            
            if target.hp >= target.max_hp:
                user._last_move_failed = True
                return f"**{user.species}** used **{move_name}**!\nBut it failed!"
            
            if getattr(target, 'substitute', None):
                try:
                    if target.substitute:
                        user._last_move_failed = True
                        return f"**{user.species}** used **{move_name}**!\nBut it failed!"
                except Exception:
                    pass
            
            # Mega Launcher: Heal Pulse heals 75% instead of 50%
            if user_ability_data.get("boost_pulse_moves") and move_lower == "heal-pulse":
                heal_fraction = 0.75
            
            # Floral Healing restores more HP in Grassy Terrain
            if effect_data.get("heals_more_in_grassy"):
                terrain = getattr(field_effects, 'terrain', None) if field_effects else None
                if terrain == "grassy":
                    heal_fraction = 2 / 3
            
            heal_amount = int(target.max_hp * heal_fraction)
            old_hp = target.hp
            target.hp = min(target.max_hp, target.hp + heal_amount)
            actual_heal = target.hp - old_hp
            
            message = f"**{user.species}** used **{move_name}**!\n{target.species} regained {actual_heal} HP!"
            
            if is_z_move and z_effect.get("reset_lower_stats"):
                lowered_stats = [stat for stat, stage in user.stages.items() if stage < 0]
                if lowered_stats:
                    for stat in lowered_stats:
                        user.stages[stat] = 0
                    message += f"\n{user.species}'s stats returned to normal!"
            
            if hasattr(user, '_last_move_failed'):
                user._last_move_failed = False
            
            return message
        
        # Refresh - cure burn, poison, or paralysis
        if move_lower == "refresh":
            gen_refresh = get_generation(field_effects=field_effects, battle_state=battle_state)
            
            # Gen VIII+: Cannot be selected
            if gen_refresh >= 8:
                return f"**{user.species}** used **{move_name}**!\nBut it failed! (Cannot be selected in Gen VIII+)"
            
            # Z-Refresh: Restore all HP
            if hasattr(user, '_is_z_move') and user._is_z_move:
                old_hp = user.hp
                user.hp = user.max_hp
                heal_amount = user.hp - old_hp
                return f"**{user.species}** used **{move_name}**!\n{user.species} regained all its HP! (+{heal_amount} HP)"
            
            # Regular Refresh: Cure burn, poison, or paralysis (not freeze or sleep)
            if user.status:
                status_lower = user.status.lower()
                if status_lower in ["brn", "burn", "psn", "poison", "tox", "badly-poisoned", "par", "paralysis"]:
                    user.status = None
                    status_names = {
                        "brn": "burn", "burn": "burn",
                        "psn": "poison", "poison": "poison",
                        "tox": "badly-poisoned", "badly-poisoned": "badly-poisoned",
                        "par": "paralysis", "paralysis": "paralysis"
                    }
                    cured_status = status_names.get(status_lower, "status condition")
                    return f"**{user.species}** used **{move_name}**!\n{user.species} was cured of its {cured_status}!"
                else:
                    return f"**{user.species}** used **{move_name}**!\nBut it failed!"
            else:
                return f"**{user.species}** used **{move_name}**!\nBut it failed!"
        
        if effect_data.get("all_consume_berries"):
            base_msg = f"**{user.species}** used **{move_name}**!"
            teatime_messages = apply_teatime(user, battle_state=battle_state, opponent=target)
            if not teatime_messages:
                teatime_messages = ["But nothing happened!"]
            return base_msg + "\n" + "\n".join(teatime_messages)
        
        # Life Dew, Lunar Blessing - heal user and ally
        if effect_data.get("heals_user_and_ally"):
            heal_fraction = effect_data["heals_user_and_ally"]
            base_msg = f"**{user.species}** used **{move_name}**!"
            
            heal_targets: List[Mon] = []
            seen_ids = set()
            user_owner_id = _resolve_owner_id(user) if battle_state else None
            
            def _add_heal_target(mon_obj: Optional[Mon]) -> None:
                if not mon_obj or mon_obj.hp <= 0:
                    return
                mon_id = id(mon_obj)
                if mon_id not in seen_ids:
                    seen_ids.add(mon_id)
                    heal_targets.append(mon_obj)
            
            _add_heal_target(user)
            if target is not None and target is not user and battle_state:
                try:
                    target_owner = _resolve_owner_id(target)
                except Exception:
                    target_owner = None
                if target_owner is not None and target_owner == user_owner_id:
                    _add_heal_target(target)
            
            if battle_state:
                try:
                    active_mon = battle_state._active(user_owner_id)
                except Exception:
                    active_mon = None
                if active_mon and active_mon is not user:
                    _add_heal_target(active_mon)
            
            healed_lines: List[str] = []
            any_healed = False
            for mon in heal_targets:
                if getattr(mon, "heal_blocked", 0) > 0:
                    continue
                heal_amount = int(mon.max_hp * heal_fraction)
                if heal_amount <= 0:
                    continue
                actual_heal = min(heal_amount, mon.max_hp - mon.hp)
                if actual_heal > 0:
                    mon.hp = min(mon.max_hp, mon.hp + actual_heal)
                    healed_lines.append(f"{mon.species} regained {actual_heal} HP!")
                    any_healed = True
            
            if not any_healed:
                if hasattr(user, "_last_move_failed"):
                    user._last_move_failed = True
                return base_msg + "\nBut it failed!"
            
            return base_msg + "\n" + "\n".join(healed_lines)
        
        # ACCURACY/EVASION MANIPULATION
        # Lock-On, Mind Reader - next move can't miss
        if effect_data.get("ensures_next_hit"):
            gen_mr = get_generation(field_effects=field_effects)
            
            if move_lower == "mind-reader":
                # Gen IX: Banned
                if gen_mr >= 9:
                    return f"**{user.species}** used **{move_name}**!\nBut it failed! (Cannot be selected in Gen IX)"
                
                # Fail if target has substitute
                if hasattr(target, 'substitute') and target.substitute:
                    return f"**{user.species}** used **{move_name}**!\nBut it failed!"
                
                # Gen II: Effect attached to target (any attacker benefits)
                if gen_mr == 2:
                    # Check if already active on target (fails if active)
                    if hasattr(target, '_mind_reader_active') and target._mind_reader_active:
                        return f"**{user.species}** used **{move_name}**!\nBut it failed!"
                    target._mind_reader_active = True
                    return f"**{user.species}** used **{move_name}**!\n{target.species} became easier to hit!"
                
                # Gen III-IV: Only one Pokémon can have effect on a target
                elif gen_mr <= 4:
                    # Check if another Pokémon already has effect on this target
                    if hasattr(target, '_mind_reader_user') and target._mind_reader_user != user:
                        # Overwrites for previous Pokémon
                        prev_user = target._mind_reader_user
                        if hasattr(prev_user, '_mind_reader_target'):
                            prev_user._mind_reader_target = None
                            prev_user._mind_reader_turns = 0
                    
                    # Check if user already has effect on this target
                    if hasattr(user, '_mind_reader_target') and user._mind_reader_target == target:
                        return f"**{user.species}** used **{move_name}**!\nBut it failed!"
                    
                    user.lock_on_target = target
                    user.lock_on_turns = 2  # Expires end of next turn
                    user._mind_reader_target = target
                    target._mind_reader_user = user
                    return f"**{user.species}** used **{move_name}**!\n{user.species} took aim at {target.species}!"
                
                # Gen V+: Multiple Pokémon can have effect on same target
                else:
                    # Only fails if user already has it active on this target
                    if hasattr(user, '_mind_reader_target') and user._mind_reader_target == target:
                        return f"**{user.species}** used **{move_name}**!\nBut it failed!"
                    
                    user.lock_on_target = target
                    user.lock_on_turns = 2  # Expires end of next turn
                    user._mind_reader_target = target
                    
                    # Z-Mind Reader: +1 Special Attack
                    if hasattr(user, '_is_z_move') and user._is_z_move:
                        z_msgs = modify_stages(user, {"spa": 1}, caused_by_opponent=False, field_effects=field_effects)
                        main_msg = f"**{user.species}** used **{move_name}**!\n{user.species} took aim at {target.species}!"
                        for z_msg in z_msgs:
                            main_msg += f"\n{z_msg}"
                        return main_msg
                    
                    return f"**{user.species}** used **{move_name}**!\n{user.species} took aim at {target.species}!"
            else:
                # Lock-On: Generation-specific behavior
                if hasattr(target, 'substitute') and target.substitute:
                    return f"**{user.species}** used **{move_name}**!\nBut it failed!"
                
                # Apply Lock-On effect (similar to Mind Reader Gen V+)
                    user.lock_on_target = target
                    user.lock_on_turns = 2  # Expires end of next turn
                    user._mind_reader_target = target
                
                # Z-Lock-On: +1 Speed (user)
                if hasattr(user, '_is_z_move') and user._is_z_move:
                    z_msgs_lock = modify_stages(user, {"spe": 1}, caused_by_opponent=False, field_effects=field_effects)
                    main_msg = f"**{user.species}** used **{move_name}**!\n{user.species} took aim at {target.species}!"
                    for z_msg in z_msgs_lock:
                        main_msg += f"\n{z_msg}"
                    return main_msg
                
                    return f"**{user.species}** used **{move_name}**!\n{user.species} took aim at {target.species}!"
        
        # Foresight - complex generation-specific mechanics (Gen VIII+ banned)
        if move_lower == "foresight":
            gen_foresight = get_generation(field_effects=field_effects, battle_state=battle_state)
            
            # Gen VIII+: Banned (cannot be selected)
            if gen_foresight >= 8:
                return f"**{user.species}** used **{move_name}**!\nBut it failed! (Cannot be selected in Gen VIII+)"
            
            # Check for Magic Coat reflection (using gen_specific flag)
            move_effect_foresight = get_move_secondary_effect(move_name)
            gen_specific_foresight = move_effect_foresight.get("gen_specific", {}) if move_effect_foresight else {}
            reflected_by_magic_coat_foresight = None
            if gen_specific_foresight:
                def _match_gen_foresight(spec: str, gen: int) -> bool:
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
                for spec, overrides in gen_specific_foresight.items():
                    if isinstance(overrides, dict) and "reflected_by_magic_coat" in overrides:
                        if _match_gen_foresight(str(spec), gen_foresight):
                            reflected_by_magic_coat_foresight = overrides.get("reflected_by_magic_coat")
                            break
            if reflected_by_magic_coat_foresight is True and getattr(target, 'magic_coat', False):
                    target.magic_coat = False
                    # Reflect back onto user
                    user._foresight_active = True
                    user._foresight_ghost_immunity_removed = True
                    user._foresight_perfect_acc = True  # Gen V-VII: Always perfect accuracy
                    user._foresight_evasion_ignored = True  # Gen V-VII: Always ignore evasion
                    return f"**{user.species}** used **{move_name}**!\n{target.species}'s Magic Coat bounced the Foresight back onto {user.species}!"
            
            # Gen II: Complex accuracy/evasion balancing
            if gen_foresight == 2:
                # Fail if already active
                if hasattr(target, '_foresight_active') and target._foresight_active:
                    return f"**{user.species}** used **{move_name}**!\nBut it failed!"
                
                # If user's accuracy < target's evasion, both treated as 0 during accuracy checks
                user_acc_stage = user.stages.get("accuracy", 0)
                target_ev_stage = target.stages.get("evasion", 0)
                if user_acc_stage < target_ev_stage:
                    # Set flag to treat both as 0 during accuracy checks (not permanently set stages)
                    target._foresight_acc_ev_balanced = True
                    target._foresight_user_acc_stage = user_acc_stage
                    target._foresight_target_ev_stage = target_ev_stage
                
                target._foresight_active = True
                target._foresight_ghost_immunity_removed = True  # Removes Ghost immunity to Normal/Fighting
                # Gen II: Can be Baton Passed (stored in battle_state for transfer)
                # Note: Baton Pass transfer is handled in apply_baton_pass and apply_switch
                return f"**{user.species}** used **{move_name}**!\n{target.species} was identified!"
            
            # Gen III+: Ignores target's evasion stat stages
            elif gen_foresight >= 3:
                # Gen III: Can be used on Pokémon already under effect (no fail check)
                # Gen V-VII: Fails if already active (already checked above for Magic Coat)
                if 5 <= gen_foresight <= 7:
                    if hasattr(target, '_foresight_active') and target._foresight_active:
                        return f"**{user.species}** used **{move_name}**!\nBut it failed!"
                
                target_ev_stage = target.stages.get("evasion", 0)
                
                # Gen III: Always ignore evasion changes
                # Gen IV: Only ignore if evasion > 0
                # Gen V+: Always ignore evasion changes
                if gen_foresight == 4:
                    # Gen IV: Only ignore if evasion > 0
                    if target_ev_stage > 0:
                        target._foresight_evasion_ignored = True
                else:
                    # Gen III, V+: Always ignore evasion changes
                    target._foresight_evasion_ignored = True
                
                # Gen IV+: Bypasses accuracy checks (always hits unless semi-invulnerable)
                if gen_foresight >= 4:
                    target._foresight_perfect_acc = True
                
                target._foresight_active = True
                target._foresight_ghost_immunity_removed = True  # Removes Ghost immunity to Normal/Fighting
                # Gen III+: Cannot be Baton Passed (effect ends on switch-out)
            
            # Z-Foresight: +2 critical hit ratio (user)
            if hasattr(user, '_is_z_move') and user._is_z_move:
                # Z-Foresight: +2 critical hit ratio
                if not hasattr(user, 'focused_energy_stage'):
                    user.focused_energy_stage = 0
                user.focused_energy_stage = min(6, user.focused_energy_stage + 2)
                user.focused_energy = True
                main_msg = f"**{user.species}** used **{move_name}**!\n{target.species} was identified!\n{user.species}'s critical hit ratio rose sharply!"
                return main_msg
            
            return f"**{user.species}** used **{move_name}**!\n{target.species} was identified!"
        
        # Foresight, Odor Sleuth - removes evasion and Ghost immunity
        if effect_data.get("removes_evasion_ghost_immunity"):
            target.identified = True
            target.evasion_ignored = True
            return f"**{user.species}** used **{move_name}**!\n{target.species} was identified!"
        
        # Miracle Eye - removes evasion and Dark immunity to Psychic
        if effect_data.get("removes_evasion_dark_immunity"):
            target.miracle_eyed = True
            target.evasion_ignored = True
            return f"**{user.species}** used **{move_name}**!\n{target.species} was identified!"
        
        # ABILITY MANIPULATION
        # Role Play - copy target's ability
        if effect_data.get("copies_ability"):
            # Ability Shield protects holder's ability from being changed/suppressed/swapped
            if item_is_active(target) and target.item:
                t_item = normalize_item_name(target.item)
                t_data = get_item_effect(t_item)
                if t_data.get("protects_ability"):
                    return f"**{user.species}** used **{move_name}**!\n{target.species}'s Ability Shield protected its ability!"
            if target.ability:
                user.ability = target.ability
                return f"**{user.species}** used **{move_name}**!\n{user.species} copied {target.species}'s {target.ability}!"
            else:
                return f"**{user.species}** used **{move_name}**!\nBut it failed!"
        
        # Skill Swap - swap abilities
        if effect_data.get("swaps_abilities"):
            if item_is_active(user) and user.item:
                if get_item_effect(normalize_item_name(user.item)).get("protects_ability"):
                    return f"**{user.species}** used **{move_name}**!\n{user.species}'s Ability Shield protected its ability!"
            if item_is_active(target) and target.item:
                if get_item_effect(normalize_item_name(target.item)).get("protects_ability"):
                    return f"**{user.species}** used **{move_name}**!\n{target.species}'s Ability Shield protected its ability!"
            if user.ability and target.ability:
                user.ability, target.ability = target.ability, user.ability
                return f"**{user.species}** used **{move_name}**!\nThe two Pokémon swapped abilities!"
            else:
                return f"**{user.species}** used **{move_name}**!\nBut it failed!"
        
        # Gastro Acid - suppress ability
        if effect_data.get("suppresses_ability"):
            if item_is_active(target) and target.item:
                if get_item_effect(normalize_item_name(target.item)).get("protects_ability"):
                    return f"**{user.species}** used **{move_name}**!\n{target.species}'s Ability Shield protected its ability!"
            target.ability_suppressed = True
            return f"**{user.species}** used **{move_name}**!\n{target.species}'s ability was suppressed!"
        
        # Worry Seed, Simple Beam - change ability
        if effect_data.get("changes_ability"):
            if item_is_active(target) and target.item:
                if get_item_effect(normalize_item_name(target.item)).get("protects_ability"):
                    return f"**{user.species}** used **{move_name}**!\n{target.species}'s Ability Shield protected its ability!"
            new_ability = effect_data["changes_ability"]
            target.ability = new_ability
            return f"**{user.species}** used **{move_name}**!\n{target.species}'s ability became {new_ability}!"
        
        # Entrainment - copy ability to target
        if effect_data.get("copies_ability_to_target"):
            if item_is_active(target) and target.item:
                if get_item_effect(normalize_item_name(target.item)).get("protects_ability"):
                    return f"**{user.species}** used **{move_name}**!\n{target.species}'s Ability Shield protected its ability!"
            if user.ability:
                target.ability = user.ability
                return f"**{user.species}** used **{move_name}**!\n{target.species} acquired {user.ability}!"
            else:
                return f"**{user.species}** used **{move_name}**!\nBut it failed!"
        
        # TYPE MANIPULATION
        # Forest's Curse, Trick-or-Treat - add type
        if effect_data.get("adds_type"):
            added_type = effect_data["adds_type"]
            target_types = [t.strip().title() for t in target.types if t]

            fail_if_type = effect_data.get("fails_if_target_has_type")
            if fail_if_type:
                fail_if_type = fail_if_type.strip().title()
                if fail_if_type in target_types:
                    user._last_move_failed = True
                    return f"**{user.species}** used **{move_name}**!\nBut it failed! ({target.species} is already {fail_if_type}-type)"

            if effect_data.get("fails_if_target_terastallized") and getattr(target, 'terastallized', False):
                user._last_move_failed = True
                return f"**{user.species}** used **{move_name}**!\nBut it failed! ({target.species} is Terastallized!)"

            normalized_added = added_type.strip().title()
            updated_types = [t for t in target.types if t]

            if effect_data.get("replaces_added_type") and len(updated_types) >= 2:
                if len(updated_types) >= 3:
                    updated_types[2] = normalized_added
                else:
                    if normalized_added not in updated_types:
                        updated_types.append(normalized_added)
            else:
                if normalized_added not in updated_types:
                    updated_types.append(normalized_added)

            # Ensure tuple preserves up to three typings, pad with None if needed
            while len(updated_types) < 2:
                updated_types.append(None)
            if len(updated_types) > 3:
                updated_types = updated_types[:3]
            target.types = tuple(updated_types)

            return f"**{user.species}** used **{move_name}**!\n{target.species} acquired the {normalized_added} type!"
        
        # Soak, Magic Powder - change type
        if effect_data.get("changes_type"):
            new_type = effect_data["changes_type"]
            target.types = (new_type, None)
            return f"**{user.species}** used **{move_name}**!\n{target.species} became pure {new_type}-type!"
        
        # Conversion - change type to match first move
        if effect_data.get("changes_type_to_move"):
            if hasattr(user, 'moves') and user.moves:
                first_move = user.moves[0]
                move_data = load_move(first_move, generation=generation_for_move_data, battle_state=battle_state)
                if move_data:
                    new_type = move_data.get("type", "Normal")
                    user.types = (new_type, None)
                    return f"**{user.species}** used **{move_name}**!\n{user.species} became {new_type}-type!"
            return f"**{user.species}** used **{move_name}**!\nBut it failed!"
        
        # Reflect Type - copy target's types
        if effect_data.get("copies_target_types"):
            user.types = target.types
            return f"**{user.species}** used **{move_name}**!\n{user.species}'s type changed to match {target.species}!"
        
        if effect_data.get("copies_target_stat_stages"):
            psych_generation = get_generation(battle_state=battle_state, field_effects=field_effects)

            target_stages = getattr(target, 'stages', None)
            if not isinstance(target_stages, dict):
                target_stages = {"atk": 0, "defn": 0, "spa": 0, "spd": 0, "spe": 0, "accuracy": 0, "evasion": 0}

            if psych_generation == 2:
                if all(value == 0 for value in target_stages.values()):
                    return f"**{user.species}** used **{move_name}**!\nBut it failed!"

            if psych_generation >= 6 and target_side:
                blocked, block_msg = check_crafty_shield(None, target_side, "status")
                if blocked:
                    return f"**{user.species}** used **{move_name}**!\n{block_msg}"

            if not hasattr(user, 'stages') or not isinstance(user.stages, dict):
                user.stages = {"atk": 0, "defn": 0, "spa": 0, "spd": 0, "spe": 0, "accuracy": 0, "evasion": 0}

            # Reset user's stages then copy
            for key in set(list(user.stages.keys()) + list(target_stages.keys())):
                user.stages[key] = target_stages.get(key, 0)

            if psych_generation >= 6:
                user.focused_energy = getattr(target, 'focused_energy', False)
                user.focused_energy_stage = getattr(target, 'focused_energy_stage', 0)
            else:
                # Gen II-V: Psych Up clears user's crit boosts
                user.focused_energy = False
                user.focused_energy_stage = 0

            return f"**{user.species}** used **{move_name}**!\n{user.species} copied {target.species}'s stat changes!"
        
        # Ion Deluge - make Normal moves Electric this turn
        if effect_data.get("makes_normal_electric"):
            if not hasattr(field_effects, 'ion_deluge'):
                field_effects.ion_deluge = True
            return f"**{user.species}** used **{move_name}**!\nA deluge of ions showers the battlefield!"
        
        # SPECIAL MOVES
        # Metronome - call random move
        if effect_data.get("calls_random_move"):
            # random already imported at top of file
            # Get list of all moves (would need to query database or have a list)
            # For now, return placeholder
            return f"**{user.species}** used **{move_name}**!\nMetronome is waving..."
        
        # Sleep Talk - use random move while asleep
        if effect_data.get("uses_random_move_while_asleep"):
            if user.status == "slp":
                if hasattr(user, 'moves') and user.moves:
                    # random already imported at top of file
                    random_move = random.choice(user.moves)
                    return f"**{user.species}** used **{move_name}**!\n{user.species} used {random_move} in its sleep!"
                else:
                    return f"**{user.species}** used **{move_name}**!\nBut it failed!"
            else:
                return f"**{user.species}** used **{move_name}**!\nBut it failed!"
        
        # Mimic - copy last move
        if effect_data.get("copies_last_move"):
            if hasattr(target, 'last_move_used') and target.last_move_used:
                # Would need to replace one of user's moves with the copied move
                return f"**{user.species}** used **{move_name}**!\n{user.species} learned {target.last_move_used}!"
            else:
                return f"**{user.species}** used **{move_name}**!\nBut it failed!"
        
        # Sketch - permanently copy move
        if effect_data.get("permanently_copies_move"):
            if hasattr(target, 'last_move_used') and target.last_move_used:
                return f"**{user.species}** used **{move_name}**!\n{user.species} sketched {target.last_move_used}!"
            else:
                return f"**{user.species}** used **{move_name}**!\nBut it failed!"
        
        # Copycat - copy last move used
        if effect_data.get("copies_last_move_used"):
            if hasattr(target, 'last_move_used') and target.last_move_used:
                return f"**{user.species}** used **{move_name}**!\n{user.species} copied {target.last_move_used}!"
            else:
                return f"**{user.species}** used **{move_name}**!\nBut it failed!"
        
        # Me First - use target's move with 1.5x power (must go first)
        if move_lower == "me-first":
            
            generation = get_generation(field_effects=field_effects, battle_state=battle_state)
            
            # Gen VIII+: Banned
            if generation >= 8:
                return f"**{user.species}** used **Me First**!\nBut it failed! (Me First cannot be selected in Generation {generation})"
            
            # Get target's chosen move
            target_chosen_move = None
            if target_choice and target_choice.get("kind") == "move":
                target_chosen_move = target_choice.get("value")
            
            # Check speeds
            user_speed = get_effective_stat(user, "spe", field_effects=field_effects)
            target_speed = get_effective_stat(target, "spe", field_effects=field_effects) if target else 0
            
            # Apply Me First
            result = apply_me_first(
                target_chosen_move,
                user_speed,
                target_speed,
                target_choice=target_choice,
                generation=generation
            )
            
            if not result:
                return f"**{user.species}** used **Me First**!\nBut it failed!"
            
            copied_move, power_mult = result
            
            # Apply the copied move with 1.5x power
            # Mark for power boost
            if not hasattr(user, '_me_first_active'):
                user._me_first_active = True
                user._me_first_power_mult = power_mult
                user._me_first_copied_move = copied_move
            
            msg = f"**{user.species}** used **Me First**!\n{user.species} stole {copied_move}!"
            
            # Execute the copied move with power boost
            # Power boost is applied in damage() function
            recursive_result = apply_move(user, target, copied_move, field_effects, target_side, 
                                        user_choice, target_choice, battle_state)
            
            # Clear flag
            user._me_first_active = False
            if hasattr(user, '_me_first_power_mult'):
                delattr(user, '_me_first_power_mult')
            if hasattr(user, '_me_first_copied_move'):
                delattr(user, '_me_first_copied_move')
            
            return msg + "\n\n" + recursive_result
        
        # Assist - use random move from party
        if effect_data.get("uses_ally_move"):
            # Would need to access party moves
            return f"**{user.species}** used **{move_name}**!\n{user.species} used a party member's move!"
        
        # Nature Power - use move based on terrain
        if effect_data.get("uses_terrain_move"):
            terrain = getattr(field_effects, 'terrain', None) if field_effects else None
            terrain_moves = {
                "electric": "Thunderbolt",
                "grassy": "Energy Ball",
                "misty": "Moonblast",
                "psychic": "Psychic"
            }
            nature_move = terrain_moves.get(terrain, "Tri Attack")
            
            # Actually execute the terrain move
            msg = f"**{user.species}** used **{move_name}**!\n{user.species} unleashed {nature_move}!"
            recursive_result = apply_move(user, target, nature_move, field_effects, target_side, 
                                        user_choice, target_choice, battle_state, is_moving_last)
            return msg + "\n\n" + recursive_result
        
        # Ally Switch - switch positions with ally (doubles)
        if effect_data.get("switches_position"):
            generation = get_generation(field_effects=field_effects, battle_state=battle_state)
            
            if generation >= 9:
                consecutive = getattr(user, '_consecutive_ally_switches', 0)
                success_chance = 1.0 if consecutive == 0 else (0.5) ** consecutive
                if random.random() >= success_chance:
                    user._consecutive_ally_switches = 0
                    user._last_move_failed = True
                    return f"**{user.species}** used **{move_name}**!\nBut it failed!"
                user._consecutive_ally_switches = consecutive + 1
            else:
                user._consecutive_ally_switches = 0
            
            main_msg = f"**{user.species}** used **{move_name}**!\n{user.species} swapped positions with its ally!"
            
            if hasattr(user, '_is_z_move') and user._is_z_move:
                z_effect = effect_data.get("z_boost_effect", {})
                stat_boost = z_effect.get("stat_boost", {})
                if stat_boost:
                    z_msgs = modify_stages(user, stat_boost, caused_by_opponent=False, field_effects=field_effects)
                    for z_msg in z_msgs:
                        main_msg += f"\n{z_msg}"
            
            if hasattr(user, '_last_move_failed'):
                user._last_move_failed = False
            
            return main_msg
        
        # Doodle - copy ability to user and ally (doubles)
        if effect_data.get("copies_ability_to_user_and_ally"):
            if target.ability:
                user.ability = target.ability
                return f"**{user.species}** used **{move_name}**!\n{user.species} and its ally copied {target.ability}!"
            else:
                return f"**{user.species}** used **{move_name}**!\nBut it failed!"
        
        # STAT SWAP/SPLIT MOVES
        # Power Split - average offensive stats
        if effect_data.get("averages_offensive_stats"):
            user_atk = user.stats.get("atk", 100)
            user_spa = user.stats.get("spa", 100)
            target_atk = target.stats.get("atk", 100)
            target_spa = target.stats.get("spa", 100)
            avg_atk = (user_atk + target_atk) // 2
            avg_spa = (user_spa + target_spa) // 2
            user.stats["atk"] = avg_atk
            user.stats["spa"] = avg_spa
            target.stats["atk"] = avg_atk
            target.stats["spa"] = avg_spa
            return f"**{user.species}** used **{move_name}**!\nThe two Pokémon shared their power!"
        
        # Guard Split - average defensive stats
        if effect_data.get("averages_defensive_stats"):
            user_def = user.stats.get("defn", 100)
            user_spd = user.stats.get("spd", 100)
            target_def = target.stats.get("defn", 100)
            target_spd = target.stats.get("spd", 100)
            avg_def = (user_def + target_def) // 2
            avg_spd = (user_spd + target_spd) // 2
            user.stats["defn"] = avg_def
            user.stats["spd"] = avg_spd
            target.stats["defn"] = avg_def
            target.stats["spd"] = avg_spd
            return f"**{user.species}** used **{move_name}**!\nThe two Pokémon shared their guard!"
        
        # Power Swap - swap offensive stat stages
        if effect_data.get("swaps_offensive_stats"):
            if hasattr(user, 'stages') and hasattr(target, 'stages'):
                user.stages["atk"], target.stages["atk"] = target.stages["atk"], user.stages["atk"]
                user.stages["spa"], target.stages["spa"] = target.stages["spa"], user.stages["spa"]
                return f"**{user.species}** used **{move_name}**!\nThe Pokémon swapped offensive stat changes!"
            else:
                return f"**{user.species}** used **{move_name}**!\nBut it failed!"
        
        # Guard Swap - swap defensive stat stages
        if effect_data.get("swaps_defensive_stats"):
            if hasattr(user, 'stages') and hasattr(target, 'stages'):
                user.stages["defn"], target.stages["defn"] = target.stages["defn"], user.stages["defn"]
                user.stages["spd"], target.stages["spd"] = target.stages["spd"], user.stages["spd"]
                return f"**{user.species}** used **{move_name}**!\nThe Pokémon swapped defensive stat changes!"
            else:
                return f"**{user.species}** used **{move_name}**!\nBut it failed!"
        
        # Speed Swap - swap actual Speed stats (not stages)
        if effect_data.get("swaps_speed_stats"):
            if not hasattr(user, 'stats') or not hasattr(target, 'stats'):
                return f"**{user.species}** used **{move_name}**!\nBut it failed!"
            user_speed = user.stats.get("spe")
            target_speed = target.stats.get("spe")
            if user_speed is None or target_speed is None:
                return f"**{user.species}** used **{move_name}**!\nBut it failed!"
            user.stats["spe"], target.stats["spe"] = target_speed, user_speed
            return f"**{user.species}** used **{move_name}**!\nThe Pokémon swapped Speed!"
        
        # Heart Swap - swap all stat stages
        if effect_data.get("swaps_all_stat_stages"):
            if hasattr(user, 'stages') and hasattr(target, 'stages'):
                user.stages, target.stages = target.stages, user.stages
                return f"**{user.species}** used **{move_name}**!\nThe Pokémon switched stat changes!"
            else:
                return f"**{user.species}** used **{move_name}**!\nBut it failed!"
        
        # SACRIFICE MOVES
        # Memento - faint user, lower target's offenses
        # Good as Gold: Memento fails and does not cause the user to faint
        if effect_data.get("faints_user") and move_lower == "memento":
            target_ability_memento = normalize_ability_name(target.ability or "")
            if target_ability_memento == "good-as-gold":
                user._last_move_failed = True
                return f"**{user.species}** used **{move_name}**!\nBut it failed! ({target.species}'s Good as Gold prevented it!)"
            # Check if this is Z-Memento
            if hasattr(user, '_is_z_move') and user._is_z_move and hasattr(user, '_original_move_name') and user._original_move_name.lower().replace(" ", "-") == "memento":
                # Z-Memento: Heal replacement fully (set flag on user's side for when Pokemon switches in)
                # Store flag in battle_state's side effects
                if battle_state:
                    user_side = battle_state.p1_side if user == battle_state._active(battle_state.p1_id) else battle_state.p2_side
                    if user_side:
                        user_side._z_memento_pending = True
                # Still faint and lower stats
                user.hp = 0
                if "stat_drop" in effect_data:
                    drop_messages = modify_stages(target, effect_data["stat_drop"])
                    main_msg = f"**{user.species}** used **{move_name}**!\n{user.species} fainted!"
                    for msg in drop_messages:
                        main_msg += f"\n{msg}"
                    main_msg += f"\n(Z-Memento: The next Pokémon sent out will be fully healed!)"
                    return main_msg
                return f"**{user.species}** used **{move_name}**!\n{user.species} fainted!\n(Z-Memento: The next Pokémon sent out will be fully healed!)"
            
            # Regular Memento
            user.hp = 0
            if "stat_drop" in effect_data:
                drop_messages = modify_stages(target, effect_data["stat_drop"])
                main_msg = f"**{user.species}** used **{move_name}**!\n{user.species} fainted!"
                for msg in drop_messages:
                    main_msg += f"\n{msg}"
                return main_msg
            return f"**{user.species}** used **{move_name}**!\n{user.species} fainted!"
        
        # Other sacrifice moves (Healing Wish, Lunar Dance)
        if effect_data.get("faints_user"):
            user.hp = 0
            if "stat_drop" in effect_data:
                drop_messages = modify_stages(target, effect_data["stat_drop"])
                main_msg = f"**{user.species}** used **{move_name}**!\n{user.species} fainted!"
                for msg in drop_messages:
                    main_msg += f"\n{msg}"
                return main_msg
            return f"**{user.species}** used **{move_name}**!\n{user.species} fainted!"
        
        # Healing Wish - faint user, heal replacement
        if effect_data.get("heals_replacement"):
            user.hp = 0
            if battle_state:
                owner_id = _resolve_owner_id(user)
                if hasattr(battle_state, "_pending_healing_wish"):
                    battle_state._pending_healing_wish[owner_id] = True
            user._healing_wish = True
            return f"**{user.species}** used **{move_name}**!\n{user.species} fainted!\nA healing wish was made!"
        
        # Lunar Dance - faint user, fully heal replacement
        if effect_data.get("heals_replacement_full"):
            user.hp = 0
            if battle_state:
                owner_id = _resolve_owner_id(user)
                if hasattr(battle_state, "_pending_lunar_dance"):
                    battle_state._pending_lunar_dance[owner_id] = True
            user._lunar_dance = True
            return f"**{user.species}** used **{move_name}**!\n{user.species} fainted!\nIt became cloaked in mystical moonlight!"
        
        # FIELD MANIPULATION
        # Mud Sport - weaken Electric moves
        if effect_data.get("weakens_electric"):
            gen_mud = get_generation(field_effects=field_effects, battle_state=battle_state)
            
            # Gen VIII+: Cannot be selected
            if gen_mud >= 8:
                return f"**{user.species}** used **{move_name}**!\nBut it failed! (Cannot be selected in Gen VIII+)"
            
            # Z-Mud Sport: +1 Special Defense (user)
            if hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs = modify_stages(user, {"spd": 1}, caused_by_opponent=False, field_effects=field_effects)
                main_msg = f"**{user.species}** used **{move_name}**!"
                for z_msg in z_msgs:
                    main_msg += f"\n{z_msg}"
                # Still set up Mud Sport
            if not hasattr(field_effects, 'mud_sport'):
                field_effects.mud_sport = effect_data.get("duration", 5)
                main_msg += f"\nElectricity's power was weakened!"
                return main_msg
            
            # Generation-specific duration
            # Gen III-IV: Until user switches out
            # Gen V+: 5 turns (if not switched out)
            if gen_mud <= 4:
                # Until switch - no turn limit, track user
                field_effects.mud_sport = True
                field_effects.mud_sport_turns = 0  # 0 = infinite (until switch)
                field_effects.mud_sport_user = id(user)  # Track user for switch check
            else:
                # Gen V+: 5 turns
                field_effects.mud_sport = True
                field_effects.mud_sport_turns = effect_data.get("duration", 5)
                field_effects.mud_sport_user = None
            
            return f"**{user.species}** used **{move_name}**!\nElectricity's power was weakened!"
        
        # Water Sport - weaken Fire moves
        if effect_data.get("weakens_fire"):
            gen_water_sport = get_generation(field_effects=field_effects, battle_state=battle_state)
            
            # Gen VIII+: Cannot be selected
            if gen_water_sport >= 8:
                return f"**{user.species}** used **{move_name}**!\nBut it failed! (Cannot be selected in Gen VIII+)"
            
            # Z-Water Sport: +1 Special Defense (user)
            if hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs = modify_stages(user, {"spd": 1}, caused_by_opponent=False, field_effects=field_effects)
                main_msg = f"**{user.species}** used **{move_name}**!"
                for z_msg in z_msgs:
                    main_msg += f"\n{z_msg}"
                # Still set up Water Sport
            else:
                main_msg = f"**{user.species}** used **{move_name}**!"
            
            # Generation-specific duration and behavior
            # Gen III-IV: Until user switches out (ends_on_switch = True)
            # Gen V: 5 turns, 67% reduction (1352/4096)
            # Gen VI-VII: 5 turns, 50% reduction
            if gen_water_sport <= 4:
                # Until switch - no turn limit, track user
                field_effects.water_sport = True
                field_effects.water_sport_turns = 0  # 0 = infinite (until switch)
                field_effects.water_sport_user = id(user)  # Track user for switch check
            else:
                # Gen V+: 5 turns
                field_effects.water_sport = True
                field_effects.water_sport_turns = effect_data.get("duration", 5)
                field_effects.water_sport_user = None
            
            main_msg += f"\nFire's power was weakened!"
            return main_msg
        
        # ADDITIONAL STATUS CONDITIONS
        # Ingrain - heal 1/16 HP per turn, can't switch
        if effect_data.get("plants_ingrain"):
            # Z-Ingrain: +1 Special Defense
            if hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs = modify_stages(user, {"spd": 1}, caused_by_opponent=False, field_effects=field_effects)
                main_msg = f"**{user.species}** used **{move_name}**!"
                for z_msg in z_msgs:
                    main_msg += f"\n{z_msg}"
                # Z-Ingrain doesn't plant roots
                return main_msg
            
            if getattr(user, 'ingrained', False) or getattr(user, '_ingrained', False):
                return f"**{user.species}** used **{move_name}**!\nBut it failed! ({user.species} is already rooted)"


            ingrain_gen = get_generation(field_effects=field_effects)
            user.ingrained = True
            user._ingrained = True
            user._ingrain_generation = ingrain_gen
            return f"**{user.species}** used **{move_name}**!\n{user.species} planted its roots!"
        
        # Magnet Rise - Ground immunity for 5 turns
        if effect_data.get("levitates"):
            gen_mr = get_generation(field_effects=field_effects)
            
            # Gen IV: Fails if Ingrain or Gravity
            if gen_mr == 4:
                if getattr(user, 'ingrained', False) or getattr(user, '_ingrained', False):
                    return f"**{user.species}** used **{move_name}**!\nBut it failed! ({user.species} is rooted)"
                if field_effects and getattr(field_effects, 'gravity', False):
                    return f"**{user.species}** used **{move_name}**!\nBut it failed! (Gravity is in effect)"
            
            # Gen V+: Removed by Smack Down or Thousand Arrows
            # If already active, fails (Gen V+)
            if gen_mr >= 5:
                if hasattr(user, '_magnet_rise_turns') and getattr(user, '_magnet_rise_turns', 0) > 0:
                    return f"**{user.species}** used **{move_name}**!\nBut it failed!"
            
            # Set duration (5 turns)
            duration = effect_data.get("duration", 5)
            user._magnet_rise_turns = duration
            
            # Z-Magnet Rise: +1 Evasion
            if hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs = modify_stages(user, {"evasion": 1}, caused_by_opponent=False, field_effects=field_effects)
                main_msg = f"**{user.species}** used **{move_name}**!\n{user.species} levitated with electromagnetism!"
                for z_msg in z_msgs:
                    main_msg += f"\n{z_msg}"
                return main_msg
            
            return f"**{user.species}** used **{move_name}**!\n{user.species} levitated with electromagnetism!"
        
        # Mean Look - trap target (complex generation-specific mechanics)
        if move_lower == "mean-look":
            gen_ml = get_generation(field_effects=field_effects)
            
            main_msg = f"**{user.species}** used **{move_name}**!"
            
            # Gen VI+: No longer affects Ghost-type Pokémon
            if gen_ml >= 6:
                target_types = [t.strip().title() if t else None for t in getattr(target, 'types', (None, None))]
                if "Ghost" in target_types:
                    return main_msg + f"\nIt doesn't affect {target.species}..."
            
            # Gen II: Bypasses accuracy checks, hits through Protect/Detect, always hits unless semi-invulnerable
            # Gen III+: Blocked by Protect/Detect (Gen III-IV), blocked by Crafty Shield (Gen VI+)
            if gen_ml == 2:
                # Gen II: Always hits unless target is semi-invulnerable
                if hasattr(target, 'invulnerable') and target.invulnerable:
                    return main_msg + "\nBut it failed!"
            else:
                # Gen III+: Can be blocked by protection moves
                if hasattr(target, 'protected_this_turn') and target.protected_this_turn:
                    # Check Crafty Shield (Gen VI+)
                    if gen_ml >= 6:
                        if getattr(target, 'crafty_shield_active', False):
                            return main_msg + "\nBut it failed!"
                    # Regular Protect/Detect (Gen III+)
                    if getattr(target, 'protect_active', False) or getattr(target, 'detect_active', False):
                        return main_msg + "\nBut it failed!"
            
            # Apply trapping effect
            target.trapped = True
            target.trap_source = user.species  # Track who trapped it
            
            # Gen II: Effect persists as long as user is in battle
            # Gen III-V: Can escape with Run Away or Smoke Ball (wild battles only)
            # Gen V: Can switch with Baton Pass, but trap is cleared
            # Gen VI+: Can switch with U-turn, Volt Switch, Parting Shot, Flip Turn
            # Dragon Tail/Circle Throw (Gen V+): Force switch even if trapped
            
            main_msg += f"\n{target.species} can't escape now!"
            
            # Z-Mean Look: +1 Special Defense (user)
            if hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs = modify_stages(user, {"spd": 1}, caused_by_opponent=False, field_effects=field_effects)
                for z_msg in z_msgs:
                    main_msg += f"\n{z_msg}"
            
            return main_msg
        
        # Block - trap target (generation-specific mechanics)
        if move_lower == "block":
            gen_block = get_generation(field_effects=field_effects)
            
            main_msg = f"**{user.species}** used **{move_name}**!"
            
            # Gen III-IV: Blocked by Protect/Detect
            if gen_block <= 4:
                if hasattr(target, 'protected_this_turn') and target.protected_this_turn:
                    if getattr(target, 'protect_active', False) or getattr(target, 'detect_active', False):
                        return main_msg + "\nBut it failed!"
            
            # Gen VI+: Ghost types immune
            if gen_block >= 6:
                target_types = [t.strip().title() if t else None for t in getattr(target, 'types', (None, None))]
                if "Ghost" in target_types:
                    return main_msg + f"\nIt doesn't affect {target.species}..."
            
            # Gen VI+: Bypasses Protect/Detect/Spiky Shield (but blocked by Crafty Shield)
            if gen_block >= 6:
                if hasattr(target, 'protected_this_turn') and target.protected_this_turn:
                    if getattr(target, 'crafty_shield_active', False):
                        return main_msg + "\nBut it failed!"
                    # Otherwise bypasses Protect/Detect/Spiky Shield
            
            # Apply trapping effect
            target.trapped = True
            target.trap_source = user.species
            target._block_generation = gen_block
            
            main_msg += f"\n{target.species} can't escape now!"
            
            # Z-Block: +1 Defense (user)
            if hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs_block = modify_stages(user, {"defn": 1}, caused_by_opponent=False, field_effects=field_effects)
                for z_msg in z_msgs_block:
                    main_msg += f"\n{z_msg}"
            
            return main_msg
        
        # Spider Web - trap target (Gen VIII+ banned)
        if move_lower == "spider-web":
            gen_sw = get_generation(field_effects=field_effects)
            
            # Gen VIII+: Banned
            if gen_sw >= 8:
                return f"**{user.species}** used **{move_name}**!\nBut it failed! (Cannot be selected in Gen VIII+)"
            
            if target is None or target.hp <= 0:
                return f"**{user.species}** used **{move_name}**!\nBut it failed!"
            
            # Gen VI+: Ghost types immune
            if gen_sw >= 6:
                target_types = [t.strip().title() if t else None for t in getattr(target, 'types', (None, None))]
                if "Ghost" in target_types:
                    return f"**{user.species}** used **{move_name}**!\nIt doesn't affect {target.species}..."
            
            # Trap the target
            target.trapped = True
            target.trap_source = user.species
            target._spider_web_generation = gen_sw
            
            # Z-Spider Web: +1 Defense
            if hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs = modify_stages(user, {"defn": 1}, caused_by_opponent=False, field_effects=field_effects)
                main_msg = f"**{user.species}** used **{move_name}**!\n{target.species} was trapped in the web!"
                for z_msg in z_msgs:
                    main_msg += f"\n{z_msg}"
                return main_msg
            
            return f"**{user.species}** used **{move_name}**!\n{target.species} was trapped in the web!"
        
        # Nightmare - lose 1/4 HP per turn while asleep
        if effect_data.get("nightmares_sleeping"):
            gen_nightmare = get_generation(field_effects=field_effects)
            
            # Gen VIII+: Banned
            if gen_nightmare >= 8:
                return f"**{user.species}** used **{move_name}**!\nBut it failed! (Cannot be selected in Gen VIII+)"
            
            # Check if target is asleep or has Comatose
            is_asleep = (target.status and target.status.lower() in ["slp", "sleep"])
            has_comatose = False
            target_ability_night = normalize_ability_name(target.ability or "")
            if target_ability_night == "comatose":
                has_comatose = True
            
            if is_asleep or has_comatose:
                if getattr(target, 'nightmared', False):
                    return f"**{user.species}** used **{move_name}**!\nBut it failed! ({target.species} is already having a nightmare)"
                target.nightmared = True
                target._nightmare_generation = gen_nightmare
                
                # Z-Nightmare: +1 Special Attack
                if hasattr(user, '_is_z_move') and user._is_z_move:
                    z_msgs = modify_stages(user, {"spa": 1}, caused_by_opponent=False, field_effects=field_effects)
                    return f"**{user.species}** used **{move_name}**!\n{target.species} began having a nightmare!\n" + "\n".join(z_msgs)
                
                return f"**{user.species}** used **{move_name}**!\n{target.species} began having a nightmare!"
            else:
                return f"**{user.species}** used **{move_name}**!\nBut it failed! ({target.species} is not asleep)"
        
        # Embargo - prevent item use
        if effect_data.get("embargoes_item"):
            target.embargoed = effect_data.get("duration", 5)
            return f"**{user.species}** used **{move_name}**!\n{target.species} can't use items anymore!"
        
        # Heal Block - prevent healing
        if effect_data.get("blocks_healing"):
            # === MENTAL HERB: Cures Heal Block (Gen 5+) ===
            if item_is_active(target) and target.item:
                t_item_mh6 = normalize_item_name(target.item)
                t_item_data_mh6 = get_item_effect(t_item_mh6)
                gen_mh6 = get_generation(field_effects=field_effects)
                if t_item_data_mh6.get("cures_mental_effects") and gen_mh6 >= 5:
                    target.item = None  # Consume Mental Herb
                    return f"**{user.species}** used **{move_name}**!\n{target.species}'s Mental Herb cured its mental status!"
            target.heal_blocked = effect_data.get("duration", 5)
            return f"**{user.species}** used **{move_name}**!\n{target.species} was prevented from healing!"
        
        # Imprison - opponent can't use moves user knows
        if effect_data.get("imprisons_shared_moves"):
            gen_imprison = get_generation(field_effects=field_effects, battle_state=battle_state)
            
            # Z-Imprison: +2 Special Defense
            if hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs = modify_stages(user, {"spd": 2}, caused_by_opponent=False, field_effects=field_effects)
                main_msg = f"**{user.species}** used **{move_name}**!"
                for z_msg in z_msgs:
                    main_msg += f"\n{z_msg}"
                # Still set up Imprison
                user.imprisoning = True
                user._imprisoned_moves = set(move.lower().replace(" ", "-") for move in user.moves)
                return main_msg
            
            # Track user's current moveset
            user.imprisoning = True
            user._imprisoned_moves = set(move.lower().replace(" ", "-") for move in user.moves)
            
            # Gen III-IV: Fail if no opponent has a shared move
            if gen_imprison <= 4:
                has_shared = False
                if target and target.moves:
                    for target_move in target.moves:
                        normalized = target_move.lower().replace(" ", "-")
                        if normalized in user._imprisoned_moves:
                            has_shared = True
                            break
                if not has_shared:
                    user.imprisoning = False
                    user._imprisoned_moves = set()
                    return f"**{user.species}** used **{move_name}**!\nBut it failed!"
            
            return f"**{user.species}** used **{move_name}**!\nIt sealed the opponent's moves!"
        
        # Purify - heal target's status and user's HP
        if effect_data.get("heals_target_status"):
            main_msg = f"**{user.species}** used **{move_name}**!"
            z_effect = effect_data.get("z_boost_effect", {})
            if not target.status:
                if hasattr(user, '_is_z_move') and user._is_z_move and z_effect.get("stat_boost"):
                    boost_msgs = modify_stages(user, z_effect["stat_boost"], caused_by_opponent=False, field_effects=field_effects)
                    for msg in boost_msgs:
                        main_msg += f"\n{msg}"
                return main_msg + "\nBut it failed!"
            status_names = {
                "par": "paralysis",
                "brn": "burn",
                "psn": "poison",
                "tox": "bad poison",
                "frz": "freeze",
                "slp": "sleep"
            }
            cured_status = status_names.get(target.status.lower(), "status condition") if isinstance(target.status, str) else "status condition"
            if target.status.lower() in ["tox", "psn"]:
                target.toxic_counter = 0
            target.status = None
            target.status_turns = 0
            heal_amount = max(1, user.max_hp // 2)
            old_hp = user.hp
            user.hp = min(user.max_hp, user.hp + heal_amount)
            actual_heal = user.hp - old_hp
            main_msg += f"\n{target.species}'s {cured_status} was cured!"
            main_msg += f"\n{user.species} restored {actual_heal} HP!"
            if hasattr(user, '_is_z_move') and user._is_z_move and z_effect.get("stat_boost"):
                boost_msgs = modify_stages(user, z_effect["stat_boost"], caused_by_opponent=False, field_effects=field_effects)
                for msg in boost_msgs:
                    main_msg += f"\n{msg}"
            return main_msg
        
        # ITEM MANIPULATION
        # Bestow - give item to target
        if effect_data.get("gives_item"):
            if user.item and not target.item:
                target.item = user.item
                item_name = user.item
                user.item = None
                return f"**{user.species}** used **{move_name}**!\n{user.species} gave {item_name} to {target.species}!"
            else:
                return f"**{user.species}** used **{move_name}**!\nBut it failed!"
        
        # Recycle - restore consumed item
        if effect_data.get("restores_consumed_item"):
            # Z-Recycle: +2 Speed (but move fails)
            if hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs = modify_stages(user, {"spe": 2}, caused_by_opponent=False, field_effects=field_effects)
                main_msg = f"**{user.species}** used **{move_name}**!"
                for z_msg in z_msgs:
                    main_msg += f"\n{z_msg}"
                main_msg += "\nBut it failed! (Cannot restore Z-Crystal)"
                return main_msg
            
            if hasattr(user, '_consumed_item') and user._consumed_item:
                user.item = user._consumed_item
                return f"**{user.species}** used **{move_name}**!\n{user.species} restored its {user.item}!"
            else:
                return f"**{user.species}** used **{move_name}**!\nBut it failed!"
        
        # MOVE REDIRECTION/MANIPULATION
        # Magic Coat - reflect status moves
        if effect_data.get("reflects_status_moves"):
            # Z-Magic Coat: +2 Special Defense
            if hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs = modify_stages(user, {"spd": 2}, caused_by_opponent=False, field_effects=field_effects)
                main_msg = f"**{user.species}** used **{move_name}**!"
                for z_msg in z_msgs:
                    main_msg += f"\n{z_msg}"
                # Z-Magic Coat doesn't set up reflection
                return main_msg
            
            user.magic_coat = True
            return f"**{user.species}** used **{move_name}**!\n{user.species} shrouded itself with Magic Coat!"
        
        # Snatch - steal beneficial status moves
        if effect_data.get("steals_stat_moves"):
            gen_snatch = get_generation(field_effects=field_effects, battle_state=battle_state)
            
            # Gen VIII+: Cannot be selected
            if gen_snatch >= 8:
                return f"**{user.species}** used **{move_name}**!\nBut it failed! (Cannot be selected in Gen VIII+)"
            
            # Z-Snatch: +2 Speed
            if hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs = modify_stages(user, {"spe": 2}, caused_by_opponent=False, field_effects=field_effects)
                main_msg = f"**{user.species}** used **{move_name}**!"
                for z_msg in z_msgs:
                    main_msg += f"\n{z_msg}"
                # Still set up Snatch
                user.snatching = True
                return main_msg
            
            user.snatching = True
            return f"**{user.species}** used **{move_name}**!\n{user.species} waits for a target to make a move!"
        
        # DOUBLES/TEAM MOVES (require doubles battle support)
        # Helping Hand - boost ally's move power by 1.5x (Gen III-IV), stacking (Gen V+)
        if effect_data.get("boosts_ally") or move_lower == "helping-hand":
            gen_hh = get_generation(field_effects=field_effects)
            
            main_msg = f"**{user.species}** used **{move_name}**!"
            
            # Gen III-IV: Targets user, Gen V+: Targets adjacent ally
            # Gen IV: Also boosts confusion damage (Gen V+: no longer boosts confusion)
            # Gen V+: Multiple Helping Hands stack (1x: 1.5x, 2x: 1.25x, 3x: 2.375x)
            # Gen IX: In Tera Raid Battles, stacking disabled (only base 50% increase)
            
            # Mark ally for boosting (would need battle state for full implementation)
            if not hasattr(target, '_helping_hand_boosts'):
                target._helping_hand_boosts = 0
            target._helping_hand_boosts += 1
            main_msg += f"\n{user.species} is ready to help {target.species if target else 'its ally'}!"
            
            # Z-Helping Hand: Reset all lowered stats
            if hasattr(user, '_is_z_move') and user._is_z_move:
                stat_resets = {}
                for stat in ["atk", "defn", "spa", "spd", "spe", "accuracy", "evasion"]:
                    if user.stages.get(stat, 0) < 0:
                        stat_resets[stat] = -user.stages.get(stat, 0)
                if stat_resets:
                    z_msgs = modify_stages(user, stat_resets, caused_by_opponent=False, field_effects=field_effects)
                    for z_msg in z_msgs:
                        main_msg += f"\n{z_msg}"
            
            return main_msg
        
        # Follow Me, Rage Powder - redirect attacks
        if effect_data.get("redirects_attacks"):
            gen_follow = get_generation(field_effects=field_effects)
            
            main_msg = f"**{user.species}** used **{move_name}**!\n{user.species} became the center of attention!"
            
            # Z-Follow Me: Reset all lowered stats (user)
            if hasattr(user, '_is_z_move') and user._is_z_move:
                stat_resets = {}
                for stat in ["atk", "defn", "spa", "spd", "spe", "accuracy", "evasion"]:
                    if user.stages.get(stat, 0) < 0:
                        stat_resets[stat] = -user.stages.get(stat, 0)
                if stat_resets:
                    z_msgs = modify_stages(user, stat_resets, caused_by_opponent=False, field_effects=field_effects)
                    for z_msg in z_msgs:
                        main_msg += f"\n{z_msg}"
            
            user.center_of_attention = True
            user._center_of_attention_source = move_lower
            return main_msg
        
        # After You - target moves immediately
        if effect_data.get("target_moves_immediately"):
            return f"**{user.species}** used **{move_name}**!\n{target.species} took its turn!"
        
        # Instruct - target uses move again
        if effect_data.get("target_uses_move_again"):
            base_msg = f"**{user.species}** used **{move_name}**!"
            if not battle_state or not hasattr(target, 'last_move_used') or not target.last_move_used:
                user._last_move_failed = True
                return base_msg + "\nBut it failed!"

            repeated_move = target.last_move_used
            repeated_norm = repeated_move.lower().replace(" ", "-")

            forbidden_moves = {
                "instruct",
                "bide",
                "focus-punch",
                "beak-blast",
                "shell-trap",
                "sketch",
                "transform",
                "mimic",
                "kings-shield",
                "king's-shield",
                "struggle"
            }

            if repeated_norm in forbidden_moves or getattr(target, 'dynamaxed', False):
                user._last_move_failed = True
                return base_msg + "\nBut it failed!"

            if getattr(target, '_sky_drop_cannot_move', False):
                user._last_move_failed = True
                return base_msg + "\nBut it failed!"

            if getattr(target, '_bide_active', False):
                user._last_move_failed = True
                return base_msg + "\nBut it failed!"

            if getattr(target, '_focus_punch_charging', False) or getattr(target, '_shell_trap_set', False) or getattr(target, '_beak_blast_charging', False):
                user._last_move_failed = True
                return base_msg + "\nBut it failed!"

            if getattr(target, 'must_recharge', False):
                user._last_move_failed = True
                return base_msg + "\nBut it failed!"

            if getattr(target, 'charging_move', None):
                user._last_move_failed = True
                return base_msg + "\nBut it failed!"

            if getattr(target, 'rampage_move', None) and getattr(target, 'rampage_turns_remaining', 0) > 0 and repeated_norm != "raging-fury":
                user._last_move_failed = True
                return base_msg + "\nBut it failed!"

            move_data_repeat = get_move(repeated_move, generation=generation_for_move_data, battle_state=battle_state) or {}
            move_effect_repeat = get_move_secondary_effect(repeated_move)

            if move_effect_repeat.get("bide_mechanic") or move_effect_repeat.get("charges") or move_effect_repeat.get("semi_invulnerable") or move_effect_repeat.get("must_recharge"):
                user._last_move_failed = True
                return base_msg + "\nBut it failed!"

            if move_effect_repeat.get("calls_random_move") or move_effect_repeat.get("uses_random_move_while_asleep") or move_effect_repeat.get("permanently_copies_move") or move_effect_repeat.get("copies_last_move") or move_effect_repeat.get("copies_last_move_used"):
                user._last_move_failed = True
                return base_msg + "\nBut it failed!"

            owner_id = _resolve_owner_id(target)
            if owner_id is None:
                user._last_move_failed = True
                return base_msg + "\nBut it failed!"

            # Ensure target still knows the move
            known_moves = [m.lower() for m in getattr(target, 'moves', [])]
            if repeated_move.lower() not in known_moves:
                user._last_move_failed = True
                return base_msg + "\nBut it failed!"

            # PP check and consumption (Struggle ignored)
            if repeated_norm != "struggle":
                try:
                    if battle_state._pp_left(owner_id, repeated_move) <= 0:
                        user._last_move_failed = True
                        return base_msg + "\nBut it failed!"
                    # Get target for Pressure check (Me First targets the original target)
                    target_for_pp = target if target else None
                    move_data_repeat = get_move(repeated_move, generation=generation_for_move_data, battle_state=battle_state)
                    battle_state._spend_pp(owner_id, repeated_move, target=target_for_pp, move_data=move_data_repeat)
                except Exception:
                    user._last_move_failed = True
                    return base_msg + "\nBut it failed!"

            # Determine the defender based on move target data
            move_target_code = (move_data_repeat or {}).get("target", "")
            user_target_codes = {"user", "user-or-ally", "user-and-allies", "ally-side", "user-side"}
            ally_target_codes = {"ally", "allies"}

            instructed_target = None
            instructed_target_side = None

            if move_target_code in user_target_codes:
                instructed_target = target
                instructed_target_side = battle_state.p1_side if owner_id == battle_state.p1_id else battle_state.p2_side
            elif move_target_code in ally_target_codes:
                instructed_target = target
                instructed_target_side = battle_state.p1_side if owner_id == battle_state.p1_id else battle_state.p2_side
            else:
                opponent_id = battle_state.p2_id if owner_id == battle_state.p1_id else battle_state.p1_id
                try:
                    instructed_target = battle_state._active(opponent_id)
                except Exception:
                    instructed_target = None
                instructed_target_side = battle_state.p2_side if owner_id == battle_state.p1_id else battle_state.p1_side

            target._moved_this_turn = True

            instruct_result = apply_move(
                target,
                instructed_target,
                repeated_move,
                field_effects,
                instructed_target_side,
                {"kind": "move", "value": repeated_move},
                None,
                battle_state,
                False
            )

            if hasattr(user, '_last_move_failed'):
                user._last_move_failed = False
            return base_msg + f"\n{target.species} followed instructions!\n{instruct_result}"
        
        # Rototiller - raise Atk/SpA of grounded Grass-types
        if effect_data.get("rototiller"):

            gravity_active = getattr(field_effects, 'gravity', False)

            candidates = set()
            if battle_state:
                try:
                    active_p1 = battle_state._active(battle_state.p1_id)
                    active_p2 = battle_state._active(battle_state.p2_id)
                    if active_p1:
                        candidates.add(active_p1)
                    if active_p2:
                        candidates.add(active_p2)
                    if hasattr(battle_state, 'p1_partner'):
                        partner = getattr(battle_state, 'p1_partner', None)
                        if partner:
                            candidates.add(partner)
                    if hasattr(battle_state, 'p2_partner'):
                        partner = getattr(battle_state, 'p2_partner', None)
                        if partner:
                            candidates.add(partner)
                except Exception:
                    pass

            candidates.add(user)
            if target:
                candidates.add(target)

            affected = []
            for mon in list(candidates):
                if not mon or mon.hp <= 0:
                    continue
                mon_types = [t.strip().title() for t in getattr(mon, 'types', []) if t]
                if "Grass" not in mon_types:
                    continue
                if not is_grounded(mon, field_gravity=gravity_active):
                    continue
                if getattr(mon, 'invulnerable', False):
                    continue
                affected.append(mon)

            if not affected:
                user._last_move_failed = True
                return f"**{user.species}** used **{move_name}**!\nBut it failed! (No grounded Grass-type targets)"

            main_msg = f"**{user.species}** used **{move_name}**!"
            for mon in affected:
                boost_msgs = modify_stages(mon, {"atk": 1, "spa": 1}, caused_by_opponent=False, field_effects=field_effects)
                if boost_msgs:
                    for boost_msg in boost_msgs:
                        main_msg += f"\n{boost_msg}"
                else:
                    main_msg += f"\n{mon.species}'s Attack rose!\n{mon.species}'s Sp. Atk rose!"

            # Z-Rototiller bonus handled via z_boost_effect
            return main_msg

        # Flower Shield - boost Defense of Grass-types
        if effect_data.get("boosts_grass_types_def"):
            target_types = [t.strip().title() for t in target.types if t]
            if "Grass" in target_types:
                boost_msgs = modify_stages(target, {"defn": 1}, caused_by_opponent=False, field_effects=field_effects)
                if boost_msgs:
                    return f"**{user.species}** used **{move_name}**!" + "".join(f"\n{msg}" for msg in boost_msgs)
                return f"**{user.species}** used **{move_name}**!\nGrass-types' Defense rose!"
            return f"**{user.species}** used **{move_name}**!"
        
        # Camouflage - change type based on terrain
        if effect_data.get("changes_type_by_terrain"):
            terrain = getattr(field_effects, 'terrain', None) if field_effects else None
            terrain_types = {
                "electric": "Electric",
                "grassy": "Grass",
                "misty": "Fairy",
                "psychic": "Psychic"
            }
            new_type = terrain_types.get(terrain, "Normal")
            user.types = (new_type, None)
            return f"**{user.species}** used **{move_name}**!\n{user.species} became {new_type}-type!"
        
        # Electrify - make target's next move Electric-type
        if effect_data.get("electrifies_next_move"):
            target.electrified = True
            return f"**{user.species}** used **{move_name}**!\n{target.species}'s moves have been electrified!"
        
        # Charge - double next Electric move power, raise SpD Gen IV+
        if move_lower == "charge":
            gen_charge = get_generation(field_effects=field_effects)
            
            main_msg = f"**{user.species}** used **{move_name}**!"
            
            # Gen IV+: Raise Special Defense by 1 stage
            if gen_charge >= 4:
                charge_msgs = modify_stages(user, {"spd": 1}, caused_by_opponent=False, field_effects=field_effects)
                for charge_msg in charge_msgs:
                    main_msg += f"\n{charge_msg}"
            
            # Set charged state (doubles next Electric move)
            user._charged = True
            main_msg += f"\n{user.species} began charging power!"
            
            # Z-Charge: +1 Special Defense (additional stage)
            if hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs_charge = modify_stages(user, {"spd": 1}, caused_by_opponent=False, field_effects=field_effects)
                for z_msg in z_msgs_charge:
                    main_msg += f"\n{z_msg}"
            
            return main_msg
        
        # Flatter - raise target's Special Attack and confuse it
        if move_lower == "flatter":
            main_msg = f"**{user.species}** used **{move_name}**!"
            
            # Flatter always raises Special Attack (even if already at +6, or if target has Contrary at -6)
            target_spa_old = target.stages.get("spa", 0)
            target.stages["spa"] = min(6, target_spa_old + 1)
            main_msg += f"\n{target.species}'s Special Attack rose!"
            
            # Flatter also causes confusion (even if already confused or protected by Safeguard/Own Tempo)
            # However, if Own Tempo is active, confusion won't take effect but Special Attack still rises
            target_ability_fl = normalize_ability_name(target.ability or "")
            if target_ability_fl == "own-tempo":
                main_msg += f"\n{target.species}'s Own Tempo prevented confusion!"
            else:
                # Check Safeguard
                if target_side and getattr(target_side, 'safeguard', False):
                    main_msg += f"\n{target.species}'s Safeguard prevented confusion!"
                else:
                    # Apply confusion (even if already confused, it will be reapplied)
                    if not target.is_confused:
                        target.is_confused = True
                        target.confusion_turns = random.randint(1, 4)
                        target._confusion_applied_this_turn = True
                        main_msg += f"\n{target.species} became confused!"
                    else:
                        main_msg += f"\n{target.species} became confused again!"
            
            # Z-Flatter: +1 Special Defense (user)
            if hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs = modify_stages(user, {"spd": 1}, caused_by_opponent=False, field_effects=field_effects)
                for z_msg in z_msgs:
                    main_msg += f"\n{z_msg}"
            
            return main_msg
        
        # Conversion 2 - change type to resist last move
        if effect_data.get("changes_type_resists_last"):
            if hasattr(target, 'last_move_used') and target.last_move_used:
                # Would need to calculate which type resists the move
                return f"**{user.species}** used **{move_name}**!\n{user.species} changed its type!"
            else:
                return f"**{user.species}** used **{move_name}**!\nBut it failed!"
        
        # Roar - force switch with generation-specific mechanics
        if move_lower == "roar":
            gen_roar = get_generation(field_effects=field_effects, battle_state=battle_state)
            
            main_msg = f"**{user.species}** used **{move_name}**!"
            
            # Gen I: Ends wild battle, level check for trainer battles
            if gen_roar == 1:
                # In wild battles, ends battle
                # In trainer battles, level check: fail if user level < target level (10-25% chance based on level difference)
                target_level = getattr(target, 'level', 100)
                user_level = getattr(user, 'level', 100)
                if user_level < target_level:
                    # Failure chance = floor(target_level/4) / (target_level + user_level + 1)
                    failure_chance = (target_level // 4) / (target_level + user_level + 1)
                    if random.random() < failure_chance:
                        return main_msg + "\nBut it failed!"
                
                # Gen I: Normal priority, can hit during Dig semi-invulnerability
                target._roar_forced_switch = True
                return main_msg + f"\n{target.species} fled!"
            
            # Gen II: Priority -1, fails if used before target acts, level check removed in trainer battles
            elif gen_roar == 2:
                # Fails if used before opponent moves (handled in priority system)
                target._roar_forced_switch = True
                return main_msg + f"\n{target.species} fled!"
            
            # Gen III-IV: Priority -6, sound-based, level check for wild battles
            elif gen_roar <= 4:
                # Soundproof blocks Roar
                target_ability_roar = normalize_ability_name(target.ability or "")
                target_ability_data_roar = get_ability_effect(target_ability_roar)
                if target_ability_data_roar.get("sound_move_immunity"):
                    return main_msg + f"\n{target.species}'s Soundproof blocked the sound!"
                
                # Suction Cups or Ingrain blocks
                can_switch, switch_reason = can_switch_out(target, user, force_switch=True, field_effects=field_effects)
                if not can_switch:
                    return main_msg + f"\nBut it failed! ({switch_reason})"
                
                # Level check for wild battles (Gen III-IV)
                if gen_roar <= 4:
                    target_level = getattr(target, 'level', 100)
                    user_level = getattr(user, 'level', 100)
                    if user_level < target_level:
                        # Formula: random X (0-255), fails if floor(X*(target_level+user_level)/256)+1 <= floor(target_level/4)
                        X = random.randint(0, 255)
                        check_value = (X * (target_level + user_level)) // 256 + 1
                        if check_value <= (target_level // 4):
                            return main_msg + "\nBut it failed!"
                
                target._roar_forced_switch = True
                return main_msg + f"\n{target.species} fled!"
            
            # Gen V+: Magic Coat reflection, always succeeds if hits
            else:
                # Soundproof blocks
                target_ability_roar = normalize_ability_name(target.ability or "")
                target_ability_data_roar = get_ability_effect(target_ability_roar)
                if target_ability_data_roar.get("sound_move_immunity"):
                    return main_msg + f"\n{target.species}'s Soundproof blocked the sound!"
                
                # Suction Cups, Ingrain, or Dynamax blocks
                can_switch, switch_reason = can_switch_out(target, user, force_switch=True, field_effects=field_effects)
                if not can_switch:
                    return main_msg + f"\nBut it failed! ({switch_reason})"
                
                target._roar_forced_switch = True
                
                # Z-Roar: +1 Defense
                if hasattr(user, '_is_z_move') and user._is_z_move:
                    z_msgs = modify_stages(user, {"defn": 1}, caused_by_opponent=False, field_effects=field_effects)
                    for z_msg in z_msgs:
                        main_msg += f"\n{z_msg}"
                
                return main_msg + f"\n{target.species} fled!"
        
        # Whirlwind - force switch with generation-specific mechanics
        if move_lower == "whirlwind":
            gen_ww = get_generation(field_effects=field_effects, battle_state=battle_state)
            
            main_msg = f"**{user.species}** used **{move_name}**!"
            
            # Gen VI+: Check Crafty Shield (blocks status moves, including Whirlwind)
            if gen_ww >= 6:
                if target_side and hasattr(target_side, '_crafty_shield_active') and target_side._crafty_shield_active:
                    return main_msg + "\nBut it failed! (Crafty Shield protected the target!)"
            
            # Gen VI+: Bypasses Protect/Detect/Spiky Shield (handled earlier, but check here for clarity)
            # Gen VI+: Always hits unless semi-invulnerable or Crafty Shield (already checked above)
            
            # Gen I: 85% accuracy, normal priority, ends wild battles, level check for trainer battles
            if gen_ww == 1:
                # In wild battles, ends battle (handled elsewhere, just force switch for trainer battles)
                # In trainer battles, level check: fail if user level < target level
                target_level = getattr(target, 'level', 100)
                user_level = getattr(user, 'level', 100)
                if user_level < target_level:
                    # Failure chance = floor(target_level/4) / (target_level + user_level + 1)
                    failure_chance = (target_level // 4) / (target_level + user_level + 1)
                    if random.random() < failure_chance:
                        return main_msg + "\nBut it failed!"
                
                # Gen I: Normal priority, can hit during Dig semi-invulnerability
                # (accuracy check happens earlier, if it passed, force switch)
                can_switch, switch_reason = can_switch_out(target, user, force_switch=True, field_effects=field_effects)
                if not can_switch:
                    return main_msg + f"\nBut it failed! ({switch_reason})"
                
                target._roar_forced_switch = True
                return main_msg + f"\n{target.species} fled!"
            
            # Gen II: 100% accuracy, -1 priority, fails if used before target acts
            elif gen_ww == 2:
                # Fails if used before opponent moves (handled in priority system)
                # Can hit during Fly semi-invulnerability, cannot hit during Dig
                can_switch, switch_reason = can_switch_out(target, user, force_switch=True, field_effects=field_effects)
                if not can_switch:
                    return main_msg + f"\nBut it failed! ({switch_reason})"
                
                target._roar_forced_switch = True
                return main_msg + f"\n{target.species} fled!"
            
            # Gen III-IV: -6 priority, level check for wild battles
            elif gen_ww <= 4:
                # Suction Cups or Ingrain blocks
                can_switch, switch_reason = can_switch_out(target, user, force_switch=True, field_effects=field_effects)
                if not can_switch:
                    return main_msg + f"\nBut it failed! ({switch_reason})"
                
                # Level check for wild battles (Gen III-IV)
                # Formula: random X (0-255), fails if floor(X*(target_level+user_level)/256)+1 <= floor(target_level/4)
                target_level = getattr(target, 'level', 100)
                user_level = getattr(user, 'level', 100)
                if user_level < target_level:
                    X = random.randint(0, 255)
                    check_value = (X * (target_level + user_level)) // 256 + 1
                    if check_value <= (target_level // 4):
                        return main_msg + "\nBut it failed!"
                
                # Cannot hit during Fly semi-invulnerability (Gen III-IV)
                if getattr(target, 'invulnerable', False) and getattr(target, 'invulnerable_type', None) == "flying":
                    return main_msg + "\nBut it failed!"
                
                target._roar_forced_switch = True
                return main_msg + f"\n{target.species} fled!"
            
            # Gen V: Always fails if user level < target level in wild battles, reflected by Magic Coat, always succeeds in trainer battles
            elif gen_ww == 5:
                # Check Magic Coat reflection (Gen V+)
                if getattr(target, 'magic_coat', False):
                    target.magic_coat = False
                    # Reflect back: force user to switch
                    can_switch_user, switch_reason_user = can_switch_out(user, target, force_switch=True, field_effects=field_effects)
                    if can_switch_user:
                        user._roar_forced_switch = True
                        return main_msg + f"\n{target.species}'s Magic Coat bounced Whirlwind back onto {user.species}!\n{user.species} fled!"
                    else:
                        return main_msg + f"\n{target.species}'s Magic Coat bounced Whirlwind back, but it failed!"
                
                # Suction Cups, Ingrain, or Dynamax blocks
                can_switch, switch_reason = can_switch_out(target, user, force_switch=True, field_effects=field_effects)
                if not can_switch:
                    return main_msg + f"\nBut it failed! ({switch_reason})"
                
                # Gen V: In trainer battles, always succeeds if hits (no level check)
                target._roar_forced_switch = True
                return main_msg + f"\n{target.species} fled!"
            
            # Gen VI+: Always hits (bypasses accuracy), can hit through Protect/Detect/Spiky Shield, fails on Crafty Shield (already checked), fails on Dynamax
            else:
                # Check Magic Coat reflection (Gen V+)
                if getattr(target, 'magic_coat', False):
                    target.magic_coat = False
                    # Reflect back: force user to switch
                    can_switch_user, switch_reason_user = can_switch_out(user, target, force_switch=True, field_effects=field_effects)
                    if can_switch_user:
                        user._roar_forced_switch = True
                        return main_msg + f"\n{target.species}'s Magic Coat bounced Whirlwind back onto {user.species}!\n{user.species} fled!"
                    else:
                        return main_msg + f"\n{target.species}'s Magic Coat bounced Whirlwind back, but it failed!"
                
                # Suction Cups, Ingrain, or Dynamax blocks
                can_switch, switch_reason = can_switch_out(target, user, force_switch=True, field_effects=field_effects)
                if not can_switch:
                    return main_msg + f"\nBut it failed! ({switch_reason})"
                
                # Gen VI+: Always hits unless semi-invulnerable (Protect/Detect/Spiky Shield bypassed, Crafty Shield already checked)
                target._roar_forced_switch = True
                
                # Z-Whirlwind: +1 Special Defense
                if hasattr(user, '_is_z_move') and user._is_z_move:
                    z_msgs = modify_stages(user, {"spd": 1}, caused_by_opponent=False, field_effects=field_effects)
                    for z_msg in z_msgs:
                        main_msg += f"\n{z_msg}"
                
                return main_msg + f"\n{target.species} fled!"
        
        # Status-inflicting moves (Thunder Wave, Will-O-Wisp, Toxic, etc.)
        # Skip self-targeting status moves (like Rest) - they're handled elsewhere
        effect_data = get_move_secondary_effect(move_name)
        if effect_data.get("status_move") and "status" in effect_data and not effect_data.get("self"):
            main_msg = f"**{user.species}** used **{move_name}**!"
            
            # === ACCURACY CHECK FOR STATUS MOVES ===
            # Check accuracy before applying status (status moves can miss)
            # _accuracy_check is defined in this file (engine.py), no import needed
            # get_generation is already imported at the top of the function
            
            generation_acc = get_generation(field_effects=field_effects, battle_state=battle_state)
            
            # Get move accuracy from move data
            move_acc = move_data.get("accuracy")
            if move_acc is None:
                move_acc = effect_data.get("accuracy", 100)  # Default to 100 if not specified
            
            # Check generation-specific accuracy overrides
            gen_specific_acc = effect_data.get("gen_specific", {})
            if isinstance(gen_specific_acc, dict):
                for key, data in gen_specific_acc.items():
                    if isinstance(data, dict) and "accuracy" in data:
                        if key.endswith("+"):
                            try:
                                min_gen = int(key[:-1])
                                if generation_acc >= min_gen:
                                    move_acc = data.get("accuracy", move_acc)
                                    break
                            except ValueError:
                                pass
                        elif "-" in key:
                            try:
                                parts = key.split("-")
                                if len(parts) == 2:
                                    min_gen = int(parts[0])
                                    max_gen = int(parts[1])
                                    if min_gen <= generation_acc <= max_gen:
                                        move_acc = data.get("accuracy", move_acc)
                                        break
                            except ValueError:
                                pass
                        elif key.isdigit() and generation_acc == int(key):
                            move_acc = data.get("accuracy", move_acc)
                            break
            
            # Perform accuracy check
            move_hit = _accuracy_check(
                move_acc,
                user,
                target,
                field_effects=field_effects,
                move_category="status",
                move_name=move_name
            )
            
            if not move_hit:
                return main_msg + "\nBut it missed!"
            
            # Good as Gold - Blocks status moves from being applied to the target
            # Note: Does NOT block self-targeting status moves (like Dragon Dance, Swords Dance, etc.)
            # This is checked here (in apply_move) in addition to damage() function
            # because Good as Gold should prevent status application, not just block move selection
            target_ability_gag = normalize_ability_name(target.ability or "")
            if target_ability_gag == "good-as-gold" and user != target:
                user._last_move_failed = True
                return main_msg + f"\nBut it failed! ({target.species}'s Good as Gold prevented it!)"
            
            # Thunder Wave: Gen II fail chance (25% for in-game opponents)
            if move_lower == "thunder-wave":
                generation_tw = get_generation(field_effects=field_effects, battle_state=battle_state)
                if generation_tw == 2:
                    gen_specific_tw = effect_data.get("gen_specific", {})
                    if isinstance(gen_specific_tw, dict):
                        gen2_data = gen_specific_tw.get("2", {})
                        if isinstance(gen2_data, dict) and gen2_data.get("fail_chance"):
                            fail_chance = gen2_data.get("fail_chance")
                            if random.random() < fail_chance:
                                return main_msg + "\nBut it failed!"
            
            # === SUBSTITUTE: Blocks status moves (unless bypassed) ===
            # Check if status move bypasses Substitute
            # Sound moves bypass Substitute
            sound_moves = [
                "alluring-voice", "boomburst", "bug-buzz", "chatter", "clanging-scales", "clangorous-soul",
                "clangorous-soulblaze", "confide", "disarming-voice", "echoed-voice", "eerie-spell", "grass-whistle",
                "growl", "heal-bell", "howl", "hyper-voice", "metal-sound", "noble-roar", "overdrive",
                "parting-shot", "perish-song", "psychic-noise", "relic-song", "roar", "round", "screech", "shadow-panic",
                "sing", "snarl", "snore", "sparkling-aria", "supersonic", "torch-song", "uproar"
            ]
            is_sound_move = move_lower in sound_moves or effect_data.get("sound_move", False)

            def _finalize_toxic_thread(message: str) -> str:
                if move_lower == "toxic-thread":
                    drop_msgs = modify_stages(target, {"spe": -1}, caused_by_opponent=True, field_effects=field_effects)
                    for drop_msg in drop_msgs:
                        message += f"\n{drop_msg}"
                    if hasattr(user, '_is_z_move') and user._is_z_move:
                        z_effect = effect_data.get("z_boost_effect", {})
                        stat_boost = z_effect.get("stat_boost")
                        if stat_boost:
                            z_msgs = modify_stages(user, stat_boost, caused_by_opponent=False, field_effects=field_effects)
                            for z_msg in z_msgs:
                                message += f"\n{z_msg}"
                return message
            
            if hasattr(target, 'substitute') and target.substitute:
                try:
                    generation = get_generation(field_effects=field_effects, battle_state=battle_state)
                except Exception:
                    generation = 9

                user_ability_norm = normalize_ability_name(user.ability or "")
                user_ability_effects = ABILITY_EFFECTS.get(user_ability_norm, {})
                has_infiltrator = bool(user_ability_effects.get("ignores_screens_substitutes", False) and generation >= 7)

                hits_substitute = False
                gen_specific = effect_data.get("gen_specific", {})
                if isinstance(gen_specific, dict):
                    for key, data in gen_specific.items():
                        if not isinstance(data, dict) or not data.get("hits_substitute"):
                            continue
                        if key.endswith("+"):
                            try:
                                min_gen = int(key[:-1])
                                if generation >= min_gen:
                                    hits_substitute = True
                                    break
                            except ValueError:
                                continue
                        else:
                            try:
                                if generation == int(key):
                                    hits_substitute = True
                                    break
                            except ValueError:
                                continue

                sound_bypasses = is_sound_move and generation >= 6

                if not sound_bypasses and not has_infiltrator and not hits_substitute:
                    main_msg += f"\nBut it failed! {target.species}'s substitute blocked the status!"
                    return _finalize_toxic_thread(main_msg)
                else:
                    if has_infiltrator:
                        ability_label = (user.ability or user_ability_norm or "Ability").replace("-", " ").title()
                        bypass_reason = ability_label
                    elif sound_bypasses:
                        bypass_reason = "Sound"
                    elif hits_substitute:
                        bypass_reason = move_name.replace("-", " ").title()
                    else:
                        bypass_reason = "Effect"
                    main_msg += f"\n**{bypass_reason}** bypassed the Substitute!"
            
            # Check if target already has status
            valid_statuses = {"par", "brn", "slp", "frz", "psn", "tox", "sleep", "paralyze", "burn", "freeze", "poison", "toxic"}
            current_status = getattr(target, 'status', None)
            # Only check if status exists AND is a valid status (not empty string or None)
            has_valid_status = False
            if current_status:
                status_normalized = str(current_status).lower().strip()
                if status_normalized and status_normalized in valid_statuses:
                    has_valid_status = True
            
            if has_valid_status and move_lower != "toxic-thread":
                main_msg += f"\nBut it failed! {target.species} already has a status condition."
                return _finalize_toxic_thread(main_msg)
            
            # Check type immunities
            target_types = [t.strip().title() if t else None for t in target.types]
            status_to_inflict = effect_data["status"]
            generation = get_generation(field_effects=field_effects, battle_state=battle_state)
            
            # Thunder Wave: Generation-specific Electric type immunity
            if move_lower == "thunder-wave" and status_to_inflict == "par":
                # Check gen_specific for cannot_paralyze_electric
                gen_specific = effect_data.get("gen_specific", {})
                cannot_paralyze_electric = False
                if isinstance(gen_specific, dict):
                    # Check for Gen 6+ (cannot_paralyze_electric: True)
                    for key, data in gen_specific.items():
                        if isinstance(data, dict) and data.get("cannot_paralyze_electric"):
                            if key.endswith("+"):
                                min_gen = int(key[:-1])
                                if generation >= min_gen:
                                    cannot_paralyze_electric = True
                                    break
                            elif key.isdigit() and generation == int(key):
                                cannot_paralyze_electric = True
                                break
                
                # Gen VI+: Electric types immune to paralysis from Thunder Wave
                if cannot_paralyze_electric and "Electric" in target_types:
                    main_msg += f"\nIt doesn't affect {target.species}..."
                    return _finalize_toxic_thread(main_msg)
                
                # Ground type immunity (always, unless Ring Target in Gen V+)
                if "Ground" in target_types:
                    # Check for Ring Target (Gen V+)
                    has_ring_target = False
                    if generation >= 5:
                        if item_is_active(target) and target.item:
                            # get_item_effect and normalize_item_name are already imported at the top of the file
                            rt_item = normalize_item_name(target.item)
                            rt_data = get_item_effect(rt_item)
                            if rt_data.get("removes_type_immunities"):
                                has_ring_target = True
                    
                    if not has_ring_target:
                        main_msg += f"\nIt doesn't affect {target.species}..."
                        return _finalize_toxic_thread(main_msg)
            
            # Other paralysis moves: Electric type immunity (Gen VI+)
            elif status_to_inflict == "par" and "Electric" in target_types:
                # Check if this move can paralyze Electric types
                gen_specific_par = effect_data.get("gen_specific", {})
                can_paralyze_electric = False
                if isinstance(gen_specific_par, dict):
                    for key, data in gen_specific_par.items():
                        if isinstance(data, dict) and data.get("can_paralyze_electric"):
                            if key.endswith("-"):
                                parts = key.split("-")
                                if len(parts) == 2:
                                    try:
                                        min_gen = int(parts[0])
                                        max_gen = int(parts[1])
                                        if min_gen <= generation <= max_gen:
                                            can_paralyze_electric = True
                                            break
                                    except ValueError:
                                        pass
                            elif key.endswith("+"):
                                min_gen = int(key[:-1])
                                if generation >= min_gen:
                                    can_paralyze_electric = True
                                    break
                            elif key.isdigit() and generation == int(key):
                                can_paralyze_electric = True
                                break
                
                # Gen VI+: Electric types immune unless move specifically can paralyze them
                if generation >= 6 and not can_paralyze_electric:
                    main_msg += f"\nIt doesn't affect {target.species}..."
                    return _finalize_toxic_thread(main_msg)
            if status_to_inflict in ["brn", "burn"] and "Fire" in target_types:
                main_msg += f"\nIt doesn't affect {target.species}..."
                return _finalize_toxic_thread(main_msg)
            
            # Will-O-Wisp: Gen IV+ activates Flash Fire
            if move_lower == "will-o-wisp" and status_to_inflict in ["brn", "burn"]:
                gen_wow = get_generation(field_effects=field_effects)
                if gen_wow >= 4:
                    target_ability_wow = normalize_ability_name(target.ability or "")
                    if target_ability_wow == "flash-fire":
                        target.flash_fire_active = True
                        main_msg += f"\n{target.species}'s Flash Fire raised its Fire power!"
                        return main_msg
            # Toxic: Generation-specific immunities
            if move_lower == "toxic":
                gen_toxic = get_generation(field_effects=field_effects)
                
                # Gen I: Only Poison immunity
                if gen_toxic == 1:
                    if "Poison" in target_types:
                        main_msg += f"\nIt doesn't affect {target.species}..."
                        return main_msg
                # Gen II+: Poison and Steel immunity
                elif gen_toxic >= 2:
                    if "Poison" in target_types or "Steel" in target_types:
                        main_msg += f"\nIt doesn't affect {target.species}..."
                        return main_msg
                
                # Gen III-IV: Immunity ability blocks
                if 3 <= gen_toxic <= 4:
                    target_ability_toxic = normalize_ability_name(target.ability or "")
                    if target_ability_toxic == "immunity":
                        main_msg += f"\n{target.species}'s Immunity prevents poisoning!"
                        return main_msg
            
            # Regular poison check (for other poison moves)
            if status_to_inflict in ["psn", "poison"] and ("Poison" in target_types or "Steel" in target_types):
                main_msg += f"\nIt doesn't affect {target.species}..."
                return main_msg
            if status_to_inflict in ["frz", "freeze"] and "Ice" in target_types:
                main_msg += f"\nIt doesn't affect {target.species}..."
                return main_msg
            
            # Check for Z-Move status effects
            if hasattr(user, '_is_z_move') and user._is_z_move and hasattr(user, '_original_move_name'):
                original_move_lower = user._original_move_name.lower().replace(" ", "-")
                
                # Z-Will-O-Wisp: +1 Attack (user)
                if original_move_lower == "will-o-wisp" and status_to_inflict in ["brn", "burn"]:
                    msgs = modify_stages(user, {"atk": 1}, caused_by_opponent=False, field_effects=field_effects)
                    return f"**{user.species}** used **{move_name}**!\n" + "\n".join(msgs)
            
            if move_lower == "toxic-thread":
                # Set move name on user so apply_status_effect can check for move-specific immunities (e.g., Spore)
                user._move_being_used = move_name
                success, status_msg = apply_status_effect(
                    target,
                    status_to_inflict,
                    user,
                    field_effects=field_effects,
                    target_side=target_side
                )
                # Clear the flag after use
                if hasattr(user, '_move_being_used'):
                    delattr(user, '_move_being_used')
                main_msg += f"\n{status_msg}"
                return _finalize_toxic_thread(main_msg)
            
            # For all other status moves (including Spore), use apply_status_effect to ensure proper application
            # This ensures all checks and proper initialization happen
            # Set move name on user so apply_status_effect can check for move-specific immunities (e.g., Spore)
            user._move_being_used = move_name
            success, status_msg = apply_status_effect(
                target,
                status_to_inflict,
                user,
                field_effects=field_effects,
                target_side=target_side
            )
            # Clear the flag after use
            if hasattr(user, '_move_being_used'):
                delattr(user, '_move_being_used')
            if not success:
                # Status application failed (already handled in apply_status_effect)
                return main_msg + f"\n{status_msg}"
            
            # Status was successfully applied - use the message from apply_status_effect for consistency
            # It already has the correct format (e.g., "Landorus **fell asleep**!")
            main_msg += f"\n{status_msg}"
            main_msg = _finalize_toxic_thread(main_msg)
            return main_msg
        
        # Confusion-inflicting moves (Supersonic, Sweet Kiss, Confuse Ray, etc.)
        # Check both "confuse" (singular) and "confuses" (plural) for compatibility
        if effect_data.get("confuse") or effect_data.get("confuses"):
            main_msg = f"**{user.species}** used **{move_name}**!"
            
            # Sweet Kiss: Own Tempo prevents confusion
            if move_lower == "sweet-kiss":
                target_ability_sk = normalize_ability_name(target.ability or "")
                target_ability_data_sk = get_ability_effect(target_ability_sk)
                if target_ability_data_sk.get("confusion_immunity"):
                    ability_name_sk = (target.ability or target_ability_sk or "Ability").replace("-", " ").title()
                    return f"**{user.species}** used **{move_name}**!\n{target.species}'s {ability_name_sk} prevents confusion!"
            
            # Check if target is already confused
            if target.confused:
                return f"**{user.species}** used **{move_name}**!\nBut it failed! ({target.species} is already confused)"
            
            # Inflict confusion (1-4 turns, random)
            target.confused = True
            target.confusion_turns = random.randint(1, 4)
            target._confusion_applied_this_turn = True
            
            # Z-Confuse Ray: +1 Special Attack (user)
            if hasattr(user, '_is_z_move') and user._is_z_move and move_lower == "confuse-ray":
                z_msgs_cr = modify_stages(user, {"spa": 1}, caused_by_opponent=False, field_effects=field_effects)
                main_msg += f"\n{target.species} became confused!"
                for z_msg in z_msgs_cr:
                    main_msg += f"\n{z_msg}"
                return main_msg
            
            # Z-Sweet Kiss: +1 Special Attack (user)
            if hasattr(user, '_is_z_move') and user._is_z_move and move_lower == "sweet-kiss":
                z_msgs_sk = modify_stages(user, {"spa": 1}, caused_by_opponent=False, field_effects=field_effects)
                main_msg += f"\n{target.species} became confused!"
                for z_msg in z_msgs_sk:
                    main_msg += f"\n{z_msg}"
                return main_msg
            
            return f"**{user.species}** used **{move_name}**!\n{target.species} became confused!"
        
        # Swagger: Raises target's Attack by 2 stages and confuses it
        if move_lower == "swagger":
            main_msg = f"**{user.species}** used **{move_name}**!"
            gen_swagger = get_generation(field_effects=field_effects)
            
            # Check accuracy (Gen II-VI: 90%, Gen VII+: 85%)
            accuracy_swagger = 90 if gen_swagger <= 6 else 85
            if not _accuracy_check(
                accuracy_swagger,
                user,
                target,
                field_effects=field_effects,
                move_category="status",
                move_name=move_name,
                ignores_target_ability=False,
            ):
                return f"**{user.species}** used **{move_name}**!\nBut it missed!"
            
            # Ensure stages dict exists
            if not hasattr(target, 'stages') or target.stages is None:
                target.stages = {}
            
            # Get current Attack stage BEFORE any changes (for Gen II confusion check)
            original_atk_stage = target.stages.get("atk", 0)
            
            # Check Contrary
            target_ability_swagger = normalize_ability_name(target.ability or "")
            target_ability_data_swagger = get_ability_effect(target_ability_swagger)
            has_contrary = target_ability_data_swagger.get("inverts_stat_changes", False)
            
            # Calculate effective Attack stage change (Contrary inverts it)
            atk_change = 2 if not has_contrary else -2
            new_atk_stage = original_atk_stage + atk_change
            
            # Clamp to -6 to +6 range
            new_atk_stage = max(-6, min(6, new_atk_stage))
            actual_change = new_atk_stage - original_atk_stage
            
            # Raise Attack by 2 stages (or -2 if Contrary)
            # Gen II-VI: Attack still raised even if already at +6 (or -6 with Contrary)
            # Gen VII+: Attack can't be raised if already at +6 (or -6 with Contrary)
            if actual_change != 0:
                target.stages["atk"] = new_atk_stage
                if abs(actual_change) == 2:
                    main_msg += f"\n{target.species}'s Attack sharply {'rose' if actual_change > 0 else 'fell'}!"
                else:
                    main_msg += f"\n{target.species}'s Attack {'rose' if actual_change > 0 else 'fell'}!"
            elif gen_swagger <= 6:
                # Gen II-VI: Attack still raised even at +6 (or -6 with Contrary)
                # But since it's already at the limit, we just show the message
                main_msg += f"\n{target.species}'s Attack sharply {'rose' if atk_change > 0 else 'fell'}!"
            
            # Get current Attack stage after change (for Gen III+ confusion checks)
            current_atk_stage = target.stages.get("atk", 0)
            
            # Confusion handling
            # Gen II: Even if target is already confused or cannot become confused (Safeguard), Attack is still raised
            # Gen II: If Attack is already at +6 BEFORE the change, it will NOT become confused
            # Gen III-VI: Can confuse even if Attack at +6 or Contrary at -6
            # Gen VII+: Fails if target cannot be confused AND (Attack at +6 OR Contrary at -6)
            
            # Check if confusion can be inflicted
            from .db_move_effects import can_inflict_confusion
            can_confuse, confuse_reason = can_inflict_confusion(target, field_effects=field_effects)
            
            # Check Safeguard
            safeguard_active = False
            if target_side and getattr(target_side, 'safeguard', False):
                safeguard_active = True
            
            # Gen II: Don't confuse if Attack already at +6 BEFORE the change
            if gen_swagger == 2:
                if original_atk_stage >= 6:
                    # Attack was raised, but confusion fails
                    return main_msg + "\nBut it failed to confuse!"
                # Even if already confused or Safeguard, Attack is still raised (already done above)
                # Try to confuse if not already confused
                if not target.confused and can_confuse and not safeguard_active:
                    target.confused = True
                    target.confusion_turns = random.randint(1, 4)
                    target._confusion_applied_this_turn = True
                    main_msg += f"\n{target.species} became confused!"
                elif not can_confuse or safeguard_active:
                    # Attack was raised, but confusion failed
                    if safeguard_active:
                        main_msg += f"\nBut it failed! (Safeguard protects {target.species})"
                    else:
                        main_msg += f"\nBut it failed to confuse!"
            
            # Gen III-VI: Can confuse even if Attack at +6 or Contrary at -6
            elif gen_swagger >= 3 and gen_swagger <= 6:
                # Can confuse even if Attack at +6 or Contrary at -6
                if not target.confused and can_confuse and not safeguard_active:
                    target.confused = True
                    target.confusion_turns = random.randint(1, 4)
                    target._confusion_applied_this_turn = True
                    main_msg += f"\n{target.species} became confused!"
                elif safeguard_active:
                    main_msg += f"\nBut it failed! (Safeguard protects {target.species})"
                elif not can_confuse:
                    # Attack was raised, but confusion failed
                    main_msg += f"\nBut it failed to confuse!"
            
            # Gen VII+: Fails if target cannot be confused AND (Attack at +6 OR Contrary at -6)
            elif gen_swagger >= 7:
                # Check if move should fail
                should_fail = False
                if not can_confuse or safeguard_active:
                    if current_atk_stage >= 6 or (has_contrary and current_atk_stage <= -6):
                        should_fail = True
                
                if should_fail:
                    if safeguard_active:
                        return main_msg + f"\nBut it failed! (Safeguard protects {target.species})"
                    else:
                        return main_msg + f"\nBut it failed to confuse!"
                
                # Try to confuse
                if not target.confused and can_confuse and not safeguard_active:
                    target.confused = True
                    target.confusion_turns = random.randint(1, 4)
                    target._confusion_applied_this_turn = True
                    main_msg += f"\n{target.species} became confused!"
                elif safeguard_active:
                    main_msg += f"\nBut it failed! (Safeguard protects {target.species})"
                elif not can_confuse:
                    main_msg += f"\nBut it failed to confuse!"
            
            # Z-Swagger: Reset all lowered stats (user)
            if hasattr(user, '_is_z_move') and user._is_z_move:
                stat_resets = {}
                for stat in ["atk", "defn", "spa", "spd", "spe", "accuracy", "evasion"]:
                    if user.stages.get(stat, 0) < 0:
                        stat_resets[stat] = -user.stages.get(stat, 0)
                if stat_resets:
                    z_msgs = modify_stages(user, stat_resets, caused_by_opponent=False, field_effects=field_effects)
                    for z_msg in z_msgs:
                        main_msg += f"\n{z_msg}"
            
            return main_msg
        
        # Hazard-setting moves (Stealth Rock, Spikes, Toxic Spikes, Sticky Web)
        hazard_moves = {
            "stealth-rock": "stealth-rock",
            "spikes": "spikes",
            "toxic-spikes": "toxic-spikes",
            "sticky-web": "sticky-web"
        }
        
        if move_lower in hazard_moves:
            # Note: Hazards are actually set in panel.py on the opponent's side
            # This is just the message
            main_msg = f"**{user.species}** used **{move_name}**!"
            
            # Z-Spikes: +1 Defense (user)
            if move_lower == "spikes" and hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs_spikes = modify_stages(user, {"defn": 1}, caused_by_opponent=False, field_effects=field_effects)
                for z_msg in z_msgs_spikes:
                    main_msg += f"\n{z_msg}"
            
            return main_msg
        
        # === HP-BASED SPECIAL MOVES ===
        
        # Pain Split
        if move_lower == "pain-split":
            user_change, target_change, msg = sm.apply_pain_split(user, target, generation=generation_check)
            user.hp = max(1, min(user.max_hp, user.hp + user_change))
            target.hp = max(1, min(target.max_hp, target.hp + target_change))
            main_msg = f"**{user.species}** used **Pain Split**!\n{msg}"
            
            # Z-Pain Split: +1 Defense (user)
            if hasattr(user, '_is_z_move') and user._is_z_move:
                z_msgs = modify_stages(user, {"defn": 1}, caused_by_opponent=False, field_effects=field_effects)
                for z_msg in z_msgs:
                    main_msg += f"\n{z_msg}"
            
            return main_msg
        
        # Super Fang
        if move_lower == "super-fang":
            damage_dealt, msg = sm.apply_super_fang(target, field_effects=field_effects)
            if damage_dealt <= 0:
                return f"**{user.species}** used **Super Fang**!\n{msg}"
            target.hp = max(0, target.hp - damage_dealt)
            return f"**{user.species}** used **Super Fang**!\n{msg}\n└ **{damage_dealt}** damage to {target.species}"
        
        # === TYPE-CHANGING MOVES ===
        
        # Conversion
        if move_lower == "conversion":
            msg = sm.apply_conversion(user, target=target, field_effects=field_effects)
            return f"**{user.species}** used **Conversion**!\n{msg}"
        
        # Substitute
        if move_lower == "substitute":
            msg = sm.apply_substitute(user, field_effects=field_effects)
            return f"**{user.species}** used **Substitute**!\n{msg}"
        
        # Reflect Type
        if move_lower == "reflect-type":
            msg = sm.apply_reflect_type(user, target)
            return f"**{user.species}** used **Reflect Type**!\n{msg}"
        
        # Forest's Curse
        if move_lower == "forests-curse":
            msg = sm.apply_forests_curse(target)
            return f"**{user.species}** used **Forest's Curse**!\n{msg}"
        
        # Trick-or-Treat (note: already handled above in special status moves, but adding here for consistency)
        if move_lower == "trick-or-treat":
            msg = sm.apply_trick_or_treat_move(target)
            return f"**{user.species}** used **Trick-or-Treat**!\n{msg}"
        
        # === STATUS FLAG MOVES ===
        
        # Destiny Bond
        if move_lower == "destiny-bond":
            msg = sm.apply_destiny_bond(user)
            return f"**{user.species}** used **Destiny Bond**!\n{msg}"
        
        # Grudge
        if move_lower == "grudge":
            gen_grudge = get_generation(field_effects=field_effects, battle_state=battle_state)
            
            # Gen IX: Cannot be selected
            if gen_grudge >= 9:
                return f"**{user.species}** used **{move_name}**!\nBut it failed! (Cannot be selected in Gen IX)"
            
            # Z-Grudge: User becomes center of attention (forces all opponent moves to target user)
            if hasattr(user, '_is_z_move') and user._is_z_move:
                user._z_grudge_center = True  # Flag for move redirection
                user.center_of_attention = True
                user._center_of_attention_source = move_lower
                msg = sm.apply_grudge(user)
                return f"**{user.species}** used **{move_name}**!\n{msg}\n{user.species} became the center of attention!"
            
            msg = sm.apply_grudge(user)
            return f"**{user.species}** used **Grudge**!\n{msg}"
        
        # Healing moves (Recover, Soft-Boiled, Roost, etc.)
        healing_moves = {
            "recover": 0.5, "soft-boiled": 0.5, "roost": 0.5, "slack-off": 0.5,
            "synthesis": 0.5, "moonlight": 0.5, "morning-sun": 0.5, "shore-up": 0.5,
            "rest": 1.0, "wish": 0.5, "heal-order": 0.5, "milk-drink": 0.5
        }
        
        if move_lower in healing_moves:
            heal_ratio = healing_moves[move_lower]
            generation_heal = get_generation(field_effects=field_effects)
            
            # REST: Heal to full and fall asleep
            if move_lower == "rest":
                heal_amount = user.max_hp - user.hp
                fail_reason = None
                ability_key = normalize_ability_name(user.ability or "")
                ability_data = get_ability_effect(ability_key)
                ability_name = (user.ability or ability_key or "Ability").replace("-", " ").title()
                using_sleep_talk = getattr(user, '_using_sleep_talk', False)

                # === Z-MOVES: Ignore Heal Block ===
                is_z_move_rest = hasattr(user, '_is_z_move') and user._is_z_move
                if getattr(user, 'heal_blocked', 0) > 0 and not is_z_move_rest:
                    fail_reason = f"{user.species} can't recover due to Heal Block!"
                elif heal_amount <= 0:
                    fail_reason = f"{user.species} is already at full HP!"
                elif generation_heal == 1 and heal_amount > 0 and (heal_amount % 256 == 255):
                    fail_reason = "The recovery glitch prevented the move!"
                else:
                    status_immunity = ability_data.get("status_immunity")
                    if status_immunity == "all" or (isinstance(status_immunity, list) and "slp" in status_immunity):
                        fail_reason = f"{user.species}'s {ability_name} prevents it from falling asleep!"
                    elif ability_data.get("team_sleep_immunity"):
                        fail_reason = f"{user.species}'s {ability_name} keeps it from falling asleep!"

                    if not fail_reason and ability_key == "leaf-guard" and generation_heal >= 5:
                        if field_effects and (getattr(field_effects, 'weather', None) == "sun" or getattr(field_effects, 'harsh_sunlight', False) or getattr(field_effects, 'special_weather', None) == "harsh-sunlight"):
                            fail_reason = f"{user.species}'s Leaf Guard blocks sleep in the sunlight!"

                    if not fail_reason and field_effects and getattr(field_effects, 'uproar_turns', 0) > 0:
                        uproar_source = getattr(field_effects, 'uproar_source', None)
                        if not (generation_heal in [3, 4] and ability_key == "soundproof"):
                            if uproar_source:
                                fail_reason = f"The uproar from {uproar_source} keeps it awake!"
                            else:
                                fail_reason = "An uproar keeps it awake!"

                    if not fail_reason and field_effects:
                        terrain = getattr(field_effects, 'terrain', None)
                        if terrain in ["electric", "misty"]:
                            grounded = is_grounded(user, field_gravity=getattr(field_effects, 'gravity', False))
                            if grounded:
                                terrain_name = "Electric" if terrain == "electric" else "Misty"
                                fail_reason = f"{terrain_name} Terrain prevents sleep!"

                    if not fail_reason and ability_data.get("status_immunity_in_sun") and generation_heal >= 5:
                        if field_effects and (getattr(field_effects, 'weather', None) == "sun" or getattr(field_effects, 'harsh_sunlight', False) or getattr(field_effects, 'special_weather', None) == "harsh-sunlight"):
                            fail_reason = f"{user.species}'s {ability_name} prevents status in the sun!"

                    if not fail_reason and ability_key in ["insomnia", "vital-spirit", "comatose"]:
                        fail_reason = f"{user.species}'s {ability_name} prevents sleep!"

                    if not fail_reason and ability_key == "purifying-salt":
                        fail_reason = f"{user.species}'s {ability_name} prevents status conditions!"

                    if not fail_reason and using_sleep_talk and generation_heal >= 3:
                        fail_reason = "Rest can't be called by Sleep Talk in this generation!"

                if fail_reason:
                    return f"**{user.species}** used **Rest**!\nBut it failed! {fail_reason}"

                # Successful Rest: heal to full and apply sleep
                # Gen I: Sleep 2 turns (counting the turn Rest is used), wake on 3rd turn, attack on 4th turn
                # Gen II-VIII: Sleep 3 turns (counting the turn Rest is used), attack on 4th turn (same turn it wakes up)
                # The user is unable to use moves while asleep for 2 turns AFTER the turn when Rest is used
                old_hp = user.hp
                user.hp = user.max_hp
                actual_heal = user.hp - old_hp
                
                # Clear any status condition (Rest cures all status)
                if user.status:
                    user.status = None
                    user.status_turns = 0
                    if hasattr(user, 'toxic_counter'):
                        user.toxic_counter = 0
                
                # Apply sleep status
                user.status = "slp"

                # Mark that sleep is from Rest
                user._sleep_from_rest = True
                
                # Rest sleep duration by generation:
                # Gen I: Sleep 2 turns (counting the turn Rest is used), wake on 3rd turn, attack on 4th turn
                # Gen II-VIII: Sleep 3 turns (counting the turn Rest is used), attack on 4th turn (same turn it wakes up)
                # The user is unable to use moves while asleep for 2 turns AFTER the turn when Rest is used
                # So: Turn 1 (Rest used) + Turn 2 + Turn 3 = 3 turns asleep, wake on Turn 4
                if generation_heal == 1:
                    sleep_turns = 2  # Gen I: 2 turns (wake on 3rd, attack on 4th)
                else:
                    sleep_turns = 3  # Gen II-VIII: 3 turns (wake and attack on 4th)
                
                # Early Bird: Halve sleep duration (rounded down, minimum 1)
                # Early Bird Rest: one fewer turn asleep (2 turns after Rest instead of 3)
                if ability_data.get("sleep_duration_halved"):
                    if generation_heal == 1:
                        sleep_turns = max(1, sleep_turns // 2)  # Gen I Early Bird: 1 turn
                    else:
                        sleep_turns = max(2, sleep_turns // 2)  # Gen II+ Early Bird: 2 turns (wake on 3rd)

                user.status_turns = sleep_turns
                # Rest: The turn Rest is used counts as sleep turn 1, so the counter should decrement immediately
                # Do NOT set _sleep_applied_this_turn = True, so the counter decrements on the turn Rest is used
                # This means: Turn 1 (Rest) = sleep turn 1, Turn 2 = sleep turn 2, Turn 3 = sleep turn 3, Turn 4 = wake up
                # For Gen II+: sleep_turns = 3 means 3 turns of sleep (turns 1, 2, 3), wake on turn 4

                # Gen 1: Cannot move on the turn it wakes up
                if generation_heal == 1:
                    user._gen1_rest_skip_turns = 1
                elif hasattr(user, '_gen1_rest_skip_turns'):
                    delattr(user, '_gen1_rest_skip_turns')
                
                # Z-Rest: Reset all lowered stats
                if hasattr(user, '_is_z_move') and user._is_z_move:
                    stat_resets = {}
                    for stat in ["atk", "defn", "spa", "spd", "spe", "accuracy", "evasion"]:
                        if user.stages.get(stat, 0) < 0:
                            stat_resets[stat] = -user.stages.get(stat, 0)
                    if stat_resets:
                        msgs = modify_stages(user, stat_resets, caused_by_opponent=False, field_effects=field_effects)
                        main_msg = f"**{user.species}** used **Rest**!\n{user.species} regained {actual_heal} HP!\n{user.species} fell asleep!"
                        for msg in msgs:
                            main_msg += f"\n{msg}"
                        return main_msg

                final_msg = f"**{user.species}** used **Rest**!\n{user.species} regained {actual_heal} HP!\n{user.species} fell asleep!"
                return final_msg
            
            # SYNTHESIS/MOONLIGHT/MORNING SUN: Weather-dependent healing
            if move_lower in ["synthesis", "moonlight", "morning-sun"]:
                weather_state = getattr(field_effects, 'weather', None) if field_effects else None
                special_weather = getattr(field_effects, 'special_weather', None) if field_effects else None

                sun_active = weather_state == "sun" or special_weather == "harsh-sunlight"
                harsh_rain = special_weather == "heavy-rain"
                strong_winds = special_weather == "strong-winds"
                inclement_weather = weather_state in {"rain", "snow", "hail", "sand", "sandstorm"} or harsh_rain

                if generation_heal == 2:
                    # Generation II: Morning/Night no weather = ¼, Daytime no weather = ½ (except link battles), 
                    # Harsh sunlight = ½, Other weather = ⅛
                    if sun_active:
                        heal_ratio = 0.5
                    elif inclement_weather:
                        heal_ratio = 0.125
                    else:
                        # No weather: ¼ HP (morning/night) or ½ HP (daytime, except link battles)
                        heal_ratio = 0.25
                        time_of_day = getattr(field_effects, 'time_of_day', None) if field_effects else None
                        # In daytime (not link battles), restore twice as much (½ instead of ¼)
                        # Note: Link battle detection not implemented - assumes non-link battle
                        if isinstance(time_of_day, str) and time_of_day.lower() in ["day", "daytime", "afternoon"]:
                            heal_ratio = 0.5
                else:
                    # Generation III+: No weather or strong winds = ½, Harsh sunlight = ⅔, Other weather = ¼
                    if sun_active:
                        heal_ratio = 2 / 3
                    elif strong_winds or weather_state is None or weather_state == "":
                        # Strong winds or no weather: ½ HP
                        heal_ratio = 0.5
                    else:
                        # Other weather (rain, snow, hail, sand, etc.): ¼ HP
                        heal_ratio = 0.25
            elif move_lower == "shore-up":
                weather_state = getattr(field_effects, 'weather', None) if field_effects else None
                if weather_state in {"sandstorm", "sand"}:
                    heal_ratio = 2 / 3
            
            # SOFT-BOILED: Generation-specific rounding and Gen I modulo bug
            if move_lower == "soft-boiled":
                # Gen I: Round down, Gen I modulo 255 bug check
                if generation_heal == 1:
                    # Gen I: Fails if HP difference is 255 or 511 (255 mod 256)
                    hp_diff = user.max_hp - user.hp
                    if hp_diff > 0 and (hp_diff % 256 == 255):
                        return f"**{user.species}** used **{move_name}**!\nBut it failed!"
                    # Round down
                    heal_amount = int(user.max_hp * heal_ratio)  # Already rounds down with int()
                elif generation_heal >= 5:
                    # Gen V+: Round up
                    heal_amount = math.ceil(user.max_hp * heal_ratio)
                else:
                    # Gen II-IV: Round down (default int behavior)
                    heal_amount = int(user.max_hp * heal_ratio)
                
                actual_heal = min(heal_amount, user.max_hp - user.hp)
                if actual_heal == 0:
                    return f"**{user.species}** used **{move_name}**!\nBut it failed!"
                user.hp = min(user.max_hp, user.hp + actual_heal)
                base_msg = f"**{user.species}** used **{move_name}**!\n{user.species} restored {actual_heal} HP!"
                
                # Z-Soft-Boiled: Reset all lowered stats (Gen V-VII)
                if hasattr(user, '_is_z_move') and user._is_z_move:
                        # Reset all lowered stats
                    stats_to_reset = {}
                    for stat in ["atk", "defn", "spa", "spd", "spe", "accuracy", "evasion"]:
                        if stat in user.stages and user.stages[stat] < 0:
                            stats_to_reset[stat] = -user.stages[stat]  # Raise by the negative amount
                    if stats_to_reset:
                        msgs = modify_stages(user, stats_to_reset, caused_by_opponent=False, field_effects=field_effects)
                        for m in msgs:
                            base_msg += f"\n{m}"
                
                return base_msg
            
            # Standard healing (Recover, Roost, etc.)
            if move_lower == "recover":
                if generation_heal == 1:
                    hp_diff = user.max_hp - user.hp
                    if hp_diff > 0 and (hp_diff % 256 == 255):
                        return f"**{user.species}** used **{move_name}**!\nBut it failed!"
                    heal_amount = int(user.max_hp * heal_ratio)
                elif generation_heal >= 5:
                    heal_amount = math.ceil(user.max_hp * heal_ratio)
                else:
                    heal_amount = int(user.max_hp * heal_ratio)
            else:
                heal_amount = int(user.max_hp * heal_ratio)
            actual_heal = min(heal_amount, user.max_hp - user.hp)
            user.hp = min(user.max_hp, user.hp + actual_heal)
            main_msg = f"**{user.species}** used **{move_name}**!\n{user.species} restored {actual_heal} HP!"
            
            # Z-Milk Drink: Reset all lowered stats
            if move_lower == "milk-drink" and hasattr(user, '_is_z_move') and user._is_z_move:
                stat_resets = {}
                for stat in ["atk", "defn", "spa", "spd", "spe", "accuracy", "evasion"]:
                    if user.stages.get(stat, 0) < 0:
                        stat_resets[stat] = -user.stages.get(stat, 0)
                if stat_resets:
                    z_msgs = modify_stages(user, stat_resets, caused_by_opponent=False, field_effects=field_effects)
                    for z_msg in z_msgs:
                        main_msg += f"\n{z_msg}"
            
            # Z-Moves for Synthesis/Moonlight/Morning Sun
            if hasattr(user, '_is_z_move') and user._is_z_move:
                if move_lower == "synthesis":
                    # Z-Synthesis: Reset all lowered stats
                    stat_resets = {}
                    for stat in ["atk", "defn", "spa", "spd", "spe", "accuracy", "evasion"]:
                        if user.stages.get(stat, 0) < 0:
                            stat_resets[stat] = -user.stages.get(stat, 0)
                    if stat_resets:
                        z_msgs = modify_stages(user, stat_resets, caused_by_opponent=False, field_effects=field_effects)
                        for z_msg in z_msgs:
                            main_msg += f"\n{z_msg}"
                elif move_lower == "moonlight":
                    # Z-Moonlight: Reset all lowered stats
                    stat_resets = {}
                    for stat in ["atk", "defn", "spa", "spd", "spe", "accuracy", "evasion"]:
                        if user.stages.get(stat, 0) < 0:
                            stat_resets[stat] = -user.stages.get(stat, 0)
                    if stat_resets:
                        z_msgs = modify_stages(user, stat_resets, caused_by_opponent=False, field_effects=field_effects)
                        for z_msg in z_msgs:
                            main_msg += f"\n{z_msg}"
                elif move_lower == "morning-sun":
                    # Z-Morning Sun: Reset all lowered stats
                    stat_resets = {}
                    for stat in ["atk", "defn", "spa", "spd", "spe", "accuracy", "evasion"]:
                        if user.stages.get(stat, 0) < 0:
                            stat_resets[stat] = -user.stages.get(stat, 0)
                    if stat_resets:
                        z_msgs = modify_stages(user, stat_resets, caused_by_opponent=False, field_effects=field_effects)
                        for z_msg in z_msgs:
                            main_msg += f"\n{z_msg}"
            
            return main_msg
        
        # Weather-setting moves
        weather_moves = {
            "rain-dance": "rain", "sunny-day": "sun", "sandstorm": "sandstorm", 
            "hail": "hail", "snowscape": "snow"
        }
        
        if move_lower in weather_moves:
            # === NULLSCAPE: Blocks all weather (acts like primal weather) ===
            nullscape_type_weather = _get_nullscape_type(battle_state=battle_state)
            if nullscape_type_weather:
                # Nullscape is active - block weather
                return f"**{user.species}** used **{move_name}**!\nNormal weather does not exist in this desolate place."
            
            # Weather is set in panel.py via field_effects
            return f"**{user.species}** used **{move_name}**!"
        
        # Terrain-setting moves
        terrain_moves = {
            "electric-terrain": "electric", "grassy-terrain": "grassy",
            "misty-terrain": "misty", "psychic-terrain": "psychic"
        }
        
        if move_lower in terrain_moves:
            # Terrain is set in panel.py via field_effects
            return f"**{user.species}** used **{move_name}**!"
        
        # Hazard removal moves (Rapid Spin, Defog)
        move_effect = get_move_secondary_effect(move_name)
        if move_effect and "removes_hazards" in move_effect:
            msg = f"**{user.species}** used **{move_name}**!"
            
            # Good as Gold: Defog fails and does not remove entry hazards, screens, terrains, etc. from the field
            if move_lower == "defog" and target:
                target_ability_defog = normalize_ability_name(target.ability or "")
                if target_ability_defog == "good-as-gold":
                    user._last_move_failed = True
                    return msg + f"\nBut it failed! ({target.species}'s Good as Gold prevented it!)"
            
            # Get side effects from battle_state
            if battle_state:
                # Determine user's side more reliably using team_for
                user_side = None
                if hasattr(battle_state, 'team_for'):
                    if user in battle_state.team_for(battle_state.p1_id):
                        user_side = battle_state.p1_side
                    elif user in battle_state.team_for(battle_state.p2_id):
                        user_side = battle_state.p2_side
                
                # Fallback to active check if team_for doesn't work
                if user_side is None:
                    user_side = battle_state.p1_side if user == battle_state._active(battle_state.p1_id) else battle_state.p2_side
                
                removes = move_effect["removes_hazards"]
                
                # Rapid Spin: removes hazards from user's side ONLY, binding effects, and Leech Seed
                if removes == "self":
                    # Only remove hazards if user hasn't fainted (check happens after damage)
                    # Binding effects and Leech Seed are removed regardless
                    
                    # Remove binding effects from user (Wrap, Clamp, Fire Spin, Infestation, etc.)
                    binding_removed = []
                    if user.partially_trapped:
                        user.partially_trapped = False
                        user.partial_trap_turns = 0
                        user.partial_trap_damage = 0.0
                        binding_removed.append("binding effects")
                    if user.trapped and user.trap_source:
                        # Only remove if trapped by a binding move (not other sources like Mean Look)
                        binding_moves = ["bind", "wrap", "clamp", "fire-spin", "whirlpool", "infestation", 
                                        "magma-storm", "sand-tomb", "snap-trap", "thunder-cage"]
                        if any(move in (user.trap_source or "").lower() for move in binding_moves):
                            user.trapped = False
                            user.trap_source = None
                            if "binding effects" not in binding_removed:
                                binding_removed.append("binding effects")
                    
                    # Remove Leech Seed from user
                    if hasattr(user, 'leech_seeded') and user.leech_seeded:
                        user.leech_seeded = False
                        binding_removed.append("Leech Seed")
                    
                    if binding_removed:
                        msg += f"\n{user.species} was freed from {', '.join(binding_removed)}!"
                    
                    # Remove hazards from user's side only (unless user fainted)
                    if user.hp > 0:
                        cleared_msg = clear_hazards(user_side.hazards, move_name)
                        if cleared_msg:
                            msg += f"\n{cleared_msg}"
                    
                    # Gen VIII+: Rapid Spin raises Speed by 1 stage (only if user hasn't fainted)
                    if user.hp > 0:
                        gen_rs = get_generation(field_effects=field_effects) if field_effects else get_generation(battle_state=battle_state)
                        if gen_rs >= 8:
                            speed_msgs = modify_stages(user, {"spe": 1}, caused_by_opponent=False, field_effects=field_effects)
                            for speed_msg in speed_msgs:
                                msg += f"\n{speed_msg}"
                
                # Defog: generation-specific hazard & screen removal
                elif removes == "both":
                    
                    gen_defog = get_generation(field_effects=field_effects, battle_state=battle_state)
                    
                    def _clear_screens(side) -> List[str]:
                        removed = []
                        if side.reflect:
                            side.reflect = False
                            side.reflect_turns = 0
                            removed.append("Reflect")
                        if side.light_screen:
                            side.light_screen = False
                            side.light_screen_turns = 0
                            removed.append("Light Screen")
                        if side.aurora_veil:
                            side.aurora_veil = False
                            side.aurora_veil_turns = 0
                            removed.append("Aurora Veil")
                        if side.safeguard:
                            side.safeguard = False
                            side.safeguard_turns = 0
                            removed.append("Safeguard")
                        if side.mist:
                            side.mist = False
                            side.mist_turns = 0
                            removed.append("Mist")
                        return removed
                    
                    # Clear fog weather if present
                    if field_effects and getattr(field_effects, "weather", None) == "fog":
                        field_effects.weather = None
                        field_effects.weather_turns = 0
                        msg += "\nThe fog was blown away!"
                    
                    # Hazard removal scope (Gen VI+: both sides, earlier: target only)
                    if gen_defog >= 6:
                        user_cleared = clear_hazards(user_side.hazards, move_name)
                        if user_cleared:
                            msg += f"\n{user_cleared}"
                    else:
                        user_cleared = ""
                    
                    opp_cleared = clear_hazards(opp_side.hazards, move_name)
                    if opp_cleared:
                        msg += f"\n{opp_cleared}"
                    
                    # Screen removal (target side only)
                    removed_screens = _clear_screens(opp_side)
                    if removed_screens:
                        msg += f"\nDefog cleared {', '.join(removed_screens)}!"
                    
                    # Gen VIII+: remove active terrain
                    if field_effects and gen_defog >= 8 and getattr(field_effects, "terrain", None):
                        terrain_name = field_effects.terrain
                        field_effects.terrain = None
                        field_effects.terrain_turns = 0
                        msg += f"\nThe {terrain_name.title()} Terrain disappeared!"
                    
                    # Lower opponent's evasion (Gen V+: fails through substitute)
                    lower_evasion = True
                    if gen_defog >= 5 and getattr(target, 'substitute', None):
                        lower_evasion = False
                    if lower_evasion:
                        target.stages["evasion"] = max(-6, target.stages.get("evasion", 0) - 1)
                        msg += f"\n{target.species}'s evasiveness fell!"
            
            return msg
        
        # Database-driven stat changes and status effects
        effects = get_move_effects(move_lower)
        
        # Haze: clear all stat changes on both active Pokémon
        if effects.get("clears_all_stats"):
            generation = get_generation(field_effects=field_effects, battle_state=battle_state)

            # Z-Haze: Restore all HP
            if hasattr(user, '_is_z_move') and user._is_z_move:
                old_hp = user.hp
                user.hp = user.max_hp
                heal_amount = user.hp - old_hp
                return f"**{user.species}** used **{move_name}**!\n{user.species} regained all its HP! (+{heal_amount} HP)"

            msg_lines = [f"**{user.species}** used **{move_name}**!", "All stat changes were eliminated!"]

            active_mons = [user, target]
            for mon_to_clear in active_mons:
                for k in list(mon_to_clear.stages.keys()):
                    mon_to_clear.stages[k] = 0
                mon_to_clear.focused_energy = False
                mon_to_clear.focused_energy_stage = 0

            barriers_removed = False
            status_cleared = False
            confusion_cleared = False
            focus_reset = False
            disable_removed = False

            # Generation I extra effects
            if generation == 1:
                # Reset screens and similar effects on both sides
                if battle_state:
                    for side in [battle_state.p1_side, battle_state.p2_side]:
                        if side.reflect:
                            side.reflect = False
                            side.reflect_turns = 0
                            barriers_removed = True
                        if side.light_screen:
                            side.light_screen = False
                            side.light_screen_turns = 0
                            barriers_removed = True
                        if side.mist:
                            side.mist = False
                            side.mist_turns = 0
                            barriers_removed = True
                        if side.safeguard:
                            side.safeguard = False
                            side.safeguard_turns = 0
                            barriers_removed = True
                        if side.lucky_chant:
                            side.lucky_chant = False
                            side.lucky_chant_turns = 0
                            barriers_removed = True
                if field_effects and hasattr(field_effects, "screens") and field_effects.screens:
                    field_effects.screens.clear()
                    barriers_removed = True

                # Convert bad poison to regular poison for both Pokémon
                for mon in active_mons:
                    if mon.status == "tox":
                        mon.status = "psn"
                        mon.toxic_counter = 0
                        status_cleared = True

                # Remove opponent's non-volatile status
                if target.status:
                    target.status = None
                    target.status_turns = 0
                    target.toxic_counter = 0
                    status_cleared = True

                # Cure confusion on both
                for mon in active_mons:
                    if getattr(mon, "confused", False):
                        mon.confused = False
                        mon.confusion_turns = 0
                        confusion_cleared = True

                # Remove Leech Seed and Disable-like effects
                for mon in active_mons:
                    if hasattr(mon, "leech_seeded") and mon.leech_seeded:
                        mon.leech_seeded = False
                        status_cleared = True
                    if getattr(mon, "disabled_move", None):
                        mon.disabled_move = None
                        mon.disable_turns = 0
                        disable_removed = True

                # Focus Energy / Dire Hit removed
                for mon in active_mons:
                    if getattr(mon, "focused_energy", False):
                        mon.focused_energy = False
                        mon.focused_energy_stage = 0
                        focus_reset = True

            else:
                # Gen IV specifically lifts Focus Energy / Dire Hit
                if generation == 4:
                    for mon in active_mons:
                        if getattr(mon, "focused_energy", False):
                            mon.focused_energy = False
                            mon.focused_energy_stage = 0
                            focus_reset = True

            if barriers_removed:
                msg_lines.append("Protective barriers were stripped away!")
            if status_cleared:
                msg_lines.append("Lingering status effects were cleansed!")
            if confusion_cleared:
                msg_lines.append("Confusion subsided!")
            if disable_removed:
                msg_lines.append("Disabling effects wore off!")
            if focus_reset:
                msg_lines.append("Critical focus was lost!")

            return "\n".join(msg_lines)

        # Bide
        if move_lower == "bide":
            gen_bide = get_generation(field_effects=field_effects)
            if gen_bide >= 8:
                return f"**{user.species}** used **Bide**!\nBut it failed! (Bide cannot be used in this generation)"
            # Initialize
            if not getattr(user, '_bide_active', False):
                user._bide_active = True
                user._bide_turns = (random.randint(2, 3) if gen_bide <= 2 else 2)
                user._bide_damage = 0
                user._bide_last_attacker = None
                if gen_bide >= 3:
                    user._bide_cannot_switch = True
                return f"**{user.species}** used **Bide**!\n{user.species} is storing energy!"
            # Continue
            if user._bide_turns > 1:
                user._bide_turns -= 1
                return f"**{user.species}** is storing energy!"
            # Release
            release_target = target
            if getattr(user, '_bide_last_attacker', None) and getattr(user._bide_last_attacker, 'hp', 0) > 0:
                release_target = user._bide_last_attacker
            dmg_accumulated = getattr(user, '_bide_damage', 0)
            user._bide_active = False
            user._bide_turns = 0
            user._bide_damage = 0
            user._bide_last_attacker = None
            if hasattr(user, '_bide_cannot_switch'):
                user._bide_cannot_switch = False

            if dmg_accumulated <= 0:
                return f"**{user.species}** used **Bide**!\nBut it failed!"

            target_types = [t.strip().title() if t else None for t in getattr(release_target, 'types', (None, None))]
            if ((gen_bide == 2) or (gen_bide in {5, 6, 7})) and "Ghost" in target_types:
                return f"**{user.species}** used **Bide**!\nIt doesn't affect {release_target.species}..."

            dmg_out = max(1, int(dmg_accumulated * 2))
            # Strike chosen target
            release_target.hp = max(0, release_target.hp - dmg_out)
            return f"**{user.species}** unleashed energy!\n{release_target.species} took {dmg_out} damage!"

        if effects.get("boosts_crit"):
            generation = get_generation(field_effects=field_effects, battle_state=battle_state)
            if getattr(user, 'focused_energy', False):
                return f"**{user.species}** used **{move_name}**!\nBut it failed!"
            
            # Gen VI+: Also fails if Dragon Cheer is active
            if generation >= 6:
                # Check for Dragon Cheer (Gen 9+ ability, but we check the flag)
                if hasattr(user, '_dragon_cheer_active') and user._dragon_cheer_active:
                    return f"**{user.species}** used **{move_name}**!\nBut it failed!"
            
            user.focused_energy = True
            if generation == 2:
                user.focused_energy_stage = 1
            elif generation >= 3:
                user.focused_energy_stage = 2
            else:
                # Treat Generation I as intended +2 stages (ignore handheld glitch)
                user.focused_energy_stage = 2
            
            base_msg = f"**{user.species}** used **{move_name}**!\n{user.species} is getting pumped!"
            
            # Z-Focus Energy: +1 Accuracy
            if hasattr(user, '_is_z_move') and user._is_z_move:
                msgs = modify_stages(user, {"accuracy": 1}, caused_by_opponent=False, field_effects=field_effects)
                for msg in msgs:
                    base_msg += f"\n{msg}"
            
            return base_msg

        # Parting Shot: Lowers target's Attack and Special Attack, then switches user out
        if move_lower == "parting-shot":
            generation = get_generation(field_effects=field_effects, battle_state=battle_state)
            msg = f"**{user.species}** used **{move_name}**!"
            
            # Check Magic Bounce / Magic Coat (Gen V+)
            magic_bounce_active = False
            magic_coat_active = False
            if generation >= 5:
                target_ability_ps = normalize_ability_name(target.ability or "")
                target_ability_data_ps = get_ability_effect(target_ability_ps)
                if target_ability_data_ps.get("reflects_status_moves"):
                    magic_bounce_active = True
                
                # Check Magic Coat (status move reflection)
                if target_side and getattr(target_side, 'magic_coat', False):
                    magic_coat_active = True
            
            # If bounced back, lower user's stats and switch target out
            if magic_bounce_active or magic_coat_active:
                ability_name = "Magic Bounce" if magic_bounce_active else "Magic Coat"
                msg += f"\n{target.species}'s {ability_name} reflected {move_name}!"
                
                # Lower user's Attack and Special Attack
                stat_drops = {"atk": -1, "spa": -1}
                stat_msgs = modify_stages(user, stat_drops, caused_by_opponent=False, field_effects=field_effects)
                for stat_msg in stat_msgs:
                    msg += f"\n{stat_msg}"
                
                # Switch target out (instead of user)
                if target.hp > 0 and battle_state:
                    target._pivot_switch_pending = True
                    msg += f"\n{target.species} must switch out!"
                
                return msg
            
            # Normal effect: Lower target's Attack and Special Attack
            stat_drops = {"atk": -1, "spa": -1}
            stat_msgs = modify_stages(target, stat_drops, caused_by_opponent=True, field_effects=field_effects)
            
            # Check if stat drops actually occurred
            stat_dropped = len(stat_msgs) > 0
            
            # Generation-specific switch behavior
            should_switch = True
            if generation >= 7:
                # Gen 7+: Don't switch if stats couldn't be lowered (e.g., Clear Body, Mist)
                if not stat_dropped:
                    should_switch = False
                
                # Also check if target already has both stats at -6 (or +6 with Contrary)
                target_ability_ps2 = normalize_ability_name(target.ability or "")
                target_ability_data_ps2 = get_ability_effect(target_ability_ps2)
                has_contrary = target_ability_data_ps2.get("inverts_stat_changes", False)
                
                atk_stage = target.stages.get("atk", 0)
                spa_stage = target.stages.get("spa", 0)
                
                if has_contrary:
                    # With Contrary, check if both are at +6
                    if atk_stage >= 6 and spa_stage >= 6:
                        should_switch = False
                else:
                    # Normal: check if both are at -6
                    if atk_stage <= -6 and spa_stage <= -6:
                        should_switch = False
                
                # Mirror Armor: User switches successfully even if stats are reflected
                # (handled by modify_stages returning messages if reflection occurs)
                if not stat_dropped and not any("Mirror Armor" in m for m in stat_msgs):
                    should_switch = False
            # Gen 6: Switches even if stats are blocked (unless move fails entirely)
            # (already handled by should_switch defaulting to True)
            
            # Apply stat drops
            for stat_msg in stat_msgs:
                msg += f"\n{stat_msg}"
            
            # Mark user for pivot switch if appropriate
            if should_switch and user.hp > 0 and battle_state:
                user._pivot_switch_pending = True
                
                # Z-Parting Shot: Heals switch-in (set flag on user's side for when Pokemon switches in)
                if hasattr(user, '_is_z_move') and user._is_z_move:
                    user_side = battle_state.p1_side if user == battle_state._active(battle_state.p1_id) else battle_state.p2_side
                    if user_side:
                        user_side._z_parting_shot_pending = True
            
            return msg

        # Stat-changing moves
        if effects.get("stat_changes"):
            # Barrier: Cannot be selected in Gen 8+
            if move_lower == "barrier":
                generation = get_generation(field_effects=field_effects, battle_state=battle_state)
                if generation >= 8:
                    return f"**{user.species}** used **{move_name}**!\nBut it failed! (Barrier cannot be selected in this generation)"
            
            # Screech: Gen 1-2 fails on substitute (sound moves don't bypass in Gen 1-5)
            # Gen 6+: Sound moves bypass substitute (handled in substitute check code)
            # Note: The substitute check at line 8286 already handles sound moves for Gen 6+, 
            # so Screech will naturally bypass in Gen 6+. Gen 1-2 will fail due to substitute blocking sound moves.
            
            msg = f"**{user.species}** used **{move_name}**!"
            
            # Mirror Herb: Copy opponent's stat boosts when they raise their stats (Gen 9+)
            stat_changes = effects.get("stat_changes", {})
            # Check if user is raising their own stats (positive changes)
            user_boosts = {k: v for k, v in stat_changes.items() if v > 0}
            if user_boosts and item_is_active(target) and target.item:
                t_item_mh = normalize_item_name(target.item)
                t_item_data_mh = get_item_effect(t_item_mh)
                gen_mh2 = get_generation(field_effects=field_effects)
                if t_item_data_mh.get("copies_stat_boosts") and gen_mh2 >= 9:
                    # Copy the boosts to target (holder of Mirror Herb)
                    copied = False
                    for stat, amount in user_boosts.items():
                        if stat in target.stages:
                            old_t = target.stages[stat]
                            target.stages[stat] = min(6, max(-6, old_t + amount))
                            if target.stages[stat] != old_t:
                                copied = True
                    if copied:
                        target.item = None  # Consume Mirror Herb
                        msg += f"\n{target.species}'s Mirror Herb copied the stat changes!"
            
            # Special case: Belly Drum costs 50% HP and maxes Attack
            if move_lower == "belly-drum":
                cost = user.max_hp // 2
                
                # Check if Attack is already at +6 (or -6 with Contrary)
                user_ability = normalize_ability_name(user.ability or "")
                user_ability_data = get_ability_effect(user_ability)
                has_contrary = user_ability_data.get("inverts_stat_changes", False)
                current_atk_stage = user.stages.get("atk", 0)
                
                # Fail if Attack is already at +6 (or -6 with Contrary)
                if (not has_contrary and current_atk_stage >= 6) or (has_contrary and current_atk_stage <= -6):
                    msg += f"\nBut it failed! ({user.species}'s Attack cannot go any higher)"
                    return msg
                
                # Gen II bug: If under 50% HP, still raises Attack 2 stages (not implementing bug per user request to skip bugs)
                
                # Z-Belly Drum: Restore all HP before HP deduction
                if hasattr(user, '_is_z_move') and user._is_z_move:
                    old_hp = user.hp
                    user.hp = user.max_hp
                    heal_amount = user.hp - old_hp
                    if heal_amount > 0:
                        msg += f"\n{user.species} regained {heal_amount} HP!"
                
                if user.hp > cost:
                    user.hp -= cost
                    
                    # Apply stat change (Contrary inverts it)
                    if has_contrary:
                        # Contrary: Belly Drum lowers Attack to -6
                        user.stages["atk"] = -6
                        msg += f"\n{user.species} cut its own HP and lowered its Attack!"
                    else:
                        # Normal: Belly Drum raises Attack to +6
                        user.stages["atk"] = 6
                        msg += f"\n{user.species} cut its own HP and maximized its Attack!"
                    
                    # Check for HP-restoring berries after HP loss
                    berry_msg = check_and_consume_hp_berries(user)
                    if berry_msg:
                        msg += f"\n{berry_msg}"
                else:
                    msg += f"\nBut it failed! ({user.species} doesn't have enough HP)"
                return msg
            
            # Apply stat changes to user
            user_changes = db_apply_stat_changes(user, effects["stat_changes"], is_opponent=False)
            for change_msg in user_changes:
                msg += f"\n{change_msg}"
            
            # Apply stat changes to opponent
            opponent_changes = db_apply_stat_changes(target, effects["stat_changes"], is_opponent=True)
            for change_msg in opponent_changes:
                msg += f"\n{change_msg}"
            
            # Defense Curl: mark bonus flag (doubling Rollout/Ice Ball power)
            if move_lower == "defense-curl":
                setattr(user, "_defense_curl_used", True)
                # Z-Defense Curl: +1 Accuracy
                if hasattr(user, '_is_z_move') and user._is_z_move:
                    msgs = modify_stages(user, {"accuracy": 1}, caused_by_opponent=False, field_effects=field_effects)
                    for m in msgs:
                        msg += f"\n{m}"
            
            # Z-Move effects for specific stat-changing moves
            if hasattr(user, '_is_z_move') and user._is_z_move:
                z_effects = {}
                
                if move_lower == "screech":
                    # Z-Screech: +1 Attack
                    z_effects = {"atk": 1}
                elif move_lower == "double-team":
                    # Z-Double Team: Reset all lowered stats
                    stat_resets = {}
                    for stat in ["atk", "defn", "spa", "spd", "spe", "accuracy", "evasion"]:
                        if user.stages.get(stat, 0) < 0:
                            stat_resets[stat] = -user.stages.get(stat, 0)
                    if stat_resets:
                        msgs = modify_stages(user, stat_resets, caused_by_opponent=False, field_effects=field_effects)
                        for m in msgs:
                            msg += f"\n{m}"
                    return msg
                elif move_lower == "harden":
                    # Z-Harden: +1 Defense
                    z_effects = {"defn": 1}
                elif move_lower == "smokescreen":
                    # Z-Smokescreen: +1 Evasion
                    z_effects = {"evasion": 1}
                elif move_lower == "confuse-ray":
                    # Z-Confuse Ray: +1 Special Attack
                    z_effects = {"spa": 1}
                elif move_lower == "withdraw":
                    # Z-Withdraw: +1 Defense
                    z_effects = {"defn": 1}
                elif move_lower == "barrier":
                    # Z-Barrier: Reset all lowered stats
                    stat_resets = {}
                    for stat in ["atk", "defn", "spa", "spd", "spe", "accuracy", "evasion"]:
                        if user.stages.get(stat, 0) < 0:
                            stat_resets[stat] = -user.stages.get(stat, 0)
                    if stat_resets:
                        msgs = modify_stages(user, stat_resets, caused_by_opponent=False, field_effects=field_effects)
                        for m in msgs:
                            msg += f"\n{m}"
                    return msg
                elif move_lower == "amnesia":
                    # Z-Amnesia: Reset all lowered stats
                    stat_resets = {}
                    for stat in ["atk", "defn", "spa", "spd", "spe", "accuracy", "evasion"]:
                        if user.stages.get(stat, 0) < 0:
                            stat_resets[stat] = -user.stages.get(stat, 0)
                    if stat_resets:
                        msgs = modify_stages(user, stat_resets, caused_by_opponent=False, field_effects=field_effects)
                        for m in msgs:
                            msg += f"\n{m}"
                    return msg
                elif move_lower == "kinesis":
                    # Z-Kinesis: +1 Evasion
                    z_effects = {"evasion": 1}
                elif move_lower == "flash":
                    # Z-Flash: +1 Evasion
                    z_effects = {"evasion": 1}
                elif move_lower == "sharpen":
                    # Z-Sharpen: +1 Attack
                    z_effects = {"atk": 1}
                elif move_lower == "acid-armor":
                    # Z-Acid Armor: Reset all lowered stats
                    stat_resets = {}
                    for stat in ["atk", "defn", "spa", "spd", "spe", "accuracy", "evasion"]:
                        if user.stages.get(stat, 0) < 0:
                            stat_resets[stat] = -user.stages.get(stat, 0)
                    if stat_resets:
                        msgs = modify_stages(user, stat_resets, caused_by_opponent=False, field_effects=field_effects)
                        for m in msgs:
                            msg += f"\n{m}"
                    return msg
                
                if z_effects:
                    msgs = modify_stages(user, z_effects, caused_by_opponent=False, field_effects=field_effects)
                    for m in msgs:
                        msg += f"\n{m}"
            
            return msg
        
        # Status-inflicting moves (pure status moves, not secondary effects)
        if effects.get("inflicts_status") and effects.get("status_chance") == 100:
            # Load move data to check if it's a damaging move
            mv_data = load_move(move_lower, generation=generation_for_move_data, battle_state=battle_state)
            power = mv_data.get("power") if mv_data else None
            
            # Only apply pure status moves here (not secondary effects from damaging moves)
            if power is None or power <= 0:
                msg = f"**{user.species}** used **{move_name}**!"
                success, status_msg = apply_status_effect(
                    target,
                    effects["inflicts_status"],
                    user,
                    field_effects=field_effects,
                    target_side=target_side
                )
                msg += f"\n{status_msg}"
                return msg
        
        # Mark Minimize flag when used (for vulnerabilities/accuracy bypass)
        if move_lower == "minimize":
            # Z-Minimize: Reset all lowered stats
            if hasattr(user, '_is_z_move') and user._is_z_move:
                stat_resets = {}
                for stat in ["atk", "defn", "spa", "spd", "spe", "accuracy", "evasion"]:
                    if user.stages.get(stat, 0) < 0:
                        stat_resets[stat] = -user.stages.get(stat, 0)  # Amount to raise back to 0
                
                if stat_resets:
                    msgs = modify_stages(user, stat_resets, caused_by_opponent=False, field_effects=field_effects)
                    base_msg = f"**{user.species}** used **{move_name}**!\n{user.species}'s evasion rose!"
                    for msg in msgs:
                        base_msg += f"\n{msg}"
                    setattr(user, "_minimized", True)
                    return base_msg
                else:
                    setattr(user, "_minimized", True)
                    return f"**{user.species}** used **{move_name}**!\n{user.species}'s evasion rose!"
            else:
                setattr(user, "_minimized", True)
                # Gen III+: Dynamax interaction - if Dynamaxed after Minimize, boosted moves don't bypass accuracy/evasion
                # This is handled in accuracy checks and damage calculation
        
        # Other status moves
        return f"**{user.species}** used **{move_name}**."
    
    # === BERRY-BASED DAMAGING MOVES ===
    
    # Natural Gift (consume Berry, variable power/type)
    if move_lower == "natural-gift":
        success, ng_power, ng_type, ng_msg = handle_natural_gift(user)
        
        if not success:
            return f"**{user.species}** used **Natural Gift**!\n{ng_msg}"
        
        # Override the move's power and type for this calculation
        # Natural Gift will use the damage() function with these parameters
        # We'll fall through to the standard damage calculation below
        # but need to temporarily store these values
        user._natural_gift_power = ng_power
        user._natural_gift_type = ng_type
        user._natural_gift_msg = ng_msg
    
    # === DAMAGE-RETURN MOVES (Counter, Mirror Coat, Metal Burst) ===
    # NOTE: These moves are now handled EARLY (before Taunt check at line ~8205)
    # This block should never be reached, but kept as a safety fallback
    if move_lower in ["counter", "mirror-coat", "metal-burst"]:
        import sys
        print(f"[Counter Debug] WARNING: Counter reached late check - should have been handled early!", file=sys.stderr, flush=True)
        damage_dealt, counter_msg = sm.apply_counter_family(move_name, user, target, field_effects=field_effects, battle_state=battle_state)
        if damage_dealt > 0:
            target.hp = max(0, target.hp - damage_dealt)
            target._last_damage_taken = damage_dealt
            target._last_damage_category = "physical"
            target._last_move_that_hit = move_name
            target._last_move_type_hit_by = "Fighting"
            if not hasattr(target, '_last_damage_hit_substitute'):
                target._last_damage_hit_substitute = False
            return f"**{user.species}** used **{move_name}**!\n{counter_msg}\n└ **{damage_dealt}** damage to {target.species}"
        else:
            return f"**{user.species}** used **{move_name}**!\n{counter_msg}"
    
    # === RANDOM DAMAGE MOVES ===
    
    # Psywave - Random damage based on level
    if move_lower == "psywave":
        damage_dealt, psywave_msg = sm.apply_psywave(user.level)
        target.hp = max(0, target.hp - damage_dealt)
        return f"**{user.species}** used **Psywave**!\n{psywave_msg}\n└ **{damage_dealt}** damage to {target.species}"
    
    # Present - Random: damage or heal
    if move_lower == "present":
        value, is_heal, present_msg, succeeded = sm.apply_present(user, target, generation=generation_check)
        if is_heal:
            if getattr(target, 'heal_blocked', 0) > 0:
                return f"**{user.species}** used **Present**!\n{present_msg}\nBut Heal Block prevented healing!"
            if not succeeded:
                return f"**{user.species}** used **Present**!\n{present_msg}"
            old_hp = target.hp
            target.hp = min(target.max_hp, target.hp + value)
            actual_heal = target.hp - old_hp
            return f"**{user.species}** used **Present**!\n{present_msg}\n{target.species} restored {actual_heal} HP!"
        else:
            # Override power for damage calculation
            if value:
                mv = mv.copy()
                mv["power"] = value
                P = value
            # Continue into damage calculation
    
    # === HP-BASED DAMAGING MOVES ===
    
    # Endeavor
    if move_lower == "endeavor":
        damage_dealt, endeavor_msg = sm.apply_endeavor(user, target)
        if damage_dealt > 0:
            # Dummy Magikarp is immortal - heals to 999 HP when it reaches 0
            if getattr(target, '_is_dummy_magikarp', False):
                target.hp = max(0, target.hp - damage_dealt)
                if target.hp <= 0:
                    target.hp = 999
                    target.max_hp = 999
            else:
                target.hp = max(1, target.hp - damage_dealt)
            return f"**{user.species}** used **Endeavor**!\n{endeavor_msg}\n└ **{damage_dealt}** damage to {target.species}"
        else:
            return f"**{user.species}** used **Endeavor**!\n{endeavor_msg}"
    
    # Final Gambit
    if move_lower == "final-gambit":
        damage_dealt, gambit_msg = sm.apply_final_gambit(user)
        target.hp = max(0, target.hp - damage_dealt)
        return f"**{user.species}** used **Final Gambit**!\n{gambit_msg}\n└ **{damage_dealt}** damage to {target.species}"
    
    # Miss
    if meta.get("miss"):
        msg = f"**{user.species}** used **{move_name}**!\nThe attack **missed**!"
        if generation_check >= 5 and getattr(user, 'rampage_move', None):
            disrupt_rampage(user, field_effects, reason="miss")
        
        # Gems are NOT consumed on miss
        if hasattr(user, '_gem_to_consume'):
            delattr(user, '_gem_to_consume')
        
        crash_msg = apply_jump_kick_crash(user, target, move_name, meta, field_effects)
        if crash_msg:
            msg += crash_msg
        
        return msg
    
    # === FALSE SWIPE: Leaves target at 1 HP minimum ===
    # Using top-level import
    endure_skip_contact = False
    if getattr(target, 'endure_active', False) and dmg >= target.hp:
        generation_endure = get_generation(field_effects=field_effects)
        if target.hp <= 1 and 3 <= generation_endure <= 4:
            endure_skip_contact = True
        dmg = max(0, target.hp - 1)
    target._endure_skip_contact = endure_skip_contact

    move_effect_data = get_move_secondary_effect(move_name)
    if move_effect_data.get("leaves_1hp"):
        # If damage would reduce target to 0 HP, cap it to leave 1 HP
        if dmg >= target.hp:
            dmg = target.hp - 1
    
    # === FOCUS SASH: Survive with 1 HP if at full HP ===
    target_item = (target.item or "").lower().replace(" ", "-")
    if target_item == "focus-sash" and target.hp == target.max_hp and dmg >= target.hp:
        dmg = target.hp - 1  # Reduce damage to leave 1 HP
        focus_sash_used = True
    else:
        focus_sash_used = False
    
    # === SUBSTITUTE: Blocks damage ===
    substitute_broken = False
    substitute_bypassed = False
    target_had_substitute = hasattr(target, 'substitute') and target.substitute
    drain_base_damage = dmg
    heal_from_substitute = False  # Initialize early to avoid UnboundLocalError
    
    if hasattr(target, 'substitute') and target.substitute:
        # Check if move bypasses Substitute
        # Sound moves bypass Substitute (all generations)
        sound_moves = [
            "alluring-voice", "boomburst", "bug-buzz", "chatter", "clanging-scales", "clangorous-soul",
            "clangorous-soulblaze", "confide", "disarming-voice", "echoed-voice", "eerie-spell", "grass-whistle",
            "growl", "heal-bell", "howl", "hyper-voice", "metal-sound", "noble-roar", "overdrive",
            "parting-shot", "perish-song", "psychic-noise", "relic-song", "roar", "round", "screech", "shadow-panic",
            "sing", "snarl", "snore", "sparkling-aria", "supersonic", "torch-song", "uproar"
        ]
        is_sound_move = move_lower in sound_moves
        
        # Check if move bypasses Substitute from move_effects
        move_effect_data_sub = get_move_secondary_effect(move_name)
        bypasses_substitute_flag = move_effect_data_sub.get("bypasses_substitute", False)
        
        # Infiltrator ability bypasses Substitute (Gen 7+)
        user_ability_norm = normalize_ability_name(user.ability or "")
        user_ability_effects = ABILITY_EFFECTS.get(user_ability_norm, {})
        has_infiltrator = user_ability_effects.get("ignores_screens_substitutes", False)
        
        # Gen 7+: Infiltrator bypasses Substitute
        # Gen 5-6: Infiltrator does NOT bypass Substitute
        if has_infiltrator:
            generation = get_generation(field_effects=field_effects)
            if generation <= 6:
                has_infiltrator = False  # Gen 5-6: Don't bypass Substitute
        
        # Bypass Substitute if sound move, bypasses_substitute flag, or Infiltrator (Gen 7+)
        sound_bypass_allowed = is_sound_move and generation_check >= 6
        if sound_bypass_allowed or has_infiltrator or bypasses_substitute_flag:
            substitute_bypassed = True
            drain_base_damage = dmg
            # Damage goes through to actual Pokémon
        else:
            # Substitute takes the damage instead
            actual_dmg, substitute_broken = target.substitute.take_damage(dmg)
            if substitute_broken:
                target.substitute = None  # Remove broken substitute
                target._substitute_broken_this_turn = True  # Track for Gen I recoil checks
            dmg = 0  # No damage to actual Pokémon
            drain_base_damage = actual_dmg
            # Track that damage hit substitute (for Counter Gen II mechanics)
            target._last_damage_hit_substitute = True
    
    # Minimize vulnerability: double damage for specific moves when target minimized
    if dmg > 0 and hasattr(target, '_minimized') and target._minimized:
        meff_single = get_move_secondary_effect(move_name)
        if meff_single.get('doubled_minimize'):
            dmg *= 2

    # Type-resist berries (single-hit path)
    if dmg > 0 and item_is_active(target) and target.item:
        t_item = normalize_item_name(target.item)
        t_item_data = get_item_effect(t_item)
        resist_type = t_item_data.get("resist_once")
        if resist_type:
            # Load move data to get type
            move_data = load_move(move_name, generation=generation_for_move_data, battle_state=battle_state)
            move_t = meta.get("type", move_data.get("type", "Normal") if move_data else "Normal")
            mult_check, _ = type_multiplier(move_t, target, user=user)
            is_chilan = (t_item == "chilan-berry")
            should_apply = (is_chilan and move_t == "Normal") or (mult_check >= 2.0 and move_t == resist_type)
            if should_apply:
                ripen_factor = 0.5
                t_ability = normalize_ability_name(target.ability or "")
                t_ability_data = get_ability_effect(t_ability)
                if t_ability_data.get("berry_effect_mult"):
                    ripen_factor *= t_ability_data["berry_effect_mult"]
                dmg = max(1, int(dmg * ripen_factor))
                target._last_consumed_berry = target.item
                target.item = None

    # === Z-MOVES: Deal 25% damage through protection ===
    if hasattr(user, '_z_move_vs_protection') and user._z_move_vs_protection:
        # Z-Moves deal 25% of original damage through protection
        dmg = max(1, int(dmg * 0.25))
        # Clear the flag
        delattr(user, '_z_move_vs_protection')

    # Apply damage (to Pokémon, or 0 if Substitute blocked it)
    # Skip if Parental Bond already applied damage
    old_hp = target.hp
    
    # Initialize msg if not already set (for non-multi-hit moves)
    try:
        _ = msg  # Check if msg exists
    except NameError:
        # msg not initialized yet (non-multi-hit move path)
        msg = f"**{user.species}** used **{move_name}**!"
        if pre_move_msgs:
            for line in pre_move_msgs:
                msg += f"\n{line}"
        if spectral_thief_msgs:
            for st_msg in spectral_thief_msgs:
                msg += f"\n{st_msg}"
    
    if not parental_bond_damage_applied:
        # Dummy Magikarp is immortal - heals to 999 HP when it reaches 0
        old_target_hp_single = target.hp
        if getattr(target, '_is_dummy_magikarp', False):
            target.hp = max(0, target.hp - dmg)
            if target.hp <= 0:
                target.hp = 999
                target.max_hp = 999
        else:
            target.hp = max(0, target.hp - dmg)
        # Track ACTUAL damage dealt (capped by target's remaining HP) for drain moves
        actual_dmg_dealt = old_target_hp_single - target.hp
        # Update drain_base_damage to reflect actual damage dealt (after all modifiers)
        # This ensures drain healing is calculated from the correct damage amount
        if not target_had_substitute or substitute_bypassed or heal_from_substitute:
            drain_base_damage = actual_dmg_dealt
        # Move type tracking is now done in damage tracking section below
        
        # Contact effects for regular moves (non-multistrike, non-Parental Bond)
        # Note: Iron Barbs and Rough Skin (Gen 5+) trigger even if 0 damage is dealt
        move_obj_regular = load_move(move_name, generation=generation_for_move_data, battle_state=battle_state)
        mechanics_regular = mechanics
        
        # Use makes_contact function which has fallback list
        is_contact = makes_contact(move_name)
        if is_contact:
            # Ensure move_obj has contact flag set
            if move_obj_regular:
                if move_obj_regular.get("contact", 0) != 1:
                    move_obj_regular = move_obj_regular.copy()
                    move_obj_regular["contact"] = 1
            else:
                # Create a minimal move_obj if it doesn't exist
                move_obj_regular = {"contact": 1, "name": move_name}
            
            contact_log_regular = _contact_side_effects(
                attacker=user,
                defender=target,
                move_obj=move_obj_regular,
                field_effects=field_effects,
                attacker_side=user_side,
                defender_side=target_side,
                damage_dealt=dmg
            )
            # Always add contact messages if any exist - be explicit
            if contact_log_regular and len(contact_log_regular) > 0:
                msg += "\n" + "\n".join(contact_log_regular)
            if hasattr(target, '_endure_skip_contact'):
                target._endure_skip_contact = False
        
        if target.hp < old_hp:
            target._took_damage_this_turn = True
    
    # === TRACK DAMAGE IMMEDIATELY FOR COUNTER/MIRROR COAT ===
    # Track damage right after it's applied so Counter can use it in the same turn
    # Always track damage info for Counter/Mirror Coat, even if damage is 0
    # This MUST happen regardless of Parental Bond, so Counter can work
    move_data_track = get_move(move_name, generation=generation_for_move_data, battle_state=battle_state)
    # Use drain_base_damage which includes substitute damage
    damage_to_track_now = drain_base_damage if drain_base_damage > 0 else dmg
    category_now = move_data_track.get("damage_class", "physical") if move_data_track else "physical"
    if normalized_move.startswith("hidden-power"):
        gen_hp_now = get_generation(field_effects=field_effects)
        category_now = "special" if gen_hp_now >= 4 else "physical"
    # Track damage immediately for Counter/Mirror Coat (always track, even if 0)
    target._last_damage_taken = damage_to_track_now
    target._last_damage_category = category_now
    target._last_move_that_hit = move_name
    if meta.get("type"):
        target._last_move_type_hit_by = meta["type"].strip().title()
    elif move_data_track:
        target._last_move_type_hit_by = move_data_track.get("type", "Normal").strip().title()
    # Track substitute flag
    if not hasattr(target, '_last_damage_hit_substitute'):
        target._last_damage_hit_substitute = False
    if substitute_broken or (target_had_substitute and not substitute_bypassed and dmg == 0):
        target._last_damage_hit_substitute = True
    else:
        target._last_damage_hit_substitute = False
    
    # Build detailed message EXACTLY like your reference image
    move_type_for_msg = meta.get("type")
    if not move_type_for_msg:
        # Check if this is a Max Move and get type from Max Move name
        if hasattr(user, '_is_max_move') and user._is_max_move:
            from .max_moves import MAX_MOVE_NAMES
            # Reverse lookup: find which type corresponds to this Max Move name
            move_name_normalized = move_name.replace("-", " ").title()
            for move_type, max_move_name in MAX_MOVE_NAMES.items():
                if max_move_name == move_name_normalized or max_move_name.replace(" ", "-").lower() == move_name.lower():
                    move_type_for_msg = move_type
                    break
            # If not found, try to get from original move
            if not move_type_for_msg and hasattr(user, '_original_move_name_max'):
                original_move = user._original_move_name_max
                move_type_for_msg = get_actual_move_type_for_max_move(original_move, user, field_effects)
        
        # If still not set, load move data to get type
        if not move_type_for_msg:
            move_data = load_move(move_name, generation=generation_for_move_data, battle_state=battle_state)
            move_type_for_msg = (move_data.get("type") if move_data else None) or "Normal"
        
        meta["type"] = move_type_for_msg

    mult, ability_msg = type_multiplier(move_type_for_msg, target, user=user)
    
    # Main attack line - format move name and species name
    user_name = format_species_name(user.species)
    if getattr(user, 'shiny', False):
        user_name = f"★ {user_name}"
    # Format move name
    move_parts = move_name.replace("-", " ").replace("_", " ").split()
    formatted_move = " ".join(part.capitalize() for part in move_parts) if move_parts else move_name.capitalize()
    msg = f"**{user_name}** used **{formatted_move}**!"
    if pre_move_msgs:
        for line in pre_move_msgs:
            msg += f"\n{line}"
    
    # Ability messages (e.g., "Pikachu's Volt Absorb absorbed the attack!")
    if ability_msg:
        msg += f"\n{ability_msg}"
        if generation_check >= 5 and getattr(user, 'rampage_move', None):
            disrupt_rampage(user, field_effects, reason="ability-absorb")
        # If ability message exists, the attack was absorbed/blocked
        # Gems are NOT consumed when ability blocks/absorbs the move
        if hasattr(user, '_gem_to_consume'):
            delattr(user, '_gem_to_consume')
        crash_msg = apply_jump_kick_crash(user, target, move_name, meta, field_effects)
        if crash_msg:
            msg += crash_msg
        handle_rollout_failure(user, normalized_move in ROLLOUT_MOVES)
        return msg
    
    if "generation_check" not in locals():
        generation_check = get_generation(battle_state=battle_state, field_effects=field_effects)

    # No effect messages
    if mult == 0:
        msg += f"\nIt had **no effect** on {target.species}!"
        if generation_check >= 5 and getattr(user, 'rampage_move', None):
            disrupt_rampage(user, field_effects, reason="immunity")
        # Gems are NOT consumed when move has no effect (type immunity)
        if hasattr(user, '_gem_to_consume'):
            delattr(user, '_gem_to_consume')
        crash_msg = apply_jump_kick_crash(user, target, move_name, meta, field_effects)
        if crash_msg:
            msg += crash_msg
        handle_rollout_failure(user, normalized_move in ROLLOUT_MOVES)
        return msg
    
    # Substitute messages
    if substitute_broken:
        msg += f"\n**{target.species}'s Substitute broke!**"
    elif substitute_bypassed and hasattr(target, 'substitute') and target.substitute:
        # Substitute was bypassed by sound move or Infiltrator
        bypass_reason = "sound" if is_sound_move else user_ability_norm.replace("-", " ").title()
        msg += f"\n**{bypass_reason}** bypassed the Substitute!"
    elif hasattr(target, 'substitute') and target.substitute and dmg == 0:
        # Substitute blocked damage (still active)
        msg += f"\nThe Substitute took the hit!"
    
    # Effectiveness messages - shown IMMEDIATELY after damage (Showdown style: before damage %)
    if move_effect_main and move_effect_main.get("fails_if_no_item") and target_item_before:
        item_display = str(target_item_before).replace("-", " ").title()
        msg += f"\nA spectral force made {target.species}'s {item_display} strike it!"

    if mult >= 2.0:
        msg += "\nIt's super effective!"
    elif mult <= 0.5 and mult > 0:
        msg += "\nIt's not very effective..."
    
    # Enigma Berry (Gen 4+): heal when hit by super effective move (single-hit path)
    if dmg > 0 and item_is_active(target) and target.item and target.hp > 0:
        enigma = normalize_item_name(target.item)
        if enigma == "enigma-berry":
            mult_check, _ = type_multiplier(meta.get("type", "Normal"), target, user=user)
            if mult_check >= 2.0:
                if get_generation(field_effects=field_effects) >= 4:
                    heal = max(1, target.max_hp // 4)
                    old = target.hp
                    target.hp = min(target.max_hp, target.hp + heal)
                    actual = target.hp - old
                    if actual > 0:
                        msg += f"\n{target.species}'s Enigma Berry restored {actual} HP!"
                    target._last_consumed_berry = target.item
                    target.item = None

    # Jaboca, Rowap, Kee, Maranga (single-hit path)
    if dmg > 0 and item_is_active(target) and target.item and target.hp > 0:
        berr = normalize_item_name(target.item)
        ripen_mult = 1.0
        t_ability = normalize_ability_name(target.ability or "")
        t_ability_data = get_ability_effect(t_ability)
        if t_ability_data.get("berry_effect_mult"):
            ripen_mult = t_ability_data["berry_effect_mult"]
        cat = (meta.get("category") or "").lower()
        if berr == "jaboca-berry" and cat == "physical":
            chip = int((target.max_hp / 8) * ripen_mult)
            chip = max(1, chip)
            user.hp = max(0, user.hp - chip)
            msg += f"\n{user.species} was hurt by {target.species}'s Jaboca Berry! (-{chip} HP)"
            target._last_consumed_berry = target.item
            target.item = None
        elif berr == "rowap-berry" and cat == "special":
            chip = int((target.max_hp / 8) * ripen_mult)
            chip = max(1, chip)
            user.hp = max(0, user.hp - chip)
            msg += f"\n{user.species} was hurt by {target.species}'s Rowap Berry! (-{chip} HP)"
            target._last_consumed_berry = target.item
            target.item = None
        elif berr == "kee-berry" and cat == "physical":
            old = target.stages.get("defn", 0)
            boost = 2 if ripen_mult > 1.0 else 1
            target.stages["defn"] = min(6, old + boost)
            msg += f"\n{target.species}'s Kee Berry {'sharply ' if boost>=2 else ''}raised its Defense!"
            target._last_consumed_berry = target.item
            target.item = None
        elif berr == "maranga-berry" and cat == "special":
            old = target.stages.get("spd", 0)
            boost = 2 if ripen_mult > 1.0 else 1
            target.stages["spd"] = min(6, old + boost)
            msg += f"\n{target.species}'s Maranga Berry {'sharply ' if boost>=2 else ''}raised its Sp. Def!"
            target._last_consumed_berry = target.item
            target.item = None
 
    # Parental Bond hit count message
    if parental_bond_active and parental_bond_hit_count > 1:
        msg += f"\n└ Hit **{parental_bond_hit_count}** time(s)!"
    
    # Damage line with HP change (Showdown format: percentage in parentheses with arrow)
    # Show percentage for all damaging moves (including Max Moves and Z-Moves)
    actual_hp_lost = old_hp - target.hp
    if dmg > 0 or (hasattr(user, '_is_max_move') and user._is_max_move and actual_hp_lost > 0):
        # Calculate percentage based on ACTUAL HP lost (not raw damage)
        # This ensures we show correct % even when damage exceeds remaining HP
        hp_percent = round((actual_hp_lost / target.max_hp) * 100, 1) if target.max_hp > 0 else 0
        hp_percent = min(hp_percent, 100.0)  # Cap at 100%
        msg += f"\n└ The opposing {target.species} lost {hp_percent}% of its health!"
    elif dmg == 0 and not substitute_broken and not (hasattr(target, 'substitute') and target.substitute):
        # No damage and no substitute = immune/no effect
        return msg
        
        # === WEAKNESS POLICY: +2 Atk & SpA when hit super effectively ===
    if mult >= 2.0:
        if item_is_active(target):
            item_data = get_item_effect(normalize_item_name(target.item))
            if item_data.get("boost_on_super_effective"):
                boosts = item_data["boost_on_super_effective"]
                for stat, amount in boosts.items():
                    old_stage = target.stages.get(stat, 0)
                    target.stages[stat] = min(6, old_stage + amount)
                target.item = None  # Consume Weakness Policy
                msg += f"\n{target.species} used its Weakness Policy!"
                if boosts.get("atk"):
                    msg += f"\n{target.species}'s Attack rose sharply!"
                if boosts.get("spa"):
                    msg += f"\n{target.species}'s Sp. Atk rose sharply!"
    
    # Focus Sash message
    if focus_sash_used:
        msg += f"\n{target.species} hung on using its Focus Sash!"
        target.item = None  # Consume Focus Sash
    
    # === TYPE GEM CONSUMPTION ===
    # Consume gem after successful hit (not consumed on miss)
    if hasattr(user, '_gem_to_consume') and user._gem_to_consume:
        user.item = None  # Consume the gem
        delattr(user, '_gem_to_consume')  # Clean up the marker
    
    # === KNOCK OFF: Remove target's item after damage ===
    if move_lower == "knock-off" and target.item and target.hp > 0:
        can_remove_item, fail_reason_knock = can_remove_item_from_target(
            target,
            user,
            field_effects=field_effects,
            allow_if_target_fainted=False,
            cause="knock-off"
        )
        if can_remove_item:
            knocked_item = target.item
            # Check if it's a choice item before removing
            knocked_item_norm = normalize_item_name(knocked_item)
            knocked_item_data = get_item_effect(knocked_item_norm)
            target.item = None
            msg += f"\n**{target.species}** lost its **{knocked_item}**!"
            
            # Clear choice lock if target lost a choice item
            if knocked_item_data.get("choice_locks_move") and hasattr(target, '_player_id') and battle_state:
                battle_state._choice_locked[target._player_id] = None
        elif fail_reason_knock:
            msg += f"\n{fail_reason_knock}"
    
    if move_effect_main.get("removes_terrain") and field_effects:
        if not meta.get("miss") and not meta.get("immune") and not meta.get("invulnerable"):
            active_terrain = getattr(field_effects, "terrain", None)
            if active_terrain:
                terrain_names = {
                    "electric": "Electric Terrain",
                    "grassy": "Grassy Terrain",
                    "misty": "Misty Terrain",
                    "psychic": "Psychic Terrain"
                }
                terrain_label = terrain_names.get(active_terrain, f"{active_terrain.title()} Terrain")
                field_effects.terrain = None
                field_effects.terrain_turns = 0
                msg += f"\nThe {terrain_label} disappeared!"
    
    weather_to_set = move_effect_main.get("weather")
    if weather_to_set and field_effects and move_connected:
        normalized_weather = weather_to_set
        if normalized_weather == "hail":
            normalized_weather = "snow"
        cleared_special = clear_special_weather(field_effects)
        field_effects.weather = normalized_weather
        field_effects.weather_turns = 5
        field_effects.special_weather = None
        field_effects.heavy_rain = False
        field_effects.harsh_sunlight = False
        field_effects.weather_lock = None
        field_effects.weather_lock_owner = None
        weather_messages = {
            "sun": "The sunlight turned harsh!",
            "rain": "It started to rain!",
            "sandstorm": "A sandstorm kicked up!",
            "snow": "It started to snow!"
        }
        msg += f"\n{weather_messages.get(normalized_weather, 'The weather changed!')}"
    
    terrain_to_set = move_effect_main.get("terrain")
    if terrain_to_set and field_effects and move_connected:
        field_effects.terrain = terrain_to_set
        field_effects.terrain_turns = 5
        terrain_messages = {
            "electric": "Electric Terrain surrounded the battlefield!",
            "grassy": "Grassy Terrain grew all around!",
            "misty": "Misty Terrain enveloped the battlefield!",
            "psychic": "Psychic Terrain filled the area!"
        }
        msg += f"\n{terrain_messages.get(terrain_to_set, 'A mysterious terrain spread across the field!')}"
    
    if move_effect_main.get("stat_boost") and move_effect_main.get("affects_allies") and move_connected and user.hp > 0:
        boost_changes = move_effect_main.get("stat_boost", {})
        boost_msgs = modify_stages(user, boost_changes, caused_by_opponent=False, field_effects=field_effects)
        for boost_msg in boost_msgs:
            msg += f"\n{boost_msg}"
    
    if (
        move_effect_main.get("target_stat_drop")
        and move_connected
        and target.hp > 0
        and not move_effect_main.get("status_move")
    ):
        drop_changes = move_effect_main.get("target_stat_drop", {})
        drop_msgs = modify_stages(target, drop_changes, caused_by_opponent=True, field_effects=field_effects)
        for drop_msg in drop_msgs:
            msg += f"\n{drop_msg}"
        if drop_msgs:
            target._stats_lowered_this_turn = True
    
    # === RELIC SONG: Change Meloetta forme after damage ===
    if move_lower == "relic-song" and user.hp > 0:
        success, relic_msg = apply_relic_song(user)
        if success:
            msg += f"\n{relic_msg}"

    # === GROUNDING MOVES: Smack Down, Thousand Arrows ===
    
    if move_lower == "smack-down" and target.hp > 0:
        ground_msg = apply_smack_down(target)
        msg += f"\n{ground_msg}"
    
    if move_lower == "thousand-arrows" and target.hp > 0:
        ground_msg = apply_thousand_arrows(target)
        msg += f"\n{ground_msg}"
    
    # === SPECTRAL THIEF: Steal stat boosts after damage ===
    if move_lower == "spectral-thief":
        steal_msg = sm.apply_spectral_thief(user, target)
        if steal_msg:
            msg += f"\n{steal_msg}"
    
    # === ITEM STEALING MOVES: Thief, Covet ===
    # These steal the target's item after dealing damage (after both Parental Bond hits)
    move_effect_check_steal = get_move_secondary_effect(move_name)
    if move_effect_check_steal.get("steals_item") and dmg > 0 and target.hp > 0:
        gen_thief = get_generation(field_effects=field_effects)
        
        # Thief: Generation-specific mechanics
        if move_lower == "thief":
            if gen_thief >= 5 and user.hp <= 0:
                pass  # User fainted; cannot steal
            elif not user.item and target.item:
                can_remove, fail_reason = can_remove_item_from_target(
                    target,
                    user,
                    field_effects=field_effects,
                    allow_if_target_fainted=(target.hp <= 0),
                    cause="thief"
                )
                if can_remove:
                    stolen_item = target.item
                    target.item = None
                    user.item = stolen_item
                    msg += f"\n**{user.species}** stole **{target.species}**'s **{stolen_item}**!"
                elif fail_reason:
                    msg += f"\n{fail_reason}"
        elif move_lower == "covet":
            # Covet: Complex generation-specific mechanics
            can_steal_covet = True
            stolen_item_covet = None
            
            # Gen III: Does not make contact (no contact-based effects)
            # Gen IV+: Makes contact
            
            # Cannot steal if user already has item
            if user.item:
                can_steal_covet = False
            
            # Cannot steal if target has no item
            if not target.item:
                can_steal_covet = False
            
            # Gen V: Power changed from 40 to 60 (handled in move data)
            
            # Gen III: Cannot steal if target has Sticky Hold (stops before stealing)
            # Gen V+: Can steal if target faints from damage (Sticky Hold bypassed)
            if can_steal_covet and target.item:
                target_ability_covet = normalize_ability_name(target.ability or "")
                
                # Check Sticky Hold
                if target_ability_covet == "sticky-hold":
                    # Gen III-IV: Cannot steal
                    if gen_thief <= 4:
                        can_steal_covet = False
                        msg += f"\n**{target.species}**'s Sticky Hold prevents item theft!"
                    # Gen V+: Can steal if target fainted
                    elif gen_thief >= 5:
                        if target.hp > 0:
                            can_steal_covet = False
                            msg += f"\n**{target.species}**'s Sticky Hold prevents item theft!"
                        # If target fainted, can steal (handled below)
                
                # Check item restrictions (Gen IV+)
                if can_steal_covet and gen_thief >= 4:
                    stolen_item_covet = target.item
                    item_norm_covet = normalize_item_name(target.item)
                    
                    # Gen IV+: Multitype prevents theft (if target has Multitype)
                    target_ability_multitype = normalize_ability_name(target.ability or "")
                    if target_ability_multitype == "multitype":
                        can_steal_covet = False
                        msg += f"\n**{target.species}**'s Multitype prevents item theft!"
                    
                    # Gen IV+: Consumable items are consumed before stealing
                    if can_steal_covet:
                        t_item_data_covet = get_item_effect(normalize_item_name(target.item))
                        if t_item_data_covet.get("consumable_on_damage"):
                            can_steal_covet = False
                            msg += f"\n{target.species}'s {target.item} was consumed before it could be stolen!"
                    
                    # Gen V+: Various restrictions
                    if can_steal_covet and gen_thief >= 5:
                        # Cannot steal Mega Stones, Z-Crystals if either could use them
                        if "mega-stone" in item_norm_covet or "z-crystal" in item_norm_covet:
                            can_steal_covet = False
                        
                        # Plates: Cannot steal if either is Arceus (Multitype has no effect on Covet)
                        if "plate" in item_norm_covet:
                            if "arceus" in user.species.lower() or "arceus" in target.species.lower():
                                can_steal_covet = False
                        
                        # Griseous Orb: Can steal if neither user nor target is Giratina
                        if "griseous-orb" in item_norm_covet:
                            if "giratina" in user.species.lower() or "giratina" in target.species.lower():
                                can_steal_covet = False
                        
                        # Drives: Cannot steal if either is Genesect
                        if "drive" in item_norm_covet:
                            if "genesect" in user.species.lower() or "genesect" in target.species.lower():
                                can_steal_covet = False
                    
                    # Gen VI+: Additional restrictions
                    if can_steal_covet and gen_thief >= 6:
                        # Memories: Cannot steal if either is Silvally
                        if "memory" in item_norm_covet:
                            if "silvally" in user.species.lower() or "silvally" in target.species.lower():
                                can_steal_covet = False
                        
                        # Rusted Sword: Cannot steal if either is Zacian
                        if "rusted-sword" in item_norm_covet:
                            if "zacian" in user.species.lower() or "zacian" in target.species.lower():
                                can_steal_covet = False
                        
                        # Rusted Shield: Cannot steal if either is Zamazenta
                        if "rusted-shield" in item_norm_covet:
                            if "zamazenta" in user.species.lower() or "zamazenta" in target.species.lower():
                                can_steal_covet = False
                        
                        # Booster Energy: Cannot steal if either is a Paradox Pokémon
                        if "booster-energy" in item_norm_covet:
                            paradox_pokemon = ["sandy-shocks", "scream-tail", "brute-bonnet", "flutter-mane", 
                                               "slither-wing", "great-tusk", "iron-treads", "iron-bundle", 
                                               "iron-hands", "iron-jugulis", "iron-moth", "iron-thorns", 
                                               "iron-valiant", "roaring-moon", "iron-leaves", "walking-wake"]
                            if any(par in user.species.lower() for par in paradox_pokemon) or \
                               any(par in target.species.lower() for par in paradox_pokemon):
                                can_steal_covet = False
                    
                    # Gen III: Cannot steal e-Reader Berries and Mail
                    if can_steal_covet and gen_thief == 3:
                        if "mail" in item_norm_covet:
                            can_steal_covet = False
                        # e-Reader berries would be specific items (not implementing full list)
                    
                    # Gen V: If user faints, cannot steal (but still dealt damage)
                    if can_steal_covet and gen_thief >= 5:
                        if user.hp <= 0:
                            can_steal_covet = False
                    
                    # Gen VI+: Covet PP changed from 40 to 25 (handled in move data)
                    
                    # Gen VI+: Max Raid Battle fails entirely (not applicable in PvP)
                    
                    # Finally, attempt to steal
                    if can_steal_covet and stolen_item_covet:
                        user.item = stolen_item_covet
                        target.item = None
                        msg += f"\n**{user.species}** stole **{target.species}**'s **{stolen_item_covet}**!"
    
    # === BERRY-EATING MOVES: Bug Bite, Pluck ===
    # These consume the target's berry after dealing damage
    if move_effect_check_steal.get("eats_berry") and dmg > 0 and target.hp > 0:
        if target.item and "berry" in target.item.lower():
            ability_supressed = getattr(target, '_ability_suppressed', False)
            target_ability_norm = normalize_ability_name(target.ability or "")
            target_ability_data = get_ability_effect(target_ability_norm)
            if target_ability_data.get("item_cannot_be_removed") and not ability_supressed:
                ability_name = (target.ability or target_ability_norm or "Ability").replace("-", " ").title()
                msg += f"\n**{target.species}**'s **{ability_name}** kept its berry!"
            else:
                berry = target.item
                target.item = None
                generation = get_generation(field_effects=field_effects)
                user_ability_norm = normalize_ability_name(user.ability or "")
                user_ability_suppressed = getattr(user, '_ability_suppressed', False)
                klutz_active = user_ability_norm == "klutz" and not user_ability_suppressed
                embargo_active = getattr(user, 'embargoed', 0) > 0
                magic_room_active = bool(getattr(field_effects, 'magic_room', 0)) if field_effects else False
                apply_effect = True
                if generation == 4 and (klutz_active or embargo_active or magic_room_active):
                    apply_effect = False
                
                berry_data = get_berry_effect(berry.lower().replace(" ", "-"))
                if apply_effect and berry_data:
                    if berry_data.get("restores_hp"):
                        heal_amount = berry_data.get("heal_amount", 0)
                        if heal_amount:
                            if heal_amount < 1:
                                heal = int(user.max_hp * heal_amount)
                            else:
                                heal = int(heal_amount)
                            user.hp = min(user.max_hp, user.hp + heal)
                            msg += f"\n**{user.species}** ate **{target.species}**'s **{berry}** and restored {heal} HP!"
                    elif berry_data.get("cures_status"):
                        cured_status = berry_data.get("cures_status")
                        if user.status == cured_status or cured_status == "any":
                            old_status = user.status
                            user.status = None
                            msg += f"\n**{user.species}** ate **{target.species}**'s **{berry}** and was cured of {old_status}!"
                    else:
                        msg += f"\n**{user.species}** ate **{target.species}**'s **{berry}**!"
                else:
                    if apply_effect and not berry_data:
                        msg += f"\n**{user.species}** ate **{target.species}**'s **{berry}**!"
                    else:
                        msg += f"\n**{user.species}** snatched **{target.species}**'s **{berry}**, but couldn't make use of it!"
    
    # Contact effects
    if extra:
        for effect in extra:
            msg += f"\n{effect}"
    
    # === EXPLOSION / SELF-DESTRUCT: User faints (generation-specific timing and mechanics) ===
    if move_lower in ["explosion", "self-destruct"]:
        generation = get_generation(field_effects=field_effects)
        
        # Explosion: Gen I power 170 (with Defense halving = 340), Gen II power 250 (with Defense halving = 500)
        # Self-Destruct: Gen I power 130 (with Defense halving = 260), Gen II power 200 (with Defense halving = 400)
        # Gen III-IV: Defense halving, Gen V: Removed
        # Gen V: User faints BEFORE dealing damage (unlike previous generations)
        # Gen VI+: User faints AFTER dealing damage (restored from Gen V behavior)
        
        # Gen IV: If all targets already fainted this turn, fails and user doesn't faint
        if generation == 4:
            # Check if target already fainted (would be handled by apply_move, but verify)
            if target.hp <= 0 and dmg == 0:
                return msg  # Don't faint if no valid target
        # Gen V: If all targets fainted, user still faints
        elif generation == 5:
            user.hp = 0
            msg += f"\n**{user.species}** fainted from the explosion!"
        # Gen VI+: User faints AFTER dealing damage (normal order)
        elif generation >= 6:
            user.hp = 0
            msg += f"\n**{user.species}** fainted from the explosion!"
        # Gen I-IV: User faints even if move misses or target is immune
        # Gen I: Breaking substitute prevents fainting
        # Gen II: Can faint even if target behind substitute
        else:
            # Gen I special: If Explosion/Self-Destruct breaks substitute, user doesn't faint (but sprite disappears)
            if hasattr(target, 'substitute') and target.substitute and generation == 1:
                # Gen I: Breaking substitute prevents fainting (both Explosion and Self-Destruct)
                pass  # Don't faint
            elif generation == 2:
                # Gen II: User faints even if target is behind substitute
                user.hp = 0
                msg += f"\n**{user.species}** fainted from the explosion!"
            else:
                # Gen III-IV: User faints normally
                user.hp = 0
                msg += f"\n**{user.species}** fainted from the explosion!"
    
    # === SHELL BELL: Heal 1/8 of damage dealt ===
    if dmg > 0 and user.item and user.hp > 0:
        item_data = get_item_effect(normalize_item_name(user.item))
        if "heals_on_damage" in item_data:
            heal = max(1, int(dmg * item_data["heals_on_damage"]))
            old_hp = user.hp
            user.hp = min(user.max_hp, user.hp + heal)
            actual_heal = user.hp - old_hp
            if actual_heal > 0:
                msg += f"\n{user.species} restored HP with Shell Bell! (+{actual_heal} HP)"
    
    # === FOCUS BAND: 10% chance to survive with 1 HP ===
    if target.hp <= 0 and target.item:
        item_data = get_item_effect(normalize_item_name(target.item))
        if "survive_chance" in item_data:
            if random.random() < item_data["survive_chance"]:
                target.hp = 1
                msg += f"\n{target.species} hung on with its Focus Band!"
    
    # === TYPE RESISTANCE BERRIES: Halve super effective damage once ===
    if mult >= 2.0 and dmg > 0 and target.item:
        item_data = get_item_effect(normalize_item_name(target.item))
        if "halves_super_effective" in item_data:
            # Check if the berry matches the move type
            if item_data.get("resists_type") == meta.get("type"):
                # Check for Ripen ability (doubles berry effects)
                berry_damage_mult = 0.5  # Default: halve damage
                target_ability = normalize_ability_name(target.ability or "")
                target_ability_data = get_ability_effect(target_ability)
                if target_ability_data.get("berry_effect_mult"):
                    # Ripen: 2x effect means damage is reduced to 1/4 instead of 1/2
                    berry_damage_mult = 0.25
                
                # Retroactively reduce the damage
                dmg_reduction = int(dmg * (1.0 - berry_damage_mult))
                target.hp = min(target.max_hp, target.hp + dmg_reduction)
                target.item = None  # Consume berry
                msg += f"\n{target.species}'s berry weakened the damage!"
    
    # === ABSORB BULB FAMILY: Boost stat when hit by specific type ===
    if dmg > 0 and target.item and item_is_active(target):
        item_data = get_item_effect(normalize_item_name(target.item))
        gen_ab = get_generation(field_effects=field_effects)
        
        if "boost_on_hit_by_type" in item_data:
            boost_data = item_data["boost_on_hit_by_type"]
            required_type = boost_data.get("type")
            move_type = meta.get("type")
            
            if required_type == move_type:
                # Check generation requirement
                min_gen = item_data.get("min_gen", 1)
                if gen_ab >= min_gen:
                    # Check if already at max stats (or -6 with Contrary)
                    target_ability_norm = normalize_ability_name(target.ability or "")
                    target_ability_data = get_ability_effect(target_ability_norm)
                    contrary = target_ability_data.get("inverts_stat_changes", False)
                    
                    # Check if protected (immunity, Wonder Guard, absorb abilities)
                    if item_data.get("doesnt_activate_if_protected"):
                        # Check for immunity (0x damage already handled, but check abilities like Water Absorb)
                        if type_mult == 0.0:  # Type immunity
                            return msg  # Don't activate
                    
                    # Check if at max stage (or -6 with Contrary)
                    should_activate = True
                    if item_data.get("doesnt_activate_at_max"):
                        stat_stages = boost_data.get("stages", {})
                        for stat, amount in stat_stages.items():
                            current_stage = target.stages.get(stat, 0)
                            if not contrary:
                                if current_stage >= 6:
                                    should_activate = False
                                    break
                            else:
                                if current_stage <= -6:
                                    should_activate = False
                                    break
                    
                    if should_activate:
                        stat_stages = boost_data.get("stages", {})
                        # Apply Contrary reversal if needed
                        if contrary and item_data.get("contrary_reverses"):
                            stat_stages = {stat: -amount for stat, amount in stat_stages.items()}
                        
                        item_name_ab = normalize_item_name(target.item)
                        target.item = None  # Consume item
                        boost_msgs = modify_stages(target, stat_stages, caused_by_opponent=True, field_effects=field_effects)
                        for boost_msg in boost_msgs:
                            msg += f"\n{boost_msg}"
                        msg += f"\n{target.species}'s {item_name_ab.replace('-', ' ').title()} was consumed!"
    
    # === POP AIR BALLOON after being hit ===
    if hasattr(target, '_balloon_will_pop') and target._balloon_will_pop:
        target.item = None
        target._balloon_will_pop = False
        msg += f"\n{target.species}'s **Air Balloon** popped!"
    elif dmg > 0 and target.item:
        item_data = get_item_effect(normalize_item_name(target.item))
        if item_data.get("pops_on_hit"):
            target.item = None
            msg += f"\n{target.species}'s **Air Balloon** popped!"
    
    # Clear Smog resets target's stat changes
    move_effect_data = get_move_secondary_effect(move_name)
    if move_effect_data.get("clears_target_stats"):
        target.stages = {
            "atk": 0, "defn": 0, "spa": 0, "spd": 0, "spe": 0,
            "accuracy": 0, "evasion": 0
        }
        msg += f"\n{target.species}'s stat changes were removed!"
    
    # === SECONDARY EFFECTS ===
    # Secondary effects (status, flinch, stat changes, etc.) are now handled by apply_secondary_effect()
    # This ensures effects are only rolled ONCE using hardcoded values from move_effects.py
    
    # === RECOIL, DRAIN & RECHARGE MOVES (from database) ===
    # mechanics already fetched at top of apply_move
    # Struggle always has recoil, even if not marked in database
    is_struggle_recoil = move_lower == "struggle"
    
    if (mechanics and dmg > 0) or (is_struggle_recoil and dmg > 0):
        # Recoil moves
        if ((mechanics and mechanics.get('is_recoil_move')) or is_struggle_recoil) and not parental_bond_skip_recoil and not skip_standard_recoil:
            # Check for Rock Head ability (negates recoil)
            # Special case: If Rock Head was replaced by Mummy/Lingering Aroma during this move,
            # the user still takes recoil damage because Rock Head was not active when damage was calculated
            user_ability_norm = normalize_ability_name(user.ability or "")
            user_ability_data = get_ability_effect(user_ability_norm)
            
            # Check if Rock Head is active OR if it prevents recoil
            has_rock_head = user_ability_data.get("no_recoil_damage", False)
            
            # Exception: Struggle always has recoil regardless of Rock Head
            is_struggle = move_lower == "struggle"
            
            if not has_rock_head or is_struggle:
                # Gen I: Take Down, Double-Edge, and Submission have no recoil on KO or substitute break
                should_apply_recoil = True
                if generation_check == 1 and move_lower in ["take-down", "double-edge", "submission"]:
                    # Check if target was KO'd or substitute was broken
                    target_koed = (target.hp <= 0)
                    substitute_was_broken = getattr(target, '_substitute_broken_this_turn', False)
                    if target_koed or substitute_was_broken:
                        should_apply_recoil = False
                
                if should_apply_recoil:
                    old_hp = user.hp
                    recoil = calculate_recoil_damage(move_name, dmg, user.max_hp, field_effects=field_effects)
                    if recoil > 0:  # Only apply if there's actual recoil damage
                        user.hp = max(0, user.hp - recoil)
                        msg += f"\n└ **{user.species}** was damaged by the recoil!"
                
                # === EMERGENCY EXIT from STRUGGLE RECOIL ONLY ===
                # Struggle recoil can trigger Emergency Exit on the user
                if move_lower == "struggle" and user.hp > 0:
                    user_ability_data = get_ability_effect(user_ability_norm)
                    if user_ability_data.get("switches_out_at_half_hp"):
                        hp_before_percent = (old_hp / user.max_hp) * 100
                        hp_after_percent = (user.hp / user.max_hp) * 100
                        
                        if hp_before_percent >= 50.0 and hp_after_percent < 50.0:
                            user._emergency_exit_triggered = True
                            ability_name = (user.ability or user_ability_norm).replace("-", " ").title()
                            msg += f"\n**{user.species}'s {ability_name}!**"
                
                if user.hp <= 0:
                    msg += f"\n**{user.species}** fainted!"
        
        # Drain moves (skip if already handled by Parental Bond or multi-hit)
        if mechanics['is_drain_move'] and not (parental_bond_drain_handled or (mechanics and mechanics.get('is_multi_hit'))):
            move_lower_drain = move_name.lower().replace(" ", "-")
            generation_drain = get_generation(field_effects=field_effects)
            
            # Note: Dream Eater sleep/substitute checks already happened at the beginning of apply_move
            # This section only handles healing logic (substitute healing behavior for Gen V+)
            
            # Dream Eater/Leech Life: Gen-specific substitute healing behavior
            heal_from_substitute = False
            if move_lower_drain in ["dream-eater", "leech-life"]:
                # Check if target has substitute
                target_has_substitute = hasattr(target, 'substitute') and target.substitute
                if target_has_substitute:
                    # Gen I-IV: Already handled at beginning (moves fail)
                    # Gen V+: Both can heal from substitute
                    if generation_drain >= 5:
                        heal_from_substitute = True
            elif move_lower_drain == "giga-drain":
                target_has_substitute = hasattr(target, 'substitute') and target.substitute
                if target_has_substitute and generation_drain >= 3:
                        heal_from_substitute = True
            # Absorb/Mega Drain: Generation-specific substitute behavior
            elif move_lower_drain in ["absorb", "mega-drain"]:
                target_has_substitute = hasattr(target, 'substitute') and target.substitute
                if target_has_substitute:
                    if generation_drain == 1:
                        # Gen I: Always miss if substitute (Japanese/Stadium behavior)
                        return f"**{user.species}** used **{move_name}**!\nBut it failed!"
                    elif generation_drain == 2:
                        # Gen II: Always miss if substitute (Japanese/Stadium behavior)
                        return f"**{user.species}** used **{move_name}**!\nBut it failed!"
                    elif generation_drain >= 3:
                        # Gen III+: Can heal from substitute
                        heal_from_substitute = True
            
            # Heal Block check (Gen VI+ for Leech Life/Absorb/Mega Drain, Gen V+ generally)
            # Note: Dream Eater Heal Block check already happened at the beginning of apply_move
            if move_lower_drain in ["absorb", "mega-drain"] and generation_drain >= 6:
                if hasattr(user, 'heal_blocked') and getattr(user, 'heal_blocked', 0) > 0:
                    # Heal Block prevents Absorb/Mega Drain from being used
                    return f"**{user.species}** used **{move_name}**!\nBut it failed!"
            elif move_lower_drain == "leech-life" and generation_drain >= 6:
                if hasattr(user, 'heal_blocked') and getattr(user, 'heal_blocked', 0) > 0:
                    # Heal Block prevents Leech Life from healing (but still deals damage)
                    pass  # Don't heal, but move still does damage
            
            if target_had_substitute and not substitute_bypassed and not heal_from_substitute:
                drain_damage_amount = 0
            else:
                drain_damage_amount = drain_base_damage
            heal = calculate_drain_healing(move_name, drain_damage_amount)
            
            # Big Root: 65% for Dream Eater/Leech Life/Absorb/Mega Drain (30% boost = 50% * 1.3 = 65%)
            if user.item and "big-root" in user.item.lower().replace(" ", "-"):
                if generation_drain >= 4:  # Big Root works Gen IV+
                    if move_lower_drain in ["dream-eater", "leech-life", "absorb", "mega-drain"]:
                        heal = int(heal * 1.3)  # 65% total
                    else:
                        heal = int(heal * 1.3)  # Other drain moves also get 30% boost
            
            # Liquid Ooze - reverses drain (damages attacker instead of healing) - Gen III+
            target_ability = normalize_ability_name(target.ability or "")
            target_ability_data = get_ability_effect(target_ability)
            if generation_drain >= 3 and target_ability_data.get("damages_draining_moves") and heal > 0:
                user.hp = max(0, user.hp - heal)
                msg += f"\n{target.species}'s Liquid Ooze damaged {user.species}! (-{heal} HP)"
                if user.hp <= 0:
                    msg += f"\n{user.species} fainted!"
            else:
                # Gen VI: Leech Life blocked by Heal Block
                if move_lower_drain == "leech-life" and generation_drain >= 6:
                    if hasattr(user, 'heal_blocked') and getattr(user, 'heal_blocked', 0) > 0:
                        msg += f"\n{user.species} could not drain HP due to Heal Block!"
                    else:
                        if heal > 0:
                            user.hp = min(user.max_hp, user.hp + heal)
                            msg += f"\n{user.species} drained {heal} HP!"
                else:
                    if getattr(user, 'heal_blocked', 0) > 0:
                        msg += f"\n{user.species} could not drain HP due to Heal Block!"
                    elif heal > 0:
                        user.hp = min(user.max_hp, user.hp + heal)
                        msg += f"\n{user.species} drained {heal} HP!"
        
        # Recharge moves (Hyper Beam, etc.) - must recharge next turn
        # Only recharge if move actually connected and had an effect
        if mechanics['is_recharge_move']:
            should_recharge = True
            
            # Check if move failed, missed, or had no effect
            move_failed = getattr(user, '_last_move_failed', False)
            move_missed = meta.get("miss", False)
            # Type immunity (0x damage) means no effect - recharge moves are all damaging moves
            type_immune = (dmg == 0 and not meta.get("status", False) and not meta.get("miss"))
            
            # Gen I Hyper Beam: No recharge on miss, KO, substitute break, or binding move glitch
            if move_lower == "hyper-beam" and generation_check == 1:
                move_hit = dmg > 0 or (meta.get("miss") == False and not meta.get("immune"))
                target_koed = target.hp <= 0
                substitute_broken = getattr(target, '_substitute_broken_this_turn', False)
                # Binding move glitch handled separately if applicable
                if meta.get("miss") or target_koed or substitute_broken:
                    should_recharge = False
            else:
                # All other recharge moves: No recharge if move failed, missed, or had no effect (type immunity)
                if move_failed or move_missed or type_immune:
                    should_recharge = False
            
            if should_recharge:
                user.must_recharge = True
                user.recharging_move = move_name  # Store which move requires recharge
                msg += f"\n{user.species} must recharge!"

    # === SHELL BELL (single-hit path) ===
    # Gen 3: heals after each damaging hit (including Substitute); ignores Heal Block
    # Gen 4: heals once after hit; ignores Heal Block; doesn't heal if only Substitute (not tracked)
    # Gen 5+: heals once after hit; blocked by Heal Block; skipped if Sheer Force boosted
    if item_is_active(user) and user.item and dmg > 0:
        if normalize_item_name(user.item) == "shell-bell":
            generation = get_generation(field_effects=field_effects)
            if generation >= 5 and getattr(user, 'heal_blocked', 0):
                pass
            elif generation >= 5 and getattr(user, '_sheer_force_active', False):
                pass
            else:
                heal = max(1, dmg // 8)
                old_hp_sb = user.hp
                user.hp = min(user.max_hp, user.hp + heal)
                actual_heal_sb = user.hp - old_hp_sb
                if actual_heal_sb > 0:
                    msg += f"\n{user.species}'s Shell Bell restored HP! (+{actual_heal_sb} HP)"
    
    # === PARENTAL BOND DEFERRED RECOIL ===
    # Apply accumulated recoil from both Parental Bond hits
    if parental_bond_skip_recoil and parental_bond_deferred_recoil > 0:
        old_hp_pb = user.hp
        user.hp = max(0, user.hp - parental_bond_deferred_recoil)
        msg += f"\n└ **{user.species}** was damaged by the recoil!"
        
        # === EMERGENCY EXIT from STRUGGLE RECOIL ONLY ===
        if move_lower == "struggle" and user.hp > 0:
            user_ability_norm_pb = normalize_ability_name(user.ability or "")
            user_ability_data_pb = get_ability_effect(user_ability_norm_pb)
            if user_ability_data_pb.get("switches_out_at_half_hp"):
                hp_before_percent_pb = (old_hp_pb / user.max_hp) * 100
                hp_after_percent_pb = (user.hp / user.max_hp) * 100
                
                if hp_before_percent_pb >= 50.0 and hp_after_percent_pb < 50.0:
                    user._emergency_exit_triggered = True
                    ability_name_pb = (user.ability or user_ability_norm_pb).replace("-", " ").title()
                    msg += f"\n**{user.species}'s {ability_name_pb}!**"
    
    # === LIFE ORB RECOIL ===
    # Life Orb takes 10% HP after dealing damage (not on status moves)
    user_item = (user.item or "").lower().replace(" ", "-")
    if user_item == "life-orb" and dmg > 0:
        life_orb_dmg = int(user.max_hp * 0.1)
        user.hp = max(0, user.hp - life_orb_dmg)
        msg += f"\n{user.species} lost {life_orb_dmg} HP from Life Orb!"
        if user.hp <= 0:
            msg += f"\n{user.species} fainted from Life Orb damage!"
    
    # === CHECK FOR HP-RESTORING BERRIES ===
    
    # Check if target should consume a berry after taking damage
    berry_msg = check_and_consume_hp_berries(target)
    if berry_msg:
        msg += f"\n{berry_msg}"
    
    # Check if attacker should consume a berry after recoil/Life Orb damage
    berry_msg = check_and_consume_hp_berries(user)
    if berry_msg:
        msg += f"\n{berry_msg}"
    
    # Secondary effects (paralysis, burn, stat drops, etc.)
    # Only apply if move actually connected AND target is still alive AND didn't miss
    move_connected = (dmg > 0 or meta.get("status", False)) and not meta.get("miss") and target.hp > 0

    if normalized_move == "brick-break" and target_side:
        brick_break_gen = get_generation(field_effects=field_effects)
        remove_allowed = False
        if brick_break_gen <= 4:
            remove_allowed = True
        else:
            # Gen 5+: Only breaks screens if move connects and is super effective
            # Calculate type effectiveness for this check
            move_data_bb = load_move(move_name, generation=generation_for_move_data, battle_state=battle_state)
            move_type_bb = move_data_bb.get("type", "Normal") if move_data_bb else "Normal"
            move_category_bb = move_data_bb.get("category", move_data_bb.get("damage_class", "physical")) if move_data_bb else "physical"
            type_mult_bb, _ = type_multiplier(move_type_bb, target, is_contact=False, move_category=move_category_bb, generation=brick_break_gen, field_effects=field_effects, user=user)
            if move_connected and type_mult_bb > 0:
                remove_allowed = True

        if remove_allowed:
            removed_effects: List[str] = []
            if target_side.reflect:
                target_side.reflect = False
                target_side.reflect_turns = 0
                removed_effects.append("Reflect")
            if target_side.light_screen:
                target_side.light_screen = False
                target_side.light_screen_turns = 0
                removed_effects.append("Light Screen")
            if brick_break_gen >= 5 and target_side.aurora_veil:
                target_side.aurora_veil = False
                target_side.aurora_veil_turns = 0
                removed_effects.append("Aurora Veil")

            if removed_effects:
                if len(removed_effects) == 1:
                    shattered = removed_effects[0]
                elif len(removed_effects) == 2:
                    shattered = " and ".join(removed_effects)
                else:
                    shattered = ", ".join(removed_effects[:-1]) + f", and {removed_effects[-1]}"
                msg += f"\n{shattered} was shattered!"

    secondary_effects = apply_secondary_effect(
        user,
        target,
        move_name,
        move_hit=move_connected,
        field_effects=field_effects,
        target_side=target_side
    )
    for effect_msg in secondary_effects:
        msg += f"\n{effect_msg}"
    
    # === FLING SPECIAL ITEM EFFECTS ===
    # Apply special item effects after damage (berries, status, flinch, etc.)
    if move_lower == "fling" and hasattr(user, '_fling_item_effect_msg') and user._fling_item_effect_msg:
        msg += f"\n{user._fling_item_effect_msg}"
        delattr(user, '_fling_item_effect_msg')
    
    # Fling berry activation (berries activate for target even if usual trigger condition not satisfied)
    if move_lower == "fling" and hasattr(user, '_fling_berry_activated') and user._fling_berry_activated:
        if hasattr(target, '_flung_berry') and target._flung_berry:
            berry_name = target._flung_berry
            berry_data = get_berry_effect(berry_name.lower().replace(" ", "-"))
            if berry_data:
                # Apply berry effect to target
                if berry_data.get("restores_hp"):
                    heal_amount = berry_data.get("heal_amount", 0)
                    if heal_amount:
                        if heal_amount < 1:
                            heal = int(target.max_hp * heal_amount)
                        else:
                            heal = int(heal_amount)
                        target.hp = min(target.max_hp, target.hp + heal)
                        msg += f"\n{target.species} consumed the {berry_name.replace('-', ' ').title()} and restored {heal} HP!"
                elif berry_data.get("cures_status"):
                    cured_status = berry_data.get("cures_status")
                    if target.status == cured_status or cured_status == "any":
                        old_status = target.status
                        target.status = None
                        msg += f"\n{target.species} consumed the {berry_name.replace('-', ' ').title()} and was cured of {old_status}!"
            delattr(target, '_flung_berry')
            delattr(target, '_flung_berry_user')
        delattr(user, '_fling_berry_activated')
    
    # Fling flinch item (King's Rock / Razor Fang)
    if move_lower == "fling" and hasattr(user, '_fling_flinch_item') and user._fling_flinch_item:
        if hasattr(target, '_flung_flinch_item') and target._flung_flinch_item:
            from .db_move_effects import apply_flinch
            flinch_success, flinch_msg = apply_flinch(
                user, target, move_has_flinch=False, flinch_chance=0.1,
                field_effects=field_effects, move_name=move_name
            )
            if flinch_success:
                msg += f"\n{flinch_msg}"
            delattr(target, '_flung_flinch_item')
        delattr(user, '_fling_flinch_item')
    
    # Clean up Fling power override
    if move_lower == "fling" and hasattr(user, '_fling_power_override'):
        delattr(user, '_fling_power_override')

    # get_move_secondary_effect is already imported at the top of the file, no need to import again
    move_effect_metadata = get_move_secondary_effect(move_name)

    if (
        move_effect_metadata
        and move_effect_metadata.get("suppresses_ability_if_moved")
        and move_connected
        and target.hp > 0
    ):
        if getattr(target, '_moved_this_turn', False):
            ability_norm = normalize_ability_name(target.ability or "")
            suppression_exceptions = set(move_effect_metadata.get("suppression_exceptions", []))
            if ability_norm and ability_norm not in suppression_exceptions:
                ability_shield_active = False
                if item_is_active(target) and getattr(target, 'item', None):
                    item_data = get_item_effect(normalize_item_name(target.item))
                    if item_data.get("protects_ability"):
                        ability_shield_active = True
                        msg += f"\n{target.species}'s Ability Shield protected its ability!"
                if not ability_shield_active:
                    if not getattr(target, '_ability_suppressed', False):
                        target._ability_suppressed = True
                        target.ability_suppressed = True
                        ability_name = (target.ability or ability_norm or "Ability").replace("-", " ").title()
                        msg += f"\n{target.species}'s {ability_name} was suppressed!"
    
    if move_effect.get("forces_switch") and move_connected and target.hp > 0 and user.hp > 0:
        substitute_blocks = move_effect.get("force_switch_blocked_by_substitute") and getattr(target, 'substitute', None)
        if substitute_blocks:
            msg += f"\nBut it failed! ({target.species} is protected by its substitute!)"
        else:
            can_switch, switch_reason = can_switch_out(target, user, force_switch=True, field_effects=field_effects)
            if can_switch:
                target._roar_forced_switch = True
            else:
                if switch_reason:
                    msg += f"\nBut it failed! ({switch_reason})"
                else:
                    msg += f"\nBut it failed!"
    
    removes_hazards = move_effect_metadata.get("removes_hazards") if move_effect_metadata else None
    if removes_hazards and battle_state and user.hp > 0:
        removes = removes_hazards
        if removes is True:
            removes = "self"


        try:
            user_side = battle_state.p1_side if user == battle_state._active(battle_state.p1_id) else battle_state.p2_side
            opp_side = battle_state.p2_side if user == battle_state._active(battle_state.p1_id) else battle_state.p1_side
        except Exception:
            user_side = None
            opp_side = None

        if removes == "both" and user_side and opp_side:
            user_cleared = clear_hazards(user_side.hazards, move_name)
            opp_cleared = clear_hazards(opp_side.hazards, move_name)
            if user_cleared:
                msg += f"\n{user_cleared}"
            if opp_cleared:
                msg += f"\n{opp_cleared}"
        elif removes == "self" and user_side:
            cleared_msg = clear_hazards(user_side.hazards, move_name)
            if cleared_msg:
                msg += f"\n{cleared_msg}"

        freed_lines: List[str] = []
        if getattr(user, "partially_trapped", False):
            user.partially_trapped = False
            user.partial_trap_turns = 0
            user.partial_trap_damage = 0.0
            freed_lines.append(f"{user.species} was freed from binding!")
        if getattr(user, "trapped", False):
            user.trapped = False
            user.trap_source = None
        if hasattr(user, "leech_seeded") and user.leech_seeded:
            user.leech_seeded = False
            freed_lines.append(f"{user.species} shed Leech Seed!")

        for line in freed_lines:
            msg += f"\n{line}"
    
    # Tri Attack special effects (thawing, random status)
    if move_lower == "tri-attack" and move_connected:
        tri_attack_msgs = sm.apply_tri_attack_effects(user, target, move_name, dmg, field_effects=field_effects)
        for tri_msg in tri_attack_msgs:
            msg += f"\n{tri_msg}"
    
    # === THROAT SPRAY: +1 SpA after using sound move (Gen 8+) ===
    if move_connected and dmg > 0 and item_is_active(user) and user.item:
        move_mech = get_move_mechanics(move_name)
        if move_mech and move_mech.get('is_sound_move'):
            u_item_ts = normalize_item_name(user.item)
            u_item_data_ts = get_item_effect(u_item_ts)
            gen_ts2 = get_generation(field_effects=field_effects)
            if u_item_data_ts.get("boosts_spa_after_sound") and gen_ts2 >= 8:
                old_spa = user.stages.get("spa", 0)
                user.stages["spa"] = min(6, old_spa + 1)
                user.item = None  # Consume Throat Spray
                msg += f"\n{user.species}'s Throat Spray raised its Sp. Atk!"
    
    # === RED CARD / EJECT BUTTON / EJECT PACK: Force switch after being hit ===
    if move_connected and target.hp > 0 and item_is_active(target) and target.item:
        t_item = normalize_item_name(target.item)
        t_item_data = get_item_effect(t_item)
        gen_now = get_generation(field_effects=field_effects)
        
        # Red Card: force opponent to switch after taking damage (Gen 5+)
        if t_item_data.get("forces_opponent_switch") and gen_now >= 5:
            # Can't switch if target is trapped
            can_switch, switch_reason = can_switch_out(user, target, force_switch=True, field_effects=field_effects)
            if can_switch:
                target.item = None  # Consume Red Card
                user._red_card_switch = True  # Flag for forced switch
                msg += f"\n{target.species}'s Red Card forced {user.species} to switch out!"
            else:
                msg += f"\n{target.species}'s Red Card tried to force a switch, but {switch_reason}"
        
        # Eject Button: force holder to switch after taking damage (Gen 5+)
        if t_item_data.get("forces_holder_switch") and gen_now >= 5:
            can_switch, switch_reason = can_switch_out(target, user, force_switch=True, field_effects=field_effects)
            if can_switch:
                target.item = None  # Consume Eject Button
                target._eject_button_switch = True
                msg += f"\n{target.species}'s Eject Button forced it to switch out!"
            else:
                msg += f"\n{target.species}'s Eject Button tried to activate, but {switch_reason}"
        
        # Eject Pack: force holder to switch after stat drop (Gen 8+)
        if t_item_data.get("ejects_on_stat_drop") and gen_now >= 8:
            # Check if stats were lowered this turn (from this move's secondary effects)
            if hasattr(target, '_stats_lowered_this_turn') and target._stats_lowered_this_turn:
                can_switch, switch_reason = can_switch_out(target, user, force_switch=True, field_effects=field_effects)
                if can_switch:
                    target.item = None  # Consume Eject Pack
                    target._eject_pack_switch = True
                    msg += f"\n{target.species}'s Eject Pack activated and forced it to switch out!"
                else:
                    msg += f"\n{target.species}'s Eject Pack tried to activate, but {switch_reason}"
    
    # === SPECIAL MOVE MECHANICS (from database) ===
    special_effects = move_effect_main
    
    # Ensure perish_song is set for perish-song move (check both normalized and original move name)
    move_name_normalized = normalized_move_name or move_name.lower().replace(" ", "-").strip()
    if move_name_normalized == "perish-song" or "perish-song" in move_name_normalized:
        # Force perish_song to be True for perish-song
        special_effects["perish_song"] = True
        move_effect_main["perish_song"] = True  # Also set in move_effect_main to be safe
    
    if special_effects.get("swaps_hazards"):
        if not battle_state:
            if hasattr(user, "_last_move_failed"):
                user._last_move_failed = True
            msg += "\nBut it failed!"
        else:
            swap_labels: List[str] = []
            side_pairs = [
                ("reflect", "reflect_turns", "Reflect"),
                ("light_screen", "light_screen_turns", "Light Screen"),
                ("aurora_veil", "aurora_veil_turns", "Aurora Veil"),
                ("tailwind", "tailwind_turns", "Tailwind"),
                ("mist", "mist_turns", "Mist"),
                ("safeguard", "safeguard_turns", "Safeguard"),
                ("lucky_chant", "lucky_chant_turns", "Lucky Chant"),
            ]
            user_side_ref = locals().get("user_side")
            target_side_ref = locals().get("target_side")
            if user_side_ref is None or target_side_ref is None:
                if hasattr(user, "_last_move_failed"):
                    user._last_move_failed = True
                msg += "\nBut it failed!"
            else:
                for flag_attr, turn_attr, label in side_pairs:
                    user_flag = getattr(user_side_ref, flag_attr, False)
                    target_flag = getattr(target_side_ref, flag_attr, False)
                    user_turns = getattr(user_side_ref, turn_attr, 0)
                    target_turns = getattr(target_side_ref, turn_attr, 0)
                    if user_flag != target_flag or user_turns != target_turns:
                        setattr(user_side_ref, flag_attr, target_flag)
                        setattr(user_side_ref, turn_attr, target_turns)
                        setattr(target_side_ref, flag_attr, user_flag)
                        setattr(target_side_ref, turn_attr, user_turns)
                        if label not in swap_labels:
                            swap_labels.append(label)
                
                hazard_labels_map = {
                    "stealth_rock": "Stealth Rock",
                    "spikes": "Spikes",
                    "toxic_spikes": "Toxic Spikes",
                    "sticky_web": "Sticky Web",
                }
                user_hazards_before = user_side_ref.hazards.to_dict() if hasattr(user_side_ref, "hazards") else {}
                target_hazards_before = target_side_ref.hazards.to_dict() if hasattr(target_side_ref, "hazards") else {}
                
                if hasattr(user_side_ref, "hazards") and hasattr(target_side_ref, "hazards"):
                    user_hazards_copy = copy.deepcopy(user_side_ref.hazards)
                    target_hazards_copy = copy.deepcopy(target_side_ref.hazards)
                    user_side_ref.hazards = target_hazards_copy
                    target_side_ref.hazards = user_hazards_copy
                    user_side_ref.hazards.generation = battle_state.gen
                    target_side_ref.hazards.generation = battle_state.gen
                    
                    for key, label in hazard_labels_map.items():
                        if user_hazards_before.get(key) != target_hazards_before.get(key):
                            if label not in swap_labels:
                                swap_labels.append(label)
                
                if not swap_labels:
                    if hasattr(user, "_last_move_failed"):
                        user._last_move_failed = True
                    msg += "\nBut nothing happened!"
                else:
                    for label in swap_labels:
                        msg += f"\n{label} changed sides!"
    
    # Species-restricted moves (e.g., Hyperspace Fury)
    if move_lower == "hyperspace-fury":
        species_lower = (user.species or "").lower()
        form_lower = (getattr(user, "form", "") or "").lower()
        if "hoopa" not in species_lower or "unbound" not in (species_lower + " " + form_lower):
            user._last_move_failed = True
            return f"**{user.species}** used **{move_name}**!\nBut it failed!"

    # Moves that require a friendly target (Hold Hands, Magnetic Flux, etc.)
    if special_effects.get("requires_ally"):
        if not battle_state or target is None:
            user._last_move_failed = True
            return f"**{user.species}** used **{move_name}**!\nBut it failed!"
        user_owner = _resolve_owner_id(user)
        target_owner = _resolve_owner_id(target)
        if user_owner != target_owner or target is user or target.hp <= 0:
            user._last_move_failed = True
            return f"**{user.species}** used **{move_name}**!\nBut it failed!"

    # Magnetic Flux: boost Plus/Minus allies
    if special_effects.get("boosts_plus_minus"):
        affected: List[Mon] = []
        if battle_state:
            owner_id = _resolve_owner_id(user)
            team = battle_state.team_for(owner_id)
            for mon in team:
                if not mon or mon.hp <= 0:
                    continue
                ability_norm = normalize_ability_name(mon.ability or "")
                if ability_norm in {"plus", "minus"}:
                    affected.append(mon)
        else:
            ability_norm = normalize_ability_name(user.ability or "")
            if ability_norm in {"plus", "minus"} and user.hp > 0:
                affected.append(user)

        if not affected:
            msg += "\nBut it failed! (No Plus/Minus allies.)"
        else:
            if move_lower == "gear-up":
                boost_stats = {"atk": 1, "spa": 1}
            else:
                boost_stats = {"defn": 1, "spd": 1}
            for ally in affected:
                boost_msgs = modify_stages(ally, boost_stats, caused_by_opponent=False, field_effects=field_effects)
                for boost_msg in boost_msgs:
                    msg += f"\n{boost_msg}"

    if special_effects.get("happy_hour"):
        if battle_state:
            owner_id = _resolve_owner_id(user)
            if not hasattr(battle_state, "_happy_hour_bonus"):
                battle_state._happy_hour_bonus = {}
            battle_state._happy_hour_bonus[owner_id] = True
        msg += "\nPrize money was doubled!"

    if special_effects.get("celebration"):
        msg += "\nCongratulations!"

    if move_lower == "hold-hands" and target:
        msg += f"\n{user.species} and {target.species} feel closer than before!"

    # Leech Seed
    if special_effects.get("sets_leech_seed"):
        if not hasattr(target, 'leech_seeded') or not target.leech_seeded:
            if "Grass" in target.types:
                msg += f"\nIt doesn't affect {target.species}!"
            else:
                target.leech_seeded = True
                msg += f"\n{target.species} was seeded!"
        else:
            msg += f"\n{target.species} is already seeded!"
    
    # Ingrain
    if special_effects.get("sets_ingrain"):
        if not getattr(user, 'ingrained', False) and not getattr(user, '_ingrained', False):
            ingrain_gen = get_generation(field_effects=field_effects)
            user.ingrained = True
            user._ingrained = True
            user._ingrain_generation = ingrain_gen
            msg += f"\n{user.species} planted its roots!"
        else:
            msg += f"\nBut it failed! ({user.species} is already rooted)"
    
    # Aqua Ring
    if special_effects.get("sets_aqua_ring"):
        user.aqua_ring = True
        msg += f"\n{user.species} surrounded itself with a veil of water!"
    
    # Trapping moves (message handled in battle_flow.py to avoid duplicates)
    if special_effects.get("traps_opponent"):
        target.trapped = True
        target.trapped_by = user.species
    
    if special_effects.get("traps_both") and target and target.hp > 0 and user.hp > 0:
        user_already = getattr(user, '_jaw_lock_active', False)
        target_already = getattr(target, '_jaw_lock_active', False)
        if user_already or target_already:
            pass
        else:
            user_can_switch, _ = can_switch_out(user, target, field_effects=field_effects)
            target_can_switch, _ = can_switch_out(target, user, field_effects=field_effects)
            if user_can_switch and target_can_switch:
                user._jaw_lock_active = True
                target._jaw_lock_active = True
                user.jaw_lock_partner = target
                target.jaw_lock_partner = user
                user.trapped = True
                user.trapped_by = target.species
                target.trapped = True
                target.trapped_by = user.species
                user.trap_source = "jaw-lock"
                target.trap_source = "jaw-lock"
                msg += f"\n{user.species} and {target.species} are locked in a Jaw Lock!"
            else:
                msg += f"\nBut the trap failed to take hold!"

    if move_lower == "octolock" and target is not None and target.hp > 0:
        target_types = [t.strip().title() if t else None for t in getattr(target, "types", (None, None))]
        if "Ghost" in target_types:
            if hasattr(user, "_last_move_failed"):
                user._last_move_failed = True
            msg += f"\nIt doesn't affect {target.species}..."
        elif getattr(target, "_octolocked_by", None) is user:
            if hasattr(user, "_last_move_failed"):
                user._last_move_failed = True
            msg += "\nBut it failed!"
        else:
            if getattr(user, "_octolock_target", None) is not target and getattr(user, "_octolock_target", None) is not None:
                release_octolock(user)
            current_locker = getattr(target, "_octolocked_by", None)
            if current_locker and current_locker is not user:
                release_octolock(target)
            drop_data = dict(special_effects.get("stat_drop_each_turn", {"defn": -1, "spd": -1}))
            user._octolock_target = target
            user._octolock_stat_drop = drop_data.copy()
            user._octolock_turns = 0
            target._octolocked_by = user
            target._octolock_stat_drop = drop_data.copy()
            target._octolock_turns = 0
            target.trapped = True
            target.trap_source = "octolock"
            target.trapped_by = user.species
            msg += f"\n{target.species} became trapped by Octolock!"
    
    # Destiny Bond
    if special_effects.get("destiny_bond"):
        user.destiny_bond = True
        msg += f"\n{user.species} is trying to take its foe down with it!"
    
    # Perish Song
    # Check both special_effects and move_effect_main, and also check move name directly
    # Normalize move name for comparison (handle both "perish-song" and "Perish Song")
    move_name_normalized_check = (normalized_move_name if 'normalized_move_name' in locals() else move_name.lower().replace(" ", "-").strip()) if move_name else ""
    has_perish_song = (
        bool(special_effects.get("perish_song")) or 
        bool(move_effect_main.get("perish_song")) or
        move_name_normalized_check == "perish-song" or
        (move_name and "perish" in move_name.lower() and "song" in move_name.lower())
    )
    
    # Debug: Print if Perish Song should trigger
    if move_name and ("perish" in move_name.lower() and "song" in move_name.lower()):
        import sys
        print(f"[DEBUG Perish Song] move_name={move_name}, normalized={move_name_normalized_check}, has_perish_song={has_perish_song}, special_effects.get('perish_song')={special_effects.get('perish_song')}, move_effect_main.get('perish_song')={move_effect_main.get('perish_song')}", file=sys.stderr, flush=True)
    
    if has_perish_song:
        # Get all Pokémon on the field
        all_mons = []
        # Initialize perish_count attribute if it doesn't exist
        if not hasattr(user, 'perish_count'):
            user.perish_count = None
        if battle_state:
            try:
                p1_active = battle_state._active(battle_state.p1_id)
                p2_active = battle_state._active(battle_state.p2_id)
                if p1_active and p1_active.hp > 0:
                    all_mons.append(p1_active)
                if p2_active and p2_active.hp > 0:
                    all_mons.append(p2_active)
            except Exception:
                # Fallback to user and target if battle_state access fails
                all_mons = [user]
                if target and target.hp > 0:
                    all_mons.append(target)
        else:
            # Fallback to user and target if no battle_state
            all_mons = [user]
            if target and target.hp > 0:
                all_mons.append(target)
        
        # Get generation for Soundproof check
        generation = get_generation(battle_state=battle_state, field_effects=field_effects)
        
        affected_mons = []
        for mon in all_mons:
            # Check if Pokémon already has a perish count
            if hasattr(mon, 'perish_count') and mon.perish_count is not None:
                continue
            
            # Check Soundproof immunity
            mon_ability = normalize_ability_name(mon.ability or "")
            ability_data = get_ability_effect(mon_ability)
            has_soundproof = ability_data.get("sound_move_immunity", False)
            
            # Gen VIII+: User is not immune to their own Perish Song
            # Other Pokémon with Soundproof are still immune
            if has_soundproof:
                if generation >= 8 and mon == user:
                    # Gen VIII+: User is affected even with Soundproof
                    pass
                else:
                    # Soundproof blocks Perish Song for other Pokémon
                    continue
            
            # Set perish count to 4 (starts at 4, decreases at end of turn)
            mon.perish_count = 4
            affected_mons.append(mon)
        
        if affected_mons:
            msg += f"\n🎵 A haunting melody echoes across the battlefield... All Pokémon that hear it will faint in **4 turns**!"
        else:
            msg += "\nBut it failed!"
    
    if special_effects.get("prevents_switching_next_turn"):
        if field_effects:
            field_effects.fairy_lock_pending = True
        msg += "\nFairy energy locked down the battlefield!"

    if special_effects.get("removes_side_protection") and target_side:
        removed_effects = []
        if getattr(target_side, '_quick_guard_active', False):
            target_side._quick_guard_active = False
            removed_effects.append("Quick Guard")
        if getattr(target_side, '_wide_guard_active', False):
            target_side._wide_guard_active = False
            removed_effects.append("Wide Guard")
        if getattr(target_side, '_crafty_shield_active', False):
            target_side._crafty_shield_active = False
            removed_effects.append("Crafty Shield")
        if removed_effects:
            if len(removed_effects) == 1:
                msg += f"\n{removed_effects[0]} was nullified!"
            elif len(removed_effects) == 2:
                msg += f"\n{removed_effects[0]} and {removed_effects[1]} were nullified!"
            else:
                last = removed_effects[-1]
                prefix = ", ".join(removed_effects[:-1])
                msg += f"\n{prefix}, and {last} were nullified!"
    
    if special_effects.get("removes_fire_type"):
        current_types = list(user.types)
        if "Fire" in current_types:
            fire_index = current_types.index("Fire")
            current_types[fire_index] = None
            user.types = tuple(current_types)
            msg += f"\n{user.species} burned away its Fire typing!"
    
    if special_effects.get("prevents_sleep"):
        uproar_duration = special_effects.get("duration", 3)
        duration_range = None
        gen_specific = special_effects.get("gen_specific")
        if isinstance(gen_specific, dict):
            def _match_gen(spec: str, gen_val: int) -> bool:
                spec = (spec or "").strip()
                if not spec:
                    return False
                if spec.endswith('+'):
                    try:
                        return gen_val >= int(spec[:-1])
                    except ValueError:
                        return False
                if '-' in spec:
                    try:
                        start_s, end_s = spec.split('-', 1)
                        return int(start_s) <= gen_val <= int(end_s)
                    except ValueError:
                        return False
                try:
                    return gen_val == int(spec)
                except ValueError:
                    return False

            for spec, data in gen_specific.items():
                if not isinstance(data, dict):
                    continue
                if _match_gen(spec, generation_check):
                    if "duration" in data:
                        uproar_duration = data.get("duration", uproar_duration)
                    if "duration_range" in data:
                        duration_range = data.get("duration_range")
        if duration_range and isinstance(duration_range, (list, tuple)) and len(duration_range) == 2:
            low, high = duration_range
            try:
                low_i = int(low)
                high_i = int(high)
                if low_i <= high_i:
                    uproar_duration = random.randint(low_i, high_i)
            except ValueError:
                pass
        if field_effects:
            current_duration = getattr(field_effects, 'uproar_turns', 0)
            field_effects.uproar_turns = max(current_duration, uproar_duration)
            field_effects.uproar_source = user.species
        msg += f"\n{user.species} caused an uproar!"
    
    # === RAMPAGE MOVES (Outrage, Thrash, Petal Dance) ===
    # Check both database and move_effects.py for rampage flag
    move_secondary_data = get_move_secondary_effect(move_name)
    if special_effects.get("rampage") or move_secondary_data.get("rampage"):
        if not hasattr(user, 'rampage_move') or not user.rampage_move:
            # Start new rampage (2-3 turns, randomly)
            # Note: random is already imported at module level
            user.rampage_move = move_lower
            generation_rampage = get_generation(field_effects=field_effects)
            user._rampage_generation = generation_rampage
            
            # Thrash: Generation-specific duration
            if move_lower == "thrash":
                thrash_data = get_move_secondary_effect("thrash")
                gen_specific = thrash_data.get("gen_specific", {})
                if generation_rampage == 1:
                    # Gen I: 3-4 turns
                    user.rampage_turns_remaining = random.choice([3, 4])
                elif generation_rampage <= 4:
                    # Gen II-IV: 2-3 turns
                    user.rampage_turns_remaining = random.choice([2, 3])
                else:
                    # Gen V+: Fixed 4 turns
                    user.rampage_turns_remaining = 4
            elif move_lower == "petal-dance":
                # Petal Dance: Generation-specific duration and power
                petal_data = get_move_secondary_effect("petal-dance")
                gen_specific = petal_data.get("gen_specific", {})
                
                if generation_rampage == 1:
                    # Gen I: 3-4 turns, 70 power
                    user.rampage_turns_remaining = random.choice([3, 4])
                    user._petal_dance_power_override = 70
                elif generation_rampage <= 3:
                    # Gen II-III: 2-3 turns, 70 power
                    user.rampage_turns_remaining = random.choice([2, 3])
                    user._petal_dance_power_override = 70
                elif generation_rampage == 4:
                    # Gen IV: 2-3 turns, 90 power
                    user.rampage_turns_remaining = random.choice([2, 3])
                    user._petal_dance_power_override = 90
                else:
                    # Gen V+: Fixed 4 turns, 120 power
                    user.rampage_turns_remaining = 4
                    user._petal_dance_power_override = 120
            else:
                # Default for other rampage moves (Outrage)
                user.rampage_turns_remaining = random.choice([2, 3])
            if hasattr(user, '_rampage_disrupted'):
                delattr(user, '_rampage_disrupted')
            if hasattr(user, '_rampage_disrupted_final_turn'):
                delattr(user, '_rampage_disrupted_final_turn')
            if hasattr(user, '_rampage_disrupted_reason'):
                delattr(user, '_rampage_disrupted_reason')
            msg += f"\n**{user.species}** began rampaging!"
            
            # Outrage: Generation-specific power (Gen II-III: 90, Gen IV+: 120)
            if move_lower == "outrage":
                gen_outrage = get_generation(field_effects=field_effects)
                if gen_outrage <= 3:
                    user._outrage_power_override = 90
                else:
                    user._outrage_power_override = 120
        # If rampage ends this turn (will be decremented in end_of_turn_cleanup)
        # The confusion will be applied when rampage_turns_remaining hits 0
    
    # === RAGE MECHANICS ===
    # Gen I: Continuous move that never stops (like rampage but different mechanics)
    # Gen II: Rage counter multiplier (damage = base * counter, counter increases when hit)
    # Gen III+: Attack boost when hit (each hit increases Attack by 1 stage)
    if move_lower == "rage":
        generation_rage = get_generation(field_effects=field_effects)
        
        if generation_rage == 1:
            # Gen I: Continuous move that never stops until KO or battle ends
            # PP is only deducted on first turn, Attack builds when damaged
            if not hasattr(user, '_rage_active') or not user._rage_active:
                user._rage_active = True
                user._rage_gen1_attack_builds = 0  # Track Attack builds
                msg += f"\n**{user.species}** is in a rage!"
        elif generation_rage == 2:
            # Gen II: Rage counter system (damage multiplier)
            if not hasattr(user, '_rage_counter'):
                user._rage_counter = 1  # Starts at 1
            # Rage counter increases when user is damaged (handled in damage calculation)
        elif generation_rage >= 3:
            # Gen III+: Attack boost when hit
            if not hasattr(user, '_rage_attack_boost_active'):
                user._rage_attack_boost_active = True
            # Attack boost happens when user is hit (handled in reactive abilities)
    
    # Knock Off (remove opponent's item)
    if special_effects.get("knock_off") and target.item:
        knocked_item = target.item
        target.item = None
        msg += f"\n{user.species} knocked off {target.species}'s {knocked_item}!"
    
    # If target lost all remaining HP
    if target.hp <= 0 and old_hp > 0:
        msg += f"\n{target.species} lost the rest of its health!"
        
        # Destiny Bond check - if target had Destiny Bond active
        if hasattr(target, 'destiny_bond') and target.destiny_bond:
            user.hp = 0
            msg += f"\n{user.species} was taken down by Destiny Bond!"
        
        # === BATTLE BOND: Transform Greninja after KO ===
        success, transform_msg = apply_battle_bond_transform(user)
        if success:
            msg += f"\n{transform_msg}"
    
    # === TRACK DAMAGE FOR COUNTER/MIRROR COAT/METAL BURST ===
    # Track damage even if it hit substitute (Gen I: substitute damage can be countered)
    # Use drain_base_damage which includes substitute damage
    # Also track even if damage is 0 (for Gen V+ Counter mechanics)
    # Ensure drain_base_damage is set (it should be set earlier in the function)
    if 'drain_base_damage' not in locals():
        drain_base_damage = dmg
    damage_to_track = drain_base_damage if drain_base_damage > 0 else dmg
    # Track category and move info even if damage is 0 (for Gen V+ Counter)
    # Always track if we have move data (even for 0 damage)
    move_data = get_move(move_name, generation=generation_for_move_data, battle_state=battle_state)
    # Track damage for Counter/Mirror Coat - always track damage when a move is used
    # Always track damage (even if 0 damage for Gen V+ Counter mechanics)
    # This should always execute since damage_to_track is always >= 0
    if True:  # Always track damage for Counter/Mirror Coat mechanics
        category = move_data.get("damage_class", "physical") if move_data else "physical"
        if normalized_move.startswith("hidden-power"):
            gen_hp_store = get_generation(field_effects=field_effects)
            category = "special" if gen_hp_store >= 4 else "physical"
        # Always track damage (even if 0) for Counter mechanics
        target._last_damage_taken = damage_to_track
        target._last_damage_category = category
        # Store last move name that hit (for Counter/Mirror Coat Gen I mechanics)
        target._last_move_that_hit = move_name
        # Store last move type that hit (for Counter Gen I type checking)
        if meta.get("type"):
            target._last_move_type_hit_by = meta["type"].strip().title()
        elif move_data:
            target._last_move_type_hit_by = move_data.get("type", "Normal").strip().title()
        # Track substitute flag if damage hit substitute (for Counter Gen II mechanics)
        if not hasattr(target, '_last_damage_hit_substitute'):
            target._last_damage_hit_substitute = False
        # Only set flag if substitute was hit and not bypassed
        if substitute_broken or (target_had_substitute and not substitute_bypassed and dmg == 0):
            target._last_damage_hit_substitute = True
        else:
            target._last_damage_hit_substitute = False
        # Accumulate Bide damage if active
        if hasattr(target, '_bide_active') and getattr(target, '_bide_active', False):
            if not hasattr(target, '_bide_damage'):
                target._bide_damage = 0
            target._bide_damage += damage_to_track
            target._bide_last_attacker = user
    
    # === EMERGENCY EXIT / WIMP OUT: Force switch if HP drops below 50% ===
    # Only activates from actual move damage (not self-inflicted, not HP reduction from other sources)
    # Does NOT activate if move is affected by Sheer Force
    # Only activates if HP went from >=50% to <50%
    if dmg > 0 and target.hp > 0:  # Target survived and took actual damage
        target_ability_norm = normalize_ability_name(target.ability or "")
        target_ability_data = get_ability_effect(target_ability_norm)
        
        # Check if attacker has Sheer Force (negates all secondary effects)
        user_ability_norm = normalize_ability_name(user.ability or "")
        user_ability_data = get_ability_effect(user_ability_norm)
        has_sheer_force = user_ability_data.get("removes_secondary_effects", False)
        
        # === EMERGENCY EXIT / WIMP OUT ===
        if target_ability_data.get("switches_out_at_half_hp"):
            if not has_sheer_force:
                # Check if HP dropped below 50% from AT OR ABOVE 50%
                hp_before_percent = (old_hp / target.max_hp) * 100
                hp_after_percent = (target.hp / target.max_hp) * 100
                
                # Must go from >=50% to <50%
                if hp_before_percent >= 50.0 and hp_after_percent < 50.0:
                    # Mark for emergency switch (battle_state will handle the actual switch)
                    target._emergency_exit_triggered = True
                    ability_name = (target.ability or target_ability_norm).replace("-", " ").title()
                    msg += f"\n**{target.species}'s {ability_name}!**"
        
        # === BERSERK: +1 SpA when HP drops below 50% ===
        # "Each time the HP of a Pokémon with Berserk is reduced below half due to being targeted by a damaging move"
        # Does NOT activate from indirect damage (status, weather, Leech Seed, etc.)
        # Does NOT activate if move is affected by Sheer Force
        # Activates EACH TIME HP crosses the 50% threshold (not just once)
        if target_ability_data.get("spa_boost_at_half_hp"):
            if not has_sheer_force:
                # Check if HP dropped below 50% from AT OR ABOVE 50%
                hp_before_percent = (old_hp / target.max_hp) * 100
                hp_after_percent = (target.hp / target.max_hp) * 100
                
                # Must go from >=50% to <50%
                if hp_before_percent >= 50.0 and hp_after_percent < 50.0:
                    old_stage = target.stages.get("spa", 0)
                    if old_stage < 6:
                        target.stages["spa"] = old_stage + 1
                        ability_name = (target.ability or target_ability_norm).replace("-", " ").title()
                        msg += f"\n**{target.species}'s {ability_name} raised its Sp. Atk!**"
    
    # === ON-HIT REACTIVE ABILITIES (Magician, Pickpocket, Anger Point, etc.) ===
    # Determine if move was contact from move data
    move_data = load_move(move_name, generation=generation_for_move_data, battle_state=battle_state)
    is_contact_move = bool(move_data.get("contact", 0)) if move_data else False
    
    # Build trigger data - include whether Substitute blocked the hit
    # Some abilities (like Anger Point in Gen 4) activate even through Substitute
    substitute_blocked = (hasattr(target, 'substitute') and target.substitute and dmg == 0 and not substitute_bypassed)
    
    trigger_data = {
        "damage": dmg,
        "is_contact": is_contact_move,
        "is_crit": meta.get("crit", False),
        "hp_before_damage": old_hp,
        "substitute_blocked": substitute_blocked,  # New flag for generation-specific Anger Point
        "substitute_broken": substitute_broken
    }
    
    # Apply reactive abilities - some only trigger if damage was dealt, others (Anger Point Gen 4) trigger through Substitute
    ability_msgs = apply_on_hit_reactive_abilities(user, target, trigger_data, battle_state)
    for ability_msg in ability_msgs:
        msg += f"\n{ability_msg}"
    
    # === ROWAP BERRY / JABOCA BERRY: Deal damage to attacker ===
    # Rowap activates on special moves, Jaboca on physical moves
    if dmg > 0 and target.item and user.hp > 0 and not substitute_blocked:
        target_item_data = get_item_effect(normalize_item_name(target.item))
        
        if "retaliation_damage" in target_item_data:
            retaliation_category = target_item_data.get("retaliation_category")
            move_category = meta.get("category", "physical")
            
            # Check if berry activates based on move category
            if retaliation_category == move_category:
                # Check for Ripen ability (doubles berry effects)
                retaliation_mult = 1.0
                target_ability = normalize_ability_name(target.ability or "")
                target_ability_data = get_ability_effect(target_ability)
                if target_ability_data.get("berry_effect_mult"):
                    retaliation_mult = target_ability_data["berry_effect_mult"]  # 2.0 for Ripen
                
                # Check for Magic Guard (blocks indirect damage)
                user_ability = normalize_ability_name(user.ability or "")
                user_ability_data = get_ability_effect(user_ability)
                if not user_ability_data.get("prevents_indirect_damage"):
                    retaliation_damage = int(user.max_hp * target_item_data["retaliation_damage"] * retaliation_mult)
                    retaliation_damage = max(1, retaliation_damage)
                    user.hp = max(0, user.hp - retaliation_damage)
                    
                    berry_name = (target.item or "").replace('-', ' ').title() if target.item else "berry"
                    msg += f"\n{user.species} was hurt by {target.species}'s {berry_name}! (-{retaliation_damage} HP)"
                    
                    if user.hp <= 0:
                        msg += f"\n{user.species} fainted!"
                
                # Consume berry
                target.item = None
    
    if spectral_thief_msgs:
        for st_msg in spectral_thief_msgs:
            msg += f"\n{st_msg}"

    # Prepend Protean/Libero message if it occurred
    if protean_msg:
        msg = protean_msg + msg
    
    # === ROLLOUT/ICE BALL: Track successful usage ===
    is_rollout_move = normalized_move in ROLLOUT_MOVES
    if is_rollout_move:
        existing_rollout_move = getattr(user, 'rollout_move', None)
        rollout_state_active = existing_rollout_move == normalized_move and getattr(user, 'rollout_turns_remaining', 0) > 0
        rollout_stage_current = max(1, min(getattr(user, '_rollout_stage', 1), 5)) if rollout_state_active else 1
        handle_rollout_success(
            user,
            normalized_move,
            is_rollout_move,
            rollout_state_active,
            rollout_stage_current,
        )
    
    if mind_blown_hp_loss > 0:
        user_name = format_species_name(user.species)
        if getattr(user, 'shiny', False):
            user_name = f"★ {user_name}"
        msg += f"\n**{user_name}** was hurt by Mind Blown! (-{mind_blown_hp_loss} HP)"
        faint_line = f"**{user_name}** fainted!"
        if mind_blown_fainted and faint_line not in msg:
            msg += f"\n{faint_line}"
    
    return msg


# ============================================================================
# Form Change Abilities
# ============================================================================

def check_form_change(mon: Mon, triggered_by: str = "turn_start", move_used: Optional[str] = None, 
                     field_effects: Optional[Dict[str, Any]] = None, battle_state: Any = None) -> Optional[str]:
    """
    Check if a Pokémon should change form based on its ability and conditions.
    Returns a message if form changed, None otherwise.
    
    triggered_by can be: "turn_start", "before_move", "after_damage", "after_ko"
    
    NOTE: This function only changes mon.form and mon.types. It does NOT modify
    mon.stages (stat boosts/drops) or mon.stats (base calculated stats). Stat stages
    are preserved and will be applied when calculating effective stats via get_effective_stat.
    """
    ability = normalize_ability_name(mon.ability or "")
    species_lower = mon.species.lower()
    msg = ""
    
    # Initialize form if not set
    if mon.form is None:
        # Set default forms
        if "aegislash" in species_lower:
            mon.form = "shield"
        elif "darmanitan" in species_lower:
            mon.form = "standard"
        elif "wishiwashi" in species_lower:
            # Schooling: check both level AND HP percentage
            hp_percent = (mon.hp / mon.max_hp) if mon.max_hp > 0 else 0
            if mon.level >= 20 and hp_percent > 0.25:
                mon.form = "school"
            else:
                mon.form = "solo"
        elif "minior" in species_lower:
            mon.form = "meteor"
        elif "mimikyu" in species_lower:
            mon.form = "disguised"
    
    # === Stance Change (Aegislash) ===
    if ability == "stance-change" and "aegislash" in species_lower:
        if triggered_by == "before_move" and move_used:
            # Load move to check if it's offensive
            gen = getattr(battle_state, "gen", None) if battle_state else None
            mv = load_move(move_used, generation=gen, battle_state=battle_state)
            if mv:
                move_name_lower = move_used.lower().replace(" ", "-")
                
                # King's Shield switches to Shield Forme
                if move_name_lower in ["kings-shield", "king-s-shield", "king's-shield"]:
                    if mon.form != "shield":
                        mon.form = "shield"
                        msg = f"{mon.species} changed to Shield Forme!"
                # Damaging moves switch to Blade Forme
                # Check both 'damage_class' and 'category' fields, and 'power' field
                else:
                    damage_class = (mv.get("damage_class") or mv.get("category") or "").lower()
                    power = mv.get("power") or 0
                    
                    if damage_class in ["physical", "special"] and power > 0:
                        if mon.form != "blade":
                            mon.form = "blade"
                            msg = f"{mon.species} changed to Blade Forme!"
    
    # === Zen Mode (Darmanitan) ===
    elif ability == "zen-mode" and "darmanitan" in species_lower:
        if triggered_by in ["turn_start", "after_damage"]:
            hp_percent = (mon.hp / mon.max_hp) if mon.max_hp > 0 else 0
            if hp_percent < 0.5 and mon.form != "zen":
                mon.form = "zen"
                # Change typing to Fire/Psychic in Zen Mode
                if mon.types[0] == "Fire":
                    mon.types = ("Fire", "Psychic")
                msg = f"{mon.species} calmed down into Zen Mode!"
            elif hp_percent >= 0.5 and mon.form != "standard":
                mon.form = "standard"
                # Revert typing
                if "galar" in species_lower:
                    mon.types = ("Ice", None)
                else:
                    mon.types = ("Fire", None)
                msg = f"{mon.species} returned to Standard Mode!"
    
    # === Schooling (Wishiwashi) ===
    elif ability == "schooling" and "wishiwashi" in species_lower:
        # Schooling checks: on switch-in, at turn start, after damage, and at end of turn
        if triggered_by in ["on_switch_in", "turn_start", "after_damage", "end_of_turn"]:
            hp_percent = (mon.hp / mon.max_hp) if mon.max_hp > 0 else 0
            # Change to School Form if level >= 20 and HP > 25%
            if mon.level >= 20 and hp_percent > 0.25:
                # Always check and set form, even if already set (ensures it's correct)
                if mon.form != "school":
                    mon.form = "school"
                    msg = f"{mon.species} formed a school!"
                # On switch-in, always show message if form is already correct (for visual feedback)
                elif triggered_by == "on_switch_in":
                    msg = f"{mon.species} formed a school!"
            # Change to Solo Form if level < 20 or HP <= 25%
            else:
                # Always check and set form, even if already set (ensures it's correct)
                if not mon.form or mon.form != "solo":
                    mon.form = "solo"
                    msg = f"{mon.species}'s school dispersed!"
                # On switch-in, always show message if form is already correct (for visual feedback)
                elif triggered_by == "on_switch_in":
                    msg = f"{mon.species}'s school dispersed!"
    
    # === Shields Down (Minior) ===
    elif ability == "shields-down" and "minior" in species_lower:
        if triggered_by in ["turn_start", "after_damage"]:
            hp_percent = (mon.hp / mon.max_hp) if mon.max_hp > 0 else 0
            if hp_percent < 0.5 and "meteor" in (mon.form or ""):
                # Change to core form (extract color from current form if present)
                color = ""
                if "-" in (mon.form or ""):
                    parts = mon.form.split("-")
                    if len(parts) > 1:
                        color = parts[0]
                mon.form = color if color else "red"  # Default to red core
                msg = f"{mon.species}'s shell broke!"
            elif hp_percent >= 0.5 and "meteor" not in (mon.form or ""):
                # Revert to meteor form
                color = mon.form
                mon.form = f"{color}-meteor" if color else "meteor"
                msg = f"{mon.species} formed a new meteor shell!"
    
    # === Disguise (Mimikyu) ===
    elif ability == "disguise" and "mimikyu" in species_lower:
        # Disguise is handled in the damage function, but we track the form here
        if triggered_by == "after_damage" and mon._disguise_broken and mon.form != "busted":
            mon.form = "busted"
            msg = f"{mon.species}'s disguise was busted!"
    
    # === Forecast (Castform) ===
    elif ability == "forecast" and "castform" in species_lower:
        if triggered_by in ["turn_start", "after_damage"] and field_effects:
            weather = getattr(field_effects, 'weather', None)
            if weather == "sun":
                if mon.form != "sunny":
                    mon.form = "sunny"
                    mon.types = ("Fire", None)
                    msg = f"{mon.species} transformed into Sunny Form!"
            elif weather == "rain":
                if mon.form != "rainy":
                    mon.form = "rainy"
                    mon.types = ("Water", None)
                    msg = f"{mon.species} transformed into Rainy Form!"
            elif weather in ["hail", "snow"]:
                if mon.form != "snowy":
                    mon.form = "snowy"
                    mon.types = ("Ice", None)
                    msg = f"{mon.species} transformed into Snowy Form!"
            elif not weather or weather == "clear":
                if mon.form != "normal":
                    mon.form = "normal"
                    mon.types = ("Normal", None)
                    msg = f"{mon.species} returned to Normal Form!"
    
    # === Flower Gift (Cherrim) ===
    elif ability == "flower-gift" and "cherrim" in species_lower:
        if triggered_by in ["turn_start", "after_damage"] and field_effects:
            weather = getattr(field_effects, 'weather', None)
            if weather == "sun":
                if mon.form != "sunshine":
                    mon.form = "sunshine"
                    msg = f"{mon.species} transformed into Sunshine Form!"
            else:
                if mon.form != "overcast":
                    mon.form = "overcast"
                    msg = f"{mon.species} returned to Overcast Form!"
    
    # === Hunger Switch (Morpeko) ===
    elif ability == "hunger-switch" and "morpeko" in species_lower:
        if triggered_by == "turn_start":
            # Alternate between Full Belly and Hangry each turn
            if mon.form == "full-belly" or not mon.form:
                mon.form = "hangry"
                msg = f"{mon.species} became Hangry Mode!"
            else:
                mon.form = "full-belly"
                msg = f"{mon.species} returned to Full Belly Mode!"
    
    # === Ice Face (Eiscue) ===
    elif ability == "ice-face" and "eiscue" in species_lower:
        # Ice Face is handled in damage function (blocks physical moves)
        # Here we handle regeneration in hail/snow
        if triggered_by == "turn_start" and field_effects:
            weather = getattr(field_effects, 'weather', None)
            if weather in ["hail", "snow"] and mon.form == "noice":
                mon.form = "ice"
                msg = f"{mon.species}'s ice face was restored!"
    
    # === Battle Bond (Greninja) ===
    elif ability == "battle-bond" and "greninja" in species_lower:
        if triggered_by == "after_ko" and mon.form != "ash":
            mon.form = "ash"
            msg = f"{mon.species} became Ash-Greninja!"
    
    return msg if msg else None


def check_item_based_forme_change(mon, triggered_by="turn_start") -> Optional[str]:
    """
    Check and apply item-based forme changes for held items only.
    
    Note: Permanent transformations (Rotom, Deoxys, Shaymin, Necrozma, Kyurem, Calyrex, 
    Hoopa, Forces of Nature) are handled via the /transform command.
    
    This function only handles Pokémon that MUST hold an item to maintain their forme:
    - Giratina (Griseous Orb)
    - Arceus (Plates)
    - Silvally (Memories)
    - Zacian/Zamazenta (Rusted Sword/Shield)
    - Dialga/Palkia (Adamant/Lustrous Orbs)
    
    Special case: Shaymin Sky reverts to Land when frozen (kept here for battle logic)
    
    NOTE: This function only changes mon.form and mon.types. It does NOT modify
    mon.stages (stat boosts/drops) or mon.stats (base calculated stats). Stat stages
    are preserved and will be applied when calculating effective stats via get_effective_stat.
    
    Returns a message if a forme change occurred
    """
    if not mon:
        return None
    
    species_lower = mon.species.lower()
    item_lower = mon.item.lower().replace(" ", "-") if mon.item else ""
    msg = None
    
    # === SHAYMIN SKY FORME - Frozen Revert Logic ===
    # Shaymin transformations are handled by /transform, but it reverts when frozen in battle
    if "shaymin" in species_lower:
        if mon.status == "frz" and mon.form == "sky":
            mon.form = "land"
            mon.types = ["Grass"]
            msg = f"{mon.species} reverted to Land Forme due to being frozen!"
            return msg
    
    # For held-item formes, item is required
    if not mon.item:
        return None
    
    # === GIRATINA ORIGIN FORME (Griseous Orb) ===
    if "giratina" in species_lower:
        if "griseous" in item_lower or "griseous-orb" in item_lower:
            if mon.form != "origin":
                mon.form = "origin"
                msg = f"{mon.species} transformed into Origin Forme!"
        else:
            if mon.form == "origin":
                mon.form = "altered"
                msg = f"{mon.species} returned to Altered Forme!"
    
    # === SHAYMIN SKY FORME (Gracidea) ===
    elif "shaymin" in species_lower:
        # Sky Forme only during day and not frozen
        if "gracidea" in item_lower:
            if mon.status != "frz" and mon.form != "sky":  # TODO: Add day/night check
                mon.form = "sky"
                mon.types = ["Grass", "Flying"]
                msg = f"{mon.species} transformed into Sky Forme!"
        else:
            if mon.form == "sky":
                mon.form = "land"
                mon.types = ["Grass"]
                msg = f"{mon.species} returned to Land Forme!"
        
        # Revert if frozen
        if mon.status == "frz" and mon.form == "sky":
            mon.form = "land"
            mon.types = ["Grass"]
            msg = f"{mon.species} reverted to Land Forme due to being frozen!"
    
    # === ARCEUS TYPE FORME (Plates) ===
    elif "arceus" in species_lower:
        plate_types = {
            "draco-plate": "Dragon", "dread-plate": "Dark", "earth-plate": "Ground",
            "fist-plate": "Fighting", "flame-plate": "Fire", "icicle-plate": "Ice",
            "insect-plate": "Bug", "iron-plate": "Steel", "meadow-plate": "Grass",
            "mind-plate": "Psychic", "pixie-plate": "Fairy", "sky-plate": "Flying",
            "splash-plate": "Water", "spooky-plate": "Ghost", "stone-plate": "Rock",
            "toxic-plate": "Poison", "zap-plate": "Electric"
        }
        
        for plate, ptype in plate_types.items():
            if plate in item_lower:
                if mon.types[0] != ptype:
                    mon.types = [ptype]
                    msg = f"{mon.species} became {ptype}-type!"
                return msg
        
        # No plate = Normal type
        if mon.types[0] != "Normal":
            mon.types = ["Normal"]
            msg = f"{mon.species} returned to Normal-type!"
    
    # === SILVALLY TYPE FORME (Memories) ===
    elif "silvally" in species_lower:
        memory_types = {
            "bug-memory": "Bug", "dark-memory": "Dark", "dragon-memory": "Dragon",
            "electric-memory": "Electric", "fairy-memory": "Fairy", "fighting-memory": "Fighting",
            "fire-memory": "Fire", "flying-memory": "Flying", "ghost-memory": "Ghost",
            "grass-memory": "Grass", "ground-memory": "Ground", "ice-memory": "Ice",
            "poison-memory": "Poison", "psychic-memory": "Psychic", "rock-memory": "Rock",
            "steel-memory": "Steel", "water-memory": "Water"
        }
        
        for memory, mtype in memory_types.items():
            if memory in item_lower:
                if mon.types[0] != mtype:
                    mon.types = [mtype]
                    msg = f"{mon.species} became {mtype}-type!"
                return msg
        
        # No memory = Normal type
        if mon.types[0] != "Normal":
            mon.types = ["Normal"]
            msg = f"{mon.species} returned to Normal-type!"
    
    # === ZACIAN/ZAMAZENTA CROWNED FORMS (Rusted Sword/Shield) ===
    elif "zacian" in species_lower:
        if "rusted-sword" in item_lower:
            if mon.form != "crowned":
                mon.form = "crowned"
                mon.types = ["Fairy", "Steel"]
                msg = f"{mon.species} became Crowned Sword!"
                # Replace Iron Head with Behemoth Blade if present
                mon.moves = ["behemoth-blade" if m.lower().replace(" ", "-") == "iron-head" else m for m in mon.moves]
        else:
            if mon.form == "crowned":
                mon.form = None
                mon.types = ["Fairy"]
                msg = f"{mon.species} lost its crowned form!"
    
    elif "zamazenta" in species_lower:
        if "rusted-shield" in item_lower:
            if mon.form != "crowned":
                mon.form = "crowned"
                mon.types = ["Fighting", "Steel"]
                msg = f"{mon.species} became Crowned Shield!"
                # Replace Iron Head with Behemoth Bash if present
                mon.moves = ["behemoth-bash" if m.lower().replace(" ", "-") == "iron-head" else m for m in mon.moves]
        else:
            if mon.form == "crowned":
                mon.form = None
                mon.types = ["Fighting"]
                msg = f"{mon.species} lost its crowned form!"

    # === PRIMAL REVERSION (Kyogre/Groudon with Blue/Red Orb) ===
    elif "kyogre" in species_lower and ("blue-orb" in item_lower or "blue orb" in item_lower):
        if mon.form != "primal":
            mon.form = "primal"
            msg = f"{mon.species} transformed into Primal Kyogre!"
    elif "groudon" in species_lower and ("red-orb" in item_lower or "red orb" in item_lower):
        if mon.form != "primal":
            mon.form = "primal"
            msg = f"{mon.species} transformed into Primal Groudon!"

    # === OGERPON MASK FORMS ===
    elif "ogerpon" in species_lower:
        mask_to_form = {
            "cornerstone-mask": "cornerstone",
            "wellspring-mask": "wellspring",
            "hearthflame-mask": "hearthflame",
            "teal-mask": "teal",
        }
        for key, form_key in mask_to_form.items():
            if key in item_lower:
                if mon.form != form_key:
                    mon.form = form_key
                    msg = f"{mon.species} donned the {form_key.title()}!"
                break
    
    # === DIALGA/PALKIA ORIGIN FORMS (Adamant/Lustrous Orbs) ===
    elif "dialga" in species_lower:
        if "adamant" in item_lower or "adamant-orb" in item_lower:
            if mon.form != "origin":
                mon.form = "origin"
                msg = f"{mon.species} transformed into Origin Forme!"
        else:
            if mon.form == "origin":
                mon.form = None
                msg = f"{mon.species} returned to its normal forme!"
    
    elif "palkia" in species_lower:
        if "lustrous" in item_lower or "lustrous-orb" in item_lower:
            if mon.form != "origin":
                mon.form = "origin"
                msg = f"{mon.species} transformed into Origin Forme!"
        else:
            if mon.form == "origin":
                mon.form = None
                msg = f"{mon.species} returned to its normal forme!"
    
    return msg


def _get_form_stats_from_db(species_name: str, form_key: str) -> Optional[Dict[str, int]]:
    """
    Load form-specific stats from the database.
    Returns a dict with keys: attack, defense, special_attack, special_defense, speed
    or None if form not found.
    Uses db_cache (pokedex_forms) when available, then DB.
    """
    species_lower = species_name.lower()
    if species_lower in ["missing n0", "missing no", "missing no.", "missingno", "missingno.", "missing n0.", "missing no."]:
        return None
    form_lower = form_key.lower() if form_key else ""

    global _POKEDEX_FORMS_TABLE_AVAILABLE
    try:
        try:
            from lib import db_cache
        except ImportError:
            db_cache = None
        if db_cache:
            forms = db_cache.get_cached_pokedex_forms()
            if forms:
                for r in forms:
                    sn = (r.get("species_name") or "").strip().lower()
                    fk = (r.get("form_key") or "").strip().lower()
                    if sn == species_lower and fk == form_lower:
                        raw = r.get("stats")
                        if raw is None:
                            return None
                        if isinstance(raw, dict):
                            return raw
                        if isinstance(raw, str):
                            return json.loads(raw)
                        return None
                # no matching row in cache; fall through to DB

        if _POKEDEX_FORMS_TABLE_AVAILABLE is False:
            return None
        from .db_pool import get_connection
        with get_connection() as conn:
            cursor = conn.execute(
                "SELECT stats FROM pokedex_forms WHERE species_name = ? AND form_key = ?",
                (species_lower, form_lower)
            )
            row = cursor.fetchone()
        if row and row[0]:
            return json.loads(row[0])
        return None
    except Exception as e:
        msg = str(e or "").lower()
        if (
            ("no such table" in msg and "pokedex_forms" in msg)
            or ("undefined table" in msg and "pokedex_forms" in msg)
            or ("relation" in msg and "pokedex_forms" in msg and "does not exist" in msg)
        ):
            _POKEDEX_FORMS_TABLE_AVAILABLE = False
            return None
        print(f"[Form Stats] Error loading form stats for {species_name}-{form_key}: {e}")
        return None


def apply_form_stat_modifiers(mon: Mon) -> Dict[str, float]:
    """
    Get stat multipliers based on current form by loading from database.
    Returns a dict with keys: atk, defn, spa, spd, spe
    """
    # Default: no modifications
    mods = {"atk": 1.0, "defn": 1.0, "spa": 1.0, "spd": 1.0, "spe": 1.0}
    
    # MissingNo works independently - stats are rolled at battle start, not stored in database
    species_lower = mon.species.lower()
    if species_lower in ["missing n0", "missing no", "missing no.", "missingno", "missingno.", "missing n0.", "missing no."]:
        return mods
    
    # If no form or form is default, no modification needed
    if not mon.form or mon.form in ["normal", "default"]:
        return mods
    
    # Load form stats from database
    form_stats = _get_form_stats_from_db(mon.species, mon.form)
    if not form_stats:
        return mods
    
    # Calculate multipliers by comparing form stats to mon's base stats
    # mon.stats contains the default form's stats
    if mon.stats.get("atk") and form_stats.get("attack"):
        mods["atk"] = form_stats["attack"] / mon.stats["atk"]
    if mon.stats.get("defn") and form_stats.get("defense"):
        mods["defn"] = form_stats["defense"] / mon.stats["defn"]
    if mon.stats.get("spa") and form_stats.get("special_attack"):
        mods["spa"] = form_stats["special_attack"] / mon.stats["spa"]
    if mon.stats.get("spd") and form_stats.get("special_defense"):
        mods["spd"] = form_stats["special_defense"] / mon.stats["spd"]
    if mon.stats.get("spe") and form_stats.get("speed"):
        mods["spe"] = form_stats["speed"] / mon.stats["spe"]
    
    return mods
