"""P4.1 step 1 (a) follow-up, READ-ONLY: (1) the two ETH surplus changes in blocks with no wallet-sent tx: full block tx list, txs
paying the wallet at top level or carrying the wallet in calldata, traced; (2) where the 0.004916 ETH held at block 12795075 arrived
(no recorded ETH row before it): balance bisection over [0, 12795075] (budget 70 probes)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__)); import p4_1_trace as T
W = T.W; w40 = W[2:]
def trace_hits(h):
    tr = T.rpc("debug_traceTransaction", [h, {"tracer": "callTracer"}]); hits = []
    def r(x, path):
        if (x.get("to") or "").lower() == W and T.i(x.get("value")) and not x.get("error"):
            hits.append({"from": (x.get("from") or "").lower(), "value_wei": T.i(x["value"]), "type": x.get("type"), "depth": len(path), "path": path})
        for y in x.get("calls") or []: r(y, path + [(x.get("to") or "").lower()])
    r(tr, []); return {"tx": h, "tx_from": tr["from"].lower(), "tx_to": (tr.get("to") or "").lower(), "selector": (tr.get("input") or "")[:10], "inflows": hits}
out = {"between": [], "early": {}}
for b in (23210972, 46860859):
    blk = T.rpc("eth_getBlockByNumber", [hex(b), True]); c = []
    for t in blk["transactions"]:
        if (t.get("to") or "").lower() == W or w40 in (t.get("input") or "").lower(): c.append(t["hash"])
    out["between"].append({"block": b, "txs_in_block": len(blk["transactions"]), "candidates": [trace_hits(h) for h in c[:6]], "n_candidates": len(c)})
# early bisection
S = {}; used = [0]
def bal(b):
    if b not in S:
        if used[0] >= 70: raise T.Cap("early probe budget 70")
        used[0] += 1; S[b] = T.bal(b)
    return S[b]
ch = []
def seg(lo, hi):
    if bal(lo) == bal(hi): return
    if hi - lo == 1: ch.append({"block": hi, "delta_wei": bal(hi) - bal(lo)}); return
    m = (lo + hi) // 2; seg(lo, m); seg(m, hi)
try: seg(0, 12795075)
except T.Cap as e: out["early"]["note"] = str(e)
out["early"].update({"changes": ch, "probes": len(S), "balance_12795075_wei": S.get(12795075)})
for c in ch[:4]:
    blk = T.rpc("eth_getBlockByNumber", [hex(c["block"]), True])
    c["txs_paying_wallet_top_level"] = [{"tx": t["hash"], "from": t["from"].lower(), "value_wei": T.i(t["value"]), "type": t.get("type")} for t in blk["transactions"] if (t.get("to") or "").lower() == W]
    c["txs_with_wallet_in_calldata"] = [t["hash"] for t in blk["transactions"] if w40 in (t.get("input") or "").lower()][:5]
T._w("p4_1_eth_extra.json", out); print(json.dumps(out, default=str)[:3000]); print(T.N)
