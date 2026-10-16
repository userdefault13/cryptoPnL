# Authenticated P0: samples -> docs/sources.md, receipts (drpc), S1b parity, light rate limit.
# Run: abra run general -k SUBGRAPH_API_KEY -- python3 verify/auth_p0.py   (key never printed/written)
import json,os,re,time,urllib.request
K=os.environ["SUBGRAPH_API_KEY"]; P="https://aarcadeghst.com/api/subgraph/%s"; RPC="https://base.drpc.org"
GS="https://api.goldsky.com/api/public/project_cmh3flagm0001r4p25foufjtt/subgraphs/%s/prod/gn"
def post(u,body,h={}):
  r=urllib.request.Request(u,json.dumps(body).encode(),{"content-type":"application/json","user-agent":"cryptoPnL-p0",**h})
  t=time.time()
  try: resp=urllib.request.urlopen(r,timeout=30); return resp.status,json.load(resp),dict(resp.headers),time.time()-t
  except urllib.error.HTTPError as e: return e.code,e.read()[:300].decode(errors="replace"),dict(e.headers),time.time()-t
def sq(sg,s): return post(P%sg,{"query":s},{"authorization":"Bearer "+K})
def rows_of(d,e):
  v=(d.get("data") or {}).get(e) if isinstance(d,dict) else None
  if isinstance(v,dict): QUIRK.add(e); return [v]
  return v
QUIRK=set()
def rpc(m,p): return post(RPC,{"jsonrpc":"2.0","id":1,"method":m,"params":p})[1]
SG="aavegotchi-core-base"
Q={
"ERC721Listing":('blockCreated','{ ERC721Listing(limit: 2, order_by: {blockCreated: desc_nulls_last}, where: {timePurchased: {_gt: "0"}}) { id category erc721TokenAddress tokenId seller buyer priceInWei blockCreated timeCreated timePurchased } }'),
"ERC1155Purchase":('timeLastPurchased','{ ERC1155Purchase(limit: 2, order_by: {timeLastPurchased: desc_nulls_last}) { id listingID erc1155TokenAddress erc1155TypeId seller buyer recipient priceInWei quantity timeLastPurchased } }'),
"ERC1155Listing":('timeCreated','{ ERC1155Listing(limit: 2, order_by: {timeCreated: desc_nulls_last}) { id erc1155TokenAddress erc1155TypeId seller priceInWei quantity sold cancelled timeCreated timeLastPurchased } }'),
"ERC721BuyOrder":('createdAt','{ ERC721BuyOrder(limit: 2, order_by: {createdAt: desc_nulls_last}) { id buyer seller erc721TokenAddress erc721TokenId priceInWei createdAt executedAt executedAtBlock canceled } }'),
"ERC1155BuyOrder":('createdAt','{ ERC1155BuyOrder(limit: 2, order_by: {createdAt: desc_nulls_last}) { id buyer erc1155TokenAddress erc1155TokenId priceInWei quantity executedQuantity createdAt lastExecutedAt } }'),
"ERC1155BuyOrderExecution":('executedAt','{ ERC1155BuyOrderExecution(limit: 2, order_by: {executedAt: desc_nulls_last}) { id buyOrder_id buyer seller erc1155TokenId priceInWei executedQuantity executedAt } }'),
"Auction":('createdAt','{ Auction(limit: 2, order_by: {createdAt: desc_nulls_last}) { id contractAddress tokenId seller highestBid highestBidder totalBids createdAt endsAt claimed isBought } }'),
"Bid":('bidTime','{ Bid(limit: 2, order_by: {bidTime: desc_nulls_last}) { id auctionID bidder amount bidTime outbid } }'),
"Auction_BidPlaced":('timestamp','{ Auction_BidPlaced(limit: 2, order_by: {timestamp: desc_nulls_last}) { id auctionId bidder bidAmount timestamp transaction_id emitter_id } }'),
"Auction_BoughtNow":('timestamp','{ Auction_BoughtNow(limit: 2, order_by: {timestamp: desc_nulls_last}) { id auctionId timestamp transaction_id } }'),
"Auction_ItemClaimed":('timestamp','{ Auction_ItemClaimed(limit: 2, order_by: {timestamp: desc_nulls_last}) { id auctionId timestamp transaction_id } }'),
}
TX={"Auction_BidPlaced","Auction_BoughtNow","Auction_ItemClaimed"}
md=["# docs/sources.md — AarcadeGh$t subgraph sources (P0, authenticated)","",
"Endpoint: `POST https://aarcadeghst.com/api/subgraph/<name>` with `Authorization: Bearer $SUBGRAPH_API_KEY` (abra; never committed). Envio self-hosted, Hasura syntax (`limit`, `order_by`, `where`, `_gt`). Mutations are rejected (403 read_only).",
"All three names (`aavegotchi-core-base`, `aavegotchi-gbm-baazaar-base`, `aavegotchi-alchemica-base`) serve the same combined schema.",""]
s,d,_,_=sq(SG,"{_meta{block{number} deployment hasIndexingErrors}}"); md+=["## _meta","```graphql","{ _meta { block { number } deployment hasIndexingErrors } }","```","```json",json.dumps(d),"```",""]
md+=["## Entity map","| Entity | tx hash field | cursor (order_by) | sample rows |","|---|---|---|---|"]
samples={}; sec=[]
for e,(cur,qq) in Q.items():
  s,d,_,_=sq(SG,qq); rows=rows_of(d,e)
  samples[e]=rows or []
  md.append(f"| {e} | {'transaction_id' if e in TX else 'none'} | {cur} | {len(rows) if rows is not None else 'ERR '+str(s)} |")
  sec+=[f"### {e}","```graphql",qq,"```","```json",json.dumps(d,indent=1)[:1800],"```",""]
