# P2.2 results: Gotchiverse classification (DESIGN v1.3 §9)

Branch `p2.2-gotchiverse` (from main bed74e9). Spec: DESIGN.md **v1.3 §9** (box copy; the repo copy stays v1.0). Plan: docs/P2_2_PLAN.md.
Times are PDT (America/Los_Angeles). Test wallet redacted as `<TEST_WALLET>`.

## Runs
- `scripts/p2_2_test.sh` on DB copies `cryptopnl_p22_base` / `cryptopnl_p22_sep` (made with `createdb -T` from the P2.1 evidence DBs, which are not written).
  The runs were one chain at a time under nohup, with every HyperSync request going through the host lock. Code at 35e3dbf.
- Base 8453 (final run, 01:07–01:14): **99.517 % classified (825 / 829 wallet txs), 4 in review.** classify ×2: identical ledger
  (`ledger_md5` 2d0a5a16…, plus a script md5 over every ledger column d902e1a3…, both equal across the two runs).
  HyperSync: 14 requests; per minute 01:08 = 5, 01:09 = 2, 01:11 = 5, 01:12 = 2; busiest 60 s window = 5 (limit 5), 0 × 429.
- Sepolia 84532 (01:14–01:16): **100 % (126 / 126), 0 in review.** classify ×2 identical. The ledger is identical to P2.1, tx for tx
  (no GV config for Sepolia). HyperSync: 4 requests (01:15 = 2, 01:16 = 2), busiest window 2.
- Earlier Base run (01:00–01:05, at aab3d0f, before the borrower rule): 99.759 %, 2 in review. HyperSync 17 requests (5, 5, 2, 5 per minute); busiest window 5.
  The first attempt (00:55) failed on HyperSync HTTP 400 because `join_mode` was sent as an int; the JSON API takes `"JoinAll"`. That cost 1 request, with no retry storm.
- Evidence: `docs/evidence/p2_2_classify_<chain>.json`, `p2_2_gv_events_<chain>.txt`, `p2_2_hypersync_<chain>.txt`.

## What changed on Base vs P2.1 (tx-level diff of the ledgers)
| tx | P2.1 | P2.2 | rule |
|----|------|------|------|
| 0x8a8ceab861e1a6cb09994aac6fb13a74fd379a3a9498bed20970fa63e019953a (id 10, free) | income | craft (`craft:instant:free`) | R3 |
| 0x6ef4ef7d2862b60d487d0ee803fd1e1df3b7f2d4d41ce5759911da534018f601 (id 10, free) | income | craft | R3 |
| 0x90e41da7e707f14f566ceecaf94ee677ca86cd4d34a18d85909b05c0910e6a40 (id 145, free) | income | craft | R3 |
| 0x74f55051230b7873bff03e5118c642189b308c6f6c5de70ce1a82da940513092 (id 56, FUD/FOMO 35/30/30/5) | nft_buy | craft | R3 |
| 0x2d99c3469986d1da807289d330f8465c8bbeb4dd1bf4b883045dd84b6bf6dad4 (lend gotchi 954) | withdrawal | transfer_internal → `lent:<borrower>` | R8 |
| 0x64f6712df870fc6e8c088d74caa06e272c805739dd47419b72225dc0a3938270 (gotchi 954 back) | deposit | transfer_internal ← `lent:<borrower>` | R8 |
| 0x3a46db382e373e96997018dd9b1c996ff6e187667a48a71aa1d5cc1aed0b8442 (FUD depositERC20 → 0x728f0baf…) | withdrawal | review | R10 |
| 0xe7505b722e29f6587875c202de12960ef5816a33f8f64094554198684913d183 (borrow gotchi 10774, 0.2 GHST) | nft_buy | spend (GHST) + untracked (gotchi, `borrowed:<lender>`) | R8b |
| 0xec5e558bb1cd3a6f8f296111ba915cd3cc36746f126426ee3eabccbcee177e79 (borrowed gotchi returned) | withdrawal | untracked (gotchi back to the lender) | R8b |
No other Base tx changed. The migration-window MintInstallation(s)/MintTiles (blocks 33,999,872 / 34,000,138) stay migration_in.

## Rule 8b (borrower side of lending)
Accepted by the architect on 2026-10-17 (KNOWN_GAPS #19). The architect will add it to DESIGN §9 as rule 8b; the repo DESIGN.md is v1.0 and has no §9, so it is not edited here.
- The borrowed gotchi is not owned, so its legs are `untracked`, pnl_excluded, with no lot.
- Upfront GHST paid is `spend`.
- The revenue share received is `income` at the block's FMV. It is unpriced until P3 and flagged in the ref as `lending:borrower:revenue:fmv_unpriced`.
- Alchemica channeled while borrowing is `income` (R7).
- The real tuple event decodes as: word 1 = listing 1018, word 2 = lender, word 3 = borrower, word 4 = gotchi 10774, word 5 = upfront 0.2 GHST. This matches the transfers.

## Real-data checks (read-only: public RPC receipts and the stored P2.1 market events)
- R1 ERC721BuyOrderExecuted word 3 = gross price: checked on 0x44c038b5…12fe (block 34,705,014: word 3 = 20 GHST = 19.3 + 0.4 + 0.2 + 0.1 out of the diamond)
  and 0xcbcdf7dc…5676 (block 38,820,441: 1 GHST = 0.965 + 0.02 + 0.01 + 0.005).
- R1 ERC1155BuyOrderAdd (wallet): 0x2a01e94f343332b04f084ec6eb48328604716f7b835cc103f9bbff36f79b5cc8 → escrow_out `baazaar:buyorder:327`.
- R1 ExecutedToRecipient: 4 wallet txs (e.g. 0x17e48fcf…877c), wallet paid → nft_buy (correct; gift_in only when there is no payment).
- R2 Auction_BoughtNow: 0x271109cf41b7c4825b17f6940d5d1f67dd699214fa21dd01d87ced0830d885fd (block 42,210,865; not this wallet). topic2 = buyer; buyer GHST → GBM;
  Tile id 4 × 64 GBM → buyer; the seller is paid from GBM in the same tx with no ItemClaimed. The seller-side rule now also closes the escrow on BoughtNow.
- R3: the 4 crafts above (receipts: MintInstallation + TransferSingle 1, no queue). hypersync_gv pulled the full craft tx (8 FUD/FOMO transfers + 2 Installation logs).
- R8 lender side: gotchi 954 pair above (the decoded tuple borrower equals the gotchi's counterparty in both txs).

## Not verified on real data (synthetic tests only; see KNOWN_GAPS #20)
Upgrade queue/finalize, equip/unequip, destroy refund, bundle sale, GBM seller create/claim/cancel, gift_in, queued craft + QueueClaimed,
MintInstallations qty override, bounce gate and ERC721 buy-order placement 0x6feecbb5. Off-pattern legs on any of these go to review.

## Tests
`tests/test_gotchiverse.py`: 11 tests. Full suite: 53 tests, OK (1 skipped).
