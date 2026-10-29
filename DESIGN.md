# cryptoPnL: Design Document (v1.3, draft for approval)

Owner: user_default · Repo: github.com/userdefault13/cryptoPnL (empty, `main`) · Status: **design only, no build until approved**

Changelog: v1.2 (2026-10-16): PR #3 (P2 classification) decisions recorded in §8: buy-order escrow as custody, a spam category, and migration basis (user_default chose carry-over of the Polygon basis, with a manual low-confidence fallback). §5 Q5 resolved.
v1.1 (2026-10-16): PR #1 (083d012) review decisions recorded in §7: balance-check scope, wearables P1.1 custody rule, Sepolia finality caveat, rates (HyperSync 7/min, RPC 1/s), and a verified Base allowlist (+5 contracts). Sepolia mismatches traced to Installation-type diamonds, not wearables.
Changelog: v1.0 (2026-10-16): **No Goldsky** (user_default). S1b Goldsky failover is replaced by Baazaar/GBM sales from **HyperSync logs** of the Aavegotchi Diamond and GBM Baazaar diamond (§1.4). AarcadeGh$t is used for **point lookups only** (paging broken: 1 row per list query). P1 bulk ingest = HyperSync, 15/min total (M1 8 + omarchywin 7, approved). The free RPC is now **base.drpc.org** (archive `eth_call`; `getLogs` ≤ 100 blocks), with mainnet.base.org as secondary. All Goldsky references are removed.
Changelog: v0.9 (2026-10-15): Added §6, an **option, not a decision**: self-hosted Base node options compared. Verdict: nothing fits omarchywin, because its disk is a 1.8 TB **HDD** and it has 11 GiB RAM, against Reth's Base minimums of 2 TB TLC NVMe and 128 GB RAM even for a full node.
Changelog: v0.8 (2026-10-15): **No paid RPC, no Alchemy, no Etherscan** (v2 deferred). S2 becomes the free public RPC `mainnet.base.org` (at-block `eth_call` tested OK, no archive guarantee, debug/trace rejected), used for `slot0`, `balanceOf`, receipts and ENS/Basename lookups, never for log history. S3 Etherscan is removed, and all history comes via HyperSync. Internal ETH is a known gap. See ENVIO_TOKEN_INDEXER.md §5c.
Changelog: v0.7 (2026-10-15): HyperSync account limit measured at about 15 queries/min total (not 29). Proposed split M1 8 + omarchywin 7. No traces: internal ETH comes from Etherscan v2 `txlistinternal` per address. See ENVIO_TOKEN_INDEXER.md §5b.
Changelog: v0.6 (2026-10-15): The Envio indexer is hosted on **omarchywin** (Tailscale 100.72.80.69, 6.0 GiB RAM available, 1.8 TB free disk, Docker 29.7.2), not the M1. It uses the M1's shared HyperSync throttle and the existing proxy over Tailscale. See ENVIO_TOKEN_INDEXER.md §5a.
Changelog: v0.5 (2026-10-15): Wallets are dynamic (connected via SIWE or connect-only, or typed in manually with checksum/ENS/Basename checks), stored with `source` and grouped by user/session, with an on-demand backfill per added address (hybrid indexing, ENVIO_TOKEN_INDEXER §3a). Privacy rules added. WETH/cbBTC are priced by `slot0` at the tx block.
Changelog: v0.4 (2026-10-15): Added the [ENVIO_TOKEN_INDEXER.md](ENVIO_TOKEN_INDEXER.md) design. A Base-first Envio indexer (`cryptopnl-tokens-base`, exposed through the aarcade-subgraph-api proxy) replaces the RPC/Etherscan transfer and swap backfill for the tracked tokens (WETH/ETH, cbBTC, GHST, FUD, FOMO, ALPHA, KEK, GLTR). GHST and alchemica prices come from Aerodrome pools.
Changelog: v0.3 (2026-10-14): Source 1 is now the self-hosted AarcadeGh$t subgraphs (fallback superseded in v1.0). RPC logs and Etherscan v2 are core. No subgraph time-travel. Subgraph events are joined to receipts for reorg safety. Rate limiter and pagination added. P0/P1 and the open questions updated.
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
| **S1b (v1.0)** | **HyperSync logs of the Aavegotchi Diamond + GBM Baazaar diamond** (§1.4) | Baazaar listings/buy-order executions and GBM auction bids/wins, the bulk marketplace history | Replaces the removed hosted-subgraph failover |
| **S2 (core, v1.0)** | **Free RPC `https://base.drpc.org`** (primary: archive `eth_call` works, `eth_getLogs` ≤ 100 blocks per Builder), `https://mainnet.base.org` (secondary, spot calls) (Sepolia: `https://sepolia.base.org`) | Spot and at-block `eth_call` (`slot0`, `balanceOf`), receipts (gas, L1 fee), `eth_getBalance` reconciliation, block hash/timestamp | Rate-limited and not for production (Base docs). At-block calls worked in tests, but archive state isn't guaranteed. `debug_*`/`trace_*` rejected. Budget ≤ 2 req/s with backoff (ENVIO §5c) |
| ~~S3 Etherscan v2~~ | **Removed in v0.8** (deferred). History comes from HyperSync (ENVIO doc §3a/§5c) | | |
| S4 | DEX pools on Base: Uni V3 WETH/USDC & cbBTC/USDC, and Aerodrome GHST/WETH and alchemica/GHST (verified, ENVIO_TOKEN_INDEXER.md §1.2) | Swap classification and at-block prices | Via the Envio indexer |
| S5 | DefiLlama / CoinGecko historical prices | Price fallback (§2) | |

**v0.8:** all log history (transfers, swaps, wallet txs) comes from HyperSync (Envio stack + per-address jobs). No Etherscan, no `eth_getLogs` history. Internal ETH is a known gap (ENVIO §5c). **v0.6:** the indexer runs on omarchywin, exposed via the M1 proxy (ENVIO_TOKEN_INDEXER §5a). **v0.4:** for the tracked tokens, ERC20 Transfer and DEX Swap backfill come from the Envio indexer `cryptopnl-tokens-base` (see ENVIO_TOKEN_INDEXER.md §7). S2/S3 remain for receipts, gas, at-block reads, untracked tokens and internal ETH.

