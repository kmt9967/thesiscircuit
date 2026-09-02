import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from test_phase1 import account, asset, clock, proposal, risk, settings

from backend.app import main
from backend.app.models import Phase1Preflight
from backend.app.services.alpaca import AccountService, AlpacaError, OrderService
from backend.app.services.preflight import PreflightBlocked, TwoStagePreflight
from backend.app.services.supabase import SupabaseAuditRepository


class MemoryAudit:
    def __init__(self):
        self.events = {}
        self.rows = {}
        self.fail_order_write = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def event(self, trace_id, sequence):
        return self.events.get(sequence)

    async def insert(self, table, row, **kwargs):
        if table == "orders" and self.fail_order_write:
            raise RuntimeError("audit unavailable")
        if table == "system_events":
            self.events[row["sequence"]] = row
        self.rows[table] = row
        return row

    async def claim(self, trace_id, payload):
        if 0 in self.events:
            raise PreflightBlocked("Claim already exists")
        self.events[0] = {"payload": payload}


def builder_for(config, changes=None, calls=None):
    async def build(stage, preferred):
        if calls is not None:
            calls.append(stage)
        overrides = (changes or {}).copy()
        selected = overrides.pop("proposal", proposal())
        decision = risk(settings=config, stage=stage, proposal=selected, **overrides)
        return Phase1Preflight(
            stage=stage,
            result=("READY_FOR_EXECUTION" if stage == "readiness"
                    else "APPROVED_FOR_SINGLE_ORDER") if decision.decision == "APPROVED"
            else "REJECTED",
            proposal=selected, risk=decision, account=account(), clock=clock(),
            open_orders=0, open_positions=0,
        )
    return build


@pytest.mark.parametrize("enabled,expected", [(False, "APPROVED"), (True, "REJECTED")])
def test_readiness_requires_disabled(enabled, expected):
    assert risk(settings=settings(execution_enabled=enabled), stage="readiness").decision == expected


@pytest.mark.parametrize("mutation", [
    {"allow_live_trading": True}, {"trading_mode": "live"}, {"alpaca_paper_trade": False},
    {"alpaca_paper_base_url": "https://" + "api.alpaca.markets"},
])
def test_readiness_rejects_even_mutated_live_configuration(mutation):
    config = settings(execution_enabled=False).model_copy(update=mutation)
    assert risk(settings=config, stage="readiness").decision == "REJECTED"


@pytest.mark.parametrize("enabled,expected", [(True, "APPROVED"), (False, "REJECTED")])
def test_execution_requires_enabled(enabled, expected):
    assert risk(settings=settings(execution_enabled=enabled), stage="execution").decision == expected


def test_both_receipts_required_and_only_one_durable_claim():
    async def run():
        config = settings(execution_enabled=False)
        repository = MemoryAudit()
        calls = []
        flow = TwoStagePreflight(repository, builder_for(config, calls=calls))
        with pytest.raises(PreflightBlocked):
            await flow.execution(None)
        ready = await flow.readiness()
        assert ready.result == "READY_FOR_EXECUTION"
        assert ready.receipt_id
        config.execution_enabled = True
        with pytest.raises(PreflightBlocked):
            await flow.submission_preflight(ready.receipt_id, None)
        final = await flow.execution(ready.receipt_id)
        assert final.result == "APPROVED_FOR_SINGLE_ORDER"
        assert final.readiness_id == ready.receipt_id
        preflight = await flow.submission_preflight(ready.receipt_id, final.receipt_id)
        await flow.claim(preflight)
        with pytest.raises(PreflightBlocked):
            await flow.claim(preflight)
        with pytest.raises(PreflightBlocked):
            await flow.submission_preflight(ready.receipt_id, final.receipt_id)
        assert calls == ["readiness", "execution", "execution"]
    asyncio.run(run())


@pytest.mark.parametrize("changes", [
    {"clock": clock(False)}, {"account": account(buying_power=1)},
    {"asset": asset(False)}, {"duplicate_order": True},
    {"positions": [{"symbol": "UNRELATED"}]}, {"total_orders": 1},
    {"account": account(expected_account_match=False)},
])
def test_final_stage_rechecks_current_risk_state(changes):
    async def run():
        config = settings(execution_enabled=False)
        repository = MemoryAudit()
        flow = TwoStagePreflight(repository, builder_for(config))
        ready = await flow.readiness()
        config.execution_enabled = True
        flow.builder = builder_for(config, changes)
        final = await flow.execution(ready.receipt_id)
        assert final.result == "REJECTED"
        assert -1 not in repository.events
    asyncio.run(run())


