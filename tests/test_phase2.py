import asyncio
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app import main
from backend.app.config import Settings
from backend.app.models import AccountSnapshot, MarketClock
from backend.app.phase2.agents import allocate, critique, propose
from backend.app.phase2.data import parse_option
from backend.app.phase2.engine import assert_dry_run, run_batch, run_cycle
from backend.app.phase2.features import classify, features
from backend.app.phase2.models import (
    Bar,
    CriticReview,
    MarketState,
    Option,
    OrderRead,
    Position,
    Proposal,
    Shadow,
)
from backend.app.phase2.outcomes import mark_shadows, reflect, review_positions, score_agents
from backend.app.phase2.policy import Policy, validate
from backend.app.phase2.repository import Phase2Repository

NOW = datetime(2026, 9, 2, 17, 0, tzinfo=timezone.utc)


def option(**changes):
    data = {"symbol": "SPY260904C00768000", "expiry": date(2026, 9, 4), "strike": 768,
                "kind": "call", "tradable": True, "quote_at": NOW, "source": "alpaca:indicative",
                "bid": 1.8, "ask": 1.85, "bid_size": 10, "ask_size": 10}
    return Option(**{**data, **changes})


def bars():
    return [Bar(t=NOW - timedelta(minutes=30-i), o=765+i*.1, h=765.2+i*.1,
                l=764.9+i*.1, c=765.1+i*.1, v=100+i, vw=765.05+i*.1) for i in range(30)]


def state(**changes):
    data = {"timestamp": NOW, "account": AccountSnapshot(status="ACTIVE", cash=99815.97,
        buying_power=399263.88, portfolio_value=100000, equity=100000, last_equity=100000,
        options_buying_power=99815.97, account_number_suffix="TEST", expected_account_match=True,
        trading_blocked=False, options_trading_level=3),
        "clock": MarketClock(timestamp=NOW, is_open=True, next_open=NOW+timedelta(days=1),
                          next_close=NOW+timedelta(hours=3)), "positions": [], "orders": [],
        "features": features(bars(), 768, NOW, NOW), "options": [option()]}
    return MarketState(**{**data, **changes})


def position(**changes):
    data = {"symbol": "SPY260904C00768000", "qty": 1, "side": "long", "entry": 1.84,
                "current_price": 1.85, "market_value": 185, "cost_basis": 184,
                "unrealized_pl": 1, "unrealized_plpc": 1/184, "asset_class": "us_option"}
    return Position(**{**data, **changes})


def proposal(s=None):
    s = s or state()
    return propose("TREND", s, classify(s.features, NOW), Policy(), NOW)


def test_features_and_all_regimes():
    f = state().features
    assert f.samples == 30 and f.rsi == 100 and f.atr > 0 and f.vwap > 0
    assert classify(f, NOW).name == "TREND_UP"
    for values, expected in [
        ({"trend_strength": -1, "return_20m": -.01}, "TREND_DOWN"),
        ({"realized_volatility": .5}, "HIGH_VOLATILITY"),
        ({"trend_strength": 0, "realized_volatility": .05}, "LOW_VOLATILITY"),
        ({"trend_strength": 0, "realized_volatility": .2}, "RANGE"),
        ({"timestamp": NOW-timedelta(minutes=10)}, "UNCERTAIN"),
    ]:
        assert classify(f.model_copy(update=values), NOW).name == expected


@pytest.mark.parametrize("failure", ["stale_quote", "future_quote", "stale_bars", "duplicates", "short"])
def test_features_fail_closed(failure):
    b, q = bars(), NOW
    if failure == "stale_quote": q -= timedelta(minutes=3)
    if failure == "future_quote": q += timedelta(seconds=1)
    if failure == "stale_bars": b = [x.model_copy(update={"t": x.t-timedelta(minutes=10)}) for x in b]
    if failure == "duplicates": b[-1] = b[-2]
    if failure == "short": b = b[:10]
    with pytest.raises(ValueError): features(b, 768, q, NOW)


def test_invalid_option_and_proposal_schemas():
    for changes in ({"ask": 1}, {"bid": float("nan")}, {"strike": 769}, {"multiplier": 10}):
        with pytest.raises(ValidationError): option(**changes)
    p = proposal()
    for changes in ({"estimated_max_loss": 1}, {"quantity": 2}, {"strategy_type": "LONG_PUT"}):
        with pytest.raises(ValidationError): Proposal.model_validate({**p.model_dump(), **changes})
    with pytest.raises(ValidationError): CriticReview.model_validate({"proposal_id": uuid4()})


