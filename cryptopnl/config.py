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

# P2 review (DESIGN v1.2 §8). Escrow diamonds: GHST sent here on order placement / bid is custody (escrow_out).
ESCROW = {8453: {"baazaar": "0xa99c4b08201f2913db8d28e71d020c4298f29dbf", "gbm": "0x80320a0000c7a6a34086e2acad6915ff57ffda31"}}
# Baazaar buy-order placement selectors (observed: 0x4cc4a386 in 0x2a01e94f…5cc8, which emits ERC1155BuyOrderAdd id 327
# per Blockscout logs). The BuyOrderAdd/Cancel events are not ingested yet; fills link to escrow by FIFO amount + order id.
BUYORDER_PLACE_SELECTORS = {"0x4cc4a386"}
# Polygon->Base re-mints (architect, PR #3 decisions): migration_in = tx.from in {bridge sender, the wallet itself}
# AND an NFT mint from 0x0 to the wallet of an allowlisted Aavegotchi contract AND (tx.to, selector) on the per-asset list.
# The bridge sender calling an unlisted selector -> review. The block window is only an assertion (warning when outside).
# Selectors: RPC eth_getTransactionByHash of the 9 Base re-mints; 0xf55b061c = mintAavegotchiBridged((address,uint256[])[])
# per Blockscout decoded_input of 0x1f6395ee…60c2. Bridge sender per Blockscout `from` of the same tx.
MIGRATION_REMINT = {8453: {
    "bridge_sender": "0xf52398257a254d541f392667600901f710a006ed", "chain_origin": 137, "window": (33_200_000, 34_000_138),
    "selectors": {  # selector -> tx.to (target)
        "0xf55b061c": "0xa99c4b08201f2913db8d28e71d020c4298f29dbf",   # Aavegotchi Diamond: mintAavegotchiBridged (gotchis)
        "0xfd7499bd": "0xa99c4b08201f2913db8d28e71d020c4298f29dbf",   # wearables (minted by the Wearable Diamond, called via Aavegotchi Diamond)
        "0x506ccb27": "0x50af2d63b839aa32b4166fd1cb247129b715186c",   # Forge
        "0x0d51a188": "0x4b0040c3646d3c44b8a28ad7055cfcf536c05372",   # REALM
        "0x9110d148": "0xebba5b725a2889f7f089a6cae0246a32cad4e26b",   # Installations
        "0x91b06c6e": "0x617fdb8093b309e4699107f48812b407a7c37938",   # Tiles
        "0x5e41ee65": "0xab59ca4a16925b0a4bac5026c94beb20a29df479"},  # FAKE Gotchis mintBatch: THIS contract only (architect, 3c8b056)
    "contracts": {"0xa99c4b08201f2913db8d28e71d020c4298f29dbf", "0x052e6c114a166b0e91c2340370d72d4c33752b4b",
                  "0x50af2d63b839aa32b4166fd1cb247129b715186c", "0x4b0040c3646d3c44b8a28ad7055cfcf536c05372",
                  "0xebba5b725a2889f7f089a6cae0246a32cad4e26b", "0x617fdb8093b309e4699107f48812b407a7c37938",
                  "0xab59ca4a16925b0a4bac5026c94beb20a29df479"}}}   # + FakeGotchisNFTDiamond (getCode 4619 B, name "FAKE Gotchis", ERC721)
# Circle CCTP on Base (domain 6), official docs fetched 2026-10-16. bridge_in requires tx.to in this set.
#  V1 (legacy) https://developers.circle.com/cctp/v1/evm-smart-contracts : TokenMessenger 0x1682Ae63…8962, MessageTransmitter 0xAD09780d…F9D4
#  V2 https://developers.circle.com/cctp/references/contract-addresses  : TokenMessengerV2 0x28b5a0e9…cf5d, MessageTransmitterV2 0x81D40F21…4B64
# Only the MessageTransmitters (they call mint on receiveMessage); TokenMessengers dropped (architect, 3c8b056).
#  V1 MessageTransmitter: https://developers.circle.com/cctp/v1/evm-smart-contracts
#  V2 MessageTransmitterV2: https://developers.circle.com/cctp/references/contract-addresses
CCTP = {8453: {"0xad09780d193884d503182ad4588450c416d6f9d4", "0x81d40f21f12a8f0e3252bccb954d722d4c464b64"}}
CCTP_TOKENS = {8453: {"0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": 6}}   # USDC (Circle-minted) -> decimals for the par basis
CONFIDENCE = {"high": 1.0, "medium": 0.6, "low": 0.2}   # label -> number (architect, PR #3)
MANUAL_CONFIDENCE = 0.2   # = CONFIDENCE["low"] (DESIGN §8 manual basis)
