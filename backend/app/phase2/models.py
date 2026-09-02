from __future__ import annotations

from datetime import date
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from backend.app.models import AccountSnapshot, MarketClock

RegimeName = Literal[
    "TREND_UP", "TREND_DOWN", "RANGE", "HIGH_VOLATILITY", "LOW_VOLATILITY", "UNCERTAIN"
]
AgentName = Literal["TREND", "RANGE", "DEFENSIVE"]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Bar(Record):
    t: AwareDatetime
    o: float = Field(gt=0)
    h: float = Field(gt=0)
    l: float = Field(gt=0)
    c: float = Field(gt=0)
    v: float = Field(ge=0)
    vw: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def valid_ohlc(self):
        if self.l > min(self.o, self.c) or self.h < max(self.o, self.c) or self.l > self.h:
            raise ValueError("Invalid OHLC range")
        return self


class Features(Record):
    timestamp: AwareDatetime
    bar_timestamp: AwareDatetime
    source: str
    price: float = Field(gt=0)
    return_1m: float
    return_20m: float
    ema_fast: float
    ema_slow: float
    rsi: float = Field(ge=0, le=100)
    atr: float = Field(ge=0)
    vwap: float | None
    volume: float
    relative_volume: float | None
    realized_volatility: float
    trend_strength: float
    intraday_range: float
    gap: float | None
    support: float
    resistance: float
    samples: int


class Option(Record):
    symbol: str = Field(pattern=r"^[A-Z]{1,6}\d{6}[CP]\d{8}$")
    underlying: Literal["SPY"] = "SPY"
    expiry: date
    strike: float = Field(gt=0)
    kind: Literal["call", "put"]
    tradable: bool
    multiplier: Literal[100] = 100
    quote_at: AwareDatetime
    source: str
    bid: float = Field(gt=0)
    ask: float = Field(gt=0)
    bid_size: float | None = Field(default=None, ge=0)
    ask_size: float | None = Field(default=None, ge=0)
    open_interest: float | None = Field(default=None, ge=0)
    open_interest_date: date | None = None
    volume: float | None = Field(default=None, ge=0)
    implied_volatility: float | None = Field(default=None, ge=0)
    delta: float | None = Field(default=None, ge=-1, le=1)
    gamma: float | None = Field(default=None, ge=0)
    theta: float | None = None
    vega: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def valid_contract(self):
        import re
        match = re.fullmatch(r"([A-Z]{1,6})(\d{6})([CP])(\d{8})", self.symbol)
        assert match
        if (match[1] != self.underlying or match[2] != self.expiry.strftime("%y%m%d")
                or match[3] != ("C" if self.kind == "call" else "P")
                or int(match[4]) / 1000 != self.strike or self.ask < self.bid):
            raise ValueError("Contract identity or quote inconsistent")
        return self

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread_pct(self) -> float:
        return (self.ask - self.bid) / self.mid


class Position(Record):
    symbol: str
    qty: float
    side: str
    entry: float = Field(ge=0)
    current_price: float = Field(ge=0)
    market_value: float
    cost_basis: float
    unrealized_pl: float
    unrealized_plpc: float
    asset_class: str


class OrderRead(Record):
    symbol: str
    client_order_id: str
    status: str
    submitted_at: AwareDatetime


class MarketState(Record):
    timestamp: AwareDatetime
    account: AccountSnapshot
    clock: MarketClock
    positions: list[Position]
    orders: list[OrderRead]
    features: Features | None = None
    options: list[Option] = Field(default_factory=list)
    data_errors: list[str] = Field(default_factory=list)


class Regime(Record):
    name: RegimeName
    confidence: float = Field(ge=0, le=1)
    timestamp: AwareDatetime
    metrics: dict[str, float | None]
    invalidation: str


