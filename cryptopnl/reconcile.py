"""P4 reconciliation (DESIGN §8 'P4 rulings (2026-10-28)' Q-C and 'P4 rulings 2' gas). The right-hand side is rebuilt from ledger rows
and ledger quantities with NO code shared with the lot engine (cryptopnl/fifo.py is not called here):

    Σ_asset (realized + unrealized) − gas_expense  ==  Σ_asset [ S + MV + X + C − A ] − gas_expense_ledger      (each within 0.01 USDC)

  S  sale proceeds: |qty| x unit price of every priced out-leg that is a trade, spend, craft input or gas payment, for the part of it
     that consumed resolved lots; minus the gas share of a tx with a sale and no acquisition (gas comes off the sale's proceeds)
  MV market value of the open resolved quantity at as_of_block (ledger in-qty of resolved lots − resolved out-qty) x the stored mark
  X  basis of exited lots (Q-B exit: realized 0)          C  cost of resolved lots disposed without a price (counted; never 0)
  A  acquisition basis of resolved lots: buys (trade value), income at FMV, bridge_in, migration carry/manual, craft outputs (the value
     of the craft inputs under the same ref), plus the gas of the tx when it went into the acquisitions' basis (pro rata to basis when
     all of the tx's acquisitions are resolved with bases > 0, else equal; a pending acquisition's share stays outside both sides)
  gas_expense_ledger: gas of txs with no trade leg, the resolved part.
The only inputs taken from the lot tables are the masks the ruling allows: which part of each out-leg consumed pending lots, whether
the lot an in-leg opened is pending, exit basis, and unpriced-disposal cost. Pending lots are excluded from both sides and counted.
NFT assets left unmarked (Q8: no P3 price) are excluded from both sides and counted. Exact Decimal arithmetic."""
from decimal import Decimal
from typing import Callable, Dict, List, Optional

D0 = Decimal(0); TOL = Decimal("0.01")
TRADE = ("swap", "nft_buy", "nft_sale", "auction")
CUSTODY = ("escrow_out", "escrow_return", "transfer_internal")
OUT_VALUED = TRADE + ("spend", "craft", "craft_pending", "fee")
UNSUPPORTED = ("upgrade", "destroy_refund")   # Base ledger has none; the ledger side does not model them (fails loudly)

def _skip(e): return e.excluded or e.category in ("spam", "untracked") or e.flag in ("spam", "untracked")
def _v(e): return None if e.price is None else abs(e.qty) * e.price

def masks(st) -> dict:
    """Pending / exit / unpriced masks from the lot state (data only, no engine code)."""
    out_res: Dict[int, Decimal] = {}; in_res: Dict[int, bool] = {}; X: Dict[str, Decimal] = {}; C: Dict[str, Decimal] = {}
    lot = {l.id: l for l in st.lots}
    for d in st.disposals:
        a = lot[d.lot].asset
        if d.lot_status == "pending": continue
        out_res[d.entry] = out_res.get(d.entry, D0) + d.qty
        if d.kind == "exit": X[a] = X.get(a, D0) + d.cost
        elif d.proceeds is None and d.cost is not None: C[a] = C.get(a, D0) + d.cost
    for l in st.lots:
        if l.parent is None and l.kind != "unrecorded": in_res[l.open_entry] = l.status != "pending"
    unrec: Dict[str, Decimal] = {}
    for l in st.lots:
        if l.parent is None and l.kind == "unrecorded": unrec[l.asset] = unrec.get(l.asset, D0) + l.qty_open
    return {"out_res": out_res, "in_res": in_res, "exit_basis": X, "unpriced_cost": C, "unrecorded_qty": unrec}

