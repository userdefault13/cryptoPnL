"""P4 FIFO engine (DESIGN v1.3 §0, §2, §3 FIFO rules, §8 P4 requirements, §9 rules 1-8). Pure functions: no DB, no network, no clock.

Input: `Entry` rows, one per ledger_entry leg. qty is signed, in whole-token units (the DB adapter divides by 10**decimals; NFTs count items).
price is the P3 unit USDC price at the tx block (POB/POS) or None. Prices are never invented: a 0 price is rejected, and an unpriced leg
gives a pending lot (unknown basis) or an unpriced disposal (proceeds None), both excluded from totals and counted.
Output: `State` (lots, disposals, pending cost buckets, counters). `run(entries, policy, state)` is deterministic, and
`run(B, p, run(A, p))` == `run(A + B, p)` when every entry of B sorts after every entry of A (recompute from block X).

Open design questions are `Policy` fields with NO default. The engine raises PolicyRequired("<question id>") the first time
it meets a row that needs an answer, so nothing is guessed:
  Q-A fee               DESIGN §5 Q7: gas 'expense' | 'capitalize'; fee_without_trade ('expense') for a capitalized fee in a tx with no trade leg
  Q-B deposit           'acquire_fmv' | 'pending';  withdrawal 'dispose_fmv' | 'custody_exit'
  Q-D nft_mark          DESIGN §5 Q8: 'exclude' | 'at_basis' | callable(asset, as_of_block, lot) -> Mark | None
  Q-E internal_transfer DESIGN §5 Q2: 'carry' | 'dispose_acquire' (transfer between two own wallets of the group)
  Q-F mark              callable(asset, as_of_block) -> Mark | None (which block, which price source); used by report()
  Q-G queue_split       'equal' (cost of one input ref shared by several craft queues, or by several minted assets)
Decided rules (not hooks): custody moves (escrow_out/return, equip parcel:, pocket:, lent:) carry lots unchanged; income opens a lot
at FMV (§3); free craft = basis 0, not income (§9 r3); migration_in keeps the carried/manual basis, else pending with a NULL
source (§8); gift_in = basis 0, flagged (§9 r1); spend = disposal at market value plus an expense (§9 r9)."""
from __future__ import annotations
import copy, hashlib, json
from dataclasses import dataclass, field, asdict
from decimal import Decimal
from typing import Callable, Dict, List, Optional, Tuple, Union

class PolicyRequired(Exception):
    def __init__(self, question: str, why: str):
        super().__init__(f"policy {question} required: {why}"); self.question = question
class FifoError(Exception):
    """Input the engine cannot account for (e.g. disposing more than is held at a location). Never silently patched."""

CHOICES = {"fee": ("expense", "capitalize"), "fee_without_trade": ("expense",), "deposit": ("acquire_fmv", "pending"),
           "withdrawal": ("dispose_fmv", "custody_exit"), "internal_transfer": ("carry", "dispose_acquire"),
           "nft_mark": ("exclude", "at_basis"), "queue_split": ("equal",)}
QID = {"fee": "Q-A", "fee_without_trade": "Q-A", "deposit": "Q-B", "withdrawal": "Q-B", "nft_mark": "Q-D",
       "internal_transfer": "Q-E", "mark": "Q-F", "queue_split": "Q-G"}

@dataclass(frozen=True)
class Mark:
    price: Decimal; source: str; label: Optional[str] = None

@dataclass(frozen=True)
class Policy:
    fee: Optional[str] = None
    fee_without_trade: Optional[str] = None
    deposit: Optional[str] = None
    withdrawal: Optional[str] = None
    internal_transfer: Optional[str] = None
    nft_mark: Union[None, str, Callable] = None
    mark: Optional[Callable] = None
    queue_split: Optional[str] = None
    def __post_init__(self):
        for k, ok in CHOICES.items():
            v = getattr(self, k)
            if v is not None and not callable(v) and v not in ok: raise ValueError(f"{k}={v!r}: expected one of {ok}")
            if callable(v) and k != "nft_mark": raise ValueError(f"{k} must be one of {ok}")
    def need(self, k: str, why: str):
        v = getattr(self, k)
        if v is None: raise PolicyRequired(QID[k], f"{k}: {why}")
        return v

