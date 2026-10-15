import json,urllib.request,time,sys
U="https://base.hypersync.xyz/query"
TR="0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
SW3="0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
SWA="0xb3e2773606abfd36b5bd91394b3a54d1398336b65d7ef9fe2a8d1f58b1f7c2d7"  # aerodrome v2 Swap(address,address,uint,uint,uint,uint)
def count(addrs,topic,frm,maxreq=25):
  n=0;b=frm;reqs=0
  while reqs<maxreq:
    q={"from_block":b,"logs":[{"address":addrs,"topics":[[topic]]}],"field_selection":{"log":["block_number"]}}
    try:
      r=json.load(urllib.request.urlopen(urllib.request.Request(U,json.dumps(q).encode(),{"content-type":"application/json"}),timeout=60))
    except Exception as e: return ("ERR",str(e)[:200],n,b)
    reqs+=1
    for d in r.get("data",[]): n+=len(d.get("logs",[]) or [])
    b=r["next_block"]
    if b>=r.get("archive_height",0): return (n,b,reqs,"done")
    time.sleep(2.2)
  return (n,b,reqs,"partial")
args=json.loads(sys.argv[1]); print(count(*args))