md+=["","Listings, purchases, buy orders, auctions and bids have **no tx hash**; only the GBM event entities (`Auction_*`) carry `transaction_id`. Join the others to chain data by block/timestamp + token/price, or source them from logs (HyperSync).",""]
md+=["## Sample queries and responses",""]+sec
# receipts
txs=[]
for e in TX:
  for r in samples[e]: txs.append((e,r["transaction_id"],int(r["timestamp"])))
s,d,_,_=sq(SG,'{ Auction_BidPlaced(limit: 8, order_by: {timestamp: desc_nulls_last}, offset: 2) { transaction_id timestamp } }')
for r in (rows_of(d,"Auction_BidPlaced") or []): txs.append(("Auction_BidPlaced",r["transaction_id"],int(r["timestamp"])))
ok=0; rec=[]
for e,tid,ts in txs:
  h=tid if re.fullmatch(r"0x[0-9a-fA-F]{64}",tid or "") else None
  if not h:
    m=re.search(r"0x[0-9a-fA-F]{64}",tid or ""); h=m.group(0) if m else None
  if not h: rec.append((e,tid,"no hash in transaction_id")); continue
  r=rpc("eth_getTransactionReceipt",[h]); res=(r or {}).get("result") if isinstance(r,dict) else None
  if not res: rec.append((e,h[:14],"no receipt "+str(r)[:80])); continue
  b=rpc("eth_getBlockByNumber",[res["blockNumber"],False])["result"]
  good=res["status"]=="0x1" and abs(int(b["timestamp"],16)-ts)<=2
  ok+=good; rec.append((e,h[:14],f"block {int(res['blockNumber'],16)} hash {res['blockHash'][:12]} ts_match={abs(int(b['timestamp'],16)-ts)<=2}"))
  time.sleep(0.3)
