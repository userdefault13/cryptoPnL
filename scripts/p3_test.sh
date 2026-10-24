#!/usr/bin/env bash
# P3 pass test (DESIGN v1.3 §4 P3 as amended by the P3 rulings, §8). ONE run, under nohup and abra (HyperSync key for the pool-swap scan):
#   CRYPTOPNL_DSN=postgresql:///cryptopnl_p3_base nohup abra run cryptoPnL -k ENVIO_API_TOKEN -- scripts/p3_test.sh 8453 > logs/p3_base.log 2>&1 &
# DB: a copy of the P2.2 Base ledger (createdb -T cryptopnl_p22_base cryptopnl_p3_base); no wallet re-ingest.
# Network: free Base RPC through the host RPC bucket (RPC_RPM/60 s, RPC_MIN_GAP_S), DefiLlama (1 req/s), HyperSync only for the
# thin-pool Swap-log scan (shared 5/min + 12 s bucket). Read-only.
set -euo pipefail
C=$1; PY=${PY:-.venv/bin/python}; cd "$(dirname "$0")/.."
export NET_REQLOG=${NET_REQLOG:-$PWD/logs/net_requests_p3.log}; mkdir -p logs docs/evidence; touch "$NET_REQLOG"
T0=$(date +%s); E=docs/evidence
$PY -m cryptopnl migrate
$PY -m cryptopnl tx-index --chain "$C"                     # RPC: tx position where a block holds >= 2 wallet txs
A=$($PY -m cryptopnl classify --chain "$C" 2>/dev/null | tail -1); B=$($PY -m cryptopnl classify --chain "$C" 2>/dev/null | tail -1)
echo "classify#1 $A"; echo "classify#2 $B"; [ "$A" = "$B" ] || { echo "FAIL: classify not idempotent"; exit 1; }
$PY -m cryptopnl classify-report --chain "$C" 2>/dev/null > "$E/p3_classify_$C.json" || true
$PY -m cryptopnl pool-swaps --chain "$C" 2>&1 | tee "$E/p3_pool_swaps_$C.log"
$PY -m cryptopnl price --chain "$C" 2>&1 | tee "$E/p3_price_$C.log"
set +e
$PY -m cryptopnl price-report --chain "$C" 2>/dev/null | tee "$E/p3_coverage_$C.json"; c3=${PIPESTATUS[0]}
$PY -m cryptopnl price-sample --chain "$C" 2>/dev/null > "$E/p3_sample_$C.jsonl"; c12=$?
tail -1 "$E/p3_sample_$C.jsonl"
$PY scripts/reqlog_summary.py "$NET_REQLOG" hypersync "$T0" 5 > "$E/p3_hypersync_$C.txt"; hs=$?
$PY scripts/reqlog_summary.py "$NET_REQLOG" rpc "$T0" "${RPC_RPM:-30}" > "$E/p3_rpc_$C.txt"; rs=$?
$PY scripts/reqlog_summary.py "$NET_REQLOG" defillama "$T0" 60 > "$E/p3_defillama_$C.txt"
for s in hypersync rpc; do awk -v t0="$T0" -v s="$s" '$1>=t0 && $2==s && $3=="attempt" {if (p!="") {d=$1-p; if (m==""||d<m) m=d}; p=$1} END {printf "min_gap_s=%s\n", (m==""?"n/a":sprintf("%.3f",m))}' "$NET_REQLOG" >> "$E/p3_${s}_$C.txt"; done
grep -vE "^  20" "$E/p3_hypersync_$C.txt"; grep -vE "^  20" "$E/p3_rpc_$C.txt"; grep -E "requests=|429s=" "$E/p3_defillama_$C.txt"
set -e
[ $c3 -eq 0 ] && [ $c12 -eq 0 ] && [ $hs -eq 0 ] && [ $rs -eq 0 ] && echo "P3 PASS chain $C" || { echo "P3 FAIL chain $C (coverage rc=$c3, sample rc=$c12, hypersync rc=$hs, rpc rc=$rs)"; exit 1; }
