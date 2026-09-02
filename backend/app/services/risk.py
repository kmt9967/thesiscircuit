from datetime import datetime, timezone
from math import isclose
from typing import Literal
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
    stage: Literal["readiness", "execution"] = "execution",
    total_orders: int = 0,
) -> ExecutionRiskDecision:
    now = now or datetime.now(timezone.utc)
    start = datetime.fromisoformat(settings.phase1_official_start_utc.replace("Z", "+00:00"))
    end = datetime.fromisoformat(settings.phase1_official_end_utc.replace("Z", "+00:00"))
    data_age = (now - proposal.data_timestamp).total_seconds()
    clock_age = (now - clock.timestamp).total_seconds()
    bid = proposal.liquidity_metrics.get("bid", 0)
    ask = proposal.liquidity_metrics.get("ask", 0)
    spread = ask - bid
    premium = round(proposal.limit_price * 100 * proposal.quantity, 2)
    checks = [
        RiskGateCheck(name="paper_mode", passed=settings.trading_mode == "paper"
                      and settings.alpaca_paper_trade, detail="paper required"),
        RiskGateCheck(
            name="paper_endpoint",
            passed=str(settings.alpaca_paper_base_url).rstrip("/") == PAPER_BASE_URL,
            detail="paper-api.alpaca.markets required",
        ),
        RiskGateCheck(name="active_account", passed=account.status == "ACTIVE"
                      and account.expected_account_match and not account.trading_blocked
                      and account.options_trading_level >= 2,
                      detail="active dedicated account; unblocked; options level >= 2"),
        RiskGateCheck(
            name="execution_gate",
            passed=settings.execution_enabled == (stage == "execution"),
            detail=f"{stage}: execution must be {'enabled' if stage == 'execution' else 'disabled'}",
        ),
        RiskGateCheck(
            name="fresh_data",
            passed=0 <= data_age <= settings.phase1_max_data_age_seconds,
            detail=f"age_seconds={data_age:.1f}",
        ),
        RiskGateCheck(
            name="instrument_tradable",
            passed=asset.tradable and asset.status == "active"
            and asset.symbol == proposal.instrument and proposal.asset_class == "us_option",
            detail=proposal.instrument,
        ),
        RiskGateCheck(
            name="tiny_position", passed=proposal.quantity == 1, detail="exactly one contract"
        ),
        RiskGateCheck(
            name="buying_power",
            passed=min(account.buying_power, account.options_buying_power or 0, account.cash)
            >= proposal.max_theoretical_loss,
            detail=f"required={proposal.max_theoretical_loss:.2f}",
        ),
        RiskGateCheck(
            name="unique_client_order_id",
            passed=not duplicate_order,
            detail=proposal.client_order_id,
        ),
        RiskGateCheck(
            name="no_conflicting_order",
            passed=not open_orders and total_orders == 0,
            detail="no order history or open orders permitted before first opening",
        ),
        RiskGateCheck(
            name="no_existing_position",
            passed=not positions,
            detail="no existing positions permitted",
        ),
        RiskGateCheck(
            name="supported_order",
            passed=proposal.order_type == "limit" and proposal.time_in_force == "day"
            and proposal.side == "buy" and proposal.strategy_type == "long_call"
            and proposal.legs == [{"symbol": proposal.instrument, "side": "buy",
                                   "position_intent": "buy_to_open"}],
            detail="single-leg DAY limit",
        ),
        RiskGateCheck(
            name="bounded_max_loss",
            passed=0 < premium <= settings.phase1_max_risk_usd
            and isclose(proposal.max_theoretical_loss, premium)
            and isclose(proposal.estimated_max_loss, premium)
            and isclose(proposal.debit, proposal.limit_price),
            detail=f"max_loss={proposal.max_theoretical_loss:.2f}",
        ),
        RiskGateCheck(
            name="hackathon_rules",
            passed=start <= now < end and proposal.asset_class == "us_option"
            and proposal.underlying == settings.phase1_symbol
            and proposal.expiry == settings.phase1_expiration_date
            and proposal.expiry >= now.date().isoformat(),
            detail="official options P&L window",
        ),
        RiskGateCheck(
            name="market_state", passed=clock.is_open and 0 <= clock_age <= 120
            and now < clock.next_close, detail="fresh open market clock; before close"
        ),
        RiskGateCheck(
            name="drawdown_limit",
            passed=account.equity >= account.last_equity * 0.99
            and abs(account.cash - settings.alpaca_competition_starting_balance) < 0.01
            and abs(account.equity - settings.alpaca_competition_starting_balance) < 0.01,
            detail="unchanged $100,000 judging account; daily drawdown below 1%",
        ),
        RiskGateCheck(
            name="live_disabled",
            passed=not settings.allow_live_trading and not settings.live_trading_allowed,
            detail="live trading permanently disabled",
        ),
        RiskGateCheck(
            name="option_liquidity",
            passed=0 < bid <= ask and spread <= 0.10 + 1e-9
            and spread / ((bid + ask) / 2) <= 0.10
            and isclose(proposal.limit_price, ask, abs_tol=0.005),
            detail=f"bid={bid:.2f}; ask={ask:.2f}; spread <= $0.10 and 10% midpoint",
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
