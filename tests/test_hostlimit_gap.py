"""Architect 429 rule (ENVIO_TOKEN_INDEXER.md v1.1): >= 12 s between HyperSync attempt starts host-wide, retries included,
on top of the 5 / 60 s sliding bucket; and a per-request outcome log (ts, host, endpoint, status, retry_after, attempt#)."""
import io, os, random, subprocess, sys, tempfile, unittest, urllib.error
from unittest import mock
from cryptopnl import net
from cryptopnl.hostlimit import HostLimiter
from tests.test_hostlimit_retry import Clock, busiest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class Gap(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.path = os.path.join(self.d, "hs.lock"); self.clk = Clock()
        self.reqlog = os.path.join(self.d, "req.log")
    def lim(self): return HostLimiter(5, 60.0, path=self.path, _clock=self.clk, _sleep=self.clk.sleep, min_gap=12.0)

    def test_gap_across_limiters_sharing_the_lock(self):
        a, b = self.lim(), self.lim(); got = []
        for i in range(20): got.append((a if i % 2 else b).wait()); self.clk.t += random.Random(i).uniform(0, 3)
        gaps = [y - x for x, y in zip(got, got[1:])]
        self.assertGreaterEqual(min(gaps), 12.0); self.assertLessEqual(busiest(got), 5)

    def test_gap_holds_for_retries_and_429s(self):
        lim = self.lim(); rnd = random.Random(3); clk = self.clk; ra = iter(["7", None, "0", None] * 50)
        def urlopen(req, timeout=None):
            clk.t += rnd.uniform(0.05, 2.0)
            if rnd.random() < 0.5:
                v = next(ra); raise urllib.error.HTTPError("u", 429, "x", {"Retry-After": v} if v else {}, io.BytesIO(b""))
            return io.BytesIO(b"{}")
        with mock.patch.dict(os.environ, {"NET_REQLOG": self.reqlog}), mock.patch.object(net.time, "time", clk), \
             mock.patch.object(net.urllib.request, "urlopen", urlopen):
            for _ in range(8):
                try: net.post_json("hypersync", lim, "https://base.hypersync.xyz/query", {}, retries=6, _sleep=clk.sleep)
                except RuntimeError: pass
        with open(self.reqlog) as f: rows = [l.split() for l in f]
        att = [float(r[0]) for r in rows if r[2] == "attempt"]; n429 = sum(1 for r in rows if "status=429" in r)
        self.assertGreater(n429, 0); self.assertGreaterEqual(min(y - x for x, y in zip(att, att[1:])), 12.0)
        self.assertLessEqual(busiest(att), 5)

    def test_gap_across_real_processes(self):
        code = ("import sys,time; sys.path.insert(0, %r); from cryptopnl.hostlimit import HostLimiter; "
                "L=HostLimiter(5,2.0,path=%r,min_gap=0.4,margin=0.0)\nfor _ in range(4): print(L.wait(), flush=True)") % (ROOT, self.path)
        ps = [subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True) for _ in range(3)]
        ts = sorted(float(x) for p in ps for x in p.communicate(timeout=60)[0].split())
        self.assertEqual(len(ts), 12); self.assertGreaterEqual(min(y - x for x, y in zip(ts, ts[1:])), 0.4 - 1e-6)

class OutcomeLog(unittest.TestCase):
    def test_fields_and_no_secrets(self):
        d = tempfile.mkdtemp(); log = os.path.join(d, "req.log"); clk = Clock(); n = [0]
        lim = HostLimiter(5, 60.0, path=os.path.join(d, "l"), _clock=clk, _sleep=clk.sleep, min_gap=12.0)
        def urlopen(req, timeout=None):
            n[0] += 1
            if n[0] == 1: raise urllib.error.HTTPError("u", 429, "x", {"Retry-After": "9"}, io.BytesIO(b""))
            return io.BytesIO(b"{}")
        with mock.patch.dict(os.environ, {"NET_REQLOG": log}), mock.patch.object(net.time, "time", clk), \
             mock.patch.object(net.urllib.request, "urlopen", urlopen):
            net.post_json("hypersync", lim, "https://base.hypersync.xyz/query?key=SECRETQ", {"q": 1},
                          {"Authorization": "Bearer SECRETTOKEN"}, _sleep=clk.sleep)
        with open(log) as f: txt = f.read()
        self.assertNotIn("SECRET", txt); self.assertNotIn("Bearer", txt)
        outs = [dict(kv.split("=", 1) for kv in l.split()[3:]) for l in txt.splitlines() if l.split()[2] == "outcome"]
        self.assertEqual([set(o) for o in outs], [{"host", "endpoint", "status", "retry_after", "attempt"}] * 2)
        self.assertEqual(outs[0], {"host": "base.hypersync.xyz", "endpoint": "/query", "status": "429", "retry_after": "9", "attempt": "1"})
        self.assertEqual(outs[1], {"host": "base.hypersync.xyz", "endpoint": "/query", "status": "200", "retry_after": "-", "attempt": "2"})
        att = [float(l.split()[0]) for l in txt.splitlines() if l.split()[2] == "attempt"]
        self.assertGreaterEqual(att[1] - att[0], 12.0)   # retry waited out Retry-After (9 s) and the 12 s gap
        for l in txt.splitlines(): float(l.split()[0])   # every line starts with a unix ts

    def test_summary_counts_attempts_only_and_429s(self):
        d = tempfile.mkdtemp(); log = os.path.join(d, "r.log")
        with open(log, "w") as f:
            f.write("100.0 hypersync attempt\n100.5 hypersync outcome host=h endpoint=/query status=429 retry_after=9 attempt=1\n"
                    "112.0 hypersync attempt\n112.4 hypersync outcome host=h endpoint=/query status=200 retry_after=- attempt=2\n")
        out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "reqlog_summary.py"), log, "hypersync", "0", "5"],
                             capture_output=True, text=True).stdout
        self.assertIn("requests=2", out); self.assertIn("429s=1", out); self.assertIn("busiest_60s_window=2", out)
        self.assertIn("status=429 retry_after=9 attempt=1", out)

class ReviewNits(unittest.TestCase):   # architect PR #5 review nits (2)-(4)
    def test_rpc_endpoint_redacted_and_json_error_logged(self):
        d = tempfile.mkdtemp(); log = os.path.join(d, "r.log"); clk = Clock(); n = [0]
        def urlopen(req, timeout=None):
            n[0] += 1
            return io.BytesIO(b"<html>" if n[0] == 1 else b"{}")
        lim = net.Limiter(1000, 10)
        with mock.patch.dict(os.environ, {"NET_REQLOG": log}), mock.patch.object(net.urllib.request, "urlopen", urlopen):
            net.post_json("rpc", lim, "https://rpc.example/v2/KEYINPATH", {}, _sleep=lambda s: None)
        with open(log) as f: txt = f.read()
        self.assertNotIn("KEYINPATH", txt); self.assertIn("host=rpc.example endpoint=<redacted>", txt)
        self.assertIn("status=200 retry_after=- attempt=1 err=JSONDecodeError", txt); self.assertIn("status=200 retry_after=- attempt=2\n", txt)

    def test_long_retry_after_warns(self):
        d = tempfile.mkdtemp(); clk = Clock(); lim = HostLimiter(5, 60.0, path=os.path.join(d, "l"), _clock=clk, _sleep=clk.sleep)
        with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            lim.backoff(301); self.assertIn("> 300s", err.getvalue())
            lim.backoff(300); self.assertEqual(err.getvalue().count("WARNING"), 1)

if __name__ == "__main__": unittest.main()
