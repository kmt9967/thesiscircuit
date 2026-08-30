from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from typing_extensions import Self

from backend.app.config import Settings
from backend.app.models import (
    AccountSnapshot,
    AssetSnapshot,
    MarketClock,
    OptionContract,
    PaperOrderRecord,
    QuoteSnapshot,
    TradeProposal,
)


class AlpacaError(RuntimeError):
    """A fail-closed Alpaca integration error."""


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class AlpacaClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        if not settings.alpaca_paper_api_key or not settings.alpaca_paper_api_secret:
            raise AlpacaError("Alpaca PAPER credentials are not configured")
        self.settings = settings
        self.client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None
        self.headers = {
            "APCA-API-KEY-ID": settings.alpaca_paper_api_key.get_secret_value(),
            "APCA-API-SECRET-KEY": settings.alpaca_paper_api_secret.get_secret_value(),
        }
        self.paper_base = str(settings.alpaca_paper_base_url).rstrip("/")
        self.data_base = str(settings.alpaca_data_base_url).rstrip("/")

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def _get(self, base: str, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            response = await self.client.get(
                f"{base}{path}", params=params, headers=self.headers
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AlpacaError(f"Read-only Alpaca request failed: {path}") from exc


class AccountService(AlpacaClient):
    async def account(self) -> AccountSnapshot:
        data = await self._get(self.paper_base, "/v2/account")
        number = str(data.get("account_number", ""))
        return AccountSnapshot(
            status=str(data.get("status", "UNKNOWN")),
            cash=_as_float(data.get("cash")),
            buying_power=_as_float(data.get("buying_power")),
            portfolio_value=_as_float(data.get("portfolio_value")),
            equity=_as_float(data.get("equity")),
            last_equity=_as_float(data.get("last_equity")),
            options_buying_power=_as_float(data.get("options_buying_power"))
            if data.get("options_buying_power") is not None
            else None,
            account_number_suffix=number[-4:] if number else "unknown",
        )

    async def clock(self) -> MarketClock:
        return MarketClock.model_validate(await self._get(self.paper_base, "/v2/clock"))

    async def positions(self) -> list[dict[str, Any]]:
        data = await self._get(self.paper_base, "/v2/positions")
        return data if isinstance(data, list) else []

    async def open_orders(self) -> list[dict[str, Any]]:
        data = await self._get(
            self.paper_base, "/v2/orders", {"status": "open", "limit": 500, "nested": "true"}
        )
        return data if isinstance(data, list) else []

    async def all_orders(self) -> list[dict[str, Any]]:
        data = await self._get(
            self.paper_base,
            "/v2/orders",
            {"status": "all", "limit": 500, "nested": "true", "direction": "asc"},
        )
        return data if isinstance(data, list) else []


class MarketDataService(AlpacaClient):
    async def asset(self, symbol: str) -> AssetSnapshot:
        data = await self._get(self.paper_base, f"/v2/assets/{symbol}")
        return AssetSnapshot(
            symbol=str(data.get("symbol", symbol)),
            asset_class=str(data.get("class", "us_equity")),
            status=str(data.get("status", "unknown")),
            tradable=bool(data.get("tradable")),
            options_enabled="options_enabled" in (data.get("attributes") or []),
        )

    async def stock_quote(self, symbol: str) -> QuoteSnapshot:
        data = await self._get(
            self.data_base,
            f"/v2/stocks/{symbol}/quotes/latest",
            {"feed": "iex"},
        )
        quote = data.get("quote") or {}
        return QuoteSnapshot(
            symbol=symbol,
            bid_price=_as_float(quote.get("bp")),
            ask_price=_as_float(quote.get("ap")),
            timestamp=quote.get("t") or datetime.now(timezone.utc),
            source="alpaca:iex",
        )

    async def bars(self, symbol: str) -> list[dict[str, Any]]:
        start = datetime.now(timezone.utc) - timedelta(days=45)
        data = await self._get(
            self.data_base,
            f"/v2/stocks/{symbol}/bars",
            {
                "timeframe": "1Day",
                "start": start.isoformat().replace("+00:00", "Z"),
                "limit": 20,
                "feed": "iex",
            },
        )
        bars = data.get("bars") or []
        return bars if isinstance(bars, list) else []

    async def option_contracts(self, underlying: str, expiration: str) -> list[OptionContract]:
        data = await self._get(
            self.paper_base,
            "/v2/options/contracts",
            {
                "underlying_symbols": underlying,
                "status": "active",
                "type": "call",
                "expiration_date": expiration,
                "limit": 1000,
            },
        )
        contracts = []
        for item in data.get("option_contracts") or []:
            contracts.append(
                OptionContract(
                    symbol=item["symbol"],
                    underlying_symbol=item["underlying_symbol"],
                    expiration_date=str(item["expiration_date"]),
                    strike_price=_as_float(item["strike_price"]),
                    option_type=item["type"],
                    status=item["status"],
                    tradable=bool(item["tradable"]),
                )
            )
        return contracts

    async def option_quotes(self, symbols: list[str]) -> dict[str, QuoteSnapshot]:
        if not symbols:
            return {}
        result: dict[str, QuoteSnapshot] = {}
        for start in range(0, len(symbols), 100):
            chunk = symbols[start : start + 100]
            data = await self._get(
                self.data_base,
                "/v1beta1/options/snapshots",
                {
                    "symbols": ",".join(chunk),
                    "feed": self.settings.alpaca_market_data_feed,
                    "limit": 100,
                },
            )
            for symbol, snapshot in (data.get("snapshots") or {}).items():
                quote = snapshot.get("latestQuote") or snapshot.get("latest_quote") or {}
                result[symbol] = QuoteSnapshot(
                    symbol=symbol,
                    bid_price=_as_float(quote.get("bp") or quote.get("bid_price")),
                    ask_price=_as_float(quote.get("ap") or quote.get("ask_price")),
                    timestamp=quote.get("t")
                    or quote.get("timestamp")
                    or datetime.now(timezone.utc),
                    source=f"alpaca:{self.settings.alpaca_market_data_feed}",
                )
        return result


class OrderService(AlpacaClient):
    async def by_client_order_id(self, client_order_id: str) -> dict[str, Any] | None:
        try:
            return await self._get(
                self.paper_base,
                "/v2/orders:by_client_order_id",
                {"client_order_id": client_order_id},
            )
        except AlpacaError:
            return None

    async def by_id(self, order_id: str) -> dict[str, Any]:
        return await self._get(self.paper_base, f"/v2/orders/{order_id}", {"nested": "true"})

    async def submit_once(
        self, proposal: TradeProposal, risk_check_id: str, risk_approved: bool
    ) -> PaperOrderRecord:
        if not risk_approved:
            raise AlpacaError("A deterministic APPROVED risk decision is required")
        existing = await self.by_client_order_id(proposal.client_order_id)
        if existing:
            return self._record(existing, proposal, risk_check_id)
        payload = {
            "symbol": proposal.instrument,
            "qty": str(proposal.quantity),
            "side": "buy",
            "type": "limit",
            "time_in_force": "day",
            "limit_price": f"{proposal.limit_price:.2f}",
            "client_order_id": proposal.client_order_id,
            "position_intent": "buy_to_open",
        }
        try:
            response = await self.client.post(
                f"{self.paper_base}/v2/orders", json=payload, headers=self.headers
            )
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exc:
            existing = await self.by_client_order_id(proposal.client_order_id)
            if not existing:
                raise AlpacaError("Order submission timed out; no matching Alpaca order found") from exc
            data = existing
        except (httpx.HTTPError, ValueError) as exc:
            raise AlpacaError("Alpaca PAPER order submission failed") from exc
        return self._record(data, proposal, risk_check_id)

    @staticmethod
    def _record(data: dict[str, Any], proposal: TradeProposal, risk_check_id: str) -> PaperOrderRecord:
        return PaperOrderRecord(
            proposal_id=proposal.id,
            risk_check_id=risk_check_id,
            trace_id=proposal.trace_id,
            alpaca_order_id=str(data["id"]),
            client_order_id=proposal.client_order_id,
            submitted_at=data.get("submitted_at") or datetime.now(timezone.utc),
            status=str(data.get("status", "unknown")),
            instrument=proposal.instrument,
            quantity=_as_float(data.get("qty"), proposal.quantity),
            filled_quantity=_as_float(data.get("filled_qty")),
            filled_average_price=_as_float(data.get("filled_avg_price"))
            if data.get("filled_avg_price") is not None
            else None,
            filled_at=data.get("filled_at"),
        )
