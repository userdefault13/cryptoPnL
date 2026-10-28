"""P3 follow-up (b): price-report (pricing.coverage) fails when migration 011 is applied but the chain has no price_run row (the RPC
errors of the pricing run are then unknown). Synthetic chain id 999003 and synthetic rows in the unit DB; no network.
Run: CRYPTOPNL_DSN=postgresql:///cryptopnl_unit_p4 ENVIO_API_TOKEN=x .venv/bin/python -m unittest -v tests.test_price_report_run"""
import os, unittest
from decimal import Decimal
os.environ.setdefault("ENVIO_API_TOKEN", "test")
from cryptopnl import db, pricing

C = 999003   # SYNTHETIC chain id
class PriceReportNeedsRun(unittest.TestCase):
    def setUp(self):
        self.c = db.connect(); db.migrate(self.c); self.tearDown()
        a = self.c.execute("INSERT INTO asset(chain_id, standard, symbol, decimals) VALUES (%s,'native','SYNTH',18) RETURNING id", (C,)).fetchone()[0]
        self.c.execute("""INSERT INTO ledger_entry(asset_id, chain_id, tx_hash, log_index, block_number, ts, qty, category, price_usdc, price_source)
            VALUES (%s,%s,%s,0,100,to_timestamp(1700000000),1,'swap',%s,'synthetic')""", (a, C, bytes.fromhex("cc" * 32), Decimal("2.5")))
        self.c.commit()
    def tearDown(self):
        self.c.rollback()
        for t in ("price_run", "ledger_entry", "asset"): self.c.execute(f"DELETE FROM {t} WHERE chain_id=%s", (C,))
        self.c.commit()
    def run_row(self, errors):
        self.c.execute("INSERT INTO price_run(chain_id, entries, rpc_calls, rpc_errors, fallthrough_after_rpc_error) VALUES (%s,1,1,%s,0)", (C, errors))
    def test_no_price_run_row_fails(self):
        r = pricing.coverage(self.c, C)
        self.assertFalse(r["pass"]); self.assertIsNone(r["price_run"]); self.assertTrue(any("no price_run row" in f for f in r["failures"]))
    def test_clean_price_run_passes(self):
        self.run_row(0); r = pricing.coverage(self.c, C)
        self.assertEqual((r["pass"], r["failures"], r["priced"]), (True, [], 1))
    def test_price_run_with_rpc_errors_still_fails(self):
        self.run_row(2); r = pricing.coverage(self.c, C)
        self.assertFalse(r["pass"]); self.assertTrue(any("hit 2 RPC errors" in f for f in r["failures"]))
