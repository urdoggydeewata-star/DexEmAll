"""Fuzzy matching for Pokémon data: species, moves, items, resolve team mon."""
from __future__ import annotations

import difflib
import re
from typing import Optional

try:
    from lib import db
    from lib import db_cache
except ImportError:
    db = None  # type: ignore
    db_cache = None  # type: ignore


def _canon(s: str) -> str:
    """Lowercase and strip non-alphanumerics for fuzzy compare."""
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


class FuzzyMatcher:
    """
    Comprehensive fuzzy matching for Pokemon data with abbreviations,
    typo tolerance, and smart suggestions.
    """

    MOVE_ABBREVIATIONS = {
        "eq": "earthquake", "dclaw": "dragon-claw", "stone": "stone-edge",
        "sword": "swords-dance", "rocks": "stealth-rock", "twave": "thunder-wave",
        "willowisp": "will-o-wisp", "wow": "will-o-wisp", "sr": "stealth-rock",
        "hp": "hidden-power", "sub": "substitute", "protect": "protect", "toxic": "toxic",
        "roost": "roost", "uturn": "u-turn", "volt": "volt-switch", "scald": "scald",
        "knock": "knock-off", "defog": "defog", "rapid": "rapid-spin", "spin": "rapid-spin",
        "flamethrower": "flamethrower", "fireblast": "fire-blast", "icebeam": "ice-beam",
        "thunderbolt": "thunderbolt", "thunder": "thunder", "psychic": "psychic",
        "shadowball": "shadow-ball", "energyball": "energy-ball", "focusblast": "focus-blast",
        "aurasphere": "aura-sphere", "darkpulse": "dark-pulse", "dragonpulse": "dragon-pulse",
        "dracometeor": "draco-meteor", "overheat": "overheat", "closecombat": "close-combat",
        "superpower": "superpower", "ironhead": "iron-head", "playrough": "play-rough",
        "moonblast": "moonblast", "gigadrain": "giga-drain",
    }

    NATURE_ABBREVIATIONS = {
        "ada": "adamant", "bold": "bold", "brave": "brave", "calm": "calm", "care": "careful",
        "hast": "hasty", "imp": "impish", "jol": "jolly", "lax": "lax", "lone": "lonely",
        "mild": "mild", "mod": "modest", "naive": "naive", "naugh": "naughty", "quie": "quiet",
        "rash": "rash", "relax": "relaxed", "sass": "sassy", "seri": "serious", "timi": "timid",
    }

    @staticmethod
    def normalize(text: str) -> str:
        """Normalize text for matching."""
        if not text:
            return ""
        return str(text).strip().lower().replace(" ", "-").replace("_", "-")

    @staticmethod
    def fuzzy_match(query: str, choices: list[str], threshold: float = 0.72) -> tuple[Optional[str], float, list[str]]:
        """Returns (best_match, score, suggestions[:5])."""
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
        """Fuzzy match move name. Returns (move_name, confidence, suggestions)."""
        query_norm = FuzzyMatcher.normalize(query)
        if query_norm in FuzzyMatcher.MOVE_ABBREVIATIONS:
            exact_move = FuzzyMatcher.MOVE_ABBREVIATIONS[query_norm]
            return exact_move, 1.0, [exact_move]
        if species_id and gen:
            cur = await conn.execute(
                "SELECT DISTINCT m.name FROM moves m JOIN learnsets l ON m.id = l.move_id "
                "WHERE l.species_id = ? AND l.generation <= ?",
                (species_id, gen),
            )
        else:
            cur = await conn.execute("SELECT name FROM moves")
        move_rows = await cur.fetchall()
        await cur.close()
        all_moves = [row["name"] for row in move_rows]
        return FuzzyMatcher.fuzzy_match(query, all_moves, threshold=0.70)

    @staticmethod
    async def fuzzy_species(conn, query: str) -> tuple[Optional[dict], float, list[str]]:
        """Fuzzy match species. Returns (species_row, confidence, suggestions)."""
        cur = await conn.execute("SELECT id, name FROM pokedex")
        species_rows = await cur.fetchall()
        await cur.close()
        species_names = [row["name"] for row in species_rows]
        best_name, score, suggestions = FuzzyMatcher.fuzzy_match(query, species_names, threshold=0.70)
        if best_name:
            cur = await conn.execute("SELECT * FROM pokedex WHERE LOWER(name) = LOWER(?)", (best_name,))
            species_row = await cur.fetchone()
            await cur.close()
            return dict(species_row) if species_row else None, score, suggestions
        return None, 0.0, suggestions

    @staticmethod
    async def fuzzy_ability(conn, query: str, valid_abilities: Optional[list[str]] = None) -> tuple[Optional[str], float, list[str]]:
        """Fuzzy match ability. Returns (ability_name, confidence, suggestions)."""
        if valid_abilities:
            choices = valid_abilities
        else:
            cur = await conn.execute("SELECT DISTINCT ability FROM pokemons WHERE ability IS NOT NULL")
            rows = await cur.fetchall()
            await cur.close()
            choices = list(set(row["ability"] for row in rows if row["ability"]))
        return FuzzyMatcher.fuzzy_match(query, choices, threshold=0.75)

    @staticmethod
    async def fuzzy_item(conn, query: str) -> tuple[Optional[str], float, list[str]]:
        """Fuzzy match item. Returns (item_id, confidence, suggestions)."""
        item_rows = []
        if db_cache is not None:
            item_rows = db_cache.get_all_cached_items()
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
        """Fuzzy match nature. Returns (nature_name, confidence, suggestions)."""
        import lib.stats as stats
        query_norm = FuzzyMatcher.normalize(query)
        if query_norm in FuzzyMatcher.NATURE_ABBREVIATIONS:
            n = FuzzyMatcher.NATURE_ABBREVIATIONS[query_norm]
            return n, 1.0, [n]
        natures = list(stats.NATURE_PLUS_MINUS.keys())
        return FuzzyMatcher.fuzzy_match(query, natures, threshold=0.75)


