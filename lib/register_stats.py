from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

from . import db

REGISTER_COST_PKC = 500_000

_REGISTER_TABLE_READY = False
_REGISTER_TABLE_LOCK = asyncio.Lock()
_LEGENDARY_SPECIES_CACHE: dict[str, bool] = {}

_COUNTER_FIELDS = (
    "times_traded",
    "eggs_bred",
    "total_routes",
    "total_exp_gained",
    "pokemon_beat",
    "shinies_killed",
    "legendaries_killed",
    "raids_won",
    "raids_lost",
    "battles_won",
    "battles_lost",
    "ribbons",
)


def normalize_move_id(move_name: Optional[str]) -> str:
    raw = str(move_name or "").strip().lower()
    if not raw:
        return ""
    return raw.replace("_", "-").replace(" ", "-")


def display_move_name(move_name: Optional[str]) -> str:
    raw = str(move_name or "").strip()
    if not raw:
        return "—"
    return raw.replace("_", " ").replace("-", " ").title()


def _is_positive_owner(owner_id: Any) -> bool:
    try:
        return int(str(owner_id)) > 0
    except Exception:
        return False


def _norm_species_key(species: Optional[str]) -> str:
    return str(species or "").strip().lower().replace("_", "-")


def _dict_from_row(row: Any) -> dict:
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    try:
        return dict(row)
    except Exception:
        return {}


def _parse_usage_blob(raw: Any) -> dict[str, int]:
    if isinstance(raw, dict):
        src = raw
    elif isinstance(raw, str):
        try:
            parsed = json.loads(raw) if raw else {}
            src = parsed if isinstance(parsed, dict) else {}
        except Exception:
            src = {}
    else:
        src = {}
    out: dict[str, int] = {}
    for k, v in src.items():
        key = normalize_move_id(str(k or ""))
        if not key:
            continue
        try:
            out[key] = max(0, int(v or 0))
        except Exception:
            continue
    return out


async def ensure_schema(conn: Any | None = None) -> None:
    global _REGISTER_TABLE_READY
    if _REGISTER_TABLE_READY:
        return
    async with _REGISTER_TABLE_LOCK:
        if _REGISTER_TABLE_READY:
            return
        owns_conn = conn is None
        c = conn
        if c is None:
            c = await db.connect()
        try:
            await c.execute(
                """
                CREATE TABLE IF NOT EXISTS registered_mons (
                    owner_id TEXT NOT NULL,
                    mon_id BIGINT NOT NULL,
                    species TEXT NOT NULL,
                    registered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    move_usage JSONB NOT NULL DEFAULT '{}'::jsonb,
                    most_used_move TEXT,
                    most_used_move_count INTEGER NOT NULL DEFAULT 0,
                    times_traded INTEGER NOT NULL DEFAULT 0,
                    eggs_bred INTEGER NOT NULL DEFAULT 0,
                    total_routes INTEGER NOT NULL DEFAULT 0,
                    total_exp_gained BIGINT NOT NULL DEFAULT 0,
                    pokemon_beat INTEGER NOT NULL DEFAULT 0,
                    shinies_killed INTEGER NOT NULL DEFAULT 0,
                    legendaries_killed INTEGER NOT NULL DEFAULT 0,
                    raids_won INTEGER NOT NULL DEFAULT 0,
                    raids_lost INTEGER NOT NULL DEFAULT 0,
                    battles_won INTEGER NOT NULL DEFAULT 0,
                    battles_lost INTEGER NOT NULL DEFAULT 0,
                    ribbons INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (owner_id, mon_id),
                    FOREIGN KEY (owner_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (mon_id) REFERENCES pokemons(id) ON DELETE CASCADE
                )
                """
            )
            if owns_conn:
                await c.commit()
            _REGISTER_TABLE_READY = True
        finally:
            if owns_conn:
                try:
                    await c.close()
                except Exception:
                    pass


