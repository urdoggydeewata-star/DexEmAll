"""
Hidden Power Type Calculation
Calculates Hidden Power type and power based on a Pokémon's IVs

Generation II:
- Type: HP_type = 4x (Attack IV mod 4) + (Defense IV mod 4)
- Power: HP_power = floor((5 × (v + 2w + 4x + 8y) + Z) / 2) + 31
  where v, w, x, y are MSB of Special, Speed, Defense, Attack IVs (1 if IV >= 8, else 0)
  and Z = Special IV mod 4
  Power ranges from 31 to 70

Generation III+:
- Type: HP_type = floor(((a + 2b + 4c + 8d + 16e + 32f) × 15) / 63)
  where a, b, c, d, e, f are LSB of HP, Attack, Defense, Speed, SpA, SpD IVs (0 if even, 1 if odd)
- Power: HP_power = floor(((u + 2v + 4w + 8x + 16y + 32z) × 40) / 63) + 30
  where u, v, w, x, y, z are second LSB of HP, Attack, Defense, Speed, SpA, SpD IVs (1 if IV mod 4 is 2 or 3, else 0)
  Power ranges from 30 to 70

Generation VI+:
- Power is fixed at 60
"""

from typing import Dict, Tuple, Optional
from functools import lru_cache
import math

# Hidden Power type based on IV bits
HP_TYPES = [
    "Fighting", "Flying", "Poison", "Ground",
    "Rock", "Bug", "Ghost", "Steel",
    "Fire", "Water", "Grass", "Electric",
    "Psychic", "Ice", "Dragon", "Dark"
]

@lru_cache(maxsize=256)
def _calculate_hidden_power_type_gen2_cached(atk_iv: int, def_iv: int) -> str:
    """Generation II type calculation (cached)"""
    # Type = 4x (Attack IV mod 4) + (Defense IV mod 4)
    a = atk_iv % 4
    b = def_iv % 4
    type_index = (4 * a) + b
    return HP_TYPES[type_index]

@lru_cache(maxsize=256)
def _calculate_hidden_power_type_gen3_cached(hp_iv: int, atk_iv: int, def_iv: int, spa_iv: int, spd_iv: int, spe_iv: int) -> str:
    """
    Generation III+ type calculation (cached)
    
    Formula: HP_type = floor((a + 2b + 4c + 8d + 16e + 32f) × 15 / 63)
    
    Where the type bits are the least significant bit (LSB) of each IV:
    - a = HP IV LSB (1 if odd, 0 if even)
    - b = Attack IV LSB (1 if odd, 0 if even)
    - c = Defense IV LSB (1 if odd, 0 if even)
    - d = Speed IV LSB (1 if odd, 0 if even)
    - e = Special Attack IV LSB (1 if odd, 0 if even)
    - f = Special Defense IV LSB (1 if odd, 0 if even)
    
    The resulting number (0-15) corresponds to a type in HP_TYPES.
    """
    # Calculate type bits (LSB of each IV: 0 if even, 1 if odd)
    a = hp_iv % 2   # HP IV LSB
    b = atk_iv % 2  # Attack IV LSB
    c = def_iv % 2  # Defense IV LSB
    d = spe_iv % 2  # Speed IV LSB
    e = spa_iv % 2  # Special Attack IV LSB
    f = spd_iv % 2  # Special Defense IV LSB
    
    # Calculate type index: floor(((a + 2b + 4c + 8d + 16e + 32f) × 15) / 63)
    type_bits = a + (2 * b) + (4 * c) + (8 * d) + (16 * e) + (32 * f)
    type_index = math.floor((type_bits * 15) / 63)
    
    return HP_TYPES[type_index]

