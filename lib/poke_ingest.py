# lib/poke_ingest.py
from __future__ import annotations
import aiohttp, asyncio, re
from typing import Any, Iterable
from . import db
import json
try:
    from . import db_cache
except ImportError:
    db_cache = None
POKEMON_URL   = "https://pokeapi.co/api/v2/pokemon/{key}"
SPECIES_URL   = "https://pokeapi.co/api/v2/pokemon-species/{key}"
MOVE_URL      = "https://pokeapi.co/api/v2/move/{key}"

VERSION_GROUP_TO_GEN = {
    # 1
    "red-blue":1, "yellow":1,
    # 2
    "gold-silver":2, "crystal":2,
    # 3
    "ruby-sapphire":3, "emerald":3, "firered-leafgreen":3, "colosseum":3, "xd":3,
    # 4
    "diamond-pearl":4, "platinum":4, "heartgold-soulsilver":4,
    # 5
    "black-white":5, "black-2-white-2":5,
    # 6
    "x-y":6, "omega-ruby-alpha-sapphire":6,
    # 7
    "sun-moon":7, "ultra-sun-ultra-moon":7, "lets-go-pikachu-lets-go-eevee":7,
    # 8
    "sword-shield":8, "brilliant-diamond-and-shining-pearl":8, "legends-arceus":8,
    # 9
    "scarlet-violet":9,
}

_re_id = re.compile(r"/(\d+)/?$")

async def _fetch_json(session: aiohttp.ClientSession, url: str) -> dict[str, Any]:
    async with session.get(url, headers={"User-Agent": "MyuuCloneBot/1.0"}) as resp:
        resp.raise_for_status()
        return await resp.json()

def _id_from_url(url: str) -> int | None:
    m = _re_id.search(url)
    return int(m.group(1)) if m else None

# ---------- MOVES ----------
async def ensure_move(session: aiohttp.ClientSession, key: str | int) -> int:
    # returns move_id in DB
    # Check cache
    name = str(key).lower()
    if isinstance(key, int) or name.isdigit():
        # move id fetch anyway; we want metadata
        pass
    j = await _fetch_json(session, MOVE_URL.format(key=name))
    mid = j["id"]
    meta = j.get("meta") or {}
    row = {
        "id": mid,
        "name": j["name"].lower(),
        "introduced_in": _id_from_url(j["generation"]["url"]),
        "type": (j.get("type") or {}).get("name"),
        "power": j.get("power"),
        "accuracy": j.get("accuracy"),
        "pp": j.get("pp"),
        "damage_class": (j.get("damage_class") or {}).get("name"),
        "meta": {
            "crit_rate": meta.get("crit_rate"),
            "drain": meta.get("drain"),
            "flinch_chance": meta.get("flinch_chance"),
            "healing": meta.get("healing"),
            "min_hits": meta.get("min_hits"),
            "max_hits": meta.get("max_hits"),
            "min_turns": meta.get("min_turns"),
            "max_turns": meta.get("max_turns"),
            "stat_chance": meta.get("stat_chance"),
            "ailment": (meta.get("ailment") or {}).get("name"),
            "category": (meta.get("category") or {}).get("name"),
        },
    }
    # upsert move
    conn = await db.connect()
    await conn.execute("""
        INSERT INTO moves (id,name,introduced_in,type,power,accuracy,pp,damage_class,meta)
        VALUES (?,?,?,?,?,?,?,?,json(?))
        ON CONFLICT(id) DO UPDATE SET
          name=excluded.name,
          introduced_in=excluded.introduced_in,
          type=excluded.type,
          power=excluded.power,
          accuracy=excluded.accuracy,
          pp=excluded.pp,
          damage_class=excluded.damage_class,
          meta=excluded.meta
    """, (row["id"], row["name"], row["introduced_in"], row["type"], row["power"],
          row["accuracy"], row["pp"], row["damage_class"], db.json.dumps(row["meta"]) if hasattr(db, "json") else __import__("json").dumps(row["meta"])))
    await conn.commit()
    if db_cache is not None:
        try:
            db_cache.invalidate_move(row["name"])
        except Exception:
            pass
    return mid

