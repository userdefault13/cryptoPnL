# cryptoPnL: Envio (HyperIndex) Token Backfill Indexer, Base-first (design v0.8)

Owner: user_default · Status: **design only (approved to design). No build, no repo changes, nothing run on the M1.**
Changelog: v0.8 (2026-10-16): **No Goldsky.** The HyperSync budget is approved at 15/min (M1 8 + omarchywin 7), and §5b option A is confirmed. Free RPC primary = **base.drpc.org** (archive `eth_call`; `getLogs` ≤ 100 blocks), with mainnet.base.org secondary. AarcadeGh$t is used for point lookups only. Marketplace (Baazaar/GBM) events may be added to this stack later (DESIGN §1.4).
Changelog: v0.7 (2026-10-15): **No paid RPC, no Alchemy, no Etherscan** (user_default; Etherscan v2 deferred). Every Etherscan/`eth_getLogs` history path is replaced by HyperSync, and the free public RPC `mainnet.base.org` handles spot/at-block `eth_call`, `balanceOf` and receipts (tested). Internal ETH is a **known gap**, since traces are a paid HyperSync add-on and the public RPC rejects debug/trace. Public-RPC limits and backoff are added, and the per-address ETA depends on the pending split. §5c supersedes earlier Etherscan/RPC mentions.
Changelog: v0.6 (2026-10-15): **Builder P0 measured HyperSync at about 15 queries/min for the whole account** (15,000 per 60s at 1,000 per query), not 29. Proposed split: M1 8 + omarchywin 7 = 15, with 429 backoff and coupled caps. ETAs recomputed at 7 RPM. **The traces dependency is removed** (likely unsupported on Base); internal ETH comes from Etherscan v2 `txlistinternal`. Every 29/18/10 RPM figure below is superseded by §5b.
Changelog: v0.5 (2026-10-15): **No M1 dependency except the proxy entry.** omarchywin gets its own local hypersync-throttle (10 RPM, localhost plus docker bridge only). The M1 throttle bind/ACL change and the forward option are removed. The token comes from omarchywin's own abra. ETA is recomputed at 10 RPM, and the first build steps are updated. Earlier "18 RPM shared / 10–15 RPM ours" figures are superseded by §5a.
Changelog: v0.4 (2026-10-15): **Host moved from omarchyM1 to omarchywin** (real facts below). RAM caps recomputed. HyperSync is routed through the M1's shared throttle over Tailscale. The M1 proxy routes to omarchywin's Hasura. abra/token injection and prerequisites added. §4–5 M1 hosting text is superseded by §5a, but the M1 baseline blocks still apply.
Changelog: v0.3 (2026-10-15): There is no static wallet list, so a **hybrid** is chosen. Full Transfers are indexed for GHST, the alchemica tokens and GLTR. USDC/WETH/cbBTC are fetched per address on demand via HyperSync through the throttle and cached. WETH/cbBTC are priced by RPC `slot0` at the tx block, and their pools are not indexed (OQ resolved).
Changelog: v0.2 (2026-10-15): Added M1 facts from Home Infra CoS (resources, ports, pre-change blocks). The local limiter is replaced by the shared `hypersync-throttle` (18 RPM). ETA recomputed, memory limits added, Gotchi-Trader candle access detailed, open questions narrowed.

Package name: `cryptopnl-tokens-base`. Starting point: `~/Dev/aavegotchi-envio-indexers/docs/GOTCHI_TRADER_UNISWAP_V3_OUTLINE.md` on the MBP (read-only). This design reuses its conventions: HyperSync primary, RPC fallback, a dedicated Postgres + Hasura per package, and a Graph-style proxy path.
Verification: all addresses, decimals, pools and deploy blocks below were checked on 2026-10-14 against **Base mainnet RPC** (`mainnet.base.org`). Checks used `symbol()/decimals()`, Uniswap V3 `factory.getPool`, Aerodrome `PoolFactory.getPool(a,b,stable)`, `balanceOf(pool)` for reserves, and a binary search over `eth_getCode` for deploy blocks. Base head was 52,629,471. Token addresses also match the Aavegotchi wiki and `aavegotchi/deployed-contract-addresses`. The scripts are in `/workspace/cryptoPnL/verify/`.

