"""P3 C1 rulings (PR #7 at fd12039, DESIGN §8 'P3 C1 rulings'): unpriced samples need a machine-checkable reason (stale_pool with the
last-swap age, no_pool, zero_reserves); stale_pool is re-derived from the pool_swap cache; GLTR gets a separate 5-block path probe at
the GLTR/GHST pool's own swap blocks (thin tier, low, flagged). Offline: fake RPC (tests.test_pricing); DB cases use the unit DB."""
import unittest
from cryptopnl import pricing
from cryptopnl.config import THIN_SWAP_WINDOW_BLOCKS as WIN
from tests import test_pricing as tp
from tests.test_pricing import FakeRPC, FakeAPI, market, w, bal, C, GHST, FUD, P_FUD, P_GHST, E18
from tests.test_p3_rulings import thin_market, BN, GLTR
P_GLTR = "0xa83b31d701633b8edcfba55b93ddbc202d8a4621"

def gltr_market():   # GLTR/GHST v2: 1e9 GLTR / 1,000 GHST ($500 GHST side, thin); GHST = 0.5 USDC
    m = market(); m[(P_GLTR, "0x0902f1ac")] = w(10 ** 9 * E18, 1_000 * E18, 0); m[bal(GHST, P_GLTR)] = w(1_000 * E18); return m