# ---------- SPECIES + LEARNSETS ----------
async def ensure_species_and_learnsets(key: str | int) -> dict[str, Any]:
    # 1) cache hit?
    cached = None
    if isinstance(key, int) or (isinstance(key, str) and key.isdigit()):
        cached = await db.get_pokedex_by_id(int(key))
    else:
        cached = await db.get_pokedex_by_name(str(key).lower())
    if cached:
        return cached

    # 2) fetch
    key_s = str(key).lower()
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        p_task = asyncio.create_task(_fetch_json(session, POKEMON_URL.format(key=key_s)))
        s_task = asyncio.create_task(_fetch_json(session, SPECIES_URL.format(key=key_s)))
        p, s = await asyncio.gather(p_task, s_task)

        # normalize species core
        types = [t["type"]["name"] for t in sorted(p["types"], key=lambda x: x["slot"])]
        base_map = {st["stat"]["name"]: st["base_stat"] for st in p["stats"]}
        stats = {
            "hp": base_map.get("hp",0),
            "attack": base_map.get("attack",0),
            "defense": base_map.get("defense",0),
            "special_attack": base_map.get("special-attack",0),
            "special_defense": base_map.get("special-defense",0),
            "speed": base_map.get("speed",0),
        }
        abilities = [{
            "name": a["ability"]["name"],
            "id": _id_from_url(a["ability"]["url"]),
            "is_hidden": bool(a.get("is_hidden", False)),
        } for a in p["abilities"]]

        # sprites (you can change paths if you prefer)
        id_ = p["id"]
        genv = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/versions/generation-v/black-white"
        genvii = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/versions/generation-vii/icons"
        sprites = {
            "genderDiffereance": bool(s.get("has_gender_differences", False)),
            "back":          f"{genv}/back/{id_}.png",
            "front":         f"{genv}/{id_}.png",
            "animated":      f"{genv}/animated/{id_}.gif",
            "icon":          f"{genvii}/{id_}.png",
            "shinyBack":     f"{genv}/back/shiny/{id_}.png",
            "shinyFront":    f"{genv}/shiny/{id_}.png",
            "shinyAnimated": f"{genv}/animated/shiny/{id_}.gif",
            "shinyIcon":     None,
        }

        # flavor, eggs, growth, gender, happiness, capture
        flavor = ""
        for entry in s.get("flavor_text_entries", []):
            if entry["language"]["name"] == "en":
                flavor = entry["flavor_text"].replace("\n"," ").replace("\f"," ").strip()
                break
        egg_groups = [g["name"] for g in s.get("egg_groups", [])]
        growth_rate = (s.get("growth_rate") or {}).get("name")
        ev_yield = {"hp":0,"atk":0,"def":0,"spa":0,"spd":0,"spe":0}
        key_map = {"hp":"hp","attack":"atk","defense":"def","special-attack":"spa","special-defense":"spd","speed":"spe"}
        for st in p["stats"]:
            e = int(st.get("effort",0))
            if e: ev_yield[key_map[st["stat"]["name"]]] = e
        rate = s.get("gender_rate", -1)
        if rate == -1:
            gender_ratio = {"genderless": True}
        else:
            female = rate*12.5
            gender_ratio = {"male": 100.0-female, "female": female}

        # evolution chain (next only, simplified)
        chain_url = (s.get("evolution_chain") or {}).get("url")
        next_evos = []
        if chain_url:
            chain = await _fetch_json(session, chain_url)
            node = chain.get("chain")
            target = p["name"].lower()
            stack = [node]
            while stack:
                n = stack.pop()
                if n["species"]["name"] == target:
                    for nxt in n.get("evolves_to", []):
                        det = (nxt.get("evolution_details") or [{}])[0]
                        next_evos.append({
                            "species": nxt["species"]["name"],
                            "details": {
                                "min_level": det.get("min_level"),
                                "trigger": (det.get("trigger") or {}).get("name") if det.get("trigger") else None,
                                "time_of_day": det.get("time_of_day"),
                                "item": (det.get("item") or {}).get("name") if det.get("item") else None,
                            }
                        })
                    break
                stack.extend(n.get("evolves_to", []))

        species_entry = {
            "id": p["id"],
            "name": p["name"].lower(),
            "introduced_in": _id_from_url((s.get("generation") or {}).get("url") or ""),
            "types": types,
            "stats": stats,
            "abilities": abilities,
            "sprites": sprites,
            "base_experience": p.get("base_experience"),
            "height_m": (p.get("height") or 0)/10.0,
            "weight_kg": (p.get("weight") or 0)/10.0,
            "base_happiness": s.get("base_happiness"),
            "capture_rate": s.get("capture_rate"),
            "egg_groups": egg_groups,
            "growth_rate": growth_rate,
            "ev_yield": ev_yield,
            "gender_ratio": gender_ratio,
            "flavor": flavor,
            "evolution": {"baby_trigger_item": (s.get("baby_trigger_item") or {}).get("name"), "next": next_evos},
        }

        # store species
        await db.upsert_pokedex(species_entry)

        # store learnsets (per generation)
        conn = await db.connect()
        for mv in p.get("moves", []):
            move_name = mv["move"]["name"].lower()
            # ensure move row (with metadata)
            mid = await ensure_move(session, move_name)

            for d in mv["version_group_details"]:
                vg = d["version_group"]["name"]
                gen = VERSION_GROUP_TO_GEN.get(vg)
                if not gen:
                    continue
                method = d["move_learn_method"]["name"]   # level-up, machine, tutor, egg
                lvl = d.get("level_learned_at") or None
                await conn.execute("""
                   INSERT OR IGNORE INTO learnsets (species_id, form_name, move_id, generation, method, level_learned)
                   VALUES (?, '', ?, ?, ?, ?)""", (p["id"], mid, gen, method, lvl))

        await conn.commit()
        if db_cache is not None:
            try:
                db_cache.invalidate_cached_table("learnsets")
            except Exception:
                pass

    return species_entry

