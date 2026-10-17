"""post_json retries dropped connections with exponential backoff (offline; urlopen stubbed)."""
import http.client, io, json, ssl, unittest, urllib.error, urllib.request
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

class TestPermanent(unittest.TestCase):
    """DESIGN v1.2 §8: permanent errors (SSL certificate failures) are not retried."""
    def setUp(self): self._u = urllib.request.urlopen
    def tearDown(self): urllib.request.urlopen = self._u
    def _calls(self, exc):
        n = []; sleeps = []
        def fake(req, timeout=None): n.append(1); raise exc
        urllib.request.urlopen = fake
        with self.assertRaisesRegex(RuntimeError, "permanent error, not retried"):
            net.post_json("p_%d" % id(exc), Lim(), "https://x", {}, _sleep=sleeps.append)
        return len(n), sleeps
    def test_ssl_cert_failure_wrapped_in_urlerror(self):
        e = urllib.error.URLError(ssl.SSLCertVerificationError(1, "certificate verify failed: self-signed certificate"))
        self.assertEqual(self._calls(e), (1, []))
    def test_ssl_cert_failure_raw(self):
        self.assertEqual(self._calls(ssl.SSLCertVerificationError(1, "certificate verify failed")), (1, []))
    def test_bad_url(self):
        self.assertEqual(self._calls(http.client.InvalidURL("nonnumeric port")), (1, []))
    def test_ssl_eof_is_transient(self):
        seq = [urllib.error.URLError(ssl.SSLEOFError(8, "EOF occurred in violation of protocol"))]; sleeps = []
        def fake(req, timeout=None):
            if seq: raise seq.pop(0)
            return Resp(json.dumps({"ok": 1}).encode())
        urllib.request.urlopen = fake
        self.assertEqual(net.post_json("p_eof", Lim(), "https://x", {}, _sleep=sleeps.append), {"ok": 1})
        self.assertEqual(len(sleeps), 1)

if __name__ == "__main__": unittest.main()
