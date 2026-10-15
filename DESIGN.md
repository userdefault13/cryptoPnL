# cryptoPnL: Design Document (v0.6, draft for approval)

Owner: user_default · Repo: github.com/userdefault13/cryptoPnL (empty, `main`) · Status: **design only, no build until approved**

Changelog: v0.6 (2026-10-15): The Envio indexer is hosted on **omarchywin** (Tailscale 100.72.80.69, 6.0 GiB RAM available, 1.8 TB free disk, Docker 29.7.2), not the M1. It uses the M1's shared HyperSync throttle and the existing proxy over Tailscale. See ENVIO_TOKEN_INDEXER.md §5a.
Changelog: v0.5 (2026-10-15): Wallets are dynamic (connected via SIWE or connect-only, or typed in manually with checksum/ENS/Basename checks), stored with `source` and grouped by user/session, with an on-demand backfill per added address (hybrid indexing, ENVIO_TOKEN_INDEXER §3a). Privacy rules added. WETH/cbBTC are priced by `slot0` at the tx block.
Changelog: v0.4 (2026-10-15): Added the [ENVIO_TOKEN_INDEXER.md](ENVIO_TOKEN_INDEXER.md) design. A Base-first Envio indexer (`cryptopnl-tokens-base`, exposed through the aarcade-subgraph-api proxy) replaces the RPC/Etherscan transfer and swap backfill for the tracked tokens (WETH/ETH, cbBTC, GHST, FUD, FOMO, ALPHA, KEK, GLTR). GHST and alchemica prices come from Aerodrome pools.
Changelog: v0.3 (2026-10-14): Source 1 is now the self-hosted AarcadeGh$t subgraphs, with the public Goldsky subgraphs as fallback. RPC logs and Etherscan v2 are core. No subgraph time-travel. Subgraph events are joined to receipts for reorg safety. Rate limiter and pagination added. P0/P1 and the open questions updated.
Changelog: v0.2 (2026-10-14): POB/S is now defined as point-of-buy / point-of-sell USDC pricing (Q1 resolved). Pricing section made explicit about the tx-time price for both legs. `basis_usdc` and `proceeds_usdc` now carry price_source and confidence.

## 0. Goals and assumptions
- Track realized and unrealized PnL for user_default's wallets, in **USDC**, using **FIFO** cost basis per (wallet-group, asset).
- Chain: **Base (8453)**. Aavegotchi's canonical home moved to Base on 2025-07-25 (Aavegotchi wiki); Polygon history is out of scope for v1 (see open questions).
- Assets: GHST, alchemica (FUD/FOMO/ALPHA/KEK), stablecoins, ETH/WETH, other ERC20s, and Aavegotchi NFTs (gotchis, portals = ERC721; wearables/items, installations/tiles = ERC1155; parcels = ERC721).
- **POB/S = point of buy / point of sell** (confirmed by user_default). Every buy and every sell is valued in USDC at the moment it happens (its tx block and timestamp). That value sets cost basis on buys and proceeds on sells, and FIFO matches buys to sells.

## 1. Data sources and ingestion
### 1.1 Sources
| # | Source | Used for | Notes |
|---|--------|----------|-------|
| **S1 (primary)** | **AarcadeGh$t self-hosted subgraphs** `https://subgraph.aarcadeghst.com/subgraphs/name/<name>` (Tailscale `100.100.99.27:8787`). Names: `aavegotchi-gbm-baazaar-base`, `aavegotchi-core-base`, `aavegotchi-alchemica-base` | Baazaar: `ERC721Listing`, `ERC1155Listing`, `ERC1155Purchase`, `ERC721BuyOrder`, `ERC1155BuyOrder`, `ERC1155BuyOrderExecution`. GBM: `Auction`, `Bid`, `Auction_BidPlaced`, `Auction_BoughtNow`, `Auction_ItemClaimed` | Base 8453 from block 33201946, about 15s behind head. Auth enforced with `Authorization: Bearer <key>` (portal-issued key, read from env/secret store and never committed). About 60 req/min, `first <= 1000`, query depth about 8, read-only. Envio/Hasura backed: **no generic ERC20/721/1155 transfer entities, no swap or price entities, and `block:{number}` is silently ignored (no history)**. The cartridge subgraphs are stale and **excluded** |
| S1b (fallback) | Public Aavegotchi Goldsky subgraphs: `.../project_cmh3flagm0001r4p25foufjtt/subgraphs/aavegotchi-core-base/prod/gn` and `.../aavegotchi-gbm-baazaar-base/prod/gn` | Same marketplace data when S1 is down or lagging | No auth, 50 req per 10s |
| **S2 (core)** | **Base JSON-RPC** (archive): `eth_getLogs` for ERC20 `Transfer`, ERC721 `Transfer`, ERC1155 `TransferSingle/Batch`, DEX `Swap`. Also receipts, blocks, and `balanceOf`/`eth_call` at a block | Ground truth for every movement, gas, block hash and timestamp, plus historical balances and pool state at a block | Required. Provider pending (Q4) |
| **S3 (core)** | **Etherscan API v2** (`chainid=8453`): `txlist`, `txlistinternal`, `tokentx`, `tokennfttx`, `token1155tx` | Wallet history discovery/backfill, and internal ETH transfers | Required. Key pending (Q4) |
| S4 | DEX pools on Base: Uni V3 WETH/USDC & cbBTC/USDC, and Aerodrome GHST/WETH and alchemica/GHST (verified, ENVIO_TOKEN_INDEXER.md §1.2) | Swap classification and at-block prices | Via the Envio indexer |
| S5 | DefiLlama / CoinGecko historical prices | Price fallback (§2) | |

