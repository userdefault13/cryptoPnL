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

# Gated assets live in config/allowlist.txt (architect review on PR #1).

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
def gated(chain): return ALLOWLIST.get(chain, set())

# P1.1 wearables: one asset per chain; ERC1155 events counted only from `emitter`, reported under `canonical`
# (holds balanceOf/balanceOfToken + emits TransferToParent/FromParent). `aliases` = mirrored contracts.
WEARABLES = {
  8453:  {"canonical": "0xa99c4b08201f2913db8d28e71d020c4298f29dbf", "emitter": "0x052e6c114a166b0e91c2340370d72d4c33752b4b",
          "aliases": ["0x052e6c114a166b0e91c2340370d72d4c33752b4b"], "parent": "0xa99c4b08201f2913db8d28e71d020c4298f29dbf"},
  # Sepolia: none. 0x4773f06f…ff64b / 0xb2d52be3…554a1 are Installation-type diamonds, not wearables (architect,
  # DESIGN v1.1 §7); excluded from the Sepolia pass criterion.
}

# Base Aavegotchi migration (first gotchi/wearable activity on Base); start of the time-spread verify samples.
MIGRATION_BLOCK = {8453: 33_200_000}

# Fixed untracked reasons (architect decisions) that override the heuristic in verify.reason().
UNTRACKED_REASONS = {84532: {"0x4773f06fb66735f1350a2db582660cbf6c0ff64b": "non-event balance changes (testnet)",
                             "0xb2d52be3ab11006685843a59ec7d17bff2c554a1": "non-event balance changes (testnet)"}}

# P2: DEX routers. A wallet tx through one of these with fungible out and nothing in is most likely a swap into native ETH
# paid back as an internal transfer (not indexed, DESIGN §1 "internal ETH gap") -> review queue, never "withdrawal".
DEX_ROUTERS = {8453: {"0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad",   # Uniswap Universal Router (blockscout-verified name)
                      "0x6ff5693b99212da76ad316178a184ab56d299b43",   # Uniswap Universal Router v4
                      "0xfdf682f51fe81aa4898f0ae2163d8a55c127fbc7",   # Uniswap v4 UniversalRouterV2.1.1 (blockscout tag, P2 hand check)
                      "0xcf77a3ba9a5ca399b7c97c74d54e5b1beb874e43",   # Aerodrome Router
                      "0x6cb442acf35158d5eda88fe602221b67b400be3e"}}  # Aerodrome Universal Router
