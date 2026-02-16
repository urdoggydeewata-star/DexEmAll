"""
Z-Move System for Generation 7

Z-Moves are powered by Z-Crystals held by Pokemon and require a Z-Ring equipped by the trainer.
Each move type has a corresponding Z-Crystal that transforms it into a Z-Move.
"""

from typing import Dict, Optional, Tuple, Any, List, Set
import re

# Z-Crystal to move type mapping
# Format: crystal_name: [move_types]
Z_CRYSTAL_TYPES = {
    "normalium-z": ["Normal"],
    "firium-z": ["Fire"],
    "waterium-z": ["Water"],
    "electrium-z": ["Electric"],
    "grassium-z": ["Grass"],
    "icium-z": ["Ice"],
    "fightinium-z": ["Fighting"],
    "poisonium-z": ["Poison"],
    "groundium-z": ["Ground"],
    "flyinium-z": ["Flying"],
    "psychium-z": ["Psychic"],
    "buginium-z": ["Bug"],
    "rockium-z": ["Rock"],
    "ghostium-z": ["Ghost"],
    "dragonium-z": ["Dragon"],
    "darkinium-z": ["Dark"],
    "steelium-z": ["Steel"],
    "fairium-z": ["Fairy"],
}

# Signature Z-Moves (special cases with unique names, power, and category)
# Format: species_normalized: {base_move_normalized: {"name": Z-Move name, "power": power, "category": "physical/special/status", "type": type, "z_crystal": crystal name}}
SIGNATURE_Z_MOVES = {
    "pikachu": {
        "volt-tackle": {"name": "Catastropika", "power": 210, "category": "physical", "type": "Electric", "z_crystal": "pikanium-z"},
        "thunderbolt": {"name": "10,000,000 Volt Thunderbolt", "power": 195, "category": "special", "type": "Electric", "z_crystal": "pikashunium-z"}  # Pikachu in cap
    },
    "raichu-alola": {"thunderbolt": {"name": "Stoked Sparksurfer", "power": 175, "category": "special", "type": "Electric", "z_crystal": "aloraichium-z"}},
    "eevee": {"last-resort": {"name": "Extreme Evoboost", "power": None, "category": "status", "type": "Normal", "z_crystal": "eevium-z"}},
    "snorlax": {"giga-impact": {"name": "Pulverizing Pancake", "power": 210, "category": "physical", "type": "Normal", "z_crystal": "snorlium-z"}},
    "mew": {"psychic": {"name": "Genesis Supernova", "power": 185, "category": "special", "type": "Psychic", "z_crystal": "mewnium-z"}},
    "decidueye": {"spirit-shackle": {"name": "Sinister Arrow Raid", "power": 180, "category": "physical", "type": "Ghost", "z_crystal": "decidium-z"}},
    "incineroar": {"darkest-lariat": {"name": "Malicious Moonsault", "power": 180, "category": "physical", "type": "Dark", "z_crystal": "incinium-z"}},
    "primarina": {"sparkling-aria": {"name": "Oceanic Operetta", "power": 195, "category": "special", "type": "Water", "z_crystal": "primarium-z"}},
    "lycanroc": {"stone-edge": {"name": "Splintered Stormshards", "power": 190, "category": "physical", "type": "Rock", "z_crystal": "lycanium-z"}},
    "lycanroc-midnight": {"stone-edge": {"name": "Splintered Stormshards", "power": 190, "category": "physical", "type": "Rock", "z_crystal": "lycanium-z"}},
    "lycanroc-dusk": {"stone-edge": {"name": "Splintered Stormshards", "power": 190, "category": "physical", "type": "Rock", "z_crystal": "lycanium-z"}},
    "mimikyu": {"play-rough": {"name": "Let's Snuggle Forever", "power": 190, "category": "physical", "type": "Fairy", "z_crystal": "mimikium-z"}},
    "kommo-o": {"clanging-scales": {"name": "Clangorous Soulblaze", "power": 185, "category": "special", "type": "Dragon", "z_crystal": "kommonium-z"}},
    "tapukoko": {"natures-madness": {"name": "Guardian of Alola", "power": None, "category": "status", "type": "Fairy", "z_crystal": "tapunium-z"}},
    "tapulele": {"natures-madness": {"name": "Guardian of Alola", "power": None, "category": "status", "type": "Fairy", "z_crystal": "tapunium-z"}},
    "tapubulu": {"natures-madness": {"name": "Guardian of Alola", "power": None, "category": "status", "type": "Fairy", "z_crystal": "tapunium-z"}},
    "tapufini": {"natures-madness": {"name": "Guardian of Alola", "power": None, "category": "status", "type": "Fairy", "z_crystal": "tapunium-z"}},
    "necrozma-dusk": {"sunsteel-strike": {"name": "Searing Sunraze Smash", "power": 200, "category": "physical", "type": "Steel", "z_crystal": "solganium-z"}},
    "necrozma-dawn": {"moongeist-beam": {"name": "Menacing Moonraze Maelstrom", "power": 200, "category": "special", "type": "Ghost", "z_crystal": "lunalium-z"}},
    "necrozma-ultra": {"photongeyser": {"name": "Light That Burns the Sky", "power": 200, "category": "special", "type": "Psychic", "z_crystal": "ultranecrozium-z"}},
    "marshadow": {"spectral-thief": {"name": "Soul-Stealing 7-Star Strike", "power": 195, "category": "physical", "type": "Ghost", "z_crystal": "marshadium-z"}},
    "zeraora": {"plasma-fists": {"name": "Catastropika", "power": 210, "category": "physical", "type": "Electric", "z_crystal": "pikanium-z"}},  # Uses same Z-Crystal as Pikachu's Volt Tackle
}

