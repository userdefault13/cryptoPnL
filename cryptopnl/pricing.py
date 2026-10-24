"""P3 pricing (DESIGN v1.3 §2 + §8 'P3 rulings'). price(asset, block): numeraire -> on-chain DEX at block (>= liquidity floor) ->
thin-pool assets (alchemica, GLTR): thin pool below the floor with a swap <= 7 d old (low, flagged) -> else unpriced. There is NO API
step in the price order (ruling, PR #7 review): DefiLlama is only the reference for the ±3% GHST check in sample(). Every DEX price
records the pool's USD depth (detail.pool_depth_usd). Trade-implied prices are applied per ledger trade group in price_ledger().
Read-only: eth_call at the block over the free public RPC through the host RPC budget (30 req/min, >= 1.5 s gap, shared 429 back-off)
and DefiLlama GET (free, no key, 1 req/s). The thin-pool Swap scan (ingest.ingest_pool_swaps) uses HyperSync (5/min, 12 s gap); this
module only reads its cache. Never invents a price: no source -> None -> ledger flag 'no_price'.
Every price is a UNIT price in USDC per whole token (decimals applied)."""
import json
from decimal import Decimal, getcontext
from .config import (NUMERAIRE, TOKENS, PRICE_POOLS, DEX_MIN_QUOTE_USD, DEFILLAMA_URL, DEFILLAMA_SEARCH_WIDTH, API_RPS,
                     PRICE_LABEL, CONFIDENCE, WETH, gated, THIN_POOL_ASSETS, THIN_ONLY_ASSETS, THIN_SWAP_WINDOW_BLOCKS, NO_PRICE_SOURCE, DEV_GATED_ASSETS)
import bisect
from .net import Limiter, post_json
getcontext().prec = 50
Q96 = Decimal(2) ** 96

def a32(a): return a[2:].rjust(64, "0")
def word(r, i): return int(r[2 + 64 * i: 2 + 64 * (i + 1)], 16)

class Price(tuple):
    """(price Decimal, source, label, detail dict)"""
    def __new__(cls, p, src, label, detail=None): return super().__new__(cls, (Decimal(p), src, label, detail or {}))
    price = property(lambda s: s[0]); source = property(lambda s: s[1]); label = property(lambda s: s[2]); detail = property(lambda s: s[3])

class DefiLlama:
    name = "defillama"
    def __init__(self, chain_prefix="base"):
        self.lim = Limiter(API_RPS, 1); self.prefix = chain_prefix; self.cache = {}
    def prices(self, ts, contracts):
        """{contract: (price, api_ts)} for the coins DefiLlama has within DEFILLAMA_SEARCH_WIDTH of ts. One GET per ts (cached)."""
        key = (ts, tuple(sorted(contracts)))
        if key not in self.cache:
            coins = ",".join(f"{self.prefix}:{c}" for c in sorted(contracts))
            r = post_json("defillama", self.lim, f"{DEFILLAMA_URL}/prices/historical/{int(ts)}/{coins}?searchWidth={DEFILLAMA_SEARCH_WIDTH}", None)
            out = {}
            for k, v in (r.get("coins") or {}).items():
                if v.get("price") is not None and abs(int(v.get("timestamp", 0)) - int(ts)) <= DEFILLAMA_SEARCH_WIDTH:
                    out[k.split(":", 1)[1].lower()] = (Decimal(str(v["price"])), int(v["timestamp"]))
            self.cache[key] = out
        return self.cache[key]

