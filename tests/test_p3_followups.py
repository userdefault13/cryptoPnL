"""P3 follow-ups done in P4. (a) RPC/HTTP error text and the request log carry only the HTTP status and the JSON-RPC error code, never
the response body (net.py post_json, sources.RPC.call, pricing.Pricer._call). Synthetic responses; no network."""
import io, os, tempfile, unittest, urllib.error
from unittest import mock
from cryptopnl import net, sources, pricing
from cryptopnl.hostlimit import HostLimiter

SECRET = b"free plan, please upgrade; echo 0xFEEDFACE"
class NoBodyInErrors(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp(); self.log = os.path.join(d, "r.log")
        lim = HostLimiter(10_000, 60.0, path=os.path.join(d, "rpc.lock"), min_gap=0); lim.backoff = lambda s: None
        self.rpc = sources.RPC("https://base.drpc.org/KEY", limiter=lim)
        ps = [mock.patch.dict(os.environ, {"NET_REQLOG": self.log}),
              mock.patch.object(sources, "post_json", lambda *a, **k: net.post_json(*a, _sleep=lambda s: None, **k))]
        for p in ps: p.start()
        self.addCleanup(lambda: [p.stop() for p in ps])
    def http(self, code, body):
        def urlopen(req, timeout=None): raise urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(body))
        return mock.patch.object(net.urllib.request, "urlopen", urlopen)
    def ok(self, body):
        return mock.patch.object(net.urllib.request, "urlopen", lambda req, timeout=None: io.BytesIO(body))
    def assertClean(self, text):
        for s in (b"free plan", b"0xFEEDFACE", b"invalid params", b"header not found", b"<html>"):
            self.assertNotIn(s.decode(), text)
    def log_text(self):
        with open(self.log) as f: return f.read()
    def test_408_exhausted_keeps_status_and_code_only(self):
        with self.http(408, b'{"jsonrpc":"2.0","id":1,"error":{"code":30,"message":"' + SECRET + b'"}}'):
            with self.assertRaises(RuntimeError) as cm: self.rpc.call("eth_blockNumber", [])
        self.assertEqual(str(cm.exception), "rpc HTTP 408 after 3 attempts (jsonrpc code 30)"); self.assertClean(self.log_text())
    def test_4xx_with_jsonrpc_body(self):
        with self.http(400, b'{"error":{"code":-32602,"message":"invalid params ' + SECRET + b'"}}'):
            with self.assertRaises(RuntimeError) as cm: self.rpc.call("eth_call", [])
        self.assertEqual(str(cm.exception), "rpc HTTP 400 (jsonrpc code -32602)"); self.assertClean(str(cm.exception))
    def test_4xx_with_non_json_body(self):
        with self.http(403, b"<html>" + SECRET + b"</html>"):
            with self.assertRaises(RuntimeError) as cm: self.rpc.call("eth_call", [])
        self.assertEqual(str(cm.exception), "rpc HTTP 403 (jsonrpc code -)")
    def test_http200_jsonrpc_error(self):
        with self.ok(b'{"jsonrpc":"2.0","id":1,"error":{"code":-32000,"message":"header not found ' + SECRET + b'","data":"0xFEEDFACE"}}'):
            with self.assertRaises(sources.RPCError) as cm: self.rpc.call("eth_call", [])
        e = cm.exception
        self.assertEqual((str(e), e.code, e.reverted), ("rpc eth_call: jsonrpc code -32000", -32000, False)); self.assertClean(str(e))
    def test_revert_still_detected_without_the_body(self):
        with self.ok(b'{"jsonrpc":"2.0","id":1,"error":{"code":3,"message":"execution reverted: ' + SECRET + b'","data":"0x08c379a0"}}'):
            with self.assertRaises(sources.RPCError) as cm: self.rpc.call("eth_call", [])
        self.assertEqual((str(cm.exception), cm.exception.reverted), ("rpc eth_call: jsonrpc code 3; execution reverted", True))
        self.assertClean(str(cm.exception))
    def test_pricer_rpc_errors_store_no_body(self):
        with self.ok(b'{"jsonrpc":"2.0","id":1,"error":{"code":-32000,"message":"header not found ' + SECRET + b'"}}'):
            pr = pricing.Pricer(8453, self.rpc, None, swaps={})
            self.assertIsNone(pr._call("0x" + "11" * 20, "0x0902f1ac", 30_000_000))
        self.assertEqual(pr.rpc_errors, [{"to": "0x" + "11" * 20, "selector": "0x0902f1ac", "block": 30_000_000, "error": "rpc eth_call: jsonrpc code -32000"}])
    def test_jsonrpc_code_parser(self):
        self.assertEqual([net.jsonrpc_code(b) for b in (b'{"error":{"code":30}}', b'{"error":{"code":"30"}}', b"oops", b"", None, b'{"error":true}')],
                         [30, None, None, None, None, None])
