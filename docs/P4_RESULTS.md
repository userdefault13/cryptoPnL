# P4 results: FIFO engine, rulings 2026-10-28 (+ rulings 2), real Base ledger copy

**Verdict: `scripts/p4_test.sh` PASSES on chain 8453.** Rebuild == incremental; the reconciliation holds per asset and in total at 0.01 USDC; open quantity equals the ledger's net quantity, with the only differences explained by unrecorded inflows; two snapshots are byte-identical.
**Caveat:** the reconciliation covers only the resolved slice of the book. 664 of the 736 root lots and 622 of the 680 disposals are pending (counted and excluded on both sides, per Q-C). Every ETH lot is pending, so no gas falls inside resolved PnL on this ledger. The gas part of the identity is proven by the golden fixtures only (G13–G14).

Run: omarchywin, worktree `~/dev/cryptoPnL-p4` at 901cb56, `scripts/with_ledger_pg.sh scripts/p4_test.sh 8453 cryptopnl_p3_base cryptopnl_p4_base` (14 s, offline: no HyperSync, no RPC; marks come from stored P3 prices). Log: `docs/evidence/p4_test_8453.log`.
Writes went only to `cryptopnl_p4_base` (`createdb -T cryptopnl_p3_base`); the template was read-only. Envio PG 5439/5440 were not touched.

## 1. Ledger md5 (P3 follow-up c), read-only
`docs/evidence/p4_ledger_md5_8453.txt`:
- `ledger_rows=1321`, blocks 4328142–52911467.
- `ledger_md5_narrow=210a71d811fd872a970b1d11770ced05` (equals the P3 value).
- `ledger_md5_report=58cc79730edcf6b11a1e8ee39ea3ab97`.
- `review_rows=1`.

The copy after migrating 013 is identical (`p4_ledger_md5_8453_copy.txt`).

## 2. Migration 013
- **Applied** on the copy only: `{"applied": ["013_p4_fifo.sql"]}`.
- **Local up/down/up (MBP PG 16):** up == up2 (483 schema lines, md5 3c1ec586cc882d08a19322d36f4dd12a); down == 001..012 (353 lines); 5 constraint tests OK (`docs/evidence/p4_migration_013_local.txt`).
- **manual_basis** is never under ON DELETE CASCADE from ledger_entry.
- **P2 lots:** the copy's 82 P2 classify lots for the chain (81 pending migration lots + 1) are replaced by the P4 projection. manual_basis had 0 rows.

## 3. Rebuild vs incremental (`p4_rebuild_8453.json`, `p4_incremental_8453.json`)
| | rebuild | incremental (split at median block 40422429: 661 + 660 rows, state reloaded from the DB) |
|---|---|---|
| engine md5 | f198ed6c64c6c66ea49db87cfde82e6c | f198ed6c64c6c66ea49db87cfde82e6c |
| fifo_lot table md5 | c227629aa3f8b422ae98ef6bd48a1219 | c227629aa3f8b422ae98ef6bd48a1219 |
| lot_disposal table md5 | b9c2d064d8b791653a9bad39c8d98031 | b9c2d064d8b791653a9bad39c8d98031 |
| lots / disposals | 755 / 680 | 755 / 680 |

The head state's md5 is unchanged by the DB round trip (2bb2cdd0e1457ca2bc2302e894e29ca6 both ways).

## 4. Reconciliation (`p4_reconcile_8453.json`), as_of_block 52911410, tolerance 0.01 USDC, exact Decimal
- **Total:** engine realized + unrealized − gas_expense(resolved) = −1.74342019081785020856… USDC. The ledger side gives the same value; residual 2.8e-48.
- **Per asset:** 15 assets compared; the largest |residual| is 8.3e-48. Examples:
  - GHST (asset 19): engine −1.32031525518 = ledger (S 6.057006, A 163.963175, MV 7.288311, X 149.297542).
  - USDC (asset 20): −0.06491976836 = ledger.
  - FOMO (96): −0.07539412237. FUD (39): −0.05824479618. KEK (28): −0.05783117790. ALPHA (97): −0.04984725689.
- **Skipped:** 3 NFT assets (4 open lots) have no P3 price (Q8), so they are left out of both sides and counted. Engine PnL inside skipped assets is 0.
- **Quantity check:** open lot quantity equals the ledger's net quantity for every asset except two. Both differences equal the `unrecorded_inflow` quantity exactly:
  - ETH: engine 0 vs ledger −1.098635134819817605.
  - GHST: engine 185.066308881067227185 vs ledger −467.563691118932770315 (diff 652.6299999999999975).
- **Basis identity** (engine self-check): residual −1.5e-47.

## 5. Totals at as_of_block 52911410 (resolved lots only; USDC; marks = latest stored P3 price at or before the block, source per row in the snapshot `mark_source`)
| variant | realized | unrealized | market value | open basis |
|---|---|---|---|---|
| all | −3.59855853704708600931 | 1.85513834622923580075 | 50.67024035982677485200 | 48.81510201359753905125 |
| excl_low | −3.59857645130237827100 | 2.08028724883323504956 | 38.56530442000144197646 | 36.48501717116820692690 |

