import json, os, datetime
from .db import b, hx
from .sources import RPC, HyperSyncWalletGV, HyperSyncWalletTxs, HyperSyncWalletLogs, HyperSyncContractLogs, HyperSyncParentTransfers, T_TO_PARENT, T_FROM_PARENT, TRANSFER, T1155S, T1155B, h2i
from .config import CHAINS, REORG_CHECK_BLOCKS, REORG_WINDOW, MARKETPLACE, MARKET_TOPICS, WEARABLES, GV, GV_TOPICS, GOTCHI_ESCROW_SEL, TYPE_COST_GETTER

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
    curs = list(curs) + conn.execute("SELECT last_block, last_block_hash FROM sync_cursor_global WHERE chain_id=%s AND last_block_hash IS NOT NULL", (chain,)).fetchall()
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
            # Sepolia only (DESIGN v1.1 §7): sepolia.base.org prunes old blocks; treated as final. Mainnet must raise.
            if chain == 84532 and ("pruned" in str(e) or "4444" in str(e)): good.append(n); continue
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
    conn.execute("UPDATE parent_scan SET last_block=%s-1 WHERE chain_id=%s AND last_block >= %s", (fork, chain, fork))
    conn.execute("UPDATE sync_cursor_global SET last_block=%s-1, last_block_hash=NULL, updated_at=now() WHERE chain_id=%s AND last_block >= %s", (fork, chain, fork))
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
        if src.covered < to:
            log(json.dumps({"warn": "hypersync stopped early (non-advancing next_block)", "requested_to": to, "covered_to": src.covered}))
        to = src.covered
    if to < 0: return
    n, h, _ = rpc.block(to)
    conn.execute("""INSERT INTO sync_cursor(source,wallet_id,last_block,last_block_hash,updated_at) VALUES (%s,%s,%s,%s,now())
                    ON CONFLICT (source,wallet_id) DO UPDATE SET last_block=EXCLUDED.last_block, last_block_hash=EXCLUDED.last_block_hash, updated_at=now()""",
                 (src.name, wid, n, b(h)))
    conn.commit()
    log(json.dumps({"chain": chain, "wallet_id": wid, "from": frm, "to": to, "logs_seen": seen, "inserted": inserted}))

def tx_payload(t):
    """Tx-level row (DESIGN §3: log_index -1): native value + gas. Fee = gas_used*effective_gas_price + l1_fee (wei)."""
    hx_ = lambda k: int(t[k], 16) if t.get(k) not in (None, "", "0x") else 0
    fee = hx_("gas_used") * hx_("effective_gas_price") + hx_("l1_fee")
    return {"from": (t.get("from") or "").lower(), "to": (t.get("to") or "").lower() or None, "value": str(hx_("value")),
            "gas_used": str(hx_("gas_used")), "effective_gas_price": str(hx_("effective_gas_price")), "l1_fee": str(hx_("l1_fee")),
            "fee": str(fee), "status": t.get("status"), "selector": (t.get("input") or "0x")[:10],
            "tx_index": hx_("transaction_index") if t.get("transaction_index") not in (None, "", "0x") else None}   # P3: order within a block

def ingest_wallet_txs(conn, chain, address, log=print):
    """P2: transactions from/to the wallet -> raw_event kind 'tx', log_index -1. Cursor = sync_cursor(source hypersync_tx)."""
    cfg = CHAINS[chain]; rpc = RPC(cfg["rpc"]); src = HyperSyncWalletTxs(cfg["hypersync"])
    wid = wallet_id(conn, chain, address)
    reorg_check(conn, chain, rpc, log)
    cur = conn.execute("SELECT last_block FROM sync_cursor WHERE source=%s AND wallet_id=%s", (src.name, wid)).fetchone()
    frm = (cur[0] + 1) if cur else 0; to = rpc.safe_head(); seen = inserted = 0
    if frm <= to:
        for txs, blocks in src.fetch(address, frm, to):
            store_blocks(conn, chain, blocks)
            for t in txs:
                if h2i(t["block_number"]) > to: continue
                seen += 1
                inserted += conn.execute("""INSERT INTO raw_event(chain_id,tx_hash,log_index,block_number,block_hash,source,kind,payload)
                    VALUES (%s,%s,-1,%s,%s,%s,'tx',%s) ON CONFLICT DO NOTHING""",
                    (chain, b(t["hash"]), h2i(t["block_number"]), b(t["block_hash"]), src.name, json.dumps(tx_payload(t)))).rowcount
            conn.commit()
        if src.covered < to: log(json.dumps({"warn": "hypersync tx scan stopped early", "requested_to": to, "covered_to": src.covered}))
        to = src.covered
    if to < 0: return
    n, h, _ = rpc.block(to)
    conn.execute("""INSERT INTO sync_cursor(source,wallet_id,last_block,last_block_hash,updated_at) VALUES (%s,%s,%s,%s,now())
                    ON CONFLICT (source,wallet_id) DO UPDATE SET last_block=EXCLUDED.last_block, last_block_hash=EXCLUDED.last_block_hash, updated_at=now()""",
                 (src.name, wid, n, b(h)))
    conn.commit()
    log(json.dumps({"chain": chain, "wallet_id": wid, "source": src.name, "from": frm, "to": to, "txs_seen": seen, "inserted": inserted}))

