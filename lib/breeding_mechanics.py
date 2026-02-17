from __future__ import annotations

import json
import random
import time
from typing import Any, Awaitable, Callable, Optional

import aiohttp

_POKEAPI_TIMEOUT = aiohttp.ClientTimeout(total=10)
_POKEAPI_UA = "DexEmAll-Breeding/1.0"
_POKEAPI_BASE_CACHE: dict[str, str] = {}
_POKEAPI_BASE_CACHE_TS: dict[str, float] = {}
_POKEAPI_BASE_CACHE_TTL = 60.0 * 60.0 * 6.0  # 6h

_PRE_EVO_MAP: dict[str, str] = {}
_PRE_EVO_MAP_TS: float = 0.0
_PRE_EVO_MAP_TTL = 60.0 * 60.0 * 6.0  # 6h

_SPECIAL_OFFSPRING_POOLS: dict[str, tuple[str, ...]] = {
    # Canonical mixed offspring lines.
    "nidoran-f": ("nidoran-f", "nidoran-m"),
    "nidoran-m": ("nidoran-f", "nidoran-m"),
    "illumise": ("illumise", "volbeat"),
    "volbeat": ("illumise", "volbeat"),
}


def norm_species(species: Any) -> str:
    return str(species or "").strip().lower().replace("_", "-").replace(" ", "-")


def norm_item(item_id: Any) -> str:
    return str(item_id or "").strip().lower().replace("_", "-").replace(" ", "-")


def ability_key(name: Any) -> str:
    return str(name or "").strip().lower().replace("_", "-").replace(" ", "-")


def parse_moves(raw_moves: Any) -> list[str]:
    moves = raw_moves
    if isinstance(moves, str):
        try:
            moves = json.loads(moves)
        except Exception:
            moves = [moves]
    if not isinstance(moves, (list, tuple)):
        return []
    out: list[str] = []
    for mv in moves[:4]:
        if isinstance(mv, dict):
            name = mv.get("name")
        else:
            name = mv
        nm = norm_species(name)
        if nm:
            out.append(nm)
    return out


def parse_evolution_blob(raw: Any) -> Any:
    if raw is None:
        return {}
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
            return data if isinstance(data, (dict, list)) else {}
        except Exception:
            return {}
    return {}


def next_evo_edges(parent_species: str, raw_evolution: Any) -> list[tuple[str, str]]:
    """
    Return (child_species, parent_species) edges from an evolution payload.
    Supports nested evolution trees and multiple payload shapes.
    """
    evo = parse_evolution_blob(raw_evolution)
    out: list[tuple[str, str]] = []

    def _node_species(node: Any) -> str:
        if isinstance(node, str):
            return norm_species(node)
        if not isinstance(node, dict):
            return ""
        raw = node.get("species") or node.get("name") or node.get("pokemon")
        if isinstance(raw, dict):
            raw = raw.get("name") or raw.get("species") or raw.get("pokemon")
        return norm_species(raw or "")

    def _node_next(node: Any) -> list[Any]:
        if isinstance(node, dict):
            nxt = node.get("next") or node.get("evolves_to") or node.get("children")
            if isinstance(nxt, list):
                return list(nxt)
            if nxt is not None:
                return [nxt]
        return []

    def _walk(parent: str, nodes: list[Any]) -> None:
        for node in nodes:
            child = _node_species(node)
            if child:
                out.append((child, parent))
                _walk(child, _node_next(node))
            else:
                _walk(parent, _node_next(node))

    start_nodes: list[Any] = []
    raw_next = evo.get("next") if isinstance(evo, dict) else None
    if isinstance(raw_next, list):
        start_nodes = list(raw_next)
    elif raw_next is not None:
        start_nodes = [raw_next]
    elif isinstance(evo, list):
        start_nodes = list(evo)

    _walk(norm_species(parent_species), start_nodes)
    return out


async def _fetch_json(url: str) -> dict:
    headers = {"User-Agent": _POKEAPI_UA}
    async with aiohttp.ClientSession(timeout=_POKEAPI_TIMEOUT, headers=headers) as sess:
        async with sess.get(url) as resp:
            if resp.status != 200:
                return {}
            try:
                data = await resp.json()
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}


def _is_pokeapi_base_cache_fresh(species_key: str) -> bool:
    ts = _POKEAPI_BASE_CACHE_TS.get(species_key)
    if ts is None:
        return False
    return (time.time() - float(ts)) <= _POKEAPI_BASE_CACHE_TTL


