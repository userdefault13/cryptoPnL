# P4 results: FIFO engine, rulings 2026-10-28 (+ rulings 2, rulings 3), real Base ledger copy

**Verdict: the engine is proven; real-ledger acceptance is deferred to P4.1.** `scripts/p4_test.sh` ends **P4 FLAGGED** (exit 3) on chain 8453:
- rebuild == incremental;
- the reconciliation holds per asset (realized and unrealized separately) and in total at 0.01 USDC, against a ledger side rebuilt independently from ledger_entry rows alone;
- engine open qty == the ledger side's own running balance;
- the snapshots are byte-identical;
- **but** the ledger's own running balance has **UNEXPLAINED GAPS**: ETH and GHST leave balances the ledger never recorded arriving. They are reported and flagged, never passed (P4 rulings 3).

Run: omarchywin, worktree `~/dev/cryptoPnL-p4` at 75452b9:
`PY=~/dev/cryptoPnL-p3/.venv/bin/python scripts/with_ledger_pg.sh scripts/p4_test.sh 8453 cryptopnl_p3_base cryptopnl_p4_base`
- 10 s, offline: no HyperSync, no RPC; marks come from stored P3 prices. Log: `docs/evidence/p4_test_8453.log`.
- Writes went only to `cryptopnl_p4_base` (`createdb -T cryptopnl_p3_base`). Envio PG 5439/5440 were not touched.
- The ledger PG password came from the compose .env fallback. abra was locked, and `cryptoPnL/CRYPTOPNL_LEDGER_PG_PASSWORD` is not known to exist (see §10).

## 1. Ledger md5, read-only
`docs/evidence/p4_ledger_md5_8453.txt`:
- `ledger_rows=1321`, blocks 4328142–52911467.
- `ledger_md5_narrow=210a71d811fd872a970b1d11770ced05` (unchanged).
- `ledger_md5_report=58cc79730edcf6b11a1e8ee39ea3ab97`.

The copy after migrating is identical (`p4_ledger_md5_8453_copy.txt`).

## 2. Migrations 013 + 014
- **Applied** on the copy: `{"applied": ["013_p4_fifo.sql", "014_p4_rulings3.sql"]}`.
- **014** adds `fifo_lot.basis_origin` (CHECK `unrecorded_inflow`). It also sets `lot_disposal_pnl.realized_usdc` to NULL for exits and adds `realized_display_usdc`, which is 0 for an exit with known cost (display only).
- **Local up/down/up** (MBP PG 16, `docs/evidence/p4_migration_014_local.txt`):
  - up == up2 (489 lines, md5 550706dc9f63d80a7284b5402634e280);
  - 014 down == 001..013 (483 lines);
  - 013 down == 001..012 (353 lines);
  - 7 constraint and view tests OK.

## 3. Rebuild vs incremental
| | rebuild | incremental (split at 40422429: 661 + 660 rows, state reloaded from the DB) |
|---|---|---|
| engine md5 | 1a0367245a6c6a5915727746fc542699 | 1a0367245a6c6a5915727746fc542699 |
| fifo_lot table md5 | 46ad52a42db6cc6161e917cb57b19076 | 46ad52a42db6cc6161e917cb57b19076 |
| lot_disposal table md5 | b9c2d064d8b791653a9bad39c8d98031 | b9c2d064d8b791653a9bad39c8d98031 |
| lots / disposals | 755 / 680 | 755 / 680 |

- The head state's md5 is unchanged by the DB round trip: 1474eaf68efc4df5717af77df2749953.
- The engine and fifo_lot md5s changed from b2089fc because `basis_origin` was added. lot_disposal is unchanged.
- Row order: (block, log_index, id). `tx_index_null_rows` = 1319 of 1321, all in single-tx blocks, which passes the check.

## 4. as_of_block = 49402932 (rulings 3: MIN over tracked assets of each one's latest stored price)
- **Set by** KEK (28), FUD (39), FOMO (96) and ALPHA (97), whose last stored P3 price is at 49402932.
- **Latest stored price for the others:** GHST (19) 51283821, USDC (20) 51481437, ETH (2) 52911410.
- **State at as_of:** the snapshot and reconcile replay the 1159 rows with block ≤ 49402932 offline. 162 rows come after as_of.