## 1. Contracts and start blocks
### 1.1 Tokens (Base 8453)
| Token | Address | Dec | Deploy block (verified) | Notes |
|---|---|---|---|---|
| USDC (quote) | `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` | 6 | 2,797,221 | Native USDC |
| WETH | `0x4200000000000000000000000000000000000006` | 18 | genesis (predeploy) | Native ETH is handled separately (§3.4) |
| cbBTC (WBTC stand-in) | `0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf` | 8 | 18,688,094 | |
| GHST | `0xcD2F22236DD9Dfe2356D7C543161D4d260FD9BcB` | 18 | 12,631,572 | OP-bridged ERC20, about 1,252 transfers/24h (Basescan) |
| FUD | `0x2028b4043e6722Ea164946c82fe806c4a43a0fF4` | 18 | 34,095,837 | About 37 transfers/24h, 273 holders (Basescan) |
| FOMO | `0xA32137bfb57d2b6A9Fd2956Ba4B54741a6D54b58` | 18 | 34,095,847 | |
| ALPHA | `0x15e7CaC885e3730ce6389447BC0f7AC032f31947` | 18 | 34,095,858 | |
| KEK | `0xE52b9170fF4ece4C35E796Ffd74B57Dec68Ca0e5` | 18 | 34,095,868 | |
| GLTR | `0x4D140CE792bEdc430498c2d219AfBC33e2992c9D` | 18 | 34,095,879 | |

The Uniswap V3 Factory `0x33128a8fC17869897dcE68Ed026d694621f6FDfD` deployed at **block 1,371,680. This is exact and confirms the outline's "~1371680"**. Aerodrome PoolFactory `0x420DD381b31aEf6683db6B902084cB0FFECe40Da` has code, and its `getPool` returned the pools below. Its own deploy block was not measured, and it isn't needed because we index pools directly.

### 1.2 Pools (only those that exist; reserves are a snapshot on 2026-10-14)
| Pair | Venue / fee | Pool | Deploy block | Reserves | Index? |
|---|---|---|---|---|---|
| WETH/USDC | Uni V3 0.05% | `0xd0b53d9277642d899df5c87a3966a349a798f224` | 3,620,407 | 2,853 WETH / 2.12M USDC | **Price ref** |
| WETH/USDC | Uni V3 0.30% | `0x6c561b446416e1a00e8e93e221854d6ea4171372` | 6,748,901 | 45,480 WETH / 35.9M USDC | Optional |
| WETH/USDC | Aerodrome volatile | `0xcdac0d6c6c59727a65f871236188350531885c43` | 3,647,441 | 1,876 WETH / 4.41M USDC | Optional |
| WETH/USDC | Uni 0.01% / 1% , Aero stable | `0xb4cb8009…00e5` / `0x0b1c2dcb…2d69` / `0x35480296…5f16` | – | small | No |
| cbBTC/USDC | Uni V3 0.05% | `0xfbb6eed8e7aa03b138556eedaf5d271a5e1e43ef` | 19,763,050 | 55.0 cbBTC / 5.16M USDC | **Price ref** |
| cbBTC/USDC | Uni V3 0.30% | `0xec558e484cc9f2210714e345298fdc53b253c27d` | 19,647,450 | 22.1 / 1.03M | Optional |
| cbBTC/USDC | Aerodrome volatile | `0x9c38b55f9a9aba91bbcedeb12bf4428f47a6a0b8` | 19,684,196 | 1.6 / 130k | No |
| cbBTC/WETH | Uni V3 0.05% / 0.30% | `0x7aea2e8a3843516afa07293a10ac8e49906dabd1` / `0x8c7080564b5a792a33ef2fd473fba6364d5495e5` | 19,725,858 / 19,647,414 | 17.6/6,921 WETH ; 38.3/3,033 WETH | Optional |
| **GHST/WETH** | **Aerodrome volatile** | `0x0dfb9cb66a18468850d6216fcc691aa20ad1e091` | 13,295,275 | **1.62M GHST / 43.0 WETH** | **Yes (GHST price ref)** |
| GHST/WETH | Uni V3 0.30% | `0x873d3c477bbaed55859c46e43fdac6e73120f80c` | 13,267,442 | 265 GHST / 0.0076 WETH | No (dust) |
| GHST/USDC | Aerodrome volatile | `0x8263c80ba82ffb3506eb731dca78546244ce2fc6` | 13,292,351 | 5.6 GHST / 0.36 USDC | No (dust) |
| **FUD/GHST** | Aerodrome volatile | `0xeae2fb93e291c2eb69195851813de24f97f1ce71` | 34,402,583 | 99.2M FUD / 5,297 GHST | **Yes** |
| **FOMO/GHST** | Aerodrome volatile | `0x62ab7d558a011237f8a57ac0f97601a764e85b88` | 34,402,633 | 43.5M / 6,424 GHST | **Yes** |
| **ALPHA/GHST** | Aerodrome volatile | `0x0ba2a49aedf9a409dbb0272db7cdf98aeb1e1837` | 34,402,659 | 21.9M / 6,371 GHST | **Yes** |
| **KEK/GHST** | Aerodrome volatile | `0x699b4eb36b95cdf62c74f6322aaa140e7958dc9f` | 34,402,689 | 8.67M / 4,946 GHST | **Yes** |
| **GLTR/GHST** | Aerodrome volatile | `0xa83b31d701633b8edcfba55b93ddbc202d8a4621` | 34,402,771 | 37.8B / 15,940 GHST | **Yes** |
| GLTR/WETH | Aerodrome volatile | `0x0598324b679e62c042e718b193d1403bdc060704` | 50,722,776 | dust WETH | No |

