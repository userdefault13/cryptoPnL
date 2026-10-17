# P2 results: ledger & classification (after the PR #3 review, DESIGN v1.2 §8)

Pass test (DESIGN v1.1 §4 / docs/P2_PLAN.md): >98% of wallet txs classified, the rest in `review_queue`, 10 hand-checked txs match the explorer.

| chain | DB | wallet txs | classified | review | % | gate | ledger rows / md5 | evidence |
|-------|----|-----------:|-----------:|-------:|--:|------|-------------------|----------|
| Base 8453 | cryptopnl_p11s_base | 829 | 828 | 1 | 99.879 | PASS | 1252 / 18fb3f0acf66c5863802e5c9247c8aad | docs/evidence/p2_classify_8453.json |
| Base Sepolia 84532 | cryptopnl_p11s_sep | 126 | 126 | 0 | 100.0 | PASS | 802 / d359b9b469d5f4baa7ab3ba38584b465 | docs/evidence/p2_classify_84532.json |

(Before the review: Base 98.914% with 9 in review, Sepolia 100%.)

- Idempotency: `classify` run twice per chain gives identical ledger/review md5 (scripts/p2_test.sh enforces this).
- Hand check: 10/10 match Blockscout, with full tx hashes. See docs/evidence/p2_handcheck.md.
- Review queue: Base has 1 tx, the Uniswap swap into ETH 0xccbfe04a…58c0 (internal ETH not indexed, DESIGN §1). Sepolia has 0.
- Unit tests: `CRYPTOPNL_DSN=postgresql:///cryptopnl_unit11 ENVIO_API_TOKEN=x .venv/bin/python -m unittest discover tests` gives 24 OK.

## Base tx categories (per tx)
spam 338 · fee 280 · withdrawal 71 · swap 41 · deposit 27 · income 22 · escrow_out 15 · nft_buy 12 · escrow_return 10 · migration_in 8 · auction 4 · review 1.

## Escrow (blocker 1)
GHST sent to the Baazaar (0xa99c…) or GBM (0x8032…) diamond on a buy-order placement or bid is `escrow_out`. It is written as two rows:
wallet -X and `escrow:<diamond>` +X. The payment for a fill or winning claim is an `escrow:` -X leg in the same trade_group as the NFT leg
(`nft_buy` / `auction`). A cancel or outbid refund is `escrow_return`: escrow -X and wallet +X. Partial fills consume only price × quantity.
- Base: 15 escrows (1 buy order, 14 GBM bids). Every one closes: 1 fill, 4 wins, 10 refunds. Open escrow at head is 0 (`open_escrow: []`).
- GBM outbid refunds return the bid plus an incentive (5% or 0.5%). The incentive is a separate `income` row with the same escrow_ref (10 rows).
- The refund 0x9248c703…1ded4 has no indexed event. It is matched heuristically to the only open GBM escrow (auction 5613, 0.5 → 0.525 GHST).
- Not ingested: Baazaar `ERC1155BuyOrderAdd` (topic0 0xb89a3fa0…7e9edc, confirmed on Blockscout) and the cancel events. A placement
  is recognised by the GHST transfer to the diamond plus selector 0x4cc4a386. The order id is stamped onto the placement rows from the fill event.
- P4 (not implemented): on a fill, the escrowed GHST lots are disposed at the fill block's GHST/USDC price, and the NFT basis equals that amount.
  `lot_disposal.payment_for` exists for that link.

## Migration basis (blocker 2): user_default's decision is carry-over
`mintAavegotchiBridged` and other bridged re-mints are `migration_in`: a custody move, never income. Rule: NFT mints from 0x0 of the
Aavegotchi contracts, in txs not sent by the wallet, within blocks 33,200,000–34,000,138. The end bound comes from our data; the architect should confirm it.
- Base: 8 txs, 74 legs, giving 74 `fifo_lot` rows with `basis_status = pending`, `basis_usdc = NULL` (unknown, **not zero**), `chain_origin = 137`,
  `basis_price_source = polygon_carryover`, and `opened_at = NULL` (the Polygon acquisition time arrives with P6).
- Pending lots count toward holdings but are excluded from basis and PnL totals (`basis_totals`). A sell from a pending lot gives a NULL (pending) realized PnL.
- Manual entry: `cryptopnl set-basis --lot <id> --basis-usdc <x> [--acquired-at <ts>]` sets price_source=manual, confidence 0.2 (low) and
  basis_status=manual. Entries live in `manual_basis`: they are never deleted, earlier ones are superseded, and they are re-applied on every classify rebuild.
- Per DESIGN v1.2 §8, there is no invented fallback when the Polygon basis can't be found. It stays pending until the Polygon carry-over (P6) or a manual entry.

## Spam
`spam` rows stay in the ledger with `pnl_excluded = true`, are never priced, and are excluded from `totals()`. They are never deposit, withdrawal or review.
- Base: 338 txs / 346 rows. That is 330 unsolicited non-allowlisted token txs (not sent by the wallet), 7 zero-value poisoning transfers (kept as qty 0) and 1 pass-through.
- Sepolia: 71 txs / 735 rows (Sepolia has no allowlist).
- **Deviation, for the architect:** the review counted 354 Base and 72 Sepolia txs. Those 354/72 included 24 Base and 1 Sepolia txs that **the wallet sent itself**,
  for example its own mints of Aarcade Cartridges (0xbdb5…, 0x2487…) and token sends it signed. DESIGN §8 defines spam as *unsolicited*, so these stay
  deposit/withdrawal/income (unpriced until P3 decides). Reported as `wallet_sent_txs_with_non_allowlisted_token_legs`.

## Schema (migration 005)
- `ledger_entry.category` (the "tx_class": text + CHECK, not a PG enum) gains escrow_out, escrow_return, spam and migration_in.
- `ledger_entry` gains `location`, `escrow_ref` and `pnl_excluded`. The unique key now includes location and category.
- `fifo_lot` and `lot_disposal` did not exist yet. They were created with the DESIGN §3 columns plus `basis_status`, `chain_origin`, `escrow_ref` and `payment_for`. `basis_usdc` and `cost_usdc` are nullable for pending basis.
- `manual_basis` was added.
