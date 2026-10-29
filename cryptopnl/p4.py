"""P4 DB adapter + CLI: ledger_entry -> fifo.Entry, the engine state <-> fifo_lot / lot_disposal / fifo_cost_bucket / fifo_run, marks
from stored P3 prices (no RPC), pnl_snapshot, reconciliation. Read-only on chain; writes only the P4 projection tables of the DB in
CRYPTOPNL_DSN (run it on a COPY of the P3 DB).
  python -m cryptopnl.p4 rebuild     --chain 8453
  python -m cryptopnl.p4 incremental --chain 8453 --split-block N   # rebuild to N, persist, reload state from the DB, continue
  python -m cryptopnl.p4 snapshot    --chain 8453 --out FILE         # pnl_snapshot at as_of_block (byte-identical when repeated)
  python -m cryptopnl.p4 reconcile   --chain 8453 --out FILE
Switches: cryptopnl/p4_policy.json (the rulings), override with --set key=value."""
import argparse, json, os, sys, hashlib
from decimal import Decimal
from . import db, fifo, reconcile
from .pricing import TOKENS

HERE = os.path.dirname(__file__)
def load_config(overrides=()):
    with open(os.path.join(HERE, "p4_policy.json")) as f: cfg = json.load(f)
    for kv in overrides:
        k, v = kv.split("=", 1); cfg[k] = None if v in ("", "none", "None") else v
    return cfg

ROWS_SQL = """SELECT l.id, l.block_number, l.tx_index, encode(l.tx_hash,'hex'), l.log_index, l.asset_id, l.qty, l.category,
  l.wallet_id, w.wallet_group, l.location, l.escrow_ref, l.trade_group::text, l.price_usdc, l.price_source, l.price_confidence_label,
  l.price_flag, l.pnl_excluded, a.standard, '0x'||encode(a.contract,'hex'), mb.id, mb.basis_usdc
  FROM ledger_entry l JOIN asset a ON a.id=l.asset_id LEFT JOIN wallet w ON w.id=l.wallet_id
  LEFT JOIN manual_basis mb ON mb.chain_id=l.chain_id AND mb.tx_hash=l.tx_hash AND mb.log_index=l.log_index AND mb.asset_id=l.asset_id
       AND mb.superseded_at IS NULL
  WHERE l.chain_id=%s ORDER BY l.block_number, l.log_index, l.id"""   # log_index is block-wide, so it orders txs too; no coalesce

class TxIndexError(ValueError): pass

def check_tx_index(raw):
    """tx_index is NULL unless a block holds 2+ wallet txs (P3). A NULL is safe only when its block has ONE tx; else raise.
    -> number of rows with NULL tx_index (reported as tx_index_null_rows)."""
    txs, nul = {}, 0
    for b, ti, tx in raw:
        txs.setdefault(b, set()).add(tx); nul += ti is None
    bad = sorted({b for b, ti, tx in raw if ti is None and len(txs[b]) > 1})
    if bad: raise TxIndexError(f"{len(bad)} blocks have rows with NULL tx_index and 2+ txs (first {bad[:5]}); run the P3 tx-index step")
    return nul

def load_rows(conn, chain, cfg, stats=None):
    dec = {c: d for c, (_, d) in TOKENS.get(chain, {}).items()}; out = []
    raw = conn.execute(ROWS_SQL, (chain,)).fetchall()
    n = check_tx_index([(r[1], r[2], r[3]) for r in raw])
    if stats is not None: stats["tx_index_null_rows"] = n
    for (i, b, ti, tx, li, aid, q, cat, wid, wg, loc, ref, tg, px, ps, lab, fl, ex, std, c, mbid, mbv) in raw:
        nft = std in ("erc721", "erc1155")
        skip = ex or cat in ("spam", "untracked") or fl in ("spam", "untracked")
        if std == "native": d = 18
        elif std == "erc20":
            d = dec.get(c)
            if d is None:
                if not skip: raise ValueError(f"ledger_entry {i}: erc20 {c} has no known decimals (pricing.TOKENS)")
                d = 0
        else: d = 0
        group = f"chain:{chain}" if cfg["group"] == "one_group_per_chain" else (wg or "default")
        out.append(fifo.Entry(id=i, block=b, tx="0x" + tx, log_index=li, asset=str(aid), qty=Decimal(q) / (Decimal(10) ** d), category=cat,
                              wallet=str(wid), group=group, location=loc, tx_index=0 if ti is None else ti, ref=ref, trade_group=tg,
                              price=None if px is None else Decimal(px), price_source=ps, label=lab, flag=fl, excluded=ex, nft=nft,
                              manual_basis=None if mbv is None else Decimal(mbv), manual_basis_id=mbid))
    return out

