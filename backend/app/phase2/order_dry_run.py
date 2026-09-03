"""Labelled DB protocol exercise. No Alpaca import/client or submission capability.

Synthetic risk/quotes/fills below are fixtures, not observations or executed orders.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid4, uuid5

import httpx

from backend.app.phase2.engine import assert_dry_run
from backend.app.phase2.models import Gate, Option, Proposal, RiskResult
from backend.app.phase2.order_intents import TERMINAL, OrderClaimService, make_intent


def synthetic_intent(batch: str, case: str, now: datetime):
    identity = uuid5(NAMESPACE_URL, f"thesiscircuit:synthetic:{batch}:{case}")
    expiry = (now+timedelta(days=3)).date()
    contract = Option(symbol=f"SPY{expiry:%y%m%d}C00700000", expiry=expiry, strike=700,
        kind="call", tradable=True, quote_at=now, source="SYNTHETIC_NOT_MARKET_DATA",
        bid=1, ask=1.05, bid_size=10, ask_size=10)
    proposal = Proposal(id=identity,agent="TREND",timestamp=now,regime="UNCERTAIN",contract=contract,
        direction="BULLISH",strategy_type="LONG_CALL",confidence=0,
        thesis="SYNTHETIC dispatcher protocol verification; not an investment proposal",
        evidence={"classification":"SYNTHETIC"},invalidation="Never execution eligible",
        estimated_max_loss=105,liquidity_assessment="SYNTHETIC",reasons_not_to_trade=["SYNTHETIC"],status="PROPOSED")
    risk = RiskResult(proposal_id=identity,decision="APPROVED",reasons=[],checks=[
        Gate(name="synthetic_protocol_only",passed=True,reason="Not a real risk authorization")])
    return make_intent(identity,proposal,risk,now,synthetic=True)


async def run_synthetic_batch(repository, settings, batch: str) -> dict:
    assert_dry_run(settings)
    results = []
    for case in ("complete", "restart_submitting"):
        assert_dry_run(settings)
        proposed = synthetic_intent(batch,case,datetime.now(timezone.utc))
        record = await repository.find(proposed.id)
        if record and record.status in TERMINAL:
            results.append({"case":case,"id":str(record.id),"status":record.status,
                            "replayed_without_writes":True,"events":record.events})
            continue
        owner = uuid4()
        if record is None:
            record = await repository.persist(proposed,owner)
            duplicate = await repository.persist(proposed,owner)
            if duplicate.id != record.id: raise RuntimeError("Duplicate persistence failed")
        claims = OrderClaimService(repository)
        # An actual process restart may encounter a still-valid previous claim.
        if record.owner_id and record.claim_expires_at:
            remaining = (record.claim_expires_at-datetime.now(timezone.utc)).total_seconds()
            if remaining>0: await asyncio.sleep(min(remaining+1,31))
        record = await claims.claim(record.id,owner)
        try:
            await claims.claim(record.id,uuid4())
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 400: raise
        else:
            raise RuntimeError("Concurrent synthetic claim was not rejected")
        if record.status == "CLAIMED":
            now=datetime.now(timezone.utc)
            record=await repository.advance(record.id,owner,"SUBMITTING",preflight={
                "at":now.isoformat(),"decision":"APPROVED","checks":[{
                    "name":"synthetic_protocol_only","passed":True,"reason":"NO BROKER CALL"}]})
        if case == "restart_submitting" and record.owner_id == owner:
            # Deliberately abandon the claim. The next worker waits for real DB expiry.
            await asyncio.sleep(31)
            owner=uuid4()
            record=await claims.claim(record.id,owner)
        assert_dry_run(settings)
        record=await repository.advance(record.id,owner,"RECONCILING")
        record=await repository.advance(record.id,owner,"UNKNOWN",error="RECONCILIATION_REQUIRED")
        owner=uuid4()
        record=await claims.claim(record.id,owner)
        await repository.advance(record.id,owner,"RECONCILING")
        # A synthetic lookup fixture resolves uncertainty. Never touches orders/fills tables.
        broker={"id":str(uuid5(record.id,"synthetic-broker-reference")),
            "client_order_id":record.document.client_order_id,"symbol":record.document.contracts[0],
            "side":"buy","quantity":1,"limit_price":"1.05","status":"filled",
            "filled_qty":"1","filled_avg_price":"1.04","submitted_at":datetime.now(timezone.utc).isoformat(),
            "filled_at":datetime.now(timezone.utc).isoformat(),"paper_mode":True,"classification":"SYNTHETIC"}
        record=await repository.advance(record.id,owner,"FILLED",broker=broker)
        if record.alpaca_order_id is not None: raise RuntimeError("Synthetic data misclassified as Alpaca")
        replay=await claims.claim(record.id,uuid4())
        if replay.events != record.events or replay.attempt_count != 1:
            raise RuntimeError("Terminal replay changed durable state")
        results.append({"case":case,"id":str(record.id),"status":record.status,
                        "replayed_without_writes":False,"events":record.events})
    return {"status":"completed","classification":"SYNTHETIC","broker_calls":0,
            "execution_enabled":False,"autonomous_trading_enabled":False,"batch":batch,"cases":results}
