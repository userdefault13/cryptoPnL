# P3 results: Base (8453): **FAIL on criterion 1**

One P3 run at `71f904f` on `cryptopnl_p3_base` (a copy of the P2.2 Base ledger with 009 applied). It was launched by user_default at about 22:45 PDT on
2026-10-23 with `CRYPTOPNL_DSN=postgresql:///cryptopnl_p3_base nohup abra run cryptoPnL -k ENVIO_API_TOKEN -- /tmp/p22run.sh scripts/p3_test.sh 8453`.
It finished at about 23:44 PDT. Full output: `docs/evidence/p3_run_8453.log`. Request log, no secrets, RPC path redacted: `docs/evidence/p3_net_requests_8453.log`.

Final line: `P3 FAIL chain 8453 (coverage rc=0, sample rc=1, hypersync rc=0, rpc rc=0)`.

| # | Criterion (DESIGN v1.3 §4 + §8 P3 rulings) | Result |
|---|---|---|
| 1 | Every fungible asset (GLTR included) priced at 20 sampled blocks | **FAIL**: ALPHA, FUD and FOMO 12/20, KEK 19/20 (7-day swap rule, see below). **GLTR was not sampled**: the Base ledger has no GLTR entries |
| 2 | DEX within ±3% of the API (gated: GHST high/medium) | **PASS**: GHST 20/20 pairs, max abs deviation 1.005%; 0 outside ±3% (gated or report only) |
| 3 | Every ledger entry has a price or a flag | **PASS**: 1321 entries, 836 priced, 518 flagged, **0 neither**, 0 zero prices |
| – | Totals with/without low confidence | value_usdc_all **4823.44**, value_usdc_excl_low **4823.15**, 33 low-confidence entries, 0 unpriced excluded |
| – | Rate limits | HyperSync 3 requests, busiest 60 s = 3 (limit 5), min gap 12.010 s, 0 429s; RPC 1497 requests, busiest 60 s = 30 (limit 30), min gap 1.510 s, 0 429s; DefiLlama 20 requests, 0 429s |

## Ledger unchanged
`classify#1` = `classify#2`: `ledger_rows 1321, ledger_md5 58cc79730edcf6b11a1e8ee39ea3ab97, review_rows 1, review_md5 e7de420e6883071793eb2790cd85b3af`.
That is the **report md5**: `classify.checksum()` hashes tx_hash, log_index, wallet_id, asset_id, qty, category, trade_group, location,
escrow_ref and pnl_excluded. It equals the P2.2 report md5 in `docs/P2_2_RESULTS.md` (§ baseline). The **baseline md5** uses the narrower
classify-only query (tx_hash, log_index, asset_id, qty, category, location, escrow_ref). Recomputed read-only on `cryptopnl_p3_base` after classify,
it gives **210a71d811fd872a970b1d11770ced05** over 1321 rows, the P2.2 baseline. There is no difference: these are two definitions of the same ledger.
The tx-index step fetched 2 tx positions over RPC (2 candidates) and did not reorder the ledger.

## Criterion 1: 20 sampled blocks (`docs/evidence/p3_sample_8453.jsonl`)
Sample seed 3, start block 48775083, blocks [48778781, 48968245, 49319375, 49408055, 49605307, 49705890, 50336888, 51029666, 51093930, 51096573, 51096720, 51157926, 51157981, 51200957, 51283821, 51481434, 51962756, 51965171, 52006332, 52111288].

| asset | gated | priced | source | confidence | pool | price range (USDC) | pool USD depth |
|---|---|---|---|---|---|---|---|
| ALPHA | yes | **12/20** | dex_reserves_thin | low | `0x0ba2a49aedf9a409dbb0272db7cdf98aeb1e1837` | 1.21282e-05 – 2.01215e-05 | 539.41 – 879.14 |
| FUD | yes | **12/20** | dex_reserves_thin | low | `0xeae2fb93e291c2eb69195851813de24f97f1ce71` | 2.32531e-06 – 3.74514e-06 | 458.65 – 735.71 |
| USDC | yes | **20/20** | numeraire | high | – (numeraire) | 1 – 1 | – |
| FOMO | yes | **12/20** | dex_reserves_thin | low | `0x62ab7d558a011237f8a57ac0f97601a764e85b88` | 6.88377e-06 – 1.03221e-05 | 575.22 – 890.13 |
| GHST | yes | **20/20** | dex_slot0 | high | `0x41d4934322f2bd6fe1dbe4124070fe61651a2067` | 0.043399 – 0.0687395 | 286525.53 – 424603.60 |
| KEK | yes | **19/20** | dex_reserves_thin | low | `0x699b4eb36b95cdf62c74f6322aaa140e7958dc9f` | 2.5503e-05 – 4.01007e-05 | 433.69 – 687.70 |
| ETH | yes | **20/20** | dex_slot0 | high | `0xd0b53d9277642d899df5c87a3966a349a798f224` | 1842.02 – 2691.03 | 2491560.85 – 4788019.32 |
| WETH | report only | **20/20** | dex_slot0 | high | `0xd0b53d9277642d899df5c87a3966a349a798f224` | 1842.02 – 2691.03 | 2491560.85 – 4788019.32 |
| cbBTC | report only | **20/20** | dex_slot0 | high | `0xfbb6eed8e7aa03b138556eedaf5d271a5e1e43ef` | 62783.8 – 84586.5 | 2655028.31 – 5714890.91 |