class Marks:
    """Q-F: marks from stored P3 prices only (ledger_entry.price_usdc of live rows), at or before as_of_block. No RPC."""
    name = "p3_stored_at_as_of"
    def __init__(self, rows):
        self.p = {}
        for e in rows:
            if e.price is None or e.excluded or e.category in ("spam", "untracked") or e.flag in ("spam", "untracked"): continue
            self.p.setdefault(e.asset, []).append((e.key(), e.price, e.price_source, e.label))
        for v in self.p.values(): v.sort(key=lambda x: x[0])
        self.nft = {e.asset for e in rows if e.nft}
    def latest_priced(self):
        """{asset: latest block with a stored P3 price}, tracked fungible assets only (NFT marks are Q8, sparse, never gate as_of)."""
        return {a: v[-1][0][0] for a, v in self.p.items() if a not in self.nft}
    def as_of_block(self):
        """Q-F / rulings 3: the latest block at which EVERY tracked asset has a stored price = MIN over assets of each one's latest."""
        lp = self.latest_priced()
        if not lp: raise ValueError("no stored P3 prices: as_of_block undefined")
        return min(lp.values())
    def as_of_detail(self):
        lp = self.latest_priced(); b = min(lp.values()); return {"as_of_block": b, "set_by_assets": sorted(a for a, x in lp.items() if x == b),
                                                                "latest_priced_block_per_asset": dict(sorted(lp.items()))}
    def __call__(self, asset, block, lot=None):
        best = None
        for k, px, src, lab in self.p.get(asset, []):
            if k[0] <= block: best = (k, px, src, lab)
        if best is None: return None
        return fifo.Mark(best[1], f"p3:{best[2]}@{best[0][0]}", best[3])

class AsOfMarks:
    """P4 rulings 4 (revises Q-F / rulings 3): fungible marks are the p3_mark rows the P3 pricing path wrote AT as_of_block, one per
    held asset (`python -m cryptopnl marks`). No row, or status no_valid_mark -> None: the asset is excluded from unrealized and
    counted, like an unpriced NFT. No RPC in the engine."""
    name = "p3_mark_at_as_of"
    def __init__(self, conn, chain, as_of):
        self.as_of, self.m, self.status = as_of, {}, {}
        for aid, st, px, src, lab, why in conn.execute("""SELECT asset_id, status, price_usdc, source, confidence_label, reason FROM p3_mark
                WHERE chain_id=%s AND as_of_block=%s ORDER BY asset_id""", (chain, as_of)):
            self.status[str(aid)] = "priced" if st == "priced" else f"no_valid_mark:{why}"
            if st == "priced": self.m[str(aid)] = fifo.Mark(Decimal(px), f"p3_mark:{src}@{as_of}", lab)
    def __call__(self, asset, block, lot=None):
        if block != self.as_of: raise ValueError(f"marks exist only at as_of_block {self.as_of}, asked for {block}")
        return self.m.get(asset)
    def coverage(self, held):
        """held: {asset: qty} fungible -> {priced, no_valid_mark: {asset: reason}, missing: [assets with no p3_mark row]}"""
        out = {"priced": 0, "no_valid_mark": {}, "missing": []}
        for a in sorted(held, key=int):
            s = self.status.get(a)
            if s == "priced": out["priced"] += 1
            elif s: out["no_valid_mark"][a] = s.split(":", 1)[1]
            else: out["missing"].append(a)
        return out

def as_of_rule(cfg, rows, override=None):
    """P4 rulings 4: as_of_block = the block user_default chose (--as-of), else the LAST ledger block."""
    if override: return override, "user_default (--as-of)"
    if cfg.get("as_of_block") != "last_ledger_block_else_user_default":
        raise SystemExit(f"as_of_block switch {cfg.get('as_of_block')!r} not supported (rulings 4: last_ledger_block_else_user_default)")
    if not rows: raise SystemExit("no ledger rows: as_of_block undefined")
    return max(e.block for e in rows), "last ledger block"