# Generic Z-Move naming pattern
# Most Z-Moves follow the pattern: Base move type + "-Z"
GENERIC_Z_MOVE_NAMES = {
    "normal": "Breakneck Blitz",
    "fire": "Inferno Overdrive",
    "water": "Hydro Vortex",
    "electric": "Gigavolt Havoc",
    "grass": "Bloom Doom",
    "ice": "Subzero Slammer",
    "fighting": "All-Out Pummeling",
    "poison": "Acid Downpour",
    "ground": "Tectonic Rage",
    "flying": "Supersonic Skystrike",
    "psychic": "Shattered Psyche",
    "bug": "Savage Spin-Out",
    "rock": "Continental Crush",
    "ghost": "Never-Ending Nightmare",
    "dragon": "Devastating Drake",
    "dark": "Black Hole Eclipse",
    "steel": "Corkscrew Crash",
    "fairy": "Twinkle Tackle",
}

# Status move Z-Move effects
# Format: move_name: {stat_boost: {stat: amount}, special_effect: description}
STATUS_Z_MOVE_EFFECTS = {
    "stockpile": {"heal_full": True},  # Z-Stockpile: Restore all HP
    "swallow": {"reset_stats": True},  # Z-Swallow: Reset all lowered stats
    "torment": {"boost": {"defn": 1}},  # Z-Torment: +1 Defense
    "flatter": {"boost": {"spd": 1}},  # Z-Flatter: +1 Special Defense
    "will-o-wisp": {"boost": {"atk": 1}},  # Z-Will-O-Wisp: +1 Attack
    "memento": {"heal_replacement": True},  # Z-Memento: Heal replacement fully
    "mimic": {"boost": {"accuracy": 1}},  # Z-Mimic: +1 Accuracy
    "screech": {"boost": {"atk": 1}},  # Z-Screech: +1 Attack
    "double-team": {"reset_stats": True},  # Z-Double Team: Reset all lowered stats
    "recover": {"reset_stats": True},  # Z-Recover: Reset all lowered stats
    "harden": {"boost": {"defn": 1}},  # Z-Harden: +1 Defense
    "minimize": {"reset_stats": True},  # Z-Minimize: Reset all lowered stats
    "smokescreen": {"boost": {"evasion": 1}},  # Z-Smokescreen: +1 Evasion
    "confuse-ray": {"boost": {"spa": 1}},  # Z-Confuse Ray: +1 Special Attack
    "withdraw": {"boost": {"defn": 1}},  # Z-Withdraw: +1 Defense
    "defense-curl": {"boost": {"accuracy": 1}},  # Z-Defense Curl: +1 Accuracy
    "barrier": {"reset_stats": True},  # Z-Barrier: Reset all lowered stats
    "light-screen": {"boost": {"spd": 1}},  # Z-Light Screen: +1 Special Defense
    "haze": {"heal_full": True},  # Z-Haze: Restore all HP
    "reflect": {"boost": {"defn": 1}},  # Z-Reflect: +1 Defense
    "focus-energy": {"boost": {"accuracy": 1}},  # Z-Focus Energy: +1 Accuracy
    "mirror-move": {"boost": {"atk": 2}, "copied_move_becomes_z_move": True},  # Z-Mirror Move: +2 Attack, copied move becomes Z-Move
    "amnesia": {"reset_stats": True},  # Z-Amnesia: Reset all lowered stats
    "kinesis": {"boost": {"evasion": 1}},  # Z-Kinesis: +1 Evasion
    "soft-boiled": {"reset_stats": True},  # Z-Soft-Boiled: Reset all lowered stats
    "glare": {"boost": {"spd": 1}},  # Z-Glare: +1 Special Defense
    "poison-gas": {"boost": {"defn": 1}},  # Z-Poison Gas: +1 Defense
    "spore": {"reset_stats": True},  # Z-Spore: Reset all lowered stats
    "flash": {"boost": {"evasion": 1}},  # Z-Flash: +1 Evasion
    "transform": {"heal_full": True},  # Z-Transform: Restore all HP
    "rest": {"reset_stats": True},  # Z-Rest: Reset all lowered stats
    "sharpen": {"boost": {"atk": 1}},  # Z-Sharpen: +1 Attack
    "conversion": {"boost": {"atk": 1, "defn": 1, "spa": 1, "spd": 1, "spe": 1}},  # Z-Conversion: +1 to all stats
    "substitute": {"reset_stats": True},  # Z-Substitute: Reset all lowered stats
    "sketch": {"boost": {"atk": 1, "defn": 1, "spa": 1, "spd": 1, "spe": 1}},  # Z-Sketch: +1 to all stats
    "celebrate": {"boost": {"atk": 1, "defn": 1, "spa": 1, "spd": 1, "spe": 1}},  # Z-Celebrate: +1 to all stats
    "spider-web": {"boost": {"defn": 1}},  # Z-Spider Web: +1 Defense
    "mind-reader": {"boost": {"spa": 1}},  # Z-Mind Reader: +1 Special Attack
    "nightmare": {"boost": {"spa": 1}},  # Z-Nightmare: +1 Special Attack
    # Z-Curse handled in apply_move: Ghost = heal full, non-Ghost = +1 Attack
    "conversion-2": {"heal_full": True},  # Z-Conversion 2: Restore all HP
    "cotton-spore": {"reset_stats": True},  # Z-Cotton Spore: Reset all lowered stats
    "spite": {"heal_full": True},  # Z-Spite: Restore all HP
    "protect": {"reset_stats": True},  # Z-Protect: Reset all lowered stats
    "scary-face": {"boost": {"spe": 1}},  # Z-Scary Face: +1 Speed
    "belly-drum": {"heal_full": True},  # Z-Belly Drum: Restore all HP before HP deduction
    "spikes": {"boost": {"defn": 1}},  # Z-Spikes: +1 Defense
    "sweet-kiss": {"boost": {"spa": 1}},  # Z-Sweet Kiss: +1 Special Attack
    "detect": {"boost": {"evasion": 1}},  # Z-Detect: +1 Evasion
    "lock-on": {"boost": {"spe": 1}},  # Z-Lock-On: +1 Speed
    "foresight": {"boost": {"crit": 2}},  # Z-Foresight: +2 critical hit ratio
    "icy-wind": {"boost": {"spe": 1}},  # Z-Icy Wind: +1 Speed (if status move)
    "sandstorm": {"boost": {"spe": 1}},  # Z-Sandstorm: +1 Speed
    "endure": {"reset_stats": True},  # Z-Endure: Reset all lowered stats
    "charm": {"boost": {"defn": 1}},  # Z-Charm: +1 Defense
    "swagger": {"reset_stats": True},  # Z-Swagger: Reset all lowered stats
    "milk-drink": {"reset_stats": True},  # Z-Milk Drink: Reset all lowered stats
    "mean-look": {"boost": {"spd": 1}},  # Z-Mean Look: +1 Special Defense
    "attract": {"reset_stats": True},  # Z-Attract: Reset all lowered stats
    "sleep-talk": {"boost": {"crit": 2}},  # Z-Sleep Talk: +2 critical hit ratio (also makes copied move Z-Move)
    "heal-bell": {"heal_full": True},  # Z-Heal Bell: Restore all HP
    "safeguard": {"boost": {"spe": 1}},  # Z-Safeguard: +1 Speed
    "pain-split": {"boost": {"defn": 1}},  # Z-Pain Split: +1 Defense
    "baton-pass": {"reset_stats": True},  # Z-Baton Pass: Reset all lowered stats
    "encore": {"boost": {"spe": 1}},  # Z-Encore: +1 Speed
    "sweet-scent": {"boost": {"accuracy": 1}},  # Z-Sweet Scent: +1 Accuracy
    "morning-sun": {"reset_stats": True},  # Z-Morning Sun: Reset all lowered stats
    "psych-up": {"heal_full": True},  # Z-Psych Up: Restore all HP
    "synthesis": {"reset_stats": True},  # Z-Synthesis: Reset all lowered stats
    "moonlight": {"reset_stats": True},  # Z-Moonlight: Reset all lowered stats
    "hail": {"boost": {"spe": 1}},  # Z-Hail: +1 Speed
    "torment": {"boost": {"defn": 1}},  # Z-Torment: +1 Defense
    "flatter": {"boost": {"spd": 1}},  # Z-Flatter: +1 Special Defense
    "will-o-wisp": {"boost": {"atk": 1}},  # Z-Will-O-Wisp: +1 Attack
    "swallow": {"reset_stats": True},  # Z-Swallow: Reset all lowered stats
    "stockpile": {"heal_full": True},  # Z-Stockpile: Restore all HP
    "follow-me": {"reset_stats": True},  # Z-Follow Me: Reset all lowered stats
    "charge": {"boost": {"spd": 1}},  # Z-Charge: +1 Special Defense
    "taunt": {"boost": {"atk": 1}},  # Z-Taunt: +1 Attack
    "helping-hand": {"reset_stats": True},  # Z-Helping Hand: Reset all lowered stats
    "trick": {"boost": {"spe": 2}},  # Z-Trick: +2 Speed (but move fails)
    "role-play": {"boost": {"spe": 1}},  # Z-Role Play: +1 Speed
    "wish": {"boost": {"spd": 1}},  # Z-Wish: +1 Special Defense
    "assist": {"special": "z_assist"},  # Z-Assist: Makes called move a Z-Move if damaging
    "ingrain": {"boost": {"spd": 1}},  # Z-Ingrain: +1 Special Defense
    "magic-coat": {"boost": {"spd": 2}},  # Z-Magic Coat: +2 Special Defense
    "recycle": {"boost": {"spe": 2}},  # Z-Recycle: +2 Speed (but move fails)
    "yawn": {"boost": {"spe": 1}},  # Z-Yawn: +1 Speed
    "skill-swap": {"boost": {"spe": 1}},  # Z-Skill Swap: +1 Speed
    "imprison": {"boost": {"spd": 2}},  # Z-Imprison: +2 Special Defense
    "refresh": {"heal_full": True},  # Z-Refresh: Restore all HP
    "grudge": {"special": "z_grudge"},  # Z-Grudge: Center of attention
    "snatch": {"boost": {"spe": 2}},  # Z-Snatch: +2 Speed
    "tail-glow": {"reset_stats": True},  # Z-Tail Glow: Reset all lowered stats
    "feather-dance": {"boost": {"defn": 1}},  # Z-Feather Dance: +1 Defense
    "teeter-dance": {"boost": {"spa": 1}},  # Z-Teeter Dance: +1 Special Attack
    "mud-sport": {"boost": {"spd": 1}},  # Z-Mud Sport: +1 Special Defense
    "sand-attack": {"boost": {"evasion": 1}},  # Z-Sand Attack: +1 Evasiveness
    "tail-whip": {"boost": {"atk": 1}},  # Z-Tail Whip: +1 Attack
    "leer": {"boost": {"atk": 1}},  # Z-Leer: +1 Attack
    "growl": {"boost": {"defn": 1}},  # Z-Growl: +1 Defense
    "roar": {"boost": {"defn": 1}},  # Z-Roar: +1 Defense
    "sing": {"boost": {"spe": 1}},  # Z-Sing: +1 Speed
    "supersonic": {"boost": {"spe": 1}},  # Z-Supersonic: +1 Speed
    "disable": {"reset_stats": True},  # Z-Disable: Reset all lowered stats
    "mist": {"heal_full": True},  # Z-Mist: Restore all HP
    "leech-seed": {"reset_stats": True},  # Z-Leech Seed: Reset all lowered stats
    "growth": {"boost": {"spa": 1}},  # Z-Growth: +1 Special Attack
    "poison-powder": {"boost": {"defn": 1}},  # Z-Poison Powder: +1 Defense
    "stun-spore": {"boost": {"spd": 1}},  # Z-Stun Spore: +1 Special Defense
    "sleep-powder": {"boost": {"spe": 1}},  # Z-Sleep Powder: +1 Speed
    "string-shot": {"boost": {"spe": 1}},  # Z-String Shot: +1 Speed
    "toxic": {"boost": {"defn": 1}},  # Z-Toxic: +1 Defense
    "hypnosis": {"boost": {"spe": 1}},  # Z-Hypnosis: +1 Speed
    "meditate": {"boost": {"atk": 1}},  # Z-Meditate: +1 Attack
    "agility": {"reset_stats": True},  # Z-Agility: Reset all lowered stats
    "electric-terrain": {"boost": {"spe": 1}},  # Z-Electric Terrain: +1 Speed
    "grassy-terrain": {"boost": {"defn": 1}},  # Z-Grassy Terrain: +1 Defense
    "misty-terrain": {"boost": {"spd": 1}},  # Z-Misty Terrain: +1 Special Defense
    "psychic-terrain": {"boost": {"spa": 1}},  # Z-Psychic Terrain: +1 Special Attack
}


