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
def tx(frm, to, value=0, fee=100, status="1"):
    return ("tx", {"from": frm, "to": to, "value": str(value), "fee": str(fee), "status": status, "selector": "0x"})
def e20(c, f, t, v): return ("erc20_transfer", {"contract": c, "from": f, "to": t, "value": str(v)})
def e721(c, f, t, i): return ("erc721_transfer", {"contract": c, "from": f, "to": t, "token_id": str(i), "value": "1"})
def mkt(c, ev): return ("market_" + ev, {"contract": c, "event": ev})

class T(unittest.TestCase):
    def setUp(self):
        self.c = db.connect(); db.migrate(self.c)
        for t in ("ledger_entry", "review_queue", "raw_event", "block", "sync_cursor", "sync_cursor_global", "asset", "wallet"):
            self.c.execute(f"DELETE FROM {t}")
        for a in (W, W2): self.c.execute("INSERT INTO wallet(chain_id,address,wallet_group) VALUES (%s,%s,'g')", (C, b(a)))
        self.c.commit(); self.n = 0
    def tearDown(self):
        for t in ("ledger_entry", "review_queue", "asset"): self.c.execute(f"DELETE FROM {t}")
        self.c.commit(); self.c.close()
    def add(self, *evs):
        self.n += 1; h = th(self.n)
        self.c.execute("INSERT INTO block VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING", (C, self.n, b(th(10**6 + self.n)), datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)))
        for i, (k, p) in enumerate(evs):
            self.c.execute("INSERT INTO raw_event VALUES (%s,%s,%s,%s,%s,'t',%s,%s)", (C, b(h), -1 if k == "tx" else i, self.n, b(th(10**6 + self.n)), k, json.dumps(p)))
        self.c.commit(); return b(h)
    def cats(self, h, wallet=W):
        return sorted((r[0], int(r[1])) for r in self.c.execute(
            "SELECT category, qty FROM ledger_entry l JOIN wallet w ON w.id=l.wallet_id WHERE tx_hash=%s AND w.address=%s", (h, b(wallet))))
    def review(self, h): r = self.c.execute("SELECT reason FROM review_queue WHERE tx_hash=%s", (h,)).fetchone(); return r and r[0]
    def run_(self): return classify.classify(self.c, C, log=lambda *_: None)

    def test_rules(self):
        fee_only = self.add(tx(W, USDC))
        failed = self.add(tx(W, X, value=5, status="0"))
        swap = self.add(tx(W, X), e20(USDC, W, X, 10), e20(GHST, X, W, 20))
        swap_native = self.add(tx(W, ROUTER, value=7), e20(GHST, X, W, 20))
        buy = self.add(tx(W, X), e20(GHST, W, X, 30), e721(NFT, X, W, 1))
        sale = self.add(tx(X, X), e721(NFT, W, X, 2), e20(GHST, X, W, 40))
        auction = self.add(tx(W, GBM), e20(GHST, W, GBM, 50), mkt(GBM, "Auction_BidPlaced"))
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
        self.assertEqual(self.cats(auction), [("auction", -50), ("fee", -100)])
        self.assertEqual(self.cats(internal), [("fee", -100), ("transfer_internal", -60)])
        self.assertEqual(self.cats(internal, W2), [("transfer_internal", 60)])
        self.assertEqual(self.cats(income), [("fee", -100), ("income", 70)])
        self.assertEqual(self.cats(spam_mint), [("deposit", 1)])                  # unsolicited, non-allowlisted mint
        self.assertEqual(self.cats(deposit), [("deposit", 80)])
        self.assertEqual(self.cats(withdrawal), [("fee", -100), ("withdrawal", -90)])
        self.assertTrue(self.review(poison).startswith("zero-value"))
        self.assertEqual(self.cats(router_out), [("fee", -100)])                  # gas recorded, legs wait in review
        self.assertTrue(self.review(router_out).startswith("DEX router"))
        self.assertEqual(self.review(mixed), "mixed in/out legs")
        self.assertEqual(s["review"], 3)
        tg = {r[0] for r in self.c.execute("SELECT trade_group FROM ledger_entry WHERE tx_hash=%s AND category='swap'", (swap,))}
        self.assertEqual(len(tg), 1); self.assertIsNotNone(tg.pop())

    def test_idempotent(self):
        self.add(tx(W, X), e20(USDC, W, X, 10), e20(GHST, X, W, 20)); self.add(e20(USDC, X, W, 0))
        self.run_(); a = classify.checksum(self.c, C); self.run_(); self.assertEqual(a, classify.checksum(self.c, C))

if __name__ == "__main__": unittest.main()
