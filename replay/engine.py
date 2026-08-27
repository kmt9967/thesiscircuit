from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReplayEvent:
    sequence: int
    kind: str
    payload: dict[str, Any]


def replay(events: list[ReplayEvent]) -> dict[str, Any]:
    ordered = sorted(events, key=lambda event: event.sequence)
    return {
        "event_count": len(ordered),
        "sequence": [event.sequence for event in ordered],
        "final_kind": ordered[-1].kind if ordered else None,
        "paper_only": True,
    }

