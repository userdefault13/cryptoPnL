-- Rollback of 006_p2_decisions.sql. Run inside a transaction; re-run `classify` afterwards on the old code.
BEGIN;
DELETE FROM ledger_entry WHERE category IN ('untracked','bridge_in');
ALTER TABLE ledger_entry DROP CONSTRAINT ledger_entry_category_check;
ALTER TABLE ledger_entry ADD CONSTRAINT ledger_entry_category_check CHECK (category IN
  ('swap','nft_buy','nft_sale','auction','transfer_internal','deposit','withdrawal','fee','income',
   'escrow_out','escrow_return','spam','migration_in'));
ALTER TABLE ledger_entry DROP COLUMN price_confidence_label;
ALTER TABLE price_point DROP COLUMN confidence_label;
ALTER TABLE fifo_lot DROP COLUMN basis_confidence_label;
ALTER TABLE lot_disposal DROP COLUMN proceeds_confidence_label;
DELETE FROM schema_migrations WHERE name='006_p2_decisions.sql';
COMMIT;
