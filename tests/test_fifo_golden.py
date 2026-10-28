"""P4 golden FIFO fixtures (SYNTHETIC, hand-built). Expected values are computed by hand in the comments; no DB, no network."""
import unittest
from decimal import Decimal as D
from cryptopnl.fifo import Policy, PolicyRequired, FifoError, run, report, identity, md5
from tests.fifo_fixtures import Book, L, marks

P = Policy(mark=marks({"GHST": "4", "USDC": "1", "ETH": "3000", "FUD": "0.004", "KEK": "0.02"}), nft_mark="exclude")
def disp(st, entry): return [d for d in st.disposals if d.entry == entry.id]
def lots(st, entry): return [l for l in st.lots if l.open_entry == entry.id]

class G1BasicFifo(unittest.TestCase):
    """bridge_in 100 USDC at par; buy 10 GHST @1 (10 USDC); buy 10 GHST @2 (20 USDC); sell 15 GHST @3 for 45 USDC.
    GHST disposals: lot1 10 -> proceeds 30, cost 10, +20; lot2 5 -> proceeds 15, cost 10, +5. Realized 25 (USDC legs at par: 0).
    Open: USDC 70 (basis 70) + 45 (basis 45); GHST 5 (basis 10). Mark GHST 4: unrealized 5*4-10 = 10; MV 70+45+20 = 135.
    Identity: root basis 100+10+20+45 = 175 = cost 10+20+10+10 = 50 + open 125."""
    def setUp(self):
        b = Book(); self.br = b.tx(1, L("USDC", "100", "bridge_in", "1", source="numeraire"))
        self.b1 = b.tx(2, L("USDC", "-10", "swap", "1"), L("GHST", "10", "swap", "1"))
        self.b2 = b.tx(3, L("USDC", "-20", "swap", "1"), L("GHST", "10", "swap", "2"))
        self.s = b.tx(4, L("GHST", "-15", "swap", "3"), L("USDC", "45", "swap", "1")); self.b = b
        self.st = run(b.rows, P); self.r = report(self.st, P, 5)
    def test_disposals(self):
        d = disp(self.st, self.s[0])
        self.assertEqual([(x.qty, x.proceeds, x.cost, x.realized) for x in d], [(D(10), D(30), D(10), D(20)), (D(5), D(15), D(10), D(5))])
    def test_totals(self):
        a = self.r["all"]
        self.assertEqual((D(a["realized_usdc"]), D(a["unrealized_usdc"]), D(a["market_value_usdc"]), D(a["open_basis_usdc"])), (D(25), D(10), D(135), D(125)))
        self.assertEqual(self.r["holdings_by_location"], {"GHST@wallet": "5", "USDC@wallet": "115"})
    def test_identity(self):
        i = identity(self.st)
        self.assertEqual((D(i["basis_opened_root"]), D(i["cost_disposed"]), D(i["basis_open"]), D(i["residual"])), (D(175), D(50), D(125), D(0)))
    def test_deterministic(self): self.assertEqual(md5(self.st), md5(run(list(reversed(self.b.rows)), P)))

