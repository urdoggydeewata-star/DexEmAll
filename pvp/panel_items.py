"""
Battle bag item constants and helpers - healing items, Poké Balls, normalization.
Extracted from pvp/panel.py for cleaner separation.
"""
from __future__ import annotations

_HEALING_ITEMS = {
    "potion": 20,
    "super potion": 50,
    "hyper potion": 120,
    "max potion": None,  # full
    "full restore": None,  # full + status clear
    "fresh water": 30,
    "soda pop": 50,
    "lemonade": 70,
    "moomoo milk": 100,
}

# Official game catch rate modifiers per Bulbapedia (Poke 1x, Great 1.5x, Ultra 2x, Master guaranteed)
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


def normalize_item(name: str) -> str:
    """Normalize item name for lookup."""
    n = str(name or "").strip().lower().replace("é", "e")
    for ch in ("-", "_", "–", "—", "‑", "‒", "−", "﹣", "－", ":"):
        n = n.replace(ch, " ")
    return " ".join(n.split())


def heal_amount_for_item(item_key: str):
    """Get heal amount for an item (handles max_potion, max-potion, max potion, etc.)."""
    norm = normalize_item(item_key)
    if norm in _HEALING_ITEMS:
        return _HEALING_ITEMS[norm]
    compact = norm.replace(" ", "")
    for k, v in _HEALING_ITEMS.items():
        if k.replace(" ", "") == compact:
            return v
    return 0


def normalize_ball_name(name: str) -> str:
    """Normalize ball name for lookup."""
    n = normalize_item(name)
    compact = "".join(ch for ch in n if ch.isalnum())
    if n in _BALLS_BASIC:
        return n
    if compact in _BALL_NAME_ALIASES:
        return _BALL_NAME_ALIASES[compact]
    return n