## 5. Reconciliation (`p4_reconcile_8453.json`), tolerance 0.01 USDC, exact Decimal; the ledger side reads ledger rows only
- **Total:** engine R + U − gas_expense(resolved) = −3.92024127016582325294… USDC = the ledger side; **residual 0**.
- **Per asset** (93 assets): max |realized residual| 1e-50, max |unrealized residual| 1e-51. The ledger side's own formula S + MV + X + C + M − A equals its R + U to within 1.1e-47.
- **Engine R + U per asset**, for the 7 assets with a nonzero value; all match the ledger side:

  | asset | R + U | realized | unrealized |
  |---|---|---|---|
  | GHST (19) | −3.5898471177 | −3.5305177175 | −0.0593294001 |
  | USDC (20) | −0.0518723687 | −0.0518723687 | 0 |
  | FOMO (96) | −0.0753941224 | −0.0083195695 | −0.0670745528 |
  | FUD (39) | −0.0582447962 | −0.0078488812 | −0.0503959150 |
  | KEK (28) | −0.0578311779 | 0 | −0.0578311779 |
  | ALPHA (97) | −0.0498472569 | 0 | −0.0498472569 |

  - GHST terms: S 6.0570, MV 5.0188, X 149.2975, A 163.9632.
- **Quantity:** engine open qty == the ledger side's running balance for every asset (0 mismatches).
- **UNEXPLAINED GAP** (the ledger side's balance went short; flagged, not passed):
  - **ETH (2):** 1.095603323941304014 ETH over 455 out-legs, blocks 12795076–49402932 (fee 406, withdrawal 36, swap 10, nft_buy 3).
  - **GHST (19):** 652.6299999999999975 GHST over 60 pocket → wallet legs, blocks 38141654–40216494.
- **Exits:** 69 exit disposal rows in the engine (53 pending, 16 resolved). On the ledger side, 7 withdrawal events consume resolved balance. Exit basis 318.81134371476028517891; display MV 3136.65386617873011483030 (not PnL; realized NULL).
- **Gas attribution (ledger side):** 367 expense, 25 into basis, 15 off proceeds, 0 NFT-sale txs at as_of. The NFT-sale rule is covered by golden G18.

## 6. Totals at as_of_block 49402932 (resolved lots only; USDC; marks = latest stored P3 price at or before the block; `mark_source` per row)
| variant | realized | unrealized | market value | open basis |
|---|---|---|---|---|
| all | −3.59855853704708600931 | −0.32168273311873724363 | 22.44676494453176518627 | 22.76844767765050242990 |
| excl_low | −3.59857645130237827100 | −0.09653383051473799482 | 10.34182900470643231073 | 10.43836283522117030555 |

- **Income:** 0.14162696287137066493.
- **Expenses:** 6.08439480767728805592.
- **Basis identity** (engine self-check): residual −2e-47.

## 7. Counts at as_of
- **Pending root lots (612):**
  - deposit 16;
  - migration 81 (NFTs, P6 carry);
  - unrecorded_inflow 515.
- **Q-H confirmed on the DB copy** (full rebuild state in `fifo_lot`): 562 root lots with `pending_reason=unrecorded_inflow`, all `basis_status=pending`, `basis_usdc` NULL, `basis_origin=unrecorded_inflow`, and `open_block` = the block of the shortfall out-leg (562/562). 5 custody children carry the same basis_origin.
- **Pending activity:** 92 pending lots open; 559 pending disposals.
- **NFTs:** 4 open NFT lots unmarked (no stored P3 price, Q8; counted, not valued).
- **Gas:** 407 entries → 413 ETH disposals, all pending (every ETH lot is a deposit or an unrecorded inflow).
  - MV 6.37599979318253295467; gas_expense 6.06275110218062249701 (resolved part 0).
  - Capitalized 0.31324869100191045765; in resolved basis 0.17824805913323320142.
- **Crafts:** 1 craft lot, 0 equal fallbacks, 3 free crafts.
- **Snapshot:** 186 pnl_snapshot rows, table md5 4b17f839e5459a60ca6ffb9b6b504f07. File md5 4fc87550f661d46e9ad6643a7734ae0a on both runs (`cmp` identical).

## 8. Likely cause of the gaps (not tuned)
- **ETH:** native ETH reached the wallet by a path ingest does not record. Likely an L1→L2 bridge deposit, or internal ETH transfers from contracts. The ledger records only 0.000101142 ETH of deposits.
- **GHST:** pocket balances were pulled into the wallet (3 txs) with no recorded inflow into the pockets. Likely channeling, or gotchis migrated from Polygon.

These are ingest gaps, not engine errors. Resolving them is P4.1.

## 9. Tests
**MBP:** full suite **249 tests OK** (8 skipped: the 7 migration tests, which run in p4_migration_test.sh and pass there, plus 1 skipped before P4).

New for rulings 3:
- `tests/test_p4_rulings3.py`, 9 tests:
  - G18 NFT-sale gas: nft_sale 500 GHST with gas 2 → proceeds 498, realized 298, GHST basis 500; the auction seller likewise.
  - G19 exit realized NULL.
  - G20 basis_origin carried to custody children.
  - MutationLifo, 3 tests: a LIFO `_take` is caught by the reconciliation (ETH realized −1000 / unrealized +1000 residuals, while the total residual is 0) and by golden G1.
  - The independent ledger side agrees with the engine on golden G1–G4, G13 and G14.
- `tests/test_p4_adapter.py`, 4 tests: as_of = MIN (set by the asset with the oldest latest price; NFTs don't gate it), the tx_index NULL check, no coalesce.
- `test_p4_migration`, +2: exit NULL in the view; basis_origin CHECK.
- G17 now expects an UNEXPLAINED GAP (flagged), not a pass.

**omarchywin:** the engine suites (golden, recompute, rulings, rulings3, adapter) give OK in p4_test.sh.

## 10. Not verified / follow-ups
- **abra:** omarchywin's abra was locked, so whether `cryptoPnL/CRYPTOPNL_LEDGER_PG_PASSWORD` exists could not be checked. Nothing was created or unlocked.
  - user_default needs to add it: `abra set cryptoPnL CRYPTOPNL_LEDGER_PG_PASSWORD`.
  - Since the architect's follow-up, `with_ledger_pg.sh` uses abra only (no .env fallback): it fails with a message naming CRYPTOPNL_LEDGER_PG_PASSWORD while abra is locked or the var is missing. The run above predates that change.
- **Gas on real data:** no resolved gas exists (all ETH lots are pending), so the gas part is proven by fixtures only.
- **excl_low:** reported, not reconciled.
- **Upgrade, destroy and bundle:** the ledger side doesn't model them (none on Base); it raises if they appear.

## 11. Open questions (owner)
1. **The missing ETH and GHST inflows** (architect + ingest owner; user_default for the facts). This is P4.1.
2. ~~fee_split equal on pending, swap gas into the bought asset's basis, Q-G equal split across queues~~: confirmed by the architect (rulings 3 item 3); `pending_architect` is empty.

## 12. P4.1 (prep — canonical run pending)
Status: **not run canonically.** The canonical rerun on `cryptopnl_p4_base` (omarchywin) waits on abra there being unlocked by user_default
(locked at every check 17:44–18:17 PT). Numbers marked *MBP non-canonical* come from the MBP copy `cryptopnl_p4_1_mbp` (P2.2 base + stored
P3 prices; evidence `docs/evidence/*_MBP_NONCANONICAL*`) and are **not** results; the canonical cells stay empty until the run.

**Ledger md5 (P4.1 md5 ruling, architect 18:22 PT): both are reported; gates use v2 from P4.1 on.** Definitions
(`cryptopnl/evidence.py`, also written into every `*ledger_md5*.txt` evidence file):
- **`ledger_md5_v1`** = the pre-P4.1 definition, unchanged (SQL byte-identical; formerly `ledger_md5_narrow`): md5 of
  `string_agg(concat_ws('|', hex(tx_hash), log_index, asset_id, qty, category, location, escrow_ref), ',' ORDER BY tx_hash, log_index,
  asset_id, location, qty)` over `ledger_entry WHERE chain_id`.
- **`ledger_md5_v1_pre_p4_1`** = v1 over the pre-P4.1 row set only: `... AND trace_address IS NULL` (every P4.1 internal-ETH leg has a
  trace address; no other row does). On a schema before migration 015 it equals v1.
- **`ledger_md5_v2`** = v1's fields + `coalesce(income_subtype,'')`, `coalesce(source_ref,'')`, `coalesce(trace_address,'')` (NULL kept
  in place as ''), `ORDER BY` v1's order + trace_address. **The canonical baseline from P4.1 on**; `scripts/p4_test.sh` gates on v2 and
  rows (`EXP_LEDGER_MD5_V2`, `EXP_LEDGER_ROWS`, no default until the canonical values below exist) and prints v1 / v1_pre, not gated.

| | canonical (`cryptopnl_p4_base`, omarchywin) | MBP non-canonical (`cryptopnl_p4_1_mbp`) | MBP pre-P4.1 control (`cryptopnl_p4_1_mbp_ctl`) |
|---|---|---|---|
| ledger_rows | _TBD_ | 1207 | 1191 |
| ledger_md5_v1 | _TBD_ (pre-P4.1: `210a71d811fd872a970b1d11770ced05`, 1321 rows) | `799e27209042e75206757ca6b4119744` | `3238fee8e7aa888d390f549b60d05200` |
| ledger_rows_pre_p4_1 | _TBD_ | 1192 | 1191 |
| ledger_md5_v1_pre_p4_1 | _TBD_ | `e7e254065b990e90a1550d545b8ca951` | `3238fee8e7aa888d390f549b60d05200` |
| internal_eth_txs (excluded below) | _TBD_ | 15 | 15 (list read from `cryptopnl_p4_1_mbp`) |
| ledger_rows_untouched_txs | _TBD_ | 1161 | 1161 |
| **ledger_md5_v1_untouched_txs** (continuity) | _TBD_ (vs the pre-P4.1 ledger over the same txs: `--untouched-txs-from-db cryptopnl_p4_base`) | `ccea8cbf4d81d8af2114ccc3ceab3695` | `ccea8cbf4d81d8af2114ccc3ceab3695` |
| **ledger_md5_v2** | **_TBD (canonical baseline)_** | `1646af93a2f1d766f9efb1c192450d4a` | `6df1b9aee68bdb0b0a7e67cb7b04987f` |
| ledger_md5_report | _TBD_ | `62458dbbddb2e5701e7054f7c348a55a` | `3bfb41e4d854f9f3fdaa104ffaefd5f7` |

The control is the same copy classified by the same code without the 15 internal-ETH raw rows (= the copy's pre-P4.1 ledger).
Three hashes are reported (architect, 19:48 PT): **v1 over all pre-P4.1 rows** (moves by rule 2, by design), **v1 over the untouched-tx
rows** (continuity: equal on both copies, `ccea8cbf…` over 1161 rows) and **v2** (the gate). `ledger_md5_v1_untouched_txs` =
v1 `AND NOT (tx_hash = ANY(<txs with a trace_address row>))`; to hash a pre-P4.1 ledger over the same rows, run
`cryptopnl ledger-md5 --untouched-txs-from-db <P4.1 db>` on it (the tx list is read from the P4.1 ledger).

**Txs touched by P4.1 on the MBP copy (excluded from the continuity hash):** 15 txs, one internal-ETH leg each.

| block | tx | internal-ETH legs | other rows in the tx |
|---|---|---|---|
| 12794901 | `0xb78fe8e8fa2df3c6fa21c9dfa97882e14e7c9aec60928fb70655dd1b8e17ae1e` | 1 | 0 |
| 12795081 | `0xccbfe04a6920793f7000b61d74e0da342e65252efe3e73170ec2f751c5bc58c0` | 1 | 2 |
| 23210972 | `0xf36f1da4357d153fa8f13a698aa012954eea7fc5fa9b34b198cc312089890210` | 1 | 0 |
| 40749157 | `0xcacfad72de1769c3cecdf63fdf0dd3f6ec958a23b53c2ef0839e3cdfa185f07f` | 1 | 1 |
| 40991112 | `0x7ec336225394e882ff9bebdab66a69b5f44e93627d65aeb633593a288e5c5592` | 1 | 2 |
| 41679144 | `0x4057b4a33188f6dcb9bf0900cc4deb2a5a3977edceeaa5fde0914e07cca7efef` | 1 | 2 |
| 46796145 | `0x640a3418c684f3ae638a62494460d8690a285005a5b5757804a8269d54d70126` | 1 | 3 |
| 46796599 | `0x3c988c5bfbb7f577970d4eb3342a3a3b5b4989f75370f8ab3db11df6917a6732` | 1 | 3 |
| 46860859 | `0xa5ee1787a49ef50f04b07cdbd3412fbbbd0dc95dc1e24c285a82feb38ab107df` | 1 | 0 |
| 46904091 | `0x0b09654a56af868a05a608b376158ac0f0d7c6bb5ed3bb882cc243fa85c4dce3` | 1 | 3 |
| 46918238 | `0x5d0d8221c923095f03bba141bf0293b63548a75312f34be3df808f145324839e` | 1 | 5 |
| 49384073 | `0x86d7518cc1776125befa6652becf2ccc76614a0f2e701cc80cd34c5ecf2714fa` | 1 | 2 |
| 51007144 | `0xdf1d76981dc9c1a165abe88a4f37e9ae62c5b560a57e6a45e3834a48a082e0e8` | 1 | 2 |
| 51481414 | `0x77b74a9f71a64c4c44eaf31893d15dd40c205da59a6a3ec495b0c3179409af00` | 1 | 3 |
| 51481437 | `0x48bb74c6f76949013d223d1623f8d417110691886a69f3ce835b73f9b91e2b67` | 1 | 3 |

Of the other rows in these txs, three differ from the pre-P4.1 control (rule 2): 49384073 and 51007144 (USDC −5 withdrawal → swap)
and 12795081 (USDC −30 swap, new: that tx was in review). The rest are unchanged.
Evidence: `docs/evidence/p4_1_ledger_md5_8453_MBP_NONCANONICAL.txt`, `..._MBP_NONCANONICAL_pre_p4_1_control.txt`.

**Old rows are NOT unchanged on the MBP copy, as is: v1_pre_p4_1 `e7e25406…` (1192 rows) ≠ the control's `3238fee8…` (1191 rows).**
Row diff (all three inside txs that gained an internal-ETH leg; rule 2 swap outputs):
- block 49384073, tx 0x86d7518c…, USDC −5: `withdrawal` → `swap` (ETH in-leg now paired);
- block 51007144, tx 0xdf1d7698…, USDC −5: `withdrawal` → `swap`;
- block 12795081, tx 0xccbfe04a…, USDC −30 `swap`: a new non-internal row (the tx was in review before; now a swap).
Rows of txs with no internal-ETH leg are byte-identical: v1 over them = `ccea8cbf4d81d8af2114ccc3ceab3695` (1161 rows) on both copies
(diagnostic, run by hand: v1 `AND tx_hash NOT IN (<the 15 internal-ETH txs>)`). So on canonical, v1_pre_p4_1 is expected to differ
from `210a71d8…` by the same rule-2 rows if those txs are in it; to be reported as is.
**as_of (rulings 4):** last ledger block = _TBD (canonical)_; set_by = last ledger block unless user_default passes `--as-of`.

**Counted exclusions: held assets with no valid mark at as_of** (excluded from unrealized, counted; never marked at basis or 0):

| asset | contract (Base) | reason (MBP) | held qty (MBP non-canonical) | canonical status |
|---|---|---|---|---|
| KEK | 0xe52b9170ff4ece4c35e796ffd74b57dec68ca0e5 | swap_scan_gap | 113,368.441671625025025670 | _TBD_ |
| FUD | 0x2028b4043e6722ea164946c82fe806c4a43a0ff4 | swap_scan_gap | 1,245,441.959187077688682901 | _TBD_ |
| FOMO | 0xa32137bfb57d2b6a9fd2956ba4b54741a6d54b58 | swap_scan_gap | 418,638.062663589051780483 | _TBD_ |
| ALPHA | 0x15e7cac885e3730ce6389447bc0f7ac032f31947 | swap_scan_gap | 261,182.755480408360768244 | _TBD_ |

On the MBP the reason is `swap_scan_gap` (no pool-swap scans there); omarchywin has the scans, so the canonical reason (stale pool,
thin tier, or priced) is only known after the run.

**Unexplained gaps:**
- **ETH:** 0 on the MBP copy (15 internal ETH legs, residual 0 at every probe); canonical _TBD_.
- **GHST:** before rule 7, 579.034393058025659651 GHST over 8 events on the MBP copy. **After rule 7 (pocket inflows, below): 0**, and
  reconcile is PASS with no unexplained gap on the MBP copy (canonical _TBD_).

**Income lines (rule 5 ruling):** `dao_distribution` from 0xf50326e1… (the Aavegotchi PTD claim, 1.0141283024 ETH at block 40749157) is
its own line under income; everything else is `general`. USDC values: _TBD (canonical)_.

**ETH pending lots by basis_origin:** _TBD (canonical)_; MBP: bridge_in 3 (Hop, Mayan Swift, Across), deposit 12, unrecorded_inflow 0.

**Rule 5 — FINAL: option (a), income (user_default 2026-10-28 19:54 PT, via the architect).** The whole 1.0141283024 ETH claim is
income at FMV (`income_subtype = dao_distribution`, `source_ref = 0xf50326e1…`, its own income line, in the income total); the ETH lot
opens at FMV (pending if unpriced). The 19:48 PT return-of-capital ruling stopped at its step-0 gate and was never built (no ROC,
RF split or basis_adjustment code or schema). Background, the PTD breakdown found at that gate:
- Sources: [pgendreau/aavegotchi-ptd](https://github.com/pgendreau/aavegotchi-ptd) @ 7cc2917 (2026-01-03): `README.md`,
  `GetTotalDistributionAmounts.py`, `CombinedVP/README.md` + `CombinedVP/getTotalVp.js`, `RF/README.md`, `AGIP155_Execution_Instructions.md`,
  `TotalDistributionAmounts.csv`, `claims.json`; AGIP 8/9 ([Aavegotchi, 2021-06-11](https://aavegotchi.medium.com/vote-agip8-and-agip9-give-voting-power-to-aavegotchis-and-wearables-9c113373a0a2)); [wiki: wearables voting power](https://wiki.aavegotchi.com/en/wearables).
- Allocation = 3 pools (`TotalDistributionAmounts.csv` sums: 1036.92 ETH = the distributor's funding): **rewardVP** 370.33 ETH
  pro rata to *combinedVP*; **rewardWeightedVP** 370.33 ETH pro rata to combinedVP × governance participation (share of decisions voted);
  **rewardRF** 296.26 ETH from the Rarity Farming S12 R1 leaderboards (BRS / kinship / XP of the wallet's gotchis, block 37694538).
- *combinedVP* (`getTotalVp.js`, Snapshot space aavegotchi.eth, Base block 37782588 / Polygon 78624868) = Snapshot VP from: GHST
  balance; **Aavegotchis and wearables** (`aavegotchi-agip`: AGIP 8 = 1 GHST of VP per gotchi BRS; AGIP 9 = wearables 5–10,000 GHST by
  rarity); **REALM parcels** (`aavegotchi-agip-17`); **GLTR-staked and unstaked GHST LP** (AGIP 37); FRENS pools; on Polygon also
  amGHST / wapGHST; **plus GHST held in the wallet's gotchi pockets** (Base + Polygon).
- This wallet (0x2127aa72…2e76, `claims.json` index 155, amountWei 1014128302400000000 = the ledger's 1.0141283024 ETH):
  combinedVP 17,687.0589; votingPercentage 0.522184 (153 proposals); rewardVP 0.4966842317 + rewardWeightedVP 0.4202192159 +
  rewardRF 0.0972248549 = 1.0141283024 ETH. The RF part (≈ 9.6%) is gotchi-based (e.g. gotchis 10478, 15486, 15017, 954, 10503 in the
  KIN / XP reward details). The split of the wallet's 17,687 VP between GHST, gotchis/wearables, parcels and LP is **not** in the repo
  (only the combined figure); not computed here.

### 12b. P4.1 rule 7: gotchi pocket inflows (architect ruling (a), 20:21 PT). MBP non-canonical; canonical _TBD_
Rule: DESIGN §8 P4.1 rule 7. Facts: `docs/evidence/p4_1_pockets.json` (`scripts/p4_1_pockets.py`; **4 HyperSync + 2 RPC** requests,
docs/P4_1_PLAN.md "Rule 7 round"), loaded with `cryptopnl pockets` (no network). Then classify, `price --seed-only` (0 RPC), `marks`
(12 RPC: GHST is now held at as_of 52112861), and P4 rebuild + reconcile.

**Gate (MBP copy):** GHST pocket in = **652629999999999997500** wei, out = **652629999999999997500** wei (652.6299999999999975 GHST, equal
to the wei); unexplained gap `{}` (ETH 0, GHST 0, was 579.034393058025659651 GHST over 8 events); acceptance **PASS**, identity_pass
true, failures []. Evidence: `docs/evidence/p4_1_rule7_reconcile_8453_MBP_NONCANONICAL.json` (before: `..._before.json`).

| | canonical | MBP before rule 7 | MBP after rule 7 |
|---|---|---|---|
| ledger_rows | _TBD_ | 1207 | 1639 |
| ledger_md5_v1 | _TBD_ | `799e27209042e75206757ca6b4119744` | `e528566f6d242a3a0d83f27b052ef8ed` |
| ledger_md5_v1_pre_p4_1 (rows) | _TBD_ | `e7e254065b990e90a1550d545b8ca951` (1192) | `41eb153178e68405e77e220072d546c9` (1624) |
| ledger_md5_v1_untouched_txs (rows) | _TBD_ | `ccea8cbf4d81d8af2114ccc3ceab3695` (1161) | `bd9c11169d6f27a95165825b6a64fed9` (1593) |
| **ledger_md5_v2** | **_TBD_** | `1646af93a2f1d766f9efb1c192450d4a` | `1dd87eeb33d8027c4dcb85ef004356b6` |
| ledger_md5_report | _TBD_ | `62458dbbddb2e5701e7054f7c348a55a` | `81a00041258c51d5db953943ab40c8c9` |
| review rows | _TBD_ | 4 (the 4 pocket txs: escrow not cached) | 10 (all `pocket_owner_mismatch`, 0 real review) |

The +432 rows: 156 income at `pocket:<id>`, 154 spam at `pocket:<id>`, and 61 + 61 custody legs (60 `batchTransferEscrow` GHST
withdrawals and the wallet's 1 FUD `depositERC20`). The untouched-txs hash covers the internal-ETH definition only, so it now also
includes the pocket rows (the hash is `trace_address`-based). Evidence: `docs/evidence/p4_1_rule7_ledger_md5_8453_MBP_NONCANONICAL.txt`.

**Pocket inflow legs by sender and token, before (on chain) → after (ledger category), blocks 35315787–46311838, 24 pockets:**

| sender | token | legs | after |
|---|---|---|---|
| RF relayer 0xf5239825… (`batchDepositGHST`) | GHST | 164 | 156 income `rarity_farming_payout` (104 txs, 652.6299999999999975 GHST) + 8 `pocket_owner_mismatch` (28.8225 GHST, gotchi 10774 before the wallet held it) |
| wallet group (0x2127…, `depositERC20`) | FUD 0x2028… | 1 | 1 `transfer_internal` |
| third party | 12 ERC-20 contracts, none allowlisted | 97 | 96 spam + 1 `pocket_owner_mismatch` (0x4fa840…, gotchi 10774) |
| third party | 7 ERC-721 contracts, none allowlisted | 54 | 54 spam |
| third party | 2 ERC-1155 contracts, none allowlisted | 4 | 4 spam |

The per-contract table is in the evidence JSON (`pockets.counts_before` / `counts_after`). Of the 97 third-party ERC-20 legs, 96 emit
Transfer with `from` = the USDC contract 0x833589fc…, the usual pattern of an airdrop-spam token.
**pocket_owner_mismatch: 10 legs** (9 inflows and the prior owner's 1 `transferEscrow` out of gotchi 10774, 28.8225 GHST at block
39606538), all `not_owned`; **rented at the deposit: 0**. The one rental of a wallet gotchi (954, listing 1151, executed 42195157,
ended 42750753) saw no pocket inflow. No lending operator was ever set (0 calls, 0 events). Nothing was lent at the first inflow block.
At that block, ownerOf equals the ledger replay for all 24 gotchis.
**Income lines (MBP):** `dao_distribution` 0xf50326e1… (1 entry); `rarity_farming_payout` 0xf5239825… (156 entries, 104 txs,
**156 unpriced** on the MBP: no stored GHST price at those blocks, so the lots are pending `no_price`, never 0); `general` (31 entries,
21 unpriced). The RF season is inferred, not tagged.
**Decision flagged for the architect:** all third-party non-GHST pocket inflows are non-allowlisted, so they fall under the §8
unsolicited-token spam rule. They are not booked as pending income lots (DESIGN §8 rule 7, implementation note).
**Canonical caveats:** pricing the 104 RF payout blocks on canonical goes through the P3 price order. Stored points or pool-swap
scans may cover them; if not, they need RPC, and that must be counted against the canonical RPC cap (250) before the run.

