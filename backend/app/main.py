from __future__ import annotations

import asyncio
import secrets
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import get_settings
from backend.app.models import (
    AssetSnapshot,
    DashboardState,
    Phase1Preflight,
    RiskDecision,
    ThesisRequest,
)
from backend.app.services.alpaca import AccountService, AlpacaError, MarketDataService, OrderService
from backend.app.services.preflight import TRACE_ID, PreflightBlocked, TwoStagePreflight
from backend.app.services.proposal import build_deterministic_proposal
from backend.app.services.risk import validate_execution
from backend.app.services.supabase import SupabaseAuditRepository
from risk.governor import evaluate_thesis

settings = get_settings()
configured_execution_enabled = settings.execution_enabled
PHASE1_RETIRED = True
phase2_batch_status: dict[str, Any] = {"status": "not_configured", "execution_enabled": False}


@asynccontextmanager
async def lifespan(app: FastAPI):
    from backend.app.phase2.data import ReadOnlyMarketProvider
    from backend.app.phase2.engine import assert_dry_run, run_batch
    from backend.app.phase2.policy import Policy
    from backend.app.phase2.repository import Phase2Repository

    if PHASE1_RETIRED:
        assert_dry_run(settings)  # Production refuses enabled execution; historical tests isolate v1.
    async def research():
        phase2_batch_status["status"] = "running"
        try:
            async with Phase2Repository(settings) as repository:
                ids = await run_batch(
                    ReadOnlyMarketProvider(settings), repository, settings,
                    Policy(emergency_kill=settings.phase2_emergency_kill,
                           daily_drawdown_fraction=settings.phase2_daily_drawdown_fraction),
                    settings.phase2_dry_run_batch,
                )
            phase2_batch_status.update(status="completed", cycle_ids=ids)
        except (httpx.HTTPError, RuntimeError, ValueError, TypeError, KeyError) as exc:
            # Never log exception bodies/headers/provider payloads containing server credentials.
            phase2_batch_status.update(status="blocked", error_type=type(exc).__name__)

    task = asyncio.create_task(research()) if settings.phase2_dry_run_batch else None
    yield
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

app = FastAPI(
    title="ThesisCircuit Paper Execution API",
    version="0.3.0",
    description="Deterministic PAPER options research; Phase 2 Part 1 has no execution authority.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.allowed_origins.split(",")],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Phase1-Authorization"],
)


async def _execution_enabled() -> bool:
    if PHASE1_RETIRED:
        return False
    if not settings.execution_enabled:
        return False
    try:
        async with SupabaseAuditRepository(settings) as repository:
            return await repository.event(TRACE_ID, 0) is None
    except (httpx.HTTPError, RuntimeError, ValueError):
        return False


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "mode": "paper",
        "orders": "enabled" if await _execution_enabled() else "disabled",
    }


@app.get("/safety")
async def safety() -> dict[str, object]:
    enabled = await _execution_enabled()
    return {
        "paper_base_url": str(settings.alpaca_paper_base_url).rstrip("/"),
        "data_base_url": str(settings.alpaca_data_base_url).rstrip("/"),
        "execution_enabled": enabled,
        "configured_execution_enabled": configured_execution_enabled,
        "allow_live_trading": settings.allow_live_trading,
        "alpaca_paper_trade": settings.alpaca_paper_trade,
        "live_trading_allowed": settings.live_trading_allowed,
        "order_submission_enabled": enabled,
        "competition_starting_balance": settings.alpaca_competition_starting_balance,
        "one_shot": True,
        "phase1_authorization_retired": PHASE1_RETIRED,
        "phase2_mode": "DRY_RUN",
        "phase2_execution_authorized": False,
    }


@app.get("/integrations")
async def integrations() -> dict[str, object]:
    alpaca_configured = bool(settings.alpaca_paper_api_key and settings.alpaca_paper_api_secret)
    supabase_configured = bool(settings.supabase_url and settings.supabase_service_role_key)
    result: dict[str, object] = {
        "alpaca": {"configured": alpaca_configured, "connected": False, "paper": True},
        "supabase": {"configured": supabase_configured, "connected": False},
    }
    try:
        async with AccountService(settings) as service:
            account = await service.account()
            orders = await service.open_orders()
            all_orders = await service.all_orders()
            result["alpaca"] = {
                "configured": True,
                "connected": True,
                "paper": True,
                "account_status": account.status,
                "starting_cash": account.cash,
                "open_orders": len(orders),
                "orders_placed": len(all_orders),
            }
    except (AlpacaError, RuntimeError):
        pass
    try:
        async with SupabaseAuditRepository(settings) as repository:
            await repository.latest("trade_proposals")
            result["supabase"] = {"configured": True, "connected": True, "status_code": 200}
    except (httpx.HTTPError, RuntimeError):
        pass
    return result


