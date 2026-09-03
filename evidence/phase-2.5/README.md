# Phase 2.5 evidence

## VERIFIED locally

- 186 backend tests passed, including 47 durable-dispatch tests.
- Ruff, Python compilation, tracked/pending secret scan and paper/live-endpoint audit passed.
- Frontend lint/typecheck, static UI safety checks and production build passed.
- No Alpaca order call was made by this task. Broker outcome tests use httpx MockTransport.

## VERIFIED in production on 2026-09-03

- Approved migration 005 applied successfully: only `phase2_order_intents`, three lifecycle
  functions and supporting indexes created. No existing table/function or historical row changed.
- New table RLS enabled. Table ACL: postgres administrator; service_role SELECT only.
- Functions are SECURITY DEFINER with fixed `search_path=public,pg_temp`; EXECUTE ACL only
  postgres owner and service_role. No public/anon/authenticated access.
- Rollback-only production SQL checks passed: actual anonymous read/RPC denial, service-role
  create/claim/advance, immutable conflicts, competing claims, single submission transition,
  SUBMITTING recovery, stale-owner fencing, UNKNOWN no-resend and terminal replay.
- Historical database counts remained one order and six autonomous cycles.
- Batch `phase25-verification-20260903-a` completed. Exactly two SYNTHETIC records retained;
  no Alpaca client is available in this runner and broker_calls=0.
- Intent `67cba490-b055-5b75-9216-bbfb2a2709a6`: 8 events, simulated FILLED.
- Intent `1d4a99c3-619b-59e4-a4bc-ffa8abb83d38`: 9 events, simulated FILLED; claim recovered
  31.636 seconds after SUBMITTING, following actual 30-second expiry. This is an abandoned-worker
  simulation, not an actual process kill. Both real `alpaca_order_id` fields remain null.
- Both paths exercised UNKNOWN → read-only simulated reconciliation → terminal replay.
- [Initial production result](production-synthetic-initial.json) preserves labelled synthetic
  timestamps and audit events. Its fake quotes/fills are not market data or actual executions.
- At initial implementation commit df6580b, real PostgreSQL CI and an eight-session contention
  test passed with exactly one winner. Later CI also tests cross-intent exclusion/orphan recovery.

## Remaining verification for final commit

- Railway/Vercel deployment-restart replay check at the completed commit.
- Final CI and fresh read-only broker-order count/disabled flag verification.

## Activation boundary

The reliability protocol is implemented and disabled. Autonomous activation is NOT yet ready:
the production startup guard remains dry-run-only, and a bounded server coordinator/order budget,
authorization duration, opening/closing scope and current-market preflight require separate review.
No Phase 2 credential was created. Existing SPY remains untouched; no new order is authorized.
