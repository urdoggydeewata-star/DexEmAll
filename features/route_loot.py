"""Route move loot tables and TM data. Extracted from pokebot.py."""
from __future__ import annotations

import random
from typing import Dict, List, Sequence, Tuple

# Gen 1 TMs (consumable) and HMs (permanent)
GEN1_TMS: List[Tuple[str, str]] = [
    ("tm-01", "Mega Punch"), ("tm-02", "Razor Wind"), ("tm-03", "Swords Dance"), ("tm-04", "Whirlwind"),
    ("tm-05", "Mega Kick"), ("tm-06", "Toxic"), ("tm-07", "Horn Drill"), ("tm-08", "Body Slam"),
    ("tm-09", "Take Down"), ("tm-10", "Double-Edge"), ("tm-11", "Bubble Beam"), ("tm-12", "Water Gun"),
    ("tm-13", "Ice Beam"), ("tm-14", "Blizzard"), ("tm-15", "Hyper Beam"), ("tm-16", "Pay Day"),
    ("tm-17", "Submission"), ("tm-18", "Counter"), ("tm-19", "Seismic Toss"), ("tm-20", "Rage"),
    ("tm-21", "Mega Drain"), ("tm-22", "Solar Beam"), ("tm-23", "Dragon Rage"), ("tm-24", "Thunderbolt"),
    ("tm-25", "Thunder"), ("tm-26", "Earthquake"), ("tm-27", "Fissure"), ("tm-28", "Dig"),
    ("tm-29", "Psychic"), ("tm-30", "Teleport"), ("tm-31", "Mimic"), ("tm-32", "Double Team"),
    ("tm-33", "Reflect"), ("tm-34", "Bide"), ("tm-35", "Metronome"), ("tm-36", "Self-Destruct"),
    ("tm-37", "Egg Bomb"), ("tm-38", "Fire Blast"), ("tm-39", "Swift"), ("tm-40", "Skull Bash"),
    ("tm-41", "Soft-Boiled"), ("tm-42", "Dream Eater"), ("tm-43", "Sky Attack"), ("tm-44", "Rest"),
    ("tm-45", "Thunder Wave"), ("tm-46", "Psywave"), ("tm-47", "Explosion"), ("tm-48", "Rock Slide"),
    ("tm-49", "Tri Attack"), ("tm-50", "Substitute"),
]
GEN1_HMS: List[Tuple[str, str]] = [
    ("hm-01", "Cut"), ("hm-02", "Fly"), ("hm-03", "Surf"), ("hm-04", "Strength"), ("hm-05", "Flash"),
]
TM_SELLER_PRICE = 500
TM_SELLER_ITEMS = [GEN1_TMS[i - 1] for i in (1, 3, 5, 6, 7, 9, 11, 12, 15, 17, 20, 21, 22, 23, 24, 31, 34, 35, 37, 40, 42, 44, 45, 49, 50)]

# Rates adjusted one decimal left (÷10) to make route balls rarer
ROUTE_MOVE_BALL_ENCOUNTER_RATES: List[Tuple[str, str, float]] = [
    ("poke_ball", "Poké Ball", 0.9),
    ("great_ball", "Great Ball", 0.6),
    ("ultra_ball", "Ultra Ball", 0.2),
    ("master_ball", "Master Ball", 0.008),
    ("nest_ball", "Nest Ball", 0.4),
    ("net_ball", "Net Ball", 0.4),
    ("dive_ball", "Dive Ball", 0.4),
    ("heal_ball", "Heal Ball", 0.4),
    ("dusk_ball", "Dusk Ball", 0.4),
    ("dream_ball", "Dream Ball", 0.4),
    ("sport_ball", "Sport Ball", 0.4),
    ("level_ball", "Level Ball", 0.4),
    ("moon_ball", "Moon Ball", 0.4),
    ("friend_ball", "Friend Ball", 0.4),
    ("love_ball", "Love Ball", 0.4),
    ("heavy_ball", "Heavy Ball", 0.4),
    ("fast_ball", "Fast Ball", 0.4),
    ("premier_ball", "Premier Ball", 0.4),
    ("repeat_ball", "Repeat Ball", 0.4),
    ("tm_ball", "TM Ball", 0.4),
    ("great_tm_ball", "Great TM Ball", 0.4),
    ("ultra_tm_ball", "Ultra TM Ball", 0.4),
    ("timer_ball", "Timer Ball", 0.4),
]

