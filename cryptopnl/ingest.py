import json, os, datetime
from .db import b, hx
from .sources import RPC, HyperSyncWalletLogs, TRANSFER, T1155S, T1155B, h2i
from .config import CHAINS, REORG_CHECK_BLOCKS, REORG_WINDOW

def addr_of(topic): return "0x" + topic[-40:].lower()
def words(data):
    d = data[2:] if data and data.startswith("0x") else (data or "")
    return [int(d[i:i+64], 16) for i in range(0, len(d), 64)]

def decode(l):
    t0 = l.get("topic0"); t1, t2, t3 = l.get("topic1"), l.get("topic2"), l.get("topic3")
    c = l["address"].lower()
    if t0 == TRANSFER and t3:
        return "erc721_transfer", {"contract": c, "from": addr_of(t1), "to": addr_of(t2), "token_id": str(int(t3, 16)), "value": "1"}
    if t0 == TRANSFER:
        w = words(l.get("data"))
        return "erc20_transfer", {"contract": c, "from": addr_of(t1), "to": addr_of(t2), "value": str(w[0] if w else 0)}
    if t0 == T1155S:
        w = words(l["data"])
        return "erc1155_single", {"contract": c, "operator": addr_of(t1), "from": addr_of(t2), "to": addr_of(t3),
                                  "ids": [str(w[0])], "values": [str(w[1])]}
    if t0 == T1155B:
        w = words(l["data"]); oi, ov = w[0] // 32, w[1] // 32
        ids = w[oi + 1: oi + 1 + w[oi]]; vals = w[ov + 1: ov + 1 + w[ov]]
        return "erc1155_batch", {"contract": c, "operator": addr_of(t1), "from": addr_of(t2), "to": addr_of(t3),
                                 "ids": [str(x) for x in ids], "values": [str(x) for x in vals]}
    return None, None

def wallet_id(conn, chain, address, label=None):
    r = conn.execute("INSERT INTO wallet(chain_id,address,label) VALUES (%s,%s,%s) ON CONFLICT (chain_id,address) DO UPDATE SET label=COALESCE(EXCLUDED.label,wallet.label) RETURNING id",
                     (chain, b(address), label)).fetchone()
    conn.commit(); return r[0]

def reorg_check(conn, chain, rpc, log=print):
    """Re-check cursor hashes + stored blocks within REORG_WINDOW of the cursor. On mismatch delete >= fork and rewind.
    Blocks the RPC no longer serves (pruned) are treated as final."""
    curs = conn.execute("""SELECT c.last_block, c.last_block_hash FROM sync_cursor c JOIN wallet w ON w.id=c.wallet_id
                           WHERE w.chain_id=%s AND c.source='hypersync' AND c.last_block_hash IS NOT NULL""", (chain,)).fetchall()
    if not curs: return None
    top = max(n for n, _ in curs)
    rows = dict(conn.execute("SELECT number, hash FROM block WHERE chain_id=%s AND number >= %s ORDER BY number DESC LIMIT %s",
                             (chain, top - REORG_WINDOW, REORG_CHECK_BLOCKS)).fetchall())
    checks = {n: hx(h) for n, h in rows.items()}
    for n, h in curs: checks.setdefault(n, hx(h))
    bad, good = [], []
    for n in sorted(checks):
        try: real = rpc.block(n)[1].lower()
        except RuntimeError as e:
            if "pruned" in str(e) or "4444" in str(e): good.append(n); continue
            raise
        (good if real == checks[n].lower() else bad).append(n)
    if not bad: return None
    stored_bad = [n for n in bad if n in rows]
    if stored_bad: fork = min(stored_bad)
    else:  # only cursor hash differs: rewind to just after the newest verified stored block, else by the whole window
        below = [n for n in good if n in rows and n < min(bad)]
        fork = (max(below) + 1) if below else max(0, min(bad) - REORG_WINDOW + 1)
    de = conn.execute("DELETE FROM raw_event WHERE chain_id=%s AND block_number >= %s", (chain, fork)).rowcount
    db_ = conn.execute("DELETE FROM block WHERE chain_id=%s AND number >= %s", (chain, fork)).rowcount
    conn.execute("""UPDATE sync_cursor c SET last_block = %s - 1, last_block_hash = NULL, updated_at = now()
                    FROM wallet w WHERE w.id=c.wallet_id AND w.chain_id=%s AND c.last_block >= %s""", (fork, chain, fork))
    conn.commit()
    log(json.dumps({"reorg": True, "chain": chain, "mismatched_blocks": bad, "fork_block": fork, "deleted_events": de, "deleted_blocks": db_}))
    return fork

