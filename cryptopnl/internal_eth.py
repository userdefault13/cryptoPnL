"""P4.1 rulings 1 (DESIGN §8): contract-internal ETH to and from the wallet, from traces. READ-ONLY on chain.
Same source as the P4.1 step 1 verification (docs/P4_1_SOURCES.md):
  1. expected native balance per block = the wallet's raw 'tx' rows only (value to/from the wallet, gas incl. L1 fee), no internal rows;
  2. RPC eth_getBalance probes at the blocks with a native delta (end of block b and b-1) and at the end block; the surplus
     S(b) = balance - expected changes only through internal transfers. A change between recorded blocks is narrowed by bisection,
     a balance held before the first recorded block by bisection over [0, first-1];
  3. debug_traceTransaction (callTracer) on the candidate txs: the wallet's txs in a changed block, else the block's txs that carry the
     wallet in calldata or pay it at top level (eth_getBlockByNumber), plus every wallet-sent EIP-7702 self-call (the only txs in which
     the wallet itself can send ETH internally). Every CALL / CREATE / SELFDESTRUCT frame below the top level with value, to or from the
     wallet, in a frame that did not revert, is one row;
  4. the residual is re-checked at every probe point with the rows included: it must be 0 to the wei (reported, never patched).
Rows: raw_event kind='internal_eth', log_index = n - 100000, n = the frame's depth-first position in the tx's trace (ordering:
  increasing in execution order, always below the gas leg -1 and the tx's logs);
payload = from, to, value, trace_address ('0.1.2'), call_type, tx_from, tx_to, selector, tx_index. Txs the wallet did not send also
get a block row (ts) and a tx_position row. Rate: the shared RPC limiter (30/min, 1.5 s gap) + a hard cap; every response is cached on
disk (CRYPTOPNL_RPC_CACHE, default logs/p4_1_cache; same keys as scripts/p4_1_trace.py), so a rerun repeats no request."""
import datetime, hashlib, json, os
from .config import CHAINS
from .db import b as hb
from .hostlimit import rpc_limiter
from .net import post_json

ROOT = os.path.join(os.path.dirname(__file__), "..")
LI0 = 100000   # internal legs: log_index = n - LI0 (DFS order preserved; P4.1 ruling 1)
VALUE_FRAMES = ("CALL", "CREATE", "CREATE2", "SELFDESTRUCT")   # DELEGATECALL/STATICCALL/CALLCODE move no ETH between accounts
def i(x): return None if x is None else (x if isinstance(x, int) else int(x, 16))

class Cap(Exception): pass
class RpcCache:
    """JSON-RPC through the host limiter, cached by request body (sha256 of ["rpc", body]). Errors are not cached."""
    def __init__(self, url, cap=370, cache_dir=None, log=None):
        self.url, self.cap, self.log = url, cap, log
        self.dir = cache_dir or os.environ.get("CRYPTOPNL_RPC_CACHE") or os.path.join(ROOT, "logs", "p4_1_cache"); os.makedirs(self.dir, exist_ok=True)
        self.n = {"requests": 0, "cached": 0, "errors": 0}
    def __call__(self, method, params):
        body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        k = hashlib.sha256(json.dumps(["rpc", body], sort_keys=True).encode()).hexdigest()[:24]; p = os.path.join(self.dir, f"rpc_{k}.json")
        if os.path.exists(p):
            self.n["cached"] += 1
            with open(p) as f: r = json.load(f)
        else:
            if self.n["requests"] >= self.cap: raise Cap(f"RPC cap {self.cap} reached")
            self.n["requests"] += 1; r = post_json("rpc", rpc_limiter(), self.url, body)
            if "error" in r: self.n["errors"] += 1; raise RuntimeError(f"rpc {method}: code {r['error'].get('code')}")
            with open(p + ".tmp", "w") as f: json.dump(r, f)
            os.replace(p + ".tmp", p)
        if "error" in r: raise RuntimeError(f"rpc {method}: code {r['error'].get('code')}")
        return r["result"]

def tx_delta(w, t):
    """Native balance change of the wallet from one raw 'tx' row, internal transfers excluded (wei). Mirrors classify.native_legs + gas."""
    ok = str(t.get("status")) != "0"; v = int(t.get("value") or 0); f, to = t.get("from"), t.get("to"); d = 0
    if v and f != to and ok: d += v if to == w else (-v if f == w else 0)
    if f == w: d -= int(t.get("fee") or 0)
    return d

