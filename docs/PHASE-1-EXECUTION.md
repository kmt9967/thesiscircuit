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

## Limitations

Basic indicative options data may differ from OPRA. A limit order may remain unfilled or be rejected. ThesisCircuit will report actual Alpaca state and will not submit a second opening or closing order automatically.
