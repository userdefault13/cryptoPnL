"""P4.1 step 1: READ-ONLY source-fact tracing of the unrecorded ETH / GHST inflows (docs/P4_1_PLAN.md). Chain data only; no ledger
writes, no signing. HyperSync and RPC go through the host limiters (5/min + 12 s gap; 30/min + 1.5 s gap) and hard caps; every
response is cached in logs/p4_1_cache/ so a rerun repeats no request. ENVIO_API_TOKEN comes from the environment (abra by name).
  abra run cryptoPnL -k ENVIO_API_TOKEN -- env NET_REQLOG=logs/p4_1_reqlog.txt .venv/bin/python scripts/p4_1_trace.py [eth|ghst|all]"""
import hashlib, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from cryptopnl.net import post_json
from cryptopnl.hostlimit import hypersync_limiter, rpc_limiter
from cryptopnl.config import CHAINS, DEX_ROUTERS

W = "0x2127aa7265d573aa467f1d73554d17890b872e76"; GHST = "0xcd2f22236dd9dfe2356d7c543161d4d260fd9bcb"
WETH = "0x4200000000000000000000000000000000000006"
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
T1155S = "0xc3d58168c5ae7397731d063d5bbf3d657854427343f4c083240f7aacaa2d0f62"
LAST = 52911467; HS_CAP, RPC_CAP = 28, 370
GHST_TXS = {"0xd329b5d246f4bad659ad766e10b8256706f59a809ceed111e867371ea8348792": 38141654,
            "0x0aeef829d5a77c4c860987567760fa25cc5da68252d3412858ae570f6193047b": 38622419,
            "0xdad1902355e2d6418032b5b165351fb80ef580889dbf7e68ced3200f5204c3f5": 40216494}
HERE = os.path.join(os.path.dirname(__file__), ".."); CACHE = os.path.join(HERE, "logs", "p4_1_cache"); os.makedirs(CACHE, exist_ok=True)
EV = os.path.join(HERE, "docs", "evidence")
N = {"hypersync": 0, "rpc": 0, "hypersync_cached": 0, "rpc_cached": 0}
class Cap(Exception): pass
def pad(a): return "0x" + "0" * 24 + a.lower()[2:]
def i(x): return None if x is None else (x if isinstance(x, int) else int(x, 16))
def addr(t): return "0x" + t[-40:].lower()

def _cached(kind, body, fn):
    k = hashlib.sha256(json.dumps([kind, body], sort_keys=True).encode()).hexdigest()[:24]; p = os.path.join(CACHE, f"{kind}_{k}.json")
    if os.path.exists(p):
        N[kind + "_cached"] += 1
        with open(p) as f: return json.load(f)
    if N[kind] >= (HS_CAP if kind == "hypersync" else RPC_CAP): raise Cap(f"{kind} cap {N[kind]} reached")
    N[kind] += 1; r = fn()
    with open(p + ".tmp", "w") as f: json.dump(r, f)
    os.replace(p + ".tmp", p); return r

def hs(q):
    url = CHAINS[8453]["hypersync"].rstrip("/") + "/query"; h = {"Authorization": "Bearer " + os.environ["ENVIO_API_TOKEN"]}
    return _cached("hypersync", q, lambda: post_json("hypersync", hypersync_limiter(), url, q, h))
def hs_all(q, frm, to):
    """All pages of q over [frm, to) (to exclusive)."""
    out = []; b = frm
    while b < to:
        r = hs({**q, "from_block": b, "to_block": to}); out += r.get("data", []); nb = r["next_block"]
        if nb <= b: break
        b = nb
    return out
def rpc(method, params):
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    r = _cached("rpc", body, lambda: post_json("rpc", rpc_limiter(), CHAINS[8453]["rpc"], body))
    if "error" in r: raise RuntimeError(f"rpc {method}: code {r['error'].get('code')}")
    return r["result"]
def bal(b): return i(rpc("eth_getBalance", [W, hex(b)]))

