from __future__ import annotations

import os
import json
import asyncio
from pathlib import Path
from typing import Tuple, List, Dict, Any, Optional

from .db_pool import get_connection, get_pool

try:
    from lib import db_cache
except ImportError:
    db_cache = None


def _open():
    """Get a connection from the pool. Use with get_connection() context manager when possible."""
    return get_pool().get_connection()


def _close_conn(conn) -> None:
    """Return a connection to the pool."""
    get_pool().return_connection(conn)


def _table_exists(conn, name: str) -> bool:
    try:
        r = conn.execute(
            "SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = ? LIMIT 1",
            (name,),
        ).fetchone()
        return bool(r)
    except Exception:
        return False

def _safe_json(s: Any, dflt):
    if s is None or s == "":
        return dflt
    if isinstance(s, (dict, list)):
        return s
    try:
        return json.loads(s)
    except Exception:
        return dflt

def _gender_female(g: Any) -> bool:
    if g is None:
        return False
    s = str(g).strip().lower()
    return s in ("f", "female", "1", "true")

def _title_type(t: str) -> str:
    # map "fire" -> "Fire", etc.
    return (t or "Normal").strip().lower().capitalize()

# ─────────────────────── PP persistence (PvE) ───────────────────────

def _fetch_move_default(name: str) -> Dict[str, Any]:
    return {
        "name": name,
        "type": "Normal",
        "category": "Physical",
        "power": 40,
        "accuracy": 100,
        "priority": 0,
        "contact": 0,
        "pp": 20,
    }

def _move_row_to_fetch_shape(r: Dict[str, Any]) -> Dict[str, Any]:
    dmg_class = (r.get("damage_class") or "").strip().lower()
    if dmg_class == "physical": category = "Physical"
    elif dmg_class == "special": category = "Special"
    else: category = "Status"
    raw_meta = r.get("meta")
    try:
        meta = json.loads(raw_meta) if isinstance(raw_meta, str) and raw_meta else (raw_meta or {})
    except Exception:
        meta = {}
    contact = int(bool(meta.get("makes_contact", False)))
    priority = int(meta.get("priority", 0))
    acc = r.get("accuracy")
    return {
        "name": r.get("name") or "",
        "type": (r.get("type") or "Normal").capitalize(),
        "category": category,
        "power": int(r.get("power") or 0),
        "accuracy": None if acc in (None, "", 0) else int(acc),
        "priority": priority,
        "contact": contact,
        "pp": int(r.get("pp") or 20),
    }

def fetch_move(name: str) -> Dict[str, Any]:
    """
    Read a move from your 'moves' table and return a normalized dict:
      {name, type, category, power, accuracy, priority, contact, pp}
    """
    if db_cache:
        for key in (name, name.lower().replace(" ", "-"), name.replace("-", " ")):
            r = db_cache.get_cached_move(key)
            if r:
                return _move_row_to_fetch_shape(r)
    with get_connection() as con:
        r = con.execute(
            "SELECT * FROM moves WHERE name = ? COLLATE NOCASE",
            (name,),
        ).fetchone()
        if not r:
            return _fetch_move_default(name)
        row = dict(r) if hasattr(r, "keys") and not isinstance(r, dict) else r
        return _move_row_to_fetch_shape(row)

def _get_active_row_by_slot(owner_id: int, team_slot: int) -> Optional[Any]:
    with get_connection() as con:
        r = con.execute(
            "SELECT rowid, moves, moves_pp FROM pokemons WHERE owner_id=? AND team_slot=?",
            (int(owner_id), int(team_slot)),
        ).fetchone()
        return r

def get_moves_pp(owner_id: int, team_slot: int) -> Optional[List[int]]:
    """Return current PP array aligned with `moves` for the given party slot; None if no moves."""
    with get_connection() as con:
        r = con.execute(
            "SELECT moves, moves_pp FROM pokemons WHERE owner_id=? AND team_slot=?",
            (int(owner_id), int(team_slot)),
        ).fetchone()
        if not r:
            return None
        try:
            moves = json.loads(r["moves"]) if r["moves"] else []
        except Exception:
            moves = []
        if not moves:
            return None
        try:
            raw_pps = r["moves_pp"]
            if isinstance(raw_pps, list):
                pps = raw_pps
            elif raw_pps:
                pps = json.loads(raw_pps)
            else:
                pps = None
        except Exception:
            pps = None
        return pps if pps is not None else None

