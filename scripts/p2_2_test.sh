#!/usr/bin/env bash
# P2.2 pass test (DESIGN v1.3 §9). ONE chain at a time, under nohup:
#   abra run cryptoPnL -k ENVIO_API_TOKEN -- nohup scripts/p2_2_test.sh <chain> > logs/p2_2_<chain>.log 2>&1 &
# CRYPTOPNL_DSN selects the DB (a copy, never the P2.1 evidence DBs). Wallets are read from the DB and redacted in output.
# HyperSync: every request goes through the host lock (<= 5 starts / 60 s, all processes); GAP sleeps kept as in P2.
set -euo pipefail
C=$1; PY=${PY:-.venv/bin/python}; GAP=${GAP:-75}; cd "$(dirname "$0")/.."
export NET_REQLOG=${NET_REQLOG:-$PWD/logs/net_requests_p2_2.log}; mkdir -p logs docs/evidence; touch "$NET_REQLOG"
W=$(psql -Atq "$CRYPTOPNL_DSN" -c "SELECT '0x'||encode(address,'hex') FROM wallet WHERE chain_id=$C ORDER BY id LIMIT 1")
red() { sed -E "s/${W#0x}/<TEST_WALLET>/Ig"; }
digest() { psql -Atq "$CRYPTOPNL_DSN" -c "SELECT md5(string_agg(concat_ws('|',encode(tx_hash,'hex'),log_index,asset_id,qty,category,location,escrow_ref),',' ORDER BY tx_hash,log_index,asset_id,location,qty)) FROM ledger_entry WHERE chain_id=$C"; }
T0=$(date +%s)
$PY -m cryptopnl migrate | red
echo "sleep ${GAP}s"; sleep "$GAP"
$PY -m cryptopnl ingest --chain "$C" --wallet "$W" 2>&1 | red          # + gv (hypersync_gv) before tx_meta
echo "sleep ${GAP}s"; sleep "$GAP"
$PY -m cryptopnl ingest --chain "$C" --wallet "$W" 2>&1 | red          # idempotent re-run
A=$($PY -m cryptopnl classify --chain "$C" 2>/dev/null | tail -1); DA=$(digest)
B=$($PY -m cryptopnl classify --chain "$C" 2>/dev/null | tail -1); DB=$(digest)
echo "classify#1 $A ledger_md5=$DA"; echo "classify#2 $B ledger_md5=$DB"
[ "$A" = "$B" ] && [ "$DA" = "$DB" ] || { echo "FAIL: classify not idempotent"; exit 1; }
set +e; $PY -m cryptopnl classify-report --chain "$C" 2>/dev/null | red > "docs/evidence/p2_2_classify_$C.json"; rc=$?; set -e
cat "docs/evidence/p2_2_classify_$C.json"
psql -Atq "$CRYPTOPNL_DSN" -c "SELECT kind, count(*) FROM raw_event WHERE chain_id=$C AND kind LIKE 'gv_%' GROUP BY 1 ORDER BY 1" | tee "docs/evidence/p2_2_gv_events_$C.txt"
$PY scripts/reqlog_summary.py "$NET_REQLOG" hypersync "$T0" 5 | tee "docs/evidence/p2_2_hypersync_$C.txt"; hs=${PIPESTATUS[0]}
[ $rc -eq 0 ] && [ $hs -eq 0 ] && echo "P2.2 PASS chain $C (classified > 98%, identical ledger, HyperSync <= 5/min)" || { echo "P2.2 FAIL chain $C (report rc=$rc, hypersync rc=$hs)"; exit 1; }
