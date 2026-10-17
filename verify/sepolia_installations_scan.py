"""Architect P1.1 ask: scan Sepolia Installation-type diamonds for TransferSingle/TransferBatch/TransferToParent
touching the test wallet. Read-only, HyperSync at <=5/min (shared limiter). Usage: abra run cryptoPnL -- python -m verify.sepolia_installations_scan <wallet>"""
import json, sys, collections
from cryptopnl.sources import HyperSyncWalletLogs, T1155S, T1155B, post_json
from cryptopnl.config import CHAINS
TO_PARENT = "0xe82810099d182b25e23e895715954d6e7b41867a02e2c693cce68a8f250e43d3"
DIAMONDS = ["0x4773f06fb66735f1350a2db582660cbf6c0ff64b", "0xb2d52be3ab11006685843a59ec7d17bff2c554a1"]
NAMES = {T1155S: "TransferSingle", T1155B: "TransferBatch", TO_PARENT: "TransferToParent"}
w = sys.argv[1].lower(); t = "0x" + w[2:].rjust(64, "0")
src = HyperSyncWalletLogs(CHAINS[84532]["hypersync"])
sel = [{"address": DIAMONDS, "topics": [[T1155S, T1155B], [], [t]]},      # from = wallet
       {"address": DIAMONDS, "topics": [[T1155S, T1155B], [], [], [t]]},  # to = wallet
       {"address": DIAMONDS, "topics": [[TO_PARENT], [t]]}]               # toContract = wallet
b, out, req = 0, [], 0
while True:
    r = post_json("hypersync", src._lim, src.url, {"from_block": b, "logs": sel, "field_selection": {"log":
        ["block_number", "transaction_hash", "log_index", "address", "topic0", "topic1", "topic2", "topic3", "data"]}}, src.headers); req += 1
    out += [l for d in r.get("data", []) for l in (d.get("logs") or [])]
    nb = r["next_block"]; ah = r.get("archive_height") or 0
    if nb <= b or nb >= ah: break
    b = nb
# also: any TransferToParent at all on these contracts (to see whether the event is used there)
r = post_json("hypersync", src._lim, src.url, {"from_block": 0, "logs": [{"address": DIAMONDS, "topics": [[TO_PARENT]]}],
    "field_selection": {"log": ["block_number", "address"]}}, src.headers); req += 1
anyp = sum(len(d.get("logs") or []) for d in r.get("data", []))
c = collections.Counter((l["address"].lower(), NAMES.get(l["topic0"], l["topic0"])) for l in out)
ids = collections.defaultdict(set)
for l in out:
    if l["topic0"] == T1155S: ids[l["address"].lower()].add(int(l["data"][2:66], 16))
print(json.dumps({"wallet": "<TEST_WALLET>", "scanned_to": nb, "requests": req,
    "counts": {f"{a}:{k}": v for (a, k), v in sorted(c.items())},
    "single_ids": {a: sorted(v) for a, v in ids.items()},
    "transfer_to_parent_any_on_contracts_first_page": anyp,
    "duplicate_tx_across_both": len({l["transaction_hash"] for l in out if l["address"].lower() == DIAMONDS[0]} & {l["transaction_hash"] for l in out if l["address"].lower() == DIAMONDS[1]})}, indent=1))
