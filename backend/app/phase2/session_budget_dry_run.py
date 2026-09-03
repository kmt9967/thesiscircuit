"""Production RPC budget fixtures; no broker transport, credentials or order API.

SYNTHETIC protocol approvals below are fixtures, not market risk approvals.
Even the closing-budget test grants no authority over an actual position.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

from backend.app.phase2.engine import assert_dry_run, run_cycle
from backend.app.phase2.execution_sessions import ExecutionSession, SessionDenied
from backend.app.phase2.models import ExitProposal, Gate, RiskResult
from backend.app.phase2.order_intents import OrderClaimService, make_intent
from backend.app.phase2.policy import Policy


async def run_budget_verification(sessions,intents,settings,batch,state_factory,clock=None):
    assert_dry_run(settings)
    clock=clock or (lambda:datetime.now(timezone.utc))
    reports=[]
    for case in ("eight_worker_race","directional_budgets","expired_budget"):
        sid=uuid5(NAMESPACE_URL,f"thesiscircuit:session-budget-synthetic:{batch}:{case}")
        cycle_id=uuid5(sid,"budget-cycle")
        actions=["OPEN"]*8+["CLOSE"] if case=="eight_worker_race" else (
            ["OPEN","OPEN","CLOSE","CLOSE"] if case=="directional_budgets" else ["OPEN"])
        identities=[uuid5(NAMESPACE_URL,f"thesiscircuit:order:SYNTHETIC:{uuid5(sid,str(n))}:{action}")
                    for n,action in enumerate(actions)]
        saved=await sessions.find(sid)
        replay=saved is not None
        if saved is None:
            now=clock(); expired=case=="expired_budget"
            d=ExecutionSession(id=sid,created_at=now-timedelta(minutes=2) if expired else now,
                starts_at=now-timedelta(minutes=2) if expired else now,
                expires_at=now-timedelta(seconds=1) if expired else now+timedelta(minutes=15),
                approval_equity=100000,classification="SYNTHETIC",entry_permission=True,max_cycles=1,
                max_closing_orders=1 if case=="directional_budgets" else 0,
                max_total_orders=2 if case=="directional_budgets" else 1,
                exit_permission=case=="directional_budgets",allow_position_exit=case=="directional_budgets")
            await sessions.create(d); await sessions.control(sid,"ACTIVATE")
            if not expired: await sessions.control(sid,"CYCLE_START",cycle_key=cycle_id)
            state=state_factory(now)
            cycle=run_cycle(state,settings,Policy(),f"synthetic-budget:{sid}",0,[],[],now)
            selected=next((p for p in cycle.proposals if p.id==cycle.allocation.proposal_id),None)
            if selected is None or cycle.decision!="DRY_RUN_CANDIDATE":
                raise RuntimeError("Synthetic fixture proposal unavailable; no budget test")
            pairs=[]
            for n,action in enumerate(actions):
                owner=uuid5(sid,f"worker:{n}"); pid=uuid5(sid,str(n))
                p=(selected.model_copy(update={"id":pid}) if action=="OPEN" else
                   ExitProposal(id=pid,timestamp=now,contract=selected.contract,quantity=1,
                                limit_price=selected.contract.bid,rationale="SYNTHETIC closing-budget fixture only"))
                risk=RiskResult(proposal_id=pid,decision="APPROVED",checks=[Gate(
                    name="SYNTHETIC_PROTOCOL_ONLY",passed=True,reason="Fixture, not actual execution approval")],
                    reasons=["SYNTHETIC budget protocol, broker calls zero"])
                i=make_intent(cycle_id,p,risk,now,synthetic=True)
                assert i.id==identities[n] and i.classification=="SYNTHETIC"
                await intents.persist(i,owner); await OrderClaimService(intents).claim(i.id,owner)
                pairs.append((i,owner))
            async def reserve(pair,sid=sid):
                i,owner=pair
                try:
                    await sessions.gate(sid,i.id,owner,"RESERVE")
                    return "RESERVED"
                except SessionDenied as exc:
                    return str(exc)
            if case=="eight_worker_race":
                outcomes=await asyncio.gather(*(reserve(p) for p in pairs[:8]))
                if outcomes.count("RESERVED")!=1 or outcomes.count("ORDER_BUDGET_EXHAUSTED")!=7:
                    raise RuntimeError("Eight-worker production budget invariant failed")
                if await reserve(pairs[-1])!="SESSION_SCOPE": raise RuntimeError("Default exit scope was not blocked")
            else:
                outcomes=[await reserve(pair) for pair in pairs]
                expected=(["RESERVED","ORDER_BUDGET_EXHAUSTED","RESERVED","ORDER_BUDGET_EXHAUSTED"]
                          if case=="directional_budgets" else ["SESSION_INACTIVE"])
                if case=="expired_budget" and outcomes==["SESSION_EXPIRED"]: pass
                elif outcomes!=expected: raise RuntimeError("Synthetic directional/expiry gate mismatch")
            # End only these new never-submitted SYNTHETIC intent records; no broker cancellation.
            for i,owner in pairs:
                await intents.advance(i.id,owner,"REJECTED",error="FINAL_PREFLIGHT_REJECTED")
            if not expired:
                await sessions.control(sid,"CYCLE_END","NO_TRADE",cycle_id)
                await sessions.control(sid,"FINISH")
        final=await sessions.control(sid)
        records=[await intents.get(identity) for identity in identities]
        expected_counts={"eight_worker_race":(1,0,1),"directional_budgets":(1,1,2),"expired_budget":(0,0,0)}[case]
        if (final.opening_consumed,final.closing_consumed,final.orders_consumed)!=expected_counts:
            raise RuntimeError("Persisted budget counts invalid")
        if final.status!=("EXPIRED" if case=="expired_budget" else "COMPLETED"):
            raise RuntimeError("Incomplete synthetic budget batch; do not blindly retry")
        if any(r.status!="REJECTED" or r.attempt_count!=0 or r.alpaca_order_id is not None
               or r.document.classification!="SYNTHETIC" for r in records):
            raise RuntimeError("Synthetic budget records contain unexpected dispatch state")
        reserved=set(final.reservations)
        if len(reserved)!=expected_counts[2]: raise RuntimeError("Persisted reservations mismatch")
        if case=="eight_worker_race" and (sum(str(i) in reserved for i in identities[:8])!=1
                                          or str(identities[-1]) in reserved):
            raise RuntimeError("Persisted race/exit proof failed")
        reports.append({"case":case,"classification":"SYNTHETIC","broker_calls":0,
            "workers":8 if case=="eight_worker_race" else None,
            "budget_winners":len(reserved),"restart_skipped":replay,"session":final.model_dump(mode="json"),
            "intents":[{"id":str(r.id),"status":r.status,"attempt_count":r.attempt_count,
                        "alpaca_order_id":None} for r in records]})
    return reports
