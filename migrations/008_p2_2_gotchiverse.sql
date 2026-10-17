-- P2.2 Gotchiverse (DESIGN v1.3 §9). Rollback: migrations/rollback/008_down.sql. No ON DELETE CASCADE added.
-- New categories: craft (inputs disposed, NFT acquired; free craft = no inputs, basis 0, never income), craft_pending (queued craft
-- inputs, cost held under escrow_ref craft:queue:<id>), upgrade (cost legs + finalize old->new id at parcel:<id>), gift_in (NFT
-- received as listing recipient with no wallet payment; basis 0, flagged), spend (bounce-gate burn), destroy_refund (unequip that
-- destroys the item: item disposed at parcel:<id>, 50 % alchemica refund acquired). Custody locations: parcel:<id>, lent:<borrower>, pocket:<gotchiId>.
BEGIN;
ALTER TABLE ledger_entry DROP CONSTRAINT ledger_entry_category_check;
ALTER TABLE ledger_entry ADD CONSTRAINT ledger_entry_category_check CHECK (category IN
  ('swap','nft_buy','nft_sale','auction','transfer_internal','deposit','withdrawal','fee','income',
   'escrow_out','escrow_return','spam','migration_in','untracked','bridge_in',
   'craft','craft_pending','upgrade','gift_in','spend','destroy_refund'));
-- Gotchi pocket (escrow) cache (§9 pocket ruling): gotchiEscrow(id) resolved once per gotchi by RPC at ingest; read by classify (no RPC there).
CREATE TABLE gotchi_escrow (chain_id int NOT NULL, gotchi_id bigint NOT NULL, escrow bytea NOT NULL, resolved_block bigint NOT NULL,
  PRIMARY KEY (chain_id, gotchi_id));
CREATE INDEX gotchi_escrow_addr ON gotchi_escrow (chain_id, escrow);
COMMIT;
