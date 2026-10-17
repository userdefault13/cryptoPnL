"""P2: raw_event -> ledger_entry / review_queue (DESIGN v1.1 §3/§4). Deterministic rules, no models, no prices (P3).
Per (wallet, tx): legs = wallet-touching ERC20/721/1155 transfers + native value (tx-level row) + gas (sent txs only).
Wearable TransferToParent/FromParent rows are custody (P1.1) and never produce ledger legs."""
import hashlib, json, uuid
from .config import gated, DEX_ROUTERS
from .db import b, hx

ZERO = "0x" + "0" * 40
GBM = {"0x80320a0000c7a6a34086e2acad6915ff57ffda31"}
BAAZAAR_EVENTS = {"ERC721ExecutedListing", "ERC1155ExecutedListing", "ERC721BuyOrderExecuted", "ERC1155BuyOrderExecute"}
TRADE_CATS = {"swap", "nft_buy", "nft_sale", "auction"}
TRANSFER_KINDS = ("erc20_transfer", "erc721_transfer", "erc1155_single", "erc1155_batch")

def legs_of(w, rows):
    """rows: [(log_index, kind, payload)] of one tx. Returns (tx, legs, market) where leg = dict(li, std, contract, token_id, qty, cp)."""
    tx, legs, market = None, [], []
    for li, kind, p in rows:
        if kind == "tx": tx = p; continue
        if kind.startswith("market_"): market.append(p); continue
        if kind not in TRANSFER_KINDS: continue
        f, t = p["from"], p["to"]
        if w not in (f, t) or f == t: continue
        sign, cp = (1, f) if t == w else (-1, t)
        if kind == "erc20_transfer":
            legs.append(dict(li=li, std="erc20", contract=p["contract"], token_id=None, qty=sign * int(p["value"]), cp=cp))
        elif kind == "erc721_transfer":
            legs.append(dict(li=li, std="erc721", contract=p["contract"], token_id=p["token_id"], qty=sign, cp=cp))
        else:
            for i, v in zip(p["ids"], p["values"]):
                legs.append(dict(li=li, std="erc1155", contract=p["contract"], token_id=i, qty=sign * int(v), cp=cp))
    return tx, legs, market

def native_legs(w, tx):
    out = []
    if not tx: return out
    v = int(tx["value"]); f, t = tx["from"], tx["to"]
    if v and f != t and str(tx.get("status")) != "0":
        if f == w: out.append(dict(li=-2, std="native", contract=None, token_id=None, qty=-v, cp=t))
        elif t == w: out.append(dict(li=-2, std="native", contract=None, token_id=None, qty=v, cp=f))
    return out

def decide(chain, w, tx, legs, market, group):
    """Returns (category, None) or (None, review_reason). legs exclude gas."""
    sent = bool(tx) and tx["from"] == w
    if tx and str(tx.get("status")) == "0":
        return (None, "failed tx with transfers") if legs else ("fee", None)
    zero = [l for l in legs if l["qty"] == 0]
    legs = [l for l in legs if l["qty"] != 0]
    if not legs:
        if sent: return "fee", None
        return (None, "zero-value transfers only (no balance effect; likely address poisoning)") if zero else (None, "no wallet legs")
    if any(m["contract"] in GBM for m in market): return "auction", None
    nft_in = any(l["qty"] > 0 for l in legs if l["std"] in ("erc721", "erc1155"))
    nft_out = any(l["qty"] < 0 for l in legs if l["std"] in ("erc721", "erc1155"))
    fin = {(l["contract"]) for l in legs if l["std"] in ("erc20", "native") and l["qty"] > 0}
    fout = {(l["contract"]) for l in legs if l["std"] in ("erc20", "native") and l["qty"] < 0}
    if any(m["event"] in BAAZAAR_EVENTS for m in market):
        if nft_in and not nft_out: return "nft_buy", None
        if nft_out and not nft_in: return "nft_sale", None
        return None, "baazaar event, ambiguous NFT direction"
    if group and all(l["cp"] in group for l in legs): return "transfer_internal", None
    any_in, any_out = nft_in or fin, nft_out or fout
    if nft_in and fout and not nft_out and not fin: return "nft_buy", None
    if nft_out and fin and not nft_in and not fout: return "nft_sale", None
    if fin and fout and not nft_in and not nft_out and fin != fout: return "swap", None
    if any_in and not any_out:
        allow = gated(chain)
        if all(l["cp"] == ZERO for l in legs) and (sent or all(l["contract"] in allow for l in legs)): return "income", None
        return "deposit", None
    if any_out and not any_in:
        routers = DEX_ROUTERS.get(chain, set())
        if fout and not nft_out and ((tx and tx["to"] in routers) or any(l["cp"] in routers for l in legs)):
            return None, "DEX router, fungible out only: native leg not indexed (internal ETH gap)"
        return "withdrawal", None
    return None, "mixed in/out legs"

