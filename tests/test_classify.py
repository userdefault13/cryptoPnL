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
BRIDGE = "0xf52398257a254d541f392667600901f710a006ed"; GOTCHI_SEL = "0xf55b061c"; TILE_SEL = "0x91b06c6e"
CCTP_MT = "0xad09780d193884d503182ad4588450c416d6f9d4"
FG = "0xab59ca4a16925b0a4bac5026c94beb20a29df479"; MINTBATCH = "0x5e41ee65"; EXEC7821 = "0xe9ae5c53"
FGC = "0xe46b8902dad841476d9fee081f1d62ae317206a9"; MASSMINT = "0x88f351bb"   # FAKE Gotchi Cards (P2.1)
FACETS = ("0x04d1424f15846e88285478e19f413aeb080740fc", "0x3aa42d4e944ff4696284573a83829e94435c0655")
def meta(frm, to, sel): return ("tx_meta", {"from": frm, "to": to, "selector": sel, "value": "0"})   # RPC tx_meta (log_index -3)

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
            self.c.execute("INSERT INTO raw_event VALUES (%s,%s,%s,%s,%s,'t',%s,%s)", (C, b(h), {"tx": -1, "tx_meta": -3}.get(k, i), bn, b(th(10**6 + bn)), k, json.dumps(p)))
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
        self.run_(); self.assertEqual(self.review(fill), "buy-order fill: no matching escrow for the order id")

    def test_b2_fill_matches_order_amount(self):
        esc = "escrow:" + BZ
        self.add(tx(W, BZ, selector=PLACE), e20(GHST, W, BZ, 100))                    # order A = 100
        self.add(tx(W, BZ, selector=PLACE), e20(GHST, W, BZ, 50))                     # order B = 50
        fb = self.add(tx(X, BZ), e1155(TILE, X, W, 28, 1), bo_exec(502, W, X, TILE, 28, 50, 1))   # fills B, not FIFO A
        self.run_()
        self.assertEqual(self.rows(fb), [("nft_buy", esc, -50, "baazaar:buyorder:502"), ("nft_buy", "wallet", 1, None)])
        refs = {r[0]: int(r[1]) for r in self.c.execute("SELECT coalesce(escrow_ref,'-'), sum(qty) FROM ledger_entry WHERE location=%s GROUP BY 1", (esc,))}
        self.assertEqual(refs, {"-": 100, "baazaar:buyorder:502": 0})                 # A still open and unlinked
        fa = self.add(tx(X, BZ), e1155(TILE, X, W, 28, 1), bo_exec(501, W, X, TILE, 28, 100, 1)); self.run_()
        self.assertEqual(self.rows(fa), [("nft_buy", esc, -100, "baazaar:buyorder:501"), ("nft_buy", "wallet", 1, None)])
        self.assertEqual(self.open_escrow(), {esc: 0})

    def test_b2_linked_order_first_and_ambiguous_review(self):
        self.add(tx(W, BZ, selector=PLACE), e20(GHST, W, BZ, 300))                    # order 600: 3 @ 100
        self.add(tx(X, BZ), e1155(TILE, X, W, 28, 1), bo_exec(600, W, X, TILE, 28, 100, 1))   # links 600 (partial)
        self.add(tx(W, BZ, selector=PLACE), e20(GHST, W, BZ, 100))                    # order 601: 1 @ 100
        f2 = self.add(tx(X, BZ), e1155(TILE, X, W, 28, 1), bo_exec(600, W, X, TILE, 28, 100, 1))  # linked entry wins over the exact 100
        self.run_(); self.assertEqual(self.rows(f2)[0], ("nft_buy", "escrow:" + BZ, -100, "baazaar:buyorder:600"))
        self.add(tx(W, BZ, selector=PLACE), e20(GHST, W, BZ, 100))                    # second unlinked 100: ambiguous
        amb = self.add(tx(X, BZ), e1155(TILE, X, W, 28, 1), bo_exec(602, W, X, TILE, 28, 100, 1)); self.run_()
        self.assertEqual(self.review(amb), "buy-order fill: ambiguous matching escrow for the order id")

    def test_b1_unclaimed_diamond_ghst_goes_to_review(self):
        out_ = self.add(tx(W, BZ, selector="0x12345678"), e20(GHST, W, BZ, 10))         # not a placement selector
        in_ = self.add(tx(X, BZ), e20(GHST, BZ, W, 10))                                 # no open escrow
        gin = self.add(tx(X, GBM), e20(GHST, GBM, W, 10))                               # GBM: no escrow, no claim
        self.run_()
        self.assertEqual(self.review(out_), "token to/from Baazaar diamond not claimed by an escrow/market rule")
        self.assertEqual(self.review(in_), "token to/from Baazaar diamond not claimed by an escrow/market rule")
        self.assertTrue(self.review(gin).startswith("gbm"))
        self.assertFalse(self.c.execute("SELECT 1 FROM ledger_entry WHERE category IN ('withdrawal','deposit')").fetchone())

    def test_untracked_legs_in_self_sent_txs(self):
        swap = self.add(tx(W, X), e20(USDC, W, X, 10), e20(SPAM, X, W, 5))             # self-sent swap USDC -> LINK-like
        mint = self.add(tx(W, X), e721(SPAM, ZERO, W, 9))                               # self-sent non-allowlisted mint
        send = self.add(tx(W, X), e20(SPAM, W, X, 3))
        s = self.run_()
        self.assertEqual(self.cats(swap), [("fee", -100), ("swap", -10), ("untracked", 5)])
        self.assertEqual(self.cats(mint), [("fee", -100), ("untracked", 1)])
        self.assertEqual(self.cats(send), [("fee", -100), ("untracked", -3)])
        r = dict(self.c.execute("SELECT category, bool_and(pnl_excluded) FROM ledger_entry WHERE category IN ('swap','untracked') GROUP BY 1").fetchall())
        self.assertEqual(r, {"swap": False, "untracked": True})
        self.assertIsNone(self.c.execute("SELECT trade_group FROM ledger_entry WHERE category='untracked' AND tx_hash=%s", (swap,)).fetchone()[0])
        self.assertEqual(s["review"], 0)
        self.assertEqual(self.c.execute("SELECT count(*) FROM fifo_lot").fetchone()[0], 0)    # no lot for untracked
        self.assertEqual(classify.report(self.c, C)["txs_by_category"].get("untracked"), 2)

    def test_bridge_in_cctp_par_else_review(self):
        ok = self.add(e20(USDC, ZERO, W, 5_000_000), meta(X, CCTP_MT, "0x57ecfd28"))
        bad = self.add(e20(USDC, ZERO, W, 1_000_000), meta(X, X, "0x57ecfd28"))
        nometa = self.add(e20(USDC, ZERO, W, 2_000_000))
        self.run_()
        self.assertEqual(self.cats(ok), [("bridge_in", 5_000_000)])
        lot = self.c.execute("SELECT basis_usdc, basis_price_source, basis_confidence, basis_confidence_label, basis_status FROM fifo_lot").fetchall()
        self.assertEqual([(float(a), b_, round(c, 2), d, e) for a, b_, c, d, e in lot], [(5.0, "numeraire", 1.0, "high", "resolved")])
        self.assertEqual(self.review(bad), "USDC mint not via Circle CCTP (tx.to unverified)")
        self.assertEqual(self.review(nometa), "USDC mint not via Circle CCTP (tx.to unverified)")
        rep = classify.report(self.c, C); json.dumps(rep)                                 # report must serialise (Decimal basis)
        self.assertEqual(rep["lots"]["basis_usdc_total_excl_pending"], "5")

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
        mint = self.add(e721(GOTCHI, ZERO, W, 954), meta(BRIDGE, BZ, GOTCHI_SEL), bn=33_205_609)   # bridge sender, listed selector
        self.run_()
        self.assertEqual(self.cats(mint), [("migration_in", 1)])                       # custody, never income
        lot = self.c.execute("SELECT id, basis_usdc, basis_status, chain_origin, basis_price_source, basis_confidence_label FROM fifo_lot").fetchall()
        self.assertEqual(len(lot), 1); lid = lot[0][0]
        self.assertEqual(lot[0][1:], (None, "pending", 137, None, None))               # unknown, NOT zero; no source yet
        self.assertEqual(classify.basis_totals(self.c, C), {"lots": 1, "pending_lots": 1, "manual_lots": 0, "basis_usdc_total_excl_pending": None})
        classify.set_manual_basis(self.c, lid, 123.45)
        r = self.c.execute("SELECT basis_usdc, basis_status, basis_price_source, basis_confidence, basis_confidence_label FROM fifo_lot WHERE id=%s", (lid,)).fetchone()
        self.assertEqual((float(r[0]), r[1], r[2], round(r[3], 2), r[4]), (123.45, "manual", "manual", 0.2, "low"))
        for bad in (-1, "abc", "nan", "inf", None):
            with self.assertRaises(ValueError): classify.set_manual_basis(self.c, lid, bad)
        with self.assertRaises(ValueError): classify.set_manual_basis(self.c, None, 1)
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

    def test_migration_selector_rule(self):
        own = self.add(tx(W, BZ, selector=GOTCHI_SEL), e721(BZ, ZERO, W, 1), bn=33_300_000)        # re-mint sent by the wallet itself
        late = self.add(e721(BZ, ZERO, W, 2), meta(BRIDGE, BZ, GOTCHI_SEL), bn=40_000_000)        # outside window: warning only
        tile = self.add(e1155(TILE, ZERO, W, 28, 3), meta(BRIDGE, TILE, TILE_SEL), bn=33_300_001)
        unlisted = self.add(e721(BZ, ZERO, W, 3), meta(BRIDGE, BZ, "0xdeadbeef"), bn=33_300_002)  # bridge sender, unlisted selector
        wrong_to = self.add(e721(BZ, ZERO, W, 4), meta(BRIDGE, TILE, GOTCHI_SEL), bn=33_300_003)  # listed selector, wrong target
        own_other = self.add(tx(W, BZ, selector="0x11111111"), e721(BZ, ZERO, W, 5), bn=33_300_004)  # own mint, unlisted: normal rules
        other = self.add(e721(BZ, ZERO, W, 6), meta(X, BZ, GOTCHI_SEL), bn=33_300_005)            # not the bridge sender
        fake = self.add(e721(SPAM, ZERO, W, 7), meta(BRIDGE, SPAM, "0x5e41ee65"), bn=33_222_797)   # bridge sender, non-allowlisted NFT
        s = self.run_()
        self.assertEqual(self.cats(own), [("fee", -100), ("migration_in", 1)])
        self.assertEqual(self.cats(late), [("migration_in", 1)])
        self.assertEqual(self.cats(tile), [("migration_in", 3)])
        self.assertEqual(self.review(unlisted), "bridge sender mint with unlisted selector/target")
        self.assertEqual(self.review(wrong_to), "bridge sender mint with unlisted selector/target")
        self.assertEqual(self.cats(own_other), [("fee", -100), ("income", 1)])
        self.assertEqual(self.cats(other), [("income", 1)])
        self.assertEqual(self.review(fake), "bridge sender mint with unlisted selector/target")      # never spam
        self.assertEqual(len(s["warnings"]), 1); self.assertIn("outside block window", s["warnings"][0])
        self.assertEqual(self.c.execute("SELECT count(*) FROM fifo_lot WHERE basis_status='pending'").fetchone()[0], 3)

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
        self.add(e721(BZ, ZERO, W, 954), meta(BRIDGE, BZ, GOTCHI_SEL), bn=33_205_609); self.add(tx(W, X), e20(USDC, W, X, 10), e20(SPAM, X, W, 5))
        self.add(e20(USDC, ZERO, W, 5_000_000), meta(X, CCTP_MT, "0x57ecfd28"))
        self.run_(); a = classify.checksum(self.c, C); self.run_(); self.assertEqual(a, classify.checksum(self.c, C))

    def test_b2_exhausted_order_never_claims_new_placement(self):     # architect BLOCKER, 3c8b056
        esc = "escrow:" + BZ
        self.add(tx(W, BZ, selector=PLACE), e20(GHST, W, BZ, 300))
        self.add(tx(X, BZ), e1155(TILE, X, W, 28, 3), bo_exec(3, W, X, TILE, 28, 100, 3))     # fill ord3 3x100: exact, links
        self.add(tx(W, BZ, selector=PLACE), e20(GHST, W, BZ, 200))
        late = self.add(tx(X, BZ), e1155(TILE, X, W, 28, 1), bo_exec(3, W, X, TILE, 28, 100, 1))  # ord3 already used up
        self.run_()
        self.assertEqual(self.review(late), "escrow fill/return larger than open escrow")
        self.assertEqual(self.open_escrow(), {esc: 200})                                      # the 200 is not consumed
        self.assertIsNone(self.c.execute("SELECT 1 FROM ledger_entry WHERE tx_hash=%s", (late,)).fetchone())

    def test_b2_partial_fallback_conditions(self):
        self.add(tx(W, BZ, selector=PLACE), e20(GHST, W, BZ, 300)); self.add(tx(W, BZ, selector=PLACE), e20(GHST, W, BZ, 300))
        two = self.add(tx(X, BZ), e1155(TILE, X, W, 28, 1), bo_exec(7, W, X, TILE, 28, 100, 1))   # two equal multiples
        self.run_(); self.assertEqual(self.review(two), "buy-order fill: ambiguous matching escrow for the order id")
        self.setUp()
        self.add(tx(W, BZ, selector=PLACE), e20(GHST, W, BZ, 250))                            # not an integer multiple of 100
        none_ = self.add(tx(X, BZ), e1155(TILE, X, W, 28, 1), bo_exec(8, W, X, TILE, 28, 100, 1))
        big = self.add(tx(X, BZ), e1155(TILE, X, W, 28, 5), bo_exec(9, W, X, TILE, 50, 100, 5))   # 500 > 250: remaining < 0
        self.run_()
        self.assertEqual(self.review(none_), "buy-order fill: no matching escrow for the order id")
        self.assertEqual(self.review(big), "buy-order fill: no matching escrow for the order id")

    def test_null_rpc_lookup_mint_goes_to_review(self):
        nul = self.add(e721(NFT, ZERO, W, 1), ("tx_meta", {"from": None, "to": None, "selector": None, "value": None, "lookup_null": True}))
        nometa = self.add(e721(NFT, ZERO, W, 2))
        self.run_()
        for h in (nul, nometa): self.assertEqual(self.review(h), "allowlisted mint from 0x0 without tx metadata (RPC lookup null)")
        self.assertFalse(self.c.execute("SELECT 1 FROM ledger_entry WHERE category='income'").fetchone())

    def test_eip7702_execute_wrapper_mint_goes_to_review(self):
        wrap = self.add(tx(W, W, selector=EXEC7821), e721(NFT, ZERO, W, 3))
        wrap_m = self.add(tx(W, W, selector=EXEC7821), e721(BZ, ZERO, W, 4), bn=33_300_000)   # would-be re-mint: still review
        plain = self.add(tx(W, W, selector=EXEC7821), e20(USDC, W, X, 10))                   # no mint: normal rules
        self.run_()
        for h in (wrap, wrap_m): self.assertEqual(self.review(h), "EIP-7702 execute wrapper with mint from 0x0: inner call not decoded")
        self.assertIsNone(self.review(plain))
        self.assertFalse(self.c.execute("SELECT 1 FROM ledger_entry WHERE category IN ('income','migration_in')").fetchone())

    def test_ghst_to_gbm_without_bid_goes_to_review(self):
        h = self.add(tx(W, GBM), e20(GHST, W, GBM, 50)); self.run_()
        self.assertTrue(self.review(h).startswith("gbm"))
        self.assertEqual(self.open_escrow(), {})

    def test_fake_gotchis_mintbatch_only_on_that_contract(self):
        fg = self.add(e721(FG, ZERO, W, 11), meta(BRIDGE, FG, MINTBATCH), bn=33_222_797)
        tile = self.add(e1155(TILE, ZERO, W, 28, 1), meta(BRIDGE, TILE, MINTBATCH), bn=33_222_798)   # mintBatch elsewhere
        self.run_()
        self.assertEqual(self.cats(fg), [("migration_in", 1)])
        self.assertIsNotNone(self.review(tile))
        lot = self.c.execute("SELECT basis_status, basis_usdc FROM fifo_lot").fetchall()
        self.assertEqual(lot, [("pending", None)])

    def test_eip7702_non_allowlisted_mint_is_swap(self):   # shaped like Base 0x4a5a7c6c…f697 (architect approval condition)
        LP = "0x7c307e128efa31f540f2e2d976c995e0b65f51f6"; POOL = "0x0a2854fbbd9b3ef66f17d47284e7f899b9509330"
        h = self.add(tx(W, W, selector=EXEC7821), e20(LP, ZERO, W, 5024135863), e20(LP, W, POOL, 9478318086722626),
                     e20(USDC, POOL, W, 25856803))
        s = self.run_()
        self.assertIsNone(self.review(h)); self.assertEqual(s["review"], 0)
        r = self.c.execute("""SELECT category, qty, pnl_excluded, price_usdc, price_source, price_confidence_label FROM ledger_entry
                              WHERE tx_hash=%s AND category<>'fee' ORDER BY log_index""", (h,)).fetchall()
        self.assertEqual([(c, int(q), p, None if u is None else int(u), ps, cl) for c, q, p, u, ps, cl in r],
                         [("untracked", 5024135863, True, None, None, None), ("untracked", -9478318086722626, True, None, None, None),
                          ("swap", 25856803, False, 1, "numeraire", "high")])
        self.assertEqual(classify.report(self.c, C)["txs_by_category"].get("swap"), 1)

    def test_fake_gotchi_cards_massmint_migration_lots_per_id(self):   # P2.1
        def batch(c, f, t, ids, vals): return ("erc1155_batch", {"contract": c, "operator": f, "from": f, "to": t, "ids": [str(i) for i in ids], "values": [str(v) for v in vals]})
        one = self.add(e1155(FGC, ZERO, W, 0, 3), meta(BRIDGE, FGC, MASSMINT), bn=33_222_090)            # shaped like 0x7ac8afa8…
        two = self.add(batch(FGC, ZERO, W, [1, 2], [2, 5]), meta(BRIDGE, FGC, MASSMINT), bn=33_222_091)  # batch: one lot per (contract, id)
        other = self.add(e1155(TILE, ZERO, W, 28, 1), meta(BRIDGE, TILE, MASSMINT), bn=33_222_092)      # massMint on another contract
        wrongsel = self.add(e1155(FGC, ZERO, W, 0, 1), meta(BRIDGE, FGC, MINTBATCH), bn=33_222_093)     # FG's selector on the cards
        facet = self.add(e1155(FACETS[0], ZERO, W, 0, 1), meta(BRIDGE, FACETS[0], MASSMINT), bn=33_222_094)  # facet-like: not allowlisted
        self.run_()
        self.assertEqual(self.cats(one), [("migration_in", 3)])
        self.assertEqual(sorted(self.cats(two)), [("migration_in", 2), ("migration_in", 5)])
        for h in (other, wrongsel, facet): self.assertIsNotNone(self.review(h))
        lots = self.c.execute("""SELECT a.token_id, l.qty_open, l.basis_status, l.basis_usdc, l.basis_price_source, l.chain_origin
                                 FROM fifo_lot l JOIN asset a ON a.id=l.asset_id ORDER BY a.token_id""").fetchall()
        self.assertEqual([(str(t), int(q), st, b_, ps, o) for t, q, st, b_, ps, o in lots],
                         [("0", 3, "pending", None, None, 137), ("1", 2, "pending", None, None, 137), ("2", 5, "pending", None, None, 137)])

if __name__ == "__main__": unittest.main()
