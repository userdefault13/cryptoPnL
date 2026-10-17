-- PR #3 architect decisions (aed10d9): untracked + bridge_in categories; a confidence label next to every confidence number.
-- Label mapping (config.CONFIDENCE, docs/P2_RESULTS.md): high = 1.0, medium = 0.6, low = 0.2.
ALTER TABLE ledger_entry DROP CONSTRAINT ledger_entry_category_check;
ALTER TABLE ledger_entry ADD CONSTRAINT ledger_entry_category_check CHECK (category IN
  ('swap','nft_buy','nft_sale','auction','transfer_internal','deposit','withdrawal','fee','income',
   'escrow_out','escrow_return','spam','migration_in','untracked','bridge_in'));
ALTER TABLE ledger_entry ADD COLUMN price_confidence_label text CHECK (price_confidence_label IN ('high','medium','low'));
ALTER TABLE price_point ADD COLUMN confidence_label text CHECK (confidence_label IN ('high','medium','low'));
ALTER TABLE fifo_lot ADD COLUMN basis_confidence_label text CHECK (basis_confidence_label IN ('high','medium','low'));
ALTER TABLE lot_disposal ADD COLUMN proceeds_confidence_label text CHECK (proceeds_confidence_label IN ('high','medium','low'));
