import os
CHAINS = {
  84532: {"name": "base-sepolia", "hypersync": os.environ.get("HYPERSYNC_URL_84532", "https://base-sepolia.hypersync.xyz"),
          "rpc": os.environ.get("SEPOLIA_RPC_URL", "https://sepolia.base.org")},
  8453:  {"name": "base", "hypersync": os.environ.get("HYPERSYNC_URL_8453", "https://base.hypersync.xyz"),
          "rpc": os.environ.get("BASE_RPC_URL", "https://base.drpc.org")},
}
DSN = os.environ.get("CRYPTOPNL_DSN", "dbname=cryptopnl")
HYPERSYNC_RPM = float(os.environ.get("HYPERSYNC_RPM", "7"))   # MBP has no local throttle: self-cap 7/min
RPC_RPS = float(os.environ.get("RPC_RPS", "1"))               # architect (PR #1): RPC 1 req/s, burst 3
RPC_BURST = int(os.environ.get("RPC_BURST", "3"))
REORG_CHECK_BLOCKS = 64                                     # max stored blocks re-checked per run
REORG_WINDOW = int(os.environ.get("REORG_WINDOW", "10000"))  # only blocks within cursor-WINDOW can still reorg (Base finalizes << 10k blocks)

def _topics():
    import os as _o
    f = _o.path.join(_o.path.dirname(__file__), "..", "verify", "marketplace_topics.txt")
    return {l.split()[0]: l.split()[1].split("(")[0] for l in open(f) if l.strip()}
MARKET_TOPICS = _topics()
# S1b replacement (DESIGN v1.0): Baazaar (Aavegotchi Diamond) + GBM diamond logs via HyperSync
MARKETPLACE = {8453: {"source": "hypersync_market", "start_block": 33315000,
                      "contracts": ["0xa99c4b08201f2913db8d28e71d020c4298f29dbf", "0x80320a0000c7a6a34086e2acad6915ff57ffda31"]}}

# Assets in scope for PnL (ENVIO_TOKEN_INDEXER §1.1 + Aavegotchi Diamond NFTs/1155s). Others are reported, not gating.
TRACKED = {8453: {"0x833589fcd6edb6e08f4c7c32d4f71b54bda02913", "0x4200000000000000000000000000000000000006",
                  "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf", "0xcd2f22236dd9dfe2356d7c543161d4d260fd9bcb",
                  "0x2028b4043e6722ea164946c82fe806c4a43a0ff4", "0xa32137bfb57d2b6a9fd2956ba4b54741a6d54b58",
                  "0x15e7cac885e3730ce6389447bc0f7ac032f31947", "0xe52b9170ff4ece4c35e796ffd74b57dec68ca0e5",
                  "0x4d140ce792bedc430498c2d219afbc33e2992c9d", "0xa99c4b08201f2913db8d28e71d020c4298f29dbf"}}

def _allow():
    import os as _o
    f = _o.path.join(_o.path.dirname(__file__), "..", "config", "allowlist.txt")
    out = {}
    if _o.path.exists(f):
        for l in open(f):
            l = l.split("#")[0].split()
            if len(l) >= 2: out.setdefault(int(l[0]), set()).add(l[1].lower())
    return out
ALLOWLIST = _allow()   # config/allowlist.txt: "<chain_id> <contract>" per line
def gated(chain): return TRACKED.get(chain, set()) | ALLOWLIST.get(chain, set())
