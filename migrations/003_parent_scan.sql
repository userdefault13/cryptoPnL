-- P1.1: per-gotchi scan progress for Aavegotchi TransferToParent/TransferFromParent (custody changes)
CREATE TABLE parent_scan (chain_id int, gotchi_id numeric, last_block bigint NOT NULL, PRIMARY KEY(chain_id, gotchi_id));
CREATE INDEX raw_event_parent ON raw_event(chain_id, ((payload->>'gotchi_id'))) WHERE kind LIKE 'wearable_%';
