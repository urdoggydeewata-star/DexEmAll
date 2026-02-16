"""
Generation Data - Content availability by generation

Tracks when Pokemon, moves, abilities, items, and mechanics were introduced.
Used for generation restriction in PVP battles.
"""

from typing import Dict, Set, List

# ============================================================================
# ABILITY GENERATIONS
# ============================================================================
# Abilities were introduced in Gen 3
# Mapping: ability_name -> generation_introduced

ABILITY_GENERATIONS: Dict[str, int] = {
    # Gen 3 Abilities (76 abilities)
    "adaptability": 4,  # Actually Gen 4
    "aerilate": 6,
    "aftermath": 4,
    "air-lock": 3,
    "analytic": 5,
    "anger-point": 4,
    "anticipation": 4,
    "arena-trap": 3,
    "aroma-veil": 6,
    "as-one": 8,
    "aura-break": 6,
    "bad-dreams": 4,
    "ball-fetch": 8,
    "battery": 7,
    "battle-armor": 3,
    "battle-bond": 7,
    "beast-boost": 7,
    "berserk": 7,
    "big-pecks": 5,
    "blaze": 3,
    "bulletproof": 6,
    "cheek-pouch": 6,
    "chilling-neigh": 8,
    "chlorophyll": 3,
    "clear-body": 3,
    "cloud-nine": 3,
    "color-change": 3,
    "comatose": 7,
    "competitive": 6,
    "compound-eyes": 3,
    "contrary": 5,
    "corrosion": 7,
    "costar": 9,
    "cotton-down": 8,
    "cud-chew": 9,
    "curious-medicine": 8,
    "cursed-body": 5,
    "cute-charm": 3,
    "damp": 3,
    "dancer": 7,
    "dark-aura": 6,
    "dauntless-shield": 8,
    "dazzling": 7,
    "defeatist": 5,
    "defiant": 5,
    "delta-stream": 6,
    "desolate-land": 6,
    "disguise": 7,
    "download": 4,
    "dragons-maw": 9,
    "drizzle": 3,
    "drought": 3,
    "dry-skin": 4,
    "early-bird": 3,
    "earth-eater": 9,
    "effect-spore": 3,
    "electric-surge": 7,
    "electromorphosis": 9,
    "emergency-exit": 7,
    "fairy-aura": 6,
    "filter": 4,
    "flame-body": 3,
    "flare-boost": 5,
    "flash-fire": 3,
    "flower-gift": 4,
    "flower-veil": 6,
    "fluffy": 7,
    "forecast": 3,
    "forewarn": 4,
    "friend-guard": 5,
    "frisk": 4,
    "full-metal-body": 7,
    "fur-coat": 6,
    "gale-wings": 6,
    "galvanize": 6,
    "gluttony": 4,
    "good-as-gold": 9,
    "gooey": 6,
    "gorilla-tactics": 8,
    "grass-pelt": 6,
    "grassy-surge": 7,
    "grim-neigh": 8,
    "guard-dog": 9,
    "gulp-missile": 8,
    "guts": 3,
    "hadron-engine": 9,
    "harvest": 5,
    "healer": 5,
    "heatproof": 4,
    "heavy-metal": 5,
    "honey-gather": 4,
    "hospitality": 9,
    "huge-power": 3,
    "hunger-switch": 8,
    "hustle": 3,
    "hydration": 4,
    "hyper-cutter": 3,
    "ice-body": 4,
    "ice-face": 8,
    "ice-scales": 8,
    "illuminate": 3,
    "illusion": 5,
    "immunity": 3,
    "imposter": 5,
    "infiltrator": 5,
    "innards-out": 7,
    "inner-focus": 3,
    "insomnia": 3,
    "intimidate": 3,
    "intrepid-sword": 8,
    "iron-barbs": 5,
    "iron-fist": 4,
    "justified": 5,
    "keen-eye": 3,
    "klutz": 4,
    "leaf-guard": 4,
    "levitate": 3,
    "libero": 8,
    "light-metal": 5,
    "lightning-rod": 3,
    "limber": 3,
    "lingering-aroma": 9,
    "liquid-ooze": 3,
    "liquid-voice": 7,
    "long-reach": 7,
    "magic-bounce": 5,
    "magic-guard": 4,
    "magician": 6,
    "magma-armor": 3,
    "magnet-pull": 3,
    "marvel-scale": 3,
    "mega-launcher": 6,
    "merciless": 7,
    "mimicry": 8,
    "minds-eye": 9,
    "minus": 3,
    "mirror-armor": 8,
    "misty-surge": 7,
    "mold-breaker": 4,
    "moody": 5,
    "motor-drive": 4,
    "moxie": 5,
    "multiscale": 5,
    "multitype": 4,
    "mummy": 5,
    "mycelium-might": 9,
    "natural-cure": 3,
    "neuroforce": 7,
    "neutralizing-gas": 8,
    "no-guard": 4,
    "normalize": 3,
    "oblivious": 3,
    "opportunist": 9,
    "orichalcum-pulse": 9,
    "overgrow": 3,
    "overcoat": 5,
    "own-tempo": 3,
    "parental-bond": 6,
    "pastel-veil": 8,
    "perish-body": 8,
    "pickpocket": 5,
    "pickup": 3,
    "pixilate": 6,
    "plus": 3,
    "poison-heal": 4,
    "poison-point": 3,
    "poison-touch": 5,
    "power-construct": 7,
    "power-of-alchemy": 7,
    "power-spot": 8,
    "prankster": 5,
    "pressure": 3,
    "primordial-sea": 6,
    "prism-armor": 7,
    "propeller-tail": 8,
    "protean": 6,
    "protosynthesis": 9,
    "psychic-surge": 7,
    "punk-rock": 8,
    "pure-power": 3,
    "purifying-salt": 9,
    "quark-drive": 9,
    "queenly-majesty": 7,
    "quick-draw": 8,
    "quick-feet": 4,
    "rain-dish": 3,
    "rattled": 5,
    "receiver": 7,
    "reckless": 4,
    "refrigerate": 6,
    "regenerator": 5,
    "ripen": 8,
    "rivalry": 4,
    "rks-system": 7,
    "rock-head": 3,
    "rocky-payload": 9,
    "rough-skin": 3,
    "run-away": 3,
    "sand-force": 5,
    "sand-rush": 5,
    "sand-spit": 8,
    "sand-stream": 3,
    "sand-veil": 3,
    "sap-sipper": 5,
    "schooling": 7,
    "scrappy": 4,
    "screen-cleaner": 8,
    "seed-sower": 9,
    "serene-grace": 3,
    "shadow-shield": 7,
    "shadow-tag": 3,
    "sharpness": 9,
    "shed-skin": 3,
    "sheer-force": 5,
    "shell-armor": 3,
    "shield-dust": 3,
    "shields-down": 7,
    "simple": 4,
    "skill-link": 4,
    "slow-start": 4,
    "slush-rush": 7,
    "sniper": 4,
    "snow-cloak": 4,
    "snow-warning": 4,
    "solar-power": 4,
    "solid-rock": 4,
    "soul-heart": 7,
    "soundproof": 3,
    "speed-boost": 3,
    "stakeout": 7,
    "stall": 4,
    "stalwart": 8,
    "stamina": 7,
    "stance-change": 6,
    "static": 3,
    "steadfast": 4,
    "steam-engine": 8,
    "steelworker": 7,
    "stench": 3,
    "sticky-hold": 3,
    "storm-drain": 4,
    "strong-jaw": 6,
    "sturdy": 3,
    "suction-cups": 3,
    "super-luck": 4,
    "supreme-overlord": 9,
    "surf-tail": 9,
    "surge-surfer": 7,
    "swarm": 3,
    "sweet-veil": 6,
    "swift-swim": 3,
    "sword-of-ruin": 9,
    "symbiosis": 6,
    "synchronize": 3,
    "tablets-of-ruin": 9,
    "tail-wind": 4,  # This is a move, not an ability
    "tangled-feet": 4,
    "tangling-hair": 7,
    "technician": 4,
    "telepathy": 5,
    "tera-shell": 9,
    "tera-shift": 9,
    "teraform-zero": 9,
    "teravolt": 5,
    "thick-fat": 3,
    "tinted-lens": 4,
    "torrent": 3,
    "tough-claws": 6,
    "toxic-boost": 4,
    "toxic-debris": 9,
    "trace": 3,
    "transistor": 7,
    "triage": 7,
    "truant": 3,
    "turboblaze": 5,
    "unaware": 4,
    "unburden": 4,
    "unnerve": 5,
    "unseen-fist": 8,
    "vessel-of-ruin": 9,
    "victory-star": 5,
    "vital-spirit": 3,
    "volt-absorb": 3,
    "wandering-spirit": 8,
    "water-absorb": 3,
    "water-bubble": 7,
    "water-compaction": 7,
    "water-veil": 3,
    "weak-armor": 5,
    "well-baked-body": 9,
    "white-smoke": 3,
    "wimp-out": 7,
    "wind-power": 9,
    "wind-rider": 9,
    "wonder-guard": 3,
    "wonder-skin": 5,
    "zen-mode": 5,
    "zero-to-hero": 9,
}

