-- PostgreSQL schema for Myuu bot
-- Uses JSONB for structured fields and timestamps in UTC.

-- Users & admins
CREATE TABLE IF NOT EXISTS users (
  user_id    TEXT PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  user_gender TEXT,
  starter    TEXT,
  coins      INTEGER NOT NULL DEFAULT 0,
  currencies JSONB NOT NULL DEFAULT '{"coins": 0}'
);

CREATE TABLE IF NOT EXISTS admins (
  user_id  TEXT PRIMARY KEY,
  added_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- One-time claim per announcement message (beta tokens)
CREATE TABLE IF NOT EXISTS beta_claims (
  message_id BIGINT PRIMARY KEY
);

-- Pokémon storage
CREATE TABLE IF NOT EXISTS pokemons (
  id            SERIAL PRIMARY KEY,
  owner_id      TEXT NOT NULL,
  species       TEXT NOT NULL,
  level         INTEGER NOT NULL DEFAULT 5,
  hp            INTEGER NOT NULL,
  hp_now        INTEGER,
  atk           INTEGER NOT NULL,
  def           INTEGER NOT NULL,
  spa           INTEGER NOT NULL,
  spd           INTEGER NOT NULL,
  spe           INTEGER NOT NULL,
  ivs           JSONB NOT NULL,
  evs           JSONB NOT NULL,
  nature        TEXT NOT NULL,
  ability       TEXT,
  gender        TEXT,
  friendship    INTEGER NOT NULL DEFAULT 50,
  held_item     TEXT,
  moves         JSONB NOT NULL,
  moves_pp      JSONB,
  moves_pp_min  JSONB,
  moves_pp_max  JSONB,
  tera_type     TEXT,
  team_slot     INTEGER,
  box_no        INTEGER,
  box_pos       INTEGER,
  fusion_data   JSONB,
  shiny         INTEGER NOT NULL DEFAULT 0,
  is_hidden_ability INTEGER NOT NULL DEFAULT 0,
  pokeball      TEXT,
  can_gigantamax BOOLEAN NOT NULL DEFAULT FALSE,
  form          TEXT,
  exp           INTEGER NOT NULL DEFAULT 0,
  exp_group     TEXT NOT NULL DEFAULT 'medium_fast',
  FOREIGN KEY (owner_id) REFERENCES users(user_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_pokemons_owner ON pokemons(owner_id);
CREATE INDEX IF NOT EXISTS idx_pokemons_team  ON pokemons(owner_id, team_slot);
CREATE INDEX IF NOT EXISTS idx_pokemons_box   ON pokemons(owner_id, box_no, box_pos);

-- Add new columns safely (for existing DBs)
ALTER TABLE users ADD COLUMN IF NOT EXISTS user_gender TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS beta_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE pokemons ADD COLUMN IF NOT EXISTS hp_now INTEGER;
ALTER TABLE pokemons ADD COLUMN IF NOT EXISTS moves_pp JSONB;
ALTER TABLE pokemons ADD COLUMN IF NOT EXISTS moves_pp_min JSONB;
ALTER TABLE pokemons ADD COLUMN IF NOT EXISTS moves_pp_max JSONB;
ALTER TABLE pokemons ADD COLUMN IF NOT EXISTS is_hidden_ability INTEGER;
ALTER TABLE pokemons ADD COLUMN IF NOT EXISTS exp INTEGER NOT NULL DEFAULT 0;
ALTER TABLE pokemons ADD COLUMN IF NOT EXISTS exp_group TEXT NOT NULL DEFAULT 'medium_fast';

-- Experience groups (Gen III+). exp_requirements seeded by ensure_exp_tables() in lib.db
CREATE TABLE IF NOT EXISTS exp_groups (
  code         TEXT PRIMARY KEY,
  description  TEXT,
  exp_at_100   INTEGER
);
INSERT INTO exp_groups (code, description, exp_at_100) VALUES
  ('erratic', 'Erratic (Gen III+)', 600000),
  ('fast', 'Fast', 800000),
  ('medium_fast', 'Medium Fast', 1000000),
  ('medium_slow', 'Medium Slow', 1059860),
  ('slow', 'Slow', 1250000),
  ('fluctuating', 'Fluctuating (Gen III+)', 1640000)
ON CONFLICT (code) DO NOTHING;

CREATE TABLE IF NOT EXISTS exp_requirements (
  group_code   TEXT NOT NULL REFERENCES exp_groups(code),
  level        INTEGER NOT NULL,
  exp_total    INTEGER NOT NULL,
  PRIMARY KEY (group_code, level)
);

-- Box metadata
CREATE TABLE IF NOT EXISTS user_boxes (
  owner_id TEXT NOT NULL,
  box_no   INTEGER NOT NULL,
  name     TEXT NOT NULL DEFAULT 'Box',
  PRIMARY KEY (owner_id, box_no),
  FOREIGN KEY (owner_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Economy + bag + box count
CREATE TABLE IF NOT EXISTS user_meta (
  owner_id  TEXT PRIMARY KEY,
  money     INTEGER NOT NULL DEFAULT 0,
  bag_pages INTEGER NOT NULL DEFAULT 6,
  box_count INTEGER NOT NULL DEFAULT 8,
  FOREIGN KEY (owner_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Adventure state (story progress, cleared areas, discovered mons)
CREATE TABLE IF NOT EXISTS adventure_state (
  owner_id TEXT PRIMARY KEY,
  data     JSONB,
  FOREIGN KEY (owner_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Item master
CREATE TABLE IF NOT EXISTS items (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  emoji       TEXT,
  icon_url    TEXT,
  category    TEXT,
  description TEXT,
  price       INTEGER,
  sell_price  INTEGER
);

-- User inventory
CREATE TABLE IF NOT EXISTS user_items (
  owner_id  TEXT NOT NULL,
  item_id   TEXT NOT NULL,
  qty       INTEGER NOT NULL DEFAULT 0 CHECK (qty >= 0),
  PRIMARY KEY (owner_id, item_id),
  FOREIGN KEY (owner_id) REFERENCES users(user_id) ON DELETE CASCADE,
  FOREIGN KEY (item_id)  REFERENCES items(id)      ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_user_items_owner ON user_items(owner_id);

-- Optional global config
CREATE TABLE IF NOT EXISTS config (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
INSERT INTO config(key, value) VALUES ('box_capacity', '30')
ON CONFLICT (key) DO NOTHING;

-- Logging
CREATE TABLE IF NOT EXISTS event_log (
  id         SERIAL PRIMARY KEY,
  user_id    TEXT NOT NULL,
  type       TEXT NOT NULL,
  payload    JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Pokédex cache
CREATE TABLE IF NOT EXISTS pokedex (
  id               INTEGER PRIMARY KEY,
  name             TEXT UNIQUE NOT NULL,
  introduced_in    INTEGER,
  types            JSONB NOT NULL,
  stats            JSONB NOT NULL,
  abilities        JSONB NOT NULL,
  sprites          JSONB,
  base_experience  INTEGER,
  height_m         REAL,
  weight_kg        REAL,
  base_happiness   INTEGER,
  capture_rate     INTEGER,
  egg_groups       JSONB,
  growth_rate      TEXT,
  ev_yield         JSONB,
  gender_ratio     JSONB,
  flavor           TEXT,
  evolution        JSONB,
  is_fully_evolved BOOLEAN,
  form_name        TEXT
);
CREATE INDEX IF NOT EXISTS idx_pokedex_name ON pokedex(name);
CREATE INDEX IF NOT EXISTS idx_pokedex_intro ON pokedex(introduced_in);

-- Move master
CREATE TABLE IF NOT EXISTS moves (
  id             INTEGER PRIMARY KEY,
  name           TEXT UNIQUE NOT NULL,
  introduced_in  INTEGER,
  type           TEXT,
  power          INTEGER,
  accuracy       INTEGER,
  pp             INTEGER,
  damage_class   TEXT,
  meta           JSONB
);
CREATE INDEX IF NOT EXISTS idx_moves_name ON moves(name);
CREATE INDEX IF NOT EXISTS idx_moves_gen  ON moves(introduced_in);

-- Learnsets
CREATE TABLE IF NOT EXISTS learnsets (
  species_id    INTEGER NOT NULL,
  form_name     TEXT NOT NULL DEFAULT '',
  move_id       INTEGER NOT NULL,
  generation    INTEGER NOT NULL,
  method        TEXT NOT NULL,
  level_learned INTEGER,
  PRIMARY KEY (species_id, form_name, move_id, generation, method),
  FOREIGN KEY (species_id) REFERENCES pokedex(id) ON DELETE CASCADE,
  FOREIGN KEY (move_id)   REFERENCES moves(id)   ON DELETE CASCADE
);

-- Rulesets
CREATE TABLE IF NOT EXISTS rulesets (
  scope      TEXT PRIMARY KEY,
  generation INTEGER NOT NULL
);

-- Form data
CREATE TABLE IF NOT EXISTS pokedex_forms (
  species_id    INTEGER NOT NULL,
  species_name  TEXT,
  form_key      TEXT NOT NULL,
  display_name  TEXT,
  stats         JSONB,
  types         JSONB,
  abilities     JSONB,
  is_battle_only BOOLEAN DEFAULT FALSE,
  PRIMARY KEY (species_id, form_key),
  FOREIGN KEY (species_id) REFERENCES pokedex(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_pokedex_forms_species ON pokedex_forms(species_id);
CREATE INDEX IF NOT EXISTS idx_pokedex_forms_name ON pokedex_forms(form_key);


-- Format rules
CREATE TABLE IF NOT EXISTS format_rules (
  format TEXT NOT NULL,
  gen    INTEGER NOT NULL,
  rules  TEXT NOT NULL,
  PRIMARY KEY (format, gen)
);

-- Generations
CREATE TABLE IF NOT EXISTS generations (
  id    INTEGER PRIMARY KEY,
  label TEXT NOT NULL,
  note  TEXT
);

-- Gigantamax forms
CREATE TABLE IF NOT EXISTS gigantamax (
  id                  SERIAL PRIMARY KEY,
  base_species        TEXT NOT NULL,
  base_species_id     INTEGER,
  gmax_form           TEXT NOT NULL,
  gmax_species_id     INTEGER,
  form_key            TEXT,
  gmax_move_changes   TEXT,
  stat_multiplier     REAL DEFAULT 1.5,
  hp_multiplier       REAL DEFAULT 1.5,
  signature_gmax_move TEXT,
  can_gigantamax      INTEGER DEFAULT 1,
  introduced_in       INTEGER DEFAULT 8,
  UNIQUE(base_species, form_key)
);

-- Item effects
CREATE TABLE IF NOT EXISTS item_effects (
  item_name        TEXT PRIMARY KEY,
  display_name     TEXT,
  pocket           TEXT,
  category         TEXT,
  attributes_json  JSONB,
  short_effect     TEXT,
  effect_text      TEXT,
  competitive_json JSONB
);

-- Mega evolution
CREATE TABLE IF NOT EXISTS mega_evolution (
  id              SERIAL PRIMARY KEY,
  base_species    TEXT NOT NULL,
  base_species_id INTEGER,
  mega_form       TEXT NOT NULL,
  mega_species_id INTEGER,
  mega_stone      TEXT,
  form_key        TEXT,
  stats           JSONB,
  types           JSONB,
  abilities       JSONB,
  is_x_form       INTEGER DEFAULT 0,
  is_y_form       INTEGER DEFAULT 0,
  introduced_in   INTEGER
);

-- Mega forms
CREATE TABLE IF NOT EXISTS mega_forms (
  base_species_id INTEGER NOT NULL,
  mega_species_id INTEGER NOT NULL,
  stone_item_id   TEXT,
  label           TEXT,
  PRIMARY KEY (base_species_id, mega_species_id)
);

-- Move generation stats
CREATE TABLE IF NOT EXISTS move_generation_stats (
  move_id      INTEGER NOT NULL,
  generation   INTEGER NOT NULL,
  pp           INTEGER,
  power        INTEGER,
  accuracy     INTEGER,
  type         TEXT,
  damage_class TEXT,
  makes_contact INTEGER,
  priority     INTEGER,
  PRIMARY KEY (move_id, generation),
  FOREIGN KEY (move_id) REFERENCES moves(id) ON DELETE CASCADE
);

-- Primal reversion
CREATE TABLE IF NOT EXISTS primal_reversion (
  id                SERIAL PRIMARY KEY,
  base_species      TEXT NOT NULL UNIQUE,
  base_species_id   INTEGER,
  primal_form       TEXT NOT NULL,
  primal_species_id INTEGER,
  orb_item          TEXT,
  form_key          TEXT,
  stats             JSONB,
  types             JSONB,
  abilities         JSONB,
  introduced_in     INTEGER DEFAULT 6
);

-- PvP formats
CREATE TABLE IF NOT EXISTS pvp_formats (
  id          SERIAL PRIMARY KEY,
  key         TEXT UNIQUE NOT NULL,
  name        TEXT NOT NULL,
  description TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- PvP format rules
CREATE TABLE IF NOT EXISTS pvp_format_rules (
  id             SERIAL PRIMARY KEY,
  format_key     TEXT NOT NULL,
  generation     INTEGER NOT NULL,
  max_mon_gen    INTEGER NOT NULL,
  clauses        JSONB NOT NULL,
  species_bans   JSONB,
  ability_bans   JSONB,
  move_bans      JSONB,
  item_bans      JSONB,
  team_combo_bans JSONB,
  mon_combo_bans JSONB,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (format_key) REFERENCES pvp_formats(key) ON DELETE CASCADE,
  UNIQUE(format_key, generation)
);

-- Team presets
CREATE TABLE IF NOT EXISTS team_presets (
  owner_id    TEXT NOT NULL,
  preset_name TEXT NOT NULL,
  team_data   JSONB NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (owner_id, preset_name),
  FOREIGN KEY (owner_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- User equipment
CREATE TABLE IF NOT EXISTS user_equipment (
  owner_id      TEXT PRIMARY KEY,
  mega_gear     TEXT,
  z_gear        TEXT,
  dmax_gear     TEXT,
  tera_gear     TEXT,
  mega_unlocked INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (owner_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- User rulesets
CREATE TABLE IF NOT EXISTS user_rulesets (
  user_id         TEXT PRIMARY KEY,
  generation      INTEGER NOT NULL,
  updated_at_utc  TIMESTAMPTZ,
  max_unlocked_gen INTEGER DEFAULT 1,
  FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
  FOREIGN KEY (generation) REFERENCES generations(id) ON UPDATE CASCADE ON DELETE RESTRICT
);

-- Optional: backfill pokemons.exp_group from pokedex.growth_rate (run once if you had exp data only in pokedex)
-- UPDATE pokemons p SET exp_group = LOWER(REPLACE(REPLACE(d.growth_rate, ' ', '_'), '-', '_'))
-- FROM pokedex d WHERE LOWER(d.name) = LOWER(p.species)
--   AND d.growth_rate IS NOT NULL
--   AND LOWER(REPLACE(REPLACE(d.growth_rate, ' ', '_'), '-', '_')) IN ('erratic','fast','medium_fast','medium_slow','slow','fluctuating');
