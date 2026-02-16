PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

/* ─────────────────────────
   USERS (one table only)
   ───────────────────────── */
CREATE TABLE IF NOT EXISTS players (
  owner_id    TEXT PRIMARY KEY,              -- Discord user id as TEXT
  starter     TEXT,                          -- chosen starter species (nullable until chosen)
  started_at  TEXT DEFAULT (datetime('now')) -- ISO timestamp
);

CREATE TABLE IF NOT EXISTS admins (
  user_id  TEXT PRIMARY KEY,
  added_at TEXT NOT NULL DEFAULT (datetime('now'))
);

/* ─────────────────────────
   POKÉMON STORAGE
   ───────────────────────── */
CREATE TABLE IF NOT EXISTS pokemons (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_id   TEXT NOT NULL,
  species    TEXT NOT NULL,
  level      INTEGER NOT NULL DEFAULT 5,
  hp         INTEGER NOT NULL,
  atk        INTEGER NOT NULL,
  def        INTEGER NOT NULL,
  spa        INTEGER NOT NULL,
  spd        INTEGER NOT NULL,
  spe        INTEGER NOT NULL,
  ivs        TEXT NOT NULL,                  -- JSON: {hp,atk,def,spa,spd,spe}
  evs        TEXT NOT NULL,                  -- JSON
  nature     TEXT NOT NULL,
  ability    TEXT,
  gender     TEXT,
  friendship INTEGER NOT NULL DEFAULT 50,
  held_item  TEXT,                           -- item_id
  moves      TEXT NOT NULL,                  -- JSON: ["tackle","growl",...]
  team_slot  INTEGER,                        -- 1..6 or NULL (in PC)
  FOREIGN KEY (owner_id) REFERENCES players(owner_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_pokemons_owner ON pokemons(owner_id);
CREATE INDEX IF NOT EXISTS idx_pokemons_team  ON pokemons(owner_id, team_slot);

/* ─────────────────────────
   ECONOMY + BAG
   ───────────────────────── */
CREATE TABLE IF NOT EXISTS user_meta (
  owner_id  TEXT PRIMARY KEY,
  money     INTEGER NOT NULL DEFAULT 0,
  bag_pages INTEGER NOT NULL DEFAULT 6,
  FOREIGN KEY (owner_id) REFERENCES players(owner_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS items (
  id          TEXT PRIMARY KEY,              -- canonical id e.g. "leftovers"
  name        TEXT NOT NULL,                 -- display name
  emoji       TEXT,                          -- optional: Unicode or <:name:id>
  icon_url    TEXT,                          -- CDN sprite for real icon
  category    TEXT,                          -- "held","consumable","key",...
  description TEXT,
  price       INTEGER,                       -- shop buy price (optional)
  sell_price  INTEGER                        -- shop sell price (optional)
);

CREATE TABLE IF NOT EXISTS user_items (
  owner_id  TEXT NOT NULL,
  item_id   TEXT NOT NULL,
  qty       INTEGER NOT NULL DEFAULT 0 CHECK (qty >= 0),
  PRIMARY KEY (owner_id, item_id),
  FOREIGN KEY (owner_id) REFERENCES players(owner_id) ON DELETE CASCADE,
  FOREIGN KEY (item_id)  REFERENCES items(id)      ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_user_items_owner ON user_items(owner_id);

/* ─────────────────────────
   OPTIONAL LOGGING
   ───────────────────────── */
CREATE TABLE IF NOT EXISTS event_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    TEXT NOT NULL,
  type       TEXT NOT NULL,
  payload    TEXT NOT NULL,                  -- JSON string
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY(user_id) REFERENCES players(owner_id) ON DELETE CASCADE
);

/* ─────────────────────────
   CACHES (DEX / MOVES / LEARNSETS / RULESETS)
   ───────────────────────── */
CREATE TABLE IF NOT EXISTS pokedex (
  id               INTEGER PRIMARY KEY,      -- national id
  name             TEXT UNIQUE NOT NULL,     -- lowercase
  introduced_in    INTEGER,
  types            TEXT NOT NULL,            -- JSON: ["grass","poison"]
  stats            TEXT NOT NULL,            -- JSON: {hp,attack,defense,special_attack,special_defense,speed}
  abilities        TEXT NOT NULL,            -- JSON: [{name,id,is_hidden},...]
  sprites          TEXT,                     -- JSON (front/back/shiny/icon/genderDifference)
  base_experience  INTEGER,
  height_m         REAL,
  weight_kg        REAL,
  base_happiness   INTEGER,
  capture_rate     INTEGER,
  egg_groups       TEXT,                     -- JSON: ["monster","grass"]
  growth_rate      TEXT,
  ev_yield         TEXT,                     -- JSON: {hp,atk,def,spa,spd,spe}
  gender_ratio     TEXT,                     -- JSON: {male,female} or {genderless:true}
  flavor           TEXT,
  evolution        TEXT                      -- JSON: {baby_trigger_item, next:[{species,details:{...}}]}
);
CREATE INDEX IF NOT EXISTS idx_pokedex_name ON pokedex(name);
CREATE INDEX IF NOT EXISTS idx_pokedex_intro ON pokedex(introduced_in);

CREATE TABLE IF NOT EXISTS moves (
  id             INTEGER PRIMARY KEY,
  name           TEXT UNIQUE NOT NULL,       -- lowercase
  introduced_in  INTEGER,
  type           TEXT,
  power          INTEGER,
  accuracy       INTEGER,
  pp             INTEGER,
  damage_class   TEXT,                       -- physical/special/status
  meta           TEXT                        -- JSON
);
CREATE INDEX IF NOT EXISTS idx_moves_name ON moves(name);
CREATE INDEX IF NOT EXISTS idx_moves_gen  ON moves(introduced_in);

CREATE TABLE IF NOT EXISTS learnsets (
  species_id    INTEGER NOT NULL,
  form_name     TEXT NOT NULL DEFAULT '',
  move_id       INTEGER NOT NULL,
  generation    INTEGER NOT NULL,
  method        TEXT NOT NULL,               -- level-up/machine/tutor/egg
  level_learned INTEGER,
  PRIMARY KEY (species_id, form_name, move_id, generation, method),
  FOREIGN KEY (species_id) REFERENCES pokedex(id) ON DELETE CASCADE,
  FOREIGN KEY (move_id)   REFERENCES moves(id)   ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS rulesets (
  scope      TEXT PRIMARY KEY,               -- "guild:123", "battle:456", or "global"
  generation INTEGER NOT NULL                -- e.g., 3..9
);

/* keep pragmas at end as well */
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
