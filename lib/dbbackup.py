# lib/db.py
import json
import pathlib
import datetime as dt
from typing import Optional
import aiosqlite
from typing import Optional, Sequence, Dict, Any
from typing import Tuple, List
# Absolute paths
ROOT = pathlib.Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "myuu.db"
SCHEMA_PATH = ROOT / "db" / "schema.sql"

_conn: Optional[aiosqlite.Connection] = None  # one shared connection


# -----------------------------
# Connection & schema
# -----------------------------
async def connect() -> aiosqlite.Connection:
    """Open (or reuse) one async connection to the SQLite file."""
    global _conn
    if _conn is None:
        _conn = await aiosqlite.connect(DB_PATH.as_posix())
        _conn.row_factory = aiosqlite.Row
        await _conn.execute("PRAGMA foreign_keys = ON;")
        await _conn.execute("PRAGMA journal_mode = WAL;")
    return _conn


async def migrate_monsters_to_pokemons() -> None:
    """
    If old 'monsters' table exists and 'pokemons' does not, rename it to 'pokemons'.
    Keeps existing data; also creates the new index name.
    """
    conn = await connect()
    cur = await conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name IN ('monsters','pokemons')"
    )
    names = {row["name"] for row in await cur.fetchall()}
    await cur.close()

    if "pokemons" in names:
        return  # already migrated

    if "monsters" in names:
        await conn.execute("ALTER TABLE monsters RENAME TO pokemons")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_pokemons_owner ON pokemons(owner_id)")
        await conn.commit()


async def init_schema() -> None:
    conn = await connect()
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        await conn.executescript(f.read())
    await migrate_monsters_to_pokemons()
    await ensure_pokemon_stat_columns()  
    await ensure_mon_meta_columns()    
    await ensure_team_slot_column()
    await conn.commit()

async def close() -> None:
    """Close DB on shutdown."""
    global _conn
    if _conn is not None:
        await _conn.close()
        _conn = None


# -----------------------------
# Users
# -----------------------------
async def get_user(user_id: str):
    conn = await connect()
    cur = await conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = await cur.fetchone()
    await cur.close()
    return row


async def create_user(user_id: str):
    conn = await connect()
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    await conn.execute(
        "INSERT OR IGNORE INTO users (user_id, created_at, coins) VALUES (?, ?, 0)",
        (user_id, now),
    )
    await conn.commit()


async def count_users() -> int:
    conn = await connect()
    cur = await conn.execute("SELECT COUNT(*) AS c FROM users")
    row = await cur.fetchone()
    await cur.close()
    return int(row["c"])


async def list_users(limit: int = 20, offset: int = 0):
    conn = await connect()
    cur = await conn.execute(
        "SELECT user_id, created_at, starter, coins "
        "FROM users ORDER BY created_at LIMIT ? OFFSET ?",
        (limit, offset),
    )
    rows = await cur.fetchall()
    await cur.close()
    return [dict(r) for r in rows]


async def grant_coins(user_id: str, delta: int):
    conn = await connect()
    await conn.execute("UPDATE users SET coins = coins + ? WHERE user_id=?", (delta, user_id))
    await conn.commit()


# -----------------------------
# Admin whitelist
# -----------------------------
async def add_admin(user_id: str) -> None:
    conn = await connect()
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    await conn.execute(
        "INSERT OR IGNORE INTO admins (user_id, added_at) VALUES (?, ?)",
        (user_id, now),
    )
    await conn.commit()


async def remove_admin(user_id: str) -> None:
    conn = await connect()
    await conn.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
    await conn.commit()


async def is_admin(user_id: str) -> bool:
    conn = await connect()
    cur = await conn.execute("SELECT 1 FROM admins WHERE user_id = ? LIMIT 1", (user_id,))
    row = await cur.fetchone()
    await cur.close()
    return row is not None


async def any_admins() -> bool:
    conn = await connect()
    cur = await conn.execute("SELECT 1 FROM admins LIMIT 1")
    row = await cur.fetchone()
    await cur.close()
    return row is not None


async def list_admins(limit: int = 100, offset: int = 0):
    conn = await connect()
    cur = await conn.execute(
        "SELECT user_id, added_at FROM admins ORDER BY added_at LIMIT ? OFFSET ?",
        (limit, offset),
    )
    rows = await cur.fetchall()
    await cur.close()
    return [dict(r) for r in rows]


