"""Durable paper-order records. SYNTHETIC records are never broker orders."""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import AwareDatetime, Field, model_validator

from backend.app.phase2.models import Cycle, ExitProposal, Proposal, Record, RiskResult
from backend.app.services.supabase import SupabaseAuditRepository

TERMINAL = {"FILLED", "CANCELED", "REJECTED", "EXPIRED"}
SPENT = {"SUBMITTING", "SUBMITTED", "RECONCILING", "UNKNOWN", *TERMINAL}


class OrderIntent(Record):
    id: UUID
    cycle_id: UUID
    proposal_id: UUID
    risk_decision_id: UUID
    action: Literal["OPEN", "CLOSE"]
    underlying: Literal["SPY"] = "SPY"
    contracts: list[str] = Field(min_length=1, max_length=1)
    side: Literal["buy", "sell"]
    quantity: int = Field(ge=1, le=3)
    order_type: Literal["limit"] = "limit"
    time_in_force: Literal["day"] = "day"
    limit_price: Decimal = Field(gt=0, decimal_places=2)
    client_order_id: str
    expected_max_loss: Decimal = Field(ge=0, le=500)
    created_at: AwareDatetime
    risk_approved_at: AwareDatetime
    paper_mode: Literal[True] = True
    classification: Literal["PAPER", "SYNTHETIC"] = "PAPER"
    proposal: Proposal | ExitProposal
    risk: RiskResult

    @model_validator(mode="after")
    def bindings(self):
        expected = uuid5(NAMESPACE_URL, f"thesiscircuit:order:{self.classification}:{self.proposal_id}:{self.action}")
        if self.id != expected or self.client_order_id != f"tc-p2-{expected}":
            raise ValueError("Non-deterministic intent identity")
        if self.proposal.id != self.proposal_id or self.risk.proposal_id != self.proposal_id:
            raise ValueError("Proposal/risk identity mismatch")
        if self.risk.decision != "APPROVED" or not self.risk.checks or not all(g.passed for g in self.risk.checks):
            raise ValueError("Independent risk approval required")
        p = self.proposal
        if p.contract is None or self.contracts != [p.contract.symbol] or p.quantity != self.quantity:
            raise ValueError("Contract or quantity mismatch")
        if self.action == "OPEN":
            if (not isinstance(p, Proposal) or self.side != "buy" or self.quantity != 1
                    or self.limit_price != Decimal(str(p.contract.ask))
                    or self.expected_max_loss != self.limit_price * 100):
                raise ValueError("Only one bounded long option entry")
        elif (not isinstance(p, ExitProposal) or self.side != "sell"
              or self.limit_price != Decimal(str(p.limit_price)) or self.expected_max_loss != 0):
            raise ValueError("Only an owned-position reducing exit")
        return self

    def broker_payload(self) -> dict:
        return {"symbol": self.contracts[0], "qty": str(self.quantity), "side": self.side,
                "type": self.order_type, "time_in_force": self.time_in_force,
                "limit_price": str(self.limit_price), "client_order_id": self.client_order_id,
                "position_intent": "buy_to_open" if self.action == "OPEN" else "sell_to_close"}


class IntentState(Record):
    id: UUID
    document: OrderIntent
    status: Literal["PENDING", "CLAIMED", "SUBMITTING", "SUBMITTED", "RECONCILING",
                    "FILLED", "CANCELED", "REJECTED", "EXPIRED", "UNKNOWN"]
    owner_id: UUID | None = None
    claim_expires_at: AwareDatetime | None = None
    claimed_at: AwareDatetime | None = None
    submitted_at: AwareDatetime | None = None
    reconciled_at: AwareDatetime | None = None
    attempt_count: int = Field(ge=0, le=1)
    alpaca_order_id: UUID | None = None
    last_error: str | None = None
    broker_state: dict | None = None
    events: list[dict]