def _fuzzy_best(query: str, choices: list[str]) -> tuple[Optional[str], float, list[str]]:
    """Return (best_choice, best_ratio, suggestions[:3]). Legacy; use FuzzyMatcher for new code."""
    qc = _canon(query)
    if not choices:
        return None, 0.0, []
    scored = [(difflib.SequenceMatcher(a=qc, b=_canon(c)).ratio(), c) for c in choices]
    scored.sort(reverse=True)
    best_ratio, best = scored[0]
    suggestions = [c for r, c in scored if r >= 0.72][:3]
    return best, best_ratio, suggestions


async def resolve_team_mon(interaction, name: str, slot: int | None = None, *, threshold: float = 0.85, conn=None) -> dict | None:
    """
    Resolve a user's TEAM Pokémon by fuzzy name (and optional slot).
    Sends ephemeral message on failure and returns None.
    """
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)
    except Exception:
        pass

    uid = str(interaction.user.id)
    team = None
    if db_cache is not None:
        try:
            cached = db_cache.get_cached_pokemons(uid)
            if cached is None:
                await db.list_pokemons(uid, limit=2000, offset=0)
                cached = db_cache.get_cached_pokemons(uid)
            if cached is not None:
                team = [
                    {"id": p.get("id"), "species": p.get("species"), "team_slot": p.get("team_slot")}
                    for p in cached
                    if p.get("team_slot") and 1 <= int(p.get("team_slot") or 0) <= 6
                ]
                team.sort(key=lambda p: (int(p.get("team_slot") or 0), int(p.get("id") or 0)))
        except Exception:
            pass

    if team is None:
        async def _run(qconn):
            cur = await qconn.execute(
                "SELECT id, species, team_slot FROM pokemons WHERE owner_id = ? AND team_slot BETWEEN 1 AND 6 ORDER BY team_slot, id",
                (uid,),
            )
            out = [dict(r) for r in await cur.fetchall()]
            await cur.close()
            return out

        if conn is not None:
            team = await _run(conn)
        else:
            async with db.session() as c:
                team = await _run(c)
        try:
            await db.list_pokemons(uid, limit=2000, offset=0)
        except Exception:
            pass

    if not team:
        await interaction.followup.send("Your team is empty.", ephemeral=True)
        return None

    species_map: dict[str, list[dict]] = {}
    for r in team:
        species_map.setdefault(r["species"].lower(), []).append(r)

    key = name.lower()
    autocorrected_to = None
    if key not in species_map:
        names = list(species_map.keys())
        best, score, suggestions = _fuzzy_best(name, names)
        qc = _canon(name)
        bc = _canon(best) if best else ""
        is_prefixish = bool(best) and len(qc) >= 4 and (bc.startswith(qc) or qc.startswith(bc))
        if best and (score >= threshold or is_prefixish):
            key = best
            autocorrected_to = best.title()
        elif suggestions:
            pretty = ", ".join(s.title() for s in suggestions)
            await interaction.followup.send(
                f"No **{name.title()}** in your team. Did you mean: {pretty} ?\n"
                "Re-run with the corrected name (and `slot:` if you have duplicates).",
                ephemeral=True,
            )
            return None
        else:
            have = ", ".join(sorted({r["species"].title() for r in team}))
            await interaction.followup.send(f"No **{name.title()}** in your team. Team contains: {have}.", ephemeral=True)
            return None

    mons = species_map[key]
    if len(mons) > 1 and slot is None:
        choices = ", ".join(f"slot {m['team_slot']} (ID #{m['id']})" for m in mons)
        await interaction.followup.send(f"You have {len(mons)} **{key.title()}** in your team: {choices}.\nRe-run with `slot:<1-6>`.", ephemeral=True)
        return None

    if slot is not None:
        for m in mons:
            if int(m["team_slot"]) == int(slot):
                m = dict(m)
                break
        else:
            choices = ", ".join(str(m["team_slot"]) for m in mons)
            await interaction.followup.send(f"No **{key.title()}** in team slot {slot}. Available slots: {choices}.", ephemeral=True)
            return None
    else:
        m = dict(mons[0])

    if autocorrected_to:
        m["_autocorrected_to"] = autocorrected_to
    return m


