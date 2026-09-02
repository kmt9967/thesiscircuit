# Phase 1 Controlled Paper Execution

## Objective

Prove one end-to-end PAPER execution while keeping decision authority deterministic and evidence honest.

## Selected instrument and order

The candidate is one SPY call expiring September 4, 2026, selected near the money from real Alpaca option contracts and indicative quotes. The exact OCC symbol, strike, quote, limit, and premium are selected only during the official window. The order is buy-to-open, quantity one, DAY limit. Maximum theoretical loss is the premium and is capped at $250.

## Lifecycle

Fresh market/account reads → readiness (execution MUST be disabled) → durable
`READY_FOR_EXECUTION` receipt → operator enables Railway execution → fresh execution
preflight → durable `APPROVED_FOR_SINGLE_ORDER` receipt → fresh submission recheck →
immutable Supabase claim → canonical audit → at most one PAPER order attempt →
immediate local shutdown → Railway environment shutdown → read-only reconciliation.

Both stages run the same 18 gates, including an explicit liquidity gate. Only the
expected execution-gate state differs. Readiness expires after 15 minutes; final
approval after 60 seconds. Final and submission checks pin the readiness instrument
and forbid an increased premium. Changed candidates require a new disabled readiness.

Supabase `system_events` sequences -2/-1 hold sanitized readiness/execution receipts.
Sequence 0 is an immutable INSERT, protected by UNIQUE(trace_id, sequence), never an
upsert. It is consumed before any broker write and persists across replicas/restarts.
Audit/network uncertainty leaves it consumed: reconcile by client ID; never retry.
Effective production execution is false whenever this claim exists, even if a
deployment temporarily still has the environment switch enabled. The operator must
also reset Railway's environment switch to false. No automatic close/cancel exists.

## Current verified result

The August 30 preflight was rejected before the official trading window; it did not
submit an order. The September 2 candidate is `SPY260904C00768000`; readiness refreshes
that contract before considering any replacement. The two-stage fix is implemented
and tested locally. Deployment and actual execution results must be recorded below
only after production verification; no test fixture represents an executed order.

September 2, 16:05:12 UTC: deployed readiness returned READY_FOR_EXECUTION with all
18 gates passing, same SPY Sep 4 768 call, fresh $2.06/$2.07 bid/ask, proposed $2.07
DAY limit and $207 premium loss bound. Account identity matched; cash/equity $100,000,
zero positions/orders; execution remained false. Supabase stored the readiness
receipt. Execution was pending server-only token setup at that checkpoint.
See `evidence/phase-1/2026-09-02-two-stage-readiness.json`. This evidence expires as
authorization and must not be reused without fresh checks.

### Completed controlled execution — September 2, 2026

- A 256-bit random execution token was configured only in Railway; it was never
  printed, written to a local file, committed, or sent to Vercel. Operator memory
  was cleared after use. Existing Alpaca/Supabase credentials were not regenerated.
- Fresh readiness at **16:18:59.237606 UTC** returned READY_FOR_EXECUTION with all
  18 gates passed and execution disabled. The dedicated account matched, cash and
  equity were $100,000, orders/positions were zero, and the market/window were open.
  The retained SPY Sep 4 $768 call quoted $1.81/$1.90; premium bound $190.
- After Railway enabled execution, the final stage at **16:21:15.665006 UTC** returned
  APPROVED_FOR_SINGLE_ORDER, all 18 gates passed, with a fresh $1.89/$1.90 quote.
- Submission rechecked everything again at **16:21:18.902860 UTC**. The quote improved
  to $1.87/$1.88; the actual one-contract buy-to-open DAY limit was **$1.88** and the
  maximum premium at the limit was **$188**, below the $250 Phase 1 cap.
- Exactly one opening order was submitted at **16:21:20.523115 UTC**. Alpaca initially
  returned `pending_new`; subsequent read-only reconciliation returned `filled`.
- Alpaca order: `533142b0-7e8c-4c77-ab20-30a764f0fb7e`.
  Client ID: `thesiscircuit-phase1-eeb2ef56-a111-59c2-815e-17bc75fdc270`.
- Actual fill: **1 contract at $1.84**, timestamp
  **2026-09-02T16:21:20.626921323Z**. Premium paid: **$184**. Cash afterward: $99,815.97.
  The $0.03 difference between cash debit and premium was not separately reconciled
  to an account-activity fee record; no fee breakdown is asserted here.
- Resulting position: **long 1 SPY260904C00768000**, entry $1.84, cost basis $184.
  At the 16:23:17 UTC reconciliation snapshot, Alpaca reported value $182 and
  unrealized P&L -$2. These are historical marks, not a forecast or fixed live value.
- Supabase contains the proposal, approved risk checks, decision write, exact
  submission claim/payload, actual order, fill, position/account snapshot, and
  system events under trace `eeb2ef56-a111-59c2-815e-17bc75fdc270`.
- The backend disabled its process-local gate immediately after the broker response.
  Railway's environment was restored to false. Production `/safety` subsequently
  confirmed both `execution_enabled=false` and `configured_execution_enabled=false`.
  A final read-only reconciliation persisted the disabled-state audit.
- Vercel displays the actual filled order, $1.84 fill, long position, risk approval,
  audit timeline, and permanent paper disclosures. Account-read and position-snapshot
  timestamps are shown separately; refreshing the page never trades.

**Phase 1 opening orders: 1. Additional orders: 0. Closing orders: 0.**
The position remains open. No live account/credentials, real funds, balance reset,
automatic strategy loop, or Phase 2 activity was created. PR #2 remains unmerged.

## Validation

68 backend tests pass, including both-stage proofs, stale/risk rejection, immutable
claim conflicts, failed duplicate lookups, timeout reconciliation, single submission,
and shutdown/restart behavior. Ruff, Python compilation, tracked/pending secret
scan, live-endpoint/paper-safety audit, frontend lint/typecheck, frontend safety tests,
and production build pass. Production Alpaca/Supabase connectivity and frontend CORS
were checked independently. See the completion evidence for observation timestamps.

## Limitations

Basic indicative options data may differ from OPRA. A limit order may remain unfilled or be rejected. ThesisCircuit will report actual Alpaca state and will not submit a second opening or closing order automatically.

The premium loss bound excludes transaction costs and any stock position resulting
from exercise. The open option expires September 4; Alpaca may automatically exercise
an ITM option at expiry. Any closing or expiry-management instruction requires
separate user authorization. Phase 2 is not started or authorized; its specification
and safe handling of the existing position remain separate decisions.
