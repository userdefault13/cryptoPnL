-- Rollback of 015_p4_1_inflows.sql. Run, then: DELETE FROM schema_migrations WHERE name='015_p4_1_inflows.sql';
-- fifo_lot is a projection (rebuilt by `python -m cryptopnl.p4 rebuild`): bridge_in origins are cleared before the 014 CHECK returns.
-- Internal ETH ledger rows themselves are removed by re-running classify without the internal_eth raw rows (not by this file).
BEGIN;
DROP TABLE IF EXISTS p3_mark;
UPDATE fifo_lot SET basis_origin = NULL WHERE basis_origin = 'bridge_in';
ALTER TABLE fifo_lot DROP CONSTRAINT IF EXISTS fifo_lot_basis_origin_check;
ALTER TABLE fifo_lot ADD CONSTRAINT fifo_lot_basis_origin_check CHECK (basis_origin IN ('unrecorded_inflow'));
ALTER TABLE ledger_entry DROP COLUMN IF EXISTS trace_address;
COMMIT;
