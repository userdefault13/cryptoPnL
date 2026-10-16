# cryptoPnL: Design Document (v1.0, draft for approval)

Owner: user_default · Repo: github.com/userdefault13/cryptoPnL (empty, `main`) · Status: **design only, no build until approved**

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
5. **Polygon pre-migration basis (still open):** nothing indexes Polygon. Should Polygon history be pulled via RPC plus explorer, or should migrated assets enter at fair value on migration day (2025-07-25)?
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
