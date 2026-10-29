"""P3 follow-up (c) + P4.1 md5 ruling (v1 unchanged, v1 over the pre-P4.1 rows, v2 = v1 + income_subtype/source_ref/trace_address): ledger md5 evidence file. Synthetic rows on a synthetic chain id (999001) in the unit DB; no network.
Run: CRYPTOPNL_DSN=postgresql:///cryptopnl_unit_p4 ENVIO_API_TOKEN=x .venv/bin/python -m unittest -v tests.test_ledger_md5"""
import hashlib, os, tempfile, unittest
from decimal import Decimal
os.environ.setdefault("ENVIO_API_TOKEN", "test")
from cryptopnl import db, evidence

C = 999001   # SYNTHETIC chain id, not a real chain
ROWS = [  # (tx_hash, log_index, qty, category, location, escrow_ref, block, income_subtype, source_ref, trace_address) -- SYNTHETIC
    (bytes.fromhex("aa" * 32), 2, Decimal("1.5"), "swap", "wallet", None, 100, None, None, None),
    (bytes.fromhex("aa" * 32), 1, Decimal("-3"), "swap", "wallet", None, 100, None, None, None),
    (bytes.fromhex("0b" * 32), 7, Decimal("1"), "transfer_internal", "escrow:0xdiamond", "listing:9", 105, None, None, None),
    # a P4.1 internal-ETH leg (trace_address set), tagged dao_distribution
    (bytes.fromhex("0c" * 32), -99998, Decimal("2"), "income", "wallet", "distribution:x", 106, "dao_distribution", "0x" + "f5" * 20, "0.1"),
    # a pre-existing row of the same tx (a tx P4.1 touched): in the pre-P4.1 set, not in the untouched-tx set
    (bytes.fromhex("0c" * 32), 4, Decimal("-1"), "fee", "wallet", None, 106, None, None, None)]
OLD = ROWS[:3] + ROWS[4:]          # trace_address IS NULL
UNTOUCHED = ROWS[:3]               # txs with no internal-ETH leg

