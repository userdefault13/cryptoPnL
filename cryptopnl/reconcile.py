"""P4 reconciliation (DESIGN §8 P4 rulings Q-C, rulings 2 gas, rulings 3 independence). The ledger side is rebuilt from ledger_entry
rows ALONE: no engine code is called and nothing is read from the lot tables (fifo_lot / lot_disposal / the engine State).

Ledger side, per asset:
  * pending vs resolved comes from ledger categories: deposit -> pending (Q-B); migration_in -> carried / manual basis, else pending;
    trade, income (FMV), bridge_in, craft outputs -> resolved when a value is known (trade-implied for the single unpriced leg of a
    trade group), else pending; gift_in -> basis 0.
  * its own running quantity balance per (asset, location), consumed oldest first, carried through custody legs (escrow, pocket,
    lending, own wallets). An out-leg larger than the balance is an UNEXPLAINED GAP (asset, qty, entry, block): the missing qty is
    carried as pending so the run can continue, and the gap is reported and flagged, never passed.
  * gas (rulings 2 + 3): every gas leg is an ETH disposal at market value; it comes off an NFT sale's proceeds (nft_sale / auction
    seller), else goes into the tx's acquisitions' basis (pro rata to basis when all resolved with bases > 0, else equal; a pending
    acquisition keeps its share outside), else off the tx's sale proceeds, else gas_expense.
  * exits (Q-B withdrawal): no realized PnL, basis X counted.
Identity (Q-C): Σ(realized + unrealized) = S + MV + X + C + M − A per asset, where S = proceeds of resolved priced disposals (gas
already deducted where it applies), MV = market value of marked open resolved quantity, X = exited basis, C = cost of resolved lots
disposed without a price, M = basis of open resolved lots left unmarked (Q8 NFTs), A = acquisition basis of resolved lots (incl. gas).
check() compares the engine's realized and unrealized per asset with the ledger side's (and the totals minus gas_expense) at 0.01 USDC,
and the engine's open quantity with the ledger side's balance. Exact Decimal arithmetic."""
from decimal import Decimal
from typing import Callable, Dict, List, Optional

D0 = Decimal(0); TOL = Decimal("0.01")
TRADE = ("swap", "nft_buy", "nft_sale", "auction"); NFT_SALE = ("nft_sale", "auction")
CUSTODY = ("escrow_out", "escrow_return", "transfer_internal")
RULINGS = {"deposit": "pending", "withdrawal": "exit", "fee": "capitalize", "fee_without_trade": "expense", "fee_split": "basis_else_equal",
           "internal_transfer": "carry", "shortfall": "pending"}

def _skip(e): return e.excluded or e.category in ("spam", "untracked") or e.flag in ("spam", "untracked")
def _v(e): return None if e.price is None else abs(e.qty) * e.price
def _refs(r): return [x for x in (r or "").split(";") if x]

class _Chunk:
    __slots__ = ("qty_open", "qty", "basis", "out", "order", "seq", "nft", "gap")
    def __init__(self, qty, basis, order, seq, nft, gap=False):
        self.qty_open = self.qty = qty; self.basis = basis; self.out = D0; self.order = order; self.seq = seq; self.nft = nft; self.gap = gap
    def cost(self, q):   # basis of q units leaving (exact remainder on the last unit); None while pending
        if self.basis is None: return None
        c = self.basis - self.out if q == self.qty else self.basis * q / self.qty_open
        self.out += c; return c

