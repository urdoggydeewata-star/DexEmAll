"""
Terastallization and type helpers - extracted from pokebot.py.
"""
from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from typing import Any

VALID_TERA_TYPES: tuple[str, ...] = (
    "normal", "fire", "water", "electric", "grass", "ice",
    "fighting", "poison", "ground", "flying", "psychic", "bug",
    "rock", "ghost", "dragon", "dark", "steel", "fairy", "stellar"
)


def normalize_type_id(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip().lower()
    s = s.replace("type", "").replace("_", "-").replace(" ", "-")
    return s or None


def extract_species_types(entry: Mapping[str, Any]) -> list[str]:
    import json
    raw = entry.get("types")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = [raw]
    if raw is None:
        return []
    types: list[str] = []
    for item in raw:
        norm = normalize_type_id(item)
        if norm and norm not in types:
            types.append(norm)
    return types


def roll_default_tera_type(types: Sequence[str]) -> str | None:
    if not types:
        return None
    return random.choice(list(types))