class Pricer:
    def __init__(self, chain, rpc, api=None, swaps=None):
        self.chain, self.rpc, self.api = chain, rpc, api
        self.swaps = swaps or {}                     # pool -> (sorted swap blocks, scanned_from, scanned_to) from pool_swap (HyperSync)
        self.thin_assets = THIN_POOL_ASSETS.get(chain, set()); self.thin_only = THIN_ONLY_ASSETS.get(chain, set()); self.thin_cand = {}
        self.tok = TOKENS.get(chain, {}); self.pools = PRICE_POOLS.get(chain, {}); self.num = NUMERAIRE.get(chain)
        self.weth = WETH.get(chain); self.memo = {}; self.calls = 0
        self.status = {}; self.rpc_errors = []; self.err_blocks = set()   # per (to, data, block): ok | revert | empty | error
        self.fallthrough = []     # DEX prices taken from a later pool after an RPC error on an earlier pool (evidence, see dex())
    def dec(self, c): return self.tok[c][1]
    def _call(self, to, data, block):
        """eth_call or None. Only a JSON-RPC 'execution reverted' is a revert (pool not usable at the block). Any other error (JSON-RPC
        errors arrive as HTTP 200 and raise RuntimeError in sources.RPC.call, e.g. rate/limit/upstream errors) is recorded in
        rpc_errors / err_blocks so unpriced_reason() reports rpc_error (fails C1) instead of no_pool."""
        self.calls += 1; k = (to, data, block)
        try: r = self.rpc.eth_call(to, data, block)
        except RuntimeError as e:
            if "execution reverted" in str(e).lower(): self.status[k] = "revert"; return None
            self.status[k] = "error"; self.err_blocks.add(block)
            self.rpc_errors.append({"to": to, "selector": data[:10], "block": block, "error": str(e)[:200]}); return None
        if r and r != "0x" and len(r) >= 66: self.status[k] = "ok"; return r
        self.status[k] = "empty"; return None
    def _absent(self, to, data, block):
        """Why a pool call gave no usable result: no_pool only on 'execution reverted' or when eth_getCode(pool) at the block is 0x;
        rpc_error on any other RPC error; bad_response when the pool has code but returned nothing usable."""
        st = self.status.get((to, data, block))
        if st == "revert": return "no_pool"
        if st == "error": return "rpc_error"
        try: self.calls += 1; code = self.rpc.call("eth_getCode", [to, hex(block)])
        except RuntimeError as e:
            self.err_blocks.add(block); self.rpc_errors.append({"to": to, "selector": "getCode", "block": block, "error": str(e)[:200]})
            return "rpc_error"
        return "no_pool" if code in (None, "", "0x", "0x0") else "bad_response"
    def token_balance(self, token, pool, block):
        r = self._call(token, "0x70a08231" + a32(pool), block)
        return None if r is None else Decimal(word(r, 0)) / 10 ** self.dec(token)

    def pool_price(self, kind, pool, asset, quote, block):
        """Price of 1 asset in quote units from pool state at block, or None. Tokens are sorted (token0 = lower address)."""
        a0 = asset.lower() < quote.lower()
        d0, d1 = (self.dec(asset), self.dec(quote)) if a0 else (self.dec(quote), self.dec(asset))
        if kind == "v3":
            r = self._call(pool, "0x3850c7bd", block)                 # slot0(): sqrtPriceX96 first (Uni V3 and Slipstream)
            if not r or word(r, 0) == 0: return None
            p01 = (Decimal(word(r, 0)) / Q96) ** 2 * (Decimal(10) ** (d0 - d1))   # token1 per token0, whole units
        else:
            r = self._call(pool, "0x0902f1ac", block)                 # getReserves(): reserve0, reserve1
            if not r or word(r, 0) == 0 or word(r, 1) == 0: return None
            p01 = (Decimal(word(r, 1)) / 10 ** d1) / (Decimal(word(r, 0)) / 10 ** d0)
        return p01 if a0 else 1 / p01

    def quote_reserve(self, pool, quote, block):
        r = self._call(quote, "0x70a08231" + a32(pool), block)       # balanceOf(pool) at block
        return None if r is None else Decimal(word(r, 0)) / 10 ** self.dec(quote)

    def dex(self, asset, block, _depth=0):
        """On-chain DEX price at block (DESIGN §2 step 2). Direct USDC pool -> 'dex_direct'; via WETH/GHST -> 'dex_routed'."""
        k = ("dex", asset, block)
        if k in self.memo: return self.memo[k]
        res = None
        if asset == self.num: res = Price(1, "numeraire", PRICE_LABEL["numeraire"])
        elif _depth < 3:
            skipped = []          # earlier pools that did not give a price, with the reason (status of the failing call)
            for kind, pool, quote in self.pools.get(asset, []):
                sel = "0x3850c7bd" if kind == "v3" else "0x0902f1ac"
                px = self.pool_price(kind, pool, asset, quote, block)
                if px is None or px <= 0: skipped.append({"pool": pool, "why": self.status.get((pool, sel, block), "zero")}); continue
                qp = Price(1, "numeraire", "high") if quote == self.num else self.dex(quote, block, _depth + 1)
                if qp is None: skipped.append({"pool": pool, "why": "quote_unpriced"}); continue
                reserve = self.quote_reserve(pool, quote, block)
                if reserve is None or reserve <= 0:
                    skipped.append({"pool": pool, "why": self.status.get((quote, "0x70a08231" + a32(pool), block), "zero") if reserve is None else "zero"}); continue
                qusd = reserve * qp.price
                # pool USD depth: v2 (constant product) = 2 x quote-side reserve at spot; v3/Slipstream = quote-side balance (lower bound)
                depth = qusd * 2 if kind == "v2" else qusd
                dd = {"pool": pool, "kind": kind, "quote": quote, "block": block, "quote_reserve_usd": str(round(qusd, 2)),
                      "pool_depth_usd": str(round(depth, 2)), "depth_method": "2x_quote_reserve" if kind == "v2" else "quote_balance",
                      "floor_usd": DEX_MIN_QUOTE_USD}
                if qusd < Decimal(str(DEX_MIN_QUOTE_USD)) or asset in self.thin_only:      # liquidity floor (GLTR: thin tier only)
                    skipped.append({"pool": pool, "why": "below_floor"})
                    if kind == "v3":                       # v3/Slipstream thin pool: both token balances must be > 0 (v2: getReserves)
                        ab = self.token_balance(asset, pool, block)
                        if ab is None or ab <= 0: continue
                    self.thin_cand.setdefault((asset, block), (px * qp.price, kind, qp, dict(dd, below_floor=True)))
                    continue
                direct = quote == self.num
                lab = PRICE_LABEL["dex_direct"] if direct else min(PRICE_LABEL["dex_routed"], qp.label, key=lambda l: CONFIDENCE[l])
                route = [pool] + ([] if direct else qp.detail.get("route", []))
                det = dict(dd, route=route, direct=direct, quote_detail=None if direct else qp.detail)
                if skipped: det["skipped_pools"] = skipped
                res = Price(px * qp.price, "dex_slot0" if kind == "v3" else "dex_reserves", lab, det)
                if any(x["why"] == "error" for x in skipped):
                    self.fallthrough.append({"asset": asset, "block": block, "used_pool": pool, "skipped_pools": skipped})
                break
        self.memo[k] = res; return res

    def api_price(self, asset, ts):
        if not self.api or asset not in self.tok: return None
        got = self.api.prices(ts, [c for c in self.tok if c != self.num]).get(asset)
        if not got: return None
        return Price(got[0], "defillama", PRICE_LABEL["defillama"], {"api_ts": got[1]})

    def thin(self, asset, block):
        """Ruling step 3: a pool below the floor (both reserves > 0, priced via a quote at/above the floor) with a Swap log in
        (block - 7 d, block] per the cached HyperSync scan. Low confidence. None when the scan does not cover the block."""
        c = self.thin_cand.get((asset, block))
        if not c: return None
        px, kind, qp, dd = c; sw = self.swaps.get(dd["pool"])
        if not sw or sw[2] < block or sw[1] > block - THIN_SWAP_WINDOW_BLOCKS: return None
        bl = sw[0]; i = bisect.bisect_right(bl, block)
        last = bl[i - 1] if i else None
        if last is None or block - last >= THIN_SWAP_WINDOW_BLOCKS: return None
        return Price(px, "dex_reserves_thin", "low", dict(dd, last_swap_block=last, swap_window_blocks=THIN_SWAP_WINDOW_BLOCKS,
                     route=[dd["pool"]] + qp.detail.get("route", []), quote_detail=qp.detail, quote_price=str(qp.price)))

    def unpriced_reason(self, asset, block):
        """C1 ruling (PR #7, 2026-10-23): why (asset, block) is unpriced, after price() returned None (uses the dex() memo / thin
        candidates of that call). Accepted (machine-checkable) codes: stale_pool (thin pool, both reserves > 0, last Swap >= 7 d before
        the block per the cached scan; last_swap_block + age), no_pool (no configured pool, or the pool has no code / reverts at the block),
        zero_reserves (a reserve or a token balance is 0). no_pool needs 'execution reverted' or eth_getCode = 0x (see _absent).
        Anything else (rpc_error, bad_response, swap_scan_gap, quote_unpriced, below_floor_not_thin_tier, unexplained) is NOT
        accepted and fails C1. Any RPC error at the block while pricing -> rpc_error (conservative)."""
        a = self.weth if asset in (None, "native") else asset.lower()
        pools = self.pools.get(a, [])
        if not pools: return {"reason": "no_pool"}
        if block in self.err_blocks:
            return {"reason": "rpc_error", "errors": [e for e in self.rpc_errors if e["block"] == block][:5]}
        c = self.thin_cand.get((a, block))
        if c:
            dd = c[3]; pool = dd["pool"]
            if a not in self.thin_assets: return {"reason": "below_floor_not_thin_tier", "pool": pool}
            sw = self.swaps.get(pool)
            if not sw or sw[2] < block or sw[1] > block - THIN_SWAP_WINDOW_BLOCKS:
                return {"reason": "swap_scan_gap", "pool": pool, "scan": None if not sw else [sw[1], sw[2]]}
            i = bisect.bisect_right(sw[0], block); last = sw[0][i - 1] if i else None
            if last is not None and block - last < THIN_SWAP_WINDOW_BLOCKS: return {"reason": "unexplained", "pool": pool, "last_swap_block": last}
            lb = last is None                      # no swap in the scanned range: age >= block - scan_from (a lower bound)
            age = block - (sw[1] if lb else last)
            return {"reason": "stale_pool", "pool": pool, "last_swap_block": last, "last_swap_age_blocks": age,
                    "last_swap_age_days": round(age * BLOCK_TIME_S / 86400, 2), "age_is_lower_bound": lb,
                    "scan_from": sw[1], "window_blocks": THIN_SWAP_WINDOW_BLOCKS}
        found = []
        for kind, pool, quote in pools:
            sel = "0x3850c7bd" if kind == "v3" else "0x0902f1ac"
            r = self._call(pool, sel, block)
            if r is None: found.append({"reason": self._absent(pool, sel, block), "pool": pool}); continue
            if word(r, 0) == 0 or (kind != "v3" and word(r, 1) == 0): found.append({"reason": "zero_reserves", "pool": pool}); continue
            zero = None
            for tkn in ([quote, a] if kind == "v3" else [quote]):        # v3: both token balances must be > 0
                b = self.token_balance(tkn, pool, block)
                if b is None:
                    zero = {"reason": "rpc_error" if self.status.get((tkn, "0x70a08231" + a32(pool), block)) == "error" else "bad_response",
                            "pool": pool, "token": tkn}; break
                if b <= 0: zero = {"reason": "zero_reserves", "pool": pool, "token": tkn}; break
            if zero: found.append(zero); continue
            if quote != self.num and self.dex(quote, block) is None: found.append({"reason": "quote_unpriced", "pool": pool, "quote": quote}); continue
            found.append({"reason": "unexplained", "pool": pool})
        bad = [f for f in found if f["reason"] not in ACCEPTED_UNPRICED]
        if bad: return dict(bad[0], pools=found)
        z = [f for f in found if f["reason"] == "zero_reserves"]
        return dict((z or found)[0], pools=found)

    def has_source(self, asset):
        a = self.weth if asset in (None, "native") else asset.lower()
        return a == self.num or (a in self.pools and a not in NO_PRICE_SOURCE.get(self.chain, set()))

    def price(self, asset, block, ts):
        """Resolution order without the trade step: numeraire, DEX at block (>= floor), then alchemica: thin pool (low) else None;
        other assets: None (no API step; DefiLlama is only the ±3% reference). GLTR: thin tier only (THIN_ONLY_ASSETS);
        NO_PRICE_SOURCE -> None, never 0. asset None = native ETH (= WETH). ts is unused by the price order (kept for callers)."""
        a = self.weth if asset is None else asset.lower()
        if a == self.num: return Price(1, "numeraire", PRICE_LABEL["numeraire"])
        if a in NO_PRICE_SOURCE.get(self.chain, set()): return None
        d = self.dex(a, block)
        if d: return d
        if a in self.thin_assets: return self.thin(a, block)
        return None

