"""Independent check of fifo.Entry.key() and the engine's sort, against a HAND-ORDERED fixture (P4 rulings 4 / P4.1 C).
SYNTHETIC rows (made-up blocks, hashes, ids). The expected order below was written by hand from the rule
(block, tx_index, tx, log_index, id) -- it is not computed with Entry.key -- and the rows are fed to the engine shuffled."""
import random, unittest
from decimal import Decimal as D
from cryptopnl import fifo
from cryptopnl.fifo import Entry

def E(name, block, txi, tx, li, i): return name, Entry(id=i, block=block, tx=tx, log_index=li, asset="ETH", qty=D(1), category="x", tx_index=txi)

HAND_ORDER = [   # read top to bottom = ledger order
    E("b10 first tx, gas leg",            10, 0, "0xffff", -1, 7),
    E("b10 first tx, log 3",              10, 0, "0xffff", 3, 2),
    E("b10 2nd tx (index 1 < hash order)", 10, 1, "0x0001", 0, 1),
    E("b11 internal frame n=0",           11, 54, "0xcfb5", -100000, 9),  # internal legs: log_index n - 100000 (DFS order), before gas
    E("b11 internal frame n=3",           11, 54, "0xcfb5", -99997, 8),   #   and the tx's logs
    E("b11 gas",                          11, 54, "0xcfb5", -1, 10),
    E("b11 log 0, id 4",                  11, 54, "0xcfb5", 0, 4),
    E("b11 log 0, id 5 (same tx+log)",    11, 54, "0xcfb5", 0, 5),
    E("b11 tx index 81 (hash sorts 1st)", 11, 81, "0x9d22", 2, 3),
    E("b12",                              12, 0, "0x0000", 0, 6),
]

class EntryKeyHandOrdered(unittest.TestCase):
    def test_key_shape(self):
        e = HAND_ORDER[0][1]; self.assertEqual(e.key(), (10, 0, "0xffff", -1, 7))
    def test_sort_matches_hand_order(self):
        want = [n for n, _ in HAND_ORDER]
        for seed in range(25):
            rows = [e for _, e in HAND_ORDER]; random.Random(seed).shuffle(rows)
            got = [next(n for n, x in HAND_ORDER if x is e) for e in sorted(rows, key=Entry.key)]
            self.assertEqual(got, want, f"seed {seed}")
    def test_tx_index_beats_hash(self):
        a = dict(HAND_ORDER)["b11 log 0, id 4"]; b = dict(HAND_ORDER)["b11 tx index 81 (hash sorts 1st)"]
        self.assertLess(b.tx, a.tx); self.assertLess(a.key(), b.key())
    def test_engine_groups_txs_in_hand_order(self):
        seen = []
        orig = fifo._tx
        try:
            fifo._tx = lambda st, p, legs: seen.append([l.id for l in legs])
            rows = [e for _, e in HAND_ORDER]; random.Random(3).shuffle(rows)
            fifo.run(rows, None)
        finally: fifo._tx = orig
        self.assertEqual(seen, [[7, 2], [1], [9, 8, 10, 4, 5], [3], [6]])

if __name__ == "__main__": unittest.main()
