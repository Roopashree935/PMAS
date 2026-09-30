-- 005: token revocation on credential rotation (issue #40, Phase 2)
--
-- Adds a nullable marker column: JWTs minted before this instant are
-- rejected, so a password rotation revokes every existing session.
-- NULL (all pre-existing rows) = no revocation — fully backward compatible.
--
-- SEQUENCING (same rule as 002/003/004): run this on the LIVE database
-- (Supabase SQL editor) BEFORE merging the code that reads the column.
-- The statement is idempotent and safe to re-run.

ALTER TABLE users ADD COLUMN IF NOT EXISTS token_valid_after TIMESTAMPTZ;
