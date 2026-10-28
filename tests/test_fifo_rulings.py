"""P4 rulings (2026-10-28) and 'P4 rulings 2' as golden fixtures (SYNTHETIC, hand-built; expected values computed by hand below).
No DB, no network. RP = the rulings' switch values (cryptopnl/p4_policy.json) with a fixed synthetic mark table."""
import unittest
from decimal import Decimal as D
from cryptopnl.fifo import Policy, PolicyRequired, run, report, gas, identity, Mark
from cryptopnl import reconcile
from tests.fifo_fixtures import Book, L, marks

MK = marks({"GHST": "4", "USDC": "1", "ETH": "3000", "FUD": "0.004"})
def RP(**kw):
    base = dict(fee="capitalize", fee_without_trade="expense", fee_split="basis_else_equal", deposit="pending", withdrawal="exit",
                internal_transfer="carry", nft_mark="exclude", mark=MK, queue_split="recipe_else_equal", shortfall="pending")
    return Policy(**{**base, **kw})
def disp(st, e): return [d for d in st.disposals if d.entry == e.id]
def lot(st, e): return [l for l in st.lots if l.open_entry == e.id][0]
NFTX = lambda a, b, l=None: None   # Q8 stand-in: no NFT has a stored price here

def gas_book():
    """bridge_in 10000 USDC; buy 1 ETH @2000 (basis 2000). Then ETH is @3000 and each gas leg is 0.001 ETH = 3 USDC at market:
    tx3 buy 25 GHST @4 for 100 USDC + gas: gas disposal proceeds 3, cost 0.001 x 2000 = 2, ETH realized +1; GHST basis 100 + 3 = 103.
    tx4 gas only (no trade leg): gas_expense 3; disposal proceeds 3, cost 2, realized +1.
    tx5 50 USDC paid for an untracked NFT (excluded) + gas: no acquisition, so gas comes off the sale: proceeds 50 - 3 = 47, cost 50, -3;
        gas disposal +1.
    Open at the marks: USDC 7850 (basis 7850), ETH 0.997 (basis 1994, MV 2991, +997), GHST 25 (basis 103, MV 100, -3).
    realized = 0 + 0 - 3 + 1 + 1 + 1 = 0; unrealized = 994; realized + unrealized - gas_expense = 991.
    Ledger side (no gas): proceeds 2000 + 100 + 50 = 2150; MV 7850 + 2991 + 100 = 10941; acquisition basis 10000 + 2000 + 100 = 12100
    -> 2150 + 10941 - 12100 = 991."""
    b = Book(); b.tx(1, L("USDC", "10000", "bridge_in", "1", source="numeraire"))
    b.tx(2, L("USDC", "-2000", "swap", "1"), L("ETH", "1", "swap", "2000"))
    t3 = b.tx(3, L("USDC", "-100", "swap", "1"), L("GHST", "25", "swap", "4"), L("ETH", "-0.001", "fee", "3000"))
    t4 = b.tx(4, L("ETH", "-0.001", "fee", "3000"))
    t5 = b.tx(5, L("USDC", "-50", "nft_buy", "1"), L("PORTAL#1", "1", "untracked", nft=True, flag="untracked"), L("ETH", "-0.001", "fee", "3000"))
    return b, t3, t4, t5

