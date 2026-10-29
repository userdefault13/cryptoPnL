"""P4.1 rule 7 (READ-ONLY): facts for the gotchi pocket inflows (docs/P4_1_PLAN.md "Rule 7 round"). Chain data only.
  R1  Multicall3 gotchiEscrow(id) for the 24 gotchis the wallet ever held, at block LAST            (1 eth_call)
  HS2 Transfer / TransferSingle / TransferBatch into or out of those escrows, blocks [0, LAST]       (txs + blocks joined)
  HS1 the wallet's lending txs to the Diamond and its 7702 execute txs, JoinAll (inputs + all their logs)
  R2  Multicall3 ownerOf / isAavegotchiLent / getGotchiLendingIdByToken for the 24 at the first inflow block (1 eth_call)
  HS3 indexed lending events (Add / Execute / Cancel / End, topic1 = listingId) for every listingId found
Host limiters (HyperSync 5/min + 12 s gap, RPC 30/min); hard caps 7 HyperSync / 6 RPC new requests; cached in logs/p4_1_cache/.
ENVIO_API_TOKEN from abra by name:
  abra run aavegotchi-envio-indexers -k ENVIO_API_TOKEN -- env NET_REQLOG=logs/p4_1_reqlog.txt $PY scripts/p4_1_pockets.py"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import p4_1_trace as T
T.HS_CAP, T.RPC_CAP = 7, 6
DIAMOND = "0xa99c4b08201f2913db8d28e71d020c4298f29dbf"; MC3 = "0xca11bde05977b3631167028862be2a173976ca11"
GOTCHIS = [954, 3033, 5041, 5402, 6701, 7298, 8461, 8532, 9934, 10478, 10503, 10774, 12302, 12444, 14314, 14338, 15017, 15486,
           16263, 16371, 19425, 22899, 23336, 23965]   # wallet-scoped ERC721 legs on the Diamond (MBP copy, 2026-10-28)
T1155B = "0x4a39dc06d4c0dbc64b70af90fd698a233a518aa5d07e595d983b8c0526c8f7fb"
LEND_SEL = ["0x2b4caab7", "0x8be5dcbe", "0x85c3c3cf", "0x8311e041", "0xca11e5e8", "0xb59ffa06", "0x96e18391", "0xb815a1ed", "0x9379f260",
            "0x7497a61c", "0xf0b09e3b", "0xf7b4edda", "0x4277a16e", "0xae0c8bd8", "0xffa7802d", "0x80825c6e", "0x33f012ce", "0x5a5fb2c5",
            "0x73890eed"]
OPERATOR_SEL = {"0x33f012ce", "0x5a5fb2c5"}; EXECUTE = "0xe9ae5c53"
EV_ADD, EV_EXEC, EV_CANCEL, EV_END = ("0xd2235b2f5daa2ac7ea851058a8b86b1e44cfa6c4904167f59114707b2574a87d",
    "0x28d7b849b5b1af16b5f1e07a41673a69940182a65953874032dc5e5698170f96", "0x58bf86d7321ca96f6873fbd24682c06a141b27bb3c7daa42393eb177d6da8d41",
    "0xd5052ec7f019796e5e27e648ce0dcc5514bdb14fb483caf83830b61f09f9a5bc")
EV_ADDED_T = "0xadc13c9d62cd4bcbbb442aa67108747dd6f5332f476b67c4d5ff7cfec4533e15"
EV_OPERATOR = "0x160787829b02b2d2716cb25e529db007ac1aab89f8660269852157327f4505f8"
LF = ["block_number", "transaction_hash", "transaction_index", "log_index", "address", "topic0", "topic1", "topic2", "topic3", "data"]
TF = ["hash", "block_number", "transaction_index", "from", "to", "input", "status"]

def w(x): return format(x, "064x")
def aggregate(calls, block):
    """Multicall3 aggregate((address,bytes)[]) -> list of return-data hex strings (each call's calldata is 36 bytes)."""
    n = len(calls); head = w(0x20) + w(n); offs = ""; body = ""
    for k, (to, data) in enumerate(calls):
        d = data[2:]; assert len(d) == 72
        offs += w(n * 32 + k * 160)
        body += w(int(to, 16)) + w(0x40) + w(36) + d + "0" * 56
    r = T.rpc("eth_call", [{"to": MC3, "data": "0x252dba42" + head + offs + body}, hex(block)])[2:]
    W = lambda k: int(r[k * 64:(k + 1) * 64], 16)
    base = W(1) // 32; m = W(base); out = []
    for k in range(m):
        p = base + 1 + W(base + 1 + k) // 32; ln = W(p); out.append(r[(p + 1) * 64:(p + 1) * 64 + ln * 2])
    return out

def main():
    # R1 escrows at LAST
    esc = aggregate([(DIAMOND, "0xa8e39da0" + w(g)) for g in GOTCHIS], T.LAST)
    escrow = {g: "0x" + e[-40:] for g, e in zip(GOTCHIS, esc) if int(e or "0", 16)}
    assert escrow.get(3033) == "0x728f0baf79ebdfa336978c90f244324a0ba7bcff", escrow.get(3033)   # config.GOTCHI_ESCROW_SEL note
    P = sorted(set(escrow.values())); PP = [T.pad(p) for p in P]; gid = {v: k for k, v in escrow.items()}
    # HS2 pocket legs
    q = {"logs": [{"topics": [[T.TRANSFER], [], PP]}, {"topics": [[T.TRANSFER], PP]},
                  {"topics": [[T.T1155S, T1155B], [], PP]}, {"topics": [[T.T1155S, T1155B], [], [], PP]}],
         "field_selection": {"log": LF, "transaction": TF, "block": ["number", "timestamp", "hash"]}}
    d = T.hs_all(q, 0, T.LAST + 1)
    txs = {t["hash"]: t for x in d for t in (x.get("transactions") or [])}
    ts = {T.i(b["number"]): T.i(b["timestamp"]) for x in d for b in (x.get("blocks") or [])}
    bh = {T.i(b["number"]): b["hash"] for x in d for b in (x.get("blocks") or [])}
    rows = []
    for x in d:
        for l in x.get("logs") or []:
            t0 = l["topic0"]; t = txs.get(l["transaction_hash"], {}); words = [l["data"][2 + 64 * k: 66 + 64 * k] for k in range((len(l["data"]) - 2) // 64)]
            if t0 == T.TRANSFER:
                f, to = T.addr(l["topic1"]), T.addr(l["topic2"])
                legs = [("erc721", str(T.i(l["topic3"])), "1")] if l.get("topic3") else [("erc20", None, str(int(words[0], 16)))]
            else:
                f, to = T.addr(l["topic2"]), T.addr(l["topic3"])
                if t0 == T.T1155S: legs = [("erc1155", str(int(words[0], 16)), str(int(words[1], 16)))]
                else:
                    a = int(words[0], 16) // 32; b2 = int(words[1], 16) // 32; n = int(words[a], 16)
                    legs = [("erc1155", str(int(words[a + 1 + k], 16)), str(int(words[b2 + 1 + k], 16))) for k in range(n)]
            for kind, tid, amt in legs:
              for pk in ([] if f == to else [a for a in (to, f) if a in gid]):   # a pocket-to-pocket move gives an out row and an in row
                rows.append({"block": T.i(l["block_number"]), "ts": ts.get(T.i(l["block_number"])), "block_hash": bh.get(T.i(l["block_number"])), "tx": l["transaction_hash"],
                             "tx_index": T.i(l.get("transaction_index")), "log_index": T.i(l["log_index"]), "token": l["address"].lower(),
                             "kind": kind, "token_id": tid, "amount_raw": amt, "from": f, "to": to, "pocket": pk, "gotchi": gid[pk],
                             "dir": "in" if pk == to else "out", "tx_from": (t.get("from") or "").lower(), "tx_to": (t.get("to") or "").lower(),
                             "selector": (t.get("input") or "0x")[:10], "tx_status": T.i(t.get("status"))})
    rows.sort(key=lambda r: (r["block"], r["log_index"]))
    first_in = min(r["block"] for r in rows if r["dir"] == "in")
    # HS1 wallet lending / execute txs with all their logs
    q1 = {"transactions": [{"from": [T.W], "to": [DIAMOND], "sighash": LEND_SEL}, {"from": [T.W], "sighash": [EXECUTE]}], "join_mode": "JoinAll",
          "field_selection": {"log": LF, "transaction": TF}}
    d1 = T.hs_all(q1, 0, T.LAST + 1)
    ltx = sorted({t["hash"]: t for x in d1 for t in (x.get("transactions") or [])}.values(), key=lambda t: T.i(t["block_number"]))
    llogs = [l for x in d1 for l in (x.get("logs") or []) if (l.get("address") or "").lower() == DIAMOND]
    operator_calls = [t["hash"] for t in ltx if (t.get("input") or "")[:10] in OPERATOR_SEL or
                      ((t.get("input") or "")[:10] == EXECUTE and any(s[2:] in (t.get("input") or "")[10:] for s in OPERATOR_SEL))]
    operator_logs = [l["transaction_hash"] for l in llogs if l["topic0"] == EV_OPERATOR]
    listing_token = {}
    for l in llogs:
        if l["topic0"] == EV_ADDED_T:
            ws = [l["data"][2 + 64 * k: 66 + 64 * k] for k in range(4)]
            listing_token[int(ws[1], 16)] = {"token": int(ws[3], 16), "lender": "0x" + ws[2][-40:], "tx": l["transaction_hash"], "block": T.i(l["block_number"])}
    # R2 owner / lent / listing id at the first inflow block
    r2 = aggregate([c for g in GOTCHIS for c in ((DIAMOND, "0x6352211e" + w(g)), (DIAMOND, "0xd731d44e" + w(g)), (DIAMOND, "0xfc02e4ee" + w(g)))], first_in)
    at_first = {g: {"owner": "0x" + r2[3 * k][-40:], "lent": bool(int(r2[3 * k + 1] or "0", 16)), "listing_id": int(r2[3 * k + 2] or "0", 16)}
                for k, g in enumerate(GOTCHIS)}
    ids = sorted(set(listing_token) | {v["listing_id"] for v in at_first.values() if v["listing_id"]})
    ev = []
    if ids:
        q3 = {"logs": [{"address": [DIAMOND], "topics": [[EV_ADD, EV_EXEC, EV_CANCEL, EV_END], ["0x" + w(i) for i in ids]]}],
              "field_selection": {"log": ["block_number", "transaction_hash", "log_index", "topic0", "topic1"]}, "join_mode": "JoinNothing"}
        d3 = T.hs_all(q3, 0, T.LAST + 1)
        nm = {EV_ADD: "add", EV_EXEC: "execute", EV_CANCEL: "cancel", EV_END: "end"}
        ev = sorted(({"block": T.i(l["block_number"]), "log_index": T.i(l["log_index"]), "tx": l["transaction_hash"], "event": nm[l["topic0"]],
                      "listing_id": T.i(l["topic1"])} for x in d3 for l in (x.get("logs") or [])), key=lambda e: (e["block"], e["log_index"]))
    out = {"query": {"gotchis": GOTCHIS, "last_block": T.LAST, "first_inflow_block": first_in}, "requests": T.N, "escrow": {str(k): v for k, v in escrow.items()},
           "rows": rows, "lending": {"wallet_txs": [{"tx": t["hash"], "block": T.i(t["block_number"]), "selector": (t.get("input") or "0x")[:10],
                                                     "status": T.i(t.get("status"))} for t in ltx],
                                     "operator_calls": operator_calls, "operator_events": operator_logs,
                                     "listings": {str(k): v for k, v in listing_token.items()}, "at_first_inflow": {str(k): v for k, v in at_first.items()},
                                     "events": ev}}
    p = os.path.join(T.EV, "p4_1_pockets.json")
    with open(p, "w") as f: json.dump(out, f, indent=1, sort_keys=True)
    print(json.dumps({"rows": len(rows), "in": sum(r["dir"] == "in" for r in rows), "pockets": len(P), "first_in": first_in, "lending_txs": len(ltx),
                      "operator_calls": len(operator_calls), "operator_events": len(operator_logs), "listings": len(ids), "lending_events": len(ev),
                      "n": T.N, "out": p}))

if __name__ == "__main__":
    try: main()
    except T.Cap as e: print(json.dumps({"stopped": str(e), "n": T.N})); sys.exit(2)