**Key finding:** GHST and alchemica have **no Uniswap V3 pools with real liquidity against USDC or WETH**. Their liquidity is on **Aerodrome**: GHST/WETH, and each alchemica token paired with GHST. So Aerodrome is required, not optional, and the price paths are `alchemica → GHST → WETH → USDC` and `GHST → WETH → USDC`. Aerodrome Slipstream (CL) pools were **not checked** (OQ 4). Price data was also checked against Basescan: GHST is about $0.0625.

## 2. Entities (every event row carries `chainId, txHash, blockNumber, blockHash, timestamp, logIndex`; id = `chainId-txHash-logIndex`)
```graphql
type Token { id: ID!  address: String!  symbol: String!  decimals: Int!  startBlock: Int! }
type Pool  { id: ID!  venue: String!  # univ3|aero_v2
  token0: Token!  token1: Token!  feeTier: Int  stable: Boolean  createdBlock: Int!
  lastSqrtPriceX96: BigInt  lastReserve0: BigInt  lastReserve1: BigInt  lastBlock: Int }
type TokenTransfer @index(fields:["from","to"]) { id: ID!  token: Token!  from: String!  to: String!
  value: BigInt!  isMint: Boolean!  isBurn: Boolean!  trackedSide: String!  # from|to|both
  chainId: Int!  txHash: String!  blockNumber: Int!  blockHash: String!  timestamp: Int!  logIndex: Int! }
type Swap { id: ID!  pool: Pool!  sender: String!  recipient: String!  amount0: BigInt!  amount1: BigInt!
  sqrtPriceX96: BigInt  tick: Int        # univ3 only
  price0In1: BigDecimal!  priceUSDC0: BigDecimal  priceUSDC1: BigDecimal
  chainId: Int!  txHash: String!  blockNumber: Int!  blockHash: String!  timestamp: Int!  logIndex: Int! }
type AccountBalance { id: ID!  # account-token
  account: String!  token: Token!  balance: BigInt!  lastTxHash: String!  lastBlockNumber: Int!  lastLogIndex: Int! }
type HourlyPrice { id: ID!  # token-hourEpoch (optional)
  token: Token!  hour: Int!  openUSDC: BigDecimal!  highUSDC: BigDecimal!  lowUSDC: BigDecimal!  closeUSDC: BigDecimal!
  volumeToken: BigDecimal!  swapCount: Int!  sourcePool: String!  lastBlockNumber: Int! }
```

## 3. Handler logic
1. **Scope (v0.3, hybrid, see §3a):** the Envio stack indexes **all** `Transfer` events of GHST, FUD, FOMO, ALPHA, KEK and GLTR (small tokens), plus `Swap`/`Sync` on the 6 Aerodrome pools. USDC, WETH and cbBTC transfers are **not** indexed by Envio. They are fetched per address on demand (§3a).
2. **Transfer handler:** upsert `TokenTransfer`. Set `isMint/isBurn` for `0x0`. Apply ±value to `AccountBalance` (all holders of the 6 small tokens). Envio rolls back on reorg (with rollback-on-reorg enabled), so balances stay consistent.
3. **Swap handler:** Uni V3 `Swap(sender,recipient,int256,int256,uint160,uint128,int24)` → price from `sqrtPriceX96`. Aerodrome V2 `Swap(sender,to,amount0In,amount1In,amount0Out,amount1Out)` → execution price from the amounts, plus `Sync(reserve0,reserve1)` → spot price. Pricing order: USDC pair → direct. WETH pair → × the latest WETH/USDC price (from the ref pool, same block or earlier). GHST pair → × the latest GHST/USDC price. Write `priceUSDC*` and update `HourlyPrice` (OHLC per token per hour, taken from the designated ref pool only).
4. **Native ETH:** ETH moves are not logs. (v0.6, **no traces**) Use HyperSync `transactions` selection (`from` or `to` = address, `value > 0`) plus receipts for gas = `gasUsed × effectiveGasPrice` + Base L1 fee. **Internal ETH** (sent by contracts, e.g. router unwraps, refunds) is a known gap in tx data. (v0.7: **known gap**, no Etherscan, see §5c.) Most DEX ETH flows are WETH and are already covered by WETH `Transfer`/`Deposit`/`Withdrawal`. WETH `Deposit/Withdrawal` events are indexed to link ETH↔WETH wraps.
5. **Dynamic pools:** no factory scanning. The pool list is static config (table 1.2), which avoids millions of `PoolCreated`/irrelevant pools.

