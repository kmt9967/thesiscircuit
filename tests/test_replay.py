from replay.engine import ReplayEvent, replay


def test_replay_orders_events_and_stays_paper_only() -> None:
    result = replay(
        [
            ReplayEvent(2, "risk-decision", {"approved": False}),
            ReplayEvent(1, "agent-vote", {"role": "skeptic"}),
        ]
    )
    assert result == {
        "event_count": 2,
        "sequence": [1, 2],
        "final_kind": "risk-decision",
        "paper_only": True,
    }

