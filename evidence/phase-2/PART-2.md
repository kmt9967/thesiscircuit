# Phase 2 Part 2 evidence — deployment verification

## VERIFIED

- Initial branch feat/phase-2-autonomous-agent clean at cf4907c; PR #3 open, green, unmerged.
- Production baseline September 2, 2026 ~21:22 UTC: market CLOSED, dedicated paper account,
  equity $99,979.97, cash $99,815.97, one historical order, one long SPY260904C00768000,
  entry $1.84, broker value $164 and unrealized -$20. Competition equity delta -$20.03.
  These are recorded broker observations, not current execution quotes.
- No Alpaca mutation performed. Neither execution flag enabled. No credentials read or exposed.
- 96 offline simulated stress cases + one historical recorded snapshot replay:
  part2-replay.json. Inputs/behavior repeatable; no parameter tuning, fills or returns invented.
- Tie-break corrected from random proposal UUID to stable strategy name.
- Freshness uses quote timestamp, not retrieval time; closed-market observations stay advisory.
- Local validation: 139 backend tests pass; Ruff, Python compilation, frontend lint/typecheck,
  static UI safety assertions, Next production build, tracked/pending secret scan,
  paper-only/live-endpoint/capability audits and git whitespace checks pass.
  Existing Starlette/httpx test-client deprecation warning only.

## MIGRATION VERIFIED

- Migration 004 applied after explicit user confirmation. Exactly one new table
  phase2_cycle_lease and two functions phase2_acquire_lease / phase2_release_lease.
- RLS enabled. Anonymous actual SELECT and acquisition calls denied. Authenticated access
  denied by grants. Service role can SELECT and invoke RPCs, not mutate the table directly.
- database/checks/phase2_lease_verification.sql passed on production in a rolled-back
  transaction: acquire, same-owner idempotency, overlap denial, wrong-owner release denial,
  cooldown, simulated expired-lease recovery, stale-owner fencing and two-attempt cap.
- Test advances only the new singleton's timestamps transactionally; no historical records
  are deleted/modified. This is controlled expiry-state verification, not a real process crash.
- Local concurrent-worker and lost-acknowledgment tests passed; completed cycles are not repeated.

## CONFIGURED IN CODE / DEPLOYMENT PENDING

- Separate Phase 2 token checker, both-disabled defaults and startup enforcement.
- Advisory sell-to-close schema with owned-quantity checks; no executable route.
- Global bounded research lease and additive migration 004.
- Actual account/competition-P&L dashboard separated from counterfactual research.

## PENDING

- Non-secret AUTONOMOUS_TRADING_ENABLED=false and bounded batch label staged in Railway.
- Push/deploy, record new cycles/position quotes/shadow marks, verify browser/CORS/CI.
- No autonomous trading readiness claim: durable Phase 2 dispatcher, intent claims,
  broker reconciliation and an explicit order/exit authorization budget remain future work.
