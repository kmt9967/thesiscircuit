from datetime import datetime
from functools import lru_cache
from typing import Literal
from uuid import UUID

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PAPER_BASE_URL = "https://paper-api.alpaca.markets"
DATA_BASE_URL = "https://data.alpaca.markets"


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
    alpaca_data_base_url: AnyHttpUrl = DATA_BASE_URL
    alpaca_market_data_feed: Literal["indicative", "opra"] = "indicative"
    live_trading_allowed: bool = False
    order_submission_enabled: bool = False
    alpaca_competition_starting_balance: int = Field(default=100_000, ge=100_000, le=100_000)
    supabase_url: AnyHttpUrl | None = None
    supabase_service_role_key: SecretStr | None = None
    database_url: SecretStr | None = None
    allowed_origins: str = "http://localhost:3000"
    phase1_symbol: Literal["SPY"] = "SPY"
    phase1_expiration_date: str = "2026-09-04"
    phase1_max_risk_usd: float = Field(default=250.0, gt=0, le=250.0)
    phase1_max_data_age_seconds: int = Field(default=120, ge=1, le=300)
    phase1_official_start_utc: str = "2026-08-31T13:30:00Z"
    phase1_official_end_utc: str = "2026-09-04T13:30:00Z"
    phase1_execution_token: SecretStr | None = None
    phase2_dry_run_batch: str = ""
    phase25_synthetic_batch: str = ""
    phase26_synthetic_batch: str = ""
    autonomous_trading_enabled: bool = False
    phase2_execution_token: SecretStr | None = None
    phase2_active_session_id: UUID | None = None
    phase2_session_starts_at: datetime | None = None
    phase2_session_expires_at: datetime | None = None
    phase2_max_order_budget: int = Field(default=0, ge=0, le=1)
    railway_project_access_token: SecretStr | None = None
    railway_project_id: str = ""
    railway_environment_id: str = ""
    railway_service_id: str = ""
    phase2_cycle_seconds: int = Field(default=60, ge=60, le=3600)
    phase2_emergency_kill: bool = False
    phase2_daily_drawdown_fraction: float = Field(default=0.01, gt=0, le=0.01)

    @model_validator(mode="after")
    def enforce_paper_only(self) -> "Settings":
        if str(self.alpaca_paper_base_url).rstrip("/") != PAPER_BASE_URL:
            raise ValueError("Only Alpaca's paper API endpoint is permitted")
        if str(self.alpaca_data_base_url).rstrip("/") != DATA_BASE_URL:
            raise ValueError("Only Alpaca's market data endpoint is permitted")
        if self.live_trading_allowed:
            raise ValueError("Live trading is permanently disabled")
        if self.allow_live_trading:
            raise ValueError("ALLOW_LIVE_TRADING must remain false")
        if self.execution_enabled != self.autonomous_trading_enabled and self.phase2_execution_token:
            raise ValueError("Phase 2 execution and autonomous gates must change together")
        if self.autonomous_trading_enabled and (not self.execution_enabled or not self.phase2_execution_token):
            raise ValueError("Autonomous mode requires separate Phase 2 server authorization and execution gate")
        if self.autonomous_trading_enabled and not all((self.phase2_active_session_id,
                self.phase2_session_starts_at,self.phase2_session_expires_at,
                self.phase2_max_order_budget,self.railway_project_access_token,
                self.railway_project_id,self.railway_environment_id,self.railway_service_id)):
            raise ValueError("Bounded activation and verified Railway shutdown configuration required")
        if self.phase2_session_starts_at and self.phase2_session_starts_at.tzinfo is None:
            raise ValueError("Phase 2 session start must include timezone")
        if self.phase2_session_expires_at and self.phase2_session_expires_at.tzinfo is None:
            raise ValueError("Phase 2 session expiry must include timezone")
        if self.execution_enabled and not (self.phase1_execution_token or self.phase2_execution_token):
            raise ValueError("Phase 1 execution requires a server-only authorization token")
        if not self.alpaca_paper_trade:
            raise ValueError("ALPACA_PAPER_TRADE must remain true")
        if self.order_submission_enabled:
            raise ValueError("Order submission is disabled in Phase 0")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
