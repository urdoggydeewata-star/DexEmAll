-- Add PokéDollars (coins) to users table if missing (PostgreSQL)
-- Run this in your SQL editor if the bot errors on coins/user balance.

-- Add coins column if it doesn't exist (PostgreSQL 9.5+)
ALTER TABLE users ADD COLUMN IF NOT EXISTS coins INTEGER NOT NULL DEFAULT 0;

-- If your Postgres version doesn't support IF NOT EXISTS, use this instead (comment out the line above):
-- DO $$
-- BEGIN
--   IF NOT EXISTS (
--     SELECT 1 FROM information_schema.columns
--     WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'coins'
--   ) THEN
--     ALTER TABLE users ADD COLUMN coins INTEGER NOT NULL DEFAULT 0;
--   END IF;
-- END $$;

-- Ensure existing rows have a value (in case column was added without DEFAULT)
UPDATE users SET coins = COALESCE(coins, 0) WHERE coins IS NULL;
