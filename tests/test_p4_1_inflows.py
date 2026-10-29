"""P4.1 rulings 1-6 (DESIGN §8). SYNTHETIC fixtures only (made-up legs, payers, prices and blocks; not chain data), except that the
payer addresses are the configured INTERNAL_ETH / DEX_ROUTERS entries so the rules are exercised through the real config."""
import unittest
from decimal import Decimal as D
from cryptopnl import classify, fifo, reconcile
from cryptopnl.classify import internal_rule, Review
from cryptopnl.config import INTERNAL_ETH, DEX_ROUTERS
from cryptopnl.fifo import run, FifoError
from cryptopnl.internal_eth import frames
from tests.fifo_fixtures import Book, L
from tests.test_fifo_rulings import RP, MK, NFTX, disp, lot, eqty

C = INTERNAL_ETH[8453]; W = "0x" + "aa" * 20; OTHER = "0x" + "bb" * 20
HOP = next(a for a, n in C["bridge_in"].items() if n == "hop"); PTD = next(iter(C["distribution"]))
LZ = next(a for a, n in C["refund"].items() if n.startswith("layerzero")); RUBIC = next(iter(C["dust"])); MM = next(iter(C["swap"]))
ROUTER = next(iter(DEX_ROUTERS[8453]))
def il(cp, wei, n=0): return dict(li=n - 100000, std="native", contract=None, token_id=None, qty=wei, cp=cp, trace=str(n))
def eth(wei, li=0): return dict(li=li, std="native", contract=None, token_id=None, qty=wei, cp=ROUTER)
def tok(q, li=1): return dict(li=li, std="erc20", contract="0x" + "cc" * 20, token_id=None, qty=q, cp=ROUTER)
SENT = {"from": W, "to": ROUTER}; NOT_SENT = {"from": OTHER, "to": HOP}

class InternalRule(unittest.TestCase):
    def test_bridge_in(self):   # rule 4
        pre, add, ref = internal_rule(8453, W, NOT_SENT, [], [il(HOP, 10**16)])
        self.assertEqual([(c, r) for _, c, r in pre], [("bridge_in", "bridge_in:hop")]); self.assertEqual((add, ref), ([], []))
    def test_bridge_payer_in_wallet_sent_tx_is_review(self):
        with self.assertRaises(Review): internal_rule(8453, W, SENT, [], [il(HOP, 1)])
    def test_distribution_is_income(self):   # rule 5 (identified distributor)
        pre, _, _ = internal_rule(8453, W, {"from": W, "to": PTD}, [], [il(PTD, 10**18)])
        self.assertEqual([(c, r) for _, c, r in pre], [("income", "distribution:aavegotchi_ptd")])
    def test_refund_nets_against_eth_sent(self):   # rule 3
        pre, add, ref = internal_rule(8453, W, SENT, [eth(-10**18), tok(5)], [il(LZ, 10**17)])
        self.assertEqual((pre, add, [r["qty"] for r in ref]), ([], [], [10**17]))
    def test_refund_larger_than_sent_is_review(self):
        with self.assertRaises(Review): internal_rule(8453, W, SENT, [eth(-10)], [il(ROUTER, 11)])
    def test_refund_without_eth_sent_is_review(self):
        with self.assertRaises(Review): internal_rule(8453, W, {"from": OTHER, "to": ROUTER}, [], [il(LZ, 5)])
    def test_dust_with_eth_sent_is_refund(self):   # rule 6 -> rule 3
        _, _, ref = internal_rule(8453, W, SENT, [eth(-100)], [il(RUBIC, 1)]); self.assertEqual(len(ref), 1)
    def test_dust_without_eth_sent_is_income(self):   # rule 6, never spam
        pre, _, ref = internal_rule(8453, W, SENT, [tok(-5)], [il(RUBIC, 1)])
        self.assertEqual(([(c, r) for _, c, r in pre], ref), ([("income", "dust:rubic")], []))
    def test_swap_output_pairs_with_token_out(self):   # rule 2
        pre, add, ref = internal_rule(8453, W, SENT, [tok(-30)], [il(MM, 10**15)])
        self.assertEqual((pre, len(add), ref), ([], 1, []))
    def test_swap_output_without_token_out_is_review(self):
        with self.assertRaises(Review): internal_rule(8453, W, SENT, [], [il(MM, 10**15)])
    def test_unknown_payer_is_review(self):
        with self.assertRaises(Review): internal_rule(8453, W, NOT_SENT, [], [il(OTHER, 1)])
        with self.assertRaises(Review): internal_rule(8453, W, SENT, [eth(-5)], [il(OTHER, 1)])
    def test_internal_send_goes_through_normal_rules(self):
        _, add, _ = internal_rule(8453, W, SENT, [], [il(OTHER, -7)]); self.assertEqual(len(add), 1)

