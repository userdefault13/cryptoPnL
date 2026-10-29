-- P4.1 rulings (DESIGN §8). Internal ETH legs keep their trace address; ETH bridge-ins open pending lots (basis_origin='bridge_in');
-- marks at as_of_block are written by the P3 pricing path (rulings 4) into p3_mark, one row per held asset (priced | no_valid_mark).
BEGIN;
ALTER TABLE ledger_entry ADD COLUMN trace_address text;   -- internal ETH legs (log_index = n - 100000): call path in the tx's trace
-- rule 5 (architect, 18:18 PT): an identified distribution is income at FMV, tagged so the report shows it as its own income line
ALTER TABLE ledger_entry ADD COLUMN IF NOT EXISTS income_subtype text, ADD COLUMN IF NOT EXISTS source_ref text;
ALTER TABLE ledger_entry ADD CONSTRAINT ledger_entry_income_subtype_check CHECK (income_subtype IS NULL OR (category = 'income'
  AND income_subtype IN ('dao_distribution') AND source_ref ~ '^0x[0-9a-f]{40}$'));
ALTER TABLE fifo_lot DROP CONSTRAINT IF EXISTS fifo_lot_basis_origin_check;
ALTER TABLE fifo_lot ADD CONSTRAINT fifo_lot_basis_origin_check CHECK (basis_origin IN ('unrecorded_inflow', 'bridge_in'));
CREATE TABLE p3_mark (chain_id int NOT NULL, asset_id int NOT NULL REFERENCES asset, as_of_block bigint NOT NULL,
  status text NOT NULL CHECK (status IN ('priced', 'no_valid_mark')), price_usdc numeric, source text, confidence_label text,
  price_id bigint REFERENCES price_point, reason text, held_qty numeric NOT NULL,
  PRIMARY KEY (chain_id, asset_id, as_of_block),
  CHECK ((status = 'priced') = (price_usdc IS NOT NULL AND price_usdc > 0)));
COMMIT;
