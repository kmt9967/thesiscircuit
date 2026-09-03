"""Finite, server-owned execution authorization. No session is an execution toggle."""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from backend.app.phase2.models import MarketState, Record, Underlying
from backend.app.phase2.order_intents import OrderIntent
from backend.app.services.supabase import SupabaseAuditRepository


class ExecutionSession(Record):
    id: UUID
    created_at: AwareDatetime
    starts_at: AwareDatetime
    expires_at: AwareDatetime
    paper_mode: Literal[True] = True
    classification: Literal["PAPER", "SYNTHETIC"] = "PAPER"
    approval_equity: Decimal = Field(gt=0)
    max_opening_orders: int = Field(default=1, ge=0, le=1)
    max_closing_orders: int = Field(default=0, ge=0, le=3)
    max_total_orders: int = Field(default=1, ge=0, le=4)
    max_simultaneous_positions: int = Field(default=3, ge=1, le=3)
    max_new_risk: Decimal = Field(default=Decimal(500), ge=0, le=500)
    max_aggregate_premium_risk: Decimal = Field(default=Decimal(2000), gt=0)
    allowed_underlyings: list[Underlying] = Field(default_factory=lambda:["SPY"],min_length=1,max_length=2)
    allowed_strategy_types: list[Literal["LONG_CALL", "LONG_PUT"]] = Field(
        default_factory=lambda:["LONG_CALL","LONG_PUT"],min_length=1,max_length=2)
    entry_permission: bool = False
    exit_permission: bool = False
    manage_existing_position: bool = True
    allow_position_exit: bool = False
    existing_position_symbols: list[str] = Field(default_factory=lambda:["SPY260904C00768000"],max_length=3)
    daily_drawdown_fraction: float = Field(default=0.01,gt=0,le=0.01)
    cadence_seconds: int = Field(default=60,ge=60,le=3600)
    max_cycles: int = Field(default=3,ge=1,le=3)
    max_broker_failures: int = Field(default=2,ge=1,le=2)

    @model_validator(mode="after")
    def bounded(self):
        if len(set(self.allowed_underlyings)) != len(self.allowed_underlyings):
            raise ValueError("Duplicate underlying scope")
        if not self.created_at <= self.starts_at < self.expires_at:
            raise ValueError("Ordered finite session timestamps required")
        if not 1 <= (self.expires_at-self.created_at).total_seconds() <= 3600:
            raise ValueError("Session lifetime must be at most one hour")
        if self.max_total_orders > self.max_opening_orders+self.max_closing_orders:
            raise ValueError("Total budget exceeds directional budgets")
        if self.max_new_risk > self.approval_equity*Decimal("0.005"):
            raise ValueError("Session new premium cap exceeds 0.5% equity")
        if self.max_aggregate_premium_risk > self.approval_equity*Decimal("0.02"):
            raise ValueError("Aggregate cap exceeds 2% equity")
        if self.max_closing_orders and not (self.exit_permission and self.allow_position_exit):
            raise ValueError("Closing budget requires separate explicit exit permission")
        if self.exit_permission != self.allow_position_exit:
            raise ValueError("Both exit permissions must agree")
        return self


class SessionState(Record):
    id: UUID
    document: ExecutionSession
    status: Literal["DRAFT","ACTIVE","EXPIRED","KILLED","COMPLETED"]
    opening_consumed: int = Field(ge=0)
    closing_consumed: int = Field(ge=0)
    orders_consumed: int = Field(ge=0)
    new_risk_consumed: Decimal = Field(ge=0)
    reservations: dict
    broker_failures: list[str]
    cycles: dict
    next_cycle_at: AwareDatetime | None
    kill_reason: str | None
    completed_at: AwareDatetime | None
    events: list[dict]


class SessionDenied(RuntimeError):
    pass


