"""Session/coordinator failure injection; independent PostgreSQL tests prove atomicity."""
import asyncio
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.config import Settings
from backend.app.phase2.execution_coordinator import BoundedExecutionCoordinator, kill_condition
from backend.app.phase2.execution_sessions import (
    ExecutionSession,
    SessionDenied,
    SessionOrderGate,
    SessionState,
    session_scope,
)
from backend.app.phase2.session_dry_run import (
    SyntheticCycleLease,
    SyntheticProvider,
    SyntheticSessionDispatcher,
    run_session_verification,
)
from tests.test_order_dispatch import Harness, Store, intent
from tests.test_phase2 import NOW, position, state
from tests.test_phase2_readiness import authorized


def definition(**changes):
    return ExecutionSession(**{"id":uuid4(),"created_at":NOW,"starts_at":NOW,
        "expires_at":NOW+timedelta(minutes=15),"approval_equity":100000,"entry_permission":True,**changes})


def row(d=None):
    d=d or definition()
    return SessionState(id=d.id,document=d,status="ACTIVE",opening_consumed=0,closing_consumed=0,
        orders_consumed=0,new_risk_consumed=0,reservations={},broker_failures=[],cycles={},
        next_cycle_at=None,kill_reason=None,completed_at=None,events=[])


class Sessions:
    """Explicit unit-test double. It is not evidence of PostgreSQL concurrency."""
    def __init__(self, intents):
        self.rows={}; self.intents=intents; self.lock=asyncio.Lock(); self.now=NOW
    async def find(self,identity):
        return self.rows[identity].model_copy(deep=True) if identity in self.rows else None
    async def create(self,d):
        if d.id not in self.rows:
            self.rows[d.id]=row(d); self.rows[d.id].status="DRAFT"
        elif self.rows[d.id].document!=d: raise RuntimeError("Immutable conflict")
        return await self.find(d.id)
    async def control(self,identity,action="INSPECT",reason=None,cycle_key=None):
        async with self.lock:
            s=self.rows[identity]
            if s.status in {"DRAFT","ACTIVE"} and self.now>=s.document.expires_at:
                s.status="EXPIRED"; s.kill_reason="SESSION_EXPIRED"
            if s.status in {"EXPIRED","KILLED","COMPLETED"}: return await self.find(identity)
            if action=="ACTIVATE": s.status="ACTIVE"
            if action=="KILL": s.status="KILLED"; s.kill_reason=reason
            if action=="FINISH": s.status="COMPLETED"
            if action=="CYCLE_START":
                key=str(cycle_key)
                if key not in s.cycles:
                    if len(s.cycles)>=s.document.max_cycles or (s.next_cycle_at and self.now<s.next_cycle_at):
                        raise SessionDenied("Cycle budget/cadence exhausted")
                    s.cycles[key]={"status":"STARTED"}
                    s.next_cycle_at=self.now+timedelta(seconds=s.document.cadence_seconds)
            if action=="CYCLE_END": s.cycles[str(cycle_key)]={"status":reason}
            if action!="INSPECT": s.events.append({"kind":action})
            return await self.find(identity)
    async def gate(self,identity,intent_id,owner,action,preflight=None):
        async with self.lock:
            s=self.rows[identity]; r=self.intents.rows[intent_id]; i=r.document
            if action=="RESULT":
                if r.status=="UNKNOWN": s.status="KILLED"; s.kill_reason="UNKNOWN_ORDER"
                return {"allowed":True}
            if s.status!="ACTIVE" or self.now>=s.document.expires_at: raise SessionDenied("SESSION_EXPIRED")
            if str(i.cycle_id) not in s.cycles: raise SessionDenied("SESSION_CYCLE_REQUIRED")
            if action=="RESERVE":
                if str(i.id) in s.reservations: return {"allowed":True,"replayed":True}
                if (s.orders_consumed>=s.document.max_total_orders or
                    (i.action=="OPEN" and s.opening_consumed>=s.document.max_opening_orders) or
                    (i.action=="CLOSE" and s.closing_consumed>=s.document.max_closing_orders)):
                    raise SessionDenied("ORDER_BUDGET_EXHAUSTED")
                s.orders_consumed+=1
                if i.action=="OPEN": s.opening_consumed+=1
                else: s.closing_consumed+=1
                s.new_risk_consumed+=i.expected_max_loss; s.reservations[str(i.id)]={"risk":str(i.expected_max_loss)}
            if action=="SUBMIT":
                if str(i.id) not in s.reservations: raise SessionDenied("Budget required")
                if self.now+timedelta(seconds=15)>s.document.expires_at: raise SessionDenied("Near expiry")
                await self.intents.advance(i.id,owner,"SUBMITTING",preflight=preflight)
            return {"allowed":True}