LOW = "low"
@dataclass(frozen=True)
class Entry:
    id: int; block: int; tx: str; log_index: int; asset: str; qty: Decimal; category: str
    wallet: str = "w1"; group: str = "default"; location: str = "wallet"; tx_index: int = 0
    ref: Optional[str] = None; trade_group: Optional[str] = None
    price: Optional[Decimal] = None; price_source: Optional[str] = None; label: Optional[str] = None
    flag: Optional[str] = None; excluded: bool = False; nft: bool = False
    # migration_in (§8): carried Polygon basis (P6) or user_default's manual entry; neither -> pending
    carry_basis: Optional[Decimal] = None; carry_source: Optional[str] = None; carry_label: Optional[str] = None; chain_origin: Optional[int] = None
    manual_basis: Optional[Decimal] = None; manual_basis_id: Optional[int] = None
    def key(self): return (self.block, self.tx_index, self.tx, self.log_index, self.id)
    def value(self) -> Optional[Decimal]:
        """|qty| x unit price at the tx block, or None (unpriced). A 0 price is never accepted (prices are not invented)."""
        if self.price is None: return None
        if self.price <= 0: raise FifoError(f"entry {self.id}: non-positive price {self.price} (a price is never 0)")
        return abs(self.qty) * self.price

@dataclass
class Lot:
    id: int; group: str; asset: str; wallet: str; location: str; open_entry: int; open_block: int; order: Tuple
    qty_open: Decimal; qty: Decimal; basis: Optional[Decimal]; source: Optional[str]; label: Optional[str]
    status: str; kind: str; nft: bool = False; ref: Optional[str] = None; parent: Optional[int] = None
    chain_origin: Optional[int] = None; pending_reason: Optional[str] = None; manual_basis_id: Optional[int] = None
    basis_out: Decimal = Decimal(0)   # basis already disposed or moved out; the last unit takes basis - basis_out, so sums are exact
    def per_unit(self) -> Optional[Decimal]:
        return None if self.basis is None else self.basis / self.qty_open
    def take_basis(self, q: Decimal) -> Optional[Decimal]:
        """Basis of q units leaving this lot (and books it as out)."""
        if self.basis is None: return None
        c = self.basis - self.basis_out if q == self.qty else self.basis * q / self.qty_open
        self.basis_out += c; return c
    def remaining_basis(self) -> Optional[Decimal]:
        return None if self.basis is None else self.basis - self.basis_out

@dataclass
class Disposal:
    id: int; lot: int; entry: int; block: int; qty: Decimal; kind: str
    proceeds: Optional[Decimal]; proceeds_source: Optional[str]; proceeds_label: Optional[str]; cost: Optional[Decimal]
    payment_for: Optional[int] = None; bundle_ref: Optional[str] = None; expense: Optional[Decimal] = None; lot_status: str = "resolved"
    own_cost: Optional[Decimal] = None   # bundle parcel row: the parcel's own basis (cost = own + the equipped items)
    @property
    def realized(self) -> Optional[Decimal]:
        if self.kind == "custody_exit" or self.proceeds is None or self.cost is None: return None
        return self.proceeds - self.cost

@dataclass
class State:
    lots: List[Lot] = field(default_factory=list); disposals: List[Disposal] = field(default_factory=list)
    buckets: Dict[str, list] = field(default_factory=dict)   # craft_pending / upgrade cost per queue ref: [USDC or None (an input unpriced), worst label]
    income: List[Tuple[int, str, Optional[Decimal]]] = field(default_factory=list)   # (entry, asset, FMV or None)
    excluded: Dict[str, int] = field(default_factory=dict); last_key: Optional[Tuple] = None; next_lot: int = 1; next_disp: int = 1
    def lot(self, i: int) -> Lot: return next(l for l in self.lots if l.id == i)

# ---------- helpers ----------
RANK = {"high": 2, "medium": 1, "low": 0}
def worst(*labels):
    ls = [l for l in labels if l is not None]
    return min(ls, key=lambda l: RANK.get(l, -1)) if ls else None
def _add(a, b):   # None (unknown) is absorbing: an unpriced input makes the whole cost unknown, never 0
    return None if a is None or b is None else a + b
def _split(total: Optional[Decimal], weights: List[Decimal]) -> List[Optional[Decimal]]:
    """Split total pro rata to weights; the last share takes the remainder so the shares sum exactly to total."""
    if total is None: return [None] * len(weights)
    W = sum(weights); out = []; acc = Decimal(0)
    for i, w in enumerate(weights):
        v = total - acc if i == len(weights) - 1 else (total * w / W if W else total / len(weights))
        out.append(v); acc += v
    return out