def ensure_moves_pp(owner_id: int, team_slot: int) -> List[int]:
    """Ensure moves_pp exists; if missing, initialize from base PP and persist."""
    with get_connection() as con:
        r = con.execute(
            "SELECT rowid, moves, moves_pp FROM pokemons WHERE owner_id=? AND team_slot=?",
            (int(owner_id), int(team_slot)),
        ).fetchone()
        if not r:
            return []
        try:
            moves = json.loads(r["moves"]) if r["moves"] else []
        except Exception:
            moves = []
        if not moves:
            cur_pp: List[int] = []
        else:
            if r["moves_pp"]:
                try:
                    raw_pps = r["moves_pp"]
                    if isinstance(raw_pps, list):
                        cur_pp = raw_pps
                    else:
                        cur_pp = json.loads(raw_pps)
                    if not isinstance(cur_pp, list) or len(cur_pp) != len(moves):
                        raise ValueError
                except Exception:
                    cur_pp = []
            else:
                cur_pp = []
            if not cur_pp:
                # init from base pp of each move
                base_pps = [int(fetch_move(m).get("pp", 20)) for m in moves]
                con.execute(
                    "UPDATE pokemons SET moves_pp=? WHERE rowid=?",
                    (json.dumps(base_pps), r["rowid"]),
                )
                con.commit()
                cur_pp = base_pps
        return cur_pp

def spend_pp(owner_id: int, team_slot: int, move_index: int, amount: int = 1) -> bool:
    """Decrement PP for a move index; returns True if spent, False if no PP."""
    with get_connection() as con:
        r = con.execute(
            "SELECT rowid, moves, moves_pp FROM pokemons WHERE owner_id=? AND team_slot=?",
            (int(owner_id), int(team_slot)),
        ).fetchone()
        if not r:
            return False
        moves = json.loads(r["moves"]) if r["moves"] else []
        if not moves or not (0 <= move_index < len(moves)):
            return False
        pps = json.loads(r["moves_pp"]) if r["moves_pp"] else None
        if pps is None or not isinstance(pps, list) or len(pps) != len(moves):
            # re-init
            pps = [int(fetch_move(m).get("pp", 20)) for m in moves]
        if int(pps[move_index]) <= 0:
            return False
        pps[move_index] = max(0, int(pps[move_index]) - int(amount))
        con.execute("UPDATE pokemons SET moves_pp=? WHERE rowid=?", (json.dumps(pps), r["rowid"]))
        con.commit()
        return True

def restore_pp(owner_id: int, team_slot: int, move_index: Optional[int] = None, frac: Optional[tuple] = None, full: bool = False):
    """
    Restore PP for a move (Ether) or all moves (Elixir).
    - move_index: which move to target (0..len-1); ignored for full=True.
    - frac: (n,d) to restore fraction of base PP (e.g., (1,5) = 20%)
    - full: restore to base PP.
    """
    with get_connection() as con:
        r = con.execute(
            "SELECT rowid, moves, moves_pp FROM pokemons WHERE owner_id=? AND team_slot=?",
            (int(owner_id), int(team_slot)),
        ).fetchone()
        if not r:
            return
        moves = json.loads(r["moves"]) if r["moves"] else []
        if not moves:
            return
        try:
            pps = json.loads(r["moves_pp"]) if r["moves_pp"] else [0] * len(moves)
        except Exception:
            pps = [0] * len(moves)
        base = [int(fetch_move(m).get("pp", 20)) for m in moves]
        if full:
            new_pp = base
        else:
            new_pp = list(pps)
            if move_index is None or not (0 <= move_index < len(moves)):
                return
            if frac is None:
                inc = base[move_index]
            else:
                n, d = frac
                inc = max(1, int(base[move_index] * n / d))
            new_pp[move_index] = min(base[move_index], int(new_pp[move_index]) + inc)
        con.execute("UPDATE pokemons SET moves_pp=? WHERE rowid=?", (json.dumps(new_pp), r["rowid"]))
        con.commit()

