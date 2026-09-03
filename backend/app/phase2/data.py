"""Read-only feature provider. Each refresh binds quotes/features to ONE underlying."""
import asyncio
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from backend.app.config import Settings
from backend.app.phase2.features import features
from backend.app.phase2.models import Bar, MarketState, Option, OrderRead, Position
from backend.app.services.alpaca import AccountService, AlpacaError, MarketDataService


def parse_option(contract: dict, snapshot: dict) -> Option:
    q = snapshot.get("latestQuote") or {}
    greeks = snapshot.get("greeks") or {}
    # latestTrade.s is trade SIZE, never daily volume. Missing volume stays unavailable.
    return Option(
        symbol=contract["symbol"], underlying=contract["underlying_symbol"],
        expiry=contract["expiration_date"], strike=contract["strike_price"], kind=contract["type"],
        tradable=contract["tradable"] and contract["status"] == "active",
        multiplier=int(contract["size"]), quote_at=q["t"], source=snapshot["source"],
        bid=q["bp"], ask=q["ap"], bid_size=q.get("bs"), ask_size=q.get("as"),
        open_interest=contract.get("open_interest"),
        open_interest_date=contract.get("open_interest_date"),
        implied_volatility=snapshot.get("impliedVolatility"),
        **{name: greeks.get(name) for name in ("delta", "gamma", "theta", "vega")},
    )


