"""P2.2 Gotchiverse classification rules (DESIGN v1.3 §9 rules 1-10). Called by classify.plan() before the escrow rules.
Each rule returns (category, out_legs, ref_updates) or None, or raises Review when a Gotchiverse flow is recognised but does not fit.
Events come from raw_event kinds market_* (bulk marketplace logs) and gv_* (ingest_gv); legs are the wallet's token moves.
No prices here (P3); no basis carry, bundle PnL or location holdings maths (P4): only categories, locations and refs."""
from .config import GV, GV_SEL

def _ev(market, name, contract=None):
    return [m for m in market if m.get("event") == name and (contract is None or m.get("contract") == contract)]
def _ti(m, i): return int(m["topics"][i], 16)
def _ta(m, i): return "0x" + m["topics"][i][-40:].lower()
def _w(m):
    d = (m.get("data") or "0x")[2:]
    return [int(d[i:i + 64], 16) for i in range(0, len(d), 64)]
def nft_key(l): return f"{l['contract']}#{l['token_id']}"
ZERO = "0x" + "0" * 40
def _li(m): return m.get("li", 0)

def gv_rule(chain, w, tx, legs, market, esc, L, Review):
    g = GV.get(chain)
    if not g: return None
    sent = bool(tx) and tx["from"] == w; to = (tx or {}).get("to"); sel = (tx or {}).get("selector")
    fung = [l for l in legs if l["std"] == "erc20"]; nfts = [l for l in legs if l["std"] in ("erc721", "erc1155")]
    items = (g["installation"], g["tile"]); cost_to = {g["realm"], g["pixelcraft"], g["dao"], g["burn"]}
    for r in (r10_pool, r1_gift, r1_buyorder_add, r2_gbm_seller, r2_buy_now, r9_bounce, r3_craft, r4_upgrade, r5_parcel, r8_lending, r_pocket, r7_income):
        out = r(g, w, tx, sent, to, sel, legs, fung, nfts, market, esc, items, cost_to, L, Review)
        if out: return out
    return None

# R10 (PR #5 review): 0xeae2fb93… is the Aerodrome FUD/GHST POOL (its own LP token), not a router. A plain add-liquidity (inputs -> pool,
# LP minted from 0x0 to the wallet) disposes the inputs at the block price (category swap, priced in P3) and the LP token is untracked.
# Anything else touching the pool (swaps through it, LP burns/transfers) -> review.
def r10_pool(g, w, tx, sent, to, sel, legs, fung, nfts, market, esc, items, cost_to, L, Review):
    pool = g.get("aero_fud_ghst_pool")
    if not pool or not any(l.get("cp") == pool or l["contract"] == pool for l in legs): return None
    lp = [l for l in legs if l["contract"] == pool and l["qty"] > 0 and l.get("cp") == ZERO]
    ins = [l for l in fung if l["contract"] != pool and l["qty"] < 0 and l.get("cp") == pool]
    if sent and len(lp) == 1 and ins and len(lp) + len(ins) == len(legs):
        ref = f"lp_add:{pool}"
        return "swap", [L(l, "swap", ref=ref) for l in ins] + [L(lp[0], "untracked", ref=ref)], []
    raise Review(f"Aerodrome FUD/GHST pool {pool}: not a plain add-liquidity (DESIGN §9 R10: pool, not a router)")

# R1: NFT received as listing recipient (ExecutedToRecipient, recipient = wallet, buyer != wallet) with no wallet payment -> gift_in
def r1_gift(g, w, tx, sent, to, sel, legs, fung, nfts, market, esc, items, cost_to, L, Review):
    rc = [m for m in market if m.get("event", "").endswith("ExecutedToRecipient") and len(m["topics"]) > 3 and _ta(m, 3) == w]
    if not rc: return None
    if any(_ta(m, 2) == w for m in rc) or any(l["qty"] < 0 for l in legs if l["std"] != "native"):
        return None                                   # the wallet bought it for itself / paid: normal buy rules
    if not nfts or any(l["qty"] < 0 for l in nfts) or fung: raise Review("ExecutedToRecipient with unexpected wallet legs")
    ref = f"gift:listing:{_ti(rc[0], 1)}:basis0"
    return "gift_in", [L(l, "gift_in", ref=ref) for l in nfts], []

