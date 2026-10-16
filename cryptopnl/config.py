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

# Gated assets live in config/allowlist.txt (architect review on PR #1). TRACKED kept empty for compatibility.
TRACKED = {}

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

# P1.1 wearables: one asset per chain; ERC1155 events counted only from `emitter`, reported under `canonical`
# (holds balanceOf/balanceOfToken + emits TransferToParent/FromParent). `aliases` = mirrored contracts.
WEARABLES = {
  8453:  {"canonical": "0xa99c4b08201f2913db8d28e71d020c4298f29dbf", "emitter": "0x052e6c114a166b0e91c2340370d72d4c33752b4b",
          "aliases": ["0x052e6c114a166b0e91c2340370d72d4c33752b4b"], "parent": "0xa99c4b08201f2913db8d28e71d020c4298f29dbf"},
  # Sepolia: none. 0x4773f06f…ff64b / 0xb2d52be3…554a1 are Installation-type diamonds, not wearables (architect,
  # DESIGN v1.1 §7); excluded from the Sepolia pass criterion.
}