class G2MigrationPending(unittest.TestCase):
    """§8: migration_in gotchi #1 with no basis -> pending, basis and price source NULL. Sold for 100 GHST @0.5 (50 USDC): a pending
    disposal (cost NULL), excluded from realized; the GHST received opens a lot at 50. Gotchi #2 carries a Polygon basis of 30
    (resolved, chain_origin 137); sold for 200 GHST @0.5 = 100 -> realized 70. Gotchi #3 has user_default's manual basis 12 (manual, low).
    Open: GHST 300 (basis 150), mark 4 -> unrealized 1200-150 = 1050; gotchi #3 is an open NFT lot -> nft_mark 'exclude' -> 1 unmarked.
    Counts: pending lots 1 (0 open), pending disposals 1."""
    def setUp(self):
        b = Book()
        self.m1 = b.tx(1, L("GOTCHI#1", "1", "migration_in", nft=True, chain_origin=137))
        self.m2 = b.tx(1, L("GOTCHI#2", "1", "migration_in", nft=True, chain_origin=137, carry_basis=D(30), carry_source="polygon_fifo", carry_label="high"), tx_index=1)
        self.m3 = b.tx(1, L("GOTCHI#3", "1", "migration_in", nft=True, chain_origin=137, manual_basis=D(12), manual_basis_id=7), tx_index=2)
        self.s1 = b.tx(2, L("GOTCHI#1", "-1", "nft_sale", nft=True), L("GHST", "100", "nft_sale", "0.5"))
        self.s2 = b.tx(3, L("GOTCHI#2", "-1", "nft_sale", nft=True), L("GHST", "200", "nft_sale", "0.5"))
        self.st = run(b.rows, P); self.r = report(self.st, P, 4)
    def test_pending_lot_has_null_source(self):
        l = lots(self.st, self.m1[0])[0]
        self.assertEqual((l.status, l.basis, l.source, l.label, l.pending_reason, l.chain_origin), ("pending", None, None, None, "migration", 137))
    def test_carry_and_manual(self):
        l2, l3 = lots(self.st, self.m2[0])[0], lots(self.st, self.m3[0])[0]
        self.assertEqual((l2.status, l2.basis, l2.source, l2.kind), ("resolved", D(30), "polygon_fifo", "migration"))
        self.assertEqual((l3.status, l3.basis, l3.source, l3.label, l3.manual_basis_id), ("manual", D(12), "manual", "low", 7))
    def test_pending_disposal_excluded(self):
        d = disp(self.st, self.s1[0])[0]
        self.assertEqual((d.lot_status, d.cost, d.realized, d.proceeds), ("pending", None, None, D(50)))
        self.assertEqual((self.r["pending_lots_total"], self.r["pending_lots_open"], self.r["pending_disposals"]), (1, 0, 1))
    def test_totals(self):
        a = self.r["all"]
        self.assertEqual((D(a["realized_usdc"]), D(a["unrealized_usdc"]), a["unmarked_nft_lots"]), (D(70), D(1050), 1))
        self.assertEqual(self.r["income_usdc"], "0")    # migration is custody, never income
    def test_nft_mark_hook_required(self):
        with self.assertRaises(PolicyRequired) as c: report(self.st, Policy(mark=P.mark), 4)
        self.assertEqual(c.exception.question, "Q-D")

class G3EscrowFill(unittest.TestCase):
    """§8 buy-order escrow. income 100 GHST @0.5 (lot basis 50, income 50). escrow_out 40 GHST -> escrow:diamond (custody, lot split:
    40 at escrow basis 20, 60 at wallet basis 30). Fill: 20 GHST from escrow @0.75 pays for wearable #9 (trade-implied basis 15):
    proceeds 15, cost 10, +5, payment_for = the wearable leg. Cancel the rest: escrow_return 20 -> wallet, basis 10 unchanged.
    Open GHST: 60 (30) + 20 (10) at wallet = 80 GHST, basis 40."""
    def setUp(self):
        b = Book(); D_ = "escrow:0xdiamond"
        self.inc = b.tx(1, L("GHST", "100", "income", "0.5"))
        self.out = b.tx(2, L("GHST", "-40", "escrow_out", ref="order:1"), L("GHST", "40", "escrow_out", location=D_, ref="order:1"))
        self.fill = b.tx(3, L("GHST", "-20", "nft_buy", "0.75", location=D_, ref="order:1", trade_group="t1"), L("WEARABLE#9", "1", "nft_buy", nft=True, trade_group="t1"))
        self.ret = b.tx(4, L("GHST", "-20", "escrow_return", location=D_, ref="order:1"), L("GHST", "20", "escrow_return", ref="order:1"))
        self.st = run(b.rows, P); self.r = report(self.st, P, 5)
    def test_fill(self):
        d = disp(self.st, self.fill[0])
        self.assertEqual([(x.qty, x.proceeds, x.cost, x.realized, x.payment_for, x.kind) for x in d], [(D(20), D(15), D(10), D(5), self.fill[1].id, "sale")])
        w = lots(self.st, self.fill[1])[0]
        self.assertEqual((w.basis, w.source, w.status), (D(15), "trade", "resolved"))
    def test_custody_keeps_basis(self):
        g = [l for l in self.st.lots if l.asset == "GHST" and l.qty > 0]
        self.assertEqual(sorted((l.location, l.qty, l.remaining_basis()) for l in g), [("wallet", D(20), D(10)), ("wallet", D(60), D(30))])
        self.assertEqual(self.r["holdings_by_location"]["GHST@wallet"], "80")
        self.assertNotIn("GHST@escrow:0xdiamond", self.r["holdings_by_location"])
        self.assertEqual((D(self.r["all"]["realized_usdc"]), D(self.r["income_usdc"])), (D(5), D(50)))
        self.assertEqual(D(identity(self.st)["residual"]), 0)

