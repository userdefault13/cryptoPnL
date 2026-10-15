import json,urllib.request
P="https://aarcadeghst.com/api/subgraph/%s"
E=["ERC721Listing","ERC1155Listing","ERC1155Purchase","ERC721BuyOrder","ERC1155BuyOrder","ERC1155BuyOrderExecution","Auction","Bid","Auction_BidPlaced","Auction_BoughtNow","Auction_ItemClaimed"]
def q(u,s):
  r=urllib.request.Request(u,json.dumps({"query":s}).encode(),{"content-type":"application/json","user-agent":"p0"})
  resp=urllib.request.urlopen(r,timeout=20); h={k:v for k,v in resp.headers.items() if 'rate' in k.lower() or 'retry' in k.lower()}
  return json.load(resp),h
for sg in ["aavegotchi-gbm-baazaar-base","aavegotchi-core-base","aavegotchi-alchemica-base"]:
  d,h=q(P%sg,'{__schema{types{name kind fields{name}}}}'); print("==",sg,"headers",h)
  if 'errors' in d: print(d['errors'][:1]); continue
  for t in d['data']['__schema']['types']:
    if t['kind']!='OBJECT' or t['name'].startswith('_') or t['name'] in('Query','Subscription'): continue
    f=[x['name'] for x in t['fields'] or []]
    if t['name'] in E or sg.endswith('alchemica-base'):
      tx=[x for x in f if 'transaction' in x.lower() or x.lower() in('txhash','hash')]
      cur=[x for x in f if any(k in x.lower() for k in ['block','time','createdat'])]
      print(f"{t['name']}|tx:{tx}|cursor:{cur}")