async def resolve_team_mon_for_owner_id(
    owner_id: str, name: str, slot: int | None = None, *, threshold: float = 0.85, conn=None
) -> tuple[dict | None, str | None]:
    """Resolve team Pokémon for arbitrary owner_id. Returns (row_or_none, error_message_or_none)."""
    uid = str(owner_id)
    query_name = str(name or "").strip()
    if not query_name:
        return None, "Please provide a Pokémon name."

    async def _run(qconn):
        cur = await qconn.execute(
            "SELECT id, species, team_slot, level, ivs, nature, form, hp_now, hp FROM pokemons "
            "WHERE owner_id=? AND team_slot BETWEEN 1 AND 6 ORDER BY team_slot, id",
            (uid,),
        )
        rows = [dict(r) for r in await cur.fetchall()]
        await cur.close()
        return rows

    if conn is not None:
        team = await _run(conn)
    else:
        async with db.session() as c:
            team = await _run(c)

    if not team:
        return None, "Target user's team is empty."

    species_map: dict[str, list[dict]] = {}
    for r in team:
        species_map.setdefault(str(r.get("species") or "").lower(), []).append(r)

    key = query_name.lower()
    autocorrected_to = None
    if key not in species_map:
        names = list(species_map.keys())
        best, score, suggestions = _fuzzy_best(query_name, names)
        qc = _canon(query_name)
        bc = _canon(best) if best else ""
        is_prefixish = bool(best) and len(qc) >= 4 and (bc.startswith(qc) or qc.startswith(bc))
        if best and (score >= threshold or is_prefixish):
            key = best
            autocorrected_to = best.title()
        elif suggestions:
            pretty = ", ".join(s.title() for s in suggestions)
            return None, f"No **{query_name.title()}** in target team. Did you mean: {pretty} ?"
        else:
            have = ", ".join(sorted({str(r.get("species") or "").title() for r in team}))
            return None, f"No **{query_name.title()}** in target team. Team contains: {have}."

    mons = species_map[key]
    if len(mons) > 1 and slot is None:
        choices = ", ".join(f"slot {int(m.get('team_slot') or 0)} (ID #{int(m.get('id') or 0)})" for m in mons)
        return None, f"Target has {len(mons)} **{key.title()}** in team: {choices}. Re-run with `slot:`."

    if slot is not None:
        chosen = None
        for m in mons:
            if int(m.get("team_slot") or 0) == int(slot):
                chosen = dict(m)
                break
        if chosen is None:
            choices = ", ".join(str(int(m.get("team_slot") or 0)) for m in mons)
            return None, f"No **{key.title()}** in target slot {slot}. Available slots: {choices}."
    else:
        chosen = dict(mons[0])

    if autocorrected_to:
        chosen["_autocorrected_to"] = autocorrected_to
    return chosen, None
