# P1 Raw ingest — plan (2026-10-16)

Basis: DESIGN.md v0.9 §1.2/§3/§4 P1, ENVIO_TOKEN_INDEXER.md v0.7 §3a/§5b/§5c. **No Goldsky (user_default, 2026-10-16): no S1b.**
Sources: **HyperSync** (all log history, per-wallet topic filter) + **free RPC** (base.drpc.org; Sepolia: sepolia.base.org) for safe head, block hashes, at-block balanceOf. AarcadeGh$t proxy = point lookups only (not used by raw ingest). Sources are pluggable (`cryptopnl/sources.py`).

## Steps
1. Migrations (`migrations/*.sql`, runner `python -m cryptopnl migrate`): wallet, asset, block, raw_event, sync_cursor (DESIGN §3 subset) + schema_migrations.
2. HyperSync wallet-log source: ERC20/721 `Transfer` (topic1|topic2 = wallet) and ERC1155 `TransferSingle/Batch` (topic2|topic3 = wallet), paged by `next_block`, token bucket **7 req/min** (no local throttle on MBP), exp. backoff on 429/5xx.
3. Ingest: scan `cursor+1 .. safe head` per (chain, wallet); `INSERT … ON CONFLICT DO NOTHING` on `(chain_id, tx_hash, log_index)`; store block hash/ts; advance `sync_cursor` with block hash.
4. Reorg: each run re-checks cursor hash + the 64 most recent stored blocks against RPC; on mismatch delete `raw_event`/`block` ≥ fork, rewind cursor, re-ingest.
5. Verify: balances from `raw_event` vs RPC `balanceOf` at ingest head + 3 sampled historical blocks, every wallet × asset (ERC20, ERC721 count, ERC1155 per id).
6. Order: Base Sepolia (84532) first, then Base (8453).

## Files
`migrations/001_init.sql`, `cryptopnl/{__init__,__main__,config,db,net,sources,ingest,verify}.py`, `scripts/p1_test.sh`.

## Test command
`abra run cryptoPnL -- scripts/p1_test.sh <chain_id> <wallet>` (abra project `cryptoPnL`: ENVIO_API_TOKEN, BASE_RPC_URL) → migrate, ingest ×2 (counts identical), verify balances, simulated reorg (tamper 3 latest blocks + cursor hash → rewind + re-ingest → counts/hashes restored), request/429 counters.

## Rollback
Local DB only: `dropdb cryptopnl_test` (own DB on Homebrew Postgres 16, not home infra/Envio). Code: delete branch `p1-raw-ingest`. Nothing on chain is written.

## Scope notes
- Native ETH and internal ETH not ingested (no traces; ENVIO §5c gap). Gas/receipts → P2.
- S1 marketplace ingest (Baazaar/GBM) cannot be bulk-ingested: proxy returns single rows, no Goldsky. Deferred; candidate: decode Baazaar/GBM diamond events from HyperSync logs.
- Test wallet: admin wallet <TEST_WALLET> (DESIGN has no static wallet list; wallets are dynamic §1.3).