@app.post("/evaluate", response_model=RiskDecision)
def evaluate(request: ThesisRequest) -> RiskDecision:
    return evaluate_thesis(request)


async def _build_preflight(
    stage: Literal["readiness", "execution"], preferred_symbol: str,
) -> Phase1Preflight:
    async with AccountService(settings) as account_service:
        account = await account_service.account()
        clock = await account_service.clock()
        positions = await account_service.positions()
        open_orders = await account_service.open_orders()
        all_orders = await account_service.all_orders()
    async with MarketDataService(settings) as market_service:
        underlying_quote = await market_service.stock_quote(settings.phase1_symbol)
        contracts = await market_service.option_contracts(
            settings.phase1_symbol, settings.phase1_expiration_date
        )
        ranked = sorted(
            [contract for contract in contracts if contract.tradable],
            key=lambda contract: abs(contract.strike_price - underlying_quote.midpoint),
        )[:300]
        quotes = await market_service.option_quotes([contract.symbol for contract in ranked])
        proposal = build_deterministic_proposal(
            settings, underlying_quote.midpoint, ranked, quotes, preferred_symbol
        )
        selected_contract = next(
            contract for contract in ranked if contract.symbol == proposal.instrument
        )
        contract_asset = AssetSnapshot(
            symbol=selected_contract.symbol,
            asset_class="us_option",
            status=selected_contract.status,
            tradable=selected_contract.tradable,
            options_enabled=True,
        )
    async with OrderService(settings) as order_service:
        duplicate = await order_service.by_client_order_id(proposal.client_order_id) is not None
    risk = validate_execution(
        settings,
        proposal,
        account,
        clock,
        contract_asset,
        open_orders,
        positions,
        duplicate,
        stage=stage,
        total_orders=len(all_orders),
    )
    proposal.status = "APPROVED" if risk.decision == "APPROVED" else "REJECTED"
    return Phase1Preflight(
        stage=stage,
        result=("READY_FOR_EXECUTION" if stage == "readiness" else "APPROVED_FOR_SINGLE_ORDER")
        if risk.decision == "APPROVED" else "REJECTED",
        proposal=proposal,
        risk=risk,
        account=account,
        clock=clock,
        open_orders=len(open_orders),
        open_positions=len(positions),
        total_orders=len(all_orders),
    )


@app.get("/phase1/account")
async def phase1_account() -> dict[str, Any]:
    try:
        async with AccountService(settings) as service:
            open_orders = await service.open_orders()
            all_orders = await service.all_orders()
            return {
                "account": (await service.account()).model_dump(mode="json"),
                "clock": (await service.clock()).model_dump(mode="json"),
                "positions": await service.positions(),
                "open_orders": open_orders,
                "orders_placed": len(all_orders),
                "paper": True,
            }
    except AlpacaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/phase1/market/{symbol}")
async def phase1_market(symbol: str) -> dict[str, Any]:
    if symbol != settings.phase1_symbol:
        raise HTTPException(status_code=400, detail="Phase 1 permits SPY only")
    try:
        async with MarketDataService(settings) as service:
            return {
                "asset": (await service.asset(symbol)).model_dump(mode="json"),
                "quote": (await service.stock_quote(symbol)).model_dump(mode="json"),
                "bars": await service.bars(symbol),
                "paper": True,
            }
    except AlpacaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/phase1/preflight", response_model=Phase1Preflight)
@app.post("/phase1/preflight/readiness", response_model=Phase1Preflight)
async def phase1_preflight() -> Phase1Preflight:
    if PHASE1_RETIRED:
        raise HTTPException(status_code=410, detail="Phase 1 preflight retired; historical audit preserved")
    if configured_execution_enabled:
        raise HTTPException(status_code=423, detail="Railway execution must be disabled before readiness")
    try:
        async with SupabaseAuditRepository(settings) as repository:
            return await TwoStagePreflight(repository, _build_preflight).readiness()
    except (AlpacaError, ValueError, PreflightBlocked, httpx.HTTPError) as exc:
        detail = str(exc) or f"Readiness integration failed ({type(exc).__name__}); execution not authorized"
        raise HTTPException(status_code=409, detail=detail) from exc


def _authorize_execution(token: str | None) -> None:
    if PHASE1_RETIRED:
        raise HTTPException(status_code=410, detail="Phase 1 execution authorization permanently retired")
    if not settings.execution_enabled:
        raise HTTPException(status_code=423, detail="EXECUTION_ENABLED is false")
    if not settings.phase1_execution_token:
        raise HTTPException(status_code=423, detail="Execution token is not configured")
    if not token or not secrets.compare_digest(token, settings.phase1_execution_token.get_secret_value()):
        raise HTTPException(status_code=403, detail="Invalid execution authorization")


