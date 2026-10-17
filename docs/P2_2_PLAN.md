# P2.2 plan: Gotchiverse classification (DESIGN v1.3 §9)

Branch `p2.2-gotchiverse`, cut from origin/main bed74e9. Commits so far: 2884148 (cherry-pick of the P3 host HyperSync lock, so it lands
before any HyperSync call) and 7d36beb (architect's PR #4 doc nits). Spec: **DESIGN.md v1.3 §9**. It exists only at `/workspace/cryptoPnL/DESIGN.md`
on the box; the repo copy (v1.0) is not overwritten. v1.3 replaces v1.2 for P3 too (P3 is paused, see `p3-pricing` docs/P3_STATUS.md).
Scope = classification only. Prices at the craft/upgrade/refund blocks are P3. Basis carry, bundles and location holdings are P4.

## Facts gathered (read-only)
- Topics computed from the Gotchiverse/Aavegotchi ABIs (keccak of the signatures): ERC721ExecutedToRecipient 0x0f52fde6171d45c02579364597406652690bf2264e564ba1a5b88ffa98d8815b,
  ERC1155ExecutedToRecipient 0x6d10597eaea3b6f10739896c93a2cdebf87810d37226b40bc3e433745f55ce9c (match the §9 prefixes), ERC721BuyOrderAdded 0x427c7dcd…a656,
  ERC1155BuyOrderAdd 0xb89a3fa0…edc, AddedToQueue 0x76575e92…f584, QueueClaimed 0xe8a0b83f…0319, MintInstallation(s), UpgradeQueued/Finalized,
  InstallationUpgraded, TransferToParent/FromParent, EventStarted, Auction_BoughtNow, AuctionCancelled, GotchiLending* (full hashes in config.GV_TOPICS).
- 0x6feecbb5 = `placeERC721BuyOrder(address,uint256,uint256,uint256,uint256,bool[])` (openchain signature DB, verified-contract flag). This moves it from [I] to [F] for the signature.
- Test wallet crafts (Base): 4 `craftInstallations(uint16[],uint40[])` 0x9ff2a527 txs to the Installation diamond. Receipts (RPC) show instant crafts
  (MintInstallation + TransferSingle amount 1, no queue). 0x74f55051… pays FUD/FOMO split 35/30/30/5 to REALM 0x4b0040c3…, Pixelcraft 0x50def14c…,
  DAO 0x939b67f6… and 0xFFfF. 0x8a8ceab8…, 0x6ef4ef7d… (id 10) and 0x90e41da7… (id 145) have no inputs (free crafts, labelled income today).
- 0xeae2fb93e291c2eb69195851813de24f97f1ce71 = Aerodrome **pool** FUD/GHST (PoolFactory.getPool(FUD, GHST, false), P3 discovery), not a router.

## Steps (small commits, pushed)
1. Plan (this file).
2. Ingest: new HyperSync source `hypersync_gv` per wallet (sync_cursor), under the host lock (≤ 5/min, nohup):
   wallet-sent txs with `join_mode` 1 (JoinAll: every log of those txs), plus wallet-topic selections for ERC721/1155ExecutedToRecipient
   (recipient), GotchiLending* (lender / borrower), and Installation/Tile TransferSingle/Batch to the wallet (pulls the finalize/claim txs others send).
   Only logs whose topic0 is in GV_TOPICS are stored (raw_event kind `gv_<Event>`); transfers/market rows already exist (PK = tx, log_index).
3. Classifier rules 1–10 (§9), each with a test. Unclear cases go to review, never guessed:
   R1 ERC721 buy orders: placement 0x6feecbb5 → escrow_out; fill price = ERC721BuyOrderExecuted data word 3; ExecutedToRecipient with the wallet as recipient and no wallet payment → `gift_in` (flagged, basis 0).
   R2 GBM seller: NFT wallet→GBM with Auction_Initialized → `escrow_out` (location escrow:gbm); claim → disposal (`auction`) vs GHST in; AuctionCancelled → `escrow_return`;
      buy-now (Auction_BoughtNow, buyer = wallet) → nft_buy only if the event is seen on Base, otherwise review.
   R3 `craft` (inputs + NFT); free craft → `craft`, no inputs, not income; queued: craft tx `craft_pending` (ref craft:queue:<id> from AddedToQueue), claim (QueueClaimed) → `craft` same ref;
      qty from MintInstallations when present, else TransferSingle.
   R4 `upgrade`: alchemica/GLTR out (incl. 0xFFfF) with UpgradeQueued (owner = wallet) or UpgradeInitiated; finalize (InstallationUpgraded prev→next) → old id -1 / new id +1 at parcel:<realm>, category upgrade; reduceUpgradeTime GLTR → upgrade.
   R5 equip/unequip: Installation/Tile TransferToParent/FromParent (topic1 = REALM, topic2 = parcel) → custody, location parcel:<id> (wallet -1 / parcel +1 and back);
      an unequip that burns the item with an alchemica refund → `destroy_refund` (item disposed at parcel, refund acquired).
   R6 parcel sold while items are equipped → the parcel leg is tagged `bundle:<parcel>` (escrow_ref) for P4; items stay at parcel:<id>.
   R7 claim/channel (0x9fefe547 / 0x8027870e) paid from REALM → income; lending revenue from the gotchi escrow → income.
   R8 lending: gotchi out/back with GotchiLendingExecuted/Ended (lender = wallet) → custody at lent:<borrower>; upfront GHST → income.
   R9 bounce gate: GLTR/alchemica to 0xFFfF in a tx with EventStarted → `spend`.
   R10 0xeae2fb93 is a pool, not a router → its txs stay as classified today / review; FUD depositERC20 to 0x728f0baf… → review (identify first).
4. Migration 008 `008_p2_2_gotchiverse.sql` (+ rollback): categories craft, craft_pending, upgrade, gift_in, spend, destroy_refund. No ON DELETE CASCADE added.
   (P3's pricing migration on the paused branch gets renumbered after this merges.)
5. Tests: synthetic fixtures for upgrade, equip/unequip/destroy, lending, GBM seller, buy-now, gift_in, queued craft, bounce gate; real-shaped fixtures for the 4 crafts.
   One real Base tx per flow sampled read-only (Blockscout / RPC receipts) where one exists; flows without a sample are listed as unverified.
6. Base + Sepolia: ingest (gv source, nohup, lock ≤ 5/min) then classify ×2 (identical), > 98 % classified, the rest in review.
7. P2_2_RESULTS.md, KNOWN_GAPS updates, PR against main. STOP.

## Test commands
- Unit: `CRYPTOPNL_DSN=postgresql:///cryptopnl_unit_p22 ENVIO_API_TOKEN=x .venv/bin/python -m unittest discover tests`
- E2E: copies of the P2.1 DBs (`createdb -T cryptopnl_p11s_base cryptopnl_p22_base`, same for Sepolia), then
  `abra run cryptoPnL -k ENVIO_API_TOKEN -- nohup scripts/p2_2_test.sh <chain> <wallet>`. HyperSync per-minute counts via NET_REQLOG + reqlog_summary.py.

## Rollback
`migrations/rollback/008_down.sql` (re-classify afterwards), `DELETE FROM raw_event WHERE source='hypersync_gv'` + its sync_cursor rows; revert commits (no force-push).
The P2.1 evidence DBs are never written (work happens on copies).
