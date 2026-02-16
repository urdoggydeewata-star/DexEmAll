"""Team import functionality for Showdown format and preset teams."""
from __future__ import annotations

import re
import json
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass


@dataclass
class ParsedPokemon:
    """Represents a parsed Pokémon from Showdown format."""
    species: str
    nickname: Optional[str] = None
    item: Optional[str] = None
    ability: Optional[str] = None
    level: int = 100
    shiny: bool = False
    gender: Optional[str] = None
    nature: Optional[str] = None
    tera_type: Optional[str] = None
    evs: Dict[str, int] = None
    ivs: Dict[str, int] = None
    moves: List[str] = None
    form: Optional[str] = None
    friendship: Optional[int] = None
    
    def __post_init__(self):
        if self.evs is None:
            self.evs = {"hp": 0, "attack": 0, "defense": 0, "special_attack": 0, "special_defense": 0, "speed": 0}
        if self.ivs is None:
            self.ivs = {"hp": 31, "attack": 31, "defense": 31, "special_attack": 31, "special_defense": 31, "speed": 31}
        if self.moves is None:
            self.moves = []


def parse_showdown_team(team_text: str) -> List[ParsedPokemon]:
    """
    Parse a Pokémon Showdown team export format.
    
    Format example:
    Pikachu @ Light Ball
    Ability: Static
    Level: 50
    EVs: 252 Atk / 4 SpD / 252 Spe
    Adamant Nature
    - Thunderbolt
    - Quick Attack
    - Iron Tail
    - Volt Tackle
    """
    pokemon_list = []
    
    # Normalize line endings: convert \r\n (Windows) and \r (Mac) to \n (Unix)
    team_text = team_text.replace('\r\n', '\n').replace('\r', '\n')
    
    # If the text has no newlines at all (single line), we need to split it intelligently
    if '\n' not in team_text.strip():
        # Single line format - split by detecting Pokemon boundaries
        # Pattern: Look for species names (capitalized) followed by @ item or ability: pattern
        # Must be at word boundary, and followed by either @ or a keyword like Ability:
        # Use negative lookahead to avoid matching mid-word
        # Split by: word boundary + capitalized word + (optional @ item) + multiple spaces + (capitalized word + @ or Ability:)
        team_text = re.sub(
            r'([A-Z][a-zA-Z\-\']+(?:\s+\([^)]+\))?(?:\s+@\s+[A-Za-z\-\'\s]+)?)\s{3,}(?=[A-Z][a-zA-Z\-\']+(?:\s+\([^)]+\))?(?:\s+@\s+[A-Za-z\-\'\s]+|(?:\s+Ability:)))',
            r'\1\n\n',
            team_text
        )
    else:
        # Multi-line format - normalize spaces to newlines where appropriate
        # Convert 3+ spaces before keywords to newlines
        team_text = re.sub(r'(\S)\s{3,}(?=(?:Ability|Level|EVs?|IVs?|Shiny|Gender|Tera Type|Tera):)', r'\1\n', team_text)
        # Handle Nature lines: "Nature" followed by 3+ spaces
        team_text = re.sub(r'(Nature)\s{3,}', r'\1\n', team_text)
        # Handle move lines: 3+ spaces before " - " or just " -"
        team_text = re.sub(r'\s{3,}(-\s*)', r'\n\1', team_text)
        # Handle Pokemon boundaries: species @ item followed by 3+ spaces and another species
        team_text = re.sub(r'([A-Z][a-zA-Z\-\']+(?:\s+\([^)]+\))?(?:\s+@\s+[^\s]+)?)\s{3,}(?=[A-Z][a-zA-Z\-\']+(?:\s+\([^)]+\))?\s+@)', r'\1\n\n', team_text)
        # Handle move ending followed by new species
        team_text = re.sub(r'(-\s+[A-Z][A-Za-z\s\-]+(?:\[[^\]]+\])?)\s{3,}(?=[A-Z][a-zA-Z\-\']+(?:\s+\([^)]+\))?\s+@)', r'\1\n\n', team_text)
        # Additional fallback: 4+ spaces before species name
        team_text = re.sub(r'\s{4,}(?=[A-Z][a-zA-Z\-\']+\s+@)', r'\n\n', team_text)
    
    # Split by double newlines (standard Showdown format)
    blocks = re.split(r'\n\n+', team_text.strip())
    
    # If we still only have one block, try to split by detecting Pokemon boundaries
    if len(blocks) == 1 and blocks[0]:
        # Try splitting by detecting new Pokemon entries
        lines = team_text.strip().split('\n')
        blocks = []
        current_block = []
        
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                if current_block:  # Empty line between Pokemon
                    blocks.append('\n'.join(current_block))
                    current_block = []
                continue
            
            # Detect if this line starts a new Pokémon entry:
            # - Doesn't start with '-' (moves)
            # - Doesn't start with common keywords followed by ':' (Ability:, Level:, EVs:, etc.)
            # - First character is a letter (likely species name)
            # - Not a Nature line (ends with "Nature")
            # - Contains @ (item indicator) or is just a species name
            is_new_pokemon = (
                not line_stripped.startswith('-') and
                not re.match(r'^(Ability|Level|EVs?|IVs?|Shiny|Gender|Tera Type|Tera):', line_stripped, re.IGNORECASE) and
                not re.match(r'^.+ Nature$', line_stripped, re.IGNORECASE) and
                len(line_stripped) > 0 and
                line_stripped[0].isalpha() and
                ('@' in line_stripped or re.match(r'^[A-Z][a-zA-Z\-\']+$', line_stripped.split()[0]))
            )
            
            # If this looks like a new Pokémon and we have a current block, save it
            if is_new_pokemon and current_block:
                blocks.append('\n'.join(current_block))
                current_block = []
            
            current_block.append(line)
        
        # Add the last block
        if current_block:
            blocks.append('\n'.join(current_block))
    
    for block in blocks:
        if not block.strip():
            continue
        
        # Handle single-line Pokemon blocks (everything on one line)
        block_text = block.strip()
        if '\n' not in block_text:
            # Single line - try to split by detecting patterns
            # Split by 2+ spaces before keywords
            block_text = re.sub(r'\s{2,}(?=(?:Ability|Level|EVs?|IVs?|Shiny|Gender|Tera Type|Tera):)', r'\n', block_text)
            # Split before Nature
            block_text = re.sub(r'\s{2,}(?=[A-Z][a-z]+\s+Nature)', r'\n', block_text)
            # Split before moves (lines starting with -)
            block_text = re.sub(r'\s{2,}(?=-\s+)', r'\n', block_text)
            # Also handle moves without dashes (if they appear after Nature or other fields)
            # This is a fallback for edge cases
            
        lines = [line.strip() for line in block_text.split('\n') if line.strip()]
        if not lines:
            continue
        
        pokemon = ParsedPokemon(species="")
        
        # First line: Species @ Item or Species (Nickname) @ Item
        first_line = lines[0]
        
        # Extract nickname if present: Species (Nickname) or just Species
        nickname_match = re.match(r'^(.+?)\s*\((.+?)\)', first_line)
        if nickname_match:
            pokemon.nickname = nickname_match.group(2)
            species_part = nickname_match.group(1).strip()
        else:
            species_part = first_line
        
        # Extract item: @ Item
        item_match = re.search(r'@\s*(.+)', species_part)
        if item_match:
            pokemon.item = item_match.group(1).strip()
            species_part = species_part[:item_match.start()].strip()
        
        # Extract species (handle forms and mega evolutions)
        species_part = species_part.strip()
        pokemon.species = species_part
        
        # Species with hyphens in their actual names (not forms)
        HYPHENATED_SPECIES = {
            'ho-oh', 'porygon-z', 'jangmo-o', 'hakamo-o', 'kommo-o',
            'type-null', 'tapu-koko', 'tapu-lele', 'tapu-bulu', 'tapu-fini',
            'nidoran-f', 'nidoran-m', 'mr-mime', 'mime-jr', 'mr-rime',
            'chi-yu', 'chien-pao', 'wo-chien', 'ting-lu', 'great-tusk',
            'scream-tail', 'brute-bonnet', 'flutter-mane', 'slither-wing',
            'sandy-shocks', 'iron-treads', 'iron-bundle', 'iron-hands',
            'iron-jugulis', 'iron-moth', 'iron-thorns', 'roaring-moon',
            'iron-valiant', 'walking-wake', 'iron-leaves', 'gouging-fire',
            'raging-bolt', 'iron-boulder', 'iron-crown', 'ting-lu'
        }
        
        # Check for mega form first (e.g., "Charizard-Mega-X" -> species="Charizard", form=None)
        # Mega forms should NOT be imported as forms - they're battle-only transformations
        mega_match = re.match(r'^(.+?)-Mega(?:-(.+))?$', species_part, re.IGNORECASE)
        if mega_match:
            # Convert mega form to base form
            pokemon.species = mega_match.group(1)
            pokemon.form = None  # Mega forms are not stored as forms
            # Note: The item should already be extracted above (e.g., "Charizardite X")
            # If no item was specified, we keep it as None (user can set it manually)
        # Check if this is a species with hyphen in the actual name
        elif species_part.lower() in HYPHENATED_SPECIES:
            # Don't split - this is the actual species name
            pokemon.species = species_part
            pokemon.form = None
        else:
            # Check for regular form in species name (e.g., "Raichu-Alola" -> species="Raichu", form="alola")
            form_match = re.match(r'^(.+?)-(.+)$', species_part)
            if form_match:
                pokemon.species = form_match.group(1)
                pokemon.form = form_match.group(2).lower()
        
        # Parse remaining lines
        for line in lines[1:]:
            line_lower = line.lower()
            
            # Ability (handle "Ability:" with optional space)
            if line_lower.startswith('ability:'):
                ability_text = line.split(':', 1)[1].strip()
                # Handle cases like "Ability:Slow Start" (no space after colon)
                pokemon.ability = ability_text
            
            # Level
            elif line_lower.startswith('level:'):
                try:
                    pokemon.level = int(line.split(':', 1)[1].strip())
                except ValueError:
                    pass
            
            # EVs
            elif line_lower.startswith('evs:') or line_lower.startswith('ev:'):
                ev_text = line.split(':', 1)[1].strip()
                pokemon.evs = parse_evs_ivs(ev_text)
            
            # IVs
            elif line_lower.startswith('ivs:') or line_lower.startswith('iv:'):
                iv_text = line.split(':', 1)[1].strip()
                # Parse IVs - only update stats that were actually specified in the text
                parsed_ivs = parse_evs_ivs(iv_text)
                # Check which stats were actually mentioned in the original text
                iv_text_lower = iv_text.lower()
                stat_abbrevs = {
                    'hp': ['hp'],
                    'attack': ['atk', 'attack'],
                    'defense': ['def', 'defense', 'defn'],
                    'special_attack': ['spa', 'spatk', 'special attack', 'special-attack'],
                    'special_defense': ['spd', 'spdef', 'special defense', 'special-defense'],
                    'speed': ['spe', 'speed']
                }
                # Only update stats that were actually mentioned in the text
                for stat_key, abbrevs in stat_abbrevs.items():
                    if any(abbrev in iv_text_lower for abbrev in abbrevs):
                        pokemon.ivs[stat_key] = parsed_ivs[stat_key]
            
            # Nature
            elif 'nature' in line_lower:
                # Extract nature name (usually before "Nature")
                nature_match = re.match(r'^(.+?)\s+Nature', line, re.IGNORECASE)
                if nature_match:
                    pokemon.nature = nature_match.group(1).strip().lower()
            
            # Tera Type (handle "Tera Type:" with optional space)
            elif line_lower.startswith('tera type:') or line_lower.startswith('tera:'):
                tera_text = line.split(':', 1)[1].strip()
                pokemon.tera_type = tera_text.lower()
            
            # Gender
            elif line_lower.startswith('gender:'):
                gender_text = line.split(':', 1)[1].strip().lower()
                if gender_text in ['m', 'male']:
                    pokemon.gender = 'male'
                elif gender_text in ['f', 'female']:
                    pokemon.gender = 'female'
                elif gender_text in ['genderless']:
                    pokemon.gender = 'genderless'
            
            # Shiny
            elif line_lower.startswith('shiny:'):
                shiny_text = line.split(':', 1)[1].strip().lower()
                pokemon.shiny = shiny_text in ['yes', 'true', '1']
            
            # Friendship (custom field)
            elif line_lower.startswith('friendship:'):
                try:
                    pokemon.friendship = int(line.split(':', 1)[1].strip())
                except ValueError:
                    pass
            
            # Moves (lines starting with -)
            elif line.startswith('-'):
                move = line[1:].strip()
                if move:
                    # Handle Hidden Power with type brackets: "Hidden Power [Fighting]" -> "Hidden Power"
                    if move.lower().startswith('hidden power'):
                        hp_match = re.match(r'hidden power\s*\[(.+?)\]', move, re.IGNORECASE)
                        if hp_match:
                            pokemon.moves.append("Hidden Power")
                        else:
                            pokemon.moves.append("Hidden Power")
                    else:
                        pokemon.moves.append(move)
            # Also handle moves without dashes (edge case - if a line doesn't match any other pattern and looks like a move)
            elif not any(line_lower.startswith(kw) for kw in ['ability:', 'level:', 'evs:', 'ev:', 'ivs:', 'iv:', 'shiny:', 'gender:', 'tera type:', 'tera:']) and not 'nature' in line_lower:
                # This might be a move without a dash - check if it looks like a move name
                # Move names are usually capitalized words
                if re.match(r'^[A-Z][a-zA-Z\s\-]+$', line.strip()):
                    move_name = line.strip()
                    if move_name.lower().startswith('hidden power'):
                        pokemon.moves.append("Hidden Power")
                    else:
                        pokemon.moves.append(move_name)
        
        if pokemon.species:
            pokemon_list.append(pokemon)
    
    return pokemon_list


