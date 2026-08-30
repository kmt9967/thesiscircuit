from typing import Literal

from pydantic import BaseModel, Field


class ThesisRequest(BaseModel):
    symbol: str = Field(pattern=r"^[A-Z.]{1,10}$")
    strategy: Literal["defined-risk-call-spread", "defined-risk-put-spread"]
    max_loss_usd: float = Field(gt=0, le=1_000)
    days_to_expiry: int = Field(ge=7, le=45)
    confidence: float = Field(ge=0, le=1)
    data_age_seconds: int = Field(ge=0)


class RiskDecision(BaseModel):
    approved_for_research: bool
    mode: Literal["paper"] = "paper"
    vetoes: list[str]
    order_submission_enabled: Literal[False] = False

