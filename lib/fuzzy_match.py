"""
Fuzzy matching for Pokémon data - extracted from pokebot.py.
Handles moves, species, abilities, items, natures with abbreviations and typo tolerance.
"""
from __future__ import annotations

import difflib
import re
from typing import Optional

try:
    from lib import db_cache
except ImportError:
    db_cache = None


def canon(s: str) -> str:
    """Lowercase and strip non-alphanumerics for fuzzy compare."""
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


class FuzzyMatcher:
    """
    Comprehensive fuzzy matching for Pokemon data with abbreviations,
    typo tolerance, and smart suggestions.
    """

    MOVE_ABBREVIATIONS = {
        "eq": "earthquake",
        "dclaw": "dragon-claw",
        "stone": "stone-edge",
        "sword": "swords-dance",
        "rocks": "stealth-rock",
        "twave": "thunder-wave",
        "willowisp": "will-o-wisp",
        "wow": "will-o-wisp",
        "sr": "stealth-rock",
        "hp": "hidden-power",
        "sub": "substitute",
        "protect": "protect",
        "toxic": "toxic",
        "roost": "roost",
        "uturn": "u-turn",
        "volt": "volt-switch",
        "scald": "scald",
        "knock": "knock-off",
        "defog": "defog",
        "rapid": "rapid-spin",
        "spin": "rapid-spin",
        "flamethrower": "flamethrower",
        "fireblast": "fire-blast",
        "icebeam": "ice-beam",
        "thunderbolt": "thunderbolt",
        "thunder": "thunder",
        "psychic": "psychic",
        "shadowball": "shadow-ball",
        "energyball": "energy-ball",
        "focusblast": "focus-blast",
        "aurasphere": "aura-sphere",
        "darkpulse": "dark-pulse",
        "dragonpulse": "dragon-pulse",
        "dracometeor": "draco-meteor",
        "overheat": "overheat",
        "closecombat": "close-combat",
        "superpower": "superpower",
        "ironhead": "iron-head",
        "playrough": "play-rough",
        "moonblast": "moonblast",
        "gigadrain": "giga-drain",
    }

    NATURE_ABBREVIATIONS = {
        "ada": "adamant", "bold": "bold", "brave": "brave", "calm": "calm",
        "care": "careful", "hast": "hasty", "imp": "impish", "jol": "jolly",
        "lax": "lax", "lone": "lonely", "mild": "mild", "mod": "modest",
        "naive": "naive", "naugh": "naughty", "quie": "quiet", "rash": "rash",
        "relax": "relaxed", "sass": "sassy", "seri": "serious", "timi": "timid",
    }

    @staticmethod
    def normalize(text: str) -> str:
        """Normalize text for matching."""
        if not text:
            return ""
        return str(text).strip().lower().replace(" ", "-").replace("_", "-")

    @staticmethod
    def fuzzy_match(query: str, choices: list[str], threshold: float = 0.72) -> tuple[Optional[str], float, list[str]]:
        """Enhanced fuzzy matching. Returns (best_match, score, suggestions[:5])."""
        if not choices:
            return None, 0.0, []

        query_norm = FuzzyMatcher.normalize(query)
        for choice in choices:
            if FuzzyMatcher.normalize(choice) == query_norm:
                return choice, 1.0, [choice]

        scored = []
        for choice in choices:
            choice_norm = FuzzyMatcher.normalize(choice)
            ratio = difflib.SequenceMatcher(a=query_norm, b=choice_norm).ratio()
            if choice_norm.startswith(query_norm):
                ratio = max(ratio, 0.85)
            if query_norm in choice_norm:
                ratio = max(ratio, 0.80)
            scored.append((ratio, choice))

        scored.sort(reverse=True, key=lambda x: x[0])
        best_score, best_choice = scored[0]
        suggestions = [c for s, c in scored if s >= threshold][:5]
        return best_choice, best_score, suggestions

    @staticmethod
    async def fuzzy_move(conn, query: str, species_id: Optional[int] = None, gen: Optional[int] = None) -> tuple[Optional[str], float, list[str]]:
        """Fuzzy match move name with abbreviation support. Optionally filter by species/gen for legality."""
        query_norm = FuzzyMatcher.normalize(query)
        if query_norm in FuzzyMatcher.MOVE_ABBREVIATIONS:
            exact_move = FuzzyMatcher.MOVE_ABBREVIATIONS[query_norm]
            return exact_move, 1.0, [exact_move]

        if species_id and gen:
            cur = await conn.execute(
                """SELECT DISTINCT m.name FROM moves m
                   JOIN learnsets l ON m.id = l.move_id
                   WHERE l.species_id = ? AND l.generation <= ?""",
                (species_id, gen),
            )
        else:
            cur = await conn.execute("SELECT name FROM moves")
        move_rows = await cur.fetchall()
        await cur.close()
        all_moves = [row["name"] for row in move_rows]
        return FuzzyMatcher.fuzzy_match(query, all_moves, threshold=0.70)

    @staticmethod
    async def fuzzy_item(conn, query: str, item_cache=None) -> tuple[Optional[str], float, list[str]]:
        """Fuzzy match item name. Uses item cache when available."""
        cache = item_cache if item_cache is not None else db_cache
        item_rows = (cache.get_all_cached_items() if cache and hasattr(cache, "get_all_cached_items") else [])
        if not item_rows:
            cur = await conn.execute("SELECT id, name FROM items")
            item_rows = [dict(r) for r in await cur.fetchall()]
            await cur.close()

        item_ids = [r.get("id") or "" for r in item_rows]
        item_names = [r.get("name") or r.get("id") or "" for r in item_rows]
        best_id, score_id, sugg_id = FuzzyMatcher.fuzzy_match(query, item_ids, threshold=0.70)
        best_name, score_name, sugg_name = FuzzyMatcher.fuzzy_match(query, item_names, threshold=0.70)

        if score_id > score_name:
            return best_id, score_id, sugg_id
        if best_name:
            for row in item_rows:
                if (row.get("name") or "").lower() == best_name.lower():
                    sugg = [r.get("id") or "" for r in item_rows if (r.get("name") or "") in sugg_name]
                    return row.get("id"), score_name, sugg
        return None, 0.0, []

    @staticmethod
    def fuzzy_nature(query: str) -> tuple[Optional[str], float, list[str]]:
        """Fuzzy match nature name with abbreviation support."""
        from lib import stats
        query_norm = FuzzyMatcher.normalize(query)
        if query_norm in FuzzyMatcher.NATURE_ABBREVIATIONS:
            n = FuzzyMatcher.NATURE_ABBREVIATIONS[query_norm]
            return n, 1.0, [n]
        natures = list(stats.NATURE_PLUS_MINUS.keys())
        return FuzzyMatcher.fuzzy_match(query, natures, threshold=0.75)


def fuzzy_best(query: str, choices: list[str]) -> tuple[Optional[str], float, list[str]]:
    """Legacy: return (best_choice, best_ratio, suggestions[:3]) using difflib."""
    qc = canon(query)
    if not choices:
        return None, 0.0, []
    scored = [(difflib.SequenceMatcher(a=qc, b=canon(c)).ratio(), c) for c in choices]
    scored.sort(reverse=True)
    best_ratio, best = scored[0]
    suggestions = [c for r, c in scored if r >= 0.72][:3]
    return best, best_ratio, suggestions
