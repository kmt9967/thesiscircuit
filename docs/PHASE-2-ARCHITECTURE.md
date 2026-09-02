# Phase 2 Part 1 — decision research, not trading

Part 1 builds and deploys a deterministic agent pipeline. No opening, closing,
cancellation, exercise, or account-reset action is available to it.

## Pipeline and capabilities

ReadOnlyMarketProvider → minute features → regime → TREND/RANGE/DEFENSIVE proposals
→ critic → multi-factor allocator → 24-gate RiskOfficer → **blocked execution**
→ counterfactual marks, position recommendations, reflection and scores.

The existing asynchronous httpx adapters are retained instead of introducing a
second alpaca-py networking stack. They use documented Alpaca REST endpoints,
bounded timeouts and explicit GET-only broker calls. Phase 2 does not import
OrderService or a trading SDK. All numeric features and proposals are Python /
Pydantic, with no LLM numeric or execution authority. Only long calls/puts are
supported; multi-leg spreads and automatic hedges are deliberately unsupported.

Official references: [option snapshots](https://docs.alpaca.markets/us/reference/optionsnapshots)
and [contract metadata](https://docs.alpaca.markets/us/reference/get-options-contracts).
Indicative quotes are modified and trades delayed; the UI labels the feed and
never presents counterfactual prices as guaranteed fills.

## Features and validity

Same-session IEX 1-minute bars: returns over 1/20 bars, EMA8/21, simple-window
RSI14, ATR14, volume-weighted reported bar VWAP, last-bar relative volume versus
prior20, annualized minute realized volatility, EMA difference/ATR, observed
session range, opening gap versus prior session, trailing20 support/resistance.
At least21 bars, positive consistent OHLC, strictly increasing times, latestbar
<=180seconds and underlying/option quotes <=120seconds are required. Missing
market data becomes UNCERTAIN / NO_TRADE. Missing volume, IV or Greeks stays null.
Option latest trade size is explicitly NOT volume. Only standard100 multipliers.

Regimes: vol>=40% HIGH_VOLATILITY; ATR-normalized trend>=0.45 and positive20bar
return TREND_UP; inverse TREND_DOWN; vol<8% LOW_VOLATILITY; abs(trend)<0.45 RANGE;
otherwise UNCERTAIN. Confidence is heuristic, not calibrated probability.

TREND follows the classified trend. RANGE requires RSI<35 or >65 in range/lowvol.
DEFENSIVE proposes a long put only with negative returns in down/highvol regimes.
All can return NO_TRADE. Contracts are selected by moneyness, spread and symbol
within eligible budget/liquidity/DTE. No fake candidate is generated to fill UI.

## Risk policy

Per trade min(0.5% equity,$500); aggregate paid premium <=2% equity; max3 positions;
one primary directional thesis per underlying (no implemented hedge exception).
Cash AND options buying power cover all premium. Daily equity decline from broker
last_equity must be <1% (configurable only tighter via PHASE2_DAILY_DRAWDOWN_FRACTION).
15-minute cooldown from any broker submission. All unknown/short/nonoption
exposure, outstanding orders, duplicate contract/client ID, malformed account,
unmatched account fingerprint, live config, stale state, outside-window/closedmarket
and emergencykill are vetoes. Ask/bid spread <=10% AND $0.15; both quote sizes>=5
OR OI>=100 dated within3days. Expiry24hours–7days. PHASE2_EMERGENCY_KILL vetoes
research approval. These limits are not modified by reflection or agent scores.

The existing Phase1 SPY position contributes its real paid premium and prevents
another SPY directional thesis. Manager recommendations HOLD/REDUCE/EXIT/EXPIRED/
RISK_ALERT cannot submit orders. Expiry/exercise handling requires separate
authorization. Long-option premium risk does not describe post-exercise exposure.

## Allocator and performance

Only candidates without severe critic objections, conflicting underlying exposure
or insufficient aggregate budget are ranked. Score =20% confidence +20% regimefit
+20% spreadquality +15% historicalquality +10% budgetefficiency +15% criticquality.
Minimum0.50; then independent risk veto. Selected-but-approved means
DRY_RUN_CANDIDATE, never executed. Current exposure can produce NO_TRADE despite
otherwise plausible fresh proposals.

Rejected evaluated proposals become COUNTERFACTUAL ask-entry shadows. Later bid
marks measure hypothetical liquidation, excluding fees and execution uncertainty.
Reject-helped = negative hypotheticalPnL; regret =max(0,hypotheticalPnL).
Overlapping same-agent/contract entries are suppressed for60minutes. Scores use
one latest completed-horizon mark per shadow, not every poll. Before a completed
60-minute horizon the score is neutral50 and PnL is interim/unscored.

Score =50 + n/(n+20) × [10×mean(clipped riskreturn,-1..1) +5×(2×hitrate−1)].
Counterfactual influence is bounded to±15. Executed metrics remain unavailable
until a future authorized execution can be attributed to an agent. Phase1 is a
separate infrastructure test, not fabricated agent performance. Reflection
describes measurable outcomes but does not claim causal IV/theta/regime attribution.

## Persistence and authorization

Migration003 is additive. `phase2_risk_decisions` avoids the existing Phase0
`risk_decisions` table's incompatible analysis-run relationship. Twelve new tables
have RLS and no anonymous/frontend access. A service-role-only transaction inserts
the full cycle and component payloads atomically. Stable batch/sequence UUIDs make
restarts idempotent. Phase1 orders/fills/claim/evidence are unchanged.

`PHASE1_RETIRED=True` removes the old token's authorization power; it cannot be
used for Phase2. The old encrypted variable may remain inert in Railway; no
secret needs to be read or transmitted. There is no Phase2 execution endpoint,
credential or UI toggle. Future authorization must be a separately scoped,
short-lived server-only capability bound to paper account, strategy/risk policy,
expiry and explicit user-authorized order budget. That future mechanism is only
designed, NOT enabled or implemented as an execution path in Part1.

`PHASE2_DRY_RUN_BATCH` is a NONSECRET operator batch label in Railway. On startup,
up to3 finite read-only cycles run >=60seconds apart; completed IDs are skipped.
No cron or infinite loop. Failed data acquisition/persistence blocks the batch.
All production startups reject EXECUTION_ENABLED=true. Public dashboard is GET-only.

## Limitations

One underlying; deterministic heuristics, not trained agents; no agent-attributed
executions yet; finite research batch, not continuous monitoring; historicalscore
query bounded to latest500 marks/100shadows; no reliable option dailyvolume when
not provided; no Greek PnL decomposition. Watch these before Part2 expansion.
Dashboard explicitly timestamps recorded snapshots; refresh does not run a cycle.

## Verification

Production evidence and actual dry-run results are recorded separately under
`evidence/phase-2/`. Implementation alone is not evidence of a production result.