BLOCK_TIME_S = 2                     # Base / Base Sepolia: 2 s blocks (last-swap age in days = blocks x 2 / 86400)
ACCEPTED_UNPRICED = ("stale_pool", "no_pool", "zero_reserves")

def price_flag_for(p):
    """Ledger/probe flag of a priced value: low-confidence prices carry the badge flag (totals are also shown without them)."""
    return "low_confidence" if p is not None and p.label == "low" else None

def verify_stale(conn, chain, pool, block, claimed_last):
    """Independent re-derivation for a stale_pool sample, straight from the pool_swap / pool_swap_scan cache (not the Pricer's copy):
    the last Swap at or before the block must equal the claimed one and be >= THIN_SWAP_WINDOW_BLOCKS (7 d) before it, and the scan
    must cover (block - 7 d, block]."""
    last = conn.execute("SELECT max(block_number) FROM pool_swap WHERE chain_id=%s AND pool=decode(%s,'hex') AND block_number <= %s",
                        (chain, pool[2:], block)).fetchone()[0]
    sc = conn.execute("SELECT from_block, scanned_to FROM pool_swap_scan WHERE chain_id=%s AND pool=decode(%s,'hex')", (chain, pool[2:])).fetchone()
    covered = bool(sc) and sc[0] <= block - THIN_SWAP_WINDOW_BLOCKS and sc[1] >= block
    lb = last is None                                   # no swap at/before the block in the scan: age >= block - scan_from
    age = None if not sc else block - (sc[0] if lb else last)
    ok = covered and last == claimed_last and age is not None and age >= THIN_SWAP_WINDOW_BLOCKS
    return {"sql_last_swap_block": last, "age_blocks": age, "age_days": None if age is None else round(age * BLOCK_TIME_S / 86400, 2),
            "age_is_lower_bound": lb, "scan": None if not sc else [sc[0], sc[1]], "ok": ok}

