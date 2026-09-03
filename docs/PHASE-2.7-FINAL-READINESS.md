# Phase 2.7 final autonomous-readiness fix

Status: implementation and disabled production verification complete.

## Integration

Core Alpaca operations now use the pinned official `alpaca-py==0.44.0` SDK. The adapter
hard-locks paper/data hosts, `paper=True`, raw response mode, no redirects, ten-second
timeouts, zero SDK retries and a bounded request allowance. Application-owned Pydantic
parsing, deterministic risk, immutable intents, atomic budget fencing and client-ID
reconciliation remain around the SDK. This is the engineering reason for choosing the
official SDK instead of routing the critical transaction boundary through MCP. Alpaca MCP
is not claimed as the execution mechanism.

## Server-only activation and shutdown

There is no Phase 2 POST route, frontend switch, cron trader or indefinite runner. Startup
requires all of the following encrypted Railway configuration to agree with one immutable
Supabase PAPER session: the distinct Phase 2 token, both execution flags, session UUID,
exact start/expiry, one-order maximum and manual-kill state. The Railway shutdown credential
is a project token scoped to the single production environment.

The supervisor removes both in-process authorities first, then updates only
`EXECUTION_ENABLED=false` and `AUTONOMOUS_TRADING_ENABLED=false` with `replace=false`, and
reads the variables back. Completion, expiry, exhausted order budget, any kill condition,
competition closure, UNKNOWN broker state, dispatcher failure and process cancellation all
enter this `finally` path. Supabase records both the session terminal event and a sanitized
`phase2_execution_shutdown` event. Durable session expiry is the restart/crash backstop.

Production control-plane verification is a separate broker-free synthetic startup job. It
requires both flags already false, verifies the project-token scope, performs only a
false-to-false update with deploys skipped, reads both values back, and stores one idempotent
`phase2_synthetic_shutdown_verified` event. It cannot create a session or construct a broker
client, and its read-only status is exposed at `/phase2/shutdown-verification`.

Production verification batch `phase27-shutdown-20260903-a` completed with the replacement
project token scoped to the ThesisCircuit `production` environment. Scope validation passed,
the false-only update was acknowledged and read back, both gates remained false, and broker
submission calls were zero. The originally surfaced token was revoked before use; exactly one
replacement remains, and both it and the independent Phase 2 authorization token are stored
only as masked Railway service variables.

## Multi-underlying safety

The validated engineering universe is SPY and QQQ. Each refresh has a required underlying
identity; stock features, option contracts and quotes are independently fetched and bound.
Each agent/critic/allocator/risk pipeline runs independently before a deterministic
cross-underlying comparison. A selected intent must retain the same underlying through its
proposal, contract, immutable intent, session scope and final fresh dispatcher read.

The existing SPY long call continues to trigger the same-underlying concentration veto.
QQQ support does not force an order: unavailable/stale data, weak signal, poor liquidity,
budget failure or any other gate yields NO_TRADE.

Fresh production batch `phase27-final-readiness-20260903-b` completed three finite cycles.
Every cycle evaluated SPY and QQQ independently. Because the U.S. market was closed and the
available data was stale, both paths returned `NO_TRADE / UNCERTAIN`; no submission path ran.

## Resting production state

- `TRADING_MODE=paper`
- `ALPACA_PAPER_TRADE=true`
- `ALLOW_LIVE_TRADING=false`
- `EXECUTION_ENABLED=false`
- `AUTONOMOUS_TRADING_ENABLED=false`
- Existing `SPY260904C00768000`: monitor only; no exit authority
- Broker submissions during this readiness fix: zero

The official scoring interval ends at `2026-09-04T13:30:00Z`. After the September 3
market close there is no later U.S. options-market-open interval inside that scoring
window: the next regular open coincides with the published end. Technical readiness does
not override that time gate.

SIMULATED PAPER TRADING — NO REAL FUNDS. Results are hypothetical and are not investment advice.