async def _get_profile_conn(conn: Any, owner_id: str, mon_id: int) -> Optional[dict]:
    cur = await conn.execute(
        "SELECT * FROM registered_mons WHERE owner_id=? AND mon_id=? LIMIT 1",
        (str(owner_id), int(mon_id)),
    )
    row = await cur.fetchone()
    await cur.close()
    return _dict_from_row(row) if row else None


def _registered_set_from_cache(cache: Any, owner_id: str) -> set[int]:
    if not isinstance(cache, Mapping):
        return set()
    raw = cache.get(str(owner_id))
    if isinstance(raw, set):
        return {int(x) for x in raw if str(x).isdigit()}
    if isinstance(raw, (list, tuple)):
        out: set[int] = set()
        for x in raw:
            try:
                i = int(x)
            except Exception:
                continue
            if i > 0:
                out.add(i)
        return out
    return set()


def is_registered_in_battle_cache(st: Any, owner_id: str, mon_id: int) -> bool:
    if not owner_id:
        return False
    try:
        mid = int(mon_id)
    except Exception:
        return False
    if mid <= 0:
        return False
    cache = getattr(st, "_registered_mon_ids", None)
    mids = _registered_set_from_cache(cache, str(owner_id))
    return mid in mids


async def seed_battle_registration_cache(st: Any) -> dict[str, set[int]]:
    """
    Preload registered mon IDs for both sides once per battle.
    This lets move/KO hooks stay O(1) and avoids DB reads each turn/event.
    """
    owner_to_mon_ids: dict[str, set[int]] = {}
    for mon in list(getattr(st, "p1_team", []) or []) + list(getattr(st, "p2_team", []) or []):
        if mon is None:
            continue
        owner = str(getattr(mon, "_owner_id", "") or "")
        try:
            mon_id = int(getattr(mon, "_db_id", 0) or 0)
        except Exception:
            mon_id = 0
        if not _is_positive_owner(owner) or mon_id <= 0:
            continue
        owner_to_mon_ids.setdefault(owner, set()).add(mon_id)

    if not owner_to_mon_ids:
        setattr(st, "_registered_mon_ids", {})
        setattr(st, "_register_cache_ready", True)
        return {}

    out: dict[str, set[int]] = {owner: set() for owner in owner_to_mon_ids}
    async with db.session() as conn:
        await ensure_schema(conn)
        for owner, mon_ids in owner_to_mon_ids.items():
            mids = sorted({int(m) for m in mon_ids if int(m) > 0})
            if not mids:
                continue
            placeholders = ",".join("?" for _ in mids)
            cur = await conn.execute(
                f"SELECT mon_id FROM registered_mons WHERE owner_id=? AND mon_id IN ({placeholders})",
                (str(owner), *mids),
            )
            rows = await cur.fetchall()
            await cur.close()
            for row in rows or []:
                d = _dict_from_row(row)
                try:
                    mid = int(d.get("mon_id", 0) or 0)
                except Exception:
                    mid = 0
                if mid > 0:
                    out[str(owner)].add(mid)

    setattr(st, "_registered_mon_ids", out)
    setattr(st, "_register_cache_ready", True)
    return out


def buffer_exp_from_summary(st: Any, default_owner_id: str, exp_summary: Iterable[tuple[Any, int, int, int]]) -> None:
    """
    Buffer EXP gains in-memory for registered mons only.
    Flushed once in flush_battle_state().
    """
    cache = getattr(st, "_registered_mon_ids", None)
    cache_map = cache if isinstance(cache, Mapping) else None
    buf = getattr(st, "_registered_exp_gains", None)
    if not isinstance(buf, dict):
        buf = {}
        setattr(st, "_registered_exp_gains", buf)
    for item in exp_summary or []:
        if not isinstance(item, (tuple, list)) or len(item) < 2:
            continue
        mon = item[0]
        try:
            gain = int(item[1] or 0)
        except Exception:
            gain = 0
        if gain <= 0:
            continue
        owner = str(getattr(mon, "_owner_id", default_owner_id) or "")
        if not _is_positive_owner(owner):
            continue
        try:
            mon_id = int(getattr(mon, "_db_id", 0) or 0)
        except Exception:
            mon_id = 0
        if mon_id <= 0:
            continue
        if cache_map is not None:
            reg_ids = _registered_set_from_cache(cache_map, owner)
            if reg_ids and mon_id not in reg_ids:
                continue
        key = (owner, mon_id)
        buf[key] = int(buf.get(key, 0) or 0) + gain


