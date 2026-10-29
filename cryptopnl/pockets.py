"""P4.1 rule 7 (DESIGN §8): load the gotchi pocket facts of docs/evidence/p4_1_pockets.json (scripts/p4_1_pockets.py, read-only
HyperSync + Multicall3 eth_call) into the ledger DB. Idempotent; no network.
  * gotchi_escrow: missing escrows are added; a different stored escrow is an error.
  * raw_event kind='pocket_transfer' (source 'hypersync_pocket'): every Transfer / TransferSingle / TransferBatch log into or out of
    a wallet's pocket that touches no wallet of the chain (wallet-touching logs are already wallet-scoped raw rows, verified present).
    payload: contract, std, from, to, value | token_id | ids/values, selector, tx_from, tx_to, wallet (owner wallet of the gotchi).
  * block / tx_position rows for those third-party txs (timestamp, hash and tx index from HyperSync).
  * gotchi_lending: one row per listing of the wallet's gotchis (add / execute / end / cancel blocks).
Only rows at or below the last block of the wallet-scoped raw data are loaded (to_block), so as_of does not move."""
import json, os
from collections import defaultdict
from .config import GV
from .ingest import gotchis_ever

def b(h): return bytes.fromhex(h[2:])
def hx(v): return "0x" + bytes(v).hex()

def load(path):
    with open(path) as f: return json.load(f)

GHST_POCKET_WEI = 652629999999999997500   # canonical Base pocket GHST in == out (raw wei; docs/P4_RESULTS.md, p4_reconcile_8453.json)
def ghst_gate_error(rec, expect_wei=GHST_POCKET_WEI):
    """p4_test GHST pocket gate (P4.2 nit): None when the reconcile output has pockets.ghst_gate with in == out == expect_wei; else why.
    A missing gate FAILS (it used to pass): a ledger with pocket rows and no GHST row means the rule did not run."""
    g = (rec.get("pockets") or {}).get("ghst_gate")
    if not g: return "ghst_gate missing from the reconcile output"
    if not g.get("in_eq_out") or g.get("in_raw") != g.get("out_raw"): return f"GHST pocket in {g.get('in_raw')} != out {g.get('out_raw')}"
    if g.get("in_raw") != str(expect_wei): return f"GHST pocket in/out {g.get('in_raw')} != pinned {expect_wei} wei"
    return None

