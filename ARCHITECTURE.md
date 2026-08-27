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

## Trust boundaries

LLM/agent outputs are untrusted proposals. Only typed schemas enter the risk layer. The risk layer is deterministic and fail-closed. Alpaca credentials, Supabase service keys, and deployment tokens never cross into the browser bundle or logs.