def normalize_crystal_name(item_name: str) -> str:
    """Normalize Z-Crystal item name to standard format."""
    if not item_name:
        return ""
    normalized = item_name.lower().strip().replace(" ", "-").replace("_", "-")
    # Remove -held, --held, -bag, or --bag suffix if present
    normalized = normalized.replace("--held", "").replace("-held", "")
    normalized = normalized.replace("--bag", "").replace("-bag", "")
    return normalized


def _normalize_species_name(name: str) -> str:
    if not name:
        return ""
    normalized = name.lower().strip()
    normalized = normalized.replace("é", "e")
    normalized = normalized.replace(" ", "-").replace("_", "-")
    normalized = re.sub(r"[^a-z0-9\-]", "-", normalized)
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    return normalized.strip("-")


def _normalize_move_name(name: str) -> str:
    if not name:
        return ""
    normalized = name.lower().strip()
    normalized = normalized.replace("é", "e")
    normalized = normalized.replace(" ", "-").replace("_", "-")
    normalized = normalized.replace("'", "").replace(".", "").replace(",", "")
    normalized = re.sub(r"[^a-z0-9\-]", "-", normalized)
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    return normalized.strip("-")


def _species_variants_for_pokemon(pokemon: Any) -> Set[str]:
    variants: Set[str] = set()
    species_attr = getattr(pokemon, "species", "") or ""
    form_attr = getattr(pokemon, "form", "") or ""
    if species_attr:
        variants.add(_normalize_species_name(species_attr))
    if form_attr:
        variants.add(_normalize_species_name(form_attr))
        if species_attr:
            variants.add(_normalize_species_name(f"{species_attr}-{form_attr}"))
    return variants


