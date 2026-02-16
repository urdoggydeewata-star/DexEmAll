"""
Battle Bond ability transformation system for Greninja.

When a Greninja with the Battle Bond ability KOs an opponent,
it transforms into Ash-Greninja temporarily (for the duration of the battle).
"""

from typing import Optional, Tuple


def can_battle_bond_transform(mon) -> bool:
    """Check if a Pokémon can transform via Battle Bond."""
    # Must be Greninja with Battle Bond ability
    if mon.species.lower() != "greninja":
        return False
    
    ability_norm = (mon.ability or "").lower().replace(" ", "-").replace("_", "-")
    if ability_norm != "battle-bond":
        return False
    
    # Must not already be transformed
    if hasattr(mon, 'form') and mon.form == "ash":
        return False
    
    return True


def apply_battle_bond_transform(mon) -> Tuple[bool, str]:
    """
    Transform Greninja into Ash-Greninja.
    Returns: (success, message)
    """
    if not can_battle_bond_transform(mon):
        return False, ""
    
    # Store original form if not already stored
    if not hasattr(mon, '_original_form_battle_bond'):
        mon._original_form_battle_bond = getattr(mon, 'form', None)
    
    # Transform to Ash-Greninja
    old_name = "Greninja"
    mon.form = "ash"
    new_name = "Ash-Greninja"
    
    # Ash-Greninja base stats: 72/145/67/153/71/132
    # Base Greninja: 72/95/67/103/71/122
    # We need to update base stats and recalculate all stats properly
    if not hasattr(mon, '_battle_bond_transformed'):
        mon._battle_bond_transformed = True
        
        # Store original base stats and calculated stats
        if not hasattr(mon, '_original_base_battle_bond'):
            mon._original_base_battle_bond = mon.base.copy()
        mon._original_stats_battle_bond = mon.stats.copy()
        
        # Update base stats to Ash-Greninja's base stats
        # Ash-Greninja base stats: 72/145/67/153/71/132
        # Base Greninja: 72/95/67/103/71/122
        # Only Atk, SpA, and Spe change
        mon.base["atk"] = 145
        mon.base["spa"] = 153
        mon.base["spe"] = 132
        # HP, Def, SpD remain the same (72, 67, 71)
        
        # Recalculate stats from new base stats using IVs, EVs, level, and nature
        # Import here to avoid circular import with engine
        from .engine import _calc_stat, NATURES
        
        # Get nature multipliers
        nature_name = getattr(mon, 'nature_name', 'hardy') or 'hardy'
        nature_mods = NATURES.get(nature_name, NATURES.get("hardy", {"atk": 1.0, "defn": 1.0, "spa": 1.0, "spd": 1.0, "spe": 1.0}))
        
        # IMPORTANT: Preserve stat stages (boosts/drops) - they are stored in mon.stages and should NOT be reset
        # Only update base stats and recalculate raw stats (before stage modifiers)
        # Stat stages in mon.stages are preserved and will be applied when calculating effective stats via get_effective_stat
        # Recalculate all non-HP stats with new base stats
        # Preserve stat stages - they will be applied via get_effective_stat
        mon.stats["atk"] = _calc_stat(mon.base.get("atk", 145), mon.ivs.get("atk", 0), mon.evs.get("atk", 0), mon.level, nature_mods.get("atk", 1.0))
        mon.stats["defn"] = _calc_stat(mon.base.get("defn", 67), mon.ivs.get("defn", 0), mon.evs.get("defn", 0), mon.level, nature_mods.get("defn", 1.0))
        mon.stats["spa"] = _calc_stat(mon.base.get("spa", 153), mon.ivs.get("spa", 0), mon.evs.get("spa", 0), mon.level, nature_mods.get("spa", 1.0))
        mon.stats["spd"] = _calc_stat(mon.base.get("spd", 71), mon.ivs.get("spd", 0), mon.evs.get("spd", 0), mon.level, nature_mods.get("spd", 1.0))
        mon.stats["spe"] = _calc_stat(mon.base.get("spe", 132), mon.ivs.get("spe", 0), mon.evs.get("spe", 0), mon.level, nature_mods.get("spe", 1.0))
        
        # IMPORTANT: Preserve stat stages (boosts/drops) - they are stored in mon.stages and should NOT be reset
        # Ensure stat stages dictionary exists, but preserve existing values
        if not hasattr(mon, 'stages') or not isinstance(mon.stages, dict):
            # Initialize if missing with default values
            mon.stages = {"atk": 0, "defn": 0, "spa": 0, "spd": 0, "spe": 0, "accuracy": 0, "evasion": 0}
        # Stat stages are preserved - they will be applied when calculating effective stats via get_effective_stat
    
    msg = f"**{old_name}'s Battle Bond!**\n{old_name} became {new_name}!"
    return True, msg


def revert_battle_bond_transform(mon) -> Tuple[bool, str]:
    """
    Revert Ash-Greninja back to base Greninja.
    Returns: (success, message)
    """
    if mon.species.lower() != "greninja":
        return False, ""
    
    if not hasattr(mon, '_battle_bond_transformed') or not mon._battle_bond_transformed:
        return False, ""
    
    # Revert form
    mon.form = mon._original_form_battle_bond if hasattr(mon, '_original_form_battle_bond') else None
    
    # Revert base stats and calculated stats
    if hasattr(mon, '_original_base_battle_bond'):
        mon.base.update(mon._original_base_battle_bond)
    if hasattr(mon, '_original_stats_battle_bond'):
        mon.stats = mon._original_stats_battle_bond.copy()
    
    # Preserve stat stages - they should remain unchanged during transformation/reversion
    # Stat stages are not reverted, they persist through the transformation
    
    # Clear flags
    mon._battle_bond_transformed = False
    
    msg = f"Ash-Greninja reverted to Greninja!"
    return True, msg