class G13GasFromEthLot(unittest.TestCase):
    def setUp(self): self.b, self.t3, self.t4, self.t5 = gas_book(); self.st = run(self.b.rows, RP()); self.r = report(self.st, RP(), 6)
    def test_gas_realizes_eth_pnl_and_goes_into_basis(self):
        d = disp(self.st, self.t3[2])[0]; g = lot(self.st, self.t3[1])
        self.assertEqual((d.kind, d.qty, d.proceeds, d.cost, d.realized), ("fee_capitalized", D("0.001"), D(3), D(2), D(1)))
        self.assertEqual((g.basis, g.fee, g.split_method), (D(103), D(3), "basis"))
    def test_gas_without_trade_is_gas_expense(self):
        d = disp(self.st, self.t4[0])[0]
        self.assertEqual((d.kind, d.proceeds, d.cost, d.realized, d.expense), ("fee", D(3), D(2), D(1), D(3)))
    def test_gas_off_sale_proceeds(self):
        s = disp(self.st, self.t5[0])[0]; f = disp(self.st, self.t5[2])[0]
        self.assertEqual((s.kind, s.proceeds, s.cost, s.realized, f.realized), ("sale", D(47), D(50), D(-3), D(1)))
    def test_totals_and_gas_lines(self):
        a = self.r["all"]
        self.assertEqual((D(a["realized_usdc"]), D(a["unrealized_usdc"]), D(a["market_value_usdc"])), (D(0), D(994), D(10941)))
        g = gas(self.st)
        self.assertEqual((g["gas_disposals"], D(g["gas_mv_usdc"]), D(g["gas_expense_usdc"]), D(g["gas_capitalized_usdc"]), D(g["gas_realized_usdc"]),
                          D(g["gas_in_basis_usdc"]), D(g["gas_on_pending_lots_usdc"])), (3, D(9), D(3), D(6), D(3), D(3), D(0)))
        self.assertEqual(self.r["excluded_rows"], {"untracked": 1}); self.assertEqual(D(identity(self.st)["residual"]), 0)
    def test_reconciliation(self):
        L_ = reconcile.ledger_side(self.b.rows, reconcile.masks(self.st), MK, NFTX, 6)
        P = L_["per_asset"]
        self.assertEqual({a: P[a]["rhs"] for a in P}, {"ETH": D(1000), "GHST": D(-3), "USDC": D(-3)})   # = engine realized + unrealized per asset
        c = reconcile.check(self.r, gas(self.st), L_, {"USDC": D(7850), "ETH": D("0.997"), "GHST": D(25)},
                            {"USDC": D(7850), "ETH": D("0.997"), "GHST": D(25)}, {})
        self.assertTrue(c["pass"], c["failures"]); self.assertEqual((c["total"]["engine_side"], c["total"]["ledger_side"]), (D(991), D(991)))
        self.assertEqual(L_["gas_txs"], {"into_basis": 1, "off_proceeds": 1, "expense": 1})
    def test_reconciliation_catches_an_engine_error(self):
        r = report(self.st, RP(), 6); r["all"]["by_asset"]["GHST"]["unrealized"] = "-2.98"      # 0.02 off
        c = reconcile.check(r, gas(self.st), reconcile.ledger_side(self.b.rows, reconcile.masks(self.st), MK, NFTX, 6), {}, {}, {})
        self.assertFalse(c["pass"]); self.assertIn("asset GHST: residual 0.02", c["failures"][0])

class G14FeeSplit(unittest.TestCase):
    """bridge_in 100 USDC and 1 ETH @2000. tx2: 30 USDC -> 10 GHST @1 (10) + 5 FUD @4 (20), gas 3: split 1:2 by basis -> GHST 11, FUD 22.
    tx3: 30 USDC -> two unpriced assets (KEK, ALPHA: no trade-implied value with two unknowns) -> both pending; gas 3 split equally
    (no resolved lot with basis > 0): each pending lot keeps fee 1.5, basis NULL, outside totals."""
    def setUp(self):
        b = Book(); b.tx(1, L("USDC", "100", "bridge_in", "1"), L("ETH", "1", "bridge_in", "2000"))
        self.t2 = b.tx(2, L("USDC", "-30", "swap", "1"), L("GHST", "10", "swap", "1"), L("FUD", "5", "swap", "4"), L("ETH", "-0.001", "fee", "3000"))
        self.t3 = b.tx(3, L("USDC", "-30", "swap", "1"), L("KEK", "10", "swap"), L("ALPHA", "10", "swap"), L("ETH", "-0.001", "fee", "3000"))
        self.b = b; self.st = run(b.rows, RP())
    def test_basis_split(self):
        g, f = lot(self.st, self.t2[1]), lot(self.st, self.t2[2])
        self.assertEqual([(x.basis, x.fee, x.split_method) for x in (g, f)], [(D(11), D(1), "basis"), (D(22), D(2), "basis")])
    def test_equal_split_on_pending(self):
        k, a = lot(self.st, self.t3[1]), lot(self.st, self.t3[2])
        self.assertEqual([(x.status, x.basis, x.fee, x.split_method) for x in (k, a)], [("pending", None, D("1.5"), "equal")] * 2)
        self.assertEqual(D(gas(self.st)["gas_on_pending_lots_usdc"]), D(3))
    def test_reconciliation_excludes_pending_on_both_sides(self):
        mk = marks({"GHST": "4", "USDC": "1", "ETH": "3000", "FUD": "0.004"}); r = report(self.st, RP(mark=mk), 4)
        L_ = reconcile.ledger_side(self.b.rows, reconcile.masks(self.st), mk, NFTX, 4)
        self.assertEqual({a: v["rhs"] for a, v in L_["per_asset"].items()}, {"ETH": D(1000), "FUD": D("-21.98"), "GHST": D(29), "USDC": D(0)})
        c = reconcile.check(r, gas(self.st), L_, {}, {}, {}); self.assertTrue(c["pass"], c["failures"])
        self.assertEqual(L_["gas_share_on_pending_acquisitions"], D(3))

