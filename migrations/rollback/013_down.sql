-- Rollback of 013_p4_fifo.sql. Run, then: DELETE FROM schema_migrations WHERE name='013_p4_fifo.sql';
-- Drops only P4 projection columns/tables. ledger_entry and manual_basis are untouched (P2's pending migration lots stay valid).
BEGIN;
DROP TABLE IF EXISTS fifo_run;
DROP TABLE IF EXISTS pnl_snapshot;
DROP TABLE IF EXISTS fifo_cost_bucket;
ALTER TABLE lot_disposal DROP COLUMN IF EXISTS lot_status, DROP COLUMN IF EXISTS expense_usdc, DROP COLUMN IF EXISTS own_cost_usdc,
  DROP COLUMN IF EXISTS bundle_ref, DROP COLUMN IF EXISTS closed_block, DROP COLUMN IF EXISTS kind;
DROP INDEX IF EXISTS fifo_lot_location;
ALTER TABLE fifo_lot DROP CONSTRAINT IF EXISTS fifo_lot_pending_null_source;
ALTER TABLE fifo_lot DROP COLUMN IF EXISTS manual_basis_id, DROP COLUMN IF EXISTS basis_out_usdc, DROP COLUMN IF EXISTS pending_reason,
  DROP COLUMN IF EXISTS parent_lot_id, DROP COLUMN IF EXISTS ref, DROP COLUMN IF EXISTS open_kind, DROP COLUMN IF EXISTS location,
  DROP COLUMN IF EXISTS wallet_id;
COMMIT;
