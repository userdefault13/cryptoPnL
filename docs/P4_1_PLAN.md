# P4.1 plan: unrecorded inflows (branch `p4.1-inflows`, off p4-fifo 938fe75; merged p4-fifo up to fc4c30a)

Separate from PR #8. Rulings: DESIGN §8 'P4 rulings 3' and 'P4 rulings 4'.

**'P4 rulings 4' as relayed by the CoS** (not yet in DESIGN.md on any origin branch at 17:21 PT; to be pulled when pushed):
- as_of_block defaults to the LAST ledger block, or a block user_default chooses.
- The P3 pricing step writes a mark for each held asset at that block, using the normal price order.
- A held asset with no valid mark is excluded from unrealized and counted, like unpriced NFTs.

## Gate (P4.1 done when all hold)
1. Every ledger row is at or before as_of_block and is reconciled (the independent ledger side, 0.01 USDC, per asset and in total).
2. 0 unexplained unrecorded-inflow gaps (`reconciliation.unexplained_gap` empty; 0 lots with `basis_origin=unrecorded_inflow`).
3. ETH and GHST engine open qty == the ledger's net qty.
4. Resolved gas disposals > 0.

## Steps
| # | Step | Writes | Files |
|---|---|---|---|
| 1 | **Source-fact tracing, READ-ONLY** (this commit): where the ETH (1.0956033 over 455 events, blocks 12795076–49402932) and GHST (652.63 from 20 pockets in the txs at 38141654 / 38622419 / 40216494) came from | none on chain or ledger; evidence files only | `scripts/p4_1_trace.py`, `docs/P4_1_SOURCES.md`, `docs/evidence/p4_1_*` |
| 2 | Ingest/classify design for the mechanisms found (architect ruling first): e.g. internal native transfers into the wallet, pocket (gotchi escrow) inflows | none until ruled | DESIGN §8, `cryptopnl/ingest.py`, `classify.py`, `config.py` |
| 3 | Ingest the missing rows on a COPY (`cryptopnl_p41_*`), new ledger md5 recorded | the copy only | migration if needed (+ rollback) |
| 4 | P3 pricing marks at as_of (rulings 4: LAST ledger block by default), held assets with no valid mark excluded + counted | the copy only | `pricing.py`, `p4.py` |
| 5 | Rerun `p4_test.sh` against the gate; P4_1_RESULTS.md | the copy only | `scripts/p4_test.sh` (gate checks), docs |

**Independent key test** (architect, rulings 4), added in step 2 before any engine change: a hand-ordered fixture (same block with several txs and tx_index NULL/set, log_index order across txs, entry ids) asserting `Entry.key()` and the sorted order equal the hand order, because the engine and reconcile share that key. File: `tests/test_entry_key.py`.

## Step 1 method and request budget (counted BEFORE running)
The source of truth is the chain, not the ledger. The canonical ledger (omarchywin `cryptopnl_p3_base`, md5 210a71d8…) needs the ledger PG, and that is blocked while omarchywin's abra is locked (with_ledger_pg.sh now uses abra only). Step 1 therefore uses:
- the wallet address (`0x2127aa7265d573aa467f1d73554d17890b872e76`, public);
- the 3 GHST tx hashes, from the MBP's older local copy (1252 rows, not canonical; identifiers only).

Where it runs: the MBP, with its own host locks (`~/.cache/cryptopnl/hypersync.lock`, `rpc.lock`), ENVIO_API_TOKEN by name from abra project cryptoPnL (`abra run cryptoPnL -k ENVIO_API_TOKEN`), RPC `https://base.drpc.org` (free, keyless). Every attempt is logged to `NET_REQLOG`.

(a) ETH: an EOA's balance changes only by top-level txs plus internal value transfers into it, so:
- **H1** HyperSync: all txs from/to the wallet, blocks 0–52911468 (value, gas_used, effective_gas_price, l1_fee, type, status) → the on-chain expected balance path without internal inflows.
- **R1** RPC `eth_getBalance` bisection over the wallet's tx blocks: actual minus expected at checkpoints; drill only into intervals with a surplus. Then one `eth_getBalance(b-1)` to tell "inside block b" from "between blocks".
- **H4** HyperSync logs naming the wallet in topic1/2/3 for any between-block interval with a surplus (1 request per interval).
- **R2** `debug_traceTransaction` (callTracer) on candidate txs only, to name the contract that sent the ETH and the mechanism.

