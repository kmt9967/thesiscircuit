import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import httpx

from backend.app.config import Settings
from backend.app.phase2.activation import (
    ActivationSupervisor,
    RailwayShutdownController,
    verify_production_shutdown_control,
)
from backend.app.phase2.execution_sessions import ExecutionSession, SessionState


def activation_fixture():
    now = datetime.now(timezone.utc)
    identity = uuid4()
    settings = Settings(execution_enabled=True, autonomous_trading_enabled=True,
        phase2_execution_token="x" * 32, phase2_active_session_id=identity,
        phase2_session_starts_at=now-timedelta(seconds=5),
        phase2_session_expires_at=now+timedelta(minutes=10), phase2_max_order_budget=1,
        railway_project_access_token="test-project-token", railway_project_id="project",
        railway_environment_id="environment", railway_service_id="service")
    document = ExecutionSession(id=identity, created_at=now-timedelta(seconds=5),
        starts_at=settings.phase2_session_starts_at, expires_at=settings.phase2_session_expires_at,
        approval_equity=Decimal(100000), max_opening_orders=1, max_closing_orders=0,
        max_total_orders=1, max_new_risk=Decimal(250),
        allowed_underlyings=["SPY", "QQQ"], entry_permission=True)
    row = SessionState(id=identity, document=document, status="DRAFT", opening_consumed=0,
        closing_consumed=0, orders_consumed=0, new_risk_consumed=0, reservations={},
        broker_failures=[], cycles={}, next_cycle_at=None, kill_reason=None, completed_at=None, events=[])
    return settings, row


class Sessions:
    def __init__(self, row): self.row, self.audit = row, []
    async def find(self, identity): return self.row if identity == self.row.id else None
    async def control(self, identity, action="INSPECT", reason=None, cycle_key=None):
        if action == "ACTIVATE": self.row.status = "ACTIVE"
        elif action == "KILL": self.row.status, self.row.kill_reason = "KILLED", reason
        elif action == "FINISH": self.row.status = "COMPLETED"
        return self.row
    async def insert(self, table, row, **kwargs):
        assert table == "system_events" and row["kind"] == "phase2_execution_shutdown"
        self.audit.append(row)
        return row


class Shutdown:
    def __init__(self, settings, *, fail=False): self.settings, self.fail, self.calls = settings, fail, []
    async def verify_scope(self): self.calls.append("scope")
    async def configured_flags(self): return True, True
    async def force_disabled(self, *, skip_deploys=False):
        self.calls.append("disable")
        self.settings.execution_enabled = self.settings.autonomous_trading_enabled = False
        if self.fail: raise RuntimeError("control plane failed")


class Coordinator:
    def __init__(self, *, fail=False): self.fail = fail
    async def run(self, identity, token):
        if self.fail: raise RuntimeError("dispatcher failed")
        return {"status": "COMPLETED", "kill_reason": None, "orders_consumed": 0}


def test_activation_is_server_bound_and_always_verifies_shutdown():
    async def run():
        settings, row = activation_fixture(); sessions = Sessions(row); shutdown = Shutdown(settings)
        result = await ActivationSupervisor(settings, sessions, Coordinator(), shutdown).run()
        assert result["shutdown_verified"] is True and result["shutdown_audit_persisted"] is True
        assert shutdown.calls == ["scope", "disable"] and len(sessions.audit) == 1
        assert settings.execution_enabled is settings.autonomous_trading_enabled is False
        assert row.status == "COMPLETED"
    asyncio.run(run())


def test_synthetic_production_shutdown_is_false_only_and_broker_free():
    class SyntheticShutdown:
        def __init__(self): self.calls = []
        async def verify_scope(self): self.calls.append("scope")
        async def configured_flags(self): self.calls.append("flags"); return False, False
        async def force_disabled(self, *, skip_deploys=False):
            assert skip_deploys is True
            self.calls.append("false-only")

    class Audit:
        def __init__(self): self.row = None
        async def event(self, trace_id, sequence): return self.row
        async def insert(self, table, row, **kwargs):
            assert table == "system_events"
            assert row["kind"] == "phase2_synthetic_shutdown_verified"
            self.row = row
            return row

    async def run():
        settings = Settings()
        control, audit = SyntheticShutdown(), Audit()
        result = await verify_production_shutdown_control(
            settings, "batch-a", controller=control, repository=audit)
        assert result["broker_submission_calls"] == 0
        assert result["execution_enabled"] is result["autonomous_trading_enabled"] is False
        assert control.calls == ["scope", "flags", "false-only", "flags"]
        repeated = await verify_production_shutdown_control(
            settings, "batch-a", controller=control, repository=audit)
        assert repeated == result and control.calls == ["scope", "flags", "false-only", "flags"]
    asyncio.run(run())


def test_synthetic_production_shutdown_rejects_any_enabled_gate():
    async def run():
        settings = Settings(execution_enabled=True, phase1_execution_token="x")
        try:
            await verify_production_shutdown_control(settings, "batch-a", controller=object(), repository=object())
        except RuntimeError as exc:
            assert "both gates disabled" in str(exc)
        else:
            raise AssertionError("enabled gate must fail closed")
    asyncio.run(run())


def test_dispatcher_failure_kills_session_and_disables_both_flags():
    async def run():
        settings, row = activation_fixture(); sessions = Sessions(row); shutdown = Shutdown(settings)
        result = await ActivationSupervisor(settings, sessions, Coordinator(fail=True), shutdown).run()
        assert result["status"] == "blocked" and result["shutdown_verified"] is True
        assert row.status == "KILLED" and row.kill_reason == "DATABASE_FAILURE"
        assert not settings.execution_enabled and not settings.autonomous_trading_enabled
    asyncio.run(run())


def test_session_environment_mismatch_never_activates_and_still_shuts_down():
    async def run():
        settings, row = activation_fixture(); row.document.max_total_orders = 0
        sessions = Sessions(row); shutdown = Shutdown(settings)
        result = await ActivationSupervisor(settings, sessions, Coordinator(), shutdown).run()
        assert result["status"] == "blocked" and row.status == "DRAFT"
        assert result["shutdown_verified"] is True
    asyncio.run(run())


def test_railway_shutdown_updates_only_two_flags_and_reads_them_back():
    calls = []
    variables = {"EXECUTION_ENABLED": "true", "AUTONOMOUS_TRADING_ENABLED": "true", "KEEP": "unchanged"}

    def handler(request):
        body = __import__("json").loads(request.content)
        calls.append(body)
        query = body["query"]
        if "projectToken" in query:
            data = {"projectToken": {"projectId": "project", "environmentId": "environment"}}
        elif "variableCollectionUpsert" in query:
            update = body["variables"]["input"]
            assert update["replace"] is False and update["skipDeploys"] is False
            assert set(update["variables"]) == {"EXECUTION_ENABLED", "AUTONOMOUS_TRADING_ENABLED"}
            variables.update(update["variables"])
            data = {"variableCollectionUpsert": True}
        else:
            data = {"variables": variables}
        return httpx.Response(200, json={"data": data})

    async def run():
        settings, _ = activation_fixture()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            control = RailwayShutdownController(settings, client)
            await control.force_disabled()
        assert variables == {"EXECUTION_ENABLED": "false", "AUTONOMOUS_TRADING_ENABLED": "false", "KEEP": "unchanged"}
        assert len(calls) == 3 and not settings.execution_enabled and not settings.autonomous_trading_enabled
    asyncio.run(run())
