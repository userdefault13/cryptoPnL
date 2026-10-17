"""P2.2 Gotchiverse rules (DESIGN v1.3 §9). Synthetic fixtures (offline, local Postgres). The craft fixtures are shaped like the test
wallet's real Base txs (0x74f55051… paid, 0x8a8ceab8… / 0x90e41da7… free; receipts read via RPC). Upgrade, equip/destroy, lending, GBM
seller, buy-now, gift, bounce gate: synthetic only (no such tx in the test wallet).
Run: CRYPTOPNL_DSN=postgresql:///cryptopnl_unit_p22 ENVIO_API_TOKEN=x .venv/bin/python -m unittest -v tests.test_gotchiverse"""
import os, unittest
os.environ.setdefault("ENVIO_API_TOKEN", "test")
from tests import test_classify as tc
from tests.test_classify import C, W, X, GHST, ZERO, GBM, tx, e20, e721, e1155, t32
from cryptopnl.db import b
REALM = "0x4b0040c3646d3c44b8a28ad7055cfcf536c05372"; INST = "0xebba5b725a2889f7f089a6cae0246a32cad4e26b"
AG = "0xa99c4b08201f2913db8d28e71d020c4298f29dbf"; BURN = "0x" + "f" * 40
PIX = "0x50def14c51123660f8768b511b93cc8c09f30356"; DAO = "0x939b67f6f6be63e09b0258621c5a24eecb92631c"
FUD = "0x2028b4043e6722ea164946c82fe806c4a43a0ff4"; GLTR = "0x4d140ce792bedc430498c2d219afbc33e2992c9d"
POCKET = "0x728f0baf79ebdfa336978c90f244324a0ba7bcff"; TILE = "0x617fdb8093b309e4699107f48812b407a7c37938"; B_ = "0x00000000000000000000000000000000000000bb"   # borrower
E18 = 10 ** 18
def gv(contract, event, topics=(), data=(), market=False):
    return (("market_" if market else "gv_") + event, {"contract": contract, "event": event,
            "topics": ["0x" + "1" * 64] + [t32(x) for x in topics], "data": "0x" + "".join(t32(x)[2:] for x in data)})
