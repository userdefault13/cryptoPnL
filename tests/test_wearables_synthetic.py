"""P1.1 BLOCKER: synthetic ToParent-then-FromParent (SYNTHETIC ONLY: stubbed HyperSync/RPC, no chain data).
Covers ingest.ingest_parent_transfers and verify.child_ledger / ledger aliasing.
Run: CRYPTOPNL_DSN=postgresql:///cryptopnl_unit11 .venv/bin/python -m unittest -v tests.test_wearables_synthetic"""
import json, os, unittest
os.environ.setdefault("ENVIO_API_TOKEN", "test")
from cryptopnl import db, ingest, sources, verify
from cryptopnl.sources import T_TO_PARENT, T_FROM_PARENT, T1155S

D = "0xa99c4b08201f2913db8d28e71d020c4298f29dbf"      # Aavegotchi Diamond (canonical + parent)
WD = "0x052e6c114a166b0e91c2340370d72d4c33752b4b"     # Wearable Diamond (1155 emitter)
W = "0x000000000000000000000000000000000000beef"
GOTCHI, TYPE, V = 954, 23, 3
def h(n): return "0x" + format(n, "064x")
def t(a): return "0x" + a[2:].rjust(64, "0")

class FakeRPC:
    def __init__(self, url): pass
    def safe_head(self): return 1000
    def block(self, n): return n, h(n), 1_700_000_000 + n

def plog(topic0, blk, li, value, parent=D):
    return {"block_number": hex(blk), "block_hash": h(blk), "transaction_hash": h(10_000 + blk), "log_index": hex(li), "address": D,
            "topic0": topic0, "topic1": t(parent), "topic2": h(GOTCHI), "topic3": h(TYPE), "data": h(value)}

class TestToParentThenFromParent(unittest.TestCase):
    def setUp(self):
        self.conn = c = db.connect(); db.migrate(c)
        for tb in ("raw_event", "block", "sync_cursor", "sync_cursor_global", "parent_scan", "wallet"): c.execute(f"DELETE FROM {tb}")
        ingest.wallet_id(c, 8453, W)
        def ins(blk, li, kind, payload):
            c.execute("""INSERT INTO raw_event(chain_id,tx_hash,log_index,block_number,block_hash,source,kind,payload)
                         VALUES (8453,%s,%s,%s,%s,'hypersync',%s,%s)""", (db.b(h(10_000 + blk)), li, blk, db.b(h(blk)), kind, json.dumps(payload)))
        z = "0x" + "0" * 40
        ins(100, 0, "erc721_transfer", {"contract": D, "from": z, "to": W, "token_id": str(GOTCHI), "value": "1"})              # wallet owns gotchi
        ins(110, 0, "erc1155_single", {"contract": WD, "operator": W, "from": z, "to": W, "ids": [str(TYPE)], "values": [str(V)]})  # mint V to owner
        # equip at 200: owner -> diamond (1155) + ToParent; unequip at 300: diamond -> owner + FromParent
        ins(200, 0, "erc1155_single", {"contract": WD, "operator": W, "from": W, "to": D, "ids": [str(TYPE)], "values": [str(V)]})
        ins(300, 0, "erc1155_single", {"contract": WD, "operator": W, "from": D, "to": W, "ids": [str(TYPE)], "values": [str(V)]})
        c.commit()
        self._rpc, self._pj = ingest.RPC, sources.post_json
        ingest.RPC = FakeRPC
        logs = [plog(T_TO_PARENT, 200, 1, V), plog(T_FROM_PARENT, 300, 1, V),
                plog(T_TO_PARENT, 250, 2, 99, parent="0x00000000000000000000000000000000000000aa")]   # foreign parent: must be ignored
        sources.post_json = lambda name, lim, url, body, headers=None, **k: {"data": [{"logs": logs, "blocks": []}], "next_block": 1001}
    def tearDown(self):
        ingest.RPC, sources.post_json = self._rpc, self._pj; self.conn.close()

    def owner(self, b): return verify.ledger(self.conn, 8453, W, b).get((D, "erc1155", str(TYPE)), 0)
    def child(self, b): return verify.child_ledger(self.conn, 8453, [GOTCHI], b).get((GOTCHI, TYPE), 0)

    def test_to_then_from_parent_custody_only(self):
        ingest.ingest_parent_transfers(self.conn, 8453, W, log=lambda *_: None)
        # child balance +v then -v
        self.assertEqual([self.child(b) for b in (150, 200, 299, 300)], [0, V, V, 0])
        # owner + children unchanged across equip/unequip (custody move, not a disposal)
        self.assertEqual([self.owner(b) + self.child(b) for b in (150, 200, 299, 300)], [V, V, V, V])
        self.assertEqual([self.owner(b) for b in (150, 200, 300)], [V, 0, V])
        # idempotent re-insert (cursor reset forces a full re-scan of the same logs)
        n1 = self.conn.execute("SELECT count(*), md5(string_agg(encode(tx_hash,'hex')||log_index, ',' ORDER BY tx_hash, log_index)) FROM raw_event").fetchone()
        self.conn.execute("DELETE FROM parent_scan"); self.conn.commit()
        ingest.ingest_parent_transfers(self.conn, 8453, W, log=lambda *_: None)
        n2 = self.conn.execute("SELECT count(*), md5(string_agg(encode(tx_hash,'hex')||log_index, ',' ORDER BY tx_hash, log_index)) FROM raw_event").fetchone()
        self.assertEqual(n1, n2)
        # no disposal rows: parent events are only wearable_to/from_parent, never 1155/erc20 transfers or disposals
        kinds = {r[0] for r in self.conn.execute("SELECT DISTINCT kind FROM raw_event WHERE source='hypersync_parent'")}
        self.assertEqual(kinds, {"wearable_to_parent", "wearable_from_parent"})
        self.assertEqual(self.conn.execute("SELECT count(*) FROM raw_event WHERE kind ILIKE '%dispos%' OR kind ILIKE '%sell%'").fetchone()[0], 0)
        # foreign parent_contract row is stored but excluded from the child ledger
        self.assertEqual(self.child(260), V)

if __name__ == "__main__": unittest.main()