class ReasonCodes(unittest.TestCase):
    def why(self, m, asset, swaps=None, api=None):
        pr = pricing.Pricer(C, FakeRPC(m), FakeAPI(api), swaps=swaps)
        self.assertIsNone(pr.price(asset, BN, 0)); return pr.unpriced_reason(asset, BN)
    def test_stale_pool_with_age(self):
        r = self.why(thin_market(), FUD, {P_FUD: ([BN - WIN - 43_200], 33_200_000, BN)})
        self.assertEqual((r["reason"], r["pool"], r["last_swap_block"], r["last_swap_age_blocks"]), ("stale_pool", P_FUD, BN - WIN - 43_200, WIN + 43_200))
        self.assertEqual(r["last_swap_age_days"], 8.0)                      # (302,400 + 43,200) x 2 s / 86,400
        self.assertIn(r["reason"], pricing.ACCEPTED_UNPRICED)
    def test_stale_pool_exactly_7d_and_no_swap_in_scan(self):
        r0 = self.why(thin_market(), FUD, {P_FUD: ([BN - WIN], 33_200_000, BN)})
        self.assertEqual((r0["last_swap_age_days"], r0["age_is_lower_bound"]), (7.0, False))
        r = self.why(thin_market(), FUD, {P_FUD: ([], 33_200_000, BN)})        # no swap in the scanned range: lower bound
        self.assertEqual((r["reason"], r["last_swap_block"], r["last_swap_age_blocks"], r["age_is_lower_bound"]),
                         ("stale_pool", None, BN - 33_200_000, True))
        self.assertEqual(r["last_swap_age_days"], round((BN - 33_200_000) * 2 / 86400, 2))
    def test_zero_reserves(self):
        m = thin_market(); m[(P_FUD, "0x0902f1ac")] = w(0, 1_000 * E18, 0)
        r = self.why(m, FUD, {P_FUD: ([BN - 10], 33_200_000, BN)}); self.assertEqual((r["reason"], r["pool"]), ("zero_reserves", P_FUD))
        m = thin_market(); m[bal(GHST, P_FUD)] = w(0)                       # quote balance 0
        self.assertEqual(self.why(m, FUD, {P_FUD: ([BN - 10], 33_200_000, BN)})["reason"], "zero_reserves")
    def test_no_pool(self):
        m = thin_market(); del m[(P_FUD, "0x0902f1ac")]                     # pool reverts / not deployed at the block
        self.assertEqual(self.why(m, FUD, {})["reason"], "no_pool")
        self.assertEqual(pricing.Pricer(C, FakeRPC(market()), FakeAPI()).unpriced_reason("0x" + "ab" * 20, BN), {"reason": "no_pool"})
    def test_unaccepted_reasons_fail_c1(self):
        r = self.why(thin_market(), FUD, {}); self.assertEqual(r["reason"], "swap_scan_gap")            # pool never scanned
        r2 = self.why(thin_market(), FUD, {P_FUD: ([BN - 10], 33_200_000, BN - 1)}); self.assertEqual(r2["reason"], "swap_scan_gap")
        m = thin_market(); del m[(P_GHST, "0x3850c7bd")]
        self.assertEqual(self.why(m, FUD, {P_FUD: ([BN - 10], 33_200_000, BN)})["reason"], "quote_unpriced")
        mg = market(ghst_usdc_reserve=999); mg[bal(GHST, P_GHST)] = w(1_000 * E18)      # v3: both balances > 0, below the floor
        self.assertEqual(self.why(mg, GHST, {}, api={GHST: "0.49"})["reason"], "below_floor_not_thin_tier")   # API price present: still unpriced
        for x in (r, r2): self.assertNotIn(x["reason"], pricing.ACCEPTED_UNPRICED)
    def test_empty_result_uses_getcode(self):
        m = thin_market(); m[(P_FUD, "0x0902f1ac")] = "0x"                  # empty eth_call result
        self.assertEqual(self.why(m, FUD, {})["reason"], "no_pool")          # eth_getCode = 0x -> no_pool
        m[("code", P_FUD)] = "0x6080"
        r = self.why(m, FUD, {}); self.assertEqual(r["reason"], "bad_response"); self.assertNotIn(r["reason"], pricing.ACCEPTED_UNPRICED)
    def test_v3_thin_pool_needs_both_balances(self):
        P_V3 = "0x" + "77" * 20
        def pr(m, sw):
            x = pricing.Pricer(C, FakeRPC(m), FakeAPI(), swaps=sw); x.pools = {FUD: [("v3", P_V3, tp.USDC)]}; x.thin_assets = {FUD}; return x
        m = market(); m[(P_V3, "0x3850c7bd")] = w(tp.sqrtp(0.0005, 18, 6), 0); m[bal(tp.USDC, P_V3)] = w(500 * 10 ** 6)   # $500 < floor
        sw = {P_V3: ([BN - 10], 33_200_000, BN)}
        m[bal(FUD, P_V3)] = w(0)
        x = pr(m, sw); self.assertIsNone(x.price(FUD, BN, 0))
        self.assertEqual((x.unpriced_reason(FUD, BN)["reason"], x.unpriced_reason(FUD, BN)["token"]), ("zero_reserves", FUD))
        m[bal(FUD, P_V3)] = w(1_000_000 * E18)
        p = pr(m, sw).price(FUD, BN, 0)
        self.assertEqual((p.source, p.label), ("dex_reserves_thin", "low")); self.assertAlmostEqual(float(p.price), 0.0005, places=9)
    def test_summary_counts_by_reason(self):
        res = {"FUD": {"gated": True, "unpriced_by_reason": {"stale_pool": 3, "rpc_error": 1}},
               "KEK": {"gated": True, "unpriced_by_reason": {"stale_pool": 1}}, "WETH": {"gated": False, "unpriced_by_reason": {"no_pool": 9}}}
        self.assertEqual(pricing._count_reasons(res), {"stale_pool": 4, "rpc_error": 1})
    def test_flag_helper(self):
        pr = pricing.Pricer(C, FakeRPC(thin_market()), FakeAPI(), swaps={P_FUD: ([BN - 10], 33_200_000, BN)})
        self.assertEqual(pricing.price_flag_for(pr.price(FUD, BN, 0)), "low_confidence")
        self.assertIsNone(pricing.price_flag_for(pr.price(GHST, BN, 0)))

