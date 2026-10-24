import os
CHAINS = {
  84532: {"name": "base-sepolia", "hypersync": os.environ.get("HYPERSYNC_URL_84532", "https://base-sepolia.hypersync.xyz"),
          "rpc": os.environ.get("SEPOLIA_RPC_URL", "https://sepolia.base.org")},
  8453:  {"name": "base", "hypersync": os.environ.get("HYPERSYNC_URL_8453", "https://base.hypersync.xyz"),
          "rpc": os.environ.get("BASE_RPC_URL", "https://base.drpc.org")},
}
DSN = os.environ.get("CRYPTOPNL_DSN", "dbname=cryptopnl")
HYPERSYNC_MIN_GAP_S = float(os.environ.get("HYPERSYNC_MIN_GAP_S", "12"))   # architect 429 rule: >= 12 s between starts, host-wide
HYPERSYNC_RPM = float(os.environ.get("HYPERSYNC_RPM", "5"))   # architect (PR #3 approval): 5/min for all runs
RPC_RPS = float(os.environ.get("RPC_RPS", "1"))               # architect (PR #1): RPC 1 req/s, burst 3
RPC_BURST = int(os.environ.get("RPC_BURST", "3"))
# P3: host-wide RPC budget (2026-10-17 run: 238 x 429 in 1444 attempts at 1 req/s, burst 3, per process). Conservative default:
# 30 starts / sliding 60 s and >= 1.5 s between starts, all processes on the host (hostlimit.rpc_limiter). Free RPC only.
RPC_RPM = float(os.environ.get("RPC_RPM", "30"))
RPC_MIN_GAP_S = float(os.environ.get("RPC_MIN_GAP_S", "1.5"))
RPC_LOCK_PATH = os.path.expanduser(os.environ.get("RPC_LOCK_PATH", "~/.cache/cryptopnl/rpc.lock"))
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
BUYORDER_PLACE_SELECTORS = {"0x4cc4a386",   # placeERC1155BuyOrder
                            "0x6feecbb5"}   # placeERC721BuyOrder(address,uint256,uint256,uint256,uint256,bool[]) (P2.2 R1; openchain, verified contract)
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
DEFILLAMA_SEARCH_WIDTH = int(os.environ.get("DEFILLAMA_SEARCH_WIDTH", "3600"))   # observed GHST points 6-30 min apart
API_RPS = float(os.environ.get("API_RPS", "1"))
# Confidence label per source (proposal; OPEN QUESTION for the architect). Numbers via CONFIDENCE.
PRICE_LABEL = {"numeraire": "high", "trade_usdc": "high", "dex_direct": "high", "dex_routed": "medium", "defillama": "medium"}

# ---- P2.2 Gotchiverse (DESIGN v1.3 §9). Addresses: allowlist (§7) + craft receipt 0x74f55051… (cost split recipients, RPC).
GV = {8453: {
    "realm": "0x4b0040c3646d3c44b8a28ad7055cfcf536c05372", "installation": "0xebba5b725a2889f7f089a6cae0246a32cad4e26b",
    "tile": "0x617fdb8093b309e4699107f48812b407a7c37938", "gbm": "0x80320a0000c7a6a34086e2acad6915ff57ffda31",
    "aavegotchi": "0xa99c4b08201f2913db8d28e71d020c4298f29dbf", "burn": "0xffffffffffffffffffffffffffffffffffffffff",
    "pixelcraft": "0x50def14c51123660f8768b511b93cc8c09f30356", "dao": "0x939b67f6f6be63e09b0258621c5a24eecb92631c",
    "ghst": "0xcd2f22236dd9dfe2356d7c543161d4d260fd9bcb", "gltr": "0x4d140ce792bedc430498c2d219afbc33e2992c9d",
    "alchemica": {"0x2028b4043e6722ea164946c82fe806c4a43a0ff4", "0xa32137bfb57d2b6a9fd2956ba4b54741a6d54b58",
                  "0x15e7cac885e3730ce6389447bc0f7ac032f31947", "0xe52b9170ff4ece4c35e796ffd74b57dec68ca0e5"},
    # Aerodrome FUD/GHST volatile pool (PoolFactory.getPool(FUD, GHST, false)); the pool is its own LP token. NOT a router (§9 R10 correction)
    "aero_fud_ghst_pool": "0xeae2fb93e291c2eb69195851813de24f97f1ce71",
    # widened R10 (architect, 2026-10-22): allowlisted pricing pools (swaps through them are swaps) and LP staking contracts (the GLTR staking farm; config key lp_gauges kept).
    "pricing_pools": ["0xeae2fb93e291c2eb69195851813de24f97f1ce71"],   # Aerodrome FUD/GHST (PoolFactory.getPool(FUD, GHST, false))
    # 0xab449dca… = Aavegotchi GLTR staking farm (Diamond; reward token getter 0xf7c618c1 -> GLTR; deposit(pid, amount) 0xe2bbb158).
    # Read-only check 2026-10-22: Aerodrome Voter 0x16613524….gauges(pool) = 0x0 and isGauge(0xab449dca…) = false, so it is not an Aerodrome gauge.
    "lp_gauges": ["0xab449dca14413a6ae0bcea9ea210b57ace280d2c"],
    # LP tokens of other pools staked in the farm (read-only 2026-10-23: symbol() = vAMM-FOMO/GHST, token0 FOMO, token1 GHST; tx 0x89d68cf4…)
    "farm_lp_tokens": ["0x62ab7d558a011237f8a57ac0f97601a764e85b88"],
    # alchemicaCost[4] order of the type getters (symbol() on Base): FUD, FOMO, ALPHA, KEK
    "alchemica_order": ["0x2028b4043e6722ea164946c82fe806c4a43a0ff4", "0xa32137bfb57d2b6a9fd2956ba4b54741a6d54b58",
                        "0x15e7cac885e3730ce6389447bc0f7ac032f31947", "0xe52b9170ff4ece4c35e796ffd74b57dec68ca0e5"],
    "start_block": 33_200_000}}
