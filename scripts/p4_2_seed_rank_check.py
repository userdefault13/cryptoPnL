"""P4.2 (architect nit, pricing.py seed): read-only, 0 RPC. Does seeding by price-order rank (Pricer.seed now) pick a different stored
point than the old rule (the highest price_point id) for any (asset, block)? Compares both choices over pricing.stored_points() and
counts the ledger rows priced from a point the new rule would not pick (ledger_entry.price_id). Any difference is a CHANGE, not a pass.
Nothing is written: the session is read-only and rolled back.
  scripts/with_ledger_pg.sh env CRYPTOPNL_DSN="dbname=cryptopnl_p41_base" .venv/bin/python scripts/p4_2_seed_rank_check.py 8453 [--out PATH]"""
import collections, json, sys
sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__file__), ".."))
from cryptopnl import db, pricing

def check(conn, chain):
    pts = pricing.stored_points(conn, chain)          # ORDER BY price_point.id
    ids = [r[0] for r in conn.execute("SELECT p.id FROM price_point p WHERE p.chain_id=%s AND p.source <> 'trade' ORDER BY p.id", (chain,))]
    assert len(ids) == len(pts)
    pr = pricing.Pricer(chain, None); old, new = {}, {}
    for pid, (c, b, p) in zip(ids, pts):
        k = (pr.weth if c is None else c.lower(), b); old[k] = (pid, p)          # old rule: the last (highest id) wins
        r = (pr.seed_rank(k[0], p), pid)
        if k not in new or r < new[k][0]: new[k] = (r, pid, p)
    n = collections.Counter((pr.weth if c is None else c.lower(), b) for c, b, _ in pts); multi = sum(1 for v in n.values() if v > 1)
    diff = [{"asset": k[0], "block": k[1], "old": {"id": old[k][0], "source": old[k][1].source, "price": str(old[k][1].price)},
             "new": {"id": new[k][1], "source": new[k][2].source, "price": str(new[k][2].price)}}
            for k in sorted(old) if old[k][0] != new[k][1]]
    moved = [d["old"]["id"] for d in diff]
    rows = conn.execute("SELECT count(*) FROM ledger_entry WHERE chain_id=%s AND price_id = ANY(%s)", (chain, moved)).fetchone()[0] if moved else 0
    same_price = sum(1 for d in diff if d["old"]["price"] == d["new"]["price"])
    return {"chain_id": chain, "stored_points": len(pts), "asset_blocks": len(old), "asset_blocks_with_several_points": multi,
            "choice_changed": len(diff), "choice_changed_same_price": same_price, "ledger_rows_on_a_changed_choice": rows,
            "verdict": "no change" if not diff else "CHANGE", "changes": diff}

if __name__ == "__main__":
    chain = int(sys.argv[1]); out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
    conn = db.connect(); conn.execute("SET TRANSACTION READ ONLY")
    try: r = check(conn, chain)
    finally: conn.rollback()
    s = json.dumps(r, indent=1, sort_keys=True) + "\n"
    if out: open(out, "w").write(s)
    print(json.dumps({k: v for k, v in r.items() if k != "changes"}))
