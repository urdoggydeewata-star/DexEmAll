PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

/* ─────────────────────────
   USERS & ADMINS
   ───────────────────────── */
CREATE TABLE IF NOT EXISTS users (
  user_id    TEXT PRIMARY KEY,              -- Discord user id (TEXT)
  created_at TEXT NOT NULL DEFAULT (datetime('now')), -- ISO timestamp
  starter    TEXT,                          -- chosen starter species (nullable until chosen)
  coins      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS admins (
  user_id  TEXT PRIMARY KEY,
  added_at TEXT NOT NULL DEFAULT (datetime('now'))
);

/* ─────────────────────────
   POKÉMON STORAGE
   ─────────────────────────
   - team_slot: 1..6 = in team, NULL = boxed
   - box_no/box_pos organize boxed mons into numbered boxes
*/
CREATE TABLE IF NOT EXISTS pokemons (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_id   TEXT NOT NULL,
  species    TEXT NOT NULL,
  level      INTEGER NOT NULL DEFAULT 5,
  hp         INTEGER NOT NULL,
  hp_now     INTEGER,                        -- current HP (nullable; fallback to hp)
  atk        INTEGER NOT NULL,
  def        INTEGER NOT NULL,
  spa        INTEGER NOT NULL,
  spd        INTEGER NOT NULL,
  spe        INTEGER NOT NULL,
  ivs        TEXT NOT NULL,                  -- JSON: {hp,attack,defense,special_attack,special_defense,speed}
  evs        TEXT NOT NULL,                  -- JSON (same shape as IVs)
  nature     TEXT NOT NULL,
  ability    TEXT,
  gender     TEXT,                           -- "male","female","genderless"
  friendship INTEGER NOT NULL DEFAULT 50,
  held_item  TEXT,                           -- item_id
  moves      TEXT NOT NULL,                  -- JSON: ["tackle","growl",...]
  moves_pp   TEXT,                           -- JSON: [pp1, pp2, pp3, pp4]
  tera_type  TEXT,                           -- terastal type id (nullable until assigned)
  team_slot  INTEGER,                        -- 1..6 or NULL (in PC)
  box_no     INTEGER,                        -- NULL when in team; set when boxed
  box_pos    INTEGER,                        -- 1..box_capacity; NULL when in team
  fusion_data TEXT,                          -- JSON: stored data of absorbed fusion partner (Kyurem/Necrozma/Calyrex)
  shiny      INTEGER NOT NULL DEFAULT 0,
  is_hidden_ability INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (owner_id) REFERENCES users(user_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_pokemons_owner     ON pokemons(owner_id);
CREATE INDEX IF NOT EXISTS idx_pokemons_team      ON pokemons(owner_id, team_slot);
CREATE INDEX IF NOT EXISTS idx_pokemons_box       ON pokemons(owner_id, box_no, box_pos);

/* Per-user box metadata: name & count */
CREATE TABLE IF NOT EXISTS user_boxes (
  owner_id TEXT NOT NULL,
  box_no   INTEGER NOT NULL,                      -- 1..box_count
  name     TEXT NOT NULL DEFAULT 'Box',
  PRIMARY KEY (owner_id, box_no),
  FOREIGN KEY (owner_id) REFERENCES users(user_id) ON DELETE CASCADE
);

/* ─────────────────────────
   ECONOMY + BAG + BOX COUNT
   ───────────────────────── */
CREATE TABLE IF NOT EXISTS user_meta (
  owner_id  TEXT PRIMARY KEY,
  money     INTEGER NOT NULL DEFAULT 0,
  bag_pages INTEGER NOT NULL DEFAULT 6,
  box_count INTEGER NOT NULL DEFAULT 8,
  FOREIGN KEY (owner_id) REFERENCES users(user_id) ON DELETE CASCADE
);

/* Adventure state (story progress, cleared areas, discovered mons) */
CREATE TABLE IF NOT EXISTS adventure_state (
  owner_id TEXT PRIMARY KEY,
  data     TEXT,
  FOREIGN KEY (owner_id) REFERENCES users(user_id) ON DELETE CASCADE
);

/* Item master (supports real icons) */
CREATE TABLE IF NOT EXISTS items (
  id          TEXT PRIMARY KEY,              -- canonical id e.g. "poke_ball"
  name        TEXT NOT NULL,                 -- display name
  emoji       TEXT,                          -- optional: Unicode or <:name:id>
  icon_url    TEXT,                          -- CDN sprite for a real icon
  category    TEXT,                          -- "held","consumable","key",...
  description TEXT,
  price       INTEGER,                       -- shop buy price (optional)
  sell_price  INTEGER                        -- shop sell price (optional)
);

/* User inventory */
CREATE TABLE IF NOT EXISTS user_items (
  owner_id  TEXT NOT NULL,
  item_id   TEXT NOT NULL,
  qty       INTEGER NOT NULL DEFAULT 0 CHECK (qty >= 0),
  PRIMARY KEY (owner_id, item_id),
  FOREIGN KEY (owner_id) REFERENCES users(user_id) ON DELETE CASCADE,
  FOREIGN KEY (item_id)  REFERENCES items(id)      ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_user_items_owner ON user_items(owner_id);

/* Optional global config (e.g. box capacity) */
CREATE TABLE IF NOT EXISTS config (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
INSERT OR IGNORE INTO config(key, value) VALUES ('box_capacity', '30');

/* ─────────────────────────
   OPTIONAL LOGGING
   ───────────────────────── */
CREATE TABLE IF NOT EXISTS event_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    TEXT NOT NULL,
  type       TEXT NOT NULL,
  payload    TEXT NOT NULL,                  -- JSON string
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
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

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
