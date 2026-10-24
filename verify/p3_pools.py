"""P3 (DESIGN §5 Q3): find DEX pools on Base for the tracked fungibles by READ-ONLY factory calls (public RPC, 1 req/s).
Factories: Uniswap V3 0x33128a8f… (docs.uniswap.org Base deployments), Aerodrome v2 PoolFactory 0x420DD381…, Aerodrome Slipstream
CLFactory 0x5e7BB104… (legacy) and 0xf8f2eB49… (Gauges V3). For each pool: balances of both tokens at the given block (liquidity proxy).
Run: .venv/bin/python verify/p3_pools.py [block]   -> JSON lines"""
import json, re, sys
sys.path.insert(0, ".")
T = {"GHST": "0xcd2f22236dd9dfe2356d7c543161d4d260fd9bcb", "FUD": "0x2028b4043e6722ea164946c82fe806c4a43a0ff4",
     "FOMO": "0xa32137bfb57d2b6a9fd2956ba4b54741a6d54b58", "ALPHA": "0x15e7cac885e3730ce6389447bc0f7ac032f31947",
     "KEK": "0xe52b9170ff4ece4c35e796ffd74b57dec68ca0e5", "GLTR": "0x4d140ce792bedc430498c2d219afbc33e2992c9d",
     "WETH": "0x4200000000000000000000000000000000000006", "cbBTC": "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf"}
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
Q = {"USDC": USDC, "WETH": T["WETH"], "GHST": T["GHST"]}
UNI, AERO = "0x33128a8fc17869897dce68ed026d694621f6fdfd", "0x420dd381b31aef6683db6b902084cb0ffece40da"
CL = ["0x5e7bb104d84c7cb9b682aac2f3d509f5f406809a", "0xf8f2eb4940cfe7d13603dddd87f123820fc061ef"]
_ADDR = re.compile(r"^0x[0-9a-f]{40}$")
def a32(a):
    """ABI address word. Rejects anything that is not exactly 20 bytes and non-zero: the 2026-10-17 GLTR miss was a 41-hex-digit
    typo, and a 2026-10-23 shell re-check passed an empty (zero) quote token; both silently returned getPool = 0x0."""
    a = a.lower()
    if not _ADDR.match(a) or int(a, 16) == 0: raise ValueError(f"bad token address for a factory call: {a!r}")
    return a[2:].rjust(64, "0")
u32 = lambda v: format(v % (1 << 256), "064x")
def calls_for(t, q):
    """[(kind, param, factory, calldata)] for every factory lookup of the pair (t, q); both orders are equivalent on these factories."""
    out = [("uniV3", f, UNI, "0x1698ee82" + a32(t) + a32(q) + u32(f)) for f in (100, 500, 3000, 10000)]
    out += [("aeroV2", st, AERO, "0x79bc57d5" + a32(t) + a32(q) + u32(int(st))) for st in (False, True)]
    out += [("aeroCL", (fac[:8], ts), fac, "0x28af8d0b" + a32(t) + a32(q) + u32(ts)) for fac in CL for ts in (1, 50, 100, 200, 2000)]
    return out
def addr(r): return None if not r or r == "0x" or int(r, 16) == 0 else "0x" + r[-40:]

def main():
    from cryptopnl.sources import RPC
    from cryptopnl.config import CHAINS
    rpc = RPC(CHAINS[8453]["rpc"]); blk = int(sys.argv[1]) if len(sys.argv) > 1 else rpc.block("latest")[0]
    def call(to, data):
        try: return rpc.eth_call(to, data, blk)
        except RuntimeError: return None
    def bal(tok, who):
        r = call(tok, "0x70a08231" + a32(who)); return int(r, 16) if r and r != "0x" else None
    DEC = {}
    def dec(tok):
        if tok not in DEC: r = call(tok, "0x313ce567"); DEC[tok] = int(r, 16) if r and r != "0x" else None
        return DEC[tok]
    seen = set()
    for tn, t in T.items():
        for qn, q in Q.items():
            if t == q or (qn, tn) in seen: continue
            seen.add((tn, qn))
            for kind, param, fac, data in calls_for(t, q):
                p = addr(call(fac, data))
                if not p: continue
                bt, bq = bal(t, p), bal(q, p)
                print(json.dumps({"block": blk, "token": tn, "quote": qn, "kind": kind, "param": param, "pool": p,
                                  "bal_token": None if bt is None else bt / 10 ** dec(t), "bal_quote": None if bq is None else bq / 10 ** dec(q)}), flush=True)
    print(json.dumps({"done": True, "block": blk}))

if __name__ == "__main__": main()