async def _pokeapi_base_species(species_name: str) -> str:
    key = norm_species(species_name)
    if not key:
        return ""
    if _is_pokeapi_base_cache_fresh(key) and key in _POKEAPI_BASE_CACHE:
        return _POKEAPI_BASE_CACHE[key]

    species_data = await _fetch_json(f"https://pokeapi.co/api/v2/pokemon-species/{key}")
    chain_url = ((species_data.get("evolution_chain") or {}).get("url") or "") if species_data else ""
    if not chain_url:
        _POKEAPI_BASE_CACHE[key] = key
        _POKEAPI_BASE_CACHE_TS[key] = time.time()
        return key

    chain_data = await _fetch_json(chain_url)
    root = norm_species(((chain_data.get("chain") or {}).get("species") or {}).get("name"))
    base = root or key
    _POKEAPI_BASE_CACHE[key] = base
    _POKEAPI_BASE_CACHE_TS[key] = time.time()
    return base


async def _build_pre_evo_map(
    fetch_pokedex_rows: Callable[[], Awaitable[list[tuple[Any, Any]]]],
) -> dict[str, str]:
    pre_map: dict[str, str] = {}
    rows = await fetch_pokedex_rows()
    for row in rows:
        try:
            parent_name, evolution_blob = row
        except Exception:
            continue
        parent = norm_species(parent_name)
        if not parent:
            continue
        for child, edge_parent in next_evo_edges(parent, evolution_blob):
            if child and child not in pre_map:
                pre_map[child] = norm_species(edge_parent or parent)
    return pre_map


async def pre_evo_map(
    fetch_pokedex_rows: Callable[[], Awaitable[list[tuple[Any, Any]]]],
    *,
    force_refresh: bool = False,
) -> dict[str, str]:
    global _PRE_EVO_MAP, _PRE_EVO_MAP_TS
    now = time.time()
    if (
        not force_refresh
        and _PRE_EVO_MAP
        and (now - float(_PRE_EVO_MAP_TS)) <= _PRE_EVO_MAP_TTL
    ):
        return _PRE_EVO_MAP
    try:
        built = await _build_pre_evo_map(fetch_pokedex_rows)
        if built:
            _PRE_EVO_MAP = built
            _PRE_EVO_MAP_TS = now
        return _PRE_EVO_MAP
    except Exception:
        return _PRE_EVO_MAP


async def resolve_egg_species(
    species: str,
    *,
    fetch_pokedex_rows: Callable[[], Awaitable[list[tuple[Any, Any]]]],
    allow_pokeapi_fallback: bool = True,
) -> str:
    """
    Resolve breeding offspring to base species.
    Special case: Manaphy always breeds Phione.
    """
    cur = norm_species(species)
    if not cur:
        return ""
    if cur == "manaphy":
        return "phione"

    original = cur
    pmap = await pre_evo_map(fetch_pokedex_rows)
    if pmap:
        seen = {cur}
        while True:
            parent = norm_species(pmap.get(cur))
            if not parent or parent in seen:
                break
            cur = parent
            seen.add(cur)

    # If local data didn't resolve any pre-evo, ask PokeAPI chain root.
    if allow_pokeapi_fallback and cur == original:
        try:
            api_base = await _pokeapi_base_species(cur)
            if api_base:
                cur = norm_species(api_base)
        except Exception:
            pass

    return cur or original


def breeding_source_parent(parent_a: dict, parent_b: dict) -> dict:
    s1 = norm_species(parent_a.get("species"))
    s2 = norm_species(parent_b.get("species"))
    ditto1 = s1 == "ditto"
    ditto2 = s2 == "ditto"
    if ditto1 and not ditto2:
        return parent_b
    if ditto2 and not ditto1:
        return parent_a
    g1 = str(parent_a.get("gender") or "").strip().lower()
    g2 = str(parent_b.get("gender") or "").strip().lower()
    if g1 == "female":
        return parent_a
    if g2 == "female":
        return parent_b
    return parent_a


def apply_special_offspring_rules(child_species: str, parent_a: dict, parent_b: dict) -> str:
    source = breeding_source_parent(parent_a, parent_b)
    source_species = norm_species(source.get("species"))
    pool = _SPECIAL_OFFSPRING_POOLS.get(source_species)
    if not pool:
        return norm_species(child_species)
    try:
        picked = random.choice(list(pool))
    except Exception:
        picked = source_species
    return norm_species(picked or child_species)


