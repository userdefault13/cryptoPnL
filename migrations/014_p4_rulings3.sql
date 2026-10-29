-- P4 rulings 3 (DESIGN §8, architect review of PR #8). Projection tables only; ledger_entry and manual_basis are untouched.
-- Q-H: a lot opened for balance that arrived with no ledger row (shortfall=pending) is marked basis_origin='unrecorded_inflow'
ALTER TABLE fifo_lot ADD COLUMN basis_origin text CHECK (basis_origin IN ('unrecorded_inflow'));
-- Exits have no realized PnL: realized_usdc is NULL (never summed into totals); realized_display_usdc shows 0 for an exit of a lot
-- with a known cost (display only, never aggregated)
DROP VIEW lot_disposal_pnl;
CREATE VIEW lot_disposal_pnl AS SELECT d.*,
  CASE WHEN d.kind = 'exit' THEN NULL ELSE d.proceeds_usdc - d.cost_usdc END AS realized_usdc,
  CASE WHEN d.kind = 'exit' THEN CASE WHEN d.cost_usdc IS NULL THEN NULL ELSE 0 END ELSE d.proceeds_usdc - d.cost_usdc END AS realized_display_usdc
  FROM lot_disposal d;
