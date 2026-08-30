from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class AgentVote:
    role: Literal["market", "options", "risk", "skeptic"]
    stance: Literal["support", "oppose", "abstain"]
    confidence: float
    rationale: str


def consensus(votes: list[AgentVote]) -> bool:
    """Return research consensus; execution authority is intentionally absent."""
    support = sum(v.confidence for v in votes if v.stance == "support")
    oppose = sum(v.confidence for v in votes if v.stance == "oppose")
    has_skeptic = any(v.role == "skeptic" for v in votes)
    return has_skeptic and support > oppose

