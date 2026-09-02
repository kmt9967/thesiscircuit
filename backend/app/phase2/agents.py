from datetime import datetime

from backend.app.phase2.models import (
    AgentName,
    Allocation,
    CriticReview,
    MarketState,
    Proposal,
    Regime,
)
from backend.app.phase2.policy import Policy, expiry_at, liquid, underlying

AGENTS: tuple[AgentName, ...] = ("TREND", "RANGE", "DEFENSIVE")


def propose(agent: AgentName, state: MarketState, regime: Regime, policy: Policy,
            now: datetime) -> Proposal:
    f = state.features
    direction = None
    if f and agent == "TREND" and regime.name in {"TREND_UP", "TREND_DOWN"}:
        direction = "call" if regime.name == "TREND_UP" else "put"
    elif f and agent == "RANGE" and regime.name in {"RANGE", "LOW_VOLATILITY"}:
        direction = "call" if f.rsi < 35 else ("put" if f.rsi > 65 else None)
    elif f and agent == "DEFENSIVE" and regime.name in {"TREND_DOWN", "HIGH_VOLATILITY"}:
        direction = "put" if f.return_20m < 0 else None
    evidence = {} if not f else {
        "price": f.price, "rsi": f.rsi, "trend_strength": f.trend_strength,
        "return_20m": f.return_20m, "realized_volatility": f.realized_volatility,
    }
    candidates = [o for o in state.options if o.kind == direction and o.tradable
                  and 0 <= (now - o.quote_at).total_seconds() <= policy.freshness_seconds
                  and policy.min_expiry_hours <= (expiry_at(o) - now).total_seconds() / 3600
                  <= policy.max_expiry_days * 24
                  and o.ask * 100 <= min(policy.per_trade_dollars,
                                        state.account.equity * policy.per_trade_fraction)
                  and liquid(o, now, policy)]
    candidate = min(candidates, key=lambda o: (abs(o.strike - f.price), o.spread_pct, o.symbol)) if candidates and f else None
    common = {"agent": agent, "timestamp": now, "regime": regime.name, "evidence": evidence,
              "invalidation": regime.invalidation}
    if not candidate or not f:
        return Proposal(**common, contract=None, direction="NONE", strategy_type="NO_TRADE",
                        confidence=0, thesis="No qualifying regime signal and liquid defined-risk contract",
                        estimated_max_loss=0, liquidity_assessment="No eligible candidate",
                        reasons_not_to_trade=state.data_errors or ["Signal, freshness, liquidity or budget not satisfied"],
                        status="NO_TRADE")
    intrinsic = max(0, f.price - candidate.strike) if direction == "call" else max(0, candidate.strike - f.price)
    return Proposal(
        **common, contract=candidate, direction="BULLISH" if direction == "call" else "BEARISH",
        strategy_type="LONG_CALL" if direction == "call" else "LONG_PUT",
        confidence=min(0.85, regime.confidence),
        thesis=f"{agent}: {regime.name} with RSI {f.rsi:.1f} and ATR-normalized trend {f.trend_strength:.2f}",
        estimated_max_loss=candidate.ask * 100, intrinsic=intrinsic,
        extrinsic=max(0, candidate.ask - intrinsic),
        breakeven=candidate.strike + candidate.ask if direction == "call" else candidate.strike - candidate.ask,
        max_profit=None if direction == "call" else max(0, candidate.strike - candidate.ask) * 100,
        liquidity_assessment=f"{candidate.source}; spread {candidate.spread_pct:.1%}; quote/OI screen passed",
        reasons_not_to_trade=["Long premium can decay to zero", "Indicative data is not an executable guarantee",
                              "Existing exposure must be independently vetoed"], status="PROPOSED",
    )


def critique(p: Proposal, state: MarketState, regime: Regime) -> CriticReview:
    concentration = any(underlying(pos.symbol) == p.underlying for pos in state.positions)
    c = p.contract
    return CriticReview(
        proposal_id=p.id,
        strongest_counterargument="Recent price direction is not evidence that movement will exceed paid premium",
        regime_contradiction=f"{regime.name} is a heuristic on a short minute-bar sample, not a forecast",
        volatility_risk="Implied volatility can fall even when direction is correct",
        liquidity_risk=f"Spread {c.spread_pct:.1%}; feed {c.source}" if c else "No eligible quote",
        timing_risk="Late entry and trend reversal can invalidate the short-horizon signal",
        expiration_theta_risk="Time decay and automatic exercise near expiry require separate operator handling",
        concentration_risk="Existing SPY position: additional directional thesis prohibited" if concentration else "No matching underlying exposure observed",
        no_trade_argument="Preserving cash avoids premium decay and avoids concentrating existing risk",
        severity=0.95 if concentration else (0.6 if regime.name == "HIGH_VOLATILITY" else 0.25),
    )


def allocate(proposals: list[Proposal], critics: list[CriticReview], state: MarketState,
             regime: Regime, historical_scores: dict[str, float], policy: Policy) -> Allocation:
    scores: dict[str, float] = {}
    directions = {p.direction for p in proposals if p.status == "PROPOSED"}
    if len(directions) > 1:
        return Allocation(decision="NO_TRADE", reason="Conflicting directional theses; no forced tie-break", scores={})
    reviews = {c.proposal_id: c for c in critics}
    remaining = state.account.equity * policy.aggregate_fraction - sum(abs(p.cost_basis) for p in state.positions)
    for p in proposals:
        critic = reviews.get(p.id)
        if p.status != "PROPOSED" or not critic or not p.contract:
            continue
        if critic.severity >= 0.8 or p.estimated_max_loss > remaining:
            continue
        if any(underlying(pos.symbol) == p.underlying for pos in state.positions):
            continue
        quality = min(100, max(0, historical_scores.get(p.agent, 50))) / 100
        # Explicitly multi-factor; no raw confidence winner and no prediction of expected profit.
        liquidity = max(0, 1 - p.contract.spread_pct / policy.max_spread_fraction)
        budget_efficiency = max(0, 1 - p.estimated_max_loss / max(1, policy.per_trade_dollars))
        scores[str(p.id)] = round(0.2 * p.confidence + 0.2 * regime.confidence +
                                  0.2 * liquidity + 0.15 * quality + 0.1 * budget_efficiency +
                                  0.15 * (1 - critic.severity), 4)
    if not scores or max(scores.values()) < 0.5:
        return Allocation(decision="NO_TRADE", reason="No candidate clears exposure, critic, budget and composite-quality floor", scores=scores)
    # Stable tie-break by strategy name, never random proposal UUID.
    identities = {str(p.id): p.agent for p in proposals}
    winner = max(scores, key=lambda key: (scores[key], identities[key]))
    return Allocation(decision="SELECT", proposal_id=winner,
                      reason="Highest eligible composite score; still subject to independent hard risk veto", scores=scores)
