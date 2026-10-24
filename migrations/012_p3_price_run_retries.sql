-- P3 (architect ruling on the d909779 rerun, 2026-10-24): price_run gets started_at and rpc_retries; finished_at is the wall-clock
-- finish (clock_timestamp(), set explicitly by price_ledger; now() would be the transaction start). Rollback: rollback/012_down.sql.
BEGIN;
ALTER TABLE price_run ADD COLUMN started_at timestamptz;
ALTER TABLE price_run ADD COLUMN rpc_retries int NOT NULL DEFAULT 0;
ALTER TABLE price_run ALTER COLUMN finished_at SET DEFAULT clock_timestamp();
COMMIT;