class NftMark(Marks):
    """Q8: an NFT is marked only at a stored P3 price (else left out of unrealized and counted; never at basis or 0)."""
    name = "p3_price_else_exclude"
    def __init__(self, marks): self.p, self.nft = marks.p, marks.nft

class Recipes:
    name = "stored_craft_recipe_cost"
    def __init__(self, conn, chain):
        self.r = {}
        for aid, b, c in conn.execute("SELECT asset_id, block_number, cost_usdc FROM craft_recipe_cost WHERE chain_id=%s", (chain,)):
            self.r[(str(aid), b)] = Decimal(c)
    def __call__(self, asset, block): return self.r.get((asset, block))

def policy(cfg, marks, recipes, fmarks=None):
    k = {x: cfg.get(x) for x in ("fee", "fee_without_trade", "fee_split", "deposit", "withdrawal", "internal_transfer", "queue_split", "shortfall")}
    nm = cfg.get("nft_mark")
    k["nft_mark"] = NftMark(marks) if nm == "p3_price_else_exclude" else nm
    k["mark"] = fmarks if cfg.get("mark") == "p3_mark_at_as_of" else (marks if cfg.get("mark") == "p3_stored_at_as_of" else None)
    k["recipe"] = recipes if cfg.get("recipe") == "stored_craft_recipe_cost" else None
    return fifo.Policy(**k)

# ---------- state <-> DB ----------
def _n(x): return None if x is None else x
def write_state(conn, chain, st, pol, from_block):
    c = conn
    # the chain's lots are projections owned by P4: its rows and P2 classify's (chain_id NULL, pending migration lots) are replaced
    mine = """SELECT f.id FROM fifo_lot f WHERE f.chain_id=%s OR (f.chain_id IS NULL AND f.open_entry_id IN (SELECT id FROM ledger_entry WHERE chain_id=%s))"""
    c.execute(f"DELETE FROM lot_disposal WHERE lot_id IN ({mine})", (chain, chain))
    c.execute(f"DELETE FROM fifo_lot WHERE id IN ({mine})", (chain, chain))
    c.execute("DELETE FROM fifo_cost_bucket WHERE chain_id=%s", (chain,))
    mx = c.execute("SELECT max(id) FROM fifo_lot").fetchone()[0]
    if mx is not None and min((l.id for l in st.lots), default=mx + 1) <= mx:
        raise RuntimeError(f"fifo_lot holds other chains' rows (ids up to {mx}): P4 lot ids would collide; use a per-chain DB copy")
    with c.cursor() as cur:
        cur.executemany("""INSERT INTO fifo_lot(id, chain_id, wallet_group, asset_id, open_entry_id, open_block, qty_open, qty_remaining, basis_usdc,
            basis_price_source, basis_status, chain_origin, wallet_id, location, open_kind, ref, parent_lot_id, pending_reason, basis_out_usdc,
            manual_basis_id, basis_label, fee_usdc, split_method, order_key, is_nft, basis_origin)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            [(l.id, chain, l.group, int(l.asset), l.open_entry, l.open_block, l.qty_open, l.qty, l.basis, l.source, l.status, l.chain_origin,
              None if l.wallet in (None, "None") else int(l.wallet), l.location, l.kind, l.ref, l.parent, l.pending_reason, l.basis_out,
              l.manual_basis_id, l.label, l.fee, l.split_method, json.dumps(list(l.order)), l.nft, l.basis_origin) for l in sorted(st.lots, key=lambda l: l.id)])
        cur.executemany("""INSERT INTO lot_disposal(id, lot_id, close_entry_id, qty, proceeds_usdc, proceeds_price_source, cost_usdc, payment_for, kind,
            closed_block, bundle_ref, own_cost_usdc, expense_usdc, lot_status, proceeds_label, display_mv_usdc)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            [(d.id, d.lot, d.entry, d.qty, d.proceeds, d.proceeds_source, d.cost, d.payment_for, d.kind, d.block, d.bundle_ref, d.own_cost,
              d.expense, d.lot_status, d.proceeds_label, d.display_mv) for d in sorted(st.disposals, key=lambda d: d.id)])
        cur.executemany("INSERT INTO fifo_cost_bucket(chain_id, wallet_group, ref, value_usdc, confidence_label, split_method) VALUES (%s,%s,%s,%s,%s,%s)",
                        [(chain, "*", k, v[0], v[1], v[2]) for k, v in sorted(st.buckets.items())])
    state = {"income": [[i, a, None if v is None else str(v)] for i, a, v in st.income], "excluded": st.excluded,
             "next_lot": st.next_lot, "next_disp": st.next_disp}
    m = fifo.md5(st)
    rid = c.execute("""INSERT INTO fifo_run(chain_id, from_block, finished_at, lots, disposals, lots_md5, policy, last_key, state)
        VALUES (%s,%s,clock_timestamp(),%s,%s,%s,%s,%s,%s) RETURNING id""",
        (chain, from_block, len(st.lots), len(st.disposals), m, json.dumps(pol.describe()), json.dumps(list(st.last_key) if st.last_key else None),
         json.dumps(state))).fetchone()[0]
    conn.commit(); return rid, m

