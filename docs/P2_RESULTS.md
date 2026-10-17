# P2 results: ledger & classification (PR #3 second review: architect decisions A, blockers B1/B2, fixes C)

Pass test (DESIGN v1.1 §4 / docs/P2_PLAN.md): >98% of wallet txs classified, the rest in `review_queue`, 10 hand-checked txs match the explorer.

| chain | DB | wallet txs | classified | review | % | gate | ledger rows / md5 | evidence |
|-------|----|-----------:|-----------:|-------:|--:|------|-------------------|----------|
| Base 8453 | cryptopnl_p11s_base | 829 | 827 | 2 | 99.759 | PASS | 1245 / 4ed2a85be9002ecffe8331198034442d | docs/evidence/p2_classify_8453.json |
| Base Sepolia 84532 | cryptopnl_p11s_sep | 126 | 126 | 0 | 100.0 | PASS | 802 / f4a81e5d4948f29677aa7db4de84d43f | docs/evidence/p2_classify_84532.json |

(Previous round, aed10d9: Base 99.879% with 1 in review, Sepolia 100%. Before the first review: Base 98.914%.)

- Runs (2026-10-16, PDT): Base `scripts/p2_test.sh` 23:07–23:11, then Sepolia 23:12–23:16. One chain at a time under nohup, with ≥75 s sleep before and between ingest passes.
  `classify` was run twice per chain and gave identical ledger/review md5.
- **HyperSync** (host-wide request log `NET_REQLOG`, one line per HTTP attempt, retries included; `scripts/reqlog_summary.py`):
  Base 23:09=4, 23:10=1, 23:11=3. Sepolia 23:13=2, 23:15=1, 23:16=2. **Busiest 60 s window = 4** (≤7). Files: docs/evidence/p2_hypersync_<chain>.txt.
  Sepolia pass 2 got **one HTTP 429** (no Retry-After header). Exponential backoff retried it and it succeeded. The budget was ≤3/min at that moment, so either
  the host-side limit is shared with another consumer or it is lower than 7/min. Not verified.
- RPC (1/s, burst 3): Base tx_meta 24 lookups, Sepolia 69, no 429. `ingest_tx_meta` is new. It calls RPC `eth_getTransactionByHash` for wallet-received mints from 0x0 whose
  tx the wallet neither sent nor received, and stores `raw_event` kind `tx_meta` (log_index -3) with {from, to, selector, value}. It is idempotent: the second pass had 0 candidates.
- Review queue. Base (2): 0xccbfe04a…58c0, the DEX swap into ETH (internal ETH gap). 0xeb12a130cdc297ede7d906ac0e31b12097e246d92fb5fdffab39944dc87fc2e8, see *Migration*. Sepolia: 0.
- Unit tests: `CRYPTOPNL_DSN=postgresql:///cryptopnl_unit11 ENVIO_API_TOKEN=x .venv/bin/python -m unittest discover tests` gives 30 OK (15 classify).

## Base tx categories (per tx)
spam 337 · fee 280 · withdrawal 61 · swap 36 · untracked 29 · deposit 25 · escrow_out 15 · nft_buy 12 · escrow_return 10 · income 9 · migration_in 8 · auction 4 · bridge_in 1 · review 2.
Sepolia: spam 71 · fee 39 · deposit 5 · withdrawal 5 · nft_buy 4 · swap 1 · untracked 1.

## Escrow (blocker 1 + B1/B2)
GHST sent to the Baazaar (0xa99c…) or GBM (0x8032…) diamond on a buy-order placement or bid is `escrow_out`: wallet -X and `escrow:<diamond>` +X.
A fill or winning claim pays from escrow (`escrow:` -X, same trade_group as the NFT leg). A cancel or outbid refund is `escrow_return`.
- Base: 15 escrows (1 buy order, 14 GBM bids). All close: 1 fill, 4 wins, 10 refunds. Open escrow at head = 0. 10 GBM incentive `income` rows.
- **B1:** any token to or from the Baazaar or GBM diamond that no escrow or market rule claims goes to **review**, never withdrawal or deposit. Tested in both directions, plus GBM.
  **Diamond-bound withdrawals finding:** there were 71 withdrawal txs on Base under aed10d9. **0 of them** have a token leg to 0xa99c… or 0x8032….
  One of them (0x3a46db382e373e96997018dd9b1c996ff6e187667a48a71aa1d5cc1aed0b8442) *calls* the Baazaar diamond (selector 0xb0facab3), but its
  only leg is token 0x2028b404… 50000000000000000 to 0x728f0baf79ebdfa336978c90f244324a0ba7bcff, not to the diamond. It stays a withdrawal.
- **B2:** buy-order fills are matched by order id. First, an entry already linked to that id. Otherwise exactly one unlinked open entry with amount = price×qty.
  Otherwise (first partial fill of an unlinked order) exactly one unlinked entry that is a multiple of price and larger than the payment. None or several candidates goes to review.
  Tests: A=100 / B=50 (fill 50 links B, A stays open and unlinked), linked id wins over an exact amount, two unlinked 100s go to review.

