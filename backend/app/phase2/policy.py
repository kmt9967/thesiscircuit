import re
from datetime import datetime, time, timezone
from math import isfinite
from zoneinfo import ZoneInfo

from pydantic import Field

from backend.app.config import PAPER_BASE_URL, Settings
from backend.app.phase2.models import Gate, MarketState, Option, Proposal, Record, RiskResult


class Policy(Record):
    per_trade_fraction: float = Field(default=0.005, gt=0, le=0.005)
    per_trade_dollars: float = Field(default=500, gt=0, le=500)
    aggregate_fraction: float = Field(default=0.02, gt=0, le=0.02)
    daily_drawdown_fraction: float = Field(default=0.01, gt=0, le=0.01)
    max_positions: int = Field(default=3, ge=1, le=3)
    max_spread_fraction: float = Field(default=0.10, gt=0, le=0.10)
    max_spread_dollars: float = Field(default=0.15, gt=0, le=0.15)
    minimum_quote_size: int = Field(default=5, ge=1)
    minimum_open_interest: int = Field(default=100, ge=1)
    min_expiry_hours: int = Field(default=24, ge=24)
    max_expiry_days: int = Field(default=7, ge=1, le=30)
    freshness_seconds: int = Field(default=120, ge=1, le=120)
    cooldown_seconds: int = Field(default=900, ge=900)
    emergency_kill: bool = False


def expiry_at(option: Option) -> datetime:
    return datetime.combine(option.expiry, time(16), ZoneInfo("America/New_York"))


def liquid(option: Option, now: datetime, policy: Policy) -> bool:
    sizes = (option.bid_size or 0) >= policy.minimum_quote_size and (
        option.ask_size or 0) >= policy.minimum_quote_size
    oi = (option.open_interest or 0) >= policy.minimum_open_interest and (
        option.open_interest_date is not None and
        0 <= (now.date() - option.open_interest_date).days <= 3)
    return (option.spread_pct <= policy.max_spread_fraction
            and option.ask - option.bid <= policy.max_spread_dollars + 1e-9 and (sizes or oi))


def underlying(symbol: str) -> str:
    match = re.fullmatch(r"([A-Z]{1,6})\d{6}[CP]\d{8}", symbol)
    return match[1] if match else symbol


def validate(proposal: Proposal, state: MarketState, settings: Settings,
             policy: Policy, now: datetime) -> RiskResult:
    c, a = proposal.contract, state.account
    expiry_hours = (expiry_at(c) - now).total_seconds() / 3600 if c else -1
    max_new = min(a.equity * policy.per_trade_fraction, policy.per_trade_dollars)
    aggregate = sum(abs(p.cost_basis) for p in state.positions)
    start = datetime.fromisoformat(settings.phase1_official_start_utc.replace("Z", "+00:00"))
    end = datetime.fromisoformat(settings.phase1_official_end_utc.replace("Z", "+00:00"))
    active = [o for o in state.orders if o.status not in {"filled", "canceled", "expired", "rejected", "replaced"}]
    last_order = max((o.submitted_at for o in state.orders), default=datetime.min.replace(tzinfo=timezone.utc))
    checks: list[Gate] = []

    def gate(name: str, passed: bool, reason: str):
        checks.append(Gate(name=name, passed=bool(passed), reason=reason))

    gate("paper_only", settings.trading_mode == "paper" and settings.alpaca_paper_trade
         and not settings.allow_live_trading and not settings.live_trading_allowed,
         "Paper mode and both live flags disabled")
    gate("paper_endpoint", str(settings.alpaca_paper_base_url).rstrip("/") == PAPER_BASE_URL,
         "Exact paper execution host only")
    gate("dry_run_gate", not settings.execution_enabled, "Part 1 requires execution disabled")
    gate("account", a.status == "ACTIVE" and a.expected_account_match and not a.trading_blocked
         and a.options_trading_level >= 2 and a.equity > 0
         and all(isfinite(value) for value in (a.equity, a.cash, a.last_equity, a.buying_power)),
         "Dedicated active options-enabled account; finite account values")
    gate("competition_window", start <= now < end, "Official competition time bounds")
    gate("market", state.clock.is_open and 0 <= (now - state.clock.timestamp).total_seconds() <= 120,
         "Open market and fresh broker clock")
    gate("state_fresh", 0 <= (now - state.timestamp).total_seconds() <= policy.freshness_seconds,
         "Fresh account/position/order snapshot")
    gate("data_fresh", c is not None and state.features is not None and
         0 <= (now - c.quote_at).total_seconds() <= policy.freshness_seconds and
         0 <= (now - state.features.timestamp).total_seconds() <= policy.freshness_seconds,
         "Fresh underlying and option quote; future timestamps rejected")
    gate("valid_options", c is not None and c.tradable and c.underlying == "SPY"
         and c.multiplier == 100, "Active standard SPY options only")
    gate("proposal", proposal.status == "PROPOSED" and c is not None
         and proposal.quantity == 1 and proposal.estimated_max_loss == c.ask * 100,
         "One defined-risk long option with verified premium formula")
    gate("max_new_risk", 0 < proposal.estimated_max_loss <= max_new, f"Maximum new risk ${max_new:.2f}")
    gate("liquidity", c is not None and liquid(c, now, policy),
         "Spread <=10% and $0.15; both quote sizes >=5 or recent OI >=100")
    gate("expiry", policy.min_expiry_hours <= expiry_hours <= policy.max_expiry_days * 24,
         "24 hours minimum to standard expiry; maximum 7 days")
    gate("buying_power", a.options_buying_power is not None and
         proposal.estimated_max_loss <= min(a.cash, a.options_buying_power),
         "Both cash and options buying power cover full premium")
    gate("positions_limit", len(state.positions) < policy.max_positions, "At most three open positions")
    gate("aggregate_risk", aggregate + proposal.estimated_max_loss <= a.equity * policy.aggregate_fraction,
         "Aggregate paid premium <=2% of current equity")
    gate("underlying_exposure", not any(underlying(p.symbol) == proposal.underlying for p in state.positions),
         "Only one directional thesis per underlying; no hedge implementation yet")
    gate("duplicate_position", c is not None and not any(p.symbol == c.symbol for p in state.positions),
         "Cannot add to an existing contract")
    gate("duplicate_order", not any(o.client_order_id == f"thesiscircuit-phase2-{proposal.id}" for o in state.orders),
         "Unique proposal-derived future client ID; no order is constructed in Part 1")
    gate("conflicting_order", not active, "No outstanding orders may reserve unknown risk")
    gate("known_exposure", all(p.asset_class == "us_option" and p.side == "long"
         and p.qty > 0 and p.cost_basis > 0 for p in state.positions),
         "Reject unknown, short, non-option or malformed exposure")
    gate("cooldown", (now - last_order).total_seconds() >= policy.cooldown_seconds,
         "15-minute minimum since any broker submission")
    gate("daily_loss", a.last_equity > 0 and (a.last_equity - a.equity) / a.last_equity
         < policy.daily_drawdown_fraction, "Daily equity drawdown below 1%; missing baseline rejected")
    gate("kill_switch", not policy.emergency_kill, "Emergency research veto is not active")
    reasons = [g.name + ": " + g.reason for g in checks if not g.passed]
    return RiskResult(proposal_id=proposal.id, decision="REJECTED" if reasons else "APPROVED",
                      checks=checks, reasons=reasons)