**v0.6:** the indexer runs on omarchywin, exposed via the M1 proxy (ENVIO_TOKEN_INDEXER §5a). **v0.4:** for the tracked tokens, ERC20 Transfer and DEX Swap backfill come from the Envio indexer `cryptopnl-tokens-base` (see ENVIO_TOKEN_INDEXER.md §7). S2/S3 remain for receipts, gas, at-block reads, untracked tokens and internal ETH.

**Rules:** (a) **never use subgraph time-travel.** Historical balances come from RPC `balanceOf` (or `eth_getBalance`) at the target block. (b) Each subgraph event is **joined to its tx receipt by tx hash** (S2) to get block number, block hash, log index and timestamp. Reorg safety comes from the receipt, never from the subgraph. (c) Nothing here indexes Polygon. Polygon history, if needed, can only come from RPC plus explorer (Q5).

### 1.3 Wallets: connected and manual (v0.5)
- **Connected:** a wallet-connect button (injected / WalletConnect / Coinbase Wallet). **Connect-only** is enough for read-only viewing. **SIWE (EIP-4361)** sign-in is required to *own* a wallet group (save it, name it, and see it on return). SIWE nonce is single-use with a 10-minute expiry, the domain/chainId (8453) are bound, and smart-wallet signatures are verified via EIP-1271/6492.
- **Manual:** an address field that accepts `0x…` (validated with the EIP-55 checksum; all-lowercase is accepted and normalized, mixed-case with a bad checksum is rejected) or a name. **ENS** is resolved on Ethereum mainnet and **Basenames** (`*.base.eth`) on Base via their resolvers. The resolved address is shown for confirmation, and the name is stored as a label. Reverse resolution is display-only.
- **Storage:** `wallet` gains `source text CHECK (source IN ('connected','manual'))`, `owner_kind ('user','session')`, `owner_id` (user id after SIWE, else an anonymous session id), `ens_name`, `added_at`, and `verified bool` (true only when a SIWE signature proves control). `wallet_group` becomes `(owner_kind, owner_id, group_name)`. A session-owned group is migrated to the user on SIWE login. The same address may appear in several owners' groups.
- **On add → on-demand backfill:** enqueue the job in ENVIO_TOKEN_INDEXER §3a. GHST/alchemica/GLTR history is read immediately from the Envio stack (`cryptopnl-tokens-base`). USDC/WETH/cbBTC/ETH come via the Etherscan quick pull, then the per-address HyperSync job. The **AarcadeGh$t subgraph queries stay per address** (Baazaar/GBM by seller/buyer/bidder = address).
- **Privacy:** addresses are public on-chain data, but *who looks at which address* is not. Rules: don't write raw addresses to application/access logs (log a salted hash or a short id; no addresses in URLs/query strings, use POST bodies or opaque wallet ids). Send no addresses to third-party analytics. Anonymous session groups expire after 30 days, deletable on request; SIWE-owned groups are deletable by the owner. Outbound queries carry addresses only to the data sources that need them (HyperSync, Etherscan, AarcadeGh$t, and the RPC for ENS), never to price APIs. Cached on-chain data is keyed by address (shared and public), while the owner→address mapping lives only in `wallet`.

