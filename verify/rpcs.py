# Compare free public Base RPCs: archive eth_call + getLogs range (GHST Transfer). Read-only, light.
import json,time,urllib.request
G="0xcD2F22236DD9Dfe2356D7C543161D4d260FD9BcB";TR="0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
def rpc(u,m,p):
  r=urllib.request.Request(u,json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),{"content-type":"application/json","user-agent":"p0"})
  t=time.time()
  try: d=json.load(urllib.request.urlopen(r,timeout=30))
  except urllib.error.HTTPError as e: d={"error":{"http":e.code,"b":e.read()[:100].decode(errors="replace")}}
  except Exception as e: d={"error":type(e).__name__}
  return d,round(time.time()-t,2)
for u in ["https://mainnet.base.org","https://base.llamarpc.com","https://base-rpc.publicnode.com","https://base.drpc.org"]:
  print("==",u); d,_=rpc(u,"eth_blockNumber",[])
  if "result" not in d: print(" head FAIL",str(d)[:150]); continue
  h=int(d["result"],16)
  for b in [3000000,10000000]:
    d,t=rpc(u,"eth_call",[{"to":G,"data":"0x18160ddd"},hex(b)]); print(" eth_call@%d"%b,"ok" if "result" in d else str(d.get("error"))[:120],t)
  for rng in [1000,5000,10000,50000,100000]:
    d,t=rpc(u,"eth_getLogs",[{"fromBlock":hex(h-100-rng),"toBlock":hex(h-100),"address":G,"topics":[TR]}])
    print(" getLogs %d"%rng,("ok n=%d"%len(d["result"])) if "result" in d else str(d.get("error"))[:140],t); time.sleep(1)
