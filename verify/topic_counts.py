# HyperSync hit count per marketplace topic0 on Base (8453), paced <= 7 req/min. Run: abra run cryptoPnL -k ENVIO_API_TOKEN -- .venv/bin/python verify/topic_counts.py
import json,os,sys,time,collections
sys.path.insert(0,".")
from cryptopnl.net import Limiter, post_json, STATS
T=[l.split()[0] for l in open("verify/marketplace_topics.txt") if l.strip()]
N={l.split()[0]:l.split()[1].split("(")[0] for l in open("verify/marketplace_topics.txt") if l.strip()}
A=["0xa99c4b08201f2913db8d28e71d020c4298f29dbf","0x80320a0000c7a6a34086e2acad6915ff57ffda31"]
lim=Limiter(7/60); H={"Authorization":"Bearer "+os.environ["ENVIO_API_TOKEN"]}
c=collections.Counter(); first={}; b=0; reqs=0; maxreq=int(os.environ.get("MAXREQ","14"))
while reqs<maxreq:
  r=post_json("hypersync",lim,"https://base.hypersync.xyz/query",{"from_block":b,"logs":[{"address":A,"topics":[T]}],"field_selection":{"log":["topic0","address","block_number"]}},H); reqs+=1
  for d in r.get("data",[]):
    for l in d.get("logs") or []:
      k=(l["address"].lower(),l["topic0"]); c[k]+=1; first.setdefault(k,l["block_number"])
  nb=r["next_block"]; done=nb>=r.get("archive_height",0)
  print(f"req {reqs} next_block {nb} done={done}",file=sys.stderr)
  if done or nb<=b: break
  b=nb
print(json.dumps({"scanned_to":b if not done else nb,"complete":done,"requests":reqs,"stats":STATS}))
for t in T:
  for a in A:
    if c[(a,t)] or True:
      pass
  tot=sum(v for (a,tt),v in c.items() if tt==t)
  where=[a[:10] for (a,tt),v in c.items() if tt==t]
  print(f"{N[t]:<24} {t[:12]}… hits={tot} emitters={where} first_block={min([first[k] for k in first if k[1]==t], default=None)}")
