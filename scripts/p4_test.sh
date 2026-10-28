#!/usr/bin/env bash
# P4 pass test (DESIGN §4 P4, §8 'P4 rulings (2026-10-28)' + 'P4 rulings 2'). ONE run, offline: no HyperSync, no RPC (marks come from
# stored P3 prices). Reads the source DB, writes only to a fresh COPY of it (never the template):
#   scripts/with_ledger_pg.sh scripts/p4_test.sh 8453 cryptopnl_p3_base cryptopnl_p4_base
# Steps: 1 ledger md5 of the source == the P3 value; 2 createdb -T source copy, migrate (013) on the copy, ledger md5 unchanged;
# 3 full rebuild; 4 incremental (rebuild to the median block, persist, reload from the DB, continue) -> md5s equal the rebuild's;
# 5 reconciliation per asset and in total (tol 0.01 USDC) + open qty vs ledger net qty; 6 snapshot twice -> byte-identical;
# 7 unit suites. Evidence: docs/evidence/p4_*_<chain>.*
set -euo pipefail
C=$1; SRC=$2; DST=$3; PY=${PY:-.venv/bin/python}; cd "$(dirname "$0")/.."
EXP_MD5=${EXP_LEDGER_MD5:-210a71d811fd872a970b1d11770ced05}; EXP_ROWS=${EXP_LEDGER_ROWS:-1321}
case "$DST" in cryptopnl_p4_*) ;; *) echo "FAIL: target DB must be named cryptopnl_p4_* (a copy), got $DST"; exit 2;; esac
[ "$SRC" != "$DST" ] || { echo "FAIL: source == target"; exit 2; }
E=docs/evidence; mkdir -p "$E" logs; T0=$(date +%s); fail() { echo "P4 FAIL: $*"; exit 1; }
j() { $PY -c "import json,sys; d=json.load(open(sys.argv[1])); print(eval(sys.argv[2], {'d': d}))" "$@"; }
echo "== 1 source ledger md5 ($SRC)"
CRYPTOPNL_DSN="dbname=$SRC" $PY -m cryptopnl ledger-md5 --chain "$C" --out "$E/p4_ledger_md5_$C.txt" 2>/dev/null | tail -1
grep -q "^ledger_md5_narrow=$EXP_MD5$" "$E/p4_ledger_md5_$C.txt" && grep -q "^ledger_rows=$EXP_ROWS$" "$E/p4_ledger_md5_$C.txt" \
  || fail "source ledger md5/rows differ from $EXP_MD5/$EXP_ROWS"
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
j "$E/p4_reconcile_$C.json" "'pass=%s total_residual=%s failures=%s' % (d['reconciliation']['pass'], d['reconciliation']['total']['residual'], d['reconciliation']['failures'])"
echo "== 6 snapshot x2"
for n in 1 2; do CRYPTOPNL_DSN="dbname=$DST" $PY -m cryptopnl.p4 snapshot --chain "$C" --out "$E/p4_snapshot_${C}_$n.json" | tail -1; done
cmp "$E/p4_snapshot_${C}_1.json" "$E/p4_snapshot_${C}_2.json" || fail "snapshots differ"
echo "snapshot byte-identical: OK ($(md5sum < "$E/p4_snapshot_${C}_1.json" | cut -c1-32))"
echo "== 7 unit suites (pure engine)"
$PY -m unittest -q tests.test_fifo_golden tests.test_fifo_recompute tests.test_fifo_rulings 2>&1 | tail -1
[ "$rc" = 0 ] || fail "reconciliation residual above 0.01 USDC (see $E/p4_reconcile_$C.json)"
echo "P4 PASS chain $C ($(( $(date +%s) - T0 )) s)"