def _D(x): return None if x is None else Decimal(x)
def load_state(conn, chain):
    """The engine state back from the P4 tables + the last fifo_run counters (recompute from block X)."""
    run = conn.execute("SELECT last_key, state FROM fifo_run WHERE chain_id=%s ORDER BY id DESC LIMIT 1", (chain,)).fetchone()
    st = fifo.State()
    for r in conn.execute("""SELECT id, wallet_group, asset_id, wallet_id, location, open_entry_id, open_block, order_key, qty_open, qty_remaining,
            basis_usdc, basis_price_source, basis_label, basis_status, open_kind, is_nft, ref, parent_lot_id, chain_origin, pending_reason,
            manual_basis_id, basis_out_usdc, fee_usdc, split_method, basis_origin FROM fifo_lot WHERE chain_id=%s ORDER BY id""", (chain,)):
        st.lots.append(fifo.Lot(id=r[0], group=r[1], asset=str(r[2]), wallet=str(r[3]), location=r[4], open_entry=r[5], open_block=r[6],
                                order=tuple(json.loads(r[7])), qty_open=_D(r[8]), qty=_D(r[9]), basis=_D(r[10]), source=r[11], label=r[12],
                                status=r[13], kind=r[14], nft=r[15], ref=r[16], parent=r[17], chain_origin=r[18], pending_reason=r[19],
                                manual_basis_id=r[20], basis_out=_D(r[21]), fee=_D(r[22]), split_method=r[23], basis_origin=r[24]))
    for r in conn.execute("""SELECT d.id, d.lot_id, d.close_entry_id, d.closed_block, d.qty, d.kind, d.proceeds_usdc, d.proceeds_price_source,
            d.proceeds_label, d.cost_usdc, d.payment_for, d.bundle_ref, d.expense_usdc, d.lot_status, d.own_cost_usdc, d.display_mv_usdc
            FROM lot_disposal d JOIN fifo_lot l ON l.id=d.lot_id WHERE l.chain_id=%s ORDER BY d.id""", (chain,)):
        st.disposals.append(fifo.Disposal(id=r[0], lot=r[1], entry=r[2], block=r[3], qty=_D(r[4]), kind=r[5], proceeds=_D(r[6]),
                                          proceeds_source=r[7], proceeds_label=r[8], cost=_D(r[9]), payment_for=r[10], bundle_ref=r[11],
                                          expense=_D(r[12]), lot_status=r[13], own_cost=_D(r[14]), display_mv=_D(r[15])))
    for ref, v, lab, sm in conn.execute("SELECT ref, value_usdc, confidence_label, split_method FROM fifo_cost_bucket WHERE chain_id=%s ORDER BY ref", (chain,)):
        st.buckets[ref] = [_D(v), lab, sm]
    if run:
        lk, s = run
        st.last_key = tuple(lk) if lk else None
        st.income = [(i, a, _D(v)) for i, a, v in s["income"]]; st.excluded = dict(s["excluded"])
        st.next_lot, st.next_disp = s["next_lot"], s["next_disp"]
    return st

TABLE_MD5 = """SELECT md5(string_agg(concat_ws('|', id, wallet_group, asset_id, wallet_id, location, open_entry_id, open_block, qty_open::text, qty_remaining::text,
  basis_usdc::text, basis_out_usdc::text, basis_price_source, basis_label, basis_status, open_kind, ref, parent_lot_id, chain_origin, pending_reason,
  manual_basis_id, fee_usdc::text, split_method, order_key, is_nft, basis_origin), ',' ORDER BY id)) FROM fifo_lot WHERE chain_id=%s"""