ROUTE_MOVE_ITEMS_BY_BALL: Dict[str, List[Tuple[str, str, float]]] = {
    "poke_ball": [
        ("poke_ball", "Poké Ball", 15.69), ("escape_rope", "Escape Rope", 15.69), ("poke_doll", "Poké Doll", 15.69),
        ("antidote", "Antidote", 5.88), ("burn_heal", "Burn Heal", 5.88), ("awakening", "Awakening", 5.88),
        ("paralyze_heal", "Paralyze Heal", 5.88), ("ice_heal", "Ice Heal", 5.88), ("repel", "Repel", 5.88),
        ("oran_berry", "Oran Berry", 5.88), ("tiny_mushroom", "Tiny Mushroom", 5.88),
        ("stardust", "Stardust", 3.92), ("potion", "Potion", 1.96),
    ],
    "great_ball": [
        ("great_ball", "Great Ball", 9.52), ("antidote", "Antidote", 9.52), ("awakening", "Awakening", 9.52),
        ("burn_heal", "Burn Heal", 9.52), ("paralyze_heal", "Paralyze Heal", 9.52), ("repel", "Repel", 9.52),
        ("berry_juice", "Berry Juice", 9.52), ("shoal_shell", "Shoal Shell", 4.76), ("shoal_salt", "Shoal Salt", 4.76),
        ("stardust", "Stardust", 4.76), ("pearl", "Pearl", 4.76), ("super_repel", "Super Repel", 4.76),
        ("super_potion", "Super Potion", 4.76),
    ],
    "ultra_ball": [
        ("ultra_ball", "Ultra Ball", 10.53), ("lemonade", "Lemonade", 10.53), ("sitrus_berry", "Sitrus Berry", 10.53),
        ("moomoo_milk", "Moomoo Milk", 10.53), ("full_heal", "Full Heal", 10.53), ("max_repel", "Max Repel", 10.53),
        ("hyper_potion", "Hyper Potion", 5.26), ("nugget", "Nugget", 5.26), ("revive", "Revive", 5.26),
        ("elixir", "Elixir", 5.26), ("leftovers", "Leftovers", 1.05),
    ],
    "master_ball": [
        ("max_elixir", "Max Elixir", 23.26), ("revive", "Revive", 23.26), ("revival_herb", "Revival Herb", 9.30),
        ("max_revive", "Max Revive", 9.30), ("pp_max", "PP Max", 5.81), ("master_ball", "Master Ball", 5.81),
    ],
    "nest_ball": [
        ("nest_ball", "Nest Ball", 9.80), ("heal_powder", "Heal Powder", 9.80), ("lum_berry", "Lum Berry", 9.80),
        ("berry_juice", "Berry Juice", 9.80), ("energy_powder", "Energy Powder", 9.80),
        ("sitrus_berry", "Sitrus Berry", 9.80), ("stick", "Stick", 9.80), ("leaf_stone", "Leaf Stone", 4.90),
        ("miracle_seed", "Miracle Seed", 4.90), ("energy_root", "Energy Root", 4.90),
        ("silver_powder", "Silver Powder", 4.90), ("bright_powder", "Bright Powder", 4.90),
        ("revival_herb", "Revival Herb", 0.98), ("leftovers", "Leftovers", 0.98),
    ],
    "net_ball": [
        ("net_ball", "Net Ball", 22.22), ("super_potion", "Super Potion", 22.22),
        ("silver_powder", "Silver Powder", 11.11), ("mystic_water", "Mystic Water", 11.11),
        ("sharp_beak", "Sharp Beak", 11.11), ("pearl", "Pearl", 11.11), ("nugget", "Nugget", 11.11),
    ],
    "dive_ball": [
        ("dive_ball", "Dive Ball", 10.64), ("fresh_water", "Fresh Water", 10.64), ("soda_pop", "Soda Pop", 10.64),
        ("lemonade", "Lemonade", 10.64), ("moomoo_milk", "Moomoo Milk", 10.64),
        ("sea_incense", "Sea Incense", 10.64), ("deep_sea_tooth", "Deep Sea Tooth", 10.64),
        ("deep_sea_scale", "Deep Sea Scale", 10.64), ("zinc", "Zinc", 2.14),
        ("helix_fossil", "Helix Fossil", 2.14), ("dome_fossil", "Dome Fossil", 2.14),
    ],
    "heal_ball": [
        ("heal_ball", "Heal Ball", 18.18), ("potion", "Potion", 18.18), ("super_potion", "Super Potion", 14.55),
        ("moomoo_milk", "Moomoo Milk", 14.55), ("full_heal", "Full Heal", 14.55),
        ("hyper_potion", "Hyper Potion", 5.45), ("max_potion", "Max Potion", 5.45),
        ("full_restore", "Full Restore", 5.45), ("revive", "Revive", 5.45), ("hp_up", "HP Up", 5.45),
    ],
    "dusk_ball": [
        ("dusk_ball", "Dusk Ball", 12.66), ("super_potion", "Super Potion", 12.66), ("ether", "Ether", 12.66),
        ("lava_cookie", "Lava Cookie", 12.66), ("stardust", "Stardust", 12.66), ("pearl", "Pearl", 12.66),
        ("black_flute", "Black Flute", 3.80), ("spell_tag", "Spell Tag", 3.80), ("black_glasses", "Black Glasses", 3.80),
    ],
    "dream_ball": [
        ("dream_ball", "Dream Ball", 10.75), ("awakening", "Awakening", 10.75), ("chesto_berry", "Chesto Berry", 10.75),
        ("super_potion", "Super Potion", 10.75), ("ether", "Ether", 10.75), ("lava_cookie", "Lava Cookie", 10.75),
        ("smoke_ball", "Smoke Ball", 10.75), ("stardust", "Stardust", 10.75), ("pearl", "Pearl", 3.23),
        ("twisted_spoon", "Twisted Spoon", 3.23),
    ],
    "sport_ball": [
        ("sport_ball", "Sport Ball", 5.43), ("black_belt", "Black Belt", 5.43), ("black_glasses", "Black Glasses", 5.43),
        ("bright_powder", "Bright Powder", 5.43), ("mystic_water", "Mystic Water", 5.43),
        ("miracle_seed", "Miracle Seed", 5.43), ("charcoal", "Charcoal", 5.43), ("spell_tag", "Spell Tag", 5.43),
        ("never_melt_ice", "Never Melt Ice", 5.43), ("soft_sand", "Soft Sand", 5.43), ("metal_coat", "Metal Coat", 5.43),
        ("sharp_beak", "Sharp Beak", 5.43), ("silk_scarf", "Silk Scarf", 5.43), ("poison_barb", "Poison Barb", 5.43),
        ("twisted_spoon", "Twisted Spoon", 5.43), ("dragon_fang", "Dragon Fang", 5.43), ("hard_stone", "Hard Stone", 5.43),
        ("magnet", "Magnet", 5.43), ("choice_band", "Choice Band", 2.17),
    ],
    "tm_ball": [
        ("tm-04", "Whirlwind", 6.67), ("tm-06", "Toxic", 6.67), ("tm-08", "Body Slam", 6.67),
        ("tm-09", "Take Down", 6.67), ("tm-11", "Bubble Beam", 6.67), ("tm-12", "Water Gun", 6.67),
        ("tm-20", "Rage", 6.67), ("tm-31", "Mimic", 6.67), ("tm-32", "Double Team", 6.67),
        ("tm-33", "Reflect", 6.67), ("tm-39", "Swift", 6.67), ("tm-44", "Rest", 6.67),
        ("tm-45", "Thunder Wave", 6.67), ("tm-48", "Rock Slide", 6.67), ("tm-50", "Substitute", 6.67),
    ],
    "great_tm_ball": [
        ("tm-03", "Swords Dance", 6.25), ("tm-05", "Mega Kick", 6.25), ("tm-13", "Ice Beam", 6.25),
        ("tm-14", "Blizzard", 6.25), ("tm-17", "Submission", 6.25), ("tm-21", "Mega Drain", 6.25),
        ("tm-22", "Solar Beam", 6.25), ("tm-23", "Dragon Rage", 6.25), ("tm-24", "Thunderbolt", 6.25),
        ("tm-25", "Thunder", 6.25), ("tm-26", "Earthquake", 6.25), ("tm-28", "Dig", 6.25),
        ("tm-29", "Psychic", 6.25), ("tm-38", "Fire Blast", 6.25), ("tm-42", "Dream Eater", 6.25),
        ("tm-49", "Tri Attack", 6.25),
    ],
    "ultra_tm_ball": [
        ("tm-01", "Mega Punch", 5.26), ("tm-02", "Razor Wind", 5.26), ("tm-07", "Horn Drill", 5.26),
        ("tm-10", "Double-Edge", 5.26), ("tm-15", "Hyper Beam", 5.26), ("tm-16", "Pay Day", 5.26),
        ("tm-18", "Counter", 5.26), ("tm-19", "Seismic Toss", 5.26), ("tm-27", "Fissure", 5.26),
        ("tm-30", "Teleport", 5.26), ("tm-34", "Bide", 5.26), ("tm-35", "Metronome", 5.26),
        ("tm-36", "Self-Destruct", 5.26), ("tm-37", "Egg Bomb", 5.26), ("tm-40", "Skull Bash", 5.26),
        ("tm-41", "Soft-Boiled", 5.26), ("tm-43", "Sky Attack", 5.26), ("tm-46", "Psywave", 5.26),
        ("tm-47", "Explosion", 5.26),
    ],
    "level_ball": [
        ("fire_stone", "Fire Stone", 8.85), ("water_stone", "Water Stone", 8.85), ("leaf_stone", "Leaf Stone", 8.85),
        ("thunder_stone", "Thunder Stone", 8.85), ("moon_stone", "Moon Stone", 8.85), ("sun_stone", "Sun Stone", 8.85),
        ("metal_coat", "Metal Coat", 8.85), ("kings_rock", "King's Rock", 8.85), ("up_grade", "Up-Grade", 8.85),
        ("dragon_scale", "Dragon Scale", 8.85), ("rare_candy", "Rare Candy", 2.65),
    ],
    "moon_ball": [
        ("berry_juice", "Berry Juice", 8.55), ("ether", "Ether", 8.55), ("shoal_shell", "Shoal Shell", 8.55),
        ("shoal_salt", "Shoal Salt", 8.55), ("stardust", "Stardust", 8.55), ("pearl", "Pearl", 8.55),
        ("super_repel", "Super Repel", 8.55), ("super_potion", "Super Potion", 8.55), ("spell_tag", "Spell Tag", 5.98),
    ],
    "friend_ball": [
        ("cheri_berry", "Cheri Berry", 4.0), ("chesto_berry", "Chesto Berry", 4.0), ("pecha_berry", "Pecha Berry", 4.0),
        ("rawst_berry", "Rawst Berry", 4.0), ("aspear_berry", "Aspear Berry", 4.0), ("persim_berry", "Persim Berry", 4.0),
        ("sitrus_berry", "Sitrus Berry", 4.0), ("aguav_berry", "Aguav Berry", 4.0), ("figy_berry", "Figy Berry", 4.0),
        ("iapapa_berry", "Iapapa Berry", 4.0), ("lum_berry", "Lum Berry", 4.0), ("liechi_berry", "Liechi Berry", 4.0),
        ("salac_berry", "Salac Berry", 4.0), ("lansat_berry", "Lansat Berry", 4.0), ("starf_berry", "Starf Berry", 4.0),
        ("__bonus_berry__", "Bonus Berry", 4.0),
    ],
    "love_ball": [
        ("everstone", "Everstone", 7.69), ("destiny_knot", "Destiny Knot", 7.69), ("oval_stone", "Oval Stone", 7.69),
        ("lax_incense", "Lax Incense", 7.69), ("sea_incense", "Sea Incense", 7.69), ("heart_scale", "Heart Scale", 7.69),
        ("power_weight", "Power Weight", 7.69), ("power_bracer", "Power Bracer", 7.69), ("power_belt", "Power Belt", 7.69),
        ("power_lens", "Power Lens", 7.69), ("power_band", "Power Band", 7.69), ("macho_brace", "Macho Brace", 7.69),
    ],
    "heavy_ball": [
        ("super_potion", "Super Potion", 10.64), ("lemonade", "Lemonade", 10.64), ("hard_stone", "Hard Stone", 10.64),
        ("everstone", "Everstone", 10.64), ("metal_coat", "Metal Coat", 5.32), ("pp_up", "PP Up", 5.32),
        ("dome_fossil", "Dome Fossil", 1.06), ("helix_fossil", "Helix Fossil", 1.06), ("old_amber", "Old Amber", 1.06),
    ],
    "fast_ball": [
        ("fresh_water", "Fresh Water", 10.53), ("soda_pop", "Soda Pop", 10.53), ("thunder_stone", "Thunder Stone", 10.53),
        ("pearl", "Pearl", 10.53), ("stardust", "Stardust", 10.53), ("magnet", "Magnet", 10.53),
    ],
    "premier_ball": [
        ("tiny_mushroom", "Tiny Mushroom", 20.41), ("stardust", "Stardust", 20.41), ("pearl", "Pearl", 20.41),
        ("nugget", "Nugget", 20.41), ("big_pearl", "Big Pearl", 6.12), ("star_piece", "Star Piece", 6.12),
        ("big_nugget", "Big Nugget", 6.12),
    ],
}