class LedgerMd5(unittest.TestCase):
    def setUp(self):
        self.c = db.connect(); db.migrate(self.c); self.tearDown()
        self.a = self.c.execute("INSERT INTO asset(chain_id, standard, symbol, decimals) VALUES (%s,'native','SYNTH',18) RETURNING id", (C,)).fetchone()[0]
        for h, li, q, cat, loc, ref, b, isub, sref, ta in ROWS:
            self.c.execute("""INSERT INTO ledger_entry(asset_id, chain_id, tx_hash, log_index, block_number, ts, qty, category, location, escrow_ref,
                income_subtype, source_ref, trace_address) VALUES (%s,%s,%s,%s,%s,to_timestamp(%s),%s,%s,%s,%s,%s,%s,%s)""",
                (self.a, C, h, li, b, 1_700_000_000 + b, q, cat, loc, ref, isub, sref, ta))
        self.c.commit()
    def tearDown(self):
        self.c.rollback()
        for t in ("review_queue", "ledger_entry", "asset"): self.c.execute(f"DELETE FROM {t} WHERE chain_id=%s", (C,))
        self.c.commit()
    def expected(self, rows=ROWS):   # independent recomputation of v1 (concat_ws skips NULLs)
        rows = sorted(rows, key=lambda r: (r[0], r[1], self.a, r[4], r[2]))
        parts = ["|".join(str(x) for x in (h.hex(), li, self.a, q, cat, loc, ref) if x is not None) for h, li, q, cat, loc, ref, *_ in rows]
        return hashlib.md5(",".join(parts).encode()).hexdigest()
    def expected_v2(self):   # v1 fields (NULL skipped) + the three new fields, NULL -> '' (kept in place)
        rows = sorted(ROWS, key=lambda r: (r[0], r[1], self.a, r[4], r[2], r[9] or ""))
        parts = ["|".join([str(x) for x in (h.hex(), li, self.a, q, cat, loc, ref) if x is not None] + [isub or "", sref or "", ta or ""])
                 for h, li, q, cat, loc, ref, _, isub, sref, ta in rows]
        return hashlib.md5(",".join(parts).encode()).hexdigest()
    def test_narrow_md5_matches_independent_computation(self):
        r = evidence.ledger_md5(self.c, C)
        self.assertEqual((r["ledger_rows"], r["ledger_min_block"], r["ledger_max_block"]), (5, 100, 106))
        self.assertEqual(r["ledger_md5_v1"], self.expected()); self.assertRegex(r["ledger_md5_report"], "^[0-9a-f]{32}$")
        self.assertEqual((r["ledger_rows_pre_p4_1"], r["ledger_md5_v1_pre_p4_1"]), (4, self.expected(OLD)))
        self.assertEqual((r["internal_eth_txs"], r["untouched_txs_from"], r["ledger_rows_untouched_txs"], r["ledger_md5_v1_untouched_txs"]),
                         (1, "self", 3, self.expected(UNTOUCHED)))
    def test_untouched_with_an_external_tx_list(self):   # e.g. a pre-P4.1 ledger hashed over the txs a P4.1 ledger did not touch
        r = evidence.ledger_md5(self.c, C, untouched_txs=[], untouched_from="other")
        self.assertEqual((r["ledger_rows_untouched_txs"], r["ledger_md5_v1_untouched_txs"], r["untouched_txs_from"]), (5, r["ledger_md5_v1"], "other"))
        r = evidence.ledger_md5(self.c, C, untouched_txs=[bytes.fromhex("aa" * 32)])
        self.assertEqual(r["ledger_md5_v1_untouched_txs"], self.expected(ROWS[2:]))
        self.assertEqual(r["ledger_md5_v2"], self.expected_v2())
    def test_v1_ignores_new_fields_v2_does_not(self):
        b = evidence.ledger_md5(self.c, C)
        self.c.execute("UPDATE ledger_entry SET source_ref=%s WHERE chain_id=%s AND log_index=-99998", ("0x" + "e5" * 20, C))
        a = evidence.ledger_md5(self.c, C)
        self.assertEqual((a["ledger_md5_v1"], a["ledger_md5_v1_pre_p4_1"]), (b["ledger_md5_v1"], b["ledger_md5_v1_pre_p4_1"]))
        self.assertNotEqual(a["ledger_md5_v2"], b["ledger_md5_v2"])
        self.c.execute("UPDATE ledger_entry SET trace_address='0.2' WHERE chain_id=%s AND log_index=-99998", (C,))
        self.assertNotEqual(evidence.ledger_md5(self.c, C)["ledger_md5_v2"], a["ledger_md5_v2"])
    def test_v1_unchanged_definition(self):   # the pre-P4.1 SQL text, byte for byte (the old NARROW_SQL)
        self.assertEqual(evidence.V1_SQL, """SELECT md5(string_agg(concat_ws('|',encode(tx_hash,'hex'),log_index,asset_id,qty,category,location,escrow_ref),','
    ORDER BY tx_hash,log_index,asset_id,location,qty)), count(*), min(block_number), max(block_number) FROM ledger_entry WHERE chain_id=%s""")
    def test_file_is_deterministic_and_complete(self):
        d = tempfile.mkdtemp(); p = os.path.join(d, "docs", "evidence", "p4_ledger_md5_999001.txt")
        evidence.write_ledger_md5(self.c, C, p); first = open(p).read()
        evidence.write_ledger_md5(self.c, C, p); self.assertEqual(open(p).read(), first)
        kv = dict(l.split("=", 1) for l in first.splitlines() if not l.startswith("#"))
        self.assertEqual((kv["chain_id"], kv["ledger_rows"], kv["ledger_md5_v1"], kv["ledger_rows_pre_p4_1"], kv["ledger_md5_v1_pre_p4_1"],
                          kv["ledger_md5_v2"], kv["review_rows"], kv["review_md5"]),
                         (str(C), "5", self.expected(), "4", self.expected(OLD), self.expected_v2(), "0", "none"))
        self.assertEqual((kv["ledger_rows_untouched_txs"], kv["ledger_md5_v1_untouched_txs"]), ("3", self.expected(UNTOUCHED)))
        for bad in ("postgres", "password", "host=", os.environ.get("CRYPTOPNL_DSN", "\0")): self.assertNotIn(bad, first)
    def test_md5_changes_when_a_row_changes(self):
        before = evidence.ledger_md5(self.c, C)
        self.c.execute("UPDATE ledger_entry SET qty=qty+1 WHERE chain_id=%s AND log_index=7", (C,))
        after = evidence.ledger_md5(self.c, C)
        for k in ("ledger_md5_v1", "ledger_md5_v1_pre_p4_1", "ledger_md5_v1_untouched_txs", "ledger_md5_v2"): self.assertNotEqual(after[k], before[k], k)
    def test_empty_chain(self):
        r = evidence.ledger_md5(self.c, C + 1)
        self.assertEqual((r["ledger_rows"], r["ledger_md5_v1"], r["ledger_md5_v2"]), (0, None, None)); self.assertIn("ledger_md5_v2=none", evidence.render(r, "x"))
