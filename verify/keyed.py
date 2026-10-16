# Keyed P0 probes. Run: abra run cryptoPnL -- python3 verify/keyed.py   (never prints secret values)
import json,os,time,urllib.request
RPC=os.environ["BASE_RPC_URL"]; TOK=os.environ["ENVIO_API_TOKEN"]
GHST="0xcD2F22236DD9Dfe2356D7C543161D4d260FD9BcB"; GS="https://api.goldsky.com/api/public/project_cmh3flagm0001r4p25foufjtt/subgraphs/aavegotchi-gbm-baazaar-base/prod/gn"
TR="0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
def post(u,body,h={}):
  r=urllib.request.Request(u,json.dumps(body).encode(),{"content-type":"application/json","user-agent":"p0",**h})
  try:
    resp=urllib.request.urlopen(r,timeout=60); return resp.status,json.load(resp),dict(resp.headers)
  except urllib.error.HTTPError as e: return e.code,(e.read()[:200].decode(errors="replace")),dict(e.headers)
  except Exception as e: return None,type(e).__name__,{}
def rpc(m,p):
  s,d,_=post(RPC,{"jsonrpc":"2.0","id":1,"method":m,"params":p})
  return d if isinstance(d,dict) else {"error":{"http":s,"body":str(d)[:120]}}
_h=rpc("eth_blockNumber",[])
if "result" not in _h:
  print("KEYED RPC FAILED:",str(_h.get("error"))[:140],"-> falling back to public mainnet.base.org (archive/getLogs results below are for PUBLIC rpc)")
  RPC="https://mainnet.base.org"; _h=rpc("eth_blockNumber",[])
head=int(_h["result"],16); print("head",head)
# archive: GHST balanceOf(GHST contract itself) + totalSupply at old blocks
for blk in [3000000,10000000,head-1000]:
  r=rpc("eth_call",[{"to":GHST,"data":"0x18160ddd"},hex(blk)])
  print("archive eth_call totalSupply @",blk,"ok" if "result" in r else r.get("error"))
r=rpc("eth_getBalance",["0x4200000000000000000000000000000000000016",hex(1000)]); print("getBalance @1000","ok" if "result" in r else r.get("error"))
# getLogs ranges
for rng in [1000,2000,5000,10000,50000,100000,500000]:
  t=time.time(); r=rpc("eth_getLogs",[{"fromBlock":hex(head-rng-100),"toBlock":hex(head-100),"address":GHST,"topics":[TR]}])
  print("getLogs GHST range",rng,("ok n=%d"%len(r["result"])) if "result" in r else str(r.get("error"))[:160],"%.1fs"%(time.time()-t)); time.sleep(0.5)
# S1 sample tx hashes from Goldsky GBM
s,d,_=post(GS,{"query":"{ transactions(first:10, orderBy:blockNumber, orderDirection:desc){ id blockNumber } }"})
txs=d.get("data",{}).get("transactions",[]) if isinstance(d,dict) else []
if not txs: print("goldsky tx sample failed",s,str(d)[:200])
ok=0
for t in txs:
  r=rpc("eth_getTransactionReceipt",[t["id"]]); res=r.get("result")
  good=bool(res) and int(res["blockNumber"],16)==int(t["blockNumber"])
  ok+=good; print("receipt",t["id"][:12],"blk",t["blockNumber"],"OK" if good else ("MISMATCH/none" if "result" in r else r.get("error")), (res or {}).get("blockHash","")[:12])
print("receipts resolved %d/%d"%(ok,len(txs)))
# HyperSync real query, ≤ ~25 req/min
HS="https://base.hypersync.xyz/query"; H={"Authorization":"Bearer "+TOK}
fb=head-200000; n=0; times=[]; codes=[]; rl={}
for i in range(5):
  t=time.time(); s,d,h=post(HS,{"from_block":fb,"to_block":head,"logs":[{"address":[GHST],"topics":[[TR]]}],"field_selection":{"log":["block_number","transaction_hash"]}},H)
  times.append(round(time.time()-t,2)); codes.append(s); rl.update({k:v for k,v in h.items() if "rate" in k.lower() or "retry" in k.lower()})
  if s==200 and isinstance(d,dict):
    n+=sum(len(x.get("logs") or []) for x in d.get("data",[])); fb=d["next_block"]
    if fb>=head: break
  else: print("hypersync err",s,str(d)[:200]); break
  time.sleep(2.5)
print("hypersync GHST transfers last 200k blocks:",n,"reqs",len(codes),"codes",codes,"lat",times,"next_block",fb,"rl headers",rl)
s,d,h=post(HS,{"from_block":head-10,"traces":[{}],"field_selection":{"trace":["block_number"]}},H)
print("hypersync traces probe",s,str(d)[:160] if s!=200 else "ok rows=%d"%sum(len(x.get('traces') or []) for x in d.get('data',[])))