class Frames(unittest.TestCase):
    """callTracer result: top level never counted; DELEGATECALL / STATICCALL carry no ETH; a reverted subtree is skipped."""
    T = {"type": "CALL", "from": W, "to": ROUTER, "value": "0x64", "calls": [
            {"type": "DELEGATECALL", "from": ROUTER, "to": OTHER, "value": "0x64"},                         # n=1, not value-moving
            {"type": "CALL", "from": ROUTER, "to": W, "value": "0xa"},                                     # n=2, refund -> kept
            {"type": "CALL", "from": ROUTER, "to": OTHER, "value": "0x5", "error": "execution reverted",   # n=3, reverted subtree
             "calls": [{"type": "CALL", "from": OTHER, "to": W, "value": "0x1"}]},
            {"type": "STATICCALL", "from": ROUTER, "to": W},
            {"type": "CALL", "from": ROUTER, "to": OTHER, "calls": [{"type": "CALL", "from": OTHER, "to": W, "value": "0x3"}]}]}
    def test_frames(self):
        self.assertEqual([(n, ta, int(x["value"], 16)) for n, ta, x in frames(W, self.T)], [(2, "1", 10), (6, "4.0", 3)])   # n = DFS index over frames outside reverted subtrees
    def test_reverted_tx(self):
        self.assertEqual(frames(W, {**self.T, "error": "out of gas"}), [])

def recon(b, st, as_of):
    return reconcile.check(fifo.report(st, RP(), as_of), fifo.gas(st), reconcile.ledger_side(b.rows, MK, NFTX, as_of), eqty(st))

class EngineRefundAndBridge(unittest.TestCase):
    """tx1: bridge_in 2 ETH @1000 (CCTP-style, resolved, basis 2000). tx2: swap 1 ETH @2000 for 1500 USDC; the router refunds
    0.25 ETH in the same tx -> one disposal of 0.75 ETH: cost 750, proceeds 1500, realized 750; no lot for the refund.
    tx3: Hop fill 0.5 ETH (ref bridge_in:hop:10) -> pending lot, basis_origin bridge_in, chain_origin 10; not income."""
    def setUp(self):
        b = Book(); b.tx(1, L("ETH", "2", "bridge_in", "1000"))
        self.s = b.tx(2, L("ETH", "-1", "swap", "2000"), L("USDC", "1500", "swap", "1"), L("ETH", "0.25", "swap", "2000", ref="eth_refund"))
        self.h = b.tx(3, L("ETH", "0.5", "bridge_in", "2000", ref="bridge_in:hop:10"))
        self.b = b; self.st = run(b.rows, RP())
    def test_refund_lowers_disposal(self):
        d = disp(self.st, self.s[0]); self.assertEqual(len(d), 1)
        self.assertEqual((d[0].qty, d[0].cost, d[0].proceeds, d[0].realized), (D("0.75"), D(750), D(1500), D(750)))
        self.assertEqual([l for l in self.st.lots if l.open_entry == self.s[2].id], [])
    def test_bridge_in_pending(self):
        l = lot(self.st, self.h[0])
        self.assertEqual((l.status, l.basis, l.basis_origin, l.pending_reason, l.chain_origin), ("pending", None, "bridge_in", "bridge_in", 10))
    def test_open_qty_equals_ledger_net(self):
        self.assertEqual(eqty(self.st)["ETH"], sum(e.qty for e in self.b.rows if e.asset == "ETH"))
    def test_reconciles_independently(self):
        c = recon(self.b, self.st, 4); self.assertEqual(c["acceptance"], "PASS", c["failures"])
    def test_manual_basis(self):
        b = Book(); h = b.tx(1, L("ETH", "0.5", "bridge_in", "2000", ref="bridge_in:across", manual_basis=D(900), manual_basis_id=7))
        l = lot(run(b.rows, RP()), h[0]); self.assertEqual((l.status, l.basis, l.basis_origin, l.manual_basis_id), ("manual", D(900), "bridge_in", 7))
    def test_refund_without_send_fails(self):
        b = Book(); b.tx(1, L("ETH", "0.1", "swap", "2000", ref="eth_refund"))
        with self.assertRaises(FifoError): run(b.rows, RP())
        with self.assertRaises(ValueError): reconcile.ledger_side(b.rows, MK, NFTX, 2)
    def test_refund_larger_than_sent_fails(self):
        b = Book(); b.tx(1, L("ETH", "1", "bridge_in", "1000")); b.tx(2, L("ETH", "-0.1", "swap", "2000"), L("ETH", "0.2", "swap", "2000", ref="eth_refund"))
        with self.assertRaises(FifoError): run(b.rows, RP())
        with self.assertRaises(ValueError): reconcile.ledger_side(b.rows, MK, NFTX, 3)

if __name__ == "__main__": unittest.main()

def esc():
    e = classify.Escrow(set()); e.type_cost = {}; return e

