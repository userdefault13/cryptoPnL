-- Rollback of 011_p3_price_run.sql. Run, then: DELETE FROM schema_migrations WHERE name='011_p3_price_run.sql';
BEGIN;
DROP TABLE IF EXISTS price_run;
COMMIT;
