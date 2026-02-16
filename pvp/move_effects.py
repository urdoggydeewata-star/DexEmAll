"""
Comprehensive Move Effects System
Status moves, secondary effects, stat changes, etc.
"""
from typing import Dict, Any, List, Optional, Tuple
import random


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _get_effective_weight(mon: Any) -> float:
    """
    Get the effective weight of a Pokémon, accounting for Heavy Metal, Light Metal abilities, and items.
    
    Heavy Metal: Doubles weight
    Light Metal: Halves weight
    Autotomize: Reduces weight by 100 kg (applied first)
    Float Stone: Halves weight (Gen 5+, minimum 0.1 kg)
    """
    # Get base weight (use stored pre-Autotomize weight if available, otherwise current weight)
    if hasattr(mon, '_weight_before_autotomize'):
        base_weight = mon._weight_before_autotomize
    else:
        base_weight = getattr(mon, 'weight_kg', 100.0)
    
    # Autotomize: Reduces weight by 100 kg (applied FIRST, before abilities/items)
    # This is critical for Float Stone interaction (Float Stone halves the reduced weight)
    if hasattr(mon, '_autotomize_used') and mon._autotomize_used:
        base_weight = max(0.1, base_weight - 100.0)  # Minimum 0.1 kg
    
    # Check for ability-based weight modifications
    if hasattr(mon, 'ability') and mon.ability:
        from .abilities import normalize_ability_name, get_ability_effect
        ability = normalize_ability_name(mon.ability)
        ability_data = get_ability_effect(ability)
        
        # Heavy Metal: Double weight
        if ability_data.get("doubles_weight"):
            base_weight *= 2.0
        # Light Metal: Halve weight
        elif ability_data.get("halves_weight"):
            base_weight *= 0.5
    
    # === FLOAT STONE: Halves holder's weight (Gen 5+) ===
    if hasattr(mon, 'item') and mon.item:
        from .items import normalize_item_name, get_item_effect
        from .generation import get_generation
        item_norm = normalize_item_name(mon.item)
        item_data = get_item_effect(item_norm)
        
        # Get generation from field_effects if available
        generation = 9  # Default
        if hasattr(mon, '_battle_context') and mon._battle_context:
            generation = get_generation(field_effects=mon._battle_context.get('field_effects'))
        
        if item_data.get("weight_multiplier") and generation >= 5:
            # Float Stone: weight_multiplier = 0.5
            base_weight *= item_data["weight_multiplier"]
            # Minimum weight check (already handled at end, but Float Stone has explicit minimum)
            minimum_weight = item_data.get("minimum_weight", 0.1)
            if base_weight < minimum_weight:
                base_weight = minimum_weight
    
    return max(0.1, base_weight)  # Minimum 0.1 kg to avoid division by zero


# ============================================================================
# SECONDARY EFFECT DATABASE
# ============================================================================

