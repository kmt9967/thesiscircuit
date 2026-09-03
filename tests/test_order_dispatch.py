"""Failure injection with a deterministic in-memory SQL contract and mock HTTP.

The independent production SQL check verifies the real atomic functions/ACLs.
"""
import asyncio
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest

from backend.app.config import Settings
from backend.app.phase2.order_dispatch import PaperOrderDispatcher, normalize_order
from backend.app.phase2.order_intents import TERMINAL, IntentState, make_intent
from backend.app.phase2.policy import Policy, validate
from backend.app.services.alpaca import AlpacaClient
from tests.test_phase2 import NOW, proposal, state
from tests.test_phase2_readiness import authorized


class Store:
    def __init__(self):
        self.rows = {}
        self.lock = asyncio.Lock()
        self.cycle_valid = True
        self.crash_after_mark = False

    async def persist(self, intent, owner):
        async with self.lock:
            if intent.id in self.rows:
                r = self.rows[intent.id]
                if r.document != intent: raise RuntimeError("Immutable intent conflict")
                return r.model_copy(deep=True)
            self.rows[intent.id] = IntentState(id=intent.id, document=intent, status="PENDING",
                                               attempt_count=0, events=[{"kind":"PENDING"}])
            return self.rows[intent.id].model_copy(deep=True)

    async def get(self, identity):
        return self.rows[identity].model_copy(deep=True)

    async def unresolved(self):
        return [r.model_copy(deep=True) for r in self.rows.values() if r.status not in TERMINAL]

    async def rpc(self, name, payload):
        from uuid import UUID
        identity, owner = UUID(payload["intent_id"]), UUID(payload["worker"])
        assert name == "phase2_claim_order_intent"
        async with self.lock:
            r = self.rows[identity]
            if r.status in TERMINAL: return r.model_copy(deep=True)
            if r.owner_id is not None and r.owner_id != owner: raise RuntimeError("Claimed")
            if r.status in {"PENDING", "CLAIMED"} and not self.cycle_valid: raise RuntimeError("Cycle lease lost")
            for other in self.rows.values():
                if (r.document.classification=="PAPER" and other.document.classification=="PAPER"
                    and other.id != identity and other.status not in TERMINAL | {"PENDING"}):
                    raise RuntimeError("Account dispatch barrier")
            r.owner_id = owner
            if r.status == "PENDING": r.status = "CLAIMED"
            r.events.append({"kind":"CLAIM"})
            return r.model_copy(deep=True)

    async def advance(self, identity, owner, status, *, broker=None, error=None, preflight=None):
        async with self.lock:
            r = self.rows[identity]
            if r.owner_id != owner or r.status in TERMINAL: raise RuntimeError("Lost claim")
            if status == "SUBMITTING":
                if r.status != "CLAIMED" or r.attempt_count: raise RuntimeError("Already consumed")
                if not self.cycle_valid: raise RuntimeError("Cycle lease lost")
                assert preflight["decision"] == "APPROVED"
                r.attempt_count += 1
            r.status, r.last_error = status, error
            r.broker_state = broker or r.broker_state
            if broker and r.document.classification=="PAPER":
                from uuid import UUID
                r.alpaca_order_id = UUID(broker["id"])
            r.events.append({"kind":status})
            if status in TERMINAL | {"UNKNOWN", "SUBMITTED"}: r.owner_id = None
            if status == "SUBMITTING" and self.crash_after_mark:
                raise RuntimeError("Lost database ACK")
            return r.model_copy(deep=True)


def intent():
    p = proposal()
    return make_intent(uuid4(), p, validate(p,state(),Settings(),Policy(),NOW), NOW)


def raw_order(i, status="filled"):
    return {"id":str(uuid4()), "client_order_id":i.client_order_id, "symbol":i.contracts[0],
        "qty":str(i.quantity), "side":i.side, "type":"limit", "time_in_force":"day", "limit_price":str(i.limit_price),
        "status":status, "filled_qty":str(i.quantity) if status == "filled" else ("1" if status == "partially_filled" else "0"),
        "filled_avg_price":"1.84" if status in {"filled","partially_filled"} else None,
        "submitted_at":NOW.isoformat(), "filled_at":NOW.isoformat() if status == "filled" else None}


class Provider:
    def __init__(self): self.current = state()
    async def refresh(self): return self.current.model_copy(deep=True)


class ProtocolBudgetGate:
    """One-slot test adapter for the older order-protocol failure suite.

    Real PostgreSQL session budget semantics are tested separately in Phase 2.6.
    """
    def __init__(self, store): self.store,self.reserved=store,set()
    async def reserve(self, intent, owner):
        if self.reserved and intent.id not in self.reserved:
            from backend.app.phase2.execution_sessions import SessionDenied
            raise SessionDenied("ORDER_BUDGET_EXHAUSTED")
        self.reserved.add(intent.id)
    async def validate(self, intent, state, now): pass
    async def submit(self, intent, owner, preflight):
        assert intent.id in self.reserved
        return await self.store.advance(intent.id,owner,"SUBMITTING",preflight=preflight)


