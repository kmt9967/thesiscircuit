# Autonomous execution boundary

Production rests research-only with `EXECUTION_ENABLED=false` and
`AUTONOMOUS_TRADING_ENABLED=false`. Phase 1 authorization is retired. There is no Phase 2
execution HTTP route, frontend toggle, or cron trader. A server-startup-only launcher can
activate exactly one pre-approved immutable session only when both encrypted flags, the
Phase 2 token, UUID, start/expiry and order budget all agree.

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
remain separate from Phase 2.5's durable per-order claim and at-most-once submission boundary.

Phase 2.5 implements durable intents, deterministic client IDs, unknown-submission reconciliation,
fresh final broker/risk reads and overlap exclusion. It never reuses Phase 1's spent claim.
See [the dispatch protocol](PHASE-2.5-ORDER-DISPATCH.md). Activation additionally requires a
Railway project token scoped to the single production environment. Terminal completion, expiry,
budget exhaustion, kill, unknown broker state, competition closure or dispatcher failure removes
local authority first, writes both Railway flags to false without replacing other variables, and
reads them back. Durable Supabase terminal events provide the crash/restart backstop. Merely
setting flags remains insufficient.

SPY and QQQ are evaluated as separate market states. Quotes/features/contracts never cross
underlyings. The existing SPY position still vetoes another SPY directional thesis; QQQ may be
selected only if its own current data, agents, liquidity and risk gates approve it. NO_TRADE is
always valid and is never overridden to consume a session budget.

Recommended initial validation limits: retain all hard ceilings, additionally constrain an
authorized trial to one opening order, <=$250 premium, then shut down for review. This is an
engineering test limit, not a recommendation to trade. Existing SPY is advisory-only; automatic
management or closing requires separate authority and a tested reduce-only dispatcher.
