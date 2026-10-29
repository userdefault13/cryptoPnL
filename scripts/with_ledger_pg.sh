#!/usr/bin/env bash
# Run a command against the cryptoPnL ledger Postgres on omarchywin (docker, 127.0.0.1:5442, user cryptopnl) with PGPASSWORD set in
# the child's environment only; the value is never printed, logged or committed.
#   scripts/with_ledger_pg.sh scripts/p4_test.sh 8453 cryptopnl_p3_base cryptopnl_p4_base
# Source (in order): abra by name -> `abra run -p $ABRA_PROJECT -k $ABRA_KEY` (default cryptoPnL / CRYPTOPNL_LEDGER_PG_PASSWORD),
# when abra is unlocked and that var exists; else the fallback, POSTGRES_PASSWORD in the compose .env ($LEDGER_PG_ENV).
# This script never unlocks abra and never creates or changes an abra var (user_default adds it: abra set cryptoPnL CRYPTOPNL_LEDGER_PG_PASSWORD).
set -euo pipefail
ABRA=${ABRA:-$HOME/.local/bin/abra}; ABRA_PROJECT=${ABRA_PROJECT:-cryptoPnL}; ABRA_KEY=${ABRA_KEY:-CRYPTOPNL_LEDGER_PG_PASSWORD}
export PGHOST=${PGHOST:-127.0.0.1} PGPORT=${PGPORT:-5442} PGUSER=${PGUSER:-cryptopnl}
if [ "${1:-}" = "--from-abra" ]; then shift; PGPASSWORD=${!ABRA_KEY:-}; unset "$ABRA_KEY"
  [ -n "$PGPASSWORD" ] || { echo "abra did not inject $ABRA_KEY" >&2; exit 2; }; export PGPASSWORD; exec "$@"; fi
if [ -x "$ABRA" ] && ! "$ABRA" unlock-status 2>&1 | grep -qi locked \
   && "$ABRA" ls "$ABRA_PROJECT" 2>/dev/null | grep -qw -- "$ABRA_KEY"; then
  echo "ledger PG password: abra $ABRA_PROJECT/$ABRA_KEY" >&2
  exec "$ABRA" run -p "$ABRA_PROJECT" -k "$ABRA_KEY" -- "$0" --from-abra "$@"
fi
ENVF=${LEDGER_PG_ENV:-$HOME/dev/cryptopnl-ledger-pg/.env}
echo "ledger PG password: fallback $ENVF (abra $ABRA_PROJECT/$ABRA_KEY unavailable: locked or not set)" >&2
[ -r "$ENVF" ] || { echo "ledger PG env file not readable: $ENVF" >&2; exit 2; }
PGPASSWORD=$(sed -n 's/^POSTGRES_PASSWORD=//p' "$ENVF" | head -1 | sed 's/^"\(.*\)"$/\1/')
export PGPASSWORD; exec "$@"
