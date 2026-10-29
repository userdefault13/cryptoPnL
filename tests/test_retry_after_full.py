"""Retry-After honoured in full (architect ruling on PR #5 at d7714d9): no 120 s cap, > 300 s warns, unparseable -> backoff."""
import io, os, tempfile, unittest, urllib.error
from unittest import mock
from cryptopnl import net
from cryptopnl.hostlimit import HostLimiter
from tests.test_hostlimit_retry import Clock

class RetryAfterFull(unittest.TestCase):
    def call(self, ra):
        d = tempfile.mkdtemp(); clk = Clock(); sleeps = []; n = [0]
        lim = HostLimiter(5, 60.0, path=os.path.join(d, "l"), _clock=clk, _sleep=clk.sleep, min_gap=12.0)
        def urlopen(req, timeout=None):
            n[0] += 1
            if n[0] == 1: raise urllib.error.HTTPError("u", 429, "x", {"Retry-After": ra}, io.BytesIO(b""))
            return io.BytesIO(b"{}")
        def sleep(s): sleeps.append(s); clk.sleep(s)
        with mock.patch.dict(os.environ, {"NET_REQLOG": os.path.join(d, "reqlog")}), \
             mock.patch.object(net.time, "time", clk), mock.patch.object(net.urllib.request, "urlopen", urlopen), \
             mock.patch.object(net.random, "random", lambda: 0.5), mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            t0 = clk.t; net.post_json("hypersync", lim, "https://base.hypersync.xyz/query", {}, _sleep=sleep)
        return sleeps, err.getvalue(), lim, clk.t - t0

    def test_large_retry_after_honoured_in_full_and_warns(self):
        sleeps, err, lim, el = self.call("600")
        self.assertEqual(sleeps, [600.0]); self.assertGreaterEqual(el, 600.0)
        self.assertIn("600s > 300s", err)

    def test_200s_honoured_in_full_no_warning(self):
        sleeps, err, _, _ = self.call("200"); self.assertEqual(sleeps, [200.0]); self.assertNotIn("hostlimit WARNING", err)

    def test_unparseable_falls_back_to_backoff(self):
        for ra in ("Wed, 21 Oct 2026 07:28:00 GMT", "soon", "inf", "-5", "nan"):
            with self.subTest(ra=ra):
                sleeps, err, _, _ = self.call(ra)
                self.assertEqual(sleeps, [1.5])   # attempt 0: 2**0 + random() (patched to 0.5)
                self.assertNotIn("hostlimit WARNING", err)

if __name__ == "__main__": unittest.main()
