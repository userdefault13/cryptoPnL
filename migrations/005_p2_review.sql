-- PR #3 review / DESIGN v1.2 §8. The ledger "tx_class" is ledger_entry.category (text + CHECK, not a PG enum).
ALTER TABLE ledger_entry DROP CONSTRAINT ledger_entry_category_check;
ALTER TABLE ledger_entry ADD CONSTRAINT ledger_entry_category_check CHECK (category IN
  ('swap','nft_buy','nft_sale','auction','transfer_internal','deposit','withdrawal','fee','income',
   'escrow_out','escrow_return','spam','migration_in'));
-- location: 'wallet' or the escrow pseudo-location 'escrow:<diamond>' so FIFO lots can follow GHST into/out of escrow.
-- escrow_ref: 'baazaar:buyorder:<id>' / 'gbm:auction:<id>'. pnl_excluded: spam (flagged, unpriced, never in PnL totals).
ALTER TABLE ledger_entry ADD COLUMN location text NOT NULL DEFAULT 'wallet',
  ADD COLUMN escrow_ref text, ADD COLUMN pnl_excluded boolean NOT NULL DEFAULT false;
ALTER TABLE ledger_entry DROP CONSTRAINT ledger_entry_chain_id_tx_hash_log_index_wallet_id_asset_id_key;
ALTER TABLE ledger_entry ADD CONSTRAINT ledger_entry_leg_key UNIQUE (chain_id, tx_hash, log_index, wallet_id, asset_id, location, category);

-- fifo_lot / lot_disposal did not exist yet (P4). Created with the DESIGN §3 columns + §8 deltas only; P2 writes
-- fifo_lot rows for migration_in legs (pending basis) and nothing to lot_disposal.
-- basis_usdc is NULL while basis_status='pending' (unknown, NOT zero; excluded from PnL totals).
CREATE TABLE fifo_lot (id bigserial PRIMARY KEY, wallet_group text NOT NULL, asset_id int REFERENCES asset,
  open_entry_id bigint REFERENCES ledger_entry ON DELETE CASCADE, opened_at timestamptz, open_block bigint,
  qty_open numeric NOT NULL, qty_remaining numeric NOT NULL,
  basis_usdc numeric, basis_usdc_per_unit numeric GENERATED ALWAYS AS (basis_usdc / NULLIF(qty_open,0)) STORED,
  basis_price_source text, basis_confidence real,
  basis_status text NOT NULL DEFAULT 'resolved' CHECK (basis_status IN ('resolved','pending','manual')),
  chain_origin int, escrow_ref text,
  CHECK (basis_status = 'pending' OR basis_usdc IS NOT NULL));
CREATE INDEX ON fifo_lot(wallet_group, asset_id, open_block, id) WHERE qty_remaining > 0;
CREATE TABLE lot_disposal (id bigserial PRIMARY KEY, lot_id bigint REFERENCES fifo_lot ON DELETE CASCADE,
  close_entry_id bigint REFERENCES ledger_entry ON DELETE CASCADE, qty numeric NOT NULL,
  proceeds_usdc numeric, proceeds_price_source text, proceeds_confidence real,
  cost_usdc numeric,   -- NULL while the lot basis is pending -> realized_pnl_usdc NULL = pending realized PnL
  realized_pnl_usdc numeric GENERATED ALWAYS AS (proceeds_usdc - cost_usdc) STORED,
  closed_at timestamptz,
  payment_for bigint REFERENCES ledger_entry ON DELETE CASCADE);  -- the NFT acquisition an escrow disposal paid for
-- user_default's manual basis entries; survive classify rebuilds, never deleted (superseded rows kept as history).
CREATE TABLE manual_basis (id bigserial PRIMARY KEY, chain_id int NOT NULL, wallet_id int REFERENCES wallet,
  tx_hash bytea NOT NULL, log_index int NOT NULL, asset_id int REFERENCES asset,
  basis_usdc numeric NOT NULL, acquired_at timestamptz, entered_by text NOT NULL DEFAULT 'user_default',
  entered_at timestamptz NOT NULL DEFAULT now(), superseded_at timestamptz);
