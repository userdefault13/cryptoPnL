#!/usr/bin/env bash
# P4 migrations 013 + 014 up/down/up on a LOCAL scratch Postgres (never the ledger PG on omarchywin, never Envio 5439/5440).
#   PGHOST=/tmp scripts/p4_migration_test.sh            (MBP: Homebrew postgresql@16 on /tmp:5432)
# 1) fresh DB A: migrate 001..014 -> S_up; 014_down -> S_down14; 013_down -> S_down; migrate again -> S_up2. PASS needs S_up == S_up2.
# 2) fresh DB B: 001..012 only (psql -f) -> S_012; fresh DB D: 001..013 -> S_013. PASS needs S_down == S_012 and S_down14 == S_013.
# 3) tests/test_p4_migration.py against DB A (constraints, manual_basis survives a ledger_entry delete, RESTRICT).
set -euo pipefail
cd "$(dirname "$0")/.."; PY=${PY:-.venv/bin/python}; A=${P4_DB_A:-cryptopnl_p4_migtest}; B=${P4_DB_B:-cryptopnl_p4_migtest_012}; D=${P4_DB_D:-cryptopnl_p4_migtest_013}
T=$(mktemp -d); dump() { pg_dump -s --no-owner --no-privileges -d "$1" | grep -v '^--' | grep -v '^$' | grep -v 'schema_migrations' | grep -v '^.restrict ' | grep -v '^.unrestrict ' || true; }
for d in "$A" "$B" "$D"; do dropdb --if-exists "$d"; createdb "$d"; done
CRYPTOPNL_DSN="dbname=$A" $PY -m cryptopnl migrate 2>/dev/null | tail -1
dump "$A" > "$T/up"
psql -q -X -v ON_ERROR_STOP=1 -d "$A" -f migrations/rollback/014_down.sql
psql -q -X -v ON_ERROR_STOP=1 -d "$A" -c "DELETE FROM schema_migrations WHERE name='014_p4_rulings3.sql'"
dump "$A" > "$T/down14"
psql -q -X -v ON_ERROR_STOP=1 -d "$A" -f migrations/rollback/013_down.sql
psql -q -X -v ON_ERROR_STOP=1 -d "$A" -c "DELETE FROM schema_migrations WHERE name='013_p4_fifo.sql'"
dump "$A" > "$T/down"
CRYPTOPNL_DSN="dbname=$A" $PY -m cryptopnl migrate 2>/dev/null | tail -1
dump "$A" > "$T/up2"
psql -q -X -v ON_ERROR_STOP=1 -d "$B" -c "CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz DEFAULT now())"
for f in migrations/0*.sql; do case "$f" in *013_*|*014_*) continue;; esac; psql -q -X -v ON_ERROR_STOP=1 -d "$B" -f "$f" >/dev/null; done
dump "$B" > "$T/m012"
psql -q -X -v ON_ERROR_STOP=1 -d "$D" -c "CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz DEFAULT now())"
for f in migrations/0*.sql; do case "$f" in *014_*) continue;; esac; psql -q -X -v ON_ERROR_STOP=1 -d "$D" -f "$f" >/dev/null; done
dump "$D" > "$T/m013"
rc=0
if cmp -s "$T/up" "$T/up2"; then echo "up == up2: OK ($(wc -l < "$T/up") schema lines, md5 $($PY -c "import hashlib,sys;print(hashlib.md5(open(sys.argv[1],'rb').read()).hexdigest())" "$T/up"))"; else echo "FAIL: up != up2"; { diff "$T/up" "$T/up2" || true; } | head -20; rc=1; fi
if cmp -s "$T/down" "$T/m012"; then echo "down == 001..012: OK ($(wc -l < "$T/down") schema lines)"; else echo "FAIL: down != 001..012"; { diff "$T/down" "$T/m012" || true; } | head -20; rc=1; fi
if cmp -s "$T/down14" "$T/m013"; then echo "014 down == 001..013: OK ($(wc -l < "$T/down14") schema lines)"; else echo "FAIL: 014 down != 001..013"; { diff "$T/down14" "$T/m013" || true; } | head -20; rc=1; fi
if cmp -s "$T/up" "$T/down14" || cmp -s "$T/down14" "$T/down"; then echo "FAIL: 013 or 014 changed nothing"; rc=1; fi
P4_MIGTEST_DSN="dbname=$A" $PY -m unittest tests.test_p4_migration -v 2>&1 | tail -12 || rc=1
P4_MIGTEST_DSN="dbname=$A" $PY -m unittest tests.test_p4_migration >/dev/null 2>&1 || rc=1
for d in "$A" "$B" "$D"; do dropdb --if-exists "$d"; done; rm -rf "$T"
[ $rc -eq 0 ] && echo "P4 MIGRATIONS 013+014 PASS (up/down/up)" || { echo "P4 MIGRATIONS 013+014 FAIL"; exit 1; }
