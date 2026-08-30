from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class OptionsThesis:
    symbol: str
    structure: Literal["defined-risk-call-spread", "defined-risk-put-spread"]
    max_loss_usd: float
    days_to_expiry: int
    reasoning: tuple[str, ...]


def propose_defined_risk_spread(
    symbol: str,
    direction: Literal["bullish", "bearish"],
    max_loss_usd: float,
    days_to_expiry: int,
) -> OptionsThesis:
    structure = "defined-risk-call-spread" if direction == "bullish" else "defined-risk-put-spread"
    return OptionsThesis(
        symbol=symbol,
        structure=structure,
        max_loss_usd=max_loss_usd,
        days_to_expiry=days_to_expiry,
        reasoning=("bounded-risk structure", "paper-only evaluation", "requires risk veto review"),
    )

