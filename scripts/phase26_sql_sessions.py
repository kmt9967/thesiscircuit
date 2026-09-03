"""CI-only real PostgreSQL finite-session tests. No network/broker transport exists.

Every generated row is a labelled SYNTHETIC fixture in the disposable localhost DB.
Production must use the separate server-side synthetic runner, never this script.
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from phase25_sql_concurrency import sql


def query(expression,role=True):
    r=sql(("set role service_role; " if role else "")+"select "+expression+";")
    if r.returncode: raise RuntimeError(r.stderr)
    return json.loads(r.stdout.splitlines()[-1])


def value(d): return "'"+json.dumps(d).replace("'","''")+"'::jsonb"


def session(**changes):
    now=datetime.now(timezone.utc)
    d={"id":str(uuid4()),"created_at":now.isoformat(),"starts_at":now.isoformat(),
       "expires_at":(now+timedelta(minutes=15)).isoformat(),"paper_mode":True,"classification":"SYNTHETIC",
       "approval_equity":"100000","max_opening_orders":1,"max_closing_orders":0,"max_total_orders":1,
       "max_simultaneous_positions":3,"max_new_risk":"500","max_aggregate_premium_risk":"2000",
       "allowed_underlyings":["SPY"],"allowed_strategy_types":["LONG_CALL","LONG_PUT"],
       "entry_permission":True,"exit_permission":False,"manage_existing_position":True,"allow_position_exit":False,
       "existing_position_symbols":["SPY260904C00768000"],"daily_drawdown_fraction":.01,
       "cadence_seconds":60,"max_cycles":3,"max_broker_failures":2,**changes}
    r=query(f"public.phase2_create_execution_session({value(d)})")
    assert r["status"]=="DRAFT"
    assert query(f"public.phase2_create_execution_session({value(d)})")==r
    query(f"public.phase2_session_control('{d['id']}','ACTIVATE')")
    return d["id"]


def start(s,cycle): return query(f"public.phase2_session_control('{s}','CYCLE_START',null,'{cycle}')")
def inspect(s): return query(f"public.phase2_session_control('{s}','INSPECT')")


def intent(cycle,side="OPEN"):
    identity,owner=str(uuid4()),str(uuid4()); now=datetime.now(timezone.utc).isoformat()
    d={"id":identity,"cycle_id":cycle,"proposal_id":identity,"risk_decision_id":identity,
       "action":side,"underlying":"SPY","contracts":["SPY260904C00768000"],
       "side":"buy" if side=="OPEN" else "sell","quantity":1,"order_type":"limit","time_in_force":"day",
       "limit_price":"1.85","client_order_id":f"tc-p2-{identity}","expected_max_loss":"185" if side=="OPEN" else "0",
       "created_at":now,"risk_approved_at":now,"paper_mode":True,"classification":"SYNTHETIC",
       "proposal":{"id":identity,"contract":{"kind":"call"}},
       "risk":{"proposal_id":identity,"decision":"APPROVED","checks":[{"passed":True}]}}
    query(f"public.phase2_create_order_intent({value(d)},'{owner}')")
    query(f"public.phase2_claim_order_intent('{identity}','{owner}')")
    return identity,owner


def gate(s,i,owner,action):
    preflight="jsonb_build_object('at',clock_timestamp(),'decision','APPROVED','checks','[{\"passed\":true}]'::jsonb)"
    return query(f"public.phase2_session_order_gate('{s}','{i}','{owner}','{action}',{preflight})")


def advance(i,owner,target,error="null"):
    return query(f"public.phase2_advance_order_intent('{i}','{owner}','{target}',null,{error})")


def main():
    if os.environ.get("CI")!="true" or os.environ.get("PGHOST")!="localhost":
        raise SystemExit("Disposable CI localhost database required")
    session(allowed_underlyings=["QQQ"])
    session(allowed_underlyings=["SPY", "QQQ"])
    bad={"allowed_underlyings":["IWM"]}
    # Build a complete document without invoking the helper, which expects success.
    now=datetime.now(timezone.utc)
    invalid={"id":str(uuid4()),"created_at":now.isoformat(),"starts_at":now.isoformat(),
        "expires_at":(now+timedelta(minutes=15)).isoformat(),"paper_mode":True,"classification":"SYNTHETIC",
        "approval_equity":"100000","max_opening_orders":1,"max_closing_orders":0,"max_total_orders":1,
        "max_simultaneous_positions":3,"max_new_risk":"500","max_aggregate_premium_risk":"2000",
        "allowed_strategy_types":["LONG_CALL"],"entry_permission":True,"exit_permission":False,
        "manage_existing_position":True,"allow_position_exit":False,"existing_position_symbols":[],
        "daily_drawdown_fraction":.01,"cadence_seconds":60,"max_cycles":1,"max_broker_failures":1,**bad}
    denied=sql("set role service_role; select public.phase2_create_execution_session("+value(invalid)+");")
    assert denied.returncode!=0
    print("PASS: immutable session scope accepts SPY/QQQ subsets and rejects unsupported underlyings")
    s=session(); cycle=str(uuid4()); start(s,cycle)
    candidates=[intent(cycle) for _ in range(8)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        result=list(pool.map(lambda pair:gate(s,*pair,"RESERVE"),candidates))
    assert sum(r["allowed"] for r in result)==1
    winner=candidates[next(n for n,r in enumerate(result) if r["allowed"])]
    saved=inspect(s)
    assert saved["orders_consumed"]==saved["opening_consumed"]==1 and saved["closing_consumed"]==0
    assert len(saved["reservations"])==1 and float(saved["new_risk_consumed"])==185
    assert gate(s,*winner,"RESERVE")["replayed"] and inspect(s)==saved
    print("PASS: eight independent SQL workers race for final session slot; exactly one budget winner; restart retains spend")

    # One irreversible submit transition; no HTTP, no broker credentials.
    assert gate(s,*winner,"SUBMIT")["intent"]["attempt_count"]==1
    try: gate(s,*winner,"SUBMIT")
    except RuntimeError as e: assert "Submission already consumed" in str(e)
    else: raise AssertionError("Duplicate submit transition")
    advance(*winner,"RECONCILING")
    advance(*winner,"UNKNOWN","'RECONCILIATION_REQUIRED'")
    gate(s,*winner,"RESULT")
    killed=inspect(s)
    assert killed["status"]=="KILLED" and killed["kill_reason"]=="UNKNOWN_ORDER"
    assert killed["orders_consumed"]==1 and not gate(s,*candidates[1],"RESERVE")["allowed"]
    # Reconciliation remains possible after session kill/expiry, never a resend.
    new_owner=str(uuid4())
    query(f"public.phase2_claim_order_intent('{winner[0]}','{new_owner}')")
    advance(winner[0],new_owner,"RECONCILING")
    advance(winner[0],new_owner,"UNKNOWN","'RECONCILIATION_REQUIRED'")
    assert inspect(s)["orders_consumed"]==1
    print("PASS: UNKNOWN kills session and permanently retains budget; reconciliation allowed, second submit forbidden")

    s=session(); cycle=str(uuid4()); start(s,cycle); i,o=intent(cycle,"CLOSE")
    assert gate(s,i,o,"RESERVE")["reason"]=="SESSION_SCOPE" and inspect(s)["orders_consumed"]==0
    detached,owner=intent(str(uuid4()))
    assert gate(s,detached,owner,"RESERVE")["reason"]=="SESSION_CYCLE_REQUIRED"
    try: start(s,str(uuid4()))
    except RuntimeError as e: assert "cadence exhausted" in str(e)
    else: raise AssertionError("Cadence bypass")
    print("PASS: existing SPY exit disabled; detached cycle blocked; cycle cadence durable")

    now=datetime.now(timezone.utc)
    expired=session(created_at=(now-timedelta(minutes=2)).isoformat(),starts_at=(now-timedelta(minutes=2)).isoformat(),
                    expires_at=(now-timedelta(seconds=1)).isoformat())
    assert inspect(expired)["status"]=="EXPIRED"
    near=session(expires_at=(datetime.now(timezone.utc)+timedelta(seconds=12)).isoformat())
    c=str(uuid4()); start(near,c); i,o=intent(c); assert gate(near,i,o,"RESERVE")["allowed"]
    assert gate(near,i,o,"SUBMIT")["reason"]=="SESSION_NEAR_EXPIRY"
    assert inspect(near)["orders_consumed"]==1
    print("PASS: expired session inert; near-expiry order blocked without refunding budget")

    # Independent opening cap even when separately permitted closing slots remain.
    s=session(max_closing_orders=1,max_total_orders=2,exit_permission=True,allow_position_exit=True)
    c=str(uuid4()); start(s,c); first=intent(c); second=intent(c)
    assert gate(s,*first,"RESERVE")["allowed"]
    assert gate(s,*second,"RESERVE")["reason"]=="ORDER_BUDGET_EXHAUSTED"
    close=intent(c,"CLOSE"); assert gate(s,*close,"RESERVE")["allowed"]
    assert inspect(s)["orders_consumed"]==2 and inspect(s)["closing_consumed"]==1
    assert not gate(s,*intent(c,"CLOSE"),"RESERVE")["allowed"]
    print("PASS: independent opening, closing and total budgets; explicit close permission required; broker calls zero")


if __name__=="__main__": main()
