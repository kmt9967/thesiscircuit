# ThesisCircuit

ThesisCircuit is a paper-only autonomous options research system for the Alpaca AI Trading Agents Hackathon. A committee of research agents produces a trade thesis, a deterministic risk governor can veto it, and the full decision can be replayed for judges. Phase 0 deliberately contains **no order-placement path** and places **zero trades**.

## Safety contract

- Alpaca paper trading only; `https://paper-api.alpaca.markets` is the only accepted broker base URL.
- `LIVE_TRADING_ALLOWED=false` and `ORDER_SUBMISSION_ENABLED=false` are mandatory.
- Options ideas are analysis artifacts, not investment advice.
- Paper results are hypothetical and do not guarantee future results.
- A fresh Alpaca paper account with a $100,000 starting balance is required for final judging; credentials are never committed.

See [PAPER-TRADING-DISCLOSURE.md](PAPER-TRADING-DISCLOSURE.md), [SECURITY.md](SECURITY.md), and [docs/OFFICIAL-RULES.md](docs/OFFICIAL-RULES.md).

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

Phase 0 establishes repository isolation, official-rule provenance, paper-only controls, cloud-ready configuration, tests, and a reviewable PR. Trading remains disabled.