# R1: buy-order placement that carries its BuyOrderAdd event: stamp the order id at placement (closes KNOWN_GAPS #1 for these)
def r1_buyorder_add(g, w, tx, sent, to, sel, legs, fung, nfts, market, esc, items, cost_to, L, Review):
    adds = [m for m in _ev(market, "ERC721BuyOrderAdded", g["aavegotchi"]) + _ev(market, "ERC1155BuyOrderAdd", g["aavegotchi"]) if _ta(m, 2) == w]
    if not (sent and adds and to == g["aavegotchi"]): return None
    out_ = [l for l in fung if l["cp"] == g["aavegotchi"] and l["qty"] < 0]
    if len(adds) != 1 or len(out_) != 1 or len(out_) != len(legs): raise Review("buy-order placement: not exactly one BuyOrderAdd and one payment")
    l = out_[0]; ref = f"baazaar:buyorder:{_ti(adds[0], 1)}"
    esc.put(g["aavegotchi"], l["contract"], ref, -l["qty"])
    return "escrow_out", [L(l, "escrow_out", ref=ref), L(l, "escrow_out", loc=f"escrow:{g['aavegotchi']}", qty=-l["qty"], ref=ref)], []

# R2: GBM seller side. Create: NFT wallet -> GBM with Auction_Initialized -> escrow_out (escrow:gbm). Cancel: AuctionCancelled -> escrow_return.
# Claim: Auction_ItemClaimed of an auction whose NFT the wallet escrowed -> NFT disposed from escrow (auction) vs the GHST proceeds.
def r2_gbm_seller(g, w, tx, sent, to, sel, legs, fung, nfts, market, esc, items, cost_to, L, Review):
    gbm = g["gbm"]; loc = f"escrow:{gbm}"
    n_out = [l for l in nfts if l["cp"] == gbm and l["qty"] < 0]
    if n_out:
        inits = _ev(market, "Auction_Initialized", gbm)
        if not sent or len(legs) != len(n_out): raise Review("NFT into GBM with other wallet legs")
        out = []
        for l in n_out:
            m = [x for x in inits if _ti(x, 2) == int(l["token_id"]) and ("0x" + format(_w(x)[0], "040x")) == l["contract"]] if inits else []
            if len(m) != 1: raise Review("NFT into GBM without exactly one matching Auction_Initialized")
            ref = f"gbm:auction:{_ti(m[0], 1)}"; esc.put(gbm, nft_key(l), ref, -l["qty"]); esc.std[nft_key(l)] = l["std"]
            out += [L(l, "escrow_out", ref=ref), L(l, "escrow_out", loc=loc, qty=-l["qty"], ref=ref)]
        return "escrow_out", out, []
    cancels = _ev(market, "AuctionCancelled", gbm)
    n_in = [l for l in nfts if l["cp"] == gbm and l["qty"] > 0]
    if cancels and n_in:
        out = []
        for l in n_in:
            refs = [f"gbm:auction:{_ti(c, 1)}" for c in cancels if esc.avail(gbm, nft_key(l), f"gbm:auction:{_ti(c, 1)}")]
            if len(refs) != 1 or len(legs) != len(n_in): raise Review("GBM cancel without a unique escrowed NFT")
            esc.take(gbm, nft_key(l), l["qty"], refs[0])
            out += [L(l, "escrow_return", ref=refs[0]), L(l, "escrow_return", loc=loc, qty=-l["qty"], ref=refs[0])]
        return "escrow_return", out, []
    # proceeds arrive on Auction_ItemClaimed, or in the buyer's tx on Auction_BoughtNow (real: 0x271109cf…85fd pays the seller from GBM)
    ends = _ev(market, "Auction_ItemClaimed", gbm) + _ev(market, "Auction_BoughtNow", gbm)
    claims = sorted({_ti(m, 1) for m in ends})   # a real buy-now emits BOTH BoughtNow and ItemClaimed (0x271109cf…, auction 5637): one auction
    mine = [(a, k) for a in claims for (d, k) in list(esc.open) if d == gbm and "#" in k and esc.avail(gbm, k, f"gbm:auction:{a}")]
    if mine:
        g_in = [l for l in fung if l["cp"] == gbm and l["qty"] > 0]
        if len(mine) != 1 or len(g_in) != 1 or len(g_in) != len(legs): raise Review("GBM seller claim: proceeds/escrow do not match one auction")
        a, k = mine[0]; ref = f"gbm:auction:{a}"; q = sum(e["qty"] for e in esc.avail(gbm, k, ref)); esc.take(gbm, k, q, ref)
        c, tid = k.split("#"); li = min(_li(m) for m in ends if _ti(m, 1) == a)
        nft_leg = dict(li=li, std=esc.std.get(k, "erc721"), contract=c, token_id=tid, qty=-q, cat="auction", loc=loc, ref=ref, spam=False)
        return "auction", [nft_leg, L(g_in[0], "auction", ref=ref)], []
    return None

