from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PAPER_BASE_URL = "https://paper-api.alpaca.markets"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    trading_mode: Literal["paper"] = "paper"
    # Use bool here so pydantic-settings can parse the string values supplied by
    # deployment platforms. The model validator below still rejects every
    # unsafe value after parsing.
    execution_enabled: bool = False
    allow_live_trading: bool = False
    alpaca_paper_trade: bool = True
    alpaca_paper_base_url: AnyHttpUrl = PAPER_BASE_URL
    alpaca_paper_api_key: SecretStr | None = None
    alpaca_paper_api_secret: SecretStr | None = None
    alpaca_paper_account_id: SecretStr | None = None
    live_trading_allowed: bool = False
    order_submission_enabled: bool = False
    alpaca_competition_starting_balance: int = Field(default=100_000, ge=100_000, le=100_000)
    supabase_url: AnyHttpUrl | None = None
    supabase_service_role_key: SecretStr | None = None
    database_url: SecretStr | None = None
    allowed_origins: str = "http://localhost:3000"

    @model_validator(mode="after")
    def enforce_paper_only(self) -> "Settings":
        if str(self.alpaca_paper_base_url).rstrip("/") != PAPER_BASE_URL:
            raise ValueError("Only Alpaca's paper API endpoint is permitted")
        if self.live_trading_allowed:
            raise ValueError("Live trading is permanently disabled")
        if self.allow_live_trading:
            raise ValueError("ALLOW_LIVE_TRADING must remain false")
        if self.execution_enabled:
            raise ValueError("EXECUTION_ENABLED must remain false in Phase 0")
        if not self.alpaca_paper_trade:
            raise ValueError("ALPACA_PAPER_TRADE must remain true")
        if self.order_submission_enabled:
            raise ValueError("Order submission is disabled in Phase 0")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
