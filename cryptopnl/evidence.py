"""P3 follow-up (c) + P4.1 md5 ruling (architect, 2026-10-28 18:22 PT): write the ledger md5s of one chain to a committed evidence file,
so a later run (P4 rebuild, a ledger copy) can be checked against it. Deterministic: no timestamp, no DSN, no host.
  ledger_md5_v1          the pre-P4.1 definition, unchanged (was `ledger_md5_narrow`), over all rows of the chain;
  ledger_md5_v1_pre_p4_1 v1 over the pre-P4.1 row set only: rows that are not P4.1 internal-ETH legs (trace_address IS NULL);
  ledger_md5_v1_untouched_txs  v1 over the rows of txs NOT touched by any P4.1 rule (continuity: those rows must not change across
                         P4.1). Touched = internal-ETH txs (a ledger row with trace_address, rules 1-6) UNION rule 7 pocket txs (a
                         raw_event of kind 'pocket_transfer') (architect ruling on PR #9, 2026-10-28 22:48 PT);
                         the tx list comes from this ledger, or from another one (`--untouched-txs-from-db`, to hash a pre-P4.1 ledger
                         over the same rows);
  ledger_md5_v2          v1's fields + income_subtype, source_ref, trace_address: the canonical baseline and the STRUCTURAL gate from P4.1 on;
  ledger_md5_v2_valued   v2's fields + price_usdc::text, price_source, price_confidence_label, price_flag (each coalesced to ''), in v2's
                         order: the VALUED gate (architect, P4.2 follow-ups). Excludes the float price_confidence (its label carries it;
                         float text is fragile) and price_id (a surrogate key). There is no value_usdc column (value = qty * price_usdc)."""
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
V1_UNTOUCHED_SQL = V1_SQL + " AND NOT (tx_hash = ANY(%s))"
INTERNAL_TXS_SQL = "SELECT DISTINCT tx_hash FROM ledger_entry WHERE chain_id=%s AND trace_address IS NOT NULL ORDER BY 1"
POCKET_TXS_SQL = "SELECT DISTINCT tx_hash FROM raw_event WHERE chain_id=%s AND kind='pocket_transfer' ORDER BY 1"   # P4.1 rule 7
# v2: the three new fields are coalesced to '' so a NULL keeps its position (concat_ws skips NULLs); v1's fields are as in v1
V2_FIELDS = V1_FIELDS + ",coalesce(income_subtype,''),coalesce(source_ref,''),coalesce(trace_address,'')"
V2_ORDER = V1_ORDER + ",trace_address"
V2_SQL = _sql(V2_FIELDS, V2_ORDER)
V2_VALUED_SQL = _sql(V2_FIELDS + ",coalesce(price_usdc::text,''),coalesce(price_source,''),coalesce(price_confidence_label,''),coalesce(price_flag,'')",
                     V2_ORDER)
V1_DOC = ("md5 of string_agg(concat_ws('|', hex(tx_hash), log_index, asset_id, qty, category, location, escrow_ref), ',' "
          "ORDER BY tx_hash, log_index, asset_id, location, qty) over ledger_entry WHERE chain_id (unchanged pre-P4.1 definition, "
          "formerly ledger_md5_narrow)")
V1_PRE_DOC = "v1 over the pre-P4.1 rows only: ... AND trace_address IS NULL (excludes the P4.1 internal-ETH legs)"
V1_UNTOUCHED_DOC = ("v1 over rows of txs no P4.1 rule touched: ... AND NOT (tx_hash = ANY(<txs having a ledger row with trace_address IS NOT NULL> "
                    "UNION <txs having a raw_event with kind = 'pocket_transfer'>)); internal_eth_txs / pocket_txs / untouched_excluded_txs = "
                    "the two lists' sizes and the union's; "
                    "untouched_txs_from = the ledger the tx list was read from (self, or --untouched-txs-from-db)")
V2_DOC = ("md5 of string_agg(concat_ws('|', <v1 fields>, coalesce(income_subtype,''), coalesce(source_ref,''), coalesce(trace_address,'')), ',' "
          "ORDER BY tx_hash, log_index, asset_id, location, qty, trace_address) over ledger_entry WHERE chain_id (P4.1 canonical baseline; gates use v2)")
V2_VALUED_DOC = ("md5 of string_agg(concat_ws('|', <v2 fields>, coalesce(price_usdc::text,''), coalesce(price_source,''), "
                 "coalesce(price_confidence_label,''), coalesce(price_flag,'')), ',' ORDER BY <v2 order>) over ledger_entry WHERE chain_id "
                 "(valued gate; excludes price_confidence (float) and price_id)")
