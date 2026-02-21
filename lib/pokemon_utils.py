"""Shared Pokémon-related helpers used by daycare, battle, and other features."""
from __future__ import annotations

import json
import random
from typing import Any, Optional

STAT_KEYS_SHORT = ("hp", "atk", "defn", "spa", "spd", "spe")
_STAT_KEYS_SHORT = STAT_KEYS_SHORT  # alias for internal use

_STARTER_SPECIES_12P5_FEMALE = frozenset({
    "bulbasaur", "charmander", "squirtle",
    "chikorita", "cyndaquil", "totodile",
    "treecko", "torchic", "mudkip",
    "turtwig", "chimchar", "piplup",
    "snivy", "tepig", "oshawott",
    "chespin", "fennekin", "froakie",
    "rowlet", "litten", "popplio",
    "grookey", "scorbunny", "sobble",
    "sprigatito", "fuecoco", "quaxly",
    "pikachu", "eevee",
})


def _j(v: Any, default: Any) -> Any:
    """Parse JSON if string, else return v or default."""
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return default
    return v if v is not None else default


def normalize_base_stats(src: dict | None) -> dict:
    """Convert stats dict to long-form keys for stat calculation. Alias: normalize_stats_for_generator."""
    if not isinstance(src, dict):
        return {}
    lk = {str(k).lower().replace("-", "_"): v for k, v in src.items()}
    return {
        "hp": int(lk.get("hp", 0)),
        "attack": int(lk.get("attack", lk.get("atk", 0))),
        "defense": int(lk.get("defense", lk.get("def", 0))),
        "special_attack": int(lk.get("special_attack", lk.get("spa", lk.get("specialattack", 0)))),
        "special_defense": int(lk.get("special_defense", lk.get("spd", lk.get("specialdefense", 0)))),
        "speed": int(lk.get("speed", lk.get("spe", 0))),
    }


normalize_stats_for_generator = normalize_base_stats


def parse_abilities(abilities_raw: Any) -> tuple[list[str], list[str]]:
    """Parse abilities into (regular, hidden). Handles various formats."""
    if isinstance(abilities_raw, str):
        try:
            abilities_raw = json.loads(abilities_raw)
        except Exception:
            abilities_raw = []
    regs, hides = [], []
    for a in (abilities_raw or []):
        if isinstance(a, str):
            regs.append(a)
            continue
        if isinstance(a, dict):
            name = a.get("name") or (a.get("ability") or {}).get("name") or ""
            is_hidden = bool(a.get("is_hidden") or a.get("hidden") or (a.get("slot") == 3))
            if name:
                (hides if is_hidden else regs).append(name)

    def _dedup(seq: list[str]) -> list[str]:
        seen = set()
        out = []
        for s in seq:
            k = s.lower()
            if k not in seen:
                seen.add(k)
                out.append(s)
        return out

    return _dedup(regs), _dedup(hides)


def normalize_ivs_evs(raw: Any, default_val: int = 0) -> dict:
    """Normalize IVs/EVs to short-key dict (hp, atk, defn, spa, spd, spe)."""
    if not raw:
        return {k: default_val for k in _STAT_KEYS_SHORT}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw else {}
        except Exception:
            raw = {}
    if isinstance(raw, (list, tuple)) and len(raw) >= 6:
        out = {k: default_val for k in _STAT_KEYS_SHORT}
        for i, key in enumerate(_STAT_KEYS_SHORT):
            try:
                out[key] = int(float(raw[i]))
            except Exception:
                continue
        return out
    if isinstance(raw, dict):
        long_to_short = {
            "hp": "hp",
            "attack": "atk", "atk": "atk",
            "defense": "defn", "def": "defn", "defn": "defn",
            "special_attack": "spa", "special_atk": "spa", "specialattack": "spa",
            "spa": "spa", "spatk": "spa", "sp_atk": "spa",
            "special_defense": "spd", "special_def": "spd", "specialdefense": "spd",
            "spd": "spd", "spdef": "spd", "sp_def": "spd",
            "speed": "spe", "spe": "spe",
            "0": "hp", "1": "atk", "2": "defn", "3": "spa", "4": "spd", "5": "spe",
        }
        pref_aliases = {
            "hp": ("ev_hp", "hp_ev", "iv_hp", "hp_iv"),
            "atk": ("ev_atk", "atk_ev", "iv_atk", "atk_iv"),
            "defn": ("ev_def", "def_ev", "iv_def", "def_iv"),
            "spa": ("ev_spa", "spa_ev", "iv_spa", "spa_iv"),
            "spd": ("ev_spd", "spd_ev", "iv_spd", "spd_iv"),
            "spe": ("ev_spe", "spe_ev", "iv_spe", "spe_iv"),
        }
        out = {k: default_val for k in _STAT_KEYS_SHORT}
        norm_raw: dict[str, Any] = {}
        for key, val in raw.items():
            k = str(key or "").lower().replace("-", "_").replace(" ", "_")
            norm_raw[k] = val
            short = long_to_short.get(k) or (k if k in _STAT_KEYS_SHORT else None)
            if short is not None:
                try:
                    out[short] = int(float(val))
                except (TypeError, ValueError):
                    pass
        for dest, keys in pref_aliases.items():
            if out.get(dest, default_val) != default_val:
                continue
            for k in keys:
                kn = str(k).lower().replace("-", "_").replace(" ", "_")
                if kn in norm_raw and norm_raw.get(kn) not in (None, ""):
                    try:
                        out[dest] = int(float(norm_raw.get(kn)))
                        break
                    except Exception:
                        continue
        return out
    return {k: default_val for k in _STAT_KEYS_SHORT}


def roll_gender_from_ratio(gender_ratio: dict) -> str:
    """Return 'male' | 'female' | 'genderless' from ratio dict."""
    if not isinstance(gender_ratio, dict):
        return "male"
    if gender_ratio.get("genderless"):
        return "genderless"
    m = float(gender_ratio.get("male", 0) or 0.0)
    f = float(gender_ratio.get("female", 0) or 0.0)
    total = m + f
    if total <= 0:
        return "male"
    return "male" if (random.random() * total) < m else "female"


def species_uses_starter_gender_ratio(species_name: Any) -> bool:
    """Check if species uses 87.5/12.5 starter ratio."""
    key = str(species_name or "").strip().lower().replace("_", "-").replace(" ", "-")
    return key in _STARTER_SPECIES_12P5_FEMALE


def gender_ratio_from_entry(entry: dict, *, species_hint: Optional[str] = None) -> dict:
    """Get gender ratio from pokedex entry with starter fallback."""
    gender_ratio = _j(entry.get("gender_ratio"), None) if entry else None
    if not gender_ratio or not isinstance(gender_ratio, dict):
        gr = entry.get("gender_rate") if entry else None
        if isinstance(gr, str):
            try:
                gr = json.loads(gr)
            except Exception:
                gr = None
        if isinstance(gr, (int, float)):
            if int(gr) == -1:
                gender_ratio = {"genderless": True}
            else:
                female = float(gr) * 12.5
                gender_ratio = {"male": 100.0 - female, "female": female}
    if not gender_ratio or not isinstance(gender_ratio, dict):
        gender_ratio = {"male": 50.0, "female": 50.0}
    species_name = str(species_hint or (entry.get("name") if isinstance(entry, dict) else "") or "")
    if species_uses_starter_gender_ratio(species_name) and not bool(gender_ratio.get("genderless")):
        return {"male": 87.5, "female": 12.5}
    return gender_ratio
