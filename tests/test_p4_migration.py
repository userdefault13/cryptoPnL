"""Migrations 013 + 014 + 015 on a LOCAL scratch DB (scripts/p4_migration_test.sh sets P4_MIGTEST_DSN; skipped otherwise). SYNTHETIC rows only.
§8: manual_basis is never under ON DELETE CASCADE from ledger_entry; pending lots carry a NULL basis and price source."""
import os, unittest
DSN = os.environ.get("P4_MIGTEST_DSN")

@unittest.skipUnless(DSN, "P4_MIGTEST_DSN not set (run scripts/p4_migration_test.sh)")
class Migration013(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.pg = psycopg; self.c = psycopg.connect(DSN, autocommit=False); x = self.c.execute
        self.w = x("INSERT INTO wallet(chain_id,address,wallet_group) VALUES (8453,'\\x01','fixture') RETURNING id").fetchone()[0]
        self.a = x("INSERT INTO asset(chain_id,contract,standard,symbol,decimals) VALUES (8453,'\\x02','erc20','FIXTURE',18) RETURNING id").fetchone()[0]
        self.e = x("""INSERT INTO ledger_entry(wallet_id,asset_id,chain_id,tx_hash,log_index,block_number,ts,qty,category)
                     VALUES (%s,%s,8453,'\\x03',0,1,now(),1,'migration_in') RETURNING id""", (self.w, self.a)).fetchone()[0]
        self.m = x("""INSERT INTO manual_basis(chain_id,wallet_id,tx_hash,log_index,asset_id,basis_usdc) VALUES (8453,%s,'\\x03',0,%s,12)
                     RETURNING id""", (self.w, self.a)).fetchone()[0]
    def tearDown(self): self.c.rollback(); self.c.close()
    def lot(self, **kw):
        cols = {**dict(wallet_group="fixture", asset_id=self.a, open_entry_id=self.e, open_block=1, qty_open=1, qty_remaining=1, basis_status="pending"), **kw}
        return self.c.execute(f"INSERT INTO fifo_lot({','.join(cols)}) VALUES ({','.join(['%s'] * len(cols))}) RETURNING id", list(cols.values())).fetchone()[0]
    def test_pending_lot_needs_null_source(self):
        self.lot()
        self.c.execute("SAVEPOINT s")
        with self.assertRaises(self.pg.errors.CheckViolation): self.lot(basis_price_source="fixture")
        self.c.execute("ROLLBACK TO SAVEPOINT s")
        with self.assertRaises(self.pg.errors.CheckViolation): self.lot(basis_usdc=0)
    def test_manual_basis_survives_ledger_delete(self):
        l = self.lot(basis_status="manual", basis_usdc=12, basis_price_source="manual", manual_basis_id=self.m)
        self.c.execute("DELETE FROM ledger_entry WHERE id=%s", (self.e,))      # cascades to the projection only
        self.assertEqual(self.c.execute("SELECT count(*) FROM fifo_lot WHERE id=%s", (l,)).fetchone()[0], 0)
        self.assertEqual(self.c.execute("SELECT basis_usdc FROM manual_basis WHERE id=%s", (self.m,)).fetchone()[0], 12)
    def test_manual_basis_delete_restricted(self):
        self.lot(basis_status="manual", basis_usdc=12, basis_price_source="manual", manual_basis_id=self.m)
        with self.assertRaises(self.pg.errors.ForeignKeyViolation): self.c.execute("DELETE FROM manual_basis WHERE id=%s", (self.m,))
    def test_no_cascade_path_from_ledger_entry_to_manual_basis(self):
        fks = self.c.execute("""SELECT confrelid::regclass::text, conrelid::regclass::text, confdeltype FROM pg_constraint WHERE contype='f'""").fetchall()
        reach, todo = set(), ["ledger_entry"]
        while todo:
            t = todo.pop()
            for parent, child, how in fks:
                if parent == t and how == "c" and child not in reach: reach.add(child); todo.append(child)
        self.assertIn("fifo_lot", reach); self.assertIn("lot_disposal", reach); self.assertNotIn("manual_basis", reach)
        self.assertFalse([f for f in fks if f[1] == "manual_basis" and f[0] == "ledger_entry"])
    def test_disposal_kind_and_mark_checks(self):
        l = self.lot(basis_status="resolved", basis_usdc=1, basis_price_source="fixture")
        self.c.execute("SAVEPOINT s")
        with self.assertRaises(self.pg.errors.CheckViolation):
            self.c.execute("INSERT INTO lot_disposal(lot_id,close_entry_id,qty,kind) VALUES (%s,%s,1,'gift_out')", (l, self.e))
        self.c.execute("ROLLBACK TO SAVEPOINT s")
        self.c.execute("INSERT INTO lot_disposal(lot_id,close_entry_id,qty,kind,lot_status,payment_for) VALUES (%s,%s,1,'sale','resolved',%s)", (l, self.e, self.e))
        with self.assertRaises(self.pg.errors.CheckViolation):
            self.c.execute("INSERT INTO pnl_snapshot(wallet_group,asset_id,as_of_block,mark_price_usdc) VALUES ('fixture',%s,1,0)", (self.a,))
    def test_exit_realized_null_in_view(self):   # rulings 3: NULL in totals, 0 only in the display column
        l = self.lot(basis_status="resolved", basis_usdc=5, basis_price_source="fixture", basis_origin=None)
        self.c.execute("INSERT INTO lot_disposal(lot_id,close_entry_id,qty,kind,lot_status,cost_usdc,display_mv_usdc) VALUES (%s,%s,1,'exit','resolved',5,7)", (l, self.e))
        self.c.execute("INSERT INTO lot_disposal(lot_id,close_entry_id,qty,kind,lot_status,cost_usdc,proceeds_usdc) VALUES (%s,%s,1,'sale','resolved',5,8)", (l, self.e))
        r = self.c.execute("SELECT kind, realized_usdc, realized_display_usdc FROM lot_disposal_pnl WHERE lot_id=%s ORDER BY kind", (l,)).fetchall()
        self.assertEqual([(k, None if a is None else int(a), None if b is None else int(b)) for k, a, b in r], [("exit", None, 0), ("sale", 3, 3)])
        self.assertEqual(int(self.c.execute("SELECT coalesce(sum(realized_usdc),0) FROM lot_disposal_pnl WHERE lot_id=%s", (l,)).fetchone()[0]), 3)
    def test_basis_origin_check(self):
        self.lot(basis_origin="unrecorded_inflow")
        with self.assertRaises(self.pg.errors.CheckViolation): self.lot(basis_origin="made_up")


@unittest.skipUnless(DSN, "P4_MIGTEST_DSN not set (run scripts/p4_migration_test.sh)")
class Migration015(Migration013):   # P4.2: 015 (P4.1 inflows) checks after up/down/up; SYNTHETIC rows
    def entry(self, **kw):
        cols = {**dict(wallet_id=self.w, asset_id=self.a, chain_id=8453, tx_hash=b"\x04", log_index=1, block_number=2, qty=1, category="income"), **kw}
        return self.c.execute(f"INSERT INTO ledger_entry(ts,{','.join(cols)}) VALUES (now(),{','.join(['%s'] * len(cols))}) RETURNING id",
                              list(cols.values())).fetchone()[0]
    def test_income_subtype_check(self):
        self.entry(income_subtype="dao_distribution", source_ref="0x" + "f5" * 20, trace_address="0.1")
        self.entry(log_index=2, income_subtype="pocket_deposit", source_ref="0x" + "aa" * 20 + ":0x" + "bb" * 32)
        for kw in (dict(income_subtype="dao_distribution", source_ref="0xnot"), dict(income_subtype="made_up", source_ref="0x" + "f5" * 20),
                   dict(category="swap", income_subtype="dao_distribution", source_ref="0x" + "f5" * 20)):
            self.c.execute("SAVEPOINT s")
            with self.assertRaises(self.pg.errors.CheckViolation): self.entry(log_index=3, **kw)
            self.c.execute("ROLLBACK TO SAVEPOINT s")
    def test_bridge_in_origin_and_p3_mark(self):
        self.lot(basis_origin="bridge_in")
        self.c.execute("INSERT INTO p3_mark(chain_id,asset_id,as_of_block,status,held_qty,reason) VALUES (8453,%s,1,'no_valid_mark',1,'no_pool')", (self.a,))
        with self.assertRaises(self.pg.errors.CheckViolation):
            self.c.execute("INSERT INTO p3_mark(chain_id,asset_id,as_of_block,status,held_qty) VALUES (8453,%s,2,'priced',1)", (self.a,))
    def test_gotchi_lending_table(self):
        self.c.execute("""INSERT INTO gotchi_lending(chain_id,listing_id,gotchi_id,lender,added_block,source) VALUES (8453,1,7001,'\\x01',1,'fixture')""")
        self.assertEqual(self.c.execute("SELECT count(*) FROM gotchi_lending WHERE chain_id=8453").fetchone()[0], 1)
