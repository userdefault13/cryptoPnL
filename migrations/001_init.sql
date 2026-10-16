-- P1 raw ingest schema (DESIGN.md v0.9 §3 subset)
CREATE TABLE wallet (id serial PRIMARY KEY, chain_id int NOT NULL, address bytea NOT NULL,
  label text, wallet_group text NOT NULL DEFAULT 'default', UNIQUE(chain_id,address));
CREATE TABLE asset (id serial PRIMARY KEY, chain_id int NOT NULL, contract bytea,
  standard text NOT NULL CHECK (standard IN ('native','erc20','erc721','erc1155')),
  token_id numeric, symbol text, decimals int, coingecko_id text, is_stable bool DEFAULT false,
  UNIQUE NULLS NOT DISTINCT (chain_id, contract, token_id));
CREATE TABLE block (chain_id int, number bigint, hash bytea NOT NULL, ts timestamptz NOT NULL,
  PRIMARY KEY(chain_id, number));
CREATE TABLE raw_event (chain_id int, tx_hash bytea, log_index int,
  block_number bigint NOT NULL, block_hash bytea NOT NULL, source text NOT NULL,
  kind text NOT NULL, payload jsonb NOT NULL, PRIMARY KEY(chain_id, tx_hash, log_index));
CREATE INDEX raw_event_block ON raw_event(chain_id, block_number);
CREATE INDEX raw_event_from ON raw_event(chain_id, (payload->>'from'));
CREATE INDEX raw_event_to ON raw_event(chain_id, (payload->>'to'));
CREATE TABLE sync_cursor (source text, wallet_id int REFERENCES wallet, last_block bigint,
  last_block_hash bytea, updated_at timestamptz, PRIMARY KEY(source, wallet_id));
