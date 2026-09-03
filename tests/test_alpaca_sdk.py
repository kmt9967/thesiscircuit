import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import requests

import backend.app.services.alpaca_sdk as sdk
from backend.app.config import DATA_BASE_URL, PAPER_BASE_URL, Settings


def configured(*, enabled=False):
    values = {"alpaca_paper_api_key": "unit-paper-key",
              "alpaca_paper_api_secret": "unit-paper-secret",
              "phase2_execution_token": "x" * 32,
              "execution_enabled": enabled,
              "autonomous_trading_enabled": enabled}
    if enabled:
        now = datetime.now(timezone.utc)
        values.update(phase2_active_session_id="00000000-0000-4000-8000-000000000001",
            phase2_session_starts_at=now, phase2_session_expires_at=now+timedelta(minutes=15),
            phase2_max_order_budget=1, railway_project_access_token="test-project-token",
            railway_project_id="test-project", railway_environment_id="test-environment",
            railway_service_id="test-service")
    return Settings(**values)


class StubSession:
    def __init__(self):
        self.remaining_requests = 0

    def close(self):
        return None


class StubTrading:
    def __init__(self, *args, **kwargs):
        assert kwargs == {"paper": True, "raw_data": True, "url_override": PAPER_BASE_URL}
        self._session = StubSession()
        self._retry = 99
        self.submissions = []

    def get_account(self):
        return {"status": "ACTIVE"}

    def submit_order(self, request):
        self.submissions.append(request)
        return {"id": "paper-order", "status": "accepted"}


class StubData:
    def __init__(self, *args, **kwargs):
        assert kwargs == {"raw_data": True, "url_override": DATA_BASE_URL}
        self._session = StubSession()
        self._retry = 99


def adapter(monkeypatch, *, enabled=False):
    monkeypatch.setattr(sdk, "TradingClient", StubTrading)
    monkeypatch.setattr(sdk, "StockHistoricalDataClient", StubData)
    monkeypatch.setattr(sdk, "OptionHistoricalDataClient", StubData)
    return sdk.OfficialAlpacaAdapter(configured(enabled=enabled))


def test_official_adapter_is_paper_only_and_disables_sdk_retries(monkeypatch):
    client = adapter(monkeypatch)
    assert client.trade._retry == client.stock._retry == client.options._retry == 0
    assert all(c._session.base in {PAPER_BASE_URL, DATA_BASE_URL}
               for c in (client.trade, client.stock, client.options))
    with pytest.raises(RuntimeError, match="paper configuration"):
        sdk.OfficialAlpacaAdapter(configured().model_copy(update={"allow_live_trading": True}))


def test_guarded_sdk_transport_enforces_host_budget_timeout_and_no_redirect(monkeypatch):
    observed = []

    def fake_request(self, method, url, **kwargs):
        observed.append((method, url, kwargs))
        response = requests.Response()
        response.status_code = 200
        return response

    monkeypatch.setattr(requests.Session, "request", fake_request)
    session = sdk.GuardedSession(DATA_BASE_URL, configured())
    with pytest.raises(RuntimeError, match="budget"):
        session.get(DATA_BASE_URL + "/v2/stocks/SPY/bars")
    session.remaining_requests = 1
    session.get(DATA_BASE_URL + "/v2/stocks/SPY/bars")
    assert observed[0][2]["timeout"] == 10
    assert observed[0][2]["allow_redirects"] is False
    assert session.remaining_requests == 0
    session.remaining_requests = 1
    with pytest.raises(RuntimeError, match="endpoint"):
        session.get("https://example.invalid/v2/account")


def test_sdk_api_error_status_is_sanitized(monkeypatch):
    client = adapter(monkeypatch)

    def failed():
        response = requests.Response()
        response.status_code = 404
        error = requests.HTTPError(response=response)
        raise sdk.APIError('{"code":404,"message":"sensitive provider body"}', error)

    client.trade.get_account = failed
    response = asyncio.run(client.get(PAPER_BASE_URL + "/v2/account"))
    assert response.status_code == 404
    assert response.json() == {"error": "Alpaca SDK request failed"}


def test_sdk_submission_is_one_bounded_official_call(monkeypatch):
    client = adapter(monkeypatch, enabled=True)
    payload = {
        "symbol": "QQQ260904C00600000",
        "qty": "1",
        "side": "buy",
        "type": "limit",
        "time_in_force": "day",
        "limit_price": "1.25",
        "client_order_id": "thesiscircuit-phase2-unit-only",
        "position_intent": "buy_to_open",
    }
    response = asyncio.run(client.post(PAPER_BASE_URL + "/v2/orders", json=payload))
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert len(client.trade.submissions) == 1
    with pytest.raises(RuntimeError, match="Only one PAPER"):
        asyncio.run(client.post(PAPER_BASE_URL + "/v2/orders", json={**payload, "qty": "2"}))


def test_sdk_read_failure_is_sanitized_httpx_error(monkeypatch):
    client = adapter(monkeypatch)
    client.trade.get_account = lambda: (_ for _ in ()).throw(RuntimeError("sensitive detail"))
    with pytest.raises(httpx.RequestError, match="SDK read failed") as caught:
        asyncio.run(client.get(PAPER_BASE_URL + "/v2/account"))
    assert "sensitive detail" not in str(caught.value)


def test_real_sdk_429_is_not_retried(monkeypatch):
    attempts = []

    def rate_limited(self, request, **kwargs):
        attempts.append(request.url)
        response = requests.Response()
        response.status_code = 429
        response._content = b'{"code":42910000,"message":"rate limited"}'
        response.request = request
        return response

    monkeypatch.setattr(requests.Session, "send", rate_limited)
    client = sdk.OfficialAlpacaAdapter(configured())
    response = asyncio.run(client.get(PAPER_BASE_URL + "/v2/account"))
    assert response.status_code == 429 and len(attempts) == 1