class ReadOnlyMarketProvider:
    def __init__(self, settings: Settings, underlying: str = "SPY"):
        if underlying not in {"SPY", "QQQ"}:
            raise ValueError("Unsupported research underlying")
        self.settings = settings
        self.underlying = underlying

    async def refresh(self, shadow_symbols: list[str] | None = None,
                      observations_only: bool = False) -> MarketState:
        now = datetime.now(timezone.utc)
        async with AccountService(self.settings) as account:
            a, clock, raw_positions, raw_orders = await asyncio.gather(
                account.account(), account.clock(), account.positions(), account.all_orders())
        if len(raw_orders) >= 500:
            raise AlpacaError("Order history is truncated; cannot prove complete risk state")
        positions = [Position(symbol=p["symbol"], qty=p["qty"], side=p["side"],
                              entry=p["avg_entry_price"], current_price=p["current_price"],
                              market_value=p["market_value"], cost_basis=p["cost_basis"],
                              unrealized_pl=p["unrealized_pl"], unrealized_plpc=p["unrealized_plpc"],
                              asset_class=p["asset_class"]) for p in raw_positions]
        orders = [OrderRead(symbol=o["symbol"], client_order_id=o["client_order_id"],
                            status=o["status"], submitted_at=o["submitted_at"]) for o in raw_orders]
        state = MarketState(underlying=self.underlying,timestamp=now, account=a, clock=clock, positions=positions, orders=orders)
        async with MarketDataService(self.settings) as data:
            # Independent observations survive a closed market or failed feature refresh.
            # They are NOT inserted into the fresh entry-candidate universe.
            for symbol in sorted({p.symbol for p in positions} | set(shadow_symbols or [])):
                try:
                    contract = await data._get(data.paper_base, f"/v2/options/contracts/{symbol}")
                    raw_snapshot = await data._get(data.data_base, "/v1beta1/options/snapshots", {
                        "symbols": symbol, "feed": self.settings.alpaca_market_data_feed,
                    })
                    observation = parse_option(contract, {**raw_snapshot["snapshots"][symbol],
                        "source": f"alpaca:{self.settings.alpaca_market_data_feed}"})
                    if not 0 <= (datetime.now(timezone.utc) - observation.quote_at).total_seconds() <= 259200:
                        raise ValueError("Observation future-dated or older than 72 hours")
                    state.observations.append(observation)
                except (AlpacaError, ValueError, KeyError, TypeError):
                    state.data_errors.append(f"Observation unavailable: {symbol}")
            if observations_only:
                return state
            try:
                asset = await data.asset(self.underlying)
                if not asset.tradable or not asset.options_enabled or asset.status != "active":
                    raise ValueError("Underlying must be active, tradable and options-enabled")
                quote = await data.stock_quote(self.underlying)
                local_date = now.astimezone(ZoneInfo("America/New_York")).date()
                session_start = datetime.combine(local_date, time(9, 30), ZoneInfo("America/New_York"))
                raw = await data._get(data.data_base, f"/v2/stocks/{self.underlying}/bars", {
                    "timeframe": "1Min", "start": session_start.isoformat(),
                    "end": now.isoformat(), "limit": 1000, "feed": "iex", "sort": "asc",
                })
                if raw.get("next_page_token"):
                    raise ValueError("Minute bar response truncated")
                bars = [Bar(**{k: b[k] for k in ("t", "o", "h", "l", "c", "v", "vw") if k in b})
                        for b in raw["bars"]]
                previous = await data._get(data.data_base, f"/v2/stocks/{self.underlying}/bars", {
                    "timeframe": "1Day", "start": (now - timedelta(days=7)).date().isoformat(),
                    "end": session_start.isoformat(), "limit": 1, "sort": "desc", "feed": "iex",
                })
                previous_close = previous["bars"][0]["c"] if previous.get("bars") else None
                state.features = features(bars, quote.midpoint, quote.timestamp,
                                          datetime.now(timezone.utc), previous_close)
                contracts = await data._get(data.paper_base, "/v2/options/contracts", {
                    "underlying_symbols": self.underlying, "status": "active",
                    "expiration_date_gte": (local_date + timedelta(days=1)).isoformat(),
                    "expiration_date_lte": (local_date + timedelta(days=7)).isoformat(),
                    "strike_price_gte": str(round(quote.midpoint * 0.985, 2)),
                    "strike_price_lte": str(round(quote.midpoint * 1.015, 2)), "limit": 1000,
                })
                if contracts.get("next_page_token"):
                    raise ValueError("Option contract universe truncated; reduce universe explicitly")
                universe = {c["symbol"]: c for c in contracts["option_contracts"]}
                # Balanced deterministic coverage by side, expiry, then moneyness.
                ranked = sorted(universe.values(), key=lambda c: (
                    c["expiration_date"], abs(float(c["strike_price"]) - quote.midpoint), c["symbol"]))[:80]
                selected = {c["symbol"]: c for c in ranked}
                for symbol in {p.symbol for p in positions} | set(shadow_symbols or []):
                    if not symbol.startswith(self.underlying) or symbol[len(self.underlying):len(self.underlying)+1].isalpha():
                        continue  # Other-underlying observations never become entry candidates.
                    if symbol not in selected:
                        selected[symbol] = universe.get(symbol) or await data._get(
                            data.paper_base, f"/v2/options/contracts/{symbol}")
                symbols = list(selected)
                snapshots = {}
                for offset in range(0, len(symbols), 100):
                    response = await data._get(data.data_base, "/v1beta1/options/snapshots", {
                        "symbols": ",".join(symbols[offset:offset + 100]), "limit": 100,
                        "feed": self.settings.alpaca_market_data_feed,
                    })
                    if response.get("next_page_token"):
                        raise ValueError("Option snapshot response truncated")
                    snapshots.update(response["snapshots"])
                rejected = 0
                for symbol, contract in selected.items():
                    try:
                        snapshot = {**snapshots[symbol], "source": f"alpaca:{self.settings.alpaca_market_data_feed}"}
                        option = parse_option(contract, snapshot)
                        if not 0 <= (datetime.now(timezone.utc) - option.quote_at).total_seconds() <= 120:
                            raise ValueError("Stale option")
                        state.options.append(option)
                    except (ValueError, KeyError, TypeError):
                        rejected += 1
                if rejected:
                    state.data_errors.append(f"Excluded {rejected} stale/malformed/missing option snapshots")
            except (AlpacaError, ValueError, KeyError, TypeError):
                state.features = None
                state.options = []
                state.data_errors.append("Market data incomplete or stale; no proposal authorized")
        return state

    async def refresh_for(self, underlying: str, shadow_symbols: list[str] | None = None,
                          observations_only: bool = False) -> MarketState:
        """Refresh one explicitly named underlying; never reuse another symbol's features."""
        if underlying != self.underlying:
            raise ValueError("Provider is bound to a different underlying")
        return await self.refresh(shadow_symbols, observations_only)


class MultiUnderlyingMarketProvider:
    """Small explicit universe; every state retains its own quote/feature provenance."""

    def __init__(self, settings: Settings, underlyings: tuple[str, ...] = ("SPY", "QQQ")):
        if not underlyings or len(set(underlyings)) != len(underlyings):
            raise ValueError("A unique underlying universe is required")
        self.underlyings = list(underlyings)
        self.providers = {symbol: ReadOnlyMarketProvider(settings, symbol) for symbol in underlyings}

    async def refresh_for(self, underlying: str, shadow_symbols: list[str] | None = None,
                          observations_only: bool = False) -> MarketState:
        try:
            provider = self.providers[underlying]
        except KeyError:
            raise ValueError("Underlying is outside the configured universe") from None
        return await provider.refresh(shadow_symbols, observations_only)

    async def refresh_all(self, underlyings: list[str], shadow_symbols: list[str] | None = None) -> list[MarketState]:
        if not underlyings or any(symbol not in self.providers for symbol in underlyings):
            raise ValueError("Session underlying scope is not configured")
        states = await asyncio.gather(*(self.refresh_for(symbol, shadow_symbols) for symbol in underlyings))
        if [state.underlying for state in states] != underlyings:
            raise RuntimeError("Cross-underlying market-state contamination")
        return states