(b) GHST:
- **H2** HyperSync: GHST Transfer logs to the wallet in the 3 txs → the 20 pocket addresses and amounts.
- **H3** HyperSync: every Transfer / TransferSingle log with a pocket address in topic1 or topic2 (any token contract), all blocks → each pocket's GHST source tx (mint, claim, other address).
- **R3** `eth_getTransactionByHash` on the source txs (to, selector) to name the mechanism.

| source | queries | expected requests | hard cap (stop and report) |
|---|---|---|---|
| HyperSync (5/min, 12 s gap) | H1 3–8 pages, H2 1–2, H3 2–6, H4 0–10 | 6–26 | **28** |
| RPC base.drpc.org (30/min, 1.5 s gap) | R1 60–300, R2 5–40, R3 3–30 | 68–370 | **370** |

Expected wall time: HyperSync ≤ 28 × 12 s ≈ 6 min; RPC ≤ 370 / 30 per min ≈ 13 min.

## Test command
- Step 1: `abra run cryptoPnL -k ENVIO_API_TOKEN -- env NET_REQLOG=logs/p4_1_reqlog.txt .venv/bin/python scripts/p4_1_trace.py` (read-only; prints request counts).
- Later steps: `scripts/with_ledger_pg.sh scripts/p4_test.sh 8453 <copy> cryptopnl_p4_*` against the gate, plus the full suite (`.venv/bin/python -m unittest discover -s tests -t .`).

## Rollback
- Step 1 writes nothing outside `docs/` and `logs/`: rollback = revert the commit.
- Steps 3–5 write only to a `cryptopnl_p41_*` copy (`dropdb` it). Any migration ships with `migrations/rollback/0NN_down.sql` and an up/down/up test. The canonical `cryptopnl_p3_base` and Envio PG 5439/5440 are never written.

## Step 1 revision (17:3x PT, before any further request)
- **HyperSync is blocked.** The first request (H2) returned **HTTP 403**: the ENVIO_API_TOKEN in the MBP's abra (`cryptoPnL`) is not accepted. The token P3 used is in omarchywin's abra, which is locked; it is not unlocked here (rule). HyperSync used: **1 request**. No HyperSync query is retried.
- **Keyless fallback for step 1, counted now:**

| source | queries | expected | hard cap |
|---|---|---|---|
| RPC base.drpc.org (30/min, 1.5 s gap) | R0 `eth_getTransactionReceipt` for the 3 GHST txs (3); R3 `eth_getLogs` GHST Transfer to/from the pockets, all blocks (2–20); R1 `eth_getBalance` spot checks (≤ 12); R2 `debug_traceTransaction` callTracer on each tx Blockscout lists as an internal ETH inflow (≤ 60) | 10–95 | **370** (unchanged) |
| Blockscout `base.blockscout.com/api` (free public explorer API, no key; own 1 req / 2 s pacing) | B1 `txlistinternal` for the wallet (1–3 pages); B2 `txlist` for the wallet (1–3 pages) | 2–6 | **10** |

  Blockscout only produces the candidate list. Every inflow reported in P4_1_SOURCES.md is confirmed from chain by RPC (`debug_traceTransaction` value into the wallet). An inflow Blockscout reports but RPC does not confirm is marked unconfirmed.
- **Revision 2** (before running): drpc's free tier rejects wide `eth_getLogs` ranges (HTTP 400, jsonrpc code 35), so R3 is dropped. Used so far: RPC 38 attempts (6 OK = the 3 receipts + 3 txs; 32 rejected getLogs, half of them repeated by a rerun because errors were not cached; now fixed). Replacement:
  - **B3** Blockscout `tokentx` (GHST only), one per pocket: **20**. Blockscout cap raised to **30**.
  - **R4** `eth_getTransactionByHash` per distinct pocket-source tx: ≤ 40, inside the RPC cap.

## P4.1 implementation round (architect review of step 1, 17:44 PT): request budget
Counted before each run; caps are hard stops. abra on omarchywin was **locked** at 17:44 / 17:49 / 17:58 PT (rechecked every few minutes,
never unlocked here), so the canonical run waits and everything below runs on the MBP's **non-canonical** copy `cryptopnl_p4_1_mbp`
(= `cryptopnl_p22_base` + migrations 009–015 + the 553 stored P3 price points of `cryptopnl_p3_base`).
- **I1 internal ETH ingest** (`python -m cryptopnl.internal_eth`, RPC 30/min, cap 40). *Not counted in this file before it ran* (cap set in
  the command only; noted here afterwards): expected 0–16 new (balances and step-1 traces are cached; the 16 wallet-sent 7702 self-calls are
  traced always). **Used: 14 new requests**, 160 cached, 0 errors.