class Rule5DaoDistributionTag(unittest.TestCase):
    """Rule 5 ruling (architect, 18:18 PT): the PTD claim stays income at FMV, tagged income_subtype=dao_distribution and
    source_ref=0xf50326e1… (the PTD MerkleDistributor), and the report shows it as its own income line. SYNTHETIC qty / prices."""
    def test_classify_tags_the_claim(self):
        cat, out, _ = classify.plan_full(8453, W, {"from": W, "to": PTD, "selector": "0x2f52ebb7"}, [il(PTD, 10**18)], [], set(), 1, esc())
        self.assertEqual(cat, "income")
        self.assertEqual([(o["cat"], o["ref"], o.get("income_subtype"), o.get("source_ref")) for o in out],
                         [("income", "distribution:aavegotchi_ptd", "dao_distribution", PTD)])
        self.assertEqual(PTD, "0xf50326e1a6c6949cc390c4efe8ea538e29a4fa11")
    def test_other_income_untagged(self):
        _, out, _ = classify.plan_full(8453, W, {"from": W, "to": ROUTER}, [tok(-5)], [], set(), 1, esc())   # no internal legs
        self.assertTrue(all(o.get("income_subtype") is None for o in out))
        _, out, _ = classify.plan_full(8453, W, SENT, [tok(-5), il(RUBIC, 1)], [], set(), 1, esc())   # rule 6 dust income: untagged
        self.assertEqual([(o["ref"], o.get("income_subtype")) for o in out if o["cat"] == "income"], [("dust:rubic", None)])
    def test_report_income_line(self):
        from cryptopnl import p4
        b = Book(); b.tx(1, L("ETH", "1", "income", "3000", income_subtype="dao_distribution", source_ref=PTD))
        b.tx(2, L("GHST", "10", "income", "4")); b.tx(3, L("FUD", "5", "income"))   # FUD unpriced: counted, never 0
        st = run(b.rows, RP()); lines = p4.income_lines(st, b.rows, fifo.report(st, RP(), 4)["income_usdc"])
        self.assertEqual([(x["income_subtype"], x["source_ref"], x["usdc"], x["entries"], x["unpriced_entries"]) for x in lines],
                         [("dao_distribution", PTD, D(3000), 1, 0), ("general", None, D(40), 2, 1)])

class Rule5FinalIncome(unittest.TestCase):
    """Rule 5 FINAL (option a, user_default 2026-10-28): the PTD claim is income. Priced: one ETH lot at FMV and the FMV in income_usdc.
    Unpriced: the lot is pending (no_price), never basis 0, and the income line counts it as unpriced. SYNTHETIC qty / price."""
    def book(self, price):
        b = Book(); e = b.tx(1, L("ETH", "1.0141283024", "income", price, income_subtype="dao_distribution", source_ref=PTD))[0]
        st = run(b.rows, RP()); return b, e, st
    def test_priced(self):
        b, e, st = self.book("3000"); l = lot(st, e); rep = fifo.report(st, RP(), 2)
        self.assertEqual((l.status, l.basis, l.kind), ("resolved", D("3042.3849072"), "income"))
        self.assertEqual(D(rep["income_usdc"]), D("3042.3849072"))
        from cryptopnl import p4
        self.assertEqual([(x["income_subtype"], x["usdc"]) for x in p4.income_lines(st, b.rows, rep["income_usdc"])], [("dao_distribution", D("3042.3849072"))])
        self.assertFalse(any(l2.kind in ("basis_adjustment", "return_of_capital") for l2 in st.lots))
    def test_unpriced_is_pending_never_zero(self):
        b, e, st = self.book(None); l = lot(st, e)
        self.assertEqual((l.status, l.basis, l.pending_reason), ("pending", None, "no_price"))
        from cryptopnl import p4
        x = p4.income_lines(st, b.rows, fifo.report(st, RP(), 2)["income_usdc"])
        self.assertEqual([(y["income_subtype"], y["usdc"], y["unpriced_entries"]) for y in x], [("dao_distribution", D(0), 1)])


class IncomeLinesRounding(unittest.TestCase):
    """Canonical P4.1 reconcile: per-line sums at Decimal prec 50 can differ from the engine's single sum in the last digit; that is
    tolerated (<= 1e-30 USDC), a real mismatch is not. SYNTHETIC entries and values."""
    def setup(self, vals):
        from types import SimpleNamespace as N
        rows = [N(id=i, income_subtype=s, source_ref=r) for i, (s, r, _) in enumerate(vals)]
        return N(income=[(i, 1, v) for i, (_, _, v) in enumerate(vals)]), rows
    def test_last_digit_rounding_tolerated(self):
        from decimal import localcontext
        from cryptopnl import p4
        a = D("1000.4189423280598324682034176848787065247069005929"); b = D("0.2244696291370285873357736589430185283444852791198")
        c = D("0.9622463907656828081414129173666257297316986144368")   # random digits found to round differently by order
        with localcontext() as ctx:
            ctx.prec = 50
            vals = [("dao_distribution", PTD, a), (None, None, b), (None, None, c)]
            st, rows = self.setup(vals); total = fifo._s(sum((v for _, _, v in st.income), D(0)))
            self.assertNotEqual(a + (b + c), D(total))   # the fixture really hits the rounding-order case
            lines = p4.income_lines(st, rows, total); self.assertEqual([x["entries"] for x in lines], [1, 2])
            with self.assertRaises(ValueError): p4.income_lines(st, rows, str(D(total) + D("0.01")))
