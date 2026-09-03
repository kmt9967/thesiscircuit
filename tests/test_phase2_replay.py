from scripts.phase2_replay import replay


def test_replay_is_reproducible_and_safety_abstains():
    a,b=replay(),replay()
    assert a == b and len(a["scenarios"]) == 8
    for scenario in a["scenarios"]:
        if scenario["scenario"] in {"bad_liquidity","stale_data"}:
            assert scenario["no_trade_frequency"] == 1
        assert scenario["max_simulated_drawdown"] is None
    assert a["historical"]["decision"] == "NO_TRADE"