ROUTE_MOVE_TIMER_POOL_KEY = "poke_ball"
ROUTE_MOVE_LAST_STANDARD_ROLL: Dict[str, Tuple[str, str, str, str]] = {}
ROUTE_MOVE_BONUS_BERRIES: List[Tuple[str, str]] = [
    ("cheri_berry", "Cheri Berry"), ("chesto_berry", "Chesto Berry"), ("pecha_berry", "Pecha Berry"),
    ("rawst_berry", "Rawst Berry"), ("aspear_berry", "Aspear Berry"), ("persim_berry", "Persim Berry"),
    ("sitrus_berry", "Sitrus Berry"), ("aguav_berry", "Aguav Berry"), ("figy_berry", "Figy Berry"),
    ("iapapa_berry", "Iapapa Berry"), ("lum_berry", "Lum Berry"),
]


def weighted_choice(items: Sequence[Tuple[str, str, float]]) -> Tuple[str, str]:
    """Pick (id, display_name) from weighted tuples (id, name, weight)."""
    if not items:
        return ("", "")
    total = 0.0
    norm: List[Tuple[str, str, float]] = []
    for key, name, weight in items:
        w = max(0.0, float(weight or 0.0))
        if w <= 0:
            continue
        norm.append((str(key), str(name), w))
        total += w
    if total <= 0 or not norm:
        key, name, _ = items[-1]
        return str(key), str(name)
    r = random.uniform(0.0, total)
    for key, name, weight in norm:
        r -= weight
        if r <= 0:
            return key, name
    return norm[-1][0], norm[-1][1]


def roll_route_ball_by_absolute_rate() -> Tuple[str, str]:
    """Roll route ball encounter using absolute percentage rates."""
    if not ROUTE_MOVE_BALL_ENCOUNTER_RATES:
        return ("__none__", "No Ball")
    r = random.uniform(0.0, 100.0)
    cumul = 0.0
    for ball_id, ball_name, pct in ROUTE_MOVE_BALL_ENCOUNTER_RATES:
        p = max(0.0, float(pct or 0.0))
        if p <= 0.0:
            continue
        cumul += p
        if r <= cumul:
            return str(ball_id), str(ball_name)
    return ("__none__", "No Ball")


def route_pick_item_from_pool(pool_key: str) -> Tuple[str, str]:
    """Pick item from a ball's loot pool."""
    pool = ROUTE_MOVE_ITEMS_BY_BALL.get(str(pool_key or "")) or ROUTE_MOVE_ITEMS_BY_BALL.get("poke_ball") or []
    item_id, item_name = weighted_choice(pool)
    if item_id == "__bonus_berry__":
        try:
            return random.choice(ROUTE_MOVE_BONUS_BERRIES)
        except Exception:
            return ("oran_berry", "Oran Berry")
    return item_id, item_name
