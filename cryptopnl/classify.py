"""P2: raw_event -> ledger_entry / review_queue / fifo_lot(migration) (DESIGN v1.1 §3/§4, v1.2 §8). Deterministic rules,
no models, no prices (P3). Per (wallet, tx), processed in chain order (escrow state carries across txs):
legs = wallet-touching ERC20/721/1155 transfers + native value (log_index -2) + gas (-1, sent txs only).
Escrow is a pseudo-location ('escrow:<diamond>'): escrow_out = wallet -X & escrow +X; a fill/claim pays from escrow
(escrow -X, same trade_group as the NFT leg); escrow_return = escrow -X & wallet +X. No FIFO disposal happens in P2.
Wearable TransferToParent/FromParent rows are custody (P1.1) and never produce ledger legs."""
import hashlib, json, uuid
from .config import gated, DEX_ROUTERS, ESCROW, BUYORDER_PLACE_SELECTORS, MIGRATION_REMINT, MANUAL_CONFIDENCE
from .db import b, hx

ZERO = "0x" + "0" * 40
GBM = {"0x80320a0000c7a6a34086e2acad6915ff57ffda31"}
BAAZAAR_EVENTS = {"ERC721ExecutedListing", "ERC1155ExecutedListing", "ERC721BuyOrderExecuted", "ERC1155BuyOrderExecute"}
TRADE_CATS = {"swap", "nft_buy", "nft_sale", "auction"}
TRANSFER_KINDS = ("erc20_transfer", "erc721_transfer", "erc1155_single", "erc1155_batch")
NFT = ("erc721", "erc1155")
GBM_INCENTIVE_MAX = 1.10   # heuristic refund match without an event: escrow <= refund <= escrow*1.10 (observed 0.5%/5%)

class Review(Exception): pass

def legs_of(w, rows):
    """rows: [(log_index, kind, payload)] of one tx. Returns (tx, legs, market) where leg = dict(li, std, contract, token_id, qty, cp)."""
    tx, legs, market = None, [], []
    for li, kind, p in rows:
        if kind == "tx": tx = p; continue
        if kind.startswith("market_"): market.append({**p, "li": li}); continue
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

def L(l, cat, loc="wallet", ref=None, qty=None, spam=False):
    d = {k: l[k] for k in ("li", "std", "contract", "token_id", "qty")}
    d.update(cat=cat, loc=loc, ref=ref, spam=spam)
    if qty is not None: d["qty"] = qty
    return d

def t_int(m, i): return int(m["topics"][i], 16)
def t_addr(m, i): return "0x" + m["topics"][i][-40:].lower()
def words(data):
    d = data[2:] if data and data.startswith("0x") else (data or "")
    return [int(d[i:i+64], 16) for i in range(0, len(d), 64)]

class Escrow:
    """Open escrow per (diamond, token): FIFO list of {ref, qty, ids(ledger rows of the placement)}. Mutations are staged
    per tx (begin/commit/rollback) so a tx that ends in review leaves the state untouched."""
    def __init__(self): self.open = {}; self._snap = None
    def begin(self): self._snap = {k: [dict(e, ids=list(e["ids"])) for e in v] for k, v in self.open.items()}
    def rollback(self): self.open = self._snap
    def put(self, d, tok, ref, qty):
        e = dict(ref=ref, qty=qty, ids=[]); self.open.setdefault((d, tok), []).append(e); return e
    def avail(self, d, tok, ref=None):
        return [e for e in self.open.get((d, tok), []) if e["qty"] > 0 and (ref is None or e["ref"] == ref)]
    def take(self, d, tok, qty, ref=None):
        """FIFO-consume qty; returns [(entry, q)] or raises Review if not enough open escrow."""
        es = self.avail(d, tok, ref)
        if sum(e["qty"] for e in es) < qty: raise Review("escrow fill/return larger than open escrow")
        out, need = [], qty
        for e in es:
            q = min(need, e["qty"]); e["qty"] -= q; out.append((e, q)); need -= q
            if not need: break
        return out

