# Ability Generation Differences

This document tracks how abilities behave differently across generations.
Use this to implement generation-specific behavior in PVP battles.

---

## How to Use This File

When implementing generation-specific logic:
```python
# Example pattern:
if battle_state.gen <= 4:
    # Gen 1-4 behavior
elif battle_state.gen <= 6:
    # Gen 5-6 behavior
else:
    # Gen 7+ behavior
```

---

## Format

### Ability Name
- **Gen X**: Description of behavior
- **Gen Y+**: Changed behavior
- **Implementation Status**: ✅ Implemented / ⏹️ Not Yet / ⚠️ Needs Update

---

## Ability Differences by Generation

### Adaptability
- **All Gens (4+)**: STAB boost is 2.0x instead of 1.5x
- **Gen 9**: Terastallization mechanics (2.25x if Tera Type matches original, 2.0x otherwise)
- **Implementation Status**: ✅ Base mechanic / ⏹️ Terastallization

---

### Aerilate
- **Gen 6**: Normal-type moves become Flying-type, 1.3x power boost
- **Gen 7+**: Power boost reduced to 1.2x
- **All Gens**: Electrify takes precedence, Ion Deluge does not
- **Implementation Status**: ✅ Implemented (Gen 7+ with correct priority handling)

---

### Aftermath
- **Gen 4-6**: Damages attacker by 1/4 of their max HP on contact KO
- **Gen 7+**: Damages attacker by 1/4 of their max HP on contact KO, blocked by Damp
- **Implementation Status**: ✅ Implemented (Gen 7+ with Damp blocking)

---

### Air Lock
- **All Gens (3+)**: Negates weather effects while active (weather itself remains, but all effects nullified)
- **Gen 5+**: Message "The effects of weather disappeared." on switch-in
- **Gen 6+**: During primal weather, weather moves/abilities fail but Air Lock still negates other effects
- **Implementation Status**: ✅ Implemented (Gen 5+ message, primal weather not yet implemented)

---

### Analytic
- **Gen 5-7**: 1.3x power if user moves last. Fainted Pokemon handling includes Speed modifications from status, items, abilities.
- **Gen 8+**: 1.3x power if user moves last. Fainted Pokemon handling uses base Speed/priority only.
- **Implementation Status**: ✅ Implemented (Gen 8 behavior)

---

### Anger Point
- **Gen 4**: Maxes Attack to +6 when hit by a crit, activates EVEN through Substitute
- **Gen 5+**: Maxes Attack to +6 when hit by a crit, does NOT activate through Substitute
- **Implementation Status**: ✅ Implemented (Gen 5+ behavior)

---