**Why ALPHA, FUD, FOMO and KEK miss blocks (the ruling working as specified, not a bug):** the thin tier needs a Swap within 302,400 blocks
(7 days). The HyperSync scan (`docs/evidence/p3_pool_swaps_8453.log`: 5 pools, blocks 33,200,000–53,015,551, 2,411 swaps seen, 2,403 inserted)
shows a no-swap gap of about 24 days in all four alchemica pools. Read-only query on `pool_swap` (gaps > 302,400 blocks):
- ALPHA `0x0ba2a49a…`: no swap between 50,761,766 and 51,806,369 (1,044,603 blocks, about 24.2 d).
- FOMO `0x62ab7d55…`: none between 50,755,966 and 51,812,309 (about 24.5 d).
- FUD `0xeae2fb93…`: none between 50,755,692 and 51,812,302 (about 24.5 d).
- KEK `0x699b4eb3…`: none between 51,031,687 and 51,812,323 (about 18.1 d).

The unpriced samples are exactly the sample blocks more than 302,400 blocks past the last swap: blocks 51,093,930 to 51,481,434 for ALPHA, FUD and FOMO
(8 each), and 51,481,434 only for KEK. No alchemica DEX pool is at or above the $1,000 floor (all thin; depth 433–890 USD) and DefiLlama has no alchemica
price, so under the rulings these (asset, block) pairs are unpriced and are never valued at 0.

**GLTR:** the sample covers tracked fungibles that have ledger activity, plus WETH and cbBTC as report-only extras. `cryptopnl_p3_base` has **0** ledger entries
for GLTR `0x4d140ce7…` (read-only check), so GLTR was not sampled and criterion 1 has **no GLTR evidence** from this run. The GLTR pool scan did run:
`0xa83b31d7…` had 261 swaps. Its swap history also has gaps over 7 days (for example 51,504,241 → 52,378,956, about 20.2 d), so GLTR would be unpriced at
some blocks under the same rule.

## Criterion 2: GHST DEX vs API (gated)
GHST: 20/20 samples priced via `dex_slot0` (Uniswap v3 GHST/USDC `0x41d4934322f2bd6fe1dbe4124070fe61651a2067`, high, depth
286525.53–424603.60 USD). DefiLlama pairs: 20, deviations
-0.655% to 1.005%, max abs 1.005%. Report-only: ETH/WETH max abs 0.181% and cbBTC 0.087% (20 pairs each).
`outside_3pct_gated = []`, `outside_3pct_report_only = []`.

## Criterion 3: ledger coverage (`docs/evidence/p3_coverage_8453.json`)
1321 entries: priced 836 (trade 40, numeraire 45, dex_slot0 670, dex_reserves 50, dex_reserves_thin 31), flagged 518 (spam 340, untracked 56,
pending_basis 81, nft_no_trade 8, low_confidence 33; the 33 low-confidence entries are both priced and flagged), neither **0**,
zero prices **0**. Labels: high 744, medium 59, low 33. The ledger price step made 1,214 RPC requests (all 200, 29.53/min).

## Totals (USDC, |qty| × price, PnL-relevant entries)
value_usdc_all **4823.44**, value_usdc_excl_low **4823.15** (33 low-confidence entries; 0 unpriced entries excluded). By asset (all / excl. low):
ETH 2995.36/2995.36, GHST 947.37/947.11, USDC 860.38/860.38, FOMO 4.31/4.31, FUD 4.31/4.31, ALPHA 3.27/3.27, KEK 3.00/3.00 (plus
untagged tokens ≤ 4.50). The low-confidence alchemica entries are small incomes. For example, ALPHA has 6 thin-priced income entries worth $0.004071
together, so its rounded totals match; the ALPHA value is mostly 3 trade-priced swaps ($3.268380).

