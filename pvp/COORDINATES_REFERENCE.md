# Battle render coordinates reference

All coordinates are in **PSD space (1536×1024)**. They are scaled to the canvas with `scale_x = canvas_w/1536`, `scale_y = canvas_h/1024`. Use `scale_pos(psd_x, psd_y)` to get pixel position.

**File:** `pvp/renderer.py`

---

## Sprites (your Pokémon = back, opponent = front)

| Element      | PSD (x, y) | Line in file |
|-------------|------------|--------------|
| Back sprite | (150, 647) | ~1300        |
| Front sprite| (1100, 380)| ~1301        |

Dynamax: Y offset applied (sprites move up). Scale is applied in the same block.

---

## HP and EXP bars (drawn in GIF render loop)

| Element       | PSD position / size              | Line in file |
|---------------|----------------------------------|--------------|
| **My HP bar** | position (1196, 745), width 289  | 1338–1339    |
| **My EXP bar**| same x as My HP bar; y = my_hp_bar_y + 15×scale_y + 2×scale_y (height 15, gap 2) | 1342–1348    |
| **Opp HP bar**| position (67, 237), width 295    | 1350–1351    |

- My HP bar height (for layout): `15 * scale_y` (line ~1343).
- EXP bar gap below HP bar: `2 * scale_y` (line ~1344).
- **Full-scale EXP bar for layout:** set env `EXP_BAR_FULL_SCALE=1` so the EXP bar always draws at 100% width for positioning; use `0` (default) for real EXP fill.

---

## UI elements in `_draw_ui_elements()` (names, level, HP text, balls)

| Element         | PSD (x, y) or note     | Line in file |
|-----------------|------------------------|--------------|
| **My name**     | (950, 700)             | 892          |
| **My level**    | (1420, 710)            | 922          |
| **My HP text** | (1098, 785)            | 931          |
| **My balls**   | start (958, 850), spacing 72 | 940–941  |
| **Opp name**   | (49, 190)              | 988          |
| **Opp level**  | (525, 200)             | 1018         |
| **Opp balls**  | start (40, 240), spacing 72   | 1028–1029 |

Icon positions (mega/dynamax/status) are derived from name position + text width in the same function.

---

## Scale helper

- `scale_pos(psd_x, psd_y)` is defined in the GIF render block at ~1335 and inside `_draw_ui_elements` at 806. Both use the same formula: `(int(psd_x * scale_x), int(psd_y * scale_y))`.

**Resize EXP bar:**
- **Width:** In the EXP bar block (~1346–1350), change the `289` in `exp_bar_width = int(289 * scale_x)` (smaller = narrower, larger = wider; PSD-space).
- **Height:** In `_draw_exp_bar()` (~line 547), change `base_height = 10` (e.g. 12 or 14 for a taller bar).

To move the EXP bar: edit the EXP bar block (~1342–1350)—change `my_hp_bar_x`, `my_exp_bar_y`, or `exp_bar_width` (or the gap/height constants) as needed.
