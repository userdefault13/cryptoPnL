-- P3 (PR #7 approval note, 2026-10-24): one row per price_ledger run, so price-report (a separate process) can fail C3 when the
-- pricing run hit RPC errors (an RPC error otherwise ends as a plain no_price flag). Also records DEX pool fall-through after an RPC
-- error (e.g. GHST failing over from its first pool). Rollback: migrations/rollback/011_down.sql. No ON DELETE CASCADE.
BEGIN;
CREATE TABLE price_run (id bigserial PRIMARY KEY, chain_id int NOT NULL, finished_at timestamptz NOT NULL DEFAULT now(),
  entries int NOT NULL, rpc_calls int NOT NULL, rpc_errors int NOT NULL, fallthrough_after_rpc_error int NOT NULL,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb);
CREATE INDEX price_run_chain ON price_run (chain_id, id);
COMMIT;