# -----------------------------
# Pokemons (renamed from monsters)
# -----------------------------
async def add_pokemon(owner_id: str, species: str, level: int = 5,
                      hp: int = 20, atk: int = 5, def_: int = 5) -> int:
    conn = await connect()
    cur = await conn.execute(
        "INSERT INTO pokemons (owner_id, species, level, hp, atk, def) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (owner_id, species, level, hp, atk, def_)
    )
    await conn.commit()
    mid = cur.lastrowid
    await cur.close()
    return int(mid)


async def list_pokemons(owner_id: str, limit: int = 50, offset: int = 0):
    conn = await connect()
    cur = await conn.execute(
        "SELECT id, species, level, hp, atk, def "
        "FROM pokemons WHERE owner_id=? ORDER BY id LIMIT ? OFFSET ?",
        (owner_id, limit, offset),
    )
    rows = await cur.fetchall()
    await cur.close()
    return [dict(r) for r in rows]

async def get_pokemon(owner_id: str, mon_id: int) -> dict | None:
    """Return one Pokémon row (with stats/meta) for an owner, or None."""
    conn = await connect()
    cur = await conn.execute(
        "SELECT * FROM pokemons WHERE owner_id=? AND id=? LIMIT 1",
        (owner_id, mon_id)
    )
    row = await cur.fetchone()
    await cur.close()
    return dict(row) if row else None

# --- Backwards-compat shims (so existing code using 'monsters' keeps working) ---
async def add_monster(owner_id: str, species: str, level: int = 5,
                      hp: int = 20, atk: int = 5, def_: int = 5) -> int:
    return await add_pokemon(owner_id, species, level, hp, atk, def_)

async def list_monsters(owner_id: str, limit: int = 50, offset: int = 0):
    return await list_pokemons(owner_id, limit, offset)


# -----------------------------
# Items & Inventory
# -----------------------------
async def ensure_item(item_id: str, name: str | None = None,
                      description: str | None = None, stackable: bool = True):
    """Create the item in the catalog if missing (idempotent)."""
    conn = await connect()
    await conn.execute(
        "INSERT OR IGNORE INTO items (item_id, name, description, stackable) "
        "VALUES (?, ?, ?, ?)",
        (item_id, name or item_id, description or "", 1 if stackable else 0)
    )
    await conn.commit()


async def take_item(owner_id: str, item_id: str, qty: int = 1) -> bool:
    """Remove qty; returns False if not enough."""
    conn = await connect()
    cur = await conn.execute(
        "SELECT qty FROM inventory WHERE owner_id=? AND item_id=?",
        (owner_id, item_id)
    )
    row = await cur.fetchone()
    await cur.close()
    have = row["qty"] if row else 0
    if have < qty:
        return False

    new_qty = have - qty
    if new_qty == 0:
        await conn.execute(
            "DELETE FROM inventory WHERE owner_id=? AND item_id=?",
            (owner_id, item_id)
        )
    else:
        await conn.execute(
            "UPDATE inventory SET qty=? WHERE owner_id=? AND item_id=?",
            (new_qty, owner_id, item_id)
        )
    await conn.commit()
    return True


async def list_inventory(owner_id: str):
    """Join with items table for names."""
    conn = await connect()
    cur = await conn.execute(
        "SELECT i.item_id, COALESCE(it.name, i.item_id) AS name, i.qty "
        "FROM inventory i "
        "LEFT JOIN items it ON it.item_id = i.item_id "
        "WHERE i.owner_id=? ORDER BY i.item_id",
        (owner_id,)
    )
    rows = await cur.fetchall()
    await cur.close()
    return [dict(r) for r in rows]


# -----------------------------
# Event log (optional)
# -----------------------------
async def log_event(user_id: str, type_: str, payload: dict):
    conn = await connect()
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    await conn.execute(
        "INSERT INTO event_log (user_id, type, payload, created_at) VALUES (?, ?, ?, ?)",
        (user_id, type_, json.dumps(payload, ensure_ascii=False), now)
    )
    await conn.commit()

# -----------------------------
# Pokédex cache (species)
# -----------------------------
async def get_pokedex_by_name(name: str):
    """Return one species row by name (lowercase) or None."""
    conn = await connect()
    cur = await conn.execute(
        "SELECT * FROM pokedex WHERE name = ?",
        (name.lower(),)
    )
    row = await cur.fetchone()
    await cur.close()
    return dict(row) if row else None