def apply_incense_baby_rules(
    base_child: str,
    parent_a: dict,
    parent_b: dict,
    incense_babies: dict[str, tuple[str, str]],
    pre_evo_map_data: Optional[dict[str, str]] = None,
) -> str:
    """
    Incense rule behavior:
      - with required incense: baby species
      - without required incense: source species (not baby)
    Non-incense lines use base_child.
    """
    source = breeding_source_parent(parent_a, parent_b)
    source_species = norm_species(source.get("species"))
    baby_rule = incense_babies.get(source_species)
    if not baby_rule:
        return norm_species(base_child)

    baby_species, required_incense = baby_rule
    need_item = norm_item(required_incense)
    held_a = norm_item(parent_a.get("held_item"))
    held_b = norm_item(parent_b.get("held_item"))
    held_source = norm_item(source.get("held_item"))
    if need_item and (held_source == need_item or held_a == need_item or held_b == need_item):
        return norm_species(baby_species)

    # Without incense, these families should produce the stage above the
    # incense baby (e.g., Blissey/Chansey -> Chansey, not Happiny/Blissey).
    if pre_evo_map_data:
        cur = source_species
        baby = norm_species(baby_species)
        seen = {cur}
        while cur:
            parent = norm_species(pre_evo_map_data.get(cur))
            if not parent or parent in seen:
                break
            if parent == baby:
                return cur
            cur = parent
            seen.add(cur)
    return source_species or norm_species(base_child)


def parse_egg_groups(entry: dict | None) -> set[str]:
    if not isinstance(entry, dict):
        return set()
    raw = entry.get("egg_groups")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = [raw]
    out: set[str] = set()
    if isinstance(raw, (list, tuple)):
        for g in raw:
            if isinstance(g, dict):
                name = g.get("name")
            else:
                name = g
            nm = norm_species(name)
            if nm:
                out.add(nm)
    return out


def pair_info(parent_a: dict, parent_b: dict, entry_a: dict | None, entry_b: dict | None) -> dict:
    fail = {
        "can_breed": False,
        "reason": "These Pokémon can't breed.",
        "child_species": None,
        "rate": 0.0,
    }
    if not parent_a or not parent_b:
        fail["reason"] = "Place two Pokémon in daycare."
        return fail
    if not entry_a or not entry_b:
        fail["reason"] = "Missing Pokédex data for one parent."
        return fail

    s1 = norm_species(parent_a.get("species"))
    s2 = norm_species(parent_b.get("species"))
    g1 = str(parent_a.get("gender") or "genderless").strip().lower()
    g2 = str(parent_b.get("gender") or "genderless").strip().lower()
    ditto1 = s1 == "ditto"
    ditto2 = s2 == "ditto"

    # Canonical exception: Manaphy + Ditto can breed and produces Phione eggs.
    if (s1 == "manaphy" and ditto2) or (s2 == "manaphy" and ditto1):
        return {
            "can_breed": True,
            "reason": "Manaphy can breed with Ditto.",
            "child_species": "manaphy",  # resolve_egg_species maps this to phione
            "rate": 0.85,
            "ditto_pair": True,
            "special_rule": "manaphy-phione",
            "egg_group_overlap": [],
        }

    if ditto1 and ditto2:
        fail["reason"] = "Two Ditto cannot breed together."
        return fail

    egg1 = parse_egg_groups(entry_a)
    egg2 = parse_egg_groups(entry_b)
    blocked_groups = {"undiscovered", "no-eggs"}
    if egg1 & blocked_groups or egg2 & blocked_groups:
        fail["reason"] = "One parent belongs to the Undiscovered egg group."
        return fail

    overlap = sorted(list((egg1 & egg2) - {"ditto"}))

    # Fallback for incomplete Pokédex rows: allow opposite-gender same-species pairs.
    if not egg1 or not egg2:
        if not (ditto1 or ditto2) and s1 == s2 and g1 != g2 and g1 != "genderless" and g2 != "genderless":
            return {
                "can_breed": True,
                "reason": "Compatible pair (egg group data fallback).",
                "child_species": s1 if g1 == "female" else s2,
                "rate": 1.0,
                "ditto_pair": False,
                "egg_group_overlap": overlap,
            }

    if not (ditto1 or ditto2):
        if g1 == g2:
            fail["reason"] = "Parents must be opposite gender."
            return fail
        if g1 == "genderless" or g2 == "genderless":
            fail["reason"] = "Genderless parents require Ditto."
            return fail
        if not ((egg1 & egg2) - {"ditto"}):
            fail["reason"] = "Parents are not in a compatible egg group."
            return fail

    if ditto1:
        child_species = s2
    elif ditto2:
        child_species = s1
    else:
        child_species = s1 if g1 == "female" else (s2 if g2 == "female" else s1)

    rate = 1.15 if (s1 == s2 and not (ditto1 or ditto2)) else (0.85 if (ditto1 or ditto2) else 0.95)
    return {
        "can_breed": True,
        "reason": "Compatible pair.",
        "child_species": child_species,
        "rate": rate,
        "ditto_pair": bool(ditto1 or ditto2),
        "egg_group_overlap": overlap,
    }


