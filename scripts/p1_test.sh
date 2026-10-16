#!/usr/bin/env bash
# P1 pass tests. Usage: abra run cryptoPnL -- scripts/p1_test.sh <chain_id> <wallet>...
set -euo pipefail
cd "$(dirname "$0")/.."
CHAIN=$1; shift; W=(); for x in "$@"; do W+=(--wallet "$x"); done
export CRYPTOPNL_DSN=${CRYPTOPNL_DSN:-dbname=cryptopnl_test}
PY=.venv/bin/python
echo "== migrate"; $PY -m cryptopnl migrate
echo "== ingest #1"; $PY -m cryptopnl ingest --chain $CHAIN "${W[@]}"
C1=$($PY -m cryptopnl counts --chain $CHAIN 2>/dev/null); echo "counts1 $C1"
echo "== ingest #2 (reset cursors to re-scan full history)"
psql -q "$CRYPTOPNL_DSN" -c "DELETE FROM sync_cursor c USING wallet w WHERE w.id=c.wallet_id AND w.chain_id=$CHAIN" -c "DELETE FROM sync_cursor_global WHERE chain_id=$CHAIN"
$PY -m cryptopnl ingest --chain $CHAIN "${W[@]}"
C2=$($PY -m cryptopnl counts --chain $CHAIN 2>/dev/null); echo "counts2 $C2"
[ "$(echo "$C1" | jq -c '{raw_event,checksum}')" = "$(echo "$C2" | jq -c '{raw_event,checksum}')" ] && echo "PASS idempotent: identical raw_event count+checksum" || { echo "FAIL idempotent"; exit 1; }
echo "== verify balances (gate: TRACKED + config/allowlist.txt; others reported untracked)"
set +e; VERIFY_OUT=${VERIFY_OUT:-/tmp/p1_verify_$CHAIN.json} $PY -m cryptopnl verify --chain $CHAIN; VR=$?; set -e
case $VR in 0) echo "PASS balances (all gated assets match)";; 3) echo "N/A balances: no gated assets configured for chain $CHAIN";; *) echo "FAIL balances"; BAL=fail;; esac
echo "== simulated reorg (REORG_WINDOW=${REORG_TEST_WINDOW:-1000000})"; $PY -m cryptopnl simulate-reorg --chain $CHAIN
export REORG_WINDOW=${REORG_TEST_WINDOW:-1000000}
$PY -m cryptopnl ingest --chain $CHAIN "${W[@]}"
C3=$($PY -m cryptopnl counts --chain $CHAIN 2>/dev/null); echo "counts3 $C3"
[ "$(echo "$C1" | jq -c '{raw_event,checksum}')" = "$(echo "$C3" | jq -c '{raw_event,checksum}')" ] && echo "PASS reorg: rewound + re-ingested, count+checksum (incl. block hashes) restored" || { echo "FAIL reorg"; exit 1; }
[ "${BAL:-}" = fail ] && exit 2 || echo "ALL PASS"
