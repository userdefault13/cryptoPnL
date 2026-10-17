"""Host-level HyperSync limiter (P3 step 1, KNOWN_GAPS #14). One budget for every process on the host.

flock(2) on a fixed lock file guards a shared sliding-window log (wall-clock start times of the last requests). A caller may start a
request only if fewer than `cap` starts fall in the last `window` seconds; otherwise it releases the lock, sleeps until the oldest start
leaves the window, and tries again. So across all processes using the same lock path, no `window`-second span ever holds more than `cap`
request starts (retries included: net.post_json calls wait() before every attempt). Default: HYPERSYNC_RPM (5) per 60 s.
Paths: HYPERSYNC_LOCK_PATH (default ~/.cache/cryptopnl/hypersync.lock); the window log is <lock>.log next to it."""
import fcntl, os, time

DEFAULT_LOCK = os.path.join(os.path.expanduser("~"), ".cache", "cryptopnl", "hypersync.lock")

class HostLimiter:
    def __init__(self, cap, window=60.0, path=None, _clock=time.time, _sleep=time.sleep):
        self.cap, self.window = int(cap), float(window)
        self.path = path or os.environ.get("HYPERSYNC_LOCK_PATH") or DEFAULT_LOCK
        self.log = self.path + ".log"; self._clock, self._sleep = _clock, _sleep
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        if self.cap < 1: raise ValueError("cap must be >= 1")

    def _try(self):
        """Under the exclusive lock: record a start and return (0, start_ts), or return (seconds to wait, None)."""
        with open(self.path, "a+") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            try:
                now = self._clock()
                try:
                    with open(self.log) as f: ts = [float(x) for x in f.read().split()]
                except FileNotFoundError: ts = []
                ts = [t for t in ts if t > now - self.window]   # starts still inside the window
                if len(ts) < self.cap:
                    ts.append(now); tmp = f"{self.log}.{os.getpid()}"
                    with open(tmp, "w") as f: f.write("\n".join(f"{t:.6f}" for t in ts)); f.flush(); os.fsync(f.fileno())
                    os.replace(tmp, self.log); return 0.0, now
                return max(0.01, min(ts) + self.window - now), None
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
        from .config import HYPERSYNC_RPM
        _HS = HostLimiter(HYPERSYNC_RPM, 60.0)
    return _HS
