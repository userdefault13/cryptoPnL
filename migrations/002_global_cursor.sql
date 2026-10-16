-- Contract-scoped (non-wallet) sources, e.g. Baazaar/GBM marketplace logs (S1b replacement, DESIGN v1.0)
CREATE TABLE sync_cursor_global (source text, chain_id int, last_block bigint, last_block_hash bytea,
  updated_at timestamptz, PRIMARY KEY(source, chain_id));
