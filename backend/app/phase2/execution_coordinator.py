"""Bounded coordinator with injected dispatcher. No broker HTTP dependency here.

Production startup remains disabled. The only configured runner is SYNTHETIC.
"""
import asyncio
from contextlib import suppress
from datetime import datetime, timezone
from math import isfinite
from uuid import NAMESPACE_URL, uuid4, uuid5

from backend.app.config import DATA_BASE_URL, PAPER_BASE_URL
from backend.app.phase2.authorization import authorization_gates
from backend.app.phase2.engine import assert_dry_run, run_cycle, run_multi_underlying_cycle
from backend.app.phase2.execution_sessions import SessionDenied, SessionOrderGate, SessionState
from backend.app.phase2.order_intents import make_intent
from backend.app.phase2.policy import Policy


def paper_configuration(settings) -> bool:
    return not (settings.trading_mode!="paper" or not settings.alpaca_paper_trade or settings.allow_live_trading
        or settings.live_trading_allowed or str(settings.alpaca_paper_base_url).rstrip("/")!=PAPER_BASE_URL
        or str(settings.alpaca_data_base_url).rstrip("/")!=DATA_BASE_URL)


def kill_condition(state, settings, session: SessionState, now) -> str | None:
    d=session.document
    if not paper_configuration(settings): return "LIVE_CONFIGURATION"
    if settings.phase2_emergency_kill: return "MANUAL_KILL"
    if (not state.account.expected_account_match or state.account.status!="ACTIVE" or state.account.trading_blocked
        or state.account.options_trading_level<2 or not all(isfinite(v) for v in
        (state.account.equity,state.account.cash,state.account.last_equity,state.account.buying_power))):
        return "CONFIG_MISMATCH"
    start=datetime.fromisoformat(settings.phase1_official_start_utc.replace("Z","+00:00"))
    end=datetime.fromisoformat(settings.phase1_official_end_utc.replace("Z","+00:00"))
    if not start<=now<end: return "COMPETITION_CLOSED"
    if not state.clock.is_open: return "MARKET_CLOSED"
    if (state.data_errors or not state.features or not state.options
        or any(not 0<=(now-t).total_seconds()<=120 for t in
               [state.timestamp,state.clock.timestamp,state.features.timestamp]+[c.quote_at for c in state.options])):
        return "STALE_DATA"
    a=state.account
    if a.last_equity<=0 or (a.last_equity-a.equity)/a.last_equity>=d.daily_drawdown_fraction: return "DRAWDOWN"
    aggregate=sum(abs(p.cost_basis) for p in state.positions)
    if aggregate>min(float(d.max_aggregate_premium_risk),a.equity*.02): return "AGGREGATE_RISK"
    if len(state.positions)>=d.max_simultaneous_positions: return "MAX_POSITIONS"
    if len(session.broker_failures)>=d.max_broker_failures: return "BROKER_FAILURES"
    return None


def session_policy(session: SessionState) -> Policy:
    d=session.document
    return Policy(per_trade_dollars=max(.01,float(d.max_new_risk)),
                  max_positions=d.max_simultaneous_positions,
                  daily_drawdown_fraction=d.daily_drawdown_fraction)