# Selectors (openchain signature DB, verified-contract flag; ABIs of the Installation/Tile/REALM diamonds)
# craft/claim/reduce selectors verified live on Base 2026-10-17 via DiamondLoupe facetAddress(bytes4) (eth_call, latest) + openchain names
GV_SEL = {"craft": {"0x9ff2a527", "0x976a1afe",           # craftInstallations(uint16[],uint40[]), craftTiles(uint16[])
                    "0xe9332638", "0xfdc6d919"},          # batchCraftInstallations((uint16,uint16,uint40)[]) [Installation], batchCraftTiles(...) [Tile]
          "craft_claim": {"0x763b948a", "0xa185cc01"},    # claimInstallations(uint256[]) [Installation], claimTiles(uint256[]) [Tile]
          "craft_reduce": {"0xe0d20147"},                 # reduceCraftTime(uint256[],uint40[]) [both]; GLTR burnFrom -> 0x0 is craft cost
          "claim_alchemica": {"0x9fefe547", "0x8027870e"},   # claimAvailableAlchemica(uint256,uint256,bytes), channelAlchemica(uint256,uint256,uint256,bytes)
          # gotchi pocket (escrow) custody on the Aavegotchi diamond: depositERC20(uint256,address,uint256), transferEscrow(uint256,address,address,uint256),
          # batchTransferEscrow(uint256[],address[],address[],uint256[]) (all live, facetAddress check)
          "pocket": {"0xb0facab3", "0xab0fcabf", "0x2a206f11"}}
# craft type cost getters (#27 split rule): selector, index of alchemicaCost[0] in the returned words (word 0 = tuple offset 0x20).
# Verified 2026-10-17 (eth_call, Base): getInstallationType(56) at block 48,779,183 = [125 FUD, 63 FOMO, 0, 0] = the inputs of real craft
# 0x74f55051…; types 10 and 145 cost 0 (the real free crafts); getTileType is live on the Tile diamond (facetAddress).
TYPE_COST_GETTER = {"installation": ("0x42784f14", 12),   # getInstallationType(uint256) -> (...11 fields, uint256[4] alchemicaCost, ...)
                    "tile": ("0xe042161f", 6)}            # getTileType(uint256) -> (width, height, deprecated, tileType, craftTime, uint256[4] alchemicaCost, name)
