"""P4.1 rule 7 (architect ruling (a), 2026-10-28 20:21 PT; DESIGN §8): gotchi pocket inflows. SYNTHETIC fixtures only (made-up gotchi
ids, blocks, quantities and prices; not chain data), except that the relayer, GHST and selector are the configured POCKETS / allowlist
entries so the rule runs through the real config."""
import unittest
from decimal import Decimal as D
from cryptopnl import classify, fifo, reconcile
from cryptopnl.classify import pocket_rule, pocket_legs, Review
from cryptopnl.config import POCKETS, gated
from cryptopnl.fifo import run
from tests.fifo_fixtures import Book, L
from tests.test_fifo_rulings import RP, MK, NFTX, lot

C = POCKETS[8453]; REL = C["rf_relayer"]; RF_SEL = next(iter(C["rf_selectors"]))
GHST = "0xcd2f22236dd9dfe2356d7c543161d4d260fd9bcb"; assert GHST in gated(8453)
W = "0x" + "aa" * 20; W2 = "0x" + "a2" * 20; OTHER = "0x" + "bb" * 20; JUNK = "0x" + "dd" * 20; JUNK_NFT = "0x" + "de" * 20
POCKET = "0x" + "e1" * 20; GID = 7001; TH = "0x" + "11" * 32
def leg(qty=10**18, cp=REL, contract=GHST, li=5, std="erc20", tid=None, sel=RF_SEL):
    return dict(li=li, std=std, contract=contract, token_id=tid, qty=qty, cp=cp, pocket=GID, selector=sel)
def esc(owned=True, lending=None):
    e = classify.Escrow({POCKET: GID}); e.type_cost = {}; e.th = TH; e.flags = []
    if owned: e.gotchis[GID] = 1
    e.lending = lending or {}; return e

class PocketLegs(unittest.TestCase):
    def test_in_out_and_pocket_to_pocket(self):
        p = {"std": "erc20", "contract": GHST, "from": REL, "to": POCKET, "value": "5", "selector": RF_SEL}
        self.assertEqual([(l["qty"], l["cp"], l["pocket"]) for l in pocket_legs(3, p, {POCKET: GID})], [(5, REL, GID)])
        p2 = dict(p, **{"from": POCKET, "to": "0x" + "e2" * 20})
        both = pocket_legs(3, p2, {POCKET: GID, "0x" + "e2" * 20: 7002})
        self.assertEqual(sorted((l["pocket"], l["qty"]) for l in both), [(7001, -5), (7002, 5)])

class CustodyIncome(unittest.TestCase):
    def test_custody_income_at_deposit(self):   # owned at the deposit block, not rented: income at pocket:<id>, RF tag, sender:tx
        e = esc(); out = pocket_rule(8453, W, None, [leg()], e, set(), 100)
        self.assertEqual([(o["cat"], o["loc"], o["qty"], o["income_subtype"], o["source_ref"]) for o in out],
                         [("income", f"pocket:{GID}", 10**18, "rarity_farming_payout", f"{REL}:{TH}")])
        self.assertEqual(e.flags, [])
    def test_other_sender_is_pocket_deposit(self):
        out = pocket_rule(8453, W, None, [leg(cp=OTHER, sel="0x12345678")], esc(), set(), 100)
        self.assertEqual([(o["cat"], o["income_subtype"], o["source_ref"]) for o in out], [("income", "pocket_deposit", f"{OTHER}:{TH}")])
    def test_relayer_without_batch_deposit_selector_is_not_rf(self):
        out = pocket_rule(8453, W, None, [leg(sel="0x00000000")], esc(), set(), 100)
        self.assertEqual(out[0]["income_subtype"], "pocket_deposit")
    def test_plan_full_third_party_tx(self):   # no wallet leg, no tx row: the pocket legs alone decide the category
        cat, out, _ = classify.plan_full(8453, W, None, [leg()], [], set(), 100, esc())
        self.assertEqual((cat, [o["cat"] for o in out]), ("income", ["income"]))
    def test_third_party_move_out_of_owned_pocket_is_review(self):
        with self.assertRaises(Review): pocket_rule(8453, W, None, [leg(qty=-5, cp=OTHER)], esc(), set(), 100)

class OwnerMismatch(unittest.TestCase):
    def test_not_owned_at_deposit_block(self):   # pocket owner not in the wallet group at the deposit block: no entry, flagged
        e = esc(owned=False); out = pocket_rule(8453, W, None, [leg(), leg(cp=OTHER, li=6, qty=-3)], e, set(), 100)
        self.assertEqual(out, []); self.assertEqual([(f["why"], f["li"]) for f in e.flags], [("not_owned", 5), ("not_owned", 6)])
        cat, out, _ = classify.plan_full(8453, W, None, [leg()], [], set(), 100, esc(owned=False))
        self.assertEqual((cat, out), ("pocket_owner_mismatch", []))
    def test_sold_gotchi_is_not_owned(self):   # the historical owner counts, not today's: owned then sold (count back to 0)
        e = esc(); e.gotchis[GID] = 0
        self.assertEqual(pocket_rule(8453, W, None, [leg()], e, set(), 100), []); self.assertEqual(len(e.flags), 1)

