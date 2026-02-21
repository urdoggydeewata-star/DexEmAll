# Pokebot Refactoring Guide

This document tracks the modular refactoring of `pokebot.py` (~29K lines) into smaller, manageable modules.

## Completed Extractions

### 1. `bot_core/` package
- **bot_core/config.py** – Env vars, owner settings, verification IDs (~55 lines)
- **bot_core/tera_helpers.py** – `_normalize_type_id`, `_extract_species_types`, `_roll_default_tera_type` (~55 lines)
- **bot_core/ball_helpers.py** – Ball normalization, friend/heal/luxury checks, `_caught_friendship_for_ball`, `_friendship_delta_with_ball_bonus` (~80 lines)

### 2. `pvp/` package
- **pvp/panel_capture.py** – Balls, healing items, `_ball_multiplier`, `_attempt_capture`, `status_bonus` (~310 lines). Reduces panel.py below 10k.

### 3. `features/` package
- **features/route_loot.py** – GEN1_TMS/HMS, TM_SELLER_*, ROUTE_MOVE_* tables, weighted_choice, roll_route_ball_by_absolute_rate, route_pick_item_from_pool (~250 lines). Route ball rates adjusted ÷10 (rarer).
- **features/adventure_constants.py** – ASSETS_*, DAYCARE_*, BOX_*, paths and daycare constants (~75 lines)

## Recommended Next Phases

### Phase 2: Core utilities
Extract to `bot_core/`:
- **db_helpers.py** – `_ensure_pg_pokemons_columns`, `_pg_pokemons_column_flags`, `_tx_begin/commit/rollback`, `_wipe_user`, `_wipe_all`
- **item_helpers.py** – `_canonical_item_token`, `_item_index`, `_resolve_item_fuzzy`, `_bag_adjust_conn`, `_count_item_in_use`, `_get_usage`, etc.
- **fuzzy.py** – `FuzzyMatcher`, `_fuzzy_best`, `resolve_team_mon`, `_resolve_team_mon_for_owner_id`

### Phase 3: Cogs (Discord commands)
Extract to `cogs/` (or `bot_core/cogs/`):
- **admin.py** – `AdminItems`, `AdminGivePokemon`, owner-only commands
- **bag.py** – `give_item`, `take`, `item` commands, `BuyItemView`, `ItemsView`
- **mpokeinfo.py** – `MPokeInfo` cog, `_MPokeInfoFlipView`

### Phase 4: Features
Extract to `features/`:
- **adventure.py** – Adventure routes, panels, maze, `AdventureRouteView`, `_send_adventure_panel`
- **daycare.py** – Daycare logic, `_daycare_*` functions, `AdventureDaycareView`
- **box.py** – Box/PC logic, `_box_*` functions, `BoxMainView`, `BoxPkModal`

### Phase 5: Battle / PvE
- **pve.py** – `_start_pve_battle`, `_award_exp_to_party`, `_run_rival_battle`, etc.

## Import Pattern
When extracting, use re-exports to avoid changing many call sites:
```python
# In pokebot.py
from bot_core.tera_helpers import extract_species_types as _extract_species_types
```

## Testing
After each extraction:
1. `python3 -m py_compile pokebot.py`
2. Run the bot and smoke-test key commands
3. Commit in small increments
