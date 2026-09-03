"""Official alpaca-py adapter; application-owned risk/intent protocol stays outside.

The HTTP-shaped compatibility boundary keeps existing parsers/tests. Production GETs
use official SDK methods; the only permitted mutation is one guarded PAPER limit buy.
No SDK retry, HTTP retry, redirect, automatic close, or cancellation is permitted.
"""
import asyncio
from urllib.parse import urlsplit

import httpx
import requests
from alpaca.common.exceptions import APIError
from alpaca.data.historical import OptionHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import OptionSnapshotRequest, StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOptionContractsRequest, GetOrdersRequest, LimitOrderRequest

from backend.app.config import DATA_BASE_URL, PAPER_BASE_URL


class GuardedSession(requests.Session):
    def __init__(self, base, settings):
        super().__init__()
        self.base,self.settings=base,settings
        self.trust_env=False
        self.remaining_requests=0

    def request(self, method, url, **kwargs):
        parsed=urlsplit(url)
        if f"{parsed.scheme}://{parsed.netloc}"!=self.base or parsed.username or parsed.password:
            raise RuntimeError("SDK endpoint denied")
        if self.remaining_requests<=0:
            raise RuntimeError("SDK bounded request budget exhausted")
        self.remaining_requests-=1
        if method.upper()!="GET":
            s=self.settings
            if (method.upper()!="POST" or url!=PAPER_BASE_URL+"/v2/orders"
                or s.trading_mode!="paper" or not s.alpaca_paper_trade or s.allow_live_trading
                or s.live_trading_allowed or not s.execution_enabled or not s.autonomous_trading_enabled
                or not s.phase2_execution_token):
                raise RuntimeError("SDK mutation denied")
        kwargs.update(timeout=10,allow_redirects=False)
        response=super().request(method,url,**kwargs)
        if 300<=response.status_code<400: raise RuntimeError("SDK redirect denied")
        return response


class OfficialAlpacaAdapter:
    def __init__(self, settings):
        if (str(settings.alpaca_paper_base_url).rstrip("/")!=PAPER_BASE_URL
            or str(settings.alpaca_data_base_url).rstrip("/")!=DATA_BASE_URL
            or settings.trading_mode!="paper" or not settings.alpaca_paper_trade
            or settings.allow_live_trading or settings.live_trading_allowed):
            raise RuntimeError("SDK paper configuration required")
        key=settings.alpaca_paper_api_key.get_secret_value()
        secret=settings.alpaca_paper_api_secret.get_secret_value()
        self.settings=settings
        self.trade=TradingClient(key,secret,paper=True,raw_data=True,url_override=PAPER_BASE_URL)
        self.stock=StockHistoricalDataClient(key,secret,raw_data=True,url_override=DATA_BASE_URL)
        self.options=OptionHistoricalDataClient(key,secret,raw_data=True,url_override=DATA_BASE_URL)
        for client,base in ((self.trade,PAPER_BASE_URL),(self.stock,DATA_BASE_URL),(self.options,DATA_BASE_URL)):
            client._session.close()
            client._session=GuardedSession(base,settings)
            # Pinned SDK source ignores retry_attempts=0 in its constructor.
            # Explicitly disable the private retry counter; regression-tested on upgrades.
            client._retry=0
        self.lock=asyncio.Lock()

    def _read(self,url,params):
        p=dict(params or {}); path=urlsplit(url).path
        if url.startswith(PAPER_BASE_URL+"/"):
            if path=="/v2/account": return self.trade.get_account()
            if path=="/v2/clock": return self.trade.get_clock()
            if path=="/v2/positions": return self.trade.get_all_positions()
            if path=="/v2/orders": return self.trade.get_orders(GetOrdersRequest(**p))
            if path=="/v2/orders:by_client_order_id": return self.trade.get_order_by_client_id(p["client_order_id"])
            if path.startswith("/v2/orders/"): return self.trade.get_order_by_id(path.rsplit("/",1)[1])
            if path.startswith("/v2/assets/"): return self.trade.get_asset(path.rsplit("/",1)[1])
            if path=="/v2/options/contracts":
                if isinstance(p.get("underlying_symbols"),str): p["underlying_symbols"]=p["underlying_symbols"].split(",")
                return self.trade.get_option_contracts(GetOptionContractsRequest(**p))
            if path.startswith("/v2/options/contracts/"): return self.trade.get_option_contract(path.rsplit("/",1)[1])
        elif url.startswith(DATA_BASE_URL+"/"):
            if path=="/v1beta1/options/snapshots":
                return {"snapshots":self.options.get_option_snapshot(OptionSnapshotRequest(
                    symbol_or_symbols=p["symbols"].split(","),feed=p["feed"]))}
            if path.startswith("/v2/stocks/"):
                symbol=path.split("/")[3]
                if path.endswith("/quotes/latest"):
                    return {"quote":self.stock.get_stock_latest_quote(StockLatestQuoteRequest(
                        symbol_or_symbols=symbol,feed=p.get("feed","iex")))[symbol]}
                if path.endswith("/bars"):
                    p["timeframe"]={"1Min":TimeFrame.Minute,"1Day":TimeFrame.Day}[p["timeframe"]]
                    result=self.stock.get_stock_bars(StockBarsRequest(symbol_or_symbols=symbol,**p))
                    return {"bars":result.get(symbol,[])}
        raise RuntimeError("Unapproved SDK read endpoint")

    async def get(self,url,params=None,headers=None):
        request=httpx.Request("GET",url)
        async with self.lock:
            for c in (self.trade,self.stock,self.options): c._session.remaining_requests=4
            try:
                result=await asyncio.to_thread(self._read,url,params)
                return httpx.Response(200,json=result,request=request)
            except APIError as exc:
                return httpx.Response(exc.status_code or 502,json={"error":"Alpaca SDK request failed"},request=request)
            except (requests.RequestException, RuntimeError, ValueError, TypeError, KeyError):
                raise httpx.RequestError("Alpaca SDK read failed",request=request) from None

    async def post(self,url,json=None,headers=None,**kwargs):
        # No await/thread boundary: a canceled task cannot leave a queued send running.
        # Timeout <=10s is inside the durable gate minimum remaining lifetime (15s).
        request=httpx.Request("POST",url)
        if (url!=PAPER_BASE_URL+"/v2/orders" or not json or json.get("side")!="buy"
            or json.get("position_intent")!="buy_to_open" or json.get("type")!="limit"
            or json.get("time_in_force")!="day" or str(json.get("qty"))!="1"):
            raise RuntimeError("Only one PAPER long option entry is permitted")
        self.trade._session.remaining_requests=1
        try:
            result=self.trade.submit_order(LimitOrderRequest(**json))
            return httpx.Response(200,json=result,request=request)
        except (APIError, requests.RequestException, RuntimeError, ValueError, TypeError, KeyError):
            # Any failure is uncertain: caller must reconcile by client ID, never resubmit.
            raise httpx.RequestError("Alpaca SDK submission uncertain",request=request) from None

    async def aclose(self):
        for client in (self.trade,self.stock,self.options): client._session.close()
