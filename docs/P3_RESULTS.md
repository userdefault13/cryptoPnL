# P3 results: Base (8453), 408-retry rerun at `c22d59a`: **PASS**

One rerun on `cryptopnl_p3_base`, launched once at **2026-10-24 17:21:38 PDT** (epoch 1792887698, `logs/p3_rerun_408.start`) with
`CRYPTOPNL_DSN=postgresql:///cryptopnl_p3_base setsid nohup ~/.local/bin/abra run cryptoPnL -k ENVIO_API_TOKEN -- /tmp/p22run.sh scripts/p3_test.sh 8453`.
The log last changed at 18:13:27 PDT. Full output: `docs/evidence/p3_rerun_408_8453.log`. This rerun's request log (lines at or after the start epoch, RPC path redacted):
`docs/evidence/p3_rerun_408_net_requests_8453.log`. Code: `1b647ba` (408 retry), `acaab35` (migration 012), `b1156d1` (started_at / rpc_retries / probe GHST ±3%), `c22d59a` (tests).

Final line: `P3 PASS chain 8453`.

| Check (architect acceptance) | Result |
|---|---|
| C1 (priced, or unpriced with an accepted reason) | **PASS**: `pass_c1: true`, `c1_failures: []`, unpriced overall `{"stale_pool": 25}` (per asset below), 0 rpc_error, 0 bad_response; 25/25 stale samples re-verified from cached `pool_swap` logs (0 lower-bound ages) |
| GLTR probe | **PASS 5/5**: each GLTR → GHST → USDC, `dex_reserves_thin`, low, `low_confidence`; GHST within ±3% of DefiLlama at **5/5** probe blocks (-2.217% to 0.791%), `ghst_outside_3pct: []` |
| C2 (GHST vs DefiLlama ±3%) | **PASS**: 20/20 gated pairs, -0.655% to 1.005%, max abs 1.005%; 0 outside (gated or report only), `pass_dex_vs_api_3pct: true` |
| C3 (every entry priced or flagged) | **PASS**: entries 1321, priced 836, flagged 518, **neither 0**, `no_price` **0** (was 20 at 13 blocks) |
| RPC errors after retries | **0** (`price_run.rpc_errors 0`, sample pass `rpc_errors 0`); retries **0** (`price_run.rpc_retries 0`; ledger STATS `"408": 0, "retries": 0`; 0 × 408 and 0 non-200 outcomes in the request log since the start) |
| price-report exit 0 | **PASS** (rc 0, `"pass": true, "failures": []`), reading `price_run` id 2 written by this run (row below) |
| HyperSync | 1 request, 0 429s, busiest 60 s = 1 (limit 5) → OK |
| RPC | 1530 requests (request log since start: 1556 attempts incl. 1 HyperSync + 25 DefiLlama), all 200, 0 × 408, 0 429s; busiest 60 s = 30 (limit 30), min gap 1.510 s |
| Narrow ledger md5 | **210a71d811fd872a970b1d11770ced05** over 1321 rows (recomputed read-only after the run) |
| GHST fall-through after an RPC error | **0** (was 2) |

## price_run row read by price-report (this rerun)
Read-only `SELECT * FROM price_run` (times in PDT): `id=2 | chain 8453 | started_at 2026-10-24 17:21:44.276652 | finished_at 2026-10-24 18:02:49.315273 |
entries 1321 | rpc_calls 1214 | rpc_errors 0 | rpc_retries 0 | fallthrough_after_rpc_error 0 | detail {"rpc_errors": [], "fallthrough": []}`.
started_at (17:21:44) is after the launch (17:21:38), and finished_at is after started_at (41 min 05 s, the `clock_timestamp()` fix from migration 012).
Row id=1 is the earlier C1 rerun (15 errors; its `finished_at` 08:41:47 is the old `now()` transaction start, and started_at is NULL because it predates 012).

## The 20 entries left `no_price` last run, now priced
`ledger_entry` has 0 `no_price` rows on 8453 (flags: low_confidence 33, nft_no_trade 8, pending_basis 81, spam 340, untracked 56, none 803).
Every entry at the 13 former 408 blocks (27388021, 27388025, 33903453, 42297928, 42343274, 42362605, 42366633, 42367506, 42367568, 42420163,
42448898, 43748241, 49402932) has a price: fees/withdrawals `dex_slot0` high, escrow_out at 33903453 `dex_reserves` medium, escrow_return/income at
42448898 `dex_slot0` high, auction at 43748241 `dex_slot0`/`trade` high, and the 4 alchemica income entries at 49402932 `dex_reserves_thin` low (low_confidence, as before).

## C1: 20 sampled blocks (`docs/evidence/p3_sample_8453.jsonl`)
Seed 3, start block 48775083, blocks [48778781, 48968245, 49319375, 49408055, 49605307, 49705890, 50336888, 51029666, 51093930, 51096573, 51096720, 51157926, 51157981, 51200957, 51283821, 51481434, 51962756, 51965171, 52006332, 52111288]. Sample and probe RPC calls: 310; RPC errors in that pass: 0.

