import os
CHAINS = {
  84532: {"name": "base-sepolia", "hypersync": os.environ.get("HYPERSYNC_URL_84532", "https://base-sepolia.hypersync.xyz"),
          "rpc": os.environ.get("SEPOLIA_RPC_URL", "https://sepolia.base.org")},
  8453:  {"name": "base", "hypersync": os.environ.get("HYPERSYNC_URL_8453", "https://base.hypersync.xyz"),
          "rpc": os.environ.get("BASE_RPC_URL", "https://base.drpc.org")},
}
DSN = os.environ.get("CRYPTOPNL_DSN", "dbname=cryptopnl")
HYPERSYNC_RPM = float(os.environ.get("HYPERSYNC_RPM", "5"))   # architect (PR #3 approval): 5/min for all runs
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
        "0x5e41ee65": "0xab59ca4a16925b0a4bac5026c94beb20a29df479",   # FAKE Gotchis mintBatch: THIS contract only (architect, 3c8b056)
        "0x88f351bb": "0xe46b8902dad841476d9fee081f1d62ae317206a9"},  # FAKE Gotchi Cards massMint: THIS contract only (P2.1)
    "contracts": {"0xa99c4b08201f2913db8d28e71d020c4298f29dbf", "0x052e6c114a166b0e91c2340370d72d4c33752b4b",
                  "0x50af2d63b839aa32b4166fd1cb247129b715186c", "0x4b0040c3646d3c44b8a28ad7055cfcf536c05372",
                  "0xebba5b725a2889f7f089a6cae0246a32cad4e26b", "0x617fdb8093b309e4699107f48812b407a7c37938",
                  "0xab59ca4a16925b0a4bac5026c94beb20a29df479",   # + FakeGotchisNFTDiamond (getCode 4619 B, name "FAKE Gotchis", ERC721)
                  "0xe46b8902dad841476d9fee081f1d62ae317206a9"}}}   # + FakeGotchisCardDiamond (getCode 4619 B, ERC165 ERC1155, no name(), uri(0)="0"; P2.1)
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

# ---- P3 pricing (DESIGN v1.2 §2). Pools found by read-only factory calls (verify/p3_pools.py, docs/evidence/p3_pools_latest.jsonl).
# Numeraire (architect ruling on KNOWN_GAPS #16): native Circle USDC only. USDbC / any bridged or wrapped USDC is NOT par.
NUMERAIRE = {8453: "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"}   # P6: Polygon native USDC also numeraire; USDC.e = pool price
USDBC = {8453: "0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca"}       # bridged USDbC: pool/API price, never par (test)
WETH = {8453: "0x4200000000000000000000000000000000000006"}
TOKENS = {8453: {   # contract -> (symbol, decimals); decimals read on-chain (decimals()) during pool discovery / DefiLlama metadata
    "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": ("USDC", 6), "0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca": ("USDbC", 6),
    "0x4200000000000000000000000000000000000006": ("WETH", 18), "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf": ("cbBTC", 8),
    "0xcd2f22236dd9dfe2356d7c543161d4d260fd9bcb": ("GHST", 18), "0x2028b4043e6722ea164946c82fe806c4a43a0ff4": ("FUD", 18),
    "0xa32137bfb57d2b6a9fd2956ba4b54741a6d54b58": ("FOMO", 18), "0x15e7cac885e3730ce6389447bc0f7ac032f31947": ("ALPHA", 18),
    "0xe52b9170ff4ece4c35e796ffd74b57dec68ca0e5": ("KEK", 18), "0x4d140ce792bedc430498c2d219aafbc33e2992c9d": ("GLTR", 18)}}
# asset -> ordered pools [(kind, pool, quote)]. kind: v3 (Uniswap V3 / Aerodrome Slipstream slot0) | v2 (Aerodrome getReserves).
# WETH/cbBTC: Uni V3 0.05% USDC pool (DESIGN §2, decided). GHST: deepest USDC pools, then GHST/WETH (routed). Alchemica: their only
# pools (Aerodrome v2 vs GHST; routed via GHST). GLTR: no pool vs USDC/WETH/GHST on these factories -> API or no_price.
PRICE_POOLS = {8453: {
    "0x4200000000000000000000000000000000000006": [("v3", "0xd0b53d9277642d899df5c87a3966a349a798f224", "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913")],
    "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf": [("v3", "0xfbb6eed8e7aa03b138556eedaf5d271a5e1e43ef", "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913")],
    "0xcd2f22236dd9dfe2356d7c543161d4d260fd9bcb": [("v3", "0x41d4934322f2bd6fe1dbe4124070fe61651a2067", "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"),
                                                   ("v3", "0x56c11053159a24c0731b4b12356bc1f0578fb474", "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"),
                                                   ("v2", "0x0dfb9cb66a18468850d6216fcc691aa20ad1e091", "0x4200000000000000000000000000000000000006")],
    "0x2028b4043e6722ea164946c82fe806c4a43a0ff4": [("v2", "0xeae2fb93e291c2eb69195851813de24f97f1ce71", "0xcd2f22236dd9dfe2356d7c543161d4d260fd9bcb")],
    "0xa32137bfb57d2b6a9fd2956ba4b54741a6d54b58": [("v2", "0x62ab7d558a011237f8a57ac0f97601a764e85b88", "0xcd2f22236dd9dfe2356d7c543161d4d260fd9bcb")],
    "0x15e7cac885e3730ce6389447bc0f7ac032f31947": [("v2", "0x0ba2a49aedf9a409dbb0272db7cdf98aeb1e1837", "0xcd2f22236dd9dfe2356d7c543161d4d260fd9bcb")],
    "0xe52b9170ff4ece4c35e796ffd74b57dec68ca0e5": [("v2", "0x699b4eb36b95cdf62c74f6322aaa140e7958dc9f", "0xcd2f22236dd9dfe2356d7c543161d4d260fd9bcb")]}}
# Reject a pool at a block when its quote-side reserve is worth less than this (DESIGN §2 "liquidity threshold"; value = OPEN QUESTION).
DEX_MIN_QUOTE_USD = float(os.environ.get("DEX_MIN_QUOTE_USD", "1000"))
# DefiLlama: free, no key. searchWidth (s) = max distance of the API point from the tx time (OPEN QUESTION; conservative default).
DEFILLAMA_URL = os.environ.get("DEFILLAMA_URL", "https://coins.llama.fi")
DEFILLAMA_SEARCH_WIDTH = int(os.environ.get("DEFILLAMA_SEARCH_WIDTH", "600"))
API_RPS = float(os.environ.get("API_RPS", "1"))
# Confidence label per source (proposal; OPEN QUESTION for the architect). Numbers via CONFIDENCE.
PRICE_LABEL = {"numeraire": "high", "trade_usdc": "high", "dex_direct": "high", "dex_routed": "medium", "defillama": "medium"}