def frames(w, tr):
    """Internal value frames to/from w of one callTracer result: [(n, trace_address, frame)] in depth-first order; reverted subtrees skipped (and not numbered)."""
    out = []; ctr = [0]
    def r(x, path):
        n = ctr[0]; ctr[0] += 1
        if x.get("error"): return
        if path and (x.get("type") or "").upper() in VALUE_FRAMES and i(x.get("value")):
            f, t = (x.get("from") or "").lower(), (x.get("to") or "").lower()
            if w in (f, t) and f != t: out.append((n, ".".join(map(str, path)), x))
        for k, y in enumerate(x.get("calls") or []): r(y, path + [k])
    if not tr.get("error"): r(tr, [])
    return out

def ingest_internal_eth(conn, chain, w, rpc, end_block=None, log=print):
    w = w.lower(); W40 = w[2:]
    txs = conn.execute("""SELECT block_number, '0x'||encode(tx_hash,'hex'), payload, '0x'||encode(block_hash,'hex') FROM raw_event
        WHERE chain_id=%s AND kind='tx' AND (payload->>'from'=%s OR payload->>'to'=%s) ORDER BY block_number, log_index""", (chain, w, w)).fetchall()
    byb, run, E = {}, 0, {}
    for bn, h, p, bh in txs:
        d = tx_delta(w, p)
        byb.setdefault(bn, []).append((h, p, bh))
        if d: run += d; E[bn] = run
    blocks = sorted(E)
    if not blocks: return {"rows": 0, "note": "no native flows"}
    end = end_block or max(byb)
    pts = [blocks[0] - 1] + blocks + ([end] if end > blocks[-1] else [])
    import bisect
    def exp(b):
        k = bisect.bisect_right(blocks, b); return E[blocks[k - 1]] if k else 0
    bal = {}
    def B(b):
        if b not in bal: bal[b] = i(rpc("eth_getBalance", [w, hex(b)]))
        return bal[b]
    S = lambda b: B(b) - exp(b)
    changes = []
    def between(lo, hi):
        while hi - lo > 1:
            m = (lo + hi) // 2
            if S(m) != S(lo): hi = m
            else: lo = m
        changes.append(("between", hi))
    def walk(a, c):
        if S(pts[a]) == S(pts[c]): return
        if c == a + 1:
            lo, b = pts[a], pts[c]
            if b - 1 > lo and S(b - 1) != S(lo): between(lo, b - 1)
            if (S(b) - S(b - 1) if b - 1 > lo else S(b) - S(lo)): changes.append(("in_block" if b in byb else "between", b))
            return
        m = (a + c) // 2; walk(a, m); walk(m, c)
    early = []
    def seg(lo, hi):   # balance held before the first native row: expected = 0 there
        if B(lo) == B(hi): return
        if hi - lo == 1: early.append(hi); return
        m = (lo + hi) // 2; seg(lo, m); seg(m, hi)
    if S(pts[0]): seg(0, pts[0])
    walk(0, len(pts) - 1)
    changes = [("between", b) for b in early] + sorted(set(changes), key=lambda x: x[1])
    blk_cache = {}
    def block(b):
        if b not in blk_cache: blk_cache[b] = rpc("eth_getBlockByNumber", [hex(b), True])
        return blk_cache[b]
    found = {}   # tx -> dict(block, tx_from, tx_to, selector, tx_index, block_hash, frames)
    def trace(h, bn, bh, tx_index=None):
        if h in found: return found[h]
        tr = rpc("debug_traceTransaction", [h, {"tracer": "callTracer"}])
        fr = frames(w, tr)
        found[h] = {"block": bn, "tx_from": (tr.get("from") or "").lower(), "tx_to": (tr.get("to") or "").lower(),
                    "selector": (tr.get("input") or "0x")[:10], "tx_index": tx_index, "block_hash": bh, "frames": fr}
        return found[h]
    net = lambda f: sum((i(x["value"]) if (x.get("to") or "").lower() == w else -i(x["value"])) for _, _, x in f["frames"])
    unexplained = []
    for kind, bn in changes:
        want = (S(bn) - S(bn - 1))
        got = 0
        for h, p, bh in byb.get(bn, []): got += net(trace(h, bn, bh))
        if got != want:
            blk = block(bn)
            for t in blk["transactions"]:
                h = t["hash"]
                if h in found or not ((t.get("to") or "").lower() == w or W40 in (t.get("input") or "").lower()): continue
                got += net(trace(h, bn, blk["hash"], i(t.get("transactionIndex"))))
        if got != want: unexplained.append({"block": bn, "kind": kind, "surplus_delta_wei": want, "traced_net_wei": got})
    for bn, lst in byb.items():   # every wallet-sent EIP-7702 self-call (wallet code runs: internal sends possible)
        for h, p, bh in lst:
            if p.get("from") == w and p.get("to") == w and (p.get("selector") or "0x") != "0x": trace(h, bn, bh)
    # store (idempotent): replace this wallet's internal rows
    conn.execute("DELETE FROM raw_event WHERE chain_id=%s AND kind='internal_eth' AND (payload->>'from'=%s OR payload->>'to'=%s)", (chain, w, w))
    rows = 0; own = {h for lst in byb.values() for h, _, _ in lst}
    for h, f in sorted(found.items(), key=lambda kv: (kv[1]["block"], kv[0])):
        for n, ta, x in f["frames"]:
            pl = {"from": (x.get("from") or "").lower(), "to": (x.get("to") or "").lower(), "value": str(i(x["value"])), "trace_address": ta,
                  "call_type": (x.get("type") or "").upper(), "tx_from": f["tx_from"], "tx_to": f["tx_to"], "selector": f["selector"],
                  "tx_index": f["tx_index"]}
            conn.execute("""INSERT INTO raw_event(chain_id,tx_hash,log_index,block_number,block_hash,source,kind,payload)
                VALUES (%s,%s,%s,%s,%s,'rpc_trace','internal_eth',%s)""", (chain, hb(h), n - LI0, f["block"], hb(f["block_hash"]), json.dumps(pl)))
            rows += 1
        if f["frames"] and h not in own:   # a tx the wallet did not send: block ts + position for ordering
            blk = block(f["block"]); ts = datetime.datetime.fromtimestamp(i(blk["timestamp"]), datetime.timezone.utc)
            conn.execute("INSERT INTO block(chain_id,number,hash,ts) VALUES (%s,%s,%s,%s) ON CONFLICT (chain_id,number) DO NOTHING",
                         (chain, f["block"], hb(blk["hash"]), ts))
            if f["tx_index"] is not None:
                conn.execute("""INSERT INTO tx_position(chain_id,tx_hash,block_number,tx_index) VALUES (%s,%s,%s,%s)
                    ON CONFLICT DO NOTHING""", (chain, hb(h), f["block"], f["tx_index"]))
    # residual with the rows included, at every probe point (cached balances: no new request)
    I = {}
    for h, f in found.items():
        I[f["block"]] = I.get(f["block"], 0) + net(f)
    ib = sorted(I); acc = 0; IC = {}
    for b in ib: acc += I[b]; IC[b] = acc
    def inc(b):
        k = bisect.bisect_right(ib, b); return IC[ib[k - 1]] if k else 0
    resid = {b: B(b) - exp(b) - inc(b) for b in sorted(bal)}
    bad = {b: r for b, r in resid.items() if r}
    conn.commit()
    out = {"chain": chain, "wallet": w, "end_block": end, "probe_points": len(bal), "changes": len(changes), "traced_txs": len(found),
           "rows": rows, "rows_in": sum(1 for f in found.values() for _, _, x in f["frames"] if (x.get("to") or "").lower() == w),
           "internal_net_wei": str(sum(I.values())), "unexplained": unexplained, "residual_nonzero_points": len(bad),
           "residual_first": [[b, str(r)] for b, r in list(bad.items())[:5]], "rpc": dict(rpc.n)}
    log(json.dumps(out)); return out

def main(argv=None):
    import argparse
    from . import db
    ap = argparse.ArgumentParser(prog="cryptopnl.internal_eth"); ap.add_argument("--chain", type=int, required=True)
    ap.add_argument("--wallet", required=True); ap.add_argument("--end-block", type=int); ap.add_argument("--cap", type=int, default=370)
    ap.add_argument("--out")
    a = ap.parse_args(argv); conn = db.connect()
    r = ingest_internal_eth(conn, a.chain, a.wallet, RpcCache(CHAINS[a.chain]["rpc"], a.cap), a.end_block)
    if a.out:
        with open(a.out, "w") as f: json.dump(r, f, indent=1, sort_keys=True)
    return 1 if (r.get("unexplained") or r.get("residual_nonzero_points")) else 0

if __name__ == "__main__":
    import sys; sys.exit(main())
