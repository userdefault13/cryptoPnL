"""Balances from raw_event vs RPC balanceOf at ingest head + 3 sampled historical blocks."""
import json
from .db import hx
from .sources import RPC
from .config import CHAINS, TRACKED, gated
import os

def ledger(conn, chain, w, block):
    out = {}
    q20 = """SELECT payload->>'contract', kind, sum(CASE WHEN payload->>'to'=%(w)s THEN (payload->>'value')::numeric ELSE 0 END)
                                 - sum(CASE WHEN payload->>'from'=%(w)s THEN (payload->>'value')::numeric ELSE 0 END)
             FROM raw_event WHERE chain_id=%(c)s AND kind IN ('erc20_transfer','erc721_transfer') AND block_number <= %(b)s
               AND (payload->>'to'=%(w)s OR payload->>'from'=%(w)s) GROUP BY 1,2"""
    for c, k, v in conn.execute(q20, {"w": w, "c": chain, "b": block}):
        out[(c, "erc20" if k == "erc20_transfer" else "erc721", None)] = int(v)
    q1155 = """SELECT payload->>'contract', i.id, sum(CASE WHEN payload->>'to'=%(w)s THEN v.val::numeric ELSE 0 END)
                                            - sum(CASE WHEN payload->>'from'=%(w)s THEN v.val::numeric ELSE 0 END)
               FROM raw_event, jsonb_array_elements_text(payload->'ids') WITH ORDINALITY i(id, o)
                    JOIN jsonb_array_elements_text(payload->'values') WITH ORDINALITY v(val, o) ON true
               WHERE i.o = v.o AND chain_id=%(c)s AND kind LIKE 'erc1155%%' AND block_number <= %(b)s
                 AND (payload->>'to'=%(w)s OR payload->>'from'=%(w)s) GROUP BY 1,2"""
    for c, i, v in conn.execute(q1155, {"w": w, "c": chain, "b": block}):
        out[(c, "erc1155", i)] = int(v)
    return out

def onchain(rpc, w, asset, block):
    c, std, tid = asset
    data = ("0x00fdd58e" + w[2:].rjust(64, "0") + hex(int(tid))[2:].rjust(64, "0")) if std == "erc1155" else ("0x70a08231" + w[2:].rjust(64, "0"))
    r = rpc.eth_call(c, data, block)
    return int(r, 16) if r and r != "0x" else 0

def reason(exp, got):
    """Why an untracked asset doesn't reconcile from standard events."""
    if isinstance(got, str): return "non-compliant (balanceOf reverts)"
    if got == 0 and exp != 0: return "spam (Transfer events without balance)"
    if got < exp: return "fee-on-transfer / burn without event"
    return "non-standard mint / rebasing"

def verify(conn, chain, log=print):
    """Gate: every gated asset (TRACKED + allowlist) matches at head + 3 historical blocks.
    Everything else is reported 'untracked' with contract + reason and excluded from PnL totals."""
    rpc = RPC(CHAINS[chain]["rpc"]); G = gated(chain)
    g_total = g_ok = 0; g_fail = []; u_total = 0; untracked = {}
    for wid, addr, last in conn.execute("""SELECT w.id, w.address, c.last_block FROM wallet w JOIN sync_cursor c ON c.wallet_id=w.id
                                           WHERE w.chain_id=%s AND c.source='hypersync'""", (chain,)).fetchall():
        w = hx(addr).lower()
        evb = [r[0] for r in conn.execute("""SELECT DISTINCT block_number FROM raw_event WHERE chain_id=%s AND (payload->>'to'=%s OR payload->>'from'=%s) ORDER BY 1""", (chain, w, w))]
        samples = sorted({evb[int(len(evb) * q)] for q in (0.25, 0.5, 0.75)}) if evb else []
        assets = set(ledger(conn, chain, w, last).keys())
        probe = sorted(assets, key=str)[0] if assets else None
        def served(blk):
            try: onchain(rpc, w, probe, blk); return True
            except RuntimeError as e: return not any(k in str(e) for k in ("pruned", "Unknown state", "4444"))
        if probe and samples and not all(served(x) for x in samples):
            pruned = samples; samples = [last - k * 400_000 for k in (3, 2, 1)]
            log(json.dumps({"note": "RPC has pruned state at event-sampled blocks; using recent historical blocks instead", "pruned_samples": pruned, "samples": samples}))
        blocks = samples + [last]
        for blk in blocks:
            exp = ledger(conn, chain, w, blk)
            for a in sorted(assets, key=str):
                try: got = onchain(rpc, w, a, blk)
                except Exception as e: got = f"ERR {str(e)[:80]}"
                e_ = exp.get(a, 0)
                if a[0] in G:
                    g_total += 1
                    if got == e_: g_ok += 1
                    else: g_fail.append({"wallet_id": wid, "block": blk, "asset": a, "raw_event": str(e_), "rpc": str(got)})
                else:
                    u_total += 1
                    if got != e_:
                        u = untracked.setdefault(a[0], {"contract": a[0], "standard": a[1], "reasons": set(), "failed_checks": 0})
                        u["reasons"].add(reason(e_, got)); u["failed_checks"] += 1
        log(json.dumps({"chain": chain, "wallet_id": wid, "blocks": blocks, "head_block": last, "assets": len(assets)}))
    rows = [dict(u, reasons=sorted(u["reasons"])) for u in sorted(untracked.values(), key=lambda x: x["contract"])]
    by = {}
    for r in rows:
        for x in r["reasons"]: by[x] = by.get(x, 0) + 1
    out = os.environ.get("VERIFY_OUT")
    if out: json.dump({"gated_failures": g_fail, "untracked": rows}, open(out, "w"), indent=1)
    log(json.dumps({"chain": chain, "gated_assets_configured": len(G), "gated_checks": g_total, "gated_match": g_ok, "gated_mismatch": len(g_fail),
                    "untracked_checks": u_total, "untracked_contracts_not_reconciling": len(rows), "untracked_by_reason": by}))
    for f in g_fail: log("GATED_MISMATCH " + json.dumps(f))
    for r in rows: log("UNTRACKED " + json.dumps(r))
    return g_total, g_ok, g_fail
