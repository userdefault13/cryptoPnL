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

def gv_rule(chain, w, tx, legs, market, esc, L, Review):
    g = GV.get(chain)
    if not g: return None
    sent = bool(tx) and tx["from"] == w; to = (tx or {}).get("to"); sel = (tx or {}).get("selector")
    fung = [l for l in legs if l["std"] == "erc20"]; nfts = [l for l in legs if l["std"] in ("erc721", "erc1155")]
    items = (g["installation"], g["tile"]); cost_to = {g["realm"], g["pixelcraft"], g["dao"], g["burn"]}
    for r in (r10_pocket, r1_gift, r1_buyorder_add, r2_gbm_seller, r2_buy_now, r9_bounce, r3_craft, r4_upgrade, r5_parcel, r8_lending, r7_income):
        out = r(g, w, tx, sent, to, sel, legs, fung, nfts, market, esc, items, cost_to, L, Review)
        if out: return out
    return None

# R10: FUD depositERC20 (gotchi pocket) to 0x728f0baf… -> review until the counterparty is identified
def r10_pocket(g, w, tx, sent, to, sel, legs, fung, nfts, market, esc, items, cost_to, L, Review):
    if sent and to == g["aavegotchi"] and sel in GV_SEL["pocket_deposit"] and fung:
        raise Review(f"gotchi pocket depositERC20 to {fung[0]['cp']}: counterparty not identified (DESIGN §9 R10)")

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
    claims = [_ti(m, 1) for m in ends]
    mine = [(a, k) for a in claims for (d, k) in list(esc.open) if d == gbm and "#" in k and esc.avail(gbm, k, f"gbm:auction:{a}")]
    if mine:
        g_in = [l for l in fung if l["cp"] == gbm and l["qty"] > 0]
        if len(mine) != 1 or len(g_in) != 1 or len(g_in) != len(legs): raise Review("GBM seller claim: proceeds/escrow do not match one auction")
        a, k = mine[0]; ref = f"gbm:auction:{a}"; q = sum(e["qty"] for e in esc.avail(gbm, k, ref)); esc.take(gbm, k, q, ref)
        c, tid = k.split("#"); li = next(m["li"] for m in ends if _ti(m, 1) == a)
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
    ev = _ev(market, "EventStarted", g["realm"])
    if not (sent and ev): return None
    if not fung or any(l["cp"] != g["burn"] or l["qty"] > 0 or not (l["contract"] == g["gltr"] or l["contract"] in g["alchemica"]) for l in legs):
        raise Review("bounce gate (EventStarted) with legs other than GLTR/alchemica to 0xFFfF")
    ref = f"bounce:event:{_ti(ev[0], 1)}"
    return "spend", [L(l, "spend", ref=ref) for l in legs], []

def _qty_override(market, g, l):
    """Installation/Tile quantity from MintInstallations/MintTiles (owner, id, uint16 amount); TransferSingle may say 1 (§9 R3)."""
    ev = {"installation": "MintInstallations", "tile": "MintTiles"}
    kind = "installation" if l["contract"] == g["installation"] else "tile"
    ms = [m for m in _ev(market, ev[kind], g[kind]) if _ti(m, 2) == int(l["token_id"])]
    return sum(_w(m)[0] for m in ms) if ms else None

# R3: craft (instant / free / queued + claim). Inputs (to REALM, Pixelcraft, DAO, 0xFFfF) are all cost.
def r3_craft(g, w, tx, sent, to, sel, legs, fung, nfts, market, esc, items, cost_to, L, Review):
    claimed = [_ti(m, 1) for c in items for m in _ev(market, "QueueClaimed", c)]
    reduced = [_ti(m, 1) for c in items for m in _ev(market, "CraftTimeReduced", c)]
    is_craft = sent and to in items and sel in GV_SEL["craft"]
    if not (is_craft or claimed or (sent and reduced and to in items)): return None
    mints = [l for l in nfts if l["contract"] in items and l["cp"] == "0x" + "0" * 40 and l["qty"] > 0]
    inputs = [l for l in fung if l["qty"] < 0]
    if any(l["cp"] not in cost_to for l in inputs) or len(mints) + len(inputs) != len(legs):
        raise Review("craft tx with legs outside the 35/30/30/5 cost split or the minted items")
    def nft_out(ref):
        out = []
        for l in mints:
            q = _qty_override(market, g, l); out.append(L(l, "craft", ref=ref, qty=q if q else None))
        return out
    if claimed:                                    # claim of a queued craft: the NFT gets the queued cost (P4)
        if inputs or not mints: raise Review("QueueClaimed without minted items / with payment legs")
        ref = "craft:queue:" + ",".join(str(q) for q in sorted(claimed))
        return "craft", nft_out(ref), []
    if reduced and not is_craft:                   # GLTR to speed up a queued craft: added to that queue's cost
        if mints or not inputs: raise Review("CraftTimeReduced with unexpected legs")
        ref = "craft:queue:" + ",".join(str(q) for q in sorted(reduced))
        return "craft_pending", [L(l, "craft_pending", ref=ref) for l in inputs], []
    queued = [_ti(m, 1) for c in items for m in _ev(market, "AddedToQueue", c)]
    if mints:                                      # instant craft (paid or free: no inputs = basis 0, never income)
        ref = "craft:instant" + ("" if inputs else ":free")
        return "craft", [L(l, "craft", ref=ref) for l in inputs] + nft_out(ref), []
    if queued:
        ref = "craft:queue:" + ",".join(str(q) for q in sorted(queued))
        return "craft_pending", [L(l, "craft_pending", ref=ref) for l in inputs], []
    raise Review("craft tx with neither minted items nor AddedToQueue")

