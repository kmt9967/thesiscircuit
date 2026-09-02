# Autonomous execution boundary

Current production is research-only. Both EXECUTION_ENABLED and AUTONOMOUS_TRADING_ENABLED
must remain false. Startup refuses either enabled flag. Phase 1 authorization is retired.
There is no Phase 2 execution HTTP route, order adapter, frontend toggle, or cron trader.

`phase2/authorization.py` implements a pure, separately tested future authorization check:
paper mode, exact paper host, both live flags off, both execution gates on, a distinct
server-only PHASE2_EXECUTION_TOKEN (minimum 32 characters), and a freshly recomputed complete
risk decision. Phase 1 tokens are never accepted. Tokens are compared in constant time and
are never returned, logged, sent to Vercel, or stored in audit tables. No Phase 2 credential
has been provisioned by this change. An APPROVED pure preflight still has
`execution_authorized=false`: it is NOT a dispatch capability.

Research cadence is 60 seconds by default, configurable 60–3600 seconds. Each explicitly
configured server batch has at most three cycles. A global Supabase lease excludes competing
workers/deployments. Each cycle has a 180-second lease and 150-second work timeout.
Owner and expiry are rechecked under a row lock when atomically committing the cycle audit.
An expired worker cannot complete or release a successor's lease. Failure stops the batch;
a later explicit rerun checks durable completion first. SQL caps attempts at two per cycle.
Lease release preserves a 60-second cooldown. START/COMPLETED/FAILED/ABANDONED events are
stored in the new lock table, with no provider exception bodies or credentials.
Stable batch/sequence IDs and transactional inserts prevent duplicate decisions. These controls
do not claim broker idempotency: Phase 2 currently cannot submit any broker request.

Before autonomous execution could be authorized, a separately reviewed dispatcher must add a
durable per-intent claim and unique client ID, unknown-submission reconciliation before any retry,
fresh final broker/risk reads, no overlapping dispatch, and explicit opening/closing scope.
It must never reuse Phase 1's spent claim. Continuous scheduling and restart reconciliation also
need a bounded authorization duration and total order budget. Merely setting flags is insufficient.

Recommended initial validation limits: retain all hard ceilings, additionally constrain an
authorized trial to one opening order, <=$250 premium, then shut down for review. This is an
engineering test limit, not a recommendation to trade. Existing SPY is advisory-only; automatic
management or closing requires separate authority and a tested reduce-only dispatcher.