| asset | C1 scope | priced | unpriced (by reason) | stale age days (min–max, re-verified) | C1 ok |
|---|---|---|---|---|---|
| ALPHA | yes | 12/20 | 8 {"stale_pool": 8} | 7.69–16.66 | 20/20 |
| FUD | yes | 12/20 | 8 {"stale_pool": 8} | 7.83–16.8 | 20/20 |
| USDC | yes | 20/20 | 0  | – | 20/20 |
| FOMO | yes | 12/20 | 8 {"stale_pool": 8} | 7.82–16.79 | 20/20 |
| GHST | yes | 20/20 | 0  | – | 20/20 |
| KEK | yes | 19/20 | 1 {"stale_pool": 1} | 10.41–10.41 | 20/20 |
| ETH | yes | 20/20 | 0  | – | 20/20 |
| WETH | report only | 20/20 | 0  | – | 20/20 |
| cbBTC | report only | 20/20 | 0  | – | 20/20 |

### Every unpriced sample, re-derived from the cached Swap logs (`verify_stale`, SQL on `pool_swap` / `pool_swap_scan`)
Age days = blocks × 2 s / 86,400 (Base 2 s blocks). The 7-day window is 302,400 blocks. 25/25 re-checks ok; 0 ages are lower bounds.

| block | asset | reason | pool | last swap block (pricer) | SQL re-derived last swap | age days | lower bound | re-check |
|---|---|---|---|---|---|---|---|---|
| 51093930 | ALPHA | stale_pool | `0x0ba2a49a…` | 50761766 | 50761766 | 7.69 | False | ok |
| 51093930 | FUD | stale_pool | `0xeae2fb93…` | 50755692 | 50755692 | 7.83 | False | ok |
| 51093930 | FOMO | stale_pool | `0x62ab7d55…` | 50755966 | 50755966 | 7.82 | False | ok |
| 51096573 | ALPHA | stale_pool | `0x0ba2a49a…` | 50761766 | 50761766 | 7.75 | False | ok |
| 51096573 | FUD | stale_pool | `0xeae2fb93…` | 50755692 | 50755692 | 7.89 | False | ok |
| 51096573 | FOMO | stale_pool | `0x62ab7d55…` | 50755966 | 50755966 | 7.88 | False | ok |
| 51096720 | ALPHA | stale_pool | `0x0ba2a49a…` | 50761766 | 50761766 | 7.75 | False | ok |
| 51096720 | FUD | stale_pool | `0xeae2fb93…` | 50755692 | 50755692 | 7.89 | False | ok |
| 51096720 | FOMO | stale_pool | `0x62ab7d55…` | 50755966 | 50755966 | 7.89 | False | ok |
| 51157926 | ALPHA | stale_pool | `0x0ba2a49a…` | 50761766 | 50761766 | 9.17 | False | ok |
| 51157926 | FUD | stale_pool | `0xeae2fb93…` | 50755692 | 50755692 | 9.31 | False | ok |
| 51157926 | FOMO | stale_pool | `0x62ab7d55…` | 50755966 | 50755966 | 9.3 | False | ok |
| 51157981 | ALPHA | stale_pool | `0x0ba2a49a…` | 50761766 | 50761766 | 9.17 | False | ok |
| 51157981 | FUD | stale_pool | `0xeae2fb93…` | 50755692 | 50755692 | 9.31 | False | ok |
| 51157981 | FOMO | stale_pool | `0x62ab7d55…` | 50755966 | 50755966 | 9.31 | False | ok |
| 51200957 | ALPHA | stale_pool | `0x0ba2a49a…` | 50761766 | 50761766 | 10.17 | False | ok |
| 51200957 | FUD | stale_pool | `0xeae2fb93…` | 50755692 | 50755692 | 10.31 | False | ok |
| 51200957 | FOMO | stale_pool | `0x62ab7d55…` | 50755966 | 50755966 | 10.3 | False | ok |
| 51283821 | ALPHA | stale_pool | `0x0ba2a49a…` | 50761766 | 50761766 | 12.08 | False | ok |
| 51283821 | FUD | stale_pool | `0xeae2fb93…` | 50755692 | 50755692 | 12.23 | False | ok |
| 51283821 | FOMO | stale_pool | `0x62ab7d55…` | 50755966 | 50755966 | 12.22 | False | ok |
| 51481434 | ALPHA | stale_pool | `0x0ba2a49a…` | 50761766 | 50761766 | 16.66 | False | ok |
| 51481434 | FUD | stale_pool | `0xeae2fb93…` | 50755692 | 50755692 | 16.8 | False | ok |
| 51481434 | FOMO | stale_pool | `0x62ab7d55…` | 50755966 | 50755966 | 16.79 | False | ok |
| 51481434 | KEK | stale_pool | `0x699b4eb3…` | 51031687 | 51031687 | 10.41 | False | ok |

## GLTR probe (pool `0xa83b31d701633b8edcfba55b93ddbc202d8a4621`, Aerodrome vAMM-GLTR/GHST; 29 cached swap blocks at or after 48775083; seed 3)
Blocks [50512192, 50561002, 50594622, 50596594, 50596838]: **5/5 pass**. Checks per block: priced, thin tier, low, flagged, pool, quote GHST, GHST→USDC, swap recent (SQL), GHST within ±3%.

