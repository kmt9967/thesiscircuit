"""Pure future-authorization checks. No HTTP route or broker dispatch is provided."""
import secrets
from datetime import datetime

from backend.app.config import Settings
from backend.app.phase2.models import ExitProposal, Gate, MarketState, Proposal, RiskResult
from backend.app.phase2.policy import Policy, expiry_at, validate


def authorization_gates(settings: Settings, supplied: str | None) -> list[Gate]:
    expected = settings.phase2_execution_token
    token_ok = bool(expected and supplied and len(expected.get_secret_value()) >= 32
                    and secrets.compare_digest(expected.get_secret_value(), supplied))
    # Phase 1 tokens are deliberately never inspected here.
    return [
        Gate(name="execution_enabled", passed=settings.execution_enabled, reason="Server execution gate required"),
        Gate(name="autonomous_enabled", passed=settings.autonomous_trading_enabled,
             reason="Separate autonomous gate required"),
        Gate(name="phase2_authorization", passed=token_ok, reason="Separate constant-time Phase 2 token check"),
    ]


def execution_preflight(proposal: Proposal, state: MarketState, settings: Settings,
                        policy: Policy, now: datetime, supplied: str | None) -> RiskResult:
    # Recompute risk, never accept a caller-provided risk decision. Only the research
    # gate is replaced by explicit authorization gates; no safety gate is skipped.
    research = validate(proposal, state, settings, policy, now)
    checks = [g for g in research.checks if g.name != "dry_run_gate"]
    checks += authorization_gates(settings, supplied)
    reasons = [g.name + ": " + g.reason for g in checks if not g.passed]
    return RiskResult(proposal_id=proposal.id, checks=checks, reasons=reasons,
                      decision="REJECTED" if reasons else "APPROVED")


def exit_preflight(exit: ExitProposal, state: MarketState, settings: Settings,
                   policy: Policy, now: datetime, supplied: str | None) -> RiskResult:
    """Same core safety checks, with explicit reducing-exposure semantics, advisory only."""
    c = exit.contract
    proposed = Proposal(id=exit.id, agent="DEFENSIVE", timestamp=exit.timestamp, regime="UNCERTAIN",
        contract=c, direction="BULLISH" if c.kind == "call" else "BEARISH",
        strategy_type="LONG_CALL" if c.kind == "call" else "LONG_PUT", confidence=0,
        thesis=exit.rationale, evidence={}, invalidation="Ownership or fresh risk state changes",
        estimated_max_loss=c.ask * 100, liquidity_assessment="Requires independent risk checks",
        reasons_not_to_trade=[], status="PROPOSED")
    result = execution_preflight(proposed, state, settings, policy, now, supplied)
    owned = [p for p in state.positions if p.symbol == c.symbol]
    ownership = (len(owned) == 1 and owned[0].side == "long" and owned[0].qty >= exit.quantity
                 and owned[0].qty.is_integer() and owned[0].asset_class == "us_option")
    # Reducing premium exposure needs no new buying power/capacity. An exit is not
    # an opening proposal; this whitelist cannot remove paper, auth, freshness or liquidity.
    entry_only = {"proposal", "max_new_risk", "buying_power", "positions_limit", "aggregate_risk",
                  "underlying_exposure", "duplicate_position", "expiry"}
    checks = [g for g in result.checks if g.name not in entry_only]
    checks += [Gate(name="owned_reduce_only", passed=ownership, reason="Sell only verified owned long contracts"),
        Gate(name="exit_limit", passed=c.bid <= exit.limit_price <= c.ask,
             reason="Positive limit inside current bid/ask"),
        Gate(name="exit_expiry", passed=(expiry_at(c)-now).total_seconds() >= 3600,
             reason="At least one hour before expiry; no automatic exercise handling"),
        Gate(name="exit_proposal_fresh", passed=0 <= (now-exit.timestamp).total_seconds() <= 120,
             reason="Fresh advisory exit")]
    reasons = [g.name + ": " + g.reason for g in checks if not g.passed]
    return RiskResult(proposal_id=exit.id, checks=checks, reasons=reasons,
                      decision="REJECTED" if reasons else "APPROVED")
