# Phase 2.6 Part 1 evidence

VERIFIED locally: 234 backend tests (48 new session tests), Ruff, Python compilation,
frontend lint/typecheck, static safety tests and production build; tracked/pending secret
and paper/live-endpoint capability scans pass. Four full synthetic fixture cases pass,
including terminal restart idempotency and rejection of falsely successful restarts.

VERIFIED PostgreSQL 16 CI: [run 33707959893](https://github.com/kmt9967/thesiscircuit/actions/runs/33707959893)
passed migration 006, RLS/RPC ACL checks, eight independent workers racing for the final
session budget (one winner), durable spend/restart, UNKNOWN kill, reconciliation,
independent opening/closing/total caps, detached-cycle rejection, cadence and expiry.
This was a disposable CI database, not a production migration.

VERIFIED production: [disabled-state snapshot](2026-09-03-disabled-production.json)
at code commit 85ef75f. Railway health OK, Alpaca PAPER and Supabase connected;
historical orders one, open orders zero, existing long SPY one unchanged. Vercel
production READY / HTTP 200; runtime error query returned no entries. Actual market
was closed and the existing option quote stale, correctly advisory-only.

CONFIGURED: execution and autonomous trading disabled; paper only; existing SPY
monitoring allowed, exits disabled; production synthetic batch defaults empty.

PLANNED / APPROVAL PENDING: Supabase migration 006, production RLS verification,
and production synthetic session batch. No actual PAPER execution is authorized.
Synthetic fixtures are not actual Alpaca prices, fills, or performance.
