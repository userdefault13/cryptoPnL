-- Rollback of 005_p2_review.sql (apply 006_down.sql first if 006 is applied). Run inside a transaction.
-- WARNING: drops manual_basis (user_default's manual entries); export it first:
--   psql -c "\copy manual_basis TO 'manual_basis_backup.csv' CSV HEADER"
BEGIN;
DROP TABLE IF EXISTS lot_disposal;
DROP TABLE IF EXISTS fifo_lot;
DROP TABLE IF EXISTS manual_basis;
DELETE FROM ledger_entry WHERE category IN ('escrow_out','escrow_return','spam','migration_in') OR location <> 'wallet';
ALTER TABLE ledger_entry DROP CONSTRAINT ledger_entry_leg_key;
ALTER TABLE ledger_entry DROP COLUMN location, DROP COLUMN escrow_ref, DROP COLUMN pnl_excluded;
ALTER TABLE ledger_entry ADD CONSTRAINT ledger_entry_chain_id_tx_hash_log_index_wallet_id_asset_id_key UNIQUE (chain_id, tx_hash, log_index, wallet_id, asset_id);
ALTER TABLE ledger_entry DROP CONSTRAINT ledger_entry_category_check;
ALTER TABLE ledger_entry ADD CONSTRAINT ledger_entry_category_check CHECK (category IN
  ('swap','nft_buy','nft_sale','auction','transfer_internal','deposit','withdrawal','fee','income'));
DELETE FROM schema_migrations WHERE name='005_p2_review.sql';
COMMIT;
-- then re-run `classify` with the pre-005 code to rebuild the ledger.
