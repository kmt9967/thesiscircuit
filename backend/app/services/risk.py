from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from backend.app.config import PAPER_BASE_URL, Settings
from backend.app.models import (
    AccountSnapshot,
    AssetSnapshot,
    ExecutionRiskDecision,
    MarketClock,
    RiskGateCheck,
    TradeProposal,
)


def validate_execution(
    settings: Settings,
    proposal: TradeProposal,
    account: AccountSnapshot,
    clock: MarketClock,
    asset: AssetSnapshot,
    open_orders: list[dict],
    positions: list[dict],
    duplicate_order: bool,
    now: datetime | None = None,
) -> ExecutionRiskDecision:
    now = now or datetime.now(timezone.utc)
    start = datetime.fromisoformat(settings.phase1_official_start_utc.replace("Z", "+00:00"))
    end = datetime.fromisoformat(settings.phase1_official_end_utc.replace("Z", "+00:00"))
    data_age = max(0.0, (now - proposal.data_timestamp).total_seconds())
    checks = [
        RiskGateCheck(name="paper_mode", passed=settings.trading_mode == "paper", detail="paper required"),
        RiskGateCheck(
            name="paper_endpoint",
            passed=str(settings.alpaca_paper_base_url).rstrip("/") == PAPER_BASE_URL,
            detail="paper-api.alpaca.markets required",
        ),
        RiskGateCheck(name="active_account", passed=account.status == "ACTIVE", detail=account.status),
        RiskGateCheck(
            name="execution_gate", passed=settings.execution_enabled, detail="server-side gate"
        ),
        RiskGateCheck(
            name="fresh_data",
            passed=data_age <= settings.phase1_max_data_age_seconds,
            detail=f"age_seconds={data_age:.1f}",
        ),
        RiskGateCheck(
            name="instrument_tradable",
            passed=asset.tradable and proposal.asset_class == "us_option",
            detail=proposal.instrument,
        ),
        RiskGateCheck(
            name="tiny_position", passed=proposal.quantity == 1, detail="exactly one contract"
        ),
        RiskGateCheck(
            name="buying_power",
            passed=account.buying_power >= proposal.max_theoretical_loss,
            detail=f"required={proposal.max_theoretical_loss:.2f}",
        ),
        RiskGateCheck(
            name="unique_client_order_id",
            passed=not duplicate_order,
            detail=proposal.client_order_id,
        ),
        RiskGateCheck(
            name="no_conflicting_order",
            passed=not any(order.get("symbol") == proposal.instrument for order in open_orders),
            detail="same-instrument open order forbidden",
        ),
        RiskGateCheck(
            name="no_existing_position",
            passed=not any(position.get("symbol") == proposal.instrument for position in positions),
            detail="same-instrument position forbidden",
        ),
        RiskGateCheck(
            name="supported_order",
            passed=proposal.order_type == "limit" and proposal.time_in_force == "day",
            detail="single-leg DAY limit",
        ),
        RiskGateCheck(
            name="bounded_max_loss",
            passed=proposal.max_theoretical_loss <= settings.phase1_max_risk_usd,
            detail=f"max_loss={proposal.max_theoretical_loss:.2f}",
        ),
        RiskGateCheck(
            name="hackathon_rules",
            passed=start <= now <= end and proposal.asset_class == "us_option",
            detail="official options P&L window",
        ),
        RiskGateCheck(
            name="market_state", passed=clock.is_open, detail="market must report open"
        ),
        RiskGateCheck(
            name="drawdown_limit",
            passed=account.equity >= account.last_equity * 0.99,
            detail="daily drawdown below 1%",
        ),
        RiskGateCheck(
            name="live_disabled",
            passed=not settings.allow_live_trading and not settings.live_trading_allowed,
            detail="live trading permanently disabled",
        ),
    ]
    approved = all(check.passed for check in checks)
    risk_id = uuid5(NAMESPACE_URL, f"{proposal.trace_id}:risk")
    return ExecutionRiskDecision(
        id=risk_id,
        trace_id=proposal.trace_id,
        proposal_id=proposal.id,
        created_at=now,
        decision="APPROVED" if approved else "REJECTED",
        checks=checks,
        max_simulated_risk=proposal.max_theoretical_loss,
    )