def _split_key(key: Any) -> tuple[Optional[str], Optional[int]]:
    if isinstance(key, tuple) and len(key) >= 2:
        owner_raw, mon_raw = key[0], key[1]
    elif isinstance(key, str) and ":" in key:
        owner_raw, mon_raw = key.split(":", 1)
    else:
        return None, None
    try:
        owner_id = str(owner_raw)
        mon_id = int(mon_raw)
    except Exception:
        return None, None
    if mon_id <= 0 or not _is_positive_owner(owner_id):
        return None, None
    return owner_id, mon_id


def _merge_move_usage(dst: dict[str, int], delta: Mapping[str, Any]) -> None:
    for move, raw_count in (delta or {}).items():
        key = normalize_move_id(str(move or ""))
        if not key:
            continue
        try:
            n = int(raw_count or 0)
        except Exception:
            n = 0
        if n <= 0:
            continue
        dst[key] = max(0, int(dst.get(key, 0))) + n


def _resolve_most_used(usage: Mapping[str, int]) -> tuple[str, int]:
    best_move = ""
    best_count = 0
    for move, raw_count in usage.items():
        try:
            n = int(raw_count or 0)
        except Exception:
            n = 0
        if n <= 0:
            continue
        if n > best_count or (n == best_count and move < best_move):
            best_move = str(move)
            best_count = n
    return best_move, best_count


async def _apply_update_conn(
    conn: Any,
    owner_id: str,
    mon_id: int,
    *,
    deltas: Optional[Mapping[str, int]] = None,
    move_usage_delta: Optional[Mapping[str, int]] = None,
) -> bool:
    profile = await _get_profile_conn(conn, owner_id, mon_id)
    if not profile:
        return False

    counters = {f: max(0, int(profile.get(f, 0) or 0)) for f in _COUNTER_FIELDS}
    for k, v in (deltas or {}).items():
        if k not in counters:
            continue
        try:
            counters[k] = max(0, counters[k] + int(v or 0))
        except Exception:
            continue

    usage = _parse_usage_blob(profile.get("move_usage"))
    _merge_move_usage(usage, move_usage_delta or {})
    best_move, best_count = _resolve_most_used(usage)
    best_move = best_move or None  # type: ignore[assignment]

    await conn.execute(
        """
        UPDATE registered_mons
        SET
            move_usage=?,
            most_used_move=?,
            most_used_move_count=?,
            times_traded=?,
            eggs_bred=?,
            total_routes=?,
            total_exp_gained=?,
            pokemon_beat=?,
            shinies_killed=?,
            legendaries_killed=?,
            raids_won=?,
            raids_lost=?,
            battles_won=?,
            battles_lost=?,
            ribbons=?
        WHERE owner_id=? AND mon_id=?
        """,
        (
            json.dumps(usage, ensure_ascii=True),
            best_move,
            int(best_count),
            int(counters["times_traded"]),
            int(counters["eggs_bred"]),
            int(counters["total_routes"]),
            int(counters["total_exp_gained"]),
            int(counters["pokemon_beat"]),
            int(counters["shinies_killed"]),
            int(counters["legendaries_killed"]),
            int(counters["raids_won"]),
            int(counters["raids_lost"]),
            int(counters["battles_won"]),
            int(counters["battles_lost"]),
            int(counters["ribbons"]),
            str(owner_id),
            int(mon_id),
        ),
    )
    return True


async def get_profile(owner_id: str, mon_id: int) -> Optional[dict]:
    async with db.session() as conn:
        await ensure_schema(conn)
        return await _get_profile_conn(conn, owner_id, mon_id)


