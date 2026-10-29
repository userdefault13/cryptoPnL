#!/usr/bin/env bash
# P4 test (DESIGN §4 P4, §8 'P4 rulings (2026-10-28)', 'P4 rulings 2', 'P4 rulings 3'). ONE run, offline: no HyperSync, no RPC (marks come from
# stored P3 prices). Reads the source DB, writes only to a fresh COPY of it (never the template):
#   scripts/with_ledger_pg.sh scripts/p4_test.sh 8453 cryptopnl_p3_base cryptopnl_p4_base
# Steps: 1 ledger md5 v2 + rows of the source == the recorded baseline (P4.1 md5 ruling: gates use v2; v1 and v1 over the
#   pre-P4.1 rows are printed, not gated); 2 createdb -T source copy, migrate (013) on the copy, ledger md5 unchanged;
# 3 full rebuild; 4 incremental (rebuild to the median block, persist, reload from the DB, continue) -> md5s equal the rebuild's;
# 5 reconciliation against an INDEPENDENT ledger side (ledger rows only, its own FIFO and running balance) per asset and in total
# (tol 0.01 USDC) at as_of_block = the last ledger block unless --as-of (P4 rulings 4; marks at as_of); 6 snapshot twice -> byte-identical;
# 7 unit suites. Outcome: exit 0 'P4 PASS'; exit 3 'P4 FLAGGED' = identity and md5s hold but the ledger has an UNEXPLAINED GAP
# (balance with no recorded inflow; real-ledger acceptance deferred to P4.1); exit 1 'P4 FAIL'. Evidence: docs/evidence/p4_*_<chain>.*
set -euo pipefail
C=$1; SRC=$2; DST=$3; PY=${PY:-.venv/bin/python}; cd "$(dirname "$0")/.."
# v2 baseline: the canonical value is recorded in docs/P4_RESULTS.md §12 after the canonical P4.1 run (no default until then).
EXP_MD5=${EXP_LEDGER_MD5_V2:?set EXP_LEDGER_MD5_V2 (canonical ledger_md5_v2 baseline, docs/P4_RESULTS.md §12)}
EXP_ROWS=${EXP_LEDGER_ROWS:?set EXP_LEDGER_ROWS (canonical ledger row count, docs/P4_RESULTS.md §12)}
PRE_V1=210a71d811fd872a970b1d11770ced05   # canonical pre-P4.1 v1 (1321 rows): informational only
case "$DST" in cryptopnl_p4_*) ;; *) echo "FAIL: target DB must be named cryptopnl_p4_* (a copy), got $DST"; exit 2;; esac
[ "$SRC" != "$DST" ] || { echo "FAIL: source == target"; exit 2; }
E=docs/evidence; mkdir -p "$E" logs; T0=$(date +%s); fail() { echo "P4 FAIL: $*"; exit 1; }
j() { $PY -c "import json,sys; d=json.load(open(sys.argv[1])); print(eval(sys.argv[2], {'d': d}))" "$@"; }
echo "== 1 source ledger md5 ($SRC)"
CRYPTOPNL_DSN="dbname=$SRC" $PY -m cryptopnl ledger-md5 --chain "$C" --out "$E/p4_ledger_md5_$C.txt" 2>/dev/null | tail -1
grep -q "^ledger_md5_v2=$EXP_MD5$" "$E/p4_ledger_md5_$C.txt" && grep -q "^ledger_rows=$EXP_ROWS$" "$E/p4_ledger_md5_$C.txt" \
  || fail "source ledger md5 v2/rows differ from $EXP_MD5/$EXP_ROWS"
