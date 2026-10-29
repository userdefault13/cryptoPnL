"""P4.2 follow-ups (architect review of PR #9): Pricer.seed keeps the stored point the price order would return (not the highest id);
the unpriced_reason docstring is a real docstring. SYNTHETIC prices and blocks only; no DB, no network."""
import os, unittest
os.environ.setdefault("ENVIO_API_TOKEN", "test")
from cryptopnl.pricing import Pricer, Price
from cryptopnl.config import PRICE_POOLS

GHST = "0xcd2f22236dd9dfe2356d7c543161d4d260fd9bcb"
P0, P1 = PRICE_POOLS[8453][GHST][0][1], PRICE_POOLS[8453][GHST][1][1]
B = 123   # SYNTHETIC block
def pt(px, src, pool=None, lab="high"): return (GHST, B, Price(px, src, lab, {"pool": pool} if pool else {}))

class SeedByRank(unittest.TestCase):
    def seeded(self, *points):
        p = Pricer(8453, None); p.seed(list(points)); return p.price(GHST, B, None)
    def test_dex_beats_a_later_thin_point(self):
        self.assertEqual(self.seeded(pt("0.5", "dex_slot0", P0), pt("0.4", "dex_reserves_thin", P0, "low")).source, "dex_slot0")
        self.assertEqual(self.seeded(pt("0.4", "dex_reserves_thin", P0, "low"), pt("0.5", "dex_slot0", P0)).source, "dex_slot0")
    def test_first_configured_pool_wins_within_the_dex_step(self):
        self.assertEqual(self.seeded(pt("0.6", "dex_slot0", P1), pt("0.5", "dex_slot0", P0)).detail["pool"], P0)
        self.assertEqual(self.seeded(pt("0.5", "dex_slot0", P0), pt("0.6", "dex_slot0", P1)).detail["pool"], P0)
    def test_unordered_source_ranks_last(self):
        self.assertEqual(self.seeded(pt("0.7", "defillama"), pt("0.4", "dex_reserves_thin", P0, "low")).source, "dex_reserves_thin")
    def test_equal_rank_keeps_input_order(self):   # stored_points is ORDER BY price_point.id -> lowest id among equals
        self.assertEqual(self.seeded(pt("0.7", "defillama"), pt("0.8", "other")).price, Price("0.7", "x", "high").price)
    def test_single_point_and_hits(self):
        p = Pricer(8453, None); p.seed([pt("0.5", "dex_slot0", P0)])
        self.assertEqual(p.price(GHST.upper().replace("0X", "0x", 1), B, None).price, Price("0.5", "x", "high").price); self.assertEqual(p.seed_hits, 1)
    def test_rank_values(self):
        p = Pricer(8453, None)
        self.assertEqual([p.seed_rank(GHST, x[2]) for x in (pt(1, "numeraire"), pt(1, "dex_slot0", P1), pt(1, "dex_reserves_thin", P0), pt(1, "defillama"))],
                         [(0, len(PRICE_POOLS[8453][GHST])), (1, 1), (2, 0), (3, len(PRICE_POOLS[8453][GHST]))])

class Docstrings(unittest.TestCase):
    def test_unpriced_reason_docstring_is_live(self):
        self.assertTrue((Pricer.unpriced_reason.__doc__ or "").startswith("C1 ruling"))
    def test_seed_only_still_answers_not_seeded(self):
        p = Pricer(8453, None); p.seed_only = True; self.assertEqual(p.unpriced_reason(GHST, B), {"reason": "not_seeded"})

class NoTestLinesInReqlog(unittest.TestCase):   # P4.2: fake requests in the unit suite must not reach an inherited NET_REQLOG
    def test_net_test_modules_leave_an_inherited_reqlog_empty(self):
        import subprocess, sys, tempfile
        f = os.path.join(tempfile.mkdtemp(), "reqlog.txt"); open(f, "w").close()
        env = dict(os.environ, NET_REQLOG=f, ENVIO_API_TOKEN="test")
        r = subprocess.run([sys.executable, "-m", "unittest", "-q", "tests.test_net_retry", "tests.test_retry_after_full"],
                           cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))), env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:]); self.assertEqual(open(f).read(), "")
    def test_committed_reqlogs_hold_real_sources_only(self):
        d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "evidence")
        for n in ("p4_1_reqlog.txt", "p4_1_rf_price_reqlog.txt"):
            for l in open(os.path.join(d, n)):
                ts, src = l.split()[:2]
                self.assertIn(src, ("rpc", "hypersync", "blockscout", "defillama"), (n, l)); self.assertGreater(float(ts), 1.7e9, (n, l))

class EvidenceHasNoHomePaths(unittest.TestCase):   # P4.2: evidence paths carry no personal name (paths use ~ or user_default)
    def test_no_name_in_evidence(self):
        d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "evidence")
        for n in sorted(os.listdir(d)):
            with open(os.path.join(d, n), "rb") as f: b = f.read().lower()
            self.assertNotIn(b"julius", b, n)

class SeedRankCheckScript(unittest.TestCase):   # scripts/p4_2_seed_rank_check.py on SYNTHETIC rows of a synthetic chain (unit DB)
    CH = 999002
    def setUp(self):
        from cryptopnl import db
        self.c = db.connect(); db.migrate(self.c); self.tearDown()
        self.a = self.c.execute("INSERT INTO asset(chain_id, contract, standard, symbol, decimals) VALUES (%s,'\\x0a','erc20','SYN',18) RETURNING id", (self.CH,)).fetchone()[0]
    def tearDown(self):
        self.c.rollback()
        for t in ("ledger_entry", "price_point", "asset"): self.c.execute(f"DELETE FROM {t} WHERE chain_id=%s", (self.CH,))
        self.c.commit()
    def pp(self, block, src, px):
        return self.c.execute("""INSERT INTO price_point(asset_id,chain_id,block_number,ts,price_usdc,source,confidence_label,detail)
            VALUES (%s,%s,%s,now(),%s,%s,'high','{}') RETURNING id""", (self.a, self.CH, block, px, src)).fetchone()[0]
    def run_check(self):
        import importlib.util
        f = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "p4_2_seed_rank_check.py")
        sp = importlib.util.spec_from_file_location("seed_rank_check", f); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
        return m.check(self.c, self.CH)
    def test_no_change_when_the_later_point_ranks_first(self):
        self.pp(10, "dex_reserves_thin", "0.4"); self.pp(10, "dex_slot0", "0.5"); self.pp(11, "dex_slot0", "0.6")
        r = self.run_check(); self.assertEqual((r["asset_blocks"], r["asset_blocks_with_several_points"], r["choice_changed"], r["verdict"]), (2, 1, 0, "no change"))
    def test_change_reported_when_a_later_point_ranks_lower(self):
        d = self.pp(10, "dex_slot0", "0.5"); t = self.pp(10, "dex_reserves_thin", "0.4")
        r = self.run_check(); self.assertEqual((r["choice_changed"], r["verdict"]), (1, "CHANGE"))
        self.assertEqual((r["changes"][0]["old"]["id"], r["changes"][0]["new"]["id"]), (t, d))

if __name__ == "__main__": unittest.main()