def escrow_rule(chain, w, tx, legs, market, esc):
    """Escrow custody at the Baazaar/GBM diamonds. Returns (category, out_legs, ref_updates) or None if not applicable.
    ref_updates: [(placement entry, ref)] to stamp the order id onto placement rows once a fill/cancel reveals it."""
    E = ESCROW.get(chain)
    if not E: return None
    gbm, bz = E["gbm"], E["baazaar"]
    sent = bool(tx) and tx["from"] == w
    fung = [l for l in legs if l["std"] == "erc20"]
    ev = lambda name, c: [m for m in market if m["event"] == name and m["contract"] == c]
    # ---- GBM: bids (escrow_out), outbid refunds (escrow_return [+ incentive income]), winning claims (auction paid from escrow)
    g_out = [l for l in fung if l["cp"] == gbm and l["qty"] < 0]
    g_in = [l for l in fung if l["cp"] == gbm and l["qty"] > 0]
    g_nft = [l for l in legs if l["std"] in NFT and l["cp"] == gbm and l["qty"] > 0]
    if g_out or g_in or g_nft:
        if len(g_out) + len(g_in) + len(g_nft) != len(legs): raise Review("gbm escrow legs mixed with other legs")
        bids_w = sorted({t_int(m, 1) for m in ev("Auction_BidPlaced", gbm) if t_addr(m, 2) == w})
        bid_any = {t_int(m, 1) for m in ev("Auction_BidPlaced", gbm)}
        claims = sorted({t_int(m, 1) for m in ev("Auction_ItemClaimed", gbm)})
        out, cat = [], None
        for l in g_in:                                  # refunds first: they release the previous (own) bid
            tok = l["contract"]
            cand = [a for a in sorted(bid_any | set(claims)) if esc.avail(gbm, tok, f"gbm:auction:{a}")]
            if not market:                              # refund with no indexed event: unique escrow within incentive band
                cand = sorted({int(e["ref"].split(":")[-1]) for e in esc.avail(gbm, tok)
                               if e["qty"] <= l["qty"] <= e["qty"] * GBM_INCENTIVE_MAX})
            if len(cand) == 1:
                ref = f"gbm:auction:{cand[0]}"; held = sum(e["qty"] for e in esc.avail(gbm, tok, ref))
                if l["qty"] < held: raise Review("gbm refund smaller than escrowed bid")
                esc.take(gbm, tok, held, ref)
                out += [L(l, "escrow_return", qty=held, ref=ref), L(l, "escrow_return", loc=f"escrow:{gbm}", qty=-held, ref=ref)]
                if l["qty"] > held: out.append(L(l, "income", qty=l["qty"] - held, ref=ref))   # GBM outbid incentive
                cat = cat or "escrow_return"
            elif claims and not cand:                   # seller proceeds from a claimed auction
                out.append(L(l, "auction")); cat = "auction"
            else: raise Review("gbm GHST in without a unique matching escrow")
        for l in g_out:
            if len(bids_w) != 1: raise Review("gbm payment without exactly one wallet bid")
            ref = f"gbm:auction:{bids_w[0]}"; esc.put(gbm, l["contract"], ref, -l["qty"])
            out += [L(l, "escrow_out", ref=ref), L(l, "escrow_out", loc=f"escrow:{gbm}", qty=-l["qty"], ref=ref)]
            cat = cat or "escrow_out"
        if g_nft:
            for a in claims:
                ref = f"gbm:auction:{a}"
                for tok in sorted({k[1] for k in esc.open if k[0] == gbm}):
                    held = sum(e["qty"] for e in esc.avail(gbm, tok, ref))
                    if held:
                        esc.take(gbm, tok, held, ref)
                        out.append(dict(li=next(m["li"] for m in ev("Auction_ItemClaimed", gbm) if t_int(m, 1) == a), std="erc20",
                                        contract=tok, token_id=None, qty=-held, cat="auction", loc=f"escrow:{gbm}", ref=ref, spam=False))
            out += [L(l, "auction") for l in g_nft]; cat = "auction"
        return cat, out, []
    # ---- Baazaar buy orders: fill (nft_buy paid from escrow), placement (escrow_out), cancel/refund (escrow_return)
    fills = [m for m in market if m["contract"] == bz and m["event"] in ("ERC1155BuyOrderExecute", "ERC721BuyOrderExecuted") and t_addr(m, 2) == w]
    if fills:
        if any(l["qty"] < 0 for l in legs) or not all(l["std"] in NFT for l in legs):
            raise Review("buy-order fill with non-NFT or outgoing wallet legs")
        out, upd = [L(l, "nft_buy") for l in legs], []
        for m in fills:
            if m["event"] != "ERC1155BuyOrderExecute": raise Review("erc721 buy-order fill: event layout not verified")
            wd = words(m["data"]); pay = wd[3] * wd[4]       # (seller, token, id, priceInWei, quantity, time)
            toks = sorted({k[1] for k in esc.open if k[0] == bz and esc.avail(bz, k[1])})
            if len(toks) != 1: raise Review("buy-order fill without matching escrow")
            ref = f"baazaar:buyorder:{t_int(m, 1)}"
            for e, q in esc.take(bz, toks[0], pay):
                if e["ref"] is None: upd.append((e, ref))
            out.append(dict(li=m["li"], std="erc20", contract=toks[0], token_id=None, qty=-pay, cat="nft_buy",
                            loc=f"escrow:{bz}", ref=ref, spam=False))
        return "nft_buy", out, upd
    if any(m["contract"] == bz for m in market): return None
    b_out = [l for l in fung if l["cp"] == bz and l["qty"] < 0]
    b_in = [l for l in fung if l["cp"] == bz and l["qty"] > 0]
    if b_out and len(b_out) == len(legs) and sent and (tx.get("selector") in BUYORDER_PLACE_SELECTORS):
        out = []
        for l in b_out:
            esc.put(bz, l["contract"], None, -l["qty"])
            out += [L(l, "escrow_out"), L(l, "escrow_out", loc=f"escrow:{bz}", qty=-l["qty"])]
        return "escrow_out", out, []
    if b_in and len(b_in) == len(legs) and all(esc.avail(bz, l["contract"]) for l in b_in):
        out, upd = [], []
        for l in b_in:   # cancel/refund: prefer the single open order with exactly this amount, else FIFO (partial refund)
            exact = [e for e in esc.avail(bz, l["contract"]) if e["qty"] == l["qty"]]
            if exact: exact[0]["qty"] = 0; taken = [(exact[0], l["qty"])]
            else: taken = esc.take(bz, l["contract"], l["qty"])
            ref = next((e["ref"] for e, _ in taken if e["ref"]), None)
            out += [L(l, "escrow_return", ref=ref), L(l, "escrow_return", loc=f"escrow:{bz}", qty=-l["qty"], ref=ref)]
        return "escrow_return", out, upd
    return None

