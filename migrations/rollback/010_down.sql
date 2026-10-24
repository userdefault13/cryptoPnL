-- Rollback of 010_p3_low_confidence.sql. Run, then: DELETE FROM schema_migrations WHERE name='010_p3_low_confidence.sql';
BEGIN;
UPDATE ledger_entry SET price_flag=NULL WHERE price_flag='low_confidence';
ALTER TABLE ledger_entry DROP CONSTRAINT ledger_entry_price_flag_check;
ALTER TABLE ledger_entry ADD CONSTRAINT ledger_entry_price_flag_check
  CHECK (price_flag IN ('spam','untracked','pending_basis','nft_no_trade','no_price'));
DROP TABLE IF EXISTS pool_swap_scan;
DROP TABLE IF EXISTS pool_swap;
COMMIT;
