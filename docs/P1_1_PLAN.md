# P1.1 Wearables (parent transfers) — plan (2026-10-16)
Branch `p1.1-wearables` off `p1-raw-ingest`; PR stacked on PR #1.

## Findings (read-only, Base)
- Aavegotchi Diamond `0xa99c…` holds state (`balanceOf(owner,id)`, `balanceOfToken(diamond,gotchiId,id)`); Wearable Diamond `0x052e…` emits the ERC1155 `TransferSingle/Batch` events and mirrors `balanceOf`. They are **one asset**: alias `0x052e → 0xa99c`.
- Equip/unequip: `TransferToParent(_toContract, _toTokenId, _tokenTypeId, _value)` / `TransferFromParent(...)` on `0xa99c` move wearables into/out of a gotchi's child balance.
- Sepolia: `0x4773…` and `0xb2d5…` both emit identical 1155 mints (duplicates). Pending: emitter guidance from cryptoPnL Architect.

## Steps
1. Config `WEARABLES[chain] = {canonical, emitter, aliases}`. Owner ledger counts 1155 events **only from the emitter** (dedupes mirrored logs) and reports them under the canonical contract.
2. Source `HyperSyncParentTransfers`: TransferToParent/FromParent from the diamond where topic2 (gotchi id) ∈ gotchis the wallet has ever held (from erc721 events on the diamond); 7 req/min.
3. raw_event kinds `wearable_to_parent` / `wearable_from_parent` (payload: gotchi_id, type_id, value, parent_contract). These are **custody changes, never disposals**: P2 must keep FIFO basis (lot moves owner → gotchi child under the same owner).
4. Verify: at head + 3 historical blocks, owner wearable balances (`balanceOf` on canonical) and child balances for gotchis owned at that block (`balanceOfToken`) vs raw_event.
5. Re-run `scripts/p1_test.sh` (idempotent, balances, reorg) on Base, then Sepolia.

## Test
`abra run cryptoPnL -- scripts/p1_test.sh <chain> <wallet>` (adds a wearables gate).
## Rollback
Delete branch; `dropdb` the e2e DBs. Read-only on chain.