**Rules:** (a) **never use subgraph time-travel.** Historical balances come from RPC `balanceOf` (or `eth_getBalance`) at the target block. (b) Each subgraph event is **joined to its tx receipt by tx hash** (S2) to get block number, block hash, log index and timestamp. Reorg safety comes from the receipt, never from the subgraph. (c) Nothing here indexes Polygon. Polygon history, if needed, can only come from RPC plus explorer (Q5).

### 1.3 Wallets: connected and manual (v0.5)
- **Connected:** a wallet-connect button (injected / WalletConnect / Coinbase Wallet). **Connect-only** is enough for read-only viewing. **SIWE (EIP-4361)** sign-in is required to *own* a wallet group (save it, name it, and see it on return). SIWE nonce is single-use with a 10-minute expiry, the domain/chainId (8453) are bound, and smart-wallet signatures are verified via EIP-1271/6492.
- **Manual:** an address field that accepts `0x…` (validated with the EIP-55 checksum; all-lowercase is accepted and normalized, mixed-case with a bad checksum is rejected) or a name. **ENS** is resolved on Ethereum mainnet and **Basenames** (`*.base.eth`) on Base via their resolvers. The resolved address is shown for confirmation, and the name is stored as a label. Reverse resolution is display-only.
- **Storage:** `wallet` gains `source text CHECK (source IN ('connected','manual'))`, `owner_kind ('user','session')`, `owner_id` (user id after SIWE, else an anonymous session id), `ens_name`, `added_at`, and `verified bool` (true only when a SIWE signature proves control). `wallet_group` becomes `(owner_kind, owner_id, group_name)`. A session-owned group is migrated to the user on SIWE login. The same address may appear in several owners' groups.
- **On add → on-demand backfill:** enqueue the job in ENVIO_TOKEN_INDEXER §3a. GHST/alchemica/GLTR history is read immediately from the Envio stack (`cryptopnl-tokens-base`). USDC/WETH/cbBTC/ETH come via the per-address HyperSync job, streamed progressively (v0.8: no Etherscan). The **AarcadeGh$t subgraph queries stay per address** (Baazaar/GBM by seller/buyer/bidder = address).
- **Privacy:** addresses are public on-chain data, but *who looks at which address* is not. Rules: don't write raw addresses to application/access logs (log a salted hash or a short id; no addresses in URLs/query strings, use POST bodies or opaque wallet ids). Send no addresses to third-party analytics. Anonymous session groups expire after 30 days, deletable on request; SIWE-owned groups are deletable by the owner. Outbound queries carry addresses only to the data sources that need them (HyperSync, AarcadeGh$t, and the public RPC for ENS/Basename), never to price APIs. Cached on-chain data is keyed by address (shared and public), while the owner→address mapping lives only in `wallet`.

### 1.4 Marketplace sales without hosted subgraphs (v1.0)
**Sources, in order:** (1) **HyperSync logs** (bulk, P1) of the two diamonds below. (2) **AarcadeGh$t point lookups** for enrichment (item metadata, listing by id, one row per query). (3) **Last resort:** `eth_getLogs` on `base.drpc.org` in windows of ≤ 100 blocks, only for gap-filling a specific block range (e.g. a single missing tx). Never for backfill.

**Contracts** (from `aavegotchi/deployed-contract-addresses` README, Base section; code presence checked on base.drpc.org 2026-10-16):
| Contract | Address | Check |
|---|---|---|
| Aavegotchi Diamond (Baazaar ERC721/ERC1155 listings + buy orders) | `0xA99c4B08201F2913Db8D28e71d020c4298F29dBF` | Repo ✅, code present (6,431 bytes proxy) ✅ |
| GBM Auction (Baazaar) diamond | `0x80320A0000C7A6a34086E2ACAD6915Ff57FfDA31` | Repo ✅, code present (3,871 bytes) ✅ |

**Events** (signatures from `aavegotchi-contracts` `diamondABI/diamond.json` and `ERC1155BuyOrderFacet.sol`, and `aavegotchi-gbm-baazaar` `diamondABI/diamond.json`; topic0 = keccak256 computed locally):
| Event | topic0 | Use |
|---|---|---|
| `ERC721ExecutedListing(uint256,address,address,address,uint256,uint256,uint256,uint256)` | `0x8abb27e5…44bb28` | ERC721 Baazaar sale (seller, buyer, price) |
| `ERC1155ExecutedListing(uint256,address,address,address,uint256,uint256,uint256,uint256,uint256)` | `0x4004185f…49515c` | ERC1155 sale (qty × price) |
| `ERC721BuyOrderExecuted(uint256,address,address,address,uint256,uint256,uint256)` | `0x252535f1…9f14f6` | ERC721 buy-order fill |
| `ERC1155BuyOrderExecute(uint256,address,address,address,uint256,uint256,uint256,uint256,uint256)` | `0xa604c414…` (see file) | ERC1155 buy-order fill |
| `Auction_Initialized(uint256,uint256,uint256,address,bytes4,uint256)` | `0x62cdbfd4…0a9b` | Auction → token/contract mapping |
| `Auction_BidPlaced(uint256,address,uint256)` | `0x1cd77ec6…5c9181` | Bids (GHST escrow out/in) |
| `Auction_BoughtNow(uint256,address)` | `0x7499cdcb…5a4ab6` | Buy-now win |
| `Auction_ItemClaimed(uint256)` | `0x36c817b0…a90a9b` | Settlement (winner = last bid) |
Full topic0 hashes are in `/workspace/cryptoPnL/verify/marketplace_topics.txt`.

