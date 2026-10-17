#!/usr/bin/env bash
# P2.2 review rerun (PR #5). Run on the machine with the DBs, under nohup, ONE invocation (chains run one after the other):
#   abra run cryptoPnL -k ENVIO_API_TOKEN -- nohup scripts/p2_2_rerun.sh > logs/p2_2_rerun.log 2>&1 &
# 1. Re-create the scratch copies cryptopnl_p22_{base,sep} from the P2.1 evidence DBs (templates are only read), so the final
#    migration 008 (BEGIN/COMMIT + gotchi_escrow) applies and hypersync_gv re-scans with the new alchemica selection.
# 2. Per chain: scripts/p2_2_test.sh (P2.2 pass) then scripts/p2_test.sh (P2 pass) on the same DB; both through the host HyperSync lock.
#    p2_test.sh's evidence lands as docs/evidence/p2_2_p2pass_*; the committed P2 evidence files are restored untouched.
set -euo pipefail; cd "$(dirname "$0")/.."; GAP=${GAP:-75}
for pair in "8453 cryptopnl_p11s_base cryptopnl_p22_base" "84532 cryptopnl_p11s_sep cryptopnl_p22_sep"; do
  set -- $pair; C=$1; TPL=$2; DB=$3
  dropdb --if-exists "$DB"; createdb -T "$TPL" "$DB"
  export CRYPTOPNL_DSN=postgresql:///$DB
  echo "== $C P2.2 pass ($(date))"; scripts/p2_2_test.sh "$C" || echo "P2.2 pass test FAILED chain $C"
  echo "sleep ${GAP}s"; sleep "$GAP"
  W=$(psql -Atq "$CRYPTOPNL_DSN" -c "SELECT '0x'||encode(address,'hex') FROM wallet WHERE chain_id=$C ORDER BY id LIMIT 1")
  echo "== $C P2 pass ($(date))"; scripts/p2_test.sh "$C" "$W" || echo "P2 pass test FAILED chain $C"
  mv "docs/evidence/p2_classify_$C.json" "docs/evidence/p2_2_p2pass_classify_$C.json"
  mv "docs/evidence/p2_hypersync_$C.txt" "docs/evidence/p2_2_p2pass_hypersync_$C.txt"
  git checkout -- "docs/evidence/p2_classify_$C.json" "docs/evidence/p2_hypersync_$C.txt"
  echo "sleep ${GAP}s"; sleep "$GAP"
done
echo "P2.2 rerun done ($(date))"