def _open(st: State, e: Entry, qty: Decimal, basis: Optional[Decimal], source: Optional[str], label: Optional[str], kind: str,
          status: str = "resolved", location: Optional[str] = None, pending_reason: Optional[str] = None, **kw) -> Lot:
    if basis is None and status != "pending": status, pending_reason = "pending", pending_reason or "no_price"
    if status == "pending": basis, source, label = None, None, None    # §8: pending lots carry a NULL basis and price source
    l = Lot(id=st.next_lot, group=e.group, asset=e.asset, wallet=e.wallet, location=location or e.location, open_entry=e.id, open_block=e.block,
            order=e.key(), qty_open=qty, qty=qty, basis=basis, source=source, label=label, status=status, kind=kind, nft=e.nft, ref=e.ref,
            pending_reason=pending_reason, **kw)
    st.next_lot += 1; st.lots.append(l); return l

def _take(st: State, group: str, asset: str, location: str, qty: Decimal, eid: int) -> List[Tuple[Lot, Decimal]]:
    """FIFO across the wallet group (DESIGN §3) within one location pool: oldest (block, tx_index, log_index) first."""
    pool = sorted((l for l in st.lots if l.group == group and l.asset == asset and l.location == location and l.qty > 0), key=lambda l: (l.order, l.id))
    out, need = [], qty
    for l in pool:
        if need <= 0: break
        q = min(l.qty, need); out.append((l, q)); need -= q
    if need > 0:
        raise FifoError(f"entry {eid}: disposes {qty} {asset} at {location} but only {qty - need} is held there")
    return out

def _dispose(st: State, e: Entry, kind: str, proceeds: Optional[Decimal], source: Optional[str], label: Optional[str],
             expense: Optional[Decimal] = None, bundle_ref: Optional[str] = None, location: Optional[str] = None) -> List[Disposal]:
    q = -e.qty if e.qty < 0 else e.qty
    parts = _take(st, e.group, e.asset, location or e.location, q, e.id)
    shares = _split(proceeds, [p for _, p in parts]); exp = _split(expense, [p for _, p in parts]) if expense is not None else [None] * len(parts)
    out = []
    for (l, p), pr, ex in zip(parts, shares, exp):
        cost = l.take_basis(p); l.qty -= p
        d = Disposal(id=st.next_disp, lot=l.id, entry=e.id, block=e.block, qty=p, kind=kind, proceeds=pr, proceeds_source=source if pr is not None else None,
                     proceeds_label=label if pr is not None else None, cost=cost, expense=ex, bundle_ref=bundle_ref, lot_status=l.status)
        st.next_disp += 1; st.disposals.append(d); out.append(d)
    return out

def _move(st: State, src: Entry, dst: Entry):
    """Custody (escrow, parcel equip, pocket, lending, own-wallet carry): lots keep basis, source, label and acquisition order."""
    q = dst.qty
    for l, p in _take(st, src.group, src.asset, src.location, q, src.id):
        if p == l.qty: l.location, l.wallet = dst.location, dst.wallet; continue
        c = l.take_basis(p); l.qty -= p
        st.lots.append(Lot(id=st.next_lot, group=l.group, asset=l.asset, wallet=dst.wallet, location=dst.location, open_entry=l.open_entry,
                           open_block=l.open_block, order=l.order, qty_open=p, qty=p, basis=c, source=l.source, label=l.label, status=l.status,
                           kind=l.kind, nft=l.nft, ref=l.ref, parent=l.id, chain_origin=l.chain_origin, pending_reason=l.pending_reason,
                           manual_basis_id=l.manual_basis_id))
        st.next_lot += 1

# ---------- per-tx handlers ----------
TRADE = ("swap", "nft_buy", "nft_sale", "auction")
CUSTODY = ("escrow_out", "escrow_return", "transfer_internal")
EXCLUDED_FLAGS = ("spam", "untracked")