# ============================================================================
# TYPE AVAILABILITY
# ============================================================================

TYPE_GENERATIONS: Dict[str, int] = {
    "Normal": 1,
    "Fire": 1,
    "Water": 1,
    "Electric": 1,
    "Grass": 1,
    "Ice": 1,
    "Fighting": 1,
    "Poison": 1,
    "Ground": 1,
    "Flying": 1,
    "Psychic": 1,
    "Bug": 1,
    "Rock": 1,
    "Ghost": 1,
    "Dragon": 1,
    "Dark": 2,      # Introduced Gen 2
    "Steel": 2,     # Introduced Gen 2
    "Fairy": 6,     # Introduced Gen 6
}

# ============================================================================
# MECHANIC AVAILABILITY
# ============================================================================

MECHANIC_GENERATIONS = {
    "abilities": 3,           # Abilities introduced Gen 3
    "held_items": 2,          # Held items introduced Gen 2
    "double_battles": 3,      # Double battles introduced Gen 3
    "physical_special_split": 4,  # Gen 4+ moves have individual phys/spec
    "mega_evolution": 6,      # Mega Evolution introduced Gen 6
    "z_moves": 7,             # Z-Moves introduced Gen 7
    "dynamax": 8,             # Dynamax introduced Gen 8
    "terastallization": 9,    # Terastallization introduced Gen 9
    "weather_permanent": 6,   # Gen 6+ weather from abilities is permanent
    "critical_hit_15x": 6,    # Gen 6+ crits are 1.5x (not 2x)
    "paralysis_50_speed": 7,  # Gen 7+ paralysis = 50% speed (not 25%)
    "burn_1_16": 7,           # Gen 7+ burn = 1/16 (not 1/8)
    "steel_poison_immune": 6, # Gen 6+ Steel is immune to Poison
    "steel_resists_ghost_dark": 5,  # Gen 2-5 only
}

