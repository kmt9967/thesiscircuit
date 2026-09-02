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

## PRODUCTION VERIFIED

- Separate Phase 2 token checker, both-disabled defaults and startup enforcement.
- Advisory sell-to-close schema with owned-quantity checks; no executable route.
- Global bounded research lease and additive migration 004.
- Actual account/competition-P&L dashboard separated from counterfactual research.

- Implementation commit a5b2208 deployed to Railway (86dd4770-1c97-4e7c-95d7-af3439a8dbdb)
  and Vercel production (5Mctei4bKPB8PGyXnFBgGbJWu3w3), both successful.
- New bounded batch phase2-part2-20260902-b completed three cycles at ~22:12–22:14 UTC:
  669d6cbb-879e-5e1c-872d-227e7d4db5fd,
  f0aab695-967f-5a7a-a3e4-78ea4f00d49b,
  413058ac-0457-5a87-aab6-f78980c46cd1.
  All NO_TRADE; nine agent abstentions; market closed and data stale. Six lifecycle
  events (START/COMPLETED per cycle), each first attempt, lock released. No overlapping work.
- Paper account equity 99979.97; competition equity delta -20.03; cash 99815.97;
  one historical order, one original SPY long call, entry 1.84, broker value164 / unrealized-20.
- Last legitimate indicative quote September2 19:59:59UTC: bid1.66/ask1.68,
  delta.345, gamma.0507, theta-.6958, vega.2086. Explicitly stale, not trade eligible.
  Advisory RISK_ALERT, regime compatibility unassessed, no closing action.
- One unique existing RANGE shadow now marked: ask3.06 → later bid3.07 at19:59:59UTC,
  elapsed162.6minutes, hypothetical+1.00. Repeated cycle marks count as one scoring sample;
  RANGE score50.24; no attribution to actual Alpaca P&L. No new shadow entries while closed.
- Production UI inspected: actual equity/P&L, stale quote and Greeks, disabled gates,
  counterfactual shadow gain and score visible. HTTP200 and CORS allow the Vercel origin.
  No new browser console errors/warnings during post-deployment verification. Two older
  extension-message-channel errors at20:59UTC predate this deployment and are not app failures.
- Backend/frontend CI passed on the implementation commit. Sanitized full evidence is in
  part2-production.json. No credential was read, generated, changed, or exposed.

## REMAINING AUTONOMOUS-ORDER LIMITATIONS

- EXECUTION_ENABLED=false and AUTONOMOUS_TRADING_ENABLED=false verified in production.
- No autonomous trading readiness claim: durable Phase 2 dispatcher, intent claims,
  broker reconciliation and an explicit order/exit authorization budget remain future work.