# R2: buy-now (Auction_BoughtNow, buyer = wallet; 19 such events on Base, e.g. 0x271109cf…85fd) -> nft_buy paid in GHST
def r2_buy_now(g, w, tx, sent, to, sel, legs, fung, nfts, market, esc, items, cost_to, L, Review):
    bn = [m for m in _ev(market, "Auction_BoughtNow", g["gbm"]) if _ta(m, 2) == w]
    if not bn: return None
    pay = [l for l in fung if l["cp"] == g["gbm"] and l["qty"] < 0]; got = [l for l in nfts if l["qty"] > 0]
    if len(bn) != 1 or not pay or not got or len(pay) + len(got) != len(legs): raise Review("GBM buy-now with unexpected legs")
    ref = f"gbm:auction:{_ti(bn[0], 1)}"
    return "nft_buy", [L(l, "nft_buy", ref=ref) for l in legs], []

# R9: bounce gate: GLTR/alchemica to 0xFFfF in a tx with REALM EventStarted -> spend
def r9_bounce(g, w, tx, sent, to, sel, legs, fung, nfts, market, esc, items, cost_to, L, Review):
    ev = _ev(market, "EventStarted", g["realm"]) or _ev(market, "EventPriorityAndDurationUpdated", g["realm"])   # create or priority/duration update
    if not (sent and ev): return None
    if not fung or any(l["cp"] != g["burn"] or l["qty"] > 0 or not (l["contract"] == g["gltr"] or l["contract"] in g["alchemica"]) for l in legs):
        raise Review("bounce gate (EventStarted) with legs other than GLTR/alchemica to 0xFFfF")
    ref = f"bounce:event:{_ti(ev[0], 1)}" + (":update" if ev[0]["event"] != "EventStarted" else "")
    return "spend", [L(l, "spend", ref=ref) for l in legs], []

def _qty_check(market, g, w, mints, Review):
    """§9 R3 correction: TransferSingle == MintInstallations/MintTiles on Base (re-mint 0x14f28eea), so no override. Per contract and id,
    the wallet's minted amounts must equal the events' amounts for that owner and id (multiset match, not a sum); a mismatch -> review."""
    ev = {g["installation"]: "MintInstallations", g["tile"]: "MintTiles"}
    for c in {l["contract"] for l in mints}:
        ms = [m for m in _ev(market, ev[c], c) if len(m["topics"]) > 2 and _ta(m, 1) == w]
        for tid in {int(l["token_id"]) for l in mints if l["contract"] == c}:
            exp = sorted(_w(m)[0] for m in ms if _ti(m, 2) == tid)
            got = sorted(l["qty"] for l in mints if l["contract"] == c and int(l["token_id"]) == tid)
            if exp and exp != got: raise Review(f"craft quantity mismatch: transfers {got} vs {ev[c]} {exp} for id {tid}")

def _q(c, q): return f"craft:queue:{c}:{q}"   # queue ids are per diamond: Installation q7 != Tile q7

def _claim_refs(market, g, w, mints, claimed, Review):
    """Per minted leg: the queue id from MintInstallation / MintTile data (owner = wallet, type = token id) among that contract's QueueClaimed ids;
    with one claimed id on the contract and no event, that id. Otherwise review."""
    ev = {g["installation"]: "MintInstallation", g["tile"]: "MintTile"}; refs = {}
    for c in {l["contract"] for l in mints}:
        cq = sorted(q for cc, q in claimed if cc == c)
        if not cq: raise Review("queue claim: minted items without a QueueClaimed on that diamond")
        ms = sorted([m for m in _ev(market, ev[c], c) if len(m["topics"]) > 2 and _ta(m, 1) == w and _w(m) and _w(m)[0] in cq], key=_li)
        for l in sorted([l for l in mints if l["contract"] == c], key=lambda l: l["li"]):
            cand = [m for m in ms if _ti(m, 2) == int(l["token_id"])]
            if cand: ms.remove(cand[0]); refs[id(l)] = _q(c, _w(cand[0])[0])
            elif len(cq) == 1: refs[id(l)] = _q(c, cq[0])
            else: raise Review("queue claim: cannot match a minted item to one queue id")
    return refs

