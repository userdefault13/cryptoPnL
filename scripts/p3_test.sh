#!/usr/bin/env bash
# P3 pass test (DESIGN §4 P3). RPC (1 req/s) + DefiLlama (1 req/s) only; ZERO HyperSync requests. Run under nohup:
#   CRYPTOPNL_DSN=postgresql:///cryptopnl_p3_base nohup scripts/p3_test.sh 8453 > logs/p3_base.log 2>&1 &
# The DB is a local copy of the P2.1 Base ledger (createdb -T cryptopnl_p11s_base cryptopnl_p3_base); no re-ingest.
set -euo pipefail
C=$1; PY=${PY:-.venv/bin/python}; cd "$(dirname "$0")/.."
export NET_REQLOG=${NET_REQLOG:-$PWD/logs/net_requests_p3.log}; mkdir -p logs docs/evidence; touch "$NET_REQLOG"
T0=$(date +%s); E=docs/evidence
$PY -m cryptopnl migrate
$PY -m cryptopnl tx-index --chain "$C"                     # RPC: tx position where a block holds >= 2 wallet txs
A=$($PY -m cryptopnl classify --chain "$C" 2>/dev/null | tail -1); B=$($PY -m cryptopnl classify --chain "$C" 2>/dev/null | tail -1)
echo "classify#1 $A"; echo "classify#2 $B"; [ "$A" = "$B" ] || { echo "FAIL: classify not idempotent"; exit 1; }
$PY -m cryptopnl classify-report --chain "$C" 2>/dev/null > "$E/p3_classify_$C.json" || true
$PY -m cryptopnl price --chain "$C" 2>&1 | tee "$E/p3_price_$C.log"
set +e
$PY -m cryptopnl price-report --chain "$C" 2>/dev/null | tee "$E/p3_coverage_$C.json"; c3=${PIPESTATUS[0]}
$PY -m cryptopnl price-sample --chain "$C" 2>/dev/null > "$E/p3_sample_$C.jsonl"; c12=$?
tail -1 "$E/p3_sample_$C.jsonl"
set -e
$PY scripts/reqlog_summary.py "$NET_REQLOG" hypersync "$T0" 5 | tee "$E/p3_hypersync_$C.txt" || true
grep -c " rpc attempt" "$NET_REQLOG" | sed 's/^/rpc attempts (all P3 runs in this log): /'
awk -v t0="$T0" '$1>=t0 {n[$2" "$3]++} END {for (k in n) print k, n[k]}' "$NET_REQLOG" | sort | tee "$E/p3_requests_$C.txt"
[ $c3 -eq 0 ] && [ $c12 -eq 0 ] && echo "P3 PASS chain $C" || { echo "P3 FAIL chain $C (coverage rc=$c3, sample rc=$c12)"; exit 1; }
