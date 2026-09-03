# Phase 2.7 evidence

Evidence in this directory is sanitized and contains no credentials or full account identifiers.

- **VERIFIED locally:** official-SDK host/retry/timeout/submission-boundary tests; server-only
  activation binding; shutdown on normal and failed coordinator outcomes; Railway variable
  mutation scope/read-back; SPY/QQQ isolation and concentration behavior; full safety scans.
- **CONFIGURED:** production must rest with both execution flags false. A single-environment
  Railway project token is required for the shutdown controller and is never exposed here.
- **PLANNED:** one later bounded PAPER session requires a separate explicit authorization and
  a fresh current-market preflight. This readiness fix does not authorize an order.

The production shutdown check is intentionally **SYNTHETIC**: exact token scope, both gates
false before and after one false-only mutation, no deploy restart, zero broker submissions,
and one idempotent sanitized Supabase event. Its result is never represented as activation
or execution evidence.

Production dry-run observations are added only after deployment and read-only verification.