class CacheChecks(tp.LedgerPass):
    def swaps(self, pool, blocks, frm, to):
        self.c.execute("DELETE FROM pool_swap WHERE chain_id=%s AND pool=decode(%s,'hex')", (C, pool[2:]))
        self.c.execute("DELETE FROM pool_swap_scan WHERE chain_id=%s AND pool=decode(%s,'hex')", (C, pool[2:]))
        for b in blocks: self.c.execute("INSERT INTO pool_swap(chain_id,pool,block_number) VALUES (%s,decode(%s,'hex'),%s)", (C, pool[2:], b))
        self.c.execute("INSERT INTO pool_swap_scan(chain_id,pool,from_block,scanned_to) VALUES (%s,decode(%s,'hex'),%s,%s)", (C, pool[2:], frm, to)); self.c.commit()
    def tearDown(self):
        self.c.execute("DELETE FROM pool_swap"); self.c.execute("DELETE FROM pool_swap_scan"); self.c.commit(); super().tearDown()
    def test_verify_stale_rederives_from_sql(self):
        self.swaps(P_FUD, [BN - WIN - 500, BN + 10], 33_200_000, BN + 100)
        ok = pricing.verify_stale(self.c, C, P_FUD, BN, BN - WIN - 500)
        self.assertEqual((ok["ok"], ok["sql_last_swap_block"], ok["age_blocks"]), (True, BN - WIN - 500, WIN + 500))
        self.assertFalse(pricing.verify_stale(self.c, C, P_FUD, BN, BN - WIN - 400)["ok"])       # claimed last swap disagrees
        self.swaps(P_FUD, [BN + 10], 33_200_000, BN + 100)                                   # no swap at/before: lower bound
        lb = pricing.verify_stale(self.c, C, P_FUD, BN, None)
        self.assertEqual((lb["ok"], lb["age_blocks"], lb["age_is_lower_bound"]), (True, BN - 33_200_000, True))
        self.swaps(P_FUD, [], BN - WIN + 1, BN + 100)
        self.assertFalse(pricing.verify_stale(self.c, C, P_FUD, BN, None)["ok"])                # lower bound < 7 d: not provably stale
        self.swaps(P_FUD, [BN - 5], 33_200_000, BN + 100)
        self.assertFalse(pricing.verify_stale(self.c, C, P_FUD, BN, BN - 5)["ok"])               # swap < 7 d: not stale
        self.swaps(P_FUD, [BN - WIN - 500], 33_200_000, BN - 1)
        self.assertFalse(pricing.verify_stale(self.c, C, P_FUD, BN, BN - WIN - 500)["ok"])       # scan does not reach the block
    def test_gltr_probe_passes_5_of_5_from_cached_swaps(self):
        blocks = [BN + i * 1000 for i in range(8)]; self.swaps(P_GLTR, blocks, 33_200_000, BN + 10_000)
        pr = pricing.Pricer(C, FakeRPC(gltr_market()), FakeAPI({GHST: "0.505"}), swaps=pricing.load_swaps(self.c, C))
        rows = []
        out = pricing.gltr_probe(self.c, C, pr, 5, 3, min_block=BN, log=lambda x: rows.append(x))
        self.assertEqual((out["pass"], out["passed"], out["of"], out["candidates"], len(out["blocks"])), (True, 5, 5, 8, 5))
        self.assertEqual((out["ghst_within_3pct"], out["ghst_outside_3pct"]), (5, []))
        import json
        g = [json.loads(r)["gltr_probe_block"]["ghst_vs_api"] for r in rows if "gltr_probe_block" in r]
        self.assertEqual(len(g), 5)
        self.assertEqual((g[0]["pool"], g[0]["dev_pct"], g[0]["pool_depth_usd"], g[0]["pool_usdc_balance"]), (P_GHST, -0.99, "10000.00", "10000"))
        self.assertTrue(all(x["within_3pct"] and x["block_ts"] is not None for x in g))
        self.assertTrue(set(out["blocks"]) <= set(blocks))
    def test_gltr_probe_fails_when_ghst_leg_misses_3pct(self):
        self.swaps(P_GLTR, [BN + i * 1000 for i in range(8)], 33_200_000, BN + 10_000)
        pr = pricing.Pricer(C, FakeRPC(gltr_market()), FakeAPI({GHST: "0.53"}), swaps=pricing.load_swaps(self.c, C))   # 0.5 vs 0.53: -5.66%
        out = pricing.gltr_probe(self.c, C, pr, 5, 3, min_block=BN, log=lambda *_: None)
        self.assertEqual((out["pass"], out["passed"], out["ghst_within_3pct"], len(out["ghst_outside_3pct"])), (False, 0, 0, 5))
        self.assertEqual(out["ghst_outside_3pct"][0]["dev_pct"], -5.66)
        pr2 = pricing.Pricer(C, FakeRPC(gltr_market()), FakeAPI(), swaps=pricing.load_swaps(self.c, C))                  # no API price: fails
        self.assertFalse(pricing.gltr_probe(self.c, C, pr2, 5, 3, min_block=BN, log=lambda *_: None)["pass"])
    def test_gltr_probe_fails_without_reserves_or_outside_min_block(self):
        self.swaps(P_GLTR, [BN + i for i in range(6)], 33_200_000, BN + 10)
        m = gltr_market(); del m[(P_GLTR, "0x0902f1ac")]
        out = pricing.gltr_probe(self.c, C, pricing.Pricer(C, FakeRPC(m), FakeAPI(), swaps=pricing.load_swaps(self.c, C)), 5, 3, min_block=BN, log=lambda *_: None)
        self.assertEqual((out["pass"], out["passed"]), (False, 0))
        out2 = pricing.gltr_probe(self.c, C, pricing.Pricer(C, FakeRPC(gltr_market()), FakeAPI(), swaps=pricing.load_swaps(self.c, C)), 5, 3, min_block=BN + 3, log=lambda *_: None)
        self.assertEqual((out2["pass"], out2["candidates"]), (False, 3))                        # fewer than 5 swap blocks -> fail