MOVE_SECONDARY_EFFECTS: Dict[str, Dict[str, Any]] = {
    
    # ========== ELECTRIC MOVES WITH PARALYSIS ==========
    "thunder-shock": {"chance": 0.1, "status": "par", "gen_specific": {"1": {"cannot_paralyze_electric": True}, "2-5": {"can_paralyze_electric": True}, "6+": {"cannot_paralyze_electric": True}}},
    "thunderbolt": {"chance": 0.1, "status": "par", "gen_specific": {"1": {"power": 95, "cannot_paralyze_electric": True}, "2-5": {"power": 95, "can_paralyze_electric": True}, "6+": {"power": 90, "cannot_paralyze_electric": True}}},
    "thunder": {"chance": 0.3, "status": "par", "gen_specific": {"1": {"power": 120, "chance": 0.1, "cannot_paralyze_electric": True}, "2-5": {"power": 120, "chance": 0.3, "can_paralyze_electric": True, "always_hit_in_rain": True, "accuracy_50_in_sun": True, "hits_semi_invulnerable": True}, "6+": {"power": 110, "cannot_paralyze_electric": True}}},
    "spark": {"chance": 0.3, "status": "par"},
    "discharge": {"chance": 0.3, "status": "par", "hits_adjacent": True},
    "thunder-fang": {
        "chance": 0.1,
        "status": "par",
        "flinch": 0.1,
        "gen_specific": {
            "4": {"affected_by_kings_rock": True},
            "5+": {"not_affected_by_kings_rock": True}
        }
    },
    "thunder-punch": {"chance": 0.1, "status": "par"},
    "shock-wave": {"never_miss": True},  # Never misses (bypasses accuracy checks)
    "volt-tackle": {"chance": 0.1, "status": "par", "recoil": 0.33},
    "wild-charge": {"recoil": 0.25},
    "bolt-strike": {"chance": 0.2, "status": "par"},
    "fusion-bolt": {
        "chance": 0.2,
        "status": "par",
        "boosted_if_fusion_flare": True,
        "gen_specific": {"9+": {"banned": True}}
    },
    "nuzzle": {"chance": 1.0, "status": "par"},  # Always paralyzes
    "thunder-wave": {"status_move": True, "status": "par", "accuracy": 90, "gen_specific": {"1": {"can_hit_substitute": True, "accuracy": 100}, "2": {"fail_chance": 0.25, "accuracy": 100}, "3-5": {"accuracy": 100}, "6": {"accuracy": 100, "cannot_paralyze_electric": True}, "7+": {"accuracy": 90, "cannot_paralyze_electric": True}}},
    "stun-spore": {"status_move": True, "status": "par", "accuracy": 75},
    "glare": {"status_move": True, "status": "par", "accuracy": 100, "gen_specific": {"1": {"accuracy": 75}, "5": {"accuracy": 90}}},  # Gen I: 75%, Gen II-IV: 75%, Gen V: 90%, Gen VI+: 100%
    "body-slam": {"chance": 0.3, "status": "par", "doubled_minimize": True},
    "lick": {"chance": 0.3, "status": "par"},
    "force-palm": {"chance": 0.3, "status": "par"},
    "bounce": {"chance": 0.3, "status": "par"},
    "zing-zap": {"chance": 0.3, "flinch": 0.3},
    
    # ========== FIRE MOVES WITH BURN ==========
    "ember": {"chance": 0.1, "status": "brn"},
    "flamethrower": {"chance": 0.1, "status": "brn"},
    "fire-blast": {"chance": 0.1, "status": "brn", "gen_specific": {"1": {"chance": 0.3}, "power": {"1-5": 120, "6+": 110}}},  # Gen I: 30% burn, Gen II-V: 10% burn; Power: 120 Gen I-V, 110 Gen VI+
    "flame-wheel": {"chance": 0.1, "status": "brn"},
    "fire-punch": {"chance": 0.1, "status": "brn"},
    "blaze-kick": {"chance": 0.1, "status": "brn", "high_crit": True},
    "sacred-fire": {"chance": 0.5, "status": "brn"},
    "heat-wave": {"chance": 0.1, "status": "brn", "wind_move": True, "gen_specific": {"3-5": {"power": 100}, "6+": {"power": 95}}},
    "lava-plume": {"chance": 0.3, "status": "brn", "hits_adjacent": True},
    "scald": {"chance": 0.3, "status": "brn", "thaws_user": True, "thaws_target_on_hit": True},
    "steam-eruption": {
        "chance": 0.3,
        "status": "brn",
        "thaws_user": True,
        "thaws_target_on_hit": True
    },
    "fire-fang": {
        "chance": 0.1,
        "status": "brn",
        "flinch": 0.1,
        "gen_specific": {
            "4": {"affected_by_kings_rock": True},
            "5+": {"not_affected_by_kings_rock": True}
        }
    },
    "searing-shot": {"chance": 0.3, "status": "brn", "bulletproof_immune": True, "gen_specific": {"9+": {"banned": True}}},
    "inferno": {"chance": 1.0, "status": "brn", "accuracy": 50},
    "will-o-wisp": {"status_move": True, "status": "brn", "accuracy": 85, "gen_specific": {"3": {"accuracy": 75}, "4+": {"accuracy": 85}}},
    "blue-flare": {"chance": 0.2, "status": "brn"},
    "burning-jealousy": {"chance": 1.0, "burn_if_stats_raised": True},
    
    # ========== ICE MOVES WITH FREEZE ==========
    "ice-beam": {"chance": 0.1, "status": "frz"},
    "blizzard": {"chance": 0.1, "status": "frz"},
    "powder-snow": {"chance": 0.1, "status": "frz"},
    "ice-punch": {"chance": 0.1, "status": "frz"},
    "ice-fang": {
        "chance": 0.1,
        "status": "frz",
        "flinch": 0.1,
        "gen_specific": {
            "4": {"affected_by_kings_rock": True},
            "5+": {"not_affected_by_kings_rock": True}
        }
    },
    "frost-breath": {
        "always_crit": True,
        "gen_specific": {
            "5": {"power": 40},
            "6+": {"power": 60}
        }
    },
    "freeze-dry": {"chance": 0.1, "status": "frz"},
    "ice-shard": {},  # Priority, no secondary
    
    # ========== POISON MOVES ==========
    "poison-sting": {"chance": 0.3, "status": "psn"},
    "sludge": {"chance": 0.3, "status": "psn", "gen_specific": {"1": {"chance": 0.4}}},  # Gen I: 40%, Gen II+: 30%
    "sludge-bomb": {"chance": 0.3, "status": "psn"},
    "sludge-wave": {"chance": 0.1, "status": "psn"},
    "poison-jab": {"chance": 0.3, "status": "psn"},
    "poison-tail": {"chance": 0.1, "status": "psn", "high_crit": True},
    "cross-poison": {"chance": 0.1, "status": "psn", "high_crit": True},
    "gunk-shot": {
        "chance": 0.3,
        "status": "psn",
        "gen_specific": {
            "4-5": {"accuracy": 70},
            "6+": {"accuracy": 80}
        }
    },
    "poison-fang": {"chance": 0.3, "status": "tox", "gen_specific": {"3-5": {"chance": 0.3}, "6+": {"chance": 0.5}}},  # Gen III-V: 30%, Gen VI+: 50% badly poison
    "toxic": {"status_move": True, "status": "tox", "accuracy": 90, "gen_specific": {"1": {"accuracy": 85}, "2": {"fail_chance": 0.25, "steel_immunity": True}, "3-4": {"immunity_ability": "immunity"}, "5": {"accuracy": 90}, "6+": {"poison_type_never_miss": True, "sure_hit_glitch": True}}},
    "poison-gas": {"status_move": True, "status": "psn", "accuracy": 90, "gen_specific": {"1": {"accuracy": 55}, "5": {"accuracy": 80}}},  # Gen I: 55%, Gen V: 80%, Gen VI+: 90%
    "poison-powder": {"status_move": True, "status": "psn", "accuracy": 75},
    "toxic-spikes": {"hazard": "toxic-spikes"},
    "smog": {"chance": 0.4, "status": "psn", "gen_specific": {"power": {"1-5": 20, "6+": 30}}},  # Power: 20 Gen I-V, 30 Gen VI+
    "poison-tail": {"chance": 0.1, "status": "psn", "high_crit": True},
    "barb-barrage": {"chance": 0.5, "status": "psn"},
    "shell-side-arm": {"chance": 0.2, "status": "psn"},
    
    # ========== SLEEP MOVES ==========
    "sleep-powder": {"status_move": True, "status": "slp", "accuracy": 75},
    "spore": {"status_move": True, "status": "slp", "accuracy": 100, "grass_immune_gen6": True, "gen_specific": {"1": {"hits_substitute": True}}},
    "hypnosis": {"status_move": True, "status": "slp", "accuracy": 60, "gen_specific": {"1": {"can_hit_substitute": True}, "2": {"fail_chance": 0.25}, "3": {"immunity_abilities": ["insomnia", "vital-spirit"]}, "4": {"accuracy": 70}, "4-diamond-pearl": {"accuracy": 70}}},  # Diamond/Pearl: 70%, Platinum/others: 60%
    "lovely-kiss": {"status_move": True, "status": "slp", "accuracy": 75, "gen_specific": {"1": {"hits_substitute": True}}},
    "sing": {"status_move": True, "status": "slp", "accuracy": 55},
    "grass-whistle": {"status_move": True, "status": "slp", "accuracy": 55, "sound_move": True, "gen_specific": {"3-5": {"hits_substitute": False}, "6+": {"hits_substitute": True}, "8+": {"banned": True}}},  # Sound move, Gen VI+ hits behind substitute, Gen VIII+ banned
    "yawn": {"status_move": True, "status": "slp", "delayed": 1},
    "relic-song": {
        "chance": 0.1,
        "status": "slp",
        "sound_move": True,
        "hits_adjacent_foes": True,
        "changes_form": True,
        "gen_specific": {
            "5": {"hits_substitute": True},
            "6+": {"hits_substitute": True, "bypasses_substitute": True}
        }
    },
    
    # ========== CONFUSION ==========
    "confusion": {"chance": 0.1, "confuse": True},
    "psybeam": {"chance": 0.1, "confuse": True},
    "dynamic-punch": {"chance": 1.0, "confuse": True, "gen_specific": {"chance": {"2": 255/256}}},
    "signal-beam": {"chance": 0.1, "confuse": True},
    "water-pulse": {"chance": 0.2, "confuse": True},
    "rock-climb": {"chance": 0.2, "confuse": True},
    "confuse-ray": {"status_move": True, "confuse": True, "accuracy": 100},
    "supersonic": {"status_move": True, "confuse": True, "accuracy": 55},
    "sweet-kiss": {"status_move": True, "confuse": True, "accuracy": 75},
    "teeter-dance": {"status_move": True, "confuse": True, "accuracy": 100},
    "swagger": {"status_move": True, "confuse": True, "atk_boost": 2},
    "flatter": {"status_move": True, "confuse": True, "spa_boost": 1},
    
    # ========== FLINCH MOVES ==========
    "bite": {"chance": 0.3, "flinch": True},
    "headbutt": {"chance": 0.3, "flinch": True},
    "stomp": {"chance": 0.3, "flinch": True},
    "rolling-kick": {"chance": 0.3, "flinch": True},
    "needle-arm": {"chance": 0.3, "flinch": True, "gen_specific": {"3": {"doubled_minimize": True}}},  # Gen III: Double damage vs Minimize, Gen VIII+ banned
    "hyper-fang": {"chance": 0.1, "flinch": True},
    "bone-club": {"chance": 0.1, "flinch": True},
    "rock-slide": {"chance": 0.3, "flinch": True, "gen_specific": {"1": {"chance": 0.0}}},  # Gen I: No flinch, Gen II+: 30% flinch
    "twister": {"chance": 0.2, "flinch": True, "wind_move": True},  # Wind move (Gen VI+)
    "astonish": {"chance": 0.3, "flinch": True, "gen_specific": {"3": {"doubled_minimize": True}}},  # Gen III only: Double damage vs Minimize
    "air-slash": {
        "chance": 0.3,
        "flinch": True,
        "gen_specific": {
            "4": {"pp": 20, "affected_by_kings_rock": True},
            "5": {"pp": 20, "not_affected_by_kings_rock": True},
            "6+": {"pp": 15, "not_affected_by_kings_rock": True, "sharpness_boost": True}
        }
    },
    "iron-head": {
        "chance": 0.3,
        "flinch": True,
        "gen_specific": {
            "4": {"affected_by_kings_rock": True},
            "5+": {"not_affected_by_kings_rock": True}
        }
    },
    "zen-headbutt": {"chance": 0.2, "flinch": True},
    "waterfall": {"chance": 0.2, "flinch": True},
    "extrasensory": {"chance": 0.1, "flinch": True, "gen_specific": {"3": {"doubled_minimize": True}, "6+": {"pp": 20}}},  # Gen III: Double damage vs Minimize, Gen VI+: PP 20 (was 30)
    "fake-out": {"chance": 1.0, "flinch": True, "priority": 3, "first_turn_only": True},
    "icicle-crash": {"chance": 0.3, "flinch": True},
    "dragon-rush": {
        "chance": 0.2,
        "flinch": True,
        "doubled_minimize": True,
        "gen_specific": {
            "4": {"affected_by_kings_rock": True},
            "5+": {"not_affected_by_kings_rock": True}
        }
    },
    
    # ========== STAT DROP MOVES (OFFENSIVE) ==========
    "aurora-beam": {"chance": 0.1, "stat_drop": {"atk": -1}, "gen_specific": {"1": {"chance": 85/256, "fail_chance_opponent": 0.25}, "2": {"chance": 0.1, "fail_chance_opponent": 0.25, "no_fail_if_lock_on_mind_reader": True}, "3+": {"chance": 0.1}}},
    "bubble": {"chance": 0.1, "stat_drop": {"spe": -1}, "gen_specific": {"1": {"chance": 0.332}}},  # Gen I: 33.2% Speed drop, Gen II+: 10%
    "bubble-beam": {"chance": 0.1, "stat_drop": {"spe": -1}},
    "acid": {"chance": 0.1, "stat_drop": {"spd": -1}},
    "acid-spray": {"chance": 1.0, "stat_drop": {"spd": -2}},
    "constrict": {"chance": 0.1, "stat_drop": {"spe": -1}},
    "crunch": {"chance": 0.2, "stat_drop": {"defn": -1}, "gen_specific": {"2-3": {"stat_drop": {"spd": -1}}, "4+": {"stat_drop": {"defn": -1}}}},
    "crush-claw": {"chance": 0.5, "stat_drop": {"defn": -1}},
    "earth-power": {"chance": 0.1, "stat_drop": {"spd": -1}},
    "energy-ball": {
        "chance": 0.1,
        "stat_drop": {"spd": -1},
        "gen_specific": {
            "4-5": {"power": 80},
            "6+": {"power": 90}
        }
    },
    "fake-tears": {"status_move": True, "stat_drop": {"spd": -2}},
    "feather-dance": {"status_move": True, "stat_drop": {"atk": -2}},
    "flash-cannon": {"chance": 0.1, "stat_drop": {"spd": -1}},
    "hammer-arm": {"self_stat_drop": {"spe": -1}},
    "icy-wind": {"chance": 1.0, "stat_drop": {"spe": -1}},
    "low-sweep": {"chance": 1.0, "stat_drop": {"spe": -1}},
    "lunge": {"chance": 1.0, "target_stat_drop": {"atk": -1}},
    "metal-sound": {"status_move": True, "stat_drop": {"spd": -2}, "sound_move": True, "gen_specific": {"3-5": {"hits_substitute": False}, "6+": {"hits_substitute": True}}},  # Sound move, Gen VI+ hits behind substitute
    "moonblast": {"chance": 0.3, "stat_drop": {"spa": -1}},
    "mystical-fire": {"chance": 1.0, "stat_drop": {"spa": -1}},
    "play-rough": {"chance": 0.1, "stat_drop": {"atk": -1}},
    "psychic": {"chance": 0.1, "stat_drop": {"spd": -1}, "gen_specific": {"1": {"chance": 0.332, "stat_drop": {"special": -1}, "fail_chance": 0.25}, "2": {"chance": 0.1, "stat_drop": {"spd": -1}, "fail_chance": 0.25}, "3+": {"chance": 0.1, "stat_drop": {"spd": -1}}}},
    "razor-shell": {"chance": 0.5, "stat_drop": {"defn": -1}, "sharpness_boost": True},
    "rock-smash": {"chance": 0.5, "stat_drop": {"defn": -1}},
    "sand-attack": {"status_move": True, "stat_drop": {"accuracy": -1}},
    "scary-face": {"status_move": True, "stat_drop": {"spe": -2}},
    "screech": {"status_move": True, "stat_drop": {"defn": -2}, "sound_move": True, "gen_specific": {"6+": {"hits_substitute": True}}},
    "seed-flare": {"chance": 0.4, "stat_drop": {"spd": -2}},
    "shadow-ball": {"chance": 0.2, "stat_drop": {"spd": -1}},
    "snarl": {
        "chance": 1.0,
        "stat_drop": {"spa": -1},
        "sound_move": True,
        "hits_adjacent_foes": True,
        "gen_specific": {
            "5": {"hits_substitute": True},
            "6+": {"bypasses_substitute": True}
        }
    },
    "string-shot": {"status_move": True, "stat_drop": {"spe": -2}},
    "struggle-bug": {"chance": 1.0, "stat_drop": {"spa": -1}},
    "superpower": {"self_stat_drop": {"atk": -1, "defn": -1}},
    "tickle": {"status_move": True, "target_stat_drop": {"atk": -1, "defn": -1}, "gen_specific": {"3": {"hits_substitute": True}, "4+": {"hits_substitute": False}}},  # Gen III: Not blocked by substitute, Gen IV+: Blocked
    "close-combat": {"self_stat_drop": {"defn": -1, "spd": -1}},  # 120 BP Fighting
    "draco-meteor": {
        "self_stat_drop": {"spa": -2},
        "gen_specific": {
            "4-5": {"power": 140},
            "6+": {"power": 130}
        }
    },  # 130 BP Dragon special
    "stone-edge": {"high_crit": True},  # 100 BP Rock physical
    "earthquake": {"hits_adjacent": True, "gen_specific": {"1": {}, "2": {"hits_semi_invulnerable_dig": True, "doubled_power_vs_dig": True}, "3-4": {"hits_all_adjacent": True, "affected_by_kings_rock": True}, "5+": {"hits_semi_invulnerable_dig": True, "doubled_damage_vs_dig": True, "halved_in_grassy_terrain": True}}},  # 100 BP Ground physical, hits all adjacent (handled in engine)
    "hydro-pump": {},  # 110 BP Water special
    "shadow-bone": {"chance": 0.2, "stat_drop": {"defn": -1}},  # 85 BP Ghost physical
    "tar-shot": {
        "status_move": True,
        "target_stat_drop": {"spe": -1},
        "adds_fire_weakness": True,
        "gen_specific": {
            "8-brilliant-diamond-shining-pearl": {"banned": True}
        }
    },
    "octolock": {"status_move": True, "stat_drop_each_turn": {"defn": -1, "spd": -1}, "traps_opponent": True},
    "eerie-impulse": {
        "status_move": True,
        "stat_drop": {"spa": -2},
        "z_boost_effect": {"stat_boost": {"spd": 1}}
    },
    "parting-shot": {
        "status_move": True,
        "stat_drop": {"atk": -1, "spa": -1},
        "forces_self_switch": True,
        "sound_move": True,
        "hits_substitute": True,
        "gen_specific": {
            "6": {"switches_even_if_stat_blocked": True},
            "7+": {"switches_even_if_stat_blocked": False}
        },
        "z_boost_effect": {"heals_switch_in": True}
    },
    "trop-kick": {"chance": 1.0, "target_stat_drop": {"atk": -1}},  # 70 BP Grass physical
    "mirror-shot": {"chance": 0.3, "stat_drop": {"accuracy": -1}},  # 65 BP Steel special
    "octazooka": {"chance": 0.5, "stat_drop": {"accuracy": -1}},  # 65 BP Water special
    "mud-bomb": {
        "chance": 0.3,
        "stat_drop": {"accuracy": -1},
        "gen_specific": {
            "6-7": {"bulletproof_immune": True},
            "8+": {"banned": True}
        }
    },  # 65 BP Ground special
    "thunderous-kick": {"chance": 1.0, "stat_drop": {"defn": -1}},  # 90 BP Fighting physical
    
    # ========== STAT BOOST MOVES (SELF) ==========
    "ancient-power": {"chance": 0.1, "stat_boost": {"atk": 1, "defn": 1, "spa": 1, "spd": 1, "spe": 1}},
    "charge-beam": {"chance": 0.7, "stat_boost": {"spa": 1}},
    "meteor-mash": {"chance": 0.2, "stat_boost": {"atk": 1}, "gen_specific": {"3-5": {"power": 100, "accuracy": 85}, "6+": {"power": 90, "accuracy": 90}}},  # Gen III-V: 100 BP/85% acc, Gen VI+: 90 BP/90% acc
    "ominous-wind": {
        "chance": 0.1,
        "stat_boost": {"atk": 1, "defn": 1, "spa": 1, "spd": 1, "spe": 1},
        "gen_specific": {"8+": {"banned": True}}
    },
    "power-up-punch": {
        "chance": 1.0,
        "stat_boost": {"atk": 1},
        "gen_specific": {"9+": {"banned": True}}
    },
    "hold-back": {"leaves_1hp": True, "gen_specific": {"8+": {"banned": True}}},
    "silver-wind": {"chance": 0.1, "stat_boost": {"atk": 1, "defn": 1, "spa": 1, "spd": 1, "spe": 1}},
    "steel-wing": {"chance": 0.1, "stat_boost": {"defn": 1}},
    
    # ========== SETUP MOVES (STATUS) - SELF STAT BOOSTS ==========
    "swords-dance": {"status_move": True, "stat_boost": {"atk": 2}},
    "dragon-dance": {"status_move": True, "stat_boost": {"atk": 1, "spe": 1}},
    "calm-mind": {"status_move": True, "stat_boost": {"spa": 1, "spd": 1}},
    "nasty-plot": {"status_move": True, "stat_boost": {"spa": 2}},
    "bulk-up": {"status_move": True, "stat_boost": {"atk": 1, "defn": 1}},
    "agility": {"status_move": True, "stat_boost": {"spe": 2}},  # Always +2 Speed, no generation changes
    "shell-smash": {
        "status_move": True,
        "stat_boost": {"atk": 2, "spa": 2, "spe": 2},
        "self_stat_drop": {"defn": -1, "spd": -1},
        "z_boost_effect": {"reset_lower_stats": True}
    },
    "quiver-dance": {"status_move": True, "stat_boost": {"spa": 1, "spd": 1, "spe": 1}},
    "coil": {"status_move": True, "stat_boost": {"atk": 1, "defn": 1, "accuracy": 1}},
    "shift-gear": {"status_move": True, "stat_boost": {"atk": 1, "spe": 2}},
    "curse": {"status_move": True, "stat_boost": {"atk": 1, "defn": 1}, "self_stat_drop": {"spe": -1}},
    "power-trick": {"status_move": True, "swaps_atk_def": True, "gen_specific": {"4": {"snatchable": False, "baton_passable": True}, "5+": {"snatchable": True, "baton_passable": True}}},  # Gen IV: Not Snatchable, Gen V+: Snatchable, Baton Passable
    "growth": {"status_move": True, "stat_boost": {"spa": 1}, "gen_specific": {"1": {"stat_boost": {"special": 1}}, "2-4": {"stat_boost": {"spa": 1}}, "5": {"stat_boost": {"atk": 1, "spa": 1}, "sun_boost": {"atk": 2, "spa": 2}}, "6+": {"pp": 20, "stat_boost": {"atk": 1, "spa": 1}, "sun_boost": {"atk": 2, "spa": 2}}}},
    "hone-claws": {"status_move": True, "stat_boost": {"atk": 1, "accuracy": 1}},
    "work-up": {
        "status_move": True,
        "stat_boost": {"atk": 1, "spa": 1},
        "z_boost_effect": {"stat_boost": {"atk": 1}}
    },
    "double-team": {"status_move": True, "stat_boost": {"evasion": 1}},
    "minimize": {"status_move": True, "stat_boost": {"evasion": 2}},
    "acupressure": {"status_move": True, "stat_boost_random": True, "gen_specific": {"1-4": {"snatchable": True}, "5+": {"snatchable": False}}},  # Random stat +2, Gen I-IV: Stolen by Snatch, Gen V+: Not stolen by Snatch
    "iron-defense": {"status_move": True, "stat_boost": {"defn": 2}},
    "amnesia": {"status_move": True, "stat_boost": {"spd": 2}, "gen_specific": {"1": {"stat_boost": {"special": 2}}}},  # Gen I: Raises Special (combined stat), Gen II+: Raises Special Defense
    "rock-polish": {"status_move": True, "stat_boost": {"spe": 2}},
    
    # ========== OPPONENT STAT DROP MOVES (STATUS) ==========
    "growl": {"status_move": True, "target_stat_drop": {"atk": -1}},
    "leer": {"status_move": True, "target_stat_drop": {"defn": -1}},
    "tail-whip": {"status_move": True, "target_stat_drop": {"defn": -1}},
    "charm": {"status_move": True, "target_stat_drop": {"atk": -2}},
    "sweet-kiss": {"status_move": True, "confuses": True},  # Causes confusion, Gen II-V: Normal-type, Gen VI+: Fairy-type
    "kinesis": {"status_move": True, "target_stat_drop": {"accuracy": -1}, "gen_specific": {"1-3": {"reflected_by_magic_coat": False}, "4+": {"reflected_by_magic_coat": True}}},  # Gen I-III: Not reflected by Magic Coat, Gen IV+: Reflected by Magic Coat
    "smokescreen": {"status_move": True, "target_stat_drop": {"accuracy": -1}},
    "flash": {"status_move": True, "target_stat_drop": {"accuracy": -1}, "gen_specific": {"1-2": {"accuracy": 70}, "4-7": {"accuracy": 100}}},  # Gen I-II: 70%, Gen IV-VII: 100%
    # Note: string-shot, scary-face, screech, fake-tears, tickle, sand-attack already defined above in offensive section
    
    # ========== RECOIL MOVES ==========
    "double-edge": {"recoil": 0.33},
    "take-down": {"recoil": 0.25},
    "submission": {"recoil": 0.25, "gen_specific": {"1": {"no_recoil_on_ko": True, "no_recoil_on_substitute": True}, "6": {"pp": 20}, "9": {"banned": True}}},
    "brave-bird": {"recoil": 0.33},
    "flare-blitz": {"recoil": 0.33, "chance": 0.1, "status": "brn", "thaws_user": True},  # Recoil 33%, 10% burn, thaws user if frozen
    "head-charge": {"recoil": 0.25, "gen_specific": {"9+": {"banned": True}}},
    "head-smash": {"recoil": 0.5},
    "volt-tackle": {"recoil": 0.33, "gen_specific": {"3": {"category": "special"}, "4+": {"chance": 0.1, "status": "par", "category": "physical"}}},  # Gen III: Special, no paralysis, Gen IV+: Physical, 10% paralysis
    "wild-charge": {"recoil": 0.25},
    "wood-hammer": {"recoil": 0.33},
    "struggle": {"recoil": 0.25, "typeless": True},
    "chloroblast": {"recoil": 0.5},  # Gen 8, 150 BP Grass special
    "wave-crash": {"recoil": 0.33},  # Gen 8, 120 BP Water physical
    "light-of-ruin": {"recoil": 0.5, "gen_specific": {"8+": {"banned": True}}},  # Gen 6, 140 BP Fairy special
    
    # ========== DRAINING MOVES ==========
    "absorb": {"drain": 0.5, "gen_specific": {"1": {"power": 20, "pp": 20, "misses_if_substitute": True, "no_heal_if_substitute_broken": True}, "3": {"heals_on_substitute": True, "affected_by_liquid_ooze": True}, "4": {"pp": 25, "boosted_by_big_root": True}, "5": {"affected_by_kings_rock": True}, "6": {"blocked_by_heal_block": True}, "7": {"power": 40, "pp": 15}, "8+": {"power": 20, "pp": 25}}},
    "mega-drain": {"drain": 0.5, "gen_specific": {"1": {"power": 40, "pp": 10, "misses_if_substitute": True, "no_heal_if_substitute_broken": True}, "3": {"heals_on_substitute": True, "affected_by_liquid_ooze": True}, "4": {"pp": 15, "boosted_by_big_root": True}, "5": {"affected_by_kings_rock": True}, "6": {"blocked_by_heal_block": True}, "7": {"power": 75, "pp": 10}, "8+": {"power": 40, "pp": 15}}},
    "giga-drain": {"drain": 0.5},
    "drain-punch": {
        "drain": 0.5,
        "gen_specific": {
            "4": {"power": 60, "pp": 5},
            "5": {"power": 75, "pp": 10},
            "6+": {"power": 75, "pp": 10, "blocked_by_heal_block": True}
        }
    },
    "draining-kiss": {"drain": 0.75},
    "dream-eater": {"drain": 0.5, "requires_sleep": True},
    "horn-leech": {
        "drain": 0.5,
        "gen_specific": {
            "6+": {"blocked_by_heal_block": True}
        }
    },
    "leech-life": {"drain": 0.5},
    "oblivion-wing": {"drain": 0.75, "gen_specific": {"9+": {"banned": True}}},
    "parabolic-charge": {
        "drain": 0.5,
        "gen_specific": {
            "6": {"power": 50, "blocked_by_heal_block": True},
            "7+": {"power": 65, "blocked_by_heal_block": True}
        }
    },
    "strength-sap": {
        "status_move": True,
        "strength_sap": True,
        "stat_drop": {"atk": -1},
        "z_boost_effect": {"stat_boost": {"defn": 1}}
    },  # Heals equal to target's Attack stat
    
    # ========== OHKO MOVES ==========
    "fissure": {"ohko": True, "accuracy": 30, "gen_specific": {"1": {"damage": 65535, "speed_check": True, "accuracy": 30, "affected_by_immunities": True}, "2": {"damage": "current_hp", "level_based_accuracy": True, "accuracy_formula": True, "affected_by_evasion": True, "can_counter": True}, "3+": {"damage": "current_hp", "level_based_accuracy": True, "not_affected_by_evasion": True, "cannot_hit_semi_invulnerable": True, "fails_vs_dynamax": True}}},
    "guillotine": {"ohko": True, "accuracy": 30},
    "horn-drill": {"ohko": True, "accuracy": 30},
    "sheer-cold": {"ohko": True, "accuracy": 30, "gen_specific": {"3-6": {"base_accuracy": 30, "ice_immune": False}, "7+": {"base_accuracy": 20, "ice_immune": True, "non_ice_base": 20}}},  # Gen III-VI: 30% base (or level formula), Gen VII+: Ice immune, 20% base if non-Ice user (or level formula)
    
    # ========== MULTI-HIT MOVES ==========
    "double-kick": {"multi_hit": 2},
    "double-slap": {"multi_hit": "2-5"},
    "fury-attack": {"multi_hit": "2-5"},
    "fury-swipes": {"multi_hit": "2-5"},
    "pin-missile": {"multi_hit": "2-5"},
    "spike-cannon": {"multi_hit": "2-5"},
    "barrage": {"multi_hit": "2-5"},
    "comet-punch": {"multi_hit": "2-5"},
    "bone-rush": {"multi_hit": "2-5"},
    "icicle-spear": {"multi_hit": "2-5"},
    "rock-blast": {"multi_hit": "2-5"},
    "bullet-seed": {"multi_hit": "2-5", "gen_specific": {"3": {"power": 10, "category": "special"}, "4": {"power": 10, "category": "physical"}, "5+": {"power": 25, "category": "physical"}}},  # Gen III: 10 BP special, Gen IV: 10 BP physical, Gen V+: 25 BP physical
    "tail-slap": {"multi_hit": "2-5"},
    "scale-shot": {"multi_hit": "2-5", "not_affected_by_sheer_force": True},
    "arm-thrust": {"multi_hit": "2-5"},
    "water-shuriken": {"multi_hit": "2-5", "priority": 1},
    "double-iron-bash": {"multi_hit": 2, "chance": 0.3, "flinch": True},
    "dual-chop": {"multi_hit": 2, "gen_specific": {"9+": {"banned": True}}},
    "dual-wingbeat": {"multi_hit": 2},
    "bonemerang": {"multi_hit": 2},
    "dragon-darts": {
        "multi_hit": 2,
        "gen_specific": {
            "8-brilliant-diamond-shining-pearl": {"banned": True}
        }
    },
    "gear-grind": {"multi_hit": 2, "gen_specific": {"9+": {"banned": True}}},
    "surging-strikes": {"multi_hit": 3, "always_crit": True},
    "triple-axel": {"multi_hit": 3, "increasing_power": True},
    "triple-kick": {"multi_hit": 3, "increasing_power": True},
    "population-bomb": {"multi_hit": "1-10", "accuracy": 90},
    
    # ========== PRIORITY MOVES ==========
    # Priority +1
    "quick-attack": {"priority": 1, "gen_specific": {"1": {"priority_carries_through_sleep_freeze": True}}},
    "aqua-jet": {"priority": 1},
    "bullet-punch": {"priority": 1},
    "mach-punch": {"priority": 1},
    "ice-shard": {"priority": 1},
    "shadow-sneak": {"priority": 1},
    "accelerock": {"priority": 1},
    "vacuum-wave": {"priority": 1},
    "water-shuriken": {"priority": 1, "hits": "2-5"},
    "sucker-punch": {"priority": 1, "fails_if_status_move": True, "gen_specific": {"4": {"power": 80}, "5-6": {"power": 80, "succeeds_on_me_first": True}, "7+": {"power": 70}}},  # Gen IV-VI: 80 BP, Gen V+: Succeeds on Me First, Gen VII+: 70 BP
    "jet-punch": {"priority": 1},  # Gen 7, 60 BP Water physical
    "baby-doll-eyes": {
        "priority": 1,
        "status_move": True,
        "target_stat_drop": {"atk": -1},
        "z_boost_effect": {"stat_boost": {"defn": 1}}
    },
    "powder": {
        "priority": 1,
        "status_move": True,
        "disables_fire_moves": True,
        "blocked_by_magic_guard": True,
        "gen_specific": {"8+": {"banned": True}}
    },
    "ion-deluge": {"priority": 1, "status_move": True, "makes_normal_electric": True},
    "bide": {"priority": 1, "bide_mechanic": True},  # Special accumulating damage move
    "thunderclap": {"priority": 1},  # Gen 9, 70 BP Electric special, fails if target not attacking
    
    # Priority +2
    "extreme-speed": {"priority": 2, "gen_specific": {"2-4": {"priority": 1}, "5+": {"priority": 2}}},
    "feint": {"priority": 2, "breaks_protection": True},
    "first-impression": {"priority": 2, "first_turn_only": True},  # Gen 7, 90 BP Bug physical
    
    # Priority +3
    "fake-out": {"priority": 3, "chance": 1.0, "flinch": True, "first_turn_only": True},
    "quick-guard": {
        "priority": 3,
        "status_move": True,
        "protect_variant": "quick-guard",
        "blocks_priority": True,
        "z_boost_effect": {"stat_boost": {"defn": 1}},
        "fails_if_moving_last": True,
        "gen_specific": {
            "5-6": {"shares_protect_counter": True, "prankster_status_bypass": True},
            "7+": {"always_succeeds": True}
        }
    },
    "wide-guard": {
        "priority": 3,
        "status_move": True,
        "blocks_spread": True,
        "protect_variant": "wide-guard"
    },  # Doubles move
    "crafty-shield": {
        "priority": 3,
        "status_move": True,
        "blocks_status": True,
        "protect_variant": "crafty-shield",
        "z_boost_effect": {"stat_boost": {"spd": 1}},
        "gen_specific": {"8+": {"banned": True}}
    },  # Doubles move
    "spotlight": {
        "priority": 3,
        "status_move": True,
        "forces_target": True,
        "z_boost_effect": {"stat_boost": {"spd": 1}},
        "gen_specific": {"8+": {"banned": True}}
    },  # Doubles move
    
    # Protection moves - Priority varies by generation (Gen II-IV: +3, Gen V+: +4)
    # Note: Priority is handled dynamically in engine.py based on generation
    "protect": {"status_move": True, "protection": True, "priority": 4},  # Default to +4, override in engine.py for Gen II-IV
    "detect": {"status_move": True, "protection": True, "priority": 4},  # Default to +4, override in engine.py for Gen II-IV
    "burning-bulwark": {"priority": 4, "status_move": True, "protection": "burning-bulwark"},  # Gen 9, burns on contact
    "silk-trap": {"priority": 4, "status_move": True, "protection": "silk-trap"},  # Gen 9, lowers Speed on contact
    
    # Priority +5
    "helping-hand": {"priority": 5, "status_move": True, "boosts_ally": 1.5},  # Doubles move
    
    # Negative Priority
    "vital-throw": {"priority": -1},  # Never misses but goes last
    "focus-punch": {"priority": -3, "fails_if_hit": True},  # 150 BP Fighting, fails if damaged
    "beak-blast": {"priority": -3, "burns_on_contact_this_turn": True},  # Burns if hit by contact move before attacking
    "shell-trap": {"priority": -3, "requires_physical_hit": True},  # Only works if hit by physical move
    "avalanche": {"priority": -4, "variable_power": "avalanche"},  # Double power if hit this turn
    "revenge": {"priority": -4, "variable_power": "revenge"},  # Double power if hit this turn
    "counter": {"priority": -5, "reflects_physical": 2.0, "gen_specific": {"1": {"priority": -1, "counters_normal_fighting_only": True, "type_ignored": True}, "2": {"counters_physical_only": True, "immunity": "ghost"}, "3": {"priority": -5}, "4": {"bypasses_protect": True}, "5+": {"blocked_by_protect": True, "affected_by_kings_rock": True}}},  # Returns 2x physical damage, Gen I-IV: Not blocked by Protect, Gen V+: Blocked by Protect
    "mirror-coat": {"priority": -5, "reflects_special": 2.0, "gen_specific": {"1-3": {"copied_by_mirror_move": True, "bypasses_protect": True}, "4": {"bypasses_protect": True}, "5+": {"blocked_by_protect": True}}},  # Returns 2x special damage, Gen I-III: Copied by Mirror Move, not blocked by Protect, Gen IV: Not copied by Mirror Move, not blocked by Protect, Gen V+: Blocked by Protect
    "circle-throw": {
        "priority": -6,
        "forces_switch": True,
        "force_switch_blocked_by_substitute": True,
        "force_switch_blocked_by_ingrain": True,
        "force_switch_blocked_by_suction_cups": True,
        "gen_specific": {"8+": {"fails_on_dynamax": True}}
    },  # Forces switch
    "dragon-tail": {
        "priority": -6,
        "forces_switch": True,
        "force_switch_blocked_by_substitute": True,
        "force_switch_blocked_by_ingrain": True,
        "force_switch_blocked_by_suction_cups": True,
        "gen_specific": {"8+": {"fails_on_dynamax": True}}
    },  # Forces switch
    "roar": {"priority": -6, "status_move": True, "forces_switch": True},  # Forces switch
    "whirlwind": {"priority": -6, "status_move": True, "forces_switch": True, "gen_specific": {"1-4": {"reflected_by_magic_coat": False}, "5+": {"reflected_by_magic_coat": True}}},  # Forces switch, Gen I-IV: Not reflected by Magic Coat, Gen V+: Reflected by Magic Coat
    "trick-room": {"priority": -7, "status_move": True, "field_effect": "trick-room", "duration": 5},  # Reverses speed order
    
    # ========== HAZARD MOVES ==========
    "stealth-rock": {"status_move": True, "hazard": "stealth-rock", "sets_hazard": "stealth-rock", "gen_specific": {"1-4": {"reflected_by_magic_coat": False}, "5+": {"reflected_by_magic_coat": True}}},  # Gen I-IV: Not reflected by Magic Coat, Gen V+: Reflected by Magic Coat
    "spikes": {"status_move": True, "hazard": "spikes", "gen_specific": {"1-4": {"reflected_by_magic_coat": False}, "5+": {"reflected_by_magic_coat": True}}},  # Gen I-IV: Not reflected by Magic Coat, Gen V+: Reflected by Magic Coat
    "toxic-spikes": {"status_move": True, "hazard": "toxic-spikes", "gen_specific": {"1-4": {"reflected_by_magic_coat": False}, "5+": {"reflected_by_magic_coat": True}}},  # Gen I-IV: Not reflected by Magic Coat, Gen V+: Reflected by Magic Coat
    "sticky-web": {
        "status_move": True,
        "hazard": "sticky-web",
        "z_boost_effect": {"stat_boost": {"spe": 1}}
    },
    
    # ========== HAZARD REMOVAL ==========
    "rapid-spin": {"removes_hazards": "self", "gen_specific": {"8+": {"stat_boost": {"spe": 1}}}},
    "defog": {"status_move": True, "removes_hazards": "both", "gen_specific": {"1-4": {"reflected_by_magic_coat": False}, "5+": {"reflected_by_magic_coat": True}}},  # Gen I-IV: Not reflected by Magic Coat, Gen V+: Reflected by Magic Coat
    "court-change": {"status_move": True, "swaps_hazards": True},
    
    # ========== WEATHER MOVES ==========
    "rain-dance": {"status_move": True, "weather": "rain"},
    "sunny-day": {"status_move": True, "weather": "sun"},
    "sandstorm": {"status_move": True, "weather": "sandstorm"},
    "hail": {"status_move": True, "weather": "hail"},
    "snowscape": {"status_move": True, "weather": "hail"},  # Gen 9 name
    
    # ========== TERRAIN MOVES ==========
    "electric-terrain": {
        "status_move": True,
        "terrain": "electric",
        "z_boost_effect": {"stat_boost": {"spe": 1}}
    },
    "grassy-terrain": {
        "status_move": True,
        "terrain": "grassy",
        "z_boost_effect": {"stat_boost": {"defn": 1}}
    },
    "misty-terrain": {
        "status_move": True,
        "terrain": "misty",
        "z_boost_effect": {"stat_boost": {"spd": 1}}
    },
    "psychic-terrain": {
        "status_move": True,
        "terrain": "psychic",
        "z_boost_effect": {"stat_boost": {"spa": 1}},
        "gen_specific": {
            "8+": {
                "power_boost": 0.3,
                "expanding_force_boost": 1.5,
                "terrain_pulse_power": 100,
                "mimicry_type": "psychic"
            }
        }
    },
    
    # ========== FIELD EFFECTS ==========
    # Removed duplicate - already in priority section
    "magic-room": {
        "status_move": True,
        "field_effect": "magic-room",
        "duration": 5,
        "priority": -7,
        "gen_specific": {"6+": {"priority": 0}}
    },
    "wonder-room": {
        "status_move": True,
        "field_effect": "wonder-room",
        "duration": 5,
        "priority": -7,
        "gen_specific": {"6+": {"priority": 0}}
    },
    "gravity": {"status_move": True, "field_effect": "gravity", "duration": 5},
    
    # ========== PROTECTION MOVES ==========
    "protect": {"status_move": True, "protection": True, "priority": 4},
    "detect": {"status_move": True, "protection": True, "priority": 4},
    "endure": {"status_move": True, "protection": "endure", "priority": 4},
    # Gen VI-VII: contact move blocked → attacker Attack -2. Gen VIII: -1. Multistrike: drop only once. Z-King's Shield (Gen VII): resets user's lowered stats.
    "kings-shield": {
        "status_move": True,
        "protection": "kings-shield",
        "priority": 4,
        "contact_attack_drop": True,
        "contact_stat_drop_once_per_move": True,
        "z_boost_effect": {"reset_lower_stats": True},
        "gen_specific": {"6": {"contact_stat_drop": {"atk": -2}}, "7": {"contact_stat_drop": {"atk": -2}}, "8": {"contact_stat_drop": {"atk": -1}}, "9+": {"banned": True}}
    },
    "spiky-shield": {
        "status_move": True,
        "protection": "spiky-shield",
        "priority": 4,
        "contact_damage_fraction": 0.125,
        "z_boost_effect": {"stat_boost": {"defn": 1}}
    },
    "baneful-bunker": {
        "status_move": True,
        "protection": "baneful-bunker",
        "priority": 4,
        "contact_poison": True,
        "z_boost_effect": {"stat_boost": {"defn": 1}},
        "gen_specific": {"8-brilliant-diamond-shining-pearl": {"banned": True}}
    },
    "obstruct": {"status_move": True, "protection": "obstruct", "priority": 4},
    "winters-aegis": {
        "status_move": True,
        "protection": "winters-aegis",
        "priority": 4,
        "contact_speed_drop": True,
        "fire_melts_shield": True,
        "z_boost_effect": {"stat_boost": {"spd": 1}}
    },
    
    # ========== HEALING MOVES ==========
    "recover": {"status_move": True, "heal": 0.5},
    "soft-boiled": {"status_move": True, "heal": 0.5, "gen_specific": {"rounding": {"1": "down", "5+": "up"}, "pp": {"9": 5}}},  # Gen I: round down, Gen V+: round up; PP: 10 Gen I-VIII, 5 Gen IX
    "roost": {"status_move": True, "heal": 0.5, "gen_specific": {"4": {"rounding": "down", "removes_flying_type": True}, "5-7": {"rounding": "up", "removes_flying_type": True}, "9": {"pp": 5}}},  # Gen IV: Rounds down, removes Flying type, Gen V-VII: Rounds up, removes Flying type, Gen IX: 5 PP
    "slack-off": {"status_move": True, "heal": 0.5, "gen_specific": {"3-4": {"rounding": "down"}, "5-8": {"rounding": "up"}, "9": {"pp": 5}}},  # Gen III-IV: round down, Gen V-VIII: round up, Gen IX: 5 PP
    "synthesis": {"status_move": True, "heal": 0.5},
    "moonlight": {"status_move": True, "heal": 0.5},
    "morning-sun": {"status_move": True, "heal": 0.5},
    "shore-up": {
        "status_move": True,
        "heal": 0.5,
        "heals_more_in_sand": True,
        "z_boost_effect": {"reset_lower_stats": True},
        "gen_specific": {
            "8-brilliant-diamond-shining-pearl": {"banned": True},
            "9+": {"pp": 5}
        }
    },
    "rest": {"status_move": True, "heal": 1.0, "status": "slp", "self": True},
    "wish": {"status_move": True, "heal": 0.5, "delayed": True},
    "pain-split": {"status_move": True, "averages_hp": True, "gen_specific": {"2": {"hits_substitute": False}, "3+": {"hits_substitute": True}}},
    
    # ========== SUBSTITUTE & TRANSFORM ==========
    "substitute": {"status_move": True, "creates_substitute": True, "cost": 0.25},
    "transform": {"status_move": True, "transforms": True},
    
    # ========== VARIABLE POWER MOVES ==========
    "gyro-ball": {"variable_power": "gyro_ball"},  # Based on speed ratio
    "electro-ball": {"variable_power": "electro_ball", "bulletproof_immune": True},
    "heavy-slam": {
        "variable_power": "heavy_slam",
        "doubled_minimize": True,
        "gen_specific": {"8+": {"fails_on_dynamax": True}}
    },  # Based on weight ratio
    "heat-crash": {
        "variable_power": "heat_crash",
        "doubled_minimize": True,
        "gen_specific": {
            "6+": {"always_hits_minimize": True},
            "8+": {"fails_on_dynamax": True}
        }
    },  # Based on weight ratio
    "low-kick": {"variable_power": "low_kick"},  # Based on target weight
    "grass-knot": {"variable_power": "grass_knot"},  # Based on target weight
    "hex": {"variable_power": "hex"},  # Double power if target has status
    "venoshock": {"variable_power": "venoshock"},  # Double power if target is poisoned
    "brine": {"variable_power": "brine"},  # Double power if target HP < 50%
    "retaliate": {"variable_power": "retaliate"},  # Double power if ally fainted
    "avalanche": {"variable_power": "avalanche"},  # Double power if hit this turn
    "assurance": {"variable_power": "assurance"},  # Double power if target hit this turn
    "payback": {"variable_power": "payback"},  # Double power if user moves last
    "revenge": {"variable_power": "revenge"},  # Double power if hit this turn
    "magnitude": {"variable_power": "magnitude"},  # Random power 10-150
    "present": {"variable_power": "present"},  # Random power, can heal
    "fury-cutter": {"variable_power": "fury_cutter"},  # Increases with consecutive hits
    "echoed-voice": {"variable_power": "echoed_voice"},  # Increases with consecutive hits
    "stored-power": {"variable_power": "stored_power"},  # Based on stat boosts
    "power-trip": {"variable_power": "power_trip", "gen_specific": {"8-brilliant-diamond-shining-pearl": {"banned": True}}},  # Based on stat boosts
    "punishment": {"variable_power": "punishment", "gen_specific": {"8+": {"banned": True}}},  # Power = 60 + 20 per stat boost (max 200), Gen VIII+ banned
    "acrobatics": {"variable_power": "acrobatics"},  # Double power if no item
    "fling": {"variable_power": "fling"},  # Based on item held
    "trump-card": {"variable_power": "trump_card"},  # Based on PP left
    "wring-out": {"variable_power": "wring_out", "gen_specific": {"8+": {"banned": True}}},  # Power = 120 × (target HP / max HP), min 1, Gen VIII+ banned
    "crush-grip": {"variable_power": "crush_grip"},  # Based on target HP%
    "eruption": {"variable_power": "eruption"},  # Based on user HP%
    "water-spout": {"variable_power": "water_spout"},  # Based on user HP%
    
    # Friendship-based moves
    "return": {"variable_power": "return"},  # Max 102 at 255 friendship
    "frustration": {"variable_power": "frustration"},  # Max 102 at 0 friendship
    
    # Low HP power moves
    "flail": {"variable_power": "flail"},  # 20-200 based on HP%
    "reversal": {"variable_power": "reversal"},  # 20-200 based on HP%
    
    # ========== STAT-CLEARING MOVES ==========
    "clear-smog": {"clears_target_stats": True},
    "haze": {"status_move": True, "clears_all_stats": True},
    
    # ========== MISC SPECIAL EFFECTS ==========
    "psyshock": {"uses_defense": True},  # Special attack, physical defense
    "psystrike": {"uses_defense": True},
    "secret-sword": {"uses_defense": True, "sharpness_boost": True},
    "solar-beam": {"charges": True, "gen_specific": {"1": {"two_turn": True}, "2": {"instant_in_sun": True, "halved_in_rain": True}, "3-4": {"instant_in_sun": True, "halved_in_rain_hail_fog_sand": True, "power_herb": True}, "5-6": {"instant_in_sun": True}, "7+": {"instant_in_sun": True, "power_herb": True}}},
    "solar-blade": {
        "charges": True,
        "gen_specific": {"8-brilliant-diamond-shining-pearl": {"banned": True}}
    },
    "sky-attack": {"charges": True, "chance": 0.3, "flinch": True, "high_crit": True},
    "razor-wind": {"charges": True, "high_crit": True},
    "skull-bash": {"charges": True, "stat_boost_charge": {"defn": 1}},
    "fly": {"semi_invulnerable": True},
    "dig": {"semi_invulnerable": True, "gen_specific": {"1": {"power": 100, "can_be_caught_during_invuln": True, "paralysis_no_reset": True}, "2-3": {"power": 60}, "4+": {"power": 80, "cannot_be_caught_during_invuln": True}}},
    "dive": {"semi_invulnerable": True},
    "bounce": {"semi_invulnerable": True, "chance": 0.3, "status": "par"},
    "phantom-force": {
        "semi_invulnerable": True,
        "ignores_protect": True,
        "removes_protection": True,
        "gen_specific": {
            "6": {"doubled_minimize": True, "always_hits_minimize": True},
            "7+": {"doubled_minimize": False}
        }
    },
    "shadow-force": {
        "semi_invulnerable": True,
        "ignores_protect": True,
        "removes_protection": True,
        "gen_specific": {"6": {"doubled_minimize": True, "always_hits_minimize": True}}
    },
    
    # ========== BASIC STAT MOVES (Gen 1-2 moves) ==========
    "harden": {"status_move": True, "stat_boost": {"defn": 1}},
    "withdraw": {"status_move": True, "stat_boost": {"defn": 1}},
    "defense-curl": {"status_move": True, "stat_boost": {"defn": 1}},
    "barrier": {"status_move": True, "stat_boost": {"defn": 2}},
    "acid-armor": {"status_move": True, "stat_boost": {"defn": 2}, "gen_specific": {"pp": {"6+": 20}}},  # PP 40→20 Gen VI+
    "meditate": {"status_move": True, "stat_boost": {"atk": 1}, "gen_specific": {"8+": {"banned": True}}},
    "sharpen": {"status_move": True, "stat_boost": {"atk": 1}},
    "howl": {"status_move": True, "stat_boost": {"atk": 1}, "gen_specific": {"3-7": {"user_only": True}, "8+": {"sound_move": True, "affects_allies": True, "soundproof_interaction": True}}},  # Gen III-VII: User only, Gen VIII+: Sound move, affects allies, blocked by Soundproof
    "cosmic-power": {"status_move": True, "stat_boost": {"defn": 1, "spd": 1}},
    "charge": {"status_move": True, "stat_boost": {"spd": 1}, "charges_electric": True},
    "focus-energy": {"status_move": True, "boosts_crit": 2},  # +2 crit stages
    "autotomize": {
        "status_move": True,
        "stat_boost": {"spe": 2},
        "gen_specific": {"9": {"banned": True}}
    },
    "cotton-guard": {
        "status_move": True,
        "stat_boost": {"defn": 3},
        "z_boost_effect": {"reset_lower_stats": True}
    },
    "belly-drum": {"status_move": True, "stat_boost": {"atk": 6}, "costs_hp": 0.5},  # Max Attack, costs 50% HP
    "clangorous-soul": {"status_move": True, "stat_boost": {"atk": 1, "defn": 1, "spa": 1, "spd": 1, "spe": 1}, "costs_hp": 0.33},
    "fillet-away": {"status_move": True, "stat_boost": {"atk": 2, "spa": 2, "spe": 2}, "costs_hp": 0.5},
    "no-retreat": {
        "status_move": True,
        "stat_boost": {"atk": 1, "defn": 1, "spa": 1, "spd": 1, "spe": 1},
        "traps_self": True,
        "gen_specific": {
            "8-brilliant-diamond-shining-pearl": {"banned": True}
        }
    },
    "defend-order": {"status_move": True, "stat_boost": {"defn": 1, "spd": 1}},
    "stockpile": {"status_move": True, "stockpile": True},  # Stores energy (up to 3 times)
    "swallow": {"status_move": True, "heals_stockpile": True},  # Heals based on stockpile
    "spit-up": {"uses_stockpile": True},  # Damage based on stockpile
    
    # ========== SCREEN & FIELD EFFECT MOVES ==========
    "light-screen": {"status_move": True, "sets_screen": "light-screen", "duration": 5},
    "reflect": {"status_move": True, "sets_screen": "reflect", "duration": 5},
    "aurora-veil": {
        "status_move": True,
        "sets_screen": "aurora-veil",
        "duration": 5,
        "requires_weather": ["hail", "snow"],
        "z_boost_effect": {"stat_boost": {"spe": 1}},
        "gen_specific": {"8-brilliant-diamond-shining-pearl": {"banned": True}}
    },
    "mist": {"status_move": True, "protects_stats": True, "duration": 5},
    "safeguard": {"status_move": True, "prevents_status": True, "duration": 5},
    "lucky-chant": {"status_move": True, "prevents_crits": True, "duration": 5, "gen_specific": {"4": {"snatchable": False}, "5-7": {"snatchable": True}, "8+": {"banned": True}}},  # Gen IV: Not Snatchable, Gen V-VII: Snatchable, Gen VIII+ banned
    "tailwind": {"status_move": True, "doubles_speed": True, "duration": 4},
    
    # ========== SPECIAL STATUS CONDITIONS ==========
    "leech-seed": {"status_move": True, "plants_leech_seed": True},  # Z-Move effect: Reset all lowered stats
    "ingrain": {"status_move": True, "plants_ingrain": True, "heals_per_turn": 0.0625},
    "aqua-ring": {"status_move": True, "aqua_ring": True, "heals_per_turn": 0.0625, "gen_specific": {"4": {"snatchable": False}, "5+": {"snatchable": True}}},  # Gen IV: Not Snatchable, Gen V+: Snatchable
    "disable": {"status_move": True, "disables_last_move": True, "duration": 4},
    "encore": {"status_move": True, "encores_last_move": True, "duration": 3, "gen_specific": {"1-4": {"reflected_by_magic_coat": False}, "5+": {"reflected_by_magic_coat": True}}},  # Gen I-IV: Not reflected by Magic Coat, Gen V+: Reflected by Magic Coat
    "torment": {"status_move": True, "torments": True, "gen_specific": {"1-4": {"reflected_by_magic_coat": False}, "5+": {"reflected_by_magic_coat": True}}},  # Gen I-IV: Not reflected by Magic Coat, Gen V+: Reflected by Magic Coat
    "taunt": {"status_move": True, "taunts": True, "duration": 3, "gen_specific": {"1-3": {"copied_by_mirror_move": False, "reflected_by_magic_coat": False}, "4": {"copied_by_mirror_move": True, "reflected_by_magic_coat": False}, "5+": {"copied_by_mirror_move": True, "reflected_by_magic_coat": True}}},  # Gen I-III: Not copied by Mirror Move, not reflected by Magic Coat, Gen IV+: Copied by Mirror Move, Gen V+: Reflected by Magic Coat
    "embargo": {"status_move": True, "embargoes_item": True, "duration": 5, "gen_specific": {"1-4": {"reflected_by_magic_coat": False}, "5+": {"reflected_by_magic_coat": True}}},  # Gen I-IV: Not reflected by Magic Coat, Gen V+: Reflected by Magic Coat
    "heal-block": {"status_move": True, "blocks_healing": True, "duration": 5, "gen_specific": {"4": {"hp_draining_allowed": True, "reflected_by_magic_coat": False}, "5-7": {"hp_draining_allowed": False, "reflected_by_magic_coat": True, "blocks_items_abilities": True}, "8+": {"banned": True}}},  # Gen IV: HP-draining allowed, not reflected, Gen V-VII: Blocks HP-draining, reflected, blocks items/abilities, Gen VIII+ banned
    "imprison": {"status_move": True, "imprisons_shared_moves": True, "gen_specific": {"1-4": {"snatchable": False}, "5+": {"snatchable": True}}},  # Gen I-IV: Not stolen by Snatch, Gen V+: Stolen by Snatch
    "mean-look": {"status_move": True, "traps": True, "gen_specific": {"1-2": {"bypasses_protect": True}, "3-5": {"blocked_by_protect": True}, "6+": {"bypasses_protect": True}}},  # Gen I-II: Not blocked by Protect, Gen III-V: Blocked by Protect, Gen VI+: Not blocked by Protect
    "block": {"status_move": True, "traps": True, "gen_specific": {"3-4": {"blocked_by_protect": True}, "5": {"baton_pass_removes": True, "blocked_by_protect": True}, "6+": {"ghost_immune": True, "bypasses_protect": True}}},  # Gen III-IV: Blocked by Protect, Gen V: Baton Pass removes trap, blocked by Protect, Gen VI+: Ghost immune, bypasses Protect
    "spider-web": {"status_move": True, "traps": True, "gen_specific": {"1-2": {"bypasses_protect": True}, "3-5": {"blocked_by_protect": True}, "6+": {"bypasses_protect": True}}},  # Gen I-II: Not blocked by Protect, Gen III-V: Blocked by Protect, Gen VI+: Not blocked by Protect
    "attract": {"status_move": True, "infatuates": True, "hits_substitute": True},
    "nightmare": {"status_move": True, "nightmares_sleeping": True, "gen_specific": {"1-2": {"bypasses_protect": True}, "3+": {"blocked_by_protect": True}}},  # Gen I-II: Not blocked by Protect, Gen III+: Blocked by Protect
    "grudge": {"status_move": True, "grudge": True},
    "destiny-bond": {"status_move": True, "destiny_bond": True},
    "perish-song": {"status_move": True, "perish_song": True, "countdown": 4, "never_miss": True, "sound_move": True, "hits_substitute": True, "bypasses_protect": True},
    
    # ========== HEALING & SUPPORT MOVES ==========
    "aromatherapy": {"status_move": True, "heals_team_status": True, "gen_specific": {"3-4": {"hits_substitute": True}, "5": {"lists_healed": True, "no_sap_sipper": True}, "6-8": {"triggers_sap_sipper": True, "allies_substitute_blocked": True, "user_substitute_allowed": True}, "9": {"banned": True}}},  # Gen III-IV: Hits through substitute, Gen V: Lists healed, no Sap Sipper, Gen VI-VIII: Triggers Sap Sipper on ally, allies behind substitute blocked, Gen IX banned
    "heal-bell": {"status_move": True, "heals_team_status": True},
    "heal-pulse": {
        "status_move": True,
        "heals_target": 0.5,
        "z_boost_effect": {"reset_lower_stats": True, "ignore_heal_block": True}
    },
    "floral-healing": {
        "status_move": True,
        "heals_target": 0.5,
        "heals_more_in_grassy": True,
        "z_boost_effect": {"reset_lower_stats": True, "ignores_heal_block": True},
        "gen_specific": {"8-brilliant-diamond-shining-pearl": {"banned": True}}
    },  # More in terrain
    "life-dew": {"status_move": True, "heals_user_and_ally": 0.25},
    "lunar-blessing": {"status_move": True, "heals_user_and_ally": 0.25},
    "jungle-healing": {"status_move": True, "heals_team": 0.25, "heals_status": True},
    "milk-drink": {"status_move": True, "heal": 0.5},
    "heal-order": {
        "status_move": True,
        "heal": 0.5,
        "gen_specific": {
            "8+": {"banned": True}
        }
    },
    "purify": {
        "status_move": True,
        "heals_target_status": True,
        "heals_user": 0.5,
        "z_boost_effect": {"stat_boost": {"atk": 1, "defn": 1, "spa": 1, "spd": 1, "spe": 1}},
        "gen_specific": {
            "8-brilliant-diamond-shining-pearl": {"banned": True},
            "9+": {"banned": True}
        }
    },
    
    # ========== MOVE/ABILITY MANIPULATION ==========
    "role-play": {"status_move": True, "copies_ability": True},
    "skill-swap": {"status_move": True, "swaps_abilities": True},
    "gastro-acid": {"status_move": True, "suppresses_ability": True, "fails_on_special_abilities": True},  # Fails on Multitype, Stance Change, etc.
    "worry-seed": {"status_move": True, "changes_ability": "insomnia", "gen_specific": {"4": {"displays_previous_ability": False, "works_on_insomnia": True, "fails_on_griseous_orb": True}, "5+": {"displays_previous_ability": True, "fails_on_insomnia": True, "works_on_griseous_orb": True}}},  # Gen IV: No display, works on Insomnia, fails on Griseous Orb, Gen V+: Displays previous, fails on Insomnia, works on Griseous Orb
    "simple-beam": {"status_move": True, "changes_ability": "simple"},
    "entrainment": {"status_move": True, "copies_ability_to_target": True},
    "doodle": {"status_move": True, "copies_ability_to_user_and_ally": True},
    "power-split": {"status_move": True, "averages_offensive_stats": True},
    "guard-split": {"status_move": True, "averages_defensive_stats": True},
    "power-swap": {"status_move": True, "swaps_offensive_stats": True, "never_miss": True},  # Swaps Attack and Special Attack stat stages
    "guard-swap": {"status_move": True, "swaps_defensive_stats": True, "never_miss": True},  # Swaps Defense and Special Defense stat stages
    "speed-swap": {
        "status_move": True,
        "swaps_speed_stats": True,
        "never_miss": True,
        "z_boost_effect": {"stat_boost": {"spe": 1}},
        "gen_specific": {"8-brilliant-diamond-shining-pearl": {"banned": True}}
    },
    "heart-swap": {"status_move": True, "swaps_all_stat_stages": True, "never_miss": True, "gen_specific": {"8": {"banned": True}}},  # Swaps all stat stages, Gen VIII banned
    
    # ========== FIELD/ENVIRONMENT MOVES ==========
    "forests-curse": {
        "status_move": True,
        "adds_type": "Grass",
        "fails_if_target_has_type": "Grass",
        "fails_if_target_terastallized": True,
        "replaces_added_type": True,
        "z_boost_effect": {
            "stat_boost": {"atk": 1, "defn": 1, "spa": 1, "spd": 1, "spe": 1}
        }
    },
    "trick-or-treat": {
        "status_move": True,
        "adds_type": "Ghost",
        "fails_if_target_has_type": "Ghost",
        "replaces_added_type": True,
        "z_boost_effect": {
            "stat_boost": {"atk": 1, "defn": 1, "spa": 1, "spd": 1, "spe": 1}
        }
    },
    "soak": {"status_move": True, "changes_type": "water"},
    "magic-powder": {
        "status_move": True,
        "changes_type": "psychic",
        "gen_specific": {
            "8-brilliant-diamond-shining-pearl": {"banned": True}
        }
    },
    "conversion": {"status_move": True, "changes_type_to_move": True},
    "conversion-2": {"status_move": True, "changes_type_resists_last": True, "gen_specific": {"2": {"blocked_by_protect": True}, "3+": {"bypasses_protect": True}}},  # Gen II: Blocked by Protect, Gen III+: Not blocked by Protect
    "camouflage": {"status_move": True, "changes_type_by_terrain": True},
    "reflect-type": {"status_move": True, "copies_target_types": True},
    "electrify": {
        "status_move": True,
        "electrifies_next_move": True,
        "never_miss": True,
        "z_boost_effect": {"stat_boost": {"spa": 1}},
        "gen_specific": {"8+": {"banned": True}}
    },
    "ion-deluge": {
        "status_move": True,
        "priority": 1,
        "makes_normal_electric": True,
        "never_miss": True,
        "z_boost_effect": {"stat_boost": {"spa": 1}},
        "gen_specific": {"8+": {"banned": True}}
    },
    "water-sport": {"status_move": True, "weakens_fire": True, "gen_specific": {"3-4": {"fire_reduction": 0.5, "ends_on_switch": True}, "5": {"fire_reduction": 0.67}, "6-7": {"fire_reduction": 0.5, "duration": 5}, "8+": {"banned": True}}},  # Gen III-IV: 50% reduction, ends on switch, Gen V: 67%, Gen VI-VII: 5 turns, Gen VIII+ banned
    "mud-sport": {"status_move": True, "weakens_electric": True, "duration": 5},
    "magnetic-flux": {
        "status_move": True,
        "boosts_plus_minus": True,
        "z_boost_effect": {"stat_boost": {"spd": 1}}
    },
    "happy-hour": {
        "status_move": True,
        "happy_hour": True,
        "z_boost_effect": {"stat_boost": {"atk": 1, "defn": 1, "spa": 1, "spd": 1, "spe": 1}},
        "gen_specific": {"8+": {"banned": True}}
    },
    "celebrate": {
        "status_move": True,
        "celebration": True,
        "z_boost_effect": {"stat_boost": {"atk": 1, "defn": 1, "spa": 1, "spd": 1, "spe": 1}},
        "gen_specific": {"8+": {"banned": True}}
    },
    "hold-hands": {
        "status_move": True,
        "requires_ally": True,
        "bypasses_standard_protect": True,
        "blocked_by_crafty_shield": True,
        "z_boost_effect": {"stat_boost": {"atk": 1, "defn": 1, "spa": 1, "spd": 1, "spe": 1}},
        "gen_specific": {"8+": {"banned": True}, "9+": {"banned": True}}
    },
    "gear-up": {
        "status_move": True,
        "boosts_plus_minus": True,
        "z_boost_effect": {"stat_boost": {"spa": 1}},
        "gen_specific": {"8-brilliant-diamond-shining-pearl": {"banned": True}, "9+": {"banned": True}}
    },
    "magnet-rise": {"status_move": True, "levitates": True, "duration": 5, "gen_specific": {"4": {"snatchable": False, "fails_if_ingrain": True, "fails_if_gravity": True}, "5+": {"snatchable": True, "removed_by_smack_down_thousand_arrows": True}}},  # Gen IV: Not Snatchable, fails if Ingrain/Gravity, Gen V+: Snatchable, removed by Smack Down/Thousand Arrows
    "telekinesis": {
        "status_move": True,
        "levitates_target": True,
        "duration": 3,
        "gen_specific": {"8+": {"banned": True}}
    },
    
    # ========== ACCURACY/EVASION MOVES ==========
    "lock-on": {"status_move": True, "ensures_next_hit": True},
    "mind-reader": {"status_move": True, "ensures_next_hit": True},
    "miracle-eye": {"status_move": True, "removes_evasion_dark_immunity": True, "gen_specific": {"1-4": {"reflected_by_magic_coat": False}, "5-7": {"reflected_by_magic_coat": True}, "8+": {"banned": True}}},  # Gen I-IV: Not reflected by Magic Coat, Gen V-VII: Reflected by Magic Coat, Gen VIII+: Banned
    "foresight": {"status_move": True, "removes_evasion_ghost_immunity": True, "gen_specific": {"1-4": {"reflected_by_magic_coat": False}, "5+": {"reflected_by_magic_coat": True}}},  # Gen I-IV: Not reflected by Magic Coat, Gen V+: Reflected by Magic Coat
    "odor-sleuth": {"status_move": True, "removes_evasion_ghost_immunity": True, "gen_specific": {"1-4": {"reflected_by_magic_coat": False}, "5+": {"reflected_by_magic_coat": True}}},  # Gen I-IV: Not reflected by Magic Coat, Gen V+: Reflected by Magic Coat
    
    # ========== DOUBLES/MULTI-BATTLE MOVES ==========
    "follow-me": {"status_move": True, "redirects_attacks": True},
    "rage-powder": {
        "status_move": True,
        "redirects_attacks": True,
        "priority": 3,
        "gen_specific": {"6+": {"priority": 2}}
    },
    "ally-switch": {
        "status_move": True,
        "switches_position": True,
        "priority": 2,
        "z_boost_effect": {"stat_boost": {"spe": 2}},
        "gen_specific": {
            "5-6": {"priority": 1},
            "7-8": {"priority": 2},
            "9+": {"priority": 2, "consecutive_success_penalty": True}
        }
    },
    "after-you": {"status_move": True, "target_moves_immediately": True},
    "instruct": {"status_move": True, "target_uses_move_again": True},
    "helping-hand": {"status_move": True, "boosts_ally": 1.5, "priority": 5},
    "aromatic-mist": {
        "status_move": True,
        "target_stat_boost": {"spd": 1},
        "z_boost_effect": {"stat_boost": {"spd": 2}}
    },
    "decorate": {"status_move": True, "target_stat_boost": {"atk": 2, "spa": 2}},
    "coaching": {"status_move": True, "target_stat_boost": {"atk": 1, "defn": 1}},
    "flower-shield": {
        "status_move": True,
        "boosts_grass_types_def": True,
        "z_boost_effect": {"stat_boost": {"defn": 1}},
        "gen_specific": {"9+": {"banned": True}}
    },
    
    # ========== SACRIFICE/MEMENTO MOVES ==========
    "memento": {"status_move": True, "faints_user": True, "stat_drop": {"atk": -2, "spa": -2}},
    "healing-wish": {"status_move": True, "faints_user": True, "heals_replacement": True},
    "lunar-dance": {"status_move": True, "faints_user": True, "heals_replacement_full": True},
    "final-gambit": {"faints_user": True, "damage_equals_hp": True},
    
    # ========== TRAPPING MOVES ==========
    "wrap": {"chance": 1.0, "traps": True, "trap_damage": 0.0625},
    "bind": {"chance": 1.0, "traps": True, "trap_damage": 0.0625},
    "fire-spin": {"chance": 1.0, "traps": True, "trap_damage": 0.0625, "gen_specific": {"1": {"power": 15, "accuracy": 70, "duration_range": [2, 5], "prevents_attack": True}, "2": {"trap_damage": 0.0625, "does_not_prevent_attack": True}, "3-4": {"trap_damage": 0.0625, "affected_by_kings_rock": True, "grip_claw_duration": 5}, "5": {"power": 35, "accuracy": 85, "duration_range": [4, 5], "grip_claw_duration": 7, "binding_band_damage": 0.125}, "6+": {"trap_damage": 0.125, "binding_band_damage": 0.1667, "ghost_immunity": True}}},
    "whirlpool": {"chance": 1.0, "traps": True, "trap_damage": 0.0625},
    "sand-tomb": {"chance": 1.0, "traps": True, "gen_specific": {"3": {"power": 15, "accuracy": 70, "trap_damage": 0.0625, "trap_duration": "2-5"}, "4": {"power": 15, "accuracy": 70, "trap_damage": 0.0625, "grip_claw_duration": 5}, "5": {"power": 35, "accuracy": 85, "trap_damage": 0.0625, "trap_duration": "4-5", "binding_band_damage": 0.125, "grip_claw_duration": 7}, "6+": {"power": 35, "accuracy": 85, "trap_damage": 0.125, "binding_band_damage": 0.1666, "ghost_immune": True}}},  # Gen III: 15 BP/70% acc, 1/16 damage, 2-5 turns; Gen IV: Grip Claw 5 turns; Gen V: 35 BP/85% acc, 1/16 damage (1/8 w/ Binding Band), 4-5 turns, Grip Claw 7 turns; Gen VI+: 1/8 damage (1/6 w/ Binding Band), Ghost immune
    "magma-storm": {
        "chance": 1.0,
        "traps": True,
        "trap_damage": 0.125,
        "gen_specific": {
            "4": {"power": 120, "accuracy": 70, "trap_damage": 0.0625, "trap_duration": [2, 5]},
            "5": {"power": 120, "accuracy": 75, "trap_damage": 0.0625, "trap_duration": [4, 5], "grip_claw_duration": 7, "binding_band_damage": 0.125},
            "6-7": {"power": 100, "accuracy": 75, "trap_damage": 0.125, "trap_duration": [4, 5], "binding_band_damage": 0.1667, "ghost_immunity": True},
            "8+": {"power": 100, "accuracy": 75, "trap_damage": 0.125, "trap_duration": [4, 5], "ghost_immunity": True}
        }
    },
    "infestation": {"chance": 1.0, "traps": True, "trap_damage": 0.125},
    "clamp": {"chance": 1.0, "traps": True, "trap_damage": 0.0625},
    "snap-trap": {"chance": 1.0, "traps": True, "trap_damage": 0.125},
    "thunder-cage": {"chance": 1.0, "traps": True, "trap_damage": 0.0625},
    "g-max-sandblast": {"chance": 1.0, "traps": True, "trap_damage": 0.0625},
    
    # ========== SPECIAL CASES & NICHE MOVES ==========
    "splash": {"status_move": True, "does_nothing": True},
    "celebrate": {"status_move": True, "does_nothing": True},
    "hold-hands": {"status_move": True, "does_nothing": True},
    "teleport": {"status_move": True, "priority": -6, "switches_out": True},
    "metronome": {"status_move": True, "calls_random_move": True},
    "mimic": {"status_move": True, "copies_last_move": True},
    "sketch": {"status_move": True, "permanently_copies_move": True},
    "nature-power": {"status_move": True, "uses_terrain_move": True},
    "bestow": {"status_move": True, "gives_item": True, "gen_specific": {"5": {"blocked_by_protect": True}, "6+": {"bypasses_protect": True}}},  # Gen V: Blocked by Protect, Gen VI+: Not blocked by Protect
    "recycle": {"status_move": True, "restores_consumed_item": True, "gen_specific": {"1-4": {"snatchable": False}, "5+": {"snatchable": True}}},  # Gen I-IV: Not stolen by Snatch, Gen V+: Stolen by Snatch
    "magic-coat": {"status_move": True, "reflects_status_moves": True, "priority": 4},
    "snatch": {"status_move": True, "steals_stat_moves": True, "priority": 4},
    "me-first": {"status_move": True, "copies_target_move": True, "power_boost": 1.5, "priority": 0, "never_miss": True, "gen_specific": {"4-6": {"choice_lock": "me-first"}, "7": {"choice_lock_special_handling": True}, "8+": {"banned": True}}},  # Copies target move with 50% power boost, always hits, Gen IV-VI: Locks into Me First, Gen VII: Special Choice lock handling, Gen VIII+ banned
    "copycat": {"status_move": True, "copies_last_move_used": True, "gen_specific": {"4": {"calling_move_counted": True, "invalid_on_status_prevents": True, "invalid_on_charging": True, "invalid_on_recharging": True, "invalid_on_bide_final": True}, "5-6": {"called_move_counted": True, "invalid_on_status_prevents": False}, "7+": {"fails_on_z_move": True, "copies_base_move_from_max": True}}},  # Gen IV: Calling move counted, invalid on various conditions, Gen V-VI: Called move counted, Gen VII+: Fails on Z-Moves, copies base from Max Moves
    "assist": {"status_move": True, "uses_ally_move": True},
    "sleep-talk": {"status_move": True, "uses_random_move_while_asleep": True},
    "captivate": {
        "status_move": True,
        "target_stat_drop": {"spa": -2},
        "opposite_gender": True,
        "gen_specific": {
            "8+": {"banned": True}
        }
    },
    "confide": {
        "status_move": True,
        "target_stat_drop": {"spa": -1},
        "never_miss": True,
        "sound_move": True,
        "hits_substitute": True,
        "bypasses_standard_protect": True,
        "blocked_by_crafty_shield": True,
        "z_boost_effect": {"stat_boost": {"spd": 1}}
    },
    "laser-focus": {
        "status_move": True,
        "next_move_crits": True,
        "z_boost_effect": {"stat_boost": {"atk": 1}}
    },
    "corrosive-gas": {"status_move": True, "destroys_items": True},
    "teatime": {"status_move": True, "all_consume_berries": True},
    "stuff-cheeks": {
        "status_move": True,
        "consumes_berry": True,
        "stat_boost": {"defn": 2},
        "gen_specific": {
            "8-brilliant-diamond-shining-pearl": {"banned": True}
        }
    },
    "tar-shot": {
        "status_move": True,
        "target_stat_drop": {"spe": -1},
        "adds_fire_weakness": True,
        "gen_specific": {
            "8-brilliant-diamond-shining-pearl": {"banned": True}
        }
    },
    "fairy-lock": {
        "status_move": True,
        "prevents_switching_next_turn": True,
        "z_boost_effect": {"stat_boost": {"defn": 1}},
        "gen_specific": {"8+": {"banned": True}}
    },
    "chilly-reception": {"status_move": True, "weather": "snow", "switches_out": True},
    "dragon-cheer": {"status_move": True, "boosts_dragon_crit": True},
    "baton-pass": {"status_move": True, "switches_out": True, "passes_boosts": True},
    "psych-up": {"status_move": True, "copies_target_stat_stages": True, "ignores_protect": True, "gen_specific": {"1": {"snatchable": True}, "2": {"snatchable": True, "bypass_accuracy": True}, "3-4": {"snatchable": True}, "5+": {"snatchable": False}}},  # Gen I-IV: Stolen by Snatch, Gen V+: Not stolen by Snatch, Gen II: Bypasses accuracy
    "power-shift": {"status_move": True, "swaps_atk_def_stats": True},
    "play-nice": {
        "status_move": True,
        "target_stat_drop": {"atk": -1},
        "never_miss": True,
        "hits_substitute": True,
        "bypasses_standard_protect": True,
        "blocked_by_crafty_shield": True,
        "z_boost_effect": {"stat_boost": {"defn": 1}}
    },
    "noble-roar": {
        "status_move": True,
        "target_stat_drop": {"atk": -1, "spa": -1},
        "sound_move": True,
        "hits_substitute": True,
        "z_boost_effect": {"stat_boost": {"defn": 1}}
    },
    "venom-drench": {
        "status_move": True,
        "target_stat_drop": {"atk": -1, "spa": -1, "spe": -1},
        "requires_poison": True,
        "z_boost_effect": {"stat_boost": {"defn": 1}},
        "gen_specific": {"9+": {"banned": True}}
    },
    "cotton-spore": {"status_move": True, "target_stat_drop": {"spe": -2}},
    "string-shot": {"status_move": True, "target_stat_drop": {"spe": -1}, "gen_specific": {"1-2": {"fail_chance": 0.25, "stat_drop": {"spe": -1}}, "3-5": {"hits_adjacent": True, "stat_drop": {"spe": -1}}, "6+": {"stat_drop": {"spe": -2}, "hits_adjacent": True}}},
    "scary-face": {"status_move": True, "target_stat_drop": {"spe": -2}},
    "refresh": {"status_move": True, "heals_self_status": True},
    "psycho-shift": {"status_move": True, "transfers_status": True},
    "quash": {"status_move": True, "makes_target_move_last": True},
    "mat-block": {
        "status_move": True,
        "protects_team": True,
        "protect_variant": "mat-block",
        "priority": 0,
        "first_turn_only": True,
        "z_boost_effect": {"stat_boost": {"defn": 1}},
        "gen_specific": {"9+": {"banned": True}}
    },
    "revival-blessing": {"status_move": True, "revives_fainted": True},
    "rototiller": {
        "status_move": True,
        "rototiller": True,
        "z_boost_effect": {"stat_boost": {"atk": 1}},
        "gen_specific": {"8+": {"banned": True}}
    },
    "spotlight": {
        "status_move": True,
        "redirects_to_target": True,
        "priority": 3,
        "z_boost_effect": {"stat_boost": {"spd": 1}},
        "gen_specific": {"8+": {"banned": True}}
    },
    "mirror-move": {"status_move": True, "copies_target_last_move": True},
    "feint": {"priority": 2, "breaks_protect": True, "gen_specific": {"1-5": {"copied_by_mirror_move": False}, "6+": {"copied_by_mirror_move": True}}},  # Gen I-V: Not copied by Mirror Move, Gen VI+: Copied by Mirror Move
    
    # ========== MORE ATTACKING MOVES WITH EFFECTS ==========
    # Fire moves with burn chance
    "fire-punch": {"chance": 0.1, "status": "brn"},
    "flame-wheel": {"chance": 0.1, "status": "brn", "thaws_user": True},
    "sacred-fire": {"chance": 0.5, "status": "brn", "thaws_user": True},
    "searing-shot": {"chance": 0.3, "status": "brn", "bulletproof_immune": True, "gen_specific": {"9+": {"banned": True}}},
    "fire-lash": {
        "chance": 1.0,
        "stat_drop": {"defn": -1},
        "gen_specific": {"8-brilliant-diamond-shining-pearl": {"banned": True}}
    },
    "mystical-fire": {"chance": 1.0, "stat_drop": {"spa": -1}},
    "burning-jealousy": {"chance": 1.0, "burn_if_stats_raised": True},
    
    # Ice moves with freeze/effects
    "ice-punch": {"chance": 0.1, "status": "frz"},
    "ice-beam": {"chance": 0.1, "status": "frz"},
    "powder-snow": {"chance": 0.1, "status": "frz"},
    "ice-fang": {"chance": 0.1, "status": "frz", "chance2": 0.1, "flinch": True},
    "icicle-crash": {"chance": 0.3, "flinch": True},
    "glaciate": {
        "chance": 1.0,
        "stat_drop": {"spe": -1},
        "hits_adjacent_foes": True
    },
    "freezing-glare": {"chance": 0.1, "status": "frz"},
    "ice-spinner": {"destroys_terrain": True},
    
    # Electric moves with paralysis
    "thunder-punch": {"chance": 0.1, "status": "par"},
    "spark": {"chance": 0.3, "status": "par"},
    "discharge": {"chance": 0.3, "status": "par", "hits_adjacent": True},
    "thunder-fang": {
        "chance": 0.1,
        "status": "par",
        "chance2": 0.1,
        "flinch": True,
        "gen_specific": {
            "4": {"affected_by_kings_rock": True},
            "5+": {"not_affected_by_kings_rock": True}
        }
    },
    "nuzzle": {"chance": 1.0, "status": "par"},
    "parabolic-charge": {"drain": 0.5},
    "eerie-impulse": {
        "status_move": True,
        "target_stat_drop": {"spa": -2},
        "z_boost_effect": {"stat_boost": {"spd": 1}}
    },
    "electroweb": {
        "chance": 1.0,
        "stat_drop": {"spe": -1},
        "hits_adjacent_foes": True
    },
    
    # Water moves with effects
    "water-pulse": {"chance": 0.2, "confuse": True},
    "bubble-beam": {"chance": 0.1, "stat_drop": {"spe": -1}},
    "octazooka": {"chance": 0.5, "stat_drop": {"accuracy": -1}},
    "muddy-water": {"chance": 0.3, "stat_drop": {"accuracy": -1}},
    "origin-pulse": {"hits_adjacent_foes": True, "mega_launcher_boost": True},
    "aqua-tail": {},
    "crabhammer": {"high_crit": True, "gen_specific": {"1-4": {"power": 90, "accuracy": 85}, "5": {"power": 90, "accuracy": 90}, "6+": {"power": 100, "accuracy": 90}}},  # Power 90→100 Gen VI+, Accuracy 85%→90% Gen V+
    "razor-shell": {"chance": 0.5, "stat_drop": {"defn": -1}, "sharpness_boost": True},
    "steam-eruption": {
        "chance": 0.3,
        "status": "brn",
        "thaws_user": True,
        "thaws_target_on_hit": True
    },
    "chilling-water": {"chance": 1.0, "target_stat_drop": {"atk": -1}},
    
    # Grass moves with effects
    "razor-leaf": {"high_crit": True, "hits_adjacent": True, "boosted_by_sharpness": True},  # Sharpness: +50% power
    "magical-leaf": {"never_miss": True},
    "seed-bomb": {"bulletproof_immune": True},
    "energy-ball": {
        "chance": 0.1,
        "stat_drop": {"spd": -1},
        "gen_specific": {
            "4-5": {"power": 80},
            "6+": {"power": 90}
        }
    },
    "leaf-storm": {
        "self_stat_drop": {"spa": -2},
        "gen_specific": {
            "4-5": {"power": 140},
            "6+": {"power": 130}
        }
    },  # Lowers user's SpA
    "power-whip": {},
    "wood-hammer": {"recoil": 0.33},
    "petal-blizzard": {"hits_adjacent": True, "hits_allies": True, "wind_move": True},
    "solar-blade": {"charges": True},
    "needle-arm": {"chance": 0.3, "flinch": True, "gen_specific": {"3": {"doubled_minimize": True}}},  # Gen III: Double damage vs Minimize, Gen VIII+ banned
    "grassy-glide": {"priority_in_terrain": True},  # Priority in Grassy Terrain
    "leafage": {},
    "branch-poke": {},
    "snap-trap": {"chance": 1.0, "traps": True},
    "apple-acid": {"chance": 1.0, "stat_drop": {"spd": -1}},
    "strength-sap": {
        "status_move": True,
        "strength_sap": True,
        "stat_drop": {"atk": -1},
        "z_boost_effect": {"stat_boost": {"defn": 1}}
    },
    
    # Fighting moves with effects
    "karate-chop": {"high_crit": True},
    "rolling-kick": {"chance": 0.3, "flinch": True},
    "submission": {"recoil": 0.25, "gen_specific": {"1": {"no_recoil_on_ko": True, "no_recoil_on_substitute": True}, "6": {"pp": 20}, "9": {"banned": True}}},
    "low-kick": {"variable_power": "low_kick", "gen_specific": {"1-2": {"power": 50, "accuracy": 90, "chance": 0.3, "flinch": True}, "3+": {"accuracy": 100, "variable_power": "low_kick", "fails_vs_dynamax": True}}},
    "cross-chop": {"high_crit": True},
    "vital-throw": {"priority": -1, "never_miss": True},
    "reversal": {"variable_power": "low_hp"},  # Already has this
    "sky-uppercut": {},
    "brick-break": {"breaks_screens": True},
    "arm-thrust": {"multi_hit": "2-5"},
    "bulk-up": {"status_move": True, "stat_boost": {"atk": 1, "defn": 1}},
    "hammer-arm": {"self_stat_drop": {"spe": -1}},
    "force-palm": {"chance": 0.3, "status": "par"},
    "aura-sphere": {"never_miss": True, "gen_specific": {"4-5": {"power": 90}, "6+": {"power": 80, "mega_launcher_boost": True, "bulletproof_immune": True}}},  # Gen IV-V: 90 BP, Gen VI+: 80 BP, boosted by Mega Launcher, Bulletproof immune
    "drain-punch": {
        "drain": 0.5,
        "gen_specific": {
            "4": {"power": 60, "pp": 5},
            "5": {"power": 75, "pp": 10},
            "6+": {"power": 75, "pp": 10, "blocked_by_heal_block": True}
        }
    },
    "vacuum-wave": {"priority": 1},
    "storm-throw": {
        "always_crit": True,
        "gen_specific": {"6+": {"power": 60}, "9+": {"banned": True}}
    },
    "sacred-sword": {
        "ignores_stat_changes": True,
        "sharpness_boost": True,
        "gen_specific": {
            "5": {"pp": 20},
            "6+": {"pp": 15}
        }
    },
    "flying-press": {"dual_type": "flying", "doubled_minimize": True},  # Fighting + Flying
    "power-up-punch": {
        "chance": 1.0,
        "stat_boost": {"atk": 1},
        "gen_specific": {"9+": {"banned": True}}
    },
    "body-press": {"uses_defense_as_attack": True},
    "triple-axel": {"multi_hit": 3, "increasing_power": True},
    "collision-course": {"boosted_super_effective": 1.33},
    "axe-kick": {"chance": 0.3, "confuse_if_miss": True},
    "upper-hand": {"priority": 3, "flinch": True, "fails_if_not_priority": True},
    
    # Poison moves with poison/effects
    "poison-sting": {"chance": 0.3, "status": "psn"},
    "sludge": {"chance": 0.3, "status": "psn"},
    "smog": {"chance": 0.4, "status": "psn"},
    "sludge-bomb": {"chance": 0.3, "status": "psn"},
    "sludge-wave": {"chance": 0.1, "status": "psn"},
    "gunk-shot": {"chance": 0.3, "status": "psn"},
    "poison-jab": {"chance": 0.3, "status": "psn"},
    "cross-poison": {"chance": 0.1, "status": "psn", "high_crit": True},
    "poison-tail": {"chance": 0.1, "status": "psn", "high_crit": True},
    "belch": {"requires_berry": True},
    "acid-spray": {"chance": 1.0, "stat_drop": {"spd": -2}},
    "shell-side-arm": {"checks_better_category": True},  # Physical or Special
    "barb-barrage": {"chance": 0.5, "status": "psn", "doubled_if_poisoned": True},
    "mortal-spin": {"removes_hazards": True, "chance": 1.0, "status": "psn"},
    
    # Ground moves
    "bone-club": {"chance": 0.1, "flinch": True},
    "bonemerang": {"multi_hit": 2},
    "dig": {"semi_invulnerable": True, "gen_specific": {"1": {"power": 100, "can_be_caught_during_invuln": True, "paralysis_no_reset": True}, "2-3": {"power": 60}, "4+": {"power": 80, "cannot_be_caught_during_invuln": True}}},
    # Note: earth-power is defined above in STAT DROP MOVES section (line 280)
    "bulldoze": {"chance": 1.0, "stat_drop": {"spe": -1}},
    "drill-run": {"high_crit": True},
    "stomping-tantrum": {"doubled_if_failed_last": True},
    "high-horsepower": {},
    "scorching-sands": {"chance": 0.3, "status": "brn"},
    "headlong-rush": {"self_stat_drop": {"defn": -1, "spd": -1}},
    "sandsear-storm": {"chance": 0.2, "status": "brn"},
    
    # Flying moves
    "wing-attack": {},
    "peck": {},
    "drill-peck": {},
    "sky-attack": {"charges": True, "chance": 0.3, "flinch": True, "high_crit": True},
    "aeroblast": {"high_crit": True},
    "air-cutter": {"high_crit": True},
    "aerial-ace": {"never_miss": True},
    "pluck": {"eats_berry": True},
    "tailwind": {"status_move": True, "doubles_speed": True},
    "air-slash": {
        "chance": 0.3,
        "flinch": True,
        "gen_specific": {
            "4": {"pp": 20, "affected_by_kings_rock": True},
            "5": {"pp": 20, "not_affected_by_kings_rock": True},
            "6+": {"pp": 15, "not_affected_by_kings_rock": True, "sharpness_boost": True}
        }
    },
    "acrobatics": {"doubled_no_item": True},
    "hurricane": {
        "chance": 0.3,
        "confuse": True,
        "wind_move": True,
        "gen_specific": {
            "5": {"power": 120, "always_hit_in_rain": True, "accuracy_50_in_sun": True, "hits_semi_invulnerable": True},
            "6+": {"power": 110, "always_hit_in_rain": True, "accuracy_50_in_sun": True, "hits_semi_invulnerable": True}
        }
    },
    "oblivion-wing": {"drain": 0.75},
    "beak-blast": {"priority": -3, "burns_contact": True},
    "dual-wingbeat": {"multi_hit": 2},
    "bleakwind-storm": {"chance": 0.3, "stat_drop": {"spe": -1}},
    
    # Psychic moves
    "confusion": {"chance": 0.1, "confuse": True},  # No generation-specific changes needed
    "psybeam": {"chance": 0.1, "confuse": True},
    "psychic": {"chance": 0.1, "stat_drop": {"spd": -1}, "gen_specific": {"1": {"chance": 0.332, "stat_drop": {"special": -1}, "fail_chance": 0.25}, "2": {"chance": 0.1, "stat_drop": {"spd": -1}, "fail_chance": 0.25}, "3+": {"chance": 0.1, "stat_drop": {"spd": -1}}}},
    "psywave": {"variable_power": "level"},
    "future-sight": {"delayed": True, "turns": 2},
    "extrasensory": {"chance": 0.1, "flinch": True, "gen_specific": {"3": {"doubled_minimize": True}, "6+": {"pp": 20}}},  # Gen III: Double damage vs Minimize, Gen VI+: PP 20 (was 30)
    "luster-purge": {"chance": 0.5, "stat_drop": {"spd": -1}},
    "mist-ball": {"chance": 0.5, "stat_drop": {"spa": -1}},
    "psycho-boost": {"self_stat_drop": {"spa": -2}, "gen_specific": {"8": {"banned": True}, "9": {"banned": True, "unbanned_from": "3.0.0"}}},  # Gen VIII: Banned, Gen IX: Banned until v3.0.0
    "psycho-cut": {"high_crit": True, "sharpness_boost": True},
    "zen-headbutt": {"chance": 0.2, "flinch": True},
    "heart-stamp": {"chance": 0.3, "flinch": True},
    "synchronoise": {"hits_same_type": True},
    "stored-power": {"power_per_boost": 20},  # 20 + 20 per stat boost
    "psyshock": {"uses_defense": True},
    "expanding-force": {
        "boosted_in_terrain": "psychic",
        "hits_adjacent_foes": True
    },
    "freezing-glare": {"chance": 0.1, "status": "frz"},
    "esper-wing": {"chance": 1.0, "stat_boost": {"spe": 1}, "high_crit": True},
    "lumina-crash": {"chance": 1.0, "stat_drop": {"spd": -2}},
    
    # Bug moves
    "twineedle": {"multi_hit": 2, "chance": 0.2, "status": "psn"},
    "pin-missile": {"multi_hit": "2-5"},
    "leech-life": {"drain": 0.5},
    "fury-cutter": {"variable_power": "fury_cutter"},
    "megahorn": {},
    "silver-wind": {"chance": 0.1, "stat_boost": {"atk": 1, "defn": 1, "spa": 1, "spd": 1, "spe": 1}},
    "signal-beam": {"chance": 0.1, "confuse": True},
    "u-turn": {"switches_out": True},
    "x-scissor": {"sharpness_boost": True},
    "bug-buzz": {"chance": 0.1, "stat_drop": {"spd": -1}, "sound_move": True},
    "attack-order": {"high_crit": True},
    "struggle-bug": {"chance": 1.0, "stat_drop": {"spa": -1}},
    "lunge": {"chance": 1.0, "target_stat_drop": {"atk": -1}},
    "first-impression": {
        "priority": 2,
        "first_turn_only": True,
        "gen_specific": {"8-brilliant-diamond-shining-pearl": {"banned": True}}
    },
    "pollen-puff": {
        "heals_if_ally": True,
        "bulletproof_immune": True,
        "blocked_by_telepathy": True,
        "gen_specific": {"8-brilliant-diamond-shining-pearl": {"banned": True}}
    },
    "skitter-smack": {"chance": 1.0, "stat_drop": {"spa": -1}},
    
    # Rock moves
    "rock-throw": {"gen_specific": {"1": {"accuracy": 65}, "2+": {"accuracy": 90}}},
    "rock-slide": {"chance": 0.3, "flinch": True, "gen_specific": {"1": {"chance": 0.0}}},  # Gen I: No flinch, Gen II+: 30% flinch
    "rollout": {"consecutive_power": True, "boosted_defense_curl": True},
    "ancient-power": {"chance": 0.1, "stat_boost": {"atk": 1, "defn": 1, "spa": 1, "spd": 1, "spe": 1}},
    "rock-blast": {"multi_hit": "2-5", "gen_specific": {"7+": {"bulletproof_immune": True}}},  # Gen VII+: Bulletproof immune, Gen VII+ Stamina activates
    "power-gem": {"gen_specific": {"4-5": {"power": 70}, "6+": {"power": 80}}},
    "rock-wrecker": {"must_recharge": True},
    "stone-edge": {"high_crit": True},
    "head-smash": {"recoil": 0.5},
    "smack-down": {"grounds_target": True, "removes_fly_dig": True},
    "accelerock": {"priority": 1},
    "diamond-storm": {
        "chance": 0.5,
        "stat_boost": {"defn": 1},
        "gen_specific": {"7+": {"stat_boost": {"defn": 2}}}
    },
    "meteor-beam": {"charges": True, "stat_boost_charge": {"spa": 1}},
    "clanging-scales": {"self_stat_drop": {"defn": -1}},
    
    # Ghost moves
    "lick": {"chance": 0.3, "status": "par"},
    "night-shade": {"fixed_damage": "level"},
    "confuse-ray": {"status_move": True, "confuse": True},
    "shadow-punch": {"never_miss": True},
    "astonish": {"chance": 0.3, "flinch": True, "gen_specific": {"3": {"doubled_minimize": True}}},  # Gen III only: Double damage vs Minimize
    "shadow-sneak": {"priority": 1},
    "shadow-claw": {"high_crit": True, "sharpness_boost": True},
    "ominous-wind": {"chance": 0.1, "stat_boost": {"atk": 1, "defn": 1, "spa": 1, "spd": 1, "spe": 1}},
    "hex": {"doubled_if_status": True},
    "phantom-force": {"semi_invulnerable": True, "ignores_protect": True},
    "shadow-bone": {"chance": 0.2, "stat_drop": {"defn": -1}},
    "spectral-thief": {"steals_boosts": True},
    "moongeist-beam": {"ignores_ability": True},
    "astral-barrage": {"ignores_ability": True},
    "bitter-malice": {"chance": 1.0, "stat_drop": {"atk": -1}},
    "rage-fist": {"power_per_hit_taken": 50},  # 50 + 50 per hit
    "last-respects": {"power_per_faint": 50},  # 50 + 50 per fainted ally
    
    # Dragon moves
    "dragon-rage": {"fixed_damage": 40, "gen_specific": {"1-2": {"affected_by_immunities": True}, "3-4": {"affected_by_kings_rock": True}, "5-7": {"affected_by_kings_rock": True}, "8+": {"banned": True}}},
    "twister": {"chance": 0.2, "flinch": True, "wind_move": True},  # Wind move (Gen VI+)
    "dragon-breath": {"chance": 0.3, "status": "par"},
    "dragon-claw": {},
    "dragon-pulse": {
        "gen_specific": {
            "4-5": {"power": 90},
            "6+": {"power": 85, "mega_launcher_boost": True}
        }
    },
    "dragon-rush": {
        "chance": 0.2,
        "flinch": True,
        "doubled_minimize": True,
        "gen_specific": {
            "4": {"affected_by_kings_rock": True},
            "5+": {"not_affected_by_kings_rock": True}
        }
    },
    "draco-meteor": {
        "self_stat_drop": {"spa": -2},
        "gen_specific": {
            "4-5": {"power": 140},
            "6+": {"power": 130}
        }
    },
    "dual-chop": {"multi_hit": 2, "gen_specific": {"9+": {"banned": True}}},
    "dragon-tail": {
        "priority": -6,
        "forces_switch": True,
        "force_switch_blocked_by_substitute": True,
        "force_switch_blocked_by_ingrain": True,
        "force_switch_blocked_by_suction_cups": True,
        "gen_specific": {"8+": {"fails_on_dynamax": True}}
    },
    "breaking-swipe": {"chance": 1.0, "target_stat_drop": {"atk": -1}},
    "clanging-scales": {"self_stat_drop": {"defn": -1}},
    "clangorous-soul": {"status_move": True, "stat_boost": {"atk": 1, "defn": 1, "spa": 1, "spd": 1, "spe": 1}, "costs_hp": 0.33},
    "spacial-rend": {"high_crit": True},
    "roar-of-time": {"must_recharge": True},
    "dragon-darts": {
        "multi_hit": 2,
        "gen_specific": {
            "8-brilliant-diamond-shining-pearl": {"banned": True}
        }
    },
    "glaive-rush": {"user_vulnerable_next_turn": True},
    
    # Dark moves
    "bite": {"chance": 0.3, "flinch": True},
    "thief": {"steals_item": True},
    # Feint Attack: Gen II-III no contact/bypasses accuracy, Gen IV-VII contact, Gen VIII+ banned
    "feint-attack": {"never_miss": True, "contact": False},  # Default Gen II-III (no contact), override in engine.py for Gen IV-VII
    "pursuit": {"doubled_if_switching": True},
    "crunch": {"chance": 0.2, "stat_drop": {"defn": -1}, "gen_specific": {"2-3": {"stat_drop": {"spd": -1}}, "4+": {"stat_drop": {"defn": -1}}}},
    "beat-up": {"multi_hit_party": True},
    "torment": {"status_move": True, "torments": True, "gen_specific": {"1-4": {"reflected_by_magic_coat": False}, "5+": {"reflected_by_magic_coat": True}}},  # Gen I-IV: Not reflected by Magic Coat, Gen V+: Reflected by Magic Coat
    "flatter": {"status_move": True, "confuse": True, "stat_boost_target": {"spa": 1}},
    "snatch": {"status_move": True, "steals_stat_moves": True, "priority": 4},
    "payback": {"doubled_if_hit_after": True},
    "assurance": {"doubled_if_damaged": True},
    "fling": {"variable_power": "item_fling"},
    "punishment": {"variable_power": "punishment", "gen_specific": {"8+": {"banned": True}}},  # Power = 60 + 20 per stat boost (max 200), Gen VIII+ banned
    "sucker-punch": {"priority": 1, "fails_if_not_attacking": True, "gen_specific": {"4": {"power": 80}, "5-6": {"power": 80, "succeeds_on_me_first": True}, "7+": {"power": 70}}},  # Gen IV-VI: 80 BP, Gen V+: Succeeds on Me First, Gen VII+: 70 BP
    "dark-void": {
        "status_move": True,
        "status": "slp",
        "accuracy": 50,
        "darkrai_only": True,
        "gen_specific": {
            "4-6": {"accuracy": 80, "darkrai_only": False},
            "7": {"accuracy": 50, "darkrai_only": True},
            "8+": {"banned": True}
        }
    },
    "night-daze": {"chance": 0.4, "stat_drop": {"accuracy": -1}},
    "foul-play": {"uses_target_attack": True},
    "snarl": {"chance": 1.0, "stat_drop": {"spa": -1}},
    "brutal-swing": {},
    "throat-chop": {"silences": True},  # Can't use sound moves
    "lash-out": {"doubled_if_stats_lowered": True},
    "wicked-blow": {"always_crit": True, "ignores_protect": False},
    "fiery-wrath": {"chance": 0.2, "flinch": True},
    "kowtow-cleave": {"never_miss": True},
    
    # Steel moves
    "metal-claw": {"chance": 0.1, "stat_boost": {"atk": 1}},
    "steel-wing": {"chance": 0.1, "stat_boost": {"defn": 1}},
    "meteor-mash": {"chance": 0.2, "stat_boost": {"atk": 1}, "high_crit": False},
    "iron-defense": {"status_move": True, "stat_boost": {"defn": 2}},
    "doom-desire": {"delayed": True, "turns": 2},
    "iron-head": {
        "chance": 0.3,
        "flinch": True,
        "gen_specific": {
            "4": {"affected_by_kings_rock": True},
            "5+": {"not_affected_by_kings_rock": True}
        }
    },
    "magnet-bomb": {
        "never_miss": True,
        "gen_specific": {
            "6-7": {"bulletproof_immune": True},
            "8+": {"banned": True}
        }
    },
    "bullet-punch": {"priority": 1},
    "flash-cannon": {"chance": 0.1, "stat_drop": {"spd": -1}},
    "gear-grind": {"multi_hit": 2, "gen_specific": {"9+": {"banned": True}}},
    "heavy-slam": {"variable_power": "weight_ratio", "doubled_minimize": True},
    "smart-strike": {"never_miss": True},
    "anchor-shot": {
        "chance": 1.0,
        "traps": True,
        "traps_opponent": True,
        "gen_specific": {"8-brilliant-diamond-shining-pearl": {"banned": True}, "9+": {"banned": True}}
    },
    "sunsteel-strike": {"ignores_ability": True},
    "double-iron-bash": {"multi_hit": 2, "chance": 0.3, "flinch": True},
    "behemoth-blade": {"doubled_vs_dynamax": True},
    "behemoth-bash": {"doubled_vs_dynamax": True},
    "steel-beam": {"recoil": 0.5},
    "steel-roller": {"destroys_terrain": True, "fails_no_terrain": True},
    "make-it-rain": {"self_stat_drop": {"spa": -1}, "money": True},
    "gigaton-hammer": {"cannot_use_twice": True},
    
    # Fairy moves
    "fairy-wind": {"wind_move": True},
    "draining-kiss": {"drain": 0.75},
    "disarming-voice": {"never_miss": True, "sound_move": True, "hits_substitute": True},
    "play-rough": {"chance": 0.1, "stat_drop": {"atk": -1}},
    "baby-doll-eyes": {
        "status_move": True,
        "target_stat_drop": {"atk": -1},
        "priority": 1,
        "z_boost_effect": {"stat_boost": {"defn": 1}}
    },
    "dazzling-gleam": {"hits_adjacent_foes": True},
    "aromatic-mist": {
        "status_move": True,
        "target_stat_boost": {"spd": 1},
        "z_boost_effect": {"stat_boost": {"spd": 2}}
    },
    "geomancy": {
        "status_move": True,
        "z_boost_effect": {"stat_boost": {"atk": 1, "defn": 1, "spa": 1, "spd": 1, "spe": 1}},
        "gen_specific": {"9+": {"banned": True}}
    },
    "fleur-cannon": {"self_stat_drop": {"spa": -2}},
    "spirit-break": {"chance": 1.0, "stat_drop": {"spa": -1}},
    "strange-steam": {"chance": 0.2, "confuse": True},
    "misty-explosion": {"boosted_in_terrain": True, "faints_user": True},
    # Gen VIII: Incarnate = chance to boost user off/def; Therian = chance to lower target off/def. Gen IX: power 100, always 30% lower target Attack by 1, wind move, accuracy unaffected by rain.
    "springtide-storm": {"chance": 0.3, "stat_drop": {"atk": -1}, "wind_move": True, "gen_specific": {"8": {"form_effect": True, "incarnate_boost_self": {"atk": 1, "spa": 1, "defn": 1, "spd": 1}, "therian_drop_target": {"atk": -1, "spa": -1, "defn": -1, "spd": -1}}, "9": {"chance": 0.3, "stat_drop": {"atk": -1}, "wind_move": True}}},
    
    # Normal moves with special mechanics
    "tackle": {},
    "scratch": {},
    "pound": {},
    "mega-punch": {},
    "pay-day": {"money": True},
    "comet-punch": {"multi_hit": "2-5"},
    "mega-kick": {},
    "headbutt": {"chance": 0.3, "flinch": True},
    "horn-attack": {},
    "fury-attack": {"multi_hit": "2-5"},
    "horn-drill": {"ohko": True},
    "body-slam": {"chance": 0.3, "status": "par", "doubled_minimize": True},
    "wrap": {"chance": 1.0, "traps": True},
    "take-down": {"recoil": 0.25},
    "thrash": {"rampage": True, "duration": 2},
    "double-edge": {"recoil": 0.33},
    "hyper-beam": {"must_recharge": True},
    "self-destruct": {"faints_user": True},
    "explosion": {"faints_user": True},
    "egg-bomb": {},
    "swift": {"never_miss": True, "hits_semi_invulnerable_gen1": True},  # Gen I: Can hit semi-invulnerable, Gen II+: Cannot
    "skull-bash": {"charges": True, "stat_boost_charge": {"defn": 1}},
    "spike-cannon": {"multi_hit": "2-5"},
    "constrict": {"chance": 0.1, "stat_drop": {"spe": -1}},
    "slash": {"high_crit": True},  # Also boosted by Sharpness (handled in engine.py)
    "tri-attack": {"chance": 0.2, "status_random": ["brn", "frz", "par"]},
    "super-fang": {"halves_hp": True},
    "rage": {"boosts_on_hit": True, "gen_specific": {"1": {"continuous_move": True, "never_stops": True, "pp_on_select_only": True, "builds_on_disabled": True}, "2": {"rage_counter": True, "damage_multiplier": True}, "3": {"builds_even_if_miss": True}, "4-7": {"builds_after_success": True}, "8+": {"banned": True}}},
    "dizzy-punch": {"chance": 0.2, "confuse": True, "gen_specific": {"1": {"chance": 0.0}}},  # Gen I: No confusion, Gen II-VII: 20% confusion
    "stomp": {"chance": 0.3, "flinch": True, "doubled_minimize": True},
    "hyper-fang": {"chance": 0.1, "flinch": True},
    "snore": {"chance": 0.3, "flinch": True, "only_while_asleep": True},
    "false-swipe": {"leaves_1hp": True},
    "fling": {"variable_power": "item_fling", "throws_item": True},
    "endeavor": {"damage_to_match_hp": True},
    "slam": {},
    "vice-grip": {},
    "guillotine": {"ohko": True},
    "rapid-spin": {"removes_hazards": "self", "gen_specific": {"8+": {"stat_boost": {"spe": 1}}}},
    "bide": {"priority": 1, "charges_2_turns": True, "returns_double": True},
    "giga-impact": {"must_recharge": True},
    "echoed-voice": {"variable_power": "echoed_voice"},
    "chip-away": {"ignores_stat_changes": True},
    "retaliate": {"doubled_if_ally_fainted": True},
    "facade": {"doubled_if_status": True},
    "crush-grip": {"variable_power": "target_hp"},
    "wring-out": {"variable_power": "target_hp"},
    "fake-out": {
        "priority": 3,
        "flinch": True,
        "first_turn_only": True,
        "contact": True,
        "gen_specific": {
            "3": {"priority": 1, "contact": False},
            "4": {"priority": 1, "contact": True}
        }
    },
    "extreme-speed": {"priority": 2, "gen_specific": {"2-4": {"priority": 1}, "5+": {"priority": 2}}},
    "boomburst": {
        "sound_move": True,
        "hits_adjacent": True,
        "hits_allies": True,
        "hits_substitute": True
    },
    "double-hit": {"multi_hit": 2},
    "round": {"boosted_if_used_together": True},
    "relic-song": {
        "chance": 0.1,
        "status": "slp",
        "sound_move": True,
        "hits_adjacent_foes": True,
        "changes_form": True,
        "gen_specific": {
            "5": {"hits_substitute": True},
            "6+": {"hits_substitute": True, "bypasses_substitute": True}
        }
    },
    "secret-sword": {"uses_defense": True, "sharpness_boost": True},
    "techno-blast": {
        "type_varies": True,
        "gen_specific": {
            "5": {"power": 85},
            "6+": {"power": 120}
        }
    },
    "tail-slap": {"multi_hit": "2-5"},
    "multi-attack": {"type_varies": True},
    "breakneck-blitz": {},  # Z-move
    "tera-blast": {"type_varies_tera": True},
    "population-bomb": {"multi_hit": 10},
    "hyper-drill": {"ignores_protect": True},
    "double-shock": {"removes_electric_type": True},
    
    # ========== FINAL BATCH - REMAINING MOVES ==========
    # More status moves
    "tail-glow": {"status_move": True, "stat_boost": {"spa": 3}},
    "spite": {"status_move": True, "reduces_pp": 4, "gen_specific": {"1-4": {"reflected_by_magic_coat": False}, "5+": {"reflected_by_magic_coat": True}}},  # Gen I-IV: Not reflected by Magic Coat, Gen V+: Reflected by Magic Coat
    "switcheroo": {"status_move": True, "swaps_items": True},
    "trick": {"status_move": True, "swaps_items": True},
    "sweet-scent": {
        "status_move": True,
        "target_stat_drop": {"evasion": -2},
        "gen_specific": {
            "2": {"chance": 0.75, "target_stat_drop": {"evasion": -1}},
            "3-5": {"target_stat_drop": {"evasion": -1}},
            "6+": {"target_stat_drop": {"evasion": -2}}
        }
    },
    "topsy-turvy": {"status_move": True, "inverts_stat_changes": True},
    "toxic-thread": {
        "status_move": True,
        "status": "psn",
        "target_stat_drop": {"spe": -1},
        "always_lowers_speed": True,
        "z_boost_effect": {"stat_boost": {"spe": 1}}
    },
    "tearful-look": {
        "status_move": True,
        "target_stat_drop": {"atk": -1, "spa": -1},
        "never_miss": True,
        "bypasses_standard_protect": True,
        "blocked_by_crafty_shield": True,
        "z_boost_effect": {"stat_boost": {"defn": 1}}
    },
    "take-heart": {"status_move": True, "stat_boost": {"spa": 1, "spd": 1}, "heals_status": True},
    "victory-dance": {"status_move": True, "stat_boost": {"atk": 1, "defn": 1, "spe": 1}},
    "spicy-extract": {"status_move": True, "target_stat_boost": {"atk": 2}, "target_stat_drop": {"defn": -2}},
    "shelter": {"status_move": True, "stat_boost": {"defn": 2}},
    "shed-tail": {"status_move": True, "creates_substitute": True, "switches_out": True, "costs_hp": 0.5},
    "tidy-up": {"status_move": True, "stat_boost": {"atk": 1, "spe": 1}, "removes_hazards": True},
    "salt-cure": {"status_move": True, "curses_with_salt": True},
    
    # More attacking moves  
    "aqua-cutter": {"high_crit": True},
    "aqua-step": {"chance": 1.0, "stat_boost": {"spe": 1}},
    "aura-wheel": {"chance": 1.0, "stat_boost": {"spe": 1}},
    "bitter-blade": {"drain": 0.5},
    "bolt-beak": {"doubled_if_move_first": True},
    "bug-bite": {"eats_berry": True},
    "ceaseless-edge": {"sets_hazard": "spikes"},
    "comeuppance": {"returns_damage": True, "priority": 0},
    "covet": {"steals_item": True},
    "cut": {},
    "darkest-lariat": {
        "ignores_stat_changes": True,
        "gen_specific": {
            "8-brilliant-diamond-shining-pearl": {"banned": True}
        }
    },
    "dire-claw": {"chance": 0.5, "status_random": ["psn", "par", "slp"]},
    "dragon-ascent": {"self_stat_drop": {"defn": -1, "spd": -1}},
    "dragon-hammer": {},
    "drum-beating": {"chance": 1.0, "stat_drop": {"spe": -1}},
    "electro-drift": {"boosted_super_effective": 1.33},
    "eternabeam": {"must_recharge": True},
    "fishious-rend": {"doubled_if_move_first": True},
    "flower-trick": {"always_crit": True, "never_miss": True},
    "flying-press": {
        "dual_type": "flying",
        "doubled_minimize": True,
        "fails_in_gravity": True,
        "gen_specific": {
            "6": {"power": 80},
            "7+": {"power": 100}
        }
    },
    "glacial-lance": {},
    "headlong-rush": {"self_stat_drop": {"defn": -1, "spd": -1}},
    "ice-hammer": {
        "self_stat_drop": {"spe": -1},
        "gen_specific": {"8+": {"banned": True}}
    },
    "icicle-spear": {"multi_hit": "2-5"},
    "ivy-cudgel": {"high_crit": True, "type_varies": True},
    "jaw-lock": {
        "traps_both": True,
        "gen_specific": {
            "8-brilliant-diamond-shining-pearl": {"banned": True}
        }
    },
    "jetpunch": {"priority": 1},  # Duplicate of jet-punch
    "jungle-healing": {"status_move": True, "heals_team": 0.25, "heals_status": True},
    "lash-out": {"doubled_if_stats_lowered": True},
    "leaf-blade": {"high_crit": True, "gen_specific": {"3": {"power": 70}, "4+": {"power": 90, "boosted_by_sharpness": True}}},  # Gen III: 70 BP, Gen IV+: 90 BP, Sharpness boost
    "malicious-moonsault": {"doubled_minimize": True},
    "matcha-gotcha": {"drain": 0.5, "chance": 0.2, "status": "brn"},
    "max-airstream": {"chance": 1.0, "stat_boost": {"spe": 1}},
    "max-darkness": {"chance": 1.0, "stat_drop": {"spd": -1}},
    "max-flare": {"weather": "sun"},
    "max-flutterby": {"chance": 1.0, "stat_drop": {"spa": -1}},
    "max-geyser": {"weather": "rain"},
    "max-guard": {
        "status_move": True,
        "protects": True,
        "protection": "max-guard",
        "priority": 4,
        "gen_specific": {
            "8-brilliant-diamond-shining-pearl": {"banned": True}
        }
    },
    "max-hailstorm": {"weather": "hail"},
    "max-knuckle": {"chance": 1.0, "stat_boost": {"atk": 1}},
    "max-lightning": {"terrain": "electric"},
    "max-mindstorm": {"terrain": "psychic"},
    "max-ooze": {"chance": 1.0, "stat_boost": {"spa": 1}},
    "max-overgrowth": {"terrain": "grassy"},
    "max-phantasm": {"chance": 1.0, "stat_drop": {"defn": -1}},
    "max-quake": {"chance": 1.0, "stat_boost": {"spd": 1}},
    "max-rockfall": {"weather": "sandstorm"},
    "max-starfall": {"terrain": "misty"},
    "max-steelspike": {"chance": 1.0, "stat_boost": {"defn": 1}},
    "max-strike": {"chance": 1.0, "stat_drop": {"spe": -1}},
    "max-wyrmwind": {"chance": 1.0, "stat_drop": {"atk": -1}},
    "meteor-assault": {"must_recharge": True},
    "mountain-gale": {"chance": 0.3, "flinch": True},
    "no-retreat": {
        "status_move": True,
        "stat_boost": {"atk": 1, "defn": 1, "spa": 1, "spd": 1, "spe": 1},
        "traps_self": True,
        "gen_specific": {
            "8-brilliant-diamond-shining-pearl": {"banned": True}
        }
    },
    "order-up": {"chance": 1.0, "stat_boost_if_tatsugiri": True},
    "petal-dance": {"rampage": True, "confuse_after": True, "gen_specific": {"1": {"duration_range": [3, 4], "power": 70, "pp": 20}, "2-3": {"duration_range": [2, 3], "power": 70}, "4": {"duration_range": [2, 3], "power": 90}, "5+": {"duration": 4, "power": 120, "pp": 10, "disrupted_by_miss": True}}},
    "plasma-fists": {"electrifies_normal": True},
    "poltergeist": {"fails_if_no_item": True},
    "precipice-blades": {"hits_adjacent_foes": True},
    "prismatic-laser": {"must_recharge": True},
    "psyblade": {"boosted_in_electric_terrain": True},
    "pyro-ball": {"chance": 0.1, "status": "brn"},
    "raging-bull": {"breaks_screens": True, "type_varies": True},
    "raging-fury": {"rampage": True, "duration": 2},
    "relic-song": {
        "chance": 0.1,
        "status": "slp",
        "sound_move": True,
        "hits_adjacent_foes": True,
        "changes_form": True,
        "gen_specific": {
            "5": {"hits_substitute": True},
            "6+": {"hits_substitute": True, "bypasses_substitute": True}
        }
    },
    "revival-blessing": {"status_move": True, "revives_fainted": True},
    "rock-tomb": {"chance": 1.0, "stat_drop": {"spe": -1}},
    "sandsear-storm": {"chance": 0.2, "status": "brn"},
    "searing-sunraze-smash": {"ignores_ability": True},
    "shell-trap": {"priority": -3, "activates_if_hit_physical": True},
    "shore-up": {
        "status_move": True,
        "heal": 0.5,
        "heals_more_in_sand": True,
        "z_boost_effect": {"reset_lower_stats": True},
        "gen_specific": {
            "8-brilliant-diamond-shining-pearl": {"banned": True},
            "9+": {"pp": 5}
        }
    },
    "silk-trap": {"status_move": True, "protects": True, "lowers_speed_contact": True},
    "snap-trap": {"chance": 1.0, "traps": True, "trap_damage": 0.125},
    "skitter-smack": {"chance": 1.0, "stat_drop": {"spa": -1}},
    "snap-trap": {"chance": 1.0, "traps": True},
    "snipe-shot": {
        "high_crit": True,
        "ignores_redirection": True,
        "gen_specific": {
            "8-brilliant-diamond-shining-pearl": {"banned": True}
        }
    },
    "sparkling-aria": {
        "heals_burn": True,
        "sound_move": True,
        "hits_adjacent": True,
        "hits_allies": True,
        "hits_substitute": True,
        "gen_specific": {"8-brilliant-diamond-shining-pearl": {"banned": True}}
    },
    "steam-roller": {"chance": 0.3, "flinch": True, "doubled_minimize": True},
    "stone-axe": {"sets_hazard": "stealth-rock"},
    "strange-steam": {"chance": 0.2, "confuse": True},
    "surging-strikes": {"multi_hit": 3, "always_crit": True},
    "syrup-bomb": {"stat_drop_over_time": {"spe": -1}},
    "temper-flare": {"doubled_if_failed_last": True},
    "thunder-cage": {"chance": 1.0, "traps": True, "trap_damage": 0.0625},
    "thunderous-kick": {"chance": 1.0, "stat_drop": {"defn": -1}},
    "torch-song": {"chance": 1.0, "stat_boost": {"spa": 1}},
    "triple-arrows": {"chance": 0.5, "stat_drop": {"defn": -1}, "chance2": 0.3, "flinch": True},
    "triple-dive": {"multi_hit": 3},
    "twin-beam": {"multi_hit": 2},
    "twineedle": {"multi_hit": 2, "chance": 0.2, "status": "psn"},
    "v-create": {
        "self_stat_drop": {"defn": -1, "spd": -1, "spe": -1},
        "gen_specific": {"9+": {"banned": True}}
    },
    "victory-dance": {"status_move": True, "stat_boost": {"atk": 1, "defn": 1, "spe": 1}},
    "volt-tackle": {"recoil": 0.33, "chance": 0.1, "status": "par"},
    "wave-crash": {"recoil": 0.33},
    "wicked-torque": {"chance": 0.1, "status": "slp"},
    "wildbolt-storm": {"chance": 0.2, "status": "par"},
    "triple-kick": {"multi_hit": 3, "increasing_power": True},
    
    # Signature/rare moves
    "aeroblast": {"high_crit": True},
    "barrage": {"multi_hit": "2-5"},
    "beak-blast": {"priority": -3, "burns_contact": True},
    "bleakwind-storm": {"chance": 0.3, "stat_drop": {"spe": -1}},
    "branch-poke": {},
    "brutal-swing": {},
    "buzzsaw": {},  # Not in DB
    "combat-torque": {"chance": 0.3, "status": "par"},
    "double-shock": {"removes_electric_type": True},
    "dragapult": {},  # Not a move
    "endbringer": {},  # Custom?
    "esper-wing": {"chance": 1.0, "stat_boost": {"spe": 1}, "high_crit": True},
    "fiery-dance": {"chance": 0.5, "stat_boost": {"spa": 1}},
    "flip-turn": {"switches_out": True},
    "floaty-fall": {"chance": 0.3, "flinch": True},
    "freeze-shock": {"charges": True, "chance": 0.3, "status": "par"},
    "frost-breath": {
        "always_crit": True,
        "gen_specific": {
            "5": {"power": 40},
            "6+": {"power": 60}
        }
    },
    "g-max-befuddle": {"chance": 0.3, "confuse": True},
    "g-max-cannonade": {"chance": 1.0, "traps": True},
    "g-max-centiferno": {"chance": 1.0, "traps": True},
    "g-max-chi-strike": {"boosts_crit_ratio": True},
    "g-max-cuddle": {"chance": 1.0, "infatuates": True},
    "g-max-depletion": {"reduces_pp": 2},
    "g-max-drum-solo": {"ignores_ability": True},
    "g-max-finale": {"heals_team": 0.167},
    "g-max-fireball": {"ignores_ability": True},
    "g-max-foam-burst": {"chance": 1.0, "stat_drop": {"spe": -2}},
    "g-max-gold-rush": {"confuse": True, "money": True},
    "g-max-gravitas": {"terrain": "gravity"},
    "g-max-hydrosnipe": {"ignores_ability": True},
    "g-max-malodor": {"chance": 1.0, "status": "psn"},
    "g-max-meltdown": {"prevents_ability": True},
    "g-max-one-blow": {"ignores_protect": True},
    "g-max-rapid-flow": {"ignores_protect": True},
    "g-max-replenish": {"restores_berries": True},
    "g-max-resonance": {"sets_aurora_veil": True},
    "g-max-sandblast": {"chance": 1.0, "traps": True},
    "g-max-smite": {"chance": 1.0, "confuse": True},
    "g-max-snooze": {"chance": 1.0, "yawns": True},
    "g-max-steelsurge": {"sets_hazard": "stealth-rock"},
    "g-max-stonesurge": {"sets_hazard": "stealth-rock"},
    "g-max-stun-shock": {"chance": 1.0, "status_random": ["par", "psn"]},
    "g-max-sweetness": {"heals_status": True},
    "g-max-tartness": {"target_stat_drop": {"evasion": -1}},
    "g-max-terror": {"traps": True},
    "g-max-vine-lash": {"chance": 1.0, "traps": True},
    "g-max-volcalith": {"sets_hazard": "stealth-rock"},
    "g-max-volt-crash": {"chance": 1.0, "status": "par"},
    "g-max-wildfire": {"chance": 1.0, "traps": True},
    "g-max-wind-rage": {"removes_screens": True},
    
    # More standard moves
    # (absorb and mega-drain already defined in draining moves section)
    "psy-shield-bash": {"chance": 1.0, "stat_boost": {"defn": 1}},
    "mystical-power": {"chance": 1.0, "stat_boost": {"spa": 1}},
    "barb-barrage": {"chance": 0.5, "status": "psn", "doubled_if_poisoned": True},
    "dire-claw": {"chance": 0.5, "status_random": ["psn", "par", "slp"]},
    "ceaseless-edge": {"sets_hazard": "spikes"},
    "stone-axe": {"sets_hazard": "stealth-rock"},
    "mountain-gale": {"chance": 0.3, "flinch": True},
    "victory-dance": {"status_move": True, "stat_boost": {"atk": 1, "defn": 1, "spe": 1}},
    "headlong-rush": {"self_stat_drop": {"defn": -1, "spd": -1}},
    "barb-barrage": {"chance": 0.5, "status": "psn", "doubled_if_poisoned": True},
    "springtide-storm": {"chance": 0.3, "stat_drop": {"atk": -1}},
    "mystical-power": {"chance": 1.0, "stat_boost": {"spa": 1}},
    "raging-fury": {"rampage": True, "duration": 2},
    "wave-crash": {"recoil": 0.33},
    "chloroblast": {"recoil": 0.5},
    "lunar-blessing": {"status_move": True, "heals_user_and_ally": 0.25},
    "take-heart": {"status_move": True, "stat_boost": {"spa": 1, "spd": 1}, "heals_status": True},
    "tera-starstorm": {},
    "double-shock": {"removes_electric_type": True},
    "gigaton-hammer": {"cannot_use_twice": True},
    "rage-fist": {"power_per_hit_taken": 50},
    "armor-cannon": {"self_stat_drop": {"defn": -1, "spd": -1}},
    "bitter-blade": {"drain": 0.5},
    "aqua-cutter": {"high_crit": True},
    "blazing-torque": {"chance": 0.3, "status": "brn"},
    "noxious-torque": {"chance": 0.3, "status": "psn"},
    "combat-torque": {"chance": 0.3, "status": "par"},
    "magical-torque": {"chance": 0.3, "confuse": True},
    "wicked-torque": {"chance": 0.1, "status": "slp"},
    "psyblade": {"boosted_in_electric_terrain": True},
    "hydro-steam": {"boosted_in_sun": True},
    "ruination": {"halves_hp": True},
    "collision-course": {"boosted_super_effective": 1.33},
    "electro-drift": {"boosted_super_effective": 1.33},
    "shed-tail": {"status_move": True, "creates_substitute": True, "switches_out": True, "costs_hp": 0.5},
    "chilly-reception": {"status_move": True, "weather": "snow", "switches_out": True},
    "tidy-up": {"status_move": True, "stat_boost": {"atk": 1, "spe": 1}, "removes_hazards": True},
    "snowscape": {"status_move": True, "weather": "snow"},
    "pounce": {"chance": 1.0, "stat_drop": {"spe": -1}},
    "trailblaze": {"chance": 1.0, "stat_boost": {"spe": 1}},
    "chilling-water": {"chance": 1.0, "target_stat_drop": {"atk": -1}},
    "hyper-drill": {"ignores_protect": True},
    "twin-beam": {"multi_hit": 2},
    "rage-fist": {"power_per_hit_taken": 50},
    "armor-cannon": {"self_stat_drop": {"defn": -1, "spd": -1}},
    "bitter-malice": {"chance": 1.0, "stat_drop": {"atk": -1}},
    "shelter": {"status_move": True, "stat_boost": {"defn": 2}},
    "triple-arrows": {"chance": 0.5, "stat_drop": {"defn": -1}, "chance2": 0.3, "flinch": True},
    "infernal-parade": {"doubled_if_status": True},
    "barb-barrage": {"chance": 0.5, "status": "psn", "doubled_if_poisoned": True},
    "psyshield-bash": {"chance": 1.0, "stat_boost": {"defn": 1}},
    "power-shift": {"status_move": True, "swaps_atk_def_stats": True},
    "stone-axe": {"sets_hazard": "stealth-rock"},
    "springtide-storm": {"chance": 0.3, "stat_drop": {"atk": -1}},
    "mystical-power": {"chance": 1.0, "stat_boost": {"spa": 1}},
    "spicy-extract": {"status_move": True, "target_stat_boost": {"atk": 2}, "target_stat_drop": {"defn": -2}},
    "spin-out": {"self_stat_drop": {"spe": -2}},
    "population-bomb": {"multi_hit": 10},
    "ice-spinner": {"destroys_terrain": True},
    "glaive-rush": {"user_vulnerable_next_turn": True},
    "fillet-away": {"status_move": True, "stat_boost": {"atk": 2, "spa": 2, "spe": 2}, "costs_hp": 0.5},
    "kowtow-cleave": {"never_miss": True},
    "flower-trick": {"always_crit": True, "never_miss": True},
    "torch-song": {"chance": 1.0, "stat_boost": {"spa": 1}},
    "aqua-step": {"chance": 1.0, "stat_boost": {"spe": 1}},
    "raging-bull": {"breaks_screens": True, "type_varies": True},
    "make-it-rain": {"self_stat_drop": {"spa": -1}, "money": True},
    "ruination": {"halves_hp": True},
    "collision-course": {"boosted_super_effective": 1.33},
    "electro-drift": {"boosted_super_effective": 1.33},
    "shed-tail": {"status_move": True, "creates_substitute": True, "switches_out": True, "costs_hp": 0.5},
    "order-up": {"chance": 1.0, "stat_boost_if_tatsugiri": True},
    "jet-punch": {"priority": 1},
    "spicy-extract": {"status_move": True, "target_stat_boost": {"atk": 2}, "target_stat_drop": {"defn": -2}},
    "spin-out": {"self_stat_drop": {"spe": -2}},
    "axe-kick": {"chance": 0.3, "confuse_if_miss": True},
    "last-respects": {"power_per_faint": 50},
    "lumina-crash": {"chance": 1.0, "stat_drop": {"spd": -2}},
    "order-up": {"chance": 1.0, "stat_boost_if_tatsugiri": True},
    "ivy-cudgel": {"high_crit": True, "type_varies": True},
    "electro-shot": {"charges": True, "stat_boost_charge": {"spa": 1}},
    "tera-starstorm": {},
    "fickle-beam": {"chance": 0.3, "doubled_power": True},
    "burning-bulwark": {"status_move": True, "protects": True, "burns_contact": True},
    "thunderclap": {"priority": 1, "fails_if_not_attacking": True},
    "mighty-cleave": {"ignores_protect": True},
    "tachyon-cutter": {"multi_hit": 2, "never_miss": True},
    "hard-press": {"variable_power": "target_hp"},
    "dragon-cheer": {"status_move": True, "boosts_dragon_crit": True},
    "alluring-voice": {"confuse_if_stat_raised": True, "sound_move": True},
    "temper-flare": {"doubled_if_failed_last": True},
    "supercell-slam": {"recoil_miss": 0.5},
    "psychic-noise": {"chance": 1.0, "blocks_healing_2turns": True, "sound_move": True},
    "upper-hand": {"priority": 3, "flinch": True, "fails_if_not_priority": True},
    "malignant-chain": {"chance": 0.5, "badly_poisons": True},
    
    # ========== FINAL 70 MOVES - COMPLETE COVERAGE ==========
    # Physical moves
    "false-surrender": {"never_miss": True},
    "fell-stinger": {
        "stat_boost_if_ko": {"atk": 3},
        "gen_specific": {
            "6": {"power": 30, "stat_boost_if_ko": {"atk": 2}},
            "7+": {"power": 50, "stat_boost_if_ko": {"atk": 3}}
        }
    },
    "flame-charge": {"chance": 1.0, "stat_boost": {"spe": 1}},
    "grav-apple": {"chance": 1.0, "stat_drop": {"defn": -1}},
    "high-jump-kick": {"crash_damage": 0.5},
    "hyperspace-fury": {
        "ignores_protect": True,
        "self_stat_drop": {"defn": -1},
        "removes_protection": True,
        "removes_side_protection": True,
        "never_miss": True,
        "hits_substitute": True,
        "requires_species": "hoopa-unbound",
        "gen_specific": {"8": {"banned": True}}
    },
    "ice-ball": {"consecutive_power": True, "boosted_defense_curl": True},
    "iron-tail": {"chance": 0.3, "stat_drop": {"defn": -1}},
    "jump-kick": {"crash_damage": 0.5},
    "knock-off": {"removes_item": True, "boosted_if_item": True},
    "lands-wrath": {"hits_adjacent_foes": True, "gen_specific": {"9+": {"banned": True}}},
    "last-resort": {"requires_other_moves_used": True, "gen_specific": {"4": {"power": 130}, "5+": {"power": 140}}},  # Gen IV: 130 BP, Gen V+: 140 BP, requires all other moves used
    "liquidation": {"chance": 0.2, "stat_drop": {"defn": -1}},
    "metal-burst": {"returns_damage": 1.5, "gen_specific": {"1-4": {"bypasses_protect": True}, "5+": {"blocked_by_protect": True}}},  # Gen I-IV: Not blocked by Protect, Gen V+: Blocked by Protect
    "natural-gift": {"variable_power": "berry", "consumes_berry": True},
    "night-slash": {"high_crit": True, "sharpness_boost": True},  # High crit, boosted by Sharpness
    "outrage": {"rampage": True, "duration": 2},
    "psychic-fangs": {"breaks_screens": True},
    # 30% secondary effect; effect and animation by environment. Serene Grace doubles chance.
    "secret-power": {"chance": 0.3, "effect_varies_by_environment": True},
    "seismic-toss": {"fixed_damage": "level", "gen_specific": {"1": {"ignores_type_immunities": True}, "2+": {"affected_by_type_immunities": True}}},
    "sky-drop": {
        "semi_invulnerable": True,
        "takes_target": True,
        "gen_specific": {
            "6-7": {"weight_limit": 200},
            "8+": {"banned": True}
        }
    },
    "smelling-salts": {"doubled_if_paralyzed": True, "heals_paralysis": True},
    "spirit-shackle": {
        "chance": 1.0,
        "traps": True,
        "traps_opponent": True,
        "gen_specific": {"8-brilliant-diamond-shining-pearl": {"banned": True}}
    },
    "steamroller": {
        "chance": 0.3,
        "flinch": True,
        "doubled_minimize": True,
        "gen_specific": {
            "6-7": {"always_hits_minimize": True},
            "8+": {"banned": True}
        }
    },
    "strength": {},
    "thousand-arrows": {"grounds_flying": True, "gen_specific": {"9+": {"banned": True}}},
    "thousand-waves": {
        "chance": 1.0,
        "traps": True,
        "traps_opponent": True,
        "gen_specific": {"9+": {"banned": True}}
    },
    "vine-whip": {},
    "wake-up-slap": {"gen_specific": {"4-5": {"power": 60, "doubled_if_sleeping": True, "doubled_if_comatose": True, "wakes_target": True, "normal_damage_on_substitute": True}, "6-7": {"power": 70, "doubled_if_sleeping": True, "doubled_if_comatose": True, "wakes_target": True, "normal_damage_on_substitute": True}, "8+": {"banned": True}}},  # Gen IV-V: 60 BP, Gen VI-VII: 70 BP, doubles if sleeping/Comatose, wakes target, normal damage on substitute, Gen VIII+ banned
    
    # Special moves
    "blast-burn": {"must_recharge": True},
    "blood-moon": {"cannot_use_twice": True},
    "burn-up": {"removes_fire_type": True},
    "chatter": {
        "chance": 0.0,
        "confuse": True,
        "sound_move": True,
        "gen_specific": {
            "4": {"chance": 0.31},  # Assumes recorded audio (max)
            "5": {"chance": 0.10},  # Recorded audio (max)
            "6-7": {"chance": 1.0},
            "8+": {"banned": True}
        },
        "requires_chatot_for_confuse": True
    },
    "core-enforcer": {
        "suppresses_ability_if_moved": True,
        "suppression_exceptions": [
            "multitype",
            "stance-change",
            "schooling",
            "comatose",
            "shields-down",
            "disguise",
            "rks-system",
            "battle-bond",
            "power-construct",
            "as-one",
            "as-one-glastrier",
            "as-one-spectrier"
        ],
        "gen_specific": {"8-brilliant-diamond-shining-pearl": {"banned": True}, "9+": {"banned": True}}
    },
    "dark-pulse": {"chance": 0.2, "flinch": True, "gen_specific": {"4": {}, "5+": {"mega_launcher_boost": True, "not_affected_by_kings_rock": True}}},  # Gen IV: Standard, Gen V+: Boosted by Mega Launcher, not affected by King's Rock
    "dragon-energy": {"variable_power": "user_hp"},
    "dynamax-cannon": {
        "doubled_vs_dynamax": True,
        "gen_specific": {
            "8-brilliant-diamond-shining-pearl": {"banned": True},
            "9+": {"doubled_vs_dynamax": False}
        }
    },
    "eerie-spell": {"reduces_pp": 3, "sound_move": True},
    "fire-pledge": {"combo_move": True},
    "flame-burst": {
        "splash_damage": True,
        "gen_specific": {"8+": {"banned": True}}
    },
    "focus-blast": {
        "chance": 0.1,
        "stat_drop": {"spd": -1},
        "gen_specific": {
            "6+": {"bulletproof_immune": True}
        }
    },
    "frenzy-plant": {"must_recharge": True},
    "fusion-flare": {
        "boosted_if_fusion_bolt": True,
        "thaws_user": True,
        "gen_specific": {"9+": {"banned": True}}
    },
    "grass-pledge": {"combo_move": True},
    "gust": {"doubled_fly_bounce_sky_drop": True},
    "hidden-power": {"type_varies_ivs": True},
    "hydro-cannon": {"must_recharge": True},
    "hyper-voice": {"sound_move": True, "gen_specific": {"3-5": {"hits_substitute": False}, "6+": {"hits_substitute": True}}},  # Sound move, Gen VI+ hits behind substitute
    "air-cutter": {"wind_move": True, "gen_specific": {"3-5": {"power": 55}, "6+": {"power": 60, "sharpness_boost": True}}},  # Gen VI+: Power 60, boosted by Sharpness
    "weather-ball": {"doubled_in_weather": True, "gen_specific": {"3-5": {"affected_by_normalize": True}, "5+": {"unaffected_by_type_abilities": True, "bulletproof_immune": True}}},  # Doubles in weather (except strong winds), Gen III-V affected by Normalize, Gen V+ unaffected by type abilities
    "hyperspace-hole": {
        "ignores_protect": True,
        "removes_protection": True,
        "removes_side_protection": True,
        "never_miss": True,
        "hits_substitute": True,
        "gen_specific": {"8+": {"banned": True}}
    },
    "ice-burn": {"charges": True, "chance": 0.3, "status": "brn"},
    "incinerate": {"burns_berries": True},
    "judgment": {"type_varies": True},
    "leaf-tornado": {
        "chance": 0.5,
        "stat_drop": {"accuracy": -1},
        "gen_specific": {"9+": {"banned": True}}
    },
    "mind-blown": {"mind_blown_hp_loss": True, "hits_allies": True},
    "mud-shot": {"chance": 1.0, "stat_drop": {"spe": -1}},
    "mud-slap": {"chance": 1.0, "stat_drop": {"accuracy": -1}},
    "nature's-madness": {"halves_hp": True},
    "overdrive": {},
    "photon-geyser": {"checks_better_category": True},
    "revelation-dance": {
        "type_varies_user": True,
        "gen_specific": {"8+": {"banned": True}}
    },
    "rising-voltage": {"doubled_in_electric_terrain": True},
    "sonic-boom": {"fixed_damage": 20},
    "surf": {},
    "terrain-pulse": {"type_varies_terrain": True, "doubled_in_terrain": True},
    "uproar": {
        "rampage": True,
        "duration": 3,
        "prevents_sleep": True,
        "gen_specific": {
            "3-4": {"duration_range": [2, 5], "power": 50},
            "5+": {"duration": 3, "power": 90}
        }
    },
    "volt-switch": {"switches_out": True},
    "water-gun": {},
    "water-pledge": {"combo_move": True},
    "weather-ball": {"type_varies_weather": True, "doubled_in_weather": True},
    "zap-cannon": {"chance": 1.0, "status": "par", "gen_specific": {"2": {"chance": 0.996}}},  # Gen II: 99.6%, Gen III+: 100%
    
    # ========== NEW BATCH MOVES ==========
    # Recoil moves
    "take-down": {"recoil": 0.25, "gen_specific": {"1": {"recoil": 0.25, "no_recoil_on_ko": True, "no_recoil_on_substitute": True}}},
    "double-edge": {"recoil": 0.33, "gen_specific": {"1": {"recoil": 0.25, "power": 100, "no_recoil_on_ko": True, "no_recoil_on_substitute": True}, "2": {"power": 120, "recoil": 0.25, "recoil_on_substitute": True}}},
    
    # Rampage moves
    "thrash": {"rampage": True, "confuse_after": True, "gen_specific": {"1": {"duration_range": [3, 4], "power": 90, "pp": 20}, "2-4": {"duration_range": [2, 3], "power": 90}, "5+": {"duration": 4, "power": 120, "pp": 10}}},
    
    # Stat drop moves
    "tail-whip": {"status_move": True, "target_stat_drop": {"defn": -1}, "hits_adjacent": True},
    "leer": {"status_move": True, "target_stat_drop": {"defn": -1}, "hits_adjacent": True},
    "growl": {"status_move": True, "target_stat_drop": {"atk": -1}, "hits_adjacent": True, "is_sound_move": True, "gen_specific": {"1-2": {"cannot_hit_substitute": True}, "6+": {"can_hit_substitute": True}}},
    
    # Poison moves
    "poison-sting": {"chance": 0.3, "status": "psn", "gen_specific": {"1": {"chance": 0.2}}},
    "twineedle": {"multi_hit": 2, "chance": 0.2, "status": "psn", "gen_specific": {"1": {"poison_on_second_only": True, "ends_on_substitute": True}, "2": {"can_poison_steel": True, "hits_after_substitute": True}, "3": {"cannot_poison_steel": True, "no_kings_rock": True}, "4": {"poison_both_hits": True, "poison_chance_both": 0.2}, "5-7": {"kings_rock": True}, "8+": {"banned": True}}},
    
    # Multi-hit moves
    "pin-missile": {"multi_hit": True, "gen_specific": {"1": {"power": 14, "accuracy": 85, "duration_range": [2, 5], "ends_on_substitute": True}, "5": {"duration_range": [2, 5], "average_power": 36.9}, "6+": {"power": 25, "accuracy": 95, "average_power": 79.2}}},
    
    # Type-changing moves
    "bite": {"chance": 0.3, "flinch": True, "gen_specific": {"1": {"type": "Normal", "chance": 0.1}, "2-3": {"type": "Dark", "category": "special", "chance": 0.3}, "4+": {"type": "Dark", "category": "physical", "chance": 0.3}}},
    
    # Forced switch moves
    "roar": {"status_move": True, "forces_switch": True, "is_sound_move": True, "priority": -6, "gen_specific": {"1": {"priority": 0, "accuracy": 100, "level_check": True, "ends_wild_battle": True, "reflected_by_magic_coat": False}, "2": {"priority": -1, "accuracy": 100, "reflected_by_magic_coat": False}, "3-4": {"priority": -6, "level_check": True, "reflected_by_magic_coat": False}, "5": {"priority": -6, "reflected_by_magic_coat": True}, "6+": {"priority": -6, "never_miss": True, "bypasses_protect": True, "reflected_by_magic_coat": True}}},
    
    # Sleep moves
    "sing": {"status_move": True, "status": "slp", "is_sound_move": True, "gen_specific": {"1": {"can_hit_substitute": True}, "2": {"cannot_hit_substitute": True, "fail_chance": 0.25}, "6+": {"can_hit_substitute": True}}},
    
    # Confusion moves
    "supersonic": {"status_move": True, "confuse": True, "is_sound_move": True, "gen_specific": {"1-5": {"cannot_hit_substitute": True}, "6+": {"can_hit_substitute": True}}},
    
    # Fixed damage moves
    "sonic-boom": {"fixed_damage": 20, "gen_specific": {"1": {"not_affected_by_immunities": True}, "2-7": {"affected_by_immunities": True}, "8+": {"banned": True}}},
    
    # Disable move
    "disable": {"status_move": True, "disables_move": True, "gen_specific": {"1": {"accuracy": 55, "duration_range": [0, 7], "random_move_selection": True, "only_count_turns_with_action": True, "reflected_by_magic_coat": False}, "2": {"accuracy": 55, "duration_range": [2, 8], "disables_last_move": True, "only_count_turns_with_action": True, "reflected_by_magic_coat": False}, "3-4": {"accuracy": 80, "duration_range": [2, 5], "disables_last_move": True, "reflected_by_magic_coat": False}, "5+": {"accuracy": 100, "duration": 4, "disables_last_move": True, "reflected_by_magic_coat": True}}},
    
    # Stat drop moves with chance
    "acid": {"chance": 0.1, "stat_drop": {"spd": -1}, "gen_specific": {"1": {"chance": 0.332, "stat_drop": {"defn": -1}, "fail_chance": 0.25}, "2": {"chance": 0.1, "stat_drop": {"defn": -1}, "fail_chance": 0.25}, "3": {"hits_adjacent": True, "stat_drop": {"defn": -1}}, "4+": {"hits_adjacent": True}}},
    
    # Fire moves
    "ember": {"chance": 0.1, "status": "brn"},
    "flamethrower": {"chance": 0.1, "status": "brn", "gen_specific": {"1-5": {"power": 95}, "6+": {"power": 90}}},
    
    # Status field effects
    "mist": {"status_move": True, "field_effect": "mist", "gen_specific": {"1": {"protects_from_stat_drops": True, "fails_if_active": True}, "2": {"protects_from_stat_drops": True, "cannot_be_hazed": True, "can_baton_pass": True}, "3+": {"side_effect": True, "duration": 5, "can_be_defogged": True}}},
    
    # Water moves
    "hydro-pump": {"gen_specific": {"1-5": {"power": 120}, "6+": {"power": 110}}},
    "surf": {"gen_specific": {"1-2": {"power": 95}, "3": {"hits_both_opponents": True, "power": 95}, "4-5": {"hits_all_adjacent": True, "power": 95}, "6+": {"power": 90}}},
    
    # Ice moves
    "ice-beam": {"chance": 0.1, "status": "frz", "gen_specific": {"1-5": {"power": 95}, "6+": {"power": 90}}},
    "blizzard": {"chance": 0.1, "status": "frz", "gen_specific": {"1": {"accuracy": 90, "chance": 0.1, "jp_chance": 0.3}, "2-3": {"accuracy": 70, "hits_both_opponents": True}, "4-5": {"accuracy": 70, "always_hit_in_hail": True, "hits_adjacent_opponents": True}, "6+": {"accuracy": 70, "power": 110, "always_hit_in_hail": True}}},
    
    # Psychic moves
    "psybeam": {"chance": 0.1, "confuse": True},
    "bubble-beam": {"chance": 0.1, "stat_drop": {"spe": -1}, "gen_specific": {"1": {"chance": 0.332, "fail_chance": 0.25}, "2": {"chance": 0.1, "fail_chance": 0.25}}},
    "aurora-beam": {"chance": 0.1, "stat_drop": {"atk": -1}, "gen_specific": {"1": {"chance": 85/256, "fail_chance_opponent": 0.25}, "2": {"chance": 0.1, "fail_chance_opponent": 0.25, "no_fail_if_lock_on_mind_reader": True}, "3+": {"chance": 0.1}}},
    
    # Recharge moves
    "hyper-beam": {"must_recharge": True, "gen_specific": {"1": {"no_recharge_on_miss_ko_substitute": True, "binding_move_glitch": True}, "2": {"always_recharge_on_hit": True}, "3": {"affected_by_kings_rock": True}, "4+": {"category": "special"}}},
    
    # Powder status moves
    "poison-powder": {"status_move": True, "status": "psn", "is_powder": True, "gen_specific": {"1": {"can_hit_substitute": True}, "2": {"fail_chance": 0.25, "steel_immunity": True}, "3-5": {"immunity_ability": "immunity"}, "6+": {"grass_immunity": True, "overcoat_immunity": True, "safety_goggles_immunity": True}}},
    "stun-spore": {"status_move": True, "status": "par", "is_powder": True, "gen_specific": {"1": {"can_hit_substitute": True}, "2": {"fail_chance": 0.25}, "3-5": {"immunity_ability": "limber"}, "6+": {"grass_immunity": True, "electric_immunity": True, "overcoat_immunity": True, "safety_goggles_immunity": True}}},
    "sleep-powder": {"status_move": True, "status": "slp", "is_powder": True, "gen_specific": {"1": {"can_hit_substitute": True}, "2": {"fail_chance": 0.25}, "3-5": {"immunity_abilities": ["insomnia", "vital-spirit", "sap-sipper"]}, "6+": {"grass_immunity": True, "overcoat_immunity": True, "safety_goggles_immunity": True, "sweet_veil_immunity": True}}},
    
    # Rampage moves (update Petal Dance)
    "petal-dance": {"rampage": True, "confuse_after": True, "gen_specific": {"1": {"duration_range": [3, 4], "power": 70, "pp": 20}, "2-3": {"duration_range": [2, 3], "power": 70}, "4": {"duration_range": [2, 3], "power": 90}, "5+": {"duration": 4, "power": 120, "pp": 10, "disrupted_by_miss": True}}},
    
    # Stat drop moves (update String Shot)
    "string-shot": {"status_move": True, "target_stat_drop": {"spe": -1}, "gen_specific": {"1-2": {"fail_chance": 0.25, "stat_drop": {"spe": -1}}, "3-5": {"hits_adjacent": True, "stat_drop": {"spe": -1}}, "6+": {"stat_drop": {"spe": -2}, "hits_adjacent": True}}},
    
    # Fixed damage moves (duplicates removed - see earlier entries)
    
    # Paralysis moves (duplicates removed - see earlier entries)
    
    # Simple moves (duplicates removed - see earlier entries)
    
    # Ground moves (duplicates removed - see earlier entries)
    
    # OHKO moves (duplicates removed - see earlier entries)
}