class G15Exit(unittest.TestCase):
    """Q-B: deposit 1 ETH @2000 -> pending lot (unknown basis, not 0, not MV). Withdraw 0.5 @2500 -> exit, still pending (consumes a
    pending lot): proceeds NULL, realized NULL (pending), MV 1250 kept for display; counted."""
    def test_pending_exit(self):
        b = Book(); dep = b.tx(1, L("ETH", "1", "deposit", "2000")); w = b.tx(2, L("ETH", "-0.5", "withdrawal", "2500"))
        st = run(b.rows, RP()); d = disp(st, w[0])[0]; r = report(st, RP(), 3)
        self.assertEqual((lot(st, dep[0]).status, lot(st, dep[0]).basis, d.kind, d.lot_status, d.proceeds, d.realized, d.display_mv),
                         ("pending", None, "exit", "pending", None, None, D(1250)))
        self.assertEqual((r["exits"], r["exits_pending"], r["pending_disposals"], D(r["all"]["realized_usdc"])), (1, 1, 1, D(0)))

class G16CraftSplit(unittest.TestCase):
    """Q-G: 100 FUD @0.1 (income, basis 10) crafted into item A and item B under one ref (inputs worth 10).
    Recipe costs A 3, B 1 per unit -> A 7.5, B 2.5 (recipe). B's recipe missing -> equal 5 / 5, flagged split_method=equal (fallback).
    A free craft (no inputs) keeps basis 0."""
    def book(self):
        b = Book(); b.tx(1, L("FUD", "100", "income", "0.1"))
        t = b.tx(2, L("FUD", "-100", "craft", "0.1", ref="craft:instant"), L("A", "1", "craft", ref="craft:instant", nft=True),
                 L("B", "1", "craft", ref="craft:instant", nft=True))
        f = b.tx(3, L("C", "1", "craft", ref="craft:instant:free", nft=True)); return b, t, f
    def test_recipe(self):
        b, t, f = self.book(); st = run(b.rows, RP(recipe=lambda a, blk: {"A": D(3), "B": D(1)}.get(a)))
        self.assertEqual([(lot(st, x).basis, lot(st, x).split_method) for x in t[1:]], [(D("7.5"), "recipe"), (D("2.5"), "recipe")])
        self.assertEqual((lot(st, f[0]).basis, lot(st, f[0]).kind, report(st, RP(), 4)["craft_split_equal_fallbacks"]), (D(0), "free_craft", 0))
    def test_equal_fallback(self):
        b, t, _ = self.book(); st = run(b.rows, RP(recipe=lambda a, blk: {"A": D(3)}.get(a)))
        self.assertEqual([(lot(st, x).basis, lot(st, x).split_method) for x in t[1:]], [(D(5), "equal"), (D(5), "equal")])
        self.assertEqual(report(st, RP(), 4)["craft_split_equal_fallbacks"], 2)
    def test_required(self):
        b, _, _ = self.book()
        with self.assertRaises(PolicyRequired) as c: run(b.rows, RP(queue_split=None))
        self.assertEqual(c.exception.question, "Q-G")

class G17Shortfall(unittest.TestCase):
    """Q-H (proposal, pending the architect): 100 FUD leave pocket:1 for the wallet but the ledger never recorded them arriving in the
    pocket. shortfall=pending opens a pending lot (unrecorded_inflow) at the pocket for the 100, which the custody move carries to the
    wallet; engine open qty 100 vs ledger net qty 0 is explained by it."""
    def test_pending_unrecorded_inflow(self):
        b = Book(); b.tx(1, L("FUD", "-100", "transfer_internal", "0.1", location="pocket:1", ref="pocket:1"),
                         L("FUD", "100", "transfer_internal", "0.1", ref="pocket:1"))
        with self.assertRaises(PolicyRequired) as c: run(b.rows, RP(shortfall=None))
        self.assertEqual(c.exception.question, "Q-H")
        st = run(b.rows, RP()); r = report(st, RP(), 2); m = reconcile.masks(st)
        self.assertEqual((r["pending_reasons"], r["holdings_by_location"], m["unrecorded_qty"]), ({"unrecorded_inflow": 1}, {"FUD@wallet": "100"}, {"FUD": D(100)}))
        L_ = reconcile.ledger_side(b.rows, m, MK, NFTX, 2)
        c = reconcile.check(r, gas(st), L_, {"FUD": D(100)}, {}, m["unrecorded_qty"])
        self.assertTrue(c["pass"], c["failures"]); self.assertEqual(c["qty_mismatches"]["FUD"]["explained"], True)

class RecomputeUnderRulings(unittest.TestCase):
    """rebuild == incremental (md5 of lots/disposals and the report) at every block boundary of the rulings books."""
    def test_every_boundary(self):
        from cryptopnl.fifo import md5
        b1 = gas_book()[0]; b2 = G14FeeSplit(); b2.setUp(); b3 = G16CraftSplit().book()[0]
        n = 0
        for rows in (b1.rows, b2.b.rows, b3.rows):
            full = run(rows, RP()); blocks = sorted({e.block for e in rows})
            for x in blocks[:-1]:
                inc = run([e for e in rows if e.block > x], RP(), run([e for e in rows if e.block <= x], RP()))
                self.assertEqual(md5(inc), md5(full)); self.assertEqual(report(inc, RP(), 9), report(full, RP(), 9)); n += 1
        self.assertGreaterEqual(n, 8)
