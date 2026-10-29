"""P4.1 step 1, keyless fallback (HyperSync 403; docs/P4_1_PLAN.md 'Step 1 revision'). READ-ONLY. RPC base.drpc.org through the host
limiter (30/min, 1.5 s gap) and the free public Blockscout API (candidate lists only; pacing 1 req / 2 s; cap 10). Every inflow is
confirmed by RPC debug_traceTransaction (ETH) or eth_getLogs / receipts (GHST). Cached in logs/p4_1_cache/.
  env NET_REQLOG=logs/p4_1_reqlog.txt .venv/bin/python scripts/p4_1_trace_rpc.py [ghst|eth|all]"""
import json, os, sys, urllib.parse
sys.path.insert(0, os.path.dirname(__file__))
import p4_1_trace as T
from cryptopnl.net import post_json, Limiter

BS = "https://base.blockscout.com/api"; BS_CAP = 30; T.N["blockscout"] = 0; T.N["blockscout_cached"] = 0
_bl = Limiter(0.5, 1)
def bs(params):
    url = BS + "?" + urllib.parse.urlencode(params)
    def go():
        if T.N["blockscout"] >= BS_CAP: raise T.Cap("blockscout cap reached")
        return post_json("blockscout", _bl, url, None)
    k = dict(params, _u=BS)
    return T._cached("blockscout", k, lambda: post_json("blockscout", _bl, url, None)) if T.N["blockscout"] < BS_CAP or True else None
_orig = T._cached
def _cached(kind, body, fn):
    if kind == "blockscout":
        import hashlib
        k = hashlib.sha256(json.dumps([kind, body], sort_keys=True).encode()).hexdigest()[:24]; p = os.path.join(T.CACHE, f"{kind}_{k}.json")
        if os.path.exists(p):
            T.N["blockscout_cached"] += 1
            with open(p) as f: return json.load(f)
        if T.N["blockscout"] >= BS_CAP: raise T.Cap("blockscout cap reached")
        T.N["blockscout"] += 1; r = fn()
        with open(p, "w") as f: json.dump(r, f)
        return r
    return _orig(kind, body, fn)
T._cached = _cached
i, W, GHST, TRANSFER, LAST = T.i, T.W, T.GHST, T.TRANSFER, T.LAST

def logs_range(flt, lo, hi, depth=0):
    """eth_getLogs over [lo, hi]; on a range/size error split in two (capped by the RPC cap)."""
    try: return T.rpc("eth_getLogs", [{**flt, "fromBlock": hex(lo), "toBlock": hex(hi)}])
    except RuntimeError as e:
        if hi - lo < 1000 or depth > 14: raise
        m = (lo + hi) // 2; return logs_range(flt, lo, m, depth + 1) + logs_range(flt, m + 1, hi, depth + 1)

def ghst():
    pockets = {}; legs = 0
    for h, blk in T.GHST_TXS.items():
        r = T.rpc("eth_getTransactionReceipt", [h])
        for l in r["logs"]:
            if l["address"].lower() == GHST and l["topics"][0] == TRANSFER and T.addr(l["topics"][2]) == W:
                legs += 1; pockets.setdefault(T.addr(l["topics"][1]), []).append({"tx": h, "block": i(l["blockNumber"]), "log_index": i(l["logIndex"]), "wei": i(l["data"])})
        pockets.setdefault("_tx_" + h, {"to": None})
        t = T.rpc("eth_getTransactionByHash", [h]); pockets["_tx_" + h] = {"from": t["from"].lower(), "to": (t.get("to") or "").lower(), "selector": t["input"][:10], "block": blk}
    P = sorted(p for p in pockets if not p.startswith("_tx_")); padded = [T.pad(p) for p in P]
    per = {}   # Blockscout tokentx (candidate list; GHST contract only) per pocket - free RPC eth_getLogs is range-limited
    for p in P:
        r = bs({"module": "account", "action": "tokentx", "address": p, "contractaddress": GHST, "startblock": 0, "endblock": LAST, "sort": "asc", "page": 1, "offset": 1000})
        rows = r.get("result") if isinstance(r.get("result"), list) else []
        per[p] = [{"block": int(x["blockNumber"]), "log_index": int(x.get("logIndex") or 0), "tx": x["hash"], "dir": "in" if x["to"].lower() == p else "out",
                   "counterparty": x["from"].lower() if x["to"].lower() == p else x["to"].lower(), "wei": int(x["value"])} for x in rows]
    src = sorted({e["tx"] for v in per.values() for e in v if e["dir"] == "in"}); info = {}
    for h in src:
        t = T.rpc("eth_getTransactionByHash", [h]); info[h] = {"from": t["from"].lower(), "to": (t.get("to") or "").lower(), "selector": t["input"][:10], "block": i(t["blockNumber"])}
    return {"pockets": {p: {"withdrawn_to_wallet": pockets[p], "ghst_transfers": per.get(p, [])} for p in P},
            "withdraw_txs": {k[4:]: v for k, v in pockets.items() if k.startswith("_tx_")}, "source_txs": info,
            "legs": legs, "withdrawn_total_wei": sum(e["wei"] for p in P for e in pockets[p])}

