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
        "live_trading_allowed": settings.live_trading_allowed,
        "order_submission_enabled": settings.order_submission_enabled,
        "competition_starting_balance": settings.alpaca_competition_starting_balance,
    }


@app.post("/evaluate", response_model=RiskDecision)
def evaluate(request: ThesisRequest) -> RiskDecision:
    return evaluate_thesis(request)

