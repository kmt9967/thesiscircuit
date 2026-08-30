from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

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
from backend.app.services.proposal import build_deterministic_proposal
from backend.app.services.risk import validate_execution
from backend.app.services.supabase import SupabaseAuditRepository
from risk.governor import evaluate_thesis

settings = get_settings()

app = FastAPI(
    title="ThesisCircuit Paper Execution API",
    version="0.2.0",
    description="Fail-closed Alpaca PAPER research and one-shot Phase 1 execution.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.allowed_origins.split(",")],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Phase1-Authorization"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "mode": "paper",
        "orders": "enabled" if settings.execution_enabled else "disabled",
    }


@app.get("/safety")
def safety() -> dict[str, object]:
    return {
        "paper_base_url": str(settings.alpaca_paper_base_url).rstrip("/"),
        "data_base_url": str(settings.alpaca_data_base_url).rstrip("/"),
        "execution_enabled": settings.execution_enabled,
        "allow_live_trading": settings.allow_live_trading,
        "alpaca_paper_trade": settings.alpaca_paper_trade,
        "live_trading_allowed": settings.live_trading_allowed,
        "order_submission_enabled": settings.execution_enabled,
        "competition_starting_balance": settings.alpaca_competition_starting_balance,
        "one_shot": True,
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


async def _build_preflight() -> Phase1Preflight:
    async with AccountService(settings) as account_service:
        account = await account_service.account()
        clock = await account_service.clock()
        positions = await account_service.positions()
        open_orders = await account_service.open_orders()
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
        proposal = build_deterministic_proposal(settings, underlying_quote.midpoint, ranked, quotes)
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
    )
    proposal.status = "APPROVED" if risk.decision == "APPROVED" else "REJECTED"
    return Phase1Preflight(
        proposal=proposal,
        risk=risk,
        account=account,
        clock=clock,
        open_orders=len(open_orders),
        open_positions=len(positions),
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
async def phase1_preflight() -> Phase1Preflight:
    try:
        return await _build_preflight()
    except (AlpacaError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _authorize_execution(token: str | None) -> None:
    if not settings.execution_enabled:
        raise HTTPException(status_code=423, detail="EXECUTION_ENABLED is false")
    if not settings.phase1_execution_token:
        raise HTTPException(status_code=423, detail="Execution token is not configured")
    if token != settings.phase1_execution_token.get_secret_value():
        raise HTTPException(status_code=403, detail="Invalid execution authorization")


@app.post("/phase1/execute")
async def phase1_execute(
    x_phase1_authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Submit the single authorized PAPER opening order; never retries blindly."""
    _authorize_execution(x_phase1_authorization)
    preflight = await _build_preflight()
    if preflight.risk.decision != "APPROVED":
        raise HTTPException(
            status_code=409,
            detail={
                "decision": preflight.risk.decision,
                "failed": [check.name for check in preflight.risk.checks if not check.passed],
            },
        )
    trace_id = str(preflight.proposal.trace_id)
    async with SupabaseAuditRepository(settings) as repository:
        existing = await repository.latest("orders", trace_id)
        if existing:
            return {"idempotent": True, "paper": True, "order": existing}
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
        async with OrderService(settings) as order_service:
            order = await order_service.submit_once(
                preflight.proposal, str(preflight.risk.id), risk_approved=True
            )
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


@app.post("/phase1/reconcile")
async def phase1_reconcile() -> dict[str, Any]:
    """Read and persist the existing one-shot order state; never submits an order."""
    async with SupabaseAuditRepository(settings) as repository:
        existing = await repository.latest("orders")
        if not existing:
            return {"paper": True, "status": "empty", "message": "No Phase 1 order exists"}
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
        execution_enabled=settings.execution_enabled,
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
