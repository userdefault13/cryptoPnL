# Authenticated introspection via proxy. Run: abra run general -k SUBGRAPH_API_KEY -- python3 verify/auth_intro.py
import json,os,urllib.request
K=os.environ["SUBGRAPH_API_KEY"]; P="https://aarcadeghst.com/api/subgraph/%s"
def q(sg,s,v=None):
  r=urllib.request.Request(P%sg,json.dumps({"query":s,"variables":v or {}}).encode(),{"content-type":"application/json","authorization":"Bearer "+K,"user-agent":"cryptoPnL-p0"})
  try: resp=urllib.request.urlopen(r,timeout=30); return resp.status,json.load(resp),dict(resp.headers)
  except urllib.error.HTTPError as e: return e.code,e.read()[:300].decode(errors="replace"),dict(e.headers)
E=["ERC721Listing","ERC1155Listing","ERC1155Purchase","ERC721BuyOrder","ERC1155BuyOrder","ERC1155BuyOrderExecution","Auction","Bid","Auction_BidPlaced","Auction_BoughtNow","Auction_ItemClaimed"]
s,d,h=q("aavegotchi-core-base","{__schema{queryType{fields{name}} types{name kind fields{name type{kind name ofType{kind name}}}}}}")
print("status",s,"hdrs",{k:v for k,v in h.items() if any(x in k.lower() for x in("rate","retry","limit"))})
T={t["name"]:t for t in d["data"]["__schema"]["types"]}
qf=[f["name"] for f in d["data"]["__schema"]["queryType"]["fields"]]
print("query fields sample:",[x for x in qf if x.split("_by_pk")[0] in E][:30])
out={}
for e in E:
  if e not in T: print(e,"MISSING"); continue
  f=[(x["name"],(x["type"].get("name") or (x["type"].get("ofType") or {}).get("name"))) for x in T[e]["fields"]]
  out[e]=f; print(e, f)
json.dump(out,open("/tmp/fields.json","w"))
