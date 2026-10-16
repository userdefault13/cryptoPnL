import glob, os, psycopg
from .config import DSN
def connect(): return psycopg.connect(DSN, autocommit=False)
def migrate(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz DEFAULT now())")
    done = {r[0] for r in conn.execute("SELECT name FROM schema_migrations")}
    here = os.path.join(os.path.dirname(__file__), "..", "migrations")
    applied = []
    for f in sorted(glob.glob(os.path.join(here, "*.sql"))):
        n = os.path.basename(f)
        if n in done: continue
        conn.execute(open(f).read()); conn.execute("INSERT INTO schema_migrations(name) VALUES (%s)", (n,)); applied.append(n)
    conn.commit(); return applied
def b(h): return bytes.fromhex(h[2:])
def hx(v): return "0x" + bytes(v).hex()
