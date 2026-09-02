# Phase 1 Risk Policy

The deterministic engine rejects unless all 18 gates pass: paper mode, paper endpoint,
active dedicated/unblocked options-enabled account, stage-specific execution gate,
fresh quote, tradable option, one-contract size, sufficient cash/options buying power,
unique client ID, zero prior/open orders, zero positions, single-leg DAY limit buy,
consistent premium-derived loss <= $250, official options/window rule, fresh open
market clock, unchanged $100,000 starting cash/equity and drawdown bound, live disabled,
and liquidity (positive uncrossed bid/ask; spread <= $0.10 and <= 10% of midpoint).

Readiness REQUIRES execution disabled and returns READY_FOR_EXECUTION. Execution
REQUIRES enabled and returns APPROVED_FOR_SINGLE_ORDER. Both durable receipts are
required before submission, which rechecks current state again. A candidate change
or increased premium requires disabling execution and restarting readiness. Missing
timestamps, malformed account lists, and failed duplicate lookups never imply safety.

An LLM cannot approve or override a rejected proposal. ThesisCircuit uses a long call for the first proof because its theoretical loss is bounded by premium paid. Naked short options, uncovered calls, unlimited-risk strategies, market orders, batch orders, and autonomous loops are excluded.

The Phase 1 authorization is now consumed: one order filled September 2 at $1.84,
after a $1.88 limit/$188 premium bound passed all gates. The resting execution gate
is false. The existing one-contract position must not be closed, added to, exercised,
or otherwise managed automatically. Premium-only bounds exclude transaction costs
and any stock exposure created by expiry exercise; separate user direction is needed.