## Rate limits (`docs/evidence/p3_hypersync_8453.txt`, `p3_rpc_8453.txt`, `p3_defillama_8453.txt`)
- HyperSync: requests=3, status_200=3, 429s=0, busiest_60s_window=3 (ending 22:45:01 PDT), limit=5 → OK, min_gap_s=12.010.
- RPC (base.drpc.org): requests=1497, status_200=1497, 429s=0, busiest_60s_window=30 (ending 22:45:49 PDT), limit=30 → OK, min_gap_s=1.510.
- DefiLlama: requests=20, status_200=20, 429s=0.

## Not verified
- GLTR pricing on real data: the ledger has no GLTR, and the sample doesn't include assets without ledger activity. The thin-tier path is covered by unit tests only.
- Sepolia: not run (Base only).
- Prices are not checked against any source except DefiLlama for GHST/ETH/WETH/cbBTC.

## Open questions (architect/CoS)
1. **7-day swap rule vs criterion 1.** All four alchemica pools had a roughly 24-day no-swap gap (blocks about 50.76M–51.81M), so a 20-block sample cannot
   reach 20/20 under the rule as written. Options: (a) accept "unpriced (stale pool)" as a valid outcome for criterion 1 (a flag, not a miss);
   (b) widen the window; (c) price from the last swap within N days at low confidence. This needs a ruling. I changed nothing.
2. **GLTR in the sample.** Should criterion 1 sample GLTR even with no ledger activity (for example, sample every tracked fungible)? That would
   produce GLTR evidence, though some blocks would be unpriced (see the 20.2 d gap).
3. Stale text: the `sample()` docstring still says "GLTR is documented as unpriced"; the code gates GLTR when it has a source. Docstring fix pending.