async def register_mon(owner_id: str, mon_id: int, species: str, *, cost: int = REGISTER_COST_PKC) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "created": False,
        "profile": None,
        "reason": "unknown_error",
        "balance": 0,
        "cost_charged": 0,
    }
    oid = str(owner_id)
    mid = int(mon_id)
    if mid <= 0:
        result["reason"] = "invalid_mon"
        return result

    async with db.session() as conn:
        await ensure_schema(conn)
        existing = await _get_profile_conn(conn, oid, mid)
        if existing:
            result.update({"ok": True, "created": False, "profile": existing, "reason": "already_registered"})
            return result

        await conn.execute(
            "INSERT INTO users(user_id, coins, currencies) VALUES(?, 0, '{\"coins\": 0}'::jsonb) ON CONFLICT(user_id) DO NOTHING",
            (oid,),
        )
        cur_user = await conn.execute("SELECT * FROM users WHERE user_id=? LIMIT 1", (oid,))
        user_row = await cur_user.fetchone()
        await cur_user.close()
        balance = int(db.get_currency_from_row(_dict_from_row(user_row), "coins"))
        result["balance"] = balance
        if balance < int(cost):
            result["reason"] = "insufficient_funds"
            return result

        await db.add_currency_conn(conn, oid, "coins", -int(cost))
        await conn.execute(
            """
            INSERT INTO registered_mons (
                owner_id, mon_id, species, move_usage, most_used_move, most_used_move_count
            ) VALUES (?, ?, ?, '{}'::jsonb, NULL, 0)
            """,
            (oid, mid, str(species or "unknown")),
        )
        await conn.commit()
        created = await _get_profile_conn(conn, oid, mid)
        result.update(
            {
                "ok": True,
                "created": True,
                "profile": created,
                "reason": "registered",
                "cost_charged": int(cost),
                "balance": max(0, balance - int(cost)),
            }
        )
        return result


async def update_registered_stats(
    owner_id: str,
    mon_id: int,
    *,
    deltas: Optional[Mapping[str, int]] = None,
    move_usage_delta: Optional[Mapping[str, int]] = None,
) -> bool:
    async with db.session() as conn:
        await ensure_schema(conn)
        updated = await _apply_update_conn(
            conn,
            str(owner_id),
            int(mon_id),
            deltas=deltas,
            move_usage_delta=move_usage_delta,
        )
        if updated:
            await conn.commit()
        return bool(updated)


async def increment_eggs_bred(owner_id: str, parent_mon_ids: Iterable[int], count: int = 1) -> None:
    try:
        n = max(0, int(count))
    except Exception:
        n = 0
    if n <= 0:
        return
    owner = str(owner_id)
    pids = []
    for pid in parent_mon_ids:
        try:
            mid = int(pid)
        except Exception:
            continue
        if mid > 0:
            pids.append(mid)
    if not pids:
        return
    async with db.session() as conn:
        await ensure_schema(conn)
        placeholders = ",".join("?" for _ in pids)
        cur = await conn.execute(
            f"SELECT mon_id FROM registered_mons WHERE owner_id=? AND mon_id IN ({placeholders})",
            (owner, *pids),
        )
        rows = await cur.fetchall()
        await cur.close()
        registered_ids = []
        for row in rows or []:
            d = _dict_from_row(row)
            try:
                rid = int(d.get("mon_id", 0) or 0)
            except Exception:
                rid = 0
            if rid > 0:
                registered_ids.append(rid)
        changed = False
        for rid in registered_ids:
            await conn.execute(
                "UPDATE registered_mons SET eggs_bred=GREATEST(0, eggs_bred + ?) WHERE owner_id=? AND mon_id=?",
                (int(n), owner, int(rid)),
            )
            changed = True
        if changed:
            await conn.commit()


async def increment_times_traded(owner_id: str, mon_id: int, delta: int = 1) -> None:
    try:
        d = int(delta)
    except Exception:
        d = 0
    if d == 0:
        return
    await update_registered_stats(str(owner_id), int(mon_id), deltas={"times_traded": d})


