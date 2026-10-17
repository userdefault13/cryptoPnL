"""Read-only eth_getCode bisection for contract deploy blocks. Usage: python -m verify.deploy_block <chain> <addr>..."""
import json, sys
from cryptopnl.sources import RPC
from cryptopnl.config import CHAINS
chain = int(sys.argv[1]); rpc = RPC(CHAINS[chain]["rpc"])
def has(a, b):
    try: return rpc.call("eth_getCode", [a, hex(b)]) not in ("0x", "", None)
    except RuntimeError as e: return "ERR:" + str(e)[:120]
head = rpc.block("latest")[0]
for a in sys.argv[2:]:
    lo, hi, calls, note = 0, head, 0, None
    r = has(a, hi); calls += 1
    if r is not True: print(json.dumps({"contract": a, "error": f"no code at head: {r}"})); continue
    while lo < hi:
        mid = (lo + hi) // 2; r = has(a, mid); calls += 1
        if isinstance(r, str): note = r; break
        if r: hi = mid
        else: lo = mid + 1
    print(json.dumps({"contract": a, "deploy_block": None if note else lo, "lowest_known": hi, "rpc_calls": calls, "note": note, "head": head}))
