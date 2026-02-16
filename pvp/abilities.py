"""
Comprehensive Pokémon Ability System
Implements all 284+ abilities from generations 1-9
"""
from typing import Dict, Any, List, Optional

# ============================================================================
# ABILITY EFFECTS DATABASE
# ============================================================================

ABILITY_EFFECTS: Dict[str, Dict[str, Any]] = {
    
    # ========== TYPE IMMUNITY & ABSORPTION ABILITIES ==========
    "levitate": {
        "immune_to": ["Ground"],
        "description": "Gives full immunity to Ground-type moves"
    },
    "volt-absorb": {
        "immune_to": ["Electric"],
        "absorb": True,
        "heal_percent": 0.25,
        "description": "Restores HP when hit by Electric moves"
    },
    "water-absorb": {
        "immune_to": ["Water"],
        "absorb": True,
        "heal_percent": 0.25,
        "description": "Restores HP when hit by Water moves"
    },
    "flash-fire": {
        "immune_to": ["Fire"],
        "boost_on_hit": {"spa": 1.5},
        "description": "Powers up Fire moves when hit by Fire"
    },
    "sap-sipper": {
        "immune_to": ["Grass"],
        "boost_on_hit_stages": {"atk": 1},
        "description": "Boosts Attack when hit by Grass moves"
    },
    "storm-drain": {
        "immune_to": ["Water"],
        "boost_on_hit_stages": {"spa": 1},
        "redirects": "Water",
        "description": "Draws in Water moves and boosts Sp. Atk"
    },
    "lightning-rod": {
        "immune_to": ["Electric"],
        "boost_on_hit_stages": {"spa": 1},
        "redirects": "Electric",
        "description": "Draws in Electric moves and boosts Sp. Atk"
    },
    "motor-drive": {
        "immune_to": ["Electric"],
        "boost_on_hit_stages": {"spe": 1},
        "description": "Boosts Speed when hit by Electric moves"
    },
    "dry-skin": {
        "immune_to": ["Water"],
        "absorb": True,
        "heal_percent": 0.25,
        "weak_to_fire": 1.25,
        "weather_effects": {"rain": "heal", "sun": "damage"},
        "description": "Restores HP in rain, damaged by Fire and sun"
    },
    "earth-eater": {
        "immune_to": ["Ground"],
        "absorb": True,
        "heal_percent": 0.25,
        "description": "Restores HP when hit by Ground moves"
    },
    "well-baked-body": {
        "immune_to": ["Fire"],
        "boost_on_hit_stages": {"defn": 2},
        "description": "Sharply boosts Defense when hit by Fire"
    },
    "wind-rider": {
        "immune_to_wind_moves": True,
        "boost_on_hit_stages": {"atk": 1},
        "boost_on_tailwind": {"atk": 1},
        "description": "Gen 9+: Immune to 17 wind moves (not Sandstorm), +1 Attack when hit or Tailwind activates."
    },
    
    # ========== WONDER GUARD (SPECIAL IMMUNITY) ==========
    "wonder-guard": {
        "only_supereffective_hits": True,
        "cannot_be_copied": True,
        "cannot_be_swapped": True,
        "cannot_be_suppressed": True,
        "description": "Only super effective moves hit. Immune to status/fixed damage/OHKO. Gen 3: Beat Up/Future Sight/Doom Desire bypass. Gen 4: Fire Fang glitch bypasses."
    },
    
    # ========== STAT BOOST ON SWITCH-IN ==========
    "intimidate": {
        "on_switch": {
            "target": "opponent",
            "stages": {"atk": -1}
        },
        "description": "Lowers opponent's Attack on switch-in"
    },
    "download": {
        "on_switch": {
            "target": "self",
            "smart_boost": True  # Boost Atk if opponent's Def < SpD, else SpA
        },
        "description": "Boosts Attack or Sp. Atk based on foe's stats"
    },
    "intrepid-sword": {
        "on_switch": {
            "target": "self",
            "stages": {"atk": 1}
        },
        "description": "Boosts Attack on switch-in"
    },
    "dauntless-shield": {
        "on_switch": {
            "target": "self",
            "stages": {"defn": 1}
        },
        "description": "Boosts Defense on switch-in"
    },
    
    # ========== WEATHER SETTERS ==========
    "drizzle": {
        "on_switch": {"weather": "rain"},
        "description": "Summons rain when switched in"
    },
    "drought": {
        "on_switch": {"weather": "sun"},
        "description": "Summons harsh sunlight when switched in"
    },
    "sand-stream": {
        "on_switch": {"weather": "sandstorm"},
        "description": "Summons sandstorm when switched in"
    },
    "snow-warning": {
        "on_switch": {"weather": "hail"},
        "description": "Summons hail when switched in"
    },
    
    # ========== TERRAIN SETTERS ==========
    "electric-surge": {
        "on_switch": {"terrain": "electric"},
        "description": "Creates Electric Terrain on switch-in"
    },
    "psychic-surge": {
        "on_switch": {"terrain": "psychic"},
        "description": "Creates Psychic Terrain on switch-in"
    },
    "grassy-surge": {
        "on_switch": {"terrain": "grassy"},
        "description": "Creates Grassy Terrain on switch-in"
    },
    "misty-surge": {
        "on_switch": {"terrain": "misty"},
        "description": "Creates Misty Terrain on switch-in"
    },
    "hadron-engine": {
        "on_switch": {"terrain": "electric"},
        "stat_mult_terrain": {"spa": 1.33, "terrain": "electric"},
        "description": "Creates Electric Terrain, boosts SpA in it"
    },
    "orichalcum-pulse": {
        "on_switch": {"weather": "sun"},
        "stat_mult_weather": {"atk": 1.33, "weather": "sun"},
        "description": "Creates sun, boosts Attack in harsh sunlight"
    },
    
    # ========== STARTER ABILITIES (LOW HP BOOST) ==========
    "overgrow": {
        "boost_type": "Grass",
        "threshold": 0.33,
        "multiplier": 1.5,
        "description": "Powers up Grass moves when HP is low"
    },
    "blaze": {
        "boost_type": "Fire",
        "threshold": 0.33,
        "multiplier": 1.5,
        "description": "Powers up Fire moves when HP is low"
    },
    "torrent": {
        "boost_type": "Water",
        "threshold": 0.33,
        "multiplier": 1.5,
        "description": "Powers up Water moves when HP is low"
    },
    "swarm": {
        "boost_type": "Bug",
        "threshold": 0.33,
        "multiplier": 1.5,
        "description": "Powers up Bug moves when HP is low"
    },
    
    # ========== CONTACT ABILITIES ==========
    "static": {
        "on_contact": {"status": "par", "chance": 0.3},
        "description": "May paralyze on contact"
    },
    "flame-body": {
        "on_contact": {"status": "brn", "chance": 0.3},
        "description": "May burn on contact"
    },
    "poison-point": {
        "on_contact": {"status": "psn", "chance": 0.3},
        "description": "May poison on contact"
    },
    "effect-spore": {
        "on_contact": {"status": ["par", "psn", "slp"], "chance": 0.3},
        "description": "May poison, paralyze, or sleep on contact"
    },
    "rough-skin": {
        "on_contact": {"damage": 0.125},
        "description": "Damages attacker on contact (1/8 max HP)"
    },
    "iron-barbs": {
        "on_contact": {"damage": 0.125},
        "description": "Damages attacker on contact (1/8 max HP)"
    },
    "cute-charm": {
        "on_contact": {"status": "infatuated", "chance": 0.3},
        "description": "May infatuate on contact"
    },
    "poison-touch": {
        "on_contact": {"status": "psn", "chance": 0.3, "attacker_inflicts": True},
        "description": "May poison on contact (attacker inflicts)"
    },
    "gooey": {
        "on_contact_stages": {"spe": -1, "target": "attacker"},
        "description": "Lowers attacker's Speed on contact"
    },
    "tangling-hair": {
        "on_contact_stages": {"spe": -1, "target": "attacker"},
        "description": "Lowers attacker's Speed on contact"
    },
    "cursed-body": {
        "on_contact": {"disable_move": True, "chance": 0.3},
        "description": "May disable move that hit it"
    },
    "mummy": {
        "on_contact": {"change_ability": "mummy"},
        "description": "Changes attacker's ability to Mummy"
    },
    "wandering-spirit": {
        "on_contact": {"swap_abilities": True},
        "description": "Swaps abilities with attacker on contact"
    },
    "lingering-aroma": {
        "on_contact": {"change_ability": "lingering-aroma"},
        "description": "Changes attacker's ability"
    },
    "toxic-debris": {
        "sets_toxic_spikes_on_physical_hit": True,
        "description": "Sets Toxic Spikes when hit by physical moves"
    },
    "cotton-down": {
        "on_hit_stages": {"spe": -1, "all_opponents": True},
        "description": "Lowers Speed of all opponents when hit"
    },
    "innards-out": {
        "on_faint": {"damage_dealt": "damage_taken"},
        "description": "Damages attacker equal to HP lost on fainting"
    },
    "aftermath": {
        "on_faint": {"damage": 0.25},
        "description": "Damages attacker on fainting (1/4 max HP)"
    },
    
    # ========== STAT MULTIPLIER ABILITIES ==========
    "huge-power": {
        "stat_mult": {"atk": 2.0},
        "description": "Doubles Attack stat"
    },
    "pure-power": {
        "stat_mult": {"atk": 2.0},
        "description": "Doubles Attack stat"
    },
    "fur-coat": {
        "stat_mult": {"defn": 2.0},
        "description": "Doubles Defense stat"
    },
    "thick-fat": {
        "resist_types": ["Fire", "Ice"],
        "multiplier": 0.5,
        "description": "Halves damage from Fire and Ice moves"
    },
    "thermal-exchange": {
        "boost_on_fire_hit": {"atk": 1},
        "burn_immunity": True,
        "description": "Raises Attack when hit by Fire moves and prevents burn (Gen 9+)"
    },
    "heatproof": {
        "resist_types": ["Fire"],
        "multiplier": 0.5,
        "description": "Halves damage from Fire moves"
    },
    "water-bubble": {
        "resist_types": ["Fire"],
        "multiplier": 0.5,
        "stat_mult": {"atk": 2.0, "type": "Water"},
        "burn_immunity": True,
        "description": "Halves Fire damage, doubles Water move power"
    },
    "multiscale": {
        "damage_reduction_full_hp": 0.5,
        "description": "Halves damage when HP is full"
    },
    "shadow-shield": {
        "damage_reduction_full_hp": 0.5,
        "description": "Halves damage when HP is full"
    },
    "prism-armor": {
        "super_effective_reduction": 0.75,
        "description": "Reduces super effective damage"
    },
    "filter": {
        "super_effective_reduction": 0.75,
        "description": "Reduces super effective damage"
    },
    "solid-rock": {
        "super_effective_reduction": 0.75,
        "description": "Reduces super effective damage"
    },
    "fluffy": {
        "resist_types": ["Physical"],  # Special handling
        "multiplier": 0.5,
        "weak_to": ["Fire"],
        "weak_mult": 2.0,
        "description": "Halves contact damage, double Fire damage"
    },
    "punk-rock": {
        "boost_sound_moves": 1.3,
        "resist_sound_moves": 0.5,
        "description": "Boosts sound moves, resists sound damage"
    },
    "ice-scales": {
        "resist_category": ["special"],
        "multiplier": 0.5,
        "description": "Halves damage from special moves"
    },
    
    # ========== WEATHER-BASED ABILITIES ==========
    "swift-swim": {
        "speed_mult": 2.0,
        "weather": "rain",
        "description": "Doubles Speed in rain"
    },
    "chlorophyll": {
        "speed_mult": 2.0,
        "weather": "sun",
        "description": "Doubles Speed in harsh sunlight"
    },
    "sand-rush": {
        "speed_mult": 2.0,
        "weather": "sandstorm",
        "description": "Doubles Speed in sandstorm"
    },
    "slush-rush": {
        "speed_mult": 2.0,
        "weather": "hail",
        "description": "Doubles Speed in snow"
    },
    "solar-power": {
        "stat_mult_weather": {"spa": 1.5, "weather": "sun"},
        "weather_damage": {"sun": 0.125},
        "description": "Boosts Sp. Atk in sun, takes damage"
    },
    "rain-dish": {
        "weather_heal": {"rain": 0.0625},
        "description": "Restores HP in rain"
    },
    "ice-body": {
        "weather_heal": {"hail": 0.0625},
        "description": "Restores HP in snow"
    },
    "sand-veil": {
        "evasion_boost_weather": {"sandstorm": 1.25},
        "sandstorm_immunity": True,
        "description": "Boosts evasion in sandstorm"
    },
    "snow-cloak": {
        "evasion_boost_weather": {"hail": 1.25},
        "hail_immunity": True,
        "description": "Boosts evasion in snow"
    },
    "sand-force": {
        "boost_types_weather": {
            "types": ["Rock", "Ground", "Steel"],
            "weather": "sandstorm",
            "multiplier": 1.3
        },
        "sandstorm_immunity": True,
        "description": "Boosts Rock/Ground/Steel in sandstorm"
    },
    "overcoat": {
        "weather_immunity": ["sandstorm", "hail"],
        "powder_immunity": True,
        "description": "Protects from weather and powder moves"
    },
    "cloud-nine": {
        "weather_negation": True,
        "description": "Negates weather effects"
    },
    "air-lock": {
        "weather_negation": True,
        "description": "Negates weather effects"
    },
    
    # ========== ACCURACY/EVASION ABILITIES ==========
    "compound-eyes": {
        "accuracy_mult": 1.3,
        "description": "Boosts accuracy by 30%"
    },
    "no-guard": {
        "perfect_accuracy": True,
        "description": "All moves always hit"
    },
    # DUPLICATE - See line ~645 for consolidated definition
    "tangled-feet": {
        "evasion_when_confused": 2.0,
        "description": "Boosts evasion when confused"
    },
    "victory-star": {
        "accuracy_mult": 4506 / 4096,  # Exact: ~1.1001 (approximately 10% boost)
        "description": "Boosts accuracy by ~10% (4506/4096). Stacks multiplicatively with allies."
    },
    "hustle": {
        "stat_mult": {"atk": 1.5},
        "accuracy_mult_physical": 0.8,
        "description": "Boosts Attack but lowers accuracy"
    },
    
    # ========== CRITICAL HIT ABILITIES ==========
    "super-luck": {
        "crit_boost": 1,
        "description": "Heightens critical hit ratio"
    },
    "sniper": {
        "crit_damage_mult": 2.25,  # Instead of 1.5x, crits do 2.25x
        "description": "Powers up critical hits"
    },
    "battle-armor": {
        "crit_immunity": True,
        "description": "Cannot be hit by critical hits"
    },
    "shell-armor": {
        "crit_immunity": True,
        "description": "Cannot be hit by critical hits"
    },
    "merciless": {
        "always_crit_if_poisoned": True,
        "description": "Always crits poisoned foes"
    },
    "anger-point": {
        "on_crit_received": {"stages": {"atk": 12}},  # Maxes Attack
        "description": "Maxes Attack when hit by a crit"
    },
    
    # ========== MOVE POWER/TYPE CHANGING ABILITIES ==========
    "adaptability": {
        "stab_boost": 2.0,  # STAB is 2x instead of 1.5x
        "description": "Powers up same-type moves"
    },
    "technician": {
        "low_power_boost": 1.5,
        "threshold": 60,
        "description": "Powers up weak moves (≤60 power)"
    },
    "iron-fist": {
        "boost_punching_moves": 1.2,
        "description": "Powers up punching moves"
    },
    "reckless": {
        "boost_recoil_moves": 1.2,
        "description": "Powers up recoil moves"
    },
    "sheer-force": {
        "boost_secondary_effect_moves": 1.3,
        "removes_secondary_effects": True,
        "description": "Powers up moves with effects, removes effects"
    },
    "serene-grace": {
        "secondary_effect_chance_mult": 2.0,
        "description": "Doubles the chance of secondary effects"
    },
    "skill-link": {
        "multi_hit_always_max": True,
        "description": "Multi-hit moves always hit 5 times"
    },
    "parental-bond": {
        "attacks_twice": True,
        "second_hit_power": 0.25,
        "description": "Attacks twice (second hit is 25% power)"
    },
    "strong-jaw": {
        "boost_biting_moves": 1.5,
        "description": "Powers up biting moves"
    },
    "mega-launcher": {
        "boost_pulse_moves": 1.5,
        "description": "Powers up pulse and aura moves"
    },
    "tough-claws": {
        "boost_contact_moves": 5325 / 4096,  # Exact multiplier: ~1.3003
        "description": "Powers up contact moves by ~30% (Gen 6+)"
    },
    "pixilate": {
        "converts_normal_to": "Fairy",
        "conversion_boost": 1.2,
        "description": "Normal moves become Fairy"
    },
    "refrigerate": {
        "converts_normal_to": "Ice",
        "conversion_boost": 1.2,
        "description": "Normal moves become Ice"
    },
    "aerilate": {
        "converts_normal_to": "Flying",
        "conversion_boost": 1.2,
        "description": "Normal moves become Flying"
    },
    "galvanize": {
        "converts_normal_to": "Electric",
        "conversion_boost": 1.2,
        "description": "Normal moves become Electric"
    },
    "normalize": {
        "converts_all_to": "Normal",
        "description": "All moves become Normal type"
    },
    "transistor": {
        "boost_type": "Electric",
        "description": "Powers up Electric moves. Gen 8: 1.5x, Gen 9: 1.3x"
    },
    "dragons-maw": {
        "boost_type": "Dragon",
        "multiplier": 1.5,
        "description": "Powers up Dragon moves"
    },
    "steelworker": {
        "boost_type": "Steel",
        "multiplier": 1.5,
        "description": "Powers up Steel moves"
    },
    "rocky-payload": {
        "boost_type": "Rock",
        "multiplier": 1.5,
        "description": "Powers up Rock moves"
    },
    "sharpness": {
        "boost_slicing_moves": 1.5,
        "description": "Powers up slicing moves"
    },
    "tinted-lens": {
        "not_very_effective_boost": 2.0,
        "description": "Not very effective moves hit normally"
    },
    "scrappy": {
        "hit_ghost_with_normal_fighting": True,
        "intimidate_immunity": True,
        "description": "Hits Ghost with Normal/Fighting"
    },
    "liquid-voice": {
        "sound_moves_become_water": True,
        "description": "Sound moves become Water type"
    },
    
    # ========== STATUS IMMUNITY ABILITIES ==========
    "immunity": {
        "status_immunity": ["psn", "tox"],
        "description": "Cannot be poisoned"
    },
    "limber": {
        "status_immunity": ["par"],
        "description": "Cannot be paralyzed"
    },
    "insomnia": {
        "status_immunity": ["slp"],
        "description": "Cannot fall asleep"
    },
    "vital-spirit": {
        "status_immunity": ["slp"],
        "prevents_yawn": True,
        "description": "Cannot fall asleep. Rest fails. Gen 3-4: Complex wake-up timing. Gen 5+: Immediate cure on entry."
    },
    "water-veil": {
        "status_immunity": ["brn"],
        "burn_immunity": True,
        "description": "Cannot be burned. Gen 3: Delayed cure timing. Gen 4: Cures on switch. Gen 5+: Immediate cure."
    },
    "magma-armor": {
        "status_immunity": ["frz"],
        "description": "Cannot be frozen"
    },
    "oblivious": {
        "taunt_immunity": True,
        "infatuation_immunity": True,
        "intimidate_immunity": True,
        "description": "Prevents infatuation and Intimidate"
    },
    "own-tempo": {
        "confusion_immunity": True,
        "intimidate_immunity": True,
        "description": "Prevents confusion"
    },
    "inner-focus": {
        "flinch_immunity": True,
        "intimidate_immunity": True,
        "description": "Prevents flinching"
    },
    "comatose": {
        "always_asleep": True,
        "status_immunity": "all",
        "description": "Always asleep but can attack"
    },
    "purifying-salt": {
        "status_immunity": "all",
        "resist_types": ["Ghost"],
        "multiplier": 0.5,
        "description": "Protected from status, Ghost resistance"
    },
    "shield-dust": {
        "secondary_effect_immunity": True,
        "description": "Blocks additional effects of moves"
    },
    "good-as-gold": {
        "status_move_immunity": True,
        "description": "Immune to all status moves"
    },
    
    # ========== STAT STAGE PROTECTION ==========
    "clear-body": {
        "stat_drop_immunity": True,
        "description": "Prevents stat reduction"
    },
    "white-smoke": {
        "stat_drop_immunity": True,
        "description": "Prevents stat reduction"
    },
    "full-metal-body": {
        "stat_drop_immunity": True,
        "description": "Prevents stat reduction"
    },
    "hyper-cutter": {
        "stat_drop_immunity": ["atk"],
        "description": "Prevents Attack reduction"
    },
    "big-pecks": {
        "stat_drop_immunity": ["defn"],
        "description": "Prevents Defense reduction"
    },
    "keen-eye": {
        "stat_drop_immunity": ["accuracy"],
        "intimidate_immunity": True,
        "ignores_evasion": True,  # Gen 7+ only (requires generation check in engine)
        "description": "Prevents accuracy reduction, immune to Intimidate, ignores evasion (Gen 7+)"
    },
    "contrary": {
        "inverts_stat_changes": True,
        "description": "Inverts stat changes"
    },
    "simple": {
        "doubles_stat_changes": True,
        "description": "Doubles stat changes"
    },
    "unaware": {
        "ignores_stat_changes": True,
        "description": "Ignores stat changes in damage calc"
    },
    "defiant": {
        "stat_drop_boost": {"atk": 2},
        "description": "Sharply boosts Attack when stats are lowered"
    },
    "competitive": {
        "stat_drop_boost": {"spa": 2},
        "description": "Sharply boosts Sp. Atk when stats are lowered"
    },
    "mirror-armor": {
        "reflects_stat_drops": True,
        "description": "Reflects stat-lowering effects"
    },
    
    # ========== PRIORITY ABILITIES ==========
    "prankster": {
        "priority_boost": 1,
        "move_category": "status",
        "description": "+1 priority to status moves"
    },
    "gale-wings": {
        "priority_boost": 1,
        "move_type": "Flying",
        "full_hp_only": True,
        "description": "+1 priority to Flying moves at full HP"
    },
    "triage": {
        "priority_boost": 3,
        "move_type": "healing",
        "description": "+3 priority to healing moves"
    },
    "stall": {
        "always_moves_last": True,
        "description": "Always moves last in priority bracket"
    },
    "quick-feet": {
        "speed_mult_status": 1.5,
        "paralysis_speed_penalty_negation": True,
        "description": "Boosts Speed when statused"
    },
    "guts": {
        "attack_mult_status": 1.5,
        "burn_attack_penalty_negation": True,
        "description": "Boosts Attack by 50% when statused"
    },
    "marvel-scale": {
        "defense_mult_status": 1.5,
        "description": "Boosts Defense by 50% when statused"
    },
    "toxic-boost": {
        "attack_mult_poison": 1.5,
        "description": "Boosts Attack by 50% when poisoned"
    },
    "flare-boost": {
        "spa_mult_burn": 1.5,
        "description": "Boosts Sp. Atk by 50% when burned"
    },
    
    # ========== ABILITY CHANGING/COPYING ==========
    "trace": {
        "copies_ability_on_entry": True,
        "cannot_be_copied": True,  # Gen 5+: Cannot be copied by Role Play, Power of Alchemy, Receiver
        "description": "Copies adjacent opponent's ability. Gen 3: Can copy any ability. Gen 4+: Some abilities cannot be copied. Gen 5+: Cannot be copied by Role Play. Gen 6+: Can reactivate if gained again."
    },
    "imposter": {
        "on_switch": {"transform": True},
        "description": "Transforms into opponent"
    },
    "protean": {
        "type_change_before_move": True,
        "once_per_switch": True,
        "description": "Changes type to move's type"
    },
    "libero": {
        "type_change_before_move": True,
        "once_per_switch": True,
        "description": "Changes type to move's type"
    },
    "color-change": {
        "type_change_after_hit": True,
        "description": "Changes type to last move hit by"
    },
    "disguise": {
        "blocks_first_hit": True,
        "form_change": True,
        "description": "Blocks first hit, then form changes"
    },
    
    # ========== SPECIAL MECHANICS ==========
    "stance-change": {
        "form_change_on_attack": True,
        "description": "Changes form when attacking/using King's Shield"
    },
    "zen-mode": {
        "form_change_at_half_hp": True,
        "cannot_be_copied": True,
        "cannot_be_swapped": True,
        "cannot_be_suppressed": True,
        "description": "Darmanitan: <50% HP → Zen Mode (Fire/Psychic or Ice/Fire). >50% HP → Standard Mode. Gen 5-6: Can be suppressed. Gen 7+: Cannot."
    },
    "shields-down": {
        "form_change_at_half_hp": True,
        "status_immunity_above_half": True,
        "description": "Changes form and loses status immunity below 50% HP"
    },
    "schooling": {
        "form_change_by_level": True,
        "threshold": 0.25,
        "description": "Forms school at level 20+ and above 25% HP"
    },
    "zero-to-hero": {
        "form_change_on_switch_out": True,
        "cannot_be_copied": True,
        "cannot_be_swapped": True,
        "cannot_be_suppressed": True,
        "description": "Gen 9+: Palafin switches to Hero Form after first switch out (not fainting). Stays Hero Form even if revived."
    },
    "power-construct": {
        "form_change_at_half_hp": True,
        "description": "Changes to Complete Form at 50% HP"
    },
    
    # ========== KO/SURVIVAL ABILITIES ==========
    "sturdy": {
        "survives_ohko": True,
        "ohko_immunity": True,
        "description": "Survives OHKO at full HP, blocks OHKO moves"
    },
    "focus-sash": {  # Item effect, but listed for reference
        "survives_ohko": True,
        "description": "Survives one hit at full HP"
    },
    "disguise": {
        "blocks_first_hit": True,
        "description": "Blocks one hit"
    },
    "ice-face": {
        "blocks_first_physical_hit": True,
        "form_change": True,
        "restores_in_hail": True,
        "description": "Blocks one physical hit"
    },
    
    # ========== HP RECOVERY ABILITIES ==========
    "regenerator": {
        "on_switch_out": {"heal": 0.33},
        "description": "Restores 1/3 HP when switching out"
    },
    "erratic": {
        "turn_based_stat_changes": {"boost": 2, "debuff": -2},
        "description": "Missing n0 exclusive: +2 to random stat, -2 to random stat each turn"
    },
    "rock-head": {
        "no_recoil_damage": True,
        "description": "Protects from recoil damage"
    },
    "magic-guard": {
        "no_indirect_damage": True,
        "description": "Only takes damage from direct attacks"
    },
    "natural-cure": {
        "on_switch_out": {"heal_status": True},
        "description": "Heals status when switching out"
    },
    "shed-skin": {
        "end_of_turn": {"heal_status": True, "chance": 0.33},
        "description": "May heal status at end of turn"
    },
    "healer": {
        "end_of_turn": {"heal_ally_status": True, "chance": 0.3},
        "description": "May heal ally's status"
    },
    "poison-heal": {
        "poisoned_heals": True,
        "heal_percent": 0.125,
        "description": "Restores HP when poisoned"
    },
    "volt-absorb": {
        "absorb_type": "Electric",
        "heal_percent": 0.25,
        "description": "Restores HP when hit by Electric"
    },
    "water-absorb": {
        "absorb_type": "Water",
        "heal_percent": 0.25,
        "description": "Restores HP when hit by Water"
    },
    
    # ========== BOOST ON KO ABILITIES ==========
    "moxie": {
        "on_ko": {"stages": {"atk": 1}},
        "description": "Boosts Attack on KO"
    },
    "beast-boost": {
        "on_ko": {"boost_highest_stat": True},
        "description": "Boosts highest stat on KO"
    },
    "chilling-neigh": {
        "on_ko": {"stages": {"atk": 1}},
        "description": "Boosts Attack on KO"
    },
    "grim-neigh": {
        "on_ko": {"stages": {"spa": 1}},
        "description": "Boosts Sp. Atk on KO"
    },
    "soul-heart": {
        "on_any_ko": {"stages": {"spa": 1}},
        "description": "Boosts Sp. Atk when any Pokémon faints"
    },
    "supreme-overlord": {
        "power_boost_per_fainted_ally": 0.1,
        "max_boost": 0.5,
        "description": "Boosts moves based on fainted allies"
    },
    
    # ========== BERRY/ITEM ABILITIES ==========
    "gluttony": {
        "berry_threshold": 0.5,  # Eats berry at 50% instead of 25%
        "description": "Eats berries early"
    },
    "ripen": {
        "berry_effect_mult": 2.0,
        "description": "Doubles berry effects"
    },
    "cheek-pouch": {
        "berry_heal_bonus": 0.33,
        "description": "Restores HP when eating berries"
    },
    "harvest": {
        "berry_restore_chance": {"sun": 1.0, "normal": 0.5},
        "description": "May restore berry after use"
    },
    "unburden": {
        "speed_mult_after_item_use": 2.0,
        "description": "Doubles Speed after using item"
    },
    "symbiosis": {
        "passes_item_to_ally": True,
        "description": "Passes item to ally when used"
    },
    "pickpocket": {
        "steals_item_on_contact": True,
        "description": "Steals attacker's item on contact"
    },
    "magician": {
        "steals_item_on_hit": True,
        "description": "Steals target's item when hitting"
    },
    "sticky-hold": {
        "item_cannot_be_removed": True,
        "description": "Item cannot be removed"
    },
    "klutz": {
        "item_disabled": True,
        "description": "Cannot use held items"
    },
    
    # ========== MISCELLANEOUS ==========
    "pressure": {
        "pp_drain_double": True,
        "description": "Doubles PP usage of opponent's moves"
    },
    "unnerve": {
        "prevents_berry_use": True,
        "description": "Prevents opponent from eating berries"
    },
    "neutralizing-gas": {
        "suppresses_abilities": True,
        "description": "Suppresses all abilities"
    },
    "mold-breaker": {
        "ignores_abilities": True,
        "ignores_opponent_abilities": True,
        "description": "Moves ignore abilities (Gen 4+). Gen 4: benefits from ally Flower Gift. Gen 8+: doesn't ignore Dark/Fairy Aura"
    },
    "teravolt": {
        "ignores_abilities": True,
        "ignores_opponent_abilities": True,
        "on_switch_message": "radiating a bursting aura",
        "description": "Moves ignore abilities (same as Mold Breaker). Gen 8+: Doesn't ignore Dark/Fairy Aura"
    },
    "turboblaze": {
        "ignores_abilities": True,
        "ignores_opponent_abilities": True,
        "on_switch_message": "radiating a blazing aura",
        "description": "Moves ignore abilities (same as Mold Breaker). Gen 8+: Doesn't ignore Dark/Fairy Aura"
    },
    "mycelium-might": {
        "status_moves_ignore_abilities": True,
        "status_moves_go_last": True,
        "description": "Status moves ignore abilities but go last"
    },
    
    # More abilities can be added here...
    
    # ========== TURN-BASED ABILITIES ==========
    "truant": {
        "only_moves_every_other_turn": True,
        "description": "Can only move every other turn"
    },
    "slow-start": {
        "half_attack_speed_for_5_turns": True,
        "description": "Half Attack and Speed for 5 turns"
    },
    "gorilla-tactics": {
        "attack_mult": 1.5,
        "choice_lock": True,
        "description": "1.5x Attack but locked into first move"
    },
    
    # ========== PRIORITY ABILITIES ==========
    "quick-draw": {
        "random_priority_boost": True,
        "priority_chance": 0.3,
        "description": "30% chance to move first in priority bracket"
    },
    
    # ========== HAZARD REFLECTION ==========
    "magic-bounce": {
        "reflects_status_moves": True,
        "description": "Reflects status moves back at user"
    },
    
    # ========== FORME-CHANGE (COMPLEX) ==========
    "gulp-missile": {
        "form_change_on_surf_dive": True,
        "damages_attacker_when_hit": True,
        "description": "Changes form with Surf/Dive, damages attacker when hit"
    },
    "curious-medicine": {
        "on_switch": {
            "reset_ally_stats": True
        },
        "description": "Resets ally's stat changes on switch-in"
    },
    "ball-fetch": {
        "fetches_failed_pokeball": True,
        "description": "Retrieves first failed Poké Ball"
    },
    
    # ========== MISSING IMPORTANT ABILITIES ==========
    "battle-bond": {
        "transform_on_ko": True,
        "description": "Transforms into Ash-Greninja after KO"
    },
    "forecast": {
        "weather_form_change": True,
        "description": "Changes form and type based on weather"
    },
    "flower-gift": {
        "sunshine_form_change": True,
        "ally_stat_boost_in_sun": {"atk": 1.5, "spd": 1.5},
        "description": "Boosts Attack and Sp. Def of allies in sun"
    },
    "hunger-switch": {
        "alternates_form_each_turn": True,
        "description": "Alternates between Full Belly and Hangry Mode each turn"
    },
    "illusion": {
        "disguises_as_last_party_member": True,
        "description": "Appears as the last Pokémon in party until hit"
    },
    "moody": {
        "random_stat_changes_each_turn": True,
        "description": "+2 to one random stat, -1 to another each turn"
    },
    "frisk": {
        "reveals_opponent_item": True,
        "description": "Reveals opponent's held item"
    },
    "pickup": {
        "may_find_item_after_battle": True,
        "description": "May pick up items after battle"
    },
    "power-of-alchemy": {
        "copies_ally_ability_on_faint": True,
        "description": "Copies ally's ability when they faint"
    },
    "receiver": {
        "copies_ally_ability_on_faint": True,
        "description": "Copies ally's ability when they faint"
    },
    "queenly-majesty": {
        "blocks_priority_moves": True,
        "description": "Protects from priority moves"
    },
    "dazzling": {
        "blocks_priority_moves": True,
        "description": "Protects from priority moves"
    },
    "as-one": {
        "has_unnerve_and_chilling_neigh": True,
        "description": "Combines Unnerve and Chilling Neigh abilities"
    },
    
    # Note: rocky-helmet is an item, not an ability
    
    # === MISSING 102 ABILITIES - COMPLETE DATABASE ===
    "analytic": {"power_boost_when_moving_last": 1.3, "description": "Boosts move power by 30% when moving last"},
    "anticipation": {"warns_of_super_effective": True, "description": "Senses dangerous moves"},
    "arena-trap": {"traps_grounded_opponents": True, "description": "Prevents grounded foes from fleeing"},
    "armor-tail": {"blocks_priority_moves": True, "description": "Blocks priority moves"},
    "aroma-veil": {"team_mental_move_immunity": True, "description": "Protects team from mental moves"},
    "as-one-glastrier": {"has_unnerve_and_chilling_neigh": True, "description": "Unnerve + Chilling Neigh"},
    "as-one-spectrier": {"has_unnerve_and_grim_neigh": True, "description": "Unnerve + Grim Neigh"},
    "aura-break": {"reverses_aura_effects": True, "description": "Reverses Dark Aura and Fairy Aura"},
    "bad-dreams": {"damages_sleeping_opponents": True, "description": "Damages sleeping opponents each turn"},
    "battery": {"ally_special_boost": 1.3, "description": "Boosts ally's special moves by 30%"},
    "beads-of-ruin": {"lowers_all_spd": 0.75, "description": "Lowers Sp. Def of all Pokémon by 25%"},
    "berserk": {"spa_boost_at_half_hp": {"spa": 1}, "description": "Boosts Sp. Atk when HP drops below half"},
    "bulletproof": {"ball_bomb_immunity": True, "description": "Immune to ball and bomb moves"},
    "commander": {"enters_dondozo_mouth": True, "description": "Goes into Dondozo's mouth"},
    "corrosion": {"can_poison_steel_poison": True, "description": "Can poison Steel and Poison types"},
    "costar": {"copies_ally_stat_changes": True, "description": "Copies ally's stat changes on entry"},
    "cud-chew": {"eats_berry_twice": True, "description": "Eats Berry twice"},
    "damp": {"prevents_explosions": True, "description": "Prevents self-destruct and Explosion"},
    "dancer": {"copies_dance_moves": True, "description": "Copies dance moves used by any Pokémon"},
    "dark-aura": {"dark_move_boost": 1.33, "description": "Boosts Dark moves for all Pokémon"},
    "defeatist": {"stats_halved_below_half": True, "description": "Halves Attack and Sp. Atk below half HP"},
    "delta-stream": {"sets_strong_winds": True, "description": "Creates strong winds weather"},
    "desolate-land": {"sets_harsh_sunlight": True, "description": "Creates harsh sunlight weather"},
    "early-bird": {"sleep_duration_halved": True, "description": "Wakes from sleep twice as fast"},
    "earth-eater": {"ground_immunity_heal": True, "description": "Immune to Ground, heals 1/4 HP"},
    "electromorphosis": {"charge_when_hit": True, "description": "Charges when hit"},
    "embody-aspect-cornerstone": {"boost_on_entry_def": {"defn": 1}, "description": "Raises Defense on entry"},
    "embody-aspect-hearthflame": {"boost_on_entry_atk": {"atk": 1}, "description": "Raises Attack on entry"},
    "embody-aspect-teal": {"boost_on_entry_spe": {"spe": 1}, "description": "Raises Speed on entry"},
    "embody-aspect-wellspring": {"boost_on_entry_spa": {"spa": 1}, "description": "Raises Sp. Atk on entry"},
    "emergency-exit": {"switches_out_at_half_hp": True, "description": "Switches out when HP drops below half"},
    "fairy-aura": {"fairy_move_boost": 1.33, "description": "Boosts Fairy moves for all Pokémon"},
    "flower-veil": {"protects_grass_types": True, "description": "Protects Grass-types from status and stat drops"},
    "forewarn": {"reveals_strongest_move": True, "description": "Reveals opponent's strongest move"},
    "friend-guard": {"reduces_ally_damage": 0.75, "description": "Reduces damage to ally"},
    "grass-pelt": {"defense_boost_in_grassy": 1.5, "description": "Boosts Defense in Grassy Terrain"},
    "guard-dog": {"intimidate_immunity_boost": True, "description": "Immune to Intimidate, boosts Attack"},
    "gulp-missile-gorging": {"damages_attacker_when_hit": True, "description": "Gulping Form effect"},
    "gulp-missile-gulping": {"damages_attacker_when_hit": True, "description": "Gorging Form effect"},
    "honey-gather": {"may_find_honey": True, "description": "May gather Honey after battle"},
    "hospitality": {"heals_ally_on_entry": True, "description": "Restores ally HP on entry"},
    "hydration": {"heals_status_in_rain": True, "description": "Heals status conditions in rain"},
    "illuminate": {"increases_encounter_rate": True, "description": "Raises likelihood of meeting wild Pokémon"},
    "infiltrator": {"ignores_screens_substitutes": True, "description": "Ignores Reflect, Light Screen, Substitute"},
    "justified": {"boost_on_hit_dark": {"atk": 1}, "description": "Raises Attack when hit by Dark moves"},
    "leaf-guard": {"status_immunity_in_sun": True, "description": "Prevents status in harsh sunlight"},
    "liquid-ooze": {"damages_draining_moves": True, "description": "Damages opponents using draining moves"},
    "long-reach": {"contact_moves_dont_make_contact": True, "description": "Contact moves don't make contact"},
    "magnet-pull": {"traps_steel_types": True, "description": "Prevents Steel-types from fleeing"},
    "mimicry": {"type_changes_with_terrain": True, "description": "Changes type with terrain"},
    "minds-eye": {
        "normal_fighting_hit_ghost": True,
        "stat_drop_immunity": ["accuracy"],  # Prevents accuracy lowering
        "ignores_evasion": True,  # Ignores target's evasion boosts
        "description": "Normal/Fighting hit Ghost, ignores evasion, prevents accuracy drops"
    },
    "minus": {"spa_boost_with_plus": 1.5, "description": "Boosts Sp. Atk with Plus ally"},
    "moldbreaker": {"ignores_target_ability": True, "description": "Moves ignore opponent's ability"},
    "multitype": {"type_change_by_plate": True, "description": "Changes type with held Plate"},
    "neuroforce": {"super_effective_boost": 1.25, "description": "Boosts super effective moves by 25%"},
    "opportunist": {"copies_opponent_boosts": True, "description": "Copies opponent's stat boosts"},
    "pastel-veil": {"team_poison_immunity": True, "description": "Prevents poisoning of user and ally"},
    "perish-body": {"perish_song_on_contact": True, "description": "Sets Perish Song count on contact"},
    "plus": {"spa_boost_with_minus": 1.5, "description": "Boosts Sp. Atk with Minus ally"},
    "poison-puppeteer": {"confuses_poisoned_foes": True, "description": "Confuses poisoned foes"},
    "power-spot": {"ally_move_boost": 1.3, "description": "Boosts power of ally's moves by 30%"},
    "primordial-sea": {"sets_heavy_rain": True, "description": "Creates heavy rain weather"},
    "propeller-tail": {"ignores_redirection": True, "description": "Ignores move redirection"},
    "protosynthesis": {"boosts_highest_stat_in_sun": True, "description": "Boosts highest stat in sun"},
    "quark-drive": {"boosts_highest_stat_in_electric": True, "description": "Boosts highest stat in Electric Terrain"},
    "rattled": {"boost_on_hit_bug_ghost_dark": {"spe": 1}, "description": "Boosts Speed when hit by Bug/Ghost/Dark"},
    "rivalry": {"power_boost_same_gender": 1.25, "description": "Boosts power vs. same gender"},
    "rks-system": {"type_change_by_memory": True, "description": "Changes type with held Memory"},
    "run-away": {"guarantees_escape": True, "description": "Enables sure getaway from wild Pokémon"},
    "sand-spit": {"sets_sandstorm_when_hit": True, "description": "Sets Sandstorm when hit"},
    "screen-cleaner": {"removes_screens": True, "description": "Removes screens on entry"},
    "seed-sower": {"sets_grassy_terrain_when_hit": True, "description": "Sets Grassy Terrain when hit"},
    "shadow-tag": {"traps_opponents": True, "description": "Prevents opponents from fleeing"},
    "soundproof": {"sound_move_immunity": True, "description": "Immune to sound-based moves"},
    "speed-boost": {"speed_boost_each_turn": {"spe": 1}, "description": "Boosts Speed each turn"},
    "stakeout": {"power_boost_vs_switching": 2.0, "description": "Doubles power vs. switching foe"},
    "stalwart": {"ignores_redirection": True, "description": "Ignores move redirection"},
    "stamina": {"boost_on_hit": {"defn": 1}, "description": "Raises Defense when hit"},
    "steadfast": {"boost_on_flinch": {"spe": 1}, "description": "Boosts Speed when flinched"},
    "steam-engine": {"boost_on_hit_fire_water": {"spe": 6}, "description": "Sharply raises Speed when hit by Fire/Water"},
    "steely-spirit": {"ally_steel_boost": 1.5, "description": "Boosts ally's Steel moves by 50%"},
    "stench": {"flinch_chance_boost": 0.1, "description": "10% chance to make foe flinch"},
    "suction-cups": {"prevents_force_switch": True, "description": "Prevents being forced to switch"},
    "surf-tail": {"moves_first_on_turns_2_plus": True, "description": "Moves first after turn 1"},
    "surge-surfer": {"speed_boost_in_electric": 2.0, "description": "Doubles Speed in Electric Terrain"},
    "sweet-veil": {"team_sleep_immunity": True, "description": "Prevents ally Pokémon from sleep"},
    "sword-of-ruin": {"lowers_all_def": 0.75, "description": "Lowers Defense of all Pokémon by 25%"},
    "synchronize": {"passes_status_to_attacker": True, "description": "Passes poison/burn/paralysis to foe"},
    "tablets-of-ruin": {"lowers_all_atk": 0.75, "description": "Lowers Attack of all other Pokémon by 25%; does not stack; Foul Play not reduced if user is only holder; Strength Sap unaffected"},
    "tail-gating": {"ignores_weather_damage": True, "description": "Ignores weather damage"},
    "telepathy": {"avoids_ally_attacks": True, "description": "Avoids ally attacks"},
    "tera-shell": {
        "description": "All moves hit for not very effective damage when at full HP (Gen 9+)"
    },
    "tera-shift": {
        "description": "Transforms Terapagos into Terastal Form on entry (Gen 9+)",
        "cannot_be_copied": True,  # Cannot be copied by Trace, Power of Alchemy, Receiver
        "cannot_be_suppressed": True  # Cannot be suppressed by Neutralizing Gas
    },
    "teraform-zero": {
        "removes_terrain_weather": True,
        "can_be_suppressed": True,  # Can be suppressed by Gastro Acid/Neutralizing Gas
        "can_be_replaced": True,  # Can be replaced by Entrainment, Worry Seed, Doodle, Mummy, etc.
        "cannot_be_copied": True,  # Cannot be copied by Trace or Role Play
        "description": "Neutralizes weather and terrain when Terapagos assumes Stellar Form (Gen 9+)"
    },
    "toxic-chain": {"may_badly_poison": 0.3, "description": "30% chance to badly poison on hit"},
    "unseen-fist": {"contact_ignores_protect": True, "description": "Contact moves bypass protection"},
    "vessel-of-ruin": {"lowers_all_spa": 0.75, "description": "Lowers Sp. Atk of all Pokémon by 25%"},
    "water-compaction": {"boost_on_hit_water": {"defn": 2}, "description": "Sharply raises Def when hit by Water"},
    "weak-armor": {"stages_on_physical_hit": {"defn": -1, "spe": 2}, "description": "Physical hits lower Def, raise Speed"},
    "wimp-out": {"switches_out_at_half_hp": True, "description": "Switches out when HP drops below half"},
    "wind-power": {
        "charge_on_wind_move": True, 
        "description": "Gen 9+: Gets Charged when hit by wind move or Tailwind takes effect. Next Electric move has 2x power. 17 wind moves (not Sandstorm)."
    },
    "wonder-skin": {"lowers_status_move_accuracy": True, "description": "Makes status moves 50% accurate"},
    "heavy-metal": {"doubles_weight": True, "description": "Doubles the Pokémon's weight"},
    "light-metal": {"halves_weight": True, "description": "Halves the Pokémon's weight"},
    
    # ========== MISSING N0 EXCLUSIVE COUNTER ABILITIES ==========
    "coercion": {
        "steals_pp_on_opponent_move": 1,
        "description": "Missing n0 exclusive: Steals 1 PP from the opponent's active Pokémon each time they use a move"
    },
    "masquerade": {
        "adds_first_type_from_copied_mon": True,
        "description": "Missing n0 exclusive: Adds the first type from another Pokémon on your team as a secondary type"
    },
    "nullscape": {
        "description": "Missing n0 exclusive: Effects depend on MissingNo's type. Untyped: All moves become untyped, MissingNo gains STAB, others lose STAB. Ice: 1.3x Ice moves, 25% speed reduction, Fighting moves fail. Rock: 1.3x Rock moves, 0.75x super effective damage, Grass moves fail. Normal: 1.3x Normal moves, Ghost moves fail, ignores Protect. Steel: 1.3x Steel moves, immune to stat drops, 10% damage reduction. Ghost: 1.3x Ghost moves, switch doesn't clear effects, Normal moves fail."
    },
    "deadlock": {
        "perfect_accuracy": True,
        "adds_bp_based_on_miss_rate": True,
        "description": "Missing n0 exclusive: All moves always hit (perfect accuracy), and adds BP based on half the move's miss rate"
    },
    "earthbound": {
        "grounds_self_and_opponent": True,
        "boosts_ground_move_power": True,
        "removes_ground_immunity": True,
        "description": "Missing n0 exclusive: Grounds all Flying-type Pokémon and Pokémon with Levitate on the field, and boosts Ground-type move power by 1.5x against grounded targets"
    },
}


def normalize_ability_name(name: str) -> str:
    """Normalize ability name to lowercase with hyphens."""
    if not name:
        return ""
    return name.lower().replace(" ", "-").replace("_", "-").strip()


def get_ability_effect(ability_name: str) -> Dict[str, Any]:
    """Get ability effect data by name."""
    normalized = normalize_ability_name(ability_name)
    return ABILITY_EFFECTS.get(normalized, {})


def has_ability_effect(ability_name: str, effect_key: str) -> bool:
    """Check if an ability has a specific effect."""
    ability_data = get_ability_effect(ability_name)
    return effect_key in ability_data


