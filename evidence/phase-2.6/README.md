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

## Approved production migration and synthetic verification

VERIFIED: migration 006 applied exactly as reviewed after explicit user approval.
One table, three functions, primary-key and two supporting indexes; no existing
table/function/policy rewritten. RLS enabled. Production ACL test passed actual
anonymous SELECT and RPC denial; anon/authenticated have no table/function access.
Only postgres administrator and service_role have function EXECUTE. Service role
has table SELECT only, and must use the fenced RPCs for mutations. All functions
are SECURITY DEFINER with fixed `search_path=public, pg_temp`.

VERIFIED: [initial production synthetic output](2026-09-03-production-synthetic-initial.json)
for `phase26-part1-20260903-a` on code e6e1deb. Four coordinator scenarios and three
budget protocol scenarios completed. Eight independent HTTP RPC contenders produced
exactly one opening-budget winner and seven denials. Default exit scope rejected the
closing fixture. Separate synthetic closing/total budget caps also passed. Expired
session rejected reservation. UNKNOWN recovery retained attempt count one and budget
consumed one. Every broker-submission counter is zero.

VERIFIED database totals after run: historical orders one; historical research cycles
six (unchanged); synthetic sessions seven; PAPER execution sessions zero. All actual
SPY position/execution controls remain unchanged. Production restart replay verification
will be recorded separately after the evidence deployment.

No actual PAPER execution is authorized. Synthetic fixtures, including artificial fills,
are not actual Alpaca prices, orders or performance. The earlier disabled-production
snapshot intentionally preserves the pre-approval state and is superseded by these results.