# R3: craft (instant / free / batch / queued + claim / reduceCraftTime). Inputs (to REALM, Pixelcraft, DAO, 0xFFfF; GLTR burnFrom -> 0x0) are cost.
def r3_craft(g, w, tx, sent, to, sel, legs, fung, nfts, market, esc, items, cost_to, L, Review):
    claimed = {(c, _ti(m, 1)) for c in items for m in _ev(market, "QueueClaimed", c)}
    reduced = sorted({(c, _ti(m, 1)) for c in items for m in _ev(market, "CraftTimeReduced", c)})
    queued = sorted({(c, _ti(m, 1)) for c in items for m in _ev(market, "AddedToQueue", c)})
    mine = sent and to in items
    is_craft, is_claim, is_reduce = (mine and sel in GV_SEL[k] for k in ("craft", "craft_claim", "craft_reduce"))
    if not (is_craft or is_claim or is_reduce or claimed or (mine and reduced)): return None
    mints = [l for l in nfts if l["contract"] in items and l["cp"] == ZERO and l["qty"] > 0]
    inputs = [l for l in fung if l["qty"] < 0]
    cost = lambda l: l["cp"] in cost_to or (l["cp"] == ZERO and l["contract"] == g["gltr"])   # reduceCraftTime: GLTR burnFrom -> 0x0
    if any(not cost(l) for l in inputs) or len(mints) + len(inputs) != len(legs):
        raise Review("craft tx with legs outside the 35/30/30/5 cost split or the minted items")
    _qty_check(market, g, w, mints, Review)
    if claimed or is_claim:                        # claim of queued crafts: each NFT gets its own queue's pending cost (P4)
        if not claimed: raise Review("craft claim selector without QueueClaimed")
        if inputs or not mints: raise Review("QueueClaimed without minted items / with payment legs")
        refs = _claim_refs(market, g, w, mints, claimed, Review)
        return "craft", [L(l, "craft", ref=refs[id(l)]) for l in mints], []
    if (is_reduce or reduced) and not is_craft:    # GLTR to speed up queued crafts: added to those queues' pending cost
        if mints or not inputs or not reduced: raise Review("reduceCraftTime with unexpected legs / without CraftTimeReduced")
        ref = ";".join(_q(c, q) for c, q in reduced)
        return "craft_pending", [L(l, "craft_pending", ref=ref) for l in inputs], []
    if mints and queued:                           # #27 split rule (queue entries carry their item type: AddedToQueue topic2)
        qi = sorted({(c, _ti(m, 1), _ti(m, 2)) for c in items for m in _ev(market, "AddedToQueue", c)})
        return _split_mixed(g, mints, qi, inputs, esc, L, Review)
    if mints:                                      # instant craft (paid or free: no inputs = basis 0, never income)
        ref = "craft:instant" + ("" if inputs else ":free")
        return "craft", [L(l, "craft", ref=ref) for l in inputs + mints], []
    if queued:                                     # one ref per queue (contract-scoped); several queues share the inputs (P4 splits)
        ref = ";".join(_q(c, q) for c, q in queued)
        return "craft_pending", [L(l, "craft_pending", ref=ref) for l in inputs], []
    raise Review("craft tx with neither minted items nor AddedToQueue")