async def get_pokedex_by_id(pid: int):
    """Return one species row by national dex id or None."""
    conn = await connect()
    cur = await conn.execute(
        "SELECT * FROM pokedex WHERE id = ?",
        (pid,)
    )
    row = await cur.fetchone()
    await cur.close()
    return dict(row) if row else None


async def upsert_pokedex(e: dict):
    """
    Insert/update one normalized species entry.

    Expected keys in e:
      id, name, introduced_in, types(list), stats(dict),
      abilities(list), sprites(dict), base_experience, height_m, weight_kg,
      base_happiness, capture_rate, egg_groups(list), growth_rate,
      ev_yield(dict), gender_ratio(dict), flavor, evolution(dict)
    """
    conn = await connect()
    await conn.execute("""
        INSERT INTO pokedex
        (id,name,introduced_in,types,stats,abilities,sprites,base_experience,height_m,weight_kg,
         base_happiness,capture_rate,egg_groups,growth_rate,ev_yield,gender_ratio,flavor,evolution)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
          name=excluded.name,
          introduced_in=excluded.introduced_in,
          types=excluded.types,
          stats=excluded.stats,
          abilities=excluded.abilities,
          sprites=excluded.sprites,
          base_experience=excluded.base_experience,
          height_m=excluded.height_m,
          weight_kg=excluded.weight_kg,
          base_happiness=excluded.base_happiness,
          capture_rate=excluded.capture_rate,
          egg_groups=excluded.egg_groups,
          growth_rate=excluded.growth_rate,
          ev_yield=excluded.ev_yield,
          gender_ratio=excluded.gender_ratio,
          flavor=excluded.flavor,
          evolution=excluded.evolution
    """, (
        e["id"], e["name"].lower(), e.get("introduced_in"),
        json.dumps(e["types"], ensure_ascii=False),
        json.dumps(e["stats"], ensure_ascii=False),
        json.dumps(e["abilities"], ensure_ascii=False),
        json.dumps(e["sprites"], ensure_ascii=False),
        e.get("base_experience"),
        e.get("height_m"),
        e.get("weight_kg"),
        e.get("base_happiness"),
        e.get("capture_rate"),
        json.dumps(e["egg_groups"], ensure_ascii=False),
        e.get("growth_rate"),
        json.dumps(e["ev_yield"], ensure_ascii=False),
        json.dumps(e["gender_ratio"], ensure_ascii=False),
        e.get("flavor"),
        json.dumps(e["evolution"], ensure_ascii=False),
    ))
    await conn.commit()

# -----------------------------
# Pokédex cache (species)
# -----------------------------
async def get_pokedex_by_name(name: str):
    """Return one species row by name (lowercase) or None."""
    conn = await connect()
    cur = await conn.execute(
        "SELECT * FROM pokedex WHERE name = ?",
        (name.lower(),)
    )
    row = await cur.fetchone()
    await cur.close()
    return dict(row) if row else None


async def get_pokedex_by_id(pid: int):
    """Return one species row by national dex id or None."""
    conn = await connect()
    cur = await conn.execute(
        "SELECT * FROM pokedex WHERE id = ?",
        (pid,)
    )
    row = await cur.fetchone()
    await cur.close()
    return dict(row) if row else None


async def upsert_pokedex(e: dict):
    """
    Insert/update one normalized species entry.

    Expected keys in e:
      id, name, introduced_in, types(list), stats(dict),
      abilities(list), sprites(dict), base_experience, height_m, weight_kg,
      base_happiness, capture_rate, egg_groups(list), growth_rate,
      ev_yield(dict), gender_ratio(dict), flavor, evolution(dict)
    """
    conn = await connect()
    await conn.execute("""
        INSERT INTO pokedex
        (id,name,introduced_in,types,stats,abilities,sprites,base_experience,height_m,weight_kg,
         base_happiness,capture_rate,egg_groups,growth_rate,ev_yield,gender_ratio,flavor,evolution)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
          name=excluded.name,
          introduced_in=excluded.introduced_in,
          types=excluded.types,
          stats=excluded.stats,
          abilities=excluded.abilities,
          sprites=excluded.sprites,
          base_experience=excluded.base_experience,
          height_m=excluded.height_m,
          weight_kg=excluded.weight_kg,
          base_happiness=excluded.base_happiness,
          capture_rate=excluded.capture_rate,
          egg_groups=excluded.egg_groups,
          growth_rate=excluded.growth_rate,
          ev_yield=excluded.ev_yield,
          gender_ratio=excluded.gender_ratio,
          flavor=excluded.flavor,
          evolution=excluded.evolution
    """, (
        e["id"], e["name"].lower(), e.get("introduced_in"),
        json.dumps(e["types"], ensure_ascii=False),
        json.dumps(e["stats"], ensure_ascii=False),
        json.dumps(e["abilities"], ensure_ascii=False),
        json.dumps(e["sprites"], ensure_ascii=False),
        e.get("base_experience"),
        e.get("height_m"),
        e.get("weight_kg"),
        e.get("base_happiness"),
        e.get("capture_rate"),
        json.dumps(e["egg_groups"], ensure_ascii=False),
        e.get("growth_rate"),
        json.dumps(e["ev_yield"], ensure_ascii=False),
        json.dumps(e["gender_ratio"], ensure_ascii=False),
        e.get("flavor"),
        json.dumps(e["evolution"], ensure_ascii=False),
    ))
    await conn.commit()
