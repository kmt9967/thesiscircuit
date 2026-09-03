# ThesisCircuit

ThesisCircuit is a paper-only options research project for the Alpaca AI Trading Agents
Hackathon. Phase 1 proves a single controlled deterministic execution with an auditable
risk decision. Phase 2 Part 1 implements a deterministic three-agent research
committee with critic, risk vetoes, counterfactual tracking and position recommendations.
It is **DRY RUN ONLY**: no new opening or closing orders, no execution credential,
and the Phase 1 token's authorization mechanism is retired.

## Phase 2 research

See [Phase 2 architecture and risk policy](docs/PHASE-2-ARCHITECTURE.md).
Part 2 validation is described in [Phase 2 readiness](docs/PHASE-2.md) and
the [one-page Alpaca technical story](docs/ALPACA-TECH-STORY.md). Both execution gates
remain disabled. [Phase 2.5](docs/PHASE-2.5-ORDER-DISPATCH.md) adds an isolated durable
order dispatcher, immutable intent claims and restart reconciliation. Its production synthetic
verification is complete; no current research loop or frontend can activate broker execution.
[Phase 2.6 Part 1](docs/PHASE-2.6-COORDINATOR.md) adds a finite execution-session
coordinator and atomic session budgets. Its new Supabase migration and production
synthetic verification are pending separate approval; broker execution remains unavailable.
The Strategy Arena, Decision Council and Shadow Desk show recorded real-data
research, not fabricated performance. Finite operator-configured batches run three
cycles and stop. The existing SPY paper position remains untouched.

## Phase 1 controlled execution

Phase 1 adds a deliberately narrow proof path: real Alpaca market data → deterministic
long-call proposal → disabled-state readiness → fresh enabled-state execution approval
→ one-use submission claim → at most one Alpaca PAPER order → Supabase audit → live
dashboard. Both historical stages enforced 18 fail-closed gates. The order path required a
server-only authorization token, accepts SPY only, limits size to one contract and
maximum premium loss to $250, and never submits a closing order.

The official judging-account window begins August 31, 2026 at 9:30 a.m. ET. Before that timestamp, the hackathon-rules gate rejects execution even if every other configuration is valid.

## Safety contract

- Alpaca paper trading only; `https://paper-api.alpaca.markets` is the only accepted broker base URL.
- `ALLOW_LIVE_TRADING=false` and `LIVE_TRADING_ALLOWED=false` are mandatory.
- `EXECUTION_ENABLED=false` is the resting state before and after the one authorized proof.
- Options ideas are analysis artifacts, not investment advice.
- Paper results are hypothetical and do not guarantee future results.
- A fresh Alpaca paper account with a $100,000 starting balance is required for final judging; credentials are never committed.

See [PAPER-TRADING-DISCLOSURE.md](PAPER-TRADING-DISCLOSURE.md), [SECURITY.md](SECURITY.md), and [docs/HACKATHON-RULES.md](docs/HACKATHON-RULES.md).

## Local development

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m uvicorn backend.app.main:app --reload --port 8000
```

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Run checks from the repository root:

```powershell
python -m pytest
python scripts/safety_audit.py
python scripts/secret_scan.py
cd frontend
npm run lint
npm run build
```

## Repository map

- `frontend/` — Next.js judge-facing dashboard for safety, architecture, rules, and replay evidence.
- `backend/` — FastAPI read-only analysis API.
- `agents/` — committee roles and auditable votes.
- `strategies/` — options thesis generation without execution.
- `risk/` — deterministic fail-closed policy engine.
- `replay/` — reproducible decision-event replay.
- `database/` — Supabase-compatible schema.
- `docs/`, `evidence/`, `submission/` — rule provenance, verification, and submission material.

## Current phase

Phase 0 and the Phase 1 controlled execution proof are complete. On September 2,
one SPY Sep 4 $768 call was submitted with a $1.88 DAY limit and filled at $1.84.
The one-contract paper position remains open. Execution is disabled, the one-use
claim is consumed, and no further order or Phase 2 activity is authorized.
See [docs/PHASE-1-EXECUTION.md](docs/PHASE-1-EXECUTION.md) for the actual audit and limits.