def _custody(st: State, p: Policy, legs: List[Entry]) -> List[Entry]:
    """Pair each custody out-leg with its in-leg (same asset, category, |qty|, ref). Same wallet -> move. Two own wallets -> Q-E."""
    cus = [e for e in legs if e.category in CUSTODY]; rest = [e for e in legs if e.category not in CUSTODY]
    ins = [e for e in cus if e.qty > 0]
    for n in [e for e in cus if e.qty < 0]:
        m = next((i for i in ins if i.asset == n.asset and i.category == n.category and i.qty == -n.qty and i.ref == n.ref), None)
        if m is None: raise FifoError(f"entry {n.id}: custody leg {n.category} without its matching in-leg")
        ins.remove(m)
        if n.wallet != m.wallet and p.need("internal_transfer", f"entry {n.id} moves {n.asset} between own wallets {n.wallet}->{m.wallet}") == "dispose_acquire":
            _dispose(st, n, "internal", n.value(), n.price_source, n.label)
            _open(st, m, m.qty, m.value(), m.price_source, m.label, "internal")
        else: _move(st, n, m)
    if ins: raise FifoError(f"entry {ins[0].id}: custody in-leg {ins[0].category} without its out-leg")
    return rest

def _refs(ref: Optional[str]) -> List[str]: return [r for r in (ref or "").split(";") if r]

def _craft(st: State, p: Policy, legs: List[Entry]) -> List[Lot]:
    """§9 rule 3. Inputs are FIFO disposals at the craft block. Instant craft: the minted items' basis = USDC value of the inputs with
    the same ref. craft_pending: the cost waits in a bucket per queue ref until the claim (QueueClaimed) mints the item. No inputs
    (free craft) -> basis 0, never income. A claim whose queue cost was never seen -> pending lot (queue_unmatched), never 0."""
    now: Dict[str, list] = {}; opened = []
    for e in [x for x in legs if x.qty < 0]:
        v = e.value(); _dispose(st, e, "craft_input", v, e.price_source, e.label)
        rs = _refs(e.ref) or ["craft:unref"]
        if len(rs) > 1: p.need("queue_split", f"entry {e.id}: one input ref shared by {len(rs)} queues ({e.ref})")
        for r, share in zip(rs, _split(v, [Decimal(1)] * len(rs))):
            tgt = st.buckets if e.category == "craft_pending" else now
            b = tgt.setdefault(r, [Decimal(0), None]); b[0] = _add(b[0], share); b[1] = worst(b[1], e.label) if b[1] else e.label
    mints = [x for x in legs if x.qty > 0]
    for r in sorted({m.ref or "" for m in mints}):
        ms = [m for m in mints if (m.ref or "") == r]
        if r in now: (total, label), kind = now.pop(r), "craft"
        elif r in st.buckets: (total, label), kind = st.buckets.pop(r), "craft_claim"
        elif r.startswith("craft:queue:"):
            for m in ms: opened.append(_open(st, m, m.qty, None, None, None, "craft_claim", status="pending", pending_reason="queue_unmatched"))
            continue
        else: total, label, kind = Decimal(0), None, "free_craft"
        if len({m.asset for m in ms}) > 1: p.need("queue_split", f"ref {r}: one cost shared by several minted assets")
        for m, b in zip(ms, _split(total, [m.qty for m in ms])):
            opened.append(_open(st, m, m.qty, b, "free_craft" if kind == "free_craft" else "craft", label, kind))
    if now: raise FifoError(f"craft inputs with ref {sorted(now)} but no item minted under it in the same tx")
    return opened