## Appendix: every sample (block, asset, price, source, confidence, pool, depth)
| block | asset | price (USDC) | source | conf. | pool | pool depth USD | last swap block | API | dev % |
|---|---|---|---|---|---|---|---|---|---|
| 48778781 | ALPHA | 1.41147e-05 | dex_reserves_thin | low | `0x0ba2a49a…` | 623.87 | 48681867 | – | – |
| 48778781 | FUD | 2.68919e-06 | dex_reserves_thin | low | `0xeae2fb93…` | 527.76 | 48681851 | – | – |
| 48778781 | USDC | 1 | numeraire | high | – | – | – | – | – |
| 48778781 | FOMO | 8.08022e-06 | dex_reserves_thin | low | `0x62ab7d55…` | 667.28 | 48681859 | – | – |
| 48778781 | GHST | 0.0491835 | dex_slot0 | high | `0x41d49343…` | 305783.43 | – | 0.0493924 | -0.423 |
| 48778781 | KEK | 2.97441e-05 | dex_reserves_thin | low | `0x699b4eb3…` | 501.92 | 48681875 | – | – |
| 48778781 | ETH | 1842.02 | dex_slot0 | high | `0xd0b53d92…` | 2579095.05 | – | 1841.92 | 0.005 |
| 48778781 | WETH | 1842.02 | dex_slot0 | high | `0xd0b53d92…` | 2579095.05 | – | 1841.92 | 0.005 |
| 48778781 | cbBTC | 63922.4 | dex_slot0 | high | `0xfbb6eed8…` | 3480134.52 | – | 63917.6 | 0.007 |
| 48968245 | ALPHA | 1.34073e-05 | dex_reserves_thin | low | `0x0ba2a49a…` | 594.73 | 48876605 | – | – |
| 48968245 | FUD | 2.54835e-06 | dex_reserves_thin | low | `0xeae2fb93…` | 502.51 | 48876593 | – | – |
| 48968245 | USDC | 1 | numeraire | high | – | – | – | – | – |
| 48968245 | FOMO | 7.6338e-06 | dex_reserves_thin | low | `0x62ab7d55…` | 634.39 | 48876599 | – | – |
| 48968245 | GHST | 0.0470541 | dex_slot0 | high | `0x41d49343…` | 298102.15 | – | 0.0473643 | -0.655 |
| 48968245 | KEK | 2.81324e-05 | dex_reserves_thin | low | `0x699b4eb3…` | 477.45 | 48876612 | – | – |
| 48968245 | ETH | 1919.24 | dex_slot0 | high | `0xd0b53d92…` | 3399086.70 | – | 1918.15 | 0.057 |
| 48968245 | WETH | 1919.24 | dex_slot0 | high | `0xd0b53d92…` | 3399086.70 | – | 1918.15 | 0.057 |
| 48968245 | cbBTC | 65612.2 | dex_slot0 | high | `0xfbb6eed8…` | 3368148.38 | – | 65565.3 | 0.072 |
| 49319375 | ALPHA | 1.23418e-05 | dex_reserves_thin | low | `0x0ba2a49a…` | 552.42 | 49276974 | – | – |
| 49319375 | FUD | 2.433e-06 | dex_reserves_thin | low | `0xeae2fb93…` | 476.29 | 49319375 | – | – |
| 49319375 | USDC | 1 | numeraire | high | – | – | – | – | – |
| 49319375 | FOMO | 7.22068e-06 | dex_reserves_thin | low | `0x62ab7d55…` | 597.81 | 49319360 | – | – |
| 49319375 | GHST | 0.0447301 | dex_slot0 | high | `0x41d49343…` | 292181.62 | – | 0.0445315 | 0.446 |
| 49319375 | KEK | 2.60368e-05 | dex_reserves_thin | low | `0x699b4eb3…` | 444.87 | 49277004 | – | – |
| 49319375 | ETH | 1922.36 | dex_slot0 | high | `0xd0b53d92…` | 3237341.16 | – | 1921.7 | 0.034 |
| 49319375 | WETH | 1922.36 | dex_slot0 | high | `0xd0b53d92…` | 3237341.16 | – | 1921.7 | 0.034 |
| 49319375 | cbBTC | 64875.5 | dex_slot0 | high | `0xfbb6eed8…` | 3863713.89 | – | 64836.3 | 0.06 |
| 49408055 | ALPHA | 1.24001e-05 | dex_reserves_thin | low | `0x0ba2a49a…` | 551.50 | 49329735 | – | – |
| 49408055 | FUD | 2.37743e-06 | dex_reserves_thin | low | `0xeae2fb93…` | 468.93 | 49329715 | – | – |
| 49408055 | USDC | 1 | numeraire | high | – | – | – | – | – |
| 49408055 | FOMO | 7.0449e-06 | dex_reserves_thin | low | `0x62ab7d55…` | 588.12 | 49329726 | – | – |
| 49408055 | GHST | 0.0443718 | dex_slot0 | high | `0x41d49343…` | 291054.86 | – | 0.0440681 | 0.689 |
| 49408055 | KEK | 2.60746e-05 | dex_reserves_thin | low | `0x699b4eb3…` | 443.41 | 49329743 | – | – |
| 49408055 | ETH | 1861.76 | dex_slot0 | high | `0xd0b53d92…` | 2491560.85 | – | 1862.32 | -0.03 |
| 49408055 | WETH | 1861.76 | dex_slot0 | high | `0xd0b53d92…` | 2491560.85 | – | 1862.32 | -0.03 |
| 49408055 | cbBTC | 62783.8 | dex_slot0 | high | `0xfbb6eed8…` | 2655028.31 | – | 62774.7 | 0.014 |
| 49605307 | ALPHA | 1.21282e-05 | dex_reserves_thin | low | `0x0ba2a49a…` | 539.41 | 49329735 | – | – |
| 49605307 | FUD | 2.32531e-06 | dex_reserves_thin | low | `0xeae2fb93…` | 458.65 | 49329715 | – | – |
| 49605307 | USDC | 1 | numeraire | high | – | – | – | – | – |
| 49605307 | FOMO | 6.89045e-06 | dex_reserves_thin | low | `0x62ab7d55…` | 575.22 | 49329726 | – | – |
| 49605307 | GHST | 0.043399 | dex_slot0 | high | `0x41d49343…` | 286525.53 | – | 0.0433742 | 0.057 |
| 49605307 | KEK | 2.5503e-05 | dex_reserves_thin | low | `0x699b4eb3…` | 433.69 | 49329743 | – | – |
| 49605307 | ETH | 1911.14 | dex_slot0 | high | `0xd0b53d92…` | 3059559.05 | – | 1910.82 | 0.017 |
| 49605307 | WETH | 1911.14 | dex_slot0 | high | `0xd0b53d92…` | 3059559.05 | – | 1910.82 | 0.017 |
| 49605307 | cbBTC | 64777.7 | dex_slot0 | high | `0xfbb6eed8…` | 3984575.80 | – | 64755.3 | 0.035 |
| 49705890 | ALPHA | 1.22691e-05 | dex_reserves_thin | low | `0x0ba2a49a…` | 547.85 | 49657271 | – | – |
| 49705890 | FUD | 2.35222e-06 | dex_reserves_thin | low | `0xeae2fb93…` | 465.81 | 49657195 | – | – |
| 49705890 | USDC | 1 | numeraire | high | – | – | – | – | – |
| 49705890 | FOMO | 6.97854e-06 | dex_reserves_thin | low | `0x62ab7d55…` | 584.56 | 49657241 | – | – |
| 49705890 | GHST | 0.0442533 | dex_slot0 | high | `0x41d49343…` | 289699.25 | – | 0.0443037 | -0.114 |
| 49705890 | KEK | 2.57565e-05 | dex_reserves_thin | low | `0x699b4eb3…` | 440.10 | 49657297 | – | – |
| 49705890 | ETH | 1922.73 | dex_slot0 | high | `0xd0b53d92…` | 3170748.63 | – | 1922.93 | -0.01 |
| 49705890 | WETH | 1922.73 | dex_slot0 | high | `0xd0b53d92…` | 3170748.63 | – | 1922.93 | -0.01 |
| 49705890 | cbBTC | 65109 | dex_slot0 | high | `0xfbb6eed8…` | 4376868.24 | – | 65108.9 | 0.0 |
| 50336888 | ALPHA | 1.25616e-05 | dex_reserves_thin | low | `0x0ba2a49a…` | 566.62 | 50287973 | – | – |
| 50336888 | FUD | 2.37142e-06 | dex_reserves_thin | low | `0xeae2fb93…` | 478.07 | 50287959 | – | – |
| 50336888 | USDC | 1 | numeraire | high | – | – | – | – | – |
| 50336888 | FOMO | 6.88377e-06 | dex_reserves_thin | low | `0x62ab7d55…` | 593.43 | 50287967 | – | – |
| 50336888 | GHST | 0.0462352 | dex_slot0 | high | `0x41d49343…` | 294537.96 | – | 0.0462444 | -0.02 |
| 50336888 | KEK | 2.5595e-05 | dex_reserves_thin | low | `0x699b4eb3…` | 448.44 | 50287980 | – | – |
| 50336888 | ETH | 2380.71 | dex_slot0 | high | `0xd0b53d92…` | 2791532.14 | – | 2381.57 | -0.036 |
| 50336888 | WETH | 2380.71 | dex_slot0 | high | `0xd0b53d92…` | 2791532.14 | – | 2381.57 | -0.036 |
| 50336888 | cbBTC | 76228.4 | dex_slot0 | high | `0xfbb6eed8…` | 5430223.23 | – | 76241.7 | -0.017 |
| 51029666 | ALPHA | 1.82454e-05 | dex_reserves_thin | low | `0x0ba2a49a…` | 787.30 | 50761766 | – | – |
| 51029666 | FUD | 3.43339e-06 | dex_reserves_thin | low | `0xeae2fb93…` | 663.20 | 50755692 | – | – |
| 51029666 | USDC | 1 | numeraire | high | – | – | – | – | – |
| 51029666 | FOMO | 9.73315e-06 | dex_reserves_thin | low | `0x62ab7d55…` | 813.54 | 50755966 | – | – |
| 51029666 | GHST | 0.0614559 | dex_slot0 | high | `0x41d49343…` | 341451.06 | – | 0.0611278 | 0.537 |
| 51029666 | KEK | 3.75572e-05 | dex_reserves_thin | low | `0x699b4eb3…` | 627.80 | 50844837 | – | – |
| 51029666 | ETH | 2467.71 | dex_slot0 | high | `0xd0b53d92…` | 3429736.07 | – | 2467.15 | 0.023 |
| 51029666 | WETH | 2467.71 | dex_slot0 | high | `0xd0b53d92…` | 3429736.07 | – | 2467.15 | 0.023 |
| 51029666 | cbBTC | 78418.8 | dex_slot0 | high | `0xfbb6eed8…` | 4148712.63 | – | 78425.2 | -0.008 |
| 51093930 | ALPHA | **unpriced** | – | – | – | – | – | – | – |
| 51093930 | FUD | **unpriced** | – | – | – | – | – | – | – |
| 51093930 | USDC | 1 | numeraire | high | – | – | – | – | – |
| 51093930 | FOMO | **unpriced** | – | – | – | – | – | – | – |
| 51093930 | GHST | 0.0601701 | dex_slot0 | high | `0x41d49343…` | 337879.86 | – | 0.0602594 | -0.148 |
| 51093930 | KEK | 3.69451e-05 | dex_reserves_thin | low | `0x699b4eb3…` | 617.57 | 51031687 | – | – |
| 51093930 | ETH | 2494.06 | dex_slot0 | high | `0xd0b53d92…` | 3770808.90 | – | 2495.37 | -0.052 |
| 51093930 | WETH | 2494.06 | dex_slot0 | high | `0xd0b53d92…` | 3770808.90 | – | 2495.37 | -0.052 |
| 51093930 | cbBTC | 78741.4 | dex_slot0 | high | `0xfbb6eed8…` | 4686051.48 | – | 78726.8 | 0.019 |
| 51096573 | ALPHA | **unpriced** | – | – | – | – | – | – | – |
| 51096573 | FUD | **unpriced** | – | – | – | – | – | – | – |
| 51096573 | USDC | 1 | numeraire | high | – | – | – | – | – |
| 51096573 | FOMO | **unpriced** | – | – | – | – | – | – | – |
| 51096573 | GHST | 0.0601701 | dex_slot0 | high | `0x41d49343…` | 337879.86 | – | 0.0602634 | -0.155 |
| 51096573 | KEK | 3.69451e-05 | dex_reserves_thin | low | `0x699b4eb3…` | 617.57 | 51031687 | – | – |
| 51096573 | ETH | 2480.8 | dex_slot0 | high | `0xd0b53d92…` | 3556919.48 | – | 2481.84 | -0.042 |
| 51096573 | WETH | 2480.8 | dex_slot0 | high | `0xd0b53d92…` | 3556919.48 | – | 2481.84 | -0.042 |
| 51096573 | cbBTC | 78528 | dex_slot0 | high | `0xfbb6eed8…` | 4593040.84 | – | 78505.3 | 0.029 |
| 51096720 | ALPHA | **unpriced** | – | – | – | – | – | – | – |
| 51096720 | FUD | **unpriced** | – | – | – | – | – | – | – |
| 51096720 | USDC | 1 | numeraire | high | – | – | – | – | – |
| 51096720 | FOMO | **unpriced** | – | – | – | – | – | – | – |
| 51096720 | GHST | 0.0601701 | dex_slot0 | high | `0x41d49343…` | 337879.86 | – | 0.0601951 | -0.041 |
| 51096720 | KEK | 3.69451e-05 | dex_reserves_thin | low | `0x699b4eb3…` | 617.57 | 51031687 | – | – |
| 51096720 | ETH | 2474.76 | dex_slot0 | high | `0xd0b53d92…` | 3463277.39 | – | 2474.72 | 0.002 |
| 51096720 | WETH | 2474.76 | dex_slot0 | high | `0xd0b53d92…` | 3463277.39 | – | 2474.72 | 0.002 |
| 51096720 | cbBTC | 78390.3 | dex_slot0 | high | `0xfbb6eed8…` | 4535606.78 | – | 78379.9 | 0.013 |
| 51157926 | ALPHA | **unpriced** | – | – | – | – | – | – | – |
| 51157926 | FUD | **unpriced** | – | – | – | – | – | – | – |
| 51157926 | USDC | 1 | numeraire | high | – | – | – | – | – |
| 51157926 | FOMO | **unpriced** | – | – | – | – | – | – | – |
| 51157926 | GHST | 0.0634994 | dex_slot0 | high | `0x41d49343…` | 353749.95 | – | 0.0629506 | 0.872 |
| 51157926 | KEK | 3.89894e-05 | dex_reserves_thin | low | `0x699b4eb3…` | 651.74 | 51031687 | – | – |
| 51157926 | ETH | 2461.86 | dex_slot0 | high | `0xd0b53d92…` | 3461955.72 | – | 2460.01 | 0.075 |
| 51157926 | WETH | 2461.86 | dex_slot0 | high | `0xd0b53d92…` | 3461955.72 | – | 2460.01 | 0.075 |
| 51157926 | cbBTC | 77131.1 | dex_slot0 | high | `0xfbb6eed8…` | 4040539.69 | – | 77125.2 | 0.008 |
| 51157981 | ALPHA | **unpriced** | – | – | – | – | – | – | – |
| 51157981 | FUD | **unpriced** | – | – | – | – | – | – | – |
| 51157981 | USDC | 1 | numeraire | high | – | – | – | – | – |
| 51157981 | FOMO | **unpriced** | – | – | – | – | – | – | – |
| 51157981 | GHST | 0.0634994 | dex_slot0 | high | `0x41d49343…` | 353749.95 | – | 0.0629506 | 0.872 |
| 51157981 | KEK | 3.89894e-05 | dex_reserves_thin | low | `0x699b4eb3…` | 651.74 | 51031687 | – | – |
| 51157981 | ETH | 2461.88 | dex_slot0 | high | `0xd0b53d92…` | 3462102.48 | – | 2459.53 | 0.095 |
| 51157981 | WETH | 2461.88 | dex_slot0 | high | `0xd0b53d92…` | 3462102.48 | – | 2459.53 | 0.095 |
| 51157981 | cbBTC | 77131.1 | dex_slot0 | high | `0xfbb6eed8…` | 4040539.69 | – | 77127.6 | 0.005 |
| 51200957 | ALPHA | **unpriced** | – | – | – | – | – | – | – |
| 51200957 | FUD | **unpriced** | – | – | – | – | – | – | – |
| 51200957 | USDC | 1 | numeraire | high | – | – | – | – | – |
| 51200957 | FOMO | **unpriced** | – | – | – | – | – | – | – |
| 51200957 | GHST | 0.0648552 | dex_slot0 | high | `0x41d49343…` | 368728.09 | – | 0.0648204 | 0.054 |
| 51200957 | KEK | 3.98218e-05 | dex_reserves_thin | low | `0x699b4eb3…` | 665.66 | 51031687 | – | – |
| 51200957 | ETH | 2510.39 | dex_slot0 | high | `0xd0b53d92…` | 3803233.92 | – | 2513.27 | -0.114 |
| 51200957 | WETH | 2510.39 | dex_slot0 | high | `0xd0b53d92…` | 3803233.92 | – | 2513.27 | -0.114 |
| 51200957 | cbBTC | 77216 | dex_slot0 | high | `0xfbb6eed8…` | 3960495.56 | – | 77209.9 | 0.008 |
| 51283821 | ALPHA | **unpriced** | – | – | – | – | – | – | – |
| 51283821 | FUD | **unpriced** | – | – | – | – | – | – | – |
| 51283821 | USDC | 1 | numeraire | high | – | – | – | – | – |
| 51283821 | FOMO | **unpriced** | – | – | – | – | – | – | – |
| 51283821 | GHST | 0.0643954 | dex_slot0 | high | `0x41d49343…` | 366002.33 | – | 0.0640949 | 0.469 |
| 51283821 | KEK | 3.95395e-05 | dex_reserves_thin | low | `0x699b4eb3…` | 660.94 | 51031687 | – | – |
| 51283821 | ETH | 2512.61 | dex_slot0 | high | `0xd0b53d92…` | 3845199.27 | – | 2513.03 | -0.016 |
| 51283821 | WETH | 2512.61 | dex_slot0 | high | `0xd0b53d92…` | 3845199.27 | – | 2513.03 | -0.016 |
| 51283821 | cbBTC | 77651.8 | dex_slot0 | high | `0xfbb6eed8…` | 4178745.99 | – | 77644.4 | 0.009 |
| 51481434 | ALPHA | **unpriced** | – | – | – | – | – | – | – |
| 51481434 | FUD | **unpriced** | – | – | – | – | – | – | – |
| 51481434 | USDC | 1 | numeraire | high | – | – | – | – | – |
| 51481434 | FOMO | **unpriced** | – | – | – | – | – | – | – |
| 51481434 | GHST | 0.0620066 | dex_slot0 | high | `0x41d49343…` | 388561.01 | – | 0.0620449 | -0.062 |
| 51481434 | KEK | **unpriced** | – | – | – | – | – | – | – |
| 51481434 | ETH | 2587.3 | dex_slot0 | high | `0xd0b53d92…` | 4534928.19 | – | 2592 | -0.181 |
| 51481434 | WETH | 2587.3 | dex_slot0 | high | `0xd0b53d92…` | 4534928.19 | – | 2592 | -0.181 |
| 51481434 | cbBTC | 80692 | dex_slot0 | high | `0xfbb6eed8…` | 5599494.21 | – | 80762 | -0.087 |
| 51962756 | ALPHA | 2.01215e-05 | dex_reserves_thin | low | `0x0ba2a49a…` | 879.14 | 51943071 | – | – |
| 51962756 | FUD | 3.74514e-06 | dex_reserves_thin | low | `0xeae2fb93…` | 735.71 | 51943058 | – | – |
| 51962756 | USDC | 1 | numeraire | high | – | – | – | – | – |
| 51962756 | FOMO | 1.03221e-05 | dex_reserves_thin | low | `0x62ab7d55…` | 890.13 | 51943065 | – | – |
| 51962756 | GHST | 0.0687395 | dex_slot0 | high | `0x41d49343…` | 424088.87 | – | 0.0684039 | 0.491 |
| 51962756 | KEK | 4.01007e-05 | dex_reserves_thin | low | `0x699b4eb3…` | 687.70 | 51943079 | – | – |
| 51962756 | ETH | 2691.03 | dex_slot0 | high | `0xd0b53d92…` | 4638291.44 | – | 2688.78 | 0.084 |
| 51962756 | WETH | 2691.03 | dex_slot0 | high | `0xd0b53d92…` | 4638291.44 | – | 2688.78 | 0.084 |
| 51962756 | cbBTC | 83610.2 | dex_slot0 | high | `0xfbb6eed8…` | 5327577.20 | – | 83574.7 | 0.042 |
| 51965171 | ALPHA | 2.00735e-05 | dex_reserves_thin | low | `0x0ba2a49a…` | 877.04 | 51943071 | – | – |
| 51965171 | FUD | 3.73621e-06 | dex_reserves_thin | low | `0xeae2fb93…` | 733.96 | 51943058 | – | – |
| 51965171 | USDC | 1 | numeraire | high | – | – | – | – | – |
| 51965171 | FOMO | 1.02975e-05 | dex_reserves_thin | low | `0x62ab7d55…` | 888.01 | 51943065 | – | – |
| 51965171 | GHST | 0.0685755 | dex_slot0 | high | `0x41d49343…` | 421102.81 | – | 0.0678929 | 1.005 |
| 51965171 | KEK | 4.00051e-05 | dex_reserves_thin | low | `0x699b4eb3…` | 686.06 | 51943079 | – | – |
| 51965171 | ETH | 2681.47 | dex_slot0 | high | `0xd0b53d92…` | 4510367.80 | – | 2680.3 | 0.044 |
| 51965171 | WETH | 2681.47 | dex_slot0 | high | `0xd0b53d92…` | 4510367.80 | – | 2680.3 | 0.044 |
| 51965171 | cbBTC | 83538.4 | dex_slot0 | high | `0xfbb6eed8…` | 5295899.61 | – | 83477.8 | 0.073 |
| 52006332 | ALPHA | 1.96128e-05 | dex_reserves_thin | low | `0x0ba2a49a…` | 856.91 | 51943071 | – | – |
| 52006332 | FUD | 3.65046e-06 | dex_reserves_thin | low | `0xeae2fb93…` | 717.11 | 51943058 | – | – |
| 52006332 | USDC | 1 | numeraire | high | – | – | – | – | – |
| 52006332 | FOMO | 1.00611e-05 | dex_reserves_thin | low | `0x62ab7d55…` | 867.63 | 51943065 | – | – |
| 52006332 | GHST | 0.0670016 | dex_slot0 | high | `0x41d49343…` | 395623.68 | – | 0.0673702 | -0.547 |
| 52006332 | KEK | 3.90869e-05 | dex_reserves_thin | low | `0x699b4eb3…` | 670.31 | 51943079 | – | – |
| 52006332 | ETH | 2681.33 | dex_slot0 | high | `0xd0b53d92…` | 4788019.32 | – | 2679.66 | 0.062 |
| 52006332 | WETH | 2681.33 | dex_slot0 | high | `0xd0b53d92…` | 4788019.32 | – | 2679.66 | 0.062 |
| 52006332 | cbBTC | 83621.5 | dex_slot0 | high | `0xfbb6eed8…` | 5600961.92 | – | 83584.6 | 0.044 |
| 52111288 | ALPHA | 1.80625e-05 | dex_reserves_thin | low | `0x0ba2a49a…` | 789.18 | 51943071 | – | – |
| 52111288 | FUD | 3.36191e-06 | dex_reserves_thin | low | `0xeae2fb93…` | 660.43 | 51943058 | – | – |
| 52111288 | USDC | 1 | numeraire | high | – | – | – | – | – |
| 52111288 | FOMO | 9.26585e-06 | dex_reserves_thin | low | `0x62ab7d55…` | 799.05 | 51943065 | – | – |
| 52111288 | GHST | 0.0617056 | dex_slot0 | high | `0x41d49343…` | 424603.60 | – | 0.0619416 | -0.381 |
| 52111288 | KEK | 3.59973e-05 | dex_reserves_thin | low | `0x699b4eb3…` | 617.33 | 51943079 | – | – |
| 52111288 | ETH | 2680.49 | dex_slot0 | high | `0xd0b53d92…` | 4530266.02 | – | 2680.77 | -0.01 |
| 52111288 | WETH | 2680.49 | dex_slot0 | high | `0xd0b53d92…` | 4530266.02 | – | 2680.77 | -0.01 |
| 52111288 | cbBTC | 84586.5 | dex_slot0 | high | `0xfbb6eed8…` | 5714890.91 | – | 84588.7 | -0.003 |
