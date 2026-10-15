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

## §4 P0 pass/fail
| Criterion | Result | Evidence |
|---|---|---|
| docs/sources.md with real authenticated queries + samples | FAIL (blocked: bot key) | proxy now 401 without a key |
| Every S1 sample event resolves to a receipt | FAIL (blocked: bot key + RPC) | only GBM event entities expose tx id; getLogs/receipts unusable on public RPC |
| Rate limits measured | PARTIAL | public RPC hard-limited (-32011 even at 1 block); Goldsky/proxy send no rate-limit headers; no burst test |
| Q2 RPC archive balanceOf/getLogs ranges | BLOCKED (RPC key) | public getLogs refused at all ranges |
| Q3 Etherscan v2 | ANSWERED: needs paid plan for Base | NOTOK message above |
| Q4 HyperSync | PARTIAL | /height OK; queries need token |
| S1b parity sample | NOT DONE (blocked: bot key) | Goldsky reachable |

**Verdict: P0 NOT DONE.** Blocked on keys: AarcadeGh$t bot key (introspection, sources.md, S1 receipts, S1b parity, proxy rate limits), Base archive RPC (getLogs ranges, balanceOf-at-block, receipts), Etherscan v2 paid key (fast path), HyperSync token (count queries, traces). P1 not started.
