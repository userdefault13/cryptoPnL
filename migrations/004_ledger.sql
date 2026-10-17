-- P2 ledger + classification (DESIGN v1.1 §3). Prices stay NULL until P3; qty is signed, in raw token units (decimals in P3).
CREATE TABLE price_point (id bigserial PRIMARY KEY, asset_id int REFERENCES asset,
  chain_id int, block_number bigint, ts timestamptz NOT NULL, price_usdc numeric NOT NULL,
  source text NOT NULL, confidence real, UNIQUE(asset_id, block_number, source));
-- log_index: the source raw_event log index; -1 = gas leg (tx-level), -2 = native value leg of the same tx.
CREATE TABLE ledger_entry (id bigserial PRIMARY KEY, wallet_id int REFERENCES wallet,
  asset_id int REFERENCES asset, chain_id int, tx_hash bytea, log_index int,
  block_number bigint NOT NULL, ts timestamptz NOT NULL,
  qty numeric NOT NULL,
  category text NOT NULL CHECK (category IN ('swap','nft_buy','nft_sale','auction','transfer_internal','deposit','withdrawal','fee','income')),
  trade_group uuid,
  price_usdc numeric, price_source text, price_confidence real, price_id bigint REFERENCES price_point,
  UNIQUE(chain_id, tx_hash, log_index, wallet_id, asset_id));
CREATE INDEX ledger_entry_tx ON ledger_entry(chain_id, tx_hash);
CREATE TABLE review_queue (chain_id int, wallet_id int REFERENCES wallet, tx_hash bytea, reason text NOT NULL,
  detail jsonb, created_at timestamptz DEFAULT now(), PRIMARY KEY(chain_id, wallet_id, tx_hash));
