"""PvP panel capture: balls, healing items, capture mechanics. Extracted from panel.py."""
from __future__ import annotations

import random
from typing import Optional, Tuple

from .engine import Mon

_HEALING_ITEMS = {
    "potion": 20,
    "super potion": 50,
    "hyper potion": 120,
    "max potion": None,
    "full restore": None,
    "fresh water": 30,
    "soda pop": 50,
    "lemonade": 70,
    "moomoo milk": 100,
}


def is_healing_item(item_key: str) -> bool:
    """Return True if item restores HP (for /give use-on-mon flow)."""
    norm = _normalize_item(item_key)
    if norm in _HEALING_ITEMS:
        return True
    compact = norm.replace(" ", "")
    return any(k.replace(" ", "") == compact for k in _HEALING_ITEMS)

_BALLS_BASIC = {
    "poke ball": 1.0,
    "poké ball": 1.0,
    "great ball": 1.5,
    "ultra ball": 2.0,
    "master ball": 9999.0,
    "safari ball": 1.5,
    "repeat ball": None,
    "timer ball": None,
    "quick ball": None,
    "dusk ball": None,
    "net ball": None,
    "nest ball": None,
    "heavy ball": None,
    "love ball": None,
    "level ball": None,
    "lure ball": None,
    "moon ball": None,
    "fast ball": None,
    "friend ball": 1.0,
    "heal ball": 1.0,
    "luxury ball": 1.0,
    "premier ball": 1.0,
    "beast ball": None,
    "dive ball": None,
    "cherish ball": 1.0,
    "sport ball": 1.0,
    "dream ball": None,
    "park ball": 1.0,
}

_ULTRA_BEAST_SPECIES = {
    "nihilego", "buzzwole", "pheromosa", "xurkitree", "celesteela",
    "kartana", "guzzlord", "poipole", "naganadel", "stakataka", "blacephalon",
}

_BALL_NAME_ALIASES = {
    "pokeball": "poke ball", "greatball": "great ball", "ultraball": "ultra ball",
    "masterball": "master ball", "safariball": "safari ball", "repeatball": "repeat ball",
    "timerball": "timer ball", "quickball": "quick ball", "duskball": "dusk ball",
    "netball": "net ball", "nestball": "nest ball", "heavyball": "heavy ball",
    "loveball": "love ball", "levelball": "level ball", "lureball": "lure ball",
    "moonball": "moon ball", "fastball": "fast ball", "friendball": "friend ball",
    "healball": "heal ball", "luxuryball": "luxury ball", "premierball": "premier ball",
    "beastball": "beast ball", "diveball": "dive ball", "cherishball": "cherish ball",
    "sportball": "sport ball", "dreamball": "dream ball", "parkball": "park ball",
}


def _normalize_item(name: str) -> str:
    n = str(name or "").strip().lower().replace("é", "e")
    for ch in ("-", "_", "–", "—", "‑", "‒", "−", "﹣", "－", ":"):
        n = n.replace(ch, " ")
    return " ".join(n.split())


def _normalize_ball_name(name: str) -> str:
    n = _normalize_item(name)
    compact = "".join(ch for ch in n if ch.isalnum())
    if n in _BALLS_BASIC:
        return n
    if compact in _BALL_NAME_ALIASES:
        return _BALL_NAME_ALIASES[compact]
    return n


def heal_amount_for_item(item_key: str):
    """Get heal amount for an item."""
    norm = _normalize_item(item_key)
    if norm in _HEALING_ITEMS:
        return _HEALING_ITEMS[norm]
    compact = norm.replace(" ", "")
    for k, v in _HEALING_ITEMS.items():
        if k.replace(" ", "") == compact:
            return v
    return 0


def status_bonus(modern_status: Optional[str]) -> float:
    if not modern_status:
        return 1.0
    s = modern_status.lower()
    if s in ("slp", "frz", "sleep", "frozen"):
        return 2.0
    if s in ("par", "brn", "psn", "tox", "poison", "burned", "paralyzed"):
        return 1.5
    return 1.0


