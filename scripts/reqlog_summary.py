"""Summarise NET_REQLOG for one source: per-minute counts (UTC minute buckets and America/Los_Angeles labels) and the
busiest sliding 60 s window. Usage: reqlog_summary.py <logfile> [source=hypersync] [since_unix_ts] [limit=5]"""
import sys, datetime, zoneinfo
f = sys.argv[1]; src = sys.argv[2] if len(sys.argv) > 2 else "hypersync"
since = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0; limit = int(sys.argv[4]) if len(sys.argv) > 4 else 5
rows = [l.split() for l in open(f)]
rows = [r for r in rows if r[1:2] == [src] and float(r[0]) >= since]
ts = sorted(float(r[0]) for r in rows if r[2:3] in (["attempt"], []))   # attempts only; outcome lines are separate
outs = [dict(kv.split("=", 1) for kv in r[3:]) for r in rows if r[2:3] == ["outcome"]]
la = zoneinfo.ZoneInfo("America/Los_Angeles"); per = {}
for t in ts:
    k = datetime.datetime.fromtimestamp(t, la).strftime("%Y-%m-%d %H:%M %Z"); per[k] = per.get(k, 0) + 1
best, j = (0, None), 0
for i, t in enumerate(ts):
    while ts[j] <= t - 60: j += 1
    if i - j + 1 > best[0]: best = (i - j + 1, t)
print(f"source={src} requests={len(ts)}")
st = {}
for o in outs: st[o.get("status")] = st.get(o.get("status"), 0) + 1
print("outcomes " + " ".join(f"status_{k}={v}" for k, v in sorted(st.items())) + f" 429s={st.get('429', 0)}")
for o in outs:
    if o.get("status") != "200": print(f"  non-200: status={o.get('status')} retry_after={o.get('retry_after')} attempt={o.get('attempt')} host={o.get('host')} endpoint={o.get('endpoint')}")
for k, n in per.items(): print(f"  {k}: {n}")
w = datetime.datetime.fromtimestamp(best[1], la).strftime("%H:%M:%S %Z") if best[1] else "-"
print(f"busiest_60s_window={best[0]} (ending {w}) limit={limit} -> {'OK' if best[0] <= limit else 'OVER'}")
sys.exit(0 if best[0] <= limit else 2)
