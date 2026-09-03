"""Server-startup-only bounded activation with Railway control-plane shutdown.

There is deliberately no HTTP activation route. Railway encrypted variables and an
immutable Supabase session document must agree before the coordinator can start.
"""
import asyncio
from contextlib import AsyncExitStack, suppress
from datetime import datetime, timezone

import httpx

from backend.app.phase2.data import MultiUnderlyingMarketProvider
from backend.app.phase2.execution_coordinator import BoundedExecutionCoordinator
from backend.app.phase2.execution_sessions import ExecutionSessionService
from backend.app.phase2.order_dispatch import PaperOrderDispatcher
from backend.app.phase2.order_intents import OrderIntentService
from backend.app.phase2.repository import Phase2Repository
from backend.app.services.alpaca import AlpacaClient

RAILWAY_GRAPHQL = "https://backboard.railway.com/graphql/v2"


class RailwayShutdownController:
    """A single-environment project token may only force both gates to false."""

    def __init__(self, settings, client: httpx.AsyncClient | None = None):
        if not settings.railway_project_access_token:
            raise RuntimeError("Railway shutdown credential missing")
        self.settings = settings
        self.headers = {"Project-Access-Token": settings.railway_project_access_token.get_secret_value()}
        self.client = client or httpx.AsyncClient(timeout=10, follow_redirects=False)
        self.owns_client = client is None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        if self.owns_client:
            await self.client.aclose()

    async def _call(self, query: str, variables: dict | None = None) -> dict:
        response = await self.client.post(RAILWAY_GRAPHQL, headers=self.headers,
                                          json={"query": query, "variables": variables or {}})
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("errors") or not isinstance(payload.get("data"), dict):
            raise RuntimeError("Railway control-plane request denied")
        return payload["data"]

    async def verify_scope(self) -> None:
        data = await self._call("query { projectToken { projectId environmentId } }")
        scope = data.get("projectToken") or {}
        if (scope.get("projectId") != self.settings.railway_project_id
                or scope.get("environmentId") != self.settings.railway_environment_id):
            raise RuntimeError("Railway token scope mismatch")

    async def configured_flags(self) -> tuple[bool, bool]:
        query = """query variables($projectId:String!,$environmentId:String!,$serviceId:String){
          variables(projectId:$projectId,environmentId:$environmentId,serviceId:$serviceId)
        }"""
        data = await self._call(query, {"projectId": self.settings.railway_project_id,
            "environmentId": self.settings.railway_environment_id,
            "serviceId": self.settings.railway_service_id})
        variables = data.get("variables")
        if not isinstance(variables, dict):
            raise TypeError("Railway variables response malformed")
        return (variables.get("EXECUTION_ENABLED") == "true",
                variables.get("AUTONOMOUS_TRADING_ENABLED") == "true")

    async def force_disabled(self) -> None:
        # Local authority disappears before the control-plane request is attempted.
        self.settings.execution_enabled = False
        self.settings.autonomous_trading_enabled = False
        await self.verify_scope()
        mutation = """mutation variableCollectionUpsert($input:VariableCollectionUpsertInput!){
          variableCollectionUpsert(input:$input)
        }"""
        data = await self._call(mutation, {"input": {
            "projectId": self.settings.railway_project_id,
            "environmentId": self.settings.railway_environment_id,
            "serviceId": self.settings.railway_service_id,
            "variables": {"EXECUTION_ENABLED": "false", "AUTONOMOUS_TRADING_ENABLED": "false"},
            "replace": False,
            "skipDeploys": False,
        }})
        if data.get("variableCollectionUpsert") is not True:
            raise RuntimeError("Railway shutdown was not acknowledged")
        if await self.configured_flags() != (False, False):
            raise RuntimeError("Railway shutdown read-back failed")


