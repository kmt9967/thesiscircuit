# Understandable, conservative scoring

Allocation score (0–1) is:

`0.20*proposal_confidence + 0.20*regime_confidence + 0.20*liquidity_quality
 + 0.15*(agent_score/100) + 0.10*budget_efficiency + 0.15*(1-critic_severity)`.

Liquidity quality = max(0, 1-spread_fraction/0.10); budget efficiency =
max(0, 1-premium/500). Composite minimum 0.50. Severe critic objections (>=0.80),
conflicting directions and portfolio concentration veto allocation regardless of score.
The independent deterministic risk engine runs afterward and cannot be overridden.

Agent score starts at 50. For n distinct completed shadow horizons:

`score = 50 + n/(n+20) * [10*mean(clip(P&L/premium,-1,1)) + 5*(2*positive_rate-1)]`.

Counterfactual influence is bounded to +/-15 points before shrinkage. One lucky sample cannot
move the score by more than 15/21 points. Score influence on allocation is only 15%.
First completed observation per shadow wins; repeated marks do not add samples.

Reported factors: risk efficiency, false-positive rate, missed opportunities, and NO_TRADE
quality (fraction of rejected shadow trades with a negative subsequent outcome). That last
metric covers only observable rejected proposals, NOT all abstentions; it has selection bias.
Zero-return outcomes are not false positives. Executed realized/unrealized returns, hit rate,
drawdown and thesis accuracy stay null until attributable executions and sufficient observations
exist. The Phase 1 infrastructure trade has no Phase 2 strategy attribution and is not credited.
Drawdown is not calculable from isolated quotes; no synthetic zero is substituted.