def load_swaps(conn, chain):
    """pool -> (sorted swap blocks, scanned_from, scanned_to) from the pool_swap cache (filled by ingest.ingest_pool_swaps)."""
    out = {}
    for pool, frm, to in conn.execute("SELECT '0x'||encode(pool,'hex'), from_block, scanned_to FROM pool_swap_scan WHERE chain_id=%s", (chain,)):
        bl = [r[0] for r in conn.execute("SELECT block_number FROM pool_swap WHERE chain_id=%s AND pool=decode(%s,'hex') ORDER BY 1", (chain, pool[2:]))]
        out[pool] = (bl, frm, to)
    return out

# ------------------------------------------------------------------ ledger pass
FUNGIBLE = ("native", "erc20")
def lab_min(*ls): return min(ls, key=lambda l: CONFIDENCE[l])

def price_ledger(conn, chain, pricer, log=print):
    """Idempotent: recomputes price columns / price_flag for every ledger entry of the chain; caches in price_point.
    Never writes fifo_lot (pending basis stays pending: P4 excludes it from mark and basis)."""
    allow = gated(chain); num = NUMERAIRE.get(chain); tsec = lambda ts: int(ts.timestamp())
    conn.execute("""UPDATE ledger_entry SET price_usdc=NULL, price_source=NULL, price_confidence=NULL, price_confidence_label=NULL,
                    price_id=NULL, price_flag=NULL WHERE chain_id=%s""", (chain,))
    rows = conn.execute("""SELECT l.id, l.asset_id, a.standard, '0x'||encode(a.contract,'hex'), l.qty, l.category, l.trade_group,
        l.block_number, l.ts, l.pnl_excluded, l.location FROM ledger_entry l JOIN asset a ON a.id=l.asset_id
        WHERE l.chain_id=%s ORDER BY l.block_number, l.tx_index NULLS LAST, l.id""", (chain,)).fetchall()
    E = {r[0]: dict(id=r[0], aid=r[1], std=r[2], c=r[3], qty=Decimal(r[4]), cat=r[5], tg=r[6], bn=r[7], ts=r[8], excl=r[9], loc=r[10]) for r in rows}
    out, stats = {}, {"entries": len(E), "by_source": {}, "by_flag": {}}
    def flag(e, f): out[e["id"]] = ("flag", f)
    def tracked_fungible(e): return e["std"] in FUNGIBLE and (e["std"] == "native" or e["c"] in allow)
    def whole(e): return e["qty"] / (Decimal(10) ** (18 if e["std"] == "native" else pricer.dec(e["c"])))
    for e in E.values():   # flags first (DESIGN §8): spam / untracked never priced; migration_in pending basis unpriced
        if e["cat"] == "spam": flag(e, "spam")
        elif e["cat"] == "untracked" or (e["excl"] and e["cat"] != "spam"): flag(e, "untracked")
        elif e["cat"] == "migration_in": flag(e, "pending_basis")
    groups = {}
    for e in E.values():
        if e["tg"] and e["id"] not in out: groups.setdefault(e["tg"], []).append(e)
    # 1) trade-implied price for 2-leg fungible swaps (one tracked leg out, one in). Untracked/spam legs are already flagged and so
    #    never act as counter-legs (DESIGN §8): a tracked leg whose counter is untracked is priced from its own DEX/API price below.
    for tg, legs in groups.items():
        fl = [e for e in legs if tracked_fungible(e) and e["cat"] == "swap" and e["loc"] == "wallet"]
        if len(fl) != 2 or (fl[0]["qty"] > 0) == (fl[1]["qty"] > 0) or fl[0]["c"] == fl[1]["c"]: continue
        for e, cp in ((fl[0], fl[1]), (fl[1], fl[0])):
            if e["c"] == num: continue                                   # USDC itself stays numeraire
            ratio = abs(whole(cp)) / abs(whole(e))
            if cp["c"] == num: out[e["id"]] = ("price", Price(ratio, "trade", PRICE_LABEL["trade_usdc"], {"counter": "USDC", "trade_group": str(tg), "block": e["bn"]}))
            else:
                cpp = pricer.price(None if cp["std"] == "native" else cp["c"], cp["bn"], tsec(cp["ts"]))
                if cpp: out[e["id"]] = ("price", Price(ratio * cpp.price, "trade", cpp.label, {"counter": cp["c"] or "native", "counter_source": cpp.source,
                                                                                    "counter_detail": cpp.detail, "trade_group": str(tg), "block": e["bn"]}))
    # 2) every other tracked fungible: numeraire / DEX / API at its block, else flag no_price
    for e in E.values():
        if e["id"] in out or not tracked_fungible(e): continue
        p = pricer.price(None if e["std"] == "native" else e["c"], e["bn"], tsec(e["ts"]))
        out[e["id"]] = ("price", p) if p else ("flag", "no_price")
    # 3) NFT legs: trade-implied value from the payment legs of the same trade group (§2 NFT cost basis); one NFT leg only
    for e in E.values():
        if e["id"] in out: continue
        if e["std"] in ("erc721", "erc1155") and e["tg"] and e["cat"] in ("nft_buy", "nft_sale", "auction"):
            legs = groups.get(e["tg"], []); nfts = [x for x in legs if x["std"] in ("erc721", "erc1155")]
            pays = [x for x in legs if x["std"] in FUNGIBLE and x["cat"] != "fee"]
            pv = [out.get(x["id"]) for x in pays]
            if len(nfts) == 1 and pays and all(v and v[0] == "price" for v in pv):
                total = sum(abs(whole(x)) * v[1].price for x, v in zip(pays, pv))
                out[e["id"]] = ("price", Price(total / abs(e["qty"]), "trade", lab_min(*[v[1].label for v in pv]),
                                               {"payment_legs": [x["id"] for x in pays], "payment_usdc": str(total)}))
                continue
        flag(e, "nft_no_trade" if e["std"] in ("erc721", "erc1155") else "no_price")
    for eid, (kind, v) in out.items():
        e = E[eid]
        if kind == "flag":
            conn.execute("UPDATE ledger_entry SET price_flag=%s WHERE id=%s", (v, eid)); stats["by_flag"][v] = stats["by_flag"].get(v, 0) + 1; continue
        pid = None
        if v.source not in ("trade",):
            pid = conn.execute("""INSERT INTO price_point(asset_id,chain_id,block_number,ts,price_usdc,source,confidence,confidence_label,detail)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (asset_id,block_number,source) DO UPDATE SET price_usdc=EXCLUDED.price_usdc,
                confidence=EXCLUDED.confidence, confidence_label=EXCLUDED.confidence_label, detail=EXCLUDED.detail RETURNING id""", (e["aid"], chain, e["bn"], e["ts"], v.price, v.source, CONFIDENCE[v.label], v.label,
                json.dumps(v.detail))).fetchone()[0]
        lf = price_flag_for(v)      # priced, badge; totals also reported without these
        conn.execute("""UPDATE ledger_entry SET price_usdc=%s, price_source=%s, price_confidence=%s, price_confidence_label=%s, price_id=%s,
            price_flag=%s WHERE id=%s""", (v.price, v.source, CONFIDENCE[v.label], v.label, pid, lf, eid))
        if lf: stats["by_flag"][lf] = stats["by_flag"].get(lf, 0) + 1
        stats["by_source"][v.source] = stats["by_source"].get(v.source, 0) + 1
    stats["rpc_calls"] = pricer.calls; stats["rpc_errors"] = len(pricer.rpc_errors)
    stats["fallthrough_after_rpc_error"] = len(pricer.fallthrough)
    conn.execute("""INSERT INTO price_run(chain_id,entries,rpc_calls,rpc_errors,fallthrough_after_rpc_error,detail) VALUES (%s,%s,%s,%s,%s,%s)""",
                 (chain, stats["entries"], pricer.calls, len(pricer.rpc_errors), len(pricer.fallthrough),
                  json.dumps({"rpc_errors": pricer.rpc_errors[:50], "fallthrough": pricer.fallthrough[:50]})))
    conn.commit(); log(json.dumps({"chain": chain, "price_ledger": stats})); return stats

