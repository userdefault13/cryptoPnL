"""P4.1 step 1 (a), keyless: find every block where the wallet's ETH balance rises beyond its recorded ETH rows (READ-ONLY).
Expected path = the MBP copy's ETH ledger rows (exact to the wei on probes: fee incl. L1 fee), actual = RPC eth_getBalance; the surplus
S(b) = actual - recorded rises only by unrecorded inflows. Bisect over the recorded blocks; a change inside the gap (b_prev, b] is split
into "in block b" vs "between" with one more probe; between-gaps are narrowed by block bisection. Then debug_traceTransaction
(callTracer) on the wallet's txs in each in-block change names the sender and mechanism. Probe budget 250 RPC; total cap 370."""
import json, sys, os
sys.path.insert(0, os.path.dirname(__file__)); import p4_1_trace as T
END = 52112861; PROBES = 250
rows = [l.split() for l in open("logs/p4_1_eth_rows_mbpcopy.txt")]
L = {}; txs = {}; run = 0
for b, h, cat, q in rows:
    b = int(b); run += int(q); L[b] = run; txs.setdefault(b, []).append((h, cat, int(q)))
blocks = sorted(L); pts = [blocks[0] - 1] + blocks + [END]
def rec(b):
    last = [x for x in blocks if x <= b]; return L[last[-1]] if last else 0
S = {}; used = [0]
class Budget(Exception): pass
def s(b):
    if b not in S:
        if used[0] >= PROBES: raise Budget()
        n0 = T.N["rpc"]; S[b] = T.bal(b) - rec(b); used[0] += T.N["rpc"] - n0
    return S[b]
changes = []; notes = []
def between(lo, hi, d):   # S changes somewhere in blocks (lo, hi], no recorded rows inside: narrow to one block
    while hi - lo > 1:
        m = (lo + hi) // 2
        if s(m) != s(lo): hi = m
        else: lo = m
    changes.append({"where": "between_recorded_blocks", "block": hi, "surplus_delta_wei": s(hi) - s(hi - 1)})
def walk(a, c):
    if s(pts[a]) == s(pts[c]): return
    if c == a + 1:
        lo, b = pts[a], pts[c]
        if b - 1 > lo and s(b - 1) != s(lo): between(lo, b - 1, None)
        if b - 1 > lo: d = s(b) - s(b - 1)
        else: d = s(b) - s(lo)
        if d: changes.append({"where": "in_recorded_block", "block": b, "surplus_delta_wei": d, "recorded": txs.get(b, [])})
        return
    m = (a + c) // 2; walk(a, m); walk(m, c)
try: s(pts[0]); walk(0, len(pts) - 1)
except Budget: notes.append(f"probe budget {PROBES} reached; result partial")
# traces for in-block changes
for c in changes:
    if c["where"] != "in_recorded_block": continue
    c["traces"] = []
    for h in sorted({h for h, _, _ in c["recorded"]}):
        try: tr = T.rpc("debug_traceTransaction", [h, {"tracer": "callTracer"}])
        except (T.Cap, RuntimeError) as e: c["traces"].append({"tx": h, "error": str(e)}); continue
        hits = []
        def r(x, path):
            if (x.get("to") or "").lower() == T.W and T.i(x.get("value")) and path and not x.get("error"):
                hits.append({"from": (x.get("from") or "").lower(), "value_wei": T.i(x["value"]), "type": x.get("type"), "depth": len(path), "path": path})
            for y in x.get("calls") or []: r(y, path + [(x.get("to") or "").lower()])
        r(tr, [])
        c["traces"].append({"tx": h, "tx_from": (tr.get("from") or "").lower(), "tx_to": (tr.get("to") or "").lower(), "selector": (tr.get("input") or "")[:10],
                            "top_value_wei": T.i(tr.get("value")) or 0, "internal_inflows": hits, "internal_sum_wei": sum(x["value_wei"] for x in hits)})
    c["explained_by_traces_wei"] = sum(t.get("internal_sum_wei", 0) for t in c["traces"])
out = {"wallet": T.W, "expected_path": "MBP cryptopnl_p3_base ETH rows (511 rows, 457 blocks; NOT the canonical ledger)", "end_block": END,
       "pre_first_row": {"block": pts[0], "balance_wei": s(pts[0])}, "surplus_at_end_wei": S.get(END), "probes": len(S), "changes": changes,
       "sum_changes_wei": sum(c["surplus_delta_wei"] for c in changes), "notes": notes, "requests": dict(T.N)}
T._w("p4_1_eth_trace.json", out); print(json.dumps({k: out[k] for k in ("probes", "surplus_at_end_wei", "sum_changes_wei", "notes", "requests")}, default=str))
print(len(changes), "changes")
