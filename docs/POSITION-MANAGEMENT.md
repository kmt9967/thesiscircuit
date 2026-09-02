# Advisory position management

Existing position: SPY260904C00768000, one long call, actual entry $1.84, expiry September 4,
2026. Acquisition premium $184; broker account cash differs by $0.03 beyond that premium,
whose fee attribution has not been independently verified. Never reset or overwrite this trade.

The read-only portfolio endpoint retrieves account, positions, orders, market clock and an
independent timestamped option snapshot. Broker current_price/P&L are explicitly broker marks,
whose underlying quote timestamp is not supplied. Last-available bid/ask and Greeks are labelled
with the snapshot time; stale values are never described as current execution data.

Recommendations: RISK_ALERT for closed/stale/missing data, proximity within 24h, or risk breach;
EXIT advisory for >=50% premium loss when data is fresh; regime contradiction produces REDUCE
advisory; expired instruments require manual broker reconciliation; otherwise HOLD. Unknown
regime means thesis compatibility unassessed, not proven valid. No action is performed.

Theta/day is model theta *100*contracts, not a promised loss. Hours to expiry assume standard
16:00 America/New_York expiry and are computed at the recorded observation time. Automatic
exercise/assignment can change exposure; no expiry automation is implemented.

ExitProposal is typed, sell-to-close only, DAY limit, quantity capped and checked against a
single owned long position. Its pure preflight shares paper/auth/window/market/freshness/
liquidity/order/cooldown/drawdown checks. Explicit reducing-exposure semantics replace entry
capacity/buying-power/concentration checks; it cannot create a short. It requires at least
one hour before expiry. Neither its schema nor approval grants dispatch authority.

Existing SPY should remain advisory-only until separate closing authority and a reviewed
reduce-only dispatcher exist. No close, modification or cancellation is authorized in Part 2.
