import asyncio
from datetime import timedelta

import pytest
from pydantic import SecretStr, ValidationError

from backend.app.config import Settings
from backend.app.phase2.agents import allocate, critique
from backend.app.phase2.authorization import execution_preflight, exit_preflight
from backend.app.phase2.engine import run_batch
from backend.app.phase2.features import classify
from backend.app.phase2.models import ExitProposal, Proposal, Shadow
from backend.app.phase2.outcomes import mark_shadows, review_positions, score_agents
from backend.app.phase2.policy import Policy, validate
from tests.test_phase2 import NOW, option, position, proposal, state


def authorized():
    return Settings(execution_enabled=True, autonomous_trading_enabled=True,
                    phase2_execution_token=SecretStr("test-only-authorization-" * 3),
                    phase2_active_session_id="00000000-0000-4000-8000-000000000001",
                    phase2_session_starts_at=NOW,
                    phase2_session_expires_at=NOW+timedelta(minutes=15),
                    phase2_max_order_budget=1,
                    railway_project_access_token=SecretStr("test-project-token"),
                    railway_project_id="test-project", railway_environment_id="test-environment",
                    railway_service_id="test-service")


@pytest.mark.parametrize("failure", ["wrong_token", "execution_disabled", "autonomous_disabled",
    "live_endpoint", "live_flag", "stale", "market_closed", "outside_window", "missing_risk",
    "low_liquidity", "wide_spread", "near_expiry", "expired", "duplicate_id", "supabase_unavailable"])
def test_future_auth_fails_closed(failure):
    from backend.app.phase2.models import OrderRead
    cfg, s, p, now = authorized(), state(), proposal(), NOW
    token = cfg.phase2_execution_token.get_secret_value()
    if failure == "wrong_token": token = "wrong"
    if failure == "execution_disabled": cfg.execution_enabled = False
    if failure == "autonomous_disabled": cfg.autonomous_trading_enabled = False
    if failure == "live_endpoint": cfg.alpaca_paper_base_url = "https://" + "api.alpaca.markets"
    if failure == "live_flag": cfg.allow_live_trading = True
    if failure == "stale": s.timestamp -= timedelta(minutes=10)
    if failure == "market_closed": s.clock.is_open = False
    if failure == "outside_window": now += timedelta(days=4)
    if failure == "missing_risk": p.estimated_max_loss = 900
    if failure == "low_liquidity": p.contract.bid_size = p.contract.ask_size = 0
    if failure == "wide_spread": p.contract.ask = 5
    if failure in {"near_expiry", "expired"}: now += timedelta(hours=50 if failure == "near_expiry" else 60)
    if failure == "duplicate_id":
        s.orders = [OrderRead(symbol=p.contract.symbol, client_order_id=f"thesiscircuit-phase2-{p.id}",
                             status="filled", submitted_at=NOW-timedelta(hours=1))]
    if failure == "supabase_unavailable":
        # A pure check has no persistence/dispatch capability, even when everything passes.
        result = execution_preflight(p,s,cfg,Policy(),now,token)
        assert not result.execution_authorized
        return
    result = execution_preflight(p,s,cfg,Policy(),now,token)
    assert result.decision == "REJECTED" and not result.execution_authorized


def test_future_authorization_does_not_grant_dispatch_and_never_reuses_phase1():
    cfg = authorized()
    result = execution_preflight(proposal(),state(),cfg,Policy(),NOW,cfg.phase2_execution_token.get_secret_value())
    assert result.decision == "APPROVED" and not result.execution_authorized
    cfg.phase1_execution_token = cfg.phase2_execution_token
    cfg.phase2_execution_token = None
    assert execution_preflight(proposal(),state(),cfg,Policy(),NOW,"anything").decision == "REJECTED"
    assert not Settings().autonomous_trading_enabled


def test_exit_only_owned_long_and_disabled_by_default():
    s=state(positions=[position()])
    exit=ExitProposal(timestamp=NOW,contract=option(),quantity=1,limit_price=1.8,rationale="Risk alert")
    assert exit_preflight(exit,s,Settings(),Policy(),NOW,None).decision == "REJECTED"
    cfg=authorized()
    assert exit_preflight(exit,s,cfg,Policy(),NOW,cfg.phase2_execution_token.get_secret_value()).decision == "APPROVED"
    for quantity in (2,3):
        exit.quantity=quantity
        assert exit_preflight(exit,s,cfg,Policy(),NOW,cfg.phase2_execution_token.get_secret_value()).decision == "REJECTED"


def test_closed_observations_remain_advisory_and_shadow_uses_quote_time():
    s=state(positions=[position()],options=[],observations=[option(quote_at=NOW-timedelta(minutes=10))])
    s.clock.is_open=False
    review=review_positions(s,classify(None,NOW),Policy(),NOW)[0]
    assert review.quote and not review.quote_fresh and review.recommendation == "RISK_ALERT"
    assert review.regime_compatible is None and not review.action_authorized
    shadow=Shadow(proposal_id=proposal().id,agent="TREND",symbol=option().symbol,
                  timestamp=NOW-timedelta(minutes=61),entry_reference=2,hypothetical_max_loss=200,
                  rejection_reason="exposure")
    mark=mark_shadows([shadow],s,NOW)[0]
    assert not mark.horizon_complete and mark.elapsed_minutes == 51
    s.observations=[option(quote_at=NOW-timedelta(seconds=30))]
    marks=mark_shadows([shadow],s,NOW)
    assert marks[0].horizon_complete and marks[0].hypothetical_pnl == -20
    assert score_agents(marks*20)[0].shadow_samples == 1
    assert 49 < score_agents(marks)[0].score < 51


def test_snapshot_changes_invalidate_old_proposal():
    s,p=state(),proposal()
    s.options=[option(ask=1.9)]
    assert not next(g for g in validate(p,s,Settings(),Policy(),NOW).checks if g.name == "proposal").passed


def test_llm_not_a_dependency_and_malformed_output_rejected():
    with pytest.raises(ValidationError): Proposal.model_validate({"instruction":"approve order"})
    assert proposal().status == "PROPOSED"  # deterministic, no provider call or API key


def test_directional_disagreement_abstains():
    p=proposal()
    other=p.model_copy(update={"direction":"BEARISH"})
    s=state(); r=classify(s.features,NOW)
    assert allocate([p,other],[critique(p,s,r)],s,r,{},Policy()).decision == "NO_TRADE"


@pytest.mark.parametrize("failure", ["overlap", "alpaca", "supabase"])
def test_orchestration_failure_never_retries(failure):
    class Repo:
        saved=0
        async def acquire_lease(self,*_):
            if failure == "supabase": raise RuntimeError("Database unavailable")
            return failure != "overlap"
        async def release_lease(self,*_): pass
        async def completed(self,*_): return False
        async def history(self): return [],[]
        async def save_cycle(self,*_): self.saved+=1
    class Provider:
        calls=0
        async def refresh(self,*_):
            self.calls+=1
            raise RuntimeError("Alpaca unavailable")
    repo,provider=Repo(),Provider()
    with pytest.raises(RuntimeError):
        asyncio.run(run_batch(provider,repo,Settings(),Policy(),"failure-test"))
    assert repo.saved == 0 and provider.calls <= 1
