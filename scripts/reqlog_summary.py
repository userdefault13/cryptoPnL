"""Summarise NET_REQLOG for one source: per-minute counts (UTC minute buckets and America/Los_Angeles labels) and the
busiest sliding 60 s window. Usage: reqlog_summary.py <logfile> [source=hypersync] [since_unix_ts] [limit=7]"""
import sys, datetime, zoneinfo
f = sys.argv[1]; src = sys.argv[2] if len(sys.argv) > 2 else "hypersync"
since = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0; limit = int(sys.argv[4]) if len(sys.argv) > 4 else 7
ts = sorted(float(l.split()[0]) for l in open(f) if l.split()[1:2] == [src] and float(l.split()[0]) >= since)
la = zoneinfo.ZoneInfo("America/Los_Angeles"); per = {}
for t in ts:
    k = datetime.datetime.fromtimestamp(t, la).strftime("%Y-%m-%d %H:%M %Z"); per[k] = per.get(k, 0) + 1
best, j = (0, None), 0
for i, t in enumerate(ts):
    while ts[j] <= t - 60: j += 1
    if i - j + 1 > best[0]: best = (i - j + 1, t)
print(f"source={src} requests={len(ts)}")
for k, n in per.items(): print(f"  {k}: {n}")
w = datetime.datetime.fromtimestamp(best[1], la).strftime("%H:%M:%S %Z") if best[1] else "-"
print(f"busiest_60s_window={best[0]} (ending {w}) limit={limit} -> {'OK' if best[0] <= limit else 'OVER'}")
sys.exit(0 if best[0] <= limit else 2)