def calculate_hidden_power_type(ivs: Dict[str, int], generation: Optional[int] = None) -> str:
    """
    Calculate Hidden Power type based on IVs and generation.
    
    Generation II:
    Type = 4x (Attack IV mod 4) + (Defense IV mod 4)
    
    Generation III+:
    Type = floor(((a + 2b + 4c + 8d + 16e + 32f) × 15) / 63)
    Where a, b, c, d, e, f are LSB of HP, Attack, Defense, Speed, SpA, SpD IVs
    
    Args:
        ivs: Dictionary with keys 'hp', 'atk', 'defn', 'spa', 'spd', 'spe'
        generation: Optional generation (defaults to 9 for Gen III+ calculation)
    
    Returns:
        Type name (e.g., "Fighting", "Fire", "Ice")
    """
    generation = generation if generation is not None else 9
    
    # Get IVs with defaults (but allow 0 as a valid value)
    if 'atk' in ivs:
        atk_iv = ivs['atk']
    elif 'attack' in ivs:
        atk_iv = ivs['attack']
    else:
        atk_iv = 31
    
    if 'defn' in ivs:
        def_iv = ivs['defn']
    elif 'def' in ivs:
        def_iv = ivs['def']
    elif 'defense' in ivs:
        def_iv = ivs['defense']
    else:
        def_iv = 31
    
    if generation == 2:
        # Generation II: Only uses Attack and Defense IVs
        return _calculate_hidden_power_type_gen2_cached(atk_iv, def_iv)
    
    # Generation III+
    # Get HP IV - explicitly check for key existence to allow 0 IVs
    if 'hp' in ivs:
        hp_iv = ivs['hp']
    else:
        hp_iv = 31
    if 'spa' in ivs:
        spa_iv = ivs['spa']
    elif 'special_attack' in ivs:
        spa_iv = ivs['special_attack']
    else:
        spa_iv = 31
    
    if 'spd' in ivs:
        spd_iv = ivs['spd']
    elif 'special_defense' in ivs:
        spd_iv = ivs['special_defense']
    else:
        spd_iv = 31
    
    if 'spe' in ivs:
        spe_iv = ivs['spe']
    elif 'speed' in ivs:
        spe_iv = ivs['speed']
    else:
        spe_iv = 31
    
    return _calculate_hidden_power_type_gen3_cached(hp_iv, atk_iv, def_iv, spa_iv, spd_iv, spe_iv)

