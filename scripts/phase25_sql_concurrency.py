"""CI-only disposable PostgreSQL concurrency test. Never connects to Supabase/Alpaca."""
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4


def sql(query):
    return subprocess.run(["psql", "-X", "-v", "ON_ERROR_STOP=1", "-At"], input=query,
                          text=True, capture_output=True, check=False)


def main():
    if os.environ.get("CI") != "true" or os.environ.get("PGHOST") != "localhost":
        raise SystemExit("Disposable CI localhost database required")
    identity, owner = str(uuid4()), str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    document = {"id":identity, "cycle_id":identity, "proposal_id":identity, "risk_decision_id":identity,
        "action":"OPEN", "underlying":"SPY", "contracts":["SPY260904C00700000"], "side":"buy", "quantity":1,
        "order_type":"limit", "time_in_force":"day", "limit_price":"1.05", "client_order_id":f"tc-p2-{identity}",
        "expected_max_loss":"105", "created_at":now, "risk_approved_at":now, "paper_mode":True,
        "classification":"SYNTHETIC", "proposal":{"id":identity}, "risk":{"proposal_id":identity,
        "decision":"APPROVED","checks":[{"passed":True}]}}
    payload=json.dumps(document).replace("'", "''")
    result=sql(f"set role service_role; select public.phase2_create_order_intent('{payload}'::jsonb,'{owner}');")
    if result.returncode: raise RuntimeError("CI fixture persistence failed: "+result.stderr)

    def contender(_):
        worker=str(uuid4())
        return sql(f"begin; set local role service_role; select public.phase2_claim_order_intent('{identity}','{worker}');"
                   "select pg_sleep(0.5); commit;")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(contender,range(8)))
    if sum(r.returncode==0 for r in results)!=1:
        raise RuntimeError("Exactly one of eight concurrent SQL workers must win")
    if any("Intent already claimed" not in r.stderr for r in results if r.returncode):
        raise RuntimeError("Unexpected SQL contention failure")
    print("PASS: eight independent PostgreSQL sessions, exactly one claim winner; zero broker calls")

    # PAPER-labelled protocol fixtures exist only in this disposable CI database.
    # No broker transport is present. Verify the cross-intent barrier and lost-cycle fencing.
    cycle, worker = str(uuid4()), str(uuid4())
    result=sql(f"set role service_role; select public.phase2_acquire_lease('{worker}',180,'{cycle}');")
    if result.returncode or "t" not in result.stdout.splitlines(): raise RuntimeError("CI cycle lease failed")
    ids=[]
    for _ in range(2):
        identity=str(uuid4()); ids.append(identity)
        document.update(id=identity, cycle_id=cycle, proposal_id=identity,risk_decision_id=identity,
                        client_order_id=f"tc-p2-{identity}",classification="PAPER",proposal={"id":identity},
                        risk={"proposal_id":identity,"decision":"APPROVED","checks":[{"passed":True}]})
        payload=json.dumps(document).replace("'", "''")
        result=sql(f"set role service_role; select public.phase2_create_order_intent('{payload}'::jsonb,'{worker}');")
        if result.returncode: raise RuntimeError("CI PAPER protocol fixture failed")
    result=sql(f"set role service_role; select public.phase2_claim_order_intent('{ids[0]}','{worker}');")
    if result.returncode: raise RuntimeError("First paper claim failed")
    result=sql(f"set role service_role; select public.phase2_claim_order_intent('{ids[1]}','{worker}');")
    if result.returncode==0 or "phase2_one_active_paper_intent" not in result.stderr:
        raise RuntimeError("Account-wide intent barrier failed")
    # Emulate time passing in isolated CI fixtures, never in a production database.
    result=sql(f"update public.phase2_cycle_lease set expires_at=clock_timestamp()-interval '1 second' where singleton;"
               f"update public.phase2_order_intents set claim_expires_at=clock_timestamp()-interval '1 second' where id='{ids[0]}';"
               f"set role service_role; select public.phase2_claim_order_intent('{ids[0]}','{uuid4()!s}')->>'status';")
    if result.returncode or "EXPIRED" not in result.stdout.splitlines():
        raise RuntimeError("Never-sent orphan did not release the account barrier")
    print("PASS: account-wide PAPER intent exclusion and abandoned pre-send cycle recovery; zero broker calls")


if __name__ == "__main__":
    main()