def split(tok, total, frm=W):   # 35/30/30/5 craft/upgrade cost split
    return [e20(tok, frm, REALM, total * 35 // 100), e20(tok, frm, PIX, total * 30 // 100), e20(tok, frm, DAO, total * 30 // 100), e20(tok, frm, BURN, total * 5 // 100)]

class GV(unittest.TestCase):
    setUp = tc.T.setUp; tearDown = tc.T.tearDown; add = tc.T.add; run_ = tc.T.run_; review = tc.T.review
    def rows(self, h):
        return sorted((r[0], r[1], r[2], int(r[3]), r[4]) for r in self.c.execute("""SELECT l.category, l.location,
            coalesce('0x'||encode(a.contract,'hex'),'native')||coalesce('#'||a.token_id::text,''), l.qty, coalesce(l.escrow_ref,'')
            FROM ledger_entry l JOIN asset a ON a.id=l.asset_id WHERE tx_hash=%s AND category<>'fee'""", (h,)))
    def cats(self, h): return sorted({r[0] for r in self.rows(h)})

    def test_craft_paid_free_and_queued(self):
        paid = self.add(tx(W, INST, selector="0x9ff2a527"), *split(FUD, 100 * E18), e1155(INST, ZERO, W, 56, 1), gv(INST, "MintInstallation", (W, 56)))
        free = self.add(tx(W, INST, selector="0x9ff2a527"), e1155(INST, ZERO, W, 10, 1), gv(INST, "MintInstallation", (W, 10)))
        q = self.add(tx(W, INST, selector="0x9ff2a527"), *split(FUD, 40 * E18), gv(INST, "AddedToQueue", (7, 145), (999, int(W, 16))))
        claim = self.add(tx(W, INST, selector="0x763b948a"), gv(INST, "QueueClaimed", (7,)), e1155(INST, ZERO, W, 145, 5),
                         gv(INST, "MintInstallation", (W, 145), (7,)), gv(INST, "MintInstallations", (W, 145), (5,)))
        s = self.run_(); self.assertEqual(s["review"], 0)
        self.assertEqual(self.cats(paid), ["craft"]); self.assertEqual(len(self.rows(paid)), 5)
        self.assertEqual(self.rows(free), [("craft", "wallet", f"{INST}#10", 1, "craft:instant:free")])   # free craft: craft, never income
        self.assertEqual(self.cats(q), ["craft_pending"]); self.assertTrue(all(r[4] == f"craft:queue:{INST}:7" for r in self.rows(q)))
        self.assertEqual(self.rows(claim), [("craft", "wallet", f"{INST}#145", 5, f"craft:queue:{INST}:7")])   # TransferSingle == MintInstallations
        self.assertNotIn("income", {r[0] for h in (paid, free, q, claim) for r in self.rows(h)})

    def test_batch_crafts_free_are_craft_not_income(self):   # B2: batchCraftInstallations 0xe9332638 / batchCraftTiles 0xfdc6d919 (live on Base)
        bi = self.add(tx(W, INST, selector="0xe9332638"), e1155(INST, ZERO, W, 10, 3), gv(INST, "MintInstallations", (W, 10), (3,)))
        bt = self.add(tx(W, TILE, selector="0xfdc6d919"), e1155(TILE, ZERO, W, 4, 2), gv(TILE, "MintTiles", (W, 4), (2,)))
        s = self.run_(); self.assertEqual(s["review"], 0)
        self.assertEqual(self.rows(bi), [("craft", "wallet", f"{INST}#10", 3, "craft:instant:free")])
        self.assertEqual(self.rows(bt), [("craft", "wallet", f"{TILE}#4", 2, "craft:instant:free")])

    def test_queue_refs_are_contract_scoped_and_per_leg(self):   # B3: Installation q7 != Tile q7; one claim covering q7 + q8
        qi = self.add(tx(W, INST, selector="0x9ff2a527"), *split(FUD, 40 * E18), gv(INST, "AddedToQueue", (7, 10), (999, int(W, 16))))
        qt = self.add(tx(W, TILE, selector="0x976a1afe"), *split(FUD, 20 * E18), gv(TILE, "AddedToQueue", (7, 4), (999, int(W, 16))))
        q8 = self.add(tx(W, INST, selector="0x9ff2a527"), *split(FUD, 40 * E18), gv(INST, "AddedToQueue", (8, 12), (999, int(W, 16))))
        ct = self.add(tx(W, TILE, selector="0xa185cc01"), gv(TILE, "QueueClaimed", (7,)), e1155(TILE, ZERO, W, 4, 1), gv(TILE, "MintTile", (W, 4), (7,)))
        ci = self.add(tx(W, INST, selector="0x763b948a"), gv(INST, "QueueClaimed", (7,)), gv(INST, "QueueClaimed", (8,)),
                      e1155(INST, ZERO, W, 12, 1), gv(INST, "MintInstallation", (W, 12), (8,)),
                      e1155(INST, ZERO, W, 10, 1), gv(INST, "MintInstallation", (W, 10), (7,)))
        s = self.run_(); self.assertEqual(s["review"], 0)
        self.assertTrue(all(r[4] == f"craft:queue:{INST}:7" for r in self.rows(qi)))
        self.assertTrue(all(r[4] == f"craft:queue:{TILE}:7" for r in self.rows(qt)))
        self.assertEqual(self.rows(ct), [("craft", "wallet", f"{TILE}#4", 1, f"craft:queue:{TILE}:7")])
        self.assertEqual(self.rows(ci), [("craft", "wallet", f"{INST}#10", 1, f"craft:queue:{INST}:7"),
                                         ("craft", "wallet", f"{INST}#12", 1, f"craft:queue:{INST}:8")])

    def test_craft_qty_mismatch_is_review(self):   # Base has no "always 1" bug: a mismatch is suspicious, not overridden
        h = self.add(tx(W, INST, selector="0xe9332638"), e1155(INST, ZERO, W, 10, 1), gv(INST, "MintInstallations", (W, 10), (3,)))
        other = self.add(tx(W, INST, selector="0xe9332638"), e1155(INST, ZERO, W, 11, 2), gv(INST, "MintInstallations", (X, 11), (9,)))   # other owner: ignored
        self.run_(); self.assertIn("quantity mismatch", self.review(h))
        self.assertEqual(self.rows(other), [("craft", "wallet", f"{INST}#11", 2, "craft:instant:free")])

    def test_reduce_craft_time_gltr_burn_to_zero(self):
        h = self.add(tx(W, INST, selector="0xe0d20147"), e20(GLTR, W, ZERO, 9 * E18), gv(INST, "CraftTimeReduced", (7,), (100,)))
        s = self.run_(); self.assertEqual(s["review"], 0)
        self.assertEqual(self.rows(h), [("craft_pending", "wallet", GLTR, -9 * E18, f"craft:queue:{INST}:7")])

    def test_craft_leg_outside_split_is_review(self):
        h = self.add(tx(W, INST, selector="0x9ff2a527"), e20(FUD, W, X, E18), e1155(INST, ZERO, W, 56, 1))
        self.run_(); self.assertIn("35/30/30/5", self.review(h))

    def test_upgrade_cost_and_finalize(self):
        cost = self.add(tx(W, INST, selector="0xd6c7ec0e"), *split(FUD, 20 * E18), e20(GLTR, W, BURN, 3 * E18), gv(INST, "UpgradeQueued", (W, 42, 3)))
        red = self.add(tx(W, INST, selector="0x942e5c6f"), e20(GLTR, W, BURN, E18), gv(INST, "UpgradeTimeReduced", (3, 42), (1, 2, 50)))
        fin = self.add(tx(X, INST, selector="0x9a508c8e"), e1155(INST, ZERO, W, 11, 1), e1155(INST, W, REALM, 11, 1),
                       gv(INST, "UpgradeQueueFinalized", (W, 42, 3)), gv(REALM, "InstallationUpgraded", (), (42, 10, 11, 1, 2)))
        s = self.run_(); self.assertEqual(s["review"], 0)
        Q = "upgrade:realm:42:queue:3"   # queue index carried: UpgradeQueued topic3, UpgradeTimeReduced topic1, UpgradeQueueFinalized topic3
        self.assertEqual(self.cats(cost), ["upgrade"]); self.assertTrue(all(r[4] == Q for r in self.rows(cost) + self.rows(red)))
        r = self.rows(fin)
        self.assertIn(("upgrade", "parcel:42", f"{INST}#10", -1, Q), r)   # old lot closes (no realized PnL: P4)
        self.assertIn(("upgrade", "parcel:42", f"{INST}#11", 1, Q), r)    # new id at the parcel
        self.assertEqual(sum(q for c, loc, a, q, _ in r if loc == "wallet"), 0)            # mint + re-equip net to zero in the wallet

    def test_equip_unequip_destroy_and_bundle(self):
        eq = self.add(tx(W, REALM), e1155(INST, W, REALM, 10, 1), gv(INST, "TransferToParent", (REALM, 42, 10), (1,)))
        eq2 = self.add(tx(W, REALM), e1155(INST, W, REALM, 12, 1), gv(INST, "TransferToParent", (REALM, 42, 12), (1,)))
        un = self.add(tx(W, REALM), e1155(INST, REALM, W, 12, 1), gv(INST, "TransferFromParent", (REALM, 42, 12), (1,)))
        sale = self.add(tx(X, X), e721(REALM, W, X, 42), e20(GHST, X, W, 40 * E18))       # parcel sold, id 10 still equipped
        eq3 = self.add(tx(W, REALM), e1155(INST, W, REALM, 13, 1), gv(INST, "TransferToParent", (REALM, 7, 13), (1,)))
        des = self.add(tx(W, INST, selector="0x32408069"), gv(INST, "TransferFromParent", (REALM, 7, 13), (1,)), e20(FUD, REALM, W, 5 * E18))
        s = self.run_(); self.assertEqual(s["review"], 0)
        self.assertEqual(self.rows(eq), [("transfer_internal", "parcel:42", f"{INST}#10", 1, "parcel:42"),
                                         ("transfer_internal", "wallet", f"{INST}#10", -1, "parcel:42")])
        self.assertEqual(self.rows(un), [("transfer_internal", "parcel:42", f"{INST}#12", -1, "parcel:42"),
                                         ("transfer_internal", "wallet", f"{INST}#12", 1, "parcel:42")])
        parcel = [r for r in self.rows(sale) if r[2] == f"{REALM}#42"][0]
        self.assertEqual(parcel[0], "nft_sale"); self.assertIn("bundle:parcel:42", parcel[4])
        self.assertEqual(sorted((r[0], r[1], r[3]) for r in self.rows(des)),
                         [("destroy_refund", "parcel:7", -1), ("destroy_refund", "wallet", 5 * E18)])

    def test_lending_custody_and_income(self):
        ex = self.add(tx(B_, AG), e721(AG, W, B_, 99), e20(GHST, B_, W, 5 * E18), gv(AG, "GotchiLendingExecuted", (1, W, B_)))
        end = self.add(tx(B_, AG), e721(AG, B_, W, 99), e20(FUD, X, W, 2 * E18), gv(AG, "GotchiLendingEnded", (1, W, B_)))
        s = self.run_(); self.assertEqual(s["review"], 0)
        self.assertEqual(self.rows(ex), [("income", "wallet", GHST, 5 * E18, "lending:upfront"),
                                         ("transfer_internal", f"lent:{B_}", f"{AG}#99", 1, f"lent:{B_}"),
                                         ("transfer_internal", "wallet", f"{AG}#99", -1, f"lent:{B_}")])
        self.assertIn(("transfer_internal", f"lent:{B_}", f"{AG}#99", -1, f"lent:{B_}"), self.rows(end))
        self.assertIn(("income", "wallet", FUD, 2 * E18, "lending:revenue"), self.rows(end))
        self.assertNotIn("nft_sale", self.cats(ex) + self.cats(end))

    def test_lending_borrower_r8b(self):   # shapes of real 0xe7505b72… / 0xec5e558b… (+ a revenue share and a channel while borrowing)
        ex = self.add(tx(W, AG), e721(AG, X, W, 10774), e20(GHST, W, X, 2 * E18 // 10), gv(AG, "GotchiLendingExecuted", (1, X, W)))
        ch = self.add(tx(W, REALM, selector="0x8027870e"), e20(FUD, REALM, W, 4 * E18))
        end = self.add(tx(X, AG), e721(AG, W, X, 10774), e20(FUD, AG, W, E18), gv(AG, "GotchiLendingEnded", (1, X, W)))
        s = self.run_(); self.assertEqual(s["review"], 0)
        self.assertEqual(self.rows(ex), [("spend", "wallet", GHST, -2 * E18 // 10, "lending:borrower:upfront"),
                                         ("untracked", "wallet", f"{AG}#10774", 1, f"borrowed:{X}")])
        self.assertEqual(self.rows(ch), [("income", "wallet", FUD, 4 * E18, "")])
        self.assertEqual(self.rows(end), [("income", "wallet", FUD, E18, "lending:borrower:revenue:fmv_unpriced"),
                                          ("untracked", "wallet", f"{AG}#10774", -1, f"borrowed:{X}")])
        q = self.c.execute("""SELECT bool_and(pnl_excluded) FILTER (WHERE category='untracked'), bool_or(price_usdc IS NOT NULL)
                              FROM ledger_entry WHERE tx_hash IN (%s,%s)""", (ex, end)).fetchone()
        self.assertEqual(q, (True, False))   # borrowed gotchi pnl_excluded; nothing priced before P3
        self.assertEqual(self.c.execute("SELECT count(*) FROM fifo_lot").fetchone()[0], 0)   # no phantom gotchi lot

    def test_lending_borrower_odd_legs_review(self):
        h = self.add(tx(W, AG), e721(AG, B_, W, 10774), gv(AG, "GotchiLendingExecuted", (1, X, W)))   # gotchi not from the lender
        self.run_(); self.assertIn("lender", self.review(h))

    def test_gbm_seller_create_claim_and_cancel(self):
        NFTC = REALM
        cr = self.add(tx(W, GBM), e721(NFTC, W, GBM, 5), gv(GBM, "Auction_Initialized", (77, 5, 1), (int(NFTC, 16), 0, 0), market=True))
        cl = self.add(tx(X, GBM), gv(GBM, "Auction_ItemClaimed", (77,), market=True), e20(GHST, GBM, W, 50 * E18))
        cr2 = self.add(tx(W, GBM), e721(NFTC, W, GBM, 6), gv(GBM, "Auction_Initialized", (78, 6, 1), (int(NFTC, 16), 0, 0), market=True))
        ca = self.add(tx(W, GBM), gv(GBM, "AuctionCancelled", (78,), (6,)), e721(NFTC, GBM, W, 6))
        s = self.run_(); self.assertEqual(s["review"], 0)
        self.assertEqual(self.cats(cr), ["escrow_out"])
        self.assertEqual(self.rows(cl), [("auction", f"escrow:{GBM}", f"{NFTC}#5", -1, "gbm:auction:77"),
                                         ("auction", "wallet", GHST, 50 * E18, "gbm:auction:77")])
        self.assertEqual(self.cats(ca), ["escrow_return"])
        self.assertEqual(self.c.execute("SELECT sum(qty) FROM ledger_entry WHERE location=%s", (f"escrow:{GBM}",)).fetchone()[0], 0)

    def test_gbm_seller_paid_by_buy_now(self):
        cr = self.add(tx(W, GBM), e1155(INST, W, GBM, 4, 64), gv(GBM, "Auction_Initialized", (90, 4, 64), (int(INST, 16), 1, 0), market=True))
        bn = self.add(tx(X, GBM), gv(GBM, "Auction_BoughtNow", (90, X), market=True), e20(GHST, GBM, W, 51 * E18),   # real 0x271109cf…: BoughtNow
                      gv(GBM, "Auction_ItemClaimed", (90,), market=True))                                          # AND ItemClaimed (logs 396/403)
        s = self.run_(); self.assertEqual(s["review"], 0)
        self.assertEqual(self.rows(bn), [("auction", f"escrow:{GBM}", f"{INST}#4", -64, "gbm:auction:90"),
                                         ("auction", "wallet", GHST, 51 * E18, "gbm:auction:90")])

    def test_gbm_buy_now(self):
        h = self.add(tx(W, GBM), e20(GHST, W, GBM, 10 * E18), gv(GBM, "Auction_BoughtNow", (88, W), market=True),   # real shape: both events
                     e1155(TILE, GBM, W, 4, 64), gv(GBM, "Auction_ItemClaimed", (88,), market=True))
        s = self.run_(); self.assertEqual(s["review"], 0)
        self.assertEqual(self.rows(h), [("nft_buy", "wallet", f"{TILE}#4", 64, "gbm:auction:88"), ("nft_buy", "wallet", GHST, -10 * E18, "gbm:auction:88")])

    def test_gift_in_and_erc721_buy_order(self):
        gift = self.add(tx(X, AG), e721(REALM, X, W, 7), gv(AG, "ERC721ExecutedToRecipient", (9, X, W)))
        place = self.add(tx(W, AG, selector="0x6feecbb5"), e20(GHST, W, AG, 100 * E18), gv(AG, "ERC721BuyOrderAdded", (5, W, 4)))
        fill = self.add(tx(X, AG), e721(REALM, X, W, 3), gv(AG, "ERC721BuyOrderExecuted", (5, W), (int(X, 16), int(REALM, 16), 3, 100 * E18, 1), market=True))
        s = self.run_(); self.assertEqual(s["review"], 0)
        self.assertEqual(self.rows(gift), [("gift_in", "wallet", f"{REALM}#7", 1, "gift:listing:9:basis0")])
        self.assertTrue(all(r[4] == "baazaar:buyorder:5" for r in self.rows(place)))
        self.assertIn(("nft_buy", f"escrow:{AG}", GHST, -100 * E18, "baazaar:buyorder:5"), self.rows(fill))   # price = data word 3

    def test_bounce_gate_create_update_and_income_path(self):
        bounce = self.add(tx(W, REALM), e20(GLTR, W, BURN, 7 * E18), gv(REALM, "EventStarted", (4,)))
        upd = self.add(tx(W, REALM), e20(GLTR, W, BURN, 2 * E18), gv(REALM, "EventPriorityAndDurationUpdated", (4,), (10, 99)))
        claim = self.add(tx(W, REALM, selector="0x9fefe547"), e20(FUD, REALM, W, 3 * E18))    # paid from REALM's balance
        s = self.run_(); self.assertEqual(s["review"], 0)
        self.assertEqual(self.rows(bounce), [("spend", "wallet", GLTR, -7 * E18, "bounce:event:4")])
        self.assertEqual(self.rows(upd), [("spend", "wallet", GLTR, -2 * E18, "bounce:event:4:update")])
        self.assertEqual(self.cats(claim), ["income"])

    def pocket(self, gid=3033):
        self.c.execute("INSERT INTO gotchi_escrow(chain_id,gotchi_id,escrow,resolved_block) VALUES (%s,%s,%s,1)", (C, gid, b(POCKET)))

    def test_pocket_custody_for_owned_gotchi(self):   # 0x728f0baf… = gotchiEscrow(3033), owner = the wallet (RPC)
        self.pocket()
        buy = self.add(tx(W, X), e721(AG, X, W, 3033), e20(GHST, W, X, 5 * E18))
        dep = self.add(tx(W, AG, selector="0xb0facab3"), e20(FUD, W, POCKET, E18 // 20))        # shape of real 0x3a46db38…
        out = self.add(tx(W, AG, selector="0x2a206f11"), e20(GHST, POCKET, W, E18))             # batchTransferEscrow (shape of 0xd329b5d2…)
        s = self.run_(); self.assertEqual(s["review"], 0)
        self.assertEqual(self.rows(dep), [("transfer_internal", "pocket:3033", FUD, E18 // 20, "pocket:3033"),
                                          ("transfer_internal", "wallet", FUD, -E18 // 20, "pocket:3033")])
        self.assertEqual(self.rows(out), [("transfer_internal", "pocket:3033", GHST, -E18, "pocket:3033"),
                                          ("transfer_internal", "wallet", GHST, E18, "pocket:3033")])
        from cryptopnl import classify
        fud = self.c.execute("SELECT id FROM asset WHERE contract=%s", (b(FUD),)).fetchone()[0]
        wallet_only = self.c.execute("SELECT sum(qty) FROM ledger_entry WHERE asset_id=%s AND location='wallet'", (fud,)).fetchone()[0]
        self.assertEqual(int(wallet_only), -E18 // 20)               # the wallet alone looks short...
        self.assertEqual(classify.totals(self.c, C).get(fud, 0), 0)   # ...holdings include the pocket: FUD moved, not lost

    def test_pocket_of_unowned_gotchi_or_other_selector_is_review(self):
        self.pocket()
        dep = self.add(tx(W, AG, selector="0xb0facab3"), e20(FUD, W, POCKET, E18))     # gotchi 3033 never owned here
        self.run_(); self.assertIn("does not own", self.review(dep))

    def test_pocket_unknown_escrow_is_review(self):
        dep = self.add(tx(W, AG, selector="0xb0facab3"), e20(FUD, W, POCKET, E18))     # cache empty
        self.run_(); self.assertIn("gotchiEscrow cache", self.review(dep))

    def test_lending_revenue_claimed_by_borrower_tuple_event(self):   # R7: tuple event (no wallet topic); lender from the decode
        ESC = "0x00000000000000000000000000000000000000ee"
        h = self.add(tx(B_, AG, selector="0xffa7802d"), e20(FUD, ESC, W, 3 * E18), e20(FUD, ESC, B_, 6 * E18),
                     gv(AG, "GotchiLendingClaimedT", (), (0x20, 1, int(W, 16), int(B_, 16), 99)))
        s = self.run_(); self.assertEqual(s["review"], 0)
        self.assertEqual(self.rows(h), [("income", "wallet", FUD, 3 * E18, "lending:revenue")])

    def test_aerodrome_pool_add_liquidity_and_other_review(self):   # R10: 0xeae2fb93… is a pool (its own LP token), not a router
        POOL = "0xeae2fb93e291c2eb69195851813de24f97f1ce71"
        add = self.add(tx(W, "0xcf77a3ba9a5ca399b7c97c74d54e5b1beb874e43"), e20(FUD, W, POOL, 100 * E18), e20(GHST, W, POOL, E18), e20(POOL, ZERO, W, 7 * E18))
        sw = self.add(tx(W, "0xcf77a3ba9a5ca399b7c97c74d54e5b1beb874e43"), e20(FUD, W, POOL, 10 * E18), e20(GHST, POOL, W, E18 // 10))
        self.run_()
        self.assertEqual(self.rows(add), [("swap", "wallet", FUD, -100 * E18, f"lp_add:{POOL}"), ("swap", "wallet", GHST, -E18, f"lp_add:{POOL}"),
                                          ("untracked", "wallet", POOL, 7 * E18, f"lp_add:{POOL}")])
        self.assertIn("pool", self.review(sw))

    def test_parcel_bundle_cleared_when_parcel_leaves(self):
        self.add(tx(W, REALM), e1155(INST, W, REALM, 10, 1), gv(INST, "TransferToParent", (REALM, 42, 10), (1,)))
        self.add(tx(X, X), e721(REALM, W, X, 42), e20(GHST, X, W, 40 * E18))          # sold with item 10: bundle, parcels cleared
        back = self.add(tx(X, X), e721(REALM, X, W, 42), e20(GHST, W, X, 30 * E18))   # bought back (bare)
        again = self.add(tx(X, X), e721(REALM, W, X, 42), e20(GHST, X, W, 35 * E18))  # sold bare: no bundle tag
        s = self.run_(); self.assertEqual(s["review"], 0)
        self.assertTrue(all("bundle" not in r[4] for r in self.rows(again)))

if __name__ == "__main__": unittest.main()