def _canon_item_id(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[\s\-]+", "_", s)
    s = re.sub(r"[^a-z0-9_]", "", s)
    return s

async def ensure_item_cached(name_or_id: str) -> dict:
    """
    Ensure an item exists in the local SQLite 'items' table with an icon_url.
    Pulls from https://pokeapi.co/api/v2/item/{name or id} and saves:
    id, name, icon_url, emoji(NULL), category, price (cost), description/effect.
    Returns a small dict with the canonical 'id' and 'icon_url'.
    """
    key = str(name_or_id).strip()
    url = f"https://pokeapi.co/api/v2/item/{key}"
    async with aiohttp.ClientSession() as sess:
        async with sess.get(url) as resp:
            if resp.status != 200:
                raise ValueError(f"PokeAPI item not found: {key} (status {resp.status})")
            data = await resp.json()

    # Canonical ID for your table (snake_case)
    item_id = _canon_item_id(data["name"])

    # Choose an English display name if available
    disp_name = None
    for na in data.get("names", []):
        if na.get("language", {}).get("name") == "en":
            disp_name = na.get("name")
            break
    if not disp_name:
        disp_name = data["name"].replace("-", " ").title()

    # Icon: 'sprites' -> 'default'
    icon_url = None
    sprites = data.get("sprites") or {}
    icon_url = sprites.get("default")

    # Category & price
    category = (data.get("category") or {}).get("name")
    if category:
        category = category.replace("-", " ")

    price = data.get("cost")  # PokeAPI uses 'cost'
    description = None

    # Prefer English 'effect_entries' or 'flavor_text_entries'
    eff_entries = data.get("effect_entries") or []
    for ent in eff_entries:
        if ent.get("language", {}).get("name") == "en":
            description = ent.get("short_effect") or ent.get("effect")
            break
    if not description:
        for ent in data.get("flavor_text_entries") or []:
            if ent.get("language", {}).get("name") == "en":
                description = ent.get("text")
                break

    # Upsert into your items table
    await db.upsert_item_master(
        item_id=item_id,
        name=disp_name,
        icon_url=icon_url,
        emoji=None  # you can still add custom emoji later if you want
    )

    # Optional: store extra fields if your schema has them
    # (category/price/description). Safe to ignore if columns exist already.
    try:
        conn = await db.connect()
        await conn.execute("""
            UPDATE items
               SET category   = COALESCE(?, category),
                   price      = COALESCE(?, price),
                   description= COALESCE(?, description)
             WHERE id = ?
        """, (category, price, description, item_id))
        await conn.commit()
    except Exception:
        pass

    return {"id": item_id, "icon_url": icon_url}