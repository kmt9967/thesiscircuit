"""Transparent 1-minute, same-session features; no learned numeric inputs."""
from datetime import datetime
from itertools import pairwise
from math import log, sqrt
from statistics import mean, pstdev

from backend.app.phase2.models import Bar, Features, Regime


def ema(values: list[float], period: int) -> float:
    value = values[0]
    for sample in values[1:]:
        value += 2 / (period + 1) * (sample - value)
    return value


def features(bars: list[Bar], price: float, quote_at: datetime, now: datetime,
             previous_close: float | None = None) -> Features:
    if len(bars) < 21 or not 0 <= (now - quote_at).total_seconds() <= 120:
        raise ValueError("Insufficient bars or stale underlying quote")
    if any(a.t >= b.t for a, b in pairwise(bars)):
        raise ValueError("Bars must be strictly ordered without duplicate timestamps")
    if not 0 <= (now - bars[-1].t).total_seconds() <= 180:
        raise ValueError("Latest minute bar is stale")
    closes = [b.c for b in bars]
    changes = [b - a for a, b in pairwise(closes)][-14:]
    gain, loss = mean(max(0, x) for x in changes), mean(max(0, -x) for x in changes)
    rsi = 50 if gain == loss == 0 else (100 if loss == 0 else 100 - 100 / (1 + gain / loss))
    ranges = [max(b.h - b.l, abs(b.h - a.c), abs(b.l - a.c))
              for a, b in pairwise(bars)][-14:]
    atr = mean(ranges)
    fast, slow = ema(closes, 8), ema(closes, 21)
    volume = sum(b.v for b in bars)
    prior_volume = mean(b.v for b in bars[-21:-1])
    return Features(
        timestamp=quote_at, bar_timestamp=bars[-1].t, source="alpaca:iex:1Min",
        price=price, return_1m=closes[-1] / closes[-2] - 1,
        return_20m=closes[-1] / closes[-21] - 1, ema_fast=fast, ema_slow=slow,
        rsi=rsi, atr=atr, vwap=sum(b.v * b.vw for b in bars) / volume
        if volume and all(b.vw is not None for b in bars) else None,
        volume=bars[-1].v, relative_volume=bars[-1].v / prior_volume if prior_volume else None,
        realized_volatility=pstdev([log(b / a) for a, b in zip(closes[-21:], closes[-20:])])
        * sqrt(390 * 252), trend_strength=(fast - slow) / atr if atr else 0,
        intraday_range=max(b.h for b in bars) - min(b.l for b in bars),
        gap=bars[0].o / previous_close - 1 if previous_close else None,
        support=min(b.l for b in bars[-20:]), resistance=max(b.h for b in bars[-20:]),
        samples=len(bars),
    )


def classify(f: Features | None, now: datetime) -> Regime:
    metrics = {} if f is None else {
        key: getattr(f, key) for key in
        ("trend_strength", "rsi", "realized_volatility", "ema_fast", "ema_slow", "return_20m")
    }
    name, confidence = "UNCERTAIN", 0.0
    if f and 0 <= (now - f.timestamp).total_seconds() <= 120:
        if f.realized_volatility >= 0.40:
            name, confidence = "HIGH_VOLATILITY", 0.8
        elif f.trend_strength >= 0.45 and f.return_20m > 0:
            name, confidence = "TREND_UP", min(0.9, 0.55 + abs(f.trend_strength) * 0.15)
        elif f.trend_strength <= -0.45 and f.return_20m < 0:
            name, confidence = "TREND_DOWN", min(0.9, 0.55 + abs(f.trend_strength) * 0.15)
        elif f.realized_volatility < 0.08:
            name, confidence = "LOW_VOLATILITY", 0.6
        elif abs(f.trend_strength) < 0.45:
            name, confidence = "RANGE", 0.65
    return Regime(name=name, confidence=confidence, timestamp=now, metrics=metrics,
                  invalidation="Recompute each cycle; stale input or threshold reversal invalidates regime")
