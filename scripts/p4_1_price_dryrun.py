"""P4.1 RF pricing: 0-RPC dry count of the requests a live `cryptopnl price --reuse-stored` pass would send (architect ruling on PR #9).
Runs the REAL pricing.price_ledger, seeded from the stored price_point exactly as --reuse-stored does, with a network-free RPC that only
records each eth_call (to, selector, block) and answers by scenario. NOTHING IS SENT, NOTHING IS COMMITTED: the transaction is rolled back,
and the synthetic answers only steer branches (pool deployed or not; never stored, never reported as prices). Read-write is refused
unless the DB is a scratch copy (dbname cryptopnl_p41_pricecount).
Pool state per block is the only input the count depends on. It comes from the stored GHST points' recorded paths (detail.pool,
skipped_pools 'empty'): P1 0x41d4… returned empty up to 43748241 and was used from 51156732; P2 0x56c1… was empty at 34202337 and used
from 37488911. Blocks between those points are unknown offline, so two scenarios bracket them: 'low' = the pool existed right after its
last empty point, 'high' = only from its first used point. Liquidity floor: never hit in any stored point (P2 quote side >= $330k);
assumed not hit. Usage: CRYPTOPNL_DSN=dbname=cryptopnl_p41_pricecount python scripts/p4_1_price_dryrun.py 8453"""
import collections, json, sys
sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__file__), ".."))
from cryptopnl import db, pricing

P1, P2 = "0x41d4934322f2bd6fe1dbe4124070fe61651a2067", "0x56c11053159a24c0731b4b12356bc1f0578fb474"
SCEN = {"low": {P1: 43748242, P2: 34202338}, "high": {P1: 51156732, P2: 37488911}}   # first block the pool answers
W = lambda *v: "0x" + "".join(format(x, "064x") for x in v)

class DryRPC:
    def __init__(self, live_from): self.live_from = live_from; self.calls = []
    def eth_call(self, to, data, block):
        self.calls.append((to, data[:10], block))
        if to in self.live_from and block < self.live_from[to]: return "0x"      # pool not deployed yet: empty, as recorded
        if data.startswith("0x3850c7bd"): return W(2 ** 96, 0, 0, 0, 0, 0, 1)    # slot0 (branch steering only)
        if data.startswith("0x0902f1ac"): return W(10 ** 30, 10 ** 30, 0)        # getReserves
        if data.startswith("0x70a08231"): return W(10 ** 40)                     # balanceOf: above the floor
        raise SystemExit(f"unexpected call {data[:10]}")
    def call(self, method, params): raise SystemExit(f"unexpected {method}")     # getCode etc.: not on the price_ledger path

def run(chain, scen):
    conn = db.connect(); name = conn.info.dbname
    if name != "cryptopnl_p41_pricecount": raise SystemExit(f"refusing: {name} is not the scratch copy")
    rpc = DryRPC(SCEN[scen]); pr = pricing.Pricer(chain, rpc, None, swaps=pricing.load_swaps(conn, chain))
    pr.seed(pricing.stored_points(conn, chain))
    miss = conn.execute("""SELECT block_number, coalesce(income_subtype, category) FROM ledger_entry WHERE chain_id=%s AND price_flag='no_price'""", (chain,)).fetchall()
    kind = {}
    for b, k in miss: kind[b] = "rf" if k == "rarity_farming_payout" else kind.get(b, "swap")
    conn.commit = lambda: None
    try: st = pricing.price_ledger(conn, chain, pr, log=lambda *a: None)
    finally: conn.rollback()
    by = collections.Counter(kind.get(b, "other") for _, _, b in rpc.calls)
    per = collections.Counter(); [per.update({b: 1}) for _, _, b in rpc.calls]
    rfb = [b for b, k in kind.items() if k == "rf"]
    return {"scenario": scen, "requests": len(rpc.calls), "by_kind": dict(by), "rf_blocks": len(rfb),
            "rf_calls_per_block": dict(collections.Counter(per[b] for b in rfb)), "seed_hits": pr.seed_hits,
            "selectors": dict(collections.Counter(s for _, s, _ in rpc.calls)), "pricer_calls": pr.calls,
            "rf_priced_in_dry_run": None}

if __name__ == "__main__":
    out = [run(int(sys.argv[1]), s) for s in ("low", "high")]
    print(json.dumps(out, indent=1))
