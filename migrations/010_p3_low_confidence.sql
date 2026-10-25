-- P3 rulings (architect, DESIGN §8 'P3 rulings'). Rollback: migrations/rollback/010_down.sql. No ON DELETE CASCADE added.
-- low_confidence: the entry HAS a price, but it is low confidence (thin pool below the liquidity floor with a swap <= 7 d old, or a
-- trade-implied price whose counter-leg is low). Counted in totals with a badge; totals are also reported without these entries.
-- pool_swap / pool_swap_scan: per-pool Swap-log block cache for the 7-day swap check (HyperSync, shared 5/min + 12 s bucket).
BEGIN;
ALTER TABLE ledger_entry DROP CONSTRAINT ledger_entry_price_flag_check;
ALTER TABLE ledger_entry ADD CONSTRAINT ledger_entry_price_flag_check
  CHECK (price_flag IN ('spam','untracked','pending_basis','nft_no_trade','no_price','low_confidence'));
CREATE TABLE pool_swap (chain_id int NOT NULL, pool bytea NOT NULL, block_number bigint NOT NULL, PRIMARY KEY (chain_id, pool, block_number));
CREATE TABLE pool_swap_scan (chain_id int NOT NULL, pool bytea NOT NULL, from_block bigint NOT NULL, scanned_to bigint NOT NULL,
  PRIMARY KEY (chain_id, pool));
COMMIT;
