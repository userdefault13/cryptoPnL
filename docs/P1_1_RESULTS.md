# P1.1 results (wearable parent transfers)

Command: `abra run cryptoPnL -- scripts/p1_test.sh <chain> <TEST_WALLET>` (fresh local DBs, nohup). Logs: `docs/evidence/p1_1_e2e_{8453,84532}.log`.

| Test | Base 8453 | Sepolia 84532 |
|---|---|---|
| Idempotent re-ingest | PASS 32,639 = 32,639 rows (incl. 92 `wearable_to_parent`), checksum `21d03b61…` | PASS 745, `e93ddc39…` |
| Gated balances (15-asset allowlist) | PASS 128/128 | N/A (no allowlist) |
| Wearables: owner `balanceOf` + gotchi `balanceOfToken` at 3 historical + head | PASS 396/396 (7 owner type ids, 23 gotchis, 92 child pairs; blocks 33208455, 33208693, 33208825, 52698329) | N/A (no wearables; 0x4773/0xb2d5 are Installation diamonds) |
| Reorg | PASS fork 52,440,523, restored | PASS fork 47,171,965, restored |

Run 1 on Base (`p1_1_e2e_8453_run1_reorgFAIL.log`): wearables 396/396 PASS, but the reorg harness missed a tampered block by 41 blocks
(window derived from the wallet cursor while the global cursor was newer, after a host pause). Fixed in `scripts/p1_test.sh` (newest of all cursors + 100k margin).

Caveat: historical sample blocks are quartiles of wearable-related event blocks; for this wallet they cluster near the Base migration (~33.2M).

Sepolia Installation-diamond scan (`verify/sepolia_installations_scan.py`, 2 HyperSync requests;
`docs/evidence/p1_1_sepolia_installations_scan.json.txt`): 7 TransferSingle to the wallet on each of 0x4773… and 0xb2d5…, same 7 ids
(10, 25, 26, 31, 65, 74, 145) in distinct txs, 0 TransferBatch, 0 TransferToParent (none on either contract at all).
