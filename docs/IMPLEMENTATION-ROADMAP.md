# Implementation Roadmap

1. Phase 0 — paper-only foundation, infrastructure, and read-only connectivity. Complete.
2. Phase 1A — typed services, deterministic proposal/risk, schema, dashboard, and production preflight. Complete.
3. Phase 1B — complete September 2: both preflights passed, exactly one paper long
   call filled, audit reconciled, real state displayed, execution disabled again.
   Existing long 1 SPY260904C00768000 remains open; do not close without authorization.
4. Phase 2 Part 1 — deterministic agents, critic, allocation, risk, counterfactuals,
   recommendation-only position manager and finite real-data dry runs. Build authorized;
   **zero new orders**. See PHASE-2-ARCHITECTURE.md and evidence/phase-2.
5. Phase 2 Part 2 — validation and readiness work authorized, orders forbidden.
   Advisory exits, separate token boundary, observations, lease and replay implemented.
   Production migration/verification status is tracked in evidence/phase-2/PART-2.md.
6. Future autonomous dispatch — not authorized or implemented. Requires separately
   reviewed durable intent claims, final preflight, unknown-order reconciliation and
   bounded execution scope. No automatic opening/closing or merge of PR #3.