class ExecutionSessionService(SupabaseAuditRepository):
    async def find(self, identity: UUID) -> SessionState | None:
        response=await self.client.get(f"{self.base}/phase2_execution_sessions",headers=self.headers,
            params={"select":"*","id":f"eq.{identity}"})
        response.raise_for_status()
        rows=response.json()
        if not isinstance(rows,list) or len(rows)>1: raise RuntimeError("Malformed session collection")
        return SessionState.model_validate(rows[0]) if rows else None

    async def call(self, name: str, payload: dict) -> dict:
        response=await self.client.post(f"{self.base}/rpc/{name}",json=payload,headers=self.headers)
        response.raise_for_status()
        value=response.json()
        if not isinstance(value,dict): raise TypeError("Malformed session acknowledgment")
        return value

    async def create(self, definition: ExecutionSession) -> SessionState:
        return SessionState.model_validate(await self.call("phase2_create_execution_session",{
            "document":definition.model_dump(mode="json")}))

    async def control(self, identity: UUID, action: str = "INSPECT", reason: str | None = None,
                      cycle_key: UUID | None = None) -> SessionState:
        return SessionState.model_validate(await self.call("phase2_session_control",{
            "session_id":str(identity),"action":action,"reason_code":reason,
            "cycle_key":str(cycle_key) if cycle_key else None}))

    async def gate(self, identity: UUID, intent: UUID, worker: UUID, action: str, preflight=None) -> dict:
        result=await self.call("phase2_session_order_gate",{"session_id":str(identity),
            "intent_id":str(intent),"worker":str(worker),"action":action,"preflight":preflight})
        if result.get("allowed") is not True:
            raise SessionDenied(result.get("reason","SESSION_DENIED"))
        return result


def session_scope(session: SessionState, intent: OrderIntent, state: MarketState, now: datetime) -> list[str]:
    """Additional session ceilings; never replaces the independent broker/risk preflight."""
    d=session.document
    reasons=[]
    if session.status!="ACTIVE" or not d.starts_at<=now<d.expires_at: reasons.append("SESSION_INACTIVE")
    if d.classification!=intent.classification: reasons.append("CLASSIFICATION_MISMATCH")
    if intent.underlying not in d.allowed_underlyings: reasons.append("UNDERLYING_SCOPE")
    strategy="LONG_CALL" if intent.proposal.contract.kind=="call" else "LONG_PUT"
    if strategy not in d.allowed_strategy_types: reasons.append("STRATEGY_SCOPE")
    if intent.action=="OPEN" and not d.entry_permission: reasons.append("ENTRY_DISABLED")
    if intent.action=="CLOSE":
        if not (d.exit_permission and d.allow_position_exit): reasons.append("EXIT_DISABLED")
        if intent.contracts[0] in d.existing_position_symbols and not d.manage_existing_position:
            reasons.append("EXISTING_POSITION_OUT_OF_SCOPE")
    equity=Decimal(str(state.account.equity))
    aggregate=Decimal(str(sum(abs(p.cost_basis) for p in state.positions)))
    if len(state.positions)+(1 if intent.action=="OPEN" else 0)>d.max_simultaneous_positions:
        reasons.append("MAX_POSITIONS")
    if intent.action=="OPEN":
        already_reserved=str(intent.id) in session.reservations
        risk=session.new_risk_consumed+(0 if already_reserved else intent.expected_max_loss)
        if risk>min(d.max_new_risk,equity*Decimal("0.005")): reasons.append("NEW_RISK_BUDGET")
        if aggregate+intent.expected_max_loss>min(d.max_aggregate_premium_risk,equity*Decimal("0.02")):
            reasons.append("AGGREGATE_RISK")
    return reasons


class SessionOrderGate:
    """The only production budget adapter accepted by the bounded coordinator."""
    def __init__(self, repository: ExecutionSessionService, identity: UUID):
        self.repository,self.identity=repository,identity

    async def reserve(self, intent: OrderIntent, owner: UUID):
        await self.repository.gate(self.identity,intent.id,owner,"RESERVE")

    async def validate(self, intent: OrderIntent, state: MarketState, now: datetime):
        session=await self.repository.control(self.identity)
        reasons=session_scope(session,intent,state,now)
        if reasons: raise SessionDenied(",".join(reasons))

    async def submit(self, intent: OrderIntent, owner: UUID, preflight: dict):
        # Session expiry/budget and the irreversible order transition share ONE DB transaction.
        await self.repository.gate(self.identity,intent.id,owner,"SUBMIT",preflight)

    async def result(self, intent: OrderIntent, owner: UUID):
        await self.repository.gate(self.identity,intent.id,owner,"RESULT")
