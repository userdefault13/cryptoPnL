"""P4 rulings 3, DB adapter parts without a DB. SYNTHETIC rows only."""
import unittest
from decimal import Decimal as D
from cryptopnl import p4
from tests.fifo_fixtures import Book, L

class AsOfIsMin(unittest.TestCase):
    """GHST priced up to block 9, FUD only up to block 4, an NFT priced at 12 (NFTs never gate as_of): as_of = 4, set by FUD."""
    def test_min(self):
        b = Book(); b.tx(1, L("GHST", "1", "income", "1")); b.tx(4, L("FUD", "1", "income", "0.1")); b.tx(9, L("GHST", "1", "income", "2"))
        b.tx(12, L("W#1", "1", "income", "5", nft=True)); b.tx(13, L("KEK", "1", "income"))   # KEK never priced: no latest, cannot gate
        m = p4.Marks(b.rows)
        self.assertEqual(m.as_of_block(), 4)
        self.assertEqual(m.as_of_detail(), {"as_of_block": 4, "set_by_assets": ["FUD"], "latest_priced_block_per_asset": {"FUD": 4, "GHST": 9}})
        self.assertEqual(m("GHST", 4).price, D(1))   # mark = latest stored price at or before as_of

class TxIndexNull(unittest.TestCase):
    def test_single_tx_block_ok(self):
        self.assertEqual(p4.check_tx_index([(1, None, "a"), (1, None, "a"), (2, 0, "b"), (2, 1, "c")]), 2)
    def test_multi_tx_block_with_null_raises(self):
        with self.assertRaises(p4.TxIndexError): p4.check_tx_index([(1, None, "a"), (1, 3, "b")])
    def test_sql_has_no_coalesce_on_tx_index(self):
        self.assertNotIn("coalesce(l.tx_index", p4.ROWS_SQL); self.assertIn("ORDER BY l.block_number, l.log_index, l.id", p4.ROWS_SQL)

if __name__ == "__main__": unittest.main()