@pytest.mark.parametrize("changes",[
    {"max_opening_orders":2},{"max_total_orders":2},{"max_closing_orders":1},
    {"exit_permission":True},{"expires_at":NOW+timedelta(hours=2)},
    {"expires_at":NOW},{"starts_at":NOW-timedelta(seconds=1)},
    {"paper_mode":False},{"approval_equity":90000},{"max_new_risk":501},
    {"daily_drawdown_fraction":.02},{"max_cycles":4},{"cadence_seconds":59},
    {"max_simultaneous_positions":4},{"allowed_underlyings":["QQQ"]},
])
def test_session_bounds_fail_closed(changes):
    with pytest.raises(ValidationError): definition(**changes)


def test_defaults_are_finite_and_existing_position_is_advisory_only():
    d=definition(entry_permission=False)
    assert d.manage_existing_position and not d.allow_position_exit and not d.exit_permission
    assert d.max_opening_orders==1 and d.max_closing_orders==0 and d.max_total_orders==1
    assert d.max_new_risk==500 and d.max_aggregate_premium_risk==2000 and d.max_cycles==3
    assert ExecutionSession.model_validate_json(d.model_dump_json())==d


@pytest.mark.parametrize("failure,reason",[
    ("expired","SESSION_INACTIVE"),("killed","SESSION_INACTIVE"),("entry","ENTRY_DISABLED"),
    ("close","EXIT_DISABLED"),("class","CLASSIFICATION_MISMATCH"),
    ("risk","NEW_RISK_BUDGET"),("aggregate","AGGREGATE_RISK"),("positions","MAX_POSITIONS"),
])
def test_independent_session_scope(failure,reason):
    s,i,m=row(),intent(),state()
    if failure=="expired": s.document.expires_at=NOW
    if failure=="killed": s.status="KILLED"
    if failure=="entry": s.document.entry_permission=False
    if failure=="close": i.action="CLOSE"
    if failure=="class": s.document.classification="SYNTHETIC"
    if failure=="risk": s.new_risk_consumed=Decimal(499)
    if failure=="aggregate": m.positions=[position(cost_basis=1999)]
    if failure=="positions": m.positions=[position()]*3
    assert reason in session_scope(s,i,m,NOW)


@pytest.mark.parametrize("failure,reason",[
    ("drawdown","DRAWDOWN"),("aggregate","AGGREGATE_RISK"),("positions","MAX_POSITIONS"),
    ("stale","STALE_DATA"),("live","LIVE_CONFIGURATION"),("endpoint","LIVE_CONFIGURATION"),
    ("account","CONFIG_MISMATCH"),("window","COMPETITION_CLOSED"),("market","MARKET_CLOSED"),
    ("broker","BROKER_FAILURES"),("manual","MANUAL_KILL"),
])
def test_kill_conditions(failure,reason):
    s,c,m,now=row(),Settings(),state(),NOW
    if failure=="drawdown": m.account.equity=98999
    if failure=="aggregate": m.positions=[position(cost_basis=2001)]
    if failure=="positions": m.positions=[position()]*3
    if failure=="stale": m.timestamp-=timedelta(minutes=3)
    if failure=="live": c.allow_live_trading=True
    if failure=="endpoint": c.alpaca_paper_base_url="https://"+"api.alpaca.markets"
    if failure=="account": m.account.expected_account_match=False
    if failure=="window": now+=timedelta(days=4)
    if failure=="market": m.clock.is_open=False
    if failure=="broker": s.broker_failures=["one","two"]
    if failure=="manual": c.phase2_emergency_kill=True
    assert kill_condition(m,c,s,now)==reason


def test_unit_budget_race_and_restart_do_not_restore_budget():
    async def run():
        store=Store(); sessions=Sessions(store); s=row(); sessions.rows[s.id]=s
        a,b=intent(),intent(); owner=uuid4()
        for i in (a,b):
            await store.persist(i,owner); s.cycles[str(i.cycle_id)]={"status":"STARTED"}
        outcomes=await asyncio.gather(*(sessions.gate(s.id,i.id,owner,"RESERVE") for i in (a,b)),return_exceptions=True)
        assert sum(isinstance(x,dict) for x in outcomes)==1 and s.orders_consumed==1
        winner=a if str(a.id) in s.reservations else b
        # New adapter over durable state; no budget refund or second claim.
        gate=SessionOrderGate(sessions,s.id)
        await gate.reserve(winner,owner)
        assert s.orders_consumed==1 and s.opening_consumed==1
    asyncio.run(run())


def test_dispatcher_requires_session_before_any_mock_broker_request():
    async def run():
        h=Harness(); h.d.session_gate=None
        with pytest.raises(RuntimeError,match="session"): await h.run()
        assert h.posts==h.gets==0
    asyncio.run(run())