def parse_evs_ivs(text: str) -> Dict[str, int]:
    """Parse EVs or IVs from text like '252 Atk / 4 SpD / 252 Spe'."""
    result = {
        "hp": 0,
        "attack": 0,
        "defense": 0,
        "special_attack": 0,
        "special_defense": 0,
        "speed": 0
    }
    
    # Split by / and parse each part
    parts = [p.strip() for p in text.split('/')]
    
    stat_map = {
        'hp': 'hp',
        'atk': 'attack',
        'attack': 'attack',
        'def': 'defense',
        'defense': 'defense',
        'defn': 'defense',
        'spa': 'special_attack',
        'spatk': 'special_attack',
        'special attack': 'special_attack',
        'special-attack': 'special_attack',
        'spd': 'special_defense',
        'spdef': 'special_defense',
        'special defense': 'special_defense',
        'special-defense': 'special_defense',
        'spe': 'speed',
        'speed': 'speed',
        'spd': 'special_defense',  # Common abbreviation
    }
    
    for part in parts:
        # Match pattern like "252 Atk" or "4 SpD"
        match = re.match(r'(\d+)\s+(.+)', part, re.IGNORECASE)
        if match:
            value = int(match.group(1))
            stat_name = match.group(2).strip().lower()
            
            # Find matching stat key
            for key, mapped_key in stat_map.items():
                if stat_name == key or stat_name.startswith(key):
                    result[mapped_key] = value
                    break
    
    return result


