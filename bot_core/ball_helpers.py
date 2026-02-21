"""
Ball and friendship helpers - pure functions for Poké Ball behavior.
Extracted from pokebot.py for modularity.
"""
from __future__ import annotations

import re
from typing import Optional


def normalize_ball_item_id(ball_name: Optional[str]) -> str:
    """Normalize a Poké Ball identifier to canonical item_id style (snake_case)."""
    raw = str(ball_name or "").strip().lower()
    if not raw:
        return "poke_ball"
    norm = re.sub(r"[\s\-]+", "_", raw)
    norm = re.sub(r"[^a-z0-9_]", "", norm)
    aliases = {
        "pokeball": "poke_ball",
        "pok_ball": "poke_ball",
        "poke_ball": "poke_ball",
        "greatball": "great_ball",
        "ultraball": "ultra_ball",
        "masterball": "master_ball",
        "safariball": "safari_ball",
        "repeatball": "repeat_ball",
        "timerball": "timer_ball",
        "quickball": "quick_ball",
        "duskball": "dusk_ball",
        "netball": "net_ball",
        "nestball": "nest_ball",
        "heavyball": "heavy_ball",
        "loveball": "love_ball",
        "levelball": "level_ball",
        "lureball": "lure_ball",
        "moonball": "moon_ball",
        "fastball": "fast_ball",
        "friendball": "friend_ball",
        "friendshipball": "friend_ball",
        "friendship_ball": "friend_ball",
        "healball": "heal_ball",
        "luxuryball": "luxury_ball",
        "premierball": "premier_ball",
        "beastball": "beast_ball",
        "diveball": "dive_ball",
        "cherishball": "cherish_ball",
        "sportball": "sport_ball",
        "dreamball": "dream_ball",
        "parkball": "park_ball",
    }
    return aliases.get(norm, norm)


def is_friend_ball(ball_item_id: Optional[str]) -> bool:
    return normalize_ball_item_id(ball_item_id) == "friend_ball"


def is_heal_ball(ball_item_id: Optional[str]) -> bool:
    return normalize_ball_item_id(ball_item_id) == "heal_ball"


def is_luxury_ball(ball_item_id: Optional[str]) -> bool:
    return normalize_ball_item_id(ball_item_id) == "luxury_ball"


def caught_friendship_for_ball(base_friendship: int, ball_item_id: Optional[str]) -> int:
    """Apply on-catch friendship behavior from the catch ball."""
    value = max(0, min(255, int(base_friendship or 0)))
    if is_friend_ball(ball_item_id):
        value = max(value, 200)
    return value


def friendship_delta_with_ball_bonus(delta: int, ball_item_id: Optional[str]) -> int:
    """Luxury Ball gives +1 friendship on positive friendship gains."""
    d = int(delta or 0)
    if d > 0 and is_luxury_ball(ball_item_id):
        return d + 1
    return d
