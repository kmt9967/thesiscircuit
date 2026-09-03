# Alpaca Integration

## Official implementation

- Production core operations use the pinned official `alpaca-py==0.44.0` SDK.
- `TradingClient(paper=True)` handles account/clock/positions/orders/assets/contracts and the
  one possible paper order call. Official stock and option historical-data clients handle
  bars, latest quotes, option snapshots and Greeks.
- The application retains its own deterministic risk engine, immutable Supabase intent,
  atomic session budget, at-most-once dispatch and client-ID reconciliation because those
  controls must share one auditable application transaction protocol.
- Alpaca MCP/CLI are not used to execute ThesisCircuit orders. MCP may be configured later as
  read-only operator/agent tooling, but no compliance claim depends on it.
- SDK redirects and automatic retries are disabled. Every SDK request has an explicit bounded
  transport allowance and timeout; a submission failure becomes UNKNOWN until GET reconciliation.

- Trading base URL is hard-locked to `https://paper-api.alpaca.markets`.
- Market data base URL is hard-locked to `https://data.alpaca.markets`.
- The Basic indicative options feed is the default; OPRA may be selected server-side only when legitimately available.
- Account reads cover account, clock, positions, and open orders.
- Market reads cover assets, latest stock quotes, daily bars, option contracts, and option snapshots.
- The only possible write is one session-budgeted, single-leg, one-contract, buy-to-open DAY
  limit PAPER option order. No session is active by default.
- `client_order_id` is deterministic. A timeout triggers a lookup by that ID and never a blind second POST.
- Reconciliation uses order/account/position GET requests only. No automatic cancel, replace, exercise, or close path exists.
- Readiness is `POST /phase1/preflight/readiness` (the legacy `/phase1/preflight`
  aliases it). It requires execution disabled. Execution approval is
  `POST /phase1/preflight/execution?readiness_id=...`, with the server-only
  authorization header. Submission requires both readiness and execution receipt IDs.
- Only HTTP 404 means a client ID is absent; timeouts, authentication errors, and
  rate limits fail closed. The durable claim remains consumed even after ambiguity.
- A long call's premium loss bound does not cover a subsequently exercised stock
  position. Alpaca may automatically exercise ITM contracts at expiry. No exercise
  or closing instruction is sent by ThesisCircuit; expiry handling needs separate
  user direction before September 4. See official Alpaca options documentation.
- Production proof completed September 2: client ID
  `thesiscircuit-phase1-eeb2ef56-a111-59c2-815e-17bc75fdc270`, one DAY limit at $1.88,
  actual Alpaca fill at $1.84. The consumed submission claim must never be deleted
  or reset to rerun the proof. Only read-only broker reconciliation was used afterward.
