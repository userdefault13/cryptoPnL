# P2 hand check: ledger_entry vs explorer (Base 8453)

Explorer: Blockscout API v2 `https://base.blockscout.com/api/v2/transactions/<hash>` (read-only, fetched 2026-10-16).
Compared per tx: wallet legs (token, token id, raw qty, log index), gas fee (explorer `fee.value` = our `fee` leg,
gas_used*effective_gas_price + l1_fee), native value, and category plausibility. Wallet redacted as `<TEST_WALLET>`.
Our side: `ledger_entry` in DB cryptopnl_p11s_base after `classify` (qty raw units, signed from the wallet's view).

| # | tx | category (ours) | ours | explorer | match |
|---|----|-----------------|------|----------|-------|
| 1 | 0x16d862b8…a89 (blk 49,424,733) | swap | fee -2150178238671; USDC -2000000 (log 104); LINK +242275798925376017 (log 106) | fee 2150178238671; USDC 2000000 wallet→UniV3 pool (log 104); LINK 242275798925376017 pool→wallet (log 106); to = Uniswap v4 UniversalRouterV2.1.1 | yes |
| 2 | 0xa87f55f7…490a76 (blk 49,347,048) | swap | fee -3393561453864; USDC -5000000 (log 77); GHST +112757101939092889336 (log 83) | fee 3393561453864; Aerodrome Router swapExactTokensForTokens; USDC 5000000 out (77); GHST 112757101939092889336 in (83) | yes |
| 3 | 0x246be3e4…558783 (blk 51,157,926) | nft_buy | fee -6979800667584; GHST -452250000000000000 (log 184); Tile id 25 +1 (log 195) | fee 6979800667584; GHST 452250000000000000 wallet→Baazaar route (184); ERC-1155 0x617f… id 25 value 1 → wallet (195) | yes |
| 4 | 0x2862c902…3d1a (blk 51,283,821) | nft_buy (ERC1155 buy order filled by seller) | Tile id 28 +2 (log 380); no fee (not sent by wallet) | executeERC1155BuyOrder by seller; ERC-1155 0x617f… id 28 value 2 → wallet (380); GHST was escrowed when the order was placed | yes |
| 5 | 0x13ad5ed9…70be (blk 43,748,241) | auction (GBM claim sent by seller) | ERC721 0xab59… id 8484 +1 (log 829); no fee | GBM claim(5785); ERC-721 "FAKE Gotchis" id 8484 GBM→wallet (829) | yes |
| 6 | 0x8ecb5b4a…da69 (blk 48,991,194) | deposit | USDC +38003075 (log 339); no fee | USDC transfer 38003075 from external EOA → wallet (339) | yes |
| 7 | 0x6a283a7e…26db (blk 51,007,159) | withdrawal | ETH -1000000000000000 (value leg, -2); fee -161038199185 | plain ETH send value 1000000000000000 to EOA; fee 161038199185; no token transfers | yes |
| 8 | 0x48bb74c6…2b67 (blk 51,481,437) | withdrawal (bridge) | fee -3490664488194; ETH -182734824052186 (value, -2); USDC -1530 (log 44) | Stargate Pool USDC sendToken; value 182734824052186; fee 3490664488194; USDC 1530 wallet→Stargate (44) | yes |
| 9 | 0x8de8de80…08fa (blk 51,481,434) | fee only | fee -457008541213 | USDC approve(Stargate, 1530); fee 457008541213; no token transfers | yes |
| 10 | 0x7611de62…b7 (blk 52,111,311) | income (mint, sent by wallet) | fee -2323445388462; ERC721 0xbdb5… id 11 +1 (log 250) | fee 2323445388462; "Aarcade Cartridge" id 11 minted 0x0→wallet (250) | yes |

**10/10 match** on legs, quantities, log indexes and fees.

Review-queue spot check (not counted in the 10):
| tx | review reason | explorer | verdict |
|----|---------------|----------|---------|
| 0xccbfe04a…58c0 (blk 12,795,081) | DEX router, fungible out only: native leg not indexed (internal ETH gap) | Uniswap Universal Router execute: USDC 30000000 out; WETH 8987936119941153 burned (unwrap) → ETH paid back as an internal transfer; fee 2113313899848 (ours: fee -2113313899848) | correct to hold in review: the ETH leg is not in our data (DESIGN §1 internal-ETH gap) |

Partially checked (explorer `token_transfers_overflow: true`, the wallet's leg not in the first page; consistent where visible):
- 0x1f6395ee…60c2 (income, ERC721 0xa99c… id 954): `mintAavegotchiBridged` decoded input lists `<TEST_WALLET>` → [954]. **Note:** this is the Polygon→Base gotchi migration re-mint, classified `income`; see open question below.
- 0xa7567682…75ec (deposit, HOODIE +9000000000): spam airdrop to ~1000 recipients, 9000000000 each in the visible page.
- 0x21f24706…e2e0 (withdrawal of "ÚSDС" 0x590a…, -5000000, not sent by wallet): phishing token emitting fake Transfer events (sender flagged `Fake_Phishing` by Blockscout). Non-allowlisted; no balance effect on real assets.