async def add_exp_from_summary(default_owner_id: str, exp_summary: Iterable[tuple[Any, int, int, int]]) -> None:
    agg: dict[tuple[str, int], int] = {}
    for item in exp_summary or []:
        if not isinstance(item, (tuple, list)) or len(item) < 2:
            continue
        mon = item[0]
        try:
            gain = int(item[1] or 0)
        except Exception:
            gain = 0
        if gain <= 0:
            continue
        mon_id = getattr(mon, "_db_id", None)
        if mon_id is None:
            continue
        try:
            mid = int(mon_id)
        except Exception:
            continue
        if mid <= 0:
            continue
        owner_raw = getattr(mon, "_owner_id", default_owner_id)
        owner = str(owner_raw)
        if not _is_positive_owner(owner):
            continue
        key = (owner, mid)
        agg[key] = agg.get(key, 0) + gain

    if not agg:
        return
    async with db.session() as conn:
        await ensure_schema(conn)
        changed = False
        for (owner, mid), gain in agg.items():
            ok = await _apply_update_conn(conn, owner, mid, deltas={"total_exp_gained": int(gain)})
            changed = changed or ok
        if changed:
            await conn.commit()


async def _is_legendary_species_conn(conn: Any, species: str) -> bool:
    key = _norm_species_key(species)
    if not key:
        return False
    if key in _LEGENDARY_SPECIES_CACHE:
        return _LEGENDARY_SPECIES_CACHE[key]

    candidates: list[str] = []
    for c in (key, key.replace("-", " "), key.replace(" ", "-")):
        c2 = str(c or "").strip().lower()
        if c2 and c2 not in candidates:
            candidates.append(c2)
    # Try peeling form suffixes (e.g. mewtwo-mega-x -> mewtwo).
    peeled = key
    while "-" in peeled:
        peeled = peeled.rsplit("-", 1)[0].strip()
        if len(peeled) >= 3 and peeled not in candidates:
            candidates.append(peeled)

    is_legend = False
    for cand in candidates:
        cur = await conn.execute(
            "SELECT is_legendary, is_mythical, category FROM pokedex WHERE LOWER(name)=? LIMIT 1",
            (cand,),
        )
        row = await cur.fetchone()
        await cur.close()
        if not row:
            continue
        d = _dict_from_row(row)
        try:
            is_legend = bool(d.get("is_legendary")) or bool(d.get("is_mythical"))
            if not is_legend:
                cat = str(d.get("category") or "").strip().lower()
                is_legend = ("legendary" in cat) or ("mythical" in cat)
        except Exception:
            is_legend = False
        if is_legend:
            break

    _LEGENDARY_SPECIES_CACHE[key] = bool(is_legend)
    return bool(is_legend)