class Harness:
    def __init__(self, mode="filled"):
        self.i, self.store, self.cfg = intent(), Store(), authorized()
        self.owner, self.provider, self.mode = uuid4(), Provider(), mode
        if mode == "partially_filled":
            from backend.app.phase2.authorization import exit_preflight
            from backend.app.phase2.models import ExitProposal
            from tests.test_phase2 import option, position
            self.provider.current=state(positions=[position(qty=2,cost_basis=368)])
            p=ExitProposal(timestamp=NOW,contract=option(),quantity=2,limit_price=1.8,rationale="Synthetic partial exit")
            risk=exit_preflight(p,self.provider.current,self.cfg,Policy(),NOW,self.cfg.phase2_execution_token.get_secret_value())
            self.i=make_intent(uuid4(),p,risk,NOW)
        self.posts, self.gets, self.existing = 0, 0, None
        self.broker = AlpacaClient.__new__(AlpacaClient)
        self.broker.headers = {}
        self.broker.client = httpx.AsyncClient(transport=httpx.MockTransport(self.handle))
        self.d = PaperOrderDispatcher(self.store,self.broker,self.provider,self.cfg,Policy(),clock=lambda:NOW,
                                      session_gate=ProtocolBudgetGate(self.store))

    def handle(self, request):
        assert request.url.host == "paper-api.alpaca.markets"
        if request.method == "GET":
            self.gets += 1
            if self.mode == "lookup_error": return httpx.Response(503)
            return httpx.Response(200,json=self.existing) if self.existing is not None else httpx.Response(404)
        assert request.method == "POST" and request.url.path == "/v2/orders"
        self.posts += 1
        if self.mode in {"timeout_found", "crash_after_call", "malformed_found"}:
            self.existing = raw_order(self.i)
        if self.mode in {"timeout_found", "timeout_absent"}:
            raise httpx.ReadTimeout("synthetic timeout",request=request)
        if self.mode == "crash_after_call": raise asyncio.CancelledError()
        if self.mode.startswith("malformed"): return httpx.Response(200,json={"wrong":"shape"})
        return httpx.Response(200,json=raw_order(self.i,self.mode))

    async def run(self):
        return await self.d.dispatch(self.i,self.owner,self.cfg.phase2_execution_token.get_secret_value())


@pytest.mark.parametrize("mode,expected", [("filled","FILLED"),("rejected","REJECTED"),
    ("canceled","CANCELED"),("expired","EXPIRED"),("partially_filled","SUBMITTED"),
    ("new","SUBMITTED"),("timeout_found","FILLED"),("timeout_absent","UNKNOWN"),
    ("malformed_found","FILLED"),("malformed_absent","UNKNOWN"),("alien_status","UNKNOWN")])
def test_submission_outcomes_and_at_most_once(mode, expected):
    async def run():
        h=Harness(mode)
        result=await h.run()
        assert result.status == expected and h.posts == 1 and result.attempt_count == 1
        for _ in range(4): await h.run()
        assert h.posts == 1
    asyncio.run(run())


def test_duplicate_creation_and_conflicting_immutable_payload():
    async def run():
        h=Harness()
        results=await asyncio.gather(*[h.store.persist(h.i,h.owner) for _ in range(10)])
        assert len(h.store.rows)==1 and len({r.id for r in results})==1
        changed=h.i.model_copy(update={"cycle_id":uuid4()})
        with pytest.raises(RuntimeError): await h.store.persist(changed,h.owner)
    asyncio.run(run())


@pytest.mark.parametrize("same_owner",[True,False])
def test_concurrent_workers_cannot_duplicate(same_owner):
    async def run():
        h=Harness()
        async def second():
            return await h.d.dispatch(h.i,h.owner if same_owner else uuid4(),h.cfg.phase2_execution_token.get_secret_value())
        await asyncio.gather(h.run(),second(),return_exceptions=True)
        assert h.posts == 1
    asyncio.run(run())


@pytest.mark.parametrize("where",["before_claim", "claimed", "lost_db_ack", "crash_after_call"])
def test_restart_recovery(where):
    async def run():
        h=Harness("crash_after_call" if where=="crash_after_call" else "filled")
        await h.store.persist(h.i,h.owner)
        if where=="claimed": await h.d.claims.claim(h.i.id,h.owner)
        if where=="lost_db_ack":
            h.store.crash_after_mark=True
            with pytest.raises(RuntimeError): await h.run()
            h.store.crash_after_mark=False
        if where=="crash_after_call":
            with pytest.raises(asyncio.CancelledError): await h.run()
        # Simulate claim expiry / fresh process. SQL separately verifies the real expiry predicate.
        h.store.rows[h.i.id].owner_id=None
        h.owner=uuid4()
        result=await h.run()
        assert h.posts == (0 if where=="lost_db_ack" else 1)
        assert result.status == ("UNKNOWN" if where=="lost_db_ack" else "FILLED")
    asyncio.run(run())


def test_matching_existing_order_never_posts():
    async def run():
        h=Harness(); h.existing=raw_order(h.i)
        r=await h.run()
        assert r.status=="FILLED" and h.posts==0 and r.attempt_count==0
    asyncio.run(run())