class G4Craft(unittest.TestCase):
    """§9 rule 3. income FUD 1000 @0.002 (basis 2), KEK 100 @0.01 (basis 1).
    Instant paid craft: FUD -500 @0.004 (proceeds 2, cost 1, +1) and KEK -50 @0.02 (proceeds 1, cost 0.5, +0.5) -> installation #10 basis 3.
    Free craft: tile #5 x2 with no inputs -> basis 0, kind free_craft, NOT income.
    Queued: craft_pending FUD -250 @0.004 (proceeds 1, cost 0.5, +0.5) -> bucket craft:queue:inst:7 = 1; the claim mints #11 at basis 1.
    A claim with no queued cost (queue 99) -> pending lot (queue_unmatched), never 0. Realized 1 + 0.5 + 0.5 = 2."""
    def setUp(self):
        b = Book()
        b.tx(1, L("FUD", "1000", "income", "0.002"), L("KEK", "100", "income", "0.01"))
        self.c = b.tx(2, L("FUD", "-500", "craft", "0.004", ref="craft:instant"), L("KEK", "-50", "craft", "0.02", ref="craft:instant"),
                      L("INST#10", "1", "craft", nft=True, ref="craft:instant"))
        self.free = b.tx(3, L("TILE#5", "2", "craft", nft=True, ref="craft:instant:free"))
        self.q = b.tx(4, L("FUD", "-250", "craft_pending", "0.004", ref="craft:queue:inst:7"))
        self.b = b; self.mid = run(b.rows, P)
        self.claim = b.tx(5, L("INST#11", "1", "craft", nft=True, ref="craft:queue:inst:7"))
        self.orphan = b.tx(6, L("INST#12", "1", "craft", nft=True, ref="craft:queue:inst:99"))
        self.st = run(b.rows, P); self.r = report(self.st, P, 7)
    def test_instant(self):
        self.assertEqual([(x.proceeds, x.cost, x.realized, x.kind) for x in disp(self.st, self.c[0]) + disp(self.st, self.c[1])],
                         [(D(2), D(1), D(1), "craft_input"), (D(1), D("0.5"), D("0.5"), "craft_input")])
        l = lots(self.st, self.c[2])[0]; self.assertEqual((l.basis, l.source, l.kind), (D(3), "craft", "craft"))
    def test_free_craft_is_basis_0_not_income(self):
        l = lots(self.st, self.free[0])[0]
        self.assertEqual((l.basis, l.qty, l.kind, l.status), (D(0), D(2), "free_craft", "resolved"))
        self.assertEqual(len(self.st.income), 2); self.assertEqual(D(self.r["income_usdc"]), D(3))
    def test_queue_until_claim(self):
        self.assertEqual(self.mid.buckets, {"craft:queue:inst:7": [D(1), "high", None]})
        self.assertEqual(report(self.mid, P, 5)["open_cost_buckets"], {"craft:queue:inst:7": ["1", "high", None]})
        l = lots(self.st, self.claim[0])[0]; self.assertEqual((l.basis, l.kind), (D(1), "craft_claim"))
        self.assertEqual(self.st.buckets, {})
    def test_unmatched_claim_pending(self):
        l = lots(self.st, self.orphan[0])[0]
        self.assertEqual((l.status, l.basis, l.source, l.pending_reason), ("pending", None, None, "queue_unmatched"))
    def test_realized(self): self.assertEqual(D(self.r["all"]["realized_usdc"]), D(2))
    def test_joined_queue_ref_needs_policy(self):
        b = Book(); b.tx(1, L("FUD", "100", "income", "0.002"))
        b.tx(2, L("FUD", "-100", "craft_pending", "0.004", ref="craft:queue:inst:7;craft:queue:inst:8"))
        with self.assertRaises(PolicyRequired) as c: run(b.rows, P)
        self.assertEqual(c.exception.question, "Q-G")
        st = run(b.rows, Policy(queue_split="equal"))   # 0.4 USDC shared equally by the two queues
        self.assertEqual(st.buckets, {"craft:queue:inst:7": [D("0.2"), "high", "equal"], "craft:queue:inst:8": [D("0.2"), "high", "equal"]})