- **Income:** 0.14162696287137066493 (31 rows, FMV).
- **Expenses:** 6.40042552806476722742 (gas plus 1 spend).
- **Exits:** 81 (65 pending, 16 resolved). Exit basis 318.81134371476028517891; exit market value for display 3157.71443602205273986317 (not PnL).

## 6. Counts
- **Pending (root lots, 664):**
  - deposit 21 (ETH 12 = 0.000101142; GHST 3 = 127.697652688894130102; USDC 6 = 159.123837).
  - migration 81 (NFTs, P6 carry pending).
  - unrecorded_inflow 562 (ETH 502 lots = 1.098635134819817605 ETH; GHST 60 lots = 652.6299999999999975).
- **Open and pending:** 92 lots open pending; 622 pending disposals.
- **NFT-excluded:** 3 assets / 4 open lots with no P3 price (left out of unrealized and counted); 81 migration NFT lots pending. 15 resolved NFT lots are open, over 11 assets; the 4 unmarked lots are among them, and the rest are marked at a stored P3 price.
- **Gas:**
  - 449 gas entries → 457 FIFO ETH disposals. **All 457 are pending**, because every ETH lot is a pending deposit or unrecorded inflow.
  - Gas market value 6.78875193604804586855. gas_expense 6.37878182256810166851 (resolved part 0). Capitalized 0.40997011347994420003.
  - In resolved basis: 0.27094493161614633243 over 32 lots (split_method basis 32, equal 0). On pending lots: 0.
  - Ledger-side attribution: 30 txs into basis, 16 off proceeds, 403 gas_expense.
- **Crafts:** 1 craft lot with inputs (single asset, split_method single); **0 equal fallbacks**; 3 free crafts (basis 0). `craft_recipe_cost` has 0 rows. No recipe RPC was needed: no Base craft mints several assets under one ref.
- **Excluded rows:** spam 340, untracked 56.
- **Snapshot:** 190 pnl_snapshot rows (95 per variant), table md5 fc4450f8d98cedcb27a44765e946e0b5. The file md5 is ea3cf48ed5ea767f568c1444cf7996f0 for both runs (`cmp` identical).

## 7. Likely cause of the pending mass (not tuned)
- **ETH:** the ledger records native inflows of only 0.000101142 ETH (12 deposits), but outflows of 1.0988 ETH:
  - withdrawals 1.00057771652161008200
  - swaps 0.09263725807013363400
  - nft_buys 0.00331086333386720000
  - gas 0.00221043889420668900

  So native ETH reached the wallet by a path ingest does not record. Likely an L1→L2 bridge deposit, or internal ETH transfers from contracts.
- **GHST:** 3 txs (blocks 38141654, 38622419, 40216494) move GHST out of 20 gotchi pockets into the wallet. No row ever records GHST arriving in those pockets (likely pocket balances from channeling or from gotchis migrated from Polygon).

Both are ledger (ingest) gaps, not engine errors. Under `shortfall=pending` they become counted pending lots instead of stopping the run.

## 8. Tests
- **MBP** (Python 3.9, local PG 16 scratch DB): full suite 234 tests OK (6 skipped: the 5 migration tests that need their own scratch DB, which run in p4_migration_test.sh and pass, plus 1 that was skipped before P4).
- **New in P4:**
  - golden FIFO 44 (G1–G12)
  - recompute 3
  - rulings 15 (G13 gas from an ETH lot bought at a different price; G14 fee split basis/equal-on-pending; G15 pending exit; G16 Q-G recipe / equal fallback / free craft; G17 shortfall; plus recompute under the rulings at every block boundary)
  - DB adapter 1
  - follow-ups (a) 8, (b) 3, (c) 4
  - migration 5
- **omarchywin** (Python 3.14): the pure engine suites pass in p4_test.sh.

## 9. Not verified
- The gas part of the identity on real data: no resolved gas exists (all ETH lots pending). It is verified only by the fixtures.
- The basis of the 562 unrecorded inflows and 21 deposits is unknown, by design. It needs manual_basis, reclassification, or an ingest fix.
- Reading recipe costs over RPC is not implemented. The table and the engine path exist and Base needed 0 recipes.
- Only the `all` variant is reconciled; `excl_low` totals are reported but not reconciled.
- Mark staleness: each asset's mark is its latest stored P3 price at or before 52911410, which can be older than that block (`mark_source` gives the block).

## 10. Open questions (owner)
1. **Q-H shortfall** (architect): confirm `shortfall=pending`, or rule otherwise.
2. **Missing native ETH inflows (~1.0986 ETH) and GHST pocket inflows (652.63 GHST)** (architect + ingest owner; user_default for the facts):
   - Is the ETH a bridge deposit?
   - Were the pocket balances channeled or migrated?
   - Should ingest add native internal transfers and pocket inflows?
3. **fee_split with mixed resolved and pending acquisitions in one tx:** equal is my reading of ruling 2(a) (architect).
4. **Swap gas** goes into the bought asset's basis, not off the sold asset's proceeds (architect).
5. **as_of_block** = the latest block with any stored P3 price; marks are the latest price at or before it (architect).
6. **Q-G for one input ref joined across several queues:** the items are unknown until claim, so the split is equal and flagged (architect).
7. **Exit rows in the stored column:** `lot_disposal.realized_pnl_usdc` stays proceeds − cost, so it is NULL for exits. The view `lot_disposal_pnl.realized_usdc` gives 0 (architect).