def ingest_tx_meta(conn, chain, address, log=print):
    """P2 decisions: tx.from/to/selector for wallet-received mints (from 0x0) whose tx the wallet did not send/receive
    (no 'tx' row): needed for the migration (bridge sender + selector) and bridge_in (tx.to = CCTP) rules.
    Read-only RPC eth_getTransactionByHash (RPC limiter 1/s, burst 3); no HyperSync. raw_event kind 'tx_meta', log_index -3.
    Idempotent: only hashes without a tx/tx_meta row; reorg rewind deletes these rows with their block."""
    rpc = RPC(CHAINS[chain]["rpc"]); fetched = 0
    todo = conn.execute("""SELECT DISTINCT ON (r.tx_hash) r.tx_hash, r.block_number, r.block_hash FROM raw_event r
        WHERE r.chain_id=%s AND r.kind = ANY(%s) AND r.payload->>'from'=%s AND r.payload->>'to'=%s
        AND NOT EXISTS (SELECT 1 FROM raw_event t WHERE t.chain_id=r.chain_id AND t.tx_hash=r.tx_hash AND t.kind IN ('tx','tx_meta'))
        ORDER BY r.tx_hash""", (chain, ["erc20_transfer", "erc721_transfer", "erc1155_single", "erc1155_batch"],
                                "0x" + "0" * 40, address.lower())).fetchall()
    for th, bn, bh in todo:
        t = rpc.call("eth_getTransactionByHash", [hx(th)])
        if t:
            meta = {"from": t["from"].lower(), "to": (t.get("to") or "").lower() or None, "selector": (t.get("input") or "0x")[:10],
                    "value": str(h2i(t.get("value") or "0x0"))}
        else:   # null lookup: recorded so classify sends allowlisted mints to review (architect, 3c8b056)
            meta = {"from": None, "to": None, "selector": None, "value": None, "lookup_null": True}
        conn.execute("""INSERT INTO raw_event(chain_id,tx_hash,log_index,block_number,block_hash,source,kind,payload)
            VALUES (%s,%s,-3,%s,%s,'rpc_txmeta','tx_meta',%s) ON CONFLICT DO NOTHING""", (chain, th, bn, bh, json.dumps(meta)))
        fetched += 1
    conn.commit()
    log(json.dumps({"chain": chain, "source": "rpc_txmeta", "candidates": len(todo), "fetched": fetched}))

def store_blocks(conn, chain, blocks):
    for x in blocks:
        ts = datetime.datetime.fromtimestamp(h2i(x["timestamp"]), datetime.timezone.utc)
        conn.execute("INSERT INTO block(chain_id,number,hash,ts) VALUES (%s,%s,%s,%s) ON CONFLICT (chain_id,number) DO UPDATE SET hash=EXCLUDED.hash, ts=EXCLUDED.ts",
                     (chain, h2i(x["number"]), b(x["hash"]), ts))