| block | GLTR price (USDC) | source | conf. | flag | GLTR/GHST pool depth USD (quote side) | last swap block | checks |
|---|---|---|---|---|---|---|---|
| 50512192 | 1.678563e-08 | dex_reserves_thin | low | low_confidence | 1319.47 (659.74) | 50512192 | all 9 pass |
| 50561002 | 1.671549e-08 | dex_reserves_thin | low | low_confidence | 1313.96 (656.98) | 50561002 | all 9 pass |
| 50594622 | 3.906237e-08 | dex_reserves_thin | low | low_confidence | 3008.36 (1504.18) | 50594622 | all 9 pass |
| 50596594 | 3.945362e-08 | dex_reserves_thin | low | low_confidence | 2921.97 (1460.98) | 50596594 | all 9 pass |
| 50596838 | 4.017945e-08 | dex_reserves_thin | low | low_confidence | 2955.57 (1477.78) | 50596838 | all 9 pass |

### GHST leg vs DefiLlama at each probe block
GHST is priced from the Uniswap v3 GHST/USDC pool at each block and compared with the nearest DefiLlama historical price. Depth = USDC side (balanceOf).

| block | GHST/USDC pool | kind | GHST (pool) | GHST (DefiLlama) | API ts → block ts (s) | dev % | pool GHST balance | pool USDC balance | pool depth USD | within ±3% |
|---|---|---|---|---|---|---|---|---|---|---|
| 50512192 | `0x41d4934322f2bd6fe1dbe4124070fe61651a2067` | v3 | 0.046068 | 0.045991 | +231 | 0.165 | 6379831.04 | 293900.283288 | 293900.28 | True |
| 50561002 | `0x41d4934322f2bd6fe1dbe4124070fe61651a2067` | v3 | 0.045875 | 0.045515 | +641 | 0.791 | 6393549.10 | 293293.934482 | 293293.93 | True |
| 50594622 | `0x41d4934322f2bd6fe1dbe4124070fe61651a2067` | v3 | 0.102904 | 0.105238 | -519 | -2.217 | 4304005.57 | 444126.969807 | 444126.97 | True |
| 50596594 | `0x41d4934322f2bd6fe1dbe4124070fe61651a2067` | v3 | 0.096116 | 0.097889 | -175 | -1.811 | 4455777.08 | 429548.651231 | 429548.65 | True |
| 50596838 | `0x41d4934322f2bd6fe1dbe4124070fe61651a2067` | v3 | 0.096563 | 0.097889 | +313 | -1.355 | 4445656.61 | 430558.41443 | 430558.41 | True |

All 5 within ±3%, so the GHST move from about 0.046 (50512192/50561002) to about 0.096–0.103 (50594622–50596838) matches DefiLlama and is not a pool artifact. Pricing unchanged.

## C3 / coverage (`docs/evidence/p3_coverage_8453.json`)
by_source: trade 40, numeraire 45, dex_slot0 670, dex_reserves 50, dex_reserves_thin 31. by_flag: spam 340, untracked 56, pending_basis 81,
low_confidence 33, nft_no_trade 8 (no `no_price`). by_label: high 744, medium 59, low 33. zero_prices 0. Neither: 0.

## Rate limits (`docs/evidence/p3_hypersync_8453.txt`, `p3_rpc_8453.txt`, `p3_defillama_8453.txt`)
- HyperSync: requests=1, status_200=1, 429s=0, busiest_60s_window=1 (ending 17:21:43 PDT), limit=5 → OK. Pool-swap scan forward 53,033,481 → 53,049,075: 0 new swaps.
- RPC: requests=1530, status_200=1530, 429s=0, 0 × 408, busiest_60s_window=30 (ending 17:22:27 PDT), limit=30 → OK, min_gap_s=1.510.
- DefiLlama: requests=25, status_200=25, 429s=0 (20 C2 + 5 probe GHST checks).

## Ledger unchanged
classify#1 = classify#2: `ledger_rows 1321, ledger_md5 58cc79730edcf6b11a1e8ee39ea3ab97` (report md5), review 1 / e7de420e…. Narrow md5 recomputed read-only
after the run: **210a71d811fd872a970b1d11770ced05** (1321 rows). tx-index: 0 candidates. Migration applied this run: `012_p3_price_run_retries.sql`.

## Not verified / open
1. The 408 retry path was not exercised in this run (the free RPC returned 0 × 408), so `rpc_retries` is 0. The retry behavior is covered by unit tests (`c22d59a`) only.
2. `pass_all_priced: false` is informational: ALPHA/FUD/FOMO 12/20 and KEK 19/20 are stale_pool (accepted C1 reason).
3. Sepolia not run.

## Earlier runs
- C1 rerun at `d909779` (2026-10-24 08:41 PDT): C1 PASS, GLTR probe 5/5, C2 PASS (−0.655% to +1.005%), but **15 × HTTP 408** (free-plan timeout) → 15 RPC errors,
  20 `no_price` entries at 13 blocks, 2 fall-throughs, price-report rc 1. Evidence: `p3_rerun_c1_8453.log`, `p3_rerun_c1_net_requests_8453.log`; P3_RESULTS at `518c428`.
- First run at `fd12039` (2026-10-23 22:45 PDT): C1 FAIL under the original rule, C2 PASS (max 1.005%), C3 PASS, 0 RPC errors. Evidence in git at `cd23af9`.

