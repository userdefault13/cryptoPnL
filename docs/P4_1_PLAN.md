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
