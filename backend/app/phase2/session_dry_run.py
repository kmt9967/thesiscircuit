"""Labelled synthetic full-coordinator exercise. No Alpaca transport is imported.

Market clock, bars, quotes, account and fills here are test fixtures, not real observations.
Only new SYNTHETIC sessions/intents are persisted; historical cycles/positions stay untouched.
"""
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, UUID, uuid5

from backend.app.models import AccountSnapshot, MarketClock
from backend.app.phase2.engine import assert_dry_run
from backend.app.phase2.execution_coordinator import BoundedExecutionCoordinator
from backend.app.phase2.execution_sessions import ExecutionSession
from backend.app.phase2.features import features
from backend.app.phase2.models import Bar, MarketState, Option, Position
from backend.app.phase2.order_intents import OrderClaimService


def synthetic_state(now, existing=False):
    # Known fixture contract; its symbol is never sent to a broker.
    expiry=(now+timedelta(days=3)).date()
    symbol=f"SPY{expiry:%y%m%d}C00768000"
    contract=Option(symbol=symbol,expiry=expiry,strike=768,kind="call",tradable=True,quote_at=now,
                    source="SYNTHETIC_NOT_MARKET_DATA",bid=1.8,ask=1.85,bid_size=10,ask_size=10)
    bars=[Bar(t=now-timedelta(minutes=30-i),o=765+i*.1,h=765.2+i*.1,l=764.9+i*.1,
              c=765.1+i*.1,v=100+i,vw=765.05+i*.1) for i in range(30)]
    f=features(bars,768,now,now)
    f.source="SYNTHETIC_NOT_MARKET_DATA"
    positions=[Position(symbol="SPY260904C00768000",qty=1,side="long",entry=1.84,current_price=1.84,
        market_value=184,cost_basis=184,unrealized_pl=0,unrealized_plpc=0,asset_class="us_option")] if existing else []
    return MarketState(timestamp=now,account=AccountSnapshot(status="ACTIVE",cash=100000,buying_power=100000,
        portfolio_value=100000,equity=100000,last_equity=100000,options_buying_power=100000,
        account_number_suffix="TEST",expected_account_match=True,trading_blocked=False,options_trading_level=3),
        clock=MarketClock(timestamp=now,is_open=True,next_open=now+timedelta(days=1),next_close=now+timedelta(hours=3)),
        positions=positions,orders=[],features=f,options=[contract])


class SyntheticProvider:
    def __init__(self, existing=False, clock=None):
        self.existing=existing
        self.clock=clock or (lambda:datetime.now(timezone.utc))
    async def refresh(self): return synthetic_state(self.clock(),self.existing)


class SyntheticCycleLease:
    """Test adapter only. Real coordinator uses the existing durable Phase2Repository.

    Session cycle IDs/cadence are still durable in the new table. This adapter avoids
    mutating the historical research-cycle singleton/tables during synthetic verification.
    """
    def __init__(self): self.owner=None
    async def acquire_lease(self,owner,seconds,cycle_id):
        if self.owner is not None: return False
        self.owner=owner
        return True
    async def release_lease(self,owner,outcome,cycle=None):
        if owner!=self.owner: raise RuntimeError("Synthetic cycle ownership lost")
        self.owner=None


class SyntheticSessionDispatcher:
    is_simulation=True
    def __init__(self, intents, gate, provider, settings, unknown=False, clock=None):
        self.intents,self.gate,self.provider,self.settings=intents,gate,provider,settings
        self.unknown=unknown
        self.clock=clock or (lambda:datetime.now(timezone.utc))

    async def dispatch(self,intent,owner,token=None):
        assert_dry_run(self.settings)
        if intent.classification!="SYNTHETIC": raise RuntimeError("Synthetic-only dispatcher")
        record=await self.intents.persist(intent,owner)
        record=await OrderClaimService(self.intents).claim(intent.id,owner)
        await self.gate.reserve(intent,owner)
        await self.gate.validate(intent,await self.provider.refresh(),self.clock())
        if record.attempt_count==0:
            await self.gate.submit(intent,owner,{"at":self.clock().isoformat(),
                **intent.risk.model_dump(mode="json"),"classification":"SYNTHETIC","broker_calls":0})
        await self.intents.advance(intent.id,owner,"RECONCILING")
        if self.unknown:
            return await self.intents.advance(intent.id,owner,"UNKNOWN",error="RECONCILIATION_REQUIRED")
        now=self.clock().isoformat()
        return await self.intents.advance(intent.id,owner,"FILLED",broker={
            "id":str(uuid5(intent.id,"synthetic-session-fill")),"client_order_id":intent.client_order_id,
            "symbol":intent.contracts[0],"side":intent.side,"quantity":intent.quantity,"status":"filled",
            "limit_price":str(intent.limit_price),"filled_qty":str(intent.quantity),
            "filled_avg_price":str(intent.limit_price),"submitted_at":now,"filled_at":now,
            "paper_mode":True,"classification":"SYNTHETIC"})


