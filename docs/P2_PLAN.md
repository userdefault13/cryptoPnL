# P2 plan: ledger and classification (DESIGN v1.1 §3, §4)

**Spec (§4 P2):** turn raw events into `ledger_entry`, including swaps, Baazaar/GBM sales, internal transfers and gas.
**Done when:** >98% of the wallet's txs are classified, the rest are in a review queue, and 10 hand-checked txs match explorer views.

Data reality (Base test wallet, P1.1 DB, measured): 499 txs carry wallet-touching logs (erc20 in 328 / out 194, erc721 in 113 / out 2,
erc1155 in 72); market events appear in 48 of them (BidPlaced 23, ItemClaimed 18, ERC1155ExecutedListing 6, BuyOrderExecute 1).
HyperSync tx query (1 request): 445 txs sent by the wallet, 28 sent to it (value, gas_used, effective_gas_price, l1_fee, status).
None of the 20 wearable-parent txs is the wallet's own (earlier gotchi owners) -> not wallet txs.

## Steps (commit + push after each)
1. `net.post_json` retries dropped connections (done, 61d5c97).
2. **Tx-level ingest:** `HyperSyncWalletTxs` (transactions from/to wallet; field_selection value, gas_used, effective_gas_price,
   l1_fee, status, input selector) -> `raw_event` kind `tx`, `log_index = -1` (DESIGN §3), source `hypersync_tx`, own cursor,
   reorg-rewound with the rest. <= 7/min shared limiter.
3. **Migration 004:** `price_point` (FK target, empty until P3), `ledger_entry` per §3 (price columns NULL until P3; `qty` in raw
   token units, decimals resolved in P3), `review_queue(chain_id, tx_hash, reason, detail, created_at)`.
4. **Classifier `cryptopnl/classify.py`** (deterministic rules, no models). Per wallet tx, legs = wallet-touching transfers + native
   value + gas. Rules, first match wins:
   - `fee`: gas leg (native ETH, qty = -(gas_used*effective_gas_price + l1_fee)) for every tx sent by the wallet (incl. failed txs).
   - `auction`: tx contains GBM market events (BidPlaced / ItemClaimed / BoughtNow) -> wallet legs in that tx.
   - `nft_buy` / `nft_sale`: Baazaar ExecutedListing / BuyOrderExecuted in tx, or NFT in + fungible out (buy) / NFT out + fungible in (sale).
   - `swap`: fungible out + different fungible in, no NFT legs (one `trade_group`).
   - `transfer_internal`: counterparty is another wallet in the same `wallet_group`; wearable custody (P1.1) stays custody.
   - `income`: mint from 0x0 with no outgoing value (rewards/claims; valuation per Q6 is P4).
   - `deposit` / `withdrawal`: remaining single-direction transfers from/to an external address (incl. spam airdrops).
   - anything else (mixed directions not matching a rule, failed tx with transfers) -> `review_queue` with a reason.
5. **CLI:** `python -m cryptopnl classify --chain C` (idempotent: delete + rebuild per chain in one transaction) and
   `classify-report` (counts, % classified, review reasons) -> `docs/evidence/p2_classify_<chain>.json`.
6. **Unit tests** (synthetic, offline): one fixture per rule + review-queue path + idempotency.
7. **Hand check:** 10 txs stratified over categories; explorer data read-only (Blockscout API v2 / Basescan pages via WebFetch);
   compare per-tx wallet legs (asset, qty) + fee against `ledger_entry`; record both sides in `docs/evidence/p2_handcheck.md`.
8. Run on Base, then Sepolia (nohup), report; PR against main.

## Test command
`abra run cryptoPnL -- scripts/p2_test.sh <chain> <wallet>`: migrate -> ingest (logs + txs) -> classify x2 (identical
counts/checksum) -> report (classified share > 98% else FAIL) ; unit: `.venv/bin/python -m unittest discover tests`.

## Rollback
P2 only adds: migration 004 (new tables), a new raw_event kind `tx` (log_index -1), new modules. Rollback =
`DROP TABLE review_queue, ledger_entry, price_point; DELETE FROM raw_event WHERE kind='tx'; DELETE FROM sync_cursor WHERE source='hypersync_tx';`
plus reverting the branch; P1 tables/cursors are untouched.

## Open questions touching P2 (DESIGN §5): none block classification
- Q2 (same-group transfers keep basis): classifier labels `transfer_internal`; basis treatment is P4. Owner: user_default.
- Q6 (income valuation) and Q7 (gas capitalize vs expense): P2 records `income` and `fee` legs neutrally; treatment is P4. Owner: user_default.