### Anticipation
- **Gen 4**: Warns of super-effective moves, OHKO moves, Self-Destruct/Explosion. Hidden Power/Judgment/Weather Ball/Natural Gift = Normal. Counter/Mirror Coat/Metal Burst don't trigger. Factors in Scrappy/Normalize/Gravity.
- **Gen 5**: Self-Destruct/Explosion = Normal (don't trigger). Counter/Mirror Coat/Metal Burst now trigger. Doesn't factor in Scrappy/Normalize/Gravity.
- **Gen 6+**: Hidden Power = actual type. Freeze-Dry/Flying Press = actual types. Factors in Inverse Battle type chart.
- **Implementation Status**: ✅ Implemented (Gen 6+ behavior, with limitation: can't determine opponent's Hidden Power type)

---

### Arena Trap
- **Gen 3-5**: Prevents grounded opponents from fleeing and switching out
- **Gen 6+**: Ghost-types are now immune (in addition to Flying/Levitate/Magnet Rise)
- **All Gens**: Bypassed by Shed Shell (switching), pivot moves (U-turn/Volt Switch/etc.), Baton Pass
- **Implementation Status**: ✅ Implemented (Gen 6+ behavior, without switch-in turn bypass)

---

### Aroma Veil
- **Gen 6**: Protects user and allies from Taunt, Torment, Encore, Disable, Heal Block, and Infatuation
- **Gen 7+**: Also protects from Cursed Body ability
- **Gen 9+**: Also protects from Psychic Noise (secondary effect)
- **Implementation Status**: ✅ Implemented (all effects except Heal Block/Psychic Noise which aren't in codebase yet)

---

### Battle Armor
- **All Gens (3+)**: Prevents critical hits
- **Implementation Status**: ✅ Implemented

---

### Battle Bond
- **Gen 7**: Greninja transforms after KO (becomes Ash-Greninja, once per battle)
- **Gen 8+**: Removed from regular play (event-only)
- **Gen 9**: Not present
- **Implementation Status**: ✅ Implemented (Gen 7 version)

---

### Beast Boost
- **All Gens (7+)**: Raises highest stat by 1 stage after KO
- **Implementation Status**: ✅ Implemented

---

### Blaze
- **Gen 1-4**: 1.5x Fire-type power when HP ≤ 1/3
- **Gen 5+**: Same (unchanged)
- **Implementation Status**: ✅ Implemented

---

### Bulletproof
- **All Gens (6+)**: Immune to ball and bomb moves
- **Implementation Status**: ⏹️ Not Yet

---

### Chlorophyll
- **Gen 1-4**: 2x Speed in sun
- **Gen 5+**: Same (unchanged)
- **Implementation Status**: ✅ Implemented

---

### Cloud Nine
- **All Gens (3+)**: Negates weather effects while active (identical to Air Lock)
- **Gen 5+**: Message "The effects of weather disappeared." on switch-in
- **Gen 6+**: During primal weather, weather moves/abilities fail but Cloud Nine still negates other effects
- **Implementation Status**: ✅ Implemented (Gen 5+ message, primal weather not yet implemented)

---

### Competitive
- **All Gens (6+)**: +2 Sp. Atk when stats are lowered
- **Gen 8+**: Doesn't activate from self-inflicted stat drops
- **Implementation Status**: ✅ Implemented

---

### Compound Eyes
- **All Gens (3+)**: 1.3x accuracy (exact: 5325/4096)
- **Does NOT affect OHKO moves** (Fissure, Horn Drill, etc.)
- **Implementation Status**: ✅ Implemented

---

### Contrary
- **Gen 5+**: Inverts all stat stage changes (increase → decrease, vice versa)
- **Gen 6+**: Flower Veil accounts for inversion (like Mist)
- **Gen 7+**: Z-move stat boosts are NOT inverted (except Extreme Evoboost/Clangorous Soulblaze)
- **All Gens**: Mold Breaker/Teravolt/Turboblaze bypass Contrary
- **Implementation Status**: ✅ Implemented (base mechanic, ⚠️ Mold Breaker bypass TODO)

---

### Corrosion
- **All Gens (7+)**: Can poison Steel and Poison types
- **Does NOT bypass**: Immunity ability, Safeguard, Toxic Spikes
- **Works with**: Baneful Bunker, Psycho Shift, Fling + Toxic Orb/Poison Barb
- **Implementation Status**: ✅ Implemented

---

### Costar
- **All Gens (9+)**: Copies ally's stat stages on switch-in (including crit ratio)
- **Implementation Status**: ⏹️ Not Implemented (Doubles/Triples only)

---

### Cotton Down
- **All Gens (8+)**: Lowers Speed of ALL OTHER Pokémon by 1 stage when hit
- **Each hit of multi-hit moves activates this ability**
- **Implementation Status**: ✅ Implemented

---

### Cud Chew
- **All Gens (9+)**: Eats Berry twice (effect activates, then activates again at end of next turn)
- **Works with**: Own Berry consumption and Flung Berries
- **Implementation Status**: ⏹️ Not Implemented (Complex, requires delayed effect system)

---

### Curious Medicine
- **All Gens (8+)**: Resets ally's stat stages to 0 on switch-in
- **Implementation Status**: ⏹️ Not Implemented (Doubles/Triples only)

---

### Cursed Body
- **Gen 5**: 30% chance to disable move that hit (contact moves only)
- **Gen 6+**: 30% chance to disable move that hit (ANY damaging move)
- **All Gens**: Disables for 4 turns (including activation turn)
- **All Gens**: Activates even if defender is KOed, but NOT if hit through Substitute
- **All Gens**: Can activate on multi-hit moves before all hits finish
- **Gen 7+**: Blocked by Aroma Veil
- **Implementation Status**: ✅ Implemented (Gen 6+ version)

---

### Cute Charm
- **Gen 3**: 33% chance to infatuate on contact (opposite gender)
- **Gen 4+**: 30% chance to infatuate on contact (opposite gender)
- **Gen 7+**: Blocked by Aroma Veil
- **All Gens**: Each hit of multi-hit move has independent chance
- **Implementation Status**: ✅ Implemented (Gen 4+ version)

---

### Damp
- **Gen 3-6**: Prevents self-destruction moves (Explosion, Self-Destruct)
- **Gen 7+**: Also prevents Aftermath ability from activating
- **Implementation Status**: ✅ Implemented (Gen 7+ with Aftermath blocking)

---

### Defeatist
- **All Gens (5+)**: Halves Attack and Sp. Atk when HP ≤ 1/2
- **Implementation Status**: ✅ Implemented

---

### Defiant
- **All Gens (5+)**: +2 Attack when stats are lowered
- **Gen 8+**: Doesn't activate from self-inflicted stat drops
- **Implementation Status**: ✅ Implemented

---

### Disguise
- **Gen 7**: Blocks first damaging hit, takes 1/8 HP damage
- **Gen 8+**: Same (unchanged)
- **Implementation Status**: ✅ Implemented

---

### Download
- **All Gens (4+)**: Raises Attack or Sp. Atk based on opponent's lower defensive stat
- **Implementation Status**: ✅ Implemented

---

### Drizzle
- **Gen 3-5**: Permanent rain
- **Gen 6+**: Rain lasts 5 turns
- **Implementation Status**: ✅ Implemented (Gen 6+ version)

---

### Drought
- **Gen 3-5**: Permanent sun
- **Gen 6+**: Sun lasts 5 turns
- **Implementation Status**: ✅ Implemented (Gen 6+ version)

---

### Dry Skin
- **Gen 4**: Restores 1/8 HP in rain, loses 1/8 HP in sun, absorbs Water moves (1/4 HP), takes 1.25x Fire damage
- **Gen 5+**: Same (unchanged)
- **Implementation Status**: ✅ Implemented

---

### Early Bird
- **All Gens (3+)**: Sleep duration halved
- **Implementation Status**: ✅ Implemented

---

### Effect Spore
- **Gen 3-4**: 10% chance of status on contact
- **Gen 5+**: 30% chance of status on contact
- **Implementation Status**: ✅ Implemented (Gen 5+ version)

---

### Emergency Exit
- **All Gens (7+)**: Forces switch when HP < 50% from damage
- **Implementation Status**: ✅ Implemented

---

### Filter
- **All Gens (4+)**: 0.75x damage from super-effective moves
- **Implementation Status**: ✅ Implemented

---

### Flame Body
- **All Gens (2+)**: 30% chance to burn on contact
- **Implementation Status**: ✅ Implemented

---

### Flash Fire
- **Gen 3-4**: Absorbs Fire moves, 1.5x Fire power after
- **Gen 5+**: Same (unchanged)
- **Implementation Status**: ✅ Implemented

---

### Flower Gift
- **Gen 4-6**: 1.5x Attack and Sp. Def in sun (for user and allies)
- **Gen 7+**: Same (unchanged)
- **Implementation Status**: ✅ Implemented

---

### Fluffy
- **All Gens (7+)**: Takes 0.5x from contact moves, 2x from Fire moves
- **Implementation Status**: ✅ Implemented

---

### Forecast
- **All Gens (3+)**: Changes type based on weather (Castform only)
- **Implementation Status**: ✅ Implemented

---

### Frisk
- **Gen 4**: Reveals opponent's held item
- **Gen 5+**: Same (unchanged)
- **Implementation Status**: ⏹️ Not Yet

---

### Galvanize
- **Gen 6**: Normal-type moves become Electric-type, 1.3x power
- **Gen 7+**: Power boost reduced to 1.2x
- **Implementation Status**: ✅ Implemented (Gen 7+ version with 1.2x boost)

---

### Guts
- **Gen 3-4**: 1.5x Attack when statused, ignores burn's Attack reduction
- **Gen 5+**: Same (unchanged)
- **Implementation Status**: ✅ Implemented

---

### Harvest
- **Gen 5-6**: 50% chance to restore Berry at end of turn (100% in sun)
- **Gen 7+**: Same (unchanged)
- **Implementation Status**: ⏹️ Not Yet

---

### Huge Power / Pure Power
- **Gen 3-4**: 2x Attack stat, also affects self-inflicted confusion damage
- **Gen 5+**: 2x Attack stat, no longer affects confusion damage
- **Implementation Status**: ✅ FULLY Implemented
  - Stat multiplier: Lines 363-364 in engine.py (`get_effective_stat()`)
  - Confusion damage: Lines 943-956 in engine.py (`check_confusion_self_hit()`)
  - Gen 3-4: Applies 2x to confusion damage
  - Gen 5+: Does NOT apply to confusion damage

---

### Hustle
- **Gen 3-4**: 1.5x Attack, 0.8x accuracy for physical moves
- **Gen 5+**: Same (unchanged)
- **Implementation Status**: ✅ Implemented

---

### Hydration
- **All Gens (4+)**: Heals status conditions in rain at end of turn
- **Implementation Status**: ✅ Implemented

---

### Hyper Cutter
- **Gen 3-7**: Prevents Attack reduction
- **Gen 8+**: Also prevents Attack reduction from Intimidate before battle
- **Implementation Status**: ✅ Implemented

---

### Ice Body
- **All Gens (4+)**: Restores 1/16 HP in hail/snow at end of turn
- **Implementation Status**: ✅ Implemented

---

### Illusion
- **All Gens (5+)**: Disguises as last party member until hit by damaging move
- **Implementation Status**: ✅ Implemented

---

### Immunity
- **All Gens (3+)**: Cannot be poisoned
- **Implementation Status**: ✅ Implemented

---

### Imposter
- **All Gens (5+)**: Transforms into opponent on switch-in
- **Implementation Status**: ✅ Implemented

---

### Infiltrator
- **Gen 5-6**: Bypasses Light Screen, Reflect, Safeguard
- **Gen 7+**: Also bypasses Substitute, Mist, Aurora Veil
- **Implementation Status**: ✅ Implemented (Gen 7+ version)

---

### Intimidate
- **Gen 2-4**: Lowers opponent's Attack by 1 stage on switch-in
- **Gen 5+**: Same (unchanged)
- **Gen 8+**: Blocked by Clear Body, Hyper Cutter, White Smoke, Full Metal Body, etc.
- **Implementation Status**: ✅ Implemented

---

### Iron Barbs
- **All Gens (5+)**: Damages attacker by 1/8 of their max HP on contact
- **Implementation Status**: ✅ Implemented

---

### Iron Fist
- **All Gens (4+)**: 1.2x power for punch moves
- **Implementation Status**: ✅ Implemented

---

### Justified
- **All Gens (5+)**: +1 Attack when hit by Dark-type move
- **Implementation Status**: ✅ Implemented

---

### Keen Eye
- **Gen 3-5**: Prevents accuracy reduction
- **Gen 6+**: Also immune to evasion boosts
- **Gen 7+**: Also ignores opponent's evasion changes
- **Implementation Status**: ✅ Implemented

---

### Levitate
- **All Gens (3+)**: Immune to Ground-type moves
- **Implementation Status**: ✅ Implemented

---

### Libero
- **All Gens (8+)**: Changes type to match move used (once per switch-in)
- **Implementation Status**: ✅ Implemented

---

### Lightning Rod
- **Gen 3-4**: Draws Electric moves to user, immune
- **Gen 5+**: Also raises Sp. Atk by 1 stage when hit
- **Implementation Status**: ✅ Implemented (Gen 5+ version)

---

### Magic Bounce
- **All Gens (5+)**: Reflects status moves back at user
- **Implementation Status**: ✅ Implemented

---

### Magic Guard
- **All Gens (4+)**: Only takes damage from direct attacks
- **Implementation Status**: ✅ Implemented

---

### Magician
- **All Gens (6+)**: Steals opponent's held item on hit (if user has no item)
- **Implementation Status**: ✅ Implemented

---

### Marvel Scale
- **All Gens (3+)**: 1.5x Defense when statused
- **Implementation Status**: ✅ Implemented

---

### Mega Launcher
- **All Gens (6+)**: 1.5x power for pulse, aura, and bomb moves
- **Implementation Status**: ✅ Implemented

---

### Merciless
- **All Gens (7+)**: Always crits poisoned targets
- **Implementation Status**: ✅ Implemented

---

### Mold Breaker
- **All Gens (4+)**: Ignores abilities that would negate or modify moves
- **Implementation Status**: ✅ Implemented

---

### Moody
- **All Gens (4+)**: +2 to random stat, -1 to another random stat at end of turn
- **Implementation Status**: ✅ Implemented

---

### Motor Drive
- **All Gens (4+)**: Immune to Electric, +1 Speed when hit
- **Implementation Status**: ✅ Implemented

---

### Moxie
- **All Gens (5+)**: +1 Attack after KO
- **Implementation Status**: ✅ Implemented

---

### Multiscale
- **All Gens (5+)**: Takes 0.5x damage at full HP
- **Implementation Status**: ✅ Implemented

---

### Natural Cure
- **All Gens (3+)**: Heals status on switch-out
- **Implementation Status**: ✅ Implemented

---

### No Guard
- **All Gens (4+)**: Both user and opponent's moves never miss
- **Implementation Status**: ✅ Implemented

---

### Overgrow
- **All Gens (3+)**: 1.5x Grass-type power when HP ≤ 1/3
- **Implementation Status**: ✅ Implemented

---

### Parental Bond
- **Gen 6**: Second hit is 50% power
- **Gen 7+**: Second hit is 25% power
- **Implementation Status**: ✅ Implemented (Gen 7+ version)

---

### Pickpocket
- **All Gens (5+)**: Steals attacker's item on contact (if user has no item)
- **Implementation Status**: ✅ Implemented

---

### Parental Bond
- **Gen 6**: Most damaging moves hit twice, second hit is 50% power (0.5x)
- **Gen 7+**: Second hit is 25% power (0.25x)
- **Implementation Status**: ✅ FULLY Implemented (lines 3861-3939, 2520-2522, 5255-5256, 5458-5525, 5369-5414 in engine.py)
- **Edge Cases**: ✅ Recoil accumulation (both hits, applied after final strike), ✅ Item stealing timing (Thief/Covet/Bug Bite/Pluck after final strike)

---

### Pastel Veil
- **All Gens (8+)**: Prevents poisoning (works in singles for user immunity)
- **Implementation Status**: ✅ Implemented (lines 190-192 in db_move_effects.py)

---

### Perish Body
- **All Gens (8+)**: When hit by contact move, both Pokemon faint in 3 turns
- **Edge Cases**: 
  - Does NOT activate if attacker already has perish count
  - Does NOT activate if attacker has Protective Pads
  - Does NOT activate if attacker has Long Reach
- **Implementation Status**: ✅ Implemented (lines 2980-3009 in engine.py, uses Perish Song countdown system)

---

### Pickpocket
- **All Gens (5+)**: Steals attacker's item on contact (if user has no item)
- **Implementation Status**: ✅ Implemented (lines 2892-2897 in engine.py, activates BEFORE Magician as per game mechanics)

---

### Pickup
- **Gen 3-4**: No effect in battle
- **Gen 5-8**: Picks up consumed items from other Pokemon at end of turn
- **Gen 9**: Picks up own consumed items at end of turn in wild battles
- **Implementation Status**: ⏹️ TODO

---

### Pixilate
- **Gen 6**: Normal-type moves become Fairy-type, 1.3x power
- **Gen 7+**: Power boost reduced to 1.2x
- **Implementation Status**: ✅ Implemented (lines 1679-1685, 2134-2145 in engine.py)

---

### Plus
- **Gen 3-4**: Boosts Sp. Atk 50% with Minus ally
- **Gen 5+**: Boosts Sp. Atk 50% with Plus OR Minus ally
- **Implementation Status**: ❌ SKIPPED (Double battles only)

---

### Poison Heal
- **All Gens (4+)**: Restores 1/8 HP at end of turn if poisoned (instead of taking damage)
- **Implementation Status**: ✅ Implemented

---

### Poison Point
- **Gen 3**: 33.33% chance (1/3) to poison on contact
- **Gen 4+**: 30% chance to poison on contact
- **Implementation Status**: ✅ Implemented (lines 1373-1380 in engine.py)

---

### Poison Puppeteer
- **All Gens (9+)**: Poisons + confuses when user is Pecharunt
- **Implementation Status**: ✅ No gen differences

---

### Poison Touch
- **Japanese BW**: 20% chance to poison on contact
- **All other versions**: 30% chance to poison on contact
- **Implementation Status**: ❌ SKIPPED (Regional difference, not generation)

---

### Power Construct
- **All Gens (7+)**: Zygarde transforms to Complete Forme at <50% HP
- **Implementation Status**: ✅ No gen differences

---

### Power of Alchemy
- **All Gens (7+)**: Copies fainted ally's ability
- **Implementation Status**: ❌ SKIPPED (Double battles only)

---

### Power Spot
- **All Gens (8+)**: Boosts ally moves by 30%
- **Implementation Status**: ❌ SKIPPED (Double battles only)

---

### Prankster
- **Gen 5**: Status moves +1 priority, not blocked by Quick Guard
- **Gen 6**: Status moves +1 priority, blocked by Quick Guard (double battles)
- **Gen 7+**: Status moves +1 priority, fails vs Dark-types
- **Implementation Status**: ✅ Implemented (Gen 7+ Dark immunity at lines 3613-3629)

---

### Pressure
- **Gen 3-4**: Opponent's moves lose 2 PP instead of 1
- **Gen 5+**: Same (unchanged)
- **Implementation Status**: ✅ Implemented

---

### Protean
- **Gen 6-8**: Changes type to match move used
- **Gen 9+**: Only works once per switch-in
- **Implementation Status**: ✅ Implemented (Gen 9+ version)

---

### Protosynthesis
- **All Gens (9+)**: On switch-in, if harsh sunlight is active or holder has Booster Energy:
  - Boosts highest stat by 1.3x (5325/4096)
  - Activates once per switch-in
  - Booster Energy takes priority over weather
- **Boosted stats**: Attack, Defense, Sp. Atk, Sp. Def, or Speed (highest base stat, excluding HP)
- **Implementation Status**: ✅ Implemented
  - Switch-in activation: lines 3536-3598 in engine.py
  - Stat boost application: lines 377-379 in engine.py (get_effective_stat)
  - Reset on switch: lines 368-370 in panel.py
  - Booster Energy item: lines 240-244 in items.py

---

### Prism Armor
- **All Gens (7+)**: Reduces super-effective damage by 25% (0.75x multiplier)
- **Implementation Status**: ✅ Implemented (lines 2393-2395 in engine.py, same as Filter/Solid Rock)

---

### Punk Rock
- **All Gens (8+)**: 1.3x power for sound moves, 0.5x damage from sound moves
- **Implementation Status**: ✅ Implemented (offensive: lines 2264-2266, defensive: lines 2421-2424 in engine.py)

---

### Purifying Salt
- **All Gens (9+)**: Grants immunity to all status conditions, halves Ghost-type damage
- **Implementation Status**: ✅ Implemented (status immunity at lines 154-157 in db_move_effects.py, Ghost resistance via resist_types in abilities.py)

---

### Quark Drive
- **All Gens (9+)**: On switch-in, if Electric Terrain is active or holder has Booster Energy:
  - Boosts highest stat by 1.3x (5325/4096)
  - Activates once per switch-in
  - Booster Energy takes priority over terrain
- **Boosted stats**: Attack, Defense, Sp. Atk, Sp. Def, or Speed (highest base stat, excluding HP)
- **Implementation Status**: ✅ Implemented
  - Switch-in activation: lines 3536-3598 in engine.py
  - Stat boost application: lines 377-379 in engine.py (get_effective_stat)
  - Reset on switch: lines 368-370 in panel.py
  - Booster Energy item: lines 240-244 in items.py

---

### Queenly Majesty
- **All Gens (7+)**: Blocks priority moves against user and allies
- **Implementation Status**: ✅ Implemented (lines 3006-3009 in engine.py)

---

### Quick Feet
- **Gen 3-4**: 1.5x Speed when statused, paralysis still reduces Speed
- **Gen 5+**: 1.5x Speed when statused, also ignores paralysis Speed reduction
- **Implementation Status**: ✅ Implemented (lines 1296-1313 in engine.py with generation check)

---

### Rain Dish
- **All Gens (3+)**: Restores 1/16 HP in rain at end of turn
- **Implementation Status**: ✅ Implemented

---

### Rattled
- **Gen 5-7**: +1 Speed when hit by Bug/Ghost/Dark move
- **Gen 8+**: Also activates when affected by Intimidate
- **Implementation Status**: ✅ Implemented (lines 2708-2715 for move activation, lines 3313-3318 for Intimidate activation)

---

### Receiver
- **All Gens (5+)**: Copies fainted ally's ability (double battles only)
- **Implementation Status**: ❌ SKIPPED (Double battles only)

---

### Reckless
- **All Gens (4+)**: 1.2x power for recoil moves
- **Implementation Status**: ✅ Implemented (line 2248 in engine.py)

---

### Refrigerate
- **Gen 6**: Normal-type moves become Ice-type, 1.3x power
- **Gen 7+**: Power boost reduced to 1.2x
- **Implementation Status**: ✅ Implemented (lines 1690-1695, 2144-2157 in engine.py with generation check)

---

### Regenerator
- **All Gens (5+)**: Restores 1/3 HP on switch-out
- **Implementation Status**: ✅ Implemented

---

### Ripen
- **All Gens (8+)**: Doubles effects of consumed berries (HP restoration, stat boosts, damage reduction, retaliation damage)
- **Does NOT affect**: Status-curing berries, Lansat Berry crit boost, Micle Berry, Custap Berry
- **Implementation Status**: ✅ Implemented
  - HP berries (Sitrus, Oran): lines 321-335, 349-351 in db_move_effects.py
  - Stat-boosting berries: lines 393-407 in db_move_effects.py
  - Type-resist berries (Occa, etc.): lines 5486-5498 in engine.py
  - Retaliation berries (Rowap, Jaboca): lines 5810-5815 in engine.py

---

### Rivalry
- **Gen 4**: 1.25x power vs. same gender, 0.75x vs. opposite gender, also affects confusion damage
- **Gen 5+**: No longer affects confusion damage
- **Implementation Status**: ✅ Implemented (lines 2249-2256 in engine.py, confusion damage system not yet in place)

---

### Rock Head
- **All Gens (2+)**: Negates recoil damage
- **Implementation Status**: ✅ Implemented

---

### Rough Skin
- **Gen 3-4**: Damages attacker by 1/16 of their max HP on contact
- **Gen 5+**: Damages attacker by 1/8 of their max HP on contact
- **Implementation Status**: ✅ Implemented (lines 1426-1433 in engine.py with generation check)

---

### Sand Force
- **All Gens (5+)**: 1.3x power for Rock, Ground, Steel moves in sandstorm
- **Implementation Status**: ✅ Implemented

---

### Sand Rush
- **All Gens (5+)**: 2x Speed in sandstorm
- **Implementation Status**: ✅ Implemented

---

### Sand Stream
- **Gen 3-5**: Permanent sandstorm
- **Gen 6+**: Sandstorm lasts 5 turns
- **Implementation Status**: ✅ Implemented (Gen 6+ version)

---

### Sand Veil
- **All Gens (3+)**: 1.25x evasion in sandstorm
- **Implementation Status**: ✅ Implemented

---

### Sap Sipper
- **All Gens (5+)**: Immune to Grass, +1 Attack when hit
- **Implementation Status**: ✅ Implemented

---

### Scrappy
- **Gen 4-6**: Can hit Ghost with Normal and Fighting moves
- **Gen 7+**: Also blocks Intimidate
- **Implementation Status**: ✅ Implemented (lines 1116-1124 for Ghost immunity bypass, lines 3273-3275 for Intimidate blocking)

---

### Serene Grace
- **All Gens (3+)**: 2x chance for move's secondary effects
- **Implementation Status**: ✅ Implemented

---

### Shadow Tag
- **All Gens (3+)**: Prevents opponents from fleeing or switching
- **Gen 4+**: Doesn't work against other Shadow Tag
- **Implementation Status**: ⏹️ Not Yet

---

### Sheer Force
- **Gen 5**: 1.3x power, removes secondary effects
- **Gen 6+**: Same (unchanged)
- **Implementation Status**: ✅ Implemented

---

### Shed Skin
- **Gen 3**: 1/3 (33.33%) chance to heal status at end of turn
- **Gen 4**: 30% chance to heal status at end of turn
- **Gen 5+**: 1/3 (33.33%) chance to heal status at end of turn
- **Implementation Status**: ✅ Implemented (engine.py lines 770-790)
- **Note**: Heals status BEFORE burn/poison damage on that turn

---

### Shell Armor
- **All Gens (3+)**: Prevents critical hits
- **Implementation Status**: ✅ Implemented

---

### Sharpness
- **Gen 9**: Boosts slicing moves by 50% (1.5x power)
- **Affected Moves**: Aerial Ace, Air Cutter, Air Slash, Aqua Cutter, Behemoth Blade, Bitter Blade, Ceaseless Edge, Cross Poison, Cut, Fury Cutter, Kowtow Cleave, Leaf Blade, Mighty Cleave, Night Slash, Population Bomb, Psycho Cut, Psyblade, Razor Leaf, Razor Shell, Sacred Sword, Secret Sword, Slash, Solar Blade, Stone Axe, Tachyon Cutter, X-Scissor
- **Implementation Status**: ✅ Implemented (engine.py lines 2410-2419)

---

### Shield Dust
- **All Gens (3+)**: Immune to additional effects of damaging moves
- **Implementation Status**: ✅ Implemented

---

### Simple
- **All Gens (4+)**: Stat changes are doubled
- **Implementation Status**: ✅ Implemented

---

### Skill Link
- **Gen 4**: Multi-hit moves always hit maximum times
- **Gen 5+**: Same (unchanged)
- **Implementation Status**: ✅ Implemented

---

### Slow Start
- **All Gens (4+)**: Attack and Speed halved for 5 turns
- **Implementation Status**: ✅ Implemented

---

### Slush Rush
- **All Gens (7+)**: 2x Speed in hail/snow
- **Implementation Status**: ✅ Implemented

---

### Sniper
- **Gen 4-6**: 1.5x damage on critical hits (total 2.25x)
- **Gen 7+**: Same (unchanged)
- **Implementation Status**: ✅ Implemented

---

### Snow Cloak
- **All Gens (4+)**: 1.25x evasion in hail/snow
- **Implementation Status**: ✅ Implemented

---

### Snow Warning
- **Gen 4-5**: Permanent hail
- **Gen 6-8**: Hail lasts 5 turns
- **Gen 9+**: Sets snow (infinite, no damage)
- **Implementation Status**: ✅ Implemented (Gen 6-8 version)

---

### Solar Power
- **All Gens (4+)**: 1.5x Sp. Atk in sun, loses 1/8 HP per turn
- **Implementation Status**: ✅ Implemented

---

### Solid Rock
- **All Gens (4+)**: 0.75x damage from super-effective moves
- **Implementation Status**: ✅ Implemented

---

### Speed Boost
- **All Gens (3+)**: +1 Speed at end of each turn
- **Gen 5+**: Doesn't activate on switch-in turn (except if forced in due to faint)
- **Implementation Status**: ✅ Implemented (Gen 5+ version)

---

### Stance Change
- **All Gens (6+)**: Changes form based on attack/King's Shield
- **Implementation Status**: ✅ Implemented

---

### Static
- **All Gens (3+)**: 30% chance to paralyze on contact
- **Implementation Status**: ✅ Implemented

---

### Steadfast
- **All Gens (4+)**: +1 Speed when flinched
- **Implementation Status**: ✅ Implemented

---

### Storm Drain
- **Gen 3-4**: Draws Water moves to user, immune
- **Gen 5+**: Also raises Sp. Atk by 1 stage when hit
- **Implementation Status**: ✅ Implemented (Gen 5+ version)

---

### Strong Jaw
- **All Gens (6+)**: 1.5x power for biting moves
- **Implementation Status**: ✅ Implemented

---

### Sturdy
- **Gen 3-4**: Immune to OHKO moves
- **Gen 5+**: Also survives with 1 HP if hit at full HP
- **Implementation Status**: ✅ Implemented (Gen 5+ version)

---

### Swarm
- **All Gens (3+)**: 1.5x Bug-type power when HP ≤ 1/3
- **Implementation Status**: ✅ Implemented

---

### Swift Swim
- **All Gens (3+)**: 2x Speed in rain
- **Implementation Status**: ✅ Implemented

---

### Synchronize
- **All Gens (3+)**: Passes burn, poison, paralysis to opponent
- **Implementation Status**: ✅ Implemented

---

### Technician
- **All Gens (4+)**: 1.5x power for moves with base power ≤ 60
- **Implementation Status**: ✅ Implemented

---

### Thick Fat
- **All Gens (2+)**: 0.5x damage from Fire and Ice moves
- **Implementation Status**: ✅ Implemented

---

### Tinted Lens
- **All Gens (4+)**: Not very effective moves deal 2x damage instead
- **Implementation Status**: ✅ Implemented

---

### Torrent
- **All Gens (3+)**: 1.5x Water-type power when HP ≤ 1/3
- **Implementation Status**: ✅ Implemented

---

### Tough Claws
- **All Gens (6+)**: 1.3x power for contact moves
- **Implementation Status**: ✅ Implemented

---

### Trace
- **All Gens (3+)**: Copies opponent's ability on switch-in
- **NOT A GENERATION DIFFERENCE**: The list of uncopyable abilities just grew over time as new abilities were introduced (Multitype, Battle Bond, Disguise, etc.). The mechanic itself never changed.
- **Implementation Status**: ✅ Implemented (lines 3370-3382 in engine.py)

---

### Natural Cure
- **Gen 3**: Heals status on switch-out
- **Gen 4-7**: Also heals status after battle ends (out of PVP scope)
- **Gen 8+**: No longer heals after battle (out of PVP scope)
- **Implementation Status**: ✅ Implemented (switch-out healing works)

----

### Neuroforce
- **All Gens (7+)**: 25% more damage with super-effective moves
- **Implementation Status**: ✅ Implemented

----

### Neutralizing Gas
- **All Gens (8+)**: Suppresses abilities
- **Implementation Status**: ✅ Implemented

----

### No Guard
- **All Gens (4+)**: All moves used by or against a Pokémon with No Guard cannot miss
- **All Gens (4+)**: Bypasses semi-invulnerable turns (Fly, Dig, Dive, etc.)
- **Gen 4 (Diamond/Pearl)**: Bug where moves with <100% accuracy could break through Protect/Detect (NOT implementing this bug)
- **Gen 4 (Platinum)+**: Bug fixed, Protect/Detect work normally
- **Implementation Status**: ✅ Implemented (perfect accuracy + invulnerability bypass, lines 1485-1524)

----

### Normalize
- **Gen 4**: Hidden Power, Weather Ball, Natural Gift, Judgment affected by Normalize
- **Gen 5-6**: Those moves NOT affected by Normalize
- **Gen 7+**: Normal-type moves get 20% power boost (4915/4096)
- **Implementation Status**: ✅ Implemented (Gen 7+ power boost added, lines 2138-2148)

----

### Oblivious
- **Gen 3-5**: Only prevents infatuation and Captivate
- **Gen 6-7**: Also prevents Taunt
- **Gen 8+**: Also blocks Intimidate
- **Implementation Status**: ✅ Implemented (Gen 8+ Intimidate blocking, lines 3237-3239)

----

### Opportunist
- **All Gens (9+)**: Copies opponent's stat boosts
- **Implementation Status**: ✅ Implemented

----

### Orichalcum Pulse
- **All Gens (9+)**: Summons sun, boosts Attack in sun
- **Implementation Status**: ✅ Implemented

----

### Overcoat
- **Gen 5**: Protects from sandstorm and hailstorm only
- **Gen 6+**: Also protects from powder/spore moves and Effect Spore
- **Implementation Status**: ✅ Implemented (weather immunity in apply_status_effects, Effect Spore blocking at lines 1400-1403, powder move immunity at lines 3727-3731)

----

### Overgrow
- **Gen 3-4**: 50% power boost to Grass moves at low HP
- **Gen 5+**: 50% Attack/Sp. Atk boost during calculation (same effect)
- **Implementation Status**: ✅ Implemented (functionally identical across gens)

----

### Own Tempo
- **Gen 3-7**: Only prevents confusion
- **Gen 8+**: Also blocks Intimidate
- **Implementation Status**: ✅ Implemented (Gen 8+ Intimidate blocking, lines 3237-3239)

----

### Unaware
- **All Gens (4+)**: Ignores opponent's stat changes
- **Implementation Status**: ✅ Implemented

---

### Unburden
- **All Gens (4+)**: 2x Speed after consuming held item
- **Implementation Status**: ✅ Implemented

---

### Volt Absorb
- **All Gens (3+)**: Immune to Electric, restores 1/4 HP when hit
- **Implementation Status**: ✅ Implemented

---

### Water Absorb
- **All Gens (3+)**: Immune to Water, restores 1/4 HP when hit
- **Implementation Status**: ✅ Implemented

---

### Water Bubble
- **All Gens (7+)**: 2x Water power, 0.5x Fire damage, cannot be burned
- **Implementation Status**: ✅ Implemented

---

### Weak Armor
- **Gen 5**: -1 Defense, +1 Speed when hit by physical move
- **Gen 6+**: -1 Defense, +2 Speed when hit by physical move
- **Implementation Status**: ✅ Implemented (Gen 6+ version)

---

### White Smoke
- **All Gens (3+)**: Prevents stat reduction
- **Implementation Status**: ✅ Implemented

---

### Wimp Out
- **All Gens (7+)**: Forces switch when HP < 50% from damage
- **Implementation Status**: ✅ Implemented

---

### Wonder Guard
- **All Gens (3+)**: Only super-effective moves hit
- **Implementation Status**: ✅ Implemented

---

### Zen Mode
- **All Gens (5+)**: Changes form when HP ≤ 50%
- **Implementation Status**: ✅ Implemented

---

### Leaf Guard
- **Gen 3-4**: Only prevents status conditions from moves during harsh sunlight
- **Gen 5+**: Also prevents status from Rest during harsh sunlight
- **Gen 6**: Cures existing status conditions when harsh sunlight begins (removed in Gen 7)
- **Gen 7+**: Reverted to Gen 5 behavior (only prevents, doesn't cure)
- **Implementation Status**: ✅ Implemented (Gen 7+ behavior - prevents status in sun)

---

### Liquid Ooze
- **All Gens (3+)**: Reverses HP drain moves (damages attacker instead of healing)
- **No generation differences**
- **Implementation Status**: ✅ Implemented

---

### Liquid Voice
- **Gen 7+**: All sound-based moves become Water-type and receive STAB bonus
- **Does not receive Aerilate/Pixilate-style power boost**
- **Implementation Status**: ✅ Implemented

---

### Long Reach
- **Gen 7+**: Contact moves used by the Pokémon do not make contact with the target
- **Prevents contact-based effects** (Static, Flame Body, Rocky Helmet, etc.)
- **Does not affect type effectiveness**
- **Implementation Status**: ✅ Implemented

---

### Ice Body
- **Gen 4**: Heals 1/16 max HP in hail
- **Gen 9+**: Also works in snow (renamed weather)
- **Implementation Status**: ✅ Implemented

---

### Ice Face
- **Gen 8+**: Ice Face form takes 0 damage from physical moves, then breaks
- **Hail/Snow**: Restores Ice Face form at end of turn
- **Implementation Status**: ✅ Implemented

---

### Ice Scales
- **Gen 8+**: Halves damage from special moves
- **Implementation Status**: ✅ Implemented

---

### Illusion
- **Gen 5**: Disguises as last party member, breaks when hit by damaging move
- **Gen 6+**: Also breaks when hit by status moves that cause damage
- **Gen 7+**: Breaks on any damaging hit
- **Implementation Status**: ✅ Implemented

---

### Immunity
- **All Gens (3+)**: Prevents poison status, cures existing poison on switch-in
- **Implementation Status**: ✅ Implemented (prevention only)

---

### Imposter
- **Gen 5**: Transforms into opponent on switch-in, COPIES stat stages
- **Gen 6+**: Doesn't copy stat stages (resets to 0)
- **Implementation Status**: ✅ Implemented (Gen 5 vs Gen 6+ stat stage handling)

---

### Infiltrator
- **Gen 5**: Ignores Reflect, Light Screen, Safeguard
- **Gen 6+**: Also ignores Substitute
- **Gen 7+**: Also ignores Aurora Veil
- **Implementation Status**: ✅ Implemented

---

### Innards Out
- **Gen 7+**: Deals damage equal to HP lost when KO'd
- **Implementation Status**: ✅ Implemented

---

### Inner Focus
- **Gen 3-4**: Prevents flinching
- **Gen 5-7**: Also prevents Intimidate
- **Gen 8+**: Intimidate immunity removed
- **Implementation Status**: ✅ Implemented (flinch immunity only)

---

### Insomnia
- **All Gens (3+)**: Prevents sleep status
- **Implementation Status**: ✅ Implemented

---

### Intimidate
- **Gen 2**: Lowers Attack on switch-in
- **Gen 3+**: Can be blocked by certain abilities
- **Gen 8+**: Reversed by Guard Dog
- **Implementation Status**: ✅ Implemented

---

### Intrepid Sword
- **Gen 8**: Raises Attack on every switch-in
- **Gen 9+**: Only activates once per battle
- **Implementation Status**: ✅ Implemented (Gen 9+)

---

### Iron Barbs
- **Gen 5+**: Deals 1/8 attacker's max HP on contact
- **Implementation Status**: ✅ Implemented

---

### Iron Fist
- **Gen 4+**: 1.2x boost to punching moves
- **Implementation Status**: ✅ Implemented

---

### Justified
- **Gen 5+**: Raises Attack when hit by Dark-type
- **Implementation Status**: ✅ Implemented

---

### Keen Eye
- **Gen 3-6**: Prevents accuracy reduction
- **Gen 7+**: Also ignores evasion boosts
- **Implementation Status**: ✅ Implemented

---

### Klutz
- **Gen 4+**: Prevents held item effects
- **Implementation Status**: ✅ Implemented

---

### Levitate
- **All Gens (3+)**: Immune to Ground-type moves
- **Gen 4+**: Immune to hazards
- **Implementation Status**: ✅ Implemented

---

### Libero
- **Gen 8**: Changes type every move
- **Gen 9+**: Only once per switch-in
- **Implementation Status**: ✅ Implemented (Gen 8 behavior)

---

### Light Metal
- **Gen 4+**: Halves weight
- **Implementation Status**: ✅ Implemented

---

### Lightning Rod
- **Gen 3-4**: Draws Electric-type moves
- **Gen 5+**: Draws Electric + immunity + Sp. Atk boost
- **Implementation Status**: ✅ Implemented (Gen 5+)

---

### Limber
- **All Gens (3+)**: Prevents paralysis
- **Implementation Status**: ✅ Implemented

---

## Summary

**Total Abilities Documented**: ~165 (more to add)
**Fully Implemented**: ~155 (94%)
**Needs Implementation**: ~10 (Shield Dust, Shields Down, Soul Heart, etc.)
**Gen-Specific Adjustments Needed**: All major generation differences implemented

---

## TODO: Implement Generation Checking

Add to `pvp/engine.py` or relevant files:
```python
def get_ability_behavior(ability_name: str, generation: int) -> Dict[str, Any]:
    """
    Returns generation-specific ability behavior.
    
    Example:
    >>> get_ability_behavior("aerilate", 6)
    {"power_mult": 1.3, "converts_to": "Flying"}
    >>> get_ability_behavior("aerilate", 7)
    {"power_mult": 1.2, "converts_to": "Flying"}
    """
    # TODO: Implement this function
    pass
```

---

## Notes

- Most abilities have remained consistent across generations
- Major changes occurred in Gen 5 (many ability buffs) and Gen 7 (Prankster nerf, -ate ability nerfs)
- Gen 9 introduced nerfs to Protean/Libero and Terastallization mechanics
- Weather abilities changed in Gen 6 (permanent → 5 turns)


### Wind Power
- **All Gens (9+)**: Gets Charged when hit by wind move or Tailwind; next Electric move 2x power
- **Wind Moves (17)**: Aeroblast, Air Cutter, Bleakwind Storm, Blizzard, Fairy Wind, Gust, Heat Wave, Hurricane, Icy Wind, Petal Blizzard, Sandsear Storm, Springtide Storm, Tailwind, Twister, Whirlwind, Wildbolt Storm
- **NOT Sandstorm** (targets field)
- **Implementation Status**: âœ… Implemented

---

### Wind Rider
- **All Gens (9+)**: Immune to 17 wind moves (not Sandstorm), +1 Attack when hit or Tailwind activates
- **Implementation Status**: âœ… Implemented

---

### Wonder Skin
- **All Gens (5+)**: Status moves become 50% accurate (if > 50%)
- **Implementation Status**: âœ… Implemented

---

### Zero to Hero
- **All Gens (9+)**: Palafin switches to Hero Form after first switch out (not fainting)
- **Implementation Status**: âœ… Implemented

---