# ---------------- (a) ETH ----------------
TXF = ["hash", "block_number", "transaction_index", "from", "to", "value", "gas_used", "effective_gas_price", "l1_fee", "status", "type", "input"]
def wallet_txs():
    d = hs_all({"transactions": [{"from": [W]}, {"to": [W]}], "field_selection": {"transaction": TXF}}, 0, LAST + 1)
    txs = {t["hash"]: t for x in d for t in (x.get("transactions") or [])}
    return sorted(txs.values(), key=lambda t: (i(t["block_number"]), i(t["transaction_index"])))
def delta(t):
    """Wallet balance change of one top-level tx, internal transfers excluded (wei)."""
    ok = i(t.get("status")) == 1; v = i(t.get("value")) or 0; d = 0
    if (t.get("to") or "").lower() == W and ok: d += v
    if (t.get("from") or "").lower() == W:
        if ok: d -= v
        d -= (i(t.get("gas_used")) or 0) * (i(t.get("effective_gas_price")) or 0) + (i(t.get("l1_fee")) or 0)
    return d

def eth():
    txs = wallet_txs(); blocks = sorted({i(t["block_number"]) for t in txs}); E = {}; run = 0
    byb = {}
    for t in txs: byb.setdefault(i(t["block_number"]), []).append(t)
    for b in blocks: run += sum(delta(t) for t in byb[b]); E[b] = run
    pts = [blocks[0] - 1] + blocks + ([LAST] if blocks[-1] < LAST else [])
    def exp(b):   # expected balance at end of block b (no internal transfers)
        last = [x for x in blocks if x <= b]; return E[last[-1]] if last else 0
    S = {}
    def s(b):
        if b not in S: S[b] = bal(b) - exp(b)
        return S[b]
    changes = []; notes = []
    def walk(lo, hi):   # indices into pts
        if s(pts[lo]) == s(pts[hi]): return
        if hi == lo + 1:
            b = pts[hi]; inside = s(b) - s(b - 1) if b - 1 > pts[lo] else s(b) - s(pts[lo]); between = s(pts[hi] - 1) - s(pts[lo]) if b - 1 > pts[lo] else 0
            if inside: changes.append({"where": "in_block", "block": b, "surplus_delta_wei": inside})
            if between: changes.append({"where": "between", "from_block": pts[lo] + 1, "to_block": b - 1, "surplus_delta_wei": between})
            return
        m = (lo + hi) // 2; walk(lo, m); walk(m, hi)
    try: s(pts[0]); walk(0, len(pts) - 1)
    except Cap as e: notes.append(str(e))
    # mechanisms
    for c in changes:
        try:
            if c["where"] == "in_block":
                c["candidates"] = []
                for t in byb.get(c["block"], []):
                    tr = rpc("debug_traceTransaction", [t["hash"], {"tracer": "callTracer"}])
                    hits = []
                    def rec(call, path):
                        if (call.get("to") or "").lower() == W and i(call.get("value")) and path: hits.append({"from": call.get("from").lower(), "value_wei": i(call["value"]), "depth": len(path), "type": call.get("type"), "path": path})
                        for k, sub in enumerate(call.get("calls") or []): rec(sub, path + [(call.get("to") or "").lower()])
                    rec(tr, [])
                    c["candidates"].append({"tx": t["hash"], "tx_to": (t.get("to") or "").lower(), "selector": (t.get("input") or "")[:10], "status": i(t.get("status")),
                                            "internal_inflows": hits, "internal_sum_wei": sum(h["value_wei"] for h in hits)})
                c["explained_wei"] = sum(x["internal_sum_wei"] for x in c["candidates"])
            else:
                sel = [{"topics": [[], [pad(W)]]}, {"topics": [[], [], [pad(W)]]}, {"topics": [[], [], [], [pad(W)]]}]
                d = hs_all({"logs": sel, "field_selection": {"log": ["block_number", "transaction_hash", "address", "topic0"]}}, c["from_block"], c["to_block"] + 1)
                c["wallet_logs"] = sorted({(i(l["block_number"]), l["transaction_hash"], l["address"].lower(), l["topic0"]) for x in d for l in (x.get("logs") or [])})
        except Cap as e: notes.append(str(e)); break
    first_bal = {"block": pts[0], "balance_wei": bal(pts[0]) if pts[0] in S or True else None}
    out = {"wallet": W, "wallet_txs": len(txs), "tx_blocks": len(blocks), "checkpoints_probed": len(S), "last_block": LAST,
           "expected_final_wei": exp(LAST), "actual_final_wei": bal(LAST), "surplus_final_wei": s(LAST),
           "top_level_inflows": [{"tx": t["hash"], "block": i(t["block_number"]), "from": t["from"].lower(), "value_wei": i(t["value"]), "type": i(t.get("type")), "status": i(t.get("status"))}
                                 for t in txs if (t.get("to") or "").lower() == W and (i(t.get("value")) or 0) > 0],
           "first_probe": first_bal, "changes": changes, "notes": notes, "routers": sorted(DEX_ROUTERS.get(8453, []))}
    return out