def calculate_hidden_power_power(ivs: Dict[str, int], generation: Optional[int] = None) -> int:
    """
    Calculate Hidden Power base power based on IVs and generation.
    
    Generation VI+: Fixed at 60
    
    Generation II:
    Power = floor((5 × (v + 2w + 4x + 8y) + Z) / 2) + 31
    - v = Special IV MSB (1 if Special IV >= 8, else 0)
    - w = Speed IV MSB (1 if Speed IV >= 8, else 0)
    - x = Defense IV MSB (1 if Defense IV >= 8, else 0)
    - y = Attack IV MSB (1 if Attack IV >= 8, else 0)
    - Z = Special IV mod 4
    Power ranges from 31 to 70
    
    Generation III-V:
    Power = floor(((u + 2v + 4w + 8x + 16y + 32z) × 40) / 63) + 30
    - u, v, w, x, y, z are second LSB of HP, Attack, Defense, Speed, SpA, SpD IVs
    - Second LSB = 1 if IV mod 4 is 2 or 3, else 0
    Power ranges from 30 to 70
    
    Args:
        ivs: Dictionary with keys 'hp', 'atk', 'defn', 'spa', 'spd', 'spe'
        generation: Optional generation override (defaults to 9)

    Returns:
        Base power (varies by generation)
    """
    generation = generation if generation is not None else 9

    if generation >= 6:
        return 60

    # Helper to fetch IV (default 31 if missing)
    def _get_iv(key: str, fallback_keys: Tuple[str, ...] = ()) -> int:
        if key in ivs:
            return ivs[key]
        for fb in fallback_keys:
            if fb in ivs:
                return ivs[fb]
        return 31

    atk_iv = _get_iv('atk', ('attack',))
    def_iv = _get_iv('defn', ('def', 'defense'))
    spa_iv = _get_iv('spa', ('special_attack',))
    spe_iv = _get_iv('spe', ('speed',))

    if generation == 2:
        # Generation II: HP_power = floor((5 × (v + 2w + 4x + 8y) + Z) / 2) + 31
        # v = Special IV MSB (1 if >= 8, else 0)
        # w = Speed IV MSB (1 if >= 8, else 0)
        # x = Defense IV MSB (1 if >= 8, else 0)
        # y = Attack IV MSB (1 if >= 8, else 0)
        # Z = Special IV mod 4
        v = 1 if spa_iv >= 8 else 0  # Special IV MSB
        w = 1 if spe_iv >= 8 else 0  # Speed IV MSB
        x = 1 if def_iv >= 8 else 0  # Defense IV MSB
        y = 1 if atk_iv >= 8 else 0  # Attack IV MSB
        z = spa_iv % 4  # Special IV mod 4
        
        power = math.floor((5 * (v + 2*w + 4*x + 8*y) + z) / 2) + 31
        return max(31, min(70, power))

    # Generation III-V: HP_power = floor(((u + 2v + 4w + 8x + 16y + 32z) × 40) / 63) + 30
    # u, v, w, x, y, z are second LSB (1 if IV mod 4 is 2 or 3, else 0)
    hp_iv = _get_iv('hp')
    spd_iv = _get_iv('spd', ('special_defense',))
    
    # Second LSB: 1 if IV mod 4 is 2 or 3, else 0
    u = 1 if (hp_iv % 4) in (2, 3) else 0   # HP IV second LSB
    v = 1 if (atk_iv % 4) in (2, 3) else 0  # Attack IV second LSB
    w = 1 if (def_iv % 4) in (2, 3) else 0  # Defense IV second LSB
    x = 1 if (spe_iv % 4) in (2, 3) else 0  # Speed IV second LSB
    y = 1 if (spa_iv % 4) in (2, 3) else 0 # Special Attack IV second LSB
    z = 1 if (spd_iv % 4) in (2, 3) else 0 # Special Defense IV second LSB

    bit_value = u + (2 * v) + (4 * w) + (8 * x) + (16 * y) + (32 * z)
    power = math.floor((bit_value * 40) / 63) + 30
    return max(30, min(70, power))

def get_hidden_power_type_from_ivs(ivs: Dict[str, int], generation: Optional[int] = None) -> Tuple[str, int]:
    """
    Get both type and power for Hidden Power based on IVs.
    
    Args:
        ivs: Dictionary with keys 'hp', 'atk', 'defn', 'spa', 'spd', 'spe'
        generation: Optional generation (defaults to 9)
    
    Returns:
        Tuple of (type_name, base_power)
    """
    hp_type = calculate_hidden_power_type(ivs, generation=generation)
    hp_power = calculate_hidden_power_power(ivs, generation=generation)
    return hp_type, hp_power

def normalize_hidden_power_move_name(move_name: str) -> str:
    """
    Normalize Hidden Power move names.
    
    Converts:
    - "hidden-power-fighting" -> "hidden-power"
    - "Hidden Power Fighting" -> "hidden-power"
    - etc.
    
    Returns:
        Normalized move name
    """
    normalized = move_name.lower().replace(" ", "-").strip()
    if normalized.startswith("hidden-power"):
        return "hidden-power"
    return normalized

def get_hidden_power_display_name(ivs: Dict[str, int], generation: Optional[int] = None) -> str:
    """
    Get the display name for Hidden Power based on IVs.
    
    Args:
        ivs: Dictionary with keys 'hp', 'atk', 'defn', 'spa', 'spd', 'spe'
        generation: Optional generation (defaults to 9)
    
    Returns:
        Display name like "Hidden Power [Fighting]" or "Hidden Power [Ice]"
    """
    hp_type = calculate_hidden_power_type(ivs, generation=generation)
    return f"Hidden Power [{hp_type}]"



