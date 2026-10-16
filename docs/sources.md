# docs/sources.md — AarcadeGh$t subgraph sources (P0, authenticated)

Endpoint: `POST https://aarcadeghst.com/api/subgraph/<name>` with `Authorization: Bearer $SUBGRAPH_API_KEY` (abra; never committed). Envio self-hosted, Hasura syntax (`limit`, `order_by`, `where`, `_gt`). Mutations are rejected (403 read_only).
All three names (`aavegotchi-core-base`, `aavegotchi-gbm-baazaar-base`, `aavegotchi-alchemica-base`) serve the same combined schema.

## _meta
```graphql
{ _meta { block { number } deployment hasIndexingErrors } }
```
```json
{"data": {"_meta": {"block": {"number": 52690739}, "deployment": "envio-self-hosted", "hasIndexingErrors": false}}}
```

## Entity map
| Entity | tx hash field | cursor (order_by) | sample rows |
|---|---|---|---|
| ERC721Listing | none | blockCreated | 1 |
| ERC1155Purchase | none | timeLastPurchased | 1 |
| ERC1155Listing | none | timeCreated | 1 |
| ERC721BuyOrder | none | createdAt | 1 |
| ERC1155BuyOrder | none | createdAt | 1 |
| ERC1155BuyOrderExecution | none | executedAt | 1 |
| Auction | none | createdAt | 1 |
| Bid | none | bidTime | 1 |
| Auction_BidPlaced | transaction_id | timestamp | 1 |
| Auction_BoughtNow | transaction_id | timestamp | 1 |
| Auction_ItemClaimed | transaction_id | timestamp | 1 |

Listings, purchases, buy orders, auctions and bids have **no tx hash**; only the GBM event entities (`Auction_*`) carry `transaction_id`. Join the others to chain data by block/timestamp + token/price, or source them from logs (HyperSync).

## Sample queries and responses

### ERC721Listing
```graphql
{ ERC721Listing(limit: 2, order_by: {blockCreated: desc_nulls_last}, where: {timePurchased: {_gt: "0"}}) { id category erc721TokenAddress tokenId seller buyer priceInWei blockCreated timeCreated timePurchased } }
```
```json
{
 "data": {
  "ERC721Listing": {
   "id": "79",
   "category": "0",
   "erc721TokenAddress": "0x0000000000000000000000000000000000000000",
   "tokenId": "0",
   "seller": "0x0000000000000000000000000000000000000000",
   "buyer": "0x7bcb24dd3ae2803b8ff1ac7314411460bc28b476",
   "priceInWei": "0",
   "blockCreated": "0",
   "timeCreated": "0",
   "timePurchased": "1777175827"
  }
 }
}
```

### ERC1155Purchase
```graphql
{ ERC1155Purchase(limit: 2, order_by: {timeLastPurchased: desc_nulls_last}) { id listingID erc1155TokenAddress erc1155TypeId seller buyer recipient priceInWei quantity timeLastPurchased } }
```
```json
{
 "data": {
  "ERC1155Purchase": {
   "id": "114_0xa9465d03ba38726277b3e478ac98aa063a0c8d0a_1753821061",
   "listingID": "114",
   "erc1155TokenAddress": "0xA99c4B08201F2913Db8D28e71d020c4298F29dBF",
   "erc1155TypeId": "40",
   "seller": "0xa2faa3405a734c04ae713aaa837e6cecc2caee9f",
   "buyer": "0xa9465d03ba38726277b3e478ac98aa063a0c8d0a",
   "recipient": "0xa9465d03ba38726277b3e478ac98aa063a0c8d0a",
   "priceInWei": "55000000000000000000",
   "quantity": "1",
   "timeLastPurchased": "1753821061"
  }
 }
}
```

### ERC1155Listing
```graphql
{ ERC1155Listing(limit: 2, order_by: {timeCreated: desc_nulls_last}) { id erc1155TokenAddress erc1155TypeId seller priceInWei quantity sold cancelled timeCreated timeLastPurchased } }
```
```json
{
 "data": {
  "ERC1155Listing": {
   "id": "5",
   "erc1155TokenAddress": "0x0000000000000000000000000000000000000000",
   "erc1155TypeId": "0",
   "seller": "0x0000000000000000000000000000000000000000",
   "priceInWei": "0",
   "quantity": "0",
   "sold": false,
   "cancelled": false,
   "timeCreated": "0",
   "timeLastPurchased": "0"
  }
 }
}
```

### ERC721BuyOrder
```graphql
{ ERC721BuyOrder(limit: 2, order_by: {createdAt: desc_nulls_last}) { id buyer seller erc721TokenAddress erc721TokenId priceInWei createdAt executedAt executedAtBlock canceled } }
```
```json
{
 "data": {
  "ERC721BuyOrder": {
   "id": "1",
   "buyer": "",
   "seller": null,
   "erc721TokenAddress": "",
   "erc721TokenId": "0",
   "priceInWei": "0",
   "createdAt": "0",
   "executedAt": null,
   "executedAtBlock": null,
   "canceled": true
  }
 }
}
```