## 3a. Wallet indexing without a static list (v0.3 decision)
Wallets are dynamic: the address connected on the site plus any address the user types in (DESIGN §1.3). Options:
| Option | Rows / disk | ETA under 18 RPM shared (≈10–15 RPM ours) | Verdict |
|---|---|---|---|
| (a) Index all Transfers for all 9 tokens | WETH and USDC on Base are among the busiest contracts on the chain. That is plausibly **hundreds of millions to billions** of Transfer rows (unverified; P0 count query). At about 0.6 KB/row that's ≥ 100s of GB, against 363 GB free and 3.2 GiB RAM | Dense pages: thousands to tens of thousands of requests → **days** | **Rejected**: disk, RAM and the shared throttle can't absorb it |
| (b) Per-address HyperSync on demand for every token | Only the user's rows | Per new address: one query with all 9 tokens' Transfer logs, topic1 = addr OR topic2 = addr, plus transactions from/to the address. Sparse, about 210 requests pessimistic → **≈ 14–21 min**, often minutes | Works, but repeats work Envio does cheaply for the small tokens, and gives no holder-wide data for GHST/alchemica |
| **(c) Hybrid (chosen)** | Envio: full GHST + alchemica + GLTR transfers about **2–2.4M rows** + 6 Aero pools' swaps about 0.1–0.5M → **about 2.5–3M rows, ≈ 1.5–3 GB** (6 GB reserved, unchanged). On-demand cache: about 1–50k rows per address | Envio backfill ≈ **1.5–2.3 h** pessimistic, one time (the §4 numbers minus the dropped wallet streams). Per new address: USDC/WETH/cbBTC + native ETH ≈ **≈ 14–21 min pessimistic** HyperSync, (v0.7: no Etherscan; first view = progressive HyperSync results, §5c) | **Recommended** |

**Why (c):** the 6 small tokens are cheap to index fully, and having them all means any newly added address gets its GHST/alchemica history **instantly** from Hasura with no backfill. Only the 3 huge tokens need per-address work, which fits the shared 18 RPM because it is bursty and per user action.

**On-demand backfill worker (app backend, not Envio):** triggered when a wallet is added (DESIGN §1.3). (1) (v0.7) Instant first view from the Envio stack (GHST/alchemica/GLTR), then progressive HyperSync pages for the rest (§5c). (2) HyperSync query through the throttle `:8797` (token = abra `aavegotchi-envio-indexers/ENVIO_API_TOKEN`), with log filters for USDC/WETH/cbBTC `Transfer` where topic1 or topic2 = address, WETH `Deposit/Withdrawal`, and transactions from/to the address for native ETH (no traces; internal ETH is a known gap, §5c). Results go to `address_cache` (Postgres in the cryptoPnL app DB, keyed `(chain_id, address, source)` with `synced_to_block`). (3) Incremental top-up on each visit from `synced_to_block`. (4) Results replace the provisional rows, with reorg safety via `blockHash` as in DESIGN §1.2. Concurrency: **1 on-demand job at a time**, a queue with a position indicator, and a per-user cap (e.g. 5 new addresses/hour) to protect the shared throttle.

## 4. Sizing, M1 RAM/disk, and sync ETA
**Real counts:** HyperSync returned **401 Unauthorized without a token**, and the public RPC rate-limited `eth_getLogs` sampling, so whole-history counts were **not obtained**. Basescan 24h figures were: GHST ≈ 1,252/day, FUD ≈ 37/day. **Method:** in P0, run a HyperSync count query per contract with the abra token (through the throttle; v0.6 budget ≤ 15/min account-wide), selecting only `block_number`. Until then, estimates are 24h rate × days since deploy, then doubled:
| Stream | Estimate | Rows |
|---|---|---|
| Per-address on-demand (USDC/WETH/cbBTC, app DB, not Envio) | 1–50k per address | per address |
| GHST full transfers (**indexed**, v0.3) | 1,252/day × ~730 d ×2 | ≈ 1.8M |
| Alchemica + GLTR full transfers (**indexed**, v0.3) | ~40–300/day each × ~440 d | ≈ 0.2–0.6M |
| Swaps, 5 alchemica/GHST Aero pools + GHST/WETH | low hundreds/day total (unverified) | ≈ 0.1–0.5M |
| Swaps, WETH/USDC 0.05% + cbBTC/USDC 0.05% (ref pools) | likely tens of millions (unverified) | **excluded by default** |