# Preset teams
PRESET_TEAMS: Dict[str, List[Dict[str, Any]]] = {
    "gen1_ou": [
        {
            "species": "Alakazam",
            "item": "twisted-spoon",
            "ability": "synchronize",
            "level": 100,
            "nature": "timid",
            "evs": {"hp": 0, "attack": 0, "defense": 0, "special_attack": 252, "special_defense": 0, "speed": 252},
            "moves": ["Psychic", "Recover", "Reflect", "Seismic Toss"]
        },
        {
            "species": "Snorlax",
            "item": "leftovers",
            "ability": "immunity",
            "level": 100,
            "nature": "adamant",
            "evs": {"hp": 252, "attack": 252, "defense": 0, "special_attack": 0, "special_defense": 0, "speed": 4},
            "moves": ["Body Slam", "Earthquake", "Rest", "Sleep Talk"]
        },
        {
            "species": "Tauros",
            "item": None,
            "ability": "intimidate",
            "level": 100,
            "nature": "jolly",
            "evs": {"hp": 0, "attack": 252, "defense": 0, "special_attack": 0, "special_defense": 0, "speed": 252},
            "moves": ["Body Slam", "Earthquake", "Hyper Beam", "Blizzard"]
        },
        {
            "species": "Exeggutor",
            "item": None,
            "ability": "chlorophyll",
            "level": 100,
            "nature": "modest",
            "evs": {"hp": 252, "attack": 0, "defense": 0, "special_attack": 252, "special_defense": 0, "speed": 4},
            "moves": ["Psychic", "Sleep Powder", "Explosion", "Solar Beam"]
        },
        {
            "species": "Gengar",
            "item": None,
            "ability": "levitate",
            "level": 100,
            "nature": "timid",
            "evs": {"hp": 0, "attack": 0, "defense": 0, "special_attack": 252, "special_defense": 0, "speed": 252},
            "moves": ["Thunderbolt", "Ice Beam", "Hypnosis", "Explosion"]
        },
        {
            "species": "Chansey",
            "item": "leftovers",
            "ability": "natural-cure",
            "level": 100,
            "nature": "bold",
            "evs": {"hp": 252, "attack": 0, "defense": 252, "special_attack": 0, "special_defense": 0, "speed": 4},
            "moves": ["Soft-Boiled", "Toxic", "Seismic Toss", "Ice Beam"]
        }
    ],
    "gen2_ou": [
        {
            "species": "Tyranitar",
            "item": "leftovers",
            "ability": "sand-stream",
            "level": 100,
            "nature": "adamant",
            "evs": {"hp": 252, "attack": 252, "defense": 0, "special_attack": 0, "special_defense": 0, "speed": 4},
            "moves": ["Rock Slide", "Earthquake", "Crunch", "Pursuit"]
        },
        {
            "species": "Skarmory",
            "item": "leftovers",
            "ability": "keen-eye",
            "level": 100,
            "nature": "impish",
            "evs": {"hp": 252, "attack": 0, "defense": 252, "special_attack": 0, "special_defense": 0, "speed": 4},
            "moves": ["Drill Peck", "Whirlwind", "Spikes", "Roost"]
        },
        {
            "species": "Raikou",
            "item": "leftovers",
            "ability": "pressure",
            "level": 100,
            "nature": "timid",
            "evs": {"hp": 0, "attack": 0, "defense": 0, "special_attack": 252, "special_defense": 0, "speed": 252},
            "moves": ["Thunderbolt", "Hidden Power Ice", "Calm Mind", "Substitute"]
        },
        {
            "species": "Snorlax",
            "item": "leftovers",
            "ability": "immunity",
            "level": 100,
            "nature": "adamant",
            "evs": {"hp": 252, "attack": 252, "defense": 0, "special_attack": 0, "special_defense": 0, "speed": 4},
            "moves": ["Body Slam", "Earthquake", "Rest", "Sleep Talk"]
        },
        {
            "species": "Cloyster",
            "item": "leftovers",
            "ability": "shell-armor",
            "level": 100,
            "nature": "jolly",
            "evs": {"hp": 0, "attack": 252, "defense": 0, "special_attack": 0, "special_defense": 0, "speed": 252},
            "moves": ["Surf", "Ice Beam", "Explosion", "Rapid Spin"]
        },
        {
            "species": "Zapdos",
            "item": "leftovers",
            "ability": "pressure",
            "level": 100,
            "nature": "timid",
            "evs": {"hp": 0, "attack": 0, "defense": 0, "special_attack": 252, "special_defense": 0, "speed": 252},
            "moves": ["Thunderbolt", "Hidden Power Ice", "Roost", "Heat Wave"]
        }
    ],
    "gen3_ou": [
        {
            "species": "Salamence",
            "item": "choice-band",
            "ability": "intimidate",
            "level": 100,
            "nature": "adamant",
            "evs": {"hp": 0, "attack": 252, "defense": 0, "special_attack": 0, "special_defense": 0, "speed": 252},
            "moves": ["Dragon Claw", "Earthquake", "Aerial Ace", "Rock Slide"]
        },
        {
            "species": "Metagross",
            "item": "leftovers",
            "ability": "clear-body",
            "level": 100,
            "nature": "adamant",
            "evs": {"hp": 252, "attack": 252, "defense": 0, "special_attack": 0, "special_defense": 0, "speed": 4},
            "moves": ["Meteor Mash", "Earthquake", "Explosion", "Agility"]
        },
        {
            "species": "Swampert",
            "item": "leftovers",
            "ability": "torrent",
            "level": 100,
            "nature": "relaxed",
            "evs": {"hp": 252, "attack": 0, "defense": 252, "special_attack": 0, "special_defense": 0, "speed": 4},
            "moves": ["Earthquake", "Surf", "Ice Beam", "Protect"]
        },
        {
            "species": "Skarmory",
            "item": "leftovers",
            "ability": "keen-eye",
            "level": 100,
            "nature": "impish",
            "evs": {"hp": 252, "attack": 0, "defense": 252, "special_attack": 0, "special_defense": 0, "speed": 4},
            "moves": ["Drill Peck", "Whirlwind", "Spikes", "Roost"]
        },
        {
            "species": "Blissey",
            "item": "leftovers",
            "ability": "natural-cure",
            "level": 100,
            "nature": "bold",
            "evs": {"hp": 252, "attack": 0, "defense": 252, "special_attack": 0, "special_defense": 0, "speed": 4},
            "moves": ["Soft-Boiled", "Seismic Toss", "Toxic", "Aromatherapy"]
        },
        {
            "species": "Gengar",
            "item": "leftovers",
            "ability": "levitate",
            "level": 100,
            "nature": "timid",
            "evs": {"hp": 0, "attack": 0, "defense": 0, "special_attack": 252, "special_defense": 0, "speed": 252},
            "moves": ["Thunderbolt", "Ice Punch", "Giga Drain", "Will-O-Wisp"]
        }
    ]
}


def get_preset_team_names() -> List[str]:
    """Get list of available preset team names."""
    return list(PRESET_TEAMS.keys())


def get_preset_team(name: str) -> Optional[List[Dict[str, Any]]]:
    """Get a preset team by name."""
    return PRESET_TEAMS.get(name.lower())