def _upgrade(st: State, legs: List[Entry]) -> List[Lot]:
    """§9 rule 4. Cost legs dispose alchemica/GLTR at the upgrade block into the bucket of their ref. Finalize: the old id closes with
    NO realized PnL (proceeds = cost) and the new id opens at the same parcel location with old basis + the bucket."""
    opened = []
    for e in [x for x in legs if x.qty < 0 and not x.nft]:
        v = e.value(); _dispose(st, e, "upgrade_input", v, e.price_source, e.label)
        b = st.buckets.setdefault(e.ref or "upgrade:unref", [Decimal(0), None]); b[0] = _add(b[0], v); b[1] = worst(b[1], e.label) if b[1] else e.label
    nft = [x for x in legs if x.nft]
    for a in {x.asset for x in nft if x.location == "wallet"}:   # new id minted to the wallet and re-equipped in the same tx: transient
        if sum(x.qty for x in nft if x.asset == a and x.location == "wallet") != 0: raise FifoError(f"upgrade: wallet legs of {a} do not net to 0")
    olds = [x for x in nft if x.location != "wallet" and x.qty < 0]; news = [x for x in nft if x.location != "wallet" and x.qty > 0]
    for o in olds:
        n = next((x for x in news if x.ref == o.ref and x.location == o.location), None)
        if n is None: raise FifoError(f"entry {o.id}: upgrade finalize without the new id")
        news.remove(n); parts = _take(st, o.group, o.asset, o.location, -o.qty, o.id)
        old_cost = Decimal(0); old_label = None
        for l, q in parts:
            c = l.take_basis(q); l.qty -= q; old_cost = _add(old_cost, c); old_label = worst(old_label, l.label)
            st.disposals.append(Disposal(id=st.next_disp, lot=l.id, entry=o.id, block=o.block, qty=q, kind="upgrade_close", proceeds=c,
                                         proceeds_source=None if c is None else "upgrade_carry", proceeds_label=l.label, cost=c, lot_status=l.status))
            st.next_disp += 1
        if o.ref in st.buckets:   # cost legs seen (this tx or an earlier UpgradeQueued / reduceUpgradeTime tx)
            bv, bl = st.buckets.pop(o.ref)
            opened.append(_open(st, n, n.qty, _add(old_cost, bv), "upgrade_carry", worst(old_label, bl), "upgrade"))
        else:                     # no cost seen for this upgrade: unknown, never 0
            opened.append(_open(st, n, n.qty, None, None, None, "upgrade", status="pending", pending_reason="upgrade_cost_unmatched"))
    if news: raise FifoError(f"entry {news[0].id}: upgrade new id without the old id")
    return opened

def _destroy(st: State, legs: List[Entry]):
    """§9 rule 5, refund type 0: the installation lot is disposed with proceeds = USDC value of the alchemica refund at that block,
    and the refunded alchemica is acquired at that same value."""
    items = [x for x in legs if x.qty < 0]; refunds = [x for x in legs if x.qty > 0]
    total = Decimal(0); label = None
    for r in refunds: total = _add(total, r.value()); label = worst(label, r.label)
    for it, share in zip(items, _split(total, [-x.qty for x in items])):
        _dispose(st, it, "destroy", share, "refund_value", label)
    for r in refunds: _open(st, r, r.qty, r.value(), r.price_source, r.label, "refund")

def _bundle(st: State, e: Entry, proceeds: Optional[Decimal], source, label) -> List[Disposal]:
    """§9 rule 6: a parcel sold with items equipped is one bundle. Parcel row: proceeds = sale price, cost = parcel basis + the
    equipped items' bases (realized PnL reported here). Item rows (bundle_item) close the items' lots at proceeds = cost (0 PnL)."""
    tag = next(r for r in _refs(e.ref) if r.startswith("bundle:parcel:")); loc = "parcel:" + tag.split(":")[2]
    items = sorted((l for l in st.lots if l.group == e.group and l.location == loc and l.qty > 0), key=lambda l: (l.order, l.id))
    ds = _dispose(st, e, "bundle", proceeds, source, label, bundle_ref=tag)
    extra = Decimal(0)
    for l in items:
        c = l.take_basis(l.qty); extra = _add(extra, c)
        st.disposals.append(Disposal(id=st.next_disp, lot=l.id, entry=e.id, block=e.block, qty=l.qty, kind="bundle_item", proceeds=c,
                                     proceeds_source=None if c is None else "bundle", proceeds_label=l.label, cost=c, bundle_ref=tag, lot_status=l.status))
        st.next_disp += 1; l.qty = Decimal(0)
    ds[-1].own_cost = ds[-1].cost; ds[-1].cost = _add(ds[-1].cost, extra)
    if extra is None: ds[-1].lot_status = "pending"
    return ds

