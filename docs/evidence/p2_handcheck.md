# P2 hand check: ledger_entry vs explorer (Base 8453)

Explorer: Blockscout API v2 `https://base.blockscout.com/api/v2/transactions/<hash>` (and `/logs`), read-only, fetched 2026-10-16.
Compared per tx: wallet legs (token, token id, raw qty, log index), gas fee (explorer `fee.value` = our `fee` leg = gas_used*effective_gas_price
+ l1_fee), native value, category. Wallet redacted as `<TEST_WALLET>`. Our side: `ledger_entry` in DB cryptopnl_p11s_base after the
PR #3 review rebuild (ledger md5 18fb3f0acf66c5863802e5c9247c8aad). qty is raw units, signed from the wallet's view; `escrow:` = escrow pseudo-location.

| # | tx (full hash) | block | category (ours) | ours | explorer | match |
|---|----------------|------:|-----------------|------|----------|-------|
| 1 | 0x16d862b8c2b212b035021f3a0e7d7ce3fd92f1c8bc756884b0a5e09bc0bf1a89 | 49,424,733 | swap (USDC leg) + untracked (LINK leg) | fee -2150178238671; USDC -2000000 swap (log 104); LINK +242275798925376017 untracked, pnl_excluded, no lot (log 106) | fee 2150178238671; USDC 2000000 wallet→UniV3 pool (104); LINK 242275798925376017 pool→wallet (106); to = Uniswap v4 UniversalRouterV2.1.1 | yes |
| 2 | 0xa87f55f7ad437f79e0cb9904f8983928b40029d3e74bab27ebae7d665b490a76 | 49,347,048 | swap | fee -3393561453864; USDC -5000000 (77); GHST +112757101939092889336 (83) | fee 3393561453864; Aerodrome Router swapExactTokensForTokens; USDC 5000000 out (77); GHST 112757101939092889336 in (83) | yes |
| 3 | 0x246be3e47cd44a7c2201a28954715410a7b4ab731c6ac0ae62383bcd5c558783 | 51,157,926 | nft_buy | fee -6979800667584; GHST -452250000000000000 (184); Tile id 25 +1 (195) | fee 6979800667584; GHST 452250000000000000 wallet→0x8622aca0547348ed2118943d7da0098eb155035a (184; a direct transfer to that address, not to the Baazaar diamond); ERC-1155 0x617f… id 25 value 1 → wallet (195) | yes |
| 4 | 0x2862c9027165cce8f3297810f4694aadd1b79f38a1b4b3416c388d83e3b33d1a | 51,283,821 | nft_buy paid from escrow (buy order 327) | Tile id 28 +2 (wallet, log 380); GHST -240000000000000000 at `escrow:0xa99c…` ref baazaar:buyorder:327; no fee (not sent by wallet) | executeERC1155BuyOrder by the seller; ERC-1155 0x617f… id 28 value 2 → wallet (380); no GHST moves in this tx (paid from escrow) | yes |
| 5 | 0x13ad5ed909257d05eea1a55897554491203158b39f4017383d4e6112d96d70be | 43,748,241 | auction paid from escrow (GBM auction 5785) | ERC721 0xab59… id 8484 +1 (829); GHST -6900000000000000000 at `escrow:0x8032…` ref gbm:auction:5785; no fee | GBM claim(5785) sent by the seller; ERC-721 "FAKE Gotchis" id 8484 GBM→wallet (829) | yes |
| 6 | 0x8ecb5b4a330112efc24a672c0e3ce6d0f792a9aee8b11633051450d43b29da69 | 48,991,194 | deposit | USDC +38003075 (339); no fee | USDC transfer 38003075, external EOA → wallet (339) | yes |
| 7 | 0x6a283a7e938598b5271d2d2b7620dcd338bfb70f4801e7278ff17eefb2b726db | 51,007,159 | withdrawal | ETH -1000000000000000 (value leg, -2); fee -161038199185 | plain ETH send, value 1000000000000000 to an EOA; fee 161038199185; no token transfers | yes |
| 8 | 0x48bb74c6f76949013d223d1623f8d417110691886a69f3ce835b73f9b91e2b67 | 51,481,437 | withdrawal (bridge) | fee -3490664488194; ETH -182734824052186 (value, -2); USDC -1530 (44) | Stargate Pool USDC sendToken; value 182734824052186; fee 3490664488194; USDC 1530 wallet→Stargate (44) | yes |
| 9 | 0x8de8de808dddaeef7017c99c4bcfd3aeb4abe7f19c945dae9fafd458958e08fa | 51,481,434 | fee only | fee -457008541213 | USDC approve(Stargate, 1530); fee 457008541213; no token transfers | yes |
| 10 | 0x7611de62ca82052771f80434c6262ce1c7331a56d067303bdbdcd708354de9b7 | 52,111,311 | income (mint sent by the wallet) | fee -2323445388462; ERC721 0xbdb5… id 11 +1 (250) | fee 2323445388462; "Aarcade Cartridge" id 11 minted 0x0→wallet (250) | yes |