def get_move_secondary_effect(move_name: str) -> Dict[str, Any]:
    """Get secondary effect data for a move."""
    normalized = move_name.lower().replace(" ", "-").strip()
    return MOVE_SECONDARY_EFFECTS.get(normalized, {})


def apply_secondary_effect(attacker: Any, defender: Any, move_name: str, move_hit: bool = True,
                           field_effects: Any = None, target_side: Any = None) -> List[str]:
    """
    Apply secondary effects of a move.
    Returns list of messages describing effects.
    
    Args:
        attacker: The attacking Mon
        defender: The defending Mon
        move_name: Name of the move
        move_hit: Whether the move successfully hit
        field_effects: FieldEffects object for generation-aware logic
    """
    messages = []
    
    effect_data = get_move_secondary_effect(move_name)
    if not effect_data:
        return messages
    
    # Self stat drops (e.g., Psycho Boost, Overheat, Superpower, Leaf Storm)
    # These are guaranteed effects, not "secondary effects" - they should happen even with Sheer Force
    # Process BEFORE move_hit check so they apply even if target faints
    if "self_stat_drop" in effect_data:
        from .engine import modify_stages
        stat_changes = effect_data["self_stat_drop"]
        stat_messages = modify_stages(attacker, stat_changes, caused_by_opponent=False, field_effects=field_effects)
        messages.extend(stat_messages)
    
    if not move_hit:
        # Target fainted - still process user stat boosts (they affect the user, not the target)
        # Process user stat boosts BEFORE returning so they apply even if target faints
        if "stat_boost" in effect_data:
            from .engine import modify_stages
            from .generation import get_generation
            
            # Use base stat_boost value (generation-specific overrides only relevant if move_hit is True)
            stat_changes = effect_data.get("stat_boost", {})
            chance = effect_data.get("chance", 1.0)
            generation = get_generation(field_effects=field_effects)
            
            if stat_changes:
                stat_changes = dict(stat_changes)
                chance = min(1.0, chance)
                roll = random.random()
                
                if roll < chance:
                    # Gen I: Amnesia raises Special (combined stat) instead of Special Defense
                    move_name_norm_stat = move_name.lower().replace(" ", "-")
                    
                    if move_name_norm_stat == "amnesia" and generation == 1 and "spd" in stat_changes:
                        special_boost = stat_changes.pop("spd")
                        stat_changes["special"] = special_boost
                    
                    # Ensure attacker has stages dict initialized
                    if not hasattr(attacker, 'stages') or not isinstance(attacker.stages, dict):
                        attacker.stages = {
                            "atk": 0, "defn": 0, "spa": 0, "spd": 0, "spe": 0, 
                            "accuracy": 0, "evasion": 0
                        }
                    # Add special stat for Gen I
                    if generation == 1 and "special" not in attacker.stages:
                        attacker.stages["special"] = 0
                    
                    stat_messages = modify_stages(attacker, stat_changes, caused_by_opponent=False, field_effects=field_effects)
                    messages.extend(stat_messages)
        
        return messages
    
    # Skip status effects for status moves - they're handled in apply_move's status move section
    # This prevents double application (e.g., Thunder Wave, Confuse Ray, Will-O-Wisp, etc.)
    if effect_data.get("status_move") and (effect_data.get("confuse") or effect_data.get("status")):
        return messages
    
    # Check abilities that modify secondary effects
    from .abilities import normalize_ability_name, get_ability_effect
    attacker_ability = normalize_ability_name(getattr(attacker, 'ability', ''))
    attacker_ability_data = get_ability_effect(attacker_ability)
    
    # Sheer Force negates secondary effects (but NOT self_stat_drop, which is processed above)
    if attacker_ability_data.get("removes_secondary_effects"):
        return messages  # No secondary effects
    
    # Covert Cloak: blocks secondary effects (status, flinch, stat drops from opponent's moves)
    if hasattr(defender, 'item') and defender.item:
        from .items import normalize_item_name, get_item_effect
        from .generation import get_generation
        def_item = normalize_item_name(defender.item)
        def_item_data = get_item_effect(def_item)
        if def_item_data.get("blocks_secondary_effects"):
            gen_cc = get_generation(field_effects=field_effects)
            if gen_cc >= 9:
                return messages  # Block all secondary effects
    
    # Serene Grace doubles secondary effect chances
    chance_multiplier = attacker_ability_data.get("secondary_effect_chance_mult", 1.0)

    from .generation import get_generation
    generation = get_generation(field_effects=field_effects)

    def _match_generation(spec: str, generation_value: int) -> bool:
        spec = (spec or "").strip()
        if not spec:
            return False
        if spec.endswith('+'):
            try:
                return generation_value >= int(spec[:-1])
            except ValueError:
                return False
        if '-' in spec:
            try:
                start_str, end_str = spec.split('-', 1)
                start = int(start_str)
                end = int(end_str)
                return start <= generation_value <= end
            except ValueError:
                return False
        try:
            return generation_value == int(spec)
        except ValueError:
            return False
    
    # === STAT BOOSTS (USER-TARGETING): Process BEFORE substitute check ===
    # Stat boosts affect the attacker, not the defender, so they should NOT be blocked by substitute
    stat_boost_present = "stat_boost" in effect_data or (
        isinstance(effect_data.get("gen_specific"), dict) and any(
            isinstance(v, dict) and v.get("stat_boost") is not None for v in effect_data["gen_specific"].values()
        )
    )
    if stat_boost_present:
        chance = effect_data.get("chance", 1.0) * chance_multiplier

        gen_specific_boost = effect_data.get("gen_specific", {})
        stat_changes = effect_data.get("stat_boost")

        if isinstance(gen_specific_boost, dict):
            for spec, overrides in gen_specific_boost.items():
                if not isinstance(overrides, dict):
                    continue
                if _match_generation(str(spec), generation):
                    if "chance" in overrides:
                        chance = overrides.get("chance", chance)
                    if "stat_boost" in overrides:
                        stat_changes = overrides.get("stat_boost")

        if stat_changes:
            stat_changes = dict(stat_changes)
            chance = min(1.0, chance)
            roll = random.random()
        else:
            roll = None

        if stat_changes and roll is not None and roll < chance:
            from .engine import modify_stages

            # Gen I: Amnesia raises Special (combined stat) instead of Special Defense
            move_name_norm_stat = move_name.lower().replace(" ", "-")
            
            if move_name_norm_stat == "amnesia" and generation == 1 and "spd" in stat_changes:
                special_boost = stat_changes.pop("spd")
                stat_changes["special"] = special_boost
            
            # Ensure attacker has stages dict initialized
            if not hasattr(attacker, 'stages') or not isinstance(attacker.stages, dict):
                attacker.stages = {
                    "atk": 0, "defn": 0, "spa": 0, "spd": 0, "spe": 0, 
                    "accuracy": 0, "evasion": 0
                }
            # Add special stat for Gen I
            if generation == 1 and "special" not in attacker.stages:
                attacker.stages["special"] = 0
            
            stat_messages = modify_stages(attacker, stat_changes, field_effects=field_effects)
            messages.extend(stat_messages)
            
            if hasattr(attacker, '_is_z_move') and attacker._is_z_move:
                if move_name_norm_stat == "defend-order":
                    extra_msgs = modify_stages(attacker, {"defn": 1}, caused_by_opponent=False, field_effects=field_effects)
                    messages.extend(extra_msgs)
                elif move_name_norm_stat == "hone-claws":
                    extra_msgs = modify_stages(attacker, {"atk": 1}, caused_by_opponent=False, field_effects=field_effects)
                    messages.extend(extra_msgs)
                elif move_name_norm_stat in {"quiver-dance", "coil"}:
                    stat_resets = {}
                    for stat in ["atk", "defn", "spa", "spd", "spe", "accuracy", "evasion"]:
                        if attacker.stages.get(stat, 0) < 0:
                            stat_resets[stat] = -attacker.stages.get(stat, 0)
                    if stat_resets:
                        reset_msgs = modify_stages(attacker, stat_resets, caused_by_opponent=False, field_effects=field_effects)
                        messages.extend(reset_msgs)
    
    # === SUBSTITUTE: Blocks all secondary effects (status, flinch, stat drops, etc.) ===
    # NOTE: Stat boosts (user-targeting) are processed above, before this check
    if hasattr(defender, 'substitute') and defender.substitute:
        # Substitute blocks all secondary effects (defender-targeting only)
        return messages
    
    if effect_data.get("burn_if_stats_raised"):
        if getattr(defender, "_stats_raised_this_turn", False):
            from .db_move_effects import apply_status_effect
            success, status_msg = apply_status_effect(
                defender,
                "brn",
                attacker,
                field_effects=field_effects,
                target_side=target_side
            )
            if status_msg:
                messages.append(status_msg)
        # Continue to other secondary effects (burn is handled, no need to exit)
    
    # Dark Void: Only Darkrai can use it in later generations
    if effect_data.get("darkrai_only") is not None:
        darkrai_only = effect_data.get("darkrai_only")
        gen_specific_darkrai = effect_data.get("gen_specific", {})
        if isinstance(gen_specific_darkrai, dict):
            for spec, overrides in gen_specific_darkrai.items():
                if isinstance(overrides, dict) and "darkrai_only" in overrides and _match_generation(str(spec), generation):
                    darkrai_only = overrides.get("darkrai_only")
        if darkrai_only:
            attacker_species = (getattr(attacker, "species", "") or "").lower()
            if "darkrai" not in attacker_species:
                messages.append("But it failed!")
                return messages
    
    # Captivate / opposite-gender requirements
    if effect_data.get("opposite_gender"):
        def _normalize_gender(value: Optional[str]) -> Optional[str]:
            if not value:
                return None
            lowered = value.lower()
            if lowered in {"male", "m"}:
                return "male"
            if lowered in {"female", "f"}:
                return "female"
            return None
        
        user_gender = _normalize_gender(getattr(attacker, "gender", None))
        target_gender = _normalize_gender(getattr(defender, "gender", None))
        
        if user_gender is None or target_gender is None or user_gender == target_gender:
            messages.append("But it failed!")
            return messages
        
        if not getattr(defender, "_ability_suppressed", False):
            from .abilities import normalize_ability_name, get_ability_effect
            defender_ability = normalize_ability_name(defender.ability or "")
            defender_ability_data = get_ability_effect(defender_ability)
            if defender_ability_data.get("infatuation_immunity"):
                ability_name = (defender.ability or defender_ability or "Ability").replace("-", " ").title()
                messages.append(f"{defender.species}'s {ability_name} protected it!")
                return messages
    
    # Secret Power: Environment-based secondary effects (30% chance; Serene Grace doubles)
    # Building/plain → paralysis; Sand → accuracy -1; Cave → flinch; Rock → confusion;
    # Tall grass → poison; Long grass → sleep; Pond → Speed -1; Sea → Attack -1; Underwater → Defense -1
    move_name_norm = move_name.lower().replace(" ", "-")
    if move_name_norm == "secret-power" and (effect_data.get("effect_varies_by_environment") or effect_data.get("effect_varies_terrain")):
        base_chance = effect_data.get("chance", 0.3)
        effect_chance = base_chance * chance_multiplier
        
        if random.random() < effect_chance:
            env = getattr(field_effects, "environment", None) or getattr(field_effects, "secret_power_environment", None) if field_effects else None
            env = (env or "plain").lower().replace(" ", "_").replace("-", "_")
            # Normalize common names
            if env in ("building", "link_battle", "link"):
                env = "building"
            elif env in ("tall_grass", "tallgrass"):
                env = "tall_grass"
            elif env in ("long_grass", "longgrass"):
                env = "long_grass"
            elif env in ("pond_water", "pond"):
                env = "pond_water"
            elif env in ("sea_water", "sea"):
                env = "sea_water"
            
            if env in ("sand",):
                old_acc = defender.stages.get("accuracy", 0)
                defender.stages["accuracy"] = max(-6, old_acc - 1)
                messages.append(f"{defender.species}'s accuracy fell!")
            elif env in ("cave",):
                defender.flinched = True
                messages.append(f"{defender.species} flinched!")
            elif env in ("rock",):
                if not getattr(defender, "confusion_turns", 0):
                    defender.confusion_turns = random.randint(2, 5) if get_generation(field_effects=field_effects) >= 4 else random.randint(1, 4)
                    messages.append(f"{defender.species} became confused!")
            elif env in ("tall_grass",):
                if not defender.status:
                    defender.status = "psn"
                    messages.append(f"{defender.species} was poisoned!")
            elif env in ("long_grass",):
                if not defender.status:
                    from .generation import get_generation
                    gen_sp = get_generation(field_effects=field_effects)
                    defender.status = "slp"
                    defender.status_turns = random.choice([2, 3, 4]) if gen_sp >= 5 else random.randint(2, 5)
                    defender._sleep_applied_this_turn = True
                    messages.append(f"{defender.species} fell asleep!")
            elif env in ("pond_water",):
                old_spe = defender.stages.get("spe", 0)
                defender.stages["spe"] = max(-6, old_spe - 1)
                messages.append(f"{defender.species}'s Speed fell!")
            elif env in ("sea_water",):
                old_atk = defender.stages.get("atk", 0)
                defender.stages["atk"] = max(-6, old_atk - 1)
                messages.append(f"{defender.species}'s Attack fell!")
            elif env in ("underwater",):
                old_def = defender.stages.get("defn", 0)
                defender.stages["defn"] = max(-6, old_def - 1)
                messages.append(f"{defender.species}'s Defense fell!")
            else:
                # Building, plain, or unknown: paralysis
                if not defender.status:
                    defender.status = "par"
                    messages.append(f"{defender.species} was paralyzed!")
        
        # Secret Power secondary effects are handled above, skip normal secondary effects
        return messages
    
    # Status effects (paralysis, burn, poison, etc.)
    if "status" in effect_data and not effect_data.get("status_move"):
        from .generation import get_generation
        generation = get_generation(field_effects=field_effects)

        base_chance = effect_data.get("chance", 1.0)
        move_name_norm = move_name.lower().replace(" ", "-")
        if move_name_norm == "waterfall" and generation <= 3:
            base_chance = 0.0

        gen_specific = effect_data.get("gen_specific", {})

        if isinstance(gen_specific, dict):
            chance_overrides: Dict[str, Any] = {}
            if isinstance(gen_specific.get("chance"), dict):
                chance_overrides = gen_specific.get("chance", {})
            else:
                for key, value in gen_specific.items():
                    if isinstance(value, dict) and "chance" in value:
                        chance_overrides[key] = value.get("chance")

            for spec, override in (chance_overrides or {}).items():
                if override is None:
                    continue
                if _match_generation(str(spec), generation):
                    base_chance = override

        chance = min(1.0, base_chance * chance_multiplier)
        if random.random() < chance:
            status_to_inflict = effect_data["status"]
            # Check if target already has status
            valid_statuses = {"par", "brn", "slp", "frz", "psn", "tox", "sleep", "paralyze", "burn", "freeze", "poison", "toxic"}
            current_status = getattr(defender, 'status', None)
            if current_status and str(current_status).lower().strip() in valid_statuses:
                return messages
            
            # Check type immunities
            defender_types = [t.strip().title() if t else None for t in getattr(defender, 'types', (None, None))]
            
            # Electric types immune to paralysis (except Lick Gen II+, see below)
            # Fire types to burn, etc.
            move_name_norm = move_name.lower().replace(" ", "-")
            
            # Body Slam: Gen I cannot paralyze Normal types
            if move_name_norm == "body-slam" and status_to_inflict == "par":
                if generation == 1 and "Normal" in defender_types:
                    return messages  # Gen I: Can't paralyze Normal types
            
            # Lick: Can paralyze Ghost types from Gen II+
            if move_name_norm == "lick" and status_to_inflict == "par":
                if "Ghost" in defender_types and generation == 1:
                    return messages  # Gen I: Can't paralyze Ghost
                # Gen II+: Can paralyze Ghost (no return here)
            # Glare: Generation-specific Ghost type immunity
            elif move_name_norm == "glare" and status_to_inflict == "par":
                # Gen I: Can paralyze Ghost types
                if "Ghost" in defender_types:
                    if generation >= 2 and generation <= 3:
                        # Gen II-III: Cannot paralyze Ghost types (unless Foresight/Odor Sleuth - not checking here)
                        return messages
                    # Gen I, Gen IV+: Can paralyze Ghost types
                # Gen VI+: Electric types immune to paralysis
                if generation >= 6 and "Electric" in defender_types:
                    return messages
            elif status_to_inflict == "par" and "Electric" in defender_types:
                # Gen VI+: Electric types immune to paralysis (except Glare handled above)
                if generation >= 6:
                    return messages
            
            if status_to_inflict in ["brn", "burn"] and "Fire" in defender_types:
                return messages
            if status_to_inflict in ["psn", "tox"] and ("Poison" in defender_types or "Steel" in defender_types):
                return messages
            if status_to_inflict in ["frz", "freeze"] and "Ice" in defender_types:
                return messages
            
            # Apply status using proper function (handles sleep duration, flags, etc.)
            from .db_move_effects import apply_status_effect
            success, status_msg = apply_status_effect(
                defender,
                status_to_inflict,
                attacker,
                field_effects=field_effects,
                target_side=target_side
            )
            if status_msg:
                messages.append(status_msg)
    
    # Confusion (generation-aware)
    if effect_data.get("confuse"):
        from .db_move_effects import apply_confusion
        base_chance = effect_data.get("chance", 1.0)
        gen_specific_confuse = effect_data.get("gen_specific", {})
        if isinstance(gen_specific_confuse, dict):
            chance_overrides: Dict[str, Any] = {}
            if isinstance(gen_specific_confuse.get("chance"), dict):
                chance_overrides = gen_specific_confuse.get("chance", {})
            else:
                for key, value in gen_specific_confuse.items():
                    if isinstance(value, dict) and "chance" in value:
                        chance_overrides[key] = value.get("chance")

            from .generation import get_generation
            generation = get_generation(field_effects=field_effects)
            for spec, override in (chance_overrides or {}).items():
                if override is None:
                    continue
                if _match_generation(str(spec), generation):
                    base_chance = override

        if effect_data.get("requires_chatot_for_confuse"):
            attacker_species = (getattr(attacker, "species", "") or "").lower()
            if "chatot" not in attacker_species:
                base_chance = 0.0
        chance = min(1.0, base_chance * chance_multiplier)
        if random.random() < chance:
            success, msg = apply_confusion(defender, target_side=target_side, user=attacker, field_effects=field_effects)
            if msg:
                messages.append(msg)
    
    # Flinching (generation-aware with King's Rock, Razor Fang, Stench)
    from .db_move_effects import apply_flinch
    
    # Determine if move has base flinch chance
    move_has_flinch = effect_data.get("flinch", False)
    base_flinch_chance = 0.0
    if move_has_flinch:
        base_flinch_chance = effect_data.get("chance", 1.0) if isinstance(move_has_flinch, bool) else move_has_flinch
        base_flinch_chance = base_flinch_chance * chance_multiplier
    
    # Check for Serene Grace
    serene_grace = (attacker_ability == "serene-grace")
    
    # Apply flinch (handles King's Rock, Razor Fang, Stench, generation differences)
    # Note: We don't know if this is a multistrike move here, so we assume it's not
    success, msg = apply_flinch(
        attacker=attacker,
        target=defender,
        move_has_flinch=bool(move_has_flinch),
        flinch_chance=base_flinch_chance,
        field_effects=field_effects,
        is_multistrike=False,
        is_final_strike=True,
        serene_grace=serene_grace,
        move_name=move_name
    )
    if success and msg:
        messages.append(msg)
    
    # Stat drops (opponent-caused, triggers Competitive/Defiant)
    if "stat_drop" in effect_data:
        # Constrict: Generation-specific chance (Gen I: 33.2%, Gen II+: 10%)
        # Mud-Slap: Generation-specific chance (Gen II: 99.6%, Gen III+: 100%)
        move_name_norm_stat = move_name.lower().replace(" ", "-")
        base_chance = effect_data.get("chance", 1.0)
        
        if move_name_norm_stat == "constrict":
            gen_specific_constrict = effect_data.get("gen_specific", {})
            if isinstance(gen_specific_constrict, dict) and "1" in gen_specific_constrict:
                if generation == 1:
                    base_chance = gen_specific_constrict["1"].get("chance", base_chance)
        elif move_name_norm_stat == "mud-slap":
            # Gen II: 99.6% chance, Gen III+: 100%
            if generation == 2:
                base_chance = 0.996
            else:
                base_chance = 1.0
        
        chance = base_chance * chance_multiplier
        chance = min(1.0, chance)
        if random.random() < chance:
            from .engine import modify_stages
            from .abilities import normalize_ability_name, get_ability_effect
            stat_changes = effect_data["stat_drop"]
            
            # Mirror Armor: Reflect stat drops back to attacker
            defender_ability = normalize_ability_name(defender.ability or "")
            defender_ability_data = get_ability_effect(defender_ability)
            
            # Check if defender has Mirror Armor and the stat changes are negative
            if defender_ability_data.get("reflects_stat_drops") and any(v < 0 for v in stat_changes.values()):
                # Check if this was already reflected (prevent infinite reflection)
                if not getattr(defender, '_mirror_armor_reflected_this_turn', False):
                    defender._mirror_armor_reflected_this_turn = True
                    # Reflect to attacker instead
                    stat_messages = modify_stages(attacker, stat_changes, caused_by_opponent=False)
                    if stat_messages:
                        ability_name = defender.ability.replace("-", " ").title() if defender.ability else "Mirror Armor"
                        messages.append(f"{defender.species}'s {ability_name} reflected the stat drop!")
                        messages.extend(stat_messages)
                else:
                    # Already reflected, don't reflect again
                    pass
            else:
                # Normal stat drop
                # Track for Eject Pack
                defender._stats_lowered_this_turn = True
                stat_messages = modify_stages(defender, stat_changes, caused_by_opponent=True)
                messages.extend(stat_messages)
    
    # Target stat drops (status moves, opponent-caused, triggers Competitive/Defiant)
    if "target_stat_drop" in effect_data or (
        isinstance(effect_data.get("gen_specific"), dict) and any(
            isinstance(v, dict) and v.get("target_stat_drop") is not None for v in effect_data["gen_specific"].values()
        )
    ):
        from .engine import modify_stages
        from .abilities import normalize_ability_name, get_ability_effect
        stat_changes = effect_data["target_stat_drop"]
        
        # Mirror Armor: Reflect stat drops back to attacker
        defender_ability = normalize_ability_name(defender.ability or "")
        defender_ability_data = get_ability_effect(defender_ability)
        
        # Check if defender has Mirror Armor and the stat changes are negative
        if defender_ability_data.get("reflects_stat_drops") and any(v < 0 for v in stat_changes.values()):
            # Check if this was already reflected (prevent infinite reflection)
            if not getattr(defender, '_mirror_armor_reflected_this_turn', False):
                defender._mirror_armor_reflected_this_turn = True
                # Reflect to attacker instead
                stat_messages = modify_stages(attacker, stat_changes, caused_by_opponent=False)
                if stat_messages:
                    ability_name = defender.ability.replace("-", " ").title() if defender.ability else "Mirror Armor"
                    messages.append(f"{defender.species}'s {ability_name} reflected the stat drop!")
                    messages.extend(stat_messages)
            else:
                # Already reflected, don't reflect again
                pass
    
    # PP reduction moves (Eerie Spell, G-Max Depletion)
    if effect_data.get("reduces_pp") and move_hit and defender.hp > 0:
        reduction_amount = effect_data.get("reduces_pp", 0)
        if reduction_amount > 0:
            # Get defender's last move used
            defender_last_move = getattr(defender, 'last_move_used', None) or getattr(defender, '_last_move', None)
            
            if defender_last_move and defender_last_move.lower() != "struggle":
                # Get battle_state from attacker or defender if available
                battle_state = getattr(attacker, '_battle_state', None) or getattr(defender, '_battle_state', None)
                
                if battle_state:
                    # Get defender's user_id
                    defender_id = None
                    if hasattr(battle_state, 'p1_team') and defender in battle_state.p1_team:
                        defender_id = battle_state.p1_id
                    elif hasattr(battle_state, 'p2_team') and defender in battle_state.p2_team:
                        defender_id = battle_state.p2_id
                    
                    if defender_id:
                        current_pp = battle_state._pp_left(defender_id, defender_last_move)
                        if current_pp > 0:
                            # Reduce PP
                            reduction = min(reduction_amount, current_pp)
                            battle_state._pp[defender_id][defender_last_move] = max(0, current_pp - reduction)
                            
                            # Generation-specific message format
                            move_name_lower = move_name.lower().replace(" ", "-")
                            if move_name_lower == "eerie-spell":
                                if generation == 2:
                                    messages.append(f"{defender.species}'s {defender_last_move} was reduced by {reduction}!")
                                elif generation == 3:
                                    messages.append(f"Reduced {defender.species}'s {defender_last_move} by {reduction}!")
                                elif generation >= 4:
                                    messages.append(f"It reduced the PP of {defender.species}'s {defender_last_move} by {reduction}!")
                                else:
                                    messages.append(f"{defender.species}'s {defender_last_move} lost {reduction} PP!")
                            elif move_name_lower == "g-max-depletion":
                                # G-Max Depletion: Only works if target used a move before being hit
                                if getattr(defender, '_moved_this_turn', False):
                                    messages.append(f"It reduced the PP of {defender.species}'s {defender_last_move} by {reduction}!")
                                # If target didn't move, no message (move still hits but no PP reduction)
        else:
            # Normal stat drop
            stat_messages = modify_stages(defender, stat_changes, caused_by_opponent=True)
            messages.extend(stat_messages)
        stat_changes = effect_data.get("target_stat_drop")
        chance = effect_data.get("chance", 1.0)

        gen_specific_drop = effect_data.get("gen_specific", {})
        if isinstance(gen_specific_drop, dict):
            for spec, overrides in gen_specific_drop.items():
                if not isinstance(overrides, dict):
                    continue
                if _match_generation(str(spec), generation):
                    if "target_stat_drop" in overrides:
                        stat_changes = overrides.get("target_stat_drop")
                    if "chance" in overrides:
                        chance = overrides.get("chance", chance)
        
        # Psychic: Generation-specific stat drop and chance
        move_name_norm_drop = move_name.lower().replace(" ", "-")
        if move_name_norm_drop == "psychic":
            if generation == 1:
                stat_changes = {"special": -1}  # Gen I: Lowers Special stat
                chance = 0.332  # 33.2% chance
                # Gen I: Additional 25% fail chance for in-game opponents (handled in engine.py)
            elif generation == 2:
                stat_changes = {"spd": -1}  # Gen II: Lowers Special Defense
                chance = 0.1  # 10% chance
                # Gen II: Additional 25% fail chance for in-game opponents (handled in engine.py)
            else:
                stat_changes = {"spd": -1}  # Gen III+: Lowers Special Defense
                chance = 0.1  # 10% chance

        if stat_changes:
            stat_changes = dict(stat_changes)

        if not stat_changes:
            pass
        else:
            if chance < 1.0:
                roll = random.random()
                if roll >= chance:
                    # Effect failed this time (Gen II Sweet Scent 25% fail chance)
                    messages.append(f"But it failed against {defender.species}!")
                    stat_changes = None
            if stat_changes:
                # Mirror Armor: Reflect stat drops back to attacker
                defender_ability = normalize_ability_name(defender.ability or "")
                defender_ability_data = get_ability_effect(defender_ability)

                # Check if defender has Mirror Armor and the stat changes are negative
                if defender_ability_data.get("reflects_stat_drops") and any(v < 0 for v in stat_changes.values()):
                    # Check if this was already reflected (prevent infinite reflection)
                    if not getattr(defender, '_mirror_armor_reflected_this_turn', False):
                        defender._mirror_armor_reflected_this_turn = True
                        # Reflect to attacker instead
                        stat_messages = modify_stages(attacker, stat_changes, caused_by_opponent=False)
                        if stat_messages:
                            ability_name = defender.ability.replace("-", " ").title() if defender.ability else "Mirror Armor"
                            messages.append(f"{defender.species}'s {ability_name} reflected the stat drop!")
                            messages.extend(stat_messages)
                    else:
                        # Already reflected, don't reflect again
                        pass
                else:
                    # Normal stat drop
                    stat_messages = modify_stages(defender, stat_changes, caused_by_opponent=True)
        messages.extend(stat_messages)
    
    # Stat boosts (self) - MOVED to before substitute check (see above around line 2583)
    # This code block has been moved earlier in the function so stat boosts apply even when hitting substitute
    
    # Recoil damage (applies to attacker)
    # Recoil damage is now handled by the database-driven system in engine.py
    # (removed to prevent double recoil application)
    
    # Trapping (Anchor Shot, Mean Look, Block, Spider Web, etc.)
    if effect_data.get("traps") or effect_data.get("traps_opponent"):
        move_name_trap = move_name.lower().replace(" ", "-")
        
        # Spider Web: Generation-specific mechanics
        if move_name_trap == "spider-web":
            from .generation import get_generation
            gen_web = get_generation(field_effects=field_effects)
            
            # Gen VI+: Ghost types are immune
            if gen_web >= 6:
                defender_types = [t.strip().title() if t else None for t in getattr(defender, 'types', (None, None))]
                if "Ghost" in defender_types:
                    messages.append(f"It doesn't affect {defender.species}...")
                    return messages
            
            # Gen VIII+: Banned
            if gen_web >= 8:
                messages.append(f"Spider Web cannot be selected in this generation!")
                return messages
        
        if not hasattr(defender, 'trapped') or not defender.trapped:
            defender.trapped = True
            defender.trapped_by = attacker.species
            messages.append(f"{defender.species} can no longer escape!")
    
    return messages


