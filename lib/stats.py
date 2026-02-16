# lib/stats.py
from __future__ import annotations
import random
import math
from typing import Dict, Tuple, Optional

# --- Nature table (plus, minus). None=None means neutral 1.0 ---
# keys use lowercase
NATURE_PLUS_MINUS: Dict[str, Tuple[Optional[str], Optional[str]]] = {
    "hardy": (None, None),   "docile": (None, None),  "bashful": (None, None),
    "quirky": (None, None),  "serious": (None, None),

    "lonely": ("attack", "defense"),
    "brave": ("attack", "speed"),
    "adamant": ("attack", "special_attack"),
    "naughty": ("attack", "special_defense"),

    "bold": ("defense", "attack"),
    "relaxed": ("defense", "speed"),
    "impish": ("defense", "special_attack"),
    "lax": ("defense", "special_defense"),

    "timid": ("speed", "attack"),
    "hasty": ("speed", "defense"),
    "jolly": ("speed", "special_attack"),
    "naive": ("speed", "special_defense"),

    "modest": ("special_attack", "attack"),
    "mild": ("special_attack", "defense"),
    "quiet": ("special_attack", "speed"),
    "rash": ("special_attack", "special_defense"),

    "calm": ("special_defense", "attack"),
    "gentle": ("special_defense", "defense"),
    "sassy": ("special_defense", "speed"),
    "careful": ("special_defense", "special_attack"),
}

STAT_KEYS = ["hp", "attack", "defense", "special_attack", "special_defense", "speed"]

def pick_random_nature() -> str:
    return random.choice(list(NATURE_PLUS_MINUS.keys()))

def nature_multipliers(nature: str) -> Dict[str, float]:
    nature = nature.lower()
    plus, minus = NATURE_PLUS_MINUS.get(nature, (None, None))
    mult = {k: 1.0 for k in STAT_KEYS if k != "hp"}  # HP has no nature
    if plus and plus in mult:  mult[plus]  = 1.1
    if minus and minus in mult: mult[minus] = 0.9
    return mult

def roll_ivs(perfect_count: int = 0) -> Dict[str, int]:
    """Return IVs (0..31) dict; can force N perfect 31 IVs."""
    ivs = {k: random.randint(0, 31) for k in STAT_KEYS}
    perfect_count = max(0, min(perfect_count, 6))
    if perfect_count:
        picks = random.sample(STAT_KEYS, k=perfect_count)
        for k in picks:
            ivs[k] = 31
    return ivs

def calc_hp(base: int, iv: int, ev: int, level: int) -> int:
    """HP stat using Generation III onward formula only.
    HP = floor( ( (2×Base + IV + floor(EV/4)) × Level ) / 100 ) + Level + 10.
    Shedinja (HP always 1) is a special case and must be overridden by the caller."""
    return math.floor(((2*base + iv + (ev // 4)) * level) / 100) + level + 10

def calc_other(base: int, iv: int, ev: int, level: int, nature_mult: float) -> int:
    """Other stats (Attack, Defense, SpA, SpD, Speed) using Generation III onward formula only.
    OtherStat = floor( ( floor( (2×Base + IV + floor(EV/4)) × Level / 100 ) + 5 ) × Nature ).
    Nature: 1.1 boost, 1.0 neutral, 0.9 hinder."""
    core = math.floor(((2*base + iv + (ev // 4)) * level) / 100) + 5
    return math.floor(core * nature_mult)

def calc_all_stats(base_stats: Dict[str, int],
                   ivs: Dict[str, int],
                   evs: Dict[str, int],
                   level: int,
                   nature: str) -> Dict[str, int]:
    """Return final stats for level using Generation III onward formulas only (not Gen I-II)."""
    nmult = nature_multipliers(nature)
    out = {}
    out["hp"] = calc_hp(base_stats["hp"], ivs["hp"], evs.get("hp", 0), level)
    for k in ("attack", "defense", "special_attack", "special_defense", "speed"):
        out[k] = calc_other(base_stats[k], ivs[k], evs.get(k, 0), level, nmult.get(k, 1.0))
    return out

DEFAULT_HA_RATE = 0.10

def choose_ability(abilities, ha_rate: float = DEFAULT_HA_RATE) -> str | None:
    """
    abilities can be list[dict] ({"name": str, "is_hidden": bool}) or list[str] (treated as visible).
    Rules:
      - Hidden ability chosen with probability ha_rate (only if present).
      - Otherwise choose uniformly among visible abilities.
    This yields:
      2 normals, no HA -> 50/50
      2 normals + HA (ha_rate=0.10) -> 45/45/10
      1 normal + HA (ha_rate=0.10) -> 90/10
      1 normal, no HA -> 100
    """
    visible, hidden = [], []
    for a in (abilities or []):
        if isinstance(a, dict):
            name = (a.get("name") or "").strip().lower().replace(" ", "-")
            if not name:
                continue
            (hidden if a.get("is_hidden") else visible).append(name)
        else:
            name = str(a).strip().lower().replace(" ", "-")
            if name:
                visible.append(name)

    # If no visibles at all, fall back to hidden or None
    if not visible and hidden:
        return random.choice(hidden)
    if not visible and not hidden:
        return None

    # Hidden roll
    if hidden and ha_rate > 0.0 and random.random() < ha_rate:
        return random.choice(hidden)

    # Otherwise: uniform over visible abilities
    return random.choice(visible)
def roll_gender(gender_ratio: dict) -> str:
    """Return 'male'/'female'/'genderless' using species ratio dict from your cache."""
    if gender_ratio.get("genderless"):
        return "genderless"
    male = float(gender_ratio.get("male", 50.0))
    return "male" if random.random() * 100 < male else "female"

def generate_mon(base_stats: Dict[str, int],
                 abilities: list[dict],
                 gender_ratio: dict,
                 level: int,
                 perfect_ivs: int = 0,
                 nature: str | None = None,
                 evs: Dict[str, int] | None = None) -> dict:
    """High-level: roll IVs/gender/ability/nature and compute final stats."""
    ivs = roll_ivs(perfect_ivs)
    evs = evs or {k: 0 for k in STAT_KEYS}
    nature = (nature or pick_random_nature()).lower()
    final_stats = calc_all_stats(base_stats, ivs, evs, level, nature)
    ability = choose_ability(abilities)
    gender = roll_gender(gender_ratio)
    return {
        "ivs": ivs,
        "evs": evs,
        "nature": nature,
        "ability": ability,
        "gender": gender,
        "stats": final_stats,  # includes hp/atk/def/spa/spd/spe
    }