def test_mock_broker_cannot_exceed_real_gate_adapter_budget_after_restart():
    async def run():
        h=Harness(); sessions=Sessions(h.store); s=row(); sessions.rows[s.id]=s
        s.cycles[str(h.i.cycle_id)]={"status":"STARTED"}
        h.d.session_gate=SessionOrderGate(sessions,s.id)
        assert (await h.run()).status=="FILLED"
        h.d.session_gate=SessionOrderGate(sessions,s.id)  # process adapter restart, durable row retained
        await h.run()
        h.i=intent(); s.cycles[str(h.i.cycle_id)]={"status":"STARTED"}
        assert (await h.run()).status=="REJECTED"
        assert h.posts==1 and s.orders_consumed==1
    asyncio.run(run())


def test_expiry_between_preflight_and_submit_is_fail_closed():
    async def run():
        h=Harness(); sessions=Sessions(h.store); s=row(); sessions.rows[s.id]=s
        s.cycles[str(h.i.cycle_id)]={"status":"STARTED"}
        gate=SessionOrderGate(sessions,s.id)
        original=gate.submit
        async def expire(i,owner,preflight):
            sessions.now=s.document.expires_at
            return await original(i,owner,preflight)
        gate.submit=expire; h.d.session_gate=gate
        with pytest.raises(SessionDenied): await h.run()
        assert h.posts==0 and s.orders_consumed==1
    asyncio.run(run())


@pytest.mark.parametrize("failure",["wrong_token","execution_disabled","autonomous_disabled","live"])
def test_coordinator_auth_before_provider_and_dispatch(failure):
    async def run():
        store=Store(); sessions=Sessions(store); s=row(); sessions.rows[s.id]=s
        cfg=authorized(); token=cfg.phase2_execution_token.get_secret_value()
        if failure=="wrong_token": token="wrong"
        if failure=="execution_disabled": cfg.execution_enabled=False
        if failure=="autonomous_disabled": cfg.autonomous_trading_enabled=False
        if failure=="live": cfg.allow_live_trading=True
        c=BoundedExecutionCoordinator(sessions,None,store,None,None,cfg,clock=lambda:NOW)
        with pytest.raises(SessionDenied): await c.run(s.id,token)
        assert s.status=="KILLED" and s.kill_reason=="AUTHORIZATION_DENIED" and not store.rows
    asyncio.run(run())


def test_four_synthetic_sessions_and_terminal_restart():
    async def run():
        intents=Store(); sessions=Sessions(intents)
        result=await run_session_verification(sessions,intents,Settings(),"unit-fixtures",clock=lambda:NOW)
        assert result["status"]=="completed" and result["broker_calls"]==0
        assert [(r["session"]["status"],r["session"]["orders_consumed"]) for r in result["cases"]]==[
            ("COMPLETED",1),("COMPLETED",0),("KILLED",1),("EXPIRED",0)]
        monitor=result["cases"][1]["coordinator"]["existing_position_actions"]
        assert monitor and all(not r["exit_allowed"] for r in monitor)
        assert all(r["session"]["closing_consumed"]==0 for r in result["cases"])
        events=[s.model_dump_json() for s in sessions.rows.values()]
        restart=await run_session_verification(sessions,intents,Settings(),"unit-fixtures",clock=lambda:NOW)
        assert all(r["restart_skipped"] for r in restart["cases"])
        assert events==[s.model_dump_json() for s in sessions.rows.values()]
    asyncio.run(run())


@pytest.mark.parametrize("failure",["database","cycle_overlap","stale"])
def test_cycle_failures_kill_without_intent(failure):
    async def run():
        intents=Store(); sessions=Sessions(intents); d=definition(classification="SYNTHETIC",max_cycles=1)
        await sessions.create(d); await sessions.control(d.id,"ACTIVATE")
        provider=SyntheticProvider(clock=lambda:NOW); cycles=SyntheticCycleLease()
        async def refresh():
            if failure=="database": raise RuntimeError("synthetic DB failure")
            s=state(); s.timestamp-=timedelta(minutes=10); return s
        if failure!="cycle_overlap": provider.refresh=refresh
        else: cycles.owner="another-worker"
        c=BoundedExecutionCoordinator(sessions,cycles,intents,provider,
            lambda g,p:SyntheticSessionDispatcher(intents,g,provider,Settings(),clock=lambda:NOW),
            Settings(),synthetic=True,clock=lambda:NOW)
        if failure=="stale": await c.run(d.id)
        else:
            with pytest.raises(RuntimeError): await c.run(d.id)
        s=await sessions.find(d.id)
        assert s.status=="KILLED" and not intents.rows and s.orders_consumed==0
    asyncio.run(run())
