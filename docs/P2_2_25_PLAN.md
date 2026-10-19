# P2.2 / KNOWN_GAPS #25 plan: Aerodrome FUD/GHST pool beyond add-liquidity

**Status:** **implemented on speculative branch `p2.2-r10b`** (2026-10-19), awaiting architect ack. Do not merge into `main` / PR #5 until ack. PR #5 can still merge with the 4 txs in review if preferred.

**Speculative results (classify-only on `cryptopnl_p22_base`, no HyperSync):** Base **828 / 829 (99.879%)**, review = 1 (internal-ETH gap only). Evidence: `docs/evidence/p2_2_r10b_classify_8453.json`. Unit suite 69 OK.

Branch `p2.2-gotchiverse`. Blocks Base from 824/829 → **828/829** (only the internal-ETH gap left). Spec today: DESIGN v1.3 §9 R10 — plain `lp_add` only; everything else touching pool `0xeae2fb93…` → review.

## Facts (read-only, `cryptopnl_p22_base` after final rerun)

Pool = Aerodrome volatile FUD/GHST `0xeae2fb93e291c2eb69195851813de24f97f1ce71` (also the LP token). Config key `aero_fud_ghst_pool`.

| tx | shape | wallet-visible legs | P2.1 | P2.2 today |
|----|-------|---------------------|------|------------|
| `0x374fdd85…1778e` | direct swap | 3 GHST → pool; ~39,076 FUD ← pool | swap | review (#25) |
| `0x88f750fc…87a00` | direct swap | 3 GHST → pool; ~39,099 FUD ← pool | swap | review (#25) |
| `0xa51f0359…dc31a` | multi-hop | 3 USDC → `0x4e392fbf…`; ~1.24e24 FUD ← pool (intermediate hops not in wallet-scoped logs) | swap | review (#25) |
| `0x061ba233…196c8` | LP stake | 100 LP → `0xab449dca…` (tx.to same); selector `0xe2bbb158` (Aerodrome gauge `deposit`) | untracked | review (#25) |

No plain `lp_add` sample in this wallet. Internal-ETH gap `0xccbfe04a…` stays review (KNOWN_GAPS #5) — out of scope.

## Proposed rule (R10b — architect text for DESIGN §9)

Keep R10 add-liquidity as written. Add **R10b** for the same pool (and, later, other configured alchemica/GHST pools if listed in config):

1. **Pool swap (direct).** Wallet-sent tx. Fungible legs only (plus fee). Exactly one allowlisted token transferred **to** the pool and exactly one different allowlisted token transferred **from** the pool to the wallet. No LP mint/burn. → both legs `swap`, ref `pool_swap:<pool>`. Price in P3.

2. **Pool swap (multi-hop / router).** Wallet-sent tx. Fungible legs only (plus fee). At least one allowlisted token out of the wallet and at least one allowlisted token in, **and** the pool is the counterparty on at least one of those legs (to=pool or from=pool). No LP mint/burn and no LP transfer. → all fungible legs `swap`, ref `pool_swap:<pool>`. (Covers `0xa51f0359…`: USDC out to a hop, FUD in from the pool.)

3. **LP stake / unstake.** Wallet transfers the pool LP token to a non-zero address that is not the pool and not `0x0`/`0xFFfF`, with no other non-fee legs → `transfer_internal`, location `gauge:<to>` (custody; LP already had no cost basis when minted as `untracked` on `lp_add`). Reverse (LP back from that address) → same location cleared. Unknown selector with extra legs → review.

4. **Else** (LP burn, partial fills that fail the shapes, NFT mixed in, etc.) → review, unchanged.

**Why not put the pool in `DEX_ROUTERS`:** R10 already forbids treating it as a router; add-liquidity and gauge flows would be mis-routed. Keep pool-specific matching in `r10_pool`.

**P2.1 parity:** (1)(2) restore `swap`; (3) upgrades P2.1 `untracked` to custody at `gauge:<addr>` so holdings stay correct. If the architect prefers P2.1 literal parity for (3), use `untracked` / `pnl_excluded` instead — call that out in ack.

## Steps

1. ~~Plan (this file)~~ — on `p2.2-gotchiverse`.
2. ~~Implement R10b in `cryptopnl/gotchiverse.py` `r10_pool`~~ — on `p2.2-r10b`.
3. ~~Tests~~ — `test_aerodrome_pool_add_liquidity_and_r10b` (direct, multi-hop, gauge, onesided+burn → review).
4. ~~Unit~~ — 69 OK (1 skipped) on builder Mac.
5. ~~Classify-only proof on existing `cryptopnl_p22_base`~~ — **828/829**. Full HyperSync `p2_2_test.sh` optional after ack (ingest unchanged).
6. Docs after ack: close KNOWN_GAPS #25; fold into P2_2_RESULTS; DESIGN §9 R10b (architect edits, or builder copies ack text like R8b).
7. Merge path after ack: `p2.2-r10b` → `p2.2-gotchiverse` (or into `main` with #5). STOP until ack.

## Out of scope

- Other Aerodrome alchemica pools (FOMO/GHST, …) until a wallet tx hits them — then add config keys and reuse R10b.
- Gauge reward claims, LP fee collection, remove-liquidity — review until a real sample exists.
- Pricing of `pool_swap` / `lp_add` legs — P3.
- Internal-ETH gap (#5).

## Ack checklist (architect)

- [ ] R10b (1) direct pool swap → `swap` / `pool_swap:<pool>`
- [ ] R10b (2) multi-hop with pool as a counterparty → `swap` / `pool_swap:<pool>`
- [ ] R10b (3) LP → gauge: **`transfer_internal` `gauge:<to>`** (recommended) or **`untracked`** (P2.1)
- [ ] Optional: generalize config to a list of alchemica/GHST pools now vs later

Once boxes are ticked (chat reply is enough), builder implements steps 2–6.
