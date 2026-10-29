# P4.1 step 1: sources of the unrecorded inflows (READ-ONLY tracing, 2026-10-28)

Wallet `0x2127aa7265d573aa467f1d73554d17890b872e76` (Base). Method and request budget: `docs/P4_1_PLAN.md` (step 1, revisions 1–2).
- Nothing was written on chain, to the ledger or to classification.
- Evidence: `docs/evidence/p4_1_eth_trace.json`, `p4_1_eth_extra.json`, `p4_1_ghst_trace.json`. Scripts: `scripts/p4_1_trace.py`, `p4_1_trace_rpc.py`, `p4_1_eth_bisect.py`, `p4_1_eth_extra.py`.

## Summary
| gap (canonical ledger, as_of 49402932) | status | sources found |
|---|---|---|
| **ETH 1.095603323941304014** over 455 events, blocks 12795076–49402932 | **explained to the wei** | 15 internal (contract → wallet) ETH transfers. 12 (#1–#12) are ≤ as_of and total 1.098089677237037763 ETH. That equals the gap plus the 0.002486353295733749 ETH still held at as_of (on-chain balance). |
| **GHST 652.6299999999999975** from 20 pockets | **withdrawal mechanism confirmed; the pockets' own GHST sources NOT traced** | The 3 txs are `batchTransferEscrow` (0x2a206f11) on the Aavegotchi Diamond. Where the 20 pockets got their GHST needs HyperSync (blocked; see §3). |

**Why the ledger missed the ETH:** every inflow is an **internal** value transfer. A contract pays the wallet inside a tx: a bridge fill, a claim, a swap output or a refund. Ingest records only top-level tx value and ERC-20 / ERC-1155 logs, so native ETH arriving by internal CALL never becomes a ledger row.
- The wallet's own swaps record the gross ETH sent, never the ETH refunded or received back.
- Recent txs go through the wallet's own EIP-7702 `execute` (0xe9ae5c53; tx `to` = the wallet).

## 1. ETH: method and checks
- **Expected path:** the ETH rows of the MBP's local `cryptopnl_p3_base` (511 rows, 457 blocks). This is an older copy, not the canonical omarchywin ledger, whose PG needs abra; abra was locked.
  - Validated against the chain: the fee at 12795076 matches the balance change exactly (621657174830 wei, L1 fee included).
  - At as_of 49402932 the copy's ETH net is **−1.095603323941304014**, identical to the canonical ledger's ETH gap.
- **Actual:** RPC `eth_getBalance`. The surplus (actual − recorded) was bisected over the recorded blocks and over [0, 12795075]:
  - 117 + 25 balance probes;
  - every surplus change pinned to one block;
  - every change confirmed by `debug_traceTransaction` (callTracer): internal CALL value into the wallet, equal to the surplus change to the wei.
- **Totals:**
  - surplus at block 52112861 = 1.100159886980823309 ETH = 0.004916023986331809 (held before the first recorded row, arrived at 12794901) + the 14 later changes;
  - Σ of the 15 inflows = 1.100159886980823309 ETH (exact).
- **Coverage:** everything to block 52112861 (the copy's last block). Blocks 52112862–52911467 (canonical last block) were not probed. They are after as_of, so outside the P4 gap.

### ETH inflows (every one confirmed by an RPC trace)
| # | block | tx | ETH (wei exact) | paid by (internal CALL) | tx from → to | mechanism | ≤ as_of 49402932 |
|---|---|---|---|---|---|---|---|
| 1 | 12794901 | `0xb78fe8e8fa2df3c6fa21c9dfa97882e14e7c9aec60928fb70655dd1b8e17ae1e` | 0.004916023986331809 (4916023986331809) | Hop L2AmmWrapper (Base) `0x10541b07d8ad2647dc6cd67abd4c03575dade261` | `0x710bda329b2a6224e4b44833de30f38e7f81d564 → 0x3666f603cc164936c1b87e207f36beba4ac5f18a` | bridge in: Hop bonder `bondWithdrawalAndDistribute`-style call (0x3d12a85a) on the Hop ETH Bridge; ETH paid by the Hop L2AmmWrapper | yes |
| 2 | 12795081 | `0xccbfe04a6920793f7000b61d74e0da342e65252efe3e73170ec2f751c5bc58c0` | 0.008987936119941153 (8987936119941153) | Uniswap Universal Router (Base) `0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad` | `0x2127aa7265d573aa467f1d73554d17890b872e76 → 0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad` | swap output: token → native ETH through Uniswap Universal Router `execute` (0x3593564c); the router sends the ETH to the wallet | yes |
| 3 | 23210972 | `0xf36f1da4357d153fa8f13a698aa012954eea7fc5fa9b34b198cc312089890210` | 0.052652326223033971 (52652326223033971) | Mayan Swift `0xc38e4e6a15593f908255214653d3d947ca1c2338` | `0xfcbac0713acf16708ab6bc977227041fa1bc618d → 0x6daea6e2b30010bf8f5aecde9741a9d86f3da919` | bridge in: Mayan Swift fill (solver tx via 1inch Router V6, 0xbc127b88); ETH paid by Mayan Swift | yes |
| 4 | 40749157 | `0xcacfad72de1769c3cecdf63fdf0dd3f6ec958a23b53c2ef0839e3cdfa185f07f` | 1.0141283024 (1014128302400000000) | ETH claim/distributor contract (emits Claimed(address,uint256); name unverified) `0xf50326e1a6c6949cc390c4efe8ea538e29a4fa11` | `0x2127aa7265d573aa467f1d73554d17890b872e76 → 0xf50326e1a6c6949cc390c4efe8ea538e29a4fa11` | claim: the wallet called 0x2f52ebb7 on the distributor; it paid 1.0141283024 ETH (Claimed event) | yes |
| 5 | 40991112 | `0x7ec336225394e882ff9bebdab66a69b5f44e93627d65aeb633593a288e5c5592` | 0.000000000000000001 (1) | (Rubic route contract) `0xaf14797ccf963b1e3d028a9d51853ace16aedba1` | `0x2127aa7265d573aa467f1d73554d17890b872e76 → 0x3335733c454805df6a77f825f266e136fb4a3333` | dust return (1 wei) from a Rubic cross-chain route (`startViaRubic`, 0xe1fcde8e) the wallet paid 0.2999485942633777 ETH into | yes |
| 6 | 41679144 | `0x4057b4a33188f6dcb9bf0900cc4deb2a5a3977edceeaa5fde0914e07cca7efef` | 0.000000000000000001 (1) | (Rubic route contract) `0xaf14797ccf963b1e3d028a9d51853ace16aedba1` | `0x2127aa7265d573aa467f1d73554d17890b872e76 → 0x3335733c454805df6a77f825f266e136fb4a3333` | dust return (1 wei) from a second Rubic route (same pattern) | yes |
| 7 | 46796145 | `0x640a3418c684f3ae638a62494460d8690a285005a5b5757804a8269d54d70126` | 0.000082582369528891 (82582369528891) | Uniswap Universal Router 2.1.1 `0xfdf682f51fe81aa4898f0ae2163d8a55c127fbc7` | `0x2127aa7265d573aa467f1d73554d17890b872e76 → 0xfdf682f51fe81aa4898f0ae2163d8a55c127fbc7` | refund of excess ETH input by Uniswap Universal Router 2.1.1 (the ledger records the gross ETH sent) | yes |
| 8 | 46796599 | `0x3c988c5bfbb7f577970d4eb3342a3a3b5b4989f75370f8ab3db11df6917a6732` | 0.000248136263416683 (248136263416683) | Uniswap Universal Router 2.1.1 `0xfdf682f51fe81aa4898f0ae2163d8a55c127fbc7` | `0x2127aa7265d573aa467f1d73554d17890b872e76 → 0xfdf682f51fe81aa4898f0ae2163d8a55c127fbc7` | refund of excess ETH input by Universal Router 2.1.1 | yes |
| 9 | 46860859 | `0xa5ee1787a49ef50f04b07cdbd3412fbbbd0dc95dc1e24c285a82feb38ab107df` | 0.014247209214890559 (14247209214890559) | Across SpokePool (Base) `0x09aea4b2242abc8bb4bb78d537a67a245a7bec64` | `0xcad97616f91872c02ba3553db315db4015cbe850 → 0xfd03abcadaf3f930fa4e37eb2f6ea3a44a41b7f0` | bridge in: Across V3 fill (relayer tx to 0xfd03…, 0x260595cf); ETH paid by the Across SpokePool | yes |
| 10 | 46904091 | `0x0b09654a56af868a05a608b376158ac0f0d7c6bb5ed3bb882cc243fa85c4dce3` | 0.000014050301010504 (14050301010504) | Uniswap Universal Router 2.1.1 `0xfdf682f51fe81aa4898f0ae2163d8a55c127fbc7` | `0x2127aa7265d573aa467f1d73554d17890b872e76 → 0xfdf682f51fe81aa4898f0ae2163d8a55c127fbc7` | refund of excess ETH input by Universal Router 2.1.1 | yes |
| 11 | 46918238 | `0x5d0d8221c923095f03bba141bf0293b63548a75312f34be3df808f145324839e` | 0.000135901291199612 (135901291199612) | Uniswap Universal Router 2.1.1 `0xfdf682f51fe81aa4898f0ae2163d8a55c127fbc7` | `0x2127aa7265d573aa467f1d73554d17890b872e76 → 0xfdf682f51fe81aa4898f0ae2163d8a55c127fbc7` | refund of excess ETH input by Universal Router 2.1.1 | yes |
| 12 | 49384073 | `0x86d7518cc1776125befa6652becf2ccc76614a0f2e701cc80cd34c5ecf2714fa` | 0.002677209067684579 (2677209067684579) | Uniswap Universal Router 2.1.1 `0xfdf682f51fe81aa4898f0ae2163d8a55c127fbc7` | `0x2127aa7265d573aa467f1d73554d17890b872e76 → 0x2127aa7265d573aa467f1d73554d17890b872e76` | swap output: token → ETH via Universal Router 2.1.1, called from the wallet's EIP-7702 `execute` (tx to the wallet itself) | yes |
| 13 | 51007144 | `0xdf1d76981dc9c1a165abe88a4f37e9ae62c5b560a57e6a45e3834a48a082e0e8` | 0.00198587025 (1985870250000000) | MetaMask Swaps Spender `0x0a2854fbbd9b3ef66f17d47284e7f899b9509330` | `0x2127aa7265d573aa467f1d73554d17890b872e76 → 0x2127aa7265d573aa467f1d73554d17890b872e76` | swap output: token → ETH via MetaMask Swaps (Router → Spender), called from the wallet's EIP-7702 `execute` | no |
| 14 | 51481414 | `0x77b74a9f71a64c4c44eaf31893d15dd40c205da59a6a3ec495b0c3179409af00` | 0.000042169919004273 (42169919004273) | LayerZero EndpointV2 `0x1a44076050125825900e736c501f859c50fe728c` | `0x2127aa7265d573aa467f1d73554d17890b872e76 → 0x27a16dc786820b16e5c9028b75b99f6f604b5d26` | refund of excess LayerZero native fee by EndpointV2 (wallet called 0x27a16dc7…, 0xcbef2aa9) | no |
| 15 | 51481437 | `0x48bb74c6f76949013d223d1623f8d417110691886a69f3ce835b73f9b91e2b67` | 0.000042169574781273 (42169574781273) | LayerZero EndpointV2 `0x1a44076050125825900e736c501f859c50fe728c` | `0x2127aa7265d573aa467f1d73554d17890b872e76 → 0x27a16dc786820b16e5c9028b75b99f6f604b5d26` | refund of excess LayerZero native fee by EndpointV2 (second send) | no |

**Sum:** 1.100159886980823309 ETH over 15 inflows; ≤ as_of: 1.098089677237037763 ETH.
By mechanism:
- **Bridges in:** Hop (#1), Mayan Swift (#3), Across (#9). Together 0.071815559424256339 ETH.
- **Claim:** distributor 0xf50326e1… (#4). 1.0141283024 ETH, the bulk of the gap.
- **Swap outputs** (token → ETH): #2, #12, #13 (#13 is after as_of).
- **Swap refunds:** Universal Router 2.1.1 (#7, #8, #10, #11).
- **LayerZero fee refunds** (#14, #15): after as_of.
- **Rubic dust:** 1 wei each (#5, #6).

Rows after as_of: #13–#15.

## 2. GHST: what is confirmed
- **Mechanism:** each of the 3 txs is sent by the wallet to the **Aavegotchi Diamond on Base** `0xa99c4b08201f2913db8d28e71d020c4298f29dbf`, selector **0x2a206f11 = EscrowFacet.batchTransferEscrow**.
  - It moves GHST (`0xcd2f22236dd9dfe2356d7c543161d4d260fd9bcb`) out of 20 gotchi escrow ("pocket") contracts into the wallet.
  - These are 60 Transfer logs, read from the RPC receipts.
- **Amounts:** total **652.6299999999999975 GHST**, exactly the canonical GHST gap.

| pocket (gotchi escrow) | 38141654 `0xd329b5d2…` | 38622419 `0x0aeef829…` | 40216494 `0xdad19023…` | total GHST |
|---|---|---|---|---|
| `0x02f7da40a267d7ae6c48caf041968542c3c46589` | 31.2850000000000015 | 6.2625 | 12.4225 | 49.9700000000000015 |
| `0x0c375f0a508f86709b675b4bbfdcef8d51de7ff3` | 13.755 | 2.7875 | 5.56 | 22.1025 |
| `0x1c0c0b9581cca74581ecf8a5c31f82653c1ef8a2` | 13.9675 | 2.8225 | 5.635 | 22.425 |
| `0x380e5e8d651cc708cf88b7a838035518fb4425a1` | 26.384999999999999 | 5.3175 | 10.635000000000001 | 42.3375 |
| `0x430a1a23bdeb6d50b0cc9bfc1f93992b582bc96f` | 14.1575 | 2.855 | 5.7075 | 22.72 |
| `0x443d5f09fd9b11250b060bdd420c7a9c8c2066c0` | 28.7975 | 5.775 | 11.46 | 46.0325 |
| `0x52265e2d4f82b0a363f5d045e2eb8769adb9ab39` | 2.6775 | 2.7025 | 5.42 | 10.8 |
| `0x6933b1a218d189d4a4c189a1e7b674453f41c0de` | 26.782499999999998 | 5.3725000000000005 | 10.7075 | 42.8624999999999985 |
| `0x728f0baf79ebdfa336978c90f244324a0ba7bcff` | 14.17 | 2.8575 | 5.715 | 22.7425 |
| `0x7323a5e018fe495bc5fb390de18ccd61fdd2d8eb` | 26.2875 | 5.3075 | 10.6025 | 42.1975 |
| `0x8f64003ac2898edc02bf4a7ec4ab6537e4861368` | 13.93 | 2.815 | 5.625 | 22.37 |
| `0x9c2e5e9686974338181b145109da56b4b4406b19` | 26.3374999999999985 | 5.3125 | 10.62 | 42.2699999999999985 |
| `0xa0173b0c67c4b96497c7185d047a00af27fce945` | 25.4875 | 5.125 | 10.2 | 40.8125 |
| `0xa51d2128f62b122b0be9b0c6b47ad6b017cd8350` | 26.624999999999999 | 5.3675 | 10.7375 | 42.729999999999999 |
| `0xa9ebe0f3ad527f3531a15d4770edc2b82b006801` | 17.1375 | 3.4675 | 6.9025 | 27.5075 |
| `0xaaeca339dec2b42cdc189e6df2b45fe8685fb6fb` | 14.7 | 2.9625 | 5.9025 | 23.565 |
| `0xbc5699672c4ae61a951704acf2265fde7d9ec5ce` | 14.96 | 3.005 | 5.995 | 23.96 |
| `0xdb084925e330a7bed6aab9d7828b4defe2b96dc1` | 20.12 | 4.0175 | 7.9675 | 32.105 |
| `0xdfcebf9865f9cc40c590e0e5f45bf78105a6e6fa` | 15.385 | 3.115 | 6.19 | 24.69 |
| `0xfba935526fafd92afcf7cc6472114458a6f77fb5` | 30.265 | 6.085 | 12.08 | 48.43 |
| **total** | 403.212499999999996 | 83.3325000000000005 | 166.085000000000001 | **652.6299999999999975** |
The ledger has these as `transfer_internal` pocket → wallet legs, so the wallet side is recorded. What is missing is how the GHST got **into** each pocket: GHST transfers into a gotchi escrow don't involve the wallet's address, so wallet-scoped ingest never sees them.


## 2b. GHST pocket inflows: TRACED (H3, 2026-10-28 20:18 PT)

Query: HyperSync `base.hypersync.xyz`, Transfer logs with topic2 ∈ the 20 pockets (in) or topic1 ∈ the pockets (out), all tokens, blocks 0–40216494, txs joined. **1 request** (HTTP 200; token `aavegotchi-envio-indexers/ENVIO_API_TOKEN` on omarchywin), 0 RPC. Evidence: `docs/evidence/p4_1_ghst_pockets.json` (346 rows, 149 txs), script `scripts/p4_1_ghst_pockets.py`.

**Facts (not classified; for the architect):**
- **All 156 GHST transfers into the 20 pockets** have log `from` = tx `from` = **0xf52398257a254d541f392667600901f710a006ed**, tx `to` = the Aavegotchi Diamond `0xa99c4b08…9dbf`, selector **0xea20c3c6 = `batchDepositGHST(uint256[],uint256[])`** (openchain + 4byte; `EscrowFacet.batchDepositGHST(_tokenIds, _values)` in aavegotchi/aavegotchi-base `contracts/Aavegotchi/facets/EscrowFacet.sol`). 104 txs, blocks 35315787–39595007.
- **Conservation:** GHST in = **652.6299999999999975**; GHST out = 652.6299999999999975 in exactly **60** legs, all to the wallet via the 3 `batchTransferEscrow` txs (0x2a206f11). Every pocket nets to 0 after block 40216494. So the canonical GHST gap (652.63) = these deposits, to the wei. No other GHST moved in or out of the pockets in the range.
- **Sender identity (free sources):** in [aavegotchi/aavegotchi-base](https://github.com/aavegotchi/aavegotchi-base) @ 9ce0c19 (2026-04-22) the address is `baseRelayerAddress` (`scripts/helperFunctions.ts:396`), `relayerPetter` (`helpers/constants.ts:187,195`), `BASE_RELAYER` / `BASE_RELAYER_PETTER` (`test/foundryTests/constants.sol`) and the `deployerAddress` of `scripts/airdrops/rarityfarming/szn11/rnd1–4.ts`. The repo's `tasks/rarityPayouts.ts` pays rarity-farming rewards with `escrowFacet.batchDepositGHST(tokenIds, amounts)` (line 672), i.e. into the gotchis' pockets. That these specific deposits are RF payouts is consistent with the code and timing but is **not proven on-chain** (the calldata carries no season / round tag).
- The wallet did not send these txs; they are third-party deposits into the escrows of the wallet's gotchis, which is why wallet-scoped ingest never saw them.

| block | date (PT) | tx | pockets | GHST |
|---|---|---|---|---|
| 35315787 | 2025-09-09 | `0x8dbcda2e061a68c4a2f862494255f40850c840bc984f92dff3b243076ba4642d` | 1 | 5.35 |
| 35315791 | 2025-09-09 | `0x3edf3b10a5483b58c46e3c93813b7582766f2b5695dca0f1fad350a2ad524fd3` | 1 | 2.8175 |
| 35315793 | 2025-09-09 | `0xb88b7b328c5d3279b286dc887768f30095ba5c45948d3b91333c03c5442a55e4` | 2 | 5.8775 |
| 35315796 | 2025-09-09 | `0x95a8ac075d966bfe9a66a711724fc808f411353d5ca7104c0d66229abc19052b` | 1 | 2.98 |
| 35315799 | 2025-09-09 | `0x7012ed13d70de69543b664d0e41a8d69579d75a3e170cfc78b07c00fac17e0b0` | 2 | 6.3375 |
| 35315804 | 2025-09-09 | `0x7acd96946e7bc5bbff4259113c1107e295445e66db8b779994cefdf99279d105` | 3 | 12.785 |
| 35315809 | 2025-09-09 | `0xa0d470090f5aae9f5eb73d0b690d150c7dd3be60454f38dd554c10287ef036ff` | 2 | 10.3424999999999995 |
| 35315814 | 2025-09-09 | `0xa6f15648b63df7e81d2530ed8dcdd81ec2daca2f49196f0456bf28921ed4b11d` | 1 | 2.7625 |
| 35315816 | 2025-09-09 | `0x38ae4795dff8017037703f0e2e50ab2c6a371351fadc37be07f607b31877e203` | 2 | 11.9950000000000005 |
| 35315819 | 2025-09-09 | `0xf8840096189f33ac36ec720df731a97b532259db2892cab9ee078f0d5fca1c05` | 1 | 5.24 |
| 35315826 | 2025-09-09 | `0xc84df238df2786f6ca306c6f546a630746458f0d8cde09aa24ed252eafc17961` | 1 | 2.755 |
| 35315834 | 2025-09-09 | `0xded3f78c87e5939fab710052ad64aa58290ad7e734e403f4d5acc2d18217de73` | 1 | 5.3125 |
| 35315836 | 2025-09-09 | `0x7b0a156dd2e79cac034d8519a5d1884026459f7d2e8950a7704da6916e5a091f` | 1 | 5.27 |
| 35952525 | 2025-09-23 | `0xcfb4440480b2df7d5dbba977771c573ed6cce03ae93067adf5bb1eb65c13c01d` | 2 | 5.8875 |
| 35952531 | 2025-09-23 | `0x15f30269b3601f2be63d607c4485fe08ef39549d4f89dc96f66827a1a3ce8357` | 1 | 2.985 |
| 35952533 | 2025-09-23 | `0x390a9c9320b8425d0f57df3c2e62a54d8e34b1e7c2827931866978092cd2aaaf` | 2 | 6.3500 |
| 35952538 | 2025-09-23 | `0x97deeede9f514c806e4e3fb7f33fb49e9b2071d61449b68d48fba6177d817ecb` | 3 | 12.7650 |
| 35952542 | 2025-09-23 | `0x1739d12b5f105c09dc2d64a25d57edab53973a7f60252d9c589a4ea87ef367ae` | 2 | 10.3349999999999995 |
| 35952547 | 2025-09-23 | `0xcc77317b9648fa472b66681ef3908f964d4a0bf97fd14793b740932cea379c68` | 1 | 2.7875 |
| 35952549 | 2025-09-23 | `0xb94708ede851be596b4d20911ad8dac822fd1de3609d1d3d52eaf6e7be274012` | 2 | 11.9875000000000005 |
| 35952553 | 2025-09-23 | `0xdc086b0c7d7a83cb6a30be751a9b9c337b08c7204a51fc93099b0d6c02ab7352` | 1 | 5.2425 |
| 35952559 | 2025-09-23 | `0x60d4a34eb11907a2c4529b513101b1f648451aaa20341e0a04d4f7e903e82e13` | 1 | 2.78 |
| 35952563 | 2025-09-23 | `0xc086692ffa6bf28ba1e709e54bb6fff461e6d58b3f541a5827fac68e44a4de18` | 1 | 5.3075 |
| 35952564 | 2025-09-23 | `0xf994c7b0243aaf2a716c36f22c73421c3e734b3184c97ae912e50d203d0f5354` | 1 | 5.26 |
| 35952843 | 2025-09-23 | `0x1ba317d8e323132f4d9da14e60dc002640b5a735eb151a3f39b179f893c3ae01` | 1 | 5.342499999999999 |
| 35952846 | 2025-09-23 | `0xcb708f6525df767f6fe11b3ac16d96a32424574a469eb1cab675cc88353221a1` | 1 | 2.825 |
| 36558587 | 2025-10-07 | `0x20d2adc2cadcfeb0c2304a61fca9e2151fcf7a4669552468edf5bf1bcd3d71df` | 1 | 5.3375 |
| 36558590 | 2025-10-07 | `0x9ba9e9f91ef4f7bbadbcb92ca060d2ae12988b0baefeb8d59c0e25fbb97e9b80` | 1 | 2.835 |
| 36558593 | 2025-10-07 | `0xf18be5071bcdabfae07a42edc48f0dc26515448c877f51971346b32715540e1f` | 2 | 5.8950 |
| 36558596 | 2025-10-07 | `0x65e6990a3bff2bc0e542dc9b712802610e9f1c39b9719bd0f556780af7391374` | 1 | 2.99 |
| 36558598 | 2025-10-07 | `0x047a1dea69a3847e0f5fcc3588b218ad399e31a3e9bd9815ffb08b565b9faf12` | 2 | 6.3525 |
| 36558602 | 2025-10-07 | `0x711d2001ba91ba13f41f9a3a81799b06c97085641b290f0db9ae7b4be723153b` | 3 | 12.8200 |
| 36558607 | 2025-10-07 | `0x1fb6419ce6d5e49d5b79a479e759ecbc6c2857ccb88ba8fb679dc3b92164af61` | 2 | 10.3374999999999995 |
| 36558610 | 2025-10-07 | `0x709e6914df9add6b7ea2da410c10f0659b4a6841e5ad635f73e6aadec5e34a5c` | 1 | 2.7925 |
| 36558612 | 2025-10-07 | `0xee9c28ae67d44749c81c36416f1ee331c6dd5ad8a1e05c8c08c1b422ea91c2b2` | 2 | 11.9925000000000005 |
| 36558614 | 2025-10-07 | `0x43770c77ecbb074d64fa72ca9fc132f5fa6ea47e1f75e5079094beca9a7ba5e2` | 1 | 5.2425 |
| 36558618 | 2025-10-07 | `0x06c7fac709dc60225f213a7942f8f192c59ef1623e0e9baab31b068b61eaf769` | 1 | 2.785 |
| 36558624 | 2025-10-07 | `0xfa72943ad5826081e5b13ae1e8049213edd46e097b846d1b12a18cb3b35b064a` | 1 | 5.3125 |
| 36558628 | 2025-10-07 | `0x86cf89c729ff31186d733097263dfdb9708dcc549054ed9ac9cebdda9b18ad10` | 1 | 5.2625 |
| 37203988 | 2025-10-22 | `0xae7ff23f2a5870d9ee63994cc6b4be15ea466566b0ee1f62c626ca11004ac57d` | 1 | 5.365 |
| 37203992 | 2025-10-22 | `0xbc3ff449a4225ad9cdd05c6f4b0a1a9be944558ba5739c0bea9b32cf615dd86e` | 1 | 2.8425 |
| 37203995 | 2025-10-22 | `0xd95403d86ce2be80fe192303ac766a54c3effa5c6af60d3e1cc65c5b7f5592fa` | 2 | 5.9275 |
| 37203999 | 2025-10-22 | `0x4109713404dac6feb3cc57555195303a1cf32bc4909de4cbe6c5f039d0cfedef` | 1 | 3 |
| 37204002 | 2025-10-22 | `0xe6e388eba7dd5f8d8d31c9890de6f431a18de136b394c00b50da0ff440c82d7e` | 2 | 6.380 |
| 37204006 | 2025-10-22 | `0x152e2e85aa5b51d485d509a3014d3658c3999274cb331bc88cac1d1de9d4a11f` | 3 | 12.8625 |
| 37204009 | 2025-10-22 | `0x8f20667b3fbb00872e34ef545f49ccd7d4b855b96d8aa9402386223651a0429f` | 2 | 10.3775 |
| 37204015 | 2025-10-22 | `0xe8f50844efc1246fa0fa9bd1b36049265aa8e898a2379fa8a134516dff7312bd` | 1 | 2.805 |
| 37204016 | 2025-10-22 | `0xc53134c63c166aad26e77c975293dd654f8ecbb15ef16276c047ad56e5fd9bc7` | 2 | 12.0375 |
| 37204019 | 2025-10-22 | `0x76aa88d81c45dfa58314bf9c0296f119011f3edd7ca19a377d82dd62d90915db` | 1 | 5.2675 |
| 37204025 | 2025-10-22 | `0xfcc5f38304d9c555fa29dbea3a4e124350a32633dcc4ad39e2a1274e26669f20` | 1 | 2.7975 |
| 37204035 | 2025-10-22 | `0x0bb038719540249f2139d384e07835fae367ea91a00d0dca77f60000490e416e` | 1 | 5.3325 |
| 37204036 | 2025-10-22 | `0x8de719f6e7bd3b8378c9738d3737ffa505ac4fa192f33ca1cd0349a8911757f6` | 1 | 5.279999999999999 |
| 37768463 | 2025-11-05 | `0x15b27ae4e3ed40b0fc3c47d45f4ac11dddd688eb20934cdeb787f80d4ff4acd0` | 1 | 5.387499999999999 |
| 37768467 | 2025-11-05 | `0x7eb5c5ec7ff5164d2d816094ffa141dbbfff30f4b075bed952343562e020c66d` | 1 | 2.85 |
| 37768474 | 2025-11-05 | `0xdcd6e669721c75e83baccca94134b26da5c195c751cd3b89338d854dd3b4a18b` | 2 | 5.9550 |
| 37768482 | 2025-11-05 | `0xc94f5c0638afd91702dca2ec30468bbaa7ca298cb68629eabc01bf04184458ab` | 1 | 3.005 |
| 37768484 | 2025-11-05 | `0x6d4d95e77d0353e145ebfbde0fcc65b931745497d76923facbadc2e65b7c7ec7` | 2 | 6.4175 |
| 37768491 | 2025-11-05 | `0x7d82e0a686120f90943c06274ab9b26db24796474f37ad52084c5231619f03b6` | 3 | 12.9075 |
| 37768495 | 2025-11-05 | `0x11c3a68f0c40564dc26d1377421954596ea9d5921a506c9f3bf53bed1f9eacc3` | 2 | 10.4325 |
| 37768501 | 2025-11-05 | `0xec312e91d37f178a6ff94acadb986387457f1371c563cd665de568f547431096` | 2 | 5.4975 |
| 37768503 | 2025-11-05 | `0xa88d909a7e1f850ba0e1e58a254c24fa997125e7ec9c4be70450a2ad2ba1be59` | 2 | 12.07 |
| 37768506 | 2025-11-05 | `0x69d5b17ef363938032765e7f6236d4e9b8fb3f59be24a0f20dc01691dfcc3339` | 1 | 5.295 |
| 37768516 | 2025-11-05 | `0xf1f5dde8b40b6209339d6338cfe64482f001338e2c4397c4df02622d5cff7990` | 1 | 2.8125 |
| 37768526 | 2025-11-05 | `0x9bcda92337f73db9edcb30a3c5ed2be84281286f09849181d076d571840c2ae7` | 1 | 5.359999999999999 |
| 37768529 | 2025-11-05 | `0x57a9e7ff0994d29d964c16b48666b707caa8f0b429a869f502c63ad05caa27ab` | 1 | 5.3125 |
| 38458458 | 2025-11-20 | `0xfb43604bb94fb47e16eff88cfa232fe114d41c4251c57d384c22ae440ecec00b` | 1 | 5.3725000000000005 |
| 38458461 | 2025-11-20 | `0x4b846cfa9b7db0603a850110e8ae840c7ade7419221ec1f7d8ed48f50d617ea0` | 1 | 2.8575 |
| 38458464 | 2025-11-20 | `0x543f2fe94bfe1bd45a02e596b25807c8a394031c17c1e1f8836bba79bad9b7e0` | 2 | 5.970 |
| 38458468 | 2025-11-20 | `0xdb555543d454f122d0fc135dc4d0f1cf1954c9c6474ca63fb423b4f676a3f721` | 1 | 3.005 |
| 38458470 | 2025-11-20 | `0x22bc1b04c94cd1c1df3cfa72a6d4da6791cf4252eca5354c420f68a48564d800` | 2 | 6.4300 |
| 38458473 | 2025-11-20 | `0xb19b50818b2fb646fc9022f593a3bdc02e57fc9723eaa024527dfca2c82b52e1` | 3 | 12.8900 |
| 38458477 | 2025-11-20 | `0x7432e288daeb1dfb6a391569e2646036bc5930778812a456c83944f196a9438e` | 2 | 10.4375 |
| 38458481 | 2025-11-20 | `0xd6a960fec3ed8bad338e980ae9be8c07cf591dd0df884ffcdf288efbcb87265f` | 2 | 5.5250 |
| 38458482 | 2025-11-20 | `0x7a0d29c4bd43e0df5f5244ab7f592dc4f31567c90160266c228366a23e5284a6` | 2 | 12.0375 |
| 38458484 | 2025-11-20 | `0xaee67b522ca20dbfba5cb3e9ed53619b705df3a167dfb369a97484bd817f2ec9` | 1 | 5.3075 |
| 38458489 | 2025-11-20 | `0x360665027365b45f8076a4013b5c9dfdd52746687005ec5dd5cc5231d0603357` | 1 | 2.815 |
| 38458494 | 2025-11-20 | `0xcdb82926053443de4a3367ac770b48bca6b9329f623707467a2cb233608154c9` | 1 | 5.3675 |
| 38458496 | 2025-11-20 | `0xb151c81374e50868d423f6da35d0023facf47758169812ba028a1ecd72e1b8ef` | 1 | 5.3175 |
| 38945492 | 2025-12-02 | `0xada74878346fc26ccdd7a6902765f4a79a36638bb18760073961d1093d5fccb6` | 1 | 5.3575 |
| 38945496 | 2025-12-02 | `0x4e00461a03578ebd8dc4a79c8ae8b8c0f027d64d3012a074a65ab4403905b656` | 1 | 2.86 |
| 38945500 | 2025-12-02 | `0x220589de207694a49af83fdb9966062796c537ef5d19eb8eeb9fd3a5c9007c2b` | 2 | 5.9525 |
| 38945503 | 2025-12-02 | `0xa36998b0e5542f6d03dd13fe5e2a42bd29485adf7b9a48f40a9ebea5eb90eb60` | 1 | 3.0025 |
| 38945505 | 2025-12-02 | `0xe9bc9df0a0e63b5ef5075173327de45a8273b0fd681230571d3df948bad7c6f0` | 2 | 6.4100 |
| 38945509 | 2025-12-02 | `0x5a09d5bdf4e44b7e5afffd6c958af948872efe8bcaad4c37890c5e2c06875d26` | 3 | 12.8350 |
| 38945515 | 2025-12-02 | `0xaf1963cd26dd71e4c619ab280de97759ae2d74e2effd084a6f0d848f61e0dbd9` | 2 | 10.415 |
| 38945519 | 2025-12-02 | `0x30d49ab57e5c0f7f7fb4550b5d74fd21b7f66f690962449d65d846e05ff9fb1a` | 2 | 5.5250 |
| 38945523 | 2025-12-02 | `0xdb50270ee3a012ddf32528091651d7829b1496f9bdb68adc99aacadb62bba22e` | 2 | 11.9775 |
| 38945524 | 2025-12-02 | `0xb00a786bf22baccb105cc00e925709e7a9387c0106f65c320186b7cf2f91b0ce` | 1 | 5.305 |
| 38945530 | 2025-12-02 | `0x033281c99bdf7c30716ad67a357bcaa9dae174ea31864dfb94f93bf0ecb5ea60` | 1 | 2.8125 |
| 38945534 | 2025-12-02 | `0x4629b3a1ba23c08a6d17e1a657281636fed336a81638c5ce7279df7d76df94d3` | 1 | 5.3675 |
| 38945536 | 2025-12-02 | `0x2f0dc86707956b82d3585a489ecc34a6b36c8d1b99d9207fda6f638f934b63c1` | 1 | 5.3175 |
| 39594959 | 2025-12-17 | `0x1c76fccb92241148040b87caa1ef91ccbdd25dbf90cf49d9b0e5275833e867ef` | 1 | 5.35 |
| 39594963 | 2025-12-17 | `0xc8038042329df64d2b515b1c2f8a3d40c5765d8f0d2dd50afd9771e636657345` | 1 | 2.855 |
| 39594967 | 2025-12-17 | `0xff9559ce89963a6d501633e13a078fca70c968a2ab89722bc070983eae646f17` | 2 | 5.9450 |
| 39594971 | 2025-12-17 | `0xbc94eef39e9ef8425f03347f342f02a1905fc1c6690d8b3f2eeb6b79130e009a` | 1 | 2.9925 |
| 39594973 | 2025-12-17 | `0x5b0a53d168d2fcb54e3ddd81748e8cd75ab0dddc675787904bb19f42d01b7f9d` | 2 | 6.395 |
| 39594979 | 2025-12-17 | `0x45fb1ac066a2f88d147d26d4ff9ec31f19d1dbe3c6e92beec7c880992d2da95c` | 3 | 12.7725 |
| 39594983 | 2025-12-17 | `0x58defb8b9e79c6456b9c5461c4e05bfc336f2435a414b8d9580a7c1680a9692c` | 2 | 10.405 |
| 39594987 | 2025-12-17 | `0xca927505bbb46a9ed86e0d1e9ee8402ee9f1d45c905e2489db4eafe9baee8a13` | 2 | 5.5300 |
| 39594989 | 2025-12-17 | `0x8def3bb46b4f52d651da5d98d9d14bffe8425b2c89a37f4eff3cb06ce59cc627` | 2 | 11.905 |
| 39594991 | 2025-12-17 | `0x62fc45cab51f4fa6557e2b419a2e6bd0e62fdd54db07afc19e066ee4c0dd9626` | 1 | 5.2975 |
| 39594998 | 2025-12-17 | `0xaca6f4c8b1394d21ccea62d7ffe58ff511c1b0afa45ff61be63fec49c46d0cd7` | 1 | 2.8125 |
| 39595005 | 2025-12-17 | `0x9ae923da41cb55b71321c389f3840d9ed5ccda3aa879f1b553b211bf0c03d2f4` | 1 | 5.37 |
| 39595007 | 2025-12-17 | `0xfc8a03ac524e74a44e56dc9820d283475dc7dacb0ede762ac72d3ad47e1cf43b` | 1 | 5.317500000000001 |

Per pocket (deposits in; all withdrawn by the 3 batches):

| pocket | deposits | GHST in | first block | last block |
|---|---|---|---|---|
| `0x02f7da40a267d7ae6c48caf041968542c3c46589` | 8 | 49.9700000000000015 | 35315816 | 39594989 |
| `0x0c375f0a508f86709b675b4bbfdcef8d51de7ff3` | 8 | 22.1025 | 35315804 | 39594979 |
| `0x1c0c0b9581cca74581ecf8a5c31f82653c1ef8a2` | 8 | 22.4250 | 35315814 | 39594987 |
| `0x380e5e8d651cc708cf88b7a838035518fb4425a1` | 8 | 42.337500000000000 | 35315836 | 39595007 |
| `0x430a1a23bdeb6d50b0cc9bfc1f93992b582bc96f` | 8 | 22.7200 | 35315793 | 39594967 |
| `0x443d5f09fd9b11250b060bdd420c7a9c8c2066c0` | 8 | 46.0325 | 35315816 | 39594989 |
| `0x52265e2d4f82b0a363f5d045e2eb8769adb9ab39` | 4 | 10.8000 | 37768501 | 39594987 |
| `0x6933b1a218d189d4a4c189a1e7b674453f41c0de` | 8 | 42.8624999999999985 | 35315787 | 39594959 |
| `0x728f0baf79ebdfa336978c90f244324a0ba7bcff` | 8 | 22.7425 | 35315791 | 39594963 |
| `0x7323a5e018fe495bc5fb390de18ccd61fdd2d8eb` | 8 | 42.1975 | 35315819 | 39594991 |
| `0x8f64003ac2898edc02bf4a7ec4ab6537e4861368` | 8 | 22.3700 | 35315826 | 39594998 |
| `0x9c2e5e9686974338181b145109da56b4b4406b19` | 8 | 42.2699999999999985 | 35315809 | 39594983 |
| `0xa0173b0c67c4b96497c7185d047a00af27fce945` | 8 | 40.8125 | 35315809 | 39594983 |
| `0xa51d2128f62b122b0be9b0c6b47ad6b017cd8350` | 8 | 42.729999999999999 | 35315834 | 39595005 |
| `0xa9ebe0f3ad527f3531a15d4770edc2b82b006801` | 8 | 27.5075 | 35315799 | 39594973 |
| `0xaaeca339dec2b42cdc189e6df2b45fe8685fb6fb` | 8 | 23.5650 | 35315799 | 39594973 |
| `0xbc5699672c4ae61a951704acf2265fde7d9ec5ce` | 8 | 23.9600 | 35315796 | 39594971 |
| `0xdb084925e330a7bed6aab9d7828b4defe2b96dc1` | 8 | 32.1050 | 35315804 | 39594979 |
| `0xdfcebf9865f9cc40c590e0e5f45bf78105a6e6fa` | 8 | 24.6900 | 35315793 | 39594967 |
| `0xfba935526fafd92afcf7cc6472114458a6f77fb5` | 8 | 48.4300 | 35315804 | 39594979 |

Other tokens into the pockets in the same range (not GHST; outside the GHST gap; not analysed): `0x6ce9b0b0750f48274d8f59a4bc42bdc22574d686` erc721 ×20, `0x3b66262eacb826810a369611caa89b97f220e676` erc20 ×20, `0x1575f7f60a4acd04332987fb741b805af96fdb90` erc20 ×20, `0x5fac1810e3f782823bd3e33d1ee38096543c6c54` erc20 ×17, `0x45eccddc5c304223d5ea8db2fbdeb6fbb53ccc39` erc721 ×17, `0xc34f23943424188b700feaa9a88830e8b7d1ca23` erc721 ×6, `0x5e6e5831fb6dbcfb03bd60b4cfb61616faa19fe7` erc721 ×6, `0x4fa840dd1e1adf293dedfd90e2a605e5cfd8ac97` erc20 ×6, `0x88a5029f468b7c4cc4c1322ddb86959f75af86fe` erc20 ×3, `0xd8c309306adf2701b8d9da4ed8699d2496d07777` erc721 ×3, `0x8a183e87726bddf7ff6ff1b8440391141281cfef` erc20 ×2, `0xb96a7fa2dc5627eb76f91962e1e45e75e572c850` erc20 ×2, `0xd498ad357daa59492d03774a4ff76939f099cd1e` erc20 ×2, `0x6537aef3eb037e3da7f7ff6dbf52038dd6d7fc75` erc20 ×2, `0xfb584ace7f491e2930491a8d01a28db308aeb65f` erc20 ×1, `0x606d092d063b4008cd526432d486ba08e0b7a051` erc721 ×1, `0x82bb29d5004c8aa36a2d89fa982e1d3c8ae3b6c8` erc20 ×1, `0xe3d6d446b951cffe5c44a6cde91415d7db139df6` erc721 ×1.

## 2c. Spoofed-sender pattern in third-party pocket ERC-20 inflows (rule 7.4 check, 2026-10-28 20:4x PT; local data, 0 requests)
Source: `docs/evidence/p4_1_pockets.json` (HS2, all Transfer logs into the 24 pockets). There are 97 third-party ERC-20 inflow legs from
12 token contracts. **None of the 12 contracts is canonical Base USDC `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`, and none is any
other allowlisted token** (checked against `config/allowlist.txt`, 17 Base entries, which include USDC). The 9 third-party NFT
contracts (7 ERC-721, 2 ERC-1155) are not allowlisted either.
**Pattern:** in **11 of the 12 contracts (96 legs)**, the Transfer event is emitted by the token contract
itself but names **USDC `0x833589fc…`** as `from`. USDC never moved: a real USDC transfer is emitted by the USDC contract, and none of
these logs is. The `from` is a spoofed sender, so an explorer shows "USDC → your pocket". Every one of these txs calls the token contract
with the same selector `0x729ad39e` (a batch "airdrop" entry point), from an EOA that differs per token. The other contract
(`0x82bb29d5…`) names a non-USDC `from`, `0x239b9c1f…`. Booked per rule 7.4: `spam` at `pocket:<id>` (96 legs) and 1
`pocket_owner_mismatch` (`0x4fa840dd…` into gotchi 10774 before the wallet held it).

| token contract (emitter) | legs | legs with from = USDC | `from` in the event | tx sender (EOA) | txs | blocks | pockets |
|---|---|---|---|---|---|---|---|
| `0x8a183e87726bddf7ff6ff1b8440391141281cfef` | 2 | 2 | `0x833589fc…` | `0x2286607a2005836451addb8ad223b7b56de5b953` | 2 | 35316780–35316782 | 2 |
| `0x88a5029f468b7c4cc4c1322ddb86959f75af86fe` | 3 | 3 | `0x833589fc…` | `0xd51f718febfd85148e41d4ec5aaef03473657139` | 3 | 35953852–35954095 | 3 |
| `0xfb584ace7f491e2930491a8d01a28db308aeb65f` | 1 | 1 | `0x833589fc…` | `0x5112f082051ee6efbc4e14cb097f4197f89a0d04` | 1 | 36558670–36558670 | 1 |
| `0x82bb29d5004c8aa36a2d89fa982e1d3c8ae3b6c8` | 1 | 0 | `0x239b9c1f…` | `0x1c01d28689fe617fc00e5efa8d70996056f3e321` | 1 | 36600524–36600524 | 1 |
| `0xb96a7fa2dc5627eb76f91962e1e45e75e572c850` | 2 | 2 | `0x833589fc…` | `0xb9d65cc976e0864187076402de813abae02db3f1` | 2 | 37206032–37206034 | 2 |
| `0xd498ad357daa59492d03774a4ff76939f099cd1e` | 2 | 2 | `0x833589fc…` | `0xc6796e4f13bbbbb5e9480a612e8804a6dc140181` | 2 | 37250917–37250917 | 2 |
| `0x3b66262eacb826810a369611caa89b97f220e676` | 20 | 20 | `0x833589fc…` | `0x0dfea3b30fc7a5cdbf51009ac09badb65f2d31a9` | 3 | 38261846–38262124 | 20 |
| `0x5fac1810e3f782823bd3e33d1ee38096543c6c54` | 17 | 17 | `0x833589fc…` | `0xf1c374fb65599e9de67cb404cb8a59e2f8bdfcb9` | 3 | 38820491–38820642 | 17 |
| `0x1575f7f60a4acd04332987fb741b805af96fdb90` | 20 | 20 | `0x833589fc…` | `0xf1c374fb65599e9de67cb404cb8a59e2f8bdfcb9` | 1 | 38854779–38854779 | 20 |
| `0x6537aef3eb037e3da7f7ff6dbf52038dd6d7fc75` | 2 | 2 | `0x833589fc…` | `0xf1c374fb65599e9de67cb404cb8a59e2f8bdfcb9` | 1 | 38976600–38976600 | 2 |
| `0x4fa840dd1e1adf293dedfd90e2a605e5cfd8ac97` | 7 | 7 | `0x833589fc…` | `0x35d317fcafc3d408d6bffc778608910ae1ed2b79` | 6 | 39595198–39619219 | 7 |
| `0xcd6b003fd8b433e79137627267bc1ce177be368d` | 20 | 20 | `0x833589fc…` | `0x4458e8202b8d83180ee3aeb3ec2590e39a0d642c` | 4 | 40430000–40431225 | 20 |

## 3. Left unexplained (and why)
1. ~~**The GHST source for each of the 20 pockets.**~~ **Traced in §2b (H3, 20:18 PT).** History of the block: This needs a full-history `Transfer(*, pocket)` query, but:
   - **HyperSync:** HTTP 403 with the MBP abra's `ENVIO_API_TOKEN`. The token P3 used is in omarchywin's abra, which was **locked** and was not unlocked.
   - **2026-10-28 20:04 PT, omarchywin abra unlocked:** H3 (`scripts/p4_1_ghst_pockets.py`) with omarchywin's `ENVIO_API_TOKEN` also got **HTTP 403** (1 request). That token last got HTTP 200 on 2026-10-24 17:21 PT. Still not traced; the token needs renewing (user_default).
   - **Free RPC `eth_getLogs`:** base.drpc.org's free tier rejects wide ranges (HTTP 400, code 35).
   - **Blockscout API:** behind a Cloudflare challenge (403).

   **Next:** once omarchywin's abra is unlocked, the planned query H3 should take 2–6 HyperSync requests: Transfer logs with topic2 ∈ the 20 pockets plus topic1 ∈ pockets, all tokens. The candidates (mint, claim, another token address or proxy, a migration batch) are untested; the per-pocket amounts look like accrued rewards, but that is NOT established.
2. **The gotchi id of each pocket.** The canonical ledger's `pocket:<id>` locations map them, and reading it needs the ledger PG (abra).
3. **The name of the ETH distributor 0xf50326e1….** Public explorer pages show `Claimed(address,uint256)` and many claimants; the program behind it is not established.
4. **ETH after block 52112861.** Not probed (outside as_of).

## 4. Requests used (all attempts, from `logs/p4_1_reqlog.txt`)
| source | planned cap | used |
|---|---|---|
| HyperSync | 28 | **1** (HTTP 403; not retried) |
| RPC base.drpc.org (30/min, 1.5 s gap, host lock) | 370 | **187** attempts: 167 OK, 16 HTTP 400 (wide `eth_getLogs`, abandoned), 4 HTTP 408 retried |
| Blockscout | 30 | **2** (both 403 Cloudflare: 1 urllib, 1 curl) |

The request log records outcomes only, not methods. By design the RPC calls were `eth_getBalance` probes, tx/receipt/block reads, and `debug_traceTransaction` on candidate txs only. None used a key.