# ─────────────────────── public: simple team ───────────────────────

async def get_active_team(user_id: int) -> List[Dict[str, Any]]:
    """
    Lightweight party for your current UI:
      [{ species, level, hp, item, moves[], is_shiny, is_female }, ...]
    Ordered by team_slot ASC.
    """
    def _work():
        from .db_pool import get_connection
        with get_connection() as conn:
            if not _table_exists(conn, "pokemons"):
                return []
            rows = conn.execute(
                "SELECT species, level, hp, held_item, moves, shiny, gender, team_slot "
                "FROM pokemons WHERE owner_id=? AND team_slot IS NOT NULL "
                "ORDER BY team_slot ASC",
                (int(user_id),),
            ).fetchall()

            team: List[Dict[str, Any]] = []
            for r in rows:
                moves = _safe_json(r["moves"], [])
                team.append({
                    "species": (r["species"] or "").strip(),
                    "level": int(r["level"] or 100),
                    "hp": int(r["hp"] or 100),
                    "item": (r["held_item"] or None),
                    "moves": [str(m).strip() for m in moves][:4] or ["Tackle"],
                    "is_shiny": bool(r["shiny"]),
                    "is_female": _gender_female(r["gender"]),
                })
            return team
    return await asyncio.to_thread(_work)

# ─────────────────────── public: sprites ───────────────────────

async def get_active_sprite_info(user_id: int) -> Tuple[str, bool, bool]:
    """
    (species, is_female, is_shiny) for the user's lead.
    Uses team_slot=1 as the active lead (or first row with team_slot if 1 missing).
    """
    def _work():
        with get_connection() as conn:
            if not _table_exists(conn, "pokemons"):
                return ("", False, False)
            row = conn.execute(
                "SELECT species, gender, shiny FROM pokemons WHERE owner_id=? AND team_slot=1 LIMIT 1",
                (int(user_id),),
            ).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT species, gender, shiny FROM pokemons WHERE owner_id=? AND team_slot IS NOT NULL ORDER BY team_slot ASC LIMIT 1",
                    (int(user_id),),
                ).fetchone()
            if not row:
                return ("", False, False)
            return (
                (row["species"] or "").strip(),
                _gender_female(row["gender"]),
                bool(row["shiny"]),
            )
    return await asyncio.to_thread(_work)

# ─────────────────────── public: rich team for engine ───────────────────────
# NOTE: The actual implementation is below (newer version with form/shiny support)

