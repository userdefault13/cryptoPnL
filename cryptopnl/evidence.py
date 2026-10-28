"""P3 follow-up (c): write the ledger md5 of one chain to a committed evidence file, so a later run (P4 rebuild, a ledger copy) can be
checked against it. Deterministic: no timestamp, no DSN, no host; the same ledger gives the same bytes."""
import pathlib
from . import classify

NARROW_SQL = """SELECT md5(string_agg(concat_ws('|',encode(tx_hash,'hex'),log_index,asset_id,qty,category,location,escrow_ref),','
    ORDER BY tx_hash,log_index,asset_id,location,qty)), count(*), min(block_number), max(block_number) FROM ledger_entry WHERE chain_id=%s"""
NARROW_DOC = ("md5 of string_agg(concat_ws('|', hex(tx_hash), log_index, asset_id, qty, category, location, escrow_ref), ',' "
              "ORDER BY tx_hash, log_index, asset_id, location, qty) over ledger_entry WHERE chain_id")

def ledger_md5(conn, chain):
    n = conn.execute(NARROW_SQL, (chain,)).fetchone(); c = classify.checksum(conn, chain)
    return {"chain_id": chain, "ledger_rows": n[1], "ledger_min_block": n[2], "ledger_max_block": n[3], "ledger_md5_narrow": n[0],
            "ledger_md5_report": c["ledger_md5"], "review_rows": c["review_rows"], "review_md5": c["review_md5"]}

def render(r, cmd):
    s = lambda v: "none" if v is None else str(v)
    keys = ("chain_id", "ledger_rows", "ledger_min_block", "ledger_max_block", "ledger_md5_narrow", "ledger_md5_report", "review_rows", "review_md5")
    return ("# cryptoPnL ledger md5 evidence (P3 follow-up c). Produced by: " + cmd + "\n"
            "# ledger_md5_narrow = " + NARROW_DOC + "\n"
            "# ledger_md5_report = classify.checksum ledger_md5 (also printed by `classify`)\n"
            + "".join(f"{k}={s(r[k])}\n" for k in keys))

def write_ledger_md5(conn, chain, path):
    r = ledger_md5(conn, chain); p = pathlib.Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render(r, f"python -m cryptopnl ledger-md5 --chain {chain} --out {p.as_posix()}")); return r
