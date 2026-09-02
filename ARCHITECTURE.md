# Architecture

## Planned multi-agent decision circuit (not activated)

1. Market/research inputs become an immutable `ThesisRequest`.
2. Independent analyst agents produce structured votes with confidence and evidence labels.
3. The strategy layer proposes an options thesis, never a broker order.
4. The deterministic risk governor evaluates paper-mode, loss bounds, liquidity, concentration, expiration, and data freshness.
5. Any failed gate vetoes the thesis. No model can override a veto.
6. The replay engine records each event so a judge can reproduce the decision path.

## Deployment boundaries

- **Vercel:** `frontend/`; public judge UI. It receives only the public backend URL.
- **Railway:** FastAPI backend. Broker and database secrets remain server-side.
- **Supabase:** append-oriented run, vote, risk-decision, and replay evidence tables with RLS enabled.
- **Alpaca:** paper account only. Phase 0 has no order submission client.

## Phase 1 execution boundary

`MarketDataService`, `AccountService`, and `OrderService` isolate Alpaca HTTP behavior.
TwoStagePreflight stores disabled-state readiness and fresh enabled-state execution
receipts in Supabase. Both use the same 18 non-overridable gates. A third fresh check
precedes a unique immutable submission claim; only the claim winner can write an order.
The claim survives restart, and ambiguity never permits a retry. Reconciliation can
recover an actual broker order by client ID if post-submit audit persistence failed.
The process-local gate closes immediately after the broker response/timeout; the
durable claim disables effective execution across replicas. Railway's environment
switch must also be explicitly restored to false.

The browser receives only `GET /phase1/dashboard`. Broker and database credentials remain in Railway.

The September 2 production proof traversed this boundary exactly once: one DAY-limit
SPY call order filled at Alpaca, then its actual order/fill/position reached Supabase
and the Vercel UI. Both execution flags are now false and the persistent claim is
consumed. Account reads and stored position snapshots have distinct timestamps.

## Trust boundaries

LLM/agent outputs are untrusted proposals. Only typed schemas enter the risk layer. The risk layer is deterministic and fail-closed. Alpaca credentials, Supabase service keys, and deployment tokens never cross into the browser bundle or logs.

