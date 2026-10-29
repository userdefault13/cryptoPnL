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
