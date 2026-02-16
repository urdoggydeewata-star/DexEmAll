"""
Comprehensive Pokémon Held Item System
Implements battle items, stat boosters, type gems, etc.
"""
from typing import Dict, Any, Optional

# ============================================================================
# HELD ITEM EFFECTS DATABASE
# ============================================================================

ITEM_EFFECTS: Dict[str, Dict[str, Any]] = {
    
    # ========== CHOICE ITEMS ==========
    "choice-band": {
        "stat_mult": {"atk": 1.5},
        "locks_move": True,
        "category": "choice",
        "description": "Boosts Attack by 50% but locks you into one move"
    },
    "choice-specs": {
        "stat_mult": {"spa": 1.5},
        "locks_move": True,
        "category": "choice",
        "description": "Boosts Sp. Atk by 50% but locks you into one move"
    },
    "choice-scarf": {
        "stat_mult": {"spe": 1.5},
        "locks_move": True,
        "category": "choice",
        "description": "Boosts Speed by 50% but locks you into one move"
    },
    
    # ========== STAT BOOST ITEMS ==========
    # Life Orb: Boosts damage by 30%, 10% HP recoil (Gen 4+)
    # Gen 4: No message, doesn't damage on Future Sight/Doom Desire/Substitute hit
    # Gen 5: Shows message, exact 5324/4096 boost, damages on Future Sight/Substitute
    # Gen 6+: Also boosts Future Sight/Doom Desire damage
    "life-orb": {
        "min_gen": 4,
        "recoil": 0.1,  # 10% max HP
        "gen_specific": {
            "4": {
                "damage_mult": 1.3,
                "no_message": True,
                "no_future_sight_damage": True,
                "no_substitute_damage": True
            },
            "5": {
                "damage_mult": 5324 / 4096,  # Exact calculation
                "shows_message": True,
                "future_sight_damages_user": True,
                "substitute_damages_user": True,
                "no_future_sight_boost": True  # Doesn't boost FS/DD damage yet
            },
            "6+": {
                "damage_mult": 5324 / 4096,
                "shows_message": True,
                "future_sight_damages_user": True,
                "substitute_damages_user": True,
                "boosts_future_sight": True  # Now boosts FS/DD damage
            }
        },
        "negated_by": ["magic-guard", "sheer-force"],
        "stolen_by_thief": "damages_thief_not_boosted",
        "activates_after": ["iron-barbs", "rocky-helmet", "rough-skin", "recoil"],
        "multistrike_after_last": True,
        "description": "Gen 4: 1.3x, no msg. Gen 5+: 5324/4096, with msg, 10% HP recoil after dmg"
    },
    # Expert Belt: Boosts super-effective moves by 20% (Gen 4+)
    "expert-belt": {
        "super_effective_boost": 1.2,
        "min_gen": 4,
        "description": "Boosts super effective moves by 20% (Gen 4+)"
    },
    "muscle-band": {
        "physical_boost": 1.1,
        "description": "Boosts physical moves by 10%"
    },
    "wise-glasses": {
        "special_boost": 1.1,
        "description": "Boosts special moves by 10%"
    },
    "assault-vest": {
        "stat_mult": {"spd": 1.5},
        "blocks_status_moves": True,
        "description": "Boosts Sp. Def by 50%, prevents using status moves"
    },
    
    # ========== TYPE-BOOSTING ITEMS ==========
    # Gen 2-3: 10% boost (1.1x), Gen 4+: 20% boost (1.2x)
    # Multiplier is dynamically calculated in engine based on generation
    
    # Gen 2 items (most type-enhancing items)
    "charcoal": {"boost_type": "Fire", "type_enhancing": True, "min_gen": 2},
    "mystic-water": {"boost_type": "Water", "type_enhancing": True, "min_gen": 2},
    "miracle-seed": {"boost_type": "Grass", "type_enhancing": True, "min_gen": 2},
    "magnet": {"boost_type": "Electric", "type_enhancing": True, "min_gen": 2},
    "soft-sand": {"boost_type": "Ground", "type_enhancing": True, "min_gen": 2},
    "sharp-beak": {"boost_type": "Flying", "type_enhancing": True, "min_gen": 2},
    "poison-barb": {"boost_type": "Poison", "type_enhancing": True, "min_gen": 2},
    "twisted-spoon": {"boost_type": "Psychic", "type_enhancing": True, "min_gen": 2},
    "never-melt-ice": {"boost_type": "Ice", "type_enhancing": True, "min_gen": 2},
    "black-belt": {"boost_type": "Fighting", "type_enhancing": True, "min_gen": 2},
    "black-glasses": {"boost_type": "Dark", "type_enhancing": True, "min_gen": 2},
    "silver-powder": {"boost_type": "Bug", "type_enhancing": True, "min_gen": 2},
    "hard-stone": {"boost_type": "Rock", "type_enhancing": True, "min_gen": 2},
    "spell-tag": {"boost_type": "Ghost", "type_enhancing": True, "min_gen": 2},
    # Dragon Fang: Gen 2 handheld bug (no effect), Stadium 2 has 10%
    # Implement handheld behavior: no boost in Gen 2; Gen 3: 10%; Gen 4+: 20%
    "dragon-fang": {
        "boost_type": "Dragon",
        "type_enhancing": True,
        "min_gen": 2,
        "gen_specific": {
            "2": {"no_boost": True}
        }
    },
    "metal-coat": {"boost_type": "Steel", "type_enhancing": True, "min_gen": 2},
    
    # Gen 2 Normal-type items (Pink Bow, Polkadot Bow - only exist in Gen 2)
    "pink-bow": {"boost_type": "Normal", "type_enhancing": True, "min_gen": 2, "max_gen": 2},
    "polkadot-bow": {"boost_type": "Normal", "type_enhancing": True, "min_gen": 2, "max_gen": 2},
    
    # Gen 3+ Normal-type item (replaces bows from Gen 3 onward)
    "silk-scarf": {"boost_type": "Normal", "type_enhancing": True, "min_gen": 3},
    
    # Gen 9 Fairy-type item
    "fairy-feather": {"boost_type": "Fairy", "type_enhancing": True, "min_gen": 9},

    # ========== NEW ITEMS (FROM USER REQUEST) ==========
    # Adrenaline Orb: +1 Speed when affected by Intimidate (consumed). Special activation rules.
    "adrenaline-orb": {
        "boost_on_intimidate": {"stages": {"spe": 1}},
        "one_time_use": True,
        "min_gen": 7,
        "activates_when_intimidate_present_even_if_blocked": True,
        "does_not_activate_if_atk_stage_at_limit": True,  # -6 normally, +6 with Contrary
        "description": "Raises Speed by 1 when Intimidated (consumed). Activates even if Intimidate blocked."
    },

    # Primal Orbs (battle-only forms, unremovable/ungiveable in main games)
    "blue-orb": {
        "enables_primal": "kyogre",
        "unremovable_in_battle": True,
        "ungiveable_in_battle": True,
        "description": "Lets Kyogre become Primal Kyogre on switch-in."
    },
    "red-orb": {
        "enables_primal": "groudon",
        "unremovable_in_battle": True,
        "ungiveable_in_battle": True,
        "description": "Lets Groudon become Primal Groudon on switch-in."
    },

    # Ogerpon Masks: Change form and boost all moves by 20%
    "cornerstone-mask": {
        "species_specific": True,
        "holder": "ogerpon",
        "changes_form": "cornerstone",
        "all_moves_multiplier": 1.2,
        "description": "+20% power and changes Ogerpon to Cornerstone Mask form"
    },
    "wellspring-mask": {
        "species_specific": True,
        "holder": "ogerpon",
        "changes_form": "wellspring",
        "all_moves_multiplier": 1.2,
        "description": "+20% power and changes Ogerpon to Wellspring Mask form"
    },
    "hearthflame-mask": {
        "species_specific": True,
        "holder": "ogerpon",
        "changes_form": "hearthflame",
        "all_moves_multiplier": 1.2,
        "description": "+20% power and changes Ogerpon to Hearthflame Mask form"
    },
    "teal-mask": {
        "species_specific": True,
        "holder": "ogerpon",
        "changes_form": "teal",
        "all_moves_multiplier": 1.0,
        "description": "Keeps Ogerpon in base Teal Mask form"
    },

    # Leader's Crest: No in-battle effect; handled in evolution logic outside battles
    "leaders-crest": {
        "no_battle_effect": True,
        "description": "Evolution requirement item for Bisharp → Kingambit (out of battle)"
    },
    
    # ========== PLATES (ARCEUS) ==========
    # Gen 4-5: 16 Plates (no Fairy)
    # Gen 6+: 17 Plates (with Pixie Plate)
    # Legends Arceus: 19 Plates (Blank Plate for Normal, Legend Plate for type-changing)
    "flame-plate": {"boost_type": "Fire", "multiplier": 1.2, "arceus": True, "changes_arceus_type": "Fire", "min_gen": 4},
    "splash-plate": {"boost_type": "Water", "multiplier": 1.2, "arceus": True, "changes_arceus_type": "Water", "min_gen": 4},
    "meadow-plate": {"boost_type": "Grass", "multiplier": 1.2, "arceus": True, "changes_arceus_type": "Grass", "min_gen": 4},
    "zap-plate": {"boost_type": "Electric", "multiplier": 1.2, "arceus": True, "changes_arceus_type": "Electric", "min_gen": 4},
    "earth-plate": {"boost_type": "Ground", "multiplier": 1.2, "arceus": True, "changes_arceus_type": "Ground", "min_gen": 4},
    "sky-plate": {"boost_type": "Flying", "multiplier": 1.2, "arceus": True, "changes_arceus_type": "Flying", "min_gen": 4},
    "toxic-plate": {"boost_type": "Poison", "multiplier": 1.2, "arceus": True, "changes_arceus_type": "Poison", "min_gen": 4},
    "mind-plate": {"boost_type": "Psychic", "multiplier": 1.2, "arceus": True, "changes_arceus_type": "Psychic", "min_gen": 4},
    "icicle-plate": {"boost_type": "Ice", "multiplier": 1.2, "arceus": True, "changes_arceus_type": "Ice", "min_gen": 4},
    "fist-plate": {"boost_type": "Fighting", "multiplier": 1.2, "arceus": True, "changes_arceus_type": "Fighting", "min_gen": 4},
    "dread-plate": {"boost_type": "Dark", "multiplier": 1.2, "arceus": True, "changes_arceus_type": "Dark", "min_gen": 4},
    "insect-plate": {"boost_type": "Bug", "multiplier": 1.2, "arceus": True, "changes_arceus_type": "Bug", "min_gen": 4},
    "stone-plate": {"boost_type": "Rock", "multiplier": 1.2, "arceus": True, "changes_arceus_type": "Rock", "min_gen": 4},
    "spooky-plate": {"boost_type": "Ghost", "multiplier": 1.2, "arceus": True, "changes_arceus_type": "Ghost", "min_gen": 4},
    "draco-plate": {"boost_type": "Dragon", "multiplier": 1.2, "arceus": True, "changes_arceus_type": "Dragon", "min_gen": 4},
    "iron-plate": {"boost_type": "Steel", "multiplier": 1.2, "arceus": True, "changes_arceus_type": "Steel", "min_gen": 4},
    "pixie-plate": {"boost_type": "Fairy", "multiplier": 1.2, "arceus": True, "changes_arceus_type": "Fairy", "min_gen": 6},  # Gen 6+
    "blank-plate": {"boost_type": "Normal", "multiplier": 1.2, "arceus": True, "changes_arceus_type": "Normal", "min_gen": 8, "legends_arceus": True},  # Legends Arceus only
    "legend-plate": {"boost_type": None, "multiplier": 1.2, "arceus": True, "changes_arceus_type": "judgment_based", "min_gen": 8, "legends_arceus": True},  # Special: Changes with Judgment
    
    # ========== MEMORIES (SILVALLY) ==========
    "fire-memory": {"boost_type": "Fire", "multiplier": 1.2, "silvally": True},
    "water-memory": {"boost_type": "Water", "multiplier": 1.2, "silvally": True},
    "grass-memory": {"boost_type": "Grass", "multiplier": 1.2, "silvally": True},
    "electric-memory": {"boost_type": "Electric", "multiplier": 1.2, "silvally": True},
    "ground-memory": {"boost_type": "Ground", "multiplier": 1.2, "silvally": True},
    "flying-memory": {"boost_type": "Flying", "multiplier": 1.2, "silvally": True},
    "poison-memory": {"boost_type": "Poison", "multiplier": 1.2, "silvally": True},
    "psychic-memory": {"boost_type": "Psychic", "multiplier": 1.2, "silvally": True},
    "ice-memory": {"boost_type": "Ice", "multiplier": 1.2, "silvally": True},
    "fighting-memory": {"boost_type": "Fighting", "multiplier": 1.2, "silvally": True},
    "dark-memory": {"boost_type": "Dark", "multiplier": 1.2, "silvally": True},
    "bug-memory": {"boost_type": "Bug", "multiplier": 1.2, "silvally": True},
    "rock-memory": {"boost_type": "Rock", "multiplier": 1.2, "silvally": True},
    "ghost-memory": {"boost_type": "Ghost", "multiplier": 1.2, "silvally": True},
    "dragon-memory": {"boost_type": "Dragon", "multiplier": 1.2, "silvally": True},
    "steel-memory": {"boost_type": "Steel", "multiplier": 1.2, "silvally": True},
    "fairy-memory": {"boost_type": "Fairy", "multiplier": 1.2, "silvally": True},
    
    # ========== SPECIES-SPECIFIC HELD ITEMS ==========
    # Deep Sea Scale: Doubles Clamperl's Special Defense (Gen 3+)
    "deep-sea-scale": {
        "species_specific": True, 
        "stat_mult": {"spd": 2.0}, 
        "holder": "clamperl",
        "min_gen": 3,
        "description": "Doubles Clamperl's Special Defense"
    },
    
    # Deep Sea Tooth: Doubles Clamperl's Special Attack (Gen 3+)
    "deep-sea-tooth": {
        "species_specific": True, 
        "stat_mult": {"spa": 2.0}, 
        "holder": "clamperl",
        "min_gen": 3,
        "description": "Doubles Clamperl's Special Attack"
    },
    
    # Light Ball: Doubles Pikachu's Attack and Special Attack (Gen 2+)
    "light-ball": {
        "species_specific": True, 
        "stat_mult": {"atk": 2.0, "spa": 2.0}, 
        "holder": ["pikachu"],
        "min_gen": 2,
        "description": "Doubles Pikachu's Attack and Special Attack"
    },
    
    # Thick Club: Doubles Cubone/Marowak's Attack (Gen 2+)
    "thick-club": {
        "species_specific": True, 
        "stat_mult": {"atk": 2.0}, 
        "holder": ["cubone", "marowak", "marowak-alola"],
        "min_gen": 2,
        "description": "Doubles Cubone/Marowak's Attack"
    },
    
    # Leek: +2 crit stages for Farfetch'd/Sirfetch'd (Gen 2+, Sirfetch'd Gen 8+)
    "leek": {
        "species_specific": True, 
        "crit_boost": 2, 
        "holder": ["farfetchd", "farfetchd-galar", "sirfetchd"],
        "min_gen": 2,
        "description": "Increases critical hit ratio by 2 stages for Farfetch'd/Sirfetch'd"
    },
    
    # Lucky Punch: +2 crit stages for Chansey (Gen 2+)
    "lucky-punch": {
        "species_specific": True, 
        "crit_boost": 2, 
        "holder": "chansey",
        "min_gen": 2,
        "description": "Increases critical hit ratio by 2 stages for Chansey"
    },
    
    # Metal Powder: Doubles Ditto's Defense (Gen 2+)
    "metal-powder": {
        "species_specific": True, 
        "stat_mult": {"defn": 2.0}, 
        "holder": "ditto",
        "min_gen": 2,
        "description": "Doubles Ditto's Defense"
    },
    
    # Quick Powder: Doubles Ditto's Speed (Gen 4+)
    "quick-powder": {
        "species_specific": True, 
        "stat_mult": {"spe": 2.0}, 
        "holder": "ditto",
        "min_gen": 4,
        "description": "Doubles Ditto's Speed"
    },
    
    # Soul Dew: Generation-specific effects for Latias/Latios
    # Gen 3-6: +50% Special Attack and Special Defense
    # Gen 7+: +20% power to Psychic and Dragon-type moves
    "soul-dew": {
        "species_specific": True,
        "holder": ["latias", "latios"],
        "min_gen": 3,
        "gen_specific": {
            "3-6": {"stat_mult": {"spa": 1.5, "spd": 1.5}},
            "7+": {"boost_types": ["Psychic", "Dragon"], "multiplier": 4915 / 4096}
        },
        "description": "Gen 3-6: +50% SpA/SpD for Latias/Latios. Gen 7+: +20% Psychic/Dragon moves"
    },
    # Creation Trio Orbs (Gen 4+): Always 20% boost since they debut in Gen 4
    "adamant-orb": {"boost_types": ["Steel", "Dragon"], "multiplier": 1.2, "holder": "dialga", "min_gen": 4, "species_specific": True},
    "lustrous-orb": {"boost_types": ["Water", "Dragon"], "multiplier": 1.2, "holder": "palkia", "min_gen": 4, "species_specific": True},
    "griseous-orb": {"boost_types": ["Ghost", "Dragon"], "multiplier": 1.2, "holder": "giratina", "min_gen": 4, "species_specific": True},
    
    # ========== LEFTOVERS & RECOVERY ==========
    "leftovers": {
        "end_of_turn_heal": 0.0625,
        "description": "Restores 1/16 HP at the end of each turn"
    },
    # Black Sludge: Heals Poison-types, damages others (Gen 4+)
    # Gen 4: Works even with Heal Block
    # Gen 5+: Doesn't heal if Heal Block active
    "black-sludge": {
        "end_of_turn_heal": 1 / 16,  # 1/16 HP for Poison-types
        "poison_type_only": True,
        "damages_non_poison": 1 / 8,  # 1/8 HP damage for non-Poison
        "min_gen": 4,
        "gen_specific": {
            "4": {"ignores_heal_block": True},
            "5+": {"blocked_by_heal_block": True}
        },
        "magic_guard_immune": True,  # Magic Guard immune to damage
        "description": "Gen 4: Heals Poison 1/16 (even Heal Block), damages others 1/8. Gen 5+: Heal Block blocks"
    },
    "shell-bell": {
        "heal_on_hit": 0.125,
        "description": "Restores 1/8 of damage dealt"
    },
    # Big Root: Boosts draining moves and residual healing
    # Gen 4: 30% boost (1.3x)
    # Gen 5+: Exact boost (5324/4096 ≈ 1.3008)
    "big-root": {
        "boosts_draining_moves": True,
        "min_gen": 4,
        "gen_specific": {
            "4": {"multiplier": 1.3},  # 30% boost
            "5+": {"multiplier": 5324 / 4096}  # Exact calculation (≈1.3008)
        },
        "affected_moves": [
            "absorb", "aqua-ring", "bitter-blade", "drain-punch", "draining-kiss",
            "dream-eater", "giga-drain", "horn-leech", "ingrain", "leech-life",
            "leech-seed", "matcha-gotcha", "mega-drain", "oblivion-wing",
            "parabolic-charge", "strength-sap"
        ],
        "description": "Boosts HP from draining moves by 30% (Gen 4: 1.3x, Gen 5+: 5324/4096)"
    },
    
    # ========== DEFENSIVE ITEMS ==========
    # Rocky Helmet: Damages attacker on contact (Gen 5+)
    # Each hit of multistrike triggers separately
    # Gen 5-6: If both faint, Rocky Helmet holder wins
    # Gen 7+: Bug in v1.0 (holder wins), v1.1+ (attacker wins)
    "rocky-helmet": {
        "contact_damage": 1 / 6,  # 1/6 max HP
        "min_gen": 5,
        "each_multistrike_hit": True,
        "stolen_before_activation": ["knock-off", "thief", "covet", "magician"],
        "gen_specific": {
            "5-6": {"both_faint_holder_wins": True},
            "7": {"both_faint_v1_0_holder_wins": True, "both_faint_v1_1_attacker_wins": True}
        },
        "description": "Damages attacker 1/6 HP on contact. Gen 5+"
    },
    "rowap-berry": {
        "retaliation_damage": 0.125,  # 1/8 max HP
        "retaliation_category": "special",  # Only activates on special moves
        "description": "Damages attacker when hit by special move (1/8 max HP)"
    },
    "jaboca-berry": {
        "retaliation_damage": 0.125,  # 1/8 max HP
        "retaliation_category": "physical",  # Only activates on physical moves
        "description": "Damages attacker when hit by physical move (1/8 max HP)"
    },
    # Eviolite: +50% Defense and Special Defense for unevolved Pokemon (Gen 5+)
    "eviolite": {
        "stat_mult": {"defn": 1.5, "spd": 1.5},
        "unevolved_only": True,
        "min_gen": 5,
        "description": "Boosts Defense and Sp. Def by 50% for unevolved Pokémon"
    },
    # Focus Sash: Survive OHKO at full HP (one-time use)
    # Gen 4: Protects from all hits of multistrike, doesn't protect from Future Sight/Doom Desire
    # Gen 5+: Only protects from first hit of multistrike
    "focus-sash": {
        "survives_ohko": True,
        "one_time_use": True,
        "requires_full_hp": True,
        "min_gen": 4,
        "gen_specific": {
            "4": {"protects_all_multistrike": True},
            "5+": {"protects_first_hit_only": True}
        },
        "description": "Survives OHKO at full HP. Gen 4: All multihits, Gen 5+: First hit only (consumed)"
    },
    
    # Focus Band: Chance to survive fatal hit with 1 HP
    # Gen 2: ~12% (30/256) chance, protects all multistrike hits, no confusion damage
    # Gen 3-4: 10% chance, protects all multistrike hits, includes confusion damage
    # Gen 5+: 10% chance, must activate independently for each hit
    "focus-band": {
        "survives_ohko_chance": True,
        "min_gen": 2,
        "gen_specific": {
            "2": {
                "chance": 30 / 256,  # ~11.7%
                "protects_all_multistrike": True,
                "confusion_damage": False  # Doesn't protect from confusion
            },
            "3-4": {
                "chance": 0.1,  # 10%
                "protects_all_multistrike": True,
                "confusion_damage": True  # Now protects from confusion
            },
            "5+": {
                "chance": 0.1,  # 10%
                "independent_checks": True,  # Must activate separately each hit
                "confusion_damage": True
            }
        },
        "description": "Gen 2: 30/256 chance. Gen 3-4: 10% all hits. Gen 5+: 10% independent checks"
    },
    # Air Balloon: Grants Ground immunity until hit (Gen 5+)
    "air-balloon": {
        "levitate_effect": True,
        "pops_on_hit": True,
        "min_gen": 5,
        "ignored_by": ["gravity", "ingrain", "smack-down", "thousand-arrows"],
        "triggers": ["unburden", "symbiosis"],
        "description": "Grants Ground immunity until hit by damaging move (Gen 5+)"
    },
    
    # Ability Shield: Protects holder's ability from being changed/suppressed (Gen 9+)
    "ability-shield": {
        "protects_ability": True,
        "min_gen": 9,
        "protects_from": [
            "gastro-acid", "worry-seed", "simple-beam", "entrainment", 
            "skill-swap", "role-play", "trace", "neutralizing-gas", 
            "mold-breaker", "teravolt", "turboblaze"
        ],
        "allows_transform": True,  # Transform/Imposter still copy ability, but then protect it
        "description": "Prevents Ability from being changed or suppressed (Gen 9+)"
    },
    
    # ========== STATUS HEALING BERRIES ==========
    "cheri-berry": {"heals_status": "par", "berry": True},
    "chesto-berry": {"heals_status": "slp", "berry": True},
    "pecha-berry": {"heals_status": "psn", "berry": True},
    "rawst-berry": {"heals_status": "brn", "berry": True},
    "aspear-berry": {"heals_status": "frz", "berry": True},
    "persim-berry": {"heals_status": "confusion", "berry": True},
    "lum-berry": {"heals_status": "all", "berry": True},

    # Touga Berry: cures confusion, cannot be stolen or tricked
    "touga-berry": {
        "heals_status": "confusion",
        "berry": True,
        "unstealable": True,
        "untrickable": True
    },
    
    # ========== HP HEALING BERRIES ==========
    "oran-berry": {"heals_hp": 10, "berry": True},
    "sitrus-berry": {"heals_hp_percent": 0.25, "berry": True},
    "berry-juice": {"heals_hp": 20, "berry": False},
    "figy-berry": {"heals_hp_percent": 0.33, "confuses_if_wrong_nature": "atk", "berry": True},
    "wiki-berry": {"heals_hp_percent": 0.33, "confuses_if_wrong_nature": "spa", "berry": True},
    "mago-berry": {"heals_hp_percent": 0.33, "confuses_if_wrong_nature": "spe", "berry": True},
    "aguav-berry": {"heals_hp_percent": 0.33, "confuses_if_wrong_nature": "spd", "berry": True},
    "iapapa-berry": {"heals_hp_percent": 0.33, "confuses_if_wrong_nature": "defn", "berry": True},
    
    # ========== PINCH BERRIES (TYPE RESISTANCE) ==========
    "occa-berry": {"resist_once": "Fire", "berry": True},
    "passho-berry": {"resist_once": "Water", "berry": True},
    "wacan-berry": {"resist_once": "Electric", "berry": True},
    "rindo-berry": {"resist_once": "Grass", "berry": True},
    "yache-berry": {"resist_once": "Ice", "berry": True},
    "chople-berry": {"resist_once": "Fighting", "berry": True},
    "kebia-berry": {"resist_once": "Poison", "berry": True},
    "shuca-berry": {"resist_once": "Ground", "berry": True},
    "coba-berry": {"resist_once": "Flying", "berry": True},
    "payapa-berry": {"resist_once": "Psychic", "berry": True},
    "tanga-berry": {"resist_once": "Bug", "berry": True},
    "charti-berry": {"resist_once": "Rock", "berry": True},
    "kasib-berry": {"resist_once": "Ghost", "berry": True},
    "haban-berry": {"resist_once": "Dragon", "berry": True},
    "colbur-berry": {"resist_once": "Dark", "berry": True},
    "babiri-berry": {"resist_once": "Steel", "berry": True},
    "chilan-berry": {"resist_once": "Normal", "berry": True},
    "roseli-berry": {"resist_once": "Fairy", "berry": True},
    
    # ========== STAT BOOST BERRIES ==========
    "liechi-berry": {"boost_stat_at_pinch": {"atk": 1}, "berry": True},
    "ganlon-berry": {"boost_stat_at_pinch": {"defn": 1}, "berry": True},
    "salac-berry": {"boost_stat_at_pinch": {"spe": 1}, "berry": True},
    "petaya-berry": {"boost_stat_at_pinch": {"spa": 1}, "berry": True},
    "apicot-berry": {"boost_stat_at_pinch": {"spd": 1}, "berry": True},
    "lansat-berry": {"crit_boost_at_pinch": 2, "berry": True},
    "starf-berry": {"random_stat_boost_at_pinch": 2, "berry": True},
    "micle-berry": {"accuracy_boost_at_pinch": True, "berry": True},
    
    # ========== DAMAGE REDUCTION ==========
    # Weakness Policy: +2 Atk/SpA when hit super-effectively (Gen 6+)
    # Doesn't activate if already at +6 (or -6 with Contrary)
    # Doesn't activate if protected or unaffected
    # Fixed-damage moves never activate it
    "weakness-policy": {
        "boost_on_super_effective": {"atk": 2, "spa": 2},
        "one_time_use": True,
        "min_gen": 6,
        "doesnt_activate_at_max": True,  # Not if +6 Atk AND +6 SpA (or -6 with Contrary)
        "doesnt_activate_if_protected": True,  # Protection, immunity, etc.
        "doesnt_activate_fixed_damage": True,  # Seismic Toss, Mirror Coat
        "contrary_reverses": True,  # Contrary: -2 Atk/SpA instead
        "mold_breaker_ignores_contrary": True,
        "symbiosis_after_all_consumptions": True,
        "description": "+2 Atk/SpA when hit super-effectively (consumed). Gen 6+"
    },
    
    # Blunder Policy: +2 Speed when a move misses due to accuracy (Gen 8+)
    "blunder-policy": {
        "boost_on_miss": {"spe": 2},
        "one_time_use": True,
        "min_gen": 8,
        "excludes": [
            "ohko_moves",  # OHKO moves don't trigger it
            "triple_kick_miss",  # Triple Kick/Axel/Population Bomb early miss
            "semi_invulnerable_miss"  # Missing due to Fly/Dig/etc.
        ],
        "description": "Raises Speed by 2 stages when move misses due to accuracy check (Gen 8+)"
    },
    "booster-energy": {
        "activates_paradox_ability": True,
        "one_time_use": True,
        "description": "Activates Protosynthesis or Quark Drive on switch-in (consumed)"
    },
    # Absorb Bulb: +1 SpA when hit by Water-type move (Gen 5+)
    "absorb-bulb": {
        "boost_on_hit_by_type": {"type": "Water", "stages": {"spa": 1}},
        "one_time_use": True,
        "min_gen": 5,
        "doesnt_activate_at_max": True,  # Not if +6 SpA (or -6 with Contrary)
        "doesnt_activate_if_protected": True,  # Protection, immunity, Water Absorb, Wonder Guard
        "contrary_reverses": True,  # Contrary: -1 SpA instead
        "symbiosis_after_all_consumptions": True,
        "description": "+1 SpA when hit by Water-type move (consumed). Gen 5+"
    },
    
    # Cell Battery: +1 Atk when hit by Electric-type move (Gen 5+)
    "cell-battery": {
        "boost_on_hit_by_type": {"type": "Electric", "stages": {"atk": 1}},
        "one_time_use": True,
        "min_gen": 5,
        "doesnt_activate_at_max": True,  # Not if +6 Atk (or -6 with Contrary)
        "doesnt_activate_if_protected": True,  # Protection, immunity, Motor Drive, Ground-type
        "contrary_reverses": True,  # Contrary: -1 Atk instead
        "symbiosis_after_all_consumptions": True,
        "description": "+1 Atk when hit by Electric-type move (consumed). Gen 5+"
    },
    
    # Luminous Moss: +1 SpD when hit by Water-type move (Gen 6+)
    "luminous-moss": {
        "boost_on_hit_by_type": {"type": "Water", "stages": {"spd": 1}},
        "one_time_use": True,
        "min_gen": 6,
        "doesnt_activate_at_max": True,  # Not if +6 SpD (or -6 with Contrary)
        "doesnt_activate_if_protected": True,  # Protection, immunity, Water Absorb, Wonder Guard
        "contrary_reverses": True,  # Contrary: -1 SpD instead
        "symbiosis_after_all_consumptions": True,
        "description": "+1 SpD when hit by Water-type move (consumed). Gen 6+"
    },
    
    # Snowball: +1 Atk when hit by Ice-type move (Gen 6+)
    "snowball": {
        "boost_on_hit_by_type": {"type": "Ice", "stages": {"atk": 1}},
        "one_time_use": True,
        "min_gen": 6,
        "doesnt_activate_at_max": True,  # Not if +6 Atk (or -6 with Contrary)
        "doesnt_activate_if_protected": True,  # Protection, immunity, Telepathy, Wonder Guard
        "contrary_reverses": True,  # Contrary: -1 Atk instead
        "symbiosis_after_all_consumptions": True,
        "description": "+1 Atk when hit by Ice-type move (consumed). Gen 6+"
    },
    
    # ========== GEMS (GEN 5-6) ==========
    "normal-gem": {"gem_type": "Normal", "multiplier": 1.3, "one_time_use": True},
    "fire-gem": {"gem_type": "Fire", "multiplier": 1.3, "one_time_use": True},
    "water-gem": {"gem_type": "Water", "multiplier": 1.3, "one_time_use": True},
    "electric-gem": {"gem_type": "Electric", "multiplier": 1.3, "one_time_use": True},
    "grass-gem": {"gem_type": "Grass", "multiplier": 1.3, "one_time_use": True},
    "ice-gem": {"gem_type": "Ice", "multiplier": 1.3, "one_time_use": True},
    "fighting-gem": {"gem_type": "Fighting", "multiplier": 1.3, "one_time_use": True},
    "poison-gem": {"gem_type": "Poison", "multiplier": 1.3, "one_time_use": True},
    "ground-gem": {"gem_type": "Ground", "multiplier": 1.3, "one_time_use": True},
    "flying-gem": {"gem_type": "Flying", "multiplier": 1.3, "one_time_use": True},
    "psychic-gem": {"gem_type": "Psychic", "multiplier": 1.3, "one_time_use": True},
    "bug-gem": {"gem_type": "Bug", "multiplier": 1.3, "one_time_use": True},
    "rock-gem": {"gem_type": "Rock", "multiplier": 1.3, "one_time_use": True},
    "ghost-gem": {"gem_type": "Ghost", "multiplier": 1.3, "one_time_use": True},
    "dragon-gem": {"gem_type": "Dragon", "multiplier": 1.3, "one_time_use": True},
    "dark-gem": {"gem_type": "Dark", "multiplier": 1.3, "one_time_use": True},
    "steel-gem": {"gem_type": "Steel", "multiplier": 1.3, "one_time_use": True},
    "fairy-gem": {"gem_type": "Fairy", "multiplier": 1.3, "one_time_use": True},
    
    # ========== MISC BATTLE ITEMS ==========
    # Metronome (Item): Boosts consecutive move use (Gen 4+)
    # Gen 4: 10% per turn, max 100% (11+ turns)
    # Gen 5+: 20% per turn, max 100% (6+ turns) - exact: +819/4096 per turn
    "metronome": {
        "consecutive_use_boost": True,
        "min_gen": 4,
        "gen_specific": {
            "4": {
                # Turn 1: 1.0, Turn 2: 1.1, Turn 3: 1.2, ... Turn 11+: 2.0
                "boost_per_turn": 0.1,
                "max_boost": 2.0,
                "turns_to_max": 11
            },
            "5+": {
                # Turn 2: 4915/4096, Turn 3: 5734/4096, Turn 4: 6553/4096, 
                # Turn 5: 7372/4096, Turn 6+: 2.0
                "boost_per_turn": 819 / 4096,  # Exact: ~0.2
                "max_boost": 2.0,
                "turns_to_max": 6,
                "exact_multipliers": {
                    2: 4915 / 4096,  # ≈1.2
                    3: 5734 / 4096,  # ≈1.4
                    4: 6553 / 4096,  # ≈1.6
                    5: 7372 / 4096,  # ≈1.8
                    6: 2.0           # Max
                }
            }
        },
        "resets_on": ["switch", "different_move", "unsuccessful_use", "protection", "immunity"],
        "charging_moves": ["bounce", "dig", "dive", "fly", "freeze-shock", "geomancy", "ice-burn", 
                           "meteor-beam", "phantom-force", "razor-wind", "shadow-force", "skull-bash",
                           "sky-attack", "solar-beam", "solar-blade", "electro-shot"],
        "description": "Gen 4: 10%/turn (11+ max). Gen 5+: 20%/turn (6+ max), exact 819/4096"
    },
    # Zoom Lens: Boosts accuracy when moving after opponent (Gen 4+)
    # Gen 4: 20% boost (1.2x)
    # Gen 5+: Exact 4915/4096 boost
    "zoom-lens": {
        "min_gen": 4,
        "gen_specific": {
            "4": {"accuracy_multiplier_after": 1.2},
            "5+": {"accuracy_multiplier_after": 4915 / 4096}  # Exact calculation
        },
        "description": "Gen 4: 1.2x accuracy after foe. Gen 5+: 4915/4096 boost when moving after"
    },
    # Wide Lens: Boosts accuracy (Gen 4+)
    # Gen 4: 10% boost (1.1x)
    # Gen 5+: Exact 4505/4096 boost
    "wide-lens": {
        "min_gen": 4,
        "gen_specific": {
            "4": {"accuracy_multiplier": 1.1},
            "5+": {"accuracy_multiplier": 4505 / 4096}  # Exact calculation
        },
        "description": "Gen 4: 1.1x accuracy. Gen 5+: 4505/4096 accuracy boost"
    },
    
    # Scope Lens: +1 crit stage (Gen 2+)
    "scope-lens": {
        "crit_boost": 1,
        "min_gen": 2,
        "description": "Increases critical hit ratio by 1 stage. Gen 2+"
    },
    "razor-claw": {
        "crit_boost": 1,
        "description": "Increases critical hit ratio"
    },
    # King's Rock: Adds flinch chance to moves (generation-specific)
    # Gen 2: 11.71875% (30/256) on final hit of multistrike moves only, affects specific moves
    # Gen 3-4: 10% on each hit, affects specific moves, not affected by Serene Grace
    # Gen 5+: 10% on ALL attacking moves without inherent flinch, affected by Serene Grace
    "kings-rock": {
        "adds_flinch": True,
        "min_gen": 2,
        "gen_specific": {
            "2": {
                "flinch_chance": 30 / 256,  # 11.71875%
                "final_hit_only": True,  # Only final hit of multistrike
                "affects_frozen_sleeping": True  # Unique to Gen 2
            },
            "3-4": {
                "flinch_chance": 0.1,  # 10%
                "each_hit": True,  # Each hit of multistrike
                "serene_grace": False  # Not affected by Serene Grace
            },
            "5+": {
                "flinch_chance": 0.1,  # 10%
                "all_attacking_moves": True,  # All moves without inherent flinch
                "serene_grace": True,  # Affected by Serene Grace
                "sheer_force_negates": True  # Sheer Force removes King's Rock flinch
            }
        },
        "description": "Gen 2: 30/256 flinch on final hit. Gen 3-4: 10% each hit. Gen 5+: 10% all moves"
    },
    # Razor Fang: Adds flinch chance to moves (Gen 4+)
    # Gen 4: 10% on specific moves, not affected by Serene Grace, U-turn quirk
    # Gen 5+: 10% on ALL attacking moves without flinch, affected by Serene Grace
    "razor-fang": {
        "adds_flinch": True,
        "min_gen": 4,
        "gen_specific": {
            "4": {
                "flinch_chance": 0.1,
                "each_hit": True,
                "serene_grace": False,
                "uturn_quirk": True  # U-turn only flinches if switched-in mon has Razor Fang
            },
            "5+": {
                "flinch_chance": 0.1,
                "all_attacking_moves": True,
                "serene_grace": True,
                "sheer_force_negates": True
            }
        },
        "description": "Gen 4: 10% flinch specific moves. Gen 5+: 10% all moves, Serene Grace"
    },
    # Covert Cloak: Blocks secondary effects of damaging moves (Gen 9+)
    "covert-cloak": {
        "blocks_secondary_effects": True,
        "flinch_immunity": True,  # Immune to flinching
        "freeze_immunity": True,  # Immune to freeze (only from damaging moves)
        "min_gen": 9,
        "does_not_prevent": ["clear-smog-stat-removal", "knock-off", "hazards-from-moves"],
        "description": "Blocks secondary effects, flinching, and freeze from damaging moves (Gen 9+)"
    },
    # Bright Powder: Reduces opponent accuracy
    # Gen 2: 20/256 (~7.8%) additional miss chance
    # Gen 3+: 10% accuracy reduction (multiply by 0.9)
    "bright-powder": {
        "min_gen": 2,
        "gen_specific": {
            "2": {"accuracy_miss_chance": 20 / 256},  # ~7.8% additional miss chance
            "3+": {"accuracy_multiplier": 0.9}  # 10% accuracy reduction
        },
        "description": "Gen 2: 20/256 miss chance, Gen 3+: Reduces accuracy by 10%"
    },
    # Lax Incense: Reduces opponent accuracy (Gen 3+)
    # Gen 3: 5% reduction (multiply by 0.95)
    # Gen 4+: 10% reduction (multiply by 0.9)
    "lax-incense": {
        "min_gen": 3,
        "gen_specific": {
            "3": {"accuracy_multiplier": 0.95},  # 5% reduction
            "4+": {"accuracy_multiplier": 0.9}  # 10% reduction
        },
        "description": "Gen 3: Reduces accuracy by 5%. Gen 4+: 10% reduction"
    },
    
    # ========== TERRAIN SEEDS ==========
    "electric-seed": {"boost_on_terrain": {"terrain": "electric", "stages": {"defn": 1}}, "one_time_use": True},
    "psychic-seed": {"boost_on_terrain": {"terrain": "psychic", "stages": {"spd": 1}}, "one_time_use": True},
    "grassy-seed": {"boost_on_terrain": {"terrain": "grassy", "stages": {"defn": 1}}, "one_time_use": True},
    "misty-seed": {"boost_on_terrain": {"terrain": "misty", "stages": {"spd": 1}}, "one_time_use": True},
    
    # ========== STAT PROTECTION & SWITCHING ITEMS ==========
    # Clear Amulet: Prevents stat lowering from moves/abilities (Gen 9+)
    "clear-amulet": {
        "prevents_stat_lowering": True,
        "min_gen": 9,
        "does_not_prevent": ["haze", "clear-smog"],  # Haze and Clear Smog bypass it
        "description": "Prevents stat lowering from moves/abilities (not Haze/Clear Smog). Gen 9+"
    },
    
    # Eject Button: Switches holder out when hit (Gen 5+)
    "eject-button": {
        "switches_on_hit": True,
        "one_time_use": True,
        "min_gen": 5,
        "requires_damage": True,  # Must take damage (not substitute)
        "activates_after_multistrike": True,  # After last hit
        "bypasses_trapping": True,  # Ignores Suction Cups, trapping moves, Dynamax
        "stolen_by_knock_off_first": True,  # Knock Off/Thief steal before it activates
        "description": "Switches holder out when hit by damaging move (consumed). Gen 5+"
    },
    
    # Eject Pack: Switches holder out when stats lowered (Gen 8+)
    "eject-pack": {
        "switches_on_stat_lower": True,
        "one_time_use": True,
        "min_gen": 8,
        "includes_self_lowering": True,  # Even from own moves like Overheat
        "sticky_web_triggers": True,  # Sticky Web immediately switches out
        "description": "Switches holder out when any stat is lowered (consumed). Gen 8+"
    },
    
    # Destiny Knot: Infatuates the infatuator (Gen 3+)
    "destiny-knot": {
        "shares_infatuation": True,
        "min_gen": 3,
        "description": "If holder becomes infatuated, infatuates the source too. Gen 3+"
    },
    
    # Float Stone: Halves holder's weight (Gen 5+)
    "float-stone": {
        "weight_multiplier": 0.5,
        "min_gen": 5,
        "minimum_weight": 0.1,  # Weight can't go below 0.1 kg
        "autotomize_applied_first": True,  # Autotomize applied before Float Stone
        "description": "Halves holder's weight (minimum 0.1 kg). Gen 5+"
    },
    
    # ========== ROOM SERVICE & TERRAIN EXTENDER ==========
    # Room Service: Lowers Speed by 1 stage in Trick Room (Gen 8+)
    # Activates when Trick Room used OR when switching in during Trick Room
    "room-service": {
        "lowers_speed_in_trick_room": True,
        "one_time_use": True,
        "min_gen": 8,
        "activates_on_switch_in": True,  # Like terrain seeds
        "stat_change": {"spe": -1},
        "description": "Lowers Speed by 1 stage in Trick Room (consumed). Gen 8+"
    },
    "terrain-extender": {
        "extends_terrain": True,
        "description": "Extends terrain duration from 5 to 8 turns"
    },
    
    # ========== WEATHER/SCREEN EXTENDERS ==========
    "heat-rock": {
        "extends_weather": "sun",
        "description": "Extends harsh sunlight duration"
    },
    "damp-rock": {
        "extends_weather": "rain",
        "description": "Extends rain duration"
    },
    "icy-rock": {
        "extends_weather": "hail",
        "description": "Extends hail duration"
    },
    "smooth-rock": {
        "extends_weather": "sandstorm",
        "description": "Extends sandstorm duration"
    },
    "light-clay": {
        "extends_screens": True,
        "description": "Extends Reflect/Light Screen from 5 to 8 turns"
    },
    
    # ========== UTILITY ITEMS ==========
    # Mental Herb: Cures mental conditions (Gen 3+)
    # Gen 3-4: Only cures infatuation
    # Gen 5+: Cures infatuation, Taunt, Encore, Torment, Heal Block, Disable (Cursed Body)
    "mental-herb": {
        "cures_mental_effects": True,
        "one_time_use": True,
        "min_gen": 3,
        "gen_specific": {
            "3-4": {
                "cures": ["infatuation"],
                "oblivious_prevents": True  # Oblivious cures before Mental Herb
            },
            "5+": {
                "cures": ["infatuation", "taunt", "encore", "torment", "heal-block", "disable", "cursed-body"],
                "consumed_before_oblivious": True  # Mental Herb consumed before Oblivious
            }
        },
        "description": "Gen 3-4: Cures infatuation. Gen 5+: Cures infatuation, Taunt, Encore, etc."
    },
    # White Herb: Resets negative stat changes (Gen 3+)
    # Complex activation timing with various abilities and moves
    "white-herb": {
        "resets_negative_stats": True,
        "one_time_use": True,
        "min_gen": 3,
        "activates_after_multistrike": True,  # After final hit of multistrike
        "activates_after_all_abilities": True,  # After Tangling Hair, Gooey, Weak Armor
        "stolen_before_activation": ["knock-off-weak-armor", "thief-weak-armor", "pickpocket-superpower"],
        "defiant_competitive_trigger_first": True,  # Defiant/Competitive boost happens first
        "description": "Resets negative stat changes (consumed). Gen 3+"
    },
    # Power Herb: Skip charge turn for charging moves (Gen 4+)
    # Charging moves: Bounce, Dig, Dive, Fly, Freeze Shock, Geomancy, Ice Burn, Meteor Beam,
    #                 Phantom Force, Razor Wind, Shadow Force, Skull Bash, Sky Attack, 
    #                 Solar Beam, Solar Blade, Electro Shot
    # Not consumed if conditions met (Solar moves in sun, Electro Shot in rain)
    # Defense boost from Skull Bash and SpA boost from Meteor Beam/Electro Shot still applied
    "power-herb": {
        "skip_charge_turn": True,
        "one_time_use": True,
        "min_gen": 4,
        "not_consumed_if": ["solar-in-sun", "electro-shot-in-rain"],
        "keeps_stat_boosts": ["skull-bash-def", "meteor-beam-spa", "electro-shot-spa"],
        "charging_moves": ["bounce", "dig", "dive", "fly", "freeze-shock", "geomancy", "ice-burn", 
                           "meteor-beam", "phantom-force", "razor-wind", "shadow-force", "skull-bash",
                           "sky-attack", "solar-beam", "solar-blade", "electro-shot"],
        "description": "Skips charge turn for charging moves (consumed). Gen 4+"
    },
    # Red Card: Forces attacker to switch when hit (Gen 5+)
    # Random switch, not trainer's choice
    # Activates after last hit of multistrike
    # Bypasses trapping (except Ingrain, Suction Cups, Commander)
    "red-card": {
        "forces_switch_on_hit": True,
        "one_time_use": True,
        "min_gen": 5,
        "random_switch": True,  # Random, not trainer choice
        "activates_after_multistrike": True,
        "requires_damage": True,  # Not if substitute takes hit
        "doesnt_work_if": ["wild-attacker", "no-switch-available", "sheer-force-boosted"],
        "bypasses_most_trapping": True,
        "cant_bypass": ["ingrain", "suction-cups", "commander-dondozo"],
        "stolen_before_activation": ["knock-off", "thief", "covet", "magician"],
        "overrides_uturn": True,  # U-turn/Volt Switch/Flip Turn become random switch
        "dynamax_immune_but_consumed": True,
        "description": "Forces attacker to random switch when hit (consumed). Gen 5+"
    },
    # Shed Shell: Allows switching even when trapped (Gen 4+)
    # Works even with Ingrain (self-inflicted)
    "shed-shell": {
        "ignores_trapping": True,
        "min_gen": 4,
        "ignores_ingrain": True,
        "description": "Can always switch out (even Ingrain). Gen 4+"
    },
    
    # Ring Target: Removes type immunities (Gen 5+)
    # Ground-type becomes vulnerable to Thunder Wave
    # Doesn't affect other immunities (Grass immune to powder)
    "ring-target": {
        "removes_type_immunities": True,
        "min_gen": 5,
        "doesnt_remove": ["powder-immunity", "other-non-type-immunities"],
        "ground_vulnerable_thunder_wave": True,
        "description": "Removes type-based damage immunities. Gen 5+"
    },
    
    # Throat Spray: +1 SpA after using sound move (Gen 8+)
    # Not consumed if move fails or battle ends
    "throat-spray": {
        "boosts_spa_after_sound": True,
        "one_time_use": True,
        "min_gen": 8,
        "stat_change": {"spa": 1},
        "not_consumed_if_fails": True,
        "not_consumed_if_battle_ends": True,
        "description": "+1 SpA after sound move (consumed). Gen 8+"
    },
    # Protective Pads: Prevents contact effects from holder's moves (Gen 7+)
    # Protects from: Static, Flame Body, Poison Point, Rough Skin, Iron Barbs, etc.
    # Perish Body: Neither Pokémon affected
    # Unseen Fist: Bypasses protection but still makes contact
    "protective-pads": {
        "no_contact_effects": True,
        "min_gen": 7,
        "protects_from_abilities": ["static", "flame-body", "poison-point", "rough-skin", "iron-barbs", 
                                     "perish-body", "rocky-helmet", "sticky-barb"],
        "unseen_fist_still_damages": True,  # Unseen Fist bypasses protection but still makes contact
        "description": "Contact moves don't trigger contact effects on target. Gen 7+"
    },
    # Safety Goggles: Immune to powder/spore moves and weather damage (Gen 6+)
    # Also blocks Effect Spore ability
    "safety-goggles": {
        "powder_immunity": True,
        "weather_immunity": True,  # Hail and Sandstorm damage
        "min_gen": 6,
        "blocks_effect_spore": True,
        "description": "Immune to powder moves, Effect Spore, and weather damage. Gen 6+"
    },
    
    # Utility Umbrella: Negates rain and sun effects (Gen 8+)
    # Holder unaffected by rain/sun (weather still exists)
    # Abilities/moves behave as if no weather
    "utility-umbrella": {
        "negates_rain_sun": True,
        "min_gen": 8,
        "holder_treats_as_no_weather": True,  # For abilities like Chlorophyll
        "water_fire_not_boosted": True,  # Water/Fire moves not boosted/weakened
        "thunder_accuracy_normal": True,  # Thunder/Hurricane normal accuracy
        "solar_beam_normal": True,  # Solar moves normal charge/power
        "weather_ball_normal": True,  # Weather Ball stays Normal-type, no boost
        "hydro_steam_not_boosted": True,  # Hydro Steam not boosted in sun
        "can_be_frozen_in_sun": True,  # Can be frozen despite harsh sunlight
        "cherrim_stays_overcast": True,  # Cherrim stays Overcast Form
        "flower_gift_ally_unaffected": True,  # But ally Flower Gift still works
        "description": "Holder unaffected by rain/sun effects. Gen 8+"
    },
    "heavy-duty-boots": {
        "hazard_immunity": True,
        "description": "Immune to entry hazards"
    },
    
    # Loaded Dice: Multi-strike moves hit at least 4 times (Gen 9+)
    # Affects: Bullet Seed, Icicle Spear, Pin Missile, Rock Blast, Tail Slap, Scale Shot, etc.
    # Triple Kick, Triple Axel, Population Bomb: Only one accuracy check
    # Population Bomb: 4-10 hits with even chance
    "loaded-dice": {
        "multistrike_min_4": True,
        "min_gen": 9,
        "one_accuracy_check": ["triple-kick", "triple-axel", "population-bomb"],
        "population_bomb_4_to_10": True,
        "description": "Multi-strike moves hit at least 4 times (if possible). Gen 9+"
    },
    
    # Punching Glove: +10% punch moves, prevents contact (Gen 9+)
    # Stacks with Iron Fist ability
    # Punch moves: All moves with "Punch" in name + some others
    "punching-glove": {
        "punch_boost": 1.1,  # 10% boost
        "prevents_contact": True,
        "min_gen": 9,
        "stacks_with_iron_fist": True,
        "description": "+10% punch moves, prevents contact (stacks with Iron Fist). Gen 9+"
    },
    
    # Mirror Herb: Copies opponent's stat boosts (Gen 9+)
    # If opponent uses Dragon Dance (+1 Atk, +1 Spe), holder gets same boosts
    # Consumed after use
    "mirror-herb": {
        "copies_stat_boosts": True,
        "one_time_use": True,
        "min_gen": 9,
        "description": "Copies opponent's stat increases (consumed). Gen 9+"
    },
    
    # Macho Brace: Doubles EVs but halves Speed (Gen 3+)
    # Stacks with Pokérus
    # Doesn't affect vitamins/feathers
    "macho-brace": {
        "stat_mult": {"spe": 0.5},  # Halves Speed
        "doubles_evs": True,
        "min_gen": 3,
        "stacks_with_pokerus": True,
        "doesnt_affect": ["vitamins", "feathers"],
        "description": "Doubles EVs gained in battle, halves Speed. Gen 3+"
    },
    
    # Quick Claw: Chance to go first in priority bracket (Gen 2+)
    # Gen 2: 60/256 (~23%) chance
    # Gen 3+: 20% chance, not affected by Trick Room or Stall
    "quick-claw": {
        "priority_boost_chance": True,
        "min_gen": 2,
        "gen_specific": {
            "2": {"chance": 60 / 256},  # ~23.4%
            "3+": {"chance": 0.2}  # 20%
        },
        "unaffected_by": ["trick-room", "stall"],
        "delayed_activation": True,  # Doesn't affect turn order until next turn if gained/lost
        "description": "Gen 2: 60/256 go first. Gen 3+: 20% go first in priority bracket"
    },
    
    # Luck Incense: Doubles prize money (Gen 3+)
    # Doubles coins from Pay Day and G-Max Gold Rush
    # Stacks with Happy Hour and Prize Money Power
    # Doesn't stack with Amulet Coin or other Luck Incenses
    "luck-incense": {
        "doubles_prize_money": True,
        "min_gen": 3,
        "stacks_with": ["happy-hour", "prize-money-power"],
        "doesnt_stack_with": ["amulet-coin", "other-luck-incense"],
        "unaffected_by_klutz": True,  # Takes effect even with Klutz
        "takes_effect_on_participation": True,  # Just needs to participate in battle
        "description": "Doubles prize money if holder participates in battle. Gen 3+"
    },
    
    # ========== NEGATIVE ITEMS ==========
    # Iron Ball: Halves Speed and grounds holder
    # Gen 4: Flying-type uses secondary type for Ground damage calculation
    # Gen 5+: Flying-type takes 1x damage from Ground (neutral), other effects negated by Klutz/Embargo
    "iron-ball": {
        "stat_mult": {"spe": 0.5},
        "grounds_holder": True,
        "min_gen": 4,
        "gen_specific": {
            "4": {
                "flying_secondary_type": True,  # Uses secondary type for Ground damage
                "always_active": True  # Speed halved even with Klutz/Embargo
            },
            "5+": {
                "flying_neutral_ground": True,  # Flying takes 1x from Ground
                "negated_by_klutz": True  # All effects negated by Klutz/Embargo/Magic Room
            }
        },
        "description": "Halves Speed, grounds holder. Gen 4: Secondary type for Ground. Gen 5+: 1x Ground"
    },
    # Lagging Tail: Forces holder to move last in priority bracket (Gen 4+)
    # Gen 4: If multiple Lagging Tail holders, slower goes first (ignores TR)
    # Gen 5+: If multiple Lagging Tail/Stall, order by Speed (respects TR)
    "lagging-tail": {
        "moves_last": True,
        "min_gen": 4,
        "unaffected_by_trick_room": True,
        "gen_specific": {
            "4": {
                "multiple_lagging_slower_first": True,  # Slower goes first if multiple
                "stall_moves_before_lagging": True  # Stall ability goes before Lagging Tail
            },
            "5+": {
                "multiple_lagging_by_speed": True,  # Order by Speed (respects TR)
                "stall_same_as_lagging": True  # Stall and Lagging Tail treated same
            }
        },
        "delayed_activation": True,  # Doesn't affect turn order until next turn if gained/lost
        "description": "Moves last in priority bracket. Gen 4: Slower first. Gen 5+: Speed order"
    },
    # Sticky Barb: Damages holder, transfers on contact (Gen 4+)
    # Damages 12.5% (1/8) max HP at end of turn
    # Transfers to attacker on contact (even with Knock Off)
    # Doesn't transfer to substitute
    "sticky-barb": {
        "damages_holder": 1 / 8,  # 12.5% max HP
        "can_transfer": True,
        "min_gen": 4,
        "transfers_on_contact": True,  # Even with Knock Off
        "negated_by_magic_guard": True,
        "sticky_hold_prevents_transfer": False,  # Transfers despite Sticky Hold
        "doesnt_transfer_to_substitute": True,
        "description": "Damages holder 1/8 HP, transfers on contact (even Knock Off). Gen 4+"
    },
    # Flame Orb: Burns holder at end of turn (Gen 4+)
    # Activates after damage from burn would be taken, so no damage the first turn
    # Activates after Hydration, Shed Skin cure status
    "flame-orb": {
        "burns_holder": True,
        "min_gen": 4,
        "activates_after_damage": True,  # No burn damage first turn
        "activates_after_cure": True,  # After Hydration/Shed Skin
        "description": "Burns holder at end of turn (no damage first turn). Gen 4+"
    },
    # Toxic Orb: Badly poisons holder at end of turn (Gen 4+)
    # Activates after damage from poison would be taken, so no damage first turn
    # Activates after Hydration, Shed Skin cure status
    # Can poison Poison-types with Corrosion
    "toxic-orb": {
        "badly_poisons_holder": True,
        "min_gen": 4,
        "activates_after_damage": True,  # No poison damage first turn
        "activates_after_cure": True,  # After Hydration/Shed Skin
        "corrosion_bypasses_poison_immunity": True,
        "description": "Badly poisons holder (no damage first turn). Gen 4+"
    },
    
    # Berserker Gene: +2 Attack but confuses holder on entry (Gen 2 only, buggy)
    # Gen 2: Confusion lasts 256 turns due to bug (underflow from 0)
    # Stadium 2: Confusion properly lasts 2-5 turns
    "berserker-gene": {
        "on_entry_boost": {"atk": 2},
        "confuses_holder": True,
        "one_time_use": True,
        "min_gen": 2,
        "max_gen": 2,
        "gen_specific": {
            "2": {"confusion_turns": 256}  # Bug: underflows to 256 turns
        },
        "description": "Raises Attack by 2 stages but confuses holder on entry (Gen 2 only, consumed)"
    },
    # Binding Band: Boosts binding/trapping move damage
    # Gen 5: 1/8 HP per turn (instead of 1/16)
    # Gen 6+: 1/6 HP per turn (instead of 1/8)
    "binding-band": {
        "boosts_binding_moves": True,
        "min_gen": 5,
        "gen_specific": {
            "5": {"binding_damage": 1 / 8},  # 1/8 instead of 1/16
            "6+": {"binding_damage": 1 / 6}  # 1/6 instead of 1/8
        },
        "description": "Gen 5: Binding moves deal 1/8 HP, Gen 6+: 1/6 HP per turn"
    },
    # Grip Claw: Makes binding moves last longer
    # Gen 4: 5 turns (instead of 2-5 random)
    # Gen 5+: 7 turns (instead of 4-5 random)
    "grip-claw": {
        "extends_binding_moves": True,
        "min_gen": 4,
        "gen_specific": {
            "4": {"binding_turns": 5},  # Always 5 turns
            "5+": {"binding_turns": 7}  # Always 7 turns
        },
        "description": "Gen 4: Binding moves last 5 turns. Gen 5+: 7 turns"
    },
    
    # ========== MEGA STONES (PLACEHOLDER) ==========
    "venusaurite": {"mega_stone": "venusaur"},
    "charizardite-x": {"mega_stone": "charizard", "form": "x"},
    "charizardite-y": {"mega_stone": "charizard", "form": "y"},
    "blastoisinite": {"mega_stone": "blastoise"},
    # ... (Add more mega stones as needed)
}


def normalize_item_name(name: str) -> str:
    """Normalize item name to lowercase with hyphens."""
    if not name:
        return ""
    return name.lower().replace(" ", "-").replace("_", "-").strip()


def get_item_effect(item_name: str) -> Dict[str, Any]:
    """Get item effect data by name."""
    normalized = normalize_item_name(item_name)
    return ITEM_EFFECTS.get(normalized, {})


def has_item_effect(item_name: str, effect_key: str) -> bool:
    """Check if an item has a specific effect."""
    item_data = get_item_effect(item_name)
    return effect_key in item_data


