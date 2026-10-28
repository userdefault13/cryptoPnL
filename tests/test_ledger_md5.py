"""P3 follow-up (c): ledger md5 evidence file. Synthetic rows on a synthetic chain id (999001) in the unit DB; no network.
Run: CRYPTOPNL_DSN=postgresql:///cryptopnl_unit_p4 ENVIO_API_TOKEN=x .venv/bin/python -m unittest -v tests.test_ledger_md5"""
import hashlib, os, tempfile, unittest
from decimal import Decimal
os.environ.setdefault("ENVIO_API_TOKEN", "test")
from cryptopnl import db, evidence

C = 999001   # SYNTHETIC chain id, not a real chain
ROWS = [  # (tx_hash, log_index, qty, category, location, escrow_ref, block) -- SYNTHETIC
    (bytes.fromhex("aa" * 32), 2, Decimal("1.5"), "swap", "wallet", None, 100),
    (bytes.fromhex("aa" * 32), 1, Decimal("-3"), "swap", "wallet", None, 100),
    (bytes.fromhex("0b" * 32), 7, Decimal("1"), "transfer_internal", "escrow:0xdiamond", "listing:9", 105)]

class LedgerMd5(unittest.TestCase):
    def setUp(self):
        self.c = db.connect(); db.migrate(self.c); self.tearDown()
        self.a = self.c.execute("INSERT INTO asset(chain_id, standard, symbol, decimals) VALUES (%s,'native','SYNTH',18) RETURNING id", (C,)).fetchone()[0]
        for h, li, q, cat, loc, ref, b in ROWS:
            self.c.execute("""INSERT INTO ledger_entry(asset_id, chain_id, tx_hash, log_index, block_number, ts, qty, category, location, escrow_ref)
                VALUES (%s,%s,%s,%s,%s,to_timestamp(%s),%s,%s,%s,%s)""", (self.a, C, h, li, b, 1_700_000_000 + b, q, cat, loc, ref))
        self.c.commit()
    def tearDown(self):
        self.c.rollback()
        for t in ("review_queue", "ledger_entry", "asset"): self.c.execute(f"DELETE FROM {t} WHERE chain_id=%s", (C,))
        self.c.commit()
    def expected(self):   # independent recomputation of the narrow md5 (concat_ws skips NULLs)
        rows = sorted(ROWS, key=lambda r: (r[0], r[1], self.a, r[4], r[2]))
        parts = ["|".join(str(x) for x in (h.hex(), li, self.a, q, cat, loc, ref) if x is not None) for h, li, q, cat, loc, ref, _ in rows]
        return hashlib.md5(",".join(parts).encode()).hexdigest()
    def test_narrow_md5_matches_independent_computation(self):
        r = evidence.ledger_md5(self.c, C)
        self.assertEqual((r["ledger_rows"], r["ledger_min_block"], r["ledger_max_block"]), (3, 100, 105))
        self.assertEqual(r["ledger_md5_narrow"], self.expected()); self.assertRegex(r["ledger_md5_report"], "^[0-9a-f]{32}$")
    def test_file_is_deterministic_and_complete(self):
        d = tempfile.mkdtemp(); p = os.path.join(d, "docs", "evidence", "p4_ledger_md5_999001.txt")
        evidence.write_ledger_md5(self.c, C, p); first = open(p).read()
        evidence.write_ledger_md5(self.c, C, p); self.assertEqual(open(p).read(), first)
        kv = dict(l.split("=", 1) for l in first.splitlines() if not l.startswith("#"))
        self.assertEqual((kv["chain_id"], kv["ledger_rows"], kv["ledger_md5_narrow"], kv["review_rows"], kv["review_md5"]),
                         (str(C), "3", self.expected(), "0", "none"))
        for bad in ("postgres", "password", "host=", os.environ.get("CRYPTOPNL_DSN", "\0")): self.assertNotIn(bad, first)
    def test_md5_changes_when_a_row_changes(self):
        before = evidence.ledger_md5(self.c, C)["ledger_md5_narrow"]
        self.c.execute("UPDATE ledger_entry SET qty=qty+1 WHERE chain_id=%s AND log_index=7", (C,))
        self.assertNotEqual(evidence.ledger_md5(self.c, C)["ledger_md5_narrow"], before)
    def test_empty_chain(self):
        r = evidence.ledger_md5(self.c, C + 1)
        self.assertEqual((r["ledger_rows"], r["ledger_md5_narrow"]), (0, None)); self.assertIn("ledger_md5_narrow=none", evidence.render(r, "x"))