# KNOWN_GAPS #27 (architect, 2026-10-17): one craft tx that both mints instantly and queues. Inputs are allocated per item from each type's
# on-chain alchemicaCost at that block (craft_type_cost cache, eth_call at ingest): instant items get their types' cost, the queued items'
# pending bucket gets the rest. Summed type costs must equal the observed inputs per token (within 1 wei), else review. Free types cost 0.
# GLTR in such a tx (per-item speed-up) is not allocated -> review; GLTR from reduceCraftTime stays with its queue (r3_craft above).
def _split_mixed(g, mints, queued, inputs, esc, L, Review):
    order = g["alchemica_order"]
    def cost(c, t):
        v = esc.type_cost.get((c, int(t), esc.bn))
        if v is None: raise Review(f"mixed instant+queued craft: type cost of {c} #{t} not cached at block {esc.bn}")
        return v
    if any(l["contract"] not in order for l in inputs): raise Review("mixed instant+queued craft with non-alchemica inputs (GLTR/GHST): not allocated")
    inst = [0] * 4; que = [0] * 4
    for l in mints:
        for i, x in enumerate(cost(l["contract"], l["token_id"])): inst[i] += x * int(l["qty"])
    for c, _, it in queued:                        # one AddedToQueue = one queued item
        for i, x in enumerate(cost(c, it)): que[i] += x
    obs = [-sum(int(l["qty"]) for l in inputs if l["contract"] == a) for a in order]
    for i, a in enumerate(order):
        if abs(obs[i] - (inst[i] + que[i])) > 1:
            raise Review(f"mixed instant+queued craft: type costs {inst[i] + que[i]} != observed inputs {obs[i]} for {a}")
    qref = ";".join(_q(c, q) for c, q, _ in queued)
    iref = "craft:instant" + ("" if any(inst) else ":free")
    out = []
    for l in inputs:
        i = order.index(l["contract"]); tot = inst[i] + que[i]
        a = -((-int(l["qty"])) * inst[i] // tot) if tot else 0; rest = int(l["qty"]) - a
        if a: out.append(L(l, "craft", ref=iref, qty=a))
        if rest: out.append(L(l, "craft_pending", ref=qref, qty=rest))
    return "craft", out + [L(l, "craft", ref=iref) for l in mints], []

# R4: upgrade. Cost tx (UpgradeQueued owner = wallet / UpgradeInitiated) and reduceUpgradeTime -> upgrade cost legs.
# Finalize (REALM InstallationUpgraded prev -> next): old id leaves parcel:<realm>, new id lands there (no realized PnL; P4).
def r4_upgrade(g, w, tx, sent, to, sel, legs, fung, nfts, market, esc, items, cost_to, L, Review):
    q = [m for m in _ev(market, "UpgradeQueued", g["installation"]) if _ta(m, 1) == w]
    qf = {_ti(m, 2): _ti(m, 3) for m in _ev(market, "UpgradeQueueFinalized", g["installation"]) if len(m["topics"]) > 3 and _ta(m, 1) == w}
    init = _ev(market, "UpgradeInitiated", g["installation"]); red = _ev(market, "UpgradeTimeReduced", g["installation"])
    up = _ev(market, "InstallationUpgraded", g["realm"])
    if not (q or init or red or up or qf): return None
    uref = lambda r, i: f"upgrade:realm:{r}" + ("" if i is None else f":queue:{i}")
    out = []; inputs = [l for l in fung if l["qty"] < 0]
    if any(l["cp"] not in cost_to for l in inputs): raise Review("upgrade cost legs outside REALM/Pixelcraft/DAO/0xFFfF")
    # queue index: UpgradeQueued topic3, UpgradeTimeReduced topic1, UpgradeQueueFinalized topic3 (finalize)
    realm, idx = ((_ti(q[0], 2), _ti(q[0], 3)) if q else (_ti(red[0], 2), _ti(red[0], 1)) if red else (_ti(init[0], 1), None) if init
                  else (_w(up[0])[0], None) if up else (next(iter(qf)), None))
    ref = uref(realm, idx)
    out += [L(l, "upgrade", ref=ref) for l in inputs]
    rest = [l for l in legs if l not in inputs]
    for m in up:
        r_id, prev, nxt = _w(m)[0], _w(m)[1], _w(m)[2]; loc = f"parcel:{r_id}"; fref = uref(r_id, qf.get(r_id))
        mine = [l for l in rest if l["contract"] == g["installation"] and int(l["token_id"]) == nxt]
        if sum(l["qty"] for l in mine) != 0: raise Review("upgrade finalize: new id not re-equipped in the same tx")
        out += [L(l, "upgrade", ref=fref) for l in mine]; rest = [l for l in rest if l not in mine]
        base = dict(li=m["li"], std="erc1155", contract=g["installation"], spam=False, cat="upgrade", ref=fref, loc=loc)
        out += [dict(base, token_id=str(prev), qty=-1), dict(base, token_id=str(nxt), qty=1)]
    if rest: raise Review("upgrade tx with unexplained legs")
    if not out: raise Review("upgrade event without wallet legs")
    return "upgrade", out, []

# R5: equip/unequip on parcels (Installation/Tile TransferToParent/FromParent, topic1 = REALM, topic2 = parcel) -> custody parcel:<id>.
# An unequip that does not return the item (burned) but pays an alchemica refund -> destroy_refund.
def r5_parcel(g, w, tx, sent, to, sel, legs, fung, nfts, market, esc, items, cost_to, L, Review):
    tp = [m for c in items for m in _ev(market, "TransferToParent", c) if _ta(m, 1) == g["realm"]]
    fp = [m for c in items for m in _ev(market, "TransferFromParent", c) if _ta(m, 1) == g["realm"]]
    if not (tp or fp): return None
    out = []; used = []
    for m, sign in [(x, -1) for x in tp] + [(x, 1) for x in fp]:
        parcel, typ, val = _ti(m, 2), _ti(m, 3), (_w(m) or [1])[0]
        leg = [l for l in nfts if l["contract"] == m["contract"] and int(l["token_id"]) == typ and l["qty"] * sign > 0
               and l["cp"] == g["realm"] and l not in used]
        loc = f"parcel:{parcel}"; ref = f"parcel:{parcel}"
        if leg:
            l = leg[0]; used.append(l)
            out += [L(l, "transfer_internal", ref=ref), L(l, "transfer_internal", loc=loc, qty=-l["qty"], ref=ref)]
            _parcel_add(esc, parcel, -l["qty"])
        elif sign > 0:                                # unequipped but not returned: destroyed (refund type 0)
            refund = [l for l in fung if l["qty"] > 0 and l["contract"] in g["alchemica"]]
            if not refund: raise Review("unequip: item neither returned nor refunded")
            out.append(dict(li=m["li"], std="erc1155", contract=m["contract"], token_id=str(typ), qty=-val, cat="destroy_refund", loc=loc, ref=ref, spam=False))
            out += [L(l, "destroy_refund", ref=ref) for l in refund if l not in used]; used += refund
            _parcel_add(esc, parcel, -val)
        else: raise Review("TransferToParent without the matching wallet -> REALM item leg")
    if any(l not in used for l in legs): raise Review("equip/unequip tx with unexplained legs")
    cats = {o["cat"] for o in out}
    return ("destroy_refund" if "destroy_refund" in cats else "transfer_internal"), out, []

def _parcel_add(esc, parcel, d):
    v = esc.parcels.get(parcel, 0) + d
    if v > 0: esc.parcels[parcel] = v
    else: esc.parcels.pop(parcel, None)   # nothing left equipped: the parcel is no longer a bundle

def _lend(market, g, names, w):
    """(lender, borrower) of lending events in the tx; indexed (topics) or tuple (data words 1..3) versions."""
    out = []
    for m in market:
        e = m.get("event", "")
        if m.get("contract") != g["aavegotchi"] or e.rstrip("T") not in names: continue
        if e.endswith("T"):
            wd = _w(m); out.append(("0x" + format(wd[2], "040x"), "0x" + format(wd[3], "040x")))
        else: out.append((_ta(m, 2), _ta(m, 3) if len(m["topics"]) > 3 else None))
    return [x for x in out if w in x]

# R8: lending. Gotchi out/back with GotchiLendingExecuted/Ended (lender = wallet) -> custody lent:<borrower>; upfront GHST -> income.
# R7 (lending part): revenue (alchemica/GHST) received with GotchiLendingClaimed/Ended -> income, also when the borrower or an operator sends
# the claim: Base emits the tuple (non-indexed) events, so lender/borrower come from the decoded tuple, never from wallet topics.
def r8_lending(g, w, tx, sent, to, sel, legs, fung, nfts, market, esc, items, cost_to, L, Review):
    ex = _lend(market, g, ("GotchiLendingExecuted",), w); end = _lend(market, g, ("GotchiLendingEnded", "GotchiLendingClaimed"), w)
    if not (ex or end): return None
    out = []; gotchi = [l for l in nfts if l["contract"] == g["aavegotchi"] and l["std"] == "erc721"]
    sides = {lender == w for lender, _ in ex + end}
    if len(sides) != 1: raise Review("lending: wallet is lender and borrower in one tx")
    if sides == {False}: return _r8b_borrower(g, w, ex, end, legs, fung, gotchi, L, Review)
    for l in gotchi:
        borrower = (ex or end)[0][1]; loc = f"lent:{borrower}"
        if l["cp"] != borrower: raise Review("lending: gotchi moved to/from an address other than the borrower")
        out += [L(l, "transfer_internal", ref=loc), L(l, "transfer_internal", loc=loc, qty=-l["qty"], ref=loc)]
    for l in fung:
        if l["qty"] <= 0: raise Review("lending tx with an outgoing token leg")
        out.append(L(l, "income", ref="lending:" + ("upfront" if ex else "revenue")))
    if len(out) != len(gotchi) * 2 + len(fung) or len(gotchi) + len(fung) != len(legs): raise Review("lending tx with unexplained legs")
    return ("income" if fung else "transfer_internal"), out, []

# R8b (architect, accepted 2026-10-17, KNOWN_GAPS #19; to be added to DESIGN §9 as rule 8b): wallet is the BORROWER.
# The borrowed gotchi is not owned: its legs (to/from the lender) are `untracked` (pnl_excluded, no lot), ref borrowed:<lender>.
# Upfront GHST paid (with GotchiLendingExecuted) -> `spend`. Revenue share received (Claimed/Ended) -> `income` at the block's FMV;
# price is P3, so the ref carries `:fmv_unpriced` (price_usdc stays NULL). Alchemica channeled while borrowing is income via R7.
# Real: 0xe7505b72…d183 (borrow 10774, 0.2 GHST to the lender) and 0xec5e558b…7e79 (10774 back to the lender).
def _r8b_borrower(g, w, ex, end, legs, fung, gotchi, L, Review):
    lender = (ex or end)[0][0]; out = []
    for l in gotchi:
        if l["cp"] != lender: raise Review("lending (borrower): gotchi moved to/from an address other than the lender")
        out.append(L(l, "untracked", ref=f"borrowed:{lender}"))
    for l in fung:
        if l["qty"] < 0:
            if not ex: raise Review("lending (borrower): outgoing token leg without GotchiLendingExecuted")
            out.append(L(l, "spend", ref="lending:borrower:upfront"))
        else:
            if not end: raise Review("lending (borrower): incoming token leg without GotchiLendingClaimed/Ended")
            out.append(L(l, "income", ref="lending:borrower:revenue:fmv_unpriced"))
    if len(gotchi) + len(fung) != len(legs): raise Review("lending (borrower) tx with unexplained legs")
    cats = {l["cat"] for l in out}
    return ("spend" if "spend" in cats else "income" if "income" in cats else "untracked"), out, []

# Gotchi pocket (DESIGN v1.3 §9, confirmed: gotchiEscrow(3033) = 0x728f0baf…, owner = the test wallet). depositERC20 into / transferEscrow /
# batchTransferEscrow out of the escrow of a gotchi the wallet owns -> custody at pocket:<gotchiId> (holdings include pockets). esc.pockets maps
# escrow -> gotchi id (gotchi_escrow cache, resolved by RPC at ingest); esc.gotchis = gotchis the wallet owns at this point (lent ones included).
def r_pocket(g, w, tx, sent, to, sel, legs, fung, nfts, market, esc, items, cost_to, L, Review):
    pk = [l for l in fung if l.get("cp") in esc.pockets]
    psel = sent and to == g["aavegotchi"] and sel in GV_SEL["pocket"]
    if not pk:
        if psel and fung: raise Review("gotchi pocket tx: escrow address not in the gotchiEscrow cache")
        return None
    if not psel: raise Review("token move to/from a gotchi pocket outside depositERC20/transferEscrow/batchTransferEscrow")
    if len(pk) != len(legs): raise Review("gotchi pocket tx with other wallet legs")
    out = []
    for l in pk:
        gid = esc.pockets[l["cp"]]
        if esc.gotchis.get(gid, 0) <= 0: raise Review(f"pocket of gotchi {gid}, which the wallet does not own at this point")
        loc = f"pocket:{gid}"
        out += [L(l, "transfer_internal", ref=loc), L(l, "transfer_internal", loc=loc, qty=-l["qty"], ref=loc)]
    return "transfer_internal", out, []

# R7: claim/channel paid from REALM's balance (Great Portal path) on the claim/channel selectors -> income, not deposit
def r7_income(g, w, tx, sent, to, sel, legs, fung, nfts, market, esc, items, cost_to, L, Review):
    if not (sent and to == g["realm"] and sel in GV_SEL["claim_alchemica"]): return None
    if not fung or any(l["qty"] < 0 or l["cp"] not in (g["realm"], "0x" + "0" * 40) or l["contract"] not in g["alchemica"] | {g["gltr"], g["ghst"]}
                       for l in legs):
        return None
    return "income", [L(l, "income") for l in legs], []
