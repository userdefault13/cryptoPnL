"""P3 step 1: host-level HyperSync limiter. Two concurrent OS processes share one flock'd budget and never exceed it.
Offline, no network. Run: ENVIO_API_TOKEN=x .venv/bin/python -m unittest -v tests.test_hostlimit"""
import json, os, subprocess, sys, tempfile, time, unittest
os.environ.setdefault("ENVIO_API_TOKEN", "test")
from cryptopnl.hostlimit import HostLimiter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHILD = """import json, sys; sys.path.insert(0, %r)
from cryptopnl.hostlimit import HostLimiter
lim = HostLimiter(%d, %r, path=%r)
print(json.dumps([lim.wait() for _ in range(%d)]))"""

def max_in_window(ts, window):
    ts = sorted(ts)
    return max(sum(1 for u in ts if t <= u < t + window) for t in ts)

def run_two(cap, window, n_each, path):
    code = CHILD % (ROOT, cap, window, path, n_each)
    ps = [subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True) for _ in range(2)]
    outs = [json.loads(p.communicate(timeout=300)[0]) for p in ps]
    assert all(p.returncode == 0 for p in ps)
    return outs

class HostLimiterTest(unittest.TestCase):
    def test_two_processes_share_budget_scaled(self):
        """5 per 2 s (the 5/60 s rule, time-scaled 30x): 2 processes x 8 requests; no 2 s window holds more than 5 starts."""
        with tempfile.TemporaryDirectory() as d:
            t0 = time.time(); a, b = run_two(5, 2.0, 8, os.path.join(d, "hs.lock")); el = time.time() - t0
        allts = a + b
        self.assertEqual(len(allts), 16)
        self.assertLessEqual(max_in_window(allts, 2.0), 5)
        self.assertEqual((len(a), len(b)), (8, 8))
        self.assertGreaterEqual(max(allts) - min(allts), 6.0)   # 16 starts at 5/2 s need >= 3 full windows
        print(f"\n  two procs: 16 starts in {el:.1f}s, max per 2s window = {max_in_window(allts, 2.0)}")

    def test_two_processes_share_budget_real_window(self):
        """Real parameters (5 per 60 s): 2 processes x 3 requests. The first 5 starts go through, the 6th waits for the window."""
        if os.environ.get("HOSTLIMIT_SLOW") != "1": self.skipTest("set HOSTLIMIT_SLOW=1 (takes ~60 s)")
        with tempfile.TemporaryDirectory() as d:
            a, b = run_two(5, 60.0, 3, os.path.join(d, "hs.lock"))
        allts = sorted(a + b)
        self.assertLessEqual(max_in_window(allts, 60.0), 5)
        self.assertGreaterEqual(allts[5] - allts[0], 60.0)
        print(f"\n  real window: 6th start {allts[5] - allts[0]:.2f}s after the 1st; max per 60s = {max_in_window(allts, 60.0)}")

    def test_sixth_request_waits_full_window_fake_clock(self):
        clock = [1000.0]; slept = []
        def sleep(s): slept.append(s); clock[0] += s
        with tempfile.TemporaryDirectory() as d:
            lim = HostLimiter(5, 60.0, path=os.path.join(d, "x.lock"), _clock=lambda: clock[0], _sleep=sleep)
            starts = [lim.wait() for _ in range(5)]
            self.assertEqual(slept, [])
            sixth = lim.wait()
        self.assertGreaterEqual(sixth - starts[0], 60.0)
        self.assertEqual(max_in_window(starts + [sixth], 60.0), 5)

    def test_hypersync_sources_use_host_limiter(self):
        from cryptopnl.sources import HyperSyncWalletLogs, HyperSyncContractLogs
        HyperSyncWalletLogs("https://example.invalid"); HyperSyncContractLogs("https://example.invalid", "x", [], [])
        self.assertIsInstance(HyperSyncWalletLogs._lim, HostLimiter)
        self.assertEqual(HyperSyncWalletLogs._lim.cap, 5); self.assertEqual(HyperSyncWalletLogs._lim.window, 60.0)

if __name__ == "__main__": unittest.main()