def totals(conn, chain):
    """USDC value (|qty| in whole units x unit price) of priced, PnL-relevant entries (not spam/untracked/pnl_excluded, not fees).
    Low-confidence entries count in value_usdc_all (badge) and are left out of value_usdc_excl_low. Unpriced entries are excluded
    from both and counted (never valued at 0)."""
    dec = {c: d for c, (_, d) in TOKENS.get(chain, {}).items()}; out = {}; tot = {"all": Decimal(0), "excl_low": Decimal(0), "low_n": 0, "unpriced_n": 0}
    for std, c, qty, px, lab, fl, sym in conn.execute("""SELECT a.standard, '0x'||encode(a.contract,'hex'), l.qty, l.price_usdc, l.price_confidence_label,
            l.price_flag, a.symbol FROM ledger_entry l JOIN asset a ON a.id=l.asset_id WHERE l.chain_id=%s AND NOT l.pnl_excluded
            AND l.category NOT IN ('spam','untracked','fee')""", (chain,)):
        k = "ETH" if std == "native" else TOKENS.get(chain, {}).get(c, (sym or c,))[0]
        r = out.setdefault(k, {"value_usdc_all": Decimal(0), "value_usdc_excl_low": Decimal(0), "low_confidence_entries": 0, "unpriced_entries": 0})
        if px is None:
            if fl == "no_price": r["unpriced_entries"] += 1; tot["unpriced_n"] += 1
            continue
        d = 18 if std == "native" else (dec.get(c, 0) if std == "erc20" else 0)
        v = abs(Decimal(qty)) / (Decimal(10) ** d) * Decimal(px)
        r["value_usdc_all"] += v; tot["all"] += v
        if lab == "low": r["low_confidence_entries"] += 1; tot["low_n"] += 1
        else: r["value_usdc_excl_low"] += v; tot["excl_low"] += v
    f = lambda x: str(round(x, 2))
    return {"value_usdc_all": f(tot["all"]), "value_usdc_excl_low": f(tot["excl_low"]), "low_confidence_entries": tot["low_n"],
            "unpriced_entries_excluded": tot["unpriced_n"],
            "by_asset": {k: {**v, "value_usdc_all": f(v["value_usdc_all"]), "value_usdc_excl_low": f(v["value_usdc_excl_low"])} for k, v in sorted(out.items())}}