def test_submission_rechecks_after_successful_execution_stage():
    async def run():
        config = settings(execution_enabled=False)
        repository = MemoryAudit()
        flow = TwoStagePreflight(repository, builder_for(config))
        ready = await flow.readiness()
        config.execution_enabled = True
        approved = await flow.execution(ready.receipt_id)
        flow.builder = builder_for(config, {"clock": clock(False)})
        with pytest.raises(PreflightBlocked, match="market_state"):
            await flow.submission_preflight(ready.receipt_id, approved.receipt_id)
        assert 0 not in repository.events
    asyncio.run(run())


def test_expired_and_mismatched_receipts_rejected():
    async def run():
        config = settings(execution_enabled=False)
        repository = MemoryAudit()
        flow = TwoStagePreflight(repository, builder_for(config))
        ready = await flow.readiness()
        config.execution_enabled = True
        with pytest.raises(PreflightBlocked):
            await flow.execution(uuid4())
        repository.events[-2]["payload"]["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(seconds=1)
        ).isoformat()
        with pytest.raises(PreflightBlocked, match="expired"):
            await flow.execution(ready.receipt_id)
    asyncio.run(run())


def test_claim_uses_insert_not_upsert_and_conflict_fails():
    def handler(request):
        assert "resolution" not in request.headers["Prefer"]
        assert "on_conflict" not in str(request.url)
        return httpx.Response(409)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            repository = SupabaseAuditRepository(settings(), client)
            with pytest.raises(httpx.HTTPStatusError):
                await repository.claim("trace", {})
    asyncio.run(run())


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_failed_duplicate_lookup_is_not_treated_as_absent(status):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(status)
        )) as client:
            with pytest.raises(AlpacaError):
                await OrderService(settings(), client).by_client_order_id("id")
    asyncio.run(run())


@pytest.mark.parametrize("value", [{}, None, "unexpected", ["invalid"]])
def test_malformed_positions_or_orders_fail_closed(value):
    with pytest.raises(AlpacaError):
        AccountService._validated_list(value)


@pytest.mark.parametrize("stages,claimed", [(False, False), (True, False), (False, True)])
def test_broker_write_requires_both_stages_and_claim(stages, claimed):
    async def run():
        def handler(request):
            pytest.fail("No network request allowed")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(AlpacaError, match="Both preflight"):
                await OrderService(settings(), client).submit_once(
                    proposal(), str(uuid4()), True,
                    stages_verified=stages, submission_claimed=claimed,
                )
    asyncio.run(run())