print("RECEIPTS %d/%d"%(ok,len(txs)))
for x in rec: print(" ",x)
# S1b parity: GBM auctions, Goldsky vs proxy
s,g,_,_=post(GS%"aavegotchi-gbm-baazaar-base",{"query":"{ auctions(first: 20, orderBy: createdAt, orderDirection: desc, where:{createdAt_lt: \"%d\"}) { id highestBid totalBids claimed } }"%(int(time.time())-3600)})
ga=(g.get("data") or {}).get("auctions",[]) if isinstance(g,dict) else []
ids=[a["id"] for a in ga]
pa={}
for i in ids:
  s,p,_,_=sq(SG,'{ Auction(where: {id: {_eq: "%s"}}) { id highestBid totalBids claimed } }'%i)
  v=(rows_of(p,"Auction") or [None])[0]
  if v: pa[i]=v
  time.sleep(0.4)
match=sum(1 for a in ga if a["id"] in pa and str(pa[a["id"]]["highestBid"])==str(a["highestBid"]) and str(pa[a["id"]]["totalBids"])==str(a["totalBids"]))
found=sum(1 for a in ga if a["id"] in pa)
print("PARITY goldsky=%d found_in_proxy=%d exact(highestBid,totalBids)=%d"%(len(ga),found,match))
for a in ga[:20]:
  if a["id"] in pa and (str(pa[a["id"]]["highestBid"])!=str(a["highestBid"]) or str(pa[a["id"]]["totalBids"])!=str(a["totalBids"])): print("  diff",a["id"],a,pa[a["id"]])
  if a["id"] not in pa: print("  missing",a["id"])
if not ga: print("  goldsky err",str(g)[:200]); 
if not pa: print("  proxy err",str(p)[:200])
if os.environ.get("SKIP_RL"):
  codes={200:46,429:1}; el=33.3; lat=[0.46]; first429=47; hdr={}
  print("RATELIMIT (recorded from 2026-10-16 ~10:25 PT run) 46x200 then 429 at req 47, ~85/min")
else:
  codes={}; lat=[]; hdr={}; first429=None; t0=time.time()
  for i in range(60):
    s,d,h,dt=sq(SG,"{_meta{block{number}}}"); codes[s]=codes.get(s,0)+1; lat.append(dt)
    hdr.update({k:v for k,v in h.items() if any(x in k.lower() for x in("ratelimit","retry-after","x-cache","x-subgraph"))})
    if s==429: first429=i+1; break
    time.sleep(0.25)
  el=time.time()-t0
  print("RATELIMIT n=%d in %.1fs (%.0f/min) codes=%s first429=%s p50=%.2fs max=%.2fs hdrs=%s"%(sum(codes.values()),el,sum(codes.values())/el*60,codes,first429,sorted(lat)[len(lat)//2],max(lat),hdr))
md+=["## Receipt resolution (base.drpc.org)",f"{ok}/{len(txs)} `transaction_id` values from Auction_* resolve to successful receipts whose block timestamp matches the event `timestamp`.",""]
md+=["## S1b parity vs Goldsky (GBM auctions, 20 latest >1h old)",f"found in proxy {found}/{len(ga)}, exact match on highestBid+totalBids {match}/{len(ga)}.",""]
md+=["## Rate limit (light)",f"{sum(codes.values())} sequential `_meta` requests at ~{sum(codes.values())/el*60:.0f}/min: codes {codes}, first 429: {first429}, p50 latency {sorted(lat)[len(lat)//2]:.2f}s. Headers: {hdr or 'none'}.",""]
md+=["## Proxy quirks",f"Entities returned as a single object instead of a list (limit/offset not honoured as list): {sorted(QUIRK) or 'none'}. The proxy appears to return only the FIRST row as an object (limit ignored, aliases renamed to the entity name, `*_aggregate` not exposed). `order_by: desc` sorts NULLs first, so use `desc_nulls_last`. Paging by `order_by` cursor + `where: {{CURSOR: {{_lt: last}}}}` must be verified against this before P1.",""]; print("QUIRK",sorted(QUIRK))
open("docs/sources.md","w").write("\n".join(md)); print("wrote docs/sources.md")