def _parcel_book():
    """Shared synthetic setup: parcel #42 bought for 100 GHST @0.5 (trade-implied basis 50); FUD 1000 income @0.002 (basis 2);
    installation #10 crafted from FUD -500 @0.004 (basis 2); tile #5 x2 free (basis 0); both equipped on parcel 42 (custody)."""
    b = Book()
    b.tx(1, L("GHST", "100", "income", "0.5"), L("FUD", "1000", "income", "0.002"))
    b.tx(2, L("GHST", "-100", "nft_buy", "0.5", trade_group="p"), L("PARCEL#42", "1", "nft_buy", nft=True, trade_group="p"))
    b.tx(3, L("FUD", "-500", "craft", "0.004", ref="craft:instant"), L("INST#10", "1", "craft", nft=True, ref="craft:instant"))
    b.tx(4, L("TILE#5", "2", "craft", nft=True, ref="craft:instant:free"))
    b.tx(5, L("INST#10", "-1", "transfer_internal", nft=True, ref="parcel:42"), L("INST#10", "1", "transfer_internal", nft=True, location="parcel:42", ref="parcel:42"),
         L("TILE#5", "-2", "transfer_internal", nft=True, ref="parcel:42"), L("TILE#5", "2", "transfer_internal", nft=True, location="parcel:42", ref="parcel:42"))
    return b

class G5Upgrade(unittest.TestCase):
    """§9 rule 4. Upgrade cost: FUD -100 @0.004 (proceeds 0.4, cost 0.2, +0.2) into bucket upgrade:realm:42:queue:0. Finalize: #20 minted
    to the wallet and re-equipped (wallet legs net 0); #10 leaves parcel:42 with NO realized PnL (proceeds = cost = 2); #20 opens at
    parcel:42 with basis 2 + 0.4 = 2.4. Realized: craft input +1 (tx 3) + upgrade input +0.2 = 1.2."""
    def setUp(self):
        b = _parcel_book(); R = "upgrade:realm:42:queue:0"
        self.cost = b.tx(6, L("FUD", "-100", "upgrade", "0.004", ref=R))
        self.fin = b.tx(7, L("INST#20", "1", "upgrade", nft=True, ref=R), L("INST#20", "-1", "upgrade", nft=True, ref=R),
                        L("INST#10", "-1", "upgrade", nft=True, location="parcel:42", ref=R), L("INST#20", "1", "upgrade", nft=True, location="parcel:42", ref=R))
        self.b = b; self.st = run(b.rows, P); self.r = report(self.st, P, 8)
    def test_old_closes_without_pnl(self):
        d = disp(self.st, self.fin[2])[0]; self.assertEqual((d.kind, d.proceeds, d.cost, d.realized), ("upgrade_close", D(2), D(2), D(0)))
    def test_new_lot(self):
        l = lots(self.st, self.fin[3])[0]; self.assertEqual((l.basis, l.location, l.kind), (D("2.4"), "parcel:42", "upgrade"))
        self.assertEqual(self.r["holdings_by_location"].get("INST#20@parcel:42"), "1"); self.assertNotIn("INST#10@parcel:42", self.r["holdings_by_location"])
    def test_realized(self):
        self.assertEqual(D(self.r["all"]["realized_usdc"]), D("1.2")); self.assertEqual(D(identity(self.st)["residual"]), 0)
    def test_missing_cost_is_pending(self):
        b = _parcel_book(); R = "upgrade:realm:42:queue:5"
        f = b.tx(7, L("INST#10", "-1", "upgrade", nft=True, location="parcel:42", ref=R), L("INST#20", "1", "upgrade", nft=True, location="parcel:42", ref=R))
        l = lots(run(b.rows, P), f[1])[0]; self.assertEqual((l.status, l.pending_reason, l.source), ("pending", "upgrade_cost_unmatched", None))

