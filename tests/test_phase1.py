import asyncio
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
import pytest
from pydantic import ValidationError

from backend.app.config import Settings
from backend.app.models import (
    AccountSnapshot,
    AssetSnapshot,
    MarketClock,
    OptionContract,
    QuoteSnapshot,
    TradeProposal,
)
from backend.app.services.alpaca import AlpacaError, OrderService
from backend.app.services.proposal import build_deterministic_proposal
from backend.app.services.risk import validate_execution
from backend.app.services.supabase import SupabaseAuditRepository

NOW = datetime(2026, 8, 31, 14, 0, tzinfo=timezone.utc)


def settings(**overrides: object) -> Settings:
    values = {
        "alpaca_paper_api_key": "paper-key",
        "alpaca_paper_api_secret": "paper-secret",
        "supabase_url": "https://project.supabase.co",
        "supabase_service_role_key": "server-secret",
        "phase1_execution_token": "one-shot-token",
        "execution_enabled": True,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def proposal(data_timestamp: datetime = NOW) -> TradeProposal:
    contract = OptionContract(
        symbol="SPY260904C00650000",
        underlying_symbol="SPY",
        expiration_date="2026-09-04",
        strike_price=650,
        option_type="call",
        status="active",
        tradable=True,
    )
    quote = QuoteSnapshot(
        symbol=contract.symbol,
        bid_price=1.0,
        ask_price=1.2,
        timestamp=data_timestamp,
        source="alpaca:indicative",
    )
    return build_deterministic_proposal(settings(), 649.5, [contract], {contract.symbol: quote})


def account(**overrides: object) -> AccountSnapshot:
    values = {
        "status": "ACTIVE",
        "cash": 100_000,
        "buying_power": 100_000,
        "portfolio_value": 100_000,
        "equity": 100_000,
        "last_equity": 100_000,
        "options_buying_power": 100_000,
        "account_number_suffix": "1234",
    }
    values.update(overrides)
    return AccountSnapshot(**values)


def clock(is_open: bool = True) -> MarketClock:
    return MarketClock(
        timestamp=NOW,
        is_open=is_open,
        next_open=NOW + timedelta(days=1),
        next_close=NOW + timedelta(hours=6),
    )


def asset(tradable: bool = True) -> AssetSnapshot:
    return AssetSnapshot(
        symbol="SPY260904C00650000",
        asset_class="us_option",
        status="active",
        tradable=tradable,
    )


def risk(**overrides: object):
    values = {
        "settings": settings(),
        "proposal": proposal(),
        "account": account(),
        "clock": clock(),
        "asset": asset(),
        "open_orders": [],
        "positions": [],
        "duplicate_order": False,
        "now": NOW,
    }
    values.update(overrides)
    return validate_execution(**values)


def test_proposal_serialization_is_canonical() -> None:
    item = proposal()
    restored = TradeProposal.model_validate_json(item.model_dump_json())
    assert restored == item
    assert restored.quantity == 1
    assert restored.max_theoretical_loss == 120
    assert restored.client_order_id.startswith("thesiscircuit-phase1-")


def test_invalid_quantity_is_rejected() -> None:
    payload = proposal().model_dump()
    payload["quantity"] = 2
    with pytest.raises(ValidationError):
        TradeProposal.model_validate(payload)


@pytest.mark.parametrize(
    ("changes", "failed_gate"),
    [
        ({"settings": settings(execution_enabled=False)}, "execution_gate"),
        ({"account": account(buying_power=10)}, "buying_power"),
        ({"proposal": proposal(NOW - timedelta(minutes=10))}, "fresh_data"),
        ({"asset": asset(False)}, "instrument_tradable"),
        ({"duplicate_order": True}, "unique_client_order_id"),
        ({"open_orders": [{"symbol": "SPY260904C00650000"}]}, "no_conflicting_order"),
        ({"positions": [{"symbol": "SPY260904C00650000"}]}, "no_existing_position"),
        ({"clock": clock(False)}, "market_state"),
    ],
)
def test_risk_rejects_unsafe_state(changes: dict[str, object], failed_gate: str) -> None:
    decision = risk(**changes)
    assert decision.decision == "REJECTED"
    assert failed_gate in {check.name for check in decision.checks if not check.passed}


def test_risk_rejects_max_risk_exceeded() -> None:
    item = proposal()
    item.max_theoretical_loss = 251
    item.estimated_max_loss = 251
    decision = risk(proposal=item)
    assert decision.decision == "REJECTED"
    assert "bounded_max_loss" in {check.name for check in decision.checks if not check.passed}


def test_risk_approves_only_complete_safe_state() -> None:
    decision = risk()
    assert decision.decision == "APPROVED"
    assert len(decision.checks) == 17
    assert all(check.passed for check in decision.checks)


def test_missing_risk_approval_blocks_order() -> None:
    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(500))) as c:
            service = OrderService(settings(), c)
            with pytest.raises(AlpacaError, match="APPROVED"):
                await service.submit_once(proposal(), "risk-id", risk_approved=False)

    asyncio.run(run())


def test_timeout_queries_by_client_id_without_second_post() -> None:
    calls = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            calls["post"] += 1
            raise httpx.ReadTimeout("uncertain", request=request)
        calls["get"] += 1
        if calls["get"] == 1:
            return httpx.Response(404, json={"message": "order not found"})
        return httpx.Response(
            200,
            json={
                "id": "11111111-1111-1111-1111-111111111111",
                "submitted_at": NOW.isoformat(),
                "status": "accepted",
                "qty": "1",
                "filled_qty": "0",
            },
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            service = OrderService(settings(), c)
            record = await service.submit_once(proposal(), str(UUID(int=1)), risk_approved=True)
            assert record.status == "accepted"

    asyncio.run(run())
    assert calls == {"post": 1, "get": 2}


def test_supabase_persistence_returns_inserted_row() -> None:
    row = {"id": "11111111-1111-1111-1111-111111111111", "paper": True}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["apikey"] == "server-secret"
        assert json.loads(request.content) == row
        return httpx.Response(201, json=[row])

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            repository = SupabaseAuditRepository(settings(), c)
            assert await repository.insert("trade_proposals", row) == row

    asyncio.run(run())
