from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PAPER_BASE_URL = "https://paper-api.alpaca.markets"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    trading_mode: Literal["paper"] = "paper"
    alpaca_paper_base_url: AnyHttpUrl = PAPER_BASE_URL
    live_trading_allowed: bool = False
    order_submission_enabled: bool = False
    alpaca_competition_starting_balance: int = Field(default=100_000, ge=100_000, le=100_000)
    allowed_origins: str = "http://localhost:3000"

    @model_validator(mode="after")
    def enforce_paper_only(self) -> "Settings":
        if str(self.alpaca_paper_base_url).rstrip("/") != PAPER_BASE_URL:
            raise ValueError("Only Alpaca's paper API endpoint is permitted")
        if self.live_trading_allowed:
            raise ValueError("Live trading is permanently disabled")
        if self.order_submission_enabled:
            raise ValueError("Order submission is disabled in Phase 0")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