## Appendix: every C1 sample
| block | asset | price (USDC) | source | conf. | flag | pool | pool depth USD | last swap block | API | dev % |
|---|---|---|---|---|---|---|---|---|---|---|
| 48778781 | ALPHA | 1.41147e-05 | dex_reserves_thin | low | low_confidence | `0x0ba2a49a…` | 623.87 | 48681867 | – | – |
| 48778781 | FUD | 2.68919e-06 | dex_reserves_thin | low | low_confidence | `0xeae2fb93…` | 527.76 | 48681851 | – | – |
| 48778781 | USDC | 1 | numeraire | high | – | – | – | – | – | – |
| 48778781 | FOMO | 8.08022e-06 | dex_reserves_thin | low | low_confidence | `0x62ab7d55…` | 667.28 | 48681859 | – | – |
| 48778781 | GHST | 0.0491835 | dex_slot0 | high | – | `0x41d49343…` | 305783.43 | – | 0.0493924 | -0.423 |
| 48778781 | KEK | 2.97441e-05 | dex_reserves_thin | low | low_confidence | `0x699b4eb3…` | 501.92 | 48681875 | – | – |
| 48778781 | ETH | 1842.02 | dex_slot0 | high | – | `0xd0b53d92…` | 2579095.05 | – | 1841.92 | 0.005 |
| 48778781 | WETH | 1842.02 | dex_slot0 | high | – | `0xd0b53d92…` | 2579095.05 | – | 1841.92 | 0.005 |
| 48778781 | cbBTC | 63922.4 | dex_slot0 | high | – | `0xfbb6eed8…` | 3480134.52 | – | 63917.6 | 0.007 |
| 48968245 | ALPHA | 1.34073e-05 | dex_reserves_thin | low | low_confidence | `0x0ba2a49a…` | 594.73 | 48876605 | – | – |
| 48968245 | FUD | 2.54835e-06 | dex_reserves_thin | low | low_confidence | `0xeae2fb93…` | 502.51 | 48876593 | – | – |
| 48968245 | USDC | 1 | numeraire | high | – | – | – | – | – | – |
| 48968245 | FOMO | 7.6338e-06 | dex_reserves_thin | low | low_confidence | `0x62ab7d55…` | 634.39 | 48876599 | – | – |
| 48968245 | GHST | 0.0470541 | dex_slot0 | high | – | `0x41d49343…` | 298102.15 | – | 0.0473643 | -0.655 |
| 48968245 | KEK | 2.81324e-05 | dex_reserves_thin | low | low_confidence | `0x699b4eb3…` | 477.45 | 48876612 | – | – |
| 48968245 | ETH | 1919.24 | dex_slot0 | high | – | `0xd0b53d92…` | 3399086.70 | – | 1918.15 | 0.057 |
| 48968245 | WETH | 1919.24 | dex_slot0 | high | – | `0xd0b53d92…` | 3399086.70 | – | 1918.15 | 0.057 |
| 48968245 | cbBTC | 65612.2 | dex_slot0 | high | – | `0xfbb6eed8…` | 3368148.38 | – | 65565.3 | 0.072 |
| 49319375 | ALPHA | 1.23418e-05 | dex_reserves_thin | low | low_confidence | `0x0ba2a49a…` | 552.42 | 49276974 | – | – |
| 49319375 | FUD | 2.433e-06 | dex_reserves_thin | low | low_confidence | `0xeae2fb93…` | 476.29 | 49319375 | – | – |
| 49319375 | USDC | 1 | numeraire | high | – | – | – | – | – | – |
| 49319375 | FOMO | 7.22068e-06 | dex_reserves_thin | low | low_confidence | `0x62ab7d55…` | 597.81 | 49319360 | – | – |
| 49319375 | GHST | 0.0447301 | dex_slot0 | high | – | `0x41d49343…` | 292181.62 | – | 0.0445315 | 0.446 |
| 49319375 | KEK | 2.60368e-05 | dex_reserves_thin | low | low_confidence | `0x699b4eb3…` | 444.87 | 49277004 | – | – |
| 49319375 | ETH | 1922.36 | dex_slot0 | high | – | `0xd0b53d92…` | 3237341.16 | – | 1921.7 | 0.034 |
| 49319375 | WETH | 1922.36 | dex_slot0 | high | – | `0xd0b53d92…` | 3237341.16 | – | 1921.7 | 0.034 |
| 49319375 | cbBTC | 64875.5 | dex_slot0 | high | – | `0xfbb6eed8…` | 3863713.89 | – | 64836.3 | 0.06 |
| 49408055 | ALPHA | 1.24001e-05 | dex_reserves_thin | low | low_confidence | `0x0ba2a49a…` | 551.50 | 49329735 | – | – |
| 49408055 | FUD | 2.37743e-06 | dex_reserves_thin | low | low_confidence | `0xeae2fb93…` | 468.93 | 49329715 | – | – |
| 49408055 | USDC | 1 | numeraire | high | – | – | – | – | – | – |
| 49408055 | FOMO | 7.0449e-06 | dex_reserves_thin | low | low_confidence | `0x62ab7d55…` | 588.12 | 49329726 | – | – |
| 49408055 | GHST | 0.0443718 | dex_slot0 | high | – | `0x41d49343…` | 291054.86 | – | 0.0440681 | 0.689 |
| 49408055 | KEK | 2.60746e-05 | dex_reserves_thin | low | low_confidence | `0x699b4eb3…` | 443.41 | 49329743 | – | – |
| 49408055 | ETH | 1861.76 | dex_slot0 | high | – | `0xd0b53d92…` | 2491560.85 | – | 1862.32 | -0.03 |
| 49408055 | WETH | 1861.76 | dex_slot0 | high | – | `0xd0b53d92…` | 2491560.85 | – | 1862.32 | -0.03 |
| 49408055 | cbBTC | 62783.8 | dex_slot0 | high | – | `0xfbb6eed8…` | 2655028.31 | – | 62774.7 | 0.014 |
| 49605307 | ALPHA | 1.21282e-05 | dex_reserves_thin | low | low_confidence | `0x0ba2a49a…` | 539.41 | 49329735 | – | – |
| 49605307 | FUD | 2.32531e-06 | dex_reserves_thin | low | low_confidence | `0xeae2fb93…` | 458.65 | 49329715 | – | – |
| 49605307 | USDC | 1 | numeraire | high | – | – | – | – | – | – |
| 49605307 | FOMO | 6.89045e-06 | dex_reserves_thin | low | low_confidence | `0x62ab7d55…` | 575.22 | 49329726 | – | – |
| 49605307 | GHST | 0.043399 | dex_slot0 | high | – | `0x41d49343…` | 286525.53 | – | 0.0433742 | 0.057 |
| 49605307 | KEK | 2.5503e-05 | dex_reserves_thin | low | low_confidence | `0x699b4eb3…` | 433.69 | 49329743 | – | – |
| 49605307 | ETH | 1911.14 | dex_slot0 | high | – | `0xd0b53d92…` | 3059559.05 | – | 1910.82 | 0.017 |
| 49605307 | WETH | 1911.14 | dex_slot0 | high | – | `0xd0b53d92…` | 3059559.05 | – | 1910.82 | 0.017 |
| 49605307 | cbBTC | 64777.7 | dex_slot0 | high | – | `0xfbb6eed8…` | 3984575.80 | – | 64755.3 | 0.035 |
| 49705890 | ALPHA | 1.22691e-05 | dex_reserves_thin | low | low_confidence | `0x0ba2a49a…` | 547.85 | 49657271 | – | – |
| 49705890 | FUD | 2.35222e-06 | dex_reserves_thin | low | low_confidence | `0xeae2fb93…` | 465.81 | 49657195 | – | – |
| 49705890 | USDC | 1 | numeraire | high | – | – | – | – | – | – |
| 49705890 | FOMO | 6.97854e-06 | dex_reserves_thin | low | low_confidence | `0x62ab7d55…` | 584.56 | 49657241 | – | – |
| 49705890 | GHST | 0.0442533 | dex_slot0 | high | – | `0x41d49343…` | 289699.25 | – | 0.0443037 | -0.114 |
| 49705890 | KEK | 2.57565e-05 | dex_reserves_thin | low | low_confidence | `0x699b4eb3…` | 440.10 | 49657297 | – | – |
| 49705890 | ETH | 1922.73 | dex_slot0 | high | – | `0xd0b53d92…` | 3170748.63 | – | 1922.93 | -0.01 |
| 49705890 | WETH | 1922.73 | dex_slot0 | high | – | `0xd0b53d92…` | 3170748.63 | – | 1922.93 | -0.01 |
| 49705890 | cbBTC | 65109 | dex_slot0 | high | – | `0xfbb6eed8…` | 4376868.24 | – | 65108.9 | 0.0 |
| 50336888 | ALPHA | 1.25616e-05 | dex_reserves_thin | low | low_confidence | `0x0ba2a49a…` | 566.62 | 50287973 | – | – |
| 50336888 | FUD | 2.37142e-06 | dex_reserves_thin | low | low_confidence | `0xeae2fb93…` | 478.07 | 50287959 | – | – |
| 50336888 | USDC | 1 | numeraire | high | – | – | – | – | – | – |
| 50336888 | FOMO | 6.88377e-06 | dex_reserves_thin | low | low_confidence | `0x62ab7d55…` | 593.43 | 50287967 | – | – |
| 50336888 | GHST | 0.0462352 | dex_slot0 | high | – | `0x41d49343…` | 294537.96 | – | 0.0462444 | -0.02 |
| 50336888 | KEK | 2.5595e-05 | dex_reserves_thin | low | low_confidence | `0x699b4eb3…` | 448.44 | 50287980 | – | – |
| 50336888 | ETH | 2380.71 | dex_slot0 | high | – | `0xd0b53d92…` | 2791532.14 | – | 2381.57 | -0.036 |
| 50336888 | WETH | 2380.71 | dex_slot0 | high | – | `0xd0b53d92…` | 2791532.14 | – | 2381.57 | -0.036 |
| 50336888 | cbBTC | 76228.4 | dex_slot0 | high | – | `0xfbb6eed8…` | 5430223.23 | – | 76241.7 | -0.017 |
| 51029666 | ALPHA | 1.82454e-05 | dex_reserves_thin | low | low_confidence | `0x0ba2a49a…` | 787.30 | 50761766 | – | – |
| 51029666 | FUD | 3.43339e-06 | dex_reserves_thin | low | low_confidence | `0xeae2fb93…` | 663.20 | 50755692 | – | – |
| 51029666 | USDC | 1 | numeraire | high | – | – | – | – | – | – |
| 51029666 | FOMO | 9.73315e-06 | dex_reserves_thin | low | low_confidence | `0x62ab7d55…` | 813.54 | 50755966 | – | – |
| 51029666 | GHST | 0.0614559 | dex_slot0 | high | – | `0x41d49343…` | 341451.06 | – | 0.0611278 | 0.537 |
| 51029666 | KEK | 3.75572e-05 | dex_reserves_thin | low | low_confidence | `0x699b4eb3…` | 627.80 | 50844837 | – | – |
| 51029666 | ETH | 2467.71 | dex_slot0 | high | – | `0xd0b53d92…` | 3429736.07 | – | 2467.15 | 0.023 |
| 51029666 | WETH | 2467.71 | dex_slot0 | high | – | `0xd0b53d92…` | 3429736.07 | – | 2467.15 | 0.023 |
| 51029666 | cbBTC | 78418.8 | dex_slot0 | high | – | `0xfbb6eed8…` | 4148712.63 | – | 78425.2 | -0.008 |
| 51093930 | ALPHA | **unpriced** (stale_pool) | – | – | no_price | – | – | – | – | – |
| 51093930 | FUD | **unpriced** (stale_pool) | – | – | no_price | – | – | – | – | – |
| 51093930 | USDC | 1 | numeraire | high | – | – | – | – | – | – |
| 51093930 | FOMO | **unpriced** (stale_pool) | – | – | no_price | – | – | – | – | – |
| 51093930 | GHST | 0.0601701 | dex_slot0 | high | – | `0x41d49343…` | 337879.86 | – | 0.0602594 | -0.148 |
| 51093930 | KEK | 3.69451e-05 | dex_reserves_thin | low | low_confidence | `0x699b4eb3…` | 617.57 | 51031687 | – | – |
| 51093930 | ETH | 2494.06 | dex_slot0 | high | – | `0xd0b53d92…` | 3770808.90 | – | 2495.37 | -0.052 |
| 51093930 | WETH | 2494.06 | dex_slot0 | high | – | `0xd0b53d92…` | 3770808.90 | – | 2495.37 | -0.052 |
| 51093930 | cbBTC | 78741.4 | dex_slot0 | high | – | `0xfbb6eed8…` | 4686051.48 | – | 78726.8 | 0.019 |
| 51096573 | ALPHA | **unpriced** (stale_pool) | – | – | no_price | – | – | – | – | – |
| 51096573 | FUD | **unpriced** (stale_pool) | – | – | no_price | – | – | – | – | – |
| 51096573 | USDC | 1 | numeraire | high | – | – | – | – | – | – |
| 51096573 | FOMO | **unpriced** (stale_pool) | – | – | no_price | – | – | – | – | – |
| 51096573 | GHST | 0.0601701 | dex_slot0 | high | – | `0x41d49343…` | 337879.86 | – | 0.0602634 | -0.155 |
| 51096573 | KEK | 3.69451e-05 | dex_reserves_thin | low | low_confidence | `0x699b4eb3…` | 617.57 | 51031687 | – | – |
| 51096573 | ETH | 2480.8 | dex_slot0 | high | – | `0xd0b53d92…` | 3556919.48 | – | 2481.84 | -0.042 |
| 51096573 | WETH | 2480.8 | dex_slot0 | high | – | `0xd0b53d92…` | 3556919.48 | – | 2481.84 | -0.042 |
| 51096573 | cbBTC | 78528 | dex_slot0 | high | – | `0xfbb6eed8…` | 4593040.84 | – | 78505.3 | 0.029 |
| 51096720 | ALPHA | **unpriced** (stale_pool) | – | – | no_price | – | – | – | – | – |
| 51096720 | FUD | **unpriced** (stale_pool) | – | – | no_price | – | – | – | – | – |
| 51096720 | USDC | 1 | numeraire | high | – | – | – | – | – | – |
| 51096720 | FOMO | **unpriced** (stale_pool) | – | – | no_price | – | – | – | – | – |
| 51096720 | GHST | 0.0601701 | dex_slot0 | high | – | `0x41d49343…` | 337879.86 | – | 0.0601951 | -0.041 |
| 51096720 | KEK | 3.69451e-05 | dex_reserves_thin | low | low_confidence | `0x699b4eb3…` | 617.57 | 51031687 | – | – |
| 51096720 | ETH | 2474.76 | dex_slot0 | high | – | `0xd0b53d92…` | 3463277.39 | – | 2474.72 | 0.002 |
| 51096720 | WETH | 2474.76 | dex_slot0 | high | – | `0xd0b53d92…` | 3463277.39 | – | 2474.72 | 0.002 |
| 51096720 | cbBTC | 78390.3 | dex_slot0 | high | – | `0xfbb6eed8…` | 4535606.78 | – | 78379.9 | 0.013 |
| 51157926 | ALPHA | **unpriced** (stale_pool) | – | – | no_price | – | – | – | – | – |
| 51157926 | FUD | **unpriced** (stale_pool) | – | – | no_price | – | – | – | – | – |
| 51157926 | USDC | 1 | numeraire | high | – | – | – | – | – | – |
| 51157926 | FOMO | **unpriced** (stale_pool) | – | – | no_price | – | – | – | – | – |
| 51157926 | GHST | 0.0634994 | dex_slot0 | high | – | `0x41d49343…` | 353749.95 | – | 0.0629506 | 0.872 |
| 51157926 | KEK | 3.89894e-05 | dex_reserves_thin | low | low_confidence | `0x699b4eb3…` | 651.74 | 51031687 | – | – |
| 51157926 | ETH | 2461.86 | dex_slot0 | high | – | `0xd0b53d92…` | 3461955.72 | – | 2460.01 | 0.075 |
| 51157926 | WETH | 2461.86 | dex_slot0 | high | – | `0xd0b53d92…` | 3461955.72 | – | 2460.01 | 0.075 |
| 51157926 | cbBTC | 77131.1 | dex_slot0 | high | – | `0xfbb6eed8…` | 4040539.69 | – | 77125.2 | 0.008 |
| 51157981 | ALPHA | **unpriced** (stale_pool) | – | – | no_price | – | – | – | – | – |
| 51157981 | FUD | **unpriced** (stale_pool) | – | – | no_price | – | – | – | – | – |
| 51157981 | USDC | 1 | numeraire | high | – | – | – | – | – | – |
| 51157981 | FOMO | **unpriced** (stale_pool) | – | – | no_price | – | – | – | – | – |
| 51157981 | GHST | 0.0634994 | dex_slot0 | high | – | `0x41d49343…` | 353749.95 | – | 0.0629506 | 0.872 |
| 51157981 | KEK | 3.89894e-05 | dex_reserves_thin | low | low_confidence | `0x699b4eb3…` | 651.74 | 51031687 | – | – |
| 51157981 | ETH | 2461.88 | dex_slot0 | high | – | `0xd0b53d92…` | 3462102.48 | – | 2459.53 | 0.095 |
| 51157981 | WETH | 2461.88 | dex_slot0 | high | – | `0xd0b53d92…` | 3462102.48 | – | 2459.53 | 0.095 |
| 51157981 | cbBTC | 77131.1 | dex_slot0 | high | – | `0xfbb6eed8…` | 4040539.69 | – | 77127.6 | 0.005 |
| 51200957 | ALPHA | **unpriced** (stale_pool) | – | – | no_price | – | – | – | – | – |
| 51200957 | FUD | **unpriced** (stale_pool) | – | – | no_price | – | – | – | – | – |
| 51200957 | USDC | 1 | numeraire | high | – | – | – | – | – | – |
| 51200957 | FOMO | **unpriced** (stale_pool) | – | – | no_price | – | – | – | – | – |
| 51200957 | GHST | 0.0648552 | dex_slot0 | high | – | `0x41d49343…` | 368728.09 | – | 0.0648204 | 0.054 |
| 51200957 | KEK | 3.98218e-05 | dex_reserves_thin | low | low_confidence | `0x699b4eb3…` | 665.66 | 51031687 | – | – |
| 51200957 | ETH | 2510.39 | dex_slot0 | high | – | `0xd0b53d92…` | 3803233.92 | – | 2513.27 | -0.114 |
| 51200957 | WETH | 2510.39 | dex_slot0 | high | – | `0xd0b53d92…` | 3803233.92 | – | 2513.27 | -0.114 |
| 51200957 | cbBTC | 77216 | dex_slot0 | high | – | `0xfbb6eed8…` | 3960495.56 | – | 77209.9 | 0.008 |
| 51283821 | ALPHA | **unpriced** (stale_pool) | – | – | no_price | – | – | – | – | – |
| 51283821 | FUD | **unpriced** (stale_pool) | – | – | no_price | – | – | – | – | – |
| 51283821 | USDC | 1 | numeraire | high | – | – | – | – | – | – |
| 51283821 | FOMO | **unpriced** (stale_pool) | – | – | no_price | – | – | – | – | – |
| 51283821 | GHST | 0.0643954 | dex_slot0 | high | – | `0x41d49343…` | 366002.33 | – | 0.0640949 | 0.469 |
| 51283821 | KEK | 3.95395e-05 | dex_reserves_thin | low | low_confidence | `0x699b4eb3…` | 660.94 | 51031687 | – | – |
| 51283821 | ETH | 2512.61 | dex_slot0 | high | – | `0xd0b53d92…` | 3845199.27 | – | 2513.03 | -0.016 |
| 51283821 | WETH | 2512.61 | dex_slot0 | high | – | `0xd0b53d92…` | 3845199.27 | – | 2513.03 | -0.016 |
| 51283821 | cbBTC | 77651.8 | dex_slot0 | high | – | `0xfbb6eed8…` | 4178745.99 | – | 77644.4 | 0.009 |
| 51481434 | ALPHA | **unpriced** (stale_pool) | – | – | no_price | – | – | – | – | – |
| 51481434 | FUD | **unpriced** (stale_pool) | – | – | no_price | – | – | – | – | – |
| 51481434 | USDC | 1 | numeraire | high | – | – | – | – | – | – |
| 51481434 | FOMO | **unpriced** (stale_pool) | – | – | no_price | – | – | – | – | – |
| 51481434 | GHST | 0.0620066 | dex_slot0 | high | – | `0x41d49343…` | 388561.01 | – | 0.0620449 | -0.062 |
| 51481434 | KEK | **unpriced** (stale_pool) | – | – | no_price | – | – | – | – | – |
| 51481434 | ETH | 2587.3 | dex_slot0 | high | – | `0xd0b53d92…` | 4534928.19 | – | 2592 | -0.181 |
| 51481434 | WETH | 2587.3 | dex_slot0 | high | – | `0xd0b53d92…` | 4534928.19 | – | 2592 | -0.181 |
| 51481434 | cbBTC | 80692 | dex_slot0 | high | – | `0xfbb6eed8…` | 5599494.21 | – | 80762 | -0.087 |
| 51962756 | ALPHA | 2.01215e-05 | dex_reserves_thin | low | low_confidence | `0x0ba2a49a…` | 879.14 | 51943071 | – | – |
| 51962756 | FUD | 3.74514e-06 | dex_reserves_thin | low | low_confidence | `0xeae2fb93…` | 735.71 | 51943058 | – | – |
| 51962756 | USDC | 1 | numeraire | high | – | – | – | – | – | – |
| 51962756 | FOMO | 1.03221e-05 | dex_reserves_thin | low | low_confidence | `0x62ab7d55…` | 890.13 | 51943065 | – | – |
| 51962756 | GHST | 0.0687395 | dex_slot0 | high | – | `0x41d49343…` | 424088.87 | – | 0.0684039 | 0.491 |
| 51962756 | KEK | 4.01007e-05 | dex_reserves_thin | low | low_confidence | `0x699b4eb3…` | 687.70 | 51943079 | – | – |
| 51962756 | ETH | 2691.03 | dex_slot0 | high | – | `0xd0b53d92…` | 4638291.44 | – | 2688.78 | 0.084 |
| 51962756 | WETH | 2691.03 | dex_slot0 | high | – | `0xd0b53d92…` | 4638291.44 | – | 2688.78 | 0.084 |
| 51962756 | cbBTC | 83610.2 | dex_slot0 | high | – | `0xfbb6eed8…` | 5327577.20 | – | 83574.7 | 0.042 |
| 51965171 | ALPHA | 2.00735e-05 | dex_reserves_thin | low | low_confidence | `0x0ba2a49a…` | 877.04 | 51943071 | – | – |
| 51965171 | FUD | 3.73621e-06 | dex_reserves_thin | low | low_confidence | `0xeae2fb93…` | 733.96 | 51943058 | – | – |
| 51965171 | USDC | 1 | numeraire | high | – | – | – | – | – | – |
| 51965171 | FOMO | 1.02975e-05 | dex_reserves_thin | low | low_confidence | `0x62ab7d55…` | 888.01 | 51943065 | – | – |
| 51965171 | GHST | 0.0685755 | dex_slot0 | high | – | `0x41d49343…` | 421102.81 | – | 0.0678929 | 1.005 |
| 51965171 | KEK | 4.00051e-05 | dex_reserves_thin | low | low_confidence | `0x699b4eb3…` | 686.06 | 51943079 | – | – |
| 51965171 | ETH | 2681.47 | dex_slot0 | high | – | `0xd0b53d92…` | 4510367.80 | – | 2680.3 | 0.044 |
| 51965171 | WETH | 2681.47 | dex_slot0 | high | – | `0xd0b53d92…` | 4510367.80 | – | 2680.3 | 0.044 |
| 51965171 | cbBTC | 83538.4 | dex_slot0 | high | – | `0xfbb6eed8…` | 5295899.61 | – | 83477.8 | 0.073 |
| 52006332 | ALPHA | 1.96128e-05 | dex_reserves_thin | low | low_confidence | `0x0ba2a49a…` | 856.91 | 51943071 | – | – |
| 52006332 | FUD | 3.65046e-06 | dex_reserves_thin | low | low_confidence | `0xeae2fb93…` | 717.11 | 51943058 | – | – |
| 52006332 | USDC | 1 | numeraire | high | – | – | – | – | – | – |
| 52006332 | FOMO | 1.00611e-05 | dex_reserves_thin | low | low_confidence | `0x62ab7d55…` | 867.63 | 51943065 | – | – |
| 52006332 | GHST | 0.0670016 | dex_slot0 | high | – | `0x41d49343…` | 395623.68 | – | 0.0673702 | -0.547 |
| 52006332 | KEK | 3.90869e-05 | dex_reserves_thin | low | low_confidence | `0x699b4eb3…` | 670.31 | 51943079 | – | – |
| 52006332 | ETH | 2681.33 | dex_slot0 | high | – | `0xd0b53d92…` | 4788019.32 | – | 2679.66 | 0.062 |
| 52006332 | WETH | 2681.33 | dex_slot0 | high | – | `0xd0b53d92…` | 4788019.32 | – | 2679.66 | 0.062 |
| 52006332 | cbBTC | 83621.5 | dex_slot0 | high | – | `0xfbb6eed8…` | 5600961.92 | – | 83584.6 | 0.044 |
| 52111288 | ALPHA | 1.80625e-05 | dex_reserves_thin | low | low_confidence | `0x0ba2a49a…` | 789.18 | 51943071 | – | – |
| 52111288 | FUD | 3.36191e-06 | dex_reserves_thin | low | low_confidence | `0xeae2fb93…` | 660.43 | 51943058 | – | – |
| 52111288 | USDC | 1 | numeraire | high | – | – | – | – | – | – |
| 52111288 | FOMO | 9.26585e-06 | dex_reserves_thin | low | low_confidence | `0x62ab7d55…` | 799.05 | 51943065 | – | – |
| 52111288 | GHST | 0.0617056 | dex_slot0 | high | – | `0x41d49343…` | 424603.60 | – | 0.0619416 | -0.381 |
| 52111288 | KEK | 3.59973e-05 | dex_reserves_thin | low | low_confidence | `0x699b4eb3…` | 617.33 | 51943079 | – | – |
| 52111288 | ETH | 2680.49 | dex_slot0 | high | – | `0xd0b53d92…` | 4530266.02 | – | 2680.77 | -0.01 |
| 52111288 | WETH | 2680.49 | dex_slot0 | high | – | `0xd0b53d92…` | 4530266.02 | – | 2680.77 | -0.01 |
| 52111288 | cbBTC | 84586.5 | dex_slot0 | high | – | `0xfbb6eed8…` | 5714890.91 | – | 84588.7 | -0.003 |
