-- P4 FIFO engine (DESIGN v1.3 §3, §8 P4 requirements, §9 rules 3-6). fifo_lot / lot_disposal / pnl_snapshot / fifo_run /
-- fifo_cost_bucket are projections, rebuilt by cryptopnl/fifo.py; deleting ledger_entry rows may cascade into them.
-- manual_basis (user-entered) is NEVER under ON DELETE CASCADE from ledger_entry: it has no FK to ledger_entry, and the new
-- fifo_lot.manual_basis_id points FROM the projection TO it with ON DELETE RESTRICT. Rollback: rollback/013_down.sql.
BEGIN;
ALTER TABLE fifo_lot ADD COLUMN wallet_id int REFERENCES wallet,
  ADD COLUMN location text NOT NULL DEFAULT 'wallet',                          -- wallet | escrow:<diamond> | parcel:<id> | pocket:<id> | lent:<addr>
  ADD COLUMN open_kind text,                                                   -- buy|income|deposit|bridge_in|gift|migration|craft|craft_claim|free_craft|upgrade|refund|internal
  ADD COLUMN ref text,                                                         -- escrow / queue / bundle ref of the opening leg
  ADD COLUMN parent_lot_id bigint REFERENCES fifo_lot ON DELETE CASCADE,       -- custody split: the lot this one was carried from
  ADD COLUMN pending_reason text,                                              -- migration|deposit|no_price|queue_unmatched|upgrade_cost_unmatched|fee_unpriced
  ADD COLUMN basis_out_usdc numeric NOT NULL DEFAULT 0,                        -- basis already disposed or carried out (exact remainders)
  ADD COLUMN manual_basis_id bigint REFERENCES manual_basis ON DELETE RESTRICT,
  ADD COLUMN chain_id int,                                                     -- P4 rows; NULL on P2 classify rows
  ADD COLUMN basis_label text,                                                 -- engine confidence label (high|medium|low)
  ADD COLUMN fee_usdc numeric,                                                 -- capitalized gas share (in basis when resolved; outside totals while pending)
  ADD COLUMN split_method text CHECK (split_method IN ('basis','equal','recipe','single')),   -- gas share | craft cost split (equal = fallback)
  ADD COLUMN order_key text,                                                   -- FIFO order of the opening leg: [block, tx_index, tx, log_index, entry]
  ADD COLUMN is_nft boolean NOT NULL DEFAULT false;
-- §8: a pending lot has an unknown basis (NULL, never 0) and a NULL price source until resolved
ALTER TABLE fifo_lot ADD CONSTRAINT fifo_lot_pending_null_source CHECK (basis_status <> 'pending' OR (basis_usdc IS NULL AND basis_price_source IS NULL));
CREATE INDEX fifo_lot_location ON fifo_lot (wallet_group, asset_id, location) WHERE qty_remaining > 0;
ALTER TABLE lot_disposal ADD COLUMN kind text CHECK (kind IN ('sale','fee','fee_capitalized','spend','withdrawal','custody_exit','internal',
    'craft_input','upgrade_input','upgrade_close','destroy','bundle','bundle_item','exit')),   -- exit: Q-B custody exit (proceeds NULL, realized 0)
  ADD COLUMN closed_block bigint,
  ADD COLUMN bundle_ref text,                                                  -- bundle:parcel:<id> (§9 rule 6)
  ADD COLUMN own_cost_usdc numeric,                                            -- bundle parcel row: the parcel's own basis
  ADD COLUMN expense_usdc numeric,                                             -- spend, and gas when Q-A = expense
  ADD COLUMN lot_status text CHECK (lot_status IN ('resolved','pending','manual')),   -- pending -> pending disposal (§8 count)
  ADD COLUMN proceeds_label text,
  ADD COLUMN display_mv_usdc numeric;                                          -- exit: market value at the block, display only
-- realized PnL with the Q-B exit rule (realized 0 when the exited lot's basis is known); the stored generated column stays proceeds - cost
CREATE VIEW lot_disposal_pnl AS SELECT d.*, CASE WHEN d.kind = 'exit' THEN CASE WHEN d.cost_usdc IS NULL THEN NULL ELSE 0 END
  ELSE d.proceeds_usdc - d.cost_usdc END AS realized_usdc FROM lot_disposal d;
-- Q-G: on-chain recipe cost per unit of a craftable item at a craft block (alchemica + GLTR + GHST valued at that block), stored at
-- ingest/pricing time (RPC under the drpc limiter) so the engine stays offline. Missing -> the craft split falls back to equal (flagged).
CREATE TABLE craft_recipe_cost (chain_id int NOT NULL, asset_id int NOT NULL REFERENCES asset, block_number bigint NOT NULL,
  cost_usdc numeric NOT NULL CHECK (cost_usdc > 0), source text NOT NULL, PRIMARY KEY (chain_id, asset_id, block_number));
-- craft_pending / upgrade cost waiting for QueueClaimed / finalize (§9 rules 3-4); NULL value = an input was unpriced (never 0)
CREATE TABLE fifo_cost_bucket (chain_id int NOT NULL, wallet_group text NOT NULL, ref text NOT NULL, value_usdc numeric, confidence_label text, split_method text,
  PRIMARY KEY (chain_id, wallet_group, ref));
-- DESIGN §3 pnl_snapshot plus the §8 pending counts; one row per (group, asset, as_of block, variant all|excl_low)
CREATE TABLE pnl_snapshot (wallet_group text NOT NULL, asset_id int REFERENCES asset, as_of timestamptz, as_of_block bigint NOT NULL,
  variant text NOT NULL DEFAULT 'all' CHECK (variant IN ('all','excl_low')),
  qty numeric, cost_basis_usdc numeric, mark_price_usdc numeric CHECK (mark_price_usdc IS NULL OR mark_price_usdc > 0),
  mark_source text, market_value_usdc numeric, realized_pnl_usdc numeric, unrealized_pnl_usdc numeric,
  pending_lots int NOT NULL DEFAULT 0, pending_disposals int NOT NULL DEFAULT 0,
  PRIMARY KEY (wallet_group, asset_id, as_of_block, variant));
-- one row per engine run: full rebuild (from_block NULL) or recompute from block X; md5 over the fixed lot/disposal columns
CREATE TABLE fifo_run (id bigserial PRIMARY KEY, chain_id int NOT NULL, from_block bigint, started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  finished_at timestamptz, lots int, disposals int, lots_md5 text, policy jsonb NOT NULL,
  last_key jsonb, state jsonb);                                                -- engine counters (income, excluded, next ids) for recompute from block X
COMMIT;