**Ref-pool decision:** do **not** index the full swap history of the WETH and cbBTC USDC pools. For cryptoPnL's point-of-buy/sell prices, (a) use the trade itself when a wallet swap is against USDC, or (b) read the ref pool `slot0` at that tx block through remote RPC (DESIGN §2 step 2). **Decided (v0.3): WETH and cbBTC are priced by an RPC `slot0` read of the Uni V3 0.05% ref pool (`0xd0b5…f224` / `0xfbb6…43ef`) at the tx block, and these pools are not indexed.** Gotchi-Trader's planned `uniswap-v3-base` indexer can supply hourly prices later if ever needed.

**Budget (default scope, ~2.5M rows at ~0.6 KB/row including indexes and Envio history tables):** Postgres disk ≈ **1.5–3 GB**, plus 2× headroom → reserve **6 GB**. RAM: indexer ≈ 0.5–1 GB, Postgres about 0.5 GB, Hasura ≈ 300 MB → **about 2 GB steady before limits**. See the RAM verdict below for the capped budget.

**RAM verdict (M1: 7.2 GiB RAM, 3.2 GiB available, 7.2 GiB swap barely used, 363 GB free disk):** disk is ample (6 GB reserve is under 2% of free). RAM is **tight**: about 2 GB steady against 3.2 GiB available leaves about 1.2 GiB headroom for the host and the existing stacks' spikes. **Recommended hard limits** in compose: `postgres` `mem_limit: 768m` with `shared_buffers=256MB`, `work_mem=8MB`, `maintenance_work_mem=64MB`, `effective_cache_size=512MB`, `max_connections=20`. `envio-indexer` `mem_limit: 1g` (Node `--max-old-space-size=768`, keep the Envio batch size modest). `hasura` `mem_limit: 384m`. **Total cap ≈ 2.15 GiB**, leaving ≥ 1 GiB free. Swap provides a safety margin, but sustained swapping is a stop condition. Run the backfill while other heavy jobs are idle, and watch `free -m` and `docker stats` during P1/P2.

**Rate limit (resolved):** Envio **2.26.0-rc.2 has no rate-limit config**. The cap is enforced by the shared host proxy **`hypersync-throttle.service`** (`~/Dev/envio-park/services/hypersync-throttle/server.mjs`), live cap **`HYPERSYNC_RPM=18` shared across all indexers**. The planned local limiter is **dropped**. The new stack points at the throttle like the existing stacks do:
```bash
HYPERSYNC_URL_8453=http://host.docker.internal:8797     # Base mainnet via shared throttle
HYPERSYNC_URL_84532=http://host.docker.internal:8798    # Base Sepolia via shared throttle
ENVIO_API_TOKEN=<abra:cryptoPnL/ENVIO_API_TOKEN>   # P1 scripts: `abra run cryptoPnL -- ...` (copied from aavegotchi-envio-indexers)
BASE_MAINNET_RPC=<abra:base-rpc-url>                    # fallback + slot0-at-block (name to confirm)
```
(`hypersync_config.url` in config.yaml is set from `HYPERSYNC_URL_<chain>`.) (v0.6: the 29 req/min figure was wrong. The measured account limit is about 15/min, see §5b.)

**ETA (still an estimate):** backfill is about 1,370 requests (about 210 sparse wallet-stream requests + about 1,160 full GHST/pool requests, at the pessimistic page sizes above). The three caught-up stacks (monolith, gotchiverse, svg) only poll the tip, so the new stack's assumed share of the 18 RPM is **10–15 RPM** (to be measured from throttle logs in P0).
- Pessimistic pages: 1,370 / 15 ≈ **1.5 h** to 1,370 / 10 ≈ **2.3 h**
- Wallet-only scope (no full GHST/pools): 210 / 15 to 210 / 10 ≈ **14–21 min**
- If pages are larger (typical for sparse filters), minutes.
- While it backfills, it slows the other stacks' tip polling within the shared 18 RPM. Acceptable because they are caught up, but check that their `latest_processed_block` keeps advancing.