class Ledger:
    def __init__(self, recipe=None):
        self.pools: Dict[tuple, List[_Chunk]] = {}; self.seq = 0; self.recipe = recipe; self.buckets: Dict[str, Optional[Decimal]] = {}
        self.a: Dict[str, dict] = {}; self.gaps: List[dict] = []; self.ge_total = D0; self.ge_res = D0
        self.gas_txs = {"nft_sale": 0, "into_basis": 0, "off_proceeds": 0, "expense": 0}; self.gas_on_pending = D0
    def A(self, asset):
        return self.a.setdefault(asset, {"R": D0, "S": D0, "X": D0, "C": D0, "A": D0, "exits": 0, "unpriced": 0, "pending_disposals": 0,
                                              "bridge_in_pending": 0, "bridge_in_manual": 0})
    def chunk(self, e, asset, loc, qty, basis):
        self.seq += 1; c = _Chunk(qty, basis, e.key(), self.seq, e.nft); self.pools.setdefault((asset, loc), []).append(c)
        if basis is not None: self.A(asset)["A"] += basis
        return c
    def take(self, e, loc=None):
        """FIFO parts [(chunk, qty)] for |e.qty| of e.asset at loc (default e.location); a shortfall is an unexplained gap."""
        loc = loc or e.location; need = abs(e.qty); pool = sorted((c for c in self.pools.get((e.asset, loc), []) if c.qty > 0), key=lambda c: (c.order, c.seq))
        out = []
        for c in pool:
            if need <= 0: break
            q = min(c.qty, need); out.append((c, q)); need -= q
        if need > 0:
            self.gaps.append({"asset": e.asset, "location": loc, "qty": need, "entry": e.id, "block": e.block, "category": e.category})
            self.seq += 1; g = _Chunk(need, None, e.key(), self.seq, e.nft, gap=True); self.pools.setdefault((e.asset, loc), []).append(g)
            out.append((g, need))
        return out
    def consume(self, e, loc=None):
        """-> (resolved qty, resolved cost, pending qty); the chunks are reduced."""
        rq = rc = pq = D0
        for c, q in self.take(e, loc):
            k = c.cost(q); c.qty -= q
            if k is None: pq += q
            else: rq += q; rc += k
        return rq, rc, pq

def ledger_side(rows: List, mark: Callable, nft_mark: Callable, as_of_block: int, recipe: Optional[Callable] = None,
                switches: Optional[dict] = None) -> dict:
    if switches is not None:
        bad = {k: switches.get(k) for k in RULINGS if switches.get(k) != RULINGS[k]}
        if bad: raise ValueError(f"the ledger side models the ruled switches only; differs: {bad}")
    L = Ledger(recipe); live = [e for e in rows if not _skip(e) and e.block <= as_of_block]
    for e in live:
        if e.category in ("upgrade", "destroy_refund") or any(r.startswith("bundle:parcel:") for r in _refs(e.ref)):
            raise ValueError(f"ledger side does not model {e.category} / bundles (none on Base)")
    txs: Dict[tuple, list] = {}
    for e in live: txs.setdefault(e.key()[:3], []).append(e)
    for k in sorted(txs): _tx(L, sorted(txs[k], key=lambda e: e.key()))
    # open positions at the marks
    per = {}
    for (asset, loc), cs in L.pools.items():
        for c in cs:
            if c.qty <= 0 or c.basis is None: continue
            a = L.A(asset); a.setdefault("MV", D0); a.setdefault("U", D0); a.setdefault("M", D0); a.setdefault("unmarked", 0)
            a.setdefault("open_resolved_qty", D0); rb = c.basis - c.out; a["open_resolved_qty"] += c.qty
            m = nft_mark(asset, as_of_block, None) if c.nft else mark(asset, as_of_block)
            if m is None: a["M"] += rb; a["unmarked"] += 1; continue
            mv = c.qty * m.price; a["MV"] += mv; a["U"] += mv - rb
    open_qty: Dict[str, Decimal] = {}
    for (asset, loc), cs in L.pools.items():
        for c in cs:
            if c.qty > 0: open_qty[asset] = open_qty.get(asset, D0) + c.qty
    for asset, a in L.a.items():
        for k in ("MV", "U", "M", "open_resolved_qty"): a.setdefault(k, D0)
        a.setdefault("unmarked", 0)
        a["formula"] = a["S"] + a["MV"] + a["X"] + a["C"] + a["M"] - a["A"]; a["R_plus_U"] = a["R"] + a["U"]
        per[asset] = a
    gap = {}
    for g in L.gaps:
        x = gap.setdefault(g["asset"], {"qty": D0, "events": 0, "first_block": g["block"], "last_block": g["block"], "by_category": {}})
        x["qty"] += g["qty"]; x["events"] += 1; x["last_block"] = g["block"]; x["by_category"][g["category"]] = x["by_category"].get(g["category"], 0) + 1
    net: Dict[str, Decimal] = {}
    for e in live: net[e.asset] = net.get(e.asset, D0) + e.qty
    return {"per_asset": per, "gas_expense_total": L.ge_total, "gas_expense_resolved": L.ge_res, "gas_txs": L.gas_txs,
            "gas_share_on_pending_acquisitions": L.gas_on_pending, "unexplained_gap": gap, "open_qty": open_qty,
            "ledger_net_qty": {a: q for a, q in net.items() if q != 0}, "rows": len(live)}