## Migration basis: carry-over, pending until P6
Rule (architect): **all** of the following must hold.
- tx.from is the bridge sender 0xf52398257a254d541f392667600901f710a006ed or the wallet itself.
- Every leg is an NFT mint from 0x0 to the wallet of an allowlisted Aavegotchi contract.
- The (selector, tx.to) pair is on the per-asset list: Diamond 0xf55b061c, wearables 0xfd7499bd (tx.to 0xa99c…), Forge 0x506ccb27, REALM 0x0d51a188, Installations 0x9110d148, Tiles 0x91b06c6e.

Any other bridge-sender mint goes to **review** (never spam or income). The block window 33,200,000–34,000,138 only produces a warning (none fired on Base).
- Base: **8 txs / 74 legs are migration_in** (1f6395, fd0dde, 8e218b, ea87f9, 5b6e21, 199b45, 14f28e, de48be). That gives 74 `fifo_lot` rows: `basis_status=pending`,
  `basis_usdc` NULL, **`basis_price_source` NULL**, `basis_confidence_label` NULL, `chain_origin=137`. Lots are per (contract, id) for ERC1155.
- **The architect's "9 re-mint txs": the 9th is 0xeb12a130…c2e8.** The bridge sender calls `mintBatch` (selector 0x5e41ee65) on **FakeGotchisNFTDiamond
  0xab59ca4a16925b0a4bac5026c94beb20a29df479** (FAKE Gotchis, ERC-721; Blockscout lists its creator as the bridge sender) and mints 7 FAKE Gotchis to `<TEST_WALLET>` at block 33,222,797.
  That contract and selector are not on the architect's list, so the rule sends it to review. Before this fix it was wrongly spam. **Decision needed:** add
  `0x5e41ee65 → 0xab59…` and the contract to the list to make it migration_in.
- Manual entry: `cryptopnl set-basis --lot <id> --basis-usdc <x> [--acquired-at <ts>]`. --lot and --basis-usdc are required, and the value must be a finite decimal ≥ 0 (otherwise exit 1).
  It sets price_source manual, confidence 0.2, label low, status manual. It is re-applied on every rebuild.

## bridge_in (Circle CCTP)
0x40a3c4… is **bridge_in at par**: USDC 99961238 (99.961238 USDC) minted from 0x0 to the wallet. tx.to is CCTP V1 MessageTransmitter 0xAD09780d193884d503182aD4588450C416D6F9D4
(selector 0x57ecfd28), and the wallet did not send the tx. It opens a lot with basis 99.961238 USD, source `par`, confidence 1.0, label high, status resolved.
Addresses come from Circle's official docs: V1 https://developers.circle.com/cctp/v1/evm-smart-contracts (TokenMessenger 0x1682Ae63…8962,
MessageTransmitter 0xAD09780d…F9D4) and V2 https://developers.circle.com/cctp/references/contract-addresses (TokenMessengerV2 0x28b5a0e9…cf5d,
MessageTransmitterV2 0x81D40F21…4B64). Any other USDC mint goes to review. The emitter can't be verified from wallet-scoped logs (docs/KNOWN_GAPS.md #6).

## Spam and untracked
- `spam` covers unsolicited (not wallet-sent) non-allowlisted token legs, zero-value poisoning and the pass-through. Rows are `pnl_excluded`. Base: 337 txs / 346 rows (eb12a1 moved to review). Sepolia: 71 / 735.
- `untracked` (architect) covers non-allowlisted legs in **wallet-sent** txs: `pnl_excluded`, no lot, no trade_group. The tracked legs keep their own category and are valued at their own price (USDC at par).
  Base: 46 txs carry untracked legs (53 rows). 29 of them are untracked-only, e.g. the wallet's own Aarcade Cartridge mints and signed junk sends. The rest keep a tracked category, e.g.
  **0x16d862…1a89: USDC -2000000 is `swap` (trade_group), LINK +242275798925376017 is `untracked`**. Sepolia: 2 txs / 2 rows.
  `wallet_sent_txs_with_non_allowlisted_token_legs` (deposit/withdrawal/income only) is now 0.

## Confidence labels
high = 1.0, medium = 0.6, low = 0.2 (`config.CONFIDENCE`). A label column sits next to every confidence number (migration 006):
`ledger_entry.price_confidence_label`, `price_point.confidence_label`, `fifo_lot.basis_confidence_label`, `lot_disposal.proceeds_confidence_label`.
In P2 the labels set are bridge_in lots (high) and manual basis (low).

## Schema (migration 006, rollback in migrations/rollback/)
`ledger_entry.category` gains `untracked` and `bridge_in`, plus the label columns above. `migrations/rollback/005_down.sql` and `006_down.sql` are the rollback SQL.

## Schema (migration 005)
- `ledger_entry.category` (the "tx_class": text + CHECK, not a PG enum) gains escrow_out, escrow_return, spam and migration_in.
- `ledger_entry` gains `location`, `escrow_ref` and `pnl_excluded`. The unique key now includes location and category.
- `fifo_lot` and `lot_disposal` did not exist yet. They were created with the DESIGN §3 columns plus `basis_status`, `chain_origin`, `escrow_ref` and `payment_for`. `basis_usdc` and `cost_usdc` are nullable for pending basis.
- `manual_basis` was added.
