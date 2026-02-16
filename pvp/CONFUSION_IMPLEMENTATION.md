# Confusion System Implementation

## Overview
Full implementation of the confusion pseudo-status condition with all generation-specific differences from Gen 1-9.

---

## Generation Differences

### Self-Hit Chance
| Generation | Chance to Hit Self | Implementation |
|------------|-------------------|----------------|
| Gen 1-6 | **50%** | Lines 923-924 in engine.py |
| Gen 7+ | **33%** | Lines 925-926 in engine.py |

### Prevention Items/Abilities
| Gen | Focus Band | Focus Sash | Sturdy | Implementation |
|-----|-----------|-----------|--------|----------------|
| Gen 1 | ❌ N/A | ❌ N/A | ❌ N/A | - |
| Gen 2 | ❌ Cannot prevent | ❌ N/A | ❌ N/A | Lines 948-949 |
| Gen 3 | ✅ Can prevent (10% chance) | ❌ N/A | ❌ N/A | Lines 976-984 |
| Gen 4 | ✅ Can prevent (10% chance) | ✅ Can prevent (at full HP) | ❌ N/A | Lines 965-974, 976-984 |
| Gen 5+ | ✅ Can prevent (10% chance) | ✅ Can prevent (at full HP) | ✅ Can prevent (at full HP) | Lines 958-963, 965-974, 976-984 |

---

## Mechanics

### Duration
- **Turns:** 1-4 turns (randomly determined at application)
- **Countdown:** Decreases by 1 at end of each turn
- **Snap Out:** Automatic when counter reaches 0

### Damage Calculation
```python
# Typeless, uses base Attack vs Defense (no stat stages)
base_attack = mon.stats["atk"]
base_defense = mon.stats["defn"]
power = 40  # Fixed power
level = mon.level

damage = int(((2 * level / 5 + 2) * power * (base_attack / base_defense) / 50) + 2)
damage = int(damage * random(0.85, 1.0))  # Random factor
```

### Application
- **Functions:**
  - `can_inflict_confusion()`: Check if confusion can be applied (lines 207-225 in db_move_effects.py)
  - `apply_confusion()`: Apply confusion to target (lines 228-266 in db_move_effects.py)
- **Berry Curing:** Persim Berry, Lum Berry (auto-consumed)
- **Cheek Pouch:** Activates after berry consumption

### Execution Check
- **Function:** `check_confusion_self_hit()` (lines 898-993 in engine.py)
- **Called:** Before move execution in battle resolution
- **Returns:** `(hit_self: bool, damage: int, message: str)`

### End-of-Turn
- **Countdown:** Lines 674-679 in engine.py
- **Auto-Snap-Out:** When `confusion_turns` reaches 0

---

## Immunities

### Abilities
| Ability | Effect |
|---------|--------|
| **Own Tempo** | Complete immunity to confusion |
| *(Check in abilities.py for others)* |

### Items
| Item | Effect | Timing |
|------|--------|--------|
| **Persim Berry** | Cures confusion | Immediate (consumed) |
| **Lum Berry** | Cures confusion + status | Immediate (consumed) |

---

## Data Structure

### Mon Dataclass Additions
```python
# Lines 110-112 in engine.py
confused: bool = False
confusion_turns: int = 0
```

---

## Files Modified

| File | Lines | Changes |
|------|-------|---------|
| **pvp/engine.py** | 110-112 | Added `confused` and `confusion_turns` to Mon dataclass |
| **pvp/engine.py** | 898-993 | Added `check_confusion_self_hit()` function |
| **pvp/engine.py** | 674-679 | Added confusion countdown in `apply_status_effects()` |
| **pvp/db_move_effects.py** | 207-266 | Added `can_inflict_confusion()` and `apply_confusion()` |
| **pvp/abilities.py** | 590-594 | Own Tempo already has `confusion_immunity: True` |

---

## Usage Example

### In Move Execution
```python
# Before executing move, check for confusion self-hit
hit_self, damage, message = check_confusion_self_hit(user, field_effects)
if hit_self:
    # User hit itself, don't execute move
    return message

# Otherwise, execute move normally
```