def migration_rule(chain, w, tx, legs, bn):
    M = MIGRATION_REMINT.get(chain)
    if not M or not legs or (tx and tx["from"] == w): return None
    lo, hi = M["window"]
    if lo <= bn <= hi and all(l["std"] in NFT and l["qty"] > 0 and l["cp"] == ZERO and l["contract"] in M["contracts"] for l in legs):
        return "migration_in", [L(l, "migration_in") for l in legs], []
    return None

def decide(chain, w, tx, legs, market, group):
    """Generic rules (unchanged order from v1). Returns (category, None) or (None, review_reason). legs exclude gas, qty != 0."""
    sent = bool(tx) and tx["from"] == w
    if any(m["contract"] in GBM for m in market): return "auction", None
    nft_in = any(l["qty"] > 0 for l in legs if l["std"] in NFT)
    nft_out = any(l["qty"] < 0 for l in legs if l["std"] in NFT)
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

def plan(chain, w, tx, legs, market, group, bn, esc):
    """Returns (category, out_legs, ref_updates) or raises Review."""
    sent = bool(tx) and tx["from"] == w
    if tx and str(tx.get("status")) == "0":
        if legs: raise Review("failed tx with transfers")
        return "fee", [], []
    zero = [l for l in legs if l["qty"] == 0]; legs = [l for l in legs if l["qty"] != 0]
    if not legs:
        if sent: return "fee", [], []
        if zero: return "spam", [L(l, "spam", spam=True) for l in zero], []   # address poisoning: kept, flagged, qty 0
        raise Review("no wallet legs")
    r = escrow_rule(chain, w, tx, legs, market, esc) or migration_rule(chain, w, tx, legs, bn)
    if r: return r
    cat, why = decide(chain, w, tx, legs, market, group)
    allow = gated(chain)
    junk = lambda l: l["std"] != "native" and l["contract"] not in allow
    # spam (DESIGN §8): unsolicited (tx not sent by the wallet) non-allowlisted token legs in one-directional or mixed txs
    if not sent and (cat in ("deposit", "withdrawal", "income") or why == "mixed in/out legs") and any(junk(l) for l in legs):
        if why and not all(junk(l) for l in legs): raise Review(why)
        out = [L(l, "spam" if junk(l) else cat, spam=junk(l)) for l in legs]
        return ("spam" if all(junk(l) for l in legs) else cat), out, []
    if why: raise Review(why)
    return cat, [L(l, cat) for l in legs], []

