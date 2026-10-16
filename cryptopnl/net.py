"""HTTP JSON with token-bucket rate limiting, exp. backoff + jitter on 429/5xx, and counters."""
import json, random, time, urllib.request, urllib.error
STATS = {}
class Limiter:
    def __init__(self, per_sec): self.interval = 1.0 / per_sec; self.next = 0.0
    def wait(self):
        now = time.monotonic()
        if now < self.next: time.sleep(self.next - now)
        self.next = max(now, self.next) + self.interval
def post_json(name, limiter, url, body, headers=None, retries=6, timeout=90):
    st = STATS.setdefault(name, {"requests": 0, "429": 0, "5xx": 0, "errors": 0})
    for attempt in range(retries):
        limiter.wait(); st["requests"] += 1
        req = urllib.request.Request(url, json.dumps(body).encode(),
              {"content-type": "application/json", "user-agent": "cryptoPnL/p1", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r: return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429: st["429"] += 1
            elif e.code >= 500: st["5xx"] += 1
            else: st["errors"] += 1; raise RuntimeError(f"{name} HTTP {e.code}: {e.read()[:200]!r}")
        except (urllib.error.URLError, TimeoutError) as e:
            st["errors"] += 1
        time.sleep(min(60, 2 ** attempt) + random.random())
    raise RuntimeError(f"{name}: retries exhausted")
