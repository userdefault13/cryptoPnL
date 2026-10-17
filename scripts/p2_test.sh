#!/usr/bin/env bash
# P2 pass test. Run ONE chain at a time: abra run cryptoPnL -- scripts/p2_test.sh <chain> <wallet>   (CRYPTOPNL_DSN selects the DB)
# HyperSync host budget 5/min (architect, PR #3 approval): sleep >= 70 s before and between the ingest passes, so no 60 s window spans two processes.
set -euo pipefail
C=$1; W=$2; PY=${PY:-.venv/bin/python}; GAP=${GAP:-75}; cd "$(dirname "$0")/.."
export NET_REQLOG=${NET_REQLOG:-$PWD/logs/net_requests.log}; mkdir -p logs docs/evidence; touch "$NET_REQLOG"
red() { sed -E "s/${W#0x}/<TEST_WALLET>/Ig; s/$W/<TEST_WALLET>/Ig"; }
T0=$(date +%s)
$PY -m cryptopnl migrate | red
echo "sleep ${GAP}s (HyperSync gap before pass 1)"; sleep "$GAP"
$PY -m cryptopnl ingest --chain "$C" --wallet "$W" 2>&1 | red          # logs + txs + parents + market (HyperSync) + tx_meta (RPC)
echo "sleep ${GAP}s (HyperSync gap between passes)"; sleep "$GAP"
$PY -m cryptopnl ingest --chain "$C" --wallet "$W" 2>&1 | red          # idempotent re-run
A=$($PY -m cryptopnl classify --chain "$C" 2>/dev/null | tail -1)
B=$($PY -m cryptopnl classify --chain "$C" 2>/dev/null | tail -1)
echo "classify#1 $A"; echo "classify#2 $B"
[ "$A" = "$B" ] || { echo "FAIL: classify not idempotent"; exit 1; }
set +e; $PY -m cryptopnl classify-report --chain "$C" 2>/dev/null | red > "docs/evidence/p2_classify_$C.json"; rc=$?; set -e
cat "docs/evidence/p2_classify_$C.json"
$PY scripts/reqlog_summary.py "$NET_REQLOG" hypersync "$T0" 5 | tee "docs/evidence/p2_hypersync_$C.txt"; hs=${PIPESTATUS[0]}
[ $rc -eq 0 ] && [ $hs -eq 0 ] && echo "P2 PASS chain $C (classified > 98%, HyperSync <= 5/min)" || { echo "P2 FAIL chain $C (report rc=$rc, hypersync rc=$hs)"; exit 1; }
