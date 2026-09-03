# ThesisCircuit — AI Logic, Risk Gates, and Alpaca Infrastructure

ThesisCircuit is an autonomous options research and paper-execution system where multiple strategies compete, a critic attacks the winning thesis, and deterministic risk controls have the final vote. Its premise is simple: a credible trading agent must explain not only why it traded, but why it refused to trade—and must remain safe through retries, restarts, and uncertain broker responses.

## AI logic

Each cycle begins with current Alpaca market, account, underlying, and options data. Three independent deterministic agents examine the same snapshot from different viewpoints: Trend seeks directional continuation, Range looks for mean reversion, and Defensive prefers capital preservation when evidence is weak. Each emits a typed thesis with rationale, confidence, data timestamps, invalidation conditions, and bounded-loss estimates. A decision council compares them, while a critic searches for stale evidence, disagreement, liquidity problems, and hidden assumptions. Shadow and counterfactual records preserve ideas that were not executed without presenting them as real trades.

The architecture intentionally keeps persuasive language separate from authority. Agent consensus may create a proposal, but it cannot authorize an order. This makes NO TRADE a valid and fully observable outcome.

## Deterministic risk gates

The governor fails closed unless configuration is paper-only, the Alpaca account is active, the official competition window and market state are valid, data is fresh, the instrument is tradable and liquid, buying power is sufficient, maximum premium loss is bounded, no position/order conflict exists, and the client order reference is unique. Live endpoints, live flags, stale quotes, unknown broker state, expired sessions, exhausted budgets, or missing approvals are vetoes that no agent can override.

Durable Supabase locks allow only one active cycle. Order intents are persisted before broker contact and atomically claimed by one worker. A timeout triggers reconciliation by `client_order_id`, never a blind retry. Bounded execution sessions expire automatically, enforce separate opening/closing/total budgets, conservatively consume budget for UNKNOWN states, and force both execution flags off at terminal outcomes.

## Alpaca infrastructure and actual proof

ThesisCircuit uses the official `alpaca-py` SDK against `https://paper-api.alpaca.markets` only. Typed application services wrap Alpaca account, clock, option-contract, quote, order, fill, and position responses. The official FAQ permits an official SDK with an explanation; `alpaca-py` was chosen so broker access remains typed while transaction ownership, idempotency, audit, and policy stay inside ThesisCircuit.

On September 2, 2026, the system completed one controlled end-to-end proof in the dedicated $100,000 PAPER account. Current data produced a one-contract SPY Sep 4 $768 long-call proposal. Eighteen readiness and execution gates approved a DAY limit order at $1.88 with $188 planned maximum premium risk. Alpaca filled the single contract at $1.84. The proposal, risk decision, order lifecycle, fill, position snapshot, and shared trace were persisted to Supabase and displayed by the production dashboard. No second or closing order was submitted.

At the final September 3 22:47 UTC observation, Alpaca reported $100,397.94 equity, $99,815.94 cash, one position, zero open orders, and one historical order. This is an actual Alpaca PAPER observation—not fabricated P&L and not a guarantee of the competition’s final measurement.

## Current production posture

The Next.js dashboard presents the Strategy Arena, Decision Council, Critic objections, risk results, actual paper-account state, and audit trail. Railway hosts the FastAPI control plane; Supabase stores RLS-protected evidence and coordination state. Production currently has execution and autonomous trading disabled. Bounded autonomous activation/shutdown has been verified synthetically with zero broker calls, but autonomous broker execution was not activated.

**SIMULATED PAPER TRADING — NO REAL FUNDS.** Results are hypothetical and are not investment advice. Options carry significant risk, and all investments involve risk.