SIGNATURE_CRYSTAL_REQUIREMENTS: Dict[str, List[Tuple[str, str]]] = {}
for species_key, moves_map in SIGNATURE_Z_MOVES.items():
    normalized_species = _normalize_species_name(species_key)
    for base_move_key, sig_data in moves_map.items():
        if isinstance(sig_data, dict):
            z_crystal_name = normalize_crystal_name(sig_data.get("z_crystal", ""))
        else:
            z_crystal_name = ""
        if z_crystal_name:
            SIGNATURE_CRYSTAL_REQUIREMENTS.setdefault(z_crystal_name, []).append(
                (normalized_species, _normalize_move_name(base_move_key))
            )


def is_z_crystal(item_name: str) -> bool:
    """Check if an item is a Z-Crystal."""
    if not item_name:
        return False
    normalized = normalize_crystal_name(item_name)
    # Check if it ends with -z or matches known crystals
    return normalized.endswith("-z") or normalized in Z_CRYSTAL_TYPES


def get_z_crystal_type(item_name: str) -> Optional[str]:
    """Get the move type that a Z-Crystal corresponds to."""
    if not item_name:
        return None
    normalized = normalize_crystal_name(item_name)
    
    # Direct lookup
    for crystal, types in Z_CRYSTAL_TYPES.items():
        if normalized == crystal:
            return types[0]  # Return first type (most crystals are single-type)
    
    # Pattern matching: extract type from name (e.g., "firium-z" -> "Fire")
    if normalized.endswith("-z"):
        base = normalized[:-2]  # Remove "-z"
        # Try to extract type from crystal name
        for crystal, types in Z_CRYSTAL_TYPES.items():
            if crystal.replace("-z", "").replace("ium", "") in base or base.replace("ium", "") in crystal.replace("-z", ""):
                return types[0]
    
    return None


