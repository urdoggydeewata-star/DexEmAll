-- Migrate from single coins column to currencies JSONB (PostgreSQL)
-- Run this in your SQL editor once. Adds a currencies JSON object so you can add more currencies later.

-- 1. Add currencies column (JSONB, default {"coins": 0})
ALTER TABLE users ADD COLUMN IF NOT EXISTS currencies JSONB NOT NULL DEFAULT '{"coins": 0}';

-- 2. Backfill from existing coins into currencies (if coins column exists)
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'coins'
  ) THEN
    UPDATE users
    SET currencies = jsonb_set(
      COALESCE(NULLIF(currencies::text, 'null')::jsonb, '{}'::jsonb),
      '{coins}',
      to_jsonb(COALESCE(coins, 0)::int)
    );
  END IF;
END $$;

-- 3. Drop old coins column (optional; uncomment when ready)
-- ALTER TABLE users DROP COLUMN IF EXISTS coins;