@pytest.mark.parametrize("failure", ["stale_intent","expired_risk","lost_cycle","stale_quote",
    "execution_disabled","autonomous_disabled","wrong_token","live_endpoint","changed_price",
    "lookup_error","missing_risk","synthetic"])
def test_fail_closed_before_http_post(failure):
    async def run():
        h=Harness("lookup_error" if failure=="lookup_error" else "filled")
        if failure=="stale_intent": h.i.created_at-=timedelta(minutes=3)
        if failure=="expired_risk": h.i.risk_approved_at-=timedelta(minutes=3)
        if failure=="lost_cycle": h.store.cycle_valid=False
        if failure=="stale_quote": h.provider.current.options[0].quote_at-=timedelta(minutes=3)
        if failure=="execution_disabled": h.cfg.execution_enabled=False
        if failure=="autonomous_disabled": h.cfg.autonomous_trading_enabled=False
        if failure=="wrong_token": h.d.authorize("incorrect"); return
        if failure=="live_endpoint": h.cfg.alpaca_paper_base_url="https://"+"api.alpaca.markets"
        if failure=="changed_price": h.provider.current.options[0].ask=1.90
        if failure=="missing_risk": h.i.risk.decision="REJECTED"
        if failure=="synthetic": h.i.classification="SYNTHETIC"
        try: await h.run()
        except (RuntimeError,ValueError): pass
        assert h.posts==0
    if failure=="wrong_token":
        with pytest.raises(RuntimeError): asyncio.run(run())
    else: asyncio.run(run())


@pytest.mark.parametrize("field,value",[("client_order_id","different"),("symbol","OTHER"),
    ("qty","2"),("side","sell"),("limit_price","99"),("filled_qty","NaN"),("filled_qty","0.5"),
    ("filled_avg_price",None),("filled_at",None),("id","not-uuid")])
def test_malformed_identity_or_fill_rejected(field,value):
    i=intent(); raw=raw_order(i); raw[field]=value
    with pytest.raises((ValueError,TypeError)): normalize_order(raw,i)


def test_close_intent_remains_owned_reduce_only():
    from backend.app.phase2.authorization import exit_preflight
    from backend.app.phase2.models import ExitProposal
    from tests.test_phase2 import option, position
    cfg=authorized(); s=state(positions=[position()])
    p=ExitProposal(timestamp=NOW,contract=option(),quantity=1,limit_price=1.8,rationale="Synthetic advisory")
    risk=exit_preflight(p,s,cfg,Policy(),NOW,cfg.phase2_execution_token.get_secret_value())
    i=make_intent(uuid4(),p,risk,NOW)
    assert i.action=="CLOSE" and i.expected_max_loss==0 and i.broker_payload()["position_intent"]=="sell_to_close"


def test_unknown_barrier_prevents_another_logical_intent():
    async def run():
        h=Harness("timeout_absent"); await h.run()
        other=intent()
        with pytest.raises(RuntimeError):
            await h.d.dispatch(other,uuid4(),h.cfg.phase2_execution_token.get_secret_value())
        assert h.posts==1
    asyncio.run(run())


def test_selected_cycle_requires_allocator_and_approved_risk():
    from backend.app.phase2.engine import run_cycle
    from backend.app.phase2.order_intents import OrderIntentService
    cycle=run_cycle(state(),Settings(),Policy(),"synthetic-selection",0,[],[],NOW)
    assert OrderIntentService.selected(cycle).proposal_id == cycle.allocation.proposal_id
    cycle.allocation.decision="NO_TRADE"
    with pytest.raises(ValueError): OrderIntentService.selected(cycle)


def test_delayed_final_db_ack_never_posts():
    async def run():
        h=Harness()
        calls=0
        def clock():
            nonlocal calls
            calls+=1
            return NOW if calls==1 else NOW+timedelta(seconds=3)
        h.d.clock=clock
        record=await h.run()
        assert record.status=="UNKNOWN" and h.posts==0 and record.attempt_count==1
        await h.run()
        assert h.posts==0
    asyncio.run(run())


def test_restart_scan_reconciles_with_execution_disabled_and_never_posts():
    async def run():
        h=Harness("crash_after_call")
        with pytest.raises(asyncio.CancelledError): await h.run()
        h.store.rows[h.i.id].owner_id=None  # Simulate expired claim; SQL expiry is tested separately.
        h.cfg.execution_enabled=h.cfg.autonomous_trading_enabled=False
        result=await h.d.reconciliation.recover()
        assert len(result)==1 and result[0].status=="FILLED" and h.posts==1
        assert await h.d.reconciliation.recover()==[] and h.posts==1
    asyncio.run(run())


def test_restart_scan_skips_another_workers_live_claim():
    from datetime import datetime, timezone
    async def run():
        h=Harness()
        await h.store.persist(h.i,h.owner)
        await h.d.claims.claim(h.i.id,h.owner)
        h.store.rows[h.i.id].claim_expires_at=datetime.now(timezone.utc)+timedelta(seconds=30)
        assert await h.d.reconciliation.recover()==[]
        assert h.posts==h.gets==0
    asyncio.run(run())