@pytest.mark.parametrize("response_kind", ["success", "timeout", "rejected", "malformed"])
def test_broker_attempt_always_disables_gate_and_never_reposts(response_kind):
    writes = []
    config = settings()

    def handler(request):
        if request.method == "GET":
            return httpx.Response(404)
        writes.append(request)
        if response_kind == "timeout":
            raise httpx.ReadTimeout("uncertain", request=request)
        if response_kind == "rejected":
            return httpx.Response(422)
        if response_kind == "malformed":
            return httpx.Response(200, text="invalid")
        return httpx.Response(200, json={"id": "paper-test-order", "status": "new",
                                       "qty": "1", "filled_qty": "0"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = OrderService(config, client)
            try:
                await service.submit_once(proposal(datetime.now(timezone.utc)), str(uuid4()), True,
                                          stages_verified=True, submission_claimed=True)
            except AlpacaError:
                assert response_kind != "success"
            assert config.execution_enabled is False
            with pytest.raises(AlpacaError, match="disabled"):
                await service.submit_once(proposal(), str(uuid4()), True,
                                          stages_verified=True, submission_claimed=True)
    asyncio.run(run())
    assert len(writes) == 1


def test_route_disables_after_pre_submit_failure(monkeypatch):
    monkeypatch.setattr(main, "PHASE1_RETIRED", False)  # Historical v1 harness only.
    config = settings()
    monkeypatch.setattr(main, "settings", config)

    async def failure(*args):
        raise RuntimeError("audit unavailable")
    monkeypatch.setattr(main, "_phase1_execute_impl", failure)
    with TestClient(main.app, raise_server_exceptions=False) as client:
        result = client.post("/phase1/execute", headers={"X-Phase1-Authorization": "one-shot-token"})
        assert result.status_code == 500
        assert config.execution_enabled is False


def test_claim_disables_after_restart_even_if_environment_true(monkeypatch):
    monkeypatch.setattr(main, "PHASE1_RETIRED", False)  # Historical v1 harness only.
    config = settings()
    repository = MemoryAudit()
    repository.events[0] = {"payload": {}}
    monkeypatch.setattr(main, "settings", config)
    monkeypatch.setattr(main, "SupabaseAuditRepository", lambda _: repository)
    with TestClient(main.app) as client:
        assert client.get("/safety").json()["execution_enabled"] is False
        assert client.get("/health").json()["orders"] == "disabled"


def test_complete_route_sequence_submits_only_once(monkeypatch):
    monkeypatch.setattr(main, "PHASE1_RETIRED", False)  # Historical v1 harness only.
    config = settings(execution_enabled=False)
    repository = MemoryAudit()
    writes = []

    class PaperBroker:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def submit_once(self, item, risk_id, **proof):
            assert config.execution_enabled
            assert proof == {"risk_approved": True, "stages_verified": True,
                             "submission_claimed": True}
            assert 0 in repository.events
            writes.append(item.client_order_id)
            return OrderService._record(
                {"id": "paper-only-test", "status": "filled", "qty": "1",
                 "filled_qty": "1", "filled_avg_price": "1.20",
                 "submitted_at": datetime.now(timezone.utc).isoformat(),
                 "filled_at": datetime.now(timezone.utc).isoformat()}, item, risk_id,
            )

    monkeypatch.setattr(main, "settings", config)
    monkeypatch.setattr(main, "SupabaseAuditRepository", lambda _: repository)
    monkeypatch.setattr(main, "_build_preflight", builder_for(config))
    monkeypatch.setattr(main, "OrderService", lambda _: PaperBroker())
    headers = {"X-Phase1-Authorization": "one-shot-token"}
    with TestClient(main.app) as client:
        ready = client.post("/phase1/preflight/readiness").json()
        assert ready["result"] == "READY_FOR_EXECUTION"
        config.execution_enabled = True
        final = client.post("/phase1/preflight/execution", headers=headers,
                            params={"readiness_id": ready["receipt_id"]}).json()
        params = {"readiness_id": ready["receipt_id"], "execution_id": final["receipt_id"]}
        response = client.post("/phase1/execute", headers=headers, params=params)
        assert response.status_code == 200
        assert response.json()["order"]["status"] == "filled"
        assert config.execution_enabled is False
        assert repository.rows["orders"]["filled_average_price"] == 1.2
        config.execution_enabled = True  # Emulate a restarted process with stale environment.
        assert client.post("/phase1/execute", headers=headers, params=params).status_code == 409
        assert config.execution_enabled is False
    assert len(writes) == 1


def test_readiness_timeout_returns_a_nonempty_safe_error(monkeypatch):
    monkeypatch.setattr(main, "PHASE1_RETIRED", False)  # Historical v1 harness only.
    repository = MemoryAudit()

    async def timeout(*args):
        raise httpx.ReadTimeout("")
    repository.event = timeout
    monkeypatch.setattr(main, "SupabaseAuditRepository", lambda _: repository)
    with TestClient(main.app) as client:
        result = client.post("/phase1/preflight/readiness")
        assert result.status_code == 409
        assert "ReadTimeout" in result.json()["detail"]
        assert "not authorized" in result.json()["detail"]


def test_readiness_requires_environment_disabled_even_after_local_shutdown(monkeypatch):
    monkeypatch.setattr(main, "PHASE1_RETIRED", False)  # Historical v1 harness only.
    monkeypatch.setattr(main, "configured_execution_enabled", True)
    monkeypatch.setattr(main, "settings", settings(execution_enabled=False))
    with TestClient(main.app) as client:
        result = client.post("/phase1/preflight/readiness")
        assert result.status_code == 423
        assert "Railway execution must be disabled" in result.json()["detail"]