**10/10 match** on legs, quantities, log indexes and fees.

## Escrow evidence (PR #3 review, blocker 1)
| tx (full hash) | block | ours | explorer |
|----------------|------:|------|----------|
| 0x2a01e94f343332b04f084ec6eb48328604716f7b835cc103f9bbff36f79b5cc8 | 41,733,159 | escrow_out: GHST -240000000000000000 (wallet) / +240000000000000000 (`escrow:0xa99c…`), ref baazaar:buyorder:327 | `/logs`: GHST Transfer 240000000000000000 wallet→Aavegotchi Diamond (log 1587); `ERC1155BuyOrderAdd(buyOrderId 327, buyer <TEST_WALLET>, token 0x617f…, id 28, category 5, priceInWei 120000000000000000, quantity 2)` (log 1588). 0.12 × 2 = 0.24 GHST = the fill's escrow payment in #4 |
| 0xc7deec784681f41a56561478f71ec75934a18a6b6a410d7b54f62e89bed49a3f | 43,593,973 | escrow_out (GBM bid, auction 5785): GHST -6900000000000000000 / +6900000000000000000 at `escrow:0x8032…` | from our raw data only (Auction_BidPlaced(5785, <TEST_WALLET>) + GHST transfer); not separately explorer-checked |

All 15 escrows on Base (1 Baazaar buy order, 14 GBM bids) close to zero: 4 paid wins (auctions 37, 218, 235, 5785), 1 filled buy order,
10 outbid refunds = bid + incentive (5% or 0.5%), with the incentive recorded as `income`. The refund 0x9248c703c1a5552360034fea42f2ca748883acf3c4f6a985c47afd1fccb1ded4
(0.525 GHST, no indexed event) is matched heuristically to the wallet's only open GBM escrow, auction 5613 (0.5 GHST × 1.05).

## Review queue (not counted in the 10)
| tx (full hash) | reason | explorer | verdict |
|----------------|--------|----------|---------|
| 0xccbfe04a6920793f7000b61d74e0da342e65252efe3e73170ec2f751c5bc58c0 | DEX router, fungible out only: native leg not indexed (internal ETH gap) | Uniswap UniversalRouter execute: USDC 30000000 wallet→pool (125); WETH 9001438277357188 pool→router (124); 13502157416035 → FeeCollector (127); 8987936119941153 burned (128, unwrap) → ETH paid back as an internal transfer; fee 2113313899848 (ours: fee -2113313899848) | correct to hold in review: the ETH leg is not in our data (DESIGN §1 internal-ETH gap) |

## Partially checked (explorer `token_transfers_overflow: true`; consistent where visible)
- 0x1f6395ee078f77a6e3b0049a4438e2507617c4d4e30c506052f02aef367160c2: now **migration_in** (ERC721 0xa99c… id 954, pending basis, chain_origin 137). `mintAavegotchiBridged` decoded input lists `<TEST_WALLET>` → [954].
- 0xa7567682e0e1dab0a468498c87d8e9d0513f08c999028a928ca6bb9d068c75ec: now **spam** (HOODIE +9000000000): an airdrop to ~1000 recipients, 9000000000 each in the visible page.
- 0x21f247067bb07f3f63a653b670990519857113170c441aced30e15ff0deca2e0: now **spam** ("ÚSDС" 0x590a…, -5000000, not sent by the wallet): a phishing token emitting fake Transfer events (sender flagged `Fake_Phishing` by Blockscout).