if __name__ == "__main__": unittest.main()


class RpcErrors(unittest.TestCase):
    """PR #7 review blocker: JSON-RPC errors arrive as HTTP 200 and raise RuntimeError in sources.RPC.call; they must surface as
    rpc_error (fails C1), never as no_pool. Only 'execution reverted' (or eth_getCode = 0x) is no_pool."""
    def rpc_with_body(self, body):
        import io, os, tempfile
        from unittest import mock
        from cryptopnl import net, sources
        from cryptopnl.hostlimit import HostLimiter
        d = tempfile.mkdtemp(); lim = HostLimiter(10_000, 60.0, path=os.path.join(d, "rpc.lock"), min_gap=0)
        def urlopen(req, timeout=None): return io.BytesIO(body)            # HTTP 200, JSON body
        ctx = [mock.patch.dict(os.environ, {"NET_REQLOG": os.path.join(d, "r.log")}), mock.patch.object(net.urllib.request, "urlopen", urlopen)]
        for c in ctx: c.start()
        self.addCleanup(lambda: [c.stop() for c in ctx])
        return sources.RPC("https://base.drpc.org/KEY", limiter=lim)
    def test_http200_jsonrpc_error_is_rpc_error_not_no_pool(self):
        rpc = self.rpc_with_body(b'{"jsonrpc":"2.0","id":1,"error":{"code":-32005,"message":"upstream rate limit exceeded"}}')
        with self.assertRaises(RuntimeError): rpc.eth_call(P_FUD, "0x0902f1ac", BN)        # sources.py raises on "error"
        pr = pricing.Pricer(C, rpc, FakeAPI(), swaps={P_FUD: ([BN - 10], 33_200_000, BN)})
        self.assertIsNone(pr.price(FUD, BN, 0))
        r = pr.unpriced_reason(FUD, BN)
        self.assertEqual(r["reason"], "rpc_error"); self.assertNotIn("rpc_error", pricing.ACCEPTED_UNPRICED)
        self.assertIn("rate limit", r["errors"][0]["error"]); self.assertGreaterEqual(len(pr.rpc_errors), 1)
    def test_http200_execution_reverted_is_no_pool(self):
        rpc = self.rpc_with_body(b'{"jsonrpc":"2.0","id":1,"error":{"code":3,"message":"execution reverted"}}')
        pr = pricing.Pricer(C, rpc, FakeAPI(), swaps={})
        self.assertIsNone(pr.price(FUD, BN, 0))
        self.assertEqual((pr.unpriced_reason(FUD, BN)["reason"], pr.rpc_errors), ("no_pool", []))

class UpsertConfidence(tp.LedgerPass):
    def test_price_point_upsert_updates_confidence(self):
        from tests.test_pricing import W, X, ZERO, tx, e20
        h = self.add(tx(W, X), e20(GHST, ZERO, W, 4 * E18), bn=BN); self.run_()
        pricing.price_ledger(self.c, C, pricing.Pricer(C, FakeRPC(market()), FakeAPI()), log=lambda *_: None)
        self.c.execute("UPDATE price_point SET confidence=0.1, confidence_label='low' WHERE source='dex_slot0'"); self.c.commit()
        pricing.price_ledger(self.c, C, pricing.Pricer(C, FakeRPC(market()), FakeAPI()), log=lambda *_: None)
        self.assertEqual(self.c.execute("SELECT DISTINCT confidence_label FROM price_point WHERE source='dex_slot0'").fetchall(), [("high",)])


