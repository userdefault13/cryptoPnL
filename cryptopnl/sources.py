"""Pluggable sources. P1: HyperSync (log history) + RPC (head/hashes/at-block reads).
The AarcadeGh$t proxy is a point-lookup source only (single-row responses); no Goldsky."""
import os
from .net import Limiter, post_json
from .config import RPC_RPS, RPC_BURST
from .hostlimit import hypersync_limiter
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
T1155S = "0xc3d58168c5ae7397731d063d5bbf3d657854427343f4c083240f7aacaa2d0f62"
T1155B = "0x4a39dc06d4c0dbc64b70af90fd698a233a518aa5d07e595d983b8c0526c8f7fb"
def topic_addr(a): return "0x" + "0" * 24 + a.lower()[2:]
def h2i(x): return x if isinstance(x, int) else int(x, 16)

class RPC:
    def __init__(self, url): self.url = url; self.lim = Limiter(RPC_RPS, RPC_BURST)
    def call(self, method, params):
        r = post_json("rpc", self.lim, self.url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        if "error" in r: raise RuntimeError(f"rpc {method}: {r['error']}")
        return r["result"]
    def block(self, tag):
        b = self.call("eth_getBlockByNumber", [tag if isinstance(tag, str) else hex(tag), False])
        return h2i(b["number"]), b["hash"], h2i(b["timestamp"])
    def safe_head(self):
        try: return self.block("safe")[0]
        except Exception: return self.block("latest")[0] - 64
    def eth_call(self, to, data, block):
        return self.call("eth_call", [{"to": to, "data": data}, hex(block)])

class HyperSyncWalletLogs:
    name = "hypersync"
    _lim = None
    def __init__(self, url):
        self.url = url.rstrip("/") + "/query"
        if HyperSyncWalletLogs._lim is None: HyperSyncWalletLogs._lim = hypersync_limiter()   # host-wide flock budget (P3 step 1)
        self.headers = {"Authorization": "Bearer " + os.environ["ENVIO_API_TOKEN"]}
    def fetch(self, wallet, frm, to):
        """Yield (logs, blocks) pages for [frm, to] (inclusive) touching wallet."""
        t = topic_addr(wallet)
        sel = [{"topics": [[TRANSFER], [t]]}, {"topics": [[TRANSFER], [], [t]]},
               {"topics": [[T1155S, T1155B], [], [t]]}, {"topics": [[T1155S, T1155B], [], [], [t]]}]
        b = frm; self.covered = frm - 1
        while b <= to:
            q = {"from_block": b, "to_block": to + 1, "logs": sel,
                 "field_selection": {"log": ["block_number", "block_hash", "transaction_hash", "log_index", "address",
                                             "topic0", "topic1", "topic2", "topic3", "data"],
                                     "block": ["number", "hash", "timestamp"]}}
            r = post_json("hypersync", self._lim, self.url, q, self.headers)
            logs = [l for d in r.get("data", []) for l in (d.get("logs") or [])]
            blocks = [x for d in r.get("data", []) for x in (d.get("blocks") or [])]
            nb = r["next_block"]
            if nb > b: self.covered = min(nb - 1, to)   # set BEFORE yield so per-page checkpoints see this page
            yield logs, blocks
            if nb <= b: break   # non-advancing: stop; covered stays at last page actually returned
            b = nb

class HyperSyncContractLogs(HyperSyncWalletLogs):
    """All logs with the given topic0s from the given contracts (bulk marketplace ingest)."""
    def __init__(self, url, name, contracts, topics):
        super().__init__(url); self.name = name; self.contracts = contracts; self.topics = topics
    def fetch_range(self, frm, to):
        b = frm; self.covered = frm - 1
        while b <= to:
            q = {"from_block": b, "to_block": to + 1, "logs": [{"address": self.contracts, "topics": [self.topics]}],
                 "field_selection": {"log": ["block_number", "block_hash", "transaction_hash", "log_index", "address",
                                             "topic0", "topic1", "topic2", "topic3", "data"],
                                     "block": ["number", "hash", "timestamp"]}}
            r = post_json("hypersync", self._lim, self.url, q, self.headers)
            nb = r["next_block"]
            if nb > b: self.covered = min(nb - 1, to)   # set BEFORE yield so per-page checkpoints see this page
            yield ([l for d in r.get("data", []) for l in (d.get("logs") or [])],
                   [x for d in r.get("data", []) for x in (d.get("blocks") or [])])
            if nb <= b: break   # non-advancing: stop; covered stays at last page actually returned
            b = nb

T_TO_PARENT = "0xe82810099d182b25e23e895715954d6e7b41867a02e2c693cce68a8f250e43d3"
T_FROM_PARENT = "0x4b287e36a0531da8ccee303de127c778302f48d8fc9569b1fe1dcb9d64465c6d"
class HyperSyncParentTransfers(HyperSyncWalletLogs):
    """Aavegotchi TransferToParent/TransferFromParent for given gotchi ids (topic2), from the parent diamond."""
    name = "hypersync_parent"
    def fetch_ids(self, contract, gotchi_ids, frm, to):
        ids = ["0x" + hex(int(i))[2:].rjust(64, "0") for i in gotchi_ids]
        b = frm; self.covered = frm - 1
        while b <= to:
            q = {"from_block": b, "to_block": to + 1,
                 "logs": [{"address": [contract], "topics": [[T_TO_PARENT, T_FROM_PARENT], [], ids]}],
                 "field_selection": {"log": ["block_number", "block_hash", "transaction_hash", "log_index", "address",
                                             "topic0", "topic1", "topic2", "topic3", "data"],
                                     "block": ["number", "hash", "timestamp"]}}
            r = post_json("hypersync", self._lim, self.url, q, self.headers)
            nb = r["next_block"]
            if nb > b: self.covered = min(nb - 1, to)
            yield ([l for d in r.get("data", []) for l in (d.get("logs") or [])],
                   [x for d in r.get("data", []) for x in (d.get("blocks") or [])])
            if nb <= b: break
            b = nb

class HyperSyncWalletTxs(HyperSyncWalletLogs):
    """P2: transactions sent from / to the wallet (gas, native value, status). Shares the 5/min limiter."""
    name = "hypersync_tx"
    def fetch(self, wallet, frm, to):
        b = frm; self.covered = frm - 1; w = wallet.lower()
        while b <= to:
            q = {"from_block": b, "to_block": to + 1, "transactions": [{"from": [w]}, {"to": [w]}],
                 "field_selection": {"transaction": ["hash", "block_number", "block_hash", "transaction_index", "from", "to",
                                                     "value", "gas_used", "effective_gas_price", "l1_fee", "status", "input"],
                                     "block": ["number", "hash", "timestamp"]}}
            r = post_json("hypersync", self._lim, self.url, q, self.headers)
            nb = r["next_block"]
            if nb > b: self.covered = min(nb - 1, to)
            yield ([t for d in r.get("data", []) for t in (d.get("transactions") or [])],
                   [x for d in r.get("data", []) for x in (d.get("blocks") or [])])
            if nb <= b: break
            b = nb

class HyperSyncWalletGV(HyperSyncWalletLogs):
    """P2.2 (DESIGN v1.3 §9): every log of wallet-sent txs (join_mode "JoinAll") plus logs of txs that carry a wallet-topic
    Gotchiverse/marketplace/lending event or an Installation/Tile/Aavegotchi token move to/from the wallet (JoinAll pulls the whole tx,
    e.g. a finalize or claim sent by someone else). Shares the host HyperSync lock (<= 5/min)."""
    name = "hypersync_gv"
    def fetch(self, wallet, frm, to, gv, topics):
        t = topic_addr(wallet); b = frm; self.covered = frm - 1
        lend = [k for k, v in topics.items() if v in ("GotchiLendingExecuted", "GotchiLendingEnded", "GotchiLendingClaimed")]
        rcpt = [k for k, v in topics.items() if v.endswith("ExecutedToRecipient")]
        nft = [gv["installation"], gv["tile"], gv["aavegotchi"], gv["realm"]]
        logs_sel = [{"topics": [rcpt, [], [], [t]]},
                    {"address": [gv["aavegotchi"]], "topics": [lend, [], [t]]}, {"address": [gv["aavegotchi"]], "topics": [lend, [], [], [t]]},
                    {"address": nft, "topics": [[T1155S, T1155B], [], [], [t]]}, {"address": nft, "topics": [[T1155S, T1155B], [], [t]]},
                    {"address": nft, "topics": [[TRANSFER], [t]]}, {"address": nft, "topics": [[TRANSFER], [], [t]]}]
        while b <= to:
            q = {"from_block": b, "to_block": to + 1, "join_mode": "JoinAll", "transactions": [{"from": [wallet.lower()]}], "logs": logs_sel,
                 "field_selection": {"log": ["block_number", "block_hash", "transaction_hash", "log_index", "address",
                                             "topic0", "topic1", "topic2", "topic3", "data"],
                                     "block": ["number", "hash", "timestamp"]}}
            r = post_json("hypersync", self._lim, self.url, q, self.headers)
            nb = r["next_block"]
            if nb > b: self.covered = min(nb - 1, to)
            yield ([l for d in r.get("data", []) for l in (d.get("logs") or [])],
                   [x for d in r.get("data", []) for x in (d.get("blocks") or [])])
            if nb <= b: break
            b = nb