async def flush_battle_state(st: Any) -> None:
    """
    Flush in-battle registered-mon tracking buffers to DB.
    Expects optional fields on BattleState:
      - _registered_move_usage[(owner_id, mon_id)] = {move_id: count}
      - _registered_ko_stats[(owner_id, mon_id)] = {pokemon_beat, shinies_killed, species_kos}
      - p1_participants / p2_participants for route/raid/battle W-L counters
    """
    agg: dict[tuple[str, int], dict[str, Any]] = {}
    registered_cache = getattr(st, "_registered_mon_ids", None)

    def _entry(owner_id: str, mon_id: int) -> dict[str, Any]:
        key = (str(owner_id), int(mon_id))
        if key not in agg:
            agg[key] = {"deltas": defaultdict(int), "moves": defaultdict(int), "species_kos": defaultdict(int)}
        return agg[key]

    # Move usage from buffered move events.
    move_buf = getattr(st, "_registered_move_usage", None) or {}
    for raw_key, usage in move_buf.items():
        owner, mon_id = _split_key(raw_key)
        if owner is None or mon_id is None:
            continue
        if not isinstance(usage, Mapping):
            continue
        rec = _entry(owner, mon_id)
        for mv, cnt in usage.items():
            key = normalize_move_id(str(mv or ""))
            if not key:
                continue
            try:
                n = int(cnt or 0)
            except Exception:
                n = 0
            if n > 0:
                rec["moves"][key] += n

    # KO stats from buffered faint events.
    ko_buf = getattr(st, "_registered_ko_stats", None) or {}
    for raw_key, payload in ko_buf.items():
        owner, mon_id = _split_key(raw_key)
        if owner is None or mon_id is None:
            continue
        if not isinstance(payload, Mapping):
            continue
        rec = _entry(owner, mon_id)
        for fld in ("pokemon_beat", "shinies_killed"):
            try:
                n = int(payload.get(fld, 0) or 0)
            except Exception:
                n = 0
            if n > 0:
                rec["deltas"][fld] += n
        species_kos = payload.get("species_kos")
        if isinstance(species_kos, Mapping):
            for sp, cnt in species_kos.items():
                species_key = _norm_species_key(str(sp or ""))
                if not species_key:
                    continue
                try:
                    n = int(cnt or 0)
                except Exception:
                    n = 0
                if n > 0:
                    rec["species_kos"][species_key] += n

    # EXP gains buffered during battle; registered-only by design.
    exp_buf = getattr(st, "_registered_exp_gains", None) or {}
    if isinstance(exp_buf, Mapping):
        for raw_key, raw_gain in exp_buf.items():
            owner, mon_id = _split_key(raw_key)
            if owner is None or mon_id is None:
                continue
            try:
                gain = int(raw_gain or 0)
            except Exception:
                gain = 0
            if gain <= 0:
                continue
            rec = _entry(owner, mon_id)
            rec["deltas"]["total_exp_gained"] += gain

    # Per-battle summary counters (routes, raids, battles).
    fmt = str(getattr(st, "fmt_label", "") or "").strip().lower()
    is_adventure = fmt.startswith("adventure") or fmt == "rival"
    is_raid = "raid" in fmt
    winner = getattr(st, "winner", None)
    sides = [
        (getattr(st, "p1_id", None), getattr(st, "p1_participants", set())),
        (getattr(st, "p2_id", None), getattr(st, "p2_participants", set())),
    ]
    for owner_raw, participants in sides:
        owner_id = str(owner_raw or "")
        if not _is_positive_owner(owner_id):
            continue
        mids: set[int] = set()
        for token in (participants or set()):
            try:
                mid = int(token)
            except Exception:
                continue
            if mid > 0:
                mids.add(mid)
        if not mids:
            continue
        reg_ids = _registered_set_from_cache(registered_cache, owner_id)
        if reg_ids:
            mids = {mid for mid in mids if mid in reg_ids}
        if not mids:
            continue
        for mid in mids:
            rec = _entry(owner_id, mid)
            if is_adventure:
                rec["deltas"]["total_routes"] += 1
            elif is_raid:
                if winner == owner_raw:
                    rec["deltas"]["raids_won"] += 1
                elif winner in (getattr(st, "p1_id", None), getattr(st, "p2_id", None)):
                    rec["deltas"]["raids_lost"] += 1
            else:
                if winner == owner_raw:
                    rec["deltas"]["battles_won"] += 1
                elif winner in (getattr(st, "p1_id", None), getattr(st, "p2_id", None)):
                    rec["deltas"]["battles_lost"] += 1

    if not agg:
        return

    async with db.session() as conn:
        await ensure_schema(conn)
        changed = False
        for (owner, mon_id), payload in agg.items():
            deltas = dict(payload["deltas"])
            species_kos = payload.get("species_kos") or {}
            if species_kos:
                legends = 0
                for species_key, count in species_kos.items():
                    if count <= 0:
                        continue
                    if await _is_legendary_species_conn(conn, str(species_key)):
                        legends += int(count)
                if legends > 0:
                    deltas["legendaries_killed"] = int(deltas.get("legendaries_killed", 0)) + legends

            ok = await _apply_update_conn(
                conn,
                owner,
                mon_id,
                deltas=deltas,
                move_usage_delta=dict(payload["moves"]),
            )
            changed = changed or ok
        if changed:
            await conn.commit()