class BoundedExecutionCoordinator:
    def __init__(self, sessions, cycles, intents, provider, dispatcher_factory, settings,
                 *, synthetic=False, clock=None, sleep=asyncio.sleep):
        self.sessions,self.cycles,self.intents=sessions,cycles,intents
        self.provider,self.dispatcher_factory,self.settings=provider,dispatcher_factory,settings
        self.synthetic=synthetic
        self.clock=clock or (lambda:datetime.now(timezone.utc))
        self.sleep=sleep

    async def _wait_for_cadence(self, session_id, token):
        """Wait in <=60s slices without ending a longer-cadence session early.

        Durable status/expiry and authorization are inspected on every slice, also
        after the final sleep. A stalled/backward clock fails closed, never spins.
        """
        while True:
            session=await self.sessions.control(session_id)
            if session.status!="ACTIVE": return session
            if self.settings.phase2_emergency_kill:
                return await self.sessions.control(session_id,"KILL","MANUAL_KILL")
            if self.synthetic:
                assert_dry_run(self.settings)
            elif (not paper_configuration(self.settings) or
                  not all(g.passed for g in authorization_gates(self.settings,token))):
                return await self.sessions.control(session_id,"KILL","AUTHORIZATION_DENIED")
            now=self.clock()
            if not session.document.starts_at<=now<session.document.expires_at:
                return await self.sessions.control(session_id,"KILL","SESSION_SCOPE")
            if not session.next_cycle_at or now>=session.next_cycle_at: return session
            if session.next_cycle_at>=session.document.expires_at:
                return await self.sessions.control(session_id,"FINISH")
            await self.sleep(min((session.next_cycle_at-now).total_seconds(),60))
            if self.clock()<=now:
                return await self.sessions.control(session_id,"KILL","CONFIG_MISMATCH")

    async def run(self, session_id, token=None) -> dict:
        report={"session_id":str(session_id),"classification":"SYNTHETIC" if self.synthetic else "PAPER",
                "cycles":[],"existing_position_actions":[],"broker_submission_authorized":False}
        session=await self.sessions.control(session_id)
        if session.document.classification!=report["classification"]:
            raise SessionDenied("Session/runner classification mismatch")
        if self.synthetic: assert_dry_run(self.settings)
        elif not paper_configuration(self.settings) or not all(g.passed for g in authorization_gates(self.settings,token)):
            await self.sessions.control(session_id,"KILL","AUTHORIZATION_DENIED")
            raise SessionDenied("Explicit server authorization and both execution flags required")
        if session.status!="ACTIVE": return {**report,"status":session.status}
        gate=SessionOrderGate(self.sessions,session_id)
        policy=session_policy(session)
        dispatcher=self.dispatcher_factory(gate,policy)
        if bool(getattr(dispatcher,"is_simulation",False))!=self.synthetic:
            raise SessionDenied("Dispatcher classification mismatch")
        # The pure research artifact has no execution authority; actual flags/token are
        # checked above, before each cycle, and independently by the final dispatcher.
        research_settings=self.settings.model_copy(update={"execution_enabled":False,"autonomous_trading_enabled":False})
        for sequence in range(session.document.max_cycles):
            session=await self.sessions.control(session_id)
            if session.status!="ACTIVE": break
            if not self.synthetic and any(r.status=="UNKNOWN" for r in await self.intents.unresolved()):
                await self.sessions.control(session_id,"KILL","UNKNOWN_ORDER"); break
            if not self.synthetic and (not paper_configuration(self.settings) or
                not all(g.passed for g in authorization_gates(self.settings,token))):
                await self.sessions.control(session_id,"KILL","AUTHORIZATION_DENIED"); break
            batch=f"session:{session_id}"
            cycle_id=uuid5(NAMESPACE_URL,f"thesiscircuit:phase2:{batch}:{sequence}")
            if str(cycle_id) in session.cycles: continue  # Never restore a used cycle after restart.
            if session.orders_consumed>=session.document.max_total_orders and session.document.max_total_orders>0:
                await self.sessions.control(session_id,"FINISH"); break
            now=self.clock()
            if not session.document.starts_at<=now<session.document.expires_at: break
            if session.next_cycle_at and now<session.next_cycle_at:
                session=await self._wait_for_cadence(session_id,token)
                if session.status!="ACTIVE": break
            owner=uuid4()
            try:
                if not await self.cycles.acquire_lease(str(owner),180,str(cycle_id)):
                    raise RuntimeError("Cycle lock unavailable")
                await self.sessions.control(session_id,"CYCLE_START",cycle_key=cycle_id)
                async def work(session=session, batch=batch, sequence=sequence, owner=owner):
                    if hasattr(self.provider, "refresh_all"):
                        states=await self.provider.refresh_all(session.document.allowed_underlyings)
                    else:
                        states=[await self.provider.refresh()]
                    for state in states:
                        reason=kill_condition(state,self.settings,session,self.clock())
                        if reason:
                            await self.sessions.control(session_id,"KILL",reason)
                            return None,None
                    cycle=(run_multi_underlying_cycle(states,research_settings,policy,batch,sequence,[],[],self.clock())
                           if len(states)>1 else
                           run_cycle(states[0],research_settings,policy,batch,sequence,[],[],self.clock()))
                    if session.document.manage_existing_position:
                        report["existing_position_actions"] += [{"symbol":r.position.symbol,
                            "recommendation":r.recommendation,"exit_allowed":False}
                            for r in cycle.position_reviews if r.position.symbol in session.document.existing_position_symbols]
                    result=None
                    if cycle.decision=="DRY_RUN_CANDIDATE" and session.document.entry_permission:
                        selected=next(p for p in cycle.proposals if p.id==cycle.allocation.proposal_id)
                        risk=next(r for r in cycle.risk if r.proposal_id==selected.id)
                        intent=make_intent(cycle.id,selected,risk,cycle.created_at,synthetic=self.synthetic)
                        result=await dispatcher.dispatch(intent,owner,token)
                        current=await self.sessions.control(session_id)
                        if str(intent.id) in current.reservations:
                            await gate.result(intent,owner)
                    return cycle,result
                cycle,result=await asyncio.wait_for(work(),150)
                if cycle is not None:
                    # Synthetic adapters do not write historical research tables.
                    await self.cycles.release_lease(str(owner),"COMPLETED",cycle)
                    await self.sessions.control(session_id,"CYCLE_END",
                        "ORDER_RECONCILED" if result else "NO_TRADE",cycle_id)
                    report["cycles"].append({"id":str(cycle.id),"decision":cycle.decision,
                        "stages":[x["stage"] for x in cycle.timeline],
                        "intent_id":str(result.id) if result else None,"intent_status":result.status if result else None})
                else:
                    await self.cycles.release_lease(str(owner),"FAILED")
                    break
            except SessionDenied:
                with suppress(Exception): await self.sessions.control(session_id,"KILL","SESSION_SCOPE")
                with suppress(Exception): await self.cycles.release_lease(str(owner),"FAILED")
                break
            except (Exception,asyncio.CancelledError):
                with suppress(Exception): await self.sessions.control(session_id,"KILL","DATABASE_FAILURE")
                with suppress(Exception): await self.cycles.release_lease(str(owner),"FAILED")
                raise
        session=await self.sessions.control(session_id)
        if session.status=="ACTIVE": session=await self.sessions.control(session_id,"FINISH")
        return {**report,"status":session.status,"orders_consumed":session.orders_consumed,
                "opening_consumed":session.opening_consumed,"closing_consumed":session.closing_consumed,
                "kill_reason":session.kill_reason}