def coverage(conn, chain):
    r = conn.execute("""SELECT count(*), count(*) FILTER (WHERE price_usdc IS NOT NULL), count(*) FILTER (WHERE price_flag IS NOT NULL),
        count(*) FILTER (WHERE price_usdc IS NULL AND price_flag IS NULL) FROM ledger_entry WHERE chain_id=%s""", (chain,)).fetchone()
    run = conn.execute("""SELECT id, finished_at, rpc_calls, rpc_errors, fallthrough_after_rpc_error, detail FROM price_run
        WHERE chain_id=%s ORDER BY id DESC LIMIT 1""", (chain,)).fetchone()
    pr = None if not run else {"id": run[0], "finished_at": str(run[1]), "rpc_calls": run[2], "rpc_errors": run[3],
                               "fallthrough_after_rpc_error": run[4], "rpc_error_samples": run[5].get("rpc_errors", [])[:10],
                               "fallthrough": run[5].get("fallthrough", [])[:10]}
    fail = []
    if r[3]: fail.append(f"{r[3]} entries have neither a price nor a flag")
    if r[0] == 0: fail.append("no ledger entries")
    if pr and pr["rpc_errors"]: fail.append(f"price run {pr['id']} hit {pr['rpc_errors']} RPC errors: unpriced entries may be RPC failures, not real no_price")
    return {"entries": r[0], "priced": r[1], "flagged": r[2], "neither": r[3], "pass": not fail, "failures": fail, "price_run": pr,
            "by_source": dict(conn.execute("SELECT price_source, count(*) FROM ledger_entry WHERE chain_id=%s AND price_source IS NOT NULL GROUP BY 1", (chain,)).fetchall()),
            "by_flag": dict(conn.execute("SELECT price_flag, count(*) FROM ledger_entry WHERE chain_id=%s AND price_flag IS NOT NULL GROUP BY 1", (chain,)).fetchall()),
            "by_label": dict(conn.execute("SELECT price_confidence_label, count(*) FROM ledger_entry WHERE chain_id=%s AND price_usdc IS NOT NULL GROUP BY 1", (chain,)).fetchall()),
            "zero_prices": conn.execute("SELECT count(*) FROM ledger_entry WHERE chain_id=%s AND price_usdc = 0", (chain,)).fetchone()[0],
            "totals": totals(conn, chain)}

