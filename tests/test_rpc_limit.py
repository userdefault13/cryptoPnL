"""P3: host-wide RPC budget for the free Base RPC (same pattern as HyperSync): every attempt takes a slot, retries included; 429s
honour Retry-After in full via the shared back-off; outcome log; separate lock from HyperSync. Fake clock, no network."""
import io, os, random, tempfile, unittest, urllib.error
from unittest import mock
from cryptopnl import net, hostlimit, sources
from cryptopnl.hostlimit import HostLimiter
from tests.test_hostlimit_retry import Clock, busiest

class RpcBudget(unittest.TestCase):
    def test_rpc_uses_host_limiter_with_its_own_lock(self):
        hostlimit._RPC = None
        with mock.patch.dict(os.environ, {"RPC_LOCK_PATH": os.path.join(tempfile.mkdtemp(), "rpc.lock")}):
            import importlib, cryptopnl.config as cfg; importlib.reload(cfg)
            r = sources.RPC("https://base.drpc.org")
            self.assertIsInstance(r.lim, HostLimiter)
            self.assertEqual((r.lim.cap, r.lim.window, r.lim.min_gap), (int(cfg.RPC_RPM), 60.0, cfg.RPC_MIN_GAP_S))
            self.assertNotEqual(r.lim.path, hostlimit.hypersync_limiter().path)
        hostlimit._RPC = None; importlib.reload(cfg)

    def test_storm_never_exceeds_budget_and_retry_after_in_full(self):
        d = tempfile.mkdtemp(); log = os.path.join(d, "r.log"); clk = Clock(); rnd = random.Random(5); sleeps = []
        lim = HostLimiter(30, 60.0, path=os.path.join(d, "rpc.lock"), _clock=clk, _sleep=clk.sleep, min_gap=1.5)
        ras = iter(["45", None, "2"] * 200)
        def urlopen(req, timeout=None):
            clk.t += rnd.uniform(0.05, 0.4)
            if rnd.random() < 0.3:
                v = next(ras); raise urllib.error.HTTPError("u", 429, "x", {"Retry-After": v} if v else {}, io.BytesIO(b""))
            return io.BytesIO(b'{"jsonrpc":"2.0","id":1,"result":"0x1"}')
        def sleep(s): sleeps.append(s); clk.sleep(s)
        rpc = sources.RPC("https://base.drpc.org/KEY", limiter=lim)
        with mock.patch.dict(os.environ, {"NET_REQLOG": log}), mock.patch.object(net.time, "time", clk), \
             mock.patch.object(net.urllib.request, "urlopen", urlopen), \
             mock.patch.object(sources, "post_json", lambda *a, **k: net.post_json(*a, _sleep=sleep, **k)):
            for _ in range(60):
                try: rpc.call("eth_blockNumber", [])
                except RuntimeError: pass
        with open(log) as f: rows = [l.split() for l in f]
        att = [float(r[0]) for r in rows if r[2] == "attempt"]; outs = [r for r in rows if r[2] == "outcome"]
        self.assertLessEqual(busiest(att), 30); self.assertGreaterEqual(min(y - x for x, y in zip(att, att[1:])), 1.5)
        self.assertIn(45.0, sleeps)                                       # Retry-After honoured in full
        self.assertTrue(any("status=429" in " ".join(r) and "retry_after=45" in " ".join(r) for r in outs))
        self.assertTrue(all("endpoint=<redacted>" in " ".join(r) for r in outs))   # RPC path never logged
        self.assertFalse(any("KEY" in " ".join(r) for r in rows))

if __name__ == "__main__": unittest.main()
