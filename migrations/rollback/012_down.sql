-- Rollback of 012_p3_price_run_retries.sql. Run, then: DELETE FROM schema_migrations WHERE name='012_p3_price_run_retries.sql';
BEGIN;
ALTER TABLE price_run ALTER COLUMN finished_at SET DEFAULT now();
ALTER TABLE price_run DROP COLUMN IF EXISTS rpc_retries;
ALTER TABLE price_run DROP COLUMN IF EXISTS started_at;
COMMIT;
