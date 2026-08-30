# Platform Setup

## Alpaca

Use a new dedicated paper account for final judging with a $100,000 starting balance. Create paper-only API credentials at action time and store them only in Railway/local ignored configuration. Do not enable or use live brokerage credentials. Alpaca MCP/CLI access should be used for read-only account, market-data, position, and activity inspection until a later reviewed phase explicitly introduces paper-order execution.

## Supabase

Create a dedicated ThesisCircuit project. Apply `database/schema.sql`. Keep RLS enabled, create no public write policy, store the service-role key only on Railway, and expose at most the anon key to server-rendered frontend code when a concrete read policy exists.

## Railway

Deploy the repository with `backend/Dockerfile`. Configure health check `/health`. Add only paper Alpaca and server-side Supabase secrets. Set `TRADING_MODE=paper`, `EXECUTION_ENABLED=false`, `ALLOW_LIVE_TRADING=false`, `ALPACA_PAPER_TRADE=true`, `LIVE_TRADING_ALLOWED=false`, and `ORDER_SUBMISSION_ENABLED=false` as explicit environment values.

## Vercel

Import the GitHub repository with root directory `frontend`. Set only `NEXT_PUBLIC_API_BASE_URL` publicly. Do not place Alpaca keys, Supabase service-role keys, database URLs, or deployment tokens in `NEXT_PUBLIC_*` variables. Use Git integration for Phase 0 preview deployment from the feature PR.

## GitHub

Create a public MIT-licensed repository named `thesiscircuit`, protect `main` when available, and open a single Phase 0 PR from `feat/phase-0-foundation`. Never commit `.env`, `.vercel`, account IDs, or evidence containing secrets.