def ingest_pockets(conn, chain, path, to_block=None, log=print):
    d = load(path); canonical = GV[chain]["aavegotchi"]
    wallets = {a: wid for wid, a in conn.execute("SELECT id, '0x'||encode(address,'hex') FROM wallet WHERE chain_id=%s", (chain,))}
    if to_block is None:
        to_block = conn.execute("""SELECT max(block_number) FROM raw_event WHERE chain_id=%s AND kind NOT IN ('pocket_transfer')""", (chain,)).fetchone()[0]
    held = {a: set(gotchis_ever(conn, chain, a, canonical)) for a in wallets}
    owner_wallet = {}
    for g in map(int, d["escrow"]):
        ws = [a for a, s in held.items() if g in s]
        if len(ws) > 1: raise RuntimeError(f"gotchi {g} held by more than one wallet of the chain; pocket rows need a per-block owner")
        if ws: owner_wallet[g] = ws[0]
    st = defaultdict(int)
    have = {int(g): hx(e) for g, e in conn.execute("SELECT gotchi_id, escrow FROM gotchi_escrow WHERE chain_id=%s", (chain,))}
    for g, e in d["escrow"].items():
        g = int(g)
        if g in have:
            if have[g] != e: raise RuntimeError(f"gotchi {g}: stored escrow {have[g]} != evidence {e}")
            st["escrow_cached"] += 1; continue
        conn.execute("INSERT INTO gotchi_escrow(chain_id,gotchi_id,escrow,resolved_block) VALUES (%s,%s,%s,%s)", (chain, g, b(e), d["query"]["last_block"]))
        st["escrow_added"] += 1
    pockets = {e: int(g) for g, e in d["escrow"].items()}
    logs = {}
    for r in d["rows"]:   # evidence rows are per (log, pocket side, token id); fold back to one raw row per log
        k = (r["tx"], r["log_index"]); x = logs.setdefault(k, {"r": r, "ids": [], "values": []})
        if r["kind"] == "erc1155" and r["dir"] == ("in" if r["to"] in pockets else "out"):
            x["ids"].append(r["token_id"]); x["values"].append(r["amount_raw"])
    for (tx, li), x in sorted(logs.items(), key=lambda kv: (kv[1]["r"]["block"], kv[0][1])):
        r = x["r"]
        if r["block"] > to_block: st["after_to_block"] += 1; continue
        if r["from"] in wallets or r["to"] in wallets:
            ok = conn.execute("SELECT 1 FROM raw_event WHERE chain_id=%s AND tx_hash=%s AND log_index=%s AND kind <> 'pocket_transfer'",
                              (chain, b(tx), li)).fetchone()
            if not ok: raise RuntimeError(f"wallet-touching pocket log {tx}:{li} has no wallet-scoped raw row; re-run ingest first")
            st["wallet_scoped_present"] += 1; continue
        g = pockets[r["pocket"]]; w = owner_wallet.get(g)
        if w is None: raise RuntimeError(f"pocket of gotchi {g} but no wallet of the chain ever held it")
        p = {"contract": r["token"], "std": r["kind"], "from": r["from"], "to": r["to"], "selector": r["selector"], "tx_from": r["tx_from"],
             "tx_to": r["tx_to"], "wallet": w}
        if r["kind"] == "erc20": p["value"] = r["amount_raw"]
        elif r["kind"] == "erc721": p["token_id"] = r["token_id"]
        else: p["ids"], p["values"] = x["ids"], x["values"]
        n = conn.execute("""INSERT INTO raw_event(chain_id,tx_hash,log_index,block_number,block_hash,source,kind,payload) VALUES
            (%s,%s,%s,%s,%s,'hypersync_pocket','pocket_transfer',%s) ON CONFLICT DO NOTHING""",
            (chain, b(tx), li, r["block"], b(r["block_hash"]), json.dumps(p, sort_keys=True))).rowcount
        if not n:
            k = conn.execute("SELECT kind FROM raw_event WHERE chain_id=%s AND tx_hash=%s AND log_index=%s", (chain, b(tx), li)).fetchone()[0]
            if k != "pocket_transfer": raise RuntimeError(f"{tx}:{li} already stored as {k}")
        st["raw_inserted" if n else "raw_present"] += 1
        bh = conn.execute("SELECT hash FROM block WHERE chain_id=%s AND number=%s", (chain, r["block"])).fetchone()
        if bh is None:
            conn.execute("INSERT INTO block(chain_id,number,hash,ts) VALUES (%s,%s,%s,to_timestamp(%s))", (chain, r["block"], b(r["block_hash"]), r["ts"]))
            st["blocks_added"] += 1
        elif hx(bh[0]) != r["block_hash"]: raise RuntimeError(f"block {r['block']}: stored hash differs from HyperSync")
        conn.execute("INSERT INTO tx_position(chain_id,tx_hash,block_number,tx_index) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                     (chain, b(tx), r["block"], r["tx_index"]))
    # rentals
    L = d["lending"]
    if L["operator_calls"] or L["operator_events"]: raise RuntimeError("a lending operator was set: listings by the operator are not in the evidence")
    lent_first = [g for g, v in L["at_first_inflow"].items() if v["lent"]]
    if lent_first: raise RuntimeError(f"gotchis already lent at the first inflow block: {lent_first} (listing predates the evidence)")
    lst = {int(k): v for k, v in L["listings"].items()}
    for k, v in L["at_first_inflow"].items():
        if v["listing_id"] and v["listing_id"] not in lst: raise RuntimeError(f"listing {v['listing_id']} of gotchi {k} has no Added event in the evidence")
    by = defaultdict(dict)
    for e in L["events"]: by[e["listing_id"]].setdefault(e["event"], (e["block"], e["log_index"]))
    for lid, v in sorted(lst.items()):
        ev = by.get(lid, {}); ex, en, ca = ev.get("execute"), ev.get("end"), ev.get("cancel")
        conn.execute("""INSERT INTO gotchi_lending(chain_id,listing_id,gotchi_id,lender,added_block,executed_block,executed_log,ended_block,ended_log,
            cancelled_block,source) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'hypersync_lending_events') ON CONFLICT (chain_id, listing_id) DO UPDATE SET
            executed_block=EXCLUDED.executed_block, executed_log=EXCLUDED.executed_log, ended_block=EXCLUDED.ended_block, ended_log=EXCLUDED.ended_log,
            cancelled_block=EXCLUDED.cancelled_block""",
            (chain, lid, v["token"], b(v["lender"]), v["block"], ex and ex[0], ex and ex[1], en and en[0], en and en[1], ca and ca[0]))
        st["listings"] += 1; st["rentals"] += bool(ex)
    # ownership cross-check at the first inflow block: ledger (wallet-scoped ERC721 legs) vs RPC ownerOf
    fb = d["query"]["first_inflow_block"]; diff = []
    for g, v in L["at_first_inflow"].items():
        g = int(g); w = owner_wallet.get(g)
        q = 0 if w is None else conn.execute("""SELECT coalesce(sum(CASE WHEN payload->>'to'=%s THEN 1 ELSE -1 END),0) FROM raw_event WHERE chain_id=%s
            AND kind='erc721_transfer' AND payload->>'contract'=%s AND payload->>'token_id'=%s AND block_number < %s""", (w, chain, canonical, str(g), fb)).fetchone()[0]
        if (q > 0) != (v["owner"] in wallets): diff.append(g)
    st["owner_crosscheck_gotchis"] = len(L["at_first_inflow"]); st["owner_crosscheck_diff"] = len(diff)
    if diff: raise RuntimeError(f"ledger owner differs from ownerOf at block {fb} for gotchis {diff}")
    conn.commit()
    out = {"chain": chain, "pockets": len(pockets), "to_block": to_block, **st}; log(json.dumps(out)); return out

def pocket_report(conn, chain, path=None):
    """Rule 7 gate and counts. Ledger side: qty in / out at pocket:* locations per asset (income + custody in; custody out), spam legs
    counted apart, pocket_owner_mismatch legs from review_queue. Evidence side (when the file exists): inflow legs by (sender class,
    token) BEFORE (as observed on chain) and AFTER (the ledger category each leg got)."""
    from decimal import Decimal
    from .config import POCKETS
    C = POCKETS.get(chain, {}); dec = {}
    q = defaultdict(lambda: {"in": Decimal(0), "out": Decimal(0), "in_income": Decimal(0), "in_internal": Decimal(0), "rows": 0})
    for c, std, tid, qty, cat, spam in conn.execute("""SELECT '0x'||encode(s.contract,'hex'), s.standard, s.token_id, l.qty, l.category, l.pnl_excluded
          FROM ledger_entry l JOIN asset s ON s.id=l.asset_id WHERE l.chain_id=%s AND l.location LIKE 'pocket:%%'""", (chain,)):
        if spam: continue
        k = c if std == "erc20" else f"{c}#{tid}"; x = q[k]; x["rows"] += 1
        if qty > 0: x["in"] += qty; x["in_income" if cat == "income" else "in_internal"] += qty
        else: x["out"] -= qty
    flags = [l for (d,) in conn.execute("SELECT detail FROM review_queue WHERE chain_id=%s AND reason='pocket_owner_mismatch'", (chain,)) for l in d["legs"]]
    out = {"assets": {k: {kk: str(vv) for kk, vv in v.items()} for k, v in sorted(q.items())},
           "pocket_owner_mismatch": {"legs": len(flags), "by_why": dict(sorted(defaultdict(int, {}).items()))}}
    bw = defaultdict(int)
    for f in flags: bw[f["why"]] += 1
    out["pocket_owner_mismatch"]["by_why"] = dict(bw)
    ghst = C.get("ghst") or "0xcd2f22236dd9dfe2356d7c543161d4d260fd9bcb"
    g = q.get(ghst)
    if g:
        out["ghst_gate"] = {"in_raw": str(g["in"]), "out_raw": str(g["out"]), "in_eq_out": g["in"] == g["out"]}
    if path and os.path.exists(path):
        d = load(path); W = {a for (a,) in conn.execute("SELECT '0x'||encode(address,'hex') FROM wallet WHERE chain_id=%s", (chain,))}
        cat = {(hx(t), li): c for t, li, c in conn.execute("""SELECT tx_hash, log_index, category FROM ledger_entry WHERE chain_id=%s
              AND location LIKE 'pocket:%%' AND qty > 0""", (chain,))}
        fl = {(hx(t), l["li"]) for t, dd in conn.execute("SELECT tx_hash, detail FROM review_queue WHERE chain_id=%s AND reason='pocket_owner_mismatch'", (chain,))
              for l in dd["legs"]}
        before, after = defaultdict(int), defaultdict(int)
        for r in d["rows"]:
            if r["dir"] != "in": continue
            snd = "rf_relayer" if r["from"] == C.get("rf_relayer") else ("wallet_group" if r["from"] in W else "third_party")
            k = f"{snd}|{r['kind']}|{r['token']}"; before[k] += 1
            a = cat.get((r["tx"], r["log_index"])) or ("pocket_owner_mismatch" if (r["tx"], r["log_index"]) in fl else "not_in_ledger")
            after[f"{k}|{a}"] += 1
        out["counts_before"] = dict(sorted(before.items())); out["counts_after"] = dict(sorted(after.items()))
    return out
