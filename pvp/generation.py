"""
Generation Support Module for PVP Engine

This module provides utilities for handling generation-specific mechanics in battles.
All abilities, moves, and items should check generation before applying effects.

Usage:
    from .generation import get_generation
    
    generation = get_generation(battle_state)
    if generation <= 7:
        # Gen 5-7 behavior
    else:
        # Gen 8+ behavior
"""

from typing import Any, Optional


def get_generation(battle_state: Any = None, field_effects: Any = None) -> int:
    """
    Extract generation from battle state or field effects.
    
    Args:
        battle_state: BattleState object (preferred)
        field_effects: FieldEffects object (fallback)
    
    Returns:
        int: The current battle generation (1-9), defaults to 9
    """
    # Try battle_state first (most reliable)
    if battle_state and hasattr(battle_state, 'gen'):
        return int(battle_state.gen)
    
    # Try field_effects as fallback
    if field_effects and hasattr(field_effects, 'generation'):
        return int(field_effects.generation)
    
    # Default to Gen 9 (latest)
    return 9


def is_gen_range(generation: int, min_gen: int, max_gen: Optional[int] = None) -> bool:
    """
    Check if generation is within a range.
    
    Args:
        generation: Current generation
        min_gen: Minimum generation (inclusive)
        max_gen: Maximum generation (inclusive), None means no upper limit
    
    Returns:
        True if generation is in range
    
    Examples:
        >>> is_gen_range(5, 5, 7)  # Gen 5-7
        True
        >>> is_gen_range(8, 8)     # Gen 8+
        True
    """
    if max_gen is None:
        return generation >= min_gen
    return min_gen <= generation <= max_gen


# Generation milestones for quick checks
GEN_1 = 1
GEN_2 = 2
GEN_3 = 3
GEN_4 = 4
GEN_5 = 5
GEN_6 = 6
GEN_7 = 7
GEN_8 = 8
GEN_9 = 9