KEYS = ("chain_id", "ledger_rows", "ledger_min_block", "ledger_max_block", "ledger_md5_v1", "ledger_rows_pre_p4_1", "ledger_md5_v1_pre_p4_1",
        "internal_eth_txs", "pocket_txs", "untouched_excluded_txs", "untouched_txs_from", "ledger_rows_untouched_txs", "ledger_md5_v1_untouched_txs",
        "ledger_md5_v2", "ledger_md5_v2_valued", "ledger_md5_report", "review_rows", "review_md5")

def has_p41(conn):
    return conn.execute("""SELECT count(*) FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'ledger_entry'
        AND column_name IN ('trace_address', 'income_subtype', 'source_ref')""").fetchone()[0] == 3
def internal_txs(conn, chain):
    """tx hashes (bytes) of the ledger's P4.1 internal-ETH legs; none before migration 015."""
    return [bytes(r[0]) for r in conn.execute(INTERNAL_TXS_SQL, (chain,))] if has_p41(conn) else []

def pocket_txs(conn, chain):
    """tx hashes (bytes) of the rule 7 pocket transfers loaded into raw_event (`cryptopnl pockets`); none before P4.1."""
    return [bytes(r[0]) for r in conn.execute(POCKET_TXS_SQL, (chain,))]
def touched_txs(conn, chain):
    """(internal-ETH txs, pocket txs): every tx a P4.1 rule touched; their union is excluded from ledger_md5_v1_untouched_txs."""
    return internal_txs(conn, chain), pocket_txs(conn, chain)

def ledger_md5(conn, chain, untouched_txs=None, untouched_from="self"):
    """untouched_txs: None = read from this ledger; else (internal-ETH txs, pocket txs) from another ledger, or a plain list = one list."""
    v1 = conn.execute(V1_SQL, (chain,)).fetchone()
    p41 = has_p41(conn)
    t = touched_txs(conn, chain) if untouched_txs is None else untouched_txs if isinstance(untouched_txs, tuple) else (list(untouched_txs), [])
    txs = sorted(set(t[0]) | set(t[1]))
    un = conn.execute(V1_UNTOUCHED_SQL, (chain, txs)).fetchone()
    if p41: pre = conn.execute(V1_PRE_SQL, (chain,)).fetchone(); v2 = conn.execute(V2_SQL, (chain,)).fetchone(); vv = conn.execute(V2_VALUED_SQL, (chain,)).fetchone()
    else: pre, v2, vv = v1, (None,), (None,)   # schema before migration 015: every row is pre-P4.1; v2 / v2_valued undefined (their gates then fail)
    c = classify.checksum(conn, chain)
    return {"chain_id": chain, "ledger_rows": v1[1], "ledger_min_block": v1[2], "ledger_max_block": v1[3], "ledger_md5_v1": v1[0],
            "ledger_rows_pre_p4_1": pre[1], "ledger_md5_v1_pre_p4_1": pre[0], "internal_eth_txs": len(t[0]), "pocket_txs": len(t[1]),
            "untouched_excluded_txs": len(txs), "untouched_txs_from": untouched_from,
            "ledger_rows_untouched_txs": un[1], "ledger_md5_v1_untouched_txs": un[0], "ledger_md5_v2": v2[0], "ledger_md5_v2_valued": vv[0],
            "ledger_md5_report": c["ledger_md5"], "review_rows": c["review_rows"], "review_md5": c["review_md5"]}

def render(r, cmd):
    s = lambda v: "none" if v is None else str(v)
    return ("# cryptoPnL ledger md5 evidence (P3 follow-up c; P4.1 md5 ruling). Produced by: " + cmd + "\n"
            "# ledger_md5_v1 = " + V1_DOC + "\n"
            "# ledger_md5_v1_pre_p4_1 = " + V1_PRE_DOC + "\n"
            "# ledger_md5_v1_untouched_txs = " + V1_UNTOUCHED_DOC + "\n"
            "# ledger_md5_v2 = " + V2_DOC + "\n"
            "# ledger_md5_v2_valued = " + V2_VALUED_DOC + "\n"
            "# ledger_md5_report = classify.checksum ledger_md5 (also printed by `classify`)\n"
            + "".join(f"{k}={s(r[k])}\n" for k in KEYS))

def write_ledger_md5(conn, chain, path, untouched_txs=None, untouched_from="self"):
    r = ledger_md5(conn, chain, untouched_txs, untouched_from); p = pathlib.Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render(r, f"python -m cryptopnl ledger-md5 --chain {chain} --out {p.as_posix()}")); return r
