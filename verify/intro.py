import json,urllib.request
G="https://api.goldsky.com/api/public/project_cmh3flagm0001r4p25foufjtt/subgraphs/%s/prod/gn"
want={"aavegotchi-core-base":["ERC721Listing","ERC1155Listing","ERC1155Purchase","ERC721BuyOrder","ERC1155BuyOrder","ERC1155BuyOrderExecution"],
"aavegotchi-gbm-baazaar-base":["Auction","Bid","AuctionBidPlaced","AuctionBoughtNow","AuctionItemClaimed","Transaction"]}
def q(u,s):
  r=urllib.request.Request(u,json.dumps({"query":s}).encode(),{"content-type":"application/json","user-agent":"p0"})
  return json.load(urllib.request.urlopen(r,timeout=20))
for sg,ents in want.items():
  for e in ents:
    d=q(G%sg,'{__type(name:"%s"){fields{name type{name kind ofType{name}}}}}'%e)['data']['__type']
    if not d: print(sg,e,"MISSING");continue
    f=[x['name'] for x in d['fields']]
    tx=[x for x in f if 'transaction' in x.lower() or 'hash' in x.lower()]
    cur=[x for x in f if any(k in x.lower() for k in ['block','time','createdat'])]
    print(f"{sg}|{e}|tx:{tx}|cursor:{cur}")