def ball_multiplier(ball_name: str, mon: Mon, battle_state: "BattleState") -> float:
    b = _normalize_ball_name(ball_name)
    try:
        gen = int(getattr(battle_state, "gen", 9) or 9)
    except Exception:
        gen = 9
    try:
        turn = max(1, int(getattr(battle_state, "turn", 1) or 1))
    except Exception:
        turn = 1
    types = [str(t).lower() for t in (getattr(mon, "types", []) or []) if t]
    try:
        level = float(getattr(mon, "level", 1) or 1)
    except Exception:
        level = 1.0
    fmt = (battle_state.fmt_label or "").lower()
    in_cave = "cave" in fmt
    at_night = "night" in fmt or "evening" in fmt
    in_water = "water" in fmt or "sea" in fmt or "ocean" in fmt
    in_dark_grass = "dark grass" in fmt

    base = _BALLS_BASIC.get(b, 1.0) or 1.0
    if b == "timer ball":
        base = min(1.0 + ((turn - 1) * 1229 / 4096), 4.0) if gen >= 5 else min(1.0 + 0.3 * (turn - 1), 4.0)
    elif b == "quick ball":
        base = (5.0 if gen >= 5 else 4.0) if turn <= 1 else 1.0
    elif b == "dusk ball":
        base = (3.5 if gen >= 5 else 4.0) if (at_night or in_cave or in_dark_grass) else 1.0
    elif b == "net ball":
        base = (3.5 if gen >= 5 else 3.0) if ("water" in types or "bug" in types) else 1.0
    elif b == "nest ball":
        base = max(1.0, min(4.0, (41.0 - level) / 10.0)) if level <= 29 else 1.0
    elif b == "repeat ball":
        caught = getattr(battle_state, "repeat_caught", None) or getattr(battle_state, "repeat_seen", set()) or set()
        caught_norm = {str(s).lower() for s in caught}
        base = (3.5 if gen >= 7 else 3.0) if mon.species.lower() in caught_norm else 1.0
    elif b == "dive ball":
        base = (3.5 if gen >= 5 else 3.0) if in_water else 1.0
    elif b == "heavy ball":
        base = 1.0
    elif b == "level ball":
        lead = battle_state._active(battle_state.p1_id)
        if lead:
            lead_level = float(getattr(lead, "level", 1) or 1)
            if lead_level >= level * 4:
                base = 8.0
            elif lead_level >= level * 2:
                base = 4.0
            elif lead_level > level:
                base = 2.0
            else:
                base = 1.0
        else:
            base = 1.0
    elif b == "love ball":
        lead = battle_state._active(battle_state.p1_id)
        lead_gender = str(getattr(lead, "gender", "") or "").upper() if lead else ""
        mon_gender = str(getattr(mon, "gender", "") or "").upper()
        opposite = lead_gender in {"M", "F"} and mon_gender in {"M", "F"} and lead_gender != mon_gender
        base = 8.0 if lead and lead.species.lower() == mon.species.lower() and opposite else 1.0
    elif b == "lure ball":
        is_fishing = bool(getattr(battle_state, "is_fishing_encounter", False))
        base = (5.0 if gen >= 7 else 3.0) if (is_fishing or in_water) else 1.0
    elif b == "moon ball":
        moon_targets = {"nidorina", "nidorino", "clefairy", "jigglypuff", "skitty", "munna"}
        base = 4.0 if mon.species.lower() in moon_targets else 1.0
    elif b == "fast ball":
        try:
            mon_base_speed = float(getattr(mon, "base_speed", 0) or 0)
            if mon_base_speed <= 0:
                base_stats = getattr(mon, "base", {}) or {}
                mon_base_speed = float(base_stats.get("spe", base_stats.get("speed", 0)) or 0)
        except Exception:
            mon_base_speed = 0.0
        base = 4.0 if mon_base_speed >= 100 else 1.0
    elif b == "beast ball":
        species_norm = str(getattr(mon, "species", "") or "").strip().lower().replace(" ", "-")
        is_ub = ("ultra beast" in (getattr(mon, "category", "") or "").lower()
                 or bool(getattr(mon, "is_ultra_beast", False))
                 or species_norm in _ULTRA_BEAST_SPECIES)
        base = 5.0 if is_ub else 0.1
    elif b == "dream ball":
        st = str(getattr(mon, "status", "") or "").lower()
        base = 4.0 if st in {"slp", "sleep"} else 1.0
    elif b == "safari ball":
        base = 1.5
    elif b == "sport ball":
        base = 1.5 if gen >= 8 else 1.0
    elif b == "great ball":
        base = 1.5
    elif b == "ultra ball":
        base = 2.0
    elif b == "master ball":
        base = 9999.0
    return max(base, 0.1)