class ActivationSupervisor:
    def __init__(self, settings, sessions, coordinator, shutdown):
        self.settings, self.sessions, self.coordinator, self.shutdown = settings, sessions, coordinator, shutdown

    async def run(self) -> dict:
        identity = self.settings.phase2_active_session_id
        token = self.settings.phase2_execution_token.get_secret_value()
        report = {"status": "starting", "session_id": str(identity), "shutdown_verified": False}
        terminal_reason = "DATABASE_FAILURE"
        try:
            await self.shutdown.verify_scope()
            if await self.shutdown.configured_flags() != (True, True):
                raise RuntimeError("Railway activation flags do not agree")
            session = await self.sessions.find(identity)
            if session is None:
                raise RuntimeError("Approved execution session missing")
            document = session.document
            if (document.classification != "PAPER" or document.starts_at != self.settings.phase2_session_starts_at
                    or document.expires_at != self.settings.phase2_session_expires_at
                    or document.max_total_orders != self.settings.phase2_max_order_budget
                    or document.max_opening_orders > 1 or document.max_closing_orders != 0
                    or document.exit_permission or document.allow_position_exit
                    or self.settings.phase2_emergency_kill):
                raise RuntimeError("Railway activation does not match immutable session bounds")
            now = datetime.now(timezone.utc)
            if not document.starts_at <= now < document.expires_at:
                terminal_reason = "SESSION_SCOPE"
                raise RuntimeError("Approved execution session is outside its finite window")
            session = await self.sessions.control(identity, "ACTIVATE")
            if session.status != "ACTIVE":
                raise RuntimeError("Execution session activation failed")
            result = await asyncio.wait_for(
                self.coordinator.run(identity, token),
                timeout=max(1, (document.expires_at - now).total_seconds() + 5),
            )
            report.update(result)
            if result.get("status") == "COMPLETED":
                await self.sessions.control(identity, "FINISH")
            terminal_reason = result.get("kill_reason") or "SESSION_SCOPE"
            return report
        except asyncio.TimeoutError:
            terminal_reason = "SESSION_SCOPE"
            report.update(status="blocked", error_type="SessionTimeout")
            return report
        except (httpx.HTTPError, RuntimeError, ValueError, TypeError, KeyError) as exc:
            report.update(status="blocked", error_type=type(exc).__name__)
            return report
        finally:
            self.settings.execution_enabled = False
            self.settings.autonomous_trading_enabled = False
            if identity:
                with suppress(httpx.HTTPError, RuntimeError, ValueError, TypeError, KeyError):
                    session = await self.sessions.control(identity)
                    if session.status == "ACTIVE":
                        await self.sessions.control(identity, "KILL", terminal_reason)
            try:
                await asyncio.shield(self.shutdown.force_disabled())
                report["shutdown_verified"] = True
            except (httpx.HTTPError, RuntimeError, ValueError, TypeError, KeyError):
                report["shutdown_verified"] = False
                report["shutdown_error"] = "ControlPlaneShutdownFailed"
            report["shutdown_audit_persisted"] = False
            if identity:
                try:
                    await self.sessions.insert("system_events", {
                        "trace_id": str(identity), "sequence": 2_600_000,
                        "kind": "phase2_execution_shutdown",
                        "payload": {"flags_false": True,
                                    "control_plane_verified": report["shutdown_verified"],
                                    "reason": terminal_reason},
                        "paper": True,
                    }, on_conflict="trace_id,sequence")
                    report["shutdown_audit_persisted"] = True
                except (httpx.HTTPError, RuntimeError, ValueError, TypeError, KeyError):
                    report["shutdown_audit_persisted"] = False


async def run_production_activation(settings) -> dict:
    """Build the production graph only after encrypted startup authorization exists."""
    async with AsyncExitStack() as stack:
        sessions = await stack.enter_async_context(ExecutionSessionService(settings))
        intents = await stack.enter_async_context(OrderIntentService(settings))
        cycles = await stack.enter_async_context(Phase2Repository(settings))
        broker = await stack.enter_async_context(AlpacaClient(settings))
        shutdown = await stack.enter_async_context(RailwayShutdownController(settings))
        provider = MultiUnderlyingMarketProvider(settings)
        coordinator = BoundedExecutionCoordinator(
            sessions, cycles, intents, provider,
            lambda gate, policy: PaperOrderDispatcher(
                intents, broker, provider, settings, policy, session_gate=gate),
            settings,
        )
        return await ActivationSupervisor(settings, sessions, coordinator, shutdown).run()