def ledger_side(rows: List, m: dict, mark: Callable, nft_mark: Callable, as_of_block: int, recipe: Optional[Callable] = None) -> dict:
    live = [e for e in rows if not _skip(e)]
    bad = sorted({e.category for e in live if e.category in UNSUPPORTED})
    if bad: raise ValueError(f"ledger side does not model {bad}")
    by_tx: Dict[tuple, list] = {}
    for e in live: by_tx.setdefault((e.block, e.tx_index, e.tx), []).append(e)
    S: Dict[str, Decimal] = {}; A: Dict[str, Decimal] = {}; Q: Dict[str, Decimal] = {}; nft: Dict[str, bool] = {}
    add = lambda dct, a, v: dct.__setitem__(a, dct.get(a, D0) + v)
    ge = D0; n_gas_exp = n_gas_buy = n_gas_sell = 0; gas_pending_share = D0
    res_frac = lambda e: (m["out_res"].get(e.id, D0) / abs(e.qty)) if e.qty else D0
    for k in sorted(by_tx):
        es = by_tx[k]
        for e in es: nft[e.asset] = nft.get(e.asset, False) or e.nft
        # trade-implied unit value of the single unpriced leg of a trade group (same rule as the books: other side all priced)
        val: Dict[int, Optional[Decimal]] = {e.id: _v(e) for e in es}
        groups: Dict[str, list] = {}
        for e in es:
            if e.category in TRADE: groups.setdefault(e.trade_group or e.tx, []).append(e)
        for G in groups.values():
            for side, other in ((lambda x: x.qty < 0, lambda x: x.qty > 0), (lambda x: x.qty > 0, lambda x: x.qty < 0)):
                un = [x for x in G if side(x) and val[x.id] is None]; ot = [x for x in G if other(x)]
                if len(un) == 1 and ot and all(val[x.id] is not None for x in ot): val[un[0].id] = sum(val[x.id] for x in ot)
        acq = []   # (entry, basis value or None) of acquisitions that take gas
        crafts: Dict[str, list] = {}
        for e in es:
            if e.category in CUSTODY: continue
            if e.qty < 0:
                if e.category in ("withdrawal",): Q[e.asset] = Q.get(e.asset, D0) - m["out_res"].get(e.id, D0); continue
                rq = m["out_res"].get(e.id, D0); Q[e.asset] = Q.get(e.asset, D0) - rq
                if e.category in OUT_VALUED and e.category != "fee" and val[e.id] is not None: add(S, e.asset, val[e.id] * rq / abs(e.qty))
                if e.category in ("craft", "craft_pending"):
                    for r in [x for x in (e.ref or "craft:unref").split(";") if x] or ["craft:unref"]:
                        c = crafts.setdefault(r, [D0]); n = len([x for x in (e.ref or "craft:unref").split(";") if x]) or 1
                        c[0] = None if (c[0] is None or val[e.id] is None) else c[0] + val[e.id] / n
            elif e.qty > 0:
                ok = m["in_res"].get(e.id, False)
                if ok: Q[e.asset] = Q.get(e.asset, D0) + e.qty
                if e.category in TRADE:
                    acq.append((e, val[e.id], ok))
                    if ok: add(A, e.asset, val[e.id])
                elif e.category in ("income", "bridge_in", "deposit") and ok: add(A, e.asset, val[e.id])
                elif e.category == "migration_in" and ok: add(A, e.asset, e.carry_basis if e.carry_basis is not None else e.manual_basis)
        # craft outputs: basis = the inputs' value under the same ref (split per unit; recipe split when several assets)
        mints = [e for e in es if e.category in ("craft", "craft_pending") and e.qty > 0]
        for r in sorted({x.ref or "craft:unref" for x in mints}):
            ms = [x for x in mints if (x.ref or "craft:unref") == r]
            if r not in crafts: continue                       # free craft (basis 0) or a claim of an earlier queue (not on Base)
            tot = crafts[r][0]; w = [x.qty for x in ms]
            if len({x.asset for x in ms}) > 1 and recipe is not None:
                rc = [recipe(x.asset, x.block) for x in ms]
                if all(c is not None and c > 0 for c in rc): w = [x.qty * c for x, c in zip(ms, rc)]
            W = sum(w)
            for x, wi in zip(ms, w):
                b = None if tot is None else tot * wi / W
                acq.append((x, b, m["in_res"].get(x.id, False)))
                if m["in_res"].get(x.id, False) and b is not None: add(A, x.asset, b)
        # gas (rulings 2): into the acquisitions' basis, else off the sales' proceeds, else gas_expense
        for f in [e for e in es if e.category == "fee"]:
            g = _v(f); fr = res_frac(f)
            if g is None: continue
            add(S, f.asset, g * fr)                               # the ETH gas disposal at market value (resolved part)
            sales = [e for e in es if e.category in TRADE and e.qty < 0 and val[e.id] is not None]
            if acq:
                n_gas_buy += 1
                allres = all(ok for _, _, ok in acq) and all(b is not None for _, b, _ in acq) and sum(b for _, b, _ in acq) > 0
                W = sum(b for _, b, _ in acq) if allres else Decimal(len(acq))
                for x, b, ok in acq:
                    sh = g * (b if allres else Decimal(1)) / W
                    if ok: add(A, x.asset, sh)
                    else: gas_pending_share += sh
            elif sales:
                n_gas_sell += 1; W = sum(val[e.id] for e in sales)
                for e in sales: add(S, e.asset, -g * val[e.id] / W * res_frac(e))
            else: n_gas_exp += 1; ge += g * fr
    per = {}; excl_nft = []; unmarked = []
    for a in sorted(set(S) | set(A) | set(Q) | set(m["exit_basis"]) | set(m["unpriced_cost"])):
        q = Q.get(a, D0); mv = D0; mk = None
        if q != 0:
            mk = nft_mark(a, as_of_block, None) if nft.get(a) else mark(a, as_of_block)
            if mk is None:
                (excl_nft if nft.get(a) else unmarked).append(a); continue
            mv = q * mk.price
        per[a] = {"S": S.get(a, D0), "MV": mv, "X": m["exit_basis"].get(a, D0), "C": m["unpriced_cost"].get(a, D0), "A": A.get(a, D0),
                  "open_resolved_qty": q, "mark_price": None if mk is None else mk.price}
        per[a]["rhs"] = per[a]["S"] + per[a]["MV"] + per[a]["X"] + per[a]["C"] - per[a]["A"]
    return {"per_asset": per, "gas_expense_resolved": ge, "excluded_nft_assets": excl_nft, "unmarked_assets": unmarked,
            "gas_txs": {"into_basis": n_gas_buy, "off_proceeds": n_gas_sell, "expense": n_gas_exp},
            "gas_share_on_pending_acquisitions": gas_pending_share}

