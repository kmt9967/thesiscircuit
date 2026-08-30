# Phase 1 Controlled Paper Execution

## Objective

Prove one end-to-end PAPER execution while keeping decision authority deterministic and evidence honest.

## Selected instrument and order

The candidate is one SPY call expiring September 4, 2026, selected near the money from real Alpaca option contracts and indicative quotes. The exact OCC symbol, strike, quote, limit, and premium are selected only during the official window. The order is buy-to-open, quantity one, DAY limit. Maximum theoretical loss is the premium and is capped at $250.

## Lifecycle

Market/account reads → canonical proposal → 17 risk gates → Supabase proposal/risk/decision events → one idempotent PAPER order → Alpaca order lookup → optional read-only reconciliation → fill and position snapshot → execution disabled.

## Current verified result

Implementation, audit schema, Railway backend, Vercel frontend, and read-only production preflight are verified. The preflight generated `SPY260904C00774000`, one long-call contract with $222 maximum simulated loss, then correctly rejected it because execution was disabled, the weekend quote was stale, the official window had not opened, and the market was closed. No Phase 1 order has been submitted. Order, fill, position, and P&L fields remain empty and must not be described as executed until Alpaca reports them.

## Limitations

Basic indicative options data may differ from OPRA. A limit order may remain unfilled or be rejected. ThesisCircuit will report actual Alpaca state and will not submit a second opening or closing order automatically.