class RpcErrorRun(tp.LedgerPass):
    """PR #7 approval note: an RPC error in price_ledger must fail price-report (C3), and GHST failing over from its first pool after an
    RPC error must be visible (price detail skipped_pools, pricer.fallthrough, price_run.fallthrough_after_rpc_error)."""
    def tearDown(self): self.c.execute("DELETE FROM price_run"); self.c.commit(); super().tearDown()
    def test_rpc_error_fails_price_report(self):
        from tests.test_pricing import W, X, ZERO, tx, e20
        self.add(tx(W, X), e20(FUD, ZERO, W, 1000 * E18), bn=BN); self.run_()
        class ErrRPC(FakeRPC):
            def eth_call(self, to, data, block):
                if to == P_FUD: raise RuntimeError("rpc eth_call: {'code': -32005, 'message': 'upstream limit exceeded'}")
                return super().eth_call(to, data, block)
        st = pricing.price_ledger(self.c, C, pricing.Pricer(C, ErrRPC(market()), FakeAPI()), log=lambda *_: None)
        self.assertGreaterEqual(st["rpc_errors"], 1)
        cov = pricing.coverage(self.c, C)
        self.assertEqual(cov["neither"], 0)                                 # C3's old check alone would pass (no_price flag)
        self.assertFalse(cov["pass"]); self.assertTrue(any("RPC errors" in f for f in cov["failures"]))
        self.assertGreaterEqual(cov["price_run"]["rpc_errors"], 1)
        pricing.price_ledger(self.c, C, pricing.Pricer(C, FakeRPC(market()), FakeAPI()), log=lambda *_: None)
        cov2 = pricing.coverage(self.c, C)                                   # a clean later run passes again
        self.assertTrue(cov2["pass"]); self.assertEqual((cov2["price_run"]["rpc_errors"], cov2["failures"]), (0, []))
    def test_price_report_cli_exit_code(self):
        import json, os, subprocess, sys
        from tests.test_pricing import W, X, ZERO, tx, e20
        self.add(tx(W, X), e20(GHST, ZERO, W, 4 * E18), bn=BN); self.run_()
        pricing.price_ledger(self.c, C, pricing.Pricer(C, FakeRPC(market()), FakeAPI()), log=lambda *_: None)
        self.c.execute("UPDATE price_run SET rpc_errors=2 WHERE id=(SELECT max(id) FROM price_run)"); self.c.commit()
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        p = subprocess.run([sys.executable, "-m", "cryptopnl", "price-report", "--chain", str(C)], cwd=root, capture_output=True, text=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn("PRICE-REPORT FAIL", p.stderr)
        self.assertIn("price_report_fail", p.stdout)
        self.assertFalse(json.loads(p.stdout.splitlines()[0])["pass"])
    def test_ghst_fallthrough_after_rpc_error_on_first_pool(self):
        P2 = pricing.PRICE_POOLS[C][GHST][1][1]
        m = market(); m[(P2, "0x3850c7bd")] = m[(P_GHST, "0x3850c7bd")]; m[bal(tp.USDC, P2)] = w(10_000 * 10 ** 6)
        class ErrRPC(FakeRPC):
            def eth_call(self, to, data, block):
                if to == P_GHST: raise RuntimeError("rpc eth_call: {'code': -32603, 'message': 'internal error'}")
                return super().eth_call(to, data, block)
        pr = pricing.Pricer(C, ErrRPC(m), FakeAPI())
        g = pr.price(GHST, BN, 0)
        self.assertEqual((g.source, g.detail["pool"]), ("dex_slot0", P2))
        self.assertEqual(g.detail["skipped_pools"], [{"pool": P_GHST, "why": "error"}])
        self.assertEqual(len(pr.fallthrough), 1); self.assertEqual(pr.fallthrough[0]["used_pool"], P2)
        self.assertEqual(len(pr.rpc_errors), 1)


class Retry408(unittest.TestCase):
    """Architect ruling on the d909779 rerun: HTTP 408 retried like 5xx (backoff, Retry-After honored), at most 3 attempts per call,
    every attempt through the RPC limiter; still failing after 3 -> RuntimeError -> rpc_error (price-report gate unchanged)."""
    def setUp(self):
        import io, os, tempfile, urllib.error
        from unittest import mock
        from cryptopnl import net, sources
        from cryptopnl.hostlimit import HostLimiter
        self.io, self.err, self.net = io, urllib.error, net
        d = tempfile.mkdtemp(); self.log = os.path.join(d, "r.log"); self.sleeps = []; self.waits = 0
        lim = HostLimiter(10_000, 60.0, path=os.path.join(d, "rpc.lock"), min_gap=0)
        real_wait = lim.wait
        def wait():
            self.waits += 1; return real_wait()
        lim.wait = wait; lim.backoff = lambda d: None
        self.rpc = sources.RPC("https://base.drpc.org/KEY", limiter=lim)
        ps = [mock.patch.dict(os.environ, {"NET_REQLOG": self.log}),
              mock.patch.object(sources, "post_json", lambda *a, **k: net.post_json(*a, _sleep=self.sleeps.append, **k))]
        for p in ps: p.start()
        self.addCleanup(lambda: [p.stop() for p in ps]); net.STATS.pop("rpc", None)
    def run_with(self, responses):
        from unittest import mock
        it = iter(responses); self.calls = 0
        def urlopen(req, timeout=None):
            self.calls += 1; r = next(it)
            if isinstance(r, tuple):
                code, ra = r; raise self.err.HTTPError("u", code, "x", {"Retry-After": ra} if ra else {},
                                                       self.io.BytesIO(b'{"error":{"message":"Request timeout on the free plan","code":30}}'))
            return self.io.BytesIO(r)
        with mock.patch.object(self.net.urllib.request, "urlopen", urlopen): return self.rpc.call("eth_blockNumber", [])
    def test_408_then_success(self):
        self.assertEqual(self.run_with([(408, "7"), b'{"jsonrpc":"2.0","id":1,"result":"0x1"}']), "0x1")
        st = self.net.STATS["rpc"]
        self.assertEqual((self.calls, self.waits, st["408"], st["retries"], st["retry_after_honored"]), (2, 2, 1, 1, 1))
        self.assertIn(7.0, self.sleeps)                                      # Retry-After honored in full
        with open(self.log) as f: att = [l for l in f if l.split()[2] == "attempt"]
        self.assertEqual(len(att), 2)                                        # both attempts went through the limiter (logged)
    def test_408_three_times_fails(self):
        with self.assertRaises(RuntimeError) as cm:
            self.run_with([(408, None), (408, None), (408, None), b'{"jsonrpc":"2.0","id":1,"result":"0x1"}'])
        self.assertIn("408 after 3 attempts", str(cm.exception))
        self.assertEqual((self.calls, self.waits, self.net.STATS["rpc"]["retries"]), (3, 3, 2))
        self.assertEqual(len(self.sleeps), 2)                                # backoff between attempts, none after the last
    def test_408_exhausted_is_rpc_error_in_pricer(self):
        from unittest import mock
        def urlopen(req, timeout=None):
            raise self.err.HTTPError("u", 408, "x", {}, self.io.BytesIO(b'{"error":{"code":30}}'))
        with mock.patch.object(self.net.urllib.request, "urlopen", urlopen):
            pr = pricing.Pricer(C, self.rpc, FakeAPI(), swaps={P_FUD: ([BN - 10], 33_200_000, BN)})
            self.assertIsNone(pr.price(FUD, BN, 0)); self.assertEqual(pr.unpriced_reason(FUD, BN)["reason"], "rpc_error")

class PriceRunTimes(tp.LedgerPass):
    def tearDown(self): self.c.execute("DELETE FROM price_run"); self.c.commit(); super().tearDown()
    def test_started_and_finished_wall_clock(self):
        from tests.test_pricing import W, X, ZERO, tx, e20
        self.add(tx(W, X), e20(GHST, ZERO, W, 4 * E18), bn=BN); self.run_()
        t0 = self.c.execute("SELECT clock_timestamp()").fetchone()[0]; self.c.commit()
        class SlowRPC(FakeRPC):
            def eth_call(self, *a):
                import time; time.sleep(0.01); return super().eth_call(*a)
        st = pricing.price_ledger(self.c, C, pricing.Pricer(C, SlowRPC(market()), FakeAPI()), log=lambda *_: None)
        s, f, rr = self.c.execute("SELECT started_at, finished_at, rpc_retries FROM price_run ORDER BY id DESC LIMIT 1").fetchone()
        self.assertTrue(t0 <= s < f); self.assertEqual((rr, st["rpc_retries"]), (0, 0))
        pr = pricing.coverage(self.c, C)["price_run"]
        self.assertEqual((pr["rpc_retries"], pr["started_at"] < pr["finished_at"]), (0, True))
