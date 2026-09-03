# Phase 2.7 evidence

Evidence in this directory is sanitized and contains no credentials or full account identifiers.

- **VERIFIED locally:** official-SDK host/retry/timeout/submission-boundary tests; server-only
  activation binding; shutdown on normal and failed coordinator outcomes; Railway variable
  mutation scope/read-back; SPY/QQQ isolation and concentration behavior; full safety scans.
- **VERIFIED in production:** a three-cycle SPY/QQQ batch completed with both paths returning
  fail-closed `NO_TRADE`; the Railway project/environment scope passed; one false-only
  variable update was acknowledged and read back; both flags remained false; Alpaca and
  Supabase reads succeeded; historical broker orders remained one and new orders zero.
- **CONFIGURED:** the replacement Railway project token is restricted to the production
  environment and the Phase 2 authorization token is server-only. Values are never exposed
  here. The previously surfaced token was revoked before use.
- **PLANNED:** one later bounded PAPER session requires a separate explicit authorization and
  a fresh current-market preflight. This readiness fix does not authorize an order.

The production shutdown check is intentionally **SYNTHETIC**: exact token scope, both gates
false before and after one false-only mutation, no deploy restart, zero broker submissions,
and one idempotent sanitized Supabase event. Its result is never represented as activation
or execution evidence.

Sanitized machine-readable production observations are in
`2026-09-03-production-readiness.json`.
