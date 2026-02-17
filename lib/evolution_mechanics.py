from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Optional

import aiohttp


_POKEAPI_TIMEOUT = aiohttp.ClientTimeout(total=10)
_POKEAPI_UA = "DexEmAll-Evolution/1.0"
_POKEAPI_NEXT_CACHE: dict[str, list[dict[str, Any]]] = {}
_POKEAPI_NEXT_CACHE_TS: dict[str, float] = {}
_POKEAPI_CACHE_TTL = 60.0 * 60.0 * 6.0  # 6 hours


_ITEM_EVOLUTION_FALLBACK: dict[str, dict[str, str]] = {
    # Gen 1
    "pikachu": {"thunder-stone": "raichu"},
    "nidorina": {"moon-stone": "nidoqueen"},
    "nidorino": {"moon-stone": "nidoking"},
    "clefairy": {"moon-stone": "clefable"},
    "jigglypuff": {"moon-stone": "wigglytuff"},
    "gloom": {"leaf-stone": "vileplume", "sun-stone": "bellossom"},
    "poliwhirl": {"water-stone": "poliwrath"},
    "weepinbell": {"leaf-stone": "victreebel"},
    "shellder": {"water-stone": "cloyster"},
    "staryu": {"water-stone": "starmie"},
    "exeggcute": {"leaf-stone": "exeggutor"},
    "vulpix": {"fire-stone": "ninetales"},
    "growlithe": {"fire-stone": "arcanine"},
    "eevee": {
        "water-stone": "vaporeon",
        "thunder-stone": "jolteon",
        "fire-stone": "flareon",
        "leaf-stone": "leafeon",
        "ice-stone": "glaceon",
    },
    # Gen 2+
    "togetic": {"shiny-stone": "togekiss"},
    "roselia": {"shiny-stone": "roserade"},
    "misdreavus": {"dusk-stone": "mismagius"},
    "murkrow": {"dusk-stone": "honchkrow"},
    "lombre": {"water-stone": "ludicolo"},
    "nuzleaf": {"leaf-stone": "shiftry"},
    "skitty": {"moon-stone": "delcatty"},
    "minccino": {"shiny-stone": "cinccino"},
    "munna": {"moon-stone": "musharna"},
    "cottonee": {"sun-stone": "whimsicott"},
    "petilil": {"sun-stone": "lilligant"},
    "pansage": {"leaf-stone": "simisage"},
    "pansear": {"fire-stone": "simisear"},
    "panpour": {"water-stone": "simipour"},
    "lampent": {"dusk-stone": "chandelure"},
    "floette": {"shiny-stone": "florges"},
    "doublade": {"dusk-stone": "aegislash"},
    "charjabug": {"thunder-stone": "vikavolt"},
}


def norm_text(v: Any) -> str:
    return str(v or "").strip().lower().replace("_", "-").replace(" ", "-")


def unwrap_nameish(v: Any) -> Any:
    if isinstance(v, dict):
        if "name" in v and not isinstance(v.get("name"), (dict, list, tuple)):
            return v.get("name")
        for key in ("item", "trigger", "species", "value", "id"):
            if key in v:
                return unwrap_nameish(v.get(key))
        return None
    return v


def details_candidates(raw_details: Any) -> list[dict]:
    details = raw_details
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except Exception:
            details = {}
    if isinstance(details, dict):
        return [details]
    if isinstance(details, (list, tuple)):
        out: list[dict] = []
        for d in details:
            if isinstance(d, str):
                try:
                    d = json.loads(d)
                except Exception:
                    d = {}
            if isinstance(d, dict):
                out.append(d)
        return out
    return []


def parse_moves(raw_moves: Any) -> set[str]:
    moves = raw_moves
    if isinstance(moves, str):
        try:
            moves = json.loads(moves)
        except Exception:
            moves = [moves]
    if not isinstance(moves, (list, tuple)):
        return set()
    out: set[str] = set()
    for m in moves[:4]:
        if isinstance(m, dict):
            name = m.get("name")
        else:
            name = m
        nm = norm_text(name)
        if nm:
            out.add(nm)
    return out


