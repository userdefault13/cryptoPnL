"""P2 classifier unit tests: one synthetic tx per rule + review paths + idempotency. Offline (local Postgres only).
Run: CRYPTOPNL_DSN=postgresql:///cryptopnl_unit11 ENVIO_API_TOKEN=x .venv/bin/python -m unittest -v tests.test_classify"""
import datetime, json, os, unittest
os.environ.setdefault("ENVIO_API_TOKEN", "test")
from cryptopnl import db, classify
from cryptopnl.db import b

C = 8453
W = "0x000000000000000000000000000000000000dead"
W2 = "0x000000000000000000000000000000000000beef"   # same wallet_group
X = "0x00000000000000000000000000000000000000aa"    # external
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"; GHST = "0xcd2f22236dd9dfe2356d7c543161d4d260fd9bcb"
NFT = "0x4b0040c3646d3c44b8a28ad7055cfcf536c05372"; SPAM = "0x00000000000000000000000000000000000005a5"
GBM = "0x80320a0000c7a6a34086e2acad6915ff57ffda31"; ROUTER = "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad"
ZERO = "0x" + "0" * 40
def th(n): return "0x" + format(n, "064x")
BZ = "0xa99c4b08201f2913db8d28e71d020c4298f29dbf"; TILE = "0x617fdb8093b309e4699107f48812b407a7c37938"
def tx(frm, to, value=0, fee=100, status="1", selector="0x"):
    return ("tx", {"from": frm, "to": to, "value": str(value), "fee": str(fee), "status": status, "selector": selector})
def t32(v): return "0x" + format(int(v, 16) if isinstance(v, str) else v, "064x")
def e1155(c, f, t, i, v): return ("erc1155_single", {"contract": c, "operator": f, "from": f, "to": t, "ids": [str(i)], "values": [str(v)]})
def bid(auction, bidder, amt): return ("market_Auction_BidPlaced", {"contract": GBM, "event": "Auction_BidPlaced",
    "topics": ["0x1cd7", t32(auction), t32(bidder)], "data": t32(amt)})
def claimed(auction): return ("market_Auction_ItemClaimed", {"contract": GBM, "event": "Auction_ItemClaimed", "topics": ["0x36c8", t32(auction)], "data": "0x"})
def bo_exec(order_id, buyer, seller, token, tid, price, qty): return ("market_ERC1155BuyOrderExecute", {"contract": BZ, "event": "ERC1155BuyOrderExecute",
    "topics": ["0xa604", t32(order_id), t32(buyer), t32(5)], "data": "0x" + "".join(t32(x)[2:] for x in (seller, token, tid, price, qty, 1770000000))})
PLACE = "0x4cc4a386"
def e20(c, f, t, v): return ("erc20_transfer", {"contract": c, "from": f, "to": t, "value": str(v)})
def e721(c, f, t, i): return ("erc721_transfer", {"contract": c, "from": f, "to": t, "token_id": str(i), "value": "1"})
def mkt(c, ev): return ("market_" + ev, {"contract": c, "event": ev})