def ingest_wallet(conn, chain, address, log=print):
    cfg = CHAINS[chain]; rpc = RPC(cfg["rpc"]); src = HyperSyncWalletLogs(cfg["hypersync"])
    wid = wallet_id(conn, chain, address)
    reorg_check(conn, chain, rpc, log)
    cur = conn.execute("SELECT last_block FROM sync_cursor WHERE source=%s AND wallet_id=%s", (src.name, wid)).fetchone()
    frm = (cur[0] + 1) if cur else 0
    to = rpc.safe_head()
    inserted = seen = 0
    if frm <= to:
        for logs, blocks in src.fetch(address, frm, to):
            for x in blocks:
                ts = datetime.datetime.fromtimestamp(h2i(x["timestamp"]), datetime.timezone.utc)
                conn.execute("INSERT INTO block(chain_id,number,hash,ts) VALUES (%s,%s,%s,%s) ON CONFLICT (chain_id,number) DO UPDATE SET hash=EXCLUDED.hash, ts=EXCLUDED.ts",
                             (chain, h2i(x["number"]), b(x["hash"]), ts))
            for l in logs:
                kind, payload = decode(l)
                if not kind or h2i(l["block_number"]) > to: continue
                seen += 1
                inserted += conn.execute("""INSERT INTO raw_event(chain_id,tx_hash,log_index,block_number,block_hash,source,kind,payload)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                    (chain, b(l["transaction_hash"]), h2i(l["log_index"]), h2i(l["block_number"]), b(l["block_hash"]),
                     src.name, kind, json.dumps(payload))).rowcount
        conn.commit()
    n, h, _ = rpc.block(to)
    conn.execute("""INSERT INTO sync_cursor(source,wallet_id,last_block,last_block_hash,updated_at) VALUES (%s,%s,%s,%s,now())
                    ON CONFLICT (source,wallet_id) DO UPDATE SET last_block=EXCLUDED.last_block, last_block_hash=EXCLUDED.last_block_hash, updated_at=now()""",
                 (src.name, wid, n, b(h)))
    conn.commit()
    log(json.dumps({"chain": chain, "wallet_id": wid, "from": frm, "to": to, "logs_seen": seen, "inserted": inserted}))

def counts(conn, chain):
    r = conn.execute("""SELECT count(*), md5(coalesce(string_agg(encode(tx_hash,'hex')||':'||log_index||':'||encode(block_hash,'hex'), ',' ORDER BY tx_hash, log_index),''))
                        FROM raw_event WHERE chain_id=%s""", (chain,)).fetchone()
    nb = conn.execute("SELECT count(*) FROM block WHERE chain_id=%s", (chain,)).fetchone()[0]
    by = dict(conn.execute("SELECT kind, count(*) FROM raw_event WHERE chain_id=%s GROUP BY kind", (chain,)).fetchall())
    return {"chain": chain, "raw_event": r[0], "block": nb, "by_kind": by, "checksum": r[1]}

def simulate_reorg(conn, chain, n=3):
    """Tamper the n newest stored block hashes (block + raw_event) and cursor hashes, as a forced hash mismatch."""
    nums = [r[0] for r in conn.execute("SELECT number FROM block WHERE chain_id=%s ORDER BY number DESC LIMIT %s", (chain, n))]
    for x in nums:
        fake = os.urandom(32)
        conn.execute("UPDATE block SET hash=%s WHERE chain_id=%s AND number=%s", (fake, chain, x))
        conn.execute("UPDATE raw_event SET block_hash=%s WHERE chain_id=%s AND block_number=%s", (fake, chain, x))
    conn.execute("UPDATE sync_cursor c SET last_block_hash=%s FROM wallet w WHERE w.id=c.wallet_id AND w.chain_id=%s", (os.urandom(32), chain))
    conn.commit(); return nums