# ============================================================================
# FORM GENERATIONS
# ============================================================================

FORM_GENERATIONS: Dict[str, int] = {
    # Alolan forms - Gen 7
    "alolan": 7,
    
    # Galarian forms - Gen 8
    "galarian": 8,
    
    # Hisuian forms - Gen 8 (Legends Arceus)
    "hisuian": 8,
    
    # Paldean forms - Gen 9
    "paldean": 9,
    
    # Mega forms - Gen 6
    "mega": 6,
    
    # Gigantamax forms - Gen 8
    "gigantamax": 8,
    "gmax": 8,
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_ability_generation(ability_name: str) -> int:
    """Get the generation an ability was introduced in."""
    normalized = ability_name.lower().replace(" ", "-").strip()
    return ABILITY_GENERATIONS.get(normalized, 3)  # Default to Gen 3 (first abilities)

def get_type_generation(type_name: str) -> int:
    """Get the generation a type was introduced in."""
    return TYPE_GENERATIONS.get(type_name.title(), 1)  # Default to Gen 1

def is_mechanic_available(mechanic: str, generation: int) -> bool:
    """Check if a mechanic is available in the given generation."""
    required_gen = MECHANIC_GENERATIONS.get(mechanic, 1)
    return generation >= required_gen

def get_form_generation(form_name: str) -> int:
    """Get the generation a form type was introduced in."""
    if not form_name:
        return 1
    
    form_lower = form_name.lower()
    for form_type, gen in FORM_GENERATIONS.items():
        if form_type in form_lower:
            return gen
    return 1  # Default to Gen 1 for base forms

# ============================================================================
# GENERATION METADATA
# ============================================================================

GENERATION_INFO = {
    1: {
        "name": "Generation I",
        "games": ["Red", "Blue", "Yellow"],
        "region": "Kanto",
        "pokemon_count": 151,
        "new_types": [],
        "new_mechanics": ["basics"],
    },
    2: {
        "name": "Generation II",
        "games": ["Gold", "Silver", "Crystal"],
        "region": "Johto",
        "pokemon_count": 251,
        "new_types": ["Dark", "Steel"],
        "new_mechanics": ["held_items", "breeding"],
    },
    3: {
        "name": "Generation III",
        "games": ["Ruby", "Sapphire", "Emerald", "FireRed", "LeafGreen"],
        "region": "Hoenn",
        "pokemon_count": 386,
        "new_types": [],
        "new_mechanics": ["abilities", "double_battles", "natures"],
    },
    4: {
        "name": "Generation IV",
        "games": ["Diamond", "Pearl", "Platinum", "HeartGold", "SoulSilver"],
        "region": "Sinnoh",
        "pokemon_count": 493,
        "new_types": [],
        "new_mechanics": ["physical_special_split"],
    },
    5: {
        "name": "Generation V",
        "games": ["Black", "White", "Black 2", "White 2"],
        "region": "Unova",
        "pokemon_count": 649,
        "new_types": [],
        "new_mechanics": ["hidden_abilities", "triple_battles"],
    },
    6: {
        "name": "Generation VI",
        "games": ["X", "Y", "Omega Ruby", "Alpha Sapphire"],
        "region": "Kalos",
        "pokemon_count": 721,
        "new_types": ["Fairy"],
        "new_mechanics": ["mega_evolution", "weather_permanent", "critical_hit_15x"],
    },
    7: {
        "name": "Generation VII",
        "games": ["Sun", "Moon", "Ultra Sun", "Ultra Moon"],
        "region": "Alola",
        "pokemon_count": 809,
        "new_types": [],
        "new_mechanics": ["z_moves", "alolan_forms", "paralysis_50_speed", "burn_1_16"],
    },
    8: {
        "name": "Generation VIII",
        "games": ["Sword", "Shield", "Brilliant Diamond", "Shining Pearl", "Legends: Arceus"],
        "region": "Galar",
        "pokemon_count": 905,
        "new_types": [],
        "new_mechanics": ["dynamax", "galarian_forms", "hisuian_forms"],
    },
    9: {
        "name": "Generation IX",
        "games": ["Scarlet", "Violet"],
        "region": "Paldea",
        "pokemon_count": 1025,
        "new_types": [],
        "new_mechanics": ["terastallization", "paldean_forms"],
    },
}