def _refund_net(es: list) -> list:
    """P4.1 rulings 3, written independently of the engine: per (asset, category), the tx's refund in-legs (ref 'eth_refund') are
    summed and taken off the out-legs of that asset and category, oldest leg first; the refund rows themselves leave."""
    from dataclasses import replace
    ref = {}
    for e in es:
        if e.ref == "eth_refund" and e.qty > 0: ref[(e.asset, e.category)] = ref.get((e.asset, e.category), D0) + e.qty
    if not ref: return es
    keep = []
    for e in es:
        if e.ref == "eth_refund" and e.qty > 0: continue
        k = (e.asset, e.category); r = ref.get(k, D0)
        if r and e.qty < 0:
            t = min(r, -e.qty); ref[k] = r - t; e = replace(e, qty=e.qty + t)
            if e.qty == 0: continue
        keep.append(e)
    left = {k: v for k, v in ref.items() if v}
    if left: raise ValueError(f"ETH refund with no ETH sent left to net in its tx: {left}")
    return keep

def _tx(L: Ledger, es: list):
    es = _refund_net(es)
    # 1 custody legs: pair out/in (asset, category, |qty|, ref); the balance moves location, nothing is realized
    cus = [e for e in es if e.category in CUSTODY]; ins = [e for e in cus if e.qty > 0]
    for n in [e for e in cus if e.qty < 0]:
        m = next((i for i in ins if i.asset == n.asset and i.category == n.category and i.qty == -n.qty and i.ref == n.ref), None)
        if m is None: raise ValueError(f"entry {n.id}: custody out-leg without its in-leg")
        ins.remove(m)
        for c, q in L.take(n):
            if q == c.qty: L.pools[(n.asset, n.location)].remove(c); L.pools.setdefault((m.asset, m.location), []).append(c); continue
            k = c.cost(q); c.qty -= q; L.seq += 1; ch = _Chunk(q, k, c.order, L.seq, c.nft, c.gap); L.pools.setdefault((m.asset, m.location), []).append(ch)
    if ins: raise ValueError(f"entry {ins[0].id}: custody in-leg without its out-leg")
    rest = [e for e in es if e.category not in CUSTODY]
    acq = []; sales = []
    # 2 crafts: inputs are disposals at value; the minted items' basis = the inputs' value under the same ref
    now: Dict[str, Optional[Decimal]] = {}
    for e in [x for x in rest if x.category in ("craft", "craft_pending") and x.qty < 0]:
        sales.append(_out(L, e, _v(e), "craft_input"))
        rs = _refs(e.ref) or ["craft:unref"]; tgt = L.buckets if e.category == "craft_pending" else now
        for r in rs:
            v = _v(e); tgt[r] = None if (r in tgt and tgt[r] is None) or v is None else tgt.get(r, D0) + v / len(rs)
    mints = [x for x in rest if x.category in ("craft", "craft_pending") and x.qty > 0]
    for r in sorted({m.ref or "" for m in mints}):
        ms = [m for m in mints if (m.ref or "") == r]
        if r in now: tot = now.pop(r); free = False
        elif r in L.buckets: tot = L.buckets.pop(r); free = False
        elif r.startswith("craft:queue:"):
            for m in ms: acq.append((m, L.chunk(m, m.asset, m.location, m.qty, None)))   # queue cost never seen: pending, still a gas target
            continue
        else: tot, free = D0, True
        w = [m.qty for m in ms]
        if not free and len({m.asset for m in ms}) > 1 and L.recipe is not None:
            rc = [L.recipe(m.asset, m.block) for m in ms]
            if all(c is not None and c > 0 for c in rc): w = [m.qty * c for m, c in zip(ms, rc)]
        W = sum(w)
        for m, wi in zip(ms, w):
            c = L.chunk(m, m.asset, m.location, m.qty, None if tot is None else tot * wi / W)
            if not free: acq.append((m, c))
    # 3 trades and other flows, per trade group (outs, then ins)
    groups: Dict[str, list] = {}
    for e in rest:
        if e.category not in ("craft", "craft_pending", "fee"): groups.setdefault(e.trade_group or e.tx, []).append(e)
    for g in sorted(groups):
        G = groups[g]; outs = [e for e in G if e.qty < 0]; ins_ = [e for e in G if e.qty > 0]
        def other(es):
            vs = [_v(x) for x in es]; return None if not es or any(v is None for v in vs) else sum(vs)
        for e in outs:
            v = _v(e)
            if v is None and e.category in TRADE and sum(1 for x in outs if _v(x) is None) == 1: v = other(ins_)
            if e.category in TRADE: sales.append(_out(L, e, v, "sale"))
            elif e.category == "spend": sales.append(_out(L, e, v, "spend"))
            elif e.category == "withdrawal":
                rq, rc, pq = L.consume(e); a = L.A(e.asset)
                if rq: a["X"] += rc; a["exits"] += 1
                if pq: a["pending_disposals"] += 1
            else: raise ValueError(f"entry {e.id}: outflow category {e.category!r} not modelled")
        for e in ins_:
            v = _v(e)
            if e.category in TRADE:
                if v is None and sum(1 for x in ins_ if _v(x) is None) == 1: v = other(outs)
                acq.append((e, L.chunk(e, e.asset, e.location, e.qty, v)))
            elif e.category == "bridge_in" and (e.ref or "").split(";")[0].startswith("bridge_in:"):
                L.chunk(e, e.asset, e.location, e.qty, e.manual_basis)   # P4.1 rulings 4: pending (unknown) unless manual_basis
                L.A(e.asset)["bridge_in_pending" if e.manual_basis is None else "bridge_in_manual"] += 1
            elif e.category in ("income", "bridge_in"): L.chunk(e, e.asset, e.location, e.qty, v)
            elif e.category == "deposit": L.chunk(e, e.asset, e.location, e.qty, None)          # Q-B: unknown basis
            elif e.category == "gift_in": L.chunk(e, e.asset, e.location, e.qty, D0)
            elif e.category == "migration_in":
                L.chunk(e, e.asset, e.location, e.qty, e.carry_basis if e.carry_basis is not None else e.manual_basis)
            else: raise ValueError(f"entry {e.id}: inflow category {e.category!r} not modelled")
    # 4 gas
    for f in [e for e in rest if e.category == "fee"]:
        g = _v(f); d = _out(L, f, g, "gas")
        if g is None: _close(L, d); continue
        nft_s = [s for s in sales if s["kind"] == "sale" and s["nft"] and s["cat"] in NFT_SALE and s["v"] is not None]
        if nft_s: L.gas_txs["nft_sale"] += 1; _deduct(nft_s, g)
        elif acq:
            L.gas_txs["into_basis"] += 1
            ok = all(c.basis is not None for _, c in acq) and sum(c.basis for _, c in acq) > 0
            W = sum(c.basis for _, c in acq) if ok else Decimal(len(acq))
            for e, c in acq:
                sh = g * (c.basis if ok else Decimal(1)) / W
                if c.basis is None: L.gas_on_pending += sh
                else: c.basis += sh; L.A(e.asset)["A"] += sh
        else:
            sl = [s for s in sales if s["kind"] == "sale" and s["v"] is not None]
            if sl: L.gas_txs["off_proceeds"] += 1; _deduct(sl, g)
            else:
                L.gas_txs["expense"] += 1; L.ge_total += g; L.ge_res += g * d["rq"] / d["q"]
        _close(L, d)
    for s in sales: _close(L, s)