def asset_id(conn, cache, chain, std, contract, token_id):
    k = (std, contract, token_id)
    if k not in cache:
        cache[k] = conn.execute("""INSERT INTO asset(chain_id,contract,standard,token_id) VALUES (%s,%s,%s,%s)
            ON CONFLICT (chain_id,contract,token_id) DO UPDATE SET standard=asset.standard RETURNING id""",
            (chain, b(contract) if contract else None, std, token_id)).fetchone()[0]
    return cache[k]

def apply_manual(conn, lot_id):
    """Apply the latest non-superseded manual_basis for the lot's opening leg (if any)."""
    r = conn.execute("""SELECT m.basis_usdc, m.acquired_at FROM fifo_lot f JOIN ledger_entry l ON l.id=f.open_entry_id
        JOIN manual_basis m ON m.chain_id=l.chain_id AND m.tx_hash=l.tx_hash AND m.log_index=l.log_index AND m.asset_id=l.asset_id
         AND m.wallet_id=l.wallet_id AND m.superseded_at IS NULL WHERE f.id=%s ORDER BY m.entered_at DESC, m.id DESC LIMIT 1""", (lot_id,)).fetchone()
    if r:
        conn.execute("""UPDATE fifo_lot SET basis_usdc=%s, basis_price_source='manual', basis_confidence=%s, basis_status='manual',
            opened_at=coalesce(%s, opened_at) WHERE id=%s""", (r[0], MANUAL_CONFIDENCE, r[1], lot_id))

def set_manual_basis(conn, lot_id, basis_usdc, acquired_at=None, entered_by="user_default"):
    """user_default's manual basis (DESIGN §8 step 2): price_source=manual, confidence low. Earlier entries are superseded, not deleted."""
    l = conn.execute("""SELECT l.chain_id, l.wallet_id, l.tx_hash, l.log_index, l.asset_id FROM fifo_lot f JOIN ledger_entry l ON l.id=f.open_entry_id
        WHERE f.id=%s""", (lot_id,)).fetchone()
    if not l: raise ValueError(f"lot {lot_id} not found")
    conn.execute("""UPDATE manual_basis SET superseded_at=now() WHERE chain_id=%s AND wallet_id=%s AND tx_hash=%s AND log_index=%s
        AND asset_id=%s AND superseded_at IS NULL""", l)
    conn.execute("""INSERT INTO manual_basis(chain_id,wallet_id,tx_hash,log_index,asset_id,basis_usdc,acquired_at,entered_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""", (*l, basis_usdc, acquired_at, entered_by))
    apply_manual(conn, lot_id); conn.commit()

