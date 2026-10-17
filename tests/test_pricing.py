"""P3 pricing unit tests. Offline: fake RPC (eth_call by (to, calldata)) and fake price API; local Postgres for the ledger pass.
Run: CRYPTOPNL_DSN=postgresql:///cryptopnl_unit_p3 ENVIO_API_TOKEN=x .venv/bin/python -m unittest -v tests.test_pricing"""
import os, unittest
from decimal import Decimal, getcontext
os.environ.setdefault("ENVIO_API_TOKEN", "test")
from cryptopnl import pricing, classify
from cryptopnl.db import b
from tests import test_classify as tc
from tests.test_classify import C, W, X, USDC, GHST, NFT, SPAM, ZERO, FG, BRIDGE, MINTBATCH, tx, e20, e721, meta
getcontext().prec = 60
WETH = "0x4200000000000000000000000000000000000006"; USDBC = "0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca"
FUD = "0x2028b4043e6722ea164946c82fe806c4a43a0ff4"; LINK = "0x88fb150bdc53a65fe94dea0c9ba0a6daf8c6e196"
P_WETH = "0xd0b53d9277642d899df5c87a3966a349a798f224"; P_GHST = "0x41d4934322f2bd6fe1dbe4124070fe61651a2067"
P_FUD = "0xeae2fb93e291c2eb69195851813de24f97f1ce71"
Q96 = Decimal(2) ** 96; E18 = 10 ** 18
def w(*xs): return "0x" + "".join(format(int(x), "064x") for x in xs)
def sqrtp(p01, d0, d1): return int((Decimal(p01) / Decimal(10) ** (d0 - d1)).sqrt() * Q96)
def bal(tok, pool): return (tok, "0x70a08231" + pool[2:].rjust(64, "0"))

class FakeRPC:
    def __init__(self, m): self.m = m; self.n = 0
    def eth_call(self, to, data, block):
        self.n += 1; r = self.m.get((to, data))
        if r is None: raise RuntimeError("execution reverted")
        return r
class FakeAPI:
    def __init__(self, p=None): self.p = p or {}
    def prices(self, ts, contracts): return {c: (Decimal(v), ts) for c, v in self.p.items() if c in contracts}

def market(ghst_usdc_reserve=10_000):
    """WETH = 2000 USDC (Uni V3, token0 WETH); GHST = 0.5 USDC (Slipstream, token0 USDC); FUD = 0.001 GHST (Aerodrome v2, token0 FUD)."""
    return {(P_WETH, "0x3850c7bd"): w(sqrtp(2000, 18, 6), 0), bal(USDC, P_WETH): w(5_000_000 * 10 ** 6),
            (P_GHST, "0x3850c7bd"): w(sqrtp(2, 6, 18), 0), bal(USDC, P_GHST): w(ghst_usdc_reserve * 10 ** 6),
            (P_FUD, "0x0902f1ac"): w(10_000_000 * E18, 10_000 * E18, 0), bal(GHST, P_FUD): w(10_000 * E18)}

class PricerMath(unittest.TestCase):
    def pr(self, m=None, api=None): return pricing.Pricer(C, FakeRPC(market() if m is None else m), FakeAPI(api))
    def test_numeraire_native_usdc(self):
        p = self.pr().price(USDC, 1, 0)
        self.assertEqual((p.price, p.source, p.label), (1, "numeraire", "high"))
    def test_usdbc_never_par(self):
        """Architect ruling (KNOWN_GAPS #16): only native USDC is the numeraire. USDbC has no pool here and no API price -> None."""
        self.assertIsNone(self.pr().price(USDBC, 1, 0))
        p = self.pr(api={USDBC: "0.9903"}).price(USDBC, 1, 0)      # with an API price it gets that price, never 1
        self.assertEqual((p.price, p.source), (Decimal("0.9903"), "defillama"))
        self.assertNotEqual(p.source, "numeraire")
    def test_v3_slot0_both_orientations(self):
        pr = self.pr()
        self.assertAlmostEqual(float(pr.price(WETH, 1, 0).price), 2000.0, places=6)     # WETH is token0
        g = pr.price(GHST, 1, 0)
        self.assertAlmostEqual(float(g.price), 0.5, places=9); self.assertEqual((g.source, g.label), ("dex_slot0", "high"))
        self.assertAlmostEqual(float(pr.price(None, 1, 0).price), 2000.0, places=6)     # native ETH = WETH
    def test_v2_routed_via_ghst_is_medium(self):
        p = self.pr().price(FUD, 1, 0)
        self.assertAlmostEqual(float(p.price), 0.0005, places=12)
        self.assertEqual((p.source, p.label, p.detail["route"]), ("dex_reserves", "medium", [P_FUD, P_GHST]))
    def test_liquidity_floor_rejects_thin_pool(self):
        m = market(ghst_usdc_reserve=999)        # $999 < DEX_MIN_QUOTE_USD (1000); other GHST pools absent -> no DEX price
        self.assertIsNone(self.pr(m).dex(GHST, 1))
        p = self.pr(m, api={GHST: "0.49"}).price(GHST, 1, 0)
        self.assertEqual((p.source, p.label), ("defillama", "medium"))
    def test_no_source_is_none_not_invented(self):
        self.assertIsNone(self.pr(m={}).price(GHST, 1, 0))