def get_z_move_name(base_move_name: str, pokemon_species: str, move_type: str, z_crystal: Optional[str] = None) -> str:
    """
    Get the Z-Move name for a given base move.
    
    Args:
        base_move_name: The original move name (e.g., "Fire Blast")
        pokemon_species: The Pokemon species using the move
        move_type: The type of the move
        z_crystal: Optional Z-Crystal name for verification
    
    Returns:
        The Z-Move name (e.g., "Inferno Overdrive")
    """
    base_normalized = base_move_name.lower().replace(" ", "-").strip()
    species_normalized = pokemon_species.lower().replace(" ", "-").strip()
    move_type_lower = move_type.lower() if move_type else ""
    
    # Check for signature Z-Moves first
    if species_normalized in SIGNATURE_Z_MOVES:
        species_z_moves = SIGNATURE_Z_MOVES[species_normalized]
        
        # Try exact match first
        if base_normalized in species_z_moves:
            sig_data = species_z_moves[base_normalized]
            # Handle both old format (string) and new format (dict)
            if isinstance(sig_data, dict):
                return sig_data.get("name", base_move_name)
            else:
                return sig_data  # Old format (just string)
        
        # Try database lookup FIRST to get canonical name (handles typos better)
        from .moves_loader import get_move
        move_data_db = get_move(base_move_name)
        if move_data_db:
            # Get canonical move name from DB
            canonical_name = move_data_db.get("name", "").lower().replace(" ", "-").strip()
            if canonical_name and canonical_name in species_z_moves:
                sig_data = species_z_moves[canonical_name]
                if isinstance(sig_data, dict):
                    return sig_data.get("name", base_move_name)
                else:
                    return sig_data
        
        # Try fuzzy match for typos/variations (e.g., "spectrial-thief" -> "spectral-thief")
        # Check if any key in species_z_moves is similar to base_normalized
        for key in species_z_moves.keys():
            # Check if keys are very similar (typo detection)
            # Allow same length or length difference of 1
            len_diff = abs(len(base_normalized) - len(key))
            if len_diff <= 1:
                if len(base_normalized) == len(key):
                    # Count character differences
                    diff = sum(1 for a, b in zip(base_normalized, key) if a != b)
                    # If only 1-3 character differences, likely a typo
                    if diff <= 3 and diff > 0:
                        sig_data = species_z_moves[key]
                        if isinstance(sig_data, dict):
                            return sig_data.get("name", base_move_name)
                        else:
                            return sig_data
                else:
                    # One is longer by 1 - check if shorter is substring of longer
                    shorter = base_normalized if len(base_normalized) < len(key) else key
                    longer = key if len(base_normalized) < len(key) else base_normalized
                    # Check if all characters of shorter appear in longer in order
                    shorter_idx = 0
                    for char in longer:
                        if shorter_idx < len(shorter) and char == shorter[shorter_idx]:
                            shorter_idx += 1
                    # If we matched all characters, it's likely the same move
                    if shorter_idx == len(shorter):
                        sig_data = species_z_moves[key]
                        if isinstance(sig_data, dict):
                            return sig_data.get("name", base_move_name)
                        else:
                            return sig_data
    
    # For status moves, Z-Move name is "Z-" + move name
    from .moves_loader import get_move
    move_data = get_move(base_move_name)
    if move_data and move_data.get("category") == "status":
        return f"Z-{base_move_name.replace('-', ' ').title()}"
    
    # For damaging moves, use generic type-based Z-Move name
    return GENERIC_Z_MOVE_NAMES.get(move_type_lower, f"{move_type} Z-Move")