- **P1 re-price after re-classify** (`cryptopnl price --seed-only`): stored points answer 507 of 542 (asset, block) pairs; the 35 others
  (alchemica / GHST blocks with no stored point) stay unpriced on this copy. **Expected RPC: 0.**
- **M1 marks at as_of** (`cryptopnl marks`, as_of = the copy's last ledger block 52112861): ETH (2–3 calls), GHST (routed, ≤ 6), each
  alchemica / GLTR held (dex then thin tier; no swap scan on the MBP → no_valid_mark, ≤ 6 each), USDC numeraire (0). **Expected ≤ 60, cap 80.**
- **Canonical (only once omarchywin's abra is unlocked):** name check of `cryptoPnL/CRYPTOPNL_LEDGER_PG_PASSWORD` (abra ls, names only);
  **H3** GHST Transfer logs into / out of the 20 pockets (HyperSync, 2–6 requests, cap 8); I1 on the canonical DB over the cache
  (new range 52112862–52911467: ≤ 120 RPC); P1 seeded from the canonical price_point (≤ 20); M1 at the canonical last block (≤ 60).
  Total canonical RPC cap 250.
- **Actuals (MBP, non-canonical, 18:00–18:08 PT):** P1 0 RPC (613 seed hits). M1 **12 + 12 = 24 RPC** (the second run re-checked the
  held rule after the any-location fix; marks are not cached), 0 errors, under the cap of 80. I1 re-run after the log_index fix: 0 new
  (174 cached). HyperSync this round: **0**. RPC this round total: **38** (14 + 24).

## Canonical round (abra unlocked, 20:03 PT): request budget (written before running)
- Name check (`XDG_RUNTIME_DIR` set, `abra ls cryptoPnL`, names only): **CRYPTOPNL_LEDGER_PG_PASSWORD is missing**; the project holds
  only `ENVIO_API_TOKEN`. The canonical run (ledger PG) is blocked; only H3 may run.
- **H3** `scripts/p4_1_ghst_pockets.py` (omarchywin worktree `~/dev/cryptoPnL-p41` at df0393d): one HyperSync query (Transfer in/out of
  the 20 pockets, all tokens, blocks 0–40216494, txs joined), paged. **Expected 1–4 requests, hard cap 8.** RPC 0.
- **Actual (20:04:54 PT): 1 HyperSync request, HTTP 403** (`base.hypersync.xyz/query`, attempt 1, no retry). The same abra token got
  HTTP 200 on 2026-10-24 17:21 PT (P3 run log `~/dev/cryptoPnL-p3/logs/net_requests_p3.log`). Stopped: a 403 is an auth/plan refusal,
  so retrying would only spend the cap. RPC 0. No ledger PG access.
- **Retry (CoS 20:18 PT), written before running.** Name check (exact-name filter, yes/no only): `cryptoPnL/CRYPTOPNL_LEDGER_PG_PASSWORD`
  **no**; `aavegotchi-envio-indexers/ENVIO_API_TOKEN` yes. Canonical run stays blocked. **H3** with the aavegotchi-envio-indexers token
  (free tier, host limiter 5/min + 12 s): **expected 1–4 requests, hard cap 7** (8 minus the 403 at 20:04). RPC 0.
  **Actual (20:18:49–20:19:15 PT): 1 HyperSync request, HTTP 200**, the whole range in one page (346 rows, 149 txs). RPC 0. Facts in
  P4_1_SOURCES.md §2b. Canonical run not started (ledger PG password missing).

## Rule 7 round (architect ruling (a) on pocket inflows, 20:21 PT): source choice and request budget (written before running)
Facts known for 0 requests (MBP copy, non-canonical): one wallet in the group (0x2127…2e76); 24 gotchis ever held on the Diamond
(wallet-scoped ERC721 legs, first at block 33205609); the gotchi_escrow cache is **empty** on the MBP copy (canonical has it), which is
why the 4 pocket txs sit in review there. The wallet's own lending txs (raw `tx` selectors): batchAddGotchiListing 42180165,
agreeGotchiLending 42190763 (wallet as borrower), claimAndEndGotchiLending 42750753, plus 16 EIP-7702 `execute` txs whose inner
calls are not stored. Every H3 deposit block (35315787–39595007) is **before** the first wallet listing tx.

**Source choice (cheapest correct):**
- **Historical owner at the deposit block:** the ledger's wallet-scoped ERC721 legs on the Diamond, replayed in classify order
  (`esc.gotchis`). 0 requests. Cross-check: one Multicall3 `aggregate` eth_call of `ownerOf` for the 24 gotchis at the first pocket
  inflow block.
- **Rental status at the deposit block:** lending events, not per-block eth_calls (per (gotchi, deposit block) eth_calls would cost
  roughly 150–350 RPC). A rental needs a listing; a listing needs a tx from the lender or a lending operator. So:
  HS1 = the wallet's txs to the Diamond with a lending selector or the 7702 `execute` selector (inputs plus their logs, JoinAll): this
  gives the listingIds (GotchiLendingAdd topic1) and shows whether any `setLendingOperator` / `batchSetLendingOperator` was ever sent.
  Listings that predate the window (carried over at migration) are caught by one Multicall3 eth_call of `getGotchiLendingIdByToken`
  plus `isAavegotchiLent` for the 24 gotchis at the first pocket inflow block (the same call as the owner cross-check).
  HS3 = the indexed lending events (GotchiLendingExecute / End / Cancel, topic1 = listingId) for those listingIds. That gives exact
  rental intervals. If HS1 shows a lending operator, stop and report, because an operator's listings would not show up in HS1.
- **Pocket legs:** one escrow-address resolution (Multicall3 of `gotchiEscrow` for the 24 gotchis at block 52911467) and HS2 = Transfer
  (ERC20/ERC721) plus TransferSingle/TransferBatch (ERC1155) into or out of the 24 escrows, blocks 0–52911467, txs and blocks joined.
  This supersedes H3 (20 pockets, up to 40216494) and covers the post-40216494 inflows.

**Budget:** HyperSync HS1 1–2, HS2 1–3, HS3 1 (0 if there are no listingIds): **expected 3–6, hard cap 7**, at 5/min with a 12 s gap
(aavegotchi-envio-indexers/ENVIO_API_TOKEN, by name). RPC: 2 Multicall3 eth_calls (escrows at 52911467; owner and lending at the
first inflow block): **expected 2, hard cap 6**, 30/min. Everything is cached in logs/p4_1_cache. The facts go to
docs/evidence/p4_1_pockets.json (chain data only). Canonical later reuses the cache (0 new requests unless the range grows).
- **Actual (20:29:58–20:33:15 PT):** HyperSync **4** (HS2, HS1, HS3, then HS2 again with `block.hash` added, which raw_event / block need;
  all HTTP 200), RPC **2** (R1, R2; HTTP 200). Under the caps of 7 / 6. Facts: 24 escrows; 381 pocket rows (320 in); 1 listing
  (gotchi 954, listing 1151: added 42180165, executed 42195157, ended 42750753); 0 lending-operator calls or events; nothing lent at the
  first inflow block (35315787); RPC ownerOf at that block equals the ledger replay for all 24 gotchis.
- **M1 re-run on the MBP copy after rule 7** (written before running): GHST is now held at as_of 52112861 (pocket income booked) and
  has no p3_mark row. `cryptopnl marks` re-marks every held asset: **expected 12–16 RPC, cap 30** (the earlier run was 12).
  **Actual (20:38 PT): 12 RPC**, 0 errors (GHST priced at as_of, dex_slot0). Rule 7 round total: HyperSync 4, RPC 14.
- **Canonical gate re-check (20:43 PT, exact-name filter, yes/no only):** `cryptoPnL/CRYPTOPNL_LEDGER_PG_PASSWORD` **no** (abra ls rc 0,
  unlocked; control `ENVIO_API_TOKEN` yes). Canonical run not started; stopped after pushing (per the 20:21 PT instruction).
- **Rule 7.4 check (20:45 PT, local evidence, 0 requests):** none of the 12 third-party ERC-20 contracts is canonical Base USDC or any
  other allowlisted token, so no leg moves from spam to pocket_deposit. **Key re-check (20:46 PT, yes/no only):**
  `cryptoPnL/CRYPTOPNL_LEDGER_PG_PASSWORD` **no** (abra ls rc 0). Stopped after pushing.