def _out(L, e, v, kind):
    rq, rc, pq = L.consume(e)
    return {"asset": e.asset, "v": v, "q": abs(e.qty), "rq": rq, "rc": rc, "pq": pq, "kind": kind, "nft": e.nft, "cat": e.category, "done": False}
def _deduct(ss, g):
    W = sum(s["v"] for s in ss)
    for s in ss: s["v"] = s["v"] - g * s["v"] / W
def _close(L, s):
    if s["done"]: return
    s["done"] = True; a = L.A(s["asset"])
    if s["pq"]: a["pending_disposals"] += 1
    if not s["rq"]: return
    if s["v"] is None: a["C"] += s["rc"]; a["unpriced"] += 1; return
    p = s["v"] * s["rq"] / s["q"]; a["S"] += p; a["R"] += p - s["rc"]

def check(engine_report: dict, engine_gas: dict, L: dict, engine_open_qty: Dict[str, Decimal]) -> dict:
    """Engine vs ledger side per asset (realized, unrealized) and in total (minus gas_expense), at TOL; the ledger-side formula
    against its own realized + unrealized; engine open qty vs the ledger side's running balance. Gaps are flagged, never passed."""
    by = engine_report["all"]["by_asset"]; rows = {}; fails = []
    tE = tL = D0
    for a in sorted(set(L["per_asset"]) | set(by)):
        e = by.get(a, {}); l = L["per_asset"].get(a, {})
        rE, uE = Decimal(e.get("realized", "0")), Decimal(e.get("unrealized", "0")); rL, uL = l.get("R", D0), l.get("U", D0)
        rr, ru = rE - rL, uE - uL; tE += rE + uE; tL += rL + uL
        rows[a] = {"engine_realized": rE, "ledger_realized": rL, "realized_residual": rr, "engine_unrealized": uE, "ledger_unrealized": uL,
                   "unrealized_residual": ru, "residual": rr + ru, **{k: l.get(k, D0) for k in ("S", "MV", "X", "C", "M", "A", "open_resolved_qty")},
                   "formula_minus_ledger": l.get("formula", D0) - l.get("R_plus_U", D0), "exits": l.get("exits", 0)}
        if abs(rr) > TOL or abs(ru) > TOL: fails.append(f"asset {a}: realized residual {rr}, unrealized residual {ru}")
        if abs(rows[a]["formula_minus_ledger"]) > TOL: fails.append(f"asset {a}: ledger formula off by {rows[a]['formula_minus_ledger']}")
    geE = Decimal(engine_gas["gas_expense_resolved_usdc"]); geL = L["gas_expense_resolved"]
    total = (tE - geE) - (tL - geL)
    if abs(total) > TOL: fails.append(f"total: residual {total}")
    if abs(geE - geL) > TOL: fails.append(f"gas_expense: engine {geE} vs ledger {geL}")
    qty = {}
    for a in sorted(set(engine_open_qty) | set(L["open_qty"])):
        x, y = engine_open_qty.get(a, D0), L["open_qty"].get(a, D0)
        if x != y: qty[a] = {"engine_open": x, "ledger_balance": y}
    if qty: fails.append(f"engine open qty != ledger running balance for {len(qty)} assets")
    gaps = L["unexplained_gap"]; identity_ok = not fails
    return {"identity_pass": identity_ok, "failures": fails, "tolerance_usdc": TOL, "per_asset": rows,
            "acceptance": "FAIL" if not identity_ok else ("FLAGGED: UNEXPLAINED GAP" if gaps else "PASS"),
            "unexplained_gap": gaps, "qty_mismatch_engine_vs_ledger": qty,
            "total": {"engine_realized_plus_unrealized": tE, "engine_gas_expense_resolved": geE, "engine_side": tE - geE,
                      "ledger_realized_plus_unrealized": tL, "ledger_gas_expense_resolved": geL, "ledger_side": tL - geL, "residual": total},
            "exits": sum(r["exits"] for r in rows.values())}
