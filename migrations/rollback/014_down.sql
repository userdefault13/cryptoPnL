-- Rollback of 014_p4_rulings3.sql. Run, then: DELETE FROM schema_migrations WHERE name='014_p4_rulings3.sql';
-- Restores 013's lot_disposal_pnl view and drops fifo_lot.basis_origin (a projection column, rebuilt by `python -m cryptopnl.p4 rebuild`).
BEGIN;
DROP VIEW IF EXISTS lot_disposal_pnl;
CREATE VIEW lot_disposal_pnl AS SELECT d.*, CASE WHEN d.kind = 'exit' THEN CASE WHEN d.cost_usdc IS NULL THEN NULL ELSE 0 END
  ELSE d.proceeds_usdc - d.cost_usdc END AS realized_usdc FROM lot_disposal d;
ALTER TABLE fifo_lot DROP COLUMN IF EXISTS basis_origin;
COMMIT;
