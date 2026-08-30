# Architecture

## Decision circuit

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

`MarketDataService`, `AccountService`, and `OrderService` isolate Alpaca HTTP behavior. A deterministic proposal builder selects a premium-bounded SPY call from real option contracts and quotes. The execution risk engine owns 17 non-overridable gates. `POST /phase1/execute` is one-shot and idempotent by deterministic client order ID and Supabase trace; timeouts query Alpaca by client order ID and are never blindly retried. `POST /phase1/reconcile` reads the existing order and persists actual fill/position state without submitting another order.

The browser receives only `GET /phase1/dashboard`. Broker and database credentials remain in Railway.

## Trust boundaries

LLM/agent outputs are untrusted proposals. Only typed schemas enter the risk layer. The risk layer is deterministic and fail-closed. Alpaca credentials, Supabase service keys, and deployment tokens never cross into the browser bundle or logs.