# ---------------- (b) GHST ----------------
def ghst():
    d = hs_all({"logs": [{"address": [GHST], "topics": [[TRANSFER], [], [pad(W)]]}],
                "field_selection": {"log": ["block_number", "transaction_hash", "log_index", "address", "topic1", "topic2", "data"]}}, 38141654, 40216495)
    legs = [l for x in d for l in (x.get("logs") or []) if l["transaction_hash"] in GHST_TXS]
    pockets = {}
    for l in legs: pockets.setdefault(addr(l["topic1"]), []).append({"tx": l["transaction_hash"], "block": i(l["block_number"]), "wei": i(l["data"])})
    P = sorted(pockets); padded = [pad(p) for p in P]
    d = hs_all({"logs": [{"topics": [[TRANSFER], [], padded]}, {"topics": [[TRANSFER], padded]},
                         {"topics": [[T1155S], [], [], padded]}, {"topics": [[T1155S], [], padded]}],
                "field_selection": {"log": ["block_number", "transaction_hash", "log_index", "address", "topic0", "topic1", "topic2", "topic3", "data"]}}, 0, LAST + 1)
    logs = sorted({(i(l["block_number"]), l["log_index"] if isinstance(l["log_index"], int) else i(l["log_index"]), l["transaction_hash"], l["address"].lower(), l["topic0"], l.get("topic1"), l.get("topic2"), l.get("topic3"), l.get("data")) for x in d for l in (x.get("logs") or [])})
    per = {}
    for (b, li, tx, a, t0, t1, t2, t3, data) in logs:
        if t0 != TRANSFER or t1 is None or t2 is None or t3 is not None: continue   # ERC20 only (ERC721 has topic3)
        f, t = addr(t1), addr(t2); amt = i(data) if data and data != "0x" else 0
        for p in P:
            if p in (f, t):
                per.setdefault(p, []).append({"block": b, "log_index": li, "tx": tx, "token": a, "dir": "in" if t == p else "out", "counterparty": f if t == p else t, "wei": amt})
    srcs = sorted({e["tx"] for v in per.values() for e in v if e["dir"] == "in"})
    txinfo = {}
    try:
        for h in srcs:
            t = rpc("eth_getTransactionByHash", [h]); txinfo[h] = {"from": t["from"].lower(), "to": (t.get("to") or "").lower(), "selector": (t.get("input") or "")[:10], "block": i(t["blockNumber"]), "type": i(t.get("type"))}
    except Cap as e: txinfo["_note"] = str(e)
    return {"pockets": {p: {"withdrawn_to_wallet": pockets[p], "transfers": per.get(p, [])} for p in P}, "source_txs": txinfo,
            "withdrawn_total_wei": sum(e["wei"] for v in pockets.values() for e in v), "legs": len(legs)}

def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"; res = {}
    try:
        if what in ("ghst", "all"): res["ghst"] = ghst(); _w("p4_1_ghst_trace.json", res["ghst"])
        if what in ("eth", "all"): res["eth"] = eth(); _w("p4_1_eth_trace.json", res["eth"])
    finally:
        print(json.dumps({"requests": N}, sort_keys=True))
def _w(n, o):
    with open(os.path.join(EV, n), "w") as f: json.dump(o, f, indent=1, sort_keys=True, default=str); f.write("\n")
if __name__ == "__main__": main()