def pick_nature(parent_a: dict, parent_b: dict) -> str:
    item_a = norm_item(parent_a.get("held_item"))
    item_b = norm_item(parent_b.get("held_item"))
    ever_items = {"everstone", "ever-stone"}
    candidates: list[str] = []
    if item_a in ever_items and parent_a.get("nature"):
        candidates.append(str(parent_a.get("nature")).strip().lower())
    if item_b in ever_items and parent_b.get("nature"):
        candidates.append(str(parent_b.get("nature")).strip().lower())
    if candidates:
        return random.choice(candidates) or "hardy"
    na = str(parent_a.get("nature") or "").strip().lower()
    nb = str(parent_b.get("nature") or "").strip().lower()
    pool = [n for n in (na, nb) if n]
    return random.choice(pool) if pool else "hardy"


def pick_ivs(parent_a: dict, parent_b: dict, normalize_ivs_evs: Callable[[Any, int], dict]) -> dict:
    stats = ["hp", "atk", "defn", "spa", "spd", "spe"]
    iv_a = normalize_ivs_evs(parent_a.get("ivs"), 0)
    iv_b = normalize_ivs_evs(parent_b.get("ivs"), 0)
    child = {k: random.randint(0, 31) for k in stats}

    power_map = {
        "power-weight": "hp",
        "power-bracer": "atk",
        "power-belt": "defn",
        "power-lens": "spa",
        "power-band": "spd",
        "power-anklet": "spe",
    }
    forced: dict[str, str] = {}
    ia = norm_item(parent_a.get("held_item"))
    ib = norm_item(parent_b.get("held_item"))
    if ia in power_map:
        forced[power_map[ia]] = "a"
    if ib in power_map:
        stat_key = power_map[ib]
        if stat_key not in forced or random.random() < 0.5:
            forced[stat_key] = "b"

    selected = set()
    for stat_key, src in forced.items():
        child[stat_key] = int(iv_a.get(stat_key, 0)) if src == "a" else int(iv_b.get(stat_key, 0))
        selected.add(stat_key)

    inherit_count = 5 if ("destiny-knot" in {ia, ib}) else 3
    remaining = [k for k in stats if k not in selected]
    random.shuffle(remaining)
    for stat_key in remaining:
        if len(selected) >= inherit_count:
            break
        src = random.choice(("a", "b"))
        child[stat_key] = int(iv_a.get(stat_key, 0)) if src == "a" else int(iv_b.get(stat_key, 0))
        selected.add(stat_key)
    return child


def pick_ball(parent_a: dict, parent_b: dict, pair_info_data: dict) -> str:
    s1 = norm_species(parent_a.get("species"))
    s2 = norm_species(parent_b.get("species"))
    ditto1 = s1 == "ditto"
    ditto2 = s2 == "ditto"
    if ditto1 and not ditto2:
        source = parent_b
    elif ditto2 and not ditto1:
        source = parent_a
    else:
        g1 = str(parent_a.get("gender") or "").strip().lower()
        g2 = str(parent_b.get("gender") or "").strip().lower()
        source = parent_a if g1 == "female" else (parent_b if g2 == "female" else random.choice([parent_a, parent_b]))
    ball = str(source.get("pokeball") or "poke-ball").strip().lower()
    return ball or "poke-ball"


