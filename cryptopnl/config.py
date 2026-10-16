import os
CHAINS = {
  84532: {"name": "base-sepolia", "hypersync": os.environ.get("HYPERSYNC_URL_84532", "https://base-sepolia.hypersync.xyz"),
          "rpc": os.environ.get("SEPOLIA_RPC_URL", "https://sepolia.base.org")},
  8453:  {"name": "base", "hypersync": os.environ.get("HYPERSYNC_URL_8453", "https://base.hypersync.xyz"),
          "rpc": os.environ.get("BASE_RPC_URL", "https://base.drpc.org")},
}
DSN = os.environ.get("CRYPTOPNL_DSN", "dbname=cryptopnl")
HYPERSYNC_RPM = float(os.environ.get("HYPERSYNC_RPM", "7"))   # MBP has no local throttle: self-cap 7/min
RPC_RPS = float(os.environ.get("RPC_RPS", "2"))               # DESIGN §1.2: public RPC <= 2 req/s
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