class OrderIntentService(SupabaseAuditRepository):
    @staticmethod
    def selected(cycle: Cycle) -> OrderIntent:
        cycle = Cycle.model_validate(cycle.model_dump())
        if cycle.decision != "DRY_RUN_CANDIDATE" or cycle.allocation.decision != "SELECT":
            raise ValueError("A validated selected cycle is required")
        proposals = [p for p in cycle.proposals if p.id == cycle.allocation.proposal_id]
        risks = [r for r in cycle.risk if r.proposal_id == cycle.allocation.proposal_id]
        if len(proposals) != 1 or len(risks) != 1:
            raise ValueError("Unambiguous selected proposal and risk required")
        return make_intent(cycle.id, proposals[0], risks[0], cycle.created_at)

    async def rpc(self, name: str, payload: dict) -> IntentState:
        response = await self.client.post(f"{self.base}/rpc/{name}", json=payload, headers=self.headers)
        response.raise_for_status()
        return IntentState.model_validate(response.json())

    async def persist(self, intent: OrderIntent, owner: UUID) -> IntentState:
        return await self.rpc("phase2_create_order_intent", {
            "document": intent.model_dump(mode="json"), "cycle_owner": str(owner)})

    async def get(self, intent_id: UUID) -> IntentState:
        result = await self.find(intent_id)
        if result is None:
            raise RuntimeError("Intent missing")
        return result

    async def find(self, intent_id: UUID) -> IntentState | None:
        response = await self.client.get(f"{self.base}/phase2_order_intents", headers=self.headers,
                                         params={"id": f"eq.{intent_id}", "select": "*"})
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list) or len(rows) > 1:
            raise RuntimeError("Intent collection malformed or ambiguous")
        return IntentState.model_validate(rows[0]) if rows else None

    async def unresolved(self) -> list[IntentState]:
        response = await self.client.get(f"{self.base}/phase2_order_intents", headers=self.headers,
            params={"select":"*", "document->>classification":"eq.PAPER",
                    "status":"not.in.(FILLED,CANCELED,REJECTED,EXPIRED)", "limit":101})
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows,list) or len(rows)>100:
            raise RuntimeError("Unresolved intent scan is malformed or exceeds bounded recovery budget")
        return [IntentState.model_validate(row) for row in rows]

    async def advance(self, intent_id: UUID, owner: UUID, status: str, *,
                      broker: dict | None = None, error: str | None = None,
                      preflight: dict | None = None) -> IntentState:
        return await self.rpc("phase2_advance_order_intent", {
            "intent_id": str(intent_id), "worker": str(owner), "target": status,
            "broker": broker, "error_code": error, "preflight": preflight})


class OrderClaimService:
    def __init__(self, repository: OrderIntentService):
        self.repository = repository

    async def claim(self, intent_id: UUID, owner: UUID) -> IntentState:
        return await self.repository.rpc("phase2_claim_order_intent", {
            "intent_id": str(intent_id), "worker": str(owner)})


def make_intent(cycle_id: UUID, proposal: Proposal | ExitProposal, risk: RiskResult,
                approved_at: datetime, *, synthetic: bool = False) -> OrderIntent:
    action = "CLOSE" if isinstance(proposal, ExitProposal) else "OPEN"
    classification = "SYNTHETIC" if synthetic else "PAPER"
    identity = uuid5(NAMESPACE_URL, f"thesiscircuit:order:{classification}:{proposal.id}:{action}")
    risk_id = uuid5(identity, risk.model_dump_json())
    return OrderIntent(id=identity, cycle_id=cycle_id, proposal_id=proposal.id, risk_decision_id=risk_id,
        action=action, side="sell" if action == "CLOSE" else "buy", contracts=[proposal.contract.symbol],
        quantity=proposal.quantity, limit_price=Decimal(str(proposal.limit_price if action == "CLOSE"
                                                          else proposal.contract.ask)),
        expected_max_loss=0 if action == "CLOSE" else Decimal(str(proposal.estimated_max_loss)),
        client_order_id=f"tc-p2-{identity}", created_at=approved_at, risk_approved_at=approved_at,
        classification=classification, proposal=proposal, risk=risk)
