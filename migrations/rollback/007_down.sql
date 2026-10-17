-- Rollback of 007_p3_pricing.sql. Run, then: DELETE FROM schema_migrations WHERE name='007_p3_pricing.sql';
BEGIN;
UPDATE fifo_lot SET basis_price_source='par' WHERE basis_price_source='numeraire';
UPDATE ledger_entry SET price_source='par' WHERE price_source='numeraire' AND price_usdc = 1;
UPDATE ledger_entry SET price_usdc=NULL, price_source=NULL, price_confidence=NULL, price_confidence_label=NULL, price_id=NULL
  WHERE price_source IS NOT NULL AND price_source <> 'par';
DELETE FROM price_point;
DROP TABLE IF EXISTS tx_position;
ALTER TABLE price_point DROP COLUMN IF EXISTS detail;
ALTER TABLE ledger_entry DROP COLUMN IF EXISTS tx_index;
ALTER TABLE ledger_entry DROP COLUMN IF EXISTS price_flag;
COMMIT;
