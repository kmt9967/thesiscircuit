from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from backend.app.config import Settings
from backend.app.models import OptionContract, QuoteSnapshot, TradeProposal


def build_deterministic_proposal(
    settings: Settings,
    underlying_price: float,
    contracts: list[OptionContract],
    quotes: dict[str, QuoteSnapshot],
) -> TradeProposal:
    candidates: list[tuple[OptionContract, QuoteSnapshot]] = []
    for contract in contracts:
        quote = quotes.get(contract.symbol)
        if not quote or not contract.tradable or quote.ask_price <= 0:
            continue
        max_loss = quote.ask_price * 100
        if contract.strike_price >= underlying_price and max_loss <= settings.phase1_max_risk_usd:
            candidates.append((contract, quote))
    if not candidates:
        raise ValueError("No tradable premium-bounded SPY call candidate is available")
    contract, quote = min(
        candidates,
        key=lambda item: (abs(item[0].strike_price - underlying_price), item[1].ask_price),
    )
    trace_id = uuid5(NAMESPACE_URL, "thesiscircuit:phase1:official-opening")
    proposal_id = uuid5(NAMESPACE_URL, f"{trace_id}:proposal")
    client_order_id = f"thesiscircuit-phase1-{trace_id}"
    limit_price = round(quote.ask_price, 2)
    max_loss = round(limit_price * 100, 2)
    return TradeProposal(
        id=proposal_id,
        trace_id=trace_id,
        created_at=datetime.now(timezone.utc),
        symbol=settings.phase1_symbol,
        instrument=contract.symbol,
        reference_price=quote.midpoint,
        limit_price=limit_price,
        rationale=(
            "Deterministic infrastructure proof: buy one near-the-money SPY call with a "
            "premium-bounded maximum loss; no profit optimization or LLM discretion."
        ),
        invalidation="Reject if any safety, freshness, account, liquidity, or official-window gate fails.",
        confidence=1.0,
        data_timestamp=quote.timestamp,
        source=quote.source,
        estimated_max_loss=max_loss,
        underlying=settings.phase1_symbol,
        expiry=contract.expiration_date,
        strike=contract.strike_price,
        legs=[{"symbol": contract.symbol, "side": "buy", "position_intent": "buy_to_open"}],
        debit=limit_price,
        max_theoretical_loss=max_loss,
        breakeven=round(contract.strike_price + limit_price, 2),
        liquidity_metrics={
            "bid": quote.bid_price,
            "ask": quote.ask_price,
            "spread": round(quote.ask_price - quote.bid_price, 2),
        },
        client_order_id=client_order_id,
    )
