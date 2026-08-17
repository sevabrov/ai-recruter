-- Runs once, on first container start (empty data volume only).
-- Extensions the later phases rely on:
--   pgcrypto  → gen_random_uuid() for primary keys
--   pg_trgm   → trigram similarity for lead deduplication (spec §45)
--   unaccent  → matching "Lucía" against "Lucia"

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