def ingest_marketplace(conn, chain, log=print):
    m = MARKETPLACE.get(chain)
    if not m: log(json.dumps({"chain": chain, "marketplace": "none configured"})); return
    cfg = CHAINS[chain]; rpc = RPC(cfg["rpc"])
    src = HyperSyncContractLogs(cfg["hypersync"], m["source"], m["contracts"], list(MARKET_TOPICS))
    reorg_check(conn, chain, rpc, log)
    cur = conn.execute("SELECT last_block FROM sync_cursor_global WHERE source=%s AND chain_id=%s", (src.name, chain)).fetchone()
    frm = (cur[0] + 1) if cur else m["start_block"]; to = rpc.safe_head(); seen = inserted = 0
    for logs, blocks in src.fetch_range(frm, to):
        store_blocks(conn, chain, blocks)
        for l in logs:
            if h2i(l["block_number"]) > to: continue
            seen += 1
            payload = {"contract": l["address"].lower(), "event": MARKET_TOPICS.get(l["topic0"], "unknown"),
                       "topics": [l.get(k) for k in ("topic0", "topic1", "topic2", "topic3") if l.get(k)], "data": l.get("data")}
            inserted += conn.execute("""INSERT INTO raw_event(chain_id,tx_hash,log_index,block_number,block_hash,source,kind,payload)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (chain, b(l["transaction_hash"]), h2i(l["log_index"]), h2i(l["block_number"]), b(l["block_hash"]),
                 src.name, "market_" + payload["event"], json.dumps(payload))).rowcount
        # checkpoint per page (only up to what HyperSync actually covered) so a long backfill resumes
        if src.covered >= frm:
            n, h, _ = rpc.block(src.covered)
            conn.execute("""INSERT INTO sync_cursor_global(source,chain_id,last_block,last_block_hash,updated_at) VALUES (%s,%s,%s,%s,now())
                    ON CONFLICT (source,chain_id) DO UPDATE SET last_block=EXCLUDED.last_block, last_block_hash=EXCLUDED.last_block_hash, updated_at=now()""",
                 (src.name, chain, n, b(h)))
        conn.commit()
    if src.covered < to: log(json.dumps({"warn": "hypersync stopped early", "requested_to": to, "covered_to": src.covered}))
    to = src.covered
    log(json.dumps({"chain": chain, "source": src.name, "from": frm, "to": to, "logs_seen": seen, "inserted": inserted}))

def gotchis_ever(conn, chain, w, canonical):
    return sorted({int(r[0]) for r in conn.execute("""SELECT DISTINCT payload->>'token_id' FROM raw_event WHERE chain_id=%s AND kind='erc721_transfer'
        AND payload->>'contract'=%s AND (payload->>'to'=%s OR payload->>'from'=%s)""", (chain, canonical, w, w))})

def ingest_parent_transfers(conn, chain, address, log=print):
    """P1.1: custody changes of wearables into/out of gotchis the wallet has held (never disposals)."""
    wcfg = WEARABLES.get(chain)
    if not wcfg: return
    cfg = CHAINS[chain]; rpc = RPC(cfg["rpc"]); src = HyperSyncParentTransfers(cfg["hypersync"])
    w = address.lower(); ids = gotchis_ever(conn, chain, w, wcfg["canonical"])
    if not ids: log(json.dumps({"chain": chain, "parent_transfers": "no gotchis"})); return
    to = rpc.safe_head(); done = dict((int(g), lb) for g, lb in conn.execute("SELECT gotchi_id, last_block FROM parent_scan WHERE chain_id=%s", (chain,)))
    groups = {}
    for g in ids: groups.setdefault(done.get(g, -1) + 1, []).append(g)
    seen = inserted = 0
    for frm, gs in sorted(groups.items()):
        if frm > to: continue
        for logs, blocks in src.fetch_ids(wcfg["parent"], gs, frm, to):
            store_blocks(conn, chain, blocks)
            for l in logs:
                if h2i(l["block_number"]) > to: continue
                seen += 1
                kind = "wearable_to_parent" if l["topic0"] == T_TO_PARENT else "wearable_from_parent"
                payload = {"contract": wcfg["canonical"], "parent_contract": addr_of(l["topic1"]), "gotchi_id": str(int(l["topic2"], 16)),
                           "type_id": str(int(l["topic3"], 16)), "value": str(words(l.get("data"))[0] if words(l.get("data")) else 0)}
                inserted += conn.execute("""INSERT INTO raw_event(chain_id,tx_hash,log_index,block_number,block_hash,source,kind,payload)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                    (chain, b(l["transaction_hash"]), h2i(l["log_index"]), h2i(l["block_number"]), b(l["block_hash"]), src.name, kind, json.dumps(payload))).rowcount
        if src.covered < to: log(json.dumps({"warn": "hypersync parent scan stopped early", "requested_to": to, "covered_to": src.covered}))
        for g in gs:   # advance only to what HyperSync actually covered (PR #1 review blocker 1)
            if src.covered >= frm:
                conn.execute("INSERT INTO parent_scan(chain_id,gotchi_id,last_block) VALUES (%s,%s,%s) ON CONFLICT (chain_id,gotchi_id) DO UPDATE SET last_block=EXCLUDED.last_block", (chain, g, src.covered))
        conn.commit()
    log(json.dumps({"chain": chain, "source": src.name, "gotchis": len(ids), "to": to, "logs_seen": seen, "inserted": inserted}))

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
    conn.execute("UPDATE sync_cursor_global SET last_block_hash=%s WHERE chain_id=%s", (os.urandom(32), chain))
    conn.commit(); return nums


