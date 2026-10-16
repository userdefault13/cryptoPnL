# P0 Introspection Report (rerun 2026-10-15 ~15:30 PT, Julius's MBP, branch p0-introspection, read-only)
Docs: DESIGN.md **v0.6**, ENVIO_TOKEN_INDEXER.md **v0.5** (copied from the box; repo was empty, so nothing was overwritten). §4 = DESIGN.md "P0 Spike" done-when.

## Keys (MBP env + ~/.zshrc, presence only)
Missing: AarcadeGh$t bot key (abra API key), Base archive RPC key, Etherscan v2 key, HyperSync/ENVIO_API_TOKEN. Secrets are held in abra (not unlocked).

## Probes (all keyless)
- **Proxy auth (PR #46): PASS.** `POST aarcadeghst.com/api/subgraph/{aavegotchi-core-base,aavegotchi-gbm-baazaar-base}` without auth → **401** `unauthorized: Authorization: Bearer <wallet JWT or abra API key> required`. (Earlier box run: 200 with no auth.)
- **S1b Goldsky (public):** both subgraphs 200, `_meta` block ≈52656817, no rate-limit headers.
- **S2 public RPC (mainnet.base.org):** eth_blockNumber OK (0x3237aab). eth_getLogs returns -32011 "request limit reached" for **every** range, including 1 block → getLogs effectively unavailable on the public endpoint; archive provider required.
- **S3 Etherscan v2 keyless chainid=8453:** NOTOK "Free API access is not supported for this chain" → paid plan required.
- **HyperSync:** `base.hypersync.xyz/height` 200, height 52656815. Queries need a token.

## Entity map (from the earlier box run; authenticated re-check blocked)
| Entity | tx hash | cursor candidate |
|---|---|---|
| ERC721Listing | no | blockCreated / timeCreated |
| ERC1155Listing | no | timeCreated |
| ERC1155Purchase | no | timeLastPurchased |
| ERC721BuyOrder | no | createdAt / executedAtBlock |
| ERC1155BuyOrder | no | createdAt |
| ERC1155BuyOrderExecution | no | none (db_write_timestamp/id) |
| Auction | no | createdAt |
| Bid | no | bidTime |
| Auction_BidPlaced / _BoughtNow / _ItemClaimed | transaction_id | timestamp |

## Keyed rerun (2026-10-15 ~21:35 PT, `abra run cryptoPnL -- python3 verify/keyed.py`)
abra project `cryptoPnL` holds BASE_RPC_URL (from AarcadeGh-t JUICEBOX_RPC_BASE) and ENVIO_API_TOKEN (from aavegotchi-envio-indexers). Values were piped through, never printed.
- **Keyed RPC (Alchemy base-mainnet): DEAD.** HTTP 403 `-32600 "App is inactive. Please create a new app"`. A new Alchemy app/key is needed.
- **Archive (public mainnet.base.org fallback): YES for state.** eth_call GHST totalSupply at blocks 3,000,000 / 10,000,000 / head-1000 OK; eth_getBalance at block 1000 OK.
- **eth_getLogs (public):** HTTP 429 -32011 "request limit reached" for every range from 1k to 500k → max range unknown until a working keyed RPC exists.
- **S1 receipts: 10/10 PASS.** The 10 latest Goldsky GBM `transactions` (blocks 52417714–52441393) resolve via eth_getTransactionReceipt; receipt blockNumber = subgraph blockNumber; blockHash captured.
- **HyperSync (token): PASS.** 5 real queries (GHST Transfer logs, last 200k blocks): all 200, ~1.0–1.4 s each, 5,060 logs over ~40k blocks scanned. Headers: `x-ratelimit-limit: 15000;w=60`, `x-ratelimit-cost: 1000` per query → **≈15 queries/min budget per token** (shared with the existing stacks: remaining was 7000 after our 5, so about 3000 was used elsewhere in the window). This is below the 29 req/min cap. The ENVIO doc's 18 RPM throttle assumption should be revised to ≤15.
- **HyperSync traces:** a query returned 200 with 0 rows for the last 10 blocks → probably not served on Base (inconclusive).

## §4 P0 pass/fail (updated)
| Criterion | Result | Evidence |
|---|---|---|
| docs/sources.md with real authenticated queries + samples | FAIL (blocked: bot key) | proxy 401 without key |
| Every S1 sample event resolves to a receipt | PASS (Goldsky GBM sample, 10/10) / PENDING for AarcadeGh$t entities (bot key) | see keyed rerun |
| Rate limits measured | PARTIAL | HyperSync ≈15 q/min (15000 per 60 s, cost 1000); public RPC getLogs 429; proxy needs bot key |
| Q2 RPC archive + getLogs range | PARTIAL | archive state yes (public); getLogs range blocked (Alchemy app inactive) |
| Q3 Etherscan v2 | ANSWERED: paid plan needed for Base | keyless NOTOK |
| Q4 HyperSync | PASS (logs) / traces likely unsupported | see above |
| S1b parity | NOT DONE (blocked: bot key) | Goldsky reachable |

**Verdict: P0 NOT DONE.** Still blocked: AarcadeGh$t bot key; a working Base RPC key (Alchemy app inactive); paid Etherscan v2 key. P1 not started.