class G6DestroyRefund(unittest.TestCase):
    """§9 rule 5, refund type 0: installation #10 (basis 2) at parcel:42 destroyed with a refund of 250 FUD @0.004 = 1:
    disposal proceeds 1, cost 2, realized -1; the refunded FUD opens at basis 1. Realized total: +1 (craft input) - 1 = 0."""
    def setUp(self):
        b = _parcel_book()
        self.d = b.tx(6, L("INST#10", "-1", "destroy_refund", nft=True, location="parcel:42", ref="parcel:42"), L("FUD", "250", "destroy_refund", "0.004", ref="parcel:42"))
        self.st = run(b.rows, P); self.r = report(self.st, P, 7)
    def test(self):
        d = disp(self.st, self.d[0])[0]; self.assertEqual((d.kind, d.proceeds, d.cost, d.realized), ("destroy", D(1), D(2), D(-1)))
        l = lots(self.st, self.d[1])[0]; self.assertEqual((l.basis, l.kind), (D(1), "refund"))
        self.assertEqual(D(self.r["all"]["realized_usdc"]), D(0))

class G7Bundle(unittest.TestCase):
    """§9 rule 6: parcel #42 (basis 50) sold with #10 (basis 2) and tile #5 x2 (basis 0) equipped, for 200 GHST @0.5 = 100.
    Parcel row: proceeds 100, cost 50 + 2 + 0 = 52, realized 48 (own cost 50). Item rows: bundle_item, proceeds = cost, 0 PnL.
    Realized total 48 + 1 (craft input) = 49. Nothing is left at parcel:42."""
    def setUp(self):
        b = _parcel_book()
        self.sale = b.tx(6, L("PARCEL#42", "-1", "nft_sale", nft=True, ref="bundle:parcel:42", trade_group="s"), L("GHST", "200", "nft_sale", "0.5", trade_group="s"))
        self.st = run(b.rows, P); self.r = report(self.st, P, 7)
    def test_parcel_row(self):
        d = [x for x in disp(self.st, self.sale[0]) if x.kind == "bundle"][0]
        self.assertEqual((d.proceeds, d.cost, d.own_cost, d.realized, d.bundle_ref), (D(100), D(52), D(50), D(48), "bundle:parcel:42"))
    def test_items(self):
        it = sorted((self.st.lot(x.lot).asset, x.qty, x.cost, x.realized) for x in disp(self.st, self.sale[0]) if x.kind == "bundle_item")
        self.assertEqual(it, [("INST#10", D(1), D(2), D(0)), ("TILE#5", D(2), D(0), D(0))])
        self.assertFalse([k for k in self.r["holdings_by_location"] if k.endswith("@parcel:42")])
    def test_totals(self):
        self.assertEqual(D(self.r["all"]["realized_usdc"]), D(49)); self.assertEqual(D(identity(self.st)["residual"]), 0)