def ingest_tx_index(conn, chain, log=print):
    """P3: tx position for wallet txs that share a block with another wallet tx and have no tx_index yet. Read-only RPC
    eth_getTransactionByHash (1 req/s, burst 3); zero HyperSync. Idempotent (only rows missing from tx_position)."""
    rpc = RPC(CHAINS[chain]["rpc"]); n = 0
    todo = conn.execute("""WITH t AS (SELECT DISTINCT tx_hash, block_number FROM ledger_entry WHERE chain_id=%s),
        multi AS (SELECT block_number FROM t GROUP BY 1 HAVING count(*) > 1)
        SELECT t.tx_hash, t.block_number FROM t JOIN multi USING (block_number)
        WHERE NOT EXISTS (SELECT 1 FROM tx_position p WHERE p.chain_id=%s AND p.tx_hash=t.tx_hash)
        AND NOT EXISTS (SELECT 1 FROM raw_event r WHERE r.chain_id=%s AND r.tx_hash=t.tx_hash AND r.kind='tx' AND r.payload->>'tx_index' IS NOT NULL)
        ORDER BY 2, 1""", (chain, chain, chain)).fetchall()
    for th, bn in todo:
        t = rpc.call("eth_getTransactionByHash", [hx(th)])
        if not t or t.get("transactionIndex") is None:
            log(json.dumps({"warn": "tx index lookup null", "tx": hx(th)})); continue
        if h2i(t["blockNumber"]) != bn: raise RuntimeError(f"{hx(th)}: block mismatch {h2i(t['blockNumber'])} != {bn} (reorg?)")
        conn.execute("INSERT INTO tx_position(chain_id,tx_hash,block_number,tx_index) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                     (chain, th, bn, h2i(t["transactionIndex"]))); n += 1
    conn.commit(); log(json.dumps({"chain": chain, "source": "rpc_txindex", "candidates": len(todo), "fetched": n}))

def ingest_gv(conn, chain, address, log=print):
    """P2.2: Gotchiverse/lending/marketplace-recipient logs for the wallet (HyperSyncWalletGV). Only logs whose topic0 is in GV_TOPICS
    are stored, as raw_event kind 'gv_<Event>' with the real log_index (transfers and market_* rows of the same log already exist and
    win on the (tx, log_index) key). Aavegotchi-diamond TransferTo/FromParent (wearables) stay with ingest_parent_transfers.
    Cursor: sync_cursor(source hypersync_gv, wallet). Idempotent."""
    gv = GV.get(chain)
    if not gv: log(json.dumps({"chain": chain, "gv": "none configured"})); return
    cfg = CHAINS[chain]; rpc = RPC(cfg["rpc"]); src = HyperSyncWalletGV(cfg["hypersync"])
    wid = wallet_id(conn, chain, address); reorg_check(conn, chain, rpc, log)
    cur = conn.execute("SELECT last_block FROM sync_cursor WHERE source=%s AND wallet_id=%s", (src.name, wid)).fetchone()
    frm = (cur[0] + 1) if cur else gv["start_block"]; to = rpc.safe_head(); seen = inserted = 0
    if frm <= to:
        for logs, blocks in src.fetch(address, frm, to, gv, GV_TOPICS):
            store_blocks(conn, chain, blocks)
            for l in logs:
                ev = GV_TOPICS.get(l.get("topic0"))
                if not ev or h2i(l["block_number"]) > to: continue
                if ev in ("TransferToParent", "TransferFromParent") and l["address"].lower() == gv["aavegotchi"]: continue
                seen += 1
                payload = {"contract": l["address"].lower(), "event": ev,
                           "topics": [l.get(k) for k in ("topic0", "topic1", "topic2", "topic3") if l.get(k)], "data": l.get("data")}
                inserted += conn.execute("""INSERT INTO raw_event(chain_id,tx_hash,log_index,block_number,block_hash,source,kind,payload)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                    (chain, b(l["transaction_hash"]), h2i(l["log_index"]), h2i(l["block_number"]), b(l["block_hash"]), src.name,
                     "gv_" + ev, json.dumps(payload))).rowcount
            if src.covered >= frm:
                n, h, _ = rpc.block(src.covered)
                conn.execute("""INSERT INTO sync_cursor(source,wallet_id,last_block,last_block_hash,updated_at) VALUES (%s,%s,%s,%s,now())
                    ON CONFLICT (source,wallet_id) DO UPDATE SET last_block=EXCLUDED.last_block, last_block_hash=EXCLUDED.last_block_hash, updated_at=now()""",
                    (src.name, wid, n, b(h)))
            conn.commit()
        if src.covered < to: log(json.dumps({"warn": "hypersync gv scan stopped early", "requested_to": to, "covered_to": src.covered}))
    log(json.dumps({"chain": chain, "wallet_id": wid, "source": src.name, "from": frm, "to": to, "logs_seen": seen, "inserted": inserted}))
    ingest_gotchi_escrows(conn, chain, address, rpc, gv, log)
    ingest_craft_type_costs(conn, chain, address, rpc, gv, log)

def ingest_craft_type_costs(conn, chain, address, rpc, gv, log=print):
    """KNOWN_GAPS #27: for wallet-sent craft txs that both mint (Installation/Tile from 0x0) and queue (AddedToQueue), read each involved
    type's alchemicaCost at the tx block (eth_call, read-only) and cache it in craft_type_cost. Only those txs, so RPC use stays light."""
    w = address.lower(); kind = {gv["installation"]: "installation", gv["tile"]: "tile"}; calls = added = 0
    rows = conn.execute("""SELECT q.tx_hash, q.block_number, q.payload->>'contract', q.payload->'topics'->>2 FROM raw_event q
        JOIN raw_event t ON t.chain_id=q.chain_id AND t.tx_hash=q.tx_hash AND t.kind='tx' AND t.payload->>'from'=%s
        WHERE q.chain_id=%s AND q.kind='gv_AddedToQueue'""", (w, chain)).fetchall()
    need = {}
    for th, bn, c, item in rows:
        if c not in kind: continue
        mints = conn.execute("""SELECT payload->>'contract', payload->>'token_id' FROM raw_event WHERE chain_id=%s AND tx_hash=%s
            AND kind LIKE 'erc1155%%' AND payload->>'from'=%s AND payload->>'to'=%s""", (chain, th, "0x" + "0" * 40, w)).fetchall()
        mints = [(mc, int(t)) for mc, t in mints if mc in kind]
        if not mints: continue                       # queue-only craft: no split needed
        for key in mints + [(c, int(item, 16))]: need.setdefault((key[0], key[1], bn), True)
    have = {(hx(c), int(t), int(bn)) for c, t, bn in conn.execute("SELECT contract, type_id, block_number FROM craft_type_cost WHERE chain_id=%s", (chain,))}
    for c, t, bn in sorted(need):
        if (c, t, bn) in have: continue
        sel, i0 = TYPE_COST_GETTER[kind[c]]
        d = rpc.eth_call(c, sel + format(t, "064x"), bn)[2:]; calls += 1
        wd = [int(d[j:j + 64], 16) for j in range(0, len(d), 64)]
        if not wd or wd[0] != 0x20: raise RuntimeError(f"type cost getter: unexpected return layout for {c} type {t}")
        added += conn.execute("INSERT INTO craft_type_cost VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                              (chain, b(c), t, bn, [str(x) for x in wd[i0:i0 + 4]])).rowcount
    conn.commit()
    log(json.dumps({"chain": chain, "source": "rpc_craft_type_cost", "mixed_craft_types": len(need), "eth_calls": calls, "added": added}))

def ingest_gotchi_escrows(conn, chain, address, rpc, gv, log=print):
    """Gotchi pocket cache (DESIGN v1.3 §9): gotchiEscrow(id) for every gotchi the wallet has held, resolved once (RPC eth_call, read-only)
    and stored in gotchi_escrow; classify reads the cache and never calls RPC. A zero address (no escrow yet) is not cached."""
    ids = gotchis_ever(conn, chain, address.lower(), gv["aavegotchi"])
    have = {r[0] for r in conn.execute("SELECT gotchi_id FROM gotchi_escrow WHERE chain_id=%s", (chain,))}
    head = rpc.safe_head(); added = 0
    for i in ids:
        if i in have: continue
        a = "0x" + rpc.eth_call(gv["aavegotchi"], GOTCHI_ESCROW_SEL + format(i, "064x"), head)[-40:]
        if int(a, 16) == 0: continue
        added += conn.execute("INSERT INTO gotchi_escrow(chain_id,gotchi_id,escrow,resolved_block) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                              (chain, i, b(a), head)).rowcount
    conn.commit()
    log(json.dumps({"chain": chain, "source": "rpc_gotchi_escrow", "gotchis": len(ids), "cached_before": len(have), "added": added}))

def ingest_pool_swaps(conn, chain, log=print):
    """P3 ruling 3: Swap-log blocks of the thin alchemica pools (Aerodrome v2 entries of PRICE_POOLS for THIN_POOL_ASSETS), one
    HyperSync scan for all of them through the shared host bucket, cached per pool in pool_swap; pool_swap_scan holds the scanned
    range per pool so later runs only scan forward. Read-only."""
    from .config import PRICE_POOLS, THIN_POOL_ASSETS, AERO_V2_SWAP_TOPIC
    from .sources import HyperSyncContractLogs
    pools = sorted({p for a in THIN_POOL_ASSETS.get(chain, ()) for k, p, _ in PRICE_POOLS.get(chain, {}).get(a, []) if k == "v2"})
    if not pools: log(json.dumps({"chain": chain, "pool_swaps": "none configured"})); return
    cfg = CHAINS[chain]; rpc = RPC(cfg["rpc"]); to = rpc.safe_head(); start = GV[chain]["start_block"]
    have = {hx(p): (f, t) for p, f, t in conn.execute("SELECT pool, from_block, scanned_to FROM pool_swap_scan WHERE chain_id=%s", (chain,))}
    frm = min((have[p][1] + 1) if p in have else start for p in pools)
    src = HyperSyncContractLogs(cfg["hypersync"], "hypersync_pool_swaps", pools, [AERO_V2_SWAP_TOPIC]); seen = ins = 0
    if frm <= to:
        for logs, _ in src.fetch_range(frm, to):
            for l in logs:
                if h2i(l["block_number"]) > to or l.get("topic0") != AERO_V2_SWAP_TOPIC: continue
                seen += 1
                ins += conn.execute("INSERT INTO pool_swap VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                                    (chain, b(l["address"].lower()), h2i(l["block_number"]))).rowcount
            for p in pools:
                if src.covered >= frm:
                    conn.execute("""INSERT INTO pool_swap_scan VALUES (%s,%s,%s,%s) ON CONFLICT (chain_id,pool) DO UPDATE
                        SET scanned_to=GREATEST(pool_swap_scan.scanned_to, EXCLUDED.scanned_to)""", (chain, b(p), have.get(p, (start,))[0], src.covered))
            conn.commit()
        if src.covered < to: log(json.dumps({"warn": "pool swap scan stopped early", "requested_to": to, "covered_to": src.covered}))
    per = dict(conn.execute("SELECT '0x'||encode(pool,'hex'), count(*) FROM pool_swap WHERE chain_id=%s GROUP BY 1", (chain,)).fetchall())
    log(json.dumps({"chain": chain, "source": src.name, "pools": pools, "from": frm, "to": to, "swaps_seen": seen, "inserted": ins, "swaps_per_pool": per}))