async def run_session_verification(sessions,intents,settings,batch,clock=None):
    assert_dry_run(settings)
    clock=clock or (lambda:datetime.now(timezone.utc))
    reports=[]
    for case in ("one_order_budget","existing_monitor_only","unknown_consumes_budget","expired_session"):
        expected={"one_order_budget":("COMPLETED",1),"existing_monitor_only":("COMPLETED",0),
                  "unknown_consumes_budget":("KILLED",1),"expired_session":("EXPIRED",0)}[case]
        async def verify_final(final,case=case,expected=expected):
            if (final.status,final.orders_consumed)!=expected or final.closing_consumed!=0:
                raise RuntimeError("Synthetic coordinator outcome mismatch")
            if final.document.classification!="SYNTHETIC": raise RuntimeError("Synthetic classification mismatch")
            if case=="unknown_consumes_budget" and final.kill_reason!="UNKNOWN_ORDER":
                raise RuntimeError("Synthetic UNKNOWN kill not proven")
            if len(final.reservations)!=expected[1]: raise RuntimeError("Synthetic reservation mismatch")
            for key in final.reservations:
                record=await intents.get(UUID(key))
                required="UNKNOWN" if case=="unknown_consumes_budget" else "FILLED"
                if (record.status!=required or record.attempt_count!=1 or record.alpaca_order_id is not None
                    or record.document.classification!="SYNTHETIC"):
                    raise RuntimeError("Synthetic lifecycle incomplete; no blind restart")
        identity=uuid5(NAMESPACE_URL,f"thesiscircuit:session-synthetic:{batch}:{case}")
        saved=await sessions.find(identity)
        if saved and saved.status in {"COMPLETED","KILLED","EXPIRED"}:
            await verify_final(saved)
            reports.append({"case":case,"session":saved.model_dump(mode="json"),"restart_skipped":True})
            continue
        now=clock()
        created=now-timedelta(minutes=2) if case=="expired_session" else now
        expires=now-timedelta(seconds=1) if case=="expired_session" else now+timedelta(minutes=15)
        definition=ExecutionSession(id=identity,created_at=created,starts_at=created,expires_at=expires,
            approval_equity=100000,classification="SYNTHETIC",entry_permission=True,max_cycles=1)
        if saved is None: await sessions.create(definition)
        await sessions.control(identity,"ACTIVATE")
        provider=SyntheticProvider(existing=case=="existing_monitor_only",clock=clock)
        def factory(gate,policy,case=case,provider=provider):
            return SyntheticSessionDispatcher(intents,gate,provider,settings,
                unknown=case=="unknown_consumes_budget",clock=clock)
        coordinator=BoundedExecutionCoordinator(sessions,SyntheticCycleLease(),intents,provider,factory,
                                                settings,synthetic=True,clock=clock)
        report=await coordinator.run(identity)
        final=await sessions.control(identity)
        await verify_final(final)
        reports.append({"case":case,"session":final.model_dump(mode="json"),"coordinator":report,"restart_skipped":False})
    from backend.app.phase2.session_budget_dry_run import run_budget_verification
    budgets=await run_budget_verification(sessions,intents,settings,batch,synthetic_state,clock)
    # Exercise recovery of this batch's UNKNOWN fixture using a new worker. No broker
    # lookup is performed: the deliberately unresolved test result stays UNKNOWN.
    unknown_id=uuid5(NAMESPACE_URL,f"thesiscircuit:session-synthetic:{batch}:unknown_consumes_budget")
    unknown_session=await sessions.control(unknown_id)
    intent_id=UUID(next(iter(unknown_session.reservations)))
    record=await intents.get(intent_id)
    replay=sum(e.get("kind")=="RECONCILING" for e in record.events)>=2
    if not replay:
        owner=uuid5(unknown_id,"synthetic-recovery-worker")
        await OrderClaimService(intents).claim(intent_id,owner)
        await intents.advance(intent_id,owner,"RECONCILING")
        record=await intents.advance(intent_id,owner,"UNKNOWN",error="RECONCILIATION_REQUIRED")
    retained=await sessions.control(unknown_id)
    if record.status!="UNKNOWN" or record.attempt_count!=1 or retained.orders_consumed!=1:
        raise RuntimeError("Synthetic uncertain-state recovery restored budget")
    return {"status":"completed","classification":"SYNTHETIC","broker_calls":0,
            "execution_enabled":False,"autonomous_trading_enabled":False,"batch":batch,"cases":reports,
            "budget_cases":budgets,"unknown_recovery":{"status":record.status,"attempt_count":record.attempt_count,
                "orders_consumed":retained.orders_consumed,"restart_skipped":replay,"broker_calls":0}}
