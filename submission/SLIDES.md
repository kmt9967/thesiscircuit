# ThesisCircuit — Final 10-Slide Deck

Use the final dark production screenshots in `evidence/final-ui/`. Keep the PAPER/no-real-
funds disclosure visible on every slide that presents broker values.

## Slide 1 — ThesisCircuit

**AI strategies compete. Risk decides. Sometimes the best trade is no trade.**

Alpaca AI Trading Agents Hackathon · PAPER options only

Visual: `evidence/final-ui/00-lablab-cover.png`

## Slide 2 — The problem

- Trading-agent demos often collapse research, persuasion, risk, and execution.
- Retries and restarts can duplicate orders.
- Rejections disappear, so risk quality cannot be evaluated.
- Broker and performance claims are difficult to audit.

## Slide 3 — The solution

- Independent Trend, Range, and Defensive agents
- Decision Council and adversarial Critic
- Deterministic, non-overridable Risk Officer
- Durable intent and bounded execution coordinator
- Supabase evidence trail and production dashboard

Visual: `evidence/final-ui/02-strategy-arena.png`

## Slide 4 — Architecture

Alpaca data → Strategy Arena → Council → Critic → Risk → durable intent → bounded
session → Alpaca PAPER, with decision and execution evidence persisted in Supabase.

Key message: generation, authorization, and broker dispatch are separate boundaries.

Visual: `evidence/final-ui/08-reliability.png`

## Slide 5 — Strategy Arena

- Same timestamped market state, three independent theses
- Typed confidence, rationale, risk budget, and objections
- Capital remains in cash when no candidate qualifies
- Scores are evidence-weighted and sparse-data-aware

Visual: `evidence/final-ui/02-strategy-arena.png`

## Slide 6 — Decision Council and Risk

- Critic challenges momentum extrapolation and concentration
- MetaAllocator may select a thesis or preserve cash
- Risk verifies PAPER endpoint, freshness, liquidity, buying power, bounded loss,
  conflicts, duplicates, cooldown, and drawdown
- Unknown or failed checks block dispatch

Visuals: `evidence/final-ui/03-decision-council.png` and
`evidence/final-ui/06-risk-engine.png`

## Slide 7 — One actual Alpaca PAPER execution

- `SPY260904C00768000` — SPY Sep 4, 2026 $768 call
- Buy to open 1 contract
- DAY limit $1.88
- Alpaca PAPER fill: 1 at $1.84
- Planned maximum premium risk: $188
- Additional or closing orders: 0

Label: **ACTUAL ALPACA PAPER RESULT — SIMULATED FUNDS**

Visual: `evidence/final-ui/05-original-paper-trade.png`

## Slide 8 — Shadow trades and decision regret

- Rejected ideas remain measurable evidence
- Later bid marks are counterfactual, never broker executions
- No fill, fee, slippage, or executable-return claim is invented
- NO TRADE quality can improve over time

Visual: `evidence/final-ui/07-shadow-desk.png`

## Slide 9 — Reliability as a product feature

- Cycle lease and stale-lock recovery
- Persist-before-dispatch durable intent
- Eight-worker claim/budget races: exactly one winner
- Reconciliation by `client_order_id` before retry
- Conservative UNKNOWN-state budget accounting
- Expiring bounded sessions and terminal shutdown

Visual: `evidence/final-ui/08-reliability.png`

## Slide 10 — Results and thesis

**Autonomy is credible only when refusal, recovery, and shutdown are as engineered as
execution.**

- One verified PAPER opening order; zero additional/closing orders
- Auditable NO TRADE decisions and shadow research
- 256 backend tests plus frontend, SQL protocol, security, and paper-safety checks
- Execution OFF · autonomy OFF · live trading prohibited
- GitHub: https://github.com/kmt9967/thesiscircuit
- Live demo: https://thesiscircuit.vercel.app/

Footer: SIMULATED PAPER TRADING — NO REAL FUNDS. Hypothetical results; not investment
advice.