class LedgerPass(unittest.TestCase):
    add = tc.T.add; run_ = tc.T.run_
    def _clear(self):
        from cryptopnl import db; c = db.connect(); db.migrate(c)
        c.execute("UPDATE ledger_entry SET price_id=NULL"); c.execute("DELETE FROM price_point"); c.execute("DELETE FROM tx_position"); c.commit(); c.close()
    def setUp(self): self._clear(); tc.T.setUp(self)
    def tearDown(self): self.c.execute("UPDATE ledger_entry SET price_id=NULL"); self.c.execute("DELETE FROM price_point"); self.c.commit(); tc.T.tearDown(self)
    def leg(self, h, contract):
        q = "SELECT category, price_usdc, price_source, price_confidence_label, price_flag FROM ledger_entry l JOIN asset a ON a.id=l.asset_id WHERE tx_hash=%s AND "
        q += "a.contract IS NULL AND category<>'fee'" if contract is None else "a.contract=%s"
        r = self.c.execute(q, (h,) if contract is None else (h, b(contract))).fetchall()
        return [(c, None if p is None else round(float(p), 9), s, l, f) for c, p, s, l, f in r]
    def test_price_ledger(self):
        swap = self.add(tx(W, X), e20(USDC, X, W, 10 * 10 ** 6), e20(GHST, W, X, 20 * E18))
        unt = self.add(tx(W, X), e20(GHST, W, X, 4 * E18), e20(LINK, X, W, E18))     # untracked counter-leg (KNOWN_GAPS #15)
        buy = self.add(tx(W, X), e20(GHST, W, X, 30 * E18), e721(NFT, X, W, 1))
        inc = self.add(tx(W, X), e20(FUD, ZERO, W, 1000 * E18))
        usdbc = self.add(tx(W, X), e20(USDBC, X, W, 5 * 10 ** 6))
        spam = self.add(e721(SPAM, ZERO, W, 3))
        mig = self.add(e721(FG, ZERO, W, 11), meta(BRIDGE, FG, MINTBATCH), bn=33_222_797)
        self.run_()
        st = pricing.price_ledger(self.c, C, pricing.Pricer(C, FakeRPC(market()), FakeAPI()), log=lambda *_: None)
        self.assertEqual(self.leg(swap, GHST), [("swap", 0.5, "trade", "high", None)])          # 10 USDC / 20 GHST
        self.assertEqual(self.leg(swap, USDC), [("swap", 1.0, "numeraire", "high", None)])
        self.assertEqual(self.leg(unt, GHST)[0][1:4], (0.5, "dex_slot0", "high"))                # own DEX price, not via LINK
        self.assertEqual(self.leg(unt, LINK), [("untracked", None, None, None, "untracked")])
        self.assertEqual(self.leg(buy, GHST)[0][1:3], (0.5, "dex_slot0"))
        self.assertEqual(self.leg(buy, NFT), [("nft_buy", 15.0, "trade", "high", None)])        # 30 GHST x 0.5
        self.assertEqual(self.leg(inc, FUD), [("income", 0.0005, "dex_reserves", "medium", None)])
        u = self.leg(usdbc, USDBC); self.assertEqual(len(u), 1)
        self.assertIsNone(u[0][1]); self.assertNotEqual(u[0][2], "numeraire")                   # USDbC never at par
        self.assertEqual(self.leg(spam, SPAM)[0][4], "spam")
        self.assertEqual(self.leg(mig, FG), [("migration_in", None, None, None, "pending_basis")])
        fee = self.c.execute("SELECT DISTINCT round(price_usdc,6), price_source FROM ledger_entry WHERE category='fee'").fetchall()
        self.assertEqual([(float(p), s) for p, s in fee], [(2000.0, "dex_slot0")])
        # P4 constraint: the pending lot is untouched (no basis, no source), i.e. no price leaks into mark or basis
        self.assertEqual(self.c.execute("SELECT basis_status, basis_usdc, basis_price_source FROM fifo_lot").fetchall(), [("pending", None, None)])
        cov = pricing.coverage(self.c, C)
        self.assertEqual(cov["neither"], 0); self.assertTrue(cov["pass"])
        st2 = pricing.price_ledger(self.c, C, pricing.Pricer(C, FakeRPC(market()), FakeAPI()), log=lambda *_: None)
        self.assertEqual((st["by_source"], st["by_flag"]), (st2["by_source"], st2["by_flag"]))   # idempotent
    def test_no_source_flags_no_price(self):
        h = self.add(tx(W, X), e20(GHST, ZERO, W, E18))
        self.run_(); pricing.price_ledger(self.c, C, pricing.Pricer(C, FakeRPC({}), FakeAPI()), log=lambda *_: None)
        self.assertEqual(self.leg(h, GHST), [("income", None, None, None, "no_price")])
        self.assertEqual(pricing.coverage(self.c, C)["neither"], 0)
    def test_tx_index_orders_within_block(self):
        """Two wallet txs in one block with equal first log index: the old (log index, hash) order puts A first; tx index (B=3, A=7) wins."""
        a = self.add(tx(W, X), e20(GHST, ZERO, W, E18), bn=500)
        bb = self.add(tx(W, X), e20(GHST, ZERO, W, 2 * E18), bn=500)
        self.c.execute("INSERT INTO tx_position VALUES (%s,%s,500,7),(%s,%s,500,3)", (C, a, C, bb)); self.c.commit()
        self.run_()
        r = self.c.execute("SELECT tx_hash, tx_index, id FROM ledger_entry WHERE category='income' ORDER BY id").fetchall()
        self.assertEqual([(bytes(h), i) for h, i, _ in r], [(bytes(bb), 3), (bytes(a), 7)])      # B inserted (processed) first
    def test_no_on_delete_cascade_on_user_data(self):
        r = self.c.execute("""SELECT conrelid::regclass::text, confdeltype FROM pg_constraint WHERE contype='f'
                              AND (conrelid='manual_basis'::regclass OR confrelid='manual_basis'::regclass)""").fetchall()
        self.assertTrue(all(t != "c" for _, t in r), r)

if __name__ == "__main__": unittest.main()
