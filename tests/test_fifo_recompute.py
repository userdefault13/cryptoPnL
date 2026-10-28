"""P4 'deterministic recompute from block X': for every block X of each SYNTHETIC fixture book, replaying the entries before X and then
continuing from that state with the rest gives the same lots/disposals md5 as one full rebuild (and the same report)."""
import unittest
from cryptopnl.fifo import Policy, FifoError, run, report, md5
from tests import test_fifo_golden as G
from tests.fifo_fixtures import L

POL = Policy(mark=G.P.mark, nft_mark="exclude", fee="expense", queue_split="equal")
def books():
    g1 = G.G1BasicFifo(); g1.setUp(); g4 = G.G4Craft(); g4.setUp()
    b5 = G._parcel_book(); R = "upgrade:realm:42:queue:0"
    b5.tx(6, L("FUD", "-100", "upgrade", "0.004", ref=R))
    b5.tx(7, L("INST#10", "-1", "upgrade", nft=True, location="parcel:42", ref=R), L("INST#20", "1", "upgrade", nft=True, location="parcel:42", ref=R))
    b5.tx(8, L("PARCEL#42", "-1", "nft_sale", nft=True, ref="bundle:parcel:42", trade_group="s"), L("GHST", "200", "nft_sale", "0.5", trade_group="s"))
    eth, _ = G._eth_book()
    return {"g1": g1.b.rows, "g4_craft": g4.b.rows, "upgrade_then_bundle": b5.rows, "eth_fee": eth.rows}

class Recompute(unittest.TestCase):
    def test_every_block_boundary(self):
        n = 0
        for name, rows in books().items():
            full = run(rows, POL); want = md5(full); rep = report(full, POL, 99)
            for X in sorted({e.block for e in rows}) + [max(e.block for e in rows) + 1]:
                head = [e for e in rows if e.block < X]; tail = [e for e in rows if e.block >= X]
                inc = run(tail, POL, run(head, POL))
                self.assertEqual(md5(inc), want, f"{name} X={X}"); self.assertEqual(report(inc, POL, 99), rep, f"{name} X={X}"); n += 1
        self.assertGreaterEqual(n, 20)
    def test_state_not_mutated(self):
        rows = books()["g1"]; head = run([e for e in rows if e.block < 3], POL); h = md5(head)
        run([e for e in rows if e.block >= 3], POL, head); self.assertEqual(md5(head), h)
    def test_out_of_order_continuation_rejected(self):
        rows = books()["g1"]; st = run(rows, POL)
        with self.assertRaises(FifoError): run([rows[0]], POL, st)