def asset_id(conn, cache, chain, std, contract, token_id):
    k = (std, contract, token_id)
    if k not in cache:
        cache[k] = conn.execute("""INSERT INTO asset(chain_id,contract,standard,token_id) VALUES (%s,%s,%s,%s)
            ON CONFLICT (chain_id,contract,token_id) DO UPDATE SET standard=asset.standard RETURNING id""",
            (chain, b(contract) if contract else None, std, token_id)).fetchone()[0]
    return cache[k]

def classify(conn, chain, log=print):
    """Idempotent: deletes and rebuilds ledger_entry + review_queue for the chain in one transaction."""
    conn.execute("DELETE FROM ledger_entry WHERE chain_id=%s", (chain,))
    conn.execute("DELETE FROM review_queue WHERE chain_id=%s", (chain,))
    wallets = conn.execute("SELECT id, '0x'||encode(address,'hex'), wallet_group FROM wallet WHERE chain_id=%s ORDER BY id", (chain,)).fetchall()
    cache, stats = {}, {"txs": 0, "classified": 0, "review": 0, "by_category": {}, "review_reasons": {}, "entries": 0}
    for wid, w, grp in wallets:
        group = {a for _, a, g in wallets if g == grp and a != w}
        txh = [r[0] for r in conn.execute("""SELECT DISTINCT tx_hash FROM raw_event WHERE chain_id=%s AND
              ((kind='tx' AND (payload->>'from'=%s OR payload->>'to'=%s)) OR
               (kind = ANY(%s) AND (payload->>'from'=%s OR payload->>'to'=%s)))""",
              (chain, w, w, list(TRANSFER_KINDS), w, w))]
        rows = {}
        for th, li, kind, p, bn, ts in conn.execute("""SELECT r.tx_hash, r.log_index, r.kind, r.payload, r.block_number, bl.ts
              FROM raw_event r JOIN block bl ON bl.chain_id=r.chain_id AND bl.number=r.block_number
              WHERE r.chain_id=%s AND r.tx_hash = ANY(%s) ORDER BY r.tx_hash, r.log_index""", (chain, txh)):
            rows.setdefault(bytes(th), {"bn": bn, "ts": ts, "rows": []})["rows"].append((li, kind, p))
        missing = len(txh) - len(rows)
        if missing: raise RuntimeError(f"{missing} wallet txs have no block row (ts unknown); re-run ingest")
        for th in sorted(rows):
            d = rows[th]; stats["txs"] += 1
            tx, legs, market = legs_of(w, d["rows"])
            legs += native_legs(w, tx)
            cat, why = decide(chain, w, tx, legs, market, group)
            legs = [l for l in legs if l["qty"] != 0]
            if why:
                stats["review"] += 1; stats["review_reasons"][why] = stats["review_reasons"].get(why, 0) + 1
                conn.execute("INSERT INTO review_queue(chain_id,wallet_id,tx_hash,reason,detail) VALUES (%s,%s,%s,%s,%s)",
                    (chain, wid, th, why, json.dumps({"legs": [{k: (str(v) if k == "qty" else v) for k, v in l.items()} for l in legs],
                                                      "market": [m["event"] for m in market], "selector": (tx or {}).get("selector")})))
                legs = []  # unclassified legs wait in the queue; gas (fact, not a judgement) is still recorded
            else:
                stats["classified"] += 1; stats["by_category"][cat] = stats["by_category"].get(cat, 0) + 1
            tg = str(uuid.UUID(bytes=hashlib.sha256(b"%d:" % chain + th + b":%d" % wid).digest()[:16])) if cat in TRADE_CATS else None
            out = [(l, cat, tg) for l in legs]
            if tx and tx["from"] == w and int(tx["fee"]):
                out.append((dict(li=-1, std="native", contract=None, token_id=None, qty=-int(tx["fee"])), "fee", None))
            for l, c, g in out:
                conn.execute("""INSERT INTO ledger_entry(wallet_id,asset_id,chain_id,tx_hash,log_index,block_number,ts,qty,category,trade_group)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (wid, asset_id(conn, cache, chain, l["std"], l["contract"], l["token_id"]), chain, th, l["li"], d["bn"], d["ts"], l["qty"], c, g))
                stats["entries"] += 1
    conn.commit()
    stats["classified_pct"] = round(100.0 * stats["classified"] / stats["txs"], 3) if stats["txs"] else None
    log(json.dumps({"chain": chain, **stats})); return stats

def checksum(conn, chain):
    r = conn.execute("""SELECT count(*), md5(string_agg(concat_ws('|',encode(tx_hash,'hex'),log_index,wallet_id,asset_id,qty,category,trade_group),',' ORDER BY tx_hash,log_index,wallet_id,asset_id))
        FROM ledger_entry WHERE chain_id=%s""", (chain,)).fetchone()
    q = conn.execute("SELECT count(*), md5(string_agg(encode(tx_hash,'hex')||reason, ',' ORDER BY tx_hash)) FROM review_queue WHERE chain_id=%s", (chain,)).fetchone()
    return {"ledger_rows": r[0], "ledger_md5": r[1], "review_rows": q[0], "review_md5": q[1]}

def report(conn, chain):
    """Counts from the stored ledger/review tables (no recomputation). A tx counts as classified when it is not in review_queue."""
    allow = gated(chain)
    txs = conn.execute("""SELECT count(*) FROM (SELECT DISTINCT wallet_id, tx_hash FROM ledger_entry WHERE chain_id=%s
                          UNION SELECT wallet_id, tx_hash FROM review_queue WHERE chain_id=%s) t""", (chain, chain)).fetchone()[0]
    rev = dict(conn.execute("SELECT reason, count(*) FROM review_queue WHERE chain_id=%s GROUP BY 1", (chain,)).fetchall())
    nrev = sum(rev.values())
    # per-tx category = the non-fee category if any, else fee
    cats = dict(conn.execute("""SELECT c, count(*) FROM (SELECT tx_hash, wallet_id, coalesce(max(category) FILTER (WHERE category<>'fee'),'fee') c
        FROM ledger_entry WHERE chain_id=%s AND (wallet_id, tx_hash) NOT IN (SELECT wallet_id, tx_hash FROM review_queue WHERE chain_id=%s)
        GROUP BY 1,2) t GROUP BY 1""", (chain, chain)).fetchall())
    rows = dict(conn.execute("SELECT category, count(*) FROM ledger_entry WHERE chain_id=%s GROUP BY 1", (chain,)).fetchall())
    spam = conn.execute("""SELECT count(DISTINCT l.tx_hash) FROM ledger_entry l JOIN asset a ON a.id=l.asset_id
        WHERE l.chain_id=%s AND l.category IN ('deposit','withdrawal','income') AND a.contract IS NOT NULL
        AND NOT ('0x'||encode(a.contract,'hex') = ANY(%s))""", (chain, list(allow))).fetchone()[0]
    pct = round(100.0 * (txs - nrev) / txs, 3) if txs else None
    return {"chain": chain, "wallet_txs": txs, "classified": txs - nrev, "review": nrev, "classified_pct": pct,
            "pass_98": bool(txs) and pct > 98, "txs_by_category": cats, "ledger_rows_by_category": rows, "review_reasons": rev,
            "txs_with_non_allowlisted_deposit_withdrawal_income": spam, **checksum(conn, chain)}