def sample(conn, chain, pricer, n=20, seed=3, extras=True, log=print):
    """P3 pass checks C1 and C2 (DESIGN v1.3 §4; §8 P3 rulings and P3 C1 rulings, PR #7). Assets = the tracked fungibles that have
    non-excluded Base ledger entries (C1 scope), plus WETH and cbBTC as report-only extras. Blocks = n distinct ledger blocks (fixed seed)
    at/after the first block where every C1 asset has ledger activity. Each (asset, block) gets the full price order (numeraire /
    DEX >= floor / thin pool / API) and, independently, the DEX (>= floor) and API prices.
    C1 (amended): every sample is priced, or unpriced with an accepted machine-checkable reason (stale_pool with the last-swap age,
    no_pool, zero_reserves). Each stale_pool sample is re-derived from the pool_swap cache by verify_stale(). Unpriced = excluded and
    flagged, never 0. GLTR has no Base ledger entries, so it is not in C1; see gltr_probe().
    C2: |dex/api - 1| <= 3%, gated only for GHST high/medium DEX prices; every other pair is report only."""
    import random
    allow = gated(chain); num = NUMERAIRE.get(chain); dev_gate = DEV_GATED_ASSETS.get(chain, set())
    firsts = conn.execute("""SELECT CASE WHEN a.standard='native' THEN 'native' ELSE '0x'||encode(a.contract,'hex') END, min(l.block_number)
        FROM ledger_entry l JOIN asset a ON a.id=l.asset_id WHERE l.chain_id=%s AND NOT l.pnl_excluded AND a.standard IN ('native','erc20')
        GROUP BY 1""", (chain,)).fetchall()
    assets = sorted(c for c, _ in firsts if c == "native" or c in allow)
    gated_assets = list(assets)
    start = max(b for c, b in firsts if c in gated_assets)
    cand = [r[0] for r in conn.execute("SELECT DISTINCT block_number FROM ledger_entry WHERE chain_id=%s AND block_number >= %s ORDER BY 1", (chain, start))]
    blocks = sorted(random.Random(seed).sample(cand, min(n, len(cand))))
    ts = dict(conn.execute("SELECT number, ts FROM block WHERE chain_id=%s AND number = ANY(%s)", (chain, blocks)).fetchall())
    extra = [c for c in (WETH.get(chain), "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf") if c not in assets] if extras else []
    sym = lambda c: "ETH" if c == "native" else pricer.tok.get(c, (c,))[0]
    res, devs, c1_bad = {}, [], []
    for bn in blocks:
        t = int(ts[bn].timestamp())
        for c in assets + extra:
            a = pricer.weth if c == "native" else c
            p = pricer.price(a, bn, t)
            d = None if a == num else pricer.dex(a, bn)
            api = None if a == num else pricer.api_price(a, t)
            det = p.detail if p else {}
            row = {"block": bn, "ts": t, "asset": sym(c), "gated": c in gated_assets, "priced": p is not None,
                   "price": None if not p else str(p.price), "source": p.source if p else None, "label": p.label if p else None,
                   "flag": price_flag_for(p), "pool": det.get("pool"), "pool_depth_usd": det.get("pool_depth_usd"),
                   "last_swap_block": det.get("last_swap_block"), "api_ts": det.get("api_ts"), "dex": None if not d else str(d.price),
                   "dex_label": d.label if d else None, "api": None if not api else str(api.price)}
            if p is None:
                why = pricer.unpriced_reason(a, bn); row["flag"] = "no_price"; row["unpriced_reason"] = why
                ok = why["reason"] in ACCEPTED_UNPRICED
                if why["reason"] == "stale_pool":
                    chk = verify_stale(conn, chain, why["pool"], bn, why["last_swap_block"]); row["stale_check"] = chk; ok = ok and chk["ok"]
                row["c1_ok"] = ok
            else: row["c1_ok"] = True
            if c in gated_assets and not row["c1_ok"]: c1_bad.append({"asset": sym(c), "block": bn, "unpriced_reason": row.get("unpriced_reason")})
            if d and api:
                row["dev_pct"] = float(round((d.price / api.price - 1) * 100, 3))
                row["dev_gated"] = a in dev_gate and d.label in ("high", "medium"); devs.append(row)
            log(json.dumps({"sample": row}))
            r = res.setdefault(sym(c), {"gated": c in gated_assets, "has_source": pricer.has_source(c), "priced": 0, "unpriced": 0,
                                        "unpriced_by_reason": {}, "stale_age_days": [], "c1_ok": 0, "by_source": {},
                                        "dex": 0, "api": 0, "both": 0, "max_abs_dev_pct": None})
            r["priced"] += row["priced"]; r["c1_ok"] += row["c1_ok"]; r["dex"] += bool(d); r["api"] += bool(api); r["both"] += "dev_pct" in row
            if p: r["by_source"][p.source] = r["by_source"].get(p.source, 0) + 1
            else:
                k = row["unpriced_reason"]["reason"]; r["unpriced"] += 1; r["unpriced_by_reason"][k] = r["unpriced_by_reason"].get(k, 0) + 1
                if k == "stale_pool": r["stale_age_days"].append(row["unpriced_reason"]["last_swap_age_days"])
            if "dev_pct" in row: r["max_abs_dev_pct"] = max(r["max_abs_dev_pct"] or 0, abs(row["dev_pct"]))
    for v in res.values():
        a_ = [x for x in v.pop("stale_age_days") if x is not None]
        v["stale_age_days_min_max"] = [min(a_), max(a_)] if a_ else None
    g = [r for r in devs if r["dev_gated"]]
    out = {"chain": chain, "blocks": blocks, "sample_start_block": start, "seed": seed, "assets": res,
           "c1_accepted_reasons": list(ACCEPTED_UNPRICED), "c1_failures": c1_bad,
           "c1_unpriced_by_reason": _count_reasons(res), "rpc_errors": len(pricer.rpc_errors), "rpc_error_samples": pricer.rpc_errors[:10],
           "fallthrough_after_rpc_error": len(pricer.fallthrough), "fallthrough_samples": pricer.fallthrough[:10],
           "pass_c1": not c1_bad and len(blocks) == n,
           "pass_all_priced": all(v["priced"] == len(blocks) for v in res.values() if v["gated"]) and len(blocks) == n,
           "not_priced_at": [{"asset": k, "priced": v["priced"], "of": len(blocks), "unpriced_by_reason": v["unpriced_by_reason"]}
                             for k, v in res.items() if v["gated"] and v["priced"] < len(blocks)],
           "pairs_with_both": len(devs), "gated_pairs": len(g), "outside_3pct_gated": [r for r in g if abs(r["dev_pct"]) > 3],
           "outside_3pct_report_only": [r for r in devs if not r["dev_gated"] and abs(r["dev_pct"]) > 3],
           "pass_dex_vs_api_3pct": bool(g) and all(abs(r["dev_pct"]) <= 3 for r in g), "rpc_calls": pricer.calls}
    log(json.dumps({"summary": out})); return out