class G8HoldingsByLocation(unittest.TestCase):
    """§9 rules 5, 8, pocket: equip (parcel:42), lend gotchi #3033 (lent:0xb0rrower), deposit FUD into the gotchi pocket (pocket:3033).
    All custody: no disposals, holdings split by location, basis unchanged."""
    def test(self):
        b = _parcel_book()
        b.tx(6, L("GOTCHI#3033", "1", "migration_in", nft=True, carry_basis=D(10), carry_source="polygon_fifo", carry_label="high", chain_origin=137))
        b.tx(7, L("GOTCHI#3033", "-1", "transfer_internal", nft=True, ref="lent:0xb0rrower"), L("GOTCHI#3033", "1", "transfer_internal", nft=True, location="lent:0xb0rrower", ref="lent:0xb0rrower"))
        b.tx(8, L("FUD", "-100", "transfer_internal", ref="pocket:3033"), L("FUD", "100", "transfer_internal", location="pocket:3033", ref="pocket:3033"))
        st = run(b.rows, P); h = report(st, P, 9)["holdings_by_location"]
        n0 = len(st.disposals)
        self.assertEqual({k: v for k, v in h.items() if "@wallet" not in k},
                         {"GOTCHI#3033@lent:0xb0rrower": "1", "FUD@pocket:3033": "100", "INST#10@parcel:42": "1", "TILE#5@parcel:42": "2"})
        self.assertEqual(h["FUD@wallet"], "400")
        self.assertEqual([d.kind for d in st.disposals], ["sale", "craft_input"]); self.assertEqual(n0, 2)
        g = [l for l in st.lots if l.asset == "GOTCHI#3033"][0]; self.assertEqual((g.basis, g.location), (D(10), "lent:0xb0rrower"))

def _eth_book():
    """bridge_in 100 USDC at par; swap 30 USDC -> 0.01 ETH @3000 (basis 30) with 0.001 ETH gas @3000 (value 3) in the same tx."""
    b = Book(); b.tx(1, L("USDC", "100", "bridge_in", "1", source="numeraire"))
    s = b.tx(2, L("USDC", "-30", "swap", "1"), L("ETH", "0.01", "swap", "3000"), L("ETH", "-0.001", "fee", "3000"))
    return b, s

class G9FeePolicy(unittest.TestCase):
    """Q-A hook (no default). expense: gas disposal proceeds 3, cost 3 (0.001 of the 0.01 lot), realized 0, expense 3; ETH left 0.009 basis 27.
    capitalize: the same disposal (cost 3, no expense) and +3 on the swap's ETH lot: basis 33, 0.009 left with basis 30."""
    def test_required(self):
        b, _ = _eth_book()
        with self.assertRaises(PolicyRequired) as c: run(b.rows, Policy())
        self.assertEqual(c.exception.question, "Q-A")
    def test_expense(self):
        b, s = _eth_book(); st = run(b.rows, Policy(fee="expense")); d = disp(st, s[2])[0]; l = lots(st, s[1])[0]
        self.assertEqual((d.kind, d.proceeds, d.cost, d.expense, l.basis, l.qty, l.remaining_basis()), ("fee", D(3), D(3), D(3), D(30), D("0.009"), D(27)))
    def test_capitalize(self):
        b, s = _eth_book()
        with self.assertRaises(PolicyRequired) as c: run(b.rows, Policy(fee="capitalize"))   # fee_split has no default either
        self.assertEqual(c.exception.question, "Q-A")
        st = run(b.rows, Policy(fee="capitalize", fee_split="basis_else_equal")); d = disp(st, s[2])[0]; l = lots(st, s[1])[0]
        self.assertEqual((d.kind, d.cost, d.expense, l.basis, l.remaining_basis()), ("fee_capitalized", D(3), None, D(33), D(30)))
        self.assertEqual((l.fee, l.split_method), (D(3), "basis"))
        self.assertEqual(D(identity(st)["residual"]), 0)
    def test_capitalize_without_trade_leg(self):
        b, _ = _eth_book(); b.tx(3, L("ETH", "-0.001", "fee", "3000"))
        with self.assertRaises(PolicyRequired) as c: run(b.rows, Policy(fee="capitalize"))
        self.assertEqual(c.exception.question, "Q-A")
        st = run(b.rows, Policy(fee="capitalize", fee_without_trade="expense", fee_split="basis_else_equal")); self.assertEqual(st.disposals[-1].expense, D(3))

