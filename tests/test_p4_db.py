"""P4 DB adapter on the unit DB: SYNTHETIC chain 999004, the hand-built gas book of tests/test_fifo_rulings.py written as ledger rows
(raw units). Checks: state round trip (md5), incremental == rebuild (engine and table md5), snapshot twice byte-identical,
reconciliation passes, open qty == ledger net qty. No network.
Run: CRYPTOPNL_DSN=postgresql:///cryptopnl_unit_p4 ENVIO_API_TOKEN=x .venv/bin/python -m unittest -v tests.test_p4_db"""
import io, json, os, unittest
from contextlib import redirect_stdout
from decimal import Decimal as D
os.environ.setdefault("ENVIO_API_TOKEN", "test")
from cryptopnl import db, fifo, p4, reconcile

C = 999004   # SYNTHETIC chain id
GHST = "0x" + "b2" * 20
USDC = "0x" + "a1" * 20
ROWS = [  # (block, asset, raw qty, category, price, flag) -- SYNTHETIC, same as gas_book()
    (1, "USDC", 10000 * 10**6, "bridge_in", "1", None),
    (2, "USDC", -2000 * 10**6, "swap", "1", None), (2, "ETH", 10**18, "swap", "2000", None),
    (3, "USDC", -100 * 10**6, "swap", "1", None), (3, "GHST", 25 * 10**18, "swap", "4", None), (3, "ETH", -10**15, "fee", "3000", None),
    (4, "ETH", -10**15, "fee", "3000", None),
    (5, "USDC", -50 * 10**6, "nft_buy", "1", None), (5, "PORTAL", 1, "untracked", None, "untracked"), (5, "ETH", -10**15, "fee", "3000", None),
    (6, "GHST", 1 * 10**18, "swap", "4", None), (6, "USDC", -4 * 10**6, "swap", "1", None)]   # late price points for the marks

class P4Db(unittest.TestCase):
    def setUp(self):
        self.c = db.connect(); db.migrate(self.c); self.tearDown()
        p4.TOKENS[C] = {USDC: ("USDC", 6), GHST: ("GHST", 18)}
        self.addCleanup(lambda: p4.TOKENS.pop(C, None))
        ids = {}
        for sym, std, con in (("ETH", "native", None), ("USDC", "erc20", USDC), ("GHST", "erc20", GHST), ("PORTAL", "erc721", "0x" + "cc" * 20)):
            ids[sym] = self.c.execute("INSERT INTO asset(chain_id, standard, contract, token_id, symbol) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                                      (C, std, None if con is None else bytes.fromhex(con[2:]), 1 if std == "erc721" else None, sym)).fetchone()[0]
        self.w = self.c.execute("INSERT INTO wallet(chain_id, address) VALUES (%s,%s) RETURNING id", (C, b"\x01" * 20)).fetchone()[0]
        for i, (blk, sym, q, cat, px, fl) in enumerate(ROWS):
            self.c.execute("""INSERT INTO ledger_entry(wallet_id, asset_id, chain_id, tx_hash, log_index, block_number, ts, qty, category, price_usdc,
                price_source, price_confidence_label, price_flag, trade_group) VALUES (%s,%s,%s,%s,%s,%s,to_timestamp(%s),%s,%s,%s,%s,%s,%s,NULL)""",
                (self.w, ids[sym], C, bytes([blk]) * 32, i, blk, 1_700_000_000 + blk, q, cat, px, None if px is None else "fixture",
                 None if px is None else "high", fl))
        self.c.commit(); self.ids = ids; self.cfg = p4.load_config()
    def tearDown(self):
        self.c.rollback()
        self.c.execute("DELETE FROM pnl_snapshot WHERE asset_id IN (SELECT id FROM asset WHERE chain_id=%s)", (C,))
        self.c.execute("DELETE FROM lot_disposal WHERE lot_id IN (SELECT id FROM fifo_lot WHERE chain_id=%s)", (C,))
        for t in ("fifo_lot", "fifo_run", "fifo_cost_bucket", "ledger_entry", "wallet", "asset"): self.c.execute(f"DELETE FROM {t} WHERE chain_id=%s", (C,))
        self.c.commit()
    def setup_engine(self):
        rows = p4.load_rows(self.c, C, self.cfg); mk = p4.Marks(rows); return rows, mk, p4.policy(self.cfg, mk, p4.Recipes(self.c, C))
    def test_rebuild_roundtrip_incremental_snapshot_reconcile(self):
        rows, mk, pol = self.setup_engine()
        self.assertEqual((len(rows), rows[1].qty, rows[5].qty, mk.as_of_block()), (12, D(-2000), D("-0.001"), 5))   # rulings 3: MIN
        self.assertEqual(mk.as_of_detail()["set_by_assets"], [str(self.ids["ETH"])])   # ETH's last stored price is at block 5 (GHST/USDC 6)
        st = fifo.run(rows, pol); _, m = p4.write_state(self.c, C, st, pol, None); t1 = p4.table_md5(self.c, C)
        self.assertEqual(fifo.md5(p4.load_state(self.c, C)), m)
        with redirect_stdout(io.StringIO()):
            rc = p4.main(["incremental", "--chain", str(C), "--split-block", "3"])
        self.assertEqual(rc, 0)
        back = p4.load_state(self.c, C); self.assertEqual(fifo.md5(back), m); self.assertEqual(p4.table_md5(self.c, C), t1)
        r1 = p4.snapshot(self.c, C, back, pol, 6); r2 = p4.snapshot(self.c, C, p4.load_state(self.c, C), pol, 6)
        self.assertEqual((r1[1], r1[2]), (r2[1], r2[2])); self.assertEqual(json.dumps(p4._j(r1[0]), sort_keys=True), json.dumps(p4._j(r2[0]), sort_keys=True))
        L_ = reconcile.ledger_side(rows, mk, pol.nft_mark, 6, None, self.cfg)
        chk = reconcile.check(fifo.report(back, pol, 6), fifo.gas(back), L_, p4.engine_qty(back))
        self.assertEqual(chk["acceptance"], "PASS", chk["failures"])
        self.assertEqual((chk["total"]["engine_side"], chk["total"]["ledger_side"]), (D(991), D(991)))   # GHST row at block 6 nets 0 (4 for 1 @4)
        gh = self.c.execute("SELECT basis_usdc, fee_usdc, split_method FROM fifo_lot WHERE chain_id=%s AND asset_id=%s ORDER BY id LIMIT 1", (C, self.ids["GHST"])).fetchone()
        self.assertEqual((gh[0], gh[1], gh[2]), (D(103), D(3), "basis"))
        ex = self.c.execute("SELECT count(*) FROM lot_disposal_pnl d JOIN fifo_lot l ON l.id=d.lot_id WHERE l.chain_id=%s AND d.kind LIKE 'fee%%'", (C,)).fetchone()[0]
        self.assertEqual(ex, 3)
