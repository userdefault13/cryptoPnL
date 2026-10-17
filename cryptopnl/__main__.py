import argparse, json, sys
from . import db, ingest, verify, classify
from .net import STATS
p = argparse.ArgumentParser(prog="cryptopnl")
p.add_argument("cmd", choices=["migrate", "ingest", "counts", "verify", "verify-wearables", "simulate-reorg", "classify", "classify-report", "lots", "set-basis"])
p.add_argument("--chain", type=int, default=84532)
p.add_argument("--wallet", action="append", default=[])
p.add_argument("--lot", type=int); p.add_argument("--basis-usdc"); p.add_argument("--acquired-at")
a = p.parse_args(); conn = db.connect(); rc = 0
if a.cmd == "migrate": print(json.dumps({"applied": db.migrate(conn)}))
elif a.cmd == "ingest":
    for w in a.wallet: ingest.ingest_wallet(conn, a.chain, w)
    for w in a.wallet: ingest.ingest_wallet_txs(conn, a.chain, w)
    for w in a.wallet: ingest.ingest_parent_transfers(conn, a.chain, w)
    ingest.ingest_marketplace(conn, a.chain)
    for w in a.wallet: ingest.ingest_gv(conn, a.chain, w)        # P2.2 Gotchiverse logs (HyperSync, host lock)
    for w in a.wallet: ingest.ingest_tx_meta(conn, a.chain, w)   # RPC only
elif a.cmd == "counts": print(json.dumps(ingest.counts(conn, a.chain)))
elif a.cmd == "verify":
    t, ok, f = verify.verify(conn, a.chain); rc = 1 if f else (3 if t == 0 else 0)
elif a.cmd == "verify-wearables":
    t, ok, f = verify.verify_wearables(conn, a.chain); rc = 1 if f else (3 if t == 0 else 0)
elif a.cmd == "simulate-reorg": print(json.dumps({"tampered_blocks": ingest.simulate_reorg(conn, a.chain)}))
elif a.cmd == "classify": classify.classify(conn, a.chain); print(json.dumps(classify.checksum(conn, a.chain)))
elif a.cmd == "classify-report":
    r = classify.report(conn, a.chain); print(json.dumps(r, indent=1))
    rc = 0 if r["pass_98"] else 1
elif a.cmd == "lots":   # migration lots + basis status (pending = unknown basis, excluded from PnL totals)
    for r in conn.execute("""SELECT f.id, encode(l.tx_hash,'hex'), l.log_index, '0x'||encode(s.contract,'hex'), s.token_id, f.qty_remaining,
        f.basis_status, f.basis_usdc, f.basis_price_source, f.chain_origin FROM fifo_lot f JOIN ledger_entry l ON l.id=f.open_entry_id
        JOIN asset s ON s.id=f.asset_id WHERE l.chain_id=%s ORDER BY f.id""", (a.chain,)):
        print(json.dumps([str(x) if x is not None else None for x in r]))
elif a.cmd == "set-basis":   # user_default's manual basis: price_source=manual, confidence low (DESIGN §8)
    if a.lot is None or a.basis_usdc is None: sys.exit("set-basis: --lot and --basis-usdc are required")
    try: classify.set_manual_basis(conn, a.lot, a.basis_usdc, a.acquired_at)
    except ValueError as e: sys.exit(f"set-basis: {e}")
    print(json.dumps({"lot": a.lot, "basis_status": "manual"}))
print("STATS " + json.dumps(STATS), file=sys.stderr); sys.exit(rc)
