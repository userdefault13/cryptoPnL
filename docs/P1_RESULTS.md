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