# R4: upgrade. Cost tx (UpgradeQueued owner = wallet / UpgradeInitiated) and reduceUpgradeTime -> upgrade cost legs.
# Finalize (REALM InstallationUpgraded prev -> next): old id leaves parcel:<realm>, new id lands there (no realized PnL; P4).
def r4_upgrade(g, w, tx, sent, to, sel, legs, fung, nfts, market, esc, items, cost_to, L, Review):
    q = [m for m in _ev(market, "UpgradeQueued", g["installation"]) if _ta(m, 1) == w]
    init = _ev(market, "UpgradeInitiated", g["installation"]); red = _ev(market, "UpgradeTimeReduced", g["installation"])
    up = _ev(market, "InstallationUpgraded", g["realm"])
    if not (q or init or red or up): return None
    out = []; inputs = [l for l in fung if l["qty"] < 0]
    if any(l["cp"] not in cost_to for l in inputs): raise Review("upgrade cost legs outside REALM/Pixelcraft/DAO/0xFFfF")
    realm = (_ti(q[0], 2) if q else _ti(init[0], 1) if init else _ti(red[0], 2) if red else _w(up[0])[0])
    ref = f"upgrade:realm:{realm}"
    out += [L(l, "upgrade", ref=ref) for l in inputs]
    rest = [l for l in legs if l not in inputs]
    for m in up:
        r_id, prev, nxt = _w(m)[0], _w(m)[1], _w(m)[2]; loc = f"parcel:{r_id}"
        mine = [l for l in rest if l["contract"] == g["installation"] and int(l["token_id"]) == nxt]
        if sum(l["qty"] for l in mine) != 0: raise Review("upgrade finalize: new id not re-equipped in the same tx")
        out += [L(l, "upgrade", ref=f"upgrade:realm:{r_id}") for l in mine]; rest = [l for l in rest if l not in mine]
        base = dict(li=m["li"], std="erc1155", contract=g["installation"], spam=False, cat="upgrade", ref=f"upgrade:realm:{r_id}", loc=loc)
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
            esc.parcels[parcel] = esc.parcels.get(parcel, 0) - l["qty"]
        elif sign > 0:                                # unequipped but not returned: destroyed (refund type 0)
            refund = [l for l in fung if l["qty"] > 0 and l["contract"] in g["alchemica"]]
            if not refund: raise Review("unequip: item neither returned nor refunded")
            out.append(dict(li=m["li"], std="erc1155", contract=m["contract"], token_id=str(typ), qty=-val, cat="destroy_refund", loc=loc, ref=ref, spam=False))
            out += [L(l, "destroy_refund", ref=ref) for l in refund if l not in used]; used += refund
            esc.parcels[parcel] = esc.parcels.get(parcel, 0) - val
        else: raise Review("TransferToParent without the matching wallet -> REALM item leg")
    if any(l not in used for l in legs): raise Review("equip/unequip tx with unexplained legs")
    cats = {o["cat"] for o in out}
    return ("destroy_refund" if "destroy_refund" in cats else "transfer_internal"), out, []

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
# R7 (lending part): revenue (alchemica/GHST) received with GotchiLendingClaimed/Ended -> income.
def r8_lending(g, w, tx, sent, to, sel, legs, fung, nfts, market, esc, items, cost_to, L, Review):
    ex = _lend(market, g, ("GotchiLendingExecuted",), w); end = _lend(market, g, ("GotchiLendingEnded", "GotchiLendingClaimed"), w)
    if not (ex or end): return None
    out = []; gotchi = [l for l in nfts if l["contract"] == g["aavegotchi"] and l["std"] == "erc721"]
    for lender, borrower in ex + end:
        if lender != w: return None                    # wallet is the borrower: normal rules (no custody of others' gotchis)
    for l in gotchi:
        borrower = (ex or end)[0][1]; loc = f"lent:{borrower}"
        if l["cp"] != borrower: raise Review("lending: gotchi moved to/from an address other than the borrower")
        out += [L(l, "transfer_internal", ref=loc), L(l, "transfer_internal", loc=loc, qty=-l["qty"], ref=loc)]
    for l in fung:
        if l["qty"] <= 0: raise Review("lending tx with an outgoing token leg")
        out.append(L(l, "income", ref="lending:" + ("upfront" if ex else "revenue")))
    if len(out) != len(gotchi) * 2 + len(fung) or len(gotchi) + len(fung) != len(legs): raise Review("lending tx with unexplained legs")
    return ("income" if fung else "transfer_internal"), out, []

# R7: claim/channel paid from REALM's balance (Great Portal path) on the claim/channel selectors -> income, not deposit
def r7_income(g, w, tx, sent, to, sel, legs, fung, nfts, market, esc, items, cost_to, L, Review):
    if not (sent and to == g["realm"] and sel in GV_SEL["claim_alchemica"]): return None
    if not fung or any(l["qty"] < 0 or l["cp"] not in (g["realm"], "0x" + "0" * 40) or l["contract"] not in g["alchemica"] | {g["gltr"], g["ghst"]}
                       for l in legs):
        return None
    return "income", [L(l, "income") for l in legs], []
