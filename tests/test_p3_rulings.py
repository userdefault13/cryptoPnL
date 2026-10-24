"""P3 rulings (architect, DESIGN §8 'P3 rulings'): price order trade -> pool >= floor -> thin pool (low, flagged, swap <= 7 d via the
cached HyperSync scan) -> unpriced; GLTR unpriced (never 0) unless trade-implied; pool USD depth on every DEX price; totals with and
without low-confidence; ±3% gate only for GHST high/medium. Offline: fake RPC/API (tests.test_pricing)."""
import unittest
from decimal import Decimal
from cryptopnl import pricing
from cryptopnl.config import THIN_SWAP_WINDOW_BLOCKS as WIN
from tests import test_pricing as tp
from tests.test_pricing import FakeRPC, FakeAPI, market, w, bal, C, W, X, GHST, FUD, P_FUD, P_GHST, E18, ZERO, tx, e20
GLTR = "0x4d140ce792bedc430498c2d219afbc33e2992c9d"; BN = 40_000_000

def thin_market():   # FUD/GHST pool holds 1,000 GHST x 0.5 = $500 < $1,000 floor; price 0.001 GHST = 0.0005 USDC
    m = market(); m[(P_FUD, "0x0902f1ac")] = w(1_000_000 * E18, 1_000 * E18, 0); m[bal(GHST, P_FUD)] = w(1_000 * E18); return m

class Rulings(unittest.TestCase):
    def pr(self, m=None, api=None, swaps=None): return pricing.Pricer(C, FakeRPC(thin_market() if m is None else m), FakeAPI(api), swaps=swaps)
    def test_depth_on_every_dex_price(self):
        pr = pricing.Pricer(C, FakeRPC(market()), FakeAPI())
        g = pr.price(GHST, BN, 0); f = pr.price(FUD, BN, 0)
        self.assertEqual((g.detail["pool"], g.detail["pool_depth_usd"], g.detail["depth_method"], g.detail["block"]), (P_GHST, "10000.00", "quote_balance", BN))
        self.assertEqual((f.detail["pool"], f.detail["quote_reserve_usd"], f.detail["pool_depth_usd"], f.detail["depth_method"]), (P_FUD, "5000.00", "10000.00", "2x_quote_reserve"))
    def test_thin_pool_with_swap_within_7d_is_low(self):
        p = self.pr(swaps={P_FUD: ([BN - 50_000], 33_200_000, BN + 10)}).price(FUD, BN, 0)
        self.assertEqual((p.source, p.label, p.detail["pool"], p.detail["last_swap_block"], p.detail["below_floor"]), ("dex_reserves_thin", "low", P_FUD, BN - 50_000, True))
        self.assertAlmostEqual(float(p.price), 0.0005, places=12); self.assertEqual(p.detail["pool_depth_usd"], "1000.00")
    def test_thin_pool_without_recent_swap_or_scan_is_unpriced(self):
        self.assertIsNone(self.pr(swaps={P_FUD: ([BN - WIN], 33_200_000, BN)}).price(FUD, BN, 0))      # swap exactly 7 d old: too old
        self.assertIsNone(self.pr(swaps={P_FUD: ([BN + 5], 33_200_000, BN + 10)}).price(FUD, BN, 0))   # only a later swap
        self.assertIsNone(self.pr(swaps={}).price(FUD, BN, 0))                                         # pool never scanned
        self.assertIsNone(self.pr(swaps={P_FUD: ([BN - 10], 33_200_000, BN - 1)}).price(FUD, BN, 0))   # scan does not reach the block
        m = thin_market(); m[(P_FUD, "0x0902f1ac")] = w(0, 1_000 * E18, 0)                              # a zero reserve: never thin-priced
        self.assertIsNone(self.pr(m, swaps={P_FUD: ([BN - 10], 33_200_000, BN)}).price(FUD, BN, 0))
    def test_thin_rule_is_alchemica_only(self):
        m = market(ghst_usdc_reserve=999)
        self.assertIsNone(self.pr(m, swaps={P_GHST: ([BN - 1], 0, BN)}).price(GHST, BN, 0))           # GHST below floor: API or nothing
    def test_gltr_unpriced_never_zero(self):
        pr = self.pr(api={GLTR: "0.00001"})
        self.assertIsNone(pr.price(GLTR, BN, 0)); self.assertFalse(pr.has_source(GLTR)); self.assertTrue(pr.has_source(FUD))

class RulingsLedger(tp.LedgerPass):
    def test_low_flag_totals_and_gltr(self):
        thin = self.add(tx(W, X), e20(FUD, ZERO, W, 1000 * E18), bn=BN)                       # income, thin pool -> low
        gl = self.add(tx(W, X), e20(GLTR, ZERO, W, 500 * E18), bn=BN)                         # GLTR income -> unpriced
        tr = self.add(tx(W, X), e20(GHST, X, W, 10 * E18), e20(GLTR, W, X, 1000 * E18), bn=BN)  # GLTR traded vs GHST -> trade-implied
        gi = self.add(tx(W, X), e20(GHST, ZERO, W, 4 * E18), bn=BN)                           # GHST income, high
        self.run_()
        pr = pricing.Pricer(C, FakeRPC(thin_market()), FakeAPI(), swaps={P_FUD: ([BN - 100], 33_200_000, BN)})
        pricing.price_ledger(self.c, C, pr, log=lambda *_: None)
        self.assertEqual(self.leg(thin, FUD), [("income", 0.0005, "dex_reserves_thin", "low", "low_confidence")])
        self.assertEqual(self.leg(gl, GLTR), [("income", None, None, None, "no_price")])
        self.assertEqual(self.leg(tr, GLTR), [("swap", 0.005, "trade", "high", None)])        # 10 GHST x 0.5 / 1000 GLTR
        cov = pricing.coverage(self.c, C); t = cov["totals"]
        self.assertEqual((cov["neither"], cov["zero_prices"]), (0, 0))
        self.assertEqual(t["low_confidence_entries"], 1); self.assertEqual(t["unpriced_entries_excluded"], 1)
        self.assertEqual(Decimal(t["value_usdc_all"]) - Decimal(t["value_usdc_excl_low"]), Decimal("0.50"))   # 1000 FUD x 0.0005
        self.assertEqual(t["by_asset"]["FUD"]["value_usdc_excl_low"], "0.00")
        self.assertEqual(t["by_asset"]["GLTR"]["unpriced_entries"], 1)

if __name__ == "__main__": unittest.main()
