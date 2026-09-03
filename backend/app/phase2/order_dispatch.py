"""Server-only durable dispatcher. No route, cron, or research-loop call enables it.

An irreversible DB SUBMITTING transition authorizes at most ONE HTTP attempt.
Every recovery after that transition is GET-only, including a broker 404.
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import httpx

from backend.app.config import PAPER_BASE_URL, Settings
from backend.app.phase2.authorization import (
    authorization_gates,
    execution_preflight,
    exit_preflight,
)
from backend.app.phase2.execution_sessions import SessionDenied
from backend.app.phase2.models import Cycle, ExitProposal
from backend.app.phase2.order_intents import (
    SPENT,
    TERMINAL,
    IntentState,
    OrderClaimService,
    OrderIntent,
    OrderIntentService,
)
from backend.app.phase2.policy import Policy
from backend.app.services.alpaca import AlpacaClient


def normalize_order(raw: dict, intent: OrderIntent) -> tuple[str, dict]:
    """Strict identity/quantity matching; store only allowlisted broker fields."""
    order_id = str(UUID(raw["id"]))
    for field, expected in (("client_order_id", intent.client_order_id), ("symbol", intent.contracts[0]),
                            ("side", intent.side), ("type", "limit"), ("time_in_force", "day")):
        if raw[field] != expected:
            raise ValueError("Broker identity mismatch")
    if (Decimal(str(raw["qty"])) != intent.quantity
            or Decimal(str(raw["limit_price"])) != intent.limit_price):
        raise ValueError("Broker terms mismatch")
    qty = Decimal(str(raw["filled_qty"]))
    price = Decimal(str(raw["filled_avg_price"])) if raw.get("filled_avg_price") is not None else None
    if (not qty.is_finite() or qty != qty.to_integral_value() or not 0 <= qty <= intent.quantity
            or (qty > 0 and (price is None or not price.is_finite() or price <= 0))):
        raise ValueError("Malformed broker fill")
    status = raw["status"]
    terminal = {"filled": "FILLED", "canceled": "CANCELED", "rejected": "REJECTED", "expired": "EXPIRED"}
    if status == "filled" and (qty != intent.quantity or not raw.get("filled_at")):
        raise ValueError("Incomplete broker fill")
    if status in terminal:
        target = terminal[status]
    elif status in {"new", "accepted", "pending_new", "accepted_for_bidding", "partially_filled",
                    "pending_cancel", "pending_replace", "done_for_day"}:
        target = "SUBMITTED"
    else:
        target = "UNKNOWN"
    def stamp(value):
        if value is None:
            return None
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Broker timestamp missing timezone")
        return parsed.isoformat()
    return target, {"id": order_id, "client_order_id": intent.client_order_id,
        "symbol": intent.contracts[0], "side": intent.side, "quantity": intent.quantity,
        "limit_price": str(intent.limit_price), "status": status, "filled_qty": str(qty),
        "filled_avg_price": str(price) if price is not None else None,
        "submitted_at": stamp(raw["submitted_at"]), "filled_at": stamp(raw.get("filled_at")),
        "paper_mode": True, "classification": intent.classification}


class OrderReconciliationService:
    def __init__(self, repository: OrderIntentService, broker: AlpacaClient):
        self.repository, self.broker = repository, broker

    async def lookup(self, intent: OrderIntent) -> dict | None:
        if intent.classification != "PAPER":
            raise RuntimeError("Synthetic intents cannot contact Alpaca")
        response = await self.broker.client.get(f"{PAPER_BASE_URL}/v2/orders:by_client_order_id",
            params={"client_order_id": intent.client_order_id}, headers=self.broker.headers)
        if response.status_code == 404:
            return None  # Absence is NOT proof that an earlier POST was never accepted.
        response.raise_for_status()
        return response.json()

    async def reconcile(self, record: IntentState, owner: UUID) -> IntentState:
        if record.status in TERMINAL:
            return record
        await self.repository.advance(record.id, owner, "RECONCILING")
        try:
            raw = await self.lookup(record.document)
            if raw is None:
                raise ValueError("Unresolved absence")
            status, broker = normalize_order(raw, record.document)
        except (httpx.HTTPError, ValueError, TypeError, KeyError, ArithmeticError):
            return await self.repository.advance(record.id, owner, "UNKNOWN", error="RECONCILIATION_REQUIRED")
        return await self.repository.advance(record.id, owner, status, broker=broker)

    async def recover(self) -> list[IntentState]:
        """Bounded restart scan; no submission capability and no execution token needed.

        Live claims are left alone. Expired never-sent cycles are fenced/expired in SQL;
        all spent claims use client-ID lookup only. UNKNOWN retains the global barrier.
        """
        results = []
        for record in await self.repository.unresolved():
            if record.document.classification != "PAPER":
                raise RuntimeError("Recovery scan returned a non-broker fixture")
            if record.claim_expires_at and record.claim_expires_at > datetime.now(timezone.utc):
                continue
            owner = uuid4()
            claimed = await OrderClaimService(self.repository).claim(record.id,owner)
            if claimed.status in SPENT:
                results.append(await self.reconcile(claimed,owner))
            # Unspent records can only be dispatched by their current authorized cycle owner.
        return results


class PaperOrderDispatcher:
    def __init__(self, repository: OrderIntentService, broker: AlpacaClient, provider,
                 settings: Settings, policy: Policy, clock=None, session_gate=None):
        self.repository, self.broker, self.provider = repository, broker, provider
        self.settings, self.policy = settings, policy
        self.session_gate = session_gate
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.claims = OrderClaimService(repository)
        self.reconciliation = OrderReconciliationService(repository, broker)

    def authorize(self, token: str | None):
        if self.session_gate is None:
            raise RuntimeError("A durable execution-session budget gate is mandatory")
        s = self.settings
        if (s.trading_mode != "paper" or not s.alpaca_paper_trade or s.allow_live_trading
                or s.live_trading_allowed or str(s.alpaca_paper_base_url).rstrip("/") != PAPER_BASE_URL
                or not all(g.passed for g in authorization_gates(s, token))):
            raise RuntimeError("Paper dispatch authorization denied")

    async def dispatch_selected(self, cycle: Cycle, cycle_owner: UUID, token: str | None) -> IntentState:
        """Future server coordinator entry: selection + independent risk are mandatory.

        The caller must still own the durable cycle lease; SQL fences that ownership.
        No current research loop or HTTP route calls this method.
        """
        return await self.dispatch(OrderIntentService.selected(cycle), cycle_owner, token)

    async def dispatch(self, intent: OrderIntent, cycle_owner: UUID, token: str | None) -> IntentState:
        self.authorize(token)
        if intent.classification != "PAPER":
            raise RuntimeError("Synthetic records have no broker submission capability")
        # Revalidate the immutable Pydantic document, including after in-memory mutation.
        intent = OrderIntent.model_validate(intent.model_dump())
        record = await self.repository.persist(intent, cycle_owner)
        if record.status in TERMINAL:
            return record
        record = await self.claims.claim(intent.id, cycle_owner)
        if record.status in SPENT:
            return await self.reconciliation.reconcile(record, cycle_owner)
        try:
            await self.session_gate.reserve(intent,cycle_owner)
        except SessionDenied:
            return await self.repository.advance(intent.id,cycle_owner,"REJECTED",error="FINAL_PREFLIGHT_REJECTED")
        # A conflicting pre-existing CID is reconciled, never posted a second time.
        try:
            existing = await self.reconciliation.lookup(intent)
        except (httpx.HTTPError, ValueError, TypeError):
            return await self.repository.advance(intent.id, cycle_owner, "UNKNOWN", error="LOOKUP_UNCERTAIN")
        if existing is not None:
            return await self.reconciliation.reconcile(record, cycle_owner)
        state = await self.provider.refresh()
        now = self.clock()
        await self.session_gate.validate(intent,state,now)
        if any(not 0 <= (now - stamp).total_seconds() <= 120
               for stamp in (intent.created_at, intent.risk_approved_at)):
            return await self.repository.advance(intent.id, cycle_owner, "REJECTED", error="STALE_INTENT_OR_RISK")
        p = intent.proposal
        current = next((c for c in state.options if c.symbol == intent.contracts[0]), None)
        # Refresh quote metadata, but NEVER change persisted symbol/quantity/limit/risk.
        terms_ok = current is not None and (current.ask == float(intent.limit_price) if intent.action == "OPEN"
                                           else current.bid <= float(intent.limit_price) <= current.ask)
        if not terms_ok or any(o.client_order_id == intent.client_order_id for o in state.orders):
            return await self.repository.advance(intent.id, cycle_owner, "REJECTED", error="TERMS_CHANGED_OR_DUPLICATE")
        p = type(p).model_validate({**p.model_dump(), "contract": current.model_dump()})
        preflight = (exit_preflight(p, state, self.settings, self.policy, now, token)
                     if isinstance(p, ExitProposal) else
                     execution_preflight(p, state, self.settings, self.policy, now, token))
        if preflight.decision != "APPROVED":
            return await self.repository.advance(intent.id, cycle_owner, "REJECTED", error="FINAL_PREFLIGHT_REJECTED",
                                                  preflight=preflight.model_dump(mode="json"))
        self.authorize(token)
        # Atomic, fenced, non-replayable authorization. A lost ACK means NO HTTP call.
        await self.session_gate.submit(intent,cycle_owner,
            {"at": now.isoformat(), **preflight.model_dump(mode="json")})
        # No await between the final local checks and issuing the sole HTTP request.
        self.authorize(token)
        if not 0 <= (self.clock() - now).total_seconds() <= 2:
            return await self.repository.advance(intent.id, cycle_owner, "UNKNOWN", error="SEND_WINDOW_EXPIRED")
        try:
            response = await self.broker.client.post(f"{PAPER_BASE_URL}/v2/orders",
                json=intent.broker_payload(), headers=self.broker.headers, timeout=10.0, follow_redirects=False)
            response.raise_for_status()
            target, normalized = normalize_order(response.json(), intent)
        except (httpx.HTTPError, ValueError, TypeError, KeyError, ArithmeticError):
            # Including HTTP 4xx: do not assume no order, first query the deterministic CID.
            return await self.reconciliation.reconcile(await self.repository.get(intent.id), cycle_owner)
        return await self.repository.advance(intent.id, cycle_owner, target, broker=normalized)
