"""P4.1 H3 (READ-ONLY): how GHST (and any token) entered / left the 20 gotchi pockets before the 3 batchTransferEscrow txs.
One HyperSync query, paged: Transfer logs with topic2 in the pockets (in) or topic1 in the pockets (out), all tokens, blocks
[0, 40216495), with the txs joined (from / to / selector). Through the host limiter (5/min + 12 s gap); hard cap 8 new requests;
cached in logs/p4_1_cache/. ENVIO_API_TOKEN from abra by name. Facts only: nothing is classified.
  abra run cryptoPnL -k ENVIO_API_TOKEN -- env NET_REQLOG=logs/p4_1_reqlog.txt $PY scripts/p4_1_ghst_pockets.py"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import p4_1_trace as T
T.HS_CAP = 8
POCKETS = """02f7da40a267d7ae6c48caf041968542c3c46589 0c375f0a508f86709b675b4bbfdcef8d51de7ff3 1c0c0b9581cca74581ecf8a5c31f82653c1ef8a2
380e5e8d651cc708cf88b7a838035518fb4425a1 430a1a23bdeb6d50b0cc9bfc1f93992b582bc96f 443d5f09fd9b11250b060bdd420c7a9c8c2066c0
52265e2d4f82b0a363f5d045e2eb8769adb9ab39 6933b1a218d189d4a4c189a1e7b674453f41c0de 728f0baf79ebdfa336978c90f244324a0ba7bcff
7323a5e018fe495bc5fb390de18ccd61fdd2d8eb 8f64003ac2898edc02bf4a7ec4ab6537e4861368 9c2e5e9686974338181b145109da56b4b4406b19
a0173b0c67c4b96497c7185d047a00af27fce945 a51d2128f62b122b0be9b0c6b47ad6b017cd8350 a9ebe0f3ad527f3531a15d4770edc2b82b006801
aaeca339dec2b42cdc189e6df2b45fe8685fb6fb bc5699672c4ae61a951704acf2265fde7d9ec5ce db084925e330a7bed6aab9d7828b4defe2b96dc1
dfcebf9865f9cc40c590e0e5f45bf78105a6e6fa fba935526fafd92afcf7cc6472114458a6f77fb5""".split()
P = ["0x" + p for p in POCKETS]; assert len(P) == 20
TO = 40216495
q = {"logs": [{"topics": [[T.TRANSFER], [], [T.pad(p) for p in P]]}, {"topics": [[T.TRANSFER], [T.pad(p) for p in P]]}],
     "field_selection": {"log": ["block_number", "transaction_hash", "log_index", "address", "topic0", "topic1", "topic2", "topic3", "data"],
                         "transaction": ["hash", "from", "to", "input", "block_number"], "block": ["number", "timestamp"]}}
try: d = T.hs_all(q, 0, TO)
except T.Cap as e: print(json.dumps({"stopped": str(e), "n": T.N})); sys.exit(2)
txs = {t["hash"]: t for x in d for t in (x.get("transactions") or [])}
ts = {T.i(b["number"]): T.i(b["timestamp"]) for x in d for b in (x.get("blocks") or [])}
rows = []
for x in d:
    for l in x.get("logs") or []:
        f, to = T.addr(l["topic1"]), T.addr(l["topic2"])
        if l.get("topic3"): kind, amt = "erc721", str(T.i(l["topic3"]))
        else: kind, amt = "erc20", str(T.i(l["data"]))
        t = txs.get(l["transaction_hash"], {})
        rows.append({"block": T.i(l["block_number"]), "ts": ts.get(T.i(l["block_number"])), "tx": l["transaction_hash"], "log_index": T.i(l["log_index"]),
                     "token": l["address"].lower(), "kind": kind, "from": f, "to": to, "amount_raw": amt,
                     "dir": "in" if to in P else "out", "tx_from": (t.get("from") or "").lower(), "tx_to": (t.get("to") or "").lower(),
                     "selector": (t.get("input") or "0x")[:10]})
rows.sort(key=lambda r: (r["block"], r["log_index"]))
out = {"query": {"pockets": P, "from_block": 0, "to_block_excl": TO}, "requests": T.N, "rows": rows}
p = os.path.join(T.EV, "p4_1_ghst_pockets.json")
with open(p, "w") as f: json.dump(out, f, indent=1, sort_keys=True)
print(json.dumps({"rows": len(rows), "txs": len(txs), "n": T.N, "out": p}))