def can_use_z_move(user_id: int, pokemon: Any, move_name: str, battle_gen: int) -> Tuple[bool, Optional[str]]:
    """
    Check if a Z-Move can be used.
    
    Returns:
        (can_use, reason_if_no)
    """
    # Only available in Gen 7
    if battle_gen != 7:
        return False, "Z-Moves are only available in Generation 7"
    
    # Need to check Z-Ring equipment (requires database access)
    # This will be done in panel.py with async database call
    
    # Check if Pokemon has a Z-Crystal
    if not pokemon.item:
        return False, "Pokemon needs to hold a Z-Crystal"
    
    pokemon_item_normalized = normalize_crystal_name(pokemon.item)
    if not is_z_crystal(pokemon_item_normalized):
        return False, "Pokemon needs to hold a Z-Crystal"
    
    from .moves_loader import get_move
    move_data = get_move(move_name)
    if not move_data:
        return False, "Invalid move"
    
    move_type = move_data.get("type", "Normal")
    move_norm = _normalize_move_name(move_name)
    canonical_move_norm = _normalize_move_name(move_data.get("name", ""))
    species_variants = _species_variants_for_pokemon(pokemon)

    signature_candidates = SIGNATURE_CRYSTAL_REQUIREMENTS.get(pokemon_item_normalized, [])
    if signature_candidates:
        for species_key, base_move_key in signature_candidates:
            if species_key not in species_variants:
                continue
            if move_norm == base_move_key or (canonical_move_norm and canonical_move_norm == base_move_key):
                return True, None
        return False, "This Z-Crystal can only be used with a specific move."

    move_type = move_data.get("type", "Normal")
    crystal_type = get_z_crystal_type(pokemon_item_normalized)
    
    if crystal_type is None:
        return False, "This Z-Crystal isn't compatible with that move."
    
    if move_type != crystal_type:
        return False, f"Move type ({move_type}) doesn't match Z-Crystal type ({crystal_type})"
    
    return True, None


