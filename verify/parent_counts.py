# P1.1 prep (read-only): HyperSync counts of Aavegotchi TransferToParent/TransferFromParent. <=5 req/min.
# Run: abra run cryptoPnL -k ENVIO_API_TOKEN -- .venv/bin/python verify/parent_counts.py <chain> <maxreq> <contract>...
import json,os,sys,collections
sys.path.insert(0,".")
from cryptopnl.net import Limiter, post_json, STATS
TP={"0xe82810099d182b25e23e895715954d6e7b41867a02e2c693cce68a8f250e43d3":"TransferToParent","0x4b287e36a0531da8ccee303de127c778302f48d8fc9569b1fe1dcb9d64465c6d":"TransferFromParent"}
chain=int(sys.argv[1]); maxreq=int(sys.argv[2]); A=[a.lower() for a in sys.argv[3:]]
U={8453:"https://base.hypersync.xyz/query",84532:"https://base-sepolia.hypersync.xyz/query"}[chain]
lim=Limiter(5/60); H={"Authorization":"Bearer "+os.environ["ENVIO_API_TOKEN"]}
c=collections.Counter(); first={}; b=0; reqs=0; done=False
while reqs<maxreq:
  r=post_json("hypersync",lim,U,{"from_block":b,"logs":[{"address":A,"topics":[list(TP)]}],"field_selection":{"log":["topic0","address","block_number"]}},H); reqs+=1
  for d in r.get("data",[]):
    for l in d.get("logs") or []:
      k=(l["address"].lower(),TP[l["topic0"]]); c[k]+=1; first.setdefault(k,l["block_number"])
  nb=r["next_block"]; done=nb>=r.get("archive_height",0)
  if done or nb<=b: break
  b=nb
print(json.dumps({"chain":chain,"scanned_to":nb,"complete":done,"requests":reqs,"counts":{f"{a}:{e}":v for (a,e),v in c.items()},"first_block":{f"{a}:{e}":v for (a,e),v in first.items()},"stats":STATS}))
