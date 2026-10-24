# P2.2 results: Gotchiverse classification (DESIGN v1.3 §9)

Branch `p2.2-gotchiverse` (from main bed74e9). Spec: DESIGN.md **v1.3 §9** (architect copy at e2abb9e). Plan: docs/P2_2_PLAN.md.
Times are PDT (America/Los_Angeles). Test wallet redacted as `<TEST_WALLET>`.

## Runs (before the PR #5 review fixes; superseded by the final rerun in the review section below)
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
| 0x3a46db382e373e96997018dd9b1c996ff6e187667a48a71aa1d5cc1aed0b8442 (FUD depositERC20 → 0x728f0baf…) | withdrawal | transfer_internal → `pocket:3033` | pocket |
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

## PR #5 review (architect: CHANGES requested at 4a3426b), fixes at 4b6c746..99fe329
DESIGN.md in the repo is now the architect's v1.3, copied verbatim (e2abb9e, sha256 03675eb3…). All evidence below is read-only.
- **B1 buy-now double count:** auction ids are de-duplicated, because real 0x271109cf… (auction 5637) emits both Auction_BoughtNow and Auction_ItemClaimed.
  The seller-paid-by-buy-now and buyer tests now use that shape (both events).
- **B2 batch crafts:** batchCraftInstallations 0xe9332638 (Installation diamond) and batchCraftTiles 0xfdc6d919 (Tile diamond) were added, plus the claim selectors claimInstallations 0x763b948a /
  claimTiles 0xa185cc01 and reduceCraftTime 0xe0d20147. All are live: DiamondLoupe `facetAddress(bytes4)` eth_call on Base returns facets 0x6eab691f… / 0xc4f58280…,
  and the cross-checks return 0x0 (e.g. 0xfdc6d919 on the Installation diamond). openchain gives the names. Free batch crafts → `craft` (`craft:instant:free`), not income.
- **B3 queue refs:** `craft:queue:<contract>:<id>` per leg. A claim takes the id from MintInstallation / MintTile data (owner = wallet, type = token id) among that
  diamond's QueueClaimed ids. Several queues in one craft tx → a `;`-joined ref (P4 splits the cost). Tests cover Installation q7 vs Tile q7 and one claim covering q7 + q8.
