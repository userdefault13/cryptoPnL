import argparse, json, sys
from . import db, ingest, verify, classify, pricing, evidence
from .net import STATS
p = argparse.ArgumentParser(prog="cryptopnl")
p.add_argument("cmd", choices=["migrate", "ingest", "counts", "verify", "verify-wearables", "simulate-reorg", "classify", "classify-report", "lots", "set-basis", "tx-index", "pool-swaps", "price", "price-report", "price-sample", "ledger-md5", "marks", "pockets"])
p.add_argument("--untouched-txs-from-db", help="ledger-md5: read the internal-ETH tx list from this database (same connection settings)")
p.add_argument("--reuse-stored", action="store_true"); p.add_argument("--seed-only", action="store_true"); p.add_argument("--as-of", type=int)
p.add_argument("--chain", type=int, default=84532)
p.add_argument("--evidence", help="pockets: evidence JSON (default config.POCKETS[chain]['evidence'])"); p.add_argument("--to-block", type=int)
p.add_argument("--wallet", action="append", default=[])
p.add_argument("--samples", type=int, default=20); p.add_argument("--seed", type=int, default=3)
p.add_argument("--out"); p.add_argument("--lot", type=int); p.add_argument("--basis-usdc"); p.add_argument("--acquired-at")
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
elif a.cmd == "pockets":   # P4.1 rule 7: pocket legs, escrows and rentals from the read-only evidence file (no network)
    import os
    from .pockets import ingest_pockets
    from .config import POCKETS
    ingest_pockets(conn, a.chain, a.evidence or os.path.join(os.path.dirname(__file__), "..", POCKETS[a.chain]["evidence"]), a.to_block)
elif a.cmd == "tx-index": ingest.ingest_tx_index(conn, a.chain)   # RPC only
elif a.cmd == "pool-swaps": ingest.ingest_pool_swaps(conn, a.chain)   # HyperSync (shared 5/min + 12 s bucket): Swap logs of thin pools
elif a.cmd == "marks":   # P4 rulings 4: a mark per held asset at as_of_block (default: the last ledger block)
    from .sources import RPC
    from .config import CHAINS
    pr = pricing.Pricer(a.chain, RPC(CHAINS[a.chain]["rpc"]), pricing.DefiLlama(), swaps=pricing.load_swaps(conn, a.chain))
    if a.reuse_stored: pr.seed(pricing.stored_points(conn, a.chain))
    asof = a.as_of or conn.execute("SELECT max(block_number) FROM ledger_entry WHERE chain_id=%s", (a.chain,)).fetchone()[0]
    r = pricing.write_marks(conn, a.chain, pr, asof); r["seed_hits"] = getattr(pr, "seed_hits", 0)
    if a.out:
        with open(a.out, "w") as f: json.dump(r, f, indent=1, sort_keys=True)
    print(json.dumps(r))
elif a.cmd in ("price", "price-sample"):
    from .sources import RPC
    from .config import CHAINS
    pr = pricing.Pricer(a.chain, RPC(CHAINS[a.chain]["rpc"]), pricing.DefiLlama(), swaps=pricing.load_swaps(conn, a.chain))
    if a.reuse_stored or a.seed_only: pr.seed(pricing.stored_points(conn, a.chain))   # P4.1: stored points first, RPC only for new (asset, block)
    pr.seed_only = a.seed_only   # non-canonical test: unseeded legs stay unpriced (no_price), no RPC
    if a.cmd == "price":
        st = pricing.price_ledger(conn, a.chain, pr); st["seed_hits"] = getattr(pr, "seed_hits", 0); st["seed_misses"] = getattr(pr, "seed_misses", 0)
        if a.out:
            with open(a.out, "w") as f: json.dump(st, f, indent=1, sort_keys=True, default=str)
        print(json.dumps(pricing.coverage(conn, a.chain), default=str))
    else:
        r = pricing.sample(conn, a.chain, pr, a.samples, a.seed)
        g = pricing.gltr_probe(conn, a.chain, pr, 5, a.seed, min_block=r["sample_start_block"])
        rc = 0 if r["pass_c1"] and r["pass_dex_vs_api_3pct"] and g["pass"] else 1
elif a.cmd == "price-report":
    r = pricing.coverage(conn, a.chain); print(json.dumps(r, default=str)); rc = 0 if r["pass"] else 1
    if not r["pass"]: print("PRICE-REPORT FAIL: " + "; ".join(r["failures"]), file=sys.stderr); print(json.dumps({"price_report_fail": r["failures"]}))
elif a.cmd == "ledger-md5":   # P3 follow-up (c): ledger md5 evidence file (default docs/evidence/p4_ledger_md5_<chain>.txt)
    txs, src = None, "self"
    if a.untouched_txs_from_db:   # e.g. hash the pre-P4.1 ledger over the rows the P4.1 ledger did not touch
        import psycopg
        with psycopg.connect(psycopg.conninfo.make_conninfo(db.DSN, dbname=a.untouched_txs_from_db)) as o: txs = evidence.touched_txs(o, a.chain)
        src = a.untouched_txs_from_db
    print(json.dumps(evidence.write_ledger_md5(conn, a.chain, a.out or f"docs/evidence/p4_ledger_md5_{a.chain}.txt", txs, src)))
print("STATS " + json.dumps(STATS), file=sys.stderr); sys.exit(rc)
