#!/usr/bin/env bash
# Run a command against the cryptoPnL ledger Postgres on omarchywin (docker, 127.0.0.1:5442, user cryptopnl) with PGPASSWORD set in
# the child's environment only; the value is never printed, logged or committed.
#   scripts/with_ledger_pg.sh scripts/p4_test.sh 8453 cryptopnl_p3_base cryptopnl_p4_base
# Source: abra by name ONLY -> `abra run -p $ABRA_PROJECT -k CRYPTOPNL_LEDGER_PG_PASSWORD` (architect, PR #8). No plaintext fallback.
# abra locked or the var missing -> exit 2 with a message. This script never unlocks abra and never creates or changes a var
# (user_default adds it: abra set cryptoPnL CRYPTOPNL_LEDGER_PG_PASSWORD).
set -euo pipefail
ABRA=${ABRA:-$HOME/.local/bin/abra}; ABRA_PROJECT=${ABRA_PROJECT:-cryptoPnL}; KEY=CRYPTOPNL_LEDGER_PG_PASSWORD
export PGHOST=${PGHOST:-127.0.0.1} PGPORT=${PGPORT:-5442} PGUSER=${PGUSER:-cryptopnl}
if [ "${1:-}" = "--from-abra" ]; then shift; PGPASSWORD=${CRYPTOPNL_LEDGER_PG_PASSWORD:-}; unset CRYPTOPNL_LEDGER_PG_PASSWORD
  [ -n "$PGPASSWORD" ] || { echo "with_ledger_pg: abra did not inject $KEY" >&2; exit 2; }; export PGPASSWORD; exec "$@"; fi
[ -x "$ABRA" ] || { echo "with_ledger_pg: abra not found at $ABRA; $KEY must come from abra project $ABRA_PROJECT" >&2; exit 2; }
if "$ABRA" unlock-status 2>&1 | grep -qi locked; then
  echo "with_ledger_pg: abra is locked; $KEY (abra project $ABRA_PROJECT) is needed. Not unlocking; stop." >&2; exit 2; fi
"$ABRA" ls "$ABRA_PROJECT" 2>/dev/null | grep -qw -- "$KEY" \
  || { echo "with_ledger_pg: $KEY missing in abra project $ABRA_PROJECT; user_default: abra set $ABRA_PROJECT $KEY" >&2; exit 2; }
exec "$ABRA" run -p "$ABRA_PROJECT" -k "$KEY" -- "$0" --from-abra "$@"