def test_alpaca_snapshot_parsing_does_not_invent_volume():
    contract = {"symbol":"SPY260904C00768000", "underlying_symbol":"SPY",
                "expiration_date":"2026-09-04", "strike_price":"768", "type":"call",
                "tradable":True, "status":"active", "size":"100"}
    snapshot = {"latestQuote":{"t":NOW.isoformat(),"bp":1.8,"ap":1.85,"bs":10,"as":10},
                "latestTrade":{"s":999}, "source":"alpaca:indicative", "greeks":{"delta":.4}}
    parsed = parse_option(contract, snapshot)
    assert parsed.delta == .4 and parsed.volume is None


def test_allocator_critic_and_no_trade():
    s = state()
    r = classify(s.features, NOW)
    p = proposal(s)
    critic = critique(p, s, r)
    assert allocate([p], [critic], s, r, {}, Policy()).decision == "SELECT"
    assert allocate([p], [], s, r, {}, Policy()).decision == "NO_TRADE"
    s.positions = [position()]
    assert allocate([p], [critique(p,s,r)], s, r, {}, Policy()).decision == "NO_TRADE"
    for agent in ("TREND", "RANGE", "DEFENSIVE"):
        empty = state(features=None, options=[])
        assert propose(agent, empty, classify(None, NOW), Policy(), NOW).status == "NO_TRADE"


def test_risk_approved_is_never_execution_authorized():
    result = validate(proposal(), state(), Settings(), Policy(), NOW)
    assert result.decision == "APPROVED", result.reasons
    assert len(result.checks) == 24 and result.execution_authorized is False


@pytest.mark.parametrize("gate,mutation", [
    ("account", lambda s: setattr(s.account, "expected_account_match", False)),
    ("market", lambda s: setattr(s.clock, "is_open", False)),
    ("state_fresh", lambda s: setattr(s, "timestamp", NOW-timedelta(minutes=5))),
    ("data_fresh", lambda s: setattr(s.features, "timestamp", NOW-timedelta(minutes=5))),
    ("buying_power", lambda s: setattr(s.account, "options_buying_power", 1)),
    ("positions_limit", lambda s: setattr(s, "positions", [position()]*3)),
    ("aggregate_risk", lambda s: setattr(s, "positions", [position(cost_basis=2000)])),
    ("underlying_exposure", lambda s: setattr(s, "positions", [position()])),
    ("duplicate_position", lambda s: setattr(s, "positions", [position()])),
    ("known_exposure", lambda s: setattr(s, "positions", [position(side="short")])),
    ("daily_loss", lambda s: setattr(s.account, "equity", 98000)),
    ("conflicting_order", lambda s: setattr(s, "orders", [OrderRead(symbol="SPY",client_order_id="test",status="new",submitted_at=NOW)])),
    ("cooldown", lambda s: setattr(s, "orders", [OrderRead(symbol="SPY",client_order_id="test",status="filled",submitted_at=NOW)])),
])
def test_risk_state_gates(gate, mutation):
    s, p = state(), proposal()
    mutation(s)
    result = validate(p, s, Settings(), Policy(), NOW)
    assert result.decision == "REJECTED"
    assert not next(g for g in result.checks if g.name == gate).passed


@pytest.mark.parametrize("gate,change", [
    ("max_new_risk", {"estimated_max_loss":501}),
    ("proposal", {"quantity":2}),
    ("valid_options", {"contract":option(tradable=False)}),
    ("liquidity", {"contract":option(ask=2.5)}),
    ("data_fresh", {"contract":option(quote_at=NOW-timedelta(minutes=5))}),
])
def test_risk_proposal_gates(gate, change):
    result = validate(proposal().model_copy(update=change), state(), Settings(), Policy(), NOW)
    assert not next(g for g in result.checks if g.name == gate).passed


def test_window_expiry_duplicate_and_kill():
    s,p = state(),proposal()
    s.orders = [OrderRead(symbol="SPY",client_order_id=f"thesiscircuit-phase2-{p.id}",
                          status="filled",submitted_at=NOW-timedelta(hours=1))]
    checks = validate(p,s,Settings(),Policy(emergency_kill=True),NOW+timedelta(days=3)).checks
    for name in ("competition_window","expiry","duplicate_order","kill_switch"):
        assert not next(g for g in checks if g.name == name).passed