GOTCHI_ESCROW_SEL = "0xa8e39da0"   # gotchiEscrow(uint256) -> address; RPC-verified: gotchiEscrow(3033) = 0x728f0baf79ebdfa336978c90f244324a0ba7bcff
# topic0 -> event name (keccak of the ABI signatures; DESIGN §9 prefixes match: 0x0f52fde6…, 0x6d10597e…)
GV_TOPICS = {
    "0x0f52fde6171d45c02579364597406652690bf2264e564ba1a5b88ffa98d8815b": "ERC721ExecutedToRecipient",   # (listingId*, buyer*, recipient*)
    "0x6d10597eaea3b6f10739896c93a2cdebf87810d37226b40bc3e433745f55ce9c": "ERC1155ExecutedToRecipient",
    "0x427c7dcdefdb1654e9ab491c1fc9a1f83a16e79968042c8bb54873541173a656": "ERC721BuyOrderAdded",        # (buyOrderId*, buyer*, ...)
    "0xb89a3fa09a6b61b06fa0f16a43b319ca184062389055411b6e698cabdf7e9edc": "ERC1155BuyOrderAdd",
    "0x2c10b67d57c65fd2fc6cc56eba63f4c5c704a09abf5aa54cec0753bfeda09c56": "ERC721BuyOrderCanceled",
    "0xa3bcfada5116fec4553cde6319984603d411a22d1b646957d5734b77693c6cd7": "ERC1155BuyOrderCancel",
    "0x76575e9201a7a7a387d15babed3e4c37a179e1a368c8482288251d52401ff584": "AddedToQueue",               # (queueId*, itemId*, readyBlock, sender)
    "0xe8a0b83f7c7560add63dd9f946f59e35fb72430cb395889f4369ba19b91e0319": "QueueClaimed",               # (queueId*)
    "0xb7907a81902fa66f0a79bc78a88097437c835502cb688cf0559b052db41d67b6": "CraftTimeReduced",           # (queueId*, blocks)
    "0x07d6dfde038acc4db278bc4333a59375b806deec664e469c6b09f17a73bafade": "MintInstallations",          # (owner*, installationId*, uint16 amount)
    "0xf2bd7a0a4587b4c000ee36ad5681c67c7fcad9d00a80bf975ac2e315f8577c4d": "MintInstallation",
    "0xcf4ec29a21df4a833e09008384c100f3bde71017c3868dd3b89e2d4b86dc5ffc": "MintTiles",                  # (owner*, tileId*, uint16 amount)
    "0x51657e5528e26561636ff2e150a205acc5869437fe7f681f906a95887e3f0eac": "MintTile",                   # (owner*, tileType*, tileId) [claim: data = queue id]
    "0xf1e7ab6f403ab027329be55c1aa82c8c92c513aae2a27fc0bbaaa03b0dd8f12a": "UpgradeQueued",              # (owner*, realmId*, queueIndex*)
    "0xff977a48e6ed060e1323f331b58d75fed1eadb4dac3e3bdb86664ea6a9f4354e": "UpgradeInitiated",           # (realmId*, x, y, blockInitiated, readyBlock, installationId)
    "0xb68ab7bf9a62eca632e4af52e2ab71db327c9abb6b5cee91ee23afb32cf40e27": "UpgradeQueueFinalized",     # 0xb68ab7bf (owner, realmId, queueIndex); indexing assumed like UpgradeQueued (unverified)
    "0xe2e4b3bcba1b8d227ae00a114468153a60fad154306154b2ff1e67325cc48315": "UpgradeFinalized",           # (realmId*, x, y, newInstallationId)
    "0x395d9a08b897acfa143a6e0de3173b720402b3f2829112ef5deadbaf1f212e25": "UpgradeTimeReduced",         # (queueId*, realmId*, x, y, blocks)
    "0x74b654614ea2444b876a14dec11c709807cda89060906c4b7e443e4f8ff9ed53": "InstallationUpgraded",       # REALM: (realmId, prevId, nextId, x, y)
    "0xe82810099d182b25e23e895715954d6e7b41867a02e2c693cce68a8f250e43d3": "TransferToParent",           # (toContract*, toTokenId*, typeId*, value)
    "0x4b287e36a0531da8ccee303de127c778302f48d8fc9569b1fe1dcb9d64465c6d": "TransferFromParent",
    "0x1eba211322935090f825dc2d5b300150db5078adc958f33161f7ea7a1d3026f0": "EventStarted",               # REALM bounce gate (eventId*)
    "0x84f9e476fba70c0e0d8226ab52049ddac7b38ea188e785c45831b91832877af8": "EventPriorityAndDurationUpdated",   # REALM bounce gate update (eventId*, priority, endTime)
    "0xdb9cc99dc874f9afbae71151f737e51547d3d412b52922793437d86607050c3c": "AuctionCancelled",           # GBM (auctionId*, tokenId)
    "0x67725b3b5836354867e57ef59784870b52a0b07f53c7f0b41fefc726225f5bfb": "GotchiLendingExecuted",      # (listingId*, lender*, borrower*, ...)
    "0x2240d94f92369c7722021a9f6158fa5577eedeae5191c5ce9fbcc9c66fe4a7ce": "GotchiLendingEnded",
    "0xee31c7b8017a392ce3690715faeb5c45ec46dc3483ea25d4b62e6f680cd878b3": "GotchiLendingClaimed",
    "0x19f483d7b19be804210fad17c0ccb74c8e82f575ed3de6a498f4d12e36a4263a": "GotchiLendingExecutedT",     # tuple versions (no indexed fields)
    "0x6c3cd77eda2c6ff7d015d27dadcdadb382c298ab604fda85d72cef7711478ca5": "GotchiLendingEndedT",
    "0x23e3c7705ebea1f89164a677cb2117a22a29cd757523cff32fc5fb52d5dbb769": "GotchiLendingClaimedT"}
