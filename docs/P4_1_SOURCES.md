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

## 3. Left unexplained (and why)
1. **The GHST source for each of the 20 pockets.** Not traced. This needs a full-history `Transfer(*, pocket)` query, but:
   - **HyperSync:** HTTP 403 with the MBP abra's `ENVIO_API_TOKEN`. The token P3 used is in omarchywin's abra, which was **locked** and was not unlocked.
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