def attempt_capture(mon: Mon, ball_name: str, battle_state: "BattleState") -> Tuple[bool, int]:
    """Return (caught, shakes)."""
    try:
        ball_mod = ball_multiplier(ball_name, mon, battle_state)
    except Exception:
        b = _normalize_ball_name(ball_name)
        ball_mod = _BALLS_BASIC.get(b, 1.0) or 1.0
    if ball_mod >= 9999:
        return True, 1
    try:
        base_rate = int(float(getattr(mon, "capture_rate", 45) or 45))
    except Exception:
        base_rate = 45
    base_rate = max(1, min(255, base_rate))
    b_norm = _normalize_ball_name(ball_name)
    if b_norm == "heavy ball":
        try:
            w = float(getattr(mon, "weight_kg", getattr(mon, "weight", 0)) or 0)
        except Exception:
            w = 0.0
        if w > 0:
            if w < 102.0:
                base_rate = max(1, base_rate - 20)
            elif w >= 409.6:
                base_rate = min(255, base_rate + 40)
            elif w >= 307.2:
                base_rate = min(255, base_rate + 30)
            elif w >= 204.8:
                base_rate = min(255, base_rate + 20)
    status_mod = status_bonus(getattr(mon, "status", None))
    try:
        max_hp = max(1, int(getattr(mon, "max_hp", 1) or 1))
    except Exception:
        max_hp = 1
    try:
        hp = max(1, int(getattr(mon, "hp", 1) or 1))
    except Exception:
        hp = 1
    try:
        gen = int(getattr(battle_state, "gen", 8) or 8)
    except Exception:
        gen = 8

    crit_capture = False
    if gen >= 5:
        try:
            seen = int(getattr(battle_state, "dex_seen", 0) or getattr(battle_state, "seen_dex_count", 0) or 0)
        except Exception:
            seen = 0
        crit_threshold = min(0.5, (base_rate * ball_mod / 255.0) * 0.2 + (seen / 6000.0))
        if random.random() < crit_threshold:
            crit_capture = True

    if gen == 1:
        f = int(((max_hp * 255 * 4) / (hp * max(1.0, 1.0 / ball_mod)))
             + (10 if getattr(mon, "status", None) in ("slp", "frz", "sleep", "frozen")
                else 5 if getattr(mon, "status", None) else 0))
        f = max(1, min(255, f))
        if random.randint(0, 255) < f:
            return True, 3
        shakes = 0
        for _ in range(3):
            if random.randint(0, 255) < f:
                shakes += 1
            else:
                break
        return False, shakes

    bonus_level = 1.0
    if gen >= 8:
        try:
            mon_level = float(getattr(mon, "level", 1) or 1)
        except Exception:
            mon_level = 1.0
        bonus_level = max((30 - mon_level) / 10, 1) if gen == 8 else max((36 - 2 * mon_level) / 10, 1)
    bonus_misc = 1.0
    if gen >= 8 and "raid" in (battle_state.fmt_label or "").lower():
        bonus_misc *= 2.0

    a = ((3 * max_hp - 2 * hp) * base_rate * ball_mod * status_mod * bonus_level * bonus_misc) / (3 * max_hp)
    if gen >= 5:
        a = a * 4096
        if a >= 1044480:
            return True, 4
        b = int(65536 * pow(a / 1044480.0, 0.1875 if gen >= 6 else 0.25))
        if crit_capture and random.randint(0, 65535) < b:
            return True, 1
        shakes = 0
        for _ in range(4):
            if random.randint(0, 65535) < b:
                shakes += 1
            else:
                break
        return shakes == 4, shakes
    else:
        a = int(a)
        if a >= 255:
            return True, 4
        b = int(65536 / pow(16711680 / max(1, a), 0.25))
        shakes = 0
        for _ in range(4):
            if random.randint(0, 65535) < b:
                shakes += 1
            else:
                break
        return shakes == 4, shakes
