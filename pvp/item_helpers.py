"""
Helper functions for safely handling item consumption and modification during battles.
Items are only temporarily modified - original items are restored after battle ends.
"""

from typing import Optional, Any

def consume_item(mon: Any) -> Optional[str]:
    """
    Consume a Pokémon's held item during battle (temporarily set to None).
    The original item is stored in _original_item_battle and will be restored after battle.
    
    Returns the item name that was consumed, or None if no item.
    """
    if not mon or not hasattr(mon, 'item'):
        return None
    
    consumed_item = mon.item
    
    # Store original item if not already stored (first consumption)
    if not hasattr(mon, '_original_item_battle'):
        mon._original_item_battle = consumed_item
    
    # Set to None (temporary - will be restored after battle)
    mon.item = None
    
    return consumed_item

def restore_item(mon: Any) -> None:
    """
    Restore a Pokémon's original item from before the battle.
    This is called automatically when battle ends via BattleState.restore_items().
    """
    if not mon or not hasattr(mon, '_original_item_battle'):
        return
    
    # Restore original item (even if it was None)
    mon.item = mon._original_item_battle
    # Clean up the temporary storage
    if hasattr(mon, '_original_item_battle'):
        delattr(mon, '_original_item_battle')

def swap_items(user: Any, target: Any) -> None:
    """
    Swap items between two Pokémon during battle.
    Original items are preserved for restoration after battle.
    """
    if not user or not target:
        return
    
    # Store original items if not already stored
    if not hasattr(user, '_original_item_battle'):
        user._original_item_battle = getattr(user, 'item', None)
    if not hasattr(target, '_original_item_battle'):
        target._original_item_battle = getattr(target, 'item', None)
    
    # Perform swap (temporary)
    user.item, target.item = target.item, user.item


