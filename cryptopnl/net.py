"""HTTP JSON with token-bucket rate limiting (rate + burst), Retry-After / exp. backoff + jitter on 429/5xx,
and per-source counters incl. effective throughput."""
import http.client, json, os, random, ssl, time, urllib.parse, urllib.request, urllib.error
STATS = {}
_T0 = {}
# NOTE: this limiter is PER PROCESS (used for RPC). HyperSync uses hostlimit.HostLimiter: one flock-guarded 5/min budget per host.
class Limiter:
    def __init__(self, per_sec, burst=1):
        self.rate = per_sec; self.cap = float(burst); self.tokens = float(burst); self.t = time.monotonic()
    def wait(self):
        while True:
            now = time.monotonic(); self.tokens = min(self.cap, self.tokens + (now - self.t) * self.rate); self.t = now
            if self.tokens >= 1: self.tokens -= 1; return
            time.sleep((1 - self.tokens) / self.rate)
def _retry_after(e):
    v = e.headers.get("Retry-After") if e.headers else None
    try: return min(120.0, float(v)) if v else None
    except ValueError: return None
def permanent(e):
    """Errors that retrying cannot fix: TLS certificate/handshake failures (except a mid-stream EOF), bad URLs.
    URLError wraps the real cause in .reason."""
    r = getattr(e, "reason", None) if isinstance(e, urllib.error.URLError) else e
    if isinstance(r, ssl.SSLError) and not isinstance(r, (ssl.SSLEOFError, ssl.SSLZeroReturnError)): return True
    if isinstance(r, json.JSONDecodeError): return False   # HTML challenge/error page instead of JSON: transient
    return isinstance(r, (ssl.CertificateError, http.client.InvalidURL, ValueError))
def _reqlog(name, outcome, ts=None):
    """Host-wide request log (NET_REQLOG=path): one line per HTTP attempt, '<unix_ts> <source> <outcome>'. Used to cite
    HyperSync per-minute counts across processes (scripts/reqlog_summary.py)."""
    f = os.environ.get("NET_REQLOG")
    if f:
        with open(f, "a") as fh: fh.write(f"{(ts if ts is not None else time.time()):.3f} {name} {outcome}\n")
def _outlog(name, url, attempt, status, retry_after, err=None):
    """Per-request outcome line (architect 429 rule): '<unix_ts> <source> outcome host=<h> endpoint=<path> status=<s>
    retry_after=<v|-> attempt=<n>'. Host and path only: no query string, headers, body or token ever reach the log."""
    f = os.environ.get("NET_REQLOG")
    if not f: return
    u = urllib.parse.urlsplit(url); ra = "-" if retry_after is None else f"{retry_after:g}"
    ep = (u.path or "/") if name == "hypersync" else "<redacted>"   # RPC URLs can carry a key in the path: host only
    with open(f, "a") as fh:
        fh.write(f"{time.time():.3f} {name} outcome host={u.hostname or '-'} endpoint={ep} status={status} retry_after={ra} attempt={attempt}"
                 + (f" err={err}" if err else "") + "\n")
def post_json(name, limiter, url, body, headers=None, retries=6, timeout=90, _sleep=time.sleep):
    st = STATS.setdefault(name, {"requests": 0, "ok": 0, "429": 0, "5xx": 0, "errors": 0, "retry_after_honored": 0})
    _T0.setdefault(name, time.monotonic())
    for attempt in range(retries):
        t = limiter.wait(); st["requests"] += 1
        _reqlog(name, "attempt", t if isinstance(t, float) else None)   # host limiter: log the gate's own start time
        req = urllib.request.Request(url, json.dumps(body).encode(),
              {"content-type": "application/json", "user-agent": "cryptoPnL/p1", **(headers or {})})
        delay = None
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                out = json.load(r); st["ok"] += 1; _rate(name); _outlog(name, url, attempt + 1, getattr(r, "status", 200) or 200, None); return out
        except urllib.error.HTTPError as e:
            if e.code == 429: st["429"] += 1
            elif e.code >= 500: st["5xx"] += 1
            else: st["errors"] += 1; _outlog(name, url, attempt + 1, e.code, None); raise RuntimeError(f"{name} HTTP {e.code}: {e.read()[:200]!r}")
            delay = _retry_after(e); _outlog(name, url, attempt + 1, e.code, delay)
            if delay is not None: st["retry_after_honored"] += 1
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException, OSError, ValueError) as e:
            if isinstance(e, json.JSONDecodeError): _outlog(name, url, attempt + 1, 200, None, err="JSONDecodeError")   # 200 with a non-JSON body
            else: _outlog(name, url, attempt + 1, type(getattr(e, "reason", e)).__name__, None)
            if permanent(e):   # e.g. SSLCertVerificationError: fail fast, never retry (architect, PR #3)
                st["errors"] += 1; st["permanent"] = st.get("permanent", 0) + 1
                raise RuntimeError(f"{name}: permanent error, not retried: {type(getattr(e, 'reason', e)).__name__}: {e}") from e
            # dropped/reset connections (ConnectionResetError, RemoteDisconnected, IncompleteRead, socket errors):
            # retry with exponential backoff + jitter, same as 5xx
            st["errors"] += 1; st["conn_retries"] = st.get("conn_retries", 0) + 1
        d = delay if delay is not None else min(60, 2 ** attempt) + random.random()
        if hasattr(limiter, "backoff"): limiter.backoff(d)   # host-wide hold-off for every process; uses no slot
        _sleep(d)
    raise RuntimeError(f"{name}: retries exhausted")
def _rate(name):
    el = max(1e-6, time.monotonic() - _T0[name]); st = STATS[name]
    st["elapsed_s"] = round(el, 1); st["effective_per_min"] = round(st["ok"] / el * 60, 2)
