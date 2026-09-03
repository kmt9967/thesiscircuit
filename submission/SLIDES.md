# ThesisCircuit — 10-Slide Deck Content

## Slide 1 — ThesisCircuit

**AI strategies compete. Risk decides. Sometimes the best trade is no trade.**

Alpaca AI Trading Agents Hackathon · PAPER options only

Visual: production hero screenshot.

## Slide 2 — The problem

- Trading-agent demos often collapse research, persuasion, risk, and execution into one opaque step.
- A retry or restart can duplicate an order.
- “No trade” decisions disappear, making risk quality impossible to judge.
- Broker claims and displayed performance are difficult to audit.

## Slide 3 — The ThesisCircuit answer

- Independent Trend, Range, and Defensive agents
- Decision Council plus adversarial Critic
- Deterministic, non-overridable risk governor
- Durable intent and bounded execution coordinator
- Supabase evidence trail and live dashboard

## Slide 4 — Decision architecture

Visual: Alpaca data → Strategy Arena → Council → Critic → Risk → durable intent → bounded session → Alpaca PAPER, with all stages writing to Supabase.

Key message: generation and authorization are deliberately separated.

## Slide 5 — Risk owns the final vote

- Exact paper endpoint and live-flag rejection
- Freshness, tradability, liquidity, market-window checks
- Buying power and premium-bounded maximum loss
- Position/order conflicts and unique client references
- Expiring sessions and atomic budgets
- UNKNOWN states fail closed

## Slide 6 — One actual PAPER proof

- `SPY260904C00768000`
- Buy to open 1 long call
- DAY limit $1.88
- Alpaca fill: 1 at $1.84
- Planned maximum premium risk: $188
- Additional/closing orders: 0

Label prominently: **ACTUAL ALPACA PAPER RESULT**.

## Slide 7 — Reliability, not happy-path theater

- Intent persisted before broker contact
- Eight-worker claim race: exactly one winner
- Reconcile by `client_order_id` before retry
- Restart and stale-lock recovery
- Conservative budget accounting for uncertain broker state
- Terminal shutdown forces both execution flags false

## Slide 8 — NO TRADE is a product feature

- Critic objections remain visible
- Risk rejections are structured and replayable
- Shadow/counterfactual ideas are clearly separated from broker orders
- The dashboard never fabricates P&L or fills

Visual: Strategy Arena / Critic screenshot.

## Slide 9 — Verified production stack

- Alpaca PAPER + official `alpaca-py`
- FastAPI / Pydantic on Railway
- Supabase PostgreSQL with RLS and server-only functions
- Next.js / TypeScript on Vercel
- 256 backend tests plus frontend, security, and safety checks

Current posture: execution OFF, autonomy OFF, live trading prohibited.

## Slide 10 — The thesis

**Autonomy is credible only when refusal, recovery, and shutdown are as engineered as execution.**

- Public code: https://github.com/kmt9967/thesiscircuit
- Live demo: https://thesiscircuit.vercel.app/

Footer: SIMULATED PAPER TRADING — NO REAL FUNDS. Hypothetical results; not investment advice.
