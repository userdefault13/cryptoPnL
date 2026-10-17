# P3 status: PAUSED (CoS option b, 2026-10-17 00:42 PDT)

P3 is paused so that P2.2 (Gotchiverse classification) can run first. One phase at a time, no parallel runs. Branch `p3-pricing` is pushed unmerged.
Main (bed74e9) has NOT been merged in yet. A trial merge in a scratch worktree was clean, with an identical tree, and 52/52 unit tests passed.

## Commits
- e2e5d16 docs: PR #4 nits (also cherry-picked as the first P2.2 commit; the two are identical when both land)
- 87c7986 step 0: docs/P3_PLAN.md
- 1f67f87 step 1: host-level HyperSync lock + two-process tests (cherry-picked into p2.2-gotchiverse)
- 15c01b3 pricer, ledger price pass, migration 007 + rollback, tests
- p3_test.sh + DefiLlama searchWidth 3600
- this WIP commit: KNOWN_GAPS #15/#16 resolved (#16 cites the architect ruling, P6 note), .env.example, partial evidence

## Base run (stopped at a safe point; local DB copy cryptopnl_p3_base, zero HyperSync)
- classify ×2 after tx-index ordering: 1252 rows / md5 34b5a786b2acdb922a07f41a7206d57a, the same as P2.1.
- Ledger price pass completed. Coverage: 1252 entries, 742 priced, 510 flagged, **0 with neither** (criterion 3 holds; docs/evidence/p3_coverage_8453.json).
  Flags: spam 339, untracked 53, pending_basis 81, nft_no_trade 7, no_price 30 (docs/evidence/p3_no_price_8453.txt).
- **RPC 429 storm:** base.drpc.org returned 238 HTTP 429s in 1444 attempts (16%) at the 1 req/s limiter, with no Retry-After. Retries absorbed them,
  but this is a storm and must be fixed before resuming: a lower RPC rate, or a second free RPC.
- The sample step (criteria 1 and 2) was stopped before it produced output. **Not verified.**

## Open before resuming (owner: architect)
- DESIGN v1.3 replaces v1.2 for P3. The plan must be re-read against v1.3 §2/§9 (craft/upgrade/refund pricing blocks).
- Liquidity floor: the alchemica/GHST Aerodrome pools hold only $220–$1,300 of GHST reserve, so the proposed $1,000 floor rejects them at later blocks.
- DefiLlama searchWidth (3600 s), the confidence-label mapping per source, and the price_point source names (dex_slot0/dex_reserves/numeraire).
- GLTR: no pool vs USDC/WETH/GHST and no DefiLlama price.

## Architect ruling (2026-10-17, 01:19 PDT): alchemica pricing order, recorded only, not implemented (P3 paused)
Try each source in order and use the first that yields a price:
1. Trade-implied price (the wallet's own trade at that tx).
2. The pool at the block, if its depth is at or above the liquidity floor. Confidence high or medium.
3. The Gotchi-Trader daily candle. Confidence medium.
4. A thin pool below the floor, if it has non-zero reserves and a swap within 7 days. Confidence low, and flagged.
5. Otherwise unpriced: excluded from totals and flagged.
- Record the pool's USD depth with each price.
- Low-confidence prices count in the totals and carry a badge. Also report a total that excludes them.
- This answers the "Liquidity floor" item above. When P3 resumes, check Gotchi-Trader against the free-sources rule and add any key it needs to .env.example by name.