def _count_reasons(res):
    out = {}
    for v in res.values():
        if not v["gated"]: continue
        for k, n in v["unpriced_by_reason"].items(): out[k] = out.get(k, 0) + n
    return out

GLTR_BASE = "0x4d140ce792bedc430498c2d219afbc33e2992c9d"

def gltr_probe(conn, chain, pricer, n=5, seed=3, min_block=None, log=print):
    """P3 C1 ruling (2): GLTR path probe, a pass/fail line separate from the C1 count. n blocks drawn (fixed seed) from the GLTR/GHST
    pool's own cached Swap blocks (pool_swap; no new HyperSync calls) at/after min_block (the C1 sample start, so GHST/USDC is on its
    >= floor tier) and inside the scanned range. Each block must price GLTR -> GHST -> USDC on the thin tier: source dex_reserves_thin,
    label low, flag low_confidence, pool = the GLTR/GHST pool, quote GHST, GHST priced against the USDC numeraire, last swap = a swap
    at/before the block per the SQL cache (age < 7 d)."""
    import random
    num = NUMERAIRE.get(chain)
    pools = [p for k, p, q in PRICE_POOLS.get(chain, {}).get(GLTR_BASE, []) if k == "v2"]
    if not pools: out = {"pass": False, "error": "no GLTR pool configured"}; log(json.dumps({"gltr_probe": out})); return out
    pool = pools[0]; ghst = PRICE_POOLS[chain][GLTR_BASE][0][2]
    sc = conn.execute("SELECT from_block, scanned_to FROM pool_swap_scan WHERE chain_id=%s AND pool=decode(%s,'hex')", (chain, pool[2:])).fetchone()
    cand = [r[0] for r in conn.execute("""SELECT DISTINCT block_number FROM pool_swap WHERE chain_id=%s AND pool=decode(%s,'hex')
        AND block_number >= %s AND block_number <= %s ORDER BY 1""", (chain, pool[2:], min_block or 0, sc[1] if sc else -1))]
    blocks = sorted(random.Random(seed).sample(cand, min(n, len(cand))))
    rows = []
    for bn in blocks:
        p = pricer.price(GLTR_BASE, bn, None); det = p.detail if p else {}; qd = det.get("quote_detail") or {}
        sql_last = conn.execute("SELECT max(block_number) FROM pool_swap WHERE chain_id=%s AND pool=decode(%s,'hex') AND block_number <= %s",
                                (chain, pool[2:], bn)).fetchone()[0]
        checks = {"priced": p is not None, "thin_tier": bool(p) and p.source == "dex_reserves_thin", "low": bool(p) and p.label == "low",
                  "flagged": price_flag_for(p) == "low_confidence", "pool": det.get("pool") == pool, "quote_ghst": det.get("quote") == ghst,
                  "ghst_to_usdc": qd.get("quote") == num and qd.get("pool") is not None,
                  "swap_recent": sql_last is not None and det.get("last_swap_block") == sql_last and bn - sql_last < THIN_SWAP_WINDOW_BLOCKS}
        row = {"block": bn, "asset": "GLTR", "price": None if not p else str(p.price), "source": p.source if p else None,
               "label": p.label if p else None, "flag": price_flag_for(p) if p else "no_price", "pool": det.get("pool"),
               "pool_depth_usd": det.get("pool_depth_usd"), "quote_reserve_usd": det.get("quote_reserve_usd"),
               "last_swap_block": det.get("last_swap_block"), "route": det.get("route"),
               "ghst_usdc": None if not qd else {"pool": qd.get("pool"), "kind": qd.get("kind"), "price": det.get("quote_price"),
                                                 "pool_depth_usd": qd.get("pool_depth_usd"), "quote": qd.get("quote")},
               "checks": checks, "pass": all(checks.values())}
        if p is None: row["unpriced_reason"] = pricer.unpriced_reason(GLTR_BASE, bn)
        rows.append(row); log(json.dumps({"gltr_probe_block": row}))
    out = {"pool": pool, "blocks": blocks, "candidates": len(cand), "min_block": min_block, "passed": sum(r["pass"] for r in rows),
           "of": n, "pass": len(rows) == n and all(r["pass"] for r in rows), "rpc_calls": pricer.calls}
    log(json.dumps({"gltr_probe": out})); return out
