# Phase 2 validation and readiness

Part 2 preserves Part 1's architecture and historical Phase 1 order. It adds independent
timestamped position observations, counterfactual marking, stable allocation ties, explicit
future Phase 2 authorization, advisory exits, distributed research locking, and offline replay.

## Actual implementation versus planned capability

Implemented: Trend/Range/Defensive policies, Critic, MetaAllocator, 24-gate entry RiskOfficer,
bounded read-only orchestration, Supabase audit, shadows/scoring/reflection, portfolio dashboard,
pure future entry/exit authorization checks and fail-closed tests.

Phase 2.5 subsequently implemented durable submission claims and restart/timeout reconciliation,
verified using labelled synthetic records with zero broker calls. See [Phase 2.5](PHASE-2.5-ORDER-DISPATCH.md).

Not activated: continuous autonomous broker dispatch, autonomous exits, execution credential provisioning,
exact-horizon historical options backtests or statistically meaningful performance validation.
Therefore the system is NOT yet ready to enable autonomous PAPER orders. It is ready for
controlled read-only dry-run validation. Both execution flags remain false.

The durable cycle dispatcher is now deployed and verified: one RLS-protected singleton,
two service-only RPCs, per-cycle owner fencing, three-minute expiry, atomic audit completion,
60-second cadence/cooldown, two-attempt ceiling and abandoned-cycle recovery. Three new
production dry runs completed with zero new orders. See evidence/phase-2/PART-2.md.

Evidence lives in `evidence/phase-2/`. The replay command is `python -m scripts.phase2_replay`.
Results are explicitly HISTORICAL or SIMULATED. Null outcomes mean unmeasured, never flat P&L.

Hard ceilings remain min($500,0.5% current equity) per opening trade, 2% aggregate paid premium,
three positions, one primary thesis per underlying, 1% daily equity-drawdown veto, 15-minute
submission cooldown, <=10% AND <=$0.15 spread, both quote sizes >=5 OR recent OI >=100,
24h–7d expiry bounds, 120-second quote/state freshness and official competition/market window.

No changes to old hackathon projects, no new Alpaca order and no live trading are part of this work.
PR #3 remains unmerged.
