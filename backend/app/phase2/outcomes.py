from datetime import datetime

from backend.app.phase2.agents import AGENTS
from backend.app.phase2.models import (
    AgentScore,
    MarketState,
    PositionReview,
    Reflection,
    Regime,
    Shadow,
    ShadowMark,
)
from backend.app.phase2.policy import Policy, expiry_at


def mark_shadows(shadows: list[Shadow], state: MarketState, now: datetime) -> list[ShadowMark]:
    options = {o.symbol: o for o in state.observations + state.options}
    marks = []
    for shadow in shadows:
        option = options.get(shadow.symbol)
        age = (option.quote_at - shadow.timestamp).total_seconds() if option else -1
        if (not option or age < 60 or option.quote_at > now
                or option.quote_at >= expiry_at(option)
                or (now - option.quote_at).total_seconds() > 259200):
            continue
        pnl = round((option.bid - shadow.entry_reference) * 100, 2)
        marks.append(ShadowMark(
            shadow_id=shadow.id, agent=shadow.agent, timestamp=option.quote_at,
            bid_reference=option.bid, hypothetical_pnl=pnl,
            risk_return=pnl / shadow.hypothetical_max_loss if shadow.hypothetical_max_loss else 0,
            decision_regret=max(0, pnl), rejection_effect="HELPED" if pnl < 0 else ("HURT" if pnl > 0 else "NEUTRAL"),
            horizon_complete=age >= shadow.horizon_minutes * 60,
            source=option.source, elapsed_minutes=round(age / 60, 2),
        ))
    return marks


def score_agents(marks: list[ShadowMark]) -> list[AgentScore]:
    # First observed completed horizon per shadow; no repeated or cherry-picked later samples.
    latest = {}
    for mark in sorted(marks, key=lambda m: m.timestamp):
        if mark.horizon_complete:
            latest.setdefault(mark.shadow_id, mark)
    scores = []
    for agent in AGENTS:
        samples = [m for m in latest.values() if m.agent == agent]
        n = len(samples)
        wins = sum(m.hypothetical_pnl > 0 for m in samples)
        mean_return = sum(max(-1, min(1, m.risk_return)) for m in samples) / n if n else 0
        # 2/3 bounded premium efficiency + 1/3 hit balance, shrunken by n/(n+20).
        reliability = n / (n + 20)
        score = 50 + reliability * (10 * mean_return + 5 * (2 * wins / n - 1)) if n else 50
        scores.append(AgentScore(
            agent=agent, score=round(score, 2), shadow_samples=n,
            shadow_pnl=round(sum(m.hypothetical_pnl for m in samples), 2) if n else None,
            shadow_false_positives=sum(m.hypothetical_pnl < 0 for m in samples),
            shadow_missed_opportunities=wins,
            counterfactual_risk_efficiency=mean_return if n else None,
            counterfactual_false_positive_rate=sum(m.hypothetical_pnl < 0 for m in samples)/n if n else None,
            no_trade_quality=sum(m.hypothetical_pnl < 0 for m in samples)/n if n else None,
            score_components={"neutral_prior":50, "reliability":reliability,
                "counterfactual_efficiency":10*reliability*mean_return,
                "counterfactual_hit_balance":5*reliability*(2*wins/n-1) if n else 0,
                "executed_outcome":None, "executed_drawdown":None},
            basis="First later observed completed horizon; neutral prior with n/(n+20) shrinkage; no executed attribution",
        ))
    return scores


def review_positions(state: MarketState, regime: Regime, policy: Policy,
                     now: datetime) -> list[PositionReview]:
    options = {o.symbol: o for o in state.observations + state.options}
    reviews = []
    for pos in state.positions:
        option = options.get(pos.symbol)
        hours = (expiry_at(option) - now).total_seconds() / 3600 if option else None
        quote_age = (now - option.quote_at).total_seconds() if option else None
        fresh = quote_age is not None and 0 <= quote_age <= policy.freshness_seconds
        compatible = None if not option or not fresh or regime.name == "UNCERTAIN" else not (
            option.kind == "call" and regime.name == "TREND_DOWN"
            or option.kind == "put" and regime.name == "TREND_UP")
        within_risk = abs(pos.cost_basis) <= min(500, state.account.equity * policy.per_trade_fraction)
        recommendation, reasons = "HOLD", ["Monitor only; no add or close authority"]
        if hours is not None and hours <= 0:
            recommendation, reasons = "EXPIRED", ["Reconcile broker exercise/expiry state; do not assume closure"]
        elif not fresh or not state.clock.is_open or hours is None or hours < policy.min_expiry_hours or not within_risk:
            recommendation, reasons = "RISK_ALERT", ["Missing fresh quote, expiry proximity or risk limit requires operator review"]
        elif pos.unrealized_plpc <= -0.5:
            recommendation, reasons = "EXIT", ["Premium drawdown >=50%; recommendation only, separate authorization required"]
        elif compatible is False:
            recommendation, reasons = "REDUCE", ["Current regime contradicts directional exposure; recommendation only"]
        reviews.append(PositionReview(
            timestamp=now, position=pos, quote=option, expiry=option.expiry if option else None,
            hours_to_expiry=hours, theta_daily_dollars=option.theta * 100 * pos.qty
            if option and option.theta is not None else None,
            regime_compatible=compatible, thesis_invalidated=None if compatible is None else not compatible,
            risk_limit_ok=within_risk, recommendation=recommendation, reasons=reasons,
            quote_fresh=fresh, quote_age_seconds=quote_age, market_open=state.clock.is_open,
        ))
    return reviews


def reflect(marks: list[ShadowMark], now: datetime) -> list[Reflection]:
    return [Reflection(
        shadow_id=m.shadow_id, agent=m.agent, timestamp=now,
        expected="A directional move sufficient to exceed premium and spread",
        observed=f"Counterfactual bid liquidation P&L {m.hypothetical_pnl:.2f}; rejection {m.rejection_effect.lower()}",
        lessons={
            "regime": "Outcome alone does not establish regime accuracy",
            "entry_timing": "Ask entry versus later bid incorporates the spread, not guaranteed fills",
            "volatility": "No causal attribution without IV series",
            "liquidity": "Counterfactual quote is not proof of executable size",
            "theta": "Observed P&L does not isolate theta",
            "risk_gate_value": f"Rejected hypothetical outcome: {m.rejection_effect}",
            "agent_quality": "Only completed 60-minute horizons may update the shrunken shadow score",
        },
    ) for m in marks if m.horizon_complete]
