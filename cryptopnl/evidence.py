"""P3 follow-up (c) + P4.1 md5 ruling (architect, 2026-10-28 18:22 PT): write the ledger md5s of one chain to a committed evidence file,
so a later run (P4 rebuild, a ledger copy) can be checked against it. Deterministic: no timestamp, no DSN, no host.
  ledger_md5_v1          the pre-P4.1 definition, unchanged (was `ledger_md5_narrow`), over all rows of the chain;
  ledger_md5_v1_pre_p4_1 v1 over the pre-P4.1 row set only: rows that are not P4.1 internal-ETH legs (trace_address IS NULL);
  ledger_md5_v2          v1's fields + income_subtype, source_ref, trace_address: the canonical baseline (and the gate) from P4.1 on."""
import pathlib
from . import classify

V1_FIELDS = "encode(tx_hash,'hex'),log_index,asset_id,qty,category,location,escrow_ref"
V1_ORDER = "tx_hash,log_index,asset_id,location,qty"
def _sql(fields, order, where=""):
    return (f"SELECT md5(string_agg(concat_ws('|',{fields}),',' ORDER BY {order})), count(*), min(block_number), max(block_number) "
            f"FROM ledger_entry WHERE chain_id=%s{where}")
V1_SQL = """SELECT md5(string_agg(concat_ws('|',encode(tx_hash,'hex'),log_index,asset_id,qty,category,location,escrow_ref),','
    ORDER BY tx_hash,log_index,asset_id,location,qty)), count(*), min(block_number), max(block_number) FROM ledger_entry WHERE chain_id=%s"""   # = pre-P4.1 NARROW_SQL, byte for byte
V1_PRE_SQL = V1_SQL + " AND trace_address IS NULL"
# v2: the three new fields are coalesced to '' so a NULL keeps its position (concat_ws skips NULLs); v1's fields are as in v1
V2_SQL = _sql(V1_FIELDS + ",coalesce(income_subtype,''),coalesce(source_ref,''),coalesce(trace_address,'')", V1_ORDER + ",trace_address")
V1_DOC = ("md5 of string_agg(concat_ws('|', hex(tx_hash), log_index, asset_id, qty, category, location, escrow_ref), ',' "
          "ORDER BY tx_hash, log_index, asset_id, location, qty) over ledger_entry WHERE chain_id (unchanged pre-P4.1 definition, "
          "formerly ledger_md5_narrow)")
V1_PRE_DOC = "v1 over the pre-P4.1 rows only: ... AND trace_address IS NULL (excludes the P4.1 internal-ETH legs)"
V2_DOC = ("md5 of string_agg(concat_ws('|', <v1 fields>, coalesce(income_subtype,''), coalesce(source_ref,''), coalesce(trace_address,'')), ',' "
          "ORDER BY tx_hash, log_index, asset_id, location, qty, trace_address) over ledger_entry WHERE chain_id (P4.1 canonical baseline; gates use v2)")
KEYS = ("chain_id", "ledger_rows", "ledger_min_block", "ledger_max_block", "ledger_md5_v1", "ledger_rows_pre_p4_1", "ledger_md5_v1_pre_p4_1",
        "ledger_md5_v2", "ledger_md5_report", "review_rows", "review_md5")

def ledger_md5(conn, chain):
    v1 = conn.execute(V1_SQL, (chain,)).fetchone()
    p41 = conn.execute("""SELECT count(*) FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'ledger_entry'
        AND column_name IN ('trace_address', 'income_subtype', 'source_ref')""").fetchone()[0] == 3
    if p41: pre = conn.execute(V1_PRE_SQL, (chain,)).fetchone(); v2 = conn.execute(V2_SQL, (chain,)).fetchone()
    else: pre, v2 = v1, (None,)   # schema before migration 015: every row is pre-P4.1; v2 undefined (a v2 gate then fails)
    c = classify.checksum(conn, chain)
    return {"chain_id": chain, "ledger_rows": v1[1], "ledger_min_block": v1[2], "ledger_max_block": v1[3], "ledger_md5_v1": v1[0],
            "ledger_rows_pre_p4_1": pre[1], "ledger_md5_v1_pre_p4_1": pre[0], "ledger_md5_v2": v2[0],
            "ledger_md5_report": c["ledger_md5"], "review_rows": c["review_rows"], "review_md5": c["review_md5"]}

def render(r, cmd):
    s = lambda v: "none" if v is None else str(v)
    return ("# cryptoPnL ledger md5 evidence (P3 follow-up c; P4.1 md5 ruling). Produced by: " + cmd + "\n"
            "# ledger_md5_v1 = " + V1_DOC + "\n"
            "# ledger_md5_v1_pre_p4_1 = " + V1_PRE_DOC + "\n"
            "# ledger_md5_v2 = " + V2_DOC + "\n"
            "# ledger_md5_report = classify.checksum ledger_md5 (also printed by `classify`)\n"
            + "".join(f"{k}={s(r[k])}\n" for k in KEYS))

def write_ledger_md5(conn, chain, path):
    r = ledger_md5(conn, chain); p = pathlib.Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render(r, f"python -m cryptopnl ledger-md5 --chain {chain} --out {p.as_posix()}")); return r
