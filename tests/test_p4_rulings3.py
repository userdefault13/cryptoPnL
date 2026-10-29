"""P4 rulings 3 (architect review of PR #8). SYNTHETIC fixtures only (made-up assets, prices, blocks; not chain data).
  * gas on an NFT sale comes off the NFT's proceeds (nft_sale and auction seller), never into the payment's basis;
  * exits: realized NULL, skipped in totals, counted;
  * the reconciliation is independent of the engine: ledger rows only, its own FIFO and running balance; a LIFO engine is caught;
  * Q-H: an unrecorded-inflow lot is pending, basis_origin=unrecorded_inflow, opens at the shortfall block, carried to children."""
import inspect, unittest
from decimal import Decimal as D
from cryptopnl import fifo, reconcile
from cryptopnl.fifo import run, report, gas
from tests.fifo_fixtures import Book, L, marks
from tests.test_fifo_rulings import RP, MK, NFTX, disp, lot, eqty

def recon(b, st, pol, as_of, mk=MK, nftm=NFTX):
    return reconcile.check(report(st, pol, as_of), gas(st), reconcile.ledger_side(b.rows, mk, nftm, as_of), eqty(st))

class G18NftSaleGas(unittest.TestCase):
    """bridge_in 1000 USDC and 1 ETH @2000. tx2: buy wearable #1 for 200 USDC (basis 200). tx3: sell it for 500 GHST @1 with gas
    0.001 ETH @2000 = 2: the 2 comes off the NFT's proceeds -> proceeds 498, realized 298; the GHST in-leg opens at 500 (not 502).
    tx4: the same through an auction (seller side): wearable #2 bought for 100, sold for 300 GHST, gas 2 -> 298 - 100 = 198; GHST 300."""
    def setUp(self):
        b = Book(); b.tx(1, L("USDC", "1000", "bridge_in", "1"), L("ETH", "1", "bridge_in", "2000"))
        b.tx(2, L("USDC", "-200", "nft_buy", "1"), L("W#1", "1", "nft_buy", nft=True))
        self.s = b.tx(3, L("W#1", "-1", "nft_sale", nft=True), L("GHST", "500", "nft_sale", "1"), L("ETH", "-0.001", "fee", "2000"))
        b.tx(4, L("USDC", "-100", "nft_buy", "1"), L("W#2", "1", "nft_buy", nft=True))
        self.a = b.tx(5, L("W#2", "-1", "auction", nft=True), L("GHST", "300", "auction", "1"), L("ETH", "-0.001", "fee", "2000"))
        self.b = b; self.st = run(b.rows, RP())
    def test_gas_off_nft_proceeds(self):
        d = disp(self.st, self.s[0])[0]; g = lot(self.st, self.s[1])
        self.assertEqual((d.proceeds, d.cost, d.realized), (D(498), D(200), D(298)))
        self.assertEqual((g.basis, g.fee), (D(500), None))
    def test_auction_seller(self):
        d = disp(self.st, self.a[0])[0]; g = lot(self.st, self.a[1])
        self.assertEqual((d.proceeds, d.realized, g.basis), (D(298), D(198), D(300)))
    def test_reconciles_independently(self):
        L_ = reconcile.ledger_side(self.b.rows, MK, NFTX, 6)
        self.assertEqual(L_["gas_txs"]["nft_sale"], 2)
        self.assertEqual(L_["per_asset"]["W#1"]["R"], D(298)); self.assertEqual(L_["per_asset"]["GHST"]["A"], D(800))
        c = recon(self.b, self.st, RP(), 6); self.assertEqual(c["acceptance"], "PASS", c["failures"])

class G19ExitNull(unittest.TestCase):
    """income 2 ETH @1000 (resolved, basis 2000); withdraw 1 ETH @3000 -> exit: realized NULL, basis 1000 exited (X), display MV 3000.
    Totals skip it (realized 0 from nothing summed), exits = 1, unpriced_disposals = 0. Mark ETH 3000: unrealized 3000 - 1000 = 2000."""
    def test_exit(self):
        b = Book(); b.tx(1, L("ETH", "2", "income", "1000")); w = b.tx(2, L("ETH", "-1", "withdrawal", "3000"))
        st = run(b.rows, RP()); d = disp(st, w[0])[0]; r = report(st, RP(), 3)
        self.assertEqual((d.kind, d.realized, d.cost, d.display_mv), ("exit", None, D(1000), D(3000)))
        a = r["all"]
        self.assertEqual((D(a["realized_usdc"]), D(a["unrealized_usdc"]), a["exits"], a["unpriced_disposals"], a["by_asset"]["ETH"]["exits"]),
                         (D(0), D(2000), 1, 0, 1))
        c = recon(b, st, RP(), 3); self.assertEqual(c["acceptance"], "PASS", c["failures"])
        self.assertEqual((c["per_asset"]["ETH"]["X"], c["exits"]), (D(1000), 1))