@pytest.mark.parametrize("change", [
    {"execution_enabled":True}, {"allow_live_trading":True}, {"alpaca_paper_trade":False},
    {"trading_mode":"live"}, {"alpaca_paper_base_url":"https://"+"api.alpaca.markets"},
])
def test_dry_run_rejects_unsafe_configuration(change):
    with pytest.raises(RuntimeError): assert_dry_run(Settings().model_copy(update=change))


def test_shadow_mark_scoring_and_reflection():
    s = state()
    shadow = Shadow(proposal_id=uuid4(), agent="TREND", symbol=option().symbol,
                    timestamp=NOW-timedelta(minutes=61), entry_reference=2,
                    hypothetical_max_loss=200, rejection_reason="Existing exposure")
    marks = mark_shadows([shadow], s, NOW)
    assert marks[0].hypothetical_pnl == -20 and marks[0].rejection_effect == "HELPED"
    score = score_agents(marks*5)[0]
    assert score.shadow_samples == 1 and score.executed_realized_pnl is None and score.score < 50
    assert reflect(marks,NOW)[0].hard_limits_changed is False
    interim = marks[0].model_copy(update={"horizon_complete":False})
    assert score_agents([interim])[0].score == 50
    assert not reflect([interim],NOW)


def test_position_monitor_never_executes():
    s = state(positions=[position(unrealized_plpc=-.6)])
    review = review_positions(s, classify(s.features,NOW), Policy(),NOW)[0]
    assert review.recommendation == "EXIT" and review.action_authorized is False
    s.options=[]
    assert review_positions(s,classify(None,NOW),Policy(),NOW)[0].recommendation == "RISK_ALERT"


def test_dry_run_cycle_keeps_existing_exposure_and_creates_shadows():
    s = state(positions=[position()])
    cycle = run_cycle(s, Settings(),Policy(),"test",0,[],[],NOW)
    assert cycle.decision == "NO_TRADE" and cycle.shadows
    assert all(not x.executed for x in cycle.shadows)
    assert not cycle.execution_enabled and cycle.state.positions[0].qty == 1
    again = run_cycle(s, Settings(),Policy(),"test",1,cycle.shadows,[],NOW+timedelta(seconds=61))
    assert not again.shadows and again.marks


def test_batch_idempotent_and_bounded():
    class Repository:
        def __init__(self):
            self.rows = {}
        async def completed(self,key): return key in self.rows
        async def history(self): return [],[]
        async def save_cycle(self,cycle): self.rows[str(cycle.id)] = cycle
    class Provider:
        count = 0
        async def refresh(self,_):
            self.count += 1
            return state(positions=[position()])
    async def run():
        repo, provider = Repository(), Provider()
        async def no_wait(_): pass
        ids = await run_batch(provider,repo,Settings(),Policy(),"bounded-test",sleep=no_wait)
        assert len(ids)==3 and provider.count==3
        await run_batch(provider,repo,Settings(),Policy(),"bounded-test",sleep=no_wait)
        assert provider.count==3
        with pytest.raises(ValueError):
            await run_batch(provider,repo,Settings(),Policy(),"test",count=4)
    asyncio.run(run())


def test_atomic_repository_acknowledgment():
    cycle = run_cycle(state(),Settings(),Policy(),"test",0,[],[],NOW)
    requests = []
    def handler(req):
        requests.append(req)
        return httpx.Response(200,json=str(cycle.id))
    async def run():
        cfg=Settings(supabase_url="https://example.supabase.co",supabase_service_role_key="test")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await Phase2Repository(cfg,client).save_cycle(cycle)
    asyncio.run(run())
    assert len(requests)==1 and requests[0].url.path.endswith("/rpc/phase2_save_cycle")


def test_no_phase2_broker_write_dependency_and_phase1_retired():
    for path in Path("backend/app/phase2").glob("*.py"):
        text=path.read_text()
        assert "OrderService" not in text and "submit_order" not in text and "close_position" not in text
    with TestClient(main.app) as client:
        assert client.post("/phase1/execute").status_code == 410
        assert client.post("/phase1/preflight/execution").status_code == 410
        assert client.post("/phase2/execute").status_code == 404
        assert client.get("/safety").json()["phase2_execution_authorized"] is False
