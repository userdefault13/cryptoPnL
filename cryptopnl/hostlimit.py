"""Host-level HyperSync limiter (P3 step 1, KNOWN_GAPS #14). One budget for every process on the host.

flock(2) on a fixed lock file guards a shared sliding-window log (wall-clock start times of the last requests). A caller may start a
request only if fewer than `cap` starts fall in the last `window` seconds; otherwise it releases the lock, sleeps until the oldest start
leaves the window, and tries again. So across all processes using the same lock path, no `window`-second span ever holds more than `cap`
request starts (retries included: net.post_json calls wait() before every attempt). Default: HYPERSYNC_RPM (5) per 60 s.
Paths: HYPERSYNC_LOCK_PATH (default ~/.cache/cryptopnl/hypersync.lock); the window log is <lock>.log next to it."""
import fcntl, os, sys, time

DEFAULT_LOCK = os.path.join(os.path.expanduser("~"), ".cache", "cryptopnl", "hypersync.lock")

class HostLimiter:
    def __init__(self, cap, window=60.0, path=None, _clock=time.time, _sleep=time.sleep, margin=1.0, min_gap=0.0):
        # margin: the gate uses window+margin so jitter between the gate and the request log can never let a 60 s span
        # (as audited by scripts/reqlog_summary.py) hold cap+1 starts (2026-10-23 rerun: busiest window 6).
        self.cap, self.window, self.margin, self.min_gap = int(cap), float(window), float(margin), float(min_gap)
        # min_gap: minimum seconds between any two attempt starts on the host (architect 429 rule, ENVIO_TOKEN_INDEXER.md v1.1)
        self.path = path or os.environ.get("HYPERSYNC_LOCK_PATH") or DEFAULT_LOCK
        self.log = self.path + ".log"; self.cool = self.path + ".cool"; self._clock, self._sleep = _clock, _sleep
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        if self.cap < 1: raise ValueError("cap must be >= 1")

    def _try(self):
        """Under the exclusive lock: record a start and return (0, start_ts), or return (seconds to wait, None)."""
        with open(self.path, "a+") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            try:
                now = self._clock()
                nb = self._cool()
                if now < nb: return max(0.01, nb - now), None      # host-wide 429 back-off: nobody starts until it ends
                try:
                    with open(self.log) as f: ts = [float(x) for x in f.read().split()]
                except FileNotFoundError: ts = []
                if ts and now < max(ts): return max(0.01, max(ts) - now), None   # clock stepped back: wait, never squeeze in
                if ts and now < max(ts) + self.min_gap: return max(0.01, max(ts) + self.min_gap - now), None   # 12 s gap
                ts = [t for t in ts if t > now - self.window - self.margin]   # starts still inside the window
                if len(ts) < self.cap:
                    ts.append(now); tmp = f"{self.log}.{os.getpid()}"
                    with open(tmp, "w") as f: f.write("\n".join(f"{t:.6f}" for t in ts)); f.flush(); os.fsync(f.fileno())
                    os.replace(tmp, self.log); return 0.0, now
                return max(0.01, min(ts) + self.window + self.margin - now), None
            finally:
                fcntl.flock(lk, fcntl.LOCK_UN)

    def _cool(self):
        try:
            with open(self.cool) as f: return float(f.read().strip() or 0)
        except (FileNotFoundError, ValueError): return 0.0

    def backoff(self, seconds):
        """After a 429/5xx: push the host-wide not-before time out by `seconds` (never pulls it in). Uses no slot; the
        retry still goes through wait() and takes its own slot inside the sliding window."""
        if float(seconds) > 300: print(f"hostlimit WARNING: Retry-After/back-off {float(seconds):g}s > 300s", file=sys.stderr)
        with open(self.path, "a+") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            try:
                nb = max(self._cool(), self._clock() + float(seconds)); tmp = f"{self.cool}.{os.getpid()}"
                with open(tmp, "w") as f: f.write(f"{nb:.6f}"); f.flush(); os.fsync(f.fileno())
                os.replace(tmp, self.cool)
            finally:
                fcntl.flock(lk, fcntl.LOCK_UN)

    def wait(self):
        """Block until a start slot is free; returns the recorded start time (wall clock, as stored in the shared log)."""
        while True:
            d, t = self._try()
            if t is not None: return t
            self._sleep(d + 0.01)

_HS = None
def hypersync_limiter():
    """The process-wide handle on the host HyperSync budget (HYPERSYNC_RPM per 60 s, shared via the lock file)."""
    global _HS
    if _HS is None:
        from .config import HYPERSYNC_RPM, HYPERSYNC_MIN_GAP_S
        _HS = HostLimiter(HYPERSYNC_RPM, 60.0, min_gap=HYPERSYNC_MIN_GAP_S)
    return _HS

_RPC = None
def rpc_limiter():
    """Host-wide budget for the free public Base RPC (base.drpc.org), same pattern as HyperSync: every attempt (retries included)
    takes a slot from one flock-guarded sliding window shared by all processes, plus a minimum gap between starts; 429/5xx back-off
    is host-wide (Retry-After in full). Own lock file (RPC_LOCK_PATH, default ~/.cache/cryptopnl/rpc.lock), separate from HyperSync."""
    global _RPC
    if _RPC is None:
        from .config import RPC_RPM, RPC_MIN_GAP_S, RPC_LOCK_PATH
        _RPC = HostLimiter(RPC_RPM, 60.0, path=RPC_LOCK_PATH, min_gap=RPC_MIN_GAP_S)
    return _RPC
