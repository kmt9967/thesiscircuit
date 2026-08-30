import pytest
from pydantic import ValidationError

from backend.app.config import PAPER_BASE_URL, Settings
from backend.app.models import ThesisRequest
from risk.governor import evaluate_thesis


def test_defaults_are_paper_only() -> None:
    settings = Settings(_env_file=None)
    assert str(settings.alpaca_paper_base_url).rstrip("/") == PAPER_BASE_URL
    assert settings.live_trading_allowed is False
    assert settings.execution_enabled is False
    assert settings.allow_live_trading is False
    assert settings.alpaca_paper_trade is True
    assert settings.order_submission_enabled is False
    assert settings.alpaca_competition_starting_balance == 100_000


def test_safe_environment_strings_are_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXECUTION_ENABLED", "false")
    monkeypatch.setenv("ALLOW_LIVE_TRADING", "false")
    monkeypatch.setenv("ALPACA_PAPER_TRADE", "true")

    settings = Settings(_env_file=None)

    assert settings.execution_enabled is False
    assert settings.allow_live_trading is False
    assert settings.alpaca_paper_trade is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ALPACA_PAPER_BASE_URL", "https://" + "api.alpaca.markets"),
        ("LIVE_TRADING_ALLOWED", "true"),
        ("ORDER_SUBMISSION_ENABLED", "true"),
        ("EXECUTION_ENABLED", "true"),
        ("ALLOW_LIVE_TRADING", "true"),
        ("ALPACA_PAPER_TRADE", "false"),
        ("ALPACA_COMPETITION_STARTING_BALANCE", "99999"),
    ],
)
def test_unsafe_environment_is_rejected(monkeypatch: pytest.MonkeyPatch, field: str, value: str) -> None:
    monkeypatch.setenv(field, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_risk_veto_is_deterministic() -> None:
    request = ThesisRequest(
        symbol="SPY",
        strategy="defined-risk-call-spread",
        max_loss_usd=700,
        days_to_expiry=10,
        confidence=0.4,
        data_age_seconds=90,
    )
    decision = evaluate_thesis(request)
    assert decision.approved_for_research is False
    assert decision.order_submission_enabled is False
    assert len(decision.vetoes) == 4