def day_phase_utc() -> str:
    hour = datetime.now(timezone.utc).hour
    return "day" if 6 <= hour < 18 else "night"


def _is_cache_fresh(species_key: str) -> bool:
    ts = _POKEAPI_NEXT_CACHE_TS.get(species_key)
    if ts is None:
        return False
    return (time.time() - ts) < _POKEAPI_CACHE_TTL


async def _fetch_json(url: str) -> dict:
    if not url:
        return {}
    try:
        async with aiohttp.ClientSession(timeout=_POKEAPI_TIMEOUT, headers={"User-Agent": _POKEAPI_UA}) as sess:
            async with sess.get(url) as resp:
                if resp.status != 200:
                    return {}
                data = await resp.json()
                return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _extract_next_from_chain(chain_data: dict, species_key: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    node = chain_data.get("chain")
    if not isinstance(node, dict):
        return out
    stack = [node]
    while stack:
        cur = stack.pop()
        cur_name = norm_text(unwrap_nameish(cur.get("species")))
        if cur_name == species_key:
            for nxt in (cur.get("evolves_to") or []):
                if not isinstance(nxt, dict):
                    continue
                child = norm_text(unwrap_nameish(nxt.get("species")))
                if not child:
                    continue
                detail_blob = nxt.get("evolution_details")
                cands = details_candidates(detail_blob)
                out.append({"species": child, "details": cands if cands else [{}]})
            break
        for nxt in (cur.get("evolves_to") or []):
            if isinstance(nxt, dict):
                stack.append(nxt)
    return out


async def _pokeapi_next_entries(species_name: str) -> list[dict[str, Any]]:
    species_key = norm_text(species_name)
    if not species_key:
        return []
    if species_key in _POKEAPI_NEXT_CACHE and _is_cache_fresh(species_key):
        return _POKEAPI_NEXT_CACHE[species_key]

    species_data = await _fetch_json(f"https://pokeapi.co/api/v2/pokemon-species/{species_key}/")
    chain_url = ((species_data.get("evolution_chain") or {}).get("url") or "") if species_data else ""
    chain_data = await _fetch_json(chain_url) if chain_url else {}
    entries = _extract_next_from_chain(chain_data, species_key)
    _POKEAPI_NEXT_CACHE[species_key] = entries
    _POKEAPI_NEXT_CACHE_TS[species_key] = time.time()
    return entries


def _parse_db_evolution(raw: Any) -> list[dict[str, Any]]:
    evo = raw
    if isinstance(evo, str):
        try:
            evo = json.loads(evo)
        except Exception:
            evo = {}
    if not isinstance(evo, dict):
        return []
    raw_next = evo.get("next")
    if isinstance(raw_next, list):
        next_list = raw_next
    elif raw_next is not None:
        next_list = [raw_next]
    else:
        next_list = []
    out: list[dict[str, Any]] = []
    for nxt in next_list:
        if isinstance(nxt, str):
            sp = norm_text(nxt)
            if sp:
                out.append({"species": sp, "details": [{}]})
            continue
        if not isinstance(nxt, dict):
            continue
        sp = norm_text(unwrap_nameish(nxt.get("species")))
        if not sp:
            continue
        detail_blob = nxt.get("details")
        if detail_blob in (None, "", []):
            detail_blob = nxt.get("evolution_details")
        cands = details_candidates(detail_blob)
        if not cands:
            cands = [nxt]
        out.append({"species": sp, "details": cands})
    return out


async def _move_type_match(conn: Any, moves_norm: set[str], required_type: str) -> bool:
    if not moves_norm:
        return False
    move_list = [m for m in moves_norm if m]
    if not move_list:
        return False
    placeholders = ",".join("?" for _ in move_list)
    try:
        cur = await conn.execute(
            f"SELECT type FROM moves WHERE LOWER(REPLACE(name, ' ', '-')) IN ({placeholders})",
            tuple(move_list),
        )
        rows = await cur.fetchall()
        await cur.close()
    except Exception:
        return False
    need = norm_text(required_type)
    for row in rows:
        t = norm_text(row["type"] if hasattr(row, "keys") else row[0])
        if t == need:
            return True
    return False


async def _details_match(
    conn: Any,
    details: dict,
    *,
    expected_trigger: str,
    level: Optional[int],
    friendship: Optional[int],
    gender: Optional[str],
    moves: Any,
    held_item: Optional[str],
    item_used: Optional[str],
    area_id: Optional[str],
) -> bool:
    trigger = norm_text(unwrap_nameish(details.get("trigger")))
    expected = norm_text(expected_trigger)

    if expected == "level-up":
        if trigger and trigger != "level-up":
            return False
    elif expected == "use-item":
        if trigger and trigger not in {"use-item", "item"}:
            return False
    elif expected and trigger and expected != trigger:
        return False

    if expected == "level-up":
        min_level = details.get("min_level")
        if min_level is not None:
            try:
                if level is None or int(level) < int(min_level):
                    return False
            except Exception:
                return False
        req_held = norm_text(unwrap_nameish(details.get("held_item")))
        if req_held and norm_text(held_item) != req_held:
            return False
    elif expected == "use-item":
        req_item = norm_text(unwrap_nameish(details.get("item")))
        if req_item and norm_text(item_used) != req_item:
            return False
        if not req_item and trigger not in {"use-item", "item"}:
            return False

    req_gender = norm_text(unwrap_nameish(details.get("gender")))
    if req_gender == "1":
        req_gender = "female"
    elif req_gender == "2":
        req_gender = "male"
    if req_gender in {"male", "female"} and norm_text(gender) != req_gender:
        return False

    req_time = norm_text(unwrap_nameish(details.get("time_of_day")))
    if req_time in {"day", "night"} and day_phase_utc() != req_time:
        return False

    for key in ("min_happiness", "min_friendship", "min_affection"):
        if details.get(key) is None:
            continue
        try:
            if friendship is None or int(friendship) < int(details.get(key)):
                return False
        except Exception:
            return False

    req_move = norm_text(unwrap_nameish(details.get("known_move")))
    req_move_type = norm_text(unwrap_nameish(details.get("known_move_type")))
    moves_norm = parse_moves(moves)
    if req_move and req_move not in moves_norm:
        return False
    if req_move_type and not await _move_type_match(conn, moves_norm, req_move_type):
        return False

    req_location = norm_text(unwrap_nameish(details.get("location")))
    if req_location and norm_text(area_id) != req_location:
        return False

    # Conditions that need battle-party or special runtime signals not currently provided.
    if details.get("trade_species") not in (None, "", False):
        return False
    if details.get("party_species") not in (None, "", False):
        return False
    if details.get("party_type") not in (None, "", False):
        return False
    if details.get("relative_physical_stats") not in (None, "", 0, False):
        return False
    if details.get("min_beauty") not in (None, "", 0, False):
        return False
    if bool(details.get("needs_overworld_rain")) or bool(details.get("turn_upside_down")):
        return False

    return True


async def _combined_next_entries(conn: Any, species_name: str) -> list[dict[str, Any]]:
    species_key = norm_text(species_name)
    if not species_key:
        return []
    db_entries: list[dict[str, Any]] = []
    try:
        cur = await conn.execute(
            "SELECT evolution FROM pokedex WHERE LOWER(name)=LOWER(?) OR LOWER(REPLACE(name,' ','-'))=LOWER(?) LIMIT 1",
            (species_name.strip(), species_key),
        )
        row = await cur.fetchone()
        await cur.close()
        if row and row.get("evolution") is not None:
            db_entries = _parse_db_evolution(row["evolution"])
    except Exception:
        db_entries = []

    # Pull richer details from PokeAPI too (covers many edge cases up to Gen 8).
    api_entries = await _pokeapi_next_entries(species_key)
    if not db_entries:
        return api_entries
    if not api_entries:
        return db_entries

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in db_entries + api_entries:
        sp = norm_text(entry.get("species"))
        detail_blob = entry.get("details") or [{}]
        sig = f"{sp}|{json.dumps(detail_blob, sort_keys=True, ensure_ascii=True)}"
        if sp and sig not in seen:
            seen.add(sig)
            out.append(entry)
    return out


def fallback_item_target(species_name: str, item_id: str) -> Optional[str]:
    sp = norm_text(species_name)
    item = norm_text(item_id)
    if not sp or not item:
        return None
    return _ITEM_EVOLUTION_FALLBACK.get(sp, {}).get(item)


async def resolve_for_trigger(
    conn: Any,
    species_name: str,
    *,
    expected_trigger: str,
    level: Optional[int] = None,
    friendship: Optional[int] = None,
    gender: Optional[str] = None,
    moves: Any = None,
    held_item: Optional[str] = None,
    item_used: Optional[str] = None,
    area_id: Optional[str] = None,
) -> Optional[str]:
    entries = await _combined_next_entries(conn, species_name)
    expected = norm_text(expected_trigger)
    for entry in entries:
        target = norm_text(entry.get("species"))
        if not target:
            continue
        detail_list = details_candidates(entry.get("details"))
        if not detail_list:
            # Bare evolution nodes are treated as level-up compatible only.
            if expected == "level-up":
                return target
            continue
        for det in detail_list:
            if await _details_match(
                conn,
                det if isinstance(det, dict) else {},
                expected_trigger=expected,
                level=level,
                friendship=friendship,
                gender=gender,
                moves=moves,
                held_item=held_item,
                item_used=item_used,
                area_id=area_id,
            ):
                return target
    return None


async def resolve_level_up_evolution(
    conn: Any,
    species_name: str,
    level: int,
    *,
    friendship: Optional[int] = None,
    gender: Optional[str] = None,
    moves: Any = None,
    held_item: Optional[str] = None,
    area_id: Optional[str] = None,
) -> Optional[str]:
    return await resolve_for_trigger(
        conn,
        species_name,
        expected_trigger="level-up",
        level=level,
        friendship=friendship,
        gender=gender,
        moves=moves,
        held_item=held_item,
        area_id=area_id,
    )


async def resolve_item_evolution(
    conn: Any,
    species_name: str,
    item_id: str,
    *,
    friendship: Optional[int] = None,
    gender: Optional[str] = None,
    moves: Any = None,
    held_item: Optional[str] = None,
    area_id: Optional[str] = None,
) -> Optional[str]:
    item = norm_text(item_id)
    if not item:
        return None
    target = await resolve_for_trigger(
        conn,
        species_name,
        expected_trigger="use-item",
        friendship=friendship,
        gender=gender,
        moves=moves,
        held_item=held_item,
        item_used=item,
        area_id=area_id,
    )
    if target:
        return target
    return fallback_item_target(species_name, item)


async def suggest_item_evolution_item(conn: Any, species_name: str) -> Optional[str]:
    entries = await _combined_next_entries(conn, species_name)
    for entry in entries:
        for det in details_candidates(entry.get("details")):
            trigger = norm_text(unwrap_nameish(det.get("trigger")))
            item_id = norm_text(unwrap_nameish(det.get("item")))
            if trigger in {"use-item", "item"} and item_id:
                return item_id
    fallbacks = _ITEM_EVOLUTION_FALLBACK.get(norm_text(species_name), {})
    if fallbacks:
        return next(iter(fallbacks.keys()))
    return None

