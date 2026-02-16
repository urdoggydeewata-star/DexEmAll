from dataclasses import dataclass

@dataclass(frozen=True)
class GenerationRules:
    gen: int
    # Baseline mechanics that accumulate by generation
    physical_special_split: bool  # Gen4+
    fairy_type: bool              # Gen6+
    # Gimmicks (see policy below)
    allow_megas: bool             # Gen6 + Gen7 (per your exception)
    allow_z_moves: bool           # Gen7 only
    allow_dynamax: bool           # Gen8 only
    allow_terastal: bool          # Gen9 only
    # Regional forms availability
    allow_alolan: bool            # Gen7+
    allow_galarian: bool          # Gen8+
    allow_hisuian: bool           # Gen8-era
    allow_paldean: bool           # Gen9+
    # Which gen’s mechanics baseline to use for legality/stats
    mechanics_baseline: int

# Accumulate through Gen6; then one gimmick per gen — with your **Mega exception for Gen7**.
GEN_RULES: dict[int, GenerationRules] = {
    1: GenerationRules(1, False, False, False, False, False, False, False, False, False, False, mechanics_baseline=1),
    2: GenerationRules(2, False, False, False, False, False, False, False, False, False, False, mechanics_baseline=2),
    3: GenerationRules(3, False, False, False, False, False, False, False, False, False, False, mechanics_baseline=3),
    4: GenerationRules(4, True,  False, False, False, False, False, False, False, False, False, mechanics_baseline=4),
    5: GenerationRules(5, True,  False, False, False, False, False, False, False, False, False, mechanics_baseline=5),
    # Gen6: Fairy + Mega
    6: GenerationRules(6, True,  True,  True,  False, False, False, False, False, False, False, mechanics_baseline=6),
    # Gen7: Z-Moves + (your exception) Megas still usable
    7: GenerationRules(7, True,  True,  True,  True,  False, False, True,  False, False, False, mechanics_baseline=7),
    # Gen8: Dynamax only (no Mega, no Z)
    8: GenerationRules(8, True,  True,  False, False, True,  False, True,  True,  True,  False, mechanics_baseline=8),
    # Gen9: Terastallization only
    9: GenerationRules(9, True,  True,  False, False, False, True,  True,  True,  True,  True,  mechanics_baseline=9),
}

def rules_for(gen: int) -> GenerationRules:
    gen = max(1, min(9, int(gen)))
    return GEN_RULES[gen]

# ---------- Helpers ----------
def mega_allowed_in_gen(gen: int) -> bool:
    """Megas are allowed through Gen7 (6 and 7). Not allowed in Gen8+."""
    return 1 <= gen <= 7  # effect-wise; you still need the bracelet unlock (handled outside)

def gimmick_from_item_id(item_id: str | None) -> str | None:
    """
    Map an item/gear id to a gimmick tag: 'mega' | 'z' | 'dmax' | 'tera' | None.
    Accepts ids like 'ampharosite', 'firium_z', 'tera_orb', or names ('Mega Bracelet', etc.).
    """
    if not item_id:
        return None
    s = str(item_id).lower().replace(" ", "_").replace("-", "_")
    if s.endswith("ite") or "key_stone" in s or "mega_bracelet" in s or "mega_ring" in s:
        return "mega"
    if s.endswith("_z") or "z_ring" in s or "z_power_ring" in s:
        return "z"
    if "dynamax" in s or s.startswith("max_") or "max_band" in s:
        return "dmax"
    if "tera_orb" in s or "terastal_orb" in s:
        return "tera"
    return None

def gimmick_allowed_in_gen(gen: int, item_id: str | None) -> bool:
    """
    Item-level gating (useful if you still want to guard e.g. Z-Crystals).
    Mega allowed through Gen7 (per your exception). Z only Gen7. Dynamax only Gen8. Tera only Gen9.
    """
    g = rules_for(gen)
    gimmick = gimmick_from_item_id(item_id)
    if gimmick is None:
        return True
    return (
        (gimmick == "mega" and mega_allowed_in_gen(gen) and g.allow_megas) or
        (gimmick == "z"    and g.allow_z_moves) or
        (gimmick == "dmax" and g.allow_dynamax) or
        (gimmick == "tera" and g.allow_terastal)
    )