def get_z_move_power(base_move: Dict[str, Any], base_move_name: str = None, pokemon_species: str = None) -> int:
    """
    Calculate Z-Move power based on base move using the official conversion table.
    
    Power conversion table:
    - 0-55: 100
    - 60-65: 120
    - 70-75: 140
    - 80-85: 160
    - 90-95: 175
    - 100: 180
    - 110: 185
    - 120-125: 190
    - 130: 195
    - 140+: 200
    
    Special exceptions:
    - Mega Drain: 120
    - Weather Ball: 160
    - Hex: 160
    - V-create: 220
    - Flying Press: 170
    - Core Enforcer: 140
    - OHKO moves: 180
    - Struggle: 1 (but can't be used as Z-Move)
    """
    base_power = base_move.get("power", 0) or 0
    move_category = base_move.get("category", "physical")
    move_name_normalized = None
    species_normalized = None
    
    if base_move_name:
        move_name_normalized = base_move_name.lower().replace(" ", "-").strip()
    elif "name" in base_move:
        move_name_normalized = base_move["name"].lower().replace(" ", "-").strip()
    
    if pokemon_species:
        species_normalized = pokemon_species.lower().replace(" ", "-").strip()
    
    # === SIGNATURE Z-MOVES: Check for fixed power (checked FIRST, before standard conversion) ===
    # Signature Z-Moves have fixed power values that override the standard conversion table
    if species_normalized and move_name_normalized:
        if species_normalized in SIGNATURE_Z_MOVES:
            species_z_moves = SIGNATURE_Z_MOVES[species_normalized]
            
            # Try exact match first
            if move_name_normalized in species_z_moves:
                sig_data = species_z_moves[move_name_normalized]
                if isinstance(sig_data, dict) and sig_data.get("power") is not None:
                    return sig_data["power"]
                # Old format or no power specified, continue to normal calculation
            
            # Try fuzzy match for typos/variations (e.g., "spectrial-thief" -> "spectral-thief")
            for key in species_z_moves.keys():
                # Check if keys are very similar (typo detection)
                if len(move_name_normalized) == len(key):
                    # Count differences
                    diff = sum(1 for a, b in zip(move_name_normalized, key) if a != b)
                    # If only 1-2 character differences, likely a typo
                    if diff <= 2 and diff > 0:
                        sig_data = species_z_moves[key]
                        if isinstance(sig_data, dict) and sig_data.get("power") is not None:
                            return sig_data["power"]
            
            # Also check with move database lookup for move name variations
            from .moves_loader import get_move
            move_data_db = get_move(base_move_name) if base_move_name else None
            if move_data_db:
                # Get canonical move name from DB
                canonical_name = move_data_db.get("name", "").lower().replace(" ", "-").strip()
                if canonical_name and canonical_name in species_z_moves:
                    sig_data = species_z_moves[canonical_name]
                    if isinstance(sig_data, dict) and sig_data.get("power") is not None:
                        return sig_data["power"]
    
    if move_category == "status":
        # Status Z-Moves have fixed power based on type
        move_type = base_move.get("type", "Normal").lower()
        status_z_powers = {
            "normal": 100,
            "fire": 100,
            "water": 100,
            "electric": 100,
            "grass": 100,
            "ice": 100,
            "fighting": 100,
            "poison": 100,
            "ground": 100,
            "flying": 100,
            "psychic": 100,
            "bug": 100,
            "rock": 100,
            "ghost": 100,
            "dragon": 100,
            "dark": 100,
            "steel": 100,
            "fairy": 100,
        }
        return status_z_powers.get(move_type, 100)
    
    # Special exceptions (these override the table)
    if move_name_normalized:
        special_powers = {
            "mega-drain": 120,
            "weather-ball": 160,
            "hex": 160,
            "v-create": 220,
            "flying-press": 170,
            "core-enforcer": 140,
            "fissure": 180,  # OHKO moves
            "horn-drill": 180,
            "guillotine": 180,
            "sheer-cold": 180,
            "struggle": 1,  # Can't actually be used, but for completeness
        }
        if move_name_normalized in special_powers:
            return special_powers[move_name_normalized]
    
    # OHKO moves (check by power = 0 or special flag)
    # If base move is an OHKO move (no power specified or special mechanics)
    # For now, we'll check if power is 0 and it's not a status move
    if base_power == 0 and move_category != "status":
        # Check if it's an OHKO move by name
        ohko_moves = ["fissure", "horn-drill", "guillotine", "sheer-cold"]
        if move_name_normalized and move_name_normalized in ohko_moves:
            return 180
    
    # Standard conversion table for damaging moves
    if base_power <= 0:
        return 100  # Struggle-like moves
    
    # Continuous ranges (no gaps)
    if base_power <= 55:
        return 100
    elif base_power <= 65:  # 56-65
        return 120
    elif base_power <= 75:  # 66-75
        return 140
    elif base_power <= 85:  # 76-85
        return 160
    elif base_power <= 95:  # 86-95
        return 175
    elif base_power <= 99:  # 96-99
        return 175
    elif base_power == 100:
        return 180
    elif base_power <= 109:  # 101-109
        return 180
    elif base_power == 110:
        return 185
    elif base_power <= 119:  # 111-119
        return 185
    elif base_power <= 125:  # 120-125
        return 190
    elif base_power <= 129:  # 126-129
        return 190
    elif base_power == 130:
        return 195
    elif base_power <= 139:  # 131-139
        return 195
    else:  # 140+
        return 200


def get_z_move_effect(base_move_name: str) -> Optional[Dict[str, Any]]:
    """
    Get special Z-Move effect for status moves.
    
    Returns:
        Effect dict with stat boosts, healing, etc. or None
    """
    base_normalized = base_move_name.lower().replace(" ", "-").strip()
    return STATUS_Z_MOVE_EFFECTS.get(base_normalized)


