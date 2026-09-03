# Evidence Index

- `phase-2/README.md` — VERIFIED three real-data dry runs, NO_TRADE, shadow and
  production dashboard; CONFIGURED paper boundaries; separated unmeasured outcomes.
- `phase-2/recorded-production-dry-runs.json` — sanitized actual persisted Phase2 state.

- `PHASE-0-CHECKLIST.md` — Phase 0 controls and deployment proof.
- `phase-1/` — sanitized Phase 1 execution-chain evidence.
- `phase-1/2026-09-02-two-stage-readiness.json` — VERIFIED fresh production readiness,
  all 18 gates passed with execution disabled; not an executed trade.
- `phase-1/2026-09-02-verification.md` — deployed checks, limitations, and pending actions.
- `phase-1/2026-09-02-completed-execution.json` — VERIFIED actual one-order execution,
  fill, position snapshot, audit, and disabled-state result; supersedes the pending status.
- `phase-1/2026-09-02-completion-report.md` — final validation and remaining boundaries.

Classifications: VERIFIED means observed directly; CONFIGURED means a setting was confirmed; PLANNED means blocked by the official trading window or another explicit prerequisite.
# Phase 2.5

See [durable order dispatch verification](phase-2.5/README.md). Synthetic protocol records are
not actual Alpaca orders. Production migration, access controls and synthetic lifecycle results are recorded there.

## Phase 2.6 Part 1

See [bounded coordinator verification](phase-2.6/README.md). Approved session schema
and production synthetic cases are verified; no autonomous execution is enabled.

## Phase 2.6 Part 2

- `phase-2.6/2026-09-03-preauthorization-research.json`: VERIFIED three fresh-market
  production research cycles, NO_TRADE, unchanged SPY position and one historical
  order. Latest cycle details and all three completion IDs are retained.
- `../docs/PHASE-2.6-PREAUTHORIZATION.md`: PLANNED finite authorization proposal,
  preflight design and activation/compliance blockers. Not an active PAPER session
  or broker-execution proof.
