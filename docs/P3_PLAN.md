# P3 plan: pricing (DESIGN v1.2 §2, §4 P3, §8)

Branch `p3-pricing`, cut from `p2.1-fake-gotchi-cards` @ ef9b36c (main @ 19754c6 does not contain PRs #2/#3/#4); PR stacked on PR #4.
Design source: DESIGN.md **v1.2** exists only in `/workspace/cryptoPnL` (box, uncommitted); every repo branch carries v1.0 or older. P3 follows v1.2.

## Done when (DESIGN §4 P3; all three, with command output cited in P3_RESULTS.md)
1. Every fungible asset (tracked: native ETH, WETH, USDC, cbBTC, GHST, FUD, FOMO, ALPHA, KEK, GLTR) is priced at 20 sampled blocks.
2. DEX prices are within ±3% of API prices wherever both exist.
3. Every ledger entry has a price or a flag (`price_usdc IS NOT NULL OR price_flag IS NOT NULL` = 100%).

## Steps (one small commit each, pushed)
0. This plan.
1. **Host-level HyperSync lock (first code commit, pushed before any backfill).** `cryptopnl/hostlimit.py`: `flock` on a fixed path
   (`HYPERSYNC_LOCK_PATH`, default `~/.cache/cryptopnl/hypersync.lock`) guarding a shared sliding-window log next to it; at most
   `HYPERSYNC_RPM` (5) request starts in any 60 s window across **all processes on the host**. Every HyperSync caller (sources.py, verify
   scripts) uses it in place of the per-process Limiter. Test: two concurrent OS processes on a shared lock with a scaled window
   (5 per 2 s) record their start times; every sliding window holds ≤ 5. Plus a real-parameter check that the 6th start waits for the window.
2. **Migration 007 (+ `migrations/rollback/007_down.sql`).** `ledger_entry.price_flag` (text, CHECK list), `ledger_entry.tx_index`,
   `asset.decimals` filled for tracked fungibles, `price_point.confidence_label` already exists; `price_point` gets `pool`/`detail`.
   No `ON DELETE CASCADE` added on user data (manual_basis stays FK-free of cascades).
3. **Pricer (`cryptopnl/pricing.py`)**, resolution order of §2:
   - *numeraire:* native Base USDC 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 = 1, source `numeraire`, high (architect, KNOWN_GAPS #16).
     Only that address. USDbC / any bridged or wrapped USDC never gets par (pool price or flag). P2's `par` label becomes `numeraire`.
   - *trade:* swap legs in one trade_group with a priceable counter-leg: ratio × counter price (USDC counter → ratio). Untracked or spam
     counter-legs are never used (§8): the tracked leg is priced from its own DEX/API price at that block (closes KNOWN_GAPS #15).
   - *DEX at block (archive RPC, read-only, 1 req/s burst 3):* WETH and cbBTC = Uni V3 0.05% USDC pool `slot0` at the tx block (§2 v0.5).
     GHST/alchemica/GLTR: §2 names Envio-indexed Aerodrome swaps, but Envio stacks are off-limits for this task, so the §2 general rule is
     used instead: Aerodrome/Uni pool state (`getReserves` / `slot0`) at the block, routed via WETH where there is no direct USDC pool.
     Pools found by on-chain factory reads (Q3); pools under a liquidity floor are rejected (floor value = open question).
   - *API fallback:* DefiLlama `coins.llama.fi/prices/historical/{ts}/base:{addr}` (free, no key). CoinGecko only if a free key is set
     (`COINGECKO_API_KEY`, optional, names only in `.env.example`).
   - native ETH = WETH price. Results cached in `price_point` (asset, block, source).
4. **Ledger pricing pass (`cryptopnl price --chain`)**: idempotent; fills price_usdc/source/confidence(+label)/price_id or `price_flag`:
   `spam`, `untracked` (pnl_excluded, never priced), `pending_basis` (migration_in: price NULL, P4 excludes it from mark and basis),
   `nft_no_trade` (NFT leg with no trade-implied price; NFT marks follow §5 Q8, which is open), `no_price` (fungible with no source; never invented).
   NFT buy/sale legs get trade-implied value from the payment leg (cost basis rule of §2).
5. **Tx order within a block by tx index.** `tx_payload` keeps HyperSync `transaction_index` for new ingests; existing rows get it from
   RPC `eth_getTransactionByHash` (read-only) only where a block holds ≥ 2 wallet txs; classify orders by (block, tx_index, log_index).
6. **Pass test `scripts/p3_test.sh <chain>`** (nohup; RPC + DefiLlama only, zero HyperSync): 20 blocks sampled across the ledger range
   (fixed seed), every fungible asset priced at each, DEX vs API deviation table, coverage query. Evidence in `docs/evidence/p3_*`.
7. Docs: P3_RESULTS.md, KNOWN_GAPS #15/#16 resolved (#16 cites the architect's ruling), P6 note (Polygon native USDC = numeraire,
   USDC.e = pool price).

## Test commands
- Unit (offline, local Postgres): `CRYPTOPNL_DSN=postgresql:///cryptopnl_unit_p3 ENVIO_API_TOKEN=x .venv/bin/python -m unittest discover tests`
- Pass test: `createdb -T cryptopnl_p11s_base cryptopnl_p3_base` (local copy of the P2.1 Base ledger, no re-ingest), then
  `CRYPTOPNL_DSN=postgresql:///cryptopnl_p3_base nohup scripts/p3_test.sh 8453 > logs/p3_base.log 2>&1 &`

## Rollback
- Schema: `psql -f migrations/rollback/007_down.sql` and delete the `007_p3_pricing.sql` row from schema_migrations.
- Data: `cryptopnl price` only writes price columns / price_point; `classify` rebuilds the ledger from raw_event. The pass test runs on a
  dropped-able copy (`dropdb cryptopnl_p3_base`); the P2 evidence DB `cryptopnl_p11s_base` is never written.
- Code: revert the branch commits (no force-push); nothing merges without review.

## Constraints honoured
Free sources only; read-only on chain; secrets by env name (abra), never printed; nohup for long jobs; stop on a 429 storm;
no home infra / live subgraphs / Envio stacks touched; abra-agent not restarted; no force-push, no merge.
