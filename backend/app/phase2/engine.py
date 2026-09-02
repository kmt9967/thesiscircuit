import asyncio
from contextlib import suppress
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid4, uuid5

from backend.app.config import DATA_BASE_URL, PAPER_BASE_URL, Settings
from backend.app.phase2.agents import AGENTS, allocate, critique, propose
from backend.app.phase2.features import classify
from backend.app.phase2.models import Cycle, MarketState, Shadow, ShadowMark
from backend.app.phase2.outcomes import mark_shadows, reflect, review_positions, score_agents
from backend.app.phase2.policy import Policy, validate


def assert_dry_run(settings: Settings) -> None:
    if (settings.execution_enabled or settings.autonomous_trading_enabled
            or settings.allow_live_trading or settings.live_trading_allowed
            or not settings.alpaca_paper_trade or settings.trading_mode != "paper"
            or str(settings.alpaca_paper_base_url).rstrip("/") != PAPER_BASE_URL
            or str(settings.alpaca_data_base_url).rstrip("/") != DATA_BASE_URL):
        raise RuntimeError("Phase 2 research requires both execution gates disabled and paper-only settings")


def run_cycle(state: MarketState, settings: Settings, policy: Policy, batch: str, sequence: int,
              shadows: list[Shadow], historical_marks: list[ShadowMark], now: datetime) -> Cycle:
    assert_dry_run(settings)
    regime = classify(state.features, now)
    marks = mark_shadows(shadows, state, now)
    scores = score_agents(historical_marks + marks)
    proposals = [propose(agent, state, regime, policy, now) for agent in AGENTS]
    critics = [critique(p, state, regime) for p in proposals]
    allocation = allocate(proposals, critics, state, regime, {s.agent: s.score for s in scores}, policy)
    risks = [validate(p, state, settings, policy, now) for p in proposals]
    approved = {r.proposal_id for r in risks if r.decision == "APPROVED"}
    selected = allocation.proposal_id if allocation.proposal_id in approved else None
    decision = "DRY_RUN_CANDIDATE" if selected else "NO_TRADE"
    # Suppress overlapping same-agent/contract counterfactuals for the fixed 60-minute horizon.
    active_shadows = {(s.agent, s.symbol) for s in shadows
                      if 0 <= (now - s.timestamp).total_seconds() < s.horizon_minutes * 60}
    new_shadows = [Shadow(
        proposal_id=p.id, agent=p.agent, symbol=p.contract.symbol, timestamp=now,
        entry_reference=p.contract.ask, hypothetical_max_loss=p.estimated_max_loss,
        rejection_reason=allocation.reason if p.id != allocation.proposal_id
        else "; ".join(next(r.reasons for r in risks if r.proposal_id == p.id)),
    ) for p in proposals if p.contract and p.id != selected
        and (p.agent, p.contract.symbol) not in active_shadows]
    stages = ["market_refresh", "features", "regime", "strategy_agents", "critic",
              "allocation", "risk_officer", "execution_blocked", "shadow_research", "position_review"]
    return Cycle(
        id=uuid5(NAMESPACE_URL, f"thesiscircuit:phase2:{batch}:{sequence}"),
        created_at=now, batch=batch, sequence=sequence, state=state, regime=regime,
        proposals=proposals, critics=critics, allocation=allocation, risk=risks, decision=decision,
        shadows=new_shadows, marks=marks, scores=scores,
        position_reviews=review_positions(state, regime, policy, now), reflections=reflect(marks, now),
        timeline=[{"sequence": i, "stage": stage, "timestamp": now.isoformat(),
                   "note": "NO ORDER CAPABILITY" if stage == "execution_blocked" else "DRY_RUN"}
                  for i, stage in enumerate(stages)],
    )


async def run_batch(provider, repository, settings: Settings, policy: Policy, batch: str,
                    count: int = 3, interval: float = 60, sleep=asyncio.sleep) -> list[str]:
    assert_dry_run(settings)
    if not batch or not 1 <= count <= 3 or not 60 <= interval <= 3600:
        raise ValueError("Only bounded 1–3 cycle batches, 60–3600 seconds apart")
    return await _run_batch(provider, repository, settings, policy, batch, count, interval, sleep)


async def _run_batch(provider, repository, settings: Settings, policy: Policy, batch: str,
                     count: int, interval: float, sleep) -> list[str]:
    """Finite server-owned dry-run batch. No public trigger and no broker write dependency.

    Deterministic batch/sequence keys and transactional insert prevent duplicate audit cycles
    across deployments. A failed data read/persistence stops the batch, never silently succeeds.
    """
    assert_dry_run(settings)
    if not batch or not 1 <= count <= 3 or interval < 60:
        raise ValueError("Only bounded 1–3 cycle batches, at least 60 seconds apart")
    completed = []
    for sequence in range(count):
        cycle_id = str(uuid5(NAMESPACE_URL, f"thesiscircuit:phase2:{batch}:{sequence}"))
        if await repository.completed(cycle_id):
            completed.append(cycle_id)
            continue
        owner = str(uuid4())
        if not await repository.acquire_lease(owner, 180, cycle_id):
            raise RuntimeError("NO_TRADE: lease overlap, cooldown, completed cycle or retry budget exhausted")
        async def work(sequence=sequence):
            assert_dry_run(settings)
            shadows, old_marks = await repository.history()
            state = await provider.refresh(list({s.symbol for s in shadows}))
            return run_cycle(state, settings, policy, batch, sequence, shadows, old_marks,
                             datetime.now(timezone.utc))
        try:
            cycle = await asyncio.wait_for(work(), timeout=150)
            assert_dry_run(settings)
            await repository.release_lease(owner, "COMPLETED", cycle)
        except (Exception, asyncio.CancelledError):
            # Ambiguous completion is never retried blindly. Next explicit run
            # checks durable completion first; SQL caps total attempts at two.
            with suppress(Exception):
                await repository.release_lease(owner, "FAILED")
            raise
        completed.append(cycle_id)
        if sequence + 1 < count:
            await sleep(interval)
    return completed
