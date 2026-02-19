from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

MARKET_PRICE_CATALOG: Dict[str, List[Tuple[str, str, int]]] = {
    "Treasure Items": [
        ("nugget", "Nugget", 5000),
        ("big_nugget", "Big Nugget", 10000),
        ("pearl", "Pearl", 700),
        ("big_pearl", "Big Pearl", 3750),
        ("stardust", "Stardust", 1000),
        ("star_piece", "Star Piece", 4900),
        ("tiny_mushroom", "Tiny Mushroom", 250),
        ("big_mushroom", "Big Mushroom", 2500),
        ("shoal_salt", "Shoal Salt", 10),
        ("shoal_shell", "Shoal Shell", 10),
    ],
    "Healing Items": [
        ("potion", "Potion", 800),
        ("super_potion", "Super Potion", 1800),
        ("hyper_potion", "Hyper Potion", 3500),
        ("full_restore", "Full Restore", 7500),
        ("revive", "Revive", 4000),
        ("fresh_water", "Fresh Water", 600),
        ("soda_pop", "Soda Pop", 900),
        ("lemonade", "Lemonade", 1200),
        ("moomoo_milk", "Moomoo Milk", 1500),
        ("antidote", "Antidote", 400),
        ("burn_heal", "Burn Heal", 500),
        ("ice_heal", "Ice Heal", 500),
        ("awakening", "Awakening", 500),
        ("paralyze_heal", "Parlyz Heal", 450),
        ("full_heal", "Full Heal", 1200),
    ],
    "PP Recovery": [
        ("ether", "Ether", 1500),
        ("elixir", "Elixir", 3500),
    ],
    "Evolution Stones": [
        ("fire_stone", "Fire Stone", 2100),
        ("water_stone", "Water Stone", 2100),
        ("thunder_stone", "Thunder Stone", 2100),
        ("leaf_stone", "Leaf Stone", 2100),
        ("moon_stone", "Moon Stone", 2100),
        ("sun_stone", "Sun Stone", 2100),
    ],
    "Poké Balls": [
        ("poke_ball", "Poké Ball", 100),
        ("great_ball", "Great Ball", 300),
        ("ultra_ball", "Ultra Ball", 600),
        ("repeat_ball", "Repeat Ball", 500),
        ("timer_ball", "Timer Ball", 500),
        ("net_ball", "Net Ball", 500),
        ("dive_ball", "Dive Ball", 500),
        ("nest_ball", "Nest Ball", 500),
        ("luxury_ball", "Luxury Ball", 500),
    ],
    "Other Battle / Escape Items": [
        ("poke_doll", "Poké Doll", 500),
        ("fluffy_tail", "Fluffy Tail", 500),
    ],
    "Held Items": [
        ("leftovers", "Leftovers", 2000),
        ("quick_claw", "Quick Claw", 50),
        ("kings_rock", "King's Rock", 100),
        ("scope_lens", "Scope Lens", 100),
        ("focus_band", "Focus Band", 100),
        ("choice_band", "Choice Band", 100),
        ("exp_share", "Exp. Share", 20000),
        ("amulet_coin", "Amulet Coin", 100),
        ("everstone", "Everstone", 100),
        ("lucky_egg", "Lucky Egg", 5000),
        ("macho_brace", "Macho Brace", 1500),
        ("soothe_bell", "Soothe Bell", 100),
    ],
}

MARKET_ITEM_ALIASES: Dict[str, str] = {
    "pokeball": "poke_ball",
    "pok_ball": "poke_ball",
    "poke_ball": "poke_ball",
    "great_ball": "great_ball",
    "ultra_ball": "ultra_ball",
    "parlyz_heal": "paralyze_heal",
    "kingsrock": "kings_rock",
}

MARKET_SELL_PRICES: Dict[str, int] = {
    item_id: int(price)
    for rows in MARKET_PRICE_CATALOG.values()
    for item_id, _disp, price in rows
}

MARKET_DISPLAY_NAMES: Dict[str, str] = {
    item_id: disp
    for rows in MARKET_PRICE_CATALOG.values()
    for item_id, disp, _price in rows
}


def _normalize_item_id(raw: str) -> str:
    s = str(raw or "").strip().lower()
    s = re.sub(r"[\s\-]+", "_", s)
    s = re.sub(r"[^a-z0-9_]", "", s)
    return s


def normalize_market_key(raw: str) -> str:
    key = _normalize_item_id(raw)
    return MARKET_ITEM_ALIASES.get(key, key)


def resolve_market_key(raw: str) -> Optional[str]:
    key = normalize_market_key(raw)
    if key in MARKET_SELL_PRICES:
        return key
    key2 = _normalize_item_id(raw)
    for item_id, display in MARKET_DISPLAY_NAMES.items():
        if _normalize_item_id(display) == key2:
            return item_id
    return None


def market_item_variants(item_key: str) -> tuple[str, ...]:
    base = _normalize_item_id(item_key)
    out = [base, base.replace("_", "-")]
    if base == "paralyze_heal":
        out.extend(["parlyz_heal", "paralyze-heal"])
    dedup: list[str] = []
    for v in out:
        if v and v not in dedup:
            dedup.append(v)
    return tuple(dedup)


def market_display_name(item_key: str) -> str:
    return MARKET_DISPLAY_NAMES.get(item_key, str(item_key or "").replace("_", " ").title())