def check(engine_report: dict, engine_gas: dict, L: dict, engine_open_qty: Dict[str, Decimal], ledger_net_qty: Dict[str, Decimal],
          unrecorded_qty: Dict[str, Decimal]) -> dict:
    """Per-asset and total residuals (engine − ledger side) at TOL; open lot qty vs ledger net qty per asset."""
    by = engine_report["all"]["by_asset"]; rows = {}; fails = []
    lhs_tot = rhs_tot = D0
    for a, r in L["per_asset"].items():
        e = by.get(a, {}); lhs = Decimal(e.get("realized", "0")) + Decimal(e.get("unrealized", "0"))
        res = lhs - r["rhs"]; lhs_tot += lhs; rhs_tot += r["rhs"]
        rows[a] = {"engine": lhs, "ledger": r["rhs"], "residual": res, **{k: r[k] for k in ("S", "MV", "X", "C", "A", "open_resolved_qty")}}
        if abs(res) > TOL: fails.append(f"asset {a}: residual {res}")
    skipped = set(L["excluded_nft_assets"]) | set(L["unmarked_assets"])
    skipped_engine = sum((Decimal(v.get("realized", "0")) + Decimal(v.get("unrealized", "0")) for a, v in by.items() if a in skipped), D0)
    ge_e = Decimal(engine_gas["gas_expense_resolved_usdc"]); ge_l = L["gas_expense_resolved"]
    tot_res = (lhs_tot - ge_e) - (rhs_tot - ge_l)
    if abs(tot_res) > TOL: fails.append(f"total: residual {tot_res}")
    if abs(ge_e - ge_l) > TOL: fails.append(f"gas_expense: engine {ge_e} vs ledger {ge_l}")
    qty = {}
    for a in sorted(set(engine_open_qty) | set(ledger_net_qty)):
        eq, lq, uq = engine_open_qty.get(a, D0), ledger_net_qty.get(a, D0), unrecorded_qty.get(a, D0)
        if eq != lq: qty[a] = {"engine_open": eq, "ledger_net": lq, "diff": eq - lq, "unrecorded_inflow": uq, "explained": eq - lq == uq}
    qfail = [a for a, v in qty.items() if not v["explained"]]
    if qfail: fails.append(f"open qty != ledger net qty (not explained by unrecorded_inflow) for {len(qfail)} assets")
    return {"pass": not fails, "failures": fails, "tolerance_usdc": TOL, "per_asset": rows,
            "total": {"engine_realized_plus_unrealized": lhs_tot, "engine_gas_expense_resolved": ge_e, "engine_side": lhs_tot - ge_e,
                      "ledger_side_before_gas": rhs_tot, "ledger_gas_expense_resolved": ge_l, "ledger_side": rhs_tot - ge_l, "residual": tot_res},
            "skipped_assets": {"nft_unmarked": len(L["excluded_nft_assets"]), "fungible_unmarked": len(L["unmarked_assets"]),
                               "engine_pnl_in_skipped_assets": skipped_engine},
            "qty_mismatches": qty, "qty_unexplained": qfail}