async def ensure_pokemon_stat_columns() -> None:
    """Add new columns to pokemons if missing (idempotent)."""
    conn = await connect()
    cur = await conn.execute("PRAGMA table_info(pokemons)")
    cols = {r["name"] for r in await cur.fetchall()}
    await cur.close()

    to_add = []
    if "spa"     not in cols: to_add.append(("spa",     "INTEGER NOT NULL DEFAULT 5"))
    if "spd"     not in cols: to_add.append(("spd",     "INTEGER NOT NULL DEFAULT 5"))
    if "spe"     not in cols: to_add.append(("spe",     "INTEGER NOT NULL DEFAULT 5"))
    if "ivs"     not in cols: to_add.append(("ivs",     "TEXT"))
    if "evs"     not in cols: to_add.append(("evs",     "TEXT"))
    if "nature"  not in cols: to_add.append(("nature",  "TEXT"))
    if "ability" not in cols: to_add.append(("ability", "TEXT"))
    if "gender"  not in cols: to_add.append(("gender",  "TEXT"))
    # (optional) if you prefer a max_hp separate from current hp:
    # if "max_hp" not in cols: to_add.append(("max_hp", "INTEGER NOT NULL DEFAULT 20"))

    for name, decl in to_add:
        await conn.execute(f"ALTER TABLE pokemons ADD COLUMN {name} {decl}")
    if to_add:
        await conn.commit()