## 5. Hosting, exposure, secrets
- **Host:** omarchyM1. Docker compose: `postgres` + `hasura` + `envio-indexer`. No limiter container; it uses the shared throttle. **Ports in use** (Home Infra CoS): 22, Hasura 8081/8083/8084, Postgres 5435 (all interfaces) and 5436/5437 (localhost), proxy `100.100.99.27:8787` and `127.0.0.1:8786`, HyperSync throttle 8797 (8453) / 8798 (84532), 4096, 631. **Proposed (free):** Postgres **`127.0.0.1:5438`** and Hasura **`8085`** for mainnet. Sepolia staging uses Postgres `127.0.0.1:5439` and Hasura `8086`. These are proposals, re-checked with `ss -ltn` immediately before deploy.
- **No second Cloudflare tunnel.** Add `cryptopnl-tokens-base` as a new **allowed name** in the existing `aarcade-subgraph-api` proxy → `https://subgraph.aarcadeghst.com/subgraphs/name/cryptopnl-tokens-base` (Tailscale `100.100.99.27:8787`), with the same `Authorization: Bearer <abra key>` auth and the same limits (about 60 req/min, `first ≤ 1000`, depth about 8, read-only). The proxy routes to M1 Hasura over Tailscale.
- **Secrets:** the token comes from **omarchywin's own abra**: user_default unlocks abra on omarchywin and copies `aavegotchi-envio-indexers/ENVIO_API_TOKEN` into it. It is referenced by **name only** and injected at start into the throttle unit's environment (e.g. an abra-wrapped `ExecStart` or a tmpfs env file), never committed or logged. RPC: `base-rpc-url` by name, in the same vault.
**Prerequisites:** Tailscale up ✅ (100.72.80.69). Docker ✅ (29.7.2). abra binary ✅. Token in omarchywin's vault ❓ (user_default). Throttle unit installed ❓. Ports 5438/8085/8797/8798 free ✅ (re-check). Proxy allow-list entry on the M1 (with approval).
**Baseline:** the M1 pre-change `latest_processed_block` (monolith 52,629,701, gotchiverse 52,629,698, svg 52,629,696) is kept for reference. The only M1 touch is the proxy entry, so after adding it, confirm those stacks still advance and the proxy still serves their names. Rollback: on omarchywin, `docker compose -p cryptopnl-tokens-base down` and `systemctl --user disable --now hypersync-throttle`. On the M1, remove the proxy entry.

## 5b. HyperSync budget (v0.6, supersedes every 29/18/10 RPM figure above)
**Measured (builder P0):** the HyperSync account sustains about **15 queries/min total** (about 15,000 rows per 60s at 1,000 per query), **shared across all stacks**. The earlier "29 req/min" figure (from the task rules and the agent instruction to cap at 29) is **higher than the real limit**. Treat **15 as the ceiling** and note that the agent rule should be updated. Current config, M1 18 + omarchywin 10 = 28, **exceeds it**.

**Proposed split (sum ≤ 15):**
| Option | M1 | omarchywin | Notes |
|---|---|---|---|
| **A (approved 2026-10-16)** | **8** | **7** | The M1 stacks (monolith, gotchiverse, svg) are caught up and only poll the tip; 8 RPM is ample |
| B | 10 | 5 | Safer for the M1, slower cryptoPnL backfill |
Changing the M1 cap (18 → 8) is **Home Infra CoS's call and needs user_default's approval**. **Both caps change together**, always keeping M1 + omarchywin ≤ 15. Both throttles must also **back off on HTTP 429**: honor `Retry-After`, otherwise exponential backoff with jitter starting at 4s, and lower the effective rate for 5 minutes after a 429.

**ETAs at omarchywin = 7 RPM (estimates):** full Envio backfill ≈ 1,370 / 7 ≈ **3.3 h**. Per address ≈ 210 / 7 ≈ **30 min** pessimistic (v0.7: no Etherscan; depends on the pending HyperSync split). Option B (5 RPM): ≈ 4.6 h / 42 min.
**Alternative, a one-time temporary boost:** during the initial backfill, while the M1 stacks are caught up, set M1 3 + omarchywin 12 (sum 15). The backfill drops to ≈ 1,370 / 12 ≈ **1.9 h**, then reverts to 8 + 7. This needs the same Home Infra and user_default approval, a scheduled window, and a check that the M1 stacks' `latest_processed_block` keeps advancing during the window.

## 5c. No paid RPC, no Etherscan (v0.7, supersedes earlier Etherscan/RPC mentions)
**Decision (user_default, 2026-10-15):** no paid Base RPC, no Alchemy, no Etherscan (v2 deferred).
- **History = HyperSync only**, on the existing token (abra `aavegotchi-envio-indexers/ENVIO_API_TOKEN`) through the local throttle. Covers transfers, swaps, WETH deposit/withdrawal and wallet transactions (`from`/`to` = address, incl. `value`, `gasUsed`, `effectiveGasPrice` and L1 fee fields where HyperSync exposes them; otherwise from receipts via RPC).
- **Per-address "first view":** no longer "seconds via Etherscan". GHST/alchemica/GLTR show **instantly** from the Envio stack. USDC/WETH/cbBTC/ETH stream in **progressively**: the HyperSync job writes each page as it lands, with a "syncing…" banner and a `synced_to_block` progress bar.
- **Free RPC (v0.8)** = `https://base.drpc.org` primary (archive `eth_call` works, `eth_getLogs` ≤ 100 blocks, last-resort gap fill only) + `https://mainnet.base.org` secondary for spot calls (and `https://sepolia.base.org` for staging), for spot and at-block `eth_call` (`slot0`, `balanceOf`) and `eth_getTransactionReceipt`. Never used for log history.