def is_status_move(move_name: str) -> bool:
    """Check if a move is a status move."""
    effect_data = get_move_secondary_effect(move_name)
    return effect_data.get("status_move", False)


def get_move_priority(move_name: str) -> int:
    """Get the priority of a move."""
    effect_data = get_move_secondary_effect(move_name)
    return effect_data.get("priority", 0)


def calculate_variable_power(move_name: str, attacker: Any, defender: Any, base_power: int,
                            *, field_effects: Any = None) -> int:
    """
    Calculate the actual power for variable power moves.
    Returns the calculated power, or base_power if not a variable power move.
    """
    effect_data = get_move_secondary_effect(move_name)
    var_type = effect_data.get("variable_power")
    
    if not var_type:
        return base_power
    
    # Import here to avoid circular imports
    from .engine import speed_value
    
    # Speed-based moves
    if field_effects is None:
        field_effects = getattr(attacker, '_field_effects', None)
    generation = None
    if field_effects is not None:
        from .generation import get_generation
        generation = get_generation(field_effects=field_effects)

    if var_type == "gyro_ball":
        # Power = 25 * (target_speed / user_speed), max 150
        user_speed = speed_value(attacker, None)
        target_speed = speed_value(defender, None)
        if user_speed > 0:
            power = min(150, int(25 * (target_speed / user_speed)))
            return max(1, power)
        return 1
    
    elif var_type == "electro_ball":
        # Power based on speed ratio: 150/120/80/60/40
        user_speed = speed_value(attacker, None)
        target_speed = speed_value(defender, None)
        if target_speed > 0:
            ratio = user_speed / target_speed
            if ratio >= 4:
                return 150
            elif ratio >= 3:
                return 120
            elif ratio >= 2:
                return 80
            elif ratio >= 1:
                return 60
        return 40
    
    # Weight-based moves
    # Dynamax Pokemon are unaffected by weight-based moves (use base power)
    elif var_type in ["heavy_slam", "heat_crash"]:
        # Dynamax Pokemon are unaffected by weight moves - use base power
        if defender.dynamaxed:
            return base_power
        # Power based on weight ratio: 120/100/80/60/40
        user_weight = _get_effective_weight(attacker)
        target_weight = _get_effective_weight(defender)
        if target_weight > 0:
            ratio = user_weight / target_weight
            if ratio >= 5:
                return 120
            elif ratio >= 4:
                return 100
            elif ratio >= 3:
                return 80
            elif ratio >= 2:
                return 60
        return 40
    
    elif var_type in ["low_kick", "grass_knot"]:
        # Low Kick: Gen I-II use fixed 50 power, Gen III+ use weight-based
        move_lower = move_name.lower().replace(" ", "-")
        if move_lower == "low-kick" and generation is not None and generation <= 2:
            # Gen I-II: Fixed 50 power
            return 50
        
        # Dynamax Pokemon are unaffected by weight moves - use base power
        if defender.dynamaxed:
            return base_power
        # Power based on target weight (Gen III+ for Low Kick, all gens for Grass Knot)
        weight = _get_effective_weight(defender)
        if weight >= 200:
            return 120
        elif weight >= 100:
            return 100
        elif weight >= 50:
            return 80
        elif weight >= 25:
            return 60
        elif weight >= 10:
            return 40
        return 20
    
    # Status condition moves
    elif var_type == "hex":
        # Double power if target has status (130 base)
        return 130 if defender.status else 65
    
    elif var_type == "venoshock":
        # Double power if target is poisoned
        if defender.status and defender.status.lower() in ["psn", "poison", "tox", "toxic"]:
            return 130
        return 65
    
    # HP-based moves
    elif var_type == "brine":
        # Double power if target HP < 50%
        hp_percent = (defender.hp / defender.max_hp) if defender.max_hp > 0 else 1
        return 130 if hp_percent < 0.5 else 65
    
    elif var_type == "wring_out":
        # Gen V+: Power = 120 × (target HP / max HP), min 1
        # Earlier gens: Power = 1 + 120 × (target HP / max HP), max 121
        from .generation import get_generation
        generation = get_generation(field_effects=field_effects) if field_effects else 9
        hp_percent = (defender.hp / defender.max_hp) if defender.max_hp > 0 else 0
        
        if generation >= 5:
            # Gen V+: Power = 120 × HP%, min 1
            return max(1, int(120 * hp_percent))
        else:
            # Gen IV: Power = 1 + 120 × HP%, max 121
            return min(121, max(1, int(1 + 120 * hp_percent)))
    
    elif var_type == "crush_grip":
        # Power = 120 * (target_HP / target_max_HP), min 1 (same as Wring Out Gen V+)
        hp_percent = (defender.hp / defender.max_hp) if defender.max_hp > 0 else 0
        return max(1, int(120 * hp_percent))
    
    elif var_type in ["eruption", "water_spout", "user_hp"]:
        # Power = 150 * (user_HP / user_max_HP), min 1
        # Formula: | (150 × HP_current) / HP_max |, minimum 1
        hp_percent = (attacker.hp / attacker.max_hp) if attacker.max_hp > 0 else 0
        return max(1, int(150 * hp_percent))
    
    # Item-based moves
    elif var_type == "acrobatics":
        # Double power if no item (110 base)
        return 110 if not attacker.item else 55
    
    # Stat boost moves
    elif var_type in ["stored_power", "power_trip"]:
        # Base 20 + 20 per positive stat stage
        boost_count = sum(max(0, stage) for stage in attacker.stages.values())
        return 20 + (20 * boost_count)
    
    elif var_type == "punishment":
        # Base 60 + 20 per positive stat stage on target, max 200
        boost_count = sum(max(0, stage) for stage in defender.stages.values())
        return min(200, 60 + (20 * boost_count))
    
    # Contextual moves (simplified, would need battle state)
    elif var_type in ["avalanche", "revenge"]:
        took_damage = getattr(attacker, '_took_damage_this_turn', False)
        return base_power * 2 if took_damage else base_power
    
    elif var_type == "payback":
        # Would need to track turn order; simplified
        return base_power
    
    # Random power moves
    elif var_type == "magnitude":
        # Random power: 10/30/50/70/90/110/150 with different probabilities
        roll = random.random()
        if roll < 0.05:
            return 10
        elif roll < 0.15:
            return 30
        elif roll < 0.35:
            return 50
        elif roll < 0.65:
            return 70
        elif roll < 0.85:
            return 90
        elif roll < 0.95:
            return 110
        return 150
    
    # NEW: Friendship-based moves
    elif var_type in ["return", "friendship"]:
        from .advanced_moves import calculate_return_power
        friendship = getattr(attacker, 'friendship', 255)
        return calculate_return_power(friendship, generation=generation)
    
    elif var_type == "frustration":
        from .advanced_moves import calculate_frustration_power
        friendship = getattr(attacker, 'friendship', 255)
        return calculate_frustration_power(friendship, generation=generation)
    
    # NEW: Low HP power moves
    elif var_type in ["flail", "reversal", "low_hp"]:
        # Get field_effects from attacker if available
        field_effects = getattr(attacker, '_field_effects', None) or getattr(defender, '_field_effects', None)
        from .advanced_moves import calculate_low_hp_power
        return calculate_low_hp_power(attacker.hp, attacker.max_hp, move_name, field_effects)
    
    # NEW: Trump Card (PP-based)
    elif var_type == "trump_card":
        from .advanced_moves import calculate_trump_card_power
        # This needs PP tracking - for now, default
        remaining_pp = getattr(attacker, '_last_move_pp', 5)
        return calculate_trump_card_power(remaining_pp)
    
    # NEW: Turn-based power (Fury Cutter, Echoed Voice)
    elif var_type == "fury_cutter":
        from .advanced_moves import handle_fury_cutter
        # Note: Hit status will be set after damage is calculated
        return handle_fury_cutter(attacker, move_name, True)
    
    elif var_type == "echoed_voice":
        from .advanced_moves import handle_echoed_voice
        return handle_echoed_voice(attacker, move_name)
    
    # Default: return base power
    return base_power

