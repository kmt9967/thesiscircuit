# Phase 2.5 — durable paper broker dispatch

## Scope and current authorization

No Alpaca order is authorized by this change. OPEN and CLOSE are server-library paths,
not HTTP routes, frontend controls, scheduled work, or automatic position management.
Production startup still requires EXECUTION_ENABLED=false and AUTONOMOUS_TRADING_ENABLED=false.
Phase 1 remains retired. No new credentials are needed for synthetic verification.

## Immutable intent and atomic claim

Migration 005 adds only `phase2_order_intents` and three SECURITY DEFINER functions:
`phase2_create_order_intent`, `phase2_claim_order_intent`, `phase2_advance_order_intent`.
RLS is enabled; public/anon/authenticated have no access. The server role has SELECT and
RPC EXECUTE, but no direct INSERT/UPDATE/DELETE. PostgreSQL owner retains administrative access.
Existing schema, audit records and cycle-lock functions are unchanged.

The JSON document binds cycle, proposal, risk approval, action, contract, quantity, DAY limit,
maximum premium risk, paper classification and timestamps. Proposal/action UUID5 yields a
stable intent ID and `tc-p2-<uuid>` client ID, independent of worker or cycle retry.
A conflicting payload cannot overwrite an existing intent. Risk-decision IDs identify the
immutable risk snapshot in this document; they are not invented foreign keys to historical rows.

OrderIntentService selects the allocator's single proposal and approved risk from a validated
cycle. PaperOrderDispatcher performs persistence, claim, fresh reads and independent final risk
checks. OrderClaimService uses atomic SQL RPCs; OrderReconciliationService does read-only lookup.
PositionManager remains advisory; CLOSE requires a fresh owned long-position, reduce-only check.

SQL serializes claim mutations, enforces one active PAPER intent account-wide, and rechecks the
original cycle owner/expiry before SUBMITTING. Claims last 30 seconds. A never-sent orphan can
expire without permanently blocking dispatch. Lost cycle ownership prevents broker submission.
The final approval must be <=2 seconds old; original intent/risk must be <=120 seconds old.
The cycle needs >=15 seconds remaining for the bounded broker request. No redirect/retry transport
is configured. A final local clock/authorization check precedes the sole HTTP POST.

## State and uncertainty

PENDING → CLAIMED → SUBMITTING → SUBMITTED/RECONCILING → FILLED/CANCELED/REJECTED/EXPIRED/UNKNOWN.
Actual broker status (including partial fill), fill quantity/price/time and matched broker ID
are stored separately from the local state. Claim/final-preflight/broker/reconciliation events
are retained in the row's audit timeline. Only allowlisted broker fields and error codes persist.

SUBMITTING increments attempt_count from zero to one atomically and can never be entered again.
A lost database acknowledgment results in no POST. Once consumed, every restart is lookup-only.
Timeout, malformed response or unknown HTTP result triggers client-ID lookup, never a resend.
Even a subsequent 404 is inconclusive: UNKNOWN retains the account-wide barrier until resolved.
Automatic retry after SUBMITTING is deliberately unsupported, even if an operator suspects absence.
Alpaca explicitly warns that a timed-out request may already have executed:
[official order-handling guidance](https://docs.alpaca.markets/us/docs/working-with-orders).
Lookup uses [Alpaca's client-ID endpoint](https://docs.alpaca.markets/us/reference/getorderbyclientorderid).

Invariant: one immutable logical intent makes at most one POST attempt. This sacrifices liveness
after uncertain pre-send failure; it does not promise exactly-once execution or guaranteed fills.
The broker cannot participate in the database transaction. Process suspension/network uncertainty
cannot be eliminated; the irreversible transition and deterministic client ID prevent resubmission.

## Synthetic verification

`PHASE25_SYNTHETIC_BATCH` is an optional server-only, bounded verification batch. It has no Alpaca
client/import and cannot issue a broker call. It exercises two labelled SYNTHETIC records:
normal completion and an abandoned SUBMITTING claim recovered after real 30-second expiry.
It tests duplicate persistence/competing claims/UNKNOWN reconciliation/terminal replay. Simulated
quotes and fills are explicitly synthetic, stored only in the new table; `alpaca_order_id` stays
null and historical orders/fills/positions tables are untouched.

The read-only `/phase2/order-dispatch-verification` endpoint reports this labelled protocol test.
It is not a market preflight, trading signal, actual broker order, or financial-performance report.
Restarting the same completed batch must skip all writes and preserve event counts.

## Validation and remaining activation work

Unit tests inject HTTP failures, process cancellation, lost DB acknowledgments, concurrency,
stale data/approval, unauthorized flags/token/host, duplicate identities and broker parsing errors.
CI provisions a disposable PostgreSQL 16 instance, applies the migrations, runs actual RLS/RPC
protocol tests, then races eight independent SQL sessions for one claim. Production permission
verification uses a rolled-back transaction; production synthetic records remain as labelled evidence.

Deployment/production results are recorded in `evidence/phase-2.5/README.md`, not assumed here.
Future activation still needs explicit bounded order budget/duration/open-close scope and a reviewed
server coordinator invoking the library under the durable cycle lease. Startup currently rejects
enabled execution; merely setting flags is intentionally insufficient. No claim of autonomous
execution readiness should be made until that activation work and current-market preflight pass.
