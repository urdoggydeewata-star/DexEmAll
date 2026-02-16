# Moves Implementation Status

## ✅ Fully Implemented
1. **Stockpile/Spit Up/Swallow** - `advanced_moves.py` lines 1060-1171
   - Has gen differences for stat boosts (Gen IV+)
   - Has gen differences for stat removal messages (Gen V+)

## ⚠️ Partially Implemented - Need Gen Updates

### 1. Beat Up
- ✅ Flag exists: `multi_hit_party: True` in move_effects.py
- ✅ Function added: `calculate_beat_up_damage()` in advanced_moves.py (lines 2049-2161)
- ❌ **NEEDS**: Integration into engine.py damage calculation
- ❌ **NEEDS**: Gen II vs III-IV vs V+ mechanics:
  - Gen II-IV: Use each party member's stats, base power 10, typeless
  - Gen V+: Use only user's Attack, power = (BaseAttack/10)+5, STAB applies
  - Gen V+: Affected by Technician
  - Gen V+: No attacker names listed

### 2. Fake Out  
- ✅ `check_fake_out_family()` in special_moves.py
- ✅ Contact flag handled: Gen III (no contact), Gen IV+ (contact)
- ❌ **NEEDS**: Priority update: Gen III (priority +1), Gen V+ (priority +3)
- ❌ **NEEDS**: Covert Cloak check (Gen IX+)
- ❌ **NEEDS**: Dynamax/Gigantamax flinch check

### 3. Uproar
- ✅ Duration system: Gen III-IV (2-5 turns), Gen V+ (3 turns)
- ✅ Power: Gen III-IV (50), Gen V+ (90)
- ✅ Sleep prevention implemented
- ❌ **NEEDS**: Gen III-IV vs Gen V+ wake-up mechanics
- ❌ **NEEDS**: Gen VI+: Hits through Substitute
- ❌ **NEEDS**: Throat Chop check (Gen VII+)

### 4. Heat Wave
- ✅ Burn chance (10%) implemented
- ❌ **NEEDS**: Gen VI+: Wind move flag
- ❌ **NEEDS**: Gen VI+: Power 95 (down from 100)

### 5. Hail
- ✅ Weather system implemented
- ❌ **NEEDS**: Gen III-IV Diamond/Pearl: Blizzard hits through Protect (30% acc)
- ❌ **NEEDS**: Gen IX: Cannot be selected (replaced by Snowscape)

### 6. Torment
- ✅ Basic implementation exists
- ❌ **NEEDS**: Gen III-IV: Cannot be reflected with Magic Coat
- ❌ **NEEDS**: Gen V+: Can be reflected with Magic Coat
- ❌ **NEEDS**: Gen VIII+: Fails on Dynamax

### 7. Flatter
- ✅ Flags exist: `confuse: True`, `spa_boost: 1`
- ❌ **NEEDS**: Verify it always boosts SpA even if already confused
- ❌ **NEEDS**: Verify it works even if target has Contrary

### 8. Will-O-Wisp
- ✅ Status move flag exists
- ✅ Accuracy 85 (Gen VI+)
- ❌ **NEEDS**: Gen III accuracy 75%
- ❌ **NEEDS**: Gen IV-V: Activates Flash Fire
- ❌ **NEEDS**: Gen VI+: Activates Flash Fire (check if already implemented)

### 9. Memento
- ✅ Basic faints_user implementation
- ❌ **NEEDS**: Gen III: Bypasses accuracy checks (always hits)
- ❌ **NEEDS**: Gen IV: Accuracy 100 (no bypass)
- ❌ **NEEDS**: Gen V+: User only faints if move hits
- ❌ **NEEDS**: Gen V+: User doesn't faint if blocked by protection/substitute/miss

### 10. Facade
- ✅ `doubled_if_status: True` flag exists
- ✅ Power doubles when user has status
- ❌ **NEEDS**: Gen III-V: Burn still halves physical Attack (unless Guts)
- ❌ **NEEDS**: Gen VI+: Burn's Attack penalty ignored for Facade

### 11. Focus Punch
- ✅ `setup_focus_punch()` exists (lines 1845-1851)
- ✅ `check_focus_punch_interrupt()` exists (lines 1854-1867)
- ✅ Also added new functions in advanced_moves.py (lines 2168-2207)
- ❌ **NEEDS**: Consolidate duplicate implementations
- ❌ **NEEDS**: Gen III-IV: Shows "used Focus Punch!" before fail message
- ❌ **NEEDS**: Gen V+: PP not consumed if fails
- ❌ **NEEDS**: Gen V+: OHKO moves don't break focus
- ❌ **NEEDS**: Gen V+: Different fail message (no "used Focus Punch!")

## Next Steps
1. Integrate Beat Up calculation into engine.py
2. Update Fake Out priority and Covert Cloak check
3. Complete Uproar gen differences
4. Update Heat Wave power and wind flag
5. Update Hail gen differences
6. Update Torment Magic Coat reflection
7. Verify Flatter always works
8. Update Will-O-Wisp accuracy and Flash Fire
9. Update Memento gen differences (accuracy, when user faints)
10. Fix Facade burn penalty handling
11. Consolidate Focus Punch implementations