### 1.2 Ingestion pipeline
1. **Backfill:** for each wallet, pull explorer history (S4) to find every tx hash and block range. Then fetch each receipt over RPC (S3) and decode all logs. Receipts are the source of truth.
2. **Incremental:** a cursor per source (`sync_cursor`: source, wallet, last_block, last_block_hash). RPC: each run scans `last_block+1 .. head-CONFIRMATIONS` with `eth_getLogs`, filtered on topic = wallet address (topics 1 and 2 for ERC20/721, topics 2 and 3 for 1155) and chunked by block range. Subgraph: filter entities by wallet (seller/buyer/bidder) plus a monotonic field (block number or timestamp field if exposed, else `id`) with `where: {field_gt: cursor}`, `orderBy` on that field and `first: 1000`. Then enrich each row through its receipt.
   - **Rate limiter and pagination in the ingest worker:** a token bucket per source (S1 ≤ 1 req/s, about 60/min; S1b 5 req/s; Etherscan per its plan tier; RPC per provider), exponential backoff with jitter on 429/5xx, cursor pagination capped at `first ≤ 1000`, and queries kept under depth 8. Fail over from S1 to S1b when S1 fails or lags by more than N minutes.
3. **Idempotency:** the natural key for raw events is `(chain_id, tx_hash, log_index)`, written with `INSERT ... ON CONFLICT DO NOTHING`. Derived tables (lots, disposals, PnL) are **recomputable projections**, rebuilt per (wallet_group, asset) from the earliest affected event.
4. **Reorgs:** finalize only at `head - 64` blocks. Base is an OP-stack L2 and `finalized`/`safe` block tags are available, so prefer the `safe` tag. Store `block_hash` on every row. On each run, re-check the stored hash for the last N blocks. On a mismatch, delete raw rows `>= fork_block`, rewind the cursor, re-ingest, and recompute the affected projections.
5. **Classification (raw → `ledger_entry`):** group logs by tx. Patterns: swap (out asset A, in asset B, same tx, DEX router/pool involved), Baazaar buy/sell (NFT in or out plus GHST the other way; sale price from S1), GBM auction win, transfer between own wallets (internal, not a disposal), deposit/withdrawal from outside, gas fee (ETH disposal), and channeling/claims (alchemica in at zero cost, i.e. income at fair market value; see Q6). Anything unclassified goes to a review queue.

