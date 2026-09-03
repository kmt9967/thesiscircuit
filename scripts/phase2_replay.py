"""Offline, reproducible SIMULATED stress replay plus one recorded HISTORICAL snapshot.

No network, broker client, parameter tuning, or production audit writes.
Run: python -m scripts.phase2_replay
"""
import json
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.app.config import Settings
from backend.app.models import AccountSnapshot, MarketClock
from backend.app.phase2.engine import run_cycle
from backend.app.phase2.features import features
from backend.app.phase2.models import Bar, MarketState, Option
from backend.app.phase2.policy import Policy

NOW = datetime(2026,9,2,17,tzinfo=timezone.utc)
SCENARIOS = ("strong_uptrend", "strong_downtrend", "range", "volatility_expansion",
             "low_volatility", "bad_liquidity", "stale_data", "contradictory_signals")


def simulated_state(name: str, variant: int) -> MarketState:
    points=[]
    scale=1+variant/20
    for i in range(61):
        if name in {"strong_uptrend", "bad_liquidity", "stale_data"}: value=764+i*.05*scale
        elif name == "strong_downtrend": value=770-i*.05*scale
        elif name == "volatility_expansion": value=767+2*scale*math.sin(i*1.8)-i*.02
        elif name == "low_volatility": value=767+.01*scale*math.sin(i*.4)
        elif name == "contradictory_signals": value=767+(i*.08 if i<50 else 4-(i-50)*.3)*scale
        else: value=767+.3*scale*math.sin(i*.6)
        points.append(value)
    bars=[Bar(t=NOW-timedelta(minutes=60-i),o=v,h=v+.10,l=v-.10,c=v,v=100+i%7,vw=v)
          for i,v in enumerate(points)]
    f=features(bars,points[-1],NOW,NOW)
    opts=[Option(symbol=f"SPY260904{kind}00768000",expiry="2026-09-04",strike=768,
          kind="call" if kind=="C" else "put",tradable=True,quote_at=NOW,source="SIMULATED",
          bid=1.8,ask=1.85,bid_size=10,ask_size=10) for kind in ("C","P")]
    if name == "bad_liquidity":
        for o in opts: o.ask=2.8; o.bid_size=0; o.ask_size=0
    if name == "stale_data":
        f.timestamp-=timedelta(minutes=10)
        for o in opts: o.quote_at-=timedelta(minutes=10)
    return MarketState(timestamp=NOW,account=AccountSnapshot(status="ACTIVE",cash=100000,
        equity=100000,portfolio_value=100000,last_equity=100000,buying_power=100000,
        options_buying_power=100000,account_number_suffix="TEST",expected_account_match=True,
        trading_blocked=False,options_trading_level=3),
        clock=MarketClock(timestamp=NOW,is_open=True,next_open=NOW+timedelta(days=1),
                          next_close=NOW+timedelta(hours=3)),positions=[],orders=[],features=f,options=opts)


def replay() -> dict:
    report={"classification":"SIMULATED STRESS REPLAY - NOT ALPACA RETURNS", "parameter_tuning":False,
            "variants_per_scenario":12,"scenarios":[]}
    for name in SCENARIOS:
        proposals=Counter(); choices=Counter(); vetoes=Counter(); regimes=Counter(); risks=[]; no_trade=0
        abstentions=Counter()
        for variant in range(12):
            cycle=run_cycle(simulated_state(name,variant),Settings(),Policy(),f"replay-{name}-{variant}",0,[],[],NOW)
            regimes[cycle.regime.name]+=1
            no_trade+=cycle.decision == "NO_TRADE"
            for p,r in zip(cycle.proposals,cycle.risk):
                if p.status == "PROPOSED":
                    proposals[p.agent]+=1; risks.append(p.estimated_max_loss)
                    for g in r.checks:
                        if not g.passed: vetoes[g.name]+=1
                else: abstentions[p.agent]+=1
                if cycle.allocation.proposal_id == p.id and cycle.decision != "NO_TRADE": choices[p.agent]+=1
        report["scenarios"].append({"scenario":name,"regimes":dict(regimes),"cycles":12,
            "proposals_by_agent":dict(proposals),"no_trade_frequency":no_trade/12,
            "agent_abstentions":dict(abstentions),
            "risk_rejections_by_gate":dict(vetoes),"selected_agents":dict(choices),
            "average_proposed_risk":round(sum(risks)/len(risks),2) if risks else None,
            "max_simulated_drawdown":None,"shadow_outcomes":None,"missed_opportunities":None,
            "false_positives":None,"outcome_limitation":"No subsequent option-price path; not calculable"})
    artifact=Path(__file__).resolve().parents[1]/"evidence/phase-2/recorded-production-dry-runs.json"
    payload=json.loads(artifact.read_text(encoding="utf-8"))["latest"]
    payload["state"]["account"]["account_number_suffix"]="REDACTED"
    s=MarketState.model_validate(payload["state"])
    timestamp=datetime.fromisoformat(payload["created_at"].replace("Z","+00:00"))
    cycle=run_cycle(s,Settings(),Policy(),"historical-replay",0,[],[],timestamp)
    report["historical"]={"classification":"HISTORICAL RECORDED SNAPSHOT REPLAY",
        "source_cycle":payload["id"],"source_time":payload["created_at"],"decision":cycle.decision,
        "proposals":[{"agent":p.agent,"status":p.status,"symbol":p.contract.symbol if p.contract else None}
                     for p in cycle.proposals],"not_a_backtest":True}
    return report


if __name__ == "__main__":
    print(json.dumps(replay(),indent=2))
