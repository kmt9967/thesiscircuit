# Phase 2.6 Part 1 — bounded coordinator

Status: implemented locally, disabled by default. New production database objects and
synthetic session verification await explicit Supabase approval. No trading authority
is granted by this implementation, deployment, or PR.

## Finite authorization

`phase2_execution_sessions` holds immutable session scope and append-only lifecycle
events: DRAFT → ACTIVE → EXPIRED / KILLED / COMPLETED. A UUID authorizes at most
one opening order by default, zero closing orders, three cycles, and one hour.
New premium is capped at min($500, 0.5% of approval/current equity); aggregate
premium is capped at 2% equity; positions at three. Lower limits are allowed.
For equity below $100,000, the approving caller must explicitly set correspondingly
lower monetary caps. Opening/closing/total counters and reservations are durable.

Only the service role can invoke:

- `phase2_create_execution_session(jsonb)` — immutable, idempotent DRAFT creation.
- `phase2_session_control(uuid,text,text,uuid)` — activation, bounded cycles, expiry, kill, completion.
- `phase2_session_order_gate(uuid,uuid,uuid,text,jsonb)` — reserve budget, fence submission, inspect result.

RLS denies anonymous/authenticated access. Service-role direct mutations are denied;
only the fenced RPCs can mutate. The new table has one-active-PAPER-session uniqueness.
The additive migration does not replace existing functions or historical records.

## Dispatch invariant

Coordinator acquires the existing durable cycle lease and registers a durable session
cycle ID before refreshing data, proposing, allocating, and running deterministic risk.
The dispatcher persists an immutable intent, acquires its exclusive claim, and consumes
a session budget reservation. Reservation happens before any possible broker submission.
The final session gate and existing irreversible `SUBMITTING` transition execute in
one PostgreSQL transaction. A second budget claim cannot exceed opening, closing,
total, or premium limits. A repeated same-intent reservation is idempotent; a distinct
session cannot reserve the same intent. No crash or rejected/unknown outcome refunds
the reservation. This deliberately sacrifices availability to prevent overspending.

The dispatcher independently rechecks token, both execution flags, exact paper host,
fresh state, immutable terms, current quote, deterministic risk and client-order-ID
reconciliation. Only its existing single HTTP boundary can reach the paper broker.
Lost database acknowledgment means no HTTP submission. Lost broker acknowledgment
means GET reconciliation, never a second POST. The former Phase 1 path stays retired.

## Expiry, failure and monitoring

Expiry is enforced using database time on every session control/budget operation and
again at the irreversible submission transition. A 15-second minimum remaining life
is required; the dispatcher also enforces its two-second local send window. No cron is
needed to enforce expiry; the stored status is materialized when inspected. Research
may finish its audit; spent-order reconciliation remains possible after expiry/kill.
No position is closed on expiry, kill, completion, or process restart.

Kill conditions include drawdown ≥1%, excess aggregate premium, position cap,
stale/missing data, live configuration, account/config mismatch, closed competition or
market, repeated broker failures, UNKNOWN order, database/cycle reliability failure,
manual kill, and authorization loss. Database failure prevents dispatch even when the
kill event itself cannot be written; finite expiry remains the durable backstop.

`MANAGE_EXISTING_POSITION=true` and `ALLOW_POSITION_EXIT=false` are explicit session
scope fields (`manage_existing_position`, `allow_position_exit`). The existing
SPY260904C00768000 long one, entry $1.84, receives advisory HOLD / EXIT / RISK_ALERT
only. The coordinator contains no automatic closing-selection path. A future explicit
exit scope would also require a separately reviewed closing orchestration path.
One primary SPY thesis/exposure, spread/liquidity and DTE gates remain unchanged.

## Synthetic verification and current production boundary

`PHASE26_SYNTHETIC_BATCH` defaults empty. Only after the new migration is approved
and verified may this non-secret server variable trigger four labelled SYNTHETIC
sessions: one-budget candidate, existing-position monitoring, UNKNOWN kill, and expiry.
The fixture market clock, quotes, account and fills are artificial—not live data or
actual broker results. Synthetic intents retain a null real Alpaca order reference.
The runner imports no broker transport, modifies no historical position/research rows,
and cannot run with either execution flag enabled. It uses a local synthetic cycle
lease adapter while exercising durable session cycles/budgets and real intent RPCs;
distributed real-cycle leasing remains independently covered by Phase 2/2.5 tests.
Completed deterministic batch IDs are skipped on restart without rewriting evidence.
Read-only output: `/phase2/session-verification`; no public activation/execute route.

Part 2 readiness requires green tests, verified production migration/access controls,
completed synthetic cases, unchanged broker order count, and a separate explicit
operator-approved finite PAPER session. Production startup still refuses enabled
execution flags. Part 1 does not remove that interlock or create a Phase 2 token.