def classify(conn, chain, log=print):
    """Idempotent: deletes and rebuilds ledger_entry + review_queue (+ migration lots) for the chain in one transaction.
    manual_basis is never deleted and is re-applied to the rebuilt lots."""
    conn.execute("DELETE FROM ledger_entry WHERE chain_id=%s", (chain,))   # cascades to fifo_lot / lot_disposal
    conn.execute("DELETE FROM review_queue WHERE chain_id=%s", (chain,))
    wallets = conn.execute("SELECT id, '0x'||encode(address,'hex'), wallet_group FROM wallet WHERE chain_id=%s ORDER BY id", (chain,)).fetchall()
    cache, stats = {}, {"txs": 0, "classified": 0, "review": 0, "by_category": {}, "review_reasons": {}, "entries": 0}
    origin = MIGRATION_REMINT.get(chain, {}).get("chain_origin")
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
        esc = Escrow()
        order = lambda h: (rows[h]["bn"], min([li for li, _, _ in rows[h]["rows"] if li >= 0] or [10**9]), h)
        for th in sorted(rows, key=order):           # chain order: escrow placement precedes fill/refund
            d = rows[th]; stats["txs"] += 1
            tx, legs, market = legs_of(w, d["rows"])
            legs += native_legs(w, tx)
            esc.begin()
            try:
                cat, out, upd = plan(chain, w, tx, legs, market, group, d["bn"], esc); why = None
            except Review as e:
                esc.rollback(); why, cat, out, upd = str(e), None, [], []
                ls = [l for l in legs if l["qty"] != 0]
                stats["review"] += 1; stats["review_reasons"][why] = stats["review_reasons"].get(why, 0) + 1
                conn.execute("INSERT INTO review_queue(chain_id,wallet_id,tx_hash,reason,detail) VALUES (%s,%s,%s,%s,%s)",
                    (chain, wid, th, why, json.dumps({"legs": [{k: (str(v) if k == "qty" else v) for k, v in l.items()} for l in ls],
                                                      "market": [m["event"] for m in market], "selector": (tx or {}).get("selector"),
                                                      "block_number": d["bn"]})))
            if not why:
                stats["classified"] += 1; stats["by_category"][cat] = stats["by_category"].get(cat, 0) + 1
            tg = str(uuid.UUID(bytes=hashlib.sha256(b"%d:" % chain + th + b":%d" % wid).digest()[:16])) if cat in TRADE_CATS else None
            if tx and tx["from"] == w and int(tx["fee"]):   # gas: a fact, recorded even for txs in review
                out = out + [dict(li=-1, std="native", contract=None, token_id=None, qty=-int(tx["fee"]), cat="fee", loc="wallet", ref=None, spam=False)]
            ids = []
            for l in out:
                eid = conn.execute("""INSERT INTO ledger_entry(wallet_id,asset_id,chain_id,tx_hash,log_index,block_number,ts,qty,category,
                    trade_group,location,escrow_ref,pnl_excluded) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (wid, asset_id(conn, cache, chain, l["std"], l["contract"], l["token_id"]), chain, th, l["li"], d["bn"], d["ts"],
                     l["qty"], l["cat"], tg if l["cat"] in TRADE_CATS else None, l["loc"], l["ref"], l["spam"])).fetchone()[0]
                ids.append(eid); stats["entries"] += 1
                if l["cat"] == "migration_in":
                    lot = conn.execute("""INSERT INTO fifo_lot(wallet_group,asset_id,open_entry_id,opened_at,open_block,qty_open,qty_remaining,
                        basis_usdc,basis_price_source,basis_status,chain_origin) VALUES (%s,%s,%s,NULL,%s,%s,%s,NULL,'polygon_carryover','pending',%s)
                        RETURNING id""", (grp, asset_id(conn, cache, chain, l["std"], l["contract"], l["token_id"]), eid, d["bn"], l["qty"], l["qty"], origin)).fetchone()[0]
                    apply_manual(conn, lot)
            # remember placement rows so a later fill/cancel can stamp the order id on them
            for e in [e for k in esc.open for e in esc.open[k] if e["ref"] is None and not e["ids"]]:
                e["ids"] = [i for i, l in zip(ids, out) if l["cat"] == "escrow_out"]
            for e, ref in upd:
                if e["ids"]: conn.execute("UPDATE ledger_entry SET escrow_ref=%s WHERE id = ANY(%s)", (ref, e["ids"]))
                e["ref"] = ref
    conn.commit()
    stats["classified_pct"] = round(100.0 * stats["classified"] / stats["txs"], 3) if stats["txs"] else None
    log(json.dumps({"chain": chain, **stats})); return stats

def checksum(conn, chain):
    r = conn.execute("""SELECT count(*), md5(string_agg(concat_ws('|',encode(tx_hash,'hex'),log_index,wallet_id,asset_id,qty,category,trade_group,location,escrow_ref,pnl_excluded),','
        ORDER BY tx_hash,log_index,wallet_id,asset_id,location,category)) FROM ledger_entry WHERE chain_id=%s""", (chain,)).fetchone()
    q = conn.execute("SELECT count(*), md5(string_agg(encode(tx_hash,'hex')||reason, ',' ORDER BY tx_hash)) FROM review_queue WHERE chain_id=%s", (chain,)).fetchone()
    return {"ledger_rows": r[0], "ledger_md5": r[1], "review_rows": q[0], "review_md5": q[1]}

def totals(conn, chain, include_spam=False):
    """Net wallet-location qty per asset_id from the ledger. Spam rows (pnl_excluded) are excluded unless include_spam;
    this is the input set for every PnL total (DESIGN §8)."""
    return {a: int(q) for a, q in conn.execute("""SELECT asset_id, sum(qty) FROM ledger_entry WHERE chain_id=%s AND location='wallet'
        AND (%s OR NOT pnl_excluded) GROUP BY 1 HAVING sum(qty) <> 0""", (chain, include_spam))}

def basis_totals(conn, chain):
    """Lots with pending basis are counted but excluded from basis totals (unknown, not zero). Manual = low confidence."""
    r = conn.execute("""SELECT count(*), count(*) FILTER (WHERE f.basis_status='pending'), count(*) FILTER (WHERE f.basis_status='manual'),
        sum(f.basis_usdc) FILTER (WHERE f.basis_status<>'pending') FROM fifo_lot f JOIN ledger_entry l ON l.id=f.open_entry_id WHERE l.chain_id=%s""",
        (chain,)).fetchone()
    return {"lots": r[0], "pending_lots": r[1], "manual_lots": r[2], "basis_usdc_total_excl_pending": r[3]}

def report(conn, chain):
    """Counts from the stored ledger/review tables (no recomputation). A tx counts as classified when it is not in review_queue."""
    txs = conn.execute("""SELECT count(*) FROM (SELECT DISTINCT wallet_id, tx_hash FROM ledger_entry WHERE chain_id=%s
                          UNION SELECT wallet_id, tx_hash FROM review_queue WHERE chain_id=%s) t""", (chain, chain)).fetchone()[0]
    rev = dict(conn.execute("SELECT reason, count(*) FROM review_queue WHERE chain_id=%s GROUP BY 1", (chain,)).fetchall())
    nrev = sum(rev.values())
    # per-tx category: priority order (a trade/custody category wins over its incidental legs), else fee
    cats = dict(conn.execute("""SELECT c, count(*) FROM (SELECT tx_hash, wallet_id, (array_agg(category ORDER BY array_position(
        ARRAY['nft_buy','nft_sale','auction','swap','migration_in','escrow_out','escrow_return','transfer_internal','income','deposit','withdrawal','spam','fee'], category)))[1] c
        FROM ledger_entry WHERE chain_id=%s AND (wallet_id, tx_hash) NOT IN (SELECT wallet_id, tx_hash FROM review_queue WHERE chain_id=%s)
        GROUP BY 1,2) t GROUP BY 1""", (chain, chain)).fetchall())
    rows = dict(conn.execute("SELECT category, count(*) FROM ledger_entry WHERE chain_id=%s GROUP BY 1", (chain,)).fetchall())
    esc = [{"ref": r[0], "location": r[1], "open_qty": str(r[2])} for r in conn.execute("""SELECT coalesce(escrow_ref,'(unlinked)'), location, sum(qty)
        FROM ledger_entry WHERE chain_id=%s AND location LIKE 'escrow:%%' GROUP BY 1,2 HAVING sum(qty)<>0 ORDER BY 1""", (chain,))]
    allow = gated(chain)
    own_junk = conn.execute("""SELECT count(DISTINCT l.tx_hash) FROM ledger_entry l JOIN asset a ON a.id=l.asset_id
        JOIN raw_event t ON t.chain_id=l.chain_id AND t.tx_hash=l.tx_hash AND t.kind='tx' AND t.payload->>'from' = (SELECT '0x'||encode(address,'hex') FROM wallet WHERE id=l.wallet_id)
        WHERE l.chain_id=%s AND l.category IN ('deposit','withdrawal','income') AND a.contract IS NOT NULL
        AND NOT ('0x'||encode(a.contract,'hex') = ANY(%s))""", (chain, list(allow))).fetchone()[0]
    pct = round(100.0 * (txs - nrev) / txs, 3) if txs else None
    return {"chain": chain, "wallet_txs": txs, "classified": txs - nrev, "review": nrev, "classified_pct": pct,
            "pass_98": bool(txs) and pct > 98, "txs_by_category": cats, "ledger_rows_by_category": rows, "review_reasons": rev,
            "spam_rows_pnl_excluded": conn.execute("SELECT count(*) FROM ledger_entry WHERE chain_id=%s AND pnl_excluded", (chain,)).fetchone()[0],
            "open_escrow": esc, "lots": basis_totals(conn, chain),
            "wallet_sent_txs_with_non_allowlisted_token_legs": own_junk, **checksum(conn, chain)}