**Unverified (P0):** the ABIs come from the Polygon-era repos (the `aavegotchi-base` repo ABI path wasn't found). Whether these exact signatures are emitted on Base is **not yet observed on-chain**: a drpc 100-block scan timed out (HTTP 408). P0 runs a HyperSync topic0 count per event on both addresses. Any event with 0 hits gets its signature re-derived from the Base facet source. Sale price is in GHST (Baazaar), priced to USDC at the tx block via §2. Royalty/fee splits come from GHST `Transfer` logs in the same tx.
**Deferred:** none of S1b is deferred. All three replacement paths are specified. Only paged bulk reads from AarcadeGh$t are deferred until Aarcadeghst CoS fixes paging.

### 1.2 Ingestion pipeline
1. **Backfill (v0.8):** for each wallet, pull history from HyperSync (Envio stack + per-address job), then fetch receipts from the free public RPC (S2) as needed for gas and L1 fee. No explorer.
2. **Incremental:** a cursor per source (`sync_cursor`: source, wallet, last_block, last_block_hash). (v0.8: log scans use HyperSync, not `eth_getLogs`.) Each run scans `last_block+1 .. head-CONFIRMATIONS`, filtered on topic = wallet address (topics 1 and 2 for ERC20/721, topics 2 and 3 for 1155) and chunked by block range. Subgraph: filter entities by wallet (seller/buyer/bidder) plus a monotonic field (block number or timestamp field if exposed, else `id`) with `where: {field_gt: cursor}`, `orderBy` on that field and `first: 1000`. Then enrich each row through its receipt.
   - **Rate limiter and pagination in the ingest worker:** a token bucket per source (S1 ≤ 1 req/s, about 60/min; S1b = HyperSync via the throttle (15/min total: M1 8 + omarchywin 7); free RPC base.drpc.org ≤ 2 req/s with backoff, mainnet.base.org secondary (v1.0)), exponential backoff with jitter on 429/5xx, cursor pagination capped at `first ≤ 1000`, and queries kept under depth 8. (v1.0) S1 AarcadeGh$t is used **only for point lookups** (by id / tx hash / tokenId) until Aarcadeghst CoS fixes paging. Bulk marketplace history comes from S1b HyperSync logs.
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
| **P0 Spike** (0.5–1 d) (v0.8: Etherscan/archive-RPC checks are replaced by HyperSync + public-RPC at-block checks) | With the bot key, introspect the three AarcadeGh$t subgraphs. Map the listed entities to fields (buyer, seller, price, tx hash, block or timestamp) and pick each entity's cursor field. (v1.0) Verify the §1.4 topic0s on Base with a HyperSync count, and spot-check 5 sales against AarcadeGh$t point lookups. Confirm RPC archive `balanceOf`-at-block and `getLogs` range limits, and Etherscan v2 access. Find GHST/alchemica addresses and liquid pools | `docs/sources.md` holds real authenticated queries and sample responses. Every S1 event in the sample resolves to a receipt (tx hash → block hash). Rate limits are measured. Q2–Q4 are answered or deferred |
| **P1 Raw ingest** | Postgres plus migrations. (v0.8: HyperSync) log backfill into `raw_event`/`block`. (v1.0) Marketplace ingest from S1b HyperSync diamond logs (§1.4), enriched by AarcadeGh$t point lookups and joined to receipts. Worker with rate limiter and pagination. Cursors and reorg rewind | Re-running ingest twice produces identical row counts. Balances computed from `raw_event` equal RPC `balanceOf` both at head **and at 3 sampled historical blocks** for every wallet and asset. No 429 storms in logs. A simulated reorg (forced hash mismatch) rewinds and re-ingests cleanly |
| **P2 Ledger and classification** | Turn raw events into `ledger_entry`, including swaps, Baazaar/GBM sales from the subgraphs, internal transfers, and gas | Over 98% of txs classified, with the rest in the review queue. 10 hand-checked txs match explorer views |
| **P3 Pricing** | `price_point` cache, DEX at-block pricer, DefiLlama/CoinGecko fallback, Baazaar NFT marks | Each fungible asset is priced at 20 sampled blocks. DEX prices fall within ±3% of API prices where both exist, and every ledger entry has a price or a flag |
| **P4 FIFO engine** | Lots, disposals, realized and unrealized PnL, deterministic recompute from block X | Golden test fixtures (hand-built FIFO scenarios) pass. A full rebuild matches the incremental result. Σ(realized + unrealized) reconciles with net USDC flows plus market value |
| **P5 Reporting** | CLI/API: PnL by asset, wallet group, and period. CSV export. Scheduled sync | user_default reviews one month's report against their own records |
| **P6 (later)** | More chains (Polygon legacy), more DEXs and protocols, UI | — |

## 5. Open questions
1. ~~What is "POB/S"?~~ **Resolved:** point of buy / point of sell, valued in USDC at tx time (see §0, §2).
2. **Pending with user_default:** the AarcadeGh$t bot API key for cryptoPnL (portal-issued). ~~Wallet list~~ is resolved in v0.5: wallets are dynamic (§1.3). Still to confirm: do transfers between wallets in the same group keep their basis? (Proposed: yes.)
3. Contract addresses and liquid DEX pools on Base for GHST, FUD, FOMO, ALPHA and KEK. Alchemica coverage on DefiLlama/CoinGecko is unverified.
4. ~~RPC provider / Etherscan key~~ **Resolved v0.8:** free public RPC only. No Etherscan (deferred). Remaining risk: public at-block state availability (fallbacks in ENVIO §5c).
5. ~~Polygon pre-migration basis~~ **Resolved v1.2 (user_default, 2026-10-16):** carry over the original Polygon basis. Bridged re-mints are custody moves (`migration_in`), never income. Fallback is in §8.
6. Treatment of channeled or claimed alchemica, rewards and staking: income at fair market value (proposed) or zero cost?
7. Gas: capitalize it into basis or record it as a separate expense? Should gas ETH be a FIFO disposal?
8. NFT marking method (last sale, floor, or comparables), and are low-confidence values included in totals?
9. For each S1 entity: which field is the monotonic cursor, and is the tx hash exposed on every entity needed for the receipt join? (P0)
10. Tax rules beyond FIFO (e.g. wash sales)? Out of scope unless requested.

## 6. Option (not a decision): run our own Base node? (v0.9)
**Goal:** close the internal-ETH gap (needs `debug_trace*`/`trace_*` over history) and remove the public-RPC dependency.
**omarchywin facts (read-only `lsblk`, 2026-10-15):** `sda` 1.8 TB **Seagate ST2000DM001, ROTA=1 → spinning HDD**. The other devices are a 29.7 GB SD card and zram. 11 GiB RAM, 8 CPUs.

**Requirements from real sources:**
- **Base docs (Node Performance):** 8+ cores, **≥ 32 GB RAM (64 GB recommended)**, a **locally attached NVMe SSD**, and disk = `2 × chain size + snapshot size + 20%`. Base's production archive node is a Reth archive on AWS `i7i.12xlarge`, RAID-0 NVMe. Reth is the recommended client.
- **Reth system requirements (Base mainnet, as of 2025-06-23, block 31,900,000):** archive **≥ 4.1 TB** TLC NVMe, full **≥ 2 TB** TLC NVMe, **128 GB+ RAM for both**, 6+ cores (5+ needed for the parallel state-root task, else > 2s block latency and lag). The chain is about 52.6M blocks now, so today's figures are larger. A Base maintainer said the archive was "3TB" in April 2025 (base/node#434).
- **Base snapshots (docs):** `--minimal` (latest state + headers), `--full` (Reth full preset keeps the last 10,064 blocks, about 5–6 h on Base), `--archive` (everything). They speed up sync but need extra space to download and extract. Current snapshot sizes are on snapshots.base.org (not checked).
- **Reth selective pruning (reth.rs config/CLI):** `[prune.segments.receipts_log_filter]` / `--prune.receiptslogfilter <addr>:<full|distance:N|before:B>` keeps receipts only for logs from chosen contracts. It **only trims receipts**. The node still stores and executes full current state, so the full-node disk/RAM floor still applies.
- **Helios (a16z):** `helios opstack --network base --execution-rpc <URL>`. It verifies an **untrusted upstream RPC** (which must support `eth_getProof`) and serves a local RPC on :8545. It's tiny, but it **doesn't remove the upstream dependency** and adds no history or traces. Verified at-block reads still need the upstream to have that state.
- **L1 dependency:** any Base node (op-node / base-node consensus) needs an Ethereum L1 execution RPC and a beacon endpoint (blobs). Free public L1 endpoints are rate-limited, and their blob-history coverage for a from-genesis sync is not established here. With a recent snapshot, only the recent L1/blob window is needed. **Unverified** that free endpoints sustain this (open question).
- Erigon / op-erigon, op-geth, Nethermind: Base now concentrates on Reth, and no Base-specific hardware figures were checked for them. Not evaluated further.

| Option | Disk | RAM | Sync | At-block `eth_call`/`balanceOf` | Logs/receipts | Traces (internal ETH) | Fits omarchywin? |
|---|---|---|---|---|---|---|---|
| Full/pruned op-reth (`--full`) | ≥ 2 TB NVMe (Reth, mid-2025, now more) | 128 GB+ (Reth) / ≥ 32 GB (Base doc) | Snapshot download + catch-up. Hours to days, not measured | Only the last ~10k blocks (~5–6 h) | Recent window only (unless receipts are kept) | Recent blocks only | **No**: HDD, too-small disk, RAM 11 GiB |
| Archive op-reth | ≥ 4.1 TB NVMe (mid-2025, ~3 TB Apr-2025 per maintainer) | 128 GB+ | Archive snapshot (days to download/extract, not measured) | Yes, full history | Yes | **Yes** (`debug_trace*` over history), the only option that closes the gap | **No** |
| Reth + `receiptslogfilter` | ≈ full-node floor (state still full) | 128 GB+ | As full | Recent only | Only for chosen contracts | Recent only | **No** |
| Helios (light client) | Negligible | Small | Seconds–minutes | Only if the upstream serves it (verified) | Via upstream | No | Yes, but **doesn't** remove the upstream or close the gap |
| Base snapshots | Speed up the above. Need extra free space to extract | – | Faster | per the chosen config | – | – | Doesn't change the verdict |

**Verdict: no self-hosted node fits omarchywin.** The disk is a spinning HDD (Base and Reth both specify NVMe SSD), smaller than even the full-node floor (≥ 2 TB), and RAM is about a tenth of Reth's Base figure. Only an **archive** node closes the internal-ETH gap (historical tracing needs historical state). The minimal hardware for that, per the sources, is ≥ 4.1 TB (now likely more) TLC NVMe + 128 GB RAM + 6+ fast cores, plus L1 RPC and beacon access. **Lightest useful option today: Helios** in front of `mainnet.base.org`, to verify at-block reads (integrity only, no new capability). Otherwise keep the v0.8 design (HyperSync + public RPC + internal-ETH gap with reconciliation). Revisit if user_default gets NVMe hardware of about 5 TB with ≥ 64–128 GB RAM, or allows paid traces / Etherscan.
**Open:** current snapshot sizes (snapshots.base.org); whether free L1 RPC and beacon endpoints sustain a Base node; Helios at-block reads against the public RPC (needs `eth_getProof` at old blocks, untested).


## 7. PR #1 decisions (v1.1)

**Balance scope.** The gate compares replayed balances with `balanceOf` at 4 sampled blocks, only for the fungible tracked tokens the wallet touched (Base: 7 assets × 4 = 28/28 passed). Untracked contracts are reported, not gated. ERC-1155/721 diamonds are reported, not gated, until P1.1.

**Wearables custody rule (P1.1).** A wearable equipped on a gotchi moves owner→gotchi via `TransferToParent` (0xe8281009…43d3) and back via `TransferFromParent` (0x4b287e36…c6d), emitted by the Aavegotchi Diamond. Effective holdings = wallet `balanceOf` + items held by gotchis the wallet owns. Equip/unequip is a custody move, never a disposal, so no FIFO lot closes. The same rule applies to installations/tiles on REALM parcels once their parent events are confirmed.

**Sepolia finality caveat.** "Pruned / 4444" state errors may be read as final only on chain 84532 (Base Sepolia test data). On Base 8453 the indexer must fail closed: safe tag, else head−64, plus a hash check.

**Rates.** HyperSync 7/min per host (omarchywin's share of the 15/min account total; the M1 keeps 8). Any other host must share a quota, not add to it. RPC 1 req/s, burst 3; Retry-After honored up to 120 s. No Goldsky, no paid RPC.

**Allowlist (Base 8453).** Every entry was checked with getCode/name/uri on base.drpc.org on 2026-10-14.

| Asset | Address | Status |
|---|---|---|
| GHST | 0xcD2F22236DD9Dfe2356D7C543161D4d260FD9BcB | in PR |
| FUD | 0x2028b4043e6722Ea164946c82fe806c4a43a0fF4 | in PR |
| FOMO | 0xA32137bfb57d2b6A9Fd2956Ba4B54741a6D54b58 | in PR |
| ALPHA | 0x15e7CaC885e3730ce6389447BC0f7AC032f31947 | in PR |
| KEK | 0xE52b9170fF4ece4C35E796Ffd74B57Dec68Ca0e5 | in PR |
| GLTR | 0x4D140CE792bEdc430498c2d219AfBC33e2992c9D | in PR |
| USDC | 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 | in PR |
| WETH | 0x4200000000000000000000000000000000000006 | in PR |
| cbBTC | 0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf | in PR |
| Aavegotchi Diamond | 0xA99c4B08201F2913Db8D28e71d020c4298F29dBF | in PR |
| Wearable Diamond ("Aavegotchi Items") | 0x052e6c114a166B0e91C2340370d72D4C33752B4b | **add** |
| Forge Diamond | 0x50aF2d63b839aA32b4166FD1Cb247129b715186C | **add** |
| REALM Parcels | 0x4B0040c3646D3c44B8a28Ad7055cfCF536c05372 | **add** |
| Installations | 0xebba5b725A2889f7f089a6cAE0246A32cad4E26b | **add** |
| Tiles | 0x617fdB8093b309e4699107F48812b407A7c37938 | **add** |

The GBM diamond 0x80320A0000C7A6a34086E2ACAD6915Ff57FfDA31 stays a marketplace log source (§1.4), not a held asset.

**Sepolia mismatches.** 0x4773f06f…ff64b and 0xb2d52be3…554a1 are 7-facet diamonds with owner 0x2fdb4b22…2db6 and `uri(1)` = metadata/installation/1. They are Installation-type diamonds, not wearables, and they are not the README's Sepolia Installation diamond 0x5Aefdc52…7609 (which shares no facets with them). Mismatch cause unverified: sepolia.base.org rejects wide getLogs (413).

## 8. PR #3 (P2 classification) decisions (v1.2)

**Buy-order escrow.** Placing a Baazaar buy order moves GHST from the wallet into diamond escrow. Classify it as `escrow_out`: a custody move with no FIFO disposal, and the lots stay open, tagged escrowed. On a **fill**, those escrowed GHST lots are disposed at the fill block's GHST/USDC price (§2 order). The NFT's basis equals that USDC value (`nft_buy` with the escrow as its payment leg). On a **cancel or refund**, `escrow_return` puts the lots back unchanged. That is a custody move, never a `deposit`, and there is no PnL. A partial fill disposes only the filled portion.

**Spam.** A new category, `spam`, covers unsolicited fake or airdropped tokens, zero-value address-poisoning transfers, and pass-through tokens. These rows stay in the ledger flagged, are never priced, are excluded from every PnL total, and are hidden in the UI by default (user_default can toggle them on). They are never `deposit`/`withdrawal`/`review`.

**Migration basis (user_default's decision: carry over).** `mintAavegotchiBridged` and other bridged re-mints are `migration_in`: a custody move, never income. Each migrated asset inherits its Polygon lots, meaning the original basis_usdc, acquisition time, and price_source, with `chain_origin = 137`. Holding period starts at the Polygon acquisition, not the re-mint.
Basis resolution, in order:
1. **Polygon carry-over:** basis from the Polygon FIFO ledger, once the Polygon phase (P6) ingests that history from free sources. `confidence` comes from the original price.
2. **Manual entry:** user_default enters the basis in USDC (optionally with an acquisition date). Stored with `price_source = manual` and `confidence = low`. Always shown with a low-confidence badge.
3. **Unresolved:** `basis_status = pending`. The lot exists (holdings are correct), but its basis is **unknown, not zero**. Lots with unknown basis are excluded from realized/unrealized totals, so they are not counted as 100% gain, and are listed in the UI with a count of unresolved lots. This follows the rule never to invent prices. A sell from a pending lot produces proceeds and a pending realized PnL that is resolved once basis arrives.
A later Polygon carry-over replaces a manual entry only if user_default confirms it; the manual value is kept in history.

**Schema deltas (P2).** `tx_class` enum += `escrow_out`, `escrow_return`, `spam`, `migration_in`. `lot` += `basis_status` (resolved|pending|manual), `chain_origin`, `escrow_ref` (order id). `lot_disposal` += `payment_for` (the NFT acquisition the escrow paid for).

**Required tests.** Escrow place→fill, place→cancel, and partial fill. The bridged mint gives migration_in with pending basis, then manual low-confidence. Spam rows are excluded from totals. Net retry does not retry permanent errors such as SSL certificate failures.

**P2 follow-ups (v1.2, 2026-10-16).**
- *Migration rule.* `migration_in` = tx from bridge sender 0xf52398257A254D541F392667600901f710a006eD **and** a mint from 0x0 to the wallet **and** an allowlisted Aavegotchi target **and** a selector in the config list (Diamond 0xf55b061c, wearables 0xfd7499bd, Forge 0x506ccb27, REALM 0x0d51a188, Installations 0x9110d148, Tiles 0x91b06c6e). A selector not on the list goes to review. Block range 33,200,000–34,000,138 is a warning assertion only. Carry-over basis applies to every asset type, and ERC1155 lots are kept per (contract, id). (Builder-reported. The selectors were not independently verified by me.)
- *Untracked.* Self-sent txs are never spam. Non-allowlisted assets (e.g. Aarcade Cartridges, LINK legs of swaps) are `untracked`: no lot, excluded from PnL. Tracked legs of the same tx are valued at the tracked asset's own POB/S price, never via the untracked leg.
- *Bridge-in USDC.* A USDC mint from 0x0 where tx `to` = a CCTP MessageTransmitter on Base (V1 0xAD09780d193884d503182aD4588450C416D6F9D4, or V2; TokenMessengers excluded, since they are the burn side) is `bridge_in` (custody), with basis at par. Known gap: the emitter can't be verified (logs are wallet-scoped).
- *Confidence.* Stored as label plus number: high=1.0, medium=0.6, low=0.2.
- *HyperSync.* The per-host lock (≤ 7/min) must merge before any further backfill. Until then, no back-to-back or parallel runs.
- *Escrow catch-all (PR #3 re-review).* GHST moving to or from the Baazaar or GBM diamond that no escrow or market rule claims → `review`, never withdrawal or deposit (the wallet is EIP-7702 delegated, so selectors and senders vary). Fill matching order: an entry already linked to the order id, then exactly one unlinked open entry with amount = price × qty. If several could match → review.
- *P4 requirements.* Realized and unrealized totals filter `basis_status <> 'pending'` on both mark and basis. Report counts of pending lots and pending disposals. Write `lot_disposal.payment_for`. User-entered data (manual_basis) never sits under ON DELETE CASCADE from ledger_entry. Pending lots carry a NULL price source until resolved.
- *FAKE Gotchis (in scope).* 0xab59ca4a16925b0a4bac5026c94beb20a29df479 joins the Base allowlist once its getCode/name check passes. Selector 0x5e41ee65 (mintBatch) counts as migration_in only on that contract. (Builder-reported: the bridge sender created it. Not independently verified by me.)
- *Partial-fill fallback.* An unlinked first fill matches only if exactly one open escrow placed before the fill is an exact integer multiple of the unit price, leaves a remaining balance ≥ 0, and no other entry carries that order id. Otherwise → review.
- *Rate note.* One Sepolia 429 at about 3/min (cause unverified). If it recurs on Base, omarchywin drops to 5/min.
- *Mints without tx details.* A mint from 0x0 of an allowlisted contract whose tx lookup failed, or that comes through a wallet EIP-7702 `execute` wrapper with an inner call that can't be decoded → review, never income.
- *7702 rule narrowed.* The review rule applies only to mints of allowlisted contracts. A non-allowlisted mint inside an `execute` wrapper is untracked, and the rest of the tx classifies normally (e.g. 0x4a5a7c6c…f697 → swap, USDC leg at par).
- *FAKE Gotchi Cards.* 0xe46b8902dad841476d9fee081f1d62ae317206a9 (ERC1155, created by the bridge sender per the Builder) is in scope for P2.1, once its getCode/name check passes.
- *Rate change (2026-10-16).* Base gave two 429s at about 6.9/min, so omarchywin's HyperSync budget drops to **5/min** (the M1 keeps 8, 13 total). This supersedes §7 Rates.
- *PR #3 approved* at ae42130, on condition of the 7702 narrowing and its test.
- *USDC numeraire.* Native USDC (Base 0x8335…2913, and Polygon native in P6) is priced 1.0, high confidence, because it is the unit of account. Bridged or wrapped USDC (USDbC, USDC.e) uses pool prices, never par. Confirms KNOWN_GAPS #16.

### P4 rulings (2026-10-28)
Config defaults of the P4 engine, as switches (`cryptopnl/p4_policy.json`, override with `--set key=value`). `fifo.Policy` itself has no defaults: an unset switch raises `PolicyRequired(<question>)`.
- **Q-B deposits/withdrawals (architect).** An external deposit opens a lot with `basis_status=pending` (unknown basis: not 0, not market value). It is excluded from totals and counted, and can be resolved through `manual_basis` or reclassification (`deposit=pending`). An external withdrawal is a custody exit (`withdrawal=exit`): `lot_disposal.kind='exit'`, proceeds NULL, realized 0, and the market value at the block is stored in `display_mv_usdc` for display only. If the lots it consumes are pending, the exit stays pending.
- **Q-C reconciliation (architect).** The right-hand side is built from `ledger_entry` rows and ledger quantities, with no code shared with the lots (`cryptopnl/reconcile.py`): Σ(realized + unrealized) over resolved lots = Σ sale proceeds + MV(open resolved quantity at as_of) + Σ basis of exited lots − Σ acquisition basis (buys plus income at FMV). Open lot quantity per asset must also equal the ledger's net quantity. Income is an inflow at FMV basis, PnL 0 at receipt, with its own reported total. Tolerance is 0.01 USDC per asset and per total, in exact Decimal/numeric. Pending lots are excluded from both sides and reported as a count.
- **Q-F mark (architect).** Marks are taken at a fixed `as_of_block`, stored in `pnl_snapshot.as_of_block`, with no RPC in the engine (`mark=p3_stored_at_as_of`). Two runs at the same `as_of_block` must give byte-identical snapshots.
- **Q7 gas (user_default, §5).** On a trade, gas goes into the basis of a buy and comes off the proceeds of a sell (`fee=capitalize`). Gas on a tx with no trade leg is a separate expense, recorded as an ETH disposal at FIFO (`fee_without_trade=expense`). The Q-C reconciliation includes gas under this treatment.
- **Q8 NFT marks (user_default).** An NFT with no P3 price is left out of unrealized and counted, never marked at basis or 0 (`nft_mark=p3_price_else_exclude`; an NFT that has a stored P3 price is marked at its latest one at or before as_of).
- **Q2 wallet group (user_default).** All Base wallets form one group (`group=one_group_per_chain`). Internal transfers carry basis within the group with no realized PnL (`internal_transfer=carry`).

### P4 rulings 2 (2026-10-28, architect)
1. **Fee split** (`fee_split=basis_else_equal`). Capitalized gas over several acquired lots of one tx is split in proportion to basis. (a) If no resolved lot in the tx has basis above 0, it is split equally. (b) A pending lot keeps its gas share in `fee_usdc`, which does not enter totals until the lot's basis is resolved. `split_method` (basis | equal) is stored on each lot.
2. **Gas.** Every gas payment is an ETH FIFO disposal with proceeds equal to ETH's market value at the block, so the ETH gain or loss is realized (kind `fee_capitalized`, or `fee` with `expense_usdc` when there is no trade leg). That market value goes into the buy's basis or comes off the sale's proceeds. Gas with no trade leg is `gas_expense`, reported as its own line. The identity becomes realized + unrealized − gas_expense = the ledger-side formula (with each tx's gas attributed from the ledger), at 0.01 USDC. Golden fixture: `tests/test_fifo_rulings.py` G13 (gas paid from an ETH lot bought at 2000 when ETH is at 3000: +1 realized per gas leg).
3. **Q-G craft split** (`queue_split=recipe_else_equal`, `recipe=stored_craft_recipe_cost`). Several minted assets under one cost ref are split by each item's on-chain recipe cost (alchemica, GLTR and GHST, valued at the craft block) when every asset under the ref has a readable recipe. Otherwise the split is equal and flagged `split_method=equal` (a fallback, not the default). Free crafts keep basis 0. Recipe costs are read at ingest or pricing time under the drpc limiter and stored in `craft_recipe_cost`; the engine stays offline. The fallback count is reported (`craft_split_equal_fallbacks`).

**Pending architect confirmation** (proposals implemented behind switches):
- ~~`shortfall=pending` (Q-H)~~ ruled in P4 rulings 3 (item 5).
- `fee_split`: an equal split also applies when any acquisition of the tx is pending.
- Gas of a swap (buy and sell in one tx) goes into the bought asset's basis.
- ~~`as_of_block` = the latest block with a stored P3 price~~ ruled in P4 rulings 3 (item 3): the MIN over tracked assets.

### P4 rulings 3 (2026-10-28, architect review of PR #8)
Switches in `cryptopnl/p4_policy.json` (`ruled_in_rulings_3`); still-open proposals stay in `pending_architect`.
1. **Gas on an NFT sale** (`nft_sale`, or the seller side of `auction`) comes off the NFT's proceeds, never into the basis of the
   payment received. Order in a tx: NFT sale → acquisitions' basis → other sale proceeds → gas_expense.
2. **Exits** (Q-B withdrawal `exit`): realized is NULL, not 0. The report skips them in totals and counts them (`exits`, per asset and
   per variant); `lot_disposal_pnl.realized_usdc` is NULL for an exit, and `realized_display_usdc` shows 0 (display only, never summed).
3. **as_of_block** = MIN over the tracked fungible assets of each asset's latest block with a stored P3 price (the latest block at which
   every tracked asset is priced). Report the asset(s) that set it. The snapshot and the reconciliation use the state at as_of_block
   (ledger rows with block ≤ as_of_block).
4. **Independent reconciliation** (Q-C): the ledger side uses ledger_entry rows only. It does not read fifo_lot, lot_disposal or the
   engine state. Pending versus resolved comes from ledger categories (deposit → pending; migration_in → carried or manual basis, else
   pending; trade, income, bridge_in and craft → resolved when a value is known, else pending; gift_in → 0), with its own FIFO
   running balance per (asset, location) carried through custody legs. An out-leg larger than that balance is an **UNEXPLAINED GAP**
   (asset, qty, block): it is reported and flagged, never a pass. For P4 it is reported and flagged; real-ledger acceptance is P4.1.
   The engine is compared per asset (realized and unrealized separately) and in total (R + U − gas_expense) at 0.01 USDC, and the engine's
   open qty is compared with the ledger side's balance. A LIFO mutation of the engine must fail the reconciliation and the golden tests
   (tests/test_p4_rulings3.py).
5. **Q-H confirmed**: a shortfall opens a pending lot with `basis_origin = unrecorded_inflow` at the shortfall block (basis NULL);
   custody children carry `basis_origin`.
6. **Ordering**: ledger rows are read in (block, log_index, entry id) order, with no coalesce on tx_index. A NULL tx_index is accepted only
   when its block holds a single tx (otherwise the run stops); the count is reported as `tx_index_null_rows`.
Schema: `migrations/014_p4_rulings3.sql` (fifo_lot.basis_origin, the new view) with `migrations/rollback/014_down.sql` (run before 013_down).
7. Status: the engine is proven on synthetic golden books and on the Base ledger (rebuild == incremental, identity within tolerance);
   **real-ledger acceptance is deferred to P4.1** (resolve the unexplained gaps: missing ETH / GHST inflows).

## 9. Gotchiverse coverage (v1.3, 2026-10-17)
Source: read-only audit of main at bed74e9, aavegotchi-realm-diamond at b152ce2, aavegotchi-contracts at 301d04f, plus Base RPC and receipts. [F] = fact, [I] = inference. Full findings are in the review notes. **Covered today:** Baazaar listings (ERC721/1155), ERC1155 buy orders, GBM buyer side, instant paid crafts, normal alchemica claims and channeling (income), and REALM parcel migration.

**Rules (all new, P2.2 unless noted)**
1. **ERC721 buy orders (parcels):** add placement selector 0x6feecbb5 ([I] from the facet lookup; signature unverified), decode the fill price from ERC721BuyOrderExecuted data word 3, and ingest BuyOrderAdd plus the `…ExecutedToRecipient` topics (0x0f52fde6…, 0x6d10597e…). An NFT received as recipient with no wallet payment → `gift_in` (basis 0, flagged), not nft_buy.
2. **GBM seller side:** NFT into GBM at auction creation → `escrow_out` (custody). Claim → disposal of that lot with proceeds = GHST received at the claim block. A cancel → `escrow_return`. Buy-now without BidPlaced → nft_buy with the GHST paid as payment (verify the event first; otherwise review).
3. **Craft:** a new category `craft`. Alchemica, GLTR and GHST inputs are FIFO disposals at the craft block, and the NFT's basis = the USDC value of the inputs (P3 prices, P4 basis). Free crafts → basis 0, **not income**. Queued crafts: the craft tx is `craft_pending` (inputs disposed, cost held in a pending-basis bucket keyed by queue id), and the claim (QueueClaimed) mints the NFT with that basis. Installation quantity comes from `MintInstallations` (the TransferSingle amount is always 1 per the source bug, [F] source, unverified on Base). Every cost leg follows the 35/30/30/5 split to REALM, Pixelcraft, the DAO and 0xFFfF; all of them count as cost.
4. **Upgrade:** a new category `upgrade`. Alchemica and GLTR spent (GLTR goes to 0xFFfF, not 0x0) are disposals at the upgrade-tx block, and their value is added to the installation's basis. Finalize burns the old id from REALM and mints the new id to the owner, then re-equips it. The old lot closes **without realized PnL**, and the new id's lot = old basis + upgrade cost, still at location parcel:<id>. Link via UpgradeQueued / UpgradeQueueFinalized (owner topic) or same-tx finalize. reduceUpgradeTime GLTR adds to the queued upgrade's cost.
5. **Equip/unequip on parcels:** custody, like wearables. Ingest TransferToParent/FromParent **from the Installation and Tile diamonds** (topic1 = REALM, topic2 = parcel id), and set location `parcel:<id>`. Holdings = wallet + items equipped on the wallet's parcels. Unequip refund type 1 → custody back. **Refund type 0 → the installation is destroyed**: dispose its lot with proceeds = the USDC value of the 50% alchemica refund at that block, and acquire the refunded alchemica at that same value.
6. **Parcel sale with equipped items** [I: the items stay children of the parcel and move with it]: dispose the parcel and its equipped items as **one bundle**. Bundle basis = parcel basis + the equipped items' bases. Proceeds = the sale price. Realized PnL is reported on the parcel row, with the items listed beneath it. Revisit if user_default prefers otherwise.
7. **Income edge paths:** a claim or channel paid from the REALM diamond's balance (the Great Portal-capacity path) on the claim/channel selectors → income, not deposit. Lending revenue splits from the gotchi escrow → income.
8. **Gotchi lending:** the gotchi going out to the borrower, and back, is custody (location `lent:<borrower>`), never a sale. The upfront GHST is income. Wearables move with the gotchi. Parcel access rights move no tokens and are ignored.
9. **Bounce gates:** GLTR/alchemica sent to 0xFFfF via createEvent → `spend` (a disposal at market value, an expense with no acquired asset).
10. **Non-Gotchiverse items that touch alchemica:** router 0xeae2fb93… (FUD/GHST addLiquidity) → add it to DEX_ROUTERS or review (LP token untracked, alchemica disposed at its price). FUD depositERC20 to 0x728f0baf… → identify it (pocket-style custody?) before classifying; send to review until then.

**Phasing:** P2.2 covers classification for rules 1–10. P3 prices alchemica and GLTR at the craft, upgrade or refund blocks. P4 handles basis carry for craft and upgrade, bundle disposal and holdings by location. Test wallet impact today: 4 crafts (3 free ones currently wrongly labelled income), 5 alchemica income txs (correct), and tile buys (correct). None of the upgrade, equip, lending or GBM-seller flows appear in this wallet, so those rules are synthetic-test-only until a wallet exercises them.
**Unverified:** that the deployed facets match the GitHub source, the 0x6feecbb5 signature, GBM seller/buy-now events, the quantity-1 bug on Base, the Great Portal payout, lending topic0s, and on-chain samples of upgrade, equip and bounce-gate txs.
- *8b. Borrower side (accepted 2026-10-17).* A borrowed gotchi is untracked/pnl_excluded. Upfront GHST paid → `spend`. Revenue share and channeled alchemica while borrowing → income at FMV.
- *Gotchi pocket (confirmed).* [F, RPC gotchiEscrow(3033)] 0x728f0baf79ebdfa336978c90f244324a0ba7bcff is gotchi 3033's escrow, and the owner is the test wallet. So depositERC20 into an owned gotchi's escrow and batchTransferEscrow out are custody at `pocket:<gotchiId>`, and holdings include pockets.
- *P3 thin pools.* Price order: trade-implied → pool at block, if ≥ the liquidity floor (high/med) → Gotchi-Trader daily candle (med) → thin pool below the floor with reserves > 0 and a swap ≤ 7 days old (low, flagged) → unpriced (excluded, flagged). Store the pool's USD depth with each price. Totals are shown both with and without low-confidence prices.
- *§9 corrections (PR #5 review, 2026-10-17).* Rule 3: [F] the TransferSingle "always 1" bug is NOT on Base (re-mint 0x14f28eea, amounts equal MintInstallations), so a MintInstallations mismatch → review. Batch selectors batchCraftInstallations 0xe9332638 and batchCraftTiles 0xfdc6d919 are live and count as craft. Queue refs are per leg and contract-scoped. reduceCraftTime GLTR burned to 0x0 is craft cost. Rule 2: a real buy-now emits both BoughtNow and ItemClaimed, so auctions are de-duplicated. Rule 7: borrower or operator revenue claims → income for the lender, matched via the lending state, not wallet topics. Rule 9: bounce-gate updates (GLTR to 0xFFfF) are also spend. Rule 10: 0xeae2fb93 is the Aerodrome FUD/GHST **pool**, not a router; add-liquidity disposes the inputs at the block price and the LP token is untracked.
