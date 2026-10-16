"""Unit tests for PR #1 review blockers. Offline: HyperSync/RPC are stubbed; uses a throwaway local Postgres DB.
Run: CRYPTOPNL_DSN=postgresql:///cryptopnl_unit ENVIO_API_TOKEN=x .venv/bin/python -m unittest -v tests.test_review_fixes"""
import os, unittest
os.environ.setdefault("ENVIO_API_TOKEN", "test")
from cryptopnl import db, ingest, sources

W = "0x000000000000000000000000000000000000dead"
def h(n): return "0x" + format(n, "064x")

class FakeRPC:
    pruned_below = None
    def __init__(self, url): pass
    def safe_head(self): return 1000
    def block(self, n):
        if self.pruned_below is not None and isinstance(n, int) and n < self.pruned_below:
            raise RuntimeError("rpc error: block pruned (code -32000)")
        return n, h(n), 1_700_000_000 + n

class Base(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(); db.migrate(self.conn)
        for t in ("raw_event", "block", "sync_cursor", "sync_cursor_global", "wallet"):
            self.conn.execute(f"DELETE FROM {t}")
        self.conn.commit()
        self._rpc = ingest.RPC; ingest.RPC = FakeRPC; FakeRPC.pruned_below = None
    def tearDown(self):
        ingest.RPC = self._rpc; sources.post_json = self._pj if hasattr(self, "_pj") else sources.post_json; self.conn.close()

class TestCursorStopsAtLastReturnedBlock(Base):
    def test_cursor_stops_at_last_returned_block_when_loop_ends_early(self):
        calls = []
        def fake_post(name, lim, url, body, headers=None, **k):
            calls.append(body["from_block"])
            # page 1 covers [0, 499]; page 2 returns a non-advancing next_block -> loop must stop early
            nb = 500 if body["from_block"] == 0 else body["from_block"]
            return {"data": [], "next_block": nb}
        self._pj = sources.post_json; sources.post_json = fake_post
        ingest.ingest_wallet(self.conn, 8453, W, log=lambda *_: None)
        last, hsh = self.conn.execute("SELECT last_block, last_block_hash FROM sync_cursor").fetchone()
        self.assertEqual(calls, [0, 500])
        self.assertEqual(last, 499, "cursor must be the last block HyperSync actually covered, not safe head 1000")
        self.assertEqual(db.hx(hsh), h(499))
    def test_cursor_reaches_head_when_fully_covered(self):
        self._pj = sources.post_json
        sources.post_json = lambda name, lim, url, body, headers=None, **k: {"data": [], "next_block": 1001}
        ingest.ingest_wallet(self.conn, 8453, W, log=lambda *_: None)
        self.assertEqual(self.conn.execute("SELECT last_block FROM sync_cursor").fetchone()[0], 1000)

class TestMarketplaceCheckpointPerPage(Base):
    def test_marketplace_checkpoint_per_page_reaches_head(self):
        seen = []
        def fake_post(name, lim, url, body, headers=None, **k):
            f = body["from_block"]; nb = {33315000: 33315400, 33315400: 33315800}.get(f, 1001)
            return {"data": [], "next_block": nb}
        self._pj = sources.post_json; sources.post_json = fake_post
        from cryptopnl.config import MARKETPLACE
        old = MARKETPLACE[8453]["start_block"]
        FakeRPC.safe_head = lambda self: 33316000
        orig = ingest.store_blocks
        def spy(conn, chain, blocks):
            r = conn.execute("SELECT last_block FROM sync_cursor_global").fetchone(); seen.append(r[0] if r else None)
        ingest.store_blocks = spy
        try:
            sources.post_json = lambda name, lim, url, body, headers=None, **k: {"data": [], "next_block": {33315000: 33315400, 33315400: 33315800}.get(body["from_block"], 33316001)}
            ingest.ingest_marketplace(self.conn, 8453, log=lambda *_: None)
        finally:
            ingest.store_blocks = orig; FakeRPC.safe_head = lambda self: 1000
        self.assertEqual(seen, [None, 33315399, 33315799], "cursor checkpointed after each page")
        self.assertEqual(self.conn.execute("SELECT last_block FROM sync_cursor_global").fetchone()[0], 33316000)

class TestPrunedFinalOnlyOnSepolia(Base):
    def _seed(self, chain):
        wid = ingest.wallet_id(self.conn, chain, W)
        self.conn.execute("INSERT INTO sync_cursor(source,wallet_id,last_block,last_block_hash) VALUES ('hypersync',%s,100,%s)", (wid, db.b(h(100))))
        self.conn.commit(); FakeRPC.pruned_below = 10_000
    def test_pruned_block_raises_on_base_mainnet(self):
        self._seed(8453)
        with self.assertRaises(RuntimeError):
            ingest.reorg_check(self.conn, 8453, FakeRPC(""), log=lambda *_: None)
    def test_pruned_block_treated_final_on_base_sepolia(self):
        self._seed(84532)
        self.assertIsNone(ingest.reorg_check(self.conn, 84532, FakeRPC(""), log=lambda *_: None))

if __name__ == "__main__": unittest.main()