class G10DepositWithdrawal(unittest.TestCase):
    """Q-B hooks (no default). deposit 1 ETH @2000; withdraw 0.5 ETH @2500.
    acquire_fmv + dispose_fmv: lot basis 2000; withdrawal proceeds 1250, cost 1000, realized 250.
    exit: the 0.5 leaves at basis 1000, proceeds NULL, realized 0, MV 1250 for display (exit_basis 1000). pending: deposit lot pending,
    withdrawal = pending disposal."""
    def book(self):
        b = Book(); dep = b.tx(1, L("ETH", "1", "deposit", "2000")); w = b.tx(2, L("ETH", "-0.5", "withdrawal", "2500")); return b, dep, w
    def test_required(self):
        b, _, _ = self.book()
        with self.assertRaises(PolicyRequired) as c: run(b.rows, Policy())
        self.assertEqual(c.exception.question, "Q-B")
    def test_fmv(self):
        b, dep, w = self.book(); pol = Policy(deposit="acquire_fmv", withdrawal="dispose_fmv", mark=P.mark)
        st = run(b.rows, pol); d = disp(st, w[0])[0]
        self.assertEqual((lots(st, dep[0])[0].basis, d.proceeds, d.cost, d.realized), (D(2000), D(1250), D(1000), D(250)))
        self.assertEqual(D(report(st, pol, 3)["all"]["unrealized_usdc"]), D(500))   # 0.5 x 3000 - 1000
    def test_exit(self):
        b, _, w = self.book(); pol = Policy(deposit="acquire_fmv", withdrawal="exit", mark=P.mark)
        st = run(b.rows, pol); d = disp(st, w[0])[0]; r = report(st, pol, 3)
        self.assertEqual((d.kind, d.proceeds, d.cost, d.realized, d.display_mv), ("exit", None, D(1000), D(0), D(1250)))
        self.assertEqual((D(r["all"]["realized_usdc"]), D(r["exit_basis_usdc"]), D(r["exit_display_mv_usdc"]), r["all"]["unpriced_disposals"], r["exits"]),
                         (D(0), D(1000), D(1250), 0, 1))
    def test_pending_deposit(self):
        b, dep, w = self.book(); st = run(b.rows, Policy(deposit="pending", withdrawal="dispose_fmv")); r = report(st, P, 3)
        self.assertEqual((lots(st, dep[0])[0].status, lots(st, dep[0])[0].source, disp(st, w[0])[0].lot_status), ("pending", None, "pending"))
        self.assertEqual((r["pending_lots_open"], r["pending_disposals"], r["pending_reasons"]), (1, 1, {"deposit": 1}))
        self.assertEqual((D(r["all"]["realized_usdc"]), D(r["all"]["unrealized_usdc"])), (D(0), D(0)))   # pending excluded on mark and basis

