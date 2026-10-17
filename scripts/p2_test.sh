#!/usr/bin/env bash
# P2 pass test. Run: abra run cryptoPnL -- scripts/p2_test.sh <chain> <wallet>   (CRYPTOPNL_DSN selects the DB)
set -euo pipefail
C=$1; W=$2; PY=${PY:-.venv/bin/python}; cd "$(dirname "$0")/.."
red() { sed -E "s/${W#0x}/<TEST_WALLET>/Ig; s/$W/<TEST_WALLET>/Ig"; }
$PY -m cryptopnl migrate | red
$PY -m cryptopnl ingest --chain "$C" --wallet "$W" 2>&1 | red          # logs + txs (log_index -1) + parents + market
$PY -m cryptopnl ingest --chain "$C" --wallet "$W" 2>&1 | red          # idempotent re-run
A=$($PY -m cryptopnl classify --chain "$C" 2>/dev/null | tail -1)
B=$($PY -m cryptopnl classify --chain "$C" 2>/dev/null | tail -1)
echo "classify#1 $A"; echo "classify#2 $B"
[ "$A" = "$B" ] || { echo "FAIL: classify not idempotent"; exit 1; }
mkdir -p docs/evidence
set +e; $PY -m cryptopnl classify-report --chain "$C" 2>/dev/null | red > "docs/evidence/p2_classify_$C.json"; rc=$?; set -e
cat "docs/evidence/p2_classify_$C.json"
[ $rc -eq 0 ] && echo "P2 PASS chain $C (classified > 98%)" || { echo "P2 FAIL chain $C"; exit 1; }
