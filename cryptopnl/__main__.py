import argparse, json, sys
from . import db, ingest, verify
from .net import STATS
p = argparse.ArgumentParser(prog="cryptopnl")
p.add_argument("cmd", choices=["migrate", "ingest", "counts", "verify", "simulate-reorg"])
p.add_argument("--chain", type=int, default=84532)
p.add_argument("--wallet", action="append", default=[])
a = p.parse_args(); conn = db.connect(); rc = 0
if a.cmd == "migrate": print(json.dumps({"applied": db.migrate(conn)}))
elif a.cmd == "ingest":
    for w in a.wallet: ingest.ingest_wallet(conn, a.chain, w)
    ingest.ingest_marketplace(conn, a.chain)
elif a.cmd == "counts": print(json.dumps(ingest.counts(conn, a.chain)))
elif a.cmd == "verify":
    t, ok, f = verify.verify(conn, a.chain); rc = 0 if t and not f else 1
elif a.cmd == "simulate-reorg": print(json.dumps({"tampered_blocks": ingest.simulate_reorg(conn, a.chain)}))
print("STATS " + json.dumps(STATS), file=sys.stderr); sys.exit(rc)