class Proposal(Record):
    id: UUID = Field(default_factory=uuid4)
    agent: AgentName
    timestamp: AwareDatetime
    regime: RegimeName
    underlying: Literal["SPY"] = "SPY"
    contract: Option | None
    direction: Literal["BULLISH", "BEARISH", "NONE"]
    strategy_type: Literal["LONG_CALL", "LONG_PUT", "NO_TRADE"]
    confidence: float = Field(ge=0, le=1)
    thesis: str = Field(min_length=1)
    evidence: dict[str, float | str | None]
    invalidation: str
    holding_horizon: str = "Intraday research; no automatic exit is authorized"
    quantity: Literal[1] = 1
    estimated_max_loss: float = Field(ge=0)
    intrinsic: float | None = None
    extrinsic: float | None = None
    breakeven: float | None = None
    max_profit: float | None = None
    liquidity_assessment: str
    reasons_not_to_trade: list[str]
    status: Literal["PROPOSED", "NO_TRADE"]

    @model_validator(mode="after")
    def consistent(self):
        if self.status == "NO_TRADE":
            if self.contract or self.estimated_max_loss != 0 or self.strategy_type != "NO_TRADE":
                raise ValueError("NO_TRADE cannot allocate risk")
        elif not self.contract or abs(self.estimated_max_loss - self.contract.ask * 100) > 0.001:
            raise ValueError("Proposal risk must equal verified one-contract ask premium")
        elif (self.strategy_type != ("LONG_CALL" if self.contract.kind == "call" else "LONG_PUT")
              or self.direction != ("BULLISH" if self.contract.kind == "call" else "BEARISH")):
            raise ValueError("Direction must match contract")
        return self


class CriticReview(Record):
    proposal_id: UUID
    strongest_counterargument: str
    regime_contradiction: str
    volatility_risk: str
    liquidity_risk: str
    timing_risk: str
    expiration_theta_risk: str
    concentration_risk: str
    no_trade_argument: str
    severity: float = Field(ge=0, le=1)


class Allocation(Record):
    decision: Literal["SELECT", "NO_TRADE"]
    proposal_id: UUID | None = None
    reason: str
    scores: dict[str, float]


class Gate(Record):
    name: str
    passed: bool
    reason: str


class RiskResult(Record):
    proposal_id: UUID
    decision: Literal["APPROVED", "REJECTED"]
    checks: list[Gate]
    reasons: list[str]
    execution_authorized: Literal[False] = False


class Shadow(Record):
    id: UUID = Field(default_factory=uuid4)
    proposal_id: UUID
    agent: AgentName
    symbol: str
    timestamp: AwareDatetime
    entry_reference: float
    hypothetical_max_loss: float
    rejection_reason: str
    horizon_minutes: int = 60
    classification: Literal["COUNTERFACTUAL"] = "COUNTERFACTUAL"
    executed: Literal[False] = False


class ShadowMark(Record):
    shadow_id: UUID
    agent: AgentName
    timestamp: AwareDatetime
    bid_reference: float
    hypothetical_pnl: float
    risk_return: float
    decision_regret: float
    rejection_effect: Literal["HELPED", "HURT", "NEUTRAL"]
    horizon_complete: bool
    classification: Literal["COUNTERFACTUAL"] = "COUNTERFACTUAL"


class AgentScore(Record):
    agent: AgentName
    score: float = Field(ge=0, le=100)
    executed_samples: int = 0
    executed_realized_pnl: float | None = None
    executed_unrealized_pnl: float | None = None
    executed_hit_rate: float | None = None
    executed_risk_return: float | None = None
    executed_drawdown: float | None = None
    executed_thesis_accuracy: float | None = None
    shadow_samples: int = 0
    shadow_pnl: float | None = None
    shadow_false_positives: int = 0
    shadow_missed_opportunities: int = 0
    basis: str


class PositionReview(Record):
    timestamp: AwareDatetime
    position: Position
    quote: Option | None
    expiry: date | None
    hours_to_expiry: float | None
    theta_daily_dollars: float | None
    regime_compatible: bool | None
    thesis_invalidated: bool | None
    risk_limit_ok: bool
    recommendation: Literal["HOLD", "REDUCE", "EXIT", "EXPIRED", "RISK_ALERT"]
    reasons: list[str]
    action_authorized: Literal[False] = False


class Reflection(Record):
    shadow_id: UUID
    agent: AgentName
    timestamp: AwareDatetime
    expected: str
    observed: str
    lessons: dict[str, str]
    hard_limits_changed: Literal[False] = False


class Cycle(Record):
    id: UUID
    created_at: AwareDatetime
    batch: str
    sequence: int
    mode: Literal["DRY_RUN"] = "DRY_RUN"
    paper: Literal[True] = True
    execution_enabled: Literal[False] = False
    state: MarketState
    regime: Regime
    proposals: list[Proposal]
    critics: list[CriticReview]
    allocation: Allocation
    risk: list[RiskResult]
    decision: Literal["NO_TRADE", "DRY_RUN_CANDIDATE"]
    shadows: list[Shadow]
    marks: list[ShadowMark]
    scores: list[AgentScore]
    position_reviews: list[PositionReview]
    reflections: list[Reflection]
    timeline: list[dict[str, Any]]