### Applying Confusion
```python
# From move secondary effect
from pvp.db_move_effects import apply_confusion

success, message = apply_confusion(target)
if success:
    battle_log.append(message)
```

---

## Testing Checklist

- [x] Gen 1-6: 50% self-hit chance
- [x] Gen 7+: 33% self-hit chance
- [x] Gen 2: Focus Band does NOT prevent confusion self-KO
- [x] Gen 3+: Focus Band CAN prevent (10% chance)
- [x] Gen 4+: Focus Sash prevents at full HP
- [x] Gen 5+: Sturdy prevents at full HP
- [x] Duration: 1-4 turns random
- [x] Own Tempo immunity
- [x] Persim Berry auto-cure
- [x] Lum Berry auto-cure
- [x] Cheek Pouch activation
- [x] Countdown and auto-snap-out
- [ ] Integration with move database (confusion_chance field)
- [ ] Panel.py integration for battle flow
- [ ] UI display of confusion status

---

## Known Limitations

1. **Gen 4 Rage Bug:** Not implemented
   - "If a confused Pokémon has used Rage and then selects a different move, it will snap out of confusion, but its rage will still be building"
   - Requires Rage move tracking system

2. **Move Database Integration:** Needs wiring
   - Moves with `confusion_chance` in database need to call `apply_confusion()`
   - Secondary effect handler needs updating

3. **UI Display:** Not yet implemented
   - Confusion icon/indicator needs adding to battle UI
   - Confusion message display in panel

---

## Next Steps

1. Wire confusion to move database
2. Add confusion application in secondary effects handler
3. Integrate `check_confusion_self_hit()` into turn resolution
4. Add UI indicators for confused status
5. Implement Gen 4 Rage bug (if desired)

---

## Production Status

✅ **Core System:** Fully implemented and tested  
✅ **Integration:** Fully wired into battle flow (`can_pokemon_move()` and `apply_confusion()`)  
⏹️ **UI:** Not yet implemented

---

## Wiring Details

### Files Modified for Integration

1. **`pvp/battle_flow.py`** (lines 10-62)
   - Updated `can_pokemon_move()` to accept `field_effects` parameter
   - Added confusion check before status conditions
   - Calls `check_confusion_self_hit()` from engine.py
   - Applies confusion damage and returns appropriate message

2. **`pvp/panel.py`** (line 536)
   - Updated call to `can_pokemon_move(atk, self.field)` to pass field_effects

3. **`pvp/move_effects.py`** (lines 1406-1417, 1476-1491)
   - Updated `apply_secondary_effect()` signature to accept `field_effects`
   - Replaced old confusion logic with call to `apply_confusion()`
   - Now properly checks Own Tempo and handles Persim/Lum Berry

4. **`pvp/engine.py`** (line 5816)
   - Updated call to `apply_secondary_effect()` to pass `field_effects`

### Battle Flow Integration

**Turn Execution Order:**
1. **Check if Pokemon can move** (`can_pokemon_move()`)
   - Confusion is checked here (BEFORE move execution)
   - If confused: Roll for self-hit (generation-aware)
   - If hits self: Apply damage, prevent move, return message
   - If doesn't hit self: Continue to move execution

2. **Execute move** (`apply_move()`)
   - Damage calculation and application
   - Secondary effects applied after move

3. **Apply secondary effects** (`apply_secondary_effect()`)
   - Confusion can be inflicted here
   - Checks Own Tempo immunity
   - Consumes Persim/Lum Berry if applicable

4. **End of turn** (`apply_status_effects()`)
   - Confusion turns are decremented
   - Confusion is removed when turns reach 0

### Testing Confirmed

- ✅ Confusion self-hit rolls work (50% Gen 1-6, 33% Gen 7+)
- ✅ Confusion damage calculated correctly (typeless, power 40, Atk vs Def)
- ✅ Own Tempo prevents confusion
- ✅ Persim Berry and Lum Berry cure confusion
- ✅ Cheek Pouch activates after berry consumption
- ✅ Confusion turns countdown properly
- ✅ Generation-specific behavior enforced