def _generic(st: State, p: Policy, legs: List[Entry]):
    opened: List[Lot] = []; sales: List[Disposal] = []
    groups: Dict[str, List[Entry]] = {}
    for e in legs: groups.setdefault(e.trade_group or e.tx, []).append(e)
    for g in sorted(groups):
        G = groups[g]; outs = [e for e in G if e.qty < 0]; ins = [e for e in G if e.qty > 0]
        def counter(es):   # trade-implied value of the other side, only when every leg of it is priced
            vs = [x.value() for x in es]; return None if not es or any(v is None for v in vs) else sum(vs)
        nft_in = [e for e in ins if e.nft and e.category in TRADE]
        for e in outs:
            v, src, lab = e.value(), e.price_source, e.label
            if v is None and e.category in TRADE and len([x for x in outs if x.value() is None]) == 1:
                v, src, lab = counter(ins), "trade", worst(*[x.label for x in ins])
            if e.category in TRADE and any(r.startswith("bundle:parcel:") for r in _refs(e.ref)):
                sales += _bundle(st, e, v, src, lab); continue
            if e.category in TRADE: ds = _dispose(st, e, "sale", v, src, lab)
            elif e.category == "spend": ds = _dispose(st, e, "spend", v, src, lab, expense=v)
            elif e.category == "withdrawal":
                pol = p.need("withdrawal", f"entry {e.id}: {e.asset} withdrawn to an outside address")
                ds = _dispose(st, e, "withdrawal" if pol == "dispose_fmv" else "custody_exit", v if pol == "dispose_fmv" else None,
                              src if pol == "dispose_fmv" else None, lab if pol == "dispose_fmv" else None)
            else: raise FifoError(f"entry {e.id}: outflow category {e.category!r} not handled")
            if e.category in TRADE and not e.nft and len(nft_in) == 1:
                for d in ds: d.payment_for = nft_in[0].id      # §8: the NFT acquisition this payment (escrow fill or direct) paid for
            sales += ds
        for e in ins:
            v, src, lab = e.value(), e.price_source, e.label
            if e.category in TRADE:
                if v is None and len([x for x in ins if x.value() is None]) == 1:
                    v, src, lab = counter(outs), "trade", worst(*[x.label for x in outs])
                opened.append(_open(st, e, e.qty, v, src, lab, "buy"))
            elif e.category == "income":
                st.income.append((e.id, e.asset, v)); opened.append(_open(st, e, e.qty, v, src, lab, "income"))   # §3: lot at FMV
            elif e.category == "deposit":
                if p.need("deposit", f"entry {e.id}: {e.asset} deposited from an outside address") == "acquire_fmv":
                    opened.append(_open(st, e, e.qty, v, src, lab, "deposit"))
                else: opened.append(_open(st, e, e.qty, None, None, None, "deposit", status="pending", pending_reason="deposit"))
            elif e.category == "bridge_in": opened.append(_open(st, e, e.qty, v, src, lab, "bridge_in"))
            elif e.category == "gift_in": opened.append(_open(st, e, e.qty, Decimal(0), "gift", LOW, "gift"))   # §9 r1: basis 0, flagged
            elif e.category == "migration_in":   # §8: custody, never income; carried basis, else manual (low), else pending
                if e.carry_basis is not None:
                    opened.append(_open(st, e, e.qty, e.carry_basis, e.carry_source, e.carry_label, "migration", chain_origin=e.chain_origin))
                elif e.manual_basis is not None:
                    opened.append(_open(st, e, e.qty, e.manual_basis, "manual", LOW, "migration", status="manual",
                                        chain_origin=e.chain_origin, manual_basis_id=e.manual_basis_id))
                else: opened.append(_open(st, e, e.qty, None, None, None, "migration", status="pending", pending_reason="migration",
                                          chain_origin=e.chain_origin))
            else: raise FifoError(f"entry {e.id}: inflow category {e.category!r} not handled")
    return opened, sales

def _fees(st: State, p: Policy, fees: List[Entry], opened: List[Lot], sales: List[Disposal]):
    """Q-A. expense: the gas ETH is a disposal at market value plus an expense of that value. capitalize: the gas ETH is still
    disposed at market value; its value is added to the basis of the lots the tx acquired (pro rata to their basis, equal when all 0),
    else deducted from the tx's sale proceeds (pro rata), else fee_without_trade."""
    for f in fees:
        v = f.value(); pol = p.need("fee", f"entry {f.id}: gas")
        if pol == "expense": _dispose(st, f, "fee", v, f.price_source, f.label, expense=v); continue
        tgt = [l for l in opened if l.kind in ("buy", "craft", "craft_claim", "upgrade") and l.status != "pending"]
        sal = [d for d in sales if d.kind in ("sale", "bundle") and d.proceeds is not None]
        if not tgt and not sal:
            p.need("fee_without_trade", f"entry {f.id}: capitalized gas in a tx with no trade leg")
            _dispose(st, f, "fee", v, f.price_source, f.label, expense=v); continue
        _dispose(st, f, "fee_capitalized", v, f.price_source, f.label)
        if tgt:
            for l, s in zip(tgt, _split(v, [l.basis for l in tgt])):
                if s is None: l.basis, l.source, l.label, l.status, l.pending_reason = None, None, None, "pending", "fee_unpriced"
                else: l.basis += s
        else:
            for d, s in zip(sal, _split(v, [d.proceeds for d in sal])):
                d.proceeds = None if s is None else d.proceeds - s

