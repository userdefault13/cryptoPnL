# P4 plan: FIFO engine (DESIGN v1.3 §4 P4, §8 P4 requirements, §9 Gotchiverse rules)

Branch `p4-fifo` off `main` 31e40bd (P3 merged, #7). Released by user_default through the CoS on 2026-10-28 15:34 PT.
DESIGN read: repo copy (md5 c6847da6…) and the architect's latest copy on the box (md5 c5f31f5c…). The box copy only adds the P3 rulings,
"Rule 10 widened" and "GLTR staking farm" notes to §9. §4, §5, §8 and the §9 P4 items are identical in both copies.

## Scope
1. FIFO lots and disposals per (wallet_group, asset), realized and unrealized PnL in USDC, deterministic recompute from block X.
2. §8 P4 requirements:
   - Realized and unrealized totals filter `basis_status <> 'pending'` on both mark and basis.
   - Report the count of pending lots and of pending disposals.
   - Write `lot_disposal.payment_for` (escrow fill → the NFT acquisition it paid for).
   - `manual_basis` is never under ON DELETE CASCADE from `ledger_entry` (it has no FK to it today; keep it that way and test it).
   - Pending lots carry a NULL price source.
3. §9 rules:
   - Craft and upgrade basis carry: inputs are disposals and their USDC value becomes the NFT basis.
   - Free craft: basis 0, not income.
   - `craft_pending`: cost held per queue ref until QueueClaimed.
   - Upgrade: the old lot closes with no realized PnL; new lot = old basis + upgrade cost.
   - Destroy/refund (rule 5, type 0).
   - Bundle disposal of a parcel with its equipped items.
   - Holdings by location (wallet, escrow:, parcel:, pocket:, lent:).
4. `migration_in`: custody. Lots keep the original (carried or manual) basis, or stay pending. Never income.
5. P3 follow-ups:
   - (a) Error messages and logs carry only the HTTP status and the JSON-RPC error code, never the response body (net.py:66-67, pricing.py:62, sources.py:17).
   - (b) price-report fails when migration 011 is applied but there is no `price_run` row for the chain.
   - (c) The narrow ledger md5 is written to an evidence file (`docs/evidence/p{3,4}_ledger_md5_<chain>.txt`).

## Steps (small commits, each verifiable)
1. This plan.
2. P3 follow-ups (a), (b), (c), plus unit tests.
3. Migration `013_p4_fifo.sql` and `rollback/013_down.sql`:
   - fifo_lot += location, open_kind, bundle_ref, queue_ref.
   - lot_disposal += kind (sale|spend|fee|craft_input|upgrade_input|bundle|destroy|custody_close) and bundle_ref.
   - pnl_snapshot as in §3.
   - fifo_run(id, chain_id, from_block, started_at, finished_at, lots, disposals, md5).
   - P2's migration lots move under the engine. Up/down/up is tested on a copy.
4. `cryptopnl/fifo.py`, the pure engine. Input: ordered ledger entries. Output: lots and disposals.
   No DB and no network inside, so the golden fixtures test it directly. Order: (block, tx_index, log_index, id), per DESIGN §3 and the P3 tx_index.
5. `cryptopnl/fifo_db.py`:
   - Load from `ledger_entry`, write lots and disposals in one transaction.
   - `rebuild(chain)` and `recompute(chain, from_block)`: delete projections with block ≥ X, replay lots open before X from their state at X.
   - `lots_md5` over a fixed column list.
6. Gotchiverse carry (craft, craft_pending/QueueClaimed, upgrade, destroy_refund, bundle, location holdings) on top of step 4, with synthetic fixtures for every §9 rule.
7. `pnl-report` CLI:
   - realized, unrealized, pending counts, by asset and location, with and without low confidence.
   - Mark at a fixed as_of block (the stored P3 price at or before it; never 0; unmarked → excluded and counted).
   - The reconciliation identity (blocked, see Q-C).
8. `scripts/p4_test.sh`: golden fixtures → full rebuild vs incremental md5 → reconciliation on a copy of `cryptopnl_p3_base` → evidence.
9. `docs/P4_RESULTS.md` and the PR.

## Files
New:
- `cryptopnl/fifo.py`, `cryptopnl/fifo_db.py`
- `migrations/013_p4_fifo.sql`, `migrations/rollback/013_down.sql`
- `tests/test_fifo_golden.py`, `tests/test_fifo_gotchiverse.py`, `tests/test_fifo_recompute.py`, `tests/test_p3_followups.py`
- `scripts/p4_test.sh`, `docs/P4_RESULTS.md`, `docs/evidence/p4_*_8453.*`

Changed: `cryptopnl/net.py`, `cryptopnl/sources.py`, `cryptopnl/pricing.py`, `cryptopnl/__main__.py`, `scripts/p3_test.sh` (md5 evidence line).

## Pass test
```
# omarchywin, ledger PG :5442 via /tmp/p22run.sh (password from ~/dev/cryptopnl-ledger-pg/.env, never printed).
# No HyperSync or RPC needed if the mark uses stored P3 prices (Q-F).
createdb -T cryptopnl_p3_base cryptopnl_p4_base
CRYPTOPNL_DSN=postgresql:///cryptopnl_p4_base /tmp/p22run.sh scripts/p4_test.sh 8453 > logs/p4_base.log 2>&1
```
PASS when:
- The golden fixtures pass (unit DB `cryptopnl_unit_p4`, created fresh).
- `fifo rebuild` md5 == `fifo recompute --from-block X` md5 for 3 values of X (earliest, mid, latest ledger block).
- The reconciliation residual is within the stated tolerance (Q-C).
- The narrow ledger md5 is still 210a71d811fd872a970b1d11770ced05, and the evidence is committed.

## Rollback
- **Code:** `git revert` the P4 commits on p4-fifo (no force push). main is untouched until the owner merges.
- **Schema:** `psql -f migrations/rollback/013_down.sql` drops the P4 columns and tables, then `DELETE FROM schema_migrations WHERE name='013_p4_fifo.sql'`.
  P2's pending migration lots are restored by `classify` (it rewrites them).
- **Data:** P4 only writes projections (fifo_lot, lot_disposal, pnl_snapshot, fifo_run) in copy DBs (`cryptopnl_p4_base`, `cryptopnl_unit_p4`).
  `DROP DATABASE` of those copies is the full rollback. `cryptopnl_p3_base`, `ledger_entry` and `manual_basis` are read-only for P4.
  Envio PG 5439/5440 is never touched.

## Open questions (architect / user_default). Steps 4–8 are blocked until answered
Real Base ledger (`docs/evidence/p3_classify_8453.json`, `p3_coverage_8453.json`), 1321 rows. Rows by category:

| category | rows | category | rows |
|---|---|---|---|
| fee (ETH gas) | 449 | spam | 340 |
| transfer_internal | 126 | migration_in (81 pending lots) | 81 |
| swap | 62 | withdrawal | 60 |
| untracked | 56 | income | 31 |
| escrow_out | 30 | nft_buy | 23 |
| deposit | 21 | escrow_return | 20 |
| craft | 12 | auction | 8 |
| bridge_in | 1 | spend | 1 |

- **Q-A (§5 Q7, owner user_default):** gas (449 fee rows). Is it capitalized into the trade's basis or proceeds, or is it a separate expense (an ETH disposal with no acquired asset)?
  When a tx has no tracked trade leg, is it an expense either way?
- **Q-B (owner architect):** `deposit` (21) and `withdrawal` (60) to and from outside addresses. Is a deposit an acquisition at FMV (POB), or a lot with pending/unknown basis?
  Is a withdrawal a disposal at FMV (realized PnL), or a custody exit (lots leave with no PnL)?
- **Q-C (owner architect):** the reconciliation identity "Σ(realized + unrealized) reconciles with net USDC flows plus market value". Which flows are "net USDC flows"?
  A proposal to confirm or replace, with every term at stored tx-time prices and pending lots excluded on both sides:
  `Σrealized + Σunrealized = MV(open lots at as_of) − Σbasis(all lots opened) + Σproceeds(all disposals)`. This holds by construction.
  The non-trivial external-flow form is:
  `= MV(as_of) + Σ value out (withdrawals, spends, fees-as-expense) − Σ value in (deposits, bridge_in, income at FMV, gifts at 0)`.
  This needs Q-A and Q-B. Also: is income PnL (a term in realized) or an inflow (a term in basis)? And what tolerance (rounding only, or a stated $ bound)?
- **Q-D (§5 Q8, owner user_default):** NFT marks for unrealized PnL. P3 implemented no Baazaar NFT marks (8 `nft_no_trade` entries).
  Until Q8 is answered, should open NFT lots be excluded from unrealized and counted, or marked at basis?
- **Q-E (§5 Q2, owner user_default):** transfer_internal (126 rows) carries basis within the wallet group (proposed yes). Are all Base wallets in one group?
- **Q-F (owner architect):** the mark block for unrealized PnL. A fixed `as_of` block per run (deterministic, uses stored P3 prices), or head priced live through the P3 pricer (RPC)?