async def get_party_for_engine(user_id: int, *, save_to_battle_cache: bool = False) -> List[Dict[str, Any]]:
    """
    Get user's team data formatted for the battle engine and legality checking.
    Returns list of Pokémon dictionaries with all necessary fields.

    When save_to_battle_cache=True (battle start), the result is stored in
    battle-scoped cache and cleared when the battle ends.
    """
    if db_cache:
        cached = db_cache.get_battle_party_cached(user_id)
        if cached is not None:
            return cached
        party_cached = db_cache.get_cached_party(str(user_id))
        if party_cached is not None:
            if save_to_battle_cache:
                db_cache.set_battle_party_cached(user_id, party_cached)
            return party_cached
    with get_connection() as conn:
        can_gmax_expr = "COALESCE(p.can_gigantamax::int, 0)"
        cur = conn.execute(f"""
            SELECT p.*, pd.id as species_id, pd.name as species_name, pd.introduced_in, pd.types, pd.stats, pd.abilities, pd.is_fully_evolved, pd.weight_kg, pd.form_name,
                   {can_gmax_expr} as can_gigantamax
            FROM pokemons p
            LEFT JOIN pokedex pd ON LOWER(p.species) = LOWER(pd.name)
            WHERE p.owner_id = ? AND p.team_slot IS NOT NULL
            ORDER BY p.team_slot
            LIMIT 6
        """, (str(user_id),))
        
        rows = cur.fetchall()
        team = []

        # Batch load mega evolutions for all species in the party
        mega_by_species_id: Dict[Any, List[Dict[str, Any]]] = {}
        species_ids = [r["species_id"] for r in rows if r and r.get("species_id") is not None]
        species_ids = list(dict.fromkeys(species_ids))

        if species_ids:
            try:
                if db_cache and getattr(db_cache, "get_cached_mega_evolution", None):
                    cached_mega = db_cache.get_cached_mega_evolution()
                else:
                    cached_mega = None
                if cached_mega:
                    for mrow in cached_mega:
                        bsid = mrow.get("base_species_id")
                        if bsid in species_ids:
                            mega_by_species_id.setdefault(bsid, []).append(mrow)
                else:
                    ph = ",".join(["?"] * len(species_ids))
                    mega_rows = conn.execute(
                        f"""
                        SELECT base_species_id, mega_form, mega_stone, form_key, stats, types, abilities, introduced_in
                        FROM mega_evolution
                        WHERE base_species_id IN ({ph})
                        """,
                        tuple(species_ids),
                    ).fetchall()
                    for mrow in mega_rows:
                        bsid = mrow["base_species_id"]
                        mega_by_species_id.setdefault(bsid, []).append(dict(mrow) if hasattr(mrow, "keys") else mrow)
            except Exception:
                mega_by_species_id = {}

        for row in rows:
            # Parse JSON fields
            ivs_raw = json.loads(row["ivs"]) if row["ivs"] else {}
            evs_raw = json.loads(row["evs"]) if row["evs"] else {}
            moves = json.loads(row["moves"]) if row["moves"] else []
            types = json.loads(row["types"]) if row["types"] else []
            stats_raw = json.loads(row["stats"]) if row["stats"] else {}
            abilities = json.loads(row["abilities"]) if row["abilities"] else []
            
            # Normalize stat keys for engine.py (def -> defn, defense -> defn, etc.)
            # IMPORTANT: Use 'in' check to handle 0 values correctly (0 is falsy but valid)
            def normalize_stats(s):
                return {
                    "hp": s.get("hp") if "hp" in s else (s.get("HP") if "HP" in s else 31),
                    "atk": s.get("atk") if "atk" in s else (s.get("attack") if "attack" in s else (s.get("Attack") if "Attack" in s else 31)),
                    "defn": s.get("def") if "def" in s else (s.get("defn") if "defn" in s else (s.get("defense") if "defense" in s else (s.get("Defense") if "Defense" in s else 31))),
                    "spa": s.get("spa") if "spa" in s else (s.get("special_attack") if "special_attack" in s else (s.get("SpecialAttack") if "SpecialAttack" in s else 31)),
                    "spd": s.get("spd") if "spd" in s else (s.get("special_defense") if "special_defense" in s else (s.get("SpecialDefense") if "SpecialDefense" in s else 31)),
                    "spe": s.get("spe") if "spe" in s else (s.get("speed") if "speed" in s else (s.get("Speed") if "Speed" in s else 31)),
                }
            
            # Normalize IVs, EVs, and base stats
            ivs = normalize_stats(ivs_raw)
            evs = normalize_stats(evs_raw)
            stats = normalize_stats(stats_raw)
            
            # Get ability from the Pokémon's stored ability (from pokemons.ability column)
            # This respects the user's chosen ability (normal or hidden)
            ability_name = row["ability"]
            
            # If no ability is stored, fall back to first non-hidden ability from pokedex
            if not ability_name and abilities:
                for ab in abilities:
                    if not ab.get("is_hidden", False):
                        ability_name = ab.get("name")
                        break
                if not ability_name and abilities:
                    ability_name = abilities[0].get("name")
            
            # Get form: use pokemons.form if set, otherwise fall back to pokedex.form_name
            # Convert row to dict to use .get() method
            row_dict = dict(row)
            form = row_dict.get("form") if row_dict.get("form") else row_dict.get("form_name")
            
            # If Pokémon has a form, try to get form-specific overrides from pokedex_forms
            # This ensures we get the correct base stats, types, and abilities for the specific form
            if form and form not in ["normal", "default", None]:
                # Try form as-is first (e.g., "wash")
                form_overrides = get_form_overrides(row["species"], form)
                # If not found, try with species prefix (e.g., "rotom-wash")
                if not form_overrides and not form.startswith(f"{row['species']}-"):
                    form_overrides = get_form_overrides(row["species"], f"{row['species']}-{form}")
                if form_overrides:
                    # Apply form-specific stats if available
                    if form_overrides.get("stats"):
                        form_stats_normalized = normalize_stats(form_overrides["stats"])
                        stats = form_stats_normalized
                    
                    # Apply form-specific types if available (e.g., Rotom forms)
                    if form_overrides.get("types"):
                        types = form_overrides["types"]
                        if isinstance(types, str):
                            try:
                                types = json.loads(types)
                            except Exception:
                                types = []
            
            # Convert types list to tuple for engine.py
            types_tuple = (types[0] if len(types) > 0 else "Normal", types[1] if len(types) > 1 else None)
            
            hp_now_val = row_dict.get("hp_now")
            if hp_now_val is None:
                hp_now_val = row["hp"]

            # Derive level from exp if exp is set (authoritative) using exp_requirements table
            # Fallback to stored level if exp is missing.
            resolved_level = row["level"]
            try:
                if row_dict.get("exp") is not None and row_dict.get("exp_group"):
                    exp_val = int(row_dict["exp"])
                    exp_group = (str(row_dict.get("exp_group") or "")).strip().lower().replace(" ", "_")
                    if db_cache and getattr(db_cache, "get_cached_exp_requirements", None):
                        exp_rows = db_cache.get_cached_exp_requirements()
                        if exp_rows:
                            best = resolved_level
                            for r in exp_rows:
                                if str(r.get("group_code") or "").strip().lower().replace(" ", "_") != exp_group:
                                    continue
                                lvl = int(r.get("level") or 0)
                                total = int(r.get("exp_total") or 0)
                                if total <= exp_val and lvl > best:
                                    best = lvl
                            resolved_level = best
                        else:
                            lvl_row = conn.execute(
                                "SELECT level FROM exp_requirements WHERE group_code = ? AND exp_total <= ? ORDER BY level DESC LIMIT 1",
                                (exp_group, exp_val),
                            ).fetchone()
                            if lvl_row and lvl_row[0]:
                                resolved_level = int(lvl_row[0])
                    else:
                        lvl_row = conn.execute(
                            "SELECT level FROM exp_requirements WHERE group_code = ? AND exp_total <= ? ORDER BY level DESC LIMIT 1",
                            (exp_group, exp_val),
                        ).fetchone()
                        if lvl_row and lvl_row[0]:
                            resolved_level = int(lvl_row[0])
            except Exception:
                pass

            mon_data = {
                "id": row["id"],
                "owner_id": row["owner_id"],
                "species_id": row["species_id"],  # This is the pokedex ID needed for move validation
                "species": row["species"],
                "species_name": row["species_name"],
                "level": resolved_level,
                "hp_now": hp_now_val,  # Current HP for battle
                "ivs": ivs,
                "evs": evs,
                "nature": row["nature"],
                "ability": ability_name,
                "gender": row["gender"],
                "friendship": row["friendship"],
                "item": row["held_item"],
                "moves": moves,
                "team_slot": row["team_slot"],
                "introduced_in": row["introduced_in"],
                "types": types_tuple,  # Tuple format (type1, type2 or None)
                "base": stats,  # Base stats dict (not base_stats)
                "is_shiny": bool(row["shiny"]),  # Load actual shiny status from database
                "is_female": row["gender"] == "female",
                "is_fully_evolved": bool(row["is_fully_evolved"]) if row["is_fully_evolved"] is not None else True,  # For Eviolite
                "weight_kg": float(row["weight_kg"]) if row["weight_kg"] is not None else 100.0,  # Weight for Low Kick/Grass Knot
                "form": form,  # Add form to the data
                "can_gigantamax": bool(row_dict.get("can_gigantamax", 0)) if "can_gigantamax" in row_dict else False,  # Gigantamax capability
                "tera_type": row_dict.get("tera_type"),
                "exp": row_dict.get("exp"),
                "exp_group": (str(row_dict.get("exp_group") or "medium_fast")).strip().lower().replace(" ", "_"),
            }
            mega_map: Dict[str, Dict[str, Any]] = {}
            try:
                mega_rows = mega_by_species_id.get(row["species_id"], []) if mega_by_species_id else []
                for mrow in mega_rows:
                    data = dict(mrow) if hasattr(mrow, "keys") else mrow
                    mega_form = data.get("mega_form")
                    if not mega_form:
                        continue
                    mega_map[str(mega_form)] = {
                        "mega_form": data.get("mega_form"),
                        "mega_stone": data.get("mega_stone"),
                        "form_key": data.get("form_key"),
                        "stats": data.get("stats"),
                        "types": data.get("types"),
                        "abilities": data.get("abilities"),
                        "introduced_in": data.get("introduced_in"),
                    }
            except Exception:
                mega_map = {}
            if mega_map:
                mon_data["mega_evolutions"] = mega_map
            team.append(mon_data)
        if db_cache:
            db_cache.set_cached_party(str(user_id), team)
            if save_to_battle_cache:
                db_cache.set_battle_party_cached(user_id, team)
        return team

