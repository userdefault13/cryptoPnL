"""HTTP JSON with token-bucket rate limiting (rate + burst), Retry-After / exp. backoff + jitter on 429/5xx,
and per-source counters incl. effective throughput."""
import http.client, json, random, time, urllib.request, urllib.error
STATS = {}
_T0 = {}
# NOTE: this limiter is PER PROCESS. The HyperSync budget (7/min for the MBP) is per HOST/account: run only one
# ingest process at a time on a host (p1_test.sh is sequential), or put a shared host throttle in front.
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
def post_json(name, limiter, url, body, headers=None, retries=6, timeout=90, _sleep=time.sleep):
    st = STATS.setdefault(name, {"requests": 0, "ok": 0, "429": 0, "5xx": 0, "errors": 0, "retry_after_honored": 0})
    _T0.setdefault(name, time.monotonic())
    for attempt in range(retries):
        limiter.wait(); st["requests"] += 1
        req = urllib.request.Request(url, json.dumps(body).encode(),
              {"content-type": "application/json", "user-agent": "cryptoPnL/p1", **(headers or {})})
        delay = None
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                out = json.load(r); st["ok"] += 1; _rate(name); return out
        except urllib.error.HTTPError as e:
            if e.code == 429: st["429"] += 1
            elif e.code >= 500: st["5xx"] += 1
            else: st["errors"] += 1; raise RuntimeError(f"{name} HTTP {e.code}: {e.read()[:200]!r}")
            delay = _retry_after(e)
            if delay is not None: st["retry_after_honored"] += 1
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException, OSError):
            # dropped/reset connections (ConnectionResetError, RemoteDisconnected, IncompleteRead, socket errors):
            # retry with exponential backoff + jitter, same as 5xx
            st["errors"] += 1; st["conn_retries"] = st.get("conn_retries", 0) + 1
        _sleep(delay if delay is not None else min(60, 2 ** attempt) + random.random())
    raise RuntimeError(f"{name}: retries exhausted")
def _rate(name):
    el = max(1e-6, time.monotonic() - _T0[name]); st = STATS[name]
    st["elapsed_s"] = round(el, 1); st["effective_per_min"] = round(st["ok"] / el * 60, 2)
