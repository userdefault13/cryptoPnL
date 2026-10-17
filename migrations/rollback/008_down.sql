-- Rollback of 008_p2_2_gotchiverse.sql. Re-run `classify` on the old code afterwards; then
-- DELETE FROM schema_migrations WHERE name='008_p2_2_gotchiverse.sql'; optionally DELETE FROM raw_event WHERE source='hypersync_gv'.
BEGIN;
DELETE FROM ledger_entry WHERE category IN ('craft','craft_pending','upgrade','gift_in','spend','destroy_refund');
ALTER TABLE ledger_entry DROP CONSTRAINT ledger_entry_category_check;
ALTER TABLE ledger_entry ADD CONSTRAINT ledger_entry_category_check CHECK (category IN
  ('swap','nft_buy','nft_sale','auction','transfer_internal','deposit','withdrawal','fee','income',
   'escrow_out','escrow_return','spam','migration_in','untracked','bridge_in'));
COMMIT;
