-- P3 pricing (DESIGN v1.2 §2). Rollback: migrations/rollback/007_down.sql. No ON DELETE CASCADE added anywhere.
-- price_flag: why an entry has no price (every entry has a price or a flag). spam/untracked: never priced (DESIGN §8);
-- pending_basis: migration_in, unknown carry-over basis (P4 excludes it from mark AND basis); nft_no_trade: NFT leg with no
-- trade-implied value (NFT marks follow §5 Q8, open); no_price: tracked fungible with no source at that block (never invented).
ALTER TABLE ledger_entry ADD COLUMN price_flag text CHECK (price_flag IN ('spam','untracked','pending_basis','nft_no_trade','no_price'));
ALTER TABLE ledger_entry ADD COLUMN tx_index int;   -- position of the tx in its block (entries within a block ordered by it)
ALTER TABLE price_point ADD COLUMN detail jsonb;    -- pool / route / API timestamp behind the price
-- tx position for txs that share a block with another wallet tx and have no HyperSync transaction_index (RPC, read-only)
CREATE TABLE tx_position (chain_id int NOT NULL, tx_hash bytea NOT NULL, block_number bigint NOT NULL, tx_index int NOT NULL,
  PRIMARY KEY (chain_id, tx_hash));
-- USDC numeraire (architect ruling, KNOWN_GAPS #16): P2's 'par' label becomes 'numeraire' (same value 1, high).
UPDATE ledger_entry SET price_source='numeraire' WHERE price_source='par';
UPDATE fifo_lot SET basis_price_source='numeraire' WHERE basis_price_source='par';
