import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import get_settings
from backend.app.models import RiskDecision, ThesisRequest
from risk.governor import evaluate_thesis

settings = get_settings()

app = FastAPI(
    title="ThesisCircuit Read-Only API",
    version="0.1.0",
    description="Paper-only analysis and replay. No order submission endpoint exists.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.allowed_origins.split(",")],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "paper", "orders": "disabled"}


@app.get("/safety")
def safety() -> dict[str, object]:
    return {
        "paper_base_url": str(settings.alpaca_paper_base_url).rstrip("/"),
        "execution_enabled": settings.execution_enabled,
        "allow_live_trading": settings.allow_live_trading,
        "alpaca_paper_trade": settings.alpaca_paper_trade,
        "live_trading_allowed": settings.live_trading_allowed,
        "order_submission_enabled": settings.order_submission_enabled,
        "competition_starting_balance": settings.alpaca_competition_starting_balance,
    }


@app.get("/integrations")
async def integrations() -> dict[str, object]:
    """Read-only connectivity proof; this function never submits an order."""
    alpaca_configured = bool(
        settings.alpaca_paper_api_key and settings.alpaca_paper_api_secret
    )
    supabase_configured = bool(settings.supabase_url and settings.supabase_service_role_key)
    result: dict[str, object] = {
        "alpaca": {"configured": alpaca_configured, "connected": False, "paper": True},
        "supabase": {"configured": supabase_configured, "connected": False},
    }

    async with httpx.AsyncClient(timeout=8.0) as client:
        if alpaca_configured:
            headers = {
                "APCA-API-KEY-ID": settings.alpaca_paper_api_key.get_secret_value(),
                "APCA-API-SECRET-KEY": settings.alpaca_paper_api_secret.get_secret_value(),
            }
            try:
                account_response = await client.get(
                    f"{str(settings.alpaca_paper_base_url).rstrip('/')}/v2/account",
                    headers=headers,
                )
                orders_response = await client.get(
                    f"{str(settings.alpaca_paper_base_url).rstrip('/')}/v2/orders",
                    params={"status": "all", "limit": 1},
                    headers=headers,
                )
                account = account_response.json() if account_response.is_success else {}
                orders = orders_response.json() if orders_response.is_success else []
                result["alpaca"] = {
                    "configured": True,
                    "connected": account_response.is_success and orders_response.is_success,
                    "paper": True,
                    "account_status": account.get("status"),
                    "starting_cash": account.get("cash"),
                    "orders_placed": len(orders) if isinstance(orders, list) else None,
                }
            except httpx.HTTPError:
                pass

        if supabase_configured:
            try:
                response = await client.get(
                    f"{str(settings.supabase_url).rstrip('/')}/rest/v1/analysis_runs",
                    params={"select": "id", "limit": 1},
                    headers={
                        "apikey": settings.supabase_service_role_key.get_secret_value(),
                    },
                )
                result["supabase"] = {
                    "configured": True,
                    "connected": response.is_success,
                    "status_code": response.status_code,
                }
            except httpx.HTTPError:
                pass

    return result


@app.post("/evaluate", response_model=RiskDecision)
def evaluate(request: ThesisRequest) -> RiskDecision:
    return evaluate_thesis(request)
