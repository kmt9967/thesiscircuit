from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ThesisRequest(BaseModel):
    symbol: str = Field(pattern=r"^[A-Z.]{1,10}$")
    strategy: Literal["defined-risk-call-spread", "defined-risk-put-spread"]
    max_loss_usd: float = Field(gt=0, le=1_000)
    days_to_expiry: int = Field(ge=7, le=45)
    confidence: float = Field(ge=0, le=1)
    data_age_seconds: int = Field(ge=0)


class RiskDecision(BaseModel):
    approved_for_research: bool
    mode: Literal["paper"] = "paper"
    vetoes: list[str]
    order_submission_enabled: Literal[False] = False


class MarketClock(BaseModel):
    timestamp: datetime
    is_open: bool
    next_open: datetime
    next_close: datetime


class AccountSnapshot(BaseModel):
    status: str
    cash: float
    buying_power: float
    portfolio_value: float
    equity: float
    last_equity: float
    options_buying_power: float | None = None
    account_number_suffix: str


class AssetSnapshot(BaseModel):
    symbol: str
    asset_class: str
    status: str
    tradable: bool
    options_enabled: bool = False


class QuoteSnapshot(BaseModel):
    symbol: str
    bid_price: float
    ask_price: float
    timestamp: datetime
    source: str

    @property
    def midpoint(self) -> float:
        return round((self.bid_price + self.ask_price) / 2, 2)


class OptionContract(BaseModel):
    symbol: str
    underlying_symbol: str
    expiration_date: str
    strike_price: float
    option_type: Literal["call", "put"]
    status: str
    tradable: bool


class TradeProposal(BaseModel):
    id: UUID
    trace_id: UUID
    created_at: datetime
    symbol: str
    instrument: str
    asset_class: Literal["us_option"] = "us_option"
    strategy_type: Literal["long_call"] = "long_call"
    side: Literal["buy"] = "buy"
    quantity: int = Field(default=1, ge=1, le=1)
    order_type: Literal["limit"] = "limit"
    time_in_force: Literal["day"] = "day"
    reference_price: float = Field(gt=0)
    limit_price: float = Field(gt=0)
    rationale: str
    invalidation: str
    confidence: float
    data_timestamp: datetime
    source: str
    estimated_max_loss: float = Field(gt=0)
    status: Literal["PROPOSED", "APPROVED", "REJECTED", "SUBMITTED"] = "PROPOSED"
    underlying: str
    expiry: str
    strike: float
    option_type: Literal["call"] = "call"
    legs: list[dict[str, Any]]
    debit: float
    max_theoretical_loss: float = Field(gt=0)
    max_theoretical_gain: str = "unbounded above strike, less premium"
    breakeven: float
    liquidity_metrics: dict[str, float]
    client_order_id: str
    paper: Literal[True] = True


class RiskGateCheck(BaseModel):
    name: str
    passed: bool
    detail: str


class ExecutionRiskDecision(BaseModel):
    id: UUID
    trace_id: UUID
    proposal_id: UUID
    created_at: datetime
    decision: Literal["APPROVED", "REJECTED"]
    checks: list[RiskGateCheck]
    max_simulated_risk: float


class PaperOrderRecord(BaseModel):
    proposal_id: UUID
    risk_check_id: UUID
    trace_id: UUID
    alpaca_order_id: str
    client_order_id: str
    submitted_at: datetime
    status: str
    instrument: str
    quantity: float
    filled_quantity: float
    filled_average_price: float | None = None
    filled_at: datetime | None = None
    paper: Literal[True] = True


class Phase1Preflight(BaseModel):
    proposal: TradeProposal
    risk: ExecutionRiskDecision
    account: AccountSnapshot
    clock: MarketClock
    open_orders: int
    open_positions: int


class DashboardState(BaseModel):
    generated_at: datetime
    paper: Literal[True] = True
    execution_enabled: bool
    account: AccountSnapshot | None = None
    integrations: dict[str, bool]
    latest_proposal: dict[str, Any] | None = None
    latest_risk: dict[str, Any] | None = None
    latest_order: dict[str, Any] | None = None
    latest_fill: dict[str, Any] | None = None
    latest_position: dict[str, Any] | None = None
    timeline: list[dict[str, Any]] = []