def _tx(st: State, p: Policy, legs: List[Entry]):
    live = []
    for e in legs:
        if e.excluded or e.category in EXCLUDED_FLAGS or e.flag in EXCLUDED_FLAGS:
            st.excluded[e.category] = st.excluded.get(e.category, 0) + 1; continue   # §8: spam / untracked never in PnL
        live.append(e)
    rest = _custody(st, p, live)
    by = lambda *c: [e for e in rest if e.category in c]
    opened: List[Lot] = []
    if by("craft", "craft_pending"): opened += _craft(st, p, by("craft", "craft_pending"))
    if by("upgrade"): opened += _upgrade(st, by("upgrade"))
    if by("destroy_refund"): _destroy(st, by("destroy_refund"))
    o, sales = _generic(st, p, [e for e in rest if e.category not in ("craft", "craft_pending", "upgrade", "destroy_refund", "fee")])
    _fees(st, p, by("fee"), opened + o, sales)

def run(entries: List[Entry], policy: Policy, state: Optional[State] = None) -> State:
    """Deterministic FIFO replay. With `state`, continues from it (recompute from block X): every entry must sort after state.last_key."""
    st = copy.deepcopy(state) if state is not None else State()
    es = sorted(entries, key=Entry.key)
    if es and st.last_key is not None and es[0].key() <= tuple(st.last_key):
        raise FifoError("entries must sort after the state's last entry (recompute from block X)")
    i = 0
    while i < len(es):
        j = i
        while j < len(es) and es[j].key()[:3] == es[i].key()[:3]: j += 1
        _tx(st, policy, es[i:j]); i = j
    if es: st.last_key = es[-1].key()
    return st

# ---------- reporting ----------
def _s(x): return format(x.normalize(), "f") if isinstance(x, Decimal) else x

def report(st: State, policy: Policy, as_of_block: int) -> dict:
    """Totals per §8: pending basis is excluded on both mark and basis (and from realized). Two variants: all confidence levels, and
    excluding low-confidence prices (§9 P3 thin pools). Unpriced disposals and unmarked lots are counted, never valued at 0."""
    out = {}
    for variant, keep_low in (("all", True), ("excl_low", False)):
        R = U = MV = OB = Decimal(0); n = {"unmarked_lots": 0, "unmarked_nft_lots": 0, "unpriced_disposals": 0, "low_excluded": 0}
        by: Dict[str, dict] = {}
        for d in st.disposals:
            if d.lot_status == "pending" or d.kind == "custody_exit": continue
            if d.realized is None: n["unpriced_disposals"] += 1; continue
            if not keep_low and LOW in (d.proceeds_label, st.lot(d.lot).label): n["low_excluded"] += 1; continue
            R += d.realized; a = by.setdefault(st.lot(d.lot).asset, {"realized": Decimal(0), "unrealized": Decimal(0)}); a["realized"] += d.realized
        for l in st.lots:
            if l.qty <= 0 or l.status == "pending": continue
            if l.nft:
                nm = policy.need("nft_mark", f"open NFT lot {l.id} ({l.asset})")
                m = None if nm == "exclude" else Mark(l.remaining_basis() / l.qty, "at_basis", l.label) if nm == "at_basis" else nm(l.asset, as_of_block, l)
                if m is None: n["unmarked_nft_lots"] += 1; continue
            else:
                m = policy.need("mark", f"open lot {l.id} ({l.asset}) needs a mark at block {as_of_block}")(l.asset, as_of_block)
                if m is None: n["unmarked_lots"] += 1; continue
            if m.price is None or (m.price <= 0 and m.source != "at_basis"): raise FifoError(f"mark for {l.asset}: non-positive price {m.price}")
            if not keep_low and LOW in (m.label, l.label): n["low_excluded"] += 1; continue
            mv = l.qty * m.price; rb = l.remaining_basis(); MV += mv; OB += rb; U += mv - rb
            a = by.setdefault(l.asset, {"realized": Decimal(0), "unrealized": Decimal(0)}); a["unrealized"] += mv - rb
        out[variant] = {"realized_usdc": _s(R), "unrealized_usdc": _s(U), "market_value_usdc": _s(MV), "open_basis_usdc": _s(OB), **n,
                        "by_asset": {k: {kk: _s(vv) for kk, vv in v.items()} for k, v in sorted(by.items())}}
    return _report_tail(st, out, as_of_block)