async def add_pokemon_with_stats(owner_id: str,
                                 species: str,
                                 level: int,
                                 final_stats: dict,
                                 ivs: dict,
                                 evs: dict,
                                 nature: str,
                                 ability: str,
                                 gender: str,
                                 tera_type: str | None = None) -> int:
    """Insert a Pokémon row including full stats + IVs/EVs/nature/ability/gender."""
    conn = await connect()
    cur = await conn.execute("""
        INSERT INTO pokemons
          (owner_id, species, level, hp, atk, def, spa, spd, spe,
           ivs, evs, nature, ability, gender, tera_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        owner_id, species, level,
        int(final_stats["hp"]),
        int(final_stats["attack"]),
        int(final_stats["defense"]),
        int(final_stats["special_attack"]),
        int(final_stats["special_defense"]),
        int(final_stats["speed"]),
        json.dumps(ivs, ensure_ascii=False),
        json.dumps(evs, ensure_ascii=False),
        nature,
        ability,
        gender,
        tera_type,
    ))
    await conn.commit()
    pid = cur.lastrowid
    await cur.close()
    return int(pid)
async def set_held_item(owner_id: str, mon_id: int, item_id: str | None) -> None:
    conn = await connect()
    await conn.execute(
        "UPDATE pokemons SET held_item=? WHERE owner_id=? AND id=?",
        (item_id, owner_id, mon_id),
    )
    await conn.commit()

async def set_pokemon_moves(owner_id: str, mon_id: int, moves: list[str] | list[int]) -> None:
    moves = list(moves or [])[:4]
    conn = await connect()
    await conn.execute(
        "UPDATE pokemons SET moves=? WHERE owner_id=? AND id=?",
        (json.dumps(moves, ensure_ascii=False), owner_id, mon_id),
    )
    await conn.commit()

async def bump_friendship(owner_id: str, mon_id: int, delta: int, lo: int = 0, hi: int = 255) -> int:
    """Increase/decrease friendship; initialize from species base_happiness if NULL."""
    conn = await connect()
    cur = await conn.execute("""
        SELECT p.friendship, p.species, COALESCE(pd.base_happiness, 70) AS base_h
        FROM pokemons p
        LEFT JOIN pokedex pd ON LOWER(pd.name) = LOWER(p.species)
        WHERE p.owner_id=? AND p.id=? LIMIT 1
    """, (owner_id, mon_id))
    row = await cur.fetchone(); await cur.close()
    if not row:
        raise ValueError("Pokémon not found")
    cur_val = row["friendship"]
    if cur_val is None:
        cur_val = int(row["base_h"])
    new_val = max(lo, min(hi, int(cur_val) + int(delta)))
    await conn.execute("UPDATE pokemons SET friendship=? WHERE owner_id=? AND id=?", (new_val, owner_id, mon_id))
    await conn.commit()
    return new_val

# Helper to compute default level-up moves from your cached learnsets
async def default_levelup_moves(species_id: int, level: int, generation: int, limit: int = 4) -> list[str]:
    conn = await connect()
    cur = await conn.execute("""
        SELECT m.name, COALESCE(l.level_learned, 0) AS lvl
        FROM learnsets l
        JOIN moves m ON m.id = l.move_id
        WHERE l.species_id = ? AND l.generation = ? AND l.method = 'level-up'
              AND COALESCE(l.level_learned, 0) <= ?
        ORDER BY lvl DESC, m.name
        LIMIT 40
    """, (species_id, generation, level))
    rows = await cur.fetchall(); await cur.close()
    seen, out = set(), []
    for r in rows:
        name = r["name"].replace("-", " ").title()
        if name not in seen:
            seen.add(name); out.append(name)
        if len(out) == limit:
            break
    return out

async def ensure_mon_meta_columns() -> None:
    """Add friendship, held_item, moves columns if missing (idempotent)."""
    conn = await connect()
    cur = await conn.execute("PRAGMA table_info(pokemons)")
    cols = {r["name"] for r in await cur.fetchall()}
    await cur.close()

    to_add = []
    if "friendship" not in cols:
        to_add.append(("friendship", "INTEGER"))
    if "held_item" not in cols:
        to_add.append(("held_item", "TEXT"))
    if "moves" not in cols:
        # JSON list of move names/ids
        to_add.append(("moves", "TEXT"))

    for name, decl in to_add:
        await conn.execute(f"ALTER TABLE pokemons ADD COLUMN {name} {decl}")

    if to_add:
        await conn.commit()
# --- MIGRATION: add team_slot if missing (NULL = boxed, 1..6 = in team) ---
async def ensure_team_slot_column() -> None:
    conn = await connect()
    cur = await conn.execute("PRAGMA table_info(pokemons)")
    cols = {r["name"] for r in await cur.fetchall()}
    await cur.close()
    if "team_slot" not in cols:
        await conn.execute("ALTER TABLE pokemons ADD COLUMN team_slot INTEGER")
        await conn.commit()

async def next_free_team_slot(owner_id: str) -> int | None:
    conn = await connect()
    cur = await conn.execute(
        "SELECT team_slot FROM pokemons WHERE owner_id=? AND team_slot BETWEEN 1 AND 6",
        (owner_id,),
    )
    used = {int(r["team_slot"]) for r in await cur.fetchall()}
    await cur.close()
    for s in range(1, 7):
        if s not in used:
            return s
    return None

async def set_team_slot(owner_id: str, mon_id: int, slot: int | None) -> None:
    conn = await connect()
    await conn.execute("UPDATE pokemons SET team_slot=? WHERE owner_id=? AND id=?",
                       (slot, owner_id, mon_id))
    await conn.commit()

async def get_team_mon_by_name(owner_id: str, species_name: str):
    """Return the first matching mon in TEAM (slot 1..6), or None."""
    conn = await connect()
    cur = await conn.execute("""
        SELECT * FROM pokemons
        WHERE owner_id = ?
          AND LOWER(species) = LOWER(?)
          AND team_slot BETWEEN 1 AND 6
        ORDER BY team_slot, id
        LIMIT 1
    """, (owner_id, species_name))
    row = await cur.fetchone(); await cur.close()
    return dict(row) if row else None
async def ensure_team_slot_column() -> None:
    conn = await connect()
    cur = await conn.execute("PRAGMA table_info(pokemons)")
    cols = {r["name"] for r in await cur.fetchall()}
    await cur.close()
    if "team_slot" not in cols:
        await conn.execute("ALTER TABLE pokemons ADD COLUMN team_slot INTEGER")
        await conn.commit()
# --- Helpers to manage the team ---
async def next_free_team_slot(owner_id: str) -> int | None:
    """Return the first free slot 1..6, or None if team is full."""
    conn = await connect()
    cur = await conn.execute(
        "SELECT team_slot FROM pokemons WHERE owner_id=? AND team_slot BETWEEN 1 AND 6",
        (owner_id,),
    )
    used = {int(r["team_slot"]) for r in await cur.fetchall()}
    await cur.close()
    for s in range(1, 7):
        if s not in used:
            return s
    return None

async def set_team_slot(owner_id: str, mon_id: int, slot: int | None) -> None:
    """Set team slot for a mon (1..6). Use None to box it."""
    conn = await connect()
    await conn.execute(
        "UPDATE pokemons SET team_slot=? WHERE owner_id=? AND id=?",
        (slot, owner_id, mon_id),
    )
    await conn.commit()
##Bag:
DEFAULT_BAG_PAGES = 6
BAG_ITEMS_PER_PAGE = 24  # set what you want

async def _table_exists(conn: aiosqlite.Connection, table: str) -> bool:
    cur = await conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,)
    )
    row = await cur.fetchone()
    await cur.close()
    return row is not None

async def _column_exists(conn: aiosqlite.Connection, table: str, column: str) -> bool:
    cur = await conn.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in await cur.fetchall()]  # r[1] = column name
    await cur.close()
    return column in cols

async def get_inventory_page(
    conn: aiosqlite.Connection,
    owner_id: int | str,
    page: int,
    per_page: int = BAG_ITEMS_PER_PAGE
) -> Tuple[List[Dict], int, int]:
    """
    Return (items, max_pages, total_distinct) for the user's bag page.
    Works with BOTH old and new schemas:
      - NEW: user_items(owner_id,item_id), items(id,name,emoji,icon_url,...)
      - OLD: inventory(owner_id,item_id,qty), items(item_id,name,...)
    """
    conn.row_factory = aiosqlite.Row
    uid = str(owner_id)

    # Detect schema flavor
    has_user_items = await _table_exists(conn, "user_items")
    has_inventory  = await _table_exists(conn, "inventory")

    if not has_user_items and not has_inventory:
        # No bag tables at all
        return [], 1, 0

    # Detect items column names
    items_has_id      = await _column_exists(conn, "items", "id")
    items_has_item_id = await _column_exists(conn, "items", "item_id")
    items_has_emoji   = await _column_exists(conn, "items", "emoji")
    items_has_icon    = await _column_exists(conn, "items", "icon_url")
    items_has_name    = await _column_exists(conn, "items", "name")

    # Decide source table + join columns
    if has_user_items:
        bag_table = "user_items"
        bag_item_col = "item_id"
        bag_owner_col = "owner_id"
        # join key on items.*
        join_left = "items"
        join_on   = "items.id = ui.item_id" if items_has_id else "items.item_id = ui.item_id"
        bag_alias = "ui"
        qty_expr  = "ui.qty"
        count_from = "user_items"
        count_where = "owner_id = ? AND qty > 0"
    else:
        # OLD schema
        bag_table = "inventory"
        bag_item_col = "item_id"
        bag_owner_col = "owner_id"
        join_left = "items"
        join_on   = "items.item_id = i.item_id"  # old schema only
        bag_alias = "i"
        qty_expr  = "i.qty"
        count_from = "inventory"
        count_where = "owner_id = ? AND qty > 0"

    # Total distinct items (with qty > 0)
    cur = await conn.execute(
        f"SELECT COUNT(*) AS c FROM {count_from} WHERE {count_where}",
        (uid,)
    )
    row = await cur.fetchone(); await cur.close()
    total_distinct = int(row["c"] if row else 0)

    # Page cap from user_meta (if present); default 6 pages
    total_pages_cap = 6
    if await _table_exists(conn, "user_meta"):
        try:
            cur = await conn.execute(
                "SELECT bag_pages FROM user_meta WHERE owner_id = ?",
                (uid,)
            )
            r = await cur.fetchone(); await cur.close()
            if r and r["bag_pages"] is not None:
                total_pages_cap = int(r["bag_pages"])
        except Exception:
            pass

    # Paging math
    max_pages = max(1, min(total_pages_cap, ((total_distinct + per_page - 1) // per_page) or 1))
    page = max(1, min(page, max_pages))
    offset = (page - 1) * per_page

    # Build SELECT columns safely
    # name fallback → if items.name missing, fallback to the bag item_id
    name_col = "items.name" if items_has_name else f"{bag_alias}.{bag_item_col}"
    emoji_col = "items.emoji"    if items_has_emoji else "NULL AS emoji"
    icon_col  = "items.icon_url" if items_has_icon  else "NULL AS icon_url"

    sql = f"""
        SELECT {bag_alias}.{bag_item_col} AS item_id,
               {qty_expr} AS qty,
               COALESCE({name_col}, {bag_alias}.{bag_item_col}) AS name,
               {emoji_col},
               {icon_col}
        FROM {bag_table} {bag_alias}
        LEFT JOIN {join_left} ON {join_on}
        WHERE {bag_alias}.{bag_owner_col} = ? AND {qty_expr} > 0
        ORDER BY (name IS NULL), name ASC, {bag_alias}.{bag_item_col} ASC
        LIMIT ? OFFSET ?
    """
    cur = await conn.execute(sql, (uid, per_page, offset))
    rows = await cur.fetchall(); await cur.close()

    items = [{
        "item_id": r["item_id"],
        "qty": int(r["qty"]),
        "name": r["name"] or r["item_id"],
        "emoji": r["emoji"],
        "icon_url": r["icon_url"],
    } for r in rows]

    return items, max_pages, total_distinct
async def _table_exists_conn(conn: aiosqlite.Connection, table: str) -> bool:
    cur = await conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,)
    )
    row = await cur.fetchone()
    await cur.close()
    return row is not None

async def give_item(owner_id: str, item_id: str, qty: int) -> int:
    """
    Add (or remove if qty<0) items to a user's bag.
    Works with BOTH schemas:
      NEW: user_items(owner_id,item_id,qty)
      OLD: inventory(owner_id,item_id,qty)
    Always uses a FRESH connection to avoid 'no active connection'.
    Returns the resulting quantity (clamped >= 0).
    """
    async with aiosqlite.connect(str(DB_PATH)) as conn:
        # pick table
        has_user_items = await _table_exists_conn(conn, "user_items")
        table = "user_items" if has_user_items else "inventory"

        # read existing qty
        cur = await conn.execute(
            f"SELECT qty FROM {table} WHERE owner_id=? AND item_id=?",
            (owner_id, item_id)
        )
        row = await cur.fetchone()
        await cur.close()

        if row:
            new_qty = max(0, int(row[0]) + int(qty))
            await conn.execute(
                f"UPDATE {table} SET qty=? WHERE owner_id=? AND item_id=?",
                (new_qty, owner_id, item_id)
            )
        else:
            new_qty = max(0, int(qty))
            await conn.execute(
                f"INSERT INTO {table} (owner_id, item_id, qty) VALUES (?, ?, ?)",
                (owner_id, item_id, new_qty)
            )

        # ensure user_meta row exists (so /bag can read pages), if table present
        if await _table_exists_conn(conn, "user_meta"):
            await conn.execute(
                "INSERT OR IGNORE INTO user_meta (owner_id) VALUES (?)",
                (owner_id,)
            )

        await conn.commit()
        return new_qty
    async def upsert_item_master(item_id: str, name: Optional[str] = None,
                             icon_url: Optional[str] = None,
                             emoji: Optional[str] = None) -> None:
     async with aiosqlite.connect(str(DB_PATH)) as conn:
        # detect key column
        cur = await conn.execute("PRAGMA table_info(items)")
        cols = [r[1] for r in await cur.fetchall()]
        await cur.close()
        keycol = "id" if "id" in cols else "item_id"

        # ensure row exists
        await conn.execute(
            f"INSERT OR IGNORE INTO items ({keycol}) VALUES (?)",
            (item_id,)
        )

        sets, vals = [], []
        if name is not None and "name" in cols:
            sets.append("name = ?"); vals.append(name)
        if icon_url is not None and "icon_url" in cols:
            sets.append("icon_url = ?"); vals.append(icon_url)
        if emoji is not None and "emoji" in cols:
            sets.append("emoji = ?"); vals.append(emoji)

        if sets:
            vals.append(item_id)
            await conn.execute(
                f"UPDATE items SET {', '.join(sets)} WHERE {keycol} = ?",
                tuple(vals)
            )
        await conn.commit()