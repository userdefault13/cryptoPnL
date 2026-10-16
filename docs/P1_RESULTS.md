# P1 Raw ingest — results (2026-10-16 PT, MBP, local Postgres 16 `cryptopnl_test`)
Sources: HyperSync (logs) + free RPC (base.drpc.org; Sepolia sepolia.base.org). **No Goldsky.** AarcadeGh$t proxy not used by bulk ingest (point lookups only). HyperSync self-capped at 7 req/min (no local throttle on MBP; shared 15/min token).
Test wallet: admin 0x2127AA7265D573Aa467f1D73554D17890b872E76. Command: `abra run cryptoPnL -- scripts/p1_test.sh <chain> <wallet>`.

## Marketplace topic0 hit counts (Base, HyperSync, Aavegotchi Diamond 0xA99c… / GBM diamond 0x8032…)
Full range 33,315,000 → 52,691,238 (from ingest #1 by_kind):
| Event | topic0 | hits |
|---|---|---|
| ERC721ExecutedListing | 0x8abb27e5… | 879 |
| ERC1155ExecutedListing | 0x4004185f… | 2,017 |
| ERC721BuyOrderExecuted | 0x252535f1… | 23 |
| ERC1155BuyOrderExecute | 0xa604c414… | 86 |
| Auction_Initialized | 0x62cdbfd4… | 6,682 |
| Auction_BidPlaced | 0x1cd77ec6… | 17,008 |
| Auction_BoughtNow | 0x7499cdcb… | 19 |
| Auction_ItemClaimed | 0x36c817b0… | 5,124 |
All 8 topics have hits; none needed re-deriving. (A first partial scan to block 39.6M showed BoughtNow=0; confirmed via receipt 0x271109cf… at block 42,210,865: GBM log topic0 = 0x7499cdcb…, auctionId 5637, matching the AarcadeGh$t proxy.)

## Pass tests
| Test | Base Sepolia 84532 | Base 8453 |
|---|---|---|
| Ingest twice → identical counts | **PASS** 745 = 745, checksum e93ddc39… | **PASS** 32,547 = 32,547 (709 wallet + 31,838 marketplace), checksum 7a3d145e… |
| Balances raw_event = RPC balanceOf at head + 3 historical blocks | **PARTIAL** 752/784; 32 fails = 8 Aavegotchi wearable ERC1155 ids on 2 contracts (0x4773…, 0xb2d5…) | **PASS for tracked assets** 28/28 (ENVIO §1.1 tokens + Aavegotchi Diamond); **FAIL for untracked** 356 of 1,188 (125 contracts) |
| No 429 storms | PASS (0 × 429) | PASS with caveat: HyperSync 4/37 and 3/36 requests 429 (shared token), drpc 92/1,311 during verify; all retried with backoff, 0 failed requests |
| Simulated reorg → rewind + re-ingest | **PASS** fork 47,171,965, 5 events deleted + re-ingested, checksum restored | **PASS** fork 52,440,523, 14 events deleted + re-ingested, checksum restored (first attempt FAILED: test window 10k didn't cover the tampered blocks; script fixed) |

Untracked mismatch breakdown (Base): 238 checks / 83 contracts events>0 but RPC 0 (spam/fake Transfer events); 64 / 24 RPC < events (fee-on-transfer or burns without events); 31 / 11 balanceOf reverts (non-compliant); 23 / 8 RPC > events (non-standard mints/rebasing).
Sample blocks: Sepolia 27,215,475 / 27,551,977 / 28,628,275 / head 48,201,486; Base 33,595,641 / 42,419,723 / 49,126,235 / head 52,692,033.

## Architect decisions applied (PR #1 review, 2026-10-16)
1. **Balance criterion = tracked assets + allowlist.** Gate set = `TRACKED` (cryptopnl/config.py: ENVIO §1.1 tokens + Aavegotchi Diamond) ∪ `config/allowlist.txt`. Every other asset is reported **untracked** with contract + reason (`spam (Transfer events without balance)`, `fee-on-transfer / burn without event`, `non-compliant (balanceOf reverts)`, `non-standard mint / rebasing`) and is **excluded from PnL totals**. Base Sepolia has no tracked list (staging addresses unverified, ENVIO OQ), so its gate is N/A and everything is reported untracked.
3. **Reorg finality:** treating RPC-pruned blocks as final is accepted for **Base Sepolia staging only**. On mainnet the full reorg check applies: finalize at the `safe` tag (fallback head−64), re-check the cursor hash + the 64 newest stored blocks within the window, delete ≥ fork, rewind, re-ingest. base.drpc.org serves full history, so the pruned branch is never taken on 8453.
4. **Rate limits:** HyperSync stays at 7 req/min (token bucket); RPC verify at 1 req/s with burst 3. `Retry-After` is honored on 429/5xx (capped at 120 s), else exp. backoff + jitter. STATS now log `ok`, `429`, `retry_after_honored`, `elapsed_s` and `effective_per_min` per source.

## P1.1 prep: wearables (read-only discovery; not implemented — needs CoS release)
Source: aavegotchi-contracts `contracts/shared/libraries/LibERC1155.sol` declares
`TransferToParent(address indexed _toContract, uint256 indexed _toTokenId, uint256 indexed _tokenTypeId, uint256 _value)` and
`TransferFromParent(address indexed _fromContract, uint256 indexed _fromTokenId, uint256 indexed _tokenTypeId, uint256 _value)` (the architect's suspicion is correct).
topic0 (keccak, checked against the known TransferSingle hash): TransferToParent `0xe82810099d182b25e23e895715954d6e7b41867a02e2c693cce68a8f250e43d3`, TransferFromParent `0x4b287e36a0531da8ccee303de127c778302f48d8fc9569b1fe1dcb9d64465c6d`.
HyperSync counts (`verify/parent_counts.py`, ≤7/min; raw output in `verify/parent_counts.out.txt`):
- Base, Aavegotchi Diamond 0xA99c…: **partial scan to block 35,978,260 (14 requests): TransferToParent 113,911 (first block 33,208,149), TransferFromParent 2,926 (first block 33,285,899).** The full range needs many more requests. Budget it in P1.1.
- Base Sepolia, 0x4773… and 0xb2d5…: **0** for both events (full range). The Sepolia wearable mismatches are not explained by parent events on those two contracts, so P1.1 should check which address emits them on Sepolia (e.g. the Sepolia Aavegotchi diamond) and look into the duplicate mint logs.
Implication: wearables equipped on a gotchi leave the owner's wallet through parent-transfer events, not standard ERC1155 events, so wallet balances for wearables need these events (or the gotchi→owner mapping) in P1.1.

## End-to-end rerun after architect decisions (2026-10-16 ~11:30–12:30 PT, fresh DBs)
Command: `abra run cryptoPnL -- scripts/p1_test.sh <chain> 0x2127AA7265D573Aa467f1D73554D17890b872E76`. Logs: `docs/evidence/p1_e2e_{8453,84532}.log`; untracked reports: `docs/evidence/p1_untracked_{8453,84532}.json`.
| Test | Base 8453 (`cryptopnl_e2e_base`) | Base Sepolia 84532 (`cryptopnl_e2e_sepolia`) |
|---|---|---|
| Ingest ×2 identical | **PASS** 32,547 = 32,547, checksum 7a3d145e… | **PASS** 745 = 745, checksum e93ddc39… |
| Balances (gate) | **PASS** gated 28/28 (10 gated contracts configured). Untracked: 1,188 checks, 125 contracts not reconciling (spam 83, fee-on-transfer/burn 24, non-compliant 11, non-standard mint/rebasing 8), excluded from PnL | **N/A**: no gated assets (staging). Untracked: 784 checks, 2 contracts not reconciling (Aavegotchi wearables, non-standard mint) |
| Rate limits | HyperSync ingest #1 41 req / 7×429, effective 5.8/min; #2 39 / 5×429, 6.07/min. RPC verify 1,221 req / 2×429 at 60.0/min. HyperSync sent no Retry-After (retry_after_honored=0), so exp. backoff was used. No failed requests | RPC verify 787 req / 0×429 at 60.2/min; HyperSync 0–2×429 per run |
| Simulated reorg | **PASS** fork 52,440,523, 14 events deleted + re-ingested, checksum restored | **PASS** fork 47,171,965, 5 events deleted + re-ingested, checksum restored |
| Script result | `ALL PASS`, EXIT=0 | `ALL PASS`, EXIT=0 |
Note: the reorg test now derives the re-check window from the tampered blocks (`REORG_WINDOW = head − min(tampered) + 1`). Production uses the default 10k-block window plus the safe tag.