DISP_MD5 = """SELECT md5(string_agg(concat_ws('|', d.id, d.lot_id, d.close_entry_id, d.closed_block, d.qty::text, d.kind, d.proceeds_usdc::text,
  d.proceeds_price_source, d.proceeds_label, d.cost_usdc::text, d.payment_for, d.bundle_ref, d.expense_usdc::text, d.lot_status,
  d.own_cost_usdc::text, d.display_mv_usdc::text), ',' ORDER BY d.id)) FROM lot_disposal d JOIN fifo_lot l ON l.id=d.lot_id WHERE l.chain_id=%s"""
def table_md5(conn, chain):
    return {"fifo_lot_md5": conn.execute(TABLE_MD5, (chain,)).fetchone()[0], "lot_disposal_md5": conn.execute(DISP_MD5, (chain,)).fetchone()[0]}

# ---------- snapshot ----------
def _j(x):
    if isinstance(x, Decimal): return fifo._s(x)
    if isinstance(x, dict): return {k: _j(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)): return [_j(v) for v in x]
    return x
def snapshot(conn, chain, st, pol, as_of):
    rep = fifo.report(st, pol, as_of)
    conn.execute("DELETE FROM pnl_snapshot WHERE as_of_block=%s AND asset_id IN (SELECT id FROM asset WHERE chain_id=%s)", (as_of, chain))
    grp = next((l.group for l in st.lots), f"chain:{chain}"); rows = []
    for variant in ("all", "excl_low"):
        for a, v in rep[variant]["by_asset"].items():
            rows.append((grp, int(a), as_of, variant, v["qty"], v["cost_basis"], v["mark_price"], v["mark_source"], v["market_value"],
                         v["realized"], v["unrealized"], v["pending_lots"], v["pending_disposals"]))
    with conn.cursor() as cur:
        cur.executemany("""INSERT INTO pnl_snapshot(wallet_group, asset_id, as_of_block, variant, qty, cost_basis_usdc, mark_price_usdc, mark_source,
            market_value_usdc, realized_pnl_usdc, unrealized_pnl_usdc, pending_lots, pending_disposals) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", rows)
    conn.commit()
    sm = conn.execute("""SELECT md5(string_agg(concat_ws('|', wallet_group, asset_id, as_of_block, variant, qty::text, cost_basis_usdc::text, mark_price_usdc::text,
        mark_source, market_value_usdc::text, realized_pnl_usdc::text, unrealized_pnl_usdc::text, pending_lots, pending_disposals), ',' ORDER BY asset_id, variant))
        FROM pnl_snapshot WHERE as_of_block=%s AND asset_id IN (SELECT id FROM asset WHERE chain_id=%s)""", (as_of, chain)).fetchone()[0]
    return rep, sm, len(rows)

def ledger_qty(rows):
    q = {}
    for e in rows:
        if e.excluded or e.category in ("spam", "untracked") or e.flag in ("spam", "untracked"): continue
        q[e.asset] = q.get(e.asset, Decimal(0)) + e.qty
    return {a: v for a, v in q.items() if v != 0}
def held_fungible(rows):
    """{asset: qty} of tracked fungible assets with a positive ledger balance at ANY location (wallet, escrow, pocket, ...), as written
    by `cryptopnl marks` (pricing.write_marks uses the same rule)."""
    q = {}
    for e in rows:
        if e.nft or e.excluded or e.category in ("spam", "untracked") or e.flag in ("spam", "untracked"): continue
        k = (e.asset, e.location); q[k] = q.get(k, Decimal(0)) + e.qty
    out = {}
    for (a, loc), v in q.items():
        if v > 0: out[a] = out.get(a, Decimal(0)) + v
    return out
def engine_qty(st):
    q = {}
    for l in st.lots:
        if l.qty > 0: q[l.asset] = q.get(l.asset, Decimal(0)) + l.qty
    return q

def main(argv=None):
    ap = argparse.ArgumentParser(prog="cryptopnl.p4")
    ap.add_argument("cmd", choices=["rebuild", "incremental", "snapshot", "reconcile"])
    ap.add_argument("--chain", type=int, required=True); ap.add_argument("--split-block", type=int); ap.add_argument("--as-of", type=int)
    ap.add_argument("--out"); ap.add_argument("--set", action="append", default=[])
    a = ap.parse_args(argv); cfg = load_config(a.set); conn = db.connect()
    stats = {}; rows = load_rows(conn, a.chain, cfg, stats); marks = Marks(rows)
    as_of, set_by = as_of_rule(cfg, rows, a.as_of)
    fm = AsOfMarks(conn, a.chain, as_of) if cfg.get("mark") == "p3_mark_at_as_of" else None
    pol = policy(cfg, marks, Recipes(conn, a.chain), fm)
    out = {"chain": a.chain, "ledger_rows": len(rows), "policy": pol.describe(), **stats}
    if a.cmd == "rebuild":
        st = fifo.run(rows, pol); rid, m = write_state(conn, a.chain, st, pol, None)
        out.update({"fifo_run": rid, "engine_md5": m, **table_md5(conn, a.chain), "lots": len(st.lots), "disposals": len(st.disposals)})
    elif a.cmd == "incremental":
        X = a.split_block; head = [e for e in rows if e.block <= X]; tail = [e for e in rows if e.block > X]
        st1 = fifo.run(head, pol); _, m1 = write_state(conn, a.chain, st1, pol, None); back = load_state(conn, a.chain)
        st2 = fifo.run(tail, pol, back); rid, m = write_state(conn, a.chain, st2, pol, X + 1)
        out.update({"fifo_run": rid, "split_block": X, "rows_head": len(head), "rows_tail": len(tail), "engine_md5": m, "head_md5": m1,
                    "head_md5_reloaded_from_db": fifo.md5(back), **table_md5(conn, a.chain),
                    "lots": len(st2.lots), "disposals": len(st2.disposals)})
    else:
        upto = [e for e in rows if e.block <= as_of]
        if len(upto) == len(rows): st, src = load_state(conn, a.chain), "fifo_run (db)"
        else: st, src = fifo.run(upto, pol), "replay of ledger rows <= as_of_block (offline)"
        held = held_fungible(upto)
        out.update({"as_of": {"as_of_block": as_of, "set_by": set_by, "last_ledger_block": max(e.block for e in rows)},
                    "state_at_as_of": src, "rows_after_as_of": len(rows) - len(upto),
                    "gate_all_rows_at_or_before_as_of": len(rows) == len(upto),
                    "marks": fm.coverage(held) if fm else None})
        if a.cmd == "snapshot":
            rep, sm, n = snapshot(conn, a.chain, st, pol, as_of)
            out.update({"as_of_block": as_of, "pnl_snapshot_rows": n, "pnl_snapshot_md5": sm, "report": rep})
        else:
            rep = fifo.report(st, pol, as_of); g = fifo.gas(st)
            L = reconcile.ledger_side(rows, pol.mark, pol.nft_mark, as_of, pol.recipe, cfg)   # ledger rows only, never engine lots
            chk = reconcile.check(rep, g, L, engine_qty(st))
            out.update({"as_of_block": as_of, "reconciliation": chk, "ledger_side_gas_txs": L["gas_txs"],
                        "gas_share_on_pending_acquisitions_ledger": L["gas_share_on_pending_acquisitions"], "gas": g,
                        "identity_basis": fifo.identity(st), "counts": {k: rep[k] for k in ("pending_lots_open", "pending_lots_total",
                        "pending_disposals", "pending_reasons", "exits", "exits_pending", "craft_lots", "craft_split_equal_fallbacks", "free_craft_lots",
                        "excluded_rows")}, "unmarked_nft_lots": rep["all"]["unmarked_nft_lots"], "unmarked_lots": rep["all"]["unmarked_lots"],
                        "totals_all": {k: rep["all"][k] for k in ("realized_usdc", "unrealized_usdc", "market_value_usdc", "open_basis_usdc")},
                        "totals_excl_low": {k: rep["excl_low"][k] for k in ("realized_usdc", "unrealized_usdc", "market_value_usdc", "open_basis_usdc")},
                        "income_usdc": rep["income_usdc"], "expenses_usdc": rep["expenses_usdc"], "exit_basis_usdc": rep["exit_basis_usdc"],
                        "exit_display_mv_usdc": rep["exit_display_mv_usdc"]})
            out["exit_rc"] = 0 if chk["acceptance"] == "PASS" else (3 if chk["identity_pass"] else 1)   # 3 = identity ok, gaps flagged
    txt = json.dumps(_j(out), indent=1, sort_keys=True) + "\n"
    if a.out:
        with open(a.out, "w") as f: f.write(txt)
    print(txt if a.cmd != "snapshot" else json.dumps(_j({k: v for k, v in out.items() if k != "report"}), sort_keys=True))
    return out.get("exit_rc", 0)

if __name__ == "__main__": sys.exit(main())