# ─────────────────────── public: forms lookup for engine ───────────────────────

def _parse_form_field(x: Any, d: Any) -> Any:
    try:
        return json.loads(x) if x and isinstance(x, str) else (x if x is not None else d)
    except Exception:
        return d

def get_form_overrides(species_name: str, form_key: str) -> Optional[Dict[str, Any]]:
    """
    Return form overrides from pokedex_forms for (species_name, form_key).
    Keys: stats (dict), types (list), abilities (list)
    """
    sn, fk = (species_name or "").strip().lower(), (form_key or "").strip().lower()
    if db_cache:
        forms = db_cache.get_cached_pokedex_forms()
        if forms:
            for r in forms:
                rsn = (r.get("species_name") or "").strip().lower()
                rfk = (r.get("form_key") or "").strip().lower()
                if rsn == sn and rfk == fk:
                    return {
                        "stats": _parse_form_field(r.get("stats"), {}),
                        "types": _parse_form_field(r.get("types"), []),
                        "abilities": _parse_form_field(r.get("abilities"), []),
                    }
            if not fk.startswith(f"{sn}-"):
                prefixed = f"{species_name}-{form_key}".strip().lower()
                for r in forms:
                    rsn = (r.get("species_name") or "").strip().lower()
                    rfk = (r.get("form_key") or "").strip().lower()
                    if rsn == sn and rfk == prefixed:
                        return {
                            "stats": _parse_form_field(r.get("stats"), {}),
                            "types": _parse_form_field(r.get("types"), []),
                            "abilities": _parse_form_field(r.get("abilities"), []),
                        }
    with get_connection() as con:
        r = con.execute(
            """
            SELECT stats, types, abilities
            FROM pokedex_forms
            WHERE LOWER(species_name)=LOWER(?) AND LOWER(form_key)=LOWER(?)
            LIMIT 1
            """,
            (species_name, form_key),
        ).fetchone()
        if not r and not form_key.lower().startswith(f"{species_name.lower()}-"):
            prefixed_form = f"{species_name}-{form_key}"
            r = con.execute(
                """
                SELECT stats, types, abilities
                FROM pokedex_forms
                WHERE LOWER(species_name)=LOWER(?) AND LOWER(form_key)=LOWER(?)
                LIMIT 1
                """,
                (species_name, prefixed_form),
            ).fetchone()
        if not r:
            return None
        row = dict(r) if hasattr(r, "keys") and not isinstance(r, dict) else r
        return {
            "stats": _parse_form_field(row.get("stats"), {}),
            "types": _parse_form_field(row.get("types"), []),
            "abilities": _parse_form_field(row.get("abilities"), []),
        }