- **R7 revenue claims by the borrower/operator:** an ingest selection pulls those txs. The lender comes from the tuple decode, not wallet topics. These are booked as lender income at the block's FMV, **confirmed by the architect on 2026-10-17** (the price comes in P3).
- **reduceCraftTime:** GLTR burnFrom → 0x0 is accepted as craft cost and lands in `craft_pending` under the queue's ref.
- **Pocket (confirmed):** custody at `pocket:<gotchiId>`; see KNOWN_GAPS #18. `gotchiEscrow(3033)` = 0x728f0baf… by RPC.
- **Quantity:** the override is removed. Per (contract, id), the wallet's minted amounts must match MintInstallations/MintTiles for owner = wallet (multiset); a mismatch → review.
- **Migration 008:** wrapped in BEGIN/COMMIT, with the new `gotchi_escrow` table. Migrate → rollback round trip checked on a scratch DB.
- **Nits:** bounce-gate updates (EventPriorityAndDurationUpdated, GLTR → 0xFFfF) → `spend` (`bounce:event:<id>:update`). Parcels are cleared when a parcel leaves (an escrow_out to GBM keeps the bundle).
  The upgrade queue index is carried (KNOWN_GAPS #23). Pool add-liquidity is classified (KNOWN_GAPS #25).
- **#27 mixed instant + queued craft:** the split rule uses on-chain type costs (KNOWN_GAPS #27), with review as the fallback. Tests cover an exact split, a mismatch and a missing cost going to review,
  a free type getting 0, and reduceCraftTime GLTR staying with its queue.
- **Unit tests (before #27):** 64 OK (1 skipped), with 22 in tests/test_gotchiverse.py. Run on the box with a local Postgres 17 and Python 3.13.
- **Base / Sepolia rerun (final, code at 34478e6, builder Mac, `scripts/p2_2_rerun.sh` under nohup, 02:10–02:28 PDT).** Each chain ran on a fresh copy
  (`cryptopnl_p22_{base,sep}` re-made from the P2.1 DBs) through `p2_2_test.sh` and then `p2_test.sh`. Every HyperSync request went through the host lock. 0 × HyperSync 429.
  | chain / pass | classified | review | ledger md5 (classify #1 = #2) | HyperSync busiest 60 s window |
  |---|---|---|---|---|
  | Base P2.2 (02:10) | **99.397 % (824 / 829)** | 5 | 96bab9e4… = 96bab9e4… (script md5 over every column fc6c3503… = fc6c3503…), 1,308 rows | 5 (ending 02:11:27), limit 5 |
  | Base P2 (02:16) | 99.397 % (824 / 829) | 5 | 96bab9e4… = 96bab9e4… | 5 (ending 02:18:21) |
  | Sepolia P2.2 (02:21) | **100 % (126 / 126)** | 0 | f4a81e5d… = f4a81e5d… (script md5 9f9beb2d… = 9f9beb2d…), 802 rows | 2 (ending 02:22:22) |
  | Sepolia P2 (02:24) | 100 % (126 / 126) | 0 | f4a81e5d… = f4a81e5d… | 2 (ending 02:26:16) |
  The Base P2.2 pass logged 1 RPC 429, absorbed by the backoff (not a storm), and 1 HyperSync connection error retried once (conn_retries 1, not a 429).
  Base review (5):
  - 4 × the Aerodrome FUD/GHST pool 0xeae2fb93…, which per KNOWN_GAPS #25 goes to review unless it is a plain add-liquidity. All 4 were classified in P2.1. **Architect decision needed:**
    - 0x374fdd859265e769db2f88c13a7b7557975eb4c1f47817192cb11db10191778e and 0x88f750fc5e81c3cf4b18f2e69c2f956253c4b6c5c861a40e13639d73aaf87a00 each swap 3 GHST → ~39,000 FUD against the pool (P2.1: swap).
    - 0xa51f0359ee945a1c7a004cb02f360a31be5d2528a2183bfd4b8c96071badc31a sends 3 USDC to 0x4e392fbf… and receives ~1.24 M (18-decimal units) of a token from the pool, a multi-hop swap (P2.1: swap).
    - 0x061ba2330f9e5b904c243f2be68fbec255c42932b52da1399854375b083196c8 is a deposit of 100 pool LP tokens to 0xab449dca…, selector 0xe2bbb158, a GLTR staking farm deposit (P2.1: untracked).
  - 1 × 0xccbfe04a6920793f7000b61d74e0da342e65252efe3e73170ec2f751c5bc58c0: DEX router, native leg not indexed (internal-ETH gap, as in P2.1).
  Resolved vs earlier runs: 0x3a46… (FUD depositERC20 → gotchi 3033's escrow) is now `transfer_internal` → `pocket:3033`. The R8b borrower pair is classified.
- **Regression found by the first rerun and fixed (34478e6):** the first rerun at eb5b88f (01:45–02:04, log kept on the Mac as `logs/p2_2_rerun_1.log`) gave Base 99.276 % (823 / 829, 6 in review), with identical md5s (cfaaa724…) and busiest windows 5/5/2/2.
  The 6th review row was 0x9248c703c1a5552360034fea42f2ca748883acf3c4f6a985c47afd1fccb1ded4, the refund of a cancelled GBM auction (0.5 GHST bid + 0.025 incentive).
  88498fc had added the AuctionCancelled topic, which switched off the P2.1 no-event fallback. The refund now matches the escrow of the auction cancelled in the tx (5613 = topic 1),
  which gives back the P2.1 result (escrow_return + income, `gbm:auction:5613`). There is a new test.
- **Unit tests:** 69 OK (1 skipped) at 34478e6 on the box (Postgres 17, Python 3.13). On the builder Mac (Python 3.9), 68 OK (1 skipped) at eb5b88f, before the regression test existed.
- Evidence: `docs/evidence/p2_2_{classify,gv_events,hypersync}_<chain>.*` (P2.2 pass) and `docs/evidence/p2_2_p2pass_{classify,hypersync}_<chain>.*` (P2 pass).

## Widened R10 (architect, 2026-10-22): KNOWN_GAPS #25 closed (e7fbf89)
- The rule is in `cryptopnl/gotchiverse.py` `r10_pool`, with config `GV.pricing_pools` and `GV.lp_gauges` (KNOWN_GAPS #25 has the full rule).
  `tests/test_gotchiverse.py::test_aerodrome_pool_widened_r10` covers add, direct swap, multi-hop, a non-allowlisted leg, stake, unstake + GLTR reward, a non-allowlisted reward,
  another LP token in the farm (normal rules), remove-liquidity, and → review for one-sided or LP-to-a-non-gauge.
- Unit suite: **69 OK (1 skipped)** on the builder Mac (Python 3.9, Postgres), at e7fbf89.
- **Classify-only check** (builder Mac, 22:11 PDT 2026-10-22). This was one run of `classify --chain 8453` on the 2026-10-17 `cryptopnl_p22_base` ingest (raw events from the 34478e6 rerun, no network).
  Result: **828 / 829 (99.879 %)**, review = 1 (0xccbfe04a…, the internal-ETH gap), ledger 1,315 rows, ledger_md5 8fc11f91d3a00533195c6e80ba9cfa3c.
  - 0x374fdd85… and 0x88f750fc…: `swap` (`pool_swap:<pool>`, −3 GHST / +~39,000 FUD).
  - 0xa51f0359…: `swap` (−3 USDC / +1,244,662.46 FUD).
  - 0x061ba233…: `untracked` (`gauge:0xab449dca…`).
  - 0x14bca6f0… stays `lp_add`; 0x89d68cf4… (another LP token into the farm) stays `untracked` under the normal rules.
  This is not the two-run md5 check. That needs the full rerun below, and the DB has since been re-made by the failed rerun.
- **Full HyperSync rerun: BLOCKED (2026-10-22 22:13–22:18 PDT).** `scripts/p2_2_rerun.sh` at e7fbf89 failed on the first HyperSync request of both Base passes with `SSL: WRONG_VERSION_NUMBER`.
  The run was stopped before Sepolia. Two failed connects in total, no queries answered, 0 × 429.
  Cause: on the builder Mac's network, port 443 of base(-sepolia).hypersync.xyz (84.32.129.x, the same answer from 1.1.1.1 / 8.8.8.8) is intercepted by a web filter.
  A plaintext probe returns `302 → https://www.safebrowse.io/warn.html?...`. Other HTTPS (GitHub) works.
  This needs the owner to allow hypersync.xyz in that filter (home network; not changed by the builder). The committed evidence files are still those of the 2026-10-17 34478e6 rerun.
  The failed-run logs are kept on the Mac in `logs/failed_2026-10-22/`.
- Note: branch `p2.2-r10b` / PR #6 (an earlier speculative R10b, 2026-10-19) used gauge = `transfer_internal` and had no remove-liquidity or rewards rules. It is superseded by this rule.
  Its uncommitted local doc edits on the Mac (an "ack 2026-10-20" for gauge = `transfer_internal`) are saved in `git stash` on the Mac and not committed.

## Full rerun on omarchywin, 2026-10-23 20:18–20:36 PT, at 394533f (host limiter fix 19d0867)
Log: `logs/p2_2_rerun.log` (not committed). Evidence: `docs/evidence/p2_2_*`.

| Pass | classified / total | review | ledger md5 (classify #1 = #2) | HyperSync requests | busiest 60 s window | 429s | script result |
|---|---|---|---|---|---|---|---|
| Base 8453 P2.2 | 833 / 834 (99.88%) | 1 | 6b00ec3c509df6309bd7a65956c1eb0a (report c41ee59ece07e4bf45bdf0a9dda14ec8, review e7de420e6883071793eb2790cd85b3af) | 18 | 5 (ending 20:19:48 PT) | **1** (first ingest: 13 requests, 12 ok) | PASS |
| Base 8453 P2 | 833 / 834 (99.88%) | 1 | report c41ee59ece07e4bf45bdf0a9dda14ec8 | 10 | 5 (ending 20:26:11 PT) | 0 | PASS |
| Sepolia 84532 P2.2 | 126 / 126 (100.0%) | 0 | 9f9beb2dd9da4aafd78cbfde889beec5 (report f4a81e5d4948f29677aa7db4de84d43f) | 4 | 2 (ending 20:30:21 PT) | 0 | PASS |
| Sepolia 84532 P2 | 126 / 126 (100.0%) | 0 | report f4a81e5d4948f29677aa7db4de84d43f | 2 | 2 (ending 20:34:12 PT) | 0 | PASS |

- Base review queue: `0xccbfe04a6920793f7000b61d74e0da342e65252efe3e73170ec2f751c5bc58c0` ("DEX router, fungible out only: native leg not indexed (internal ETH gap)"). Sepolia: none.
- Window bar met on every pass (≤ 5; the 10:02 run had 6). **Zero-429 bar NOT met: Base P2.2 had 1 × 429** (retried inside the window; the window stayed at 5). Status: FAIL on the 429 criterion, pending CoS/architect.
- Unit suite: 75 tests OK (1 skipped) on cryptopnl_unit22.