**Free public RPC test (read-only, 2026-10-15 PT, `https://mainnet.base.org`):** `eth_call` at **old blocks works**. `slot0()` on the WETH/USDC 0.05% pool returned state at blocks 4,000,000 and 30,000,000. GHST `balanceOf(pool)` returned at block 20,000,000. `eth_getCode` at block 1,371,680 worked earlier. So historical state **was served for these sample calls**, but Base docs give **no archive guarantee and no numeric limit** ("rate-limited, not suitable for production"; HTTP only, no WebSocket). `debug_traceTransaction`, `debug_traceBlockByNumber` and `trace_block` were **rejected** ("rejected due to request filter settings"). Earlier, `eth_getLogs` hit "request limit reached". `base-rpc.publicnode.com` refused historical requests ("Archive requests require a personal token"). Other free endpoints (`sepolia.base.org` for testnet) are documented. No others are assumed.

**Archive fallback** (if at-block calls start failing, e.g. "missing trie node", or are throttled): (1) **price from indexed swaps**: for GHST/alchemica, the Envio Aerodrome `Swap`/`Sync` at or before the block. For WETH/cbBTC, (2) **nearest-block approach**: use the trade itself when the wallet swap is against USDC. Otherwise use the nearest available `slot0` (retry at the head-side block that the node serves) and flag `confidence` lower with the block distance recorded. Then (3) the Gotchi-Trader daily candle (§8), low confidence. Historical balances, if at-block `balanceOf` fails, are **replayed from indexed transfers** (Envio and the per-address cache), with at-block `balanceOf` as a spot-check only.

**Public-RPC budget and backoff:** no documented numeric limit, so be conservative. Use a single client-side token bucket on omarchywin for `mainnet.base.org`, **≤ 2 req/s sustained, burst 5**, concurrency 2. Use JSON-RPC batching of ≤ 10 calls. On HTTP 429 / JSON-RPC `-32011 request limit reached` / 5xx: honor `Retry-After`, otherwise exponential backoff with jitter (1s → 60s), and halve the rate for 5 minutes. Cache every at-block result in `price_point` (immutable once finalized) so each (pool, block) is fetched once. Typical load is a few calls per wallet trade (receipt + 1–2 `slot0`), which is small.

**Internal ETH: known gap.** HyperSync traces on Base are a **paid add-on, access on request** (`base-traces.hypersync.xyz`, from block 24,000,000; Envio docs), so they are excluded by the no-paid rule. The public RPC rejects `debug_*`/`trace_*` (tested). With no Etherscan, there is **no free replacement**. **Mitigation:** (a) WETH `Transfer`/`Deposit`/`Withdrawal` cover most DEX flows, since routers mostly trade WETH. (b) Top-level tx `value` plus receipts cover direct ETH sends and gas. (c) A reconciliation check compares the ETH balance replayed from known flows with `eth_getBalance` at block (public RPC). Any mismatch is posted as an `unexplained_eth` ledger adjustment, flagged for review, at fair value. **Impact (qualitative):** small for typical use. It misses ETH received from contracts, such as router "swap to native ETH" unwraps that don't emit WETH `Withdrawal` to the user, refunds, bridge/claim payouts, and multisig/smart-wallet internal sends. Those can understate ETH acquisitions (missing lots, so later sells show inflated gains) until reconciled. Smart-wallet users (ERC-4337) are most affected, since their ETH moves are often internal. Revisit if Etherscan or paid traces are allowed later.

**Per-address ETA:** ≈ 210 HyperSync requests ÷ omarchywin's cap. **This depends on the pending HyperSync split** (§5b): 7 RPM ≈ 30 min, 5 RPM ≈ 42 min, both pessimistic estimates.

## 6. Staging and rollout
1. **P0 first steps (v0.5, omarchywin):** (a) user_default unlocks abra on omarchywin and copies `aavegotchi-envio-indexers/ENVIO_API_TOKEN`. (b) Install the copied `hypersync-throttle` as a user systemd unit (127.0.0.1 + 172.17.0.1, `HYPERSYNC_RPM=10`) and check that `ss -ltn` shows only those binds. (c) Re-check that ports 5438/8085/8086/5439/8797/8798 are free. Then the **pre-flight (read-only):** the snapshot, resources, ports and Envio version are done (§4–5). Remaining: run HyperSync count queries through the throttle, measure the RPM the existing stacks actually use from throttle logs, (Traces: dropped in v0.6, likely unsupported on Base.) *Done when* real counts and measured headroom replace the estimates in §4.
2. **P1 Base Sepolia:** same package, `networks: [84532]`, pointed at Base Sepolia test tokens/pools (Aavegotchi lists Base Sepolia contracts in its wiki, but addresses for this list and the Sepolia Uniswap/Aerodrome deployments are **unverified**, see the OQ 3 proposal). Exposed as `cryptopnl-tokens-base-sepolia` through the proxy. *Done when* it is synced to head, a forced reorg test (or a Sepolia natural reorg) leaves balances = `balanceOf`, the throttle logs show the shared total ≤ 18 RPM, and the existing stacks' `latest_processed_block` still advances.
3. **P2 Base mainnet:** deploy with the default scope. *Done when* the sync completes, wallet `AccountBalance` = RPC `balanceOf` at head and at 3 historical blocks, 20 sampled swap prices fall within ±2% of DefiLlama/CoinGecko, and the proxy name answers with the Bearer key.
4. **P3:** optional full-GHST transfers and HourlyPrice, and wiring into cryptoPnL ingest.

