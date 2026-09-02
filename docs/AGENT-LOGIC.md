# Strategy logic — Phase 2

All strategy agents are deterministic Python policies, not LLM calls. Model outages cannot
change the trading decision. Strict Pydantic schemas reject free-form/malformed proposals.
No LLM can override the independent RiskOfficer.

- Trend: long call in TREND_UP, long put in TREND_DOWN.
- Range: long call below RSI 35, put above RSI 65, only in RANGE/LOW_VOLATILITY.
- Defensive: long put in falling TREND_DOWN/HIGH_VOLATILITY.
- Critic: challenges directional edge, volatility, spread, timing, theta and concentration.
- MetaAllocator: rejects contradictory proposed directions; applies exposure/critic/budget
  screens and a composite score. Equal scores use stable strategy-name ordering, not UUIDs.
- Reflection: reports observed counterfactual outcomes without inventing causal explanations.

EMA8/21, RSI14, ATR14, return20m, VWAP and realized volatility are calculated from actual
minute bars. See PHASE-2-ARCHITECTURE.md for thresholds. Confidence is heuristic, not a
calibrated probability. NO_TRADE is a normal output, not a service failure.

Validation: `python -m scripts.phase2_replay` runs 96 fixed simulated cases (12 variations
of 8 price/data conditions), plus the preserved historical production snapshot. No parameter
search or tuning occurred. Synthetic outcomes are never uploaded as actual account results.
This is behavioral stress testing, not evidence of investment performance. A reversal path
can resolve to a downtrend; contradictory agent directions are independently tested to abstain.