## 2. Pricing (USDC): point of buy / point of sell
**Rule:** `price_usdc` is captured **at tx time (the tx's block and timestamp) for both legs** of every acquisition and disposal. It is stored on the `ledger_entry` (`price_usdc`, `price_source`, `price_confidence`). It is then frozen into `fifo_lot.basis_usdc` (point of buy) and `lot_disposal.proceeds_usdc` (point of sell), each with its own `*_price_source` and `*_confidence`. Realized PnL depends only on these stored tx-time values. It never reprices later. **Unrealized PnL** for open lots uses the **current** price (same resolution order, at head) against the stored `basis_usdc`.

Resolution order for `price(asset, tx_block)`:
1. **Trade-implied price:** if the counter-asset is USDC, use the execution ratio directly. If the counter-asset can be priced at that block (e.g. GHST or WETH), use ratio × that asset's price. Source = `trade`, highest confidence.
2. **On-chain DEX price at block:** (v0.5) **WETH and cbBTC:** RPC `slot0` of the Uni V3 0.05% USDC pool at the tx block, decided; those pools are not indexed. **GHST/alchemica:** Envio-indexed Aerodrome swaps/Sync at or before the block. General rule: read pool state (`slot0`/`observe` TWAP for Uniswap v3-style pools, reserves for v2/Aerodrome-style pools) at that block through archive RPC, or take the volume-weighted average of `Swap` logs in a ±N-block window. Route through WETH→USDC when there is no direct USDC pool. Reject pools with liquidity below a threshold.
3. **API fallback:** DefiLlama `coins.llama.fi/prices/historical/{ts}/base:{address}` (free, keyed by chain:address) or CoinGecko `/coins/{id}/history` and `/market_chart/range` (GHST is listed; alchemica coverage on Base is unverified, Q3).
4. **Stablecoins:** USDC = 1.0 by definition. Other stablecoins use the API price.
- **NFTs:** cost basis = the GHST or USDC actually paid, converted to USDC at the trade block. Unrealized value comes from Baazaar/GBM sale history (S1/S2): the last sale of the same item (1155 wearables, by erc1155TypeId), and for 721 gotchis, a floor or comparable-sales heuristic (median of the last K sales in the same rarity/BRS band, with listing floor as an optional input). Flag NFT marks as low confidence.
- **Cache:** every resolved price is stored in `price_point` keyed by (asset, block) plus a timestamp, with its source and confidence. Lookups snap to the nearest cached block within a tolerance.

## 3. Schema (Postgres)
```sql
CREATE TABLE wallet (id serial PRIMARY KEY, chain_id int NOT NULL, address bytea NOT NULL,
  label text, wallet_group text NOT NULL DEFAULT 'default', UNIQUE(chain_id,address));

CREATE TABLE asset (id serial PRIMARY KEY, chain_id int NOT NULL, contract bytea,  -- NULL = native ETH
  standard text NOT NULL CHECK (standard IN ('native','erc20','erc721','erc1155')),
  token_id numeric,            -- NULL for fungibles; 721 id or 1155 type id
  symbol text, decimals int, coingecko_id text, is_stable bool DEFAULT false,
  UNIQUE(chain_id, contract, token_id));

CREATE TABLE block (chain_id int, number bigint, hash bytea NOT NULL, ts timestamptz NOT NULL,
  PRIMARY KEY(chain_id, number));

CREATE TABLE raw_event (chain_id int, tx_hash bytea, log_index int,  -- -1 for tx-level (gas, native)
  block_number bigint NOT NULL, block_hash bytea NOT NULL, source text NOT NULL,
  kind text NOT NULL, payload jsonb NOT NULL, PRIMARY KEY(chain_id, tx_hash, log_index));

CREATE TABLE ledger_entry (id bigserial PRIMARY KEY, wallet_id int REFERENCES wallet,
  asset_id int REFERENCES asset, chain_id int, tx_hash bytea, log_index int,
  block_number bigint NOT NULL, ts timestamptz NOT NULL,
  qty numeric NOT NULL,                 -- signed: + in, - out
  category text NOT NULL,               -- swap|nft_buy|nft_sale|auction|transfer_internal|deposit|withdrawal|fee|income
  trade_group uuid,                     -- links legs of one swap or sale
  price_usdc numeric,                   -- unit USDC price at tx time (POB/POS)
  price_source text, price_confidence real, price_id bigint REFERENCES price_point,
  UNIQUE(chain_id, tx_hash, log_index, wallet_id, asset_id));

CREATE TABLE price_point (id bigserial PRIMARY KEY, asset_id int REFERENCES asset,
  chain_id int, block_number bigint, ts timestamptz NOT NULL, price_usdc numeric NOT NULL,
  source text NOT NULL,   -- trade|dex_twap|dex_swaps|defillama|coingecko|baazaar
  confidence real, UNIQUE(asset_id, block_number, source));

CREATE TABLE fifo_lot (id bigserial PRIMARY KEY, wallet_group text NOT NULL, asset_id int,
  open_entry_id bigint REFERENCES ledger_entry, opened_at timestamptz, open_block bigint,
  qty_open numeric NOT NULL, qty_remaining numeric NOT NULL,
  basis_usdc numeric NOT NULL,          -- total USDC basis at point of buy (incl. capitalized fees per Q7)
  basis_usdc_per_unit numeric GENERATED ALWAYS AS (basis_usdc / NULLIF(qty_open,0)) STORED,
  basis_price_source text NOT NULL, basis_confidence real);
CREATE INDEX ON fifo_lot(wallet_group, asset_id, open_block, id) WHERE qty_remaining > 0;

CREATE TABLE lot_disposal (id bigserial PRIMARY KEY, lot_id bigint REFERENCES fifo_lot,
  close_entry_id bigint REFERENCES ledger_entry, qty numeric NOT NULL,
  proceeds_usdc numeric NOT NULL,       -- USDC at point of sell, pro-rata to qty
  proceeds_price_source text NOT NULL, proceeds_confidence real,
  cost_usdc numeric NOT NULL,           -- qty x lot basis_usdc_per_unit
  realized_pnl_usdc numeric GENERATED ALWAYS AS (proceeds_usdc - cost_usdc) STORED,
  closed_at timestamptz);

CREATE TABLE pnl_snapshot (wallet_group text, asset_id int, as_of timestamptz, as_of_block bigint,
  qty numeric, cost_basis_usdc numeric, mark_price_usdc numeric, market_value_usdc numeric,
  realized_pnl_usdc numeric, unrealized_pnl_usdc numeric, PRIMARY KEY(wallet_group, asset_id, as_of));

CREATE TABLE sync_cursor (source text, wallet_id int, last_block bigint, last_block_hash bytea,
  updated_at timestamptz, PRIMARY KEY(source, wallet_id));
```
FIFO rules: lots are ordered by (open_block, log_index). Transfers between own wallets in the same group carry lots over without disposing (lot-level FIFO across the group). Gas is a disposal of ETH, and its cost is added to the trade's basis or deducted from proceeds (Q7). Income (channeling, rewards) opens a lot at its USDC value at receipt. Unrealized PnL = Σ remaining qty × current mark − Σ remaining basis_usdc (pro-rata).

## 4. Phased build plan (each phase has a check before moving on)
| Phase | Scope | Done when |
|-------|-------|-----------|
| **P0 Spike** (0.5–1 d) | With the bot key, introspect the three AarcadeGh$t subgraphs. Map the listed entities to fields (buyer, seller, price, tx hash, block or timestamp) and pick each entity's cursor field. Check S1b parity on a sample. Confirm RPC archive `balanceOf`-at-block and `getLogs` range limits, and Etherscan v2 access. Find GHST/alchemica addresses and liquid pools | `docs/sources.md` holds real authenticated queries and sample responses. Every S1 event in the sample resolves to a receipt (tx hash → block hash). Rate limits are measured. Q2–Q4 are answered or deferred |
| **P1 Raw ingest** | Postgres plus migrations. Etherscan v2 + RPC log backfill (core) into `raw_event`/`block`. S1 marketplace ingest (with S1b failover), joined to receipts. Worker with rate limiter and pagination. Cursors and reorg rewind | Re-running ingest twice produces identical row counts. Balances computed from `raw_event` equal RPC `balanceOf` both at head **and at 3 sampled historical blocks** for every wallet and asset. No 429 storms in logs. A simulated reorg (forced hash mismatch) rewinds and re-ingests cleanly |
| **P2 Ledger and classification** | Turn raw events into `ledger_entry`, including swaps, Baazaar/GBM sales from the subgraphs, internal transfers, and gas | Over 98% of txs classified, with the rest in the review queue. 10 hand-checked txs match explorer views |
| **P3 Pricing** | `price_point` cache, DEX at-block pricer, DefiLlama/CoinGecko fallback, Baazaar NFT marks | Each fungible asset is priced at 20 sampled blocks. DEX prices fall within ±3% of API prices where both exist, and every ledger entry has a price or a flag |
| **P4 FIFO engine** | Lots, disposals, realized and unrealized PnL, deterministic recompute from block X | Golden test fixtures (hand-built FIFO scenarios) pass. A full rebuild matches the incremental result. Σ(realized + unrealized) reconciles with net USDC flows plus market value |
| **P5 Reporting** | CLI/API: PnL by asset, wallet group, and period. CSV export. Scheduled sync | user_default reviews one month's report against their own records |
| **P6 (later)** | More chains (Polygon legacy), more DEXs and protocols, UI | — |

## 5. Open questions
1. ~~What is "POB/S"?~~ **Resolved:** point of buy / point of sell, valued in USDC at tx time (see §0, §2).
2. **Pending with user_default:** the AarcadeGh$t bot API key for cryptoPnL (portal-issued). ~~Wallet list~~ is resolved in v0.5: wallets are dynamic (§1.3). Still to confirm: do transfers between wallets in the same group keep their basis? (Proposed: yes.)
3. Contract addresses and liquid DEX pools on Base for GHST, FUD, FOMO, ALPHA and KEK. Alchemica coverage on DefiLlama/CoinGecko is unverified.
4. **Pending with user_default:** the archive Base RPC provider and the Etherscan v2 API key (and its plan limits).
5. **Polygon pre-migration basis (still open):** nothing indexes Polygon. Should Polygon history be pulled via RPC plus explorer, or should migrated assets enter at fair value on migration day (2025-07-25)?
6. Treatment of channeled or claimed alchemica, rewards and staking: income at fair market value (proposed) or zero cost?
7. Gas: capitalize it into basis or record it as a separate expense? Should gas ETH be a FIFO disposal?
8. NFT marking method (last sale, floor, or comparables), and are low-confidence values included in totals?
9. For each S1 entity: which field is the monotonic cursor, and is the tx hash exposed on every entity needed for the receipt join? (P0)
10. Tax rules beyond FIFO (e.g. wash sales)? Out of scope unless requested.