@app.post("/phase1/preflight/execution", response_model=Phase1Preflight)
async def phase1_execution_preflight(
    readiness_id: UUID | None = None,
    x_phase1_authorization: str | None = Header(default=None),
) -> Phase1Preflight:
    _authorize_execution(x_phase1_authorization)
    try:
        async with SupabaseAuditRepository(settings) as repository:
            result = await TwoStagePreflight(repository, _build_preflight).execution(readiness_id)
            if result.result != "APPROVED_FOR_SINGLE_ORDER":
                settings.execution_enabled = False
            return result
    except (AlpacaError, ValueError, PreflightBlocked, httpx.HTTPError) as exc:
        settings.execution_enabled = False
        raise HTTPException(status_code=409, detail="Execution preflight blocked; disable and repeat readiness") from exc


async def _phase1_execute_impl(
    readiness_id: UUID | None = None,
    execution_id: UUID | None = None,
    x_phase1_authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Submit the single authorized PAPER opening order; never retries blindly."""
    _authorize_execution(x_phase1_authorization)
    async with SupabaseAuditRepository(settings) as repository:
        coordinator = TwoStagePreflight(repository, _build_preflight)
        try:
            preflight = await coordinator.submission_preflight(readiness_id, execution_id)
        except (AlpacaError, ValueError, PreflightBlocked, httpx.HTTPError) as exc:
            settings.execution_enabled = False
            raise HTTPException(status_code=409, detail="Submission blocked; reconcile before any further action") from exc
        trace_id = str(preflight.proposal.trace_id)
        # Claim before writing canonical audit rows; losing callers cannot overwrite them.
        await coordinator.claim(preflight)
        await repository.insert("trade_proposals", preflight.proposal.model_dump(mode="json"))
        await repository.insert("risk_checks", preflight.risk.model_dump(mode="json"))
        await repository.insert(
            "decisions",
            {
                "id": str(preflight.risk.id),
                "trace_id": trace_id,
                "proposal_id": str(preflight.proposal.id),
                "decision": preflight.risk.decision,
                "reason": "All deterministic gates approved",
                "paper": True,
            },
        )
        await repository.insert(
            "system_events",
            {
                "trace_id": trace_id,
                "sequence": 1,
                "kind": "proposal_created",
                "payload": {"instrument": preflight.proposal.instrument, "paper": True},
                "paper": True,
            },
        )
        await repository.insert(
            "system_events",
            {
                "trace_id": trace_id,
                "sequence": 2,
                "kind": "risk_approved",
                "payload": {"max_loss": preflight.proposal.max_theoretical_loss},
                "paper": True,
            },
        )
        try:
            async with OrderService(settings) as order_service:
                order = await order_service.submit_once(
                    preflight.proposal, str(preflight.risk.id), risk_approved=True,
                    stages_verified=True, submission_claimed=True,
                )
        finally:
            settings.execution_enabled = False
        order_row = order.model_dump(mode="json")
        await repository.insert("orders", order_row)
        await repository.insert(
            "system_events",
            {
                "trace_id": trace_id,
                "sequence": 3,
                "kind": "paper_order_submitted",
                "payload": {
                    "client_order_id": order.client_order_id,
                    "status": order.status,
                    "paper": True,
                },
                "paper": True,
            },
        )
    return {"idempotent": False, "paper": True, "order": order_row}


@app.post("/phase1/execute")
async def phase1_execute(
    readiness_id: UUID | None = None,
    execution_id: UUID | None = None,
    x_phase1_authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _authorize_execution(x_phase1_authorization)
    try:
        return await _phase1_execute_impl(readiness_id, execution_id, x_phase1_authorization)
    finally:
        # Also shut down on pre-submit audit failure, malformed response, or cancellation.
        settings.execution_enabled = False


@app.post("/phase1/reconcile")
async def phase1_reconcile() -> dict[str, Any]:
    """Read and persist the existing one-shot order state; never submits an order."""
    async with SupabaseAuditRepository(settings) as repository:
        existing = await repository.latest("orders")
        if not existing:
            claim = await repository.event(TRACE_ID, 0)
            if not claim:
                return {"paper": True, "status": "empty", "message": "No Phase 1 order exists"}
            preflight = Phase1Preflight.model_validate(claim["payload"]["preflight"])
            async with OrderService(settings) as order_service:
                raw = await order_service.by_client_order_id(preflight.proposal.client_order_id)
                if not raw:
                    return {"paper": True, "status": "uncertain", "message": "Claim exists; no broker order found. Never retry."}
                existing = order_service._record(
                    raw, preflight.proposal, str(preflight.risk.id)
                ).model_dump(mode="json")
            await repository.insert("orders", existing, on_conflict="alpaca_order_id")
        async with OrderService(settings) as order_service:
            raw = await order_service.by_id(existing["alpaca_order_id"])
        existing.update(
            {
                "status": raw.get("status", existing.get("status")),
                "filled_quantity": float(raw.get("filled_qty") or 0),
                "filled_average_price": float(raw["filled_avg_price"])
                if raw.get("filled_avg_price")
                else None,
                "filled_at": raw.get("filled_at"),
            }
        )
        await repository.insert("orders", existing, on_conflict="alpaca_order_id")
        if existing.get("filled_quantity", 0) > 0:
            await repository.insert(
                "fills",
                {
                    "trace_id": existing["trace_id"],
                    "order_id": existing["alpaca_order_id"],
                    "instrument": existing["instrument"],
                    "quantity": existing["filled_quantity"],
                    "price": existing["filled_average_price"],
                    "filled_at": existing["filled_at"],
                    "paper": True,
                },
                on_conflict="order_id,filled_at",
            )
        async with AccountService(settings) as account_service:
            positions = await account_service.positions()
            account = await account_service.account()
        position = next(
            (item for item in positions if item.get("symbol") == existing["instrument"]), None
        )
        await repository.insert(
            "positions_snapshots",
            {
                "trace_id": existing["trace_id"],
                "instrument": existing["instrument"],
                "position": position,
                "account": account.model_dump(mode="json"),
                "paper": True,
            },
        )
        await repository.insert("system_events", {
            "trace_id": existing["trace_id"], "sequence": 4, "kind": "actual_alpaca_state",
            "payload": {"order": existing, "position": position,
                        "account": account.model_dump(mode="json")}, "paper": True,
        }, on_conflict="trace_id,sequence")
        await repository.insert("system_events", {
            "trace_id": existing["trace_id"], "sequence": 5, "kind": "execution_shutdown",
            "payload": {"execution_enabled": await _execution_enabled(),
                        "configured_execution_enabled": configured_execution_enabled}, "paper": True,
        }, on_conflict="trace_id,sequence")
        return {"paper": True, "order": existing, "position": position}


@app.get("/phase1/dashboard", response_model=DashboardState)
async def phase1_dashboard() -> DashboardState:
    account = None
    alpaca_connected = False
    supabase_connected = False
    latest_proposal = latest_risk = latest_order = latest_fill = latest_position = None
    timeline: list[dict[str, Any]] = []
    try:
        async with AccountService(settings) as account_service:
            account = await account_service.account()
            alpaca_connected = True
    except (AlpacaError, RuntimeError):
        pass
    try:
        async with SupabaseAuditRepository(settings) as repository:
            latest_order = await repository.latest("orders")
            trace_id = latest_order.get("trace_id") if latest_order else None
            latest_proposal = await repository.latest("trade_proposals", trace_id)
            latest_risk = await repository.latest("risk_checks", trace_id)
            latest_fill = await repository.latest("fills", trace_id)
            latest_position = await repository.latest("positions_snapshots", trace_id)
            timeline = await repository.timeline(trace_id) if trace_id else []
            supabase_connected = True
    except (httpx.HTTPError, RuntimeError):
        pass
    return DashboardState(
        generated_at=datetime.now(timezone.utc),
        execution_enabled=await _execution_enabled(),
        account=account,
        integrations={
            "alpaca": alpaca_connected,
            "supabase": supabase_connected,
            "risk_engine": True,
        },
        latest_proposal=latest_proposal,
        latest_risk=latest_risk,
        latest_order=latest_order,
        latest_fill=latest_fill,
        latest_position=latest_position,
        timeline=timeline,
    )


@app.get("/phase2/dashboard")
async def phase2_dashboard() -> dict[str, Any]:
    from backend.app.phase2.repository import Phase2Repository
    try:
        async with Phase2Repository(settings) as repository:
            rows = await repository.recent("autonomous_cycles", 5)
            shadows = await repository.recent("shadow_trades")
            marks = await repository.recent("shadow_marks", 100)
        return {"mode": "DRY_RUN", "execution_enabled": False, "database_connected": True,
                "batch_status": phase2_batch_status, "latest": rows[0]["payload"] if rows else None,
                "cycles": [{"id": r["id"], "created_at": r["created_at"],
                            "decision": r["payload"]["decision"]} for r in rows],
                "shadows": [r["payload"] for r in shadows], "marks": [r["payload"] for r in marks]}
    except (httpx.HTTPError, ValueError, TypeError, RuntimeError):
        raise HTTPException(status_code=503, detail="Phase 2 audit unavailable; execution remains disabled")
