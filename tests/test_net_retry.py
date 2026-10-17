"""post_json retries dropped connections with exponential backoff (offline; urlopen stubbed)."""
import http.client, io, json, unittest, urllib.request
from cryptopnl import net

class Lim:
    def wait(self): pass

class Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False

class TestConnRetry(unittest.TestCase):
    def setUp(self): self._u = urllib.request.urlopen
    def tearDown(self): urllib.request.urlopen = self._u
    def _run(self, errors):
        seq = list(errors); sleeps = []
        def fake(req, timeout=None):
            if seq: raise seq.pop(0)
            return Resp(json.dumps({"ok": 1}).encode())
        urllib.request.urlopen = fake
        out = net.post_json("t_%d" % id(errors), Lim(), "http://x", {}, _sleep=sleeps.append)
        return out, sleeps
    def test_connection_reset_then_success(self):
        out, sleeps = self._run([ConnectionResetError(54, "Connection reset by peer"),
                                 http.client.RemoteDisconnected("closed"), BrokenPipeError()])
        self.assertEqual(out, {"ok": 1})
        self.assertEqual(len(sleeps), 3)
        for i, s in enumerate(sleeps):           # exponential backoff 2^attempt + jitter [0,1)
            self.assertGreaterEqual(s, 2 ** i); self.assertLess(s, 2 ** i + 1)
    def test_gives_up_after_retries(self):
        urllib.request.urlopen = lambda req, timeout=None: (_ for _ in ()).throw(ConnectionResetError())
        with self.assertRaisesRegex(RuntimeError, "retries exhausted"):
            net.post_json("t_fail", Lim(), "http://x", {}, retries=3, _sleep=lambda s: None)

if __name__ == "__main__": unittest.main()