### ERC1155BuyOrder
```graphql
{ ERC1155BuyOrder(limit: 2, order_by: {createdAt: desc_nulls_last}) { id buyer erc1155TokenAddress erc1155TokenId priceInWei quantity executedQuantity createdAt lastExecutedAt } }
```
```json
{
 "data": {
  "ERC1155BuyOrder": {
   "id": "2",
   "buyer": "0x3ca2e945a3bc25399c75f49e9e45d34d897c1041",
   "erc1155TokenAddress": "0xa99c4b08201f2913db8d28e71d020c4298f29dbf",
   "erc1155TokenId": "246",
   "priceInWei": "60000000000000000000",
   "quantity": "0",
   "executedQuantity": "1",
   "createdAt": "1754545851",
   "lastExecutedAt": "1754630155"
  }
 }
}
```

### ERC1155BuyOrderExecution
```graphql
{ ERC1155BuyOrderExecution(limit: 2, order_by: {executedAt: desc_nulls_last}) { id buyOrder_id buyer seller erc1155TokenId priceInWei executedQuantity executedAt } }
```
```json
{
 "data": {
  "ERC1155BuyOrderExecution": {
   "id": "2-33920404-66",
   "buyOrder_id": "2",
   "buyer": "0x3ca2e945a3bc25399c75f49e9e45d34d897c1041",
   "seller": "0xa2faa3405a734c04ae713aaa837e6cecc2caee9f",
   "erc1155TokenId": "246",
   "priceInWei": "60000000000000000000",
   "executedQuantity": "1",
   "executedAt": "1754630155"
  }
 }
}
```

### Auction
```graphql
{ Auction(limit: 2, order_by: {createdAt: desc_nulls_last}) { id contractAddress tokenId seller highestBid highestBidder totalBids createdAt endsAt claimed isBought } }
```
```json
{
 "data": {
  "Auction": {
   "id": "93",
   "contractAddress": "0x80320a0000c7a6a34086e2acad6915ff57ffda31",
   "tokenId": "0",
   "seller": null,
   "highestBid": "1100000000000000000",
   "highestBidder": "0xc86688ac87eecde601bc733c5622c62071b91376",
   "totalBids": "2",
   "createdAt": null,
   "endsAt": null,
   "claimed": true,
   "isBought": false
  }
 }
}
```

### Bid
```graphql
{ Bid(limit: 2, order_by: {bidTime: desc_nulls_last}) { id auctionID bidder amount bidTime outbid } }
```
```json
{
 "data": {
  "Bid": {
   "id": "108_0xa322f14c4e9628f5934420a6098a01e7c999e657_200000000000000000",
   "auctionID": "108",
   "bidder": "0xa322f14c4e9628f5934420a6098a01e7c999e657",
   "amount": "200000000000000000",
   "bidTime": "1753715765",
   "outbid": true
  }
 }
}
```

### Auction_BidPlaced
```graphql
{ Auction_BidPlaced(limit: 2, order_by: {timestamp: desc_nulls_last}) { id auctionId bidder bidAmount timestamp transaction_id emitter_id } }
```
```json
{
 "data": {
  "Auction_BidPlaced": {
   "id": "33463209-202",
   "auctionId": "108",
   "bidder": "0x9fe6d7d5e9c9e3bff91149fbf731b618cbce3375",
   "bidAmount": "210000000000000020",
   "timestamp": "1753715765",
   "transaction_id": "0xda76272b1823a71be9561bc4e11fb64b99a1c1b9d19254c6de1f827474e40301",
   "emitter": "0x9fe6d7d5e9c9e3bff91149fbf731b618cbce3375"
  }
 }
}
```

### Auction_BoughtNow
```graphql
{ Auction_BoughtNow(limit: 2, order_by: {timestamp: desc_nulls_last}) { id auctionId timestamp transaction_id } }
```
```json
{
 "data": {
  "Auction_BoughtNow": {
   "id": "42210865-396",
   "auctionId": "5637",
   "timestamp": "1771211077",
   "transaction_id": "0x271109cf41b7c4825b17f6940d5d1f67dd699214fa21dd01d87ced0830d885fd"
  }
 }
}
```

### Auction_ItemClaimed
```graphql
{ Auction_ItemClaimed(limit: 2, order_by: {timestamp: desc_nulls_last}) { id auctionId timestamp transaction_id } }
```
```json
{
 "data": {
  "Auction_ItemClaimed": {
   "id": "33466404-1690",
   "auctionId": "20",
   "timestamp": "1753722155",
   "transaction_id": "0xaee178bad63087b4b6e0673b83851277ebed56e4859c96b9a112477a593cc98b"
  }
 }
}
```

## Receipt resolution (base.drpc.org)
4/4 `transaction_id` values from Auction_* resolve to successful receipts whose block timestamp matches the event `timestamp`.

## S1b parity vs Goldsky (GBM auctions, 20 latest >1h old)
found in proxy 20/20, exact match on highestBid+totalBids 20/20.

## Rate limit (light)
47 sequential `_meta` requests at ~85/min: codes {200: 46, 429: 1}, first 429: 47, p50 latency 0.46s. Headers: none.

## Proxy quirks
Entities returned as a single object instead of a list (limit/offset not honoured as list): ['Auction', 'Auction_BidPlaced', 'Auction_BoughtNow', 'Auction_ItemClaimed', 'Bid', 'ERC1155BuyOrder', 'ERC1155BuyOrderExecution', 'ERC1155Listing', 'ERC1155Purchase', 'ERC721BuyOrder', 'ERC721Listing']. The proxy appears to return only the FIRST row as an object (limit ignored, aliases renamed to the entity name, `*_aggregate` not exposed). `order_by: desc` sorts NULLs first, so use `desc_nulls_last`. Paging by `order_by` cursor + `where: {CURSOR: {_lt: last}}` must be verified against this before P1.