class G20ChildCarriesBasisOrigin(unittest.TestCase):
    def test_partial_move(self):
        b = Book(); s = b.tx(5, L("FUD", "-40", "transfer_internal", "0.1", location="pocket:1", ref="p"), L("FUD", "40", "transfer_internal", "0.1", ref="p"))
        b.tx(6, L("FUD", "-10", "transfer_internal", "0.1", ref="q"), L("FUD", "10", "transfer_internal", "0.1", location="pocket:2", ref="q"))
        st = run(b.rows, RP())
        got = sorted((l.location, l.qty, l.status, l.basis_origin, l.open_block) for l in st.lots if l.qty > 0)
        self.assertEqual(got, [("pocket:2", D(10), "pending", "unrecorded_inflow", 5), ("wallet", D(30), "pending", "unrecorded_inflow", 5)])
        self.assertIn("basis_origin", fifo.LOT_COLS)

def lifo_take():
    """The engine's _take with the pool order reversed (newest first): a deliberate mutation."""
    src = inspect.getsource(fifo._take); key = "key=lambda l: (l.order, l.id))"
    assert src.count(key) == 1; ns = dict(vars(fifo)); exec(src.replace(key, "key=lambda l: (l.order, l.id), reverse=True)"), ns)
    return ns["_take"]

class MutationLifo(unittest.TestCase):
    """buy 1 ETH @1000, buy 1 ETH @2000, sell 1 ETH @3000 for USDC; mark 3000. FIFO: realized 2000, unrealized 1000.
    A LIFO engine reports realized 1000, unrealized 2000: the same total, so only a per-asset realized/unrealized split catches it."""
    def book(self):
        b = Book(); b.tx(1, L("USDC", "3000", "bridge_in", "1"))
        b.tx(2, L("USDC", "-1000", "swap", "1"), L("ETH", "1", "swap", "1000")); b.tx(3, L("USDC", "-2000", "swap", "1"), L("ETH", "1", "swap", "2000"))
        b.tx(4, L("ETH", "-1", "swap", "3000"), L("USDC", "3000", "swap", "1")); return b
    def test_fifo_passes(self):
        b = self.book(); c = recon(b, run(b.rows, RP()), RP(), 5); self.assertEqual(c["acceptance"], "PASS", c["failures"])
    def test_lifo_caught_by_reconciliation(self):
        b = self.book(); orig = fifo._take; fifo._take = lifo_take()
        try: st = run(b.rows, RP())
        finally: fifo._take = orig
        self.assertEqual(D(report(st, RP(), 5)["all"]["by_asset"]["ETH"]["realized"]), D(1000))   # the mutation took effect
        c = recon(b, st, RP(), 5)
        self.assertEqual((c["identity_pass"], c["acceptance"]), (False, "FAIL"))
        self.assertIn("asset ETH: realized residual -1000, unrealized residual 1000", c["failures"])
        self.assertEqual(c["total"]["residual"], 0)   # the total alone would have passed
    def test_lifo_caught_by_golden(self):
        from tests import test_fifo_golden as G
        orig = fifo._take; fifo._take = lifo_take()
        try: res = unittest.TextTestRunner(stream=open("/dev/null", "w"), verbosity=0).run(unittest.defaultTestLoader.loadTestsFromTestCase(G.G1BasicFifo))
        finally: fifo._take = orig
        self.assertGreater(len(res.failures) + len(res.errors), 0)

class IndependentOnGoldenBooks(unittest.TestCase):
    """The independent ledger side agrees with the engine on the earlier golden books (FIFO, migration, escrow fill, craft, gas, fee
    split). Upgrade / destroy / bundle books are not modelled by the ledger side (none on Base) and are skipped."""
    def test_books(self):
        from tests import test_fifo_golden as G, test_fifo_rulings as R, fifo_fixtures as F
        made = []; init = F.Book.__init__
        def rec(self): init(self); made.append(self)
        F.Book.__init__ = rec
        try:
            for cls, pol, as_of, mk in ((G.G1BasicFifo, G.P, 5, None), (G.G2MigrationPending, G.P, 5, None), (G.G3EscrowFill, G.P, 5, None),
                                        (G.G4Craft, G.P, 8, None),
                                        (R.G13GasFromEthLot, RP(), 6, MK), (R.G14FeeSplit, RP(), 4, MK)):
                made.clear(); t = cls(); t.setUp(); self.assertTrue(made, cls.__name__); b = made[-1]; st = run(b.rows, pol); m = mk or pol.mark
                c = recon(b, st, pol, as_of, m, NFTX)
                self.assertEqual(c["acceptance"], "PASS", (cls.__name__, c["failures"]))
        finally: F.Book.__init__ = init

if __name__ == "__main__": unittest.main()