class RentalAtDeposit(unittest.TestCase):
    LEND = {GID: [((100, 7), (200, 3))]}   # executed at block 100 log 7, ended at block 200 log 3
    def test_rented_at_deposit_block(self):
        e = esc(lending=self.LEND); self.assertEqual(pocket_rule(8453, W, None, [leg()], e, set(), 150), [])
        self.assertEqual([f["why"] for f in e.flags], ["rented"])
    def test_interval_edges(self):   # [executed, ended): same-block ordering by log index
        for bn, li, rented in ((100, 6, False), (100, 8, True), (200, 2, True), (200, 4, False), (300, 0, False)):
            e = esc(lending=self.LEND); out = pocket_rule(8453, W, None, [leg(li=li)], e, set(), bn)
            self.assertEqual((bool(e.flags), len(out)), (rented, 0 if rented else 1), (bn, li))
    def test_open_rental(self):   # executed, never ended
        e = esc(lending={GID: [((100, 0), None)]}); pocket_rule(8453, W, None, [leg()], e, set(), 10**9)
        self.assertEqual([f["why"] for f in e.flags], ["rented"])

class WalletGroupSender(unittest.TestCase):
    def test_group_sender_is_internal_move(self):
        out = pocket_rule(8453, W, None, [leg(cp=W2, sel="0xb0facab3")], esc(), {W2}, 100)
        self.assertEqual([(o["cat"], o["loc"], o["ref"], o.get("income_subtype")) for o in out],
                         [("transfer_internal", f"pocket:{GID}", f"pocket:{GID}", None)])

class NotAllowlisted(unittest.TestCase):
    def test_unsolicited_junk_is_spam(self):   # DESIGN §8 unsolicited non-allowlisted token rule: no lot, never in PnL
        out = pocket_rule(8453, W, None, [leg(cp=OTHER, contract=JUNK), leg(cp=OTHER, contract=JUNK_NFT, std="erc721", tid="1", qty=1, li=6)],
                          esc(), set(), 100)
        self.assertEqual([(o["cat"], o["spam"]) for o in out], [("spam", True), ("spam", True)])

class EngineSide(unittest.TestCase):
    """SYNTHETIC: 25 GHST arrive in pocket:7001 at block 10 (income @4), leave for the wallet at block 20 (custody), sold at block 30 @5."""
    def book(self, price="4"):
        b = Book(); i = b.tx(10, L("GHST", "25", "income", price, location="pocket:7001", income_subtype="rarity_farming_payout",
                                   source_ref=f"{REL}:{TH}"))[0]
        b.tx(20, L("GHST", "-25", "transfer_internal", "4.5", location="pocket:7001", ref="pocket:7001"),
                 L("GHST", "25", "transfer_internal", "4.5", ref="pocket:7001"))
        s = b.tx(30, L("GHST", "-25", "swap", "5"), L("USDC", "125", "swap", "1"))[0]
        return b, i, s
    def test_withdrawal_carries_basis_and_lot_date(self):
        b, i, s = self.book(); st = run(b.rows, RP()); l = lot(st, i)
        self.assertEqual((l.basis, l.open_block, l.status, l.location), (D(100), 10, "resolved", "wallet"))   # moved, same lot
        self.assertEqual([d for d in st.disposals if d.entry == b.rows[1].id], [])   # custody: nothing realized
        ds = [d for d in st.disposals if d.entry == s.id]
        self.assertEqual([(d.lot, d.realized) for d in ds], [(l.id, D(25))])   # 125 - 100: basis and acquisition from the pocket deposit
        self.assertEqual(D(fifo.report(st, RP(), 40)["income_usdc"]), D(100))
        self.assertEqual(reconcile.ledger_side(b.rows, MK, NFTX, 40)["unexplained_gap"], {})   # the pocket was funded: no gap
        before = reconcile.ledger_side([r for r in b.rows if r.id != i.id], MK, NFTX, 40)["unexplained_gap"]   # pre-rule-7 ledger
        self.assertEqual((before["GHST"]["qty"], before["GHST"]["by_category"]), (D(25), {"transfer_internal": 1}))
    def test_unpriced_erc20_is_pending_never_zero(self):
        b, i, _ = self.book(price=None); st = run(b.rows, RP()); l = lot(st, i)
        self.assertEqual((l.status, l.basis), ("pending", None))
        from cryptopnl import p4
        lines = p4.income_lines(st, b.rows, fifo.report(st, RP(), 40)["income_usdc"])
        self.assertEqual([(x["income_subtype"], x["source_ref"], x["entries"], x["unpriced_entries"], x["usdc"], x["txs"]) for x in lines],
                         [("rarity_farming_payout", REL, 1, 1, D(0), 1)])
    def test_unpriced_nft_excluded_from_unrealized_and_counted(self):   # Q8
        b = Book(); n = b.tx(10, L("BADGE#1", "1", "income", None, location="pocket:7001", nft=True))[0]
        st = run(b.rows, RP(nft_mark="exclude")); rep = fifo.report(st, RP(nft_mark="exclude"), 40)
        self.assertEqual(lot(st, n).basis, None)
        a = rep["all"]; self.assertEqual((D(a["unrealized_usdc"]), D(a["market_value_usdc"])), (D(0), D(0)))
        self.assertEqual(a["unmarked_nft_lots"] + a["by_asset"]["BADGE#1"]["pending_lots"], 1)
    def test_priced_nft_income(self):
        b = Book(); n = b.tx(10, L("BADGE#2", "1", "income", "7", location="pocket:7001", nft=True))[0]
        st = run(b.rows, RP(nft_mark="at_basis")); self.assertEqual((lot(st, n).basis, lot(st, n).status), (D(7), "resolved"))
        self.assertEqual(D(fifo.report(st, RP(nft_mark="at_basis"), 40)["income_usdc"]), D(7))

if __name__ == "__main__": unittest.main()