k() { grep "^$1=" "$E/p4_ledger_md5_$C.txt" | cut -d= -f2; }
echo "v1 $(k ledger_md5_v1); v1 over pre-P4.1 rows $(k ledger_md5_v1_pre_p4_1) ($(k ledger_rows_pre_p4_1) rows; moved by rule 2 by design; pre-P4.1 v1 was $PRE_V1)"
echo "v1 over untouched-tx rows (continuity) $(k ledger_md5_v1_untouched_txs) ($(k ledger_rows_untouched_txs) rows, $(k internal_eth_txs) txs excluded); not gated"
echo "== 2 copy $SRC -> $DST, migrate the copy"
dropdb --if-exists "$DST"; createdb -T "$SRC" "$DST"
CRYPTOPNL_DSN="dbname=$DST" $PY -m cryptopnl migrate 2>/dev/null | tail -1
CRYPTOPNL_DSN="dbname=$DST" $PY -m cryptopnl ledger-md5 --chain "$C" --out "$E/p4_ledger_md5_${C}_copy.txt" 2>/dev/null >/dev/null
diff <(grep -v '^#' "$E/p4_ledger_md5_$C.txt") <(grep -v '^#' "$E/p4_ledger_md5_${C}_copy.txt") || fail "copy ledger differs from source"
echo "== 3 full rebuild"
CRYPTOPNL_DSN="dbname=$DST" $PY -m cryptopnl.p4 rebuild --chain "$C" --out "$E/p4_rebuild_$C.json" > /dev/null
echo "rebuild $(j "$E/p4_rebuild_$C.json" "d['engine_md5'], d['fifo_lot_md5'], d['lot_disposal_md5'], d['lots'], d['disposals']")"
X=$(psql -Atq -d "$DST" -c "SELECT percentile_disc(0.5) WITHIN GROUP (ORDER BY block_number) FROM ledger_entry WHERE chain_id=$C")
echo "== 4 incremental from block $X"
CRYPTOPNL_DSN="dbname=$DST" $PY -m cryptopnl.p4 incremental --chain "$C" --split-block "$X" --out "$E/p4_incremental_$C.json" > /dev/null
for k in engine_md5 fifo_lot_md5 lot_disposal_md5 lots disposals; do
  a=$(j "$E/p4_rebuild_$C.json" "d['$k']"); b=$(j "$E/p4_incremental_$C.json" "d['$k']")
  [ "$a" = "$b" ] || fail "rebuild vs incremental $k: $a != $b"; done
[ "$(j "$E/p4_incremental_$C.json" "d['head_md5']==d['head_md5_reloaded_from_db']")" = True ] || fail "state round trip through the DB changed the md5"
echo "incremental == rebuild: OK"
echo "== 5 reconciliation"
rc=0; CRYPTOPNL_DSN="dbname=$DST" $PY -m cryptopnl.p4 reconcile --chain "$C" --out "$E/p4_reconcile_$C.json" > /dev/null || rc=$?
[ "$rc" = 0 ] || [ "$rc" = 3 ] || [ "$rc" = 1 ] || fail "reconcile crashed (rc $rc)"
j "$E/p4_reconcile_$C.json" "'as_of_block=%s set_by=%s acceptance=%s identity_pass=%s total_residual=%s exits=%s failures=%s' % (d['as_of_block'], d['as_of']['set_by'], d['reconciliation']['acceptance'], d['reconciliation']['identity_pass'], d['reconciliation']['total']['residual'], d['reconciliation']['exits'], d['reconciliation']['failures'])"
j "$E/p4_reconcile_$C.json" "'\\n'.join('UNEXPLAINED GAP asset %s: qty %s in %s events, blocks %s..%s' % (a, g['qty'], g['events'], g['first_block'], g['last_block']) for a, g in sorted(d['reconciliation']['unexplained_gap'].items())) or 'no unexplained gap'"
j "$E/p4_reconcile_$C.json" "'pockets (P4.1 rule 7): ghst_gate=%s owner_mismatch_legs=%s' % (d.get('pockets', {}).get('ghst_gate'), d.get('pockets', {}).get('pocket_owner_mismatch', {}).get('legs'))"
pg=$($PY -c "import json,sys; g=json.load(open(sys.argv[1])).get('pockets',{}).get('ghst_gate'); print('ok' if (g is None or g['in_eq_out']) else 'bad')" "$E/p4_reconcile_$C.json")
[ "$pg" = ok ] || fail "GHST pocket in != out (P4.1 rule 7 gate)"
echo "== 6 snapshot x2"
for n in 1 2; do CRYPTOPNL_DSN="dbname=$DST" $PY -m cryptopnl.p4 snapshot --chain "$C" --out "$E/p4_snapshot_${C}_$n.json" | tail -1; done
cmp "$E/p4_snapshot_${C}_1.json" "$E/p4_snapshot_${C}_2.json" || fail "snapshots differ"
echo "snapshot byte-identical: OK ($(md5sum < "$E/p4_snapshot_${C}_1.json" | cut -c1-32))"
echo "== 7 unit suites (pure engine)"
u=$($PY -m unittest -q tests.test_fifo_golden tests.test_fifo_recompute tests.test_fifo_rulings tests.test_p4_rulings3 tests.test_p4_adapter tests.test_entry_key tests.test_p4_1_inflows tests.test_p4_1_pockets 2>&1 | tail -1); echo "$u"
[ "$u" = OK ] || fail "unit suites: $u"
[ "$rc" != 1 ] || fail "reconciliation residual above 0.01 USDC or qty mismatch (see $E/p4_reconcile_$C.json)"
if [ "$rc" = 3 ]; then
  echo "P4 FLAGGED chain $C: identity within 0.01 USDC, md5s equal; UNEXPLAINED GAP reported above (real-ledger acceptance deferred to P4.1) ($(( $(date +%s) - T0 )) s)"
  exit 3; fi
echo "P4 PASS chain $C ($(( $(date +%s) - T0 )) s)"
