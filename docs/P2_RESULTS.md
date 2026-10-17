# P2 results: ledger & classification

Pass test (DESIGN v1.1 §4 / docs/P2_PLAN.md): >98% of wallet txs classified, the rest in `review_queue`, and 10 hand-checked txs matching the explorer.

| chain | DB | wallet txs | classified | review | % | gate | ledger rows / md5 | evidence |
|-------|----|-----------:|-----------:|-------:|--:|------|-------------------|----------|
| Base 8453 | cryptopnl_p11s_base | 829 | 820 | 9 | 98.914 | PASS | 1202 / f7c3e423439305c3650e65c57fbce277 | docs/evidence/p2_classify_8453.json |
| Base Sepolia 84532 | cryptopnl_p11s_sep | 126 | 126 | 0 | 100.0 | PASS | 802 / 9070322da1b4db06847e3e4ddb346c0a | docs/evidence/p2_classify_84532.json |

- Idempotency: `classify` run twice per chain gives identical ledger/review md5 (scripts/p2_test.sh enforces this).
- Hand check: 10/10 match Blockscout. See docs/evidence/p2_handcheck.md.
- Base review queue (9): 7 zero-value poisoning transfers, 1 mixed in/out (pass-through spam token), 1 DEX-router swap into ETH (internal ETH not indexed; known gap, DESIGN §1).
- Spam: 354 Base / 72 Sepolia txs carry non-allowlisted token deposit/withdrawal/income legs. They stay in the ledger and are not priced (P3/P4 decision).

Test command: `CRYPTOPNL_DSN=dbname=<db> abra run cryptoPnL -- scripts/p2_test.sh <chain> <wallet>`; unit tests: `CRYPTOPNL_DSN=postgresql:///cryptopnl_unit11 ENVIO_API_TOKEN=x .venv/bin/python -m unittest discover tests` (12 OK).