class T(unittest.TestCase):
    def setUp(self):
        self.c = db.connect(); db.migrate(self.c)
        for t in ("manual_basis", "ledger_entry", "review_queue", "raw_event", "block", "sync_cursor", "sync_cursor_global", "asset", "wallet"):
            self.c.execute(f"DELETE FROM {t}")
        for a in (W, W2): self.c.execute("INSERT INTO wallet(chain_id,address,wallet_group) VALUES (%s,%s,'g')", (C, b(a)))
        self.c.commit(); self.n = 0
    def tearDown(self):
        for t in ("manual_basis", "ledger_entry", "review_queue", "asset"): self.c.execute(f"DELETE FROM {t}")
        self.c.commit(); self.c.close()
    def add(self, *evs, bn=None):
        self.n += 1; h = th(self.n); bn = bn or self.n
        self.c.execute("INSERT INTO block VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING", (C, bn, b(th(10**6 + bn)), datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)))
        for i, (k, p) in enumerate(evs):
            self.c.execute("INSERT INTO raw_event VALUES (%s,%s,%s,%s,%s,'t',%s,%s)", (C, b(h), -1 if k == "tx" else i, bn, b(th(10**6 + bn)), k, json.dumps(p)))
        self.c.commit(); return b(h)
    def cats(self, h, wallet=W):
        return sorted((r[0], int(r[1])) for r in self.c.execute(
            "SELECT category, qty FROM ledger_entry l JOIN wallet w ON w.id=l.wallet_id WHERE tx_hash=%s AND w.address=%s", (h, b(wallet))))
    def rows(self, h):
        return sorted((r[0], r[1], int(r[2]), r[3]) for r in self.c.execute(
            "SELECT category, location, qty, escrow_ref FROM ledger_entry WHERE tx_hash=%s AND category<>'fee'", (h,)))
    def open_escrow(self):
        return {r[0]: int(r[1]) for r in self.c.execute("SELECT location, sum(qty) FROM ledger_entry WHERE location LIKE 'escrow:%' GROUP BY 1")}
    def review(self, h): r = self.c.execute("SELECT reason FROM review_queue WHERE tx_hash=%s", (h,)).fetchone(); return r and r[0]
    def run_(self): return classify.classify(self.c, C, log=lambda *_: None)

    def test_rules(self):
        fee_only = self.add(tx(W, USDC))
        failed = self.add(tx(W, X, value=5, status="0"))
        swap = self.add(tx(W, X), e20(USDC, W, X, 10), e20(GHST, X, W, 20))
        swap_native = self.add(tx(W, ROUTER, value=7), e20(GHST, X, W, 20))
        buy = self.add(tx(W, X), e20(GHST, W, X, 30), e721(NFT, X, W, 1))
        sale = self.add(tx(X, X), e721(NFT, W, X, 2), e20(GHST, X, W, 40))
        auction = self.add(tx(W, GBM), e20(GHST, W, GBM, 50), bid(1, W, 50))
        internal = self.add(tx(W, USDC), e20(USDC, W, W2, 60))
        income = self.add(tx(W, X), e20(GHST, ZERO, W, 70))
        spam_mint = self.add(e721(SPAM, ZERO, W, 3))
        deposit = self.add(e20(USDC, X, W, 80))
        withdrawal = self.add(tx(W, X, value=90))
        poison = self.add(e20(USDC, X, W, 0))
        router_out = self.add(tx(W, ROUTER), e20(USDC, W, X, 11))
        mixed = self.add(e20(SPAM, X, W, 5), e20(SPAM, W, X, 5))
        s = self.run_()
        self.assertEqual(self.cats(fee_only), [("fee", -100)])
        self.assertEqual(self.cats(failed), [("fee", -100)])                       # failed: gas only, no value leg
        self.assertEqual(self.cats(swap), [("fee", -100), ("swap", -10), ("swap", 20)])
        self.assertEqual(self.cats(swap_native), [("fee", -100), ("swap", -7), ("swap", 20)])
        self.assertEqual(self.cats(buy), [("fee", -100), ("nft_buy", -30), ("nft_buy", 1)])
        self.assertEqual(self.cats(sale), [("nft_sale", -1), ("nft_sale", 40)])  # not sent by W: no fee leg
        self.assertEqual(self.cats(auction), [("escrow_out", -50), ("escrow_out", 50), ("fee", -100)])   # bid = custody
        self.assertEqual(self.cats(internal), [("fee", -100), ("transfer_internal", -60)])
        self.assertEqual(self.cats(internal, W2), [("transfer_internal", 60)])
        self.assertEqual(self.cats(income), [("fee", -100), ("income", 70)])
        self.assertEqual(self.cats(spam_mint), [("spam", 1)])                     # unsolicited, non-allowlisted mint
        self.assertEqual(self.cats(deposit), [("deposit", 80)])
        self.assertEqual(self.cats(withdrawal), [("fee", -100), ("withdrawal", -90)])
        self.assertEqual(self.cats(poison), [("spam", 0)]); self.assertIsNone(self.review(poison))   # poisoning: flagged, kept
        self.assertEqual(self.cats(router_out), [("fee", -100)])                  # gas recorded, legs wait in review
        self.assertTrue(self.review(router_out).startswith("DEX router"))
        self.assertEqual(self.cats(mixed), [("spam", -5), ("spam", 5)]); self.assertIsNone(self.review(mixed))  # pass-through
        self.assertEqual(s["review"], 1)                                          # only the DEX swap into ETH
        tg = {r[0] for r in self.c.execute("SELECT trade_group FROM ledger_entry WHERE tx_hash=%s AND category='swap'", (swap,))}
        self.assertEqual(len(tg), 1); self.assertIsNotNone(tg.pop())

    def test_escrow_place_fill(self):
        place = self.add(tx(W, BZ, selector=PLACE), e20(GHST, W, BZ, 240))
        fill = self.add(tx(X, BZ), e1155(TILE, X, W, 28, 2), bo_exec(327, W, X, TILE, 28, 120, 2))
        self.run_(); ref = "baazaar:buyorder:327"; esc = "escrow:" + BZ
        self.assertEqual(self.rows(place), [("escrow_out", esc, 240, ref), ("escrow_out", "wallet", -240, ref)])  # custody, not withdrawal
        self.assertEqual(self.rows(fill), [("nft_buy", esc, -240, ref), ("nft_buy", "wallet", 2, None)])         # paid from escrow
        tg = {r[0] for r in self.c.execute("SELECT trade_group FROM ledger_entry WHERE tx_hash=%s", (fill,))}
        self.assertEqual(len(tg), 1); self.assertIsNotNone(tg.pop())
        self.assertEqual(self.open_escrow(), {esc: 0})
        self.assertFalse(self.c.execute("SELECT 1 FROM ledger_entry WHERE category IN ('withdrawal','deposit')").fetchone())

    def test_escrow_place_cancel(self):
        place = self.add(tx(W, BZ, selector=PLACE), e20(GHST, W, BZ, 240))
        cancel = self.add(tx(W, BZ), e20(GHST, BZ, W, 240))
        self.run_(); esc = "escrow:" + BZ
        self.assertEqual(self.rows(cancel), [("escrow_return", esc, -240, None), ("escrow_return", "wallet", 240, None)])  # not a deposit
        self.assertEqual(self.open_escrow(), {esc: 0})
        self.assertFalse(self.c.execute("SELECT 1 FROM ledger_entry WHERE category IN ('withdrawal','deposit','income')").fetchone())

    def test_escrow_partial_fill_then_cancel(self):
        self.add(tx(W, BZ, selector=PLACE), e20(GHST, W, BZ, 300))                     # order: 3 @ 100
        fill = self.add(tx(X, BZ), e1155(TILE, X, W, 28, 1), bo_exec(400, W, X, TILE, 28, 100, 1))
        esc = "escrow:" + BZ; self.run_()
        self.assertEqual(self.rows(fill), [("nft_buy", esc, -100, "baazaar:buyorder:400"), ("nft_buy", "wallet", 1, None)])
        self.assertEqual(self.open_escrow(), {esc: 200})                              # only the filled portion leaves escrow
        cancel = self.add(tx(W, BZ), e20(GHST, BZ, W, 200)); self.run_()
        self.assertEqual(self.rows(cancel), [("escrow_return", esc, -200, "baazaar:buyorder:400"), ("escrow_return", "wallet", 200, "baazaar:buyorder:400")])
        self.assertEqual(self.open_escrow(), {esc: 0})

    def test_fill_without_escrow_goes_to_review(self):
        fill = self.add(tx(X, BZ), e1155(TILE, X, W, 28, 1), bo_exec(401, W, X, TILE, 28, 100, 1))
        self.run_(); self.assertEqual(self.review(fill), "buy-order fill without matching escrow")

    def test_gbm_bid_outbid_refund_and_win(self):
        esc = "escrow:" + GBM
        b1 = self.add(tx(W, GBM), e20(GHST, W, GBM, 100), bid(9, W, 100))
        refund = self.add(tx(X, GBM), e20(GHST, GBM, W, 105), bid(9, X, 200))       # outbid: bid back + 5% incentive
        b2 = self.add(tx(W, GBM), e20(GHST, W, GBM, 70), bid(10, W, 70))
        win = self.add(tx(X, GBM), e721(NFT, GBM, W, 77), claimed(10))
        self.run_()
        self.assertEqual(self.rows(refund), [("escrow_return", esc, -100, "gbm:auction:9"), ("escrow_return", "wallet", 100, "gbm:auction:9"),
                                             ("income", "wallet", 5, "gbm:auction:9")])
        self.assertEqual(self.rows(win), [("auction", esc, -70, "gbm:auction:10"), ("auction", "wallet", 1, None)])
        self.assertEqual(self.open_escrow(), {esc: 0})

    def test_bridged_mint_pending_then_manual(self):
        GOTCHI = BZ
        mint = self.add(e721(GOTCHI, ZERO, W, 954), bn=33_205_609)                     # not sent by W, inside the window
        self.run_()
        self.assertEqual(self.cats(mint), [("migration_in", 1)])                       # custody, never income
        lot = self.c.execute("SELECT id, basis_usdc, basis_status, chain_origin, basis_price_source FROM fifo_lot").fetchall()
        self.assertEqual(len(lot), 1); lid = lot[0][0]
        self.assertEqual(lot[0][1:], (None, "pending", 137, "polygon_carryover"))      # unknown, NOT zero
        self.assertEqual(classify.basis_totals(self.c, C), {"lots": 1, "pending_lots": 1, "manual_lots": 0, "basis_usdc_total_excl_pending": None})
        classify.set_manual_basis(self.c, lid, 123.45)
        r = self.c.execute("SELECT basis_usdc, basis_status, basis_price_source, basis_confidence FROM fifo_lot WHERE id=%s", (lid,)).fetchone()
        self.assertEqual((float(r[0]), r[1], r[2], round(r[3], 2)), (123.45, "manual", "manual", 0.2))
        self.run_()                                                                    # rebuild keeps the manual entry
        r = self.c.execute("SELECT id, basis_usdc, basis_status FROM fifo_lot").fetchone()
        self.assertEqual((float(r[1]), r[2]), (123.45, "manual"))
        classify.set_manual_basis(self.c, r[0], 200)
        self.assertEqual(self.c.execute("SELECT count(*), count(*) FILTER (WHERE superseded_at IS NULL) FROM manual_basis").fetchone(), (2, 1))
        self.assertEqual(float(classify.basis_totals(self.c, C)["basis_usdc_total_excl_pending"]), 200.0)
        # a sell from a pending lot gives proceeds and a pending (NULL) realized PnL
        self.c.execute("UPDATE fifo_lot SET basis_usdc=NULL, basis_status='pending'")
        did = self.c.execute("INSERT INTO lot_disposal(lot_id, qty, proceeds_usdc, cost_usdc) SELECT id, 1, 50, basis_usdc FROM fifo_lot RETURNING realized_pnl_usdc").fetchone()
        self.assertIsNone(did[0]); self.c.rollback()

    def test_mint_outside_window_or_sent_is_not_migration(self):
        own = self.add(tx(W, BZ), e721(BZ, ZERO, W, 1), bn=33_300_000)                  # wallet-sent mint
        late = self.add(e721(BZ, ZERO, W, 2), bn=40_000_000)
        self.run_()
        self.assertEqual(self.cats(own), [("fee", -100), ("income", 1)])
        self.assertEqual(self.cats(late), [("income", 1)])

    def test_spam_excluded_from_totals(self):
        self.add(e20(SPAM, X, W, 10**24))                                               # fake-token airdrop
        self.add(e20(USDC, X, W, 80))
        self.add(e20(USDC, X, W, 0))                                                    # poisoning
        self.run_()
        usdc = self.c.execute("SELECT id FROM asset WHERE contract=%s", (b(USDC),)).fetchone()[0]
        spam = self.c.execute("SELECT id FROM asset WHERE contract=%s", (b(SPAM),)).fetchone()[0]
        self.assertEqual(classify.totals(self.c, C), {usdc: 80})
        self.assertEqual(classify.totals(self.c, C, include_spam=True), {usdc: 80, spam: 10**24})
        self.assertEqual(self.c.execute("SELECT count(*) FROM ledger_entry WHERE category='spam' AND pnl_excluded").fetchone()[0], 2)
        self.assertEqual(self.c.execute("SELECT count(*) FROM review_queue").fetchone()[0], 0)

    def test_idempotent(self):
        self.add(tx(W, X), e20(USDC, W, X, 10), e20(GHST, X, W, 20)); self.add(e20(USDC, X, W, 0))
        self.add(tx(W, BZ, selector=PLACE), e20(GHST, W, BZ, 240)); self.add(tx(X, BZ), e1155(TILE, X, W, 28, 2), bo_exec(327, W, X, TILE, 28, 120, 2))
        self.add(e721(BZ, ZERO, W, 954), bn=33_205_609)
        self.run_(); a = classify.checksum(self.c, C); self.run_(); self.assertEqual(a, classify.checksum(self.c, C))

if __name__ == "__main__": unittest.main()