**Rollback:** the new stack is isolated (own compose project, volume and ports). Rollback = remove the proxy allow-list entry, then `docker compose -p cryptopnl-tokens-base down` (keep the volume for forensics, or drop it). Then confirm every existing stack's `latest_processed_block` is still ≥ the P0 snapshot and advancing. No existing stack's config is touched, so there is nothing to revert there.

## 7. How it plugs into DESIGN.md
- Replaces DESIGN §1 **S2/S3 transfer and swap backfill** (RPC `eth_getLogs` + Etherscan; v0.7: both dropped) for the tracked tokens. cryptoPnL ingest reads `TokenTransfer`/`Swap` through the proxy name, joins by `txHash`, and keeps `blockHash` for reorg checks.
- **Still on the free public RPC (v0.7):** receipts (gas, L1 fee), `balanceOf`/`slot0` at a block. Untracked tokens' history goes through HyperSync. Internal ETH is a known gap (§5c).
- Pricing (DESIGN §2): `Swap.priceUSDC*` at the tx block is the "pool-at-block" source for GHST and alchemica. For WETH/cbBTC, use the trade itself or RPC `slot0` at the block. API fallback is unchanged.

## 8. Later phase (not in scope now)
- **Polygon history** (pre-2025-07-25 Aavegotchi era: deprecated Polygon GHST and alchemica addresses are in the wiki) and **Ethereum mainnet WBTC/ETH**. Same package pattern per chain, same limiter.
- **Fallback price:** **daily Coinbase candles** from Gotchi-Trader on the 2011 machine (WBTC from 2015, ETH from 2018), used when no on-chain price exists at the block. Confidence is low (daily granularity). Source: **Gotchi-Trader Postgres on the 2011, `127.0.0.1:5434`, db `gotchi_trader`, table `candles`** (`chain_id, symbol, source, pool_address, interval` (default `'1d'`), `open_time`, `open, high, low, close, volume, volume_usd`; PK `(chain_id, source, symbol, interval, open_time, pool_address)`).
  **Read-only access:** create a dedicated role `cryptopnl_ro` with `CONNECT` on `gotchi_trader`, `USAGE` on the schema, `SELECT` on `candles` only, and `default_transaction_read_only=on`. Its password goes in abra (proposed name `gotchi-trader/CRYPTOPNL_RO_PG_URL`). It binds to localhost, so cryptoPnL reaches it via an SSH tunnel or a Tailscale-only port forward to the 2011 (no new public exposure). Query: `SELECT close FROM candles WHERE chain_id=$1 AND symbol=$2 AND interval='1d' AND open_time <= $ts ORDER BY open_time DESC LIMIT 1`, using `source`='coinbase' (exact value to confirm when reading). Stored as `price_source='gotchi_trader_candle_1d'`, low confidence. The role creation is a change on the 2011 and needs user_default's approval at that time.

## 9. Open questions
**Resolved in v0.2:** M1 resources, ports and per-stack blocks (§4–5); Envio version and rate limiting (shared throttle, 18 RPM); HyperSync token name (`aavegotchi-envio-indexers/ENVIO_API_TOKEN`); candle source location and schema (§8). Traces support is folded into P0.

**Resolved in v0.3:** wallet indexing = hybrid (§3a); WETH/cbBTC = `slot0` at the tx block, pools not indexed.

**Still open:**
0. (v0.5) Is the ENVIO token copied into omarchywin's abra yet? And who records the cap-coupling rule on the M1 throttle side (Home Infra CoS)?
1. Base Sepolia staging addresses (proposal: mock ERC20s + one Uniswap V3 pool on Uniswap's official Base Sepolia deployment, addresses to verify first).
2. Aerodrome Slipstream (CL) pools for GHST/alchemica/cbBTC are not checked yet.
3. Real Transfer counts for WETH/USDC/cbBTC, to confirm the rejection of option (a), and the actual pages per address (P0, via the throttle).