def pick_ability(
    parent_a: dict,
    parent_b: dict,
    child_entry: dict,
    pair_info_data: dict,
    *,
    parse_abilities_fn: Callable[[Any], tuple[list[str], list[str]]],
    roll_hidden_ability_fn: Callable[[Any], tuple[str, bool]],
) -> tuple[str, bool]:
    regs, hides = parse_abilities_fn(child_entry.get("abilities"))
    regs_norm = [ability_key(a) for a in regs if a]
    hides_norm = [ability_key(a) for a in hides if a]

    s1 = norm_species(parent_a.get("species"))
    s2 = norm_species(parent_b.get("species"))
    ditto1 = s1 == "ditto"
    ditto2 = s2 == "ditto"
    if ditto1 and not ditto2:
        source = parent_b
    elif ditto2 and not ditto1:
        source = parent_a
    else:
        g1 = str(parent_a.get("gender") or "").strip().lower()
        g2 = str(parent_b.get("gender") or "").strip().lower()
        source = parent_a if g1 == "female" else (parent_b if g2 == "female" else parent_a)

    parent_ability = ability_key(source.get("ability"))
    parent_hidden = bool(source.get("is_hidden_ability"))

    if parent_hidden and parent_ability in hides_norm and random.random() < 0.60:
        return parent_ability, True
    if parent_ability in regs_norm and random.random() < 0.80:
        return parent_ability, False

    ability_name, is_hidden = roll_hidden_ability_fn(child_entry.get("abilities"))
    ability_name = ability_key(ability_name)
    if ability_name:
        return ability_name, bool(is_hidden)
    if regs_norm:
        return random.choice(regs_norm), False
    if hides_norm:
        return random.choice(hides_norm), True
    return "run-away", False


async def inherited_egg_moves(
    parent_a: dict,
    parent_b: dict,
    child_species: str,
    *,
    egg_move_pool_fetch: Callable[[str], Awaitable[set[str]]],
    mirror_herb_items: set[str],
) -> list[str]:
    item_a = norm_item(parent_a.get("held_item"))
    item_b = norm_item(parent_b.get("held_item"))
    if item_a not in mirror_herb_items and item_b not in mirror_herb_items:
        return []
    egg_pool = await egg_move_pool_fetch(child_species)
    if not egg_pool:
        return []
    parent_moves = set(parse_moves(parent_a.get("moves"))) | set(parse_moves(parent_b.get("moves")))
    inheritable = [m for m in parent_moves if m in egg_pool]
    random.shuffle(inheritable)
    return inheritable[:4]


async def create_egg(
    parent_a: dict,
    parent_b: dict,
    pair_info_data: dict,
    *,
    resolve_egg_species_fn: Callable[[str], Awaitable[str]],
    species_entry_fetch: Callable[[str], Awaitable[Optional[dict]]],
    pick_ivs_fn: Callable[[dict, dict], dict],
    pick_nature_fn: Callable[[dict, dict], str],
    pick_ability_fn: Callable[[dict, dict, dict, dict], tuple[str, bool]],
    pick_ball_fn: Callable[[dict, dict, dict], str],
    inherited_egg_moves_fn: Callable[[dict, dict, str], Awaitable[list[str]]],
    incense_babies: dict[str, tuple[str, str]],
    hatch_min: float,
    hatch_max: float,
    pre_evo_map_fetch: Optional[Callable[[], Awaitable[dict[str, str]]]] = None,
) -> Optional[dict]:
    base_child = await resolve_egg_species_fn(str(pair_info_data.get("child_species") or ""))
    if not base_child:
        return None
    pre_map_data: dict[str, str] = {}
    if pre_evo_map_fetch is not None:
        try:
            pre_map_data = await pre_evo_map_fetch() or {}
        except Exception:
            pre_map_data = {}
    child_species = apply_incense_baby_rules(
        base_child,
        parent_a,
        parent_b,
        incense_babies,
        pre_evo_map_data=pre_map_data,
    )
    child_species = apply_special_offspring_rules(child_species, parent_a, parent_b)
    child_entry = await species_entry_fetch(child_species)
    if not child_entry:
        return None

    now = float(time.time())
    hatch_steps = random.uniform(float(hatch_min), float(hatch_max))
    child_ivs = pick_ivs_fn(parent_a, parent_b)
    child_nature = pick_nature_fn(parent_a, parent_b)
    child_ability, child_hidden = pick_ability_fn(parent_a, parent_b, child_entry, pair_info_data)
    child_ball = pick_ball_fn(parent_a, parent_b, pair_info_data)
    inherited_moves = await inherited_egg_moves_fn(parent_a, parent_b, child_species)

    return {
        "id": f"egg-{int(now * 1000)}-{random.randint(1000, 9999)}",
        "species": child_species,
        "created_at": now,
        "hatch_steps": float(hatch_steps),
        "progress": 0.0,
        "nature": child_nature,
        "ivs": child_ivs,
        "ability": child_ability,
        "is_hidden_ability": bool(child_hidden),
        "pokeball": child_ball,
        "egg_moves": inherited_moves,
    }