def _report_tail(st: State, out: dict, as_of_block: int) -> dict:
    hold: Dict[str, Decimal] = {}
    for l in st.lots:
        if l.qty > 0: k = f"{l.asset}@{l.location}"; hold[k] = hold.get(k, Decimal(0)) + l.qty
    roots = [l for l in st.lots if l.status == "pending" and l.parent is None]
    out.update({
        "as_of_block": as_of_block,
        "pending_lots_open": sum(1 for l in st.lots if l.status == "pending" and l.qty > 0),
        "pending_lots_total": len(roots),
        "pending_disposals": sum(1 for d in st.disposals if d.lot_status == "pending"),
        "pending_reasons": {r: sum(1 for l in roots if l.pending_reason == r) for r in sorted({l.pending_reason for l in roots})},
        "expenses_usdc": _s(sum((d.expense for d in st.disposals if d.expense is not None), Decimal(0))),
        "income_usdc": _s(sum((v for _, _, v in st.income if v is not None), Decimal(0))),
        "income_unpriced": sum(1 for _, _, v in st.income if v is None),
        "custody_exit_basis_usdc": _s(sum((d.cost for d in st.disposals if d.kind == "custody_exit" and d.cost is not None), Decimal(0))),
        "excluded_rows": dict(sorted(st.excluded.items())),
        "holdings_by_location": {k: _s(v) for k, v in sorted(hold.items())},
        "open_cost_buckets": {k: [_s(v[0]), v[1]] for k, v in sorted(st.buckets.items())}})
    return out

def identity(st: State) -> dict:
    """Engine consistency check (holds by construction when nothing is lost): the basis opened at root lots (incl. capitalized fees)
    = the cost of every disposal (bundle parcel rows count only the parcel's own cost; the items are their bundle_item rows)
    + the basis still open. Moves into child lots neither add nor lose basis. Rows with unknown (pending) basis are outside it.
    The P4 pass identity against external flows ("net USDC flows plus market value") is design question Q-C, NOT computed here."""
    D0 = Decimal(0)
    root = sum((l.basis for l in st.lots if l.parent is None and l.basis is not None), D0)
    cost = sum(((d.own_cost if d.kind == "bundle" else d.cost) for d in st.disposals
                if (d.own_cost if d.kind == "bundle" else d.cost) is not None), D0)
    open_b = sum((l.remaining_basis() for l in st.lots if l.basis is not None and l.qty > 0), D0)
    return {"basis_opened_root": _s(root), "cost_disposed": _s(cost), "basis_open": _s(open_b), "residual": _s(root - cost - open_b)}

LOT_COLS = ("id", "group", "asset", "wallet", "location", "open_entry", "open_block", "qty_open", "qty", "basis", "basis_out", "source",
            "label", "status", "kind", "ref", "parent", "chain_origin", "pending_reason", "manual_basis_id")
DISP_COLS = ("id", "lot", "entry", "block", "qty", "kind", "proceeds", "proceeds_source", "proceeds_label", "cost", "payment_for",
             "bundle_ref", "expense", "lot_status", "own_cost")
def canonical(st: State) -> str:
    rows = {"lots": [[_s(getattr(l, c)) for c in LOT_COLS] for l in sorted(st.lots, key=lambda l: l.id)],
            "disposals": [[_s(getattr(d, c)) for c in DISP_COLS] for d in sorted(st.disposals, key=lambda d: d.id)],
            "buckets": {k: [_s(v[0]), v[1]] for k, v in sorted(st.buckets.items())}}
    return json.dumps(rows, separators=(",", ":"), sort_keys=True)
def md5(st: State) -> str:
    """md5 of the lots and disposals (fixed column lists): equal for a full rebuild and an incremental recompute."""
    return hashlib.md5(canonical(st).encode()).hexdigest()
