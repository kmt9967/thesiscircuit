# Lablab Submission Fields

Prepared for the official Lablab submission form. Do not commit a full Alpaca account identifier; enter it only in the private submission field.

## Project title

ThesisCircuit

## Tagline

AI strategies compete. Risk decides. Sometimes the best trade is no trade.

## Short description

ThesisCircuit is an auditable autonomous options system where competing strategy agents, a critic, and deterministic risk controls turn live Alpaca data into bounded PAPER decisions—including a verified real fill and defensible no-trade outcomes.

## Long description

ThesisCircuit asks a different question from most trading agents: not “Can an AI generate a trade?” but “Can it produce a decision that remains safe, explainable, and idempotent under real operating conditions?”

Three deterministic agents—Trend, Range, and Defensive—independently analyze current Alpaca market and options data. A Decision Council compares their typed theses, a Critic challenges stale evidence and hidden assumptions, and a deterministic risk governor has the final vote. Agent language can never override a rejection. NO TRADE, shadow ideas, and counterfactuals are preserved as first-class evidence without being shown as real broker activity.

ThesisCircuit uses Alpaca’s official `alpaca-py` SDK and PAPER endpoint only. Supabase provides an RLS-protected audit trail, durable cycle locks, atomic order-intent claims, restart recovery, and bounded execution-session budgets. Railway hosts the FastAPI control plane, while the Vercel dashboard exposes account state, agent debate, risk decisions, the actual paper order lifecycle, and clear disclosures.

The system proved its complete path with exactly one authorized opening order: one SPY Sep 4 $768 long call, submitted as a DAY limit at $1.88 and filled by Alpaca PAPER at $1.84. The planned maximum premium risk was $188. The proposal, 18-gate risk decision, fill, resulting position, and trace were persisted and rendered in production. No additional or closing order was placed.

Production now rests fail-closed with execution and autonomous trading disabled. Bounded activation, shutdown, lock recovery, duplicate prevention, and eight-worker race behavior were verified synthetically with zero additional broker calls.

SIMULATED PAPER TRADING — NO REAL FUNDS. Results are hypothetical and are not investment advice. Options carry significant risk, and all investments involve risk.

## Suggested categories and tags

- AI Agents
- FinTech
- Developer Tools
- Risk Management
- Options Trading

## Technologies

- Alpaca Trading API and official `alpaca-py` SDK
- Python, FastAPI, Pydantic, pytest, Ruff
- Supabase / PostgreSQL / Row Level Security
- Next.js, React, TypeScript
- Railway and Vercel
- GitHub Actions

## Links

- Public GitHub: https://github.com/kmt9967/thesiscircuit
- Live demo: https://thesiscircuit.vercel.app/
- Production API: https://thesiscircuit-production.up.railway.app/
- Video: `[ADD PUBLIC DEMO VIDEO URL]`
- Slides: `[ADD PUBLIC SLIDE-DECK URL]`

## Private form values

- Alpaca PAPER account ID: `[ENTER DEDICATED JUDGING ACCOUNT ID IN LABLAB ONLY]`

## Media

- Cover: `evidence/final-ui/00-lablab-cover.png`
- Hero/account: `evidence/final-ui/01-hero-account.png`
- Strategy Arena: `evidence/final-ui/02-strategy-arena.png`
- Decision Council: `evidence/final-ui/03-decision-council.png`
- Position Watch: `evidence/final-ui/04-position-watch.png`
- Verified PAPER trade: `evidence/final-ui/05-original-paper-trade.png`
- Risk Engine: `evidence/final-ui/06-risk-engine.png`
- Shadow Desk: `evidence/final-ui/07-shadow-desk.png`
- Reliability: `evidence/final-ui/08-reliability.png`
- Mobile dashboard/navigation: `evidence/final-ui/09-mobile-dashboard.png` and
  `evidence/final-ui/10-mobile-drawer.png`