def eth():
    base = {"module": "account", "address": W, "startblock": 0, "endblock": LAST, "sort": "asc", "offset": 1000}
    internal, top = [], []
    for page in (1, 2, 3):
        r = bs({**base, "action": "txlistinternal", "page": page}); rs = r.get("result") or []
        if not isinstance(rs, list): break
        internal += rs
        if len(rs) < 1000: break
    for page in (1, 2, 3):
        r = bs({**base, "action": "txlist", "page": page}); rs = r.get("result") or []
        if not isinstance(rs, list): break
        top += rs
        if len(rs) < 1000: break
    cand = sorted({x["transactionHash"] for x in internal if x.get("to", "").lower() == W and int(x.get("value") or 0) > 0 and str(x.get("isError", "0")) == "0"})
    conf = []; notes = []
    for h in cand:
        try: tr = T.rpc("debug_traceTransaction", [h, {"tracer": "callTracer"}])
        except T.Cap as e: notes.append(str(e)); break
        except RuntimeError as e: conf.append({"tx": h, "error": str(e)}); continue
        hits = []
        def rec(c, path):
            if (c.get("to") or "").lower() == W and i(c.get("value")) and path and not c.get("error"):
                hits.append({"from": (c.get("from") or "").lower(), "value_wei": i(c["value"]), "type": c.get("type"), "depth": len(path)})
            for s in c.get("calls") or []: rec(s, path + [(c.get("to") or "").lower()])
        if not tr.get("error"): rec(tr, [])
        bsx = [x for x in internal if x["transactionHash"] == h and x.get("to", "").lower() == W]
        conf.append({"tx": h, "block": int(bsx[0]["blockNumber"]), "tx_from": (tr.get("from") or "").lower(), "tx_to": (tr.get("to") or "").lower(),
                     "selector": (tr.get("input") or "")[:10], "top_value_wei": i(tr.get("value")) or 0, "internal_inflows": hits,
                     "rpc_wei": sum(x["value_wei"] for x in hits), "blockscout_wei": sum(int(x["value"]) for x in bsx)})
    topin = [{"tx": x["hash"], "block": int(x["blockNumber"]), "from": x["from"].lower(), "value_wei": int(x["value"]), "isError": x.get("isError")}
             for x in top if x.get("to", "").lower() == W and int(x.get("value") or 0) > 0]
    final = T.bal(LAST)
    sent = [x for x in top if x.get("from", "").lower() == W]
    return {"internal_rows": len(internal), "internal_into_wallet_txs": len(cand), "confirmed": conf, "top_level_inflows": topin,
            "top_level_sent": len(sent), "balance_at_last_wei": final, "notes": notes}

def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    try:
        if what in ("ghst", "all"): T._w("p4_1_ghst_trace.json", ghst())
        if what in ("eth", "all"): T._w("p4_1_eth_trace.json", eth())
    finally: print(json.dumps({"requests": T.N}, sort_keys=True))
if __name__ == "__main__": main()
