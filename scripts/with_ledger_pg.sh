#!/usr/bin/env bash
# Run a command against the cryptoPnL ledger Postgres on omarchywin (docker, 127.0.0.1:5442, user cryptopnl). The password is read
# from the compose .env into PGPASSWORD of the child process only; it is never printed, logged or committed. No abra needed.
#   scripts/with_ledger_pg.sh scripts/p4_test.sh 8453 cryptopnl_p3_base cryptopnl_p4_base
set -euo pipefail
ENVF=${LEDGER_PG_ENV:-$HOME/dev/cryptopnl-ledger-pg/.env}
[ -r "$ENVF" ] || { echo "ledger PG env file not readable: $ENVF" >&2; exit 2; }
PGPASSWORD=$(sed -n 's/^POSTGRES_PASSWORD=//p' "$ENVF" | head -1 | sed 's/^"\(.*\)"$/\1/')
export PGPASSWORD PGHOST=${PGHOST:-127.0.0.1} PGPORT=${PGPORT:-5442} PGUSER=${PGUSER:-cryptopnl}
exec "$@"