class G11InternalTransfer(unittest.TestCase):
    """Q-E hook (no default): 10 GHST @1 bought in wallet w1, sent to own wallet w2 (same group) when GHST is @2.
    carry: no disposal, the lot moves to w2 with basis 10. dispose_acquire: disposal proceeds 20, cost 10, +10; new lot basis 20."""
    def book(self):
        b = Book(); b.tx(1, L("USDC", "10", "bridge_in", "1", source="numeraire"))
        b.tx(2, L("USDC", "-10", "swap", "1"), L("GHST", "10", "swap", "1"))
        t = b.tx(3, L("GHST", "-10", "transfer_internal", "2", wallet="w1"), L("GHST", "10", "transfer_internal", "2", wallet="w2")); return b, t
    def test_required(self):
        b, _ = self.book()
        with self.assertRaises(PolicyRequired) as c: run(b.rows, Policy())
        self.assertEqual(c.exception.question, "Q-E")
    def test_carry(self):
        b, t = self.book(); st = run(b.rows, Policy(internal_transfer="carry"))
        g = [l for l in st.lots if l.asset == "GHST"]
        self.assertEqual([(l.wallet, l.basis, l.qty) for l in g], [("w2", D(10), D(10))]); self.assertEqual(disp(st, t[0]), [])
    def test_dispose_acquire(self):
        b, t = self.book(); st = run(b.rows, Policy(internal_transfer="dispose_acquire")); d = disp(st, t[0])[0]
        self.assertEqual((d.kind, d.proceeds, d.cost, d.realized, lots(st, t[1])[0].basis), ("internal", D(20), D(10), D(10), D(20)))

class G12NeverZeroAndExclusions(unittest.TestCase):
    """spam/untracked rows never enter FIFO (counted); a 0 price is rejected; an unpriced sale is counted, never valued at 0;
    low-confidence prices are in 'all' and out of 'excl_low' (§9 P3 thin pools)."""
    def test_excluded(self):
        b = Book(); b.tx(1, L("SPAMCOIN", "1000", "spam")); b.tx(2, L("LINK", "5", "untracked")); b.tx(3, L("GHST", "1", "income", "1", excluded=True))
        st = run(b.rows, P); self.assertEqual((st.lots, report(st, P, 4)["excluded_rows"]), ([], {"income": 1, "spam": 1, "untracked": 1}))
    def test_zero_price_rejected(self):
        b = Book(); b.tx(1, L("GHST", "1", "income", "0"))
        with self.assertRaises(FifoError): run(b.rows, P)
    def test_unpriced_sale_counted(self):
        b = Book(); b.tx(1, L("GHST", "10", "income", "1")); s = b.tx(2, L("GHST", "-10", "swap"), L("LINKISH", "1", "swap"))
        st = run(b.rows, P); d = disp(st, s[0])[0]; r = report(st, P, 3)
        self.assertEqual((d.proceeds, d.realized, r["all"]["unpriced_disposals"]), (None, None, 1))
        l = lots(st, s[1])[0]; self.assertEqual((l.status, l.pending_reason, l.source), ("pending", "no_price", None))
    def test_low_confidence_variants(self):
        b = Book(); b.tx(1, L("FUD", "1000", "income", "0.002", label="low")); b.tx(2, L("FUD", "-500", "swap", "0.004", label="low"), L("USDC", "2", "swap", "1"))
        st = run(b.rows, P); r = report(st, P, 3)
        self.assertEqual((D(r["all"]["realized_usdc"]), D(r["excl_low"]["realized_usdc"]), r["excl_low"]["low_excluded"]), (D(1), D(0), 2))
        self.assertEqual(D(r["all"]["unrealized_usdc"]), D(1))   # FUD 500 x 0.004 - 1
    def test_oversell_is_an_error(self):
        b = Book(); b.tx(1, L("GHST", "1", "income", "1")); b.tx(2, L("GHST", "-2", "swap", "1"), L("USDC", "2", "swap", "1"))
        with self.assertRaises(PolicyRequired) as c: run(b.rows, P)          # Q-H: no default for a shortfall
        self.assertEqual(c.exception.question, "Q-H")
    def test_mark_hook_required(self):
        b = Book(); b.tx(1, L("GHST", "1", "income", "1"))
        with self.assertRaises(PolicyRequired) as c: report(run(b.rows, P), Policy(nft_mark="exclude"), 2)
        self.assertEqual(c.exception.question, "Q-F")
    def test_policy_values_validated(self):
        with self.assertRaises(ValueError): Policy(fee="maybe")
