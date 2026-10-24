"""429s and retries can never push a 60 s window above 5 (CoS/architect 2026-10-23: the 6-start Base window is a FAIL).
Fake clock; every HTTP attempt is logged through net._reqlog and audited the same way as scripts/reqlog_summary.py."""
import io, os, random, tempfile, unittest, urllib.error
from unittest import mock
from cryptopnl import net
from cryptopnl.hostlimit import HostLimiter

def busiest(ts, w=60.0):
    ts = sorted(ts); best = j = 0
    for i, t in enumerate(ts):
        while ts[j] <= t - w: j += 1
        best = max(best, i - j + 1)
    return best

class Clock:
    def __init__(self, t=1_000_000.0): self.t = t
    def __call__(self): return self.t
    def sleep(self, s): self.t += max(0.0, s)

class RetryWindow(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.reqlog = os.path.join(self.d, "req.log"); self.clk = Clock()
        self.lim = HostLimiter(5, 60.0, path=os.path.join(self.d, "hs.lock"), _clock=self.clk, _sleep=self.clk.sleep)

    def run_calls(self, n, p429, seed, retry_after=None):
        rnd = random.Random(seed); clk = self.clk
        def urlopen(req, timeout=None):
            clk.t += rnd.uniform(0.05, 3.0)                       # request latency
            if rnd.random() < p429:
                hdr = {"Retry-After": str(retry_after)} if retry_after is not None else {}
                raise urllib.error.HTTPError("u", 429, "Too Many", hdr, io.BytesIO(b""))
            return io.BytesIO(b"{}")
        with mock.patch.dict(os.environ, {"NET_REQLOG": self.reqlog}), mock.patch.object(net.time, "time", clk), \
             mock.patch.object(net.urllib.request, "urlopen", urlopen), mock.patch.object(net.random, "random", lambda: 0.5):
            for _ in range(n):
                try: net.post_json("hypersync", self.lim, "http://x", {}, retries=6, _sleep=clk.sleep)
                except RuntimeError: pass
                clk.t += rnd.uniform(0, 2)
        with open(self.reqlog) as f: return [float(l.split()[0]) for l in f if " hypersync attempt" in l]

    def test_no_429(self):
        ts = self.run_calls(30, 0.0, 1); self.assertEqual(len(ts), 30); self.assertLessEqual(busiest(ts), 5)

    def test_429_storms_never_exceed_5(self):
        for seed in range(25):
            for p in (0.2, 0.5, 0.9):
                with self.subTest(seed=seed, p=p):
                    self.setUp(); ts = self.run_calls(12, p, seed)
                    self.assertGreater(len(ts), 12 if p >= 0.5 else 0); self.assertLessEqual(busiest(ts), 5)

    def test_retry_after_honoured_and_held_host_wide(self):
        ts = self.run_calls(10, 0.5, 7, retry_after=30); self.assertLessEqual(busiest(ts), 5)
        self.assertGreaterEqual(self.lim._cool(), 0.0)

    def test_backoff_blocks_other_processes_without_using_a_slot(self):
        other = HostLimiter(5, 60.0, path=self.lim.path, _clock=self.clk, _sleep=self.clk.sleep)
        t0 = self.clk.t; self.lim.backoff(20.0)
        self.assertGreaterEqual(other.wait(), t0 + 20.0)          # a second limiter on the same lock waits out the back-off
        with open(self.lim.log) as f: self.assertEqual(len(f.read().split()), 1)   # only the real start took a slot

    def test_replay_2026_10_23_base_window(self):
        # Attempt times from logs/net_requests_p2_2.log (Base P2.2 pass, 2026-10-23); the 10th made the window 6.
        T = [29.746, 31.197, 32.539, 33.639, 39.931, 89.762, 91.530, 92.904, 94.579, 96.638]
        got = []
        for t in T: self.clk.t = max(self.clk.t, 1_000_000.0 + t); got.append(self.lim.wait())
        self.assertLessEqual(busiest(got), 5)

    def test_clock_step_back_does_not_squeeze_in(self):
        got = [self.lim.wait() for _ in range(5)]
        self.clk.t -= 30; got += [self.lim.wait() for _ in range(5)]
        self.assertLessEqual(busiest(got), 5); self.assertGreaterEqual(got[5], got[4])

if __name__ == "__main__": unittest.main()
