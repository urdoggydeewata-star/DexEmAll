from __future__ import annotations
from pathlib import Path
from typing import Optional

# Root: pvp/_common/sprites/<species>/
BASE_SPRITES_DIR = Path(__file__).resolve().parent / "_common" / "sprites"

def _norm_species(name: str) -> str:
    s = (name or "").strip().lower()
    # normalize typical names to folder naming convention
    for ch in [" ", ".", "'", ":", "é", "♀", "♂", "’"]:
        s = s.replace(ch, "-")
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-")

# File priority for a given perspective (front/back)
# We try from most specific → least specific
def _candidates(persp: str, shiny: bool, female: bool, prefer_animated: bool) -> list[str]:
    anim = "animated"
    combos: list[str] = []
    
    # Only try shiny/female sprites if the Pokémon actually has those attributes
    if prefer_animated:
        # Try animated versions first
        if shiny and female:
            combos += [f"female-{anim}-shiny-{persp}.gif"]
        elif shiny:
            combos += [f"{anim}-shiny-{persp}.gif"]
        elif female:
            combos += [f"female-{anim}-{persp}.gif"]
        else:
            # Non-shiny, non-female animated
            combos += [f"{anim}-{persp}.gif"]
    
    # Static sprites
    if shiny and female:
        combos += [f"female-shiny-{persp}.png"]
    elif shiny:
        combos += [f"shiny-{persp}.png"]
    elif female:
        combos += [f"female-{persp}.png"]
    
    # Always fall back to default sprite
    combos += [f"{persp}.png"]
    
    return combos

def find_sprite(
    species: str,
    *,
    gen: int,                     # unused for this layout, kept for API compat
    perspective: str,             # "front" or "back"
    shiny: bool,
    female: bool,
    prefer_animated: bool = True,
    form: Optional[str] = None,   # Form name (e.g., "shield", "blade", "disguised", "busted", or "shaymin-sky")
) -> Optional[Path]:
    """Return the best-matching sprite file for your on-disk layout, or None.
    
    If form is provided, will try species-form first (e.g., "aegislash-shield"),
    then fall back to base species if not found.
    
    Handles both short forms ("sky") and full forms ("shaymin-sky").
    """
    # Try form-specific folder first if form is provided
    if form:
        norm_species = _norm_species(species)
        norm_form = _norm_species(form)
        
        # Special handling for Ash Greninja - try "greninja-battle-bond" folder name
        if norm_form == "ash" and norm_species == "greninja":
            # Try "greninja-battle-bond" first (actual folder name)
            form_species_candidates = ["greninja-battle-bond", "ash-greninja", "greninja-ash"]
            for candidate in form_species_candidates:
                form_folder = BASE_SPRITES_DIR / candidate
                if form_folder.exists():
                    for fn in _candidates(perspective, shiny, female, prefer_animated):
                        p = form_folder / fn
                        if p.exists():
                            return p
                    # last-resort: any gif/png in form folder matching perspective
                    for p in list(form_folder.glob(f"*{perspective}.gif")) + list(form_folder.glob(f"*{perspective}.png")):
                        if p.is_file():
                            return p
        # Special handling for Missing n0 forms - use "missing-n0-{form}" or "missing-no-{form}" folder structure
        # Use static sprites if animated aren't present, but NO fallback to base species
        elif norm_species == "missing-n0" and norm_form in ["n0", "n1", "n2", "n3", "n4", "n5"]:
            # Try both "missing-n0-{form}" and "missing-no-{form}" folder names (inconsistent naming)
            # n0 form uses base "missing-n0" folder, n1 uses "missing-n0-n1", n2-n5 use "missing-no-{form}"
            if norm_form == "n0":
                # n0 form (Untyped) uses the base folder
                form_folder = BASE_SPRITES_DIR / norm_species  # missing-n0
            elif norm_form == "n1":
                form_folder = BASE_SPRITES_DIR / f"{norm_species}-{norm_form}"  # missing-n0-n1
            else:
                # n2-n5 use "missing-no-{form}" instead of "missing-n0-{form}"
                form_folder = BASE_SPRITES_DIR / f"missing-no-{norm_form}"  # missing-no-n2, etc.
            
            if form_folder.exists():
                # Try animated first if prefer_animated is True
                if prefer_animated:
                    for fn in _candidates(perspective, shiny, female, prefer_animated=True):
                        p = form_folder / fn
                        if p.exists():
                            return p
                    # If no animated sprites found, try static sprites
                    for fn in _candidates(perspective, shiny, female, prefer_animated=False):
                        p = form_folder / fn
                        if p.exists():
                            return p
                else:
                    # If prefer_animated is False, just try static
                    for fn in _candidates(perspective, shiny, female, prefer_animated=False):
                        p = form_folder / fn
                        if p.exists():
                            return p
                # last-resort: any gif/png in form folder matching perspective
                for p in list(form_folder.glob(f"*{perspective}.gif")) + list(form_folder.glob(f"*{perspective}.png")):
                    if p.is_file():
                        return p
            # NO FALLBACK to base species for Missing n0 - return None if form-specific sprite not found
            return None
        else:
            # Standard form handling: {species}-{form} folder pattern
            # Examples: shaymin-sky, shaymin-land, wishiwashi-school, wishiwashi-solo
            # If form already includes species name (e.g., "shaymin-sky"), use as-is
            # Otherwise prepend species (e.g., "sky" → "shaymin-sky")
            if norm_form.startswith(f"{norm_species}-"):
                form_folder_name = norm_form
            else:
                form_folder_name = f"{norm_species}-{norm_form}"
            form_folder = BASE_SPRITES_DIR / form_folder_name
            if form_folder.exists():
                for fn in _candidates(perspective, shiny, female, prefer_animated):
                    p = form_folder / fn
                    if p.exists():
                        return p
                # last-resort: any gif/png in form folder matching perspective
                for p in list(form_folder.glob(f"*{perspective}.gif")) + list(form_folder.glob(f"*{perspective}.png")):
                    if p.is_file():
                        return p
            # If form folder doesn't exist, continue to fall back to base species folder below
    
    # Fall back to base species folder
    folder = BASE_SPRITES_DIR / _norm_species(species)
    if not folder.exists():
        return None

    for fn in _candidates(perspective, shiny, female, prefer_animated):
        p = folder / fn
        if p.exists():
            return p

    # last-resort: any gif/png in folder matching perspective
    for p in list(folder.glob(f"*{perspective}.gif")) + list(folder.glob(f"*{perspective}.png")):
        if p.is_file():
            return p
    return None