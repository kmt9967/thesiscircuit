# Phase 2.6 Part 2: bounded PAPER session proposal

**REVIEW COMPLETE; NOT AUTHORIZED; PRODUCTION ACTIVATION NOT READY.**
No broker mutation, PAPER session creation, token provisioning, execution enablement,
or PR merge occurred. Both execution flags remain false.

## Account and SPY review

Three real-data production research cycles completed at 16:22:33, 16:23:36 and
16:24:40 UTC on September 3, 2026. These are timestamped observations, not reusable
execution preflights. [Sanitized evidence](../evidence/phase-2.6/2026-09-03-preauthorization-research.json).

At the final cycle: dedicated active PAPER account matched; equity $100,369.94,
cash/options buying power $99,815.94; general buying power $399,263.76.
Risk uses cash AND options buying power, not the larger general figure.
Daily baseline equity $99,986.94; no drawdown at this observation. One historical
filled order, zero open orders, one existing position, zero new Phase 2 orders.

SPY260904C00768000 remained long one, entry $1.84, premium paid $184.
Broker mark $5.54, value $554, unrealized PAPER P&L +$370 (+201.087%).
Independent indicative quote at 16:24:38.233623 UTC (12:24:38.233623 ET): $5.44/$5.58,
age 2.525 seconds at review. Midpoint and broker mark are not interchangeable;
Alpaca does not provide a separate position-mark timestamp.
Snapshot Greeks: delta .7619, gamma .0476, theta -1.0647, vega .1252, IV .161.
No independent Greek timestamp is supplied. Theta scaled to one contract is about
-$106.47/day as a sensitivity, NOT a forecast or guaranteed loss.
Assuming September 4 16:00 ET expiry: 27.589 hours (1.150 days) remained.

System recommendation: **HOLD, monitor only**, with an expiration RISK_ALERT for
operator attention. LOW_VOLATILITY did not contradict the long call; the model reported
regime compatible and thesis not invalidated. This short-horizon heuristic is not
proof that the original thesis is correct. The option was ITM relative to the observed
underlying $772.51. If still ITM at expiry, Alpaca can automatically exercise it;
a standard long 768 call can become 100 SPY shares requiring $76,800 simulated cash.
The premium cap does not bound subsequent stock exposure. Broker exercise/risk actions
can occur while our flags are false. No exercise, DNE, exit or broker-setting change
is authorized here. [Alpaca expiration policy](https://docs.alpaca.markets/us/docs/options-trading).

## Agents and bounded boundary

Batch `phase26-preauthorization-20260903-a` completed exactly three leased, idempotent
research cycles, all NO_TRADE. The latest full cycle observed 80 option quotes, fresh
underlying minute-bar features, and no data errors. Regime: LOW_VOLATILITY, confidence .60.
Trend, Range and Defensive each returned NO_TRADE with no contract: no qualifying
regime signal/liquid-contract combination. Critic severity .95 included existing-SPY
concentration. MetaAllocator selected nothing; three risk decisions were REJECTED.
Null-contract proposals fail `data_fresh`, `valid_options`, `proposal`, `max_new_risk`,
`liquidity`, `expiry`, and `duplicate_position`. This does NOT mean the downloaded
market snapshot was stale. `underlying_exposure` independently failed because SPY is held.

No new shadows in the latest cycle. The existing RANGE counterfactual was re-marked,
not traded: latest hypothetical bid-liquidation P&L +$499. Scores: TREND 50.00, RANGE
50.24, DEFENSIVE 50.00. RANGE's one first-observed completed horizon contributed +$1,
not the later cherry-picked +$499. Reflection recorded a missed hypothetical opportunity,
without changing hard limits or attributing the historical Phase 1 fill to these agents.

The durable research coordinator ran in production and persisted its full chain.
The active PAPER execution coordinator was deliberately NOT invoked: it requires both
flags true and an approved active session. Session/budget/intent/claim/reconciliation
components retain the separately labelled Part 1 production SYNTHETIC evidence.
Do not represent real-data research as completed broker-dispatch proof.

## Exact first-session proposal (PLANNED, not a session record)

| Limit | Proposal |
| --- | --- |
| Start | T0 after later explicit approval and fresh market-open preflight on September 3, 2026; no later than 18:00 UTC (14:00 ET / 23:00 PKT). No rollover if missed. |
| Lifetime | At most 60 minutes from creation/T0; hard expiry T0+60 minutes, no later than 19:00 UTC. Early completion/kill allowed. |
| Cycles | At most 3: T0, T0+20 minutes, T0+40 minutes. No cron, catch-up burst or indefinite loop. |
| Opening / closing / total orders | At most 1 / 0 / 1. Zero orders is a valid outcome. |
| Positions | At most 2 including the existing position; the stricter one-thesis-per-underlying gate remains. |
| New premium | min($250, 0.5% of fresh equity), cumulative and never refunded after rejection/UNKNOWN/crash; excludes broker fees. |
| Aggregate premium | min($2,000, 2% of fresh equity), including existing $184 cost basis and reserved risk; recheck before submission. |
| Instruments | SPY only; one standard 100-multiplier LONG_CALL or LONG_PUT; buy one, DAY limit, no extended hours. No shorts, spreads, hedge, add-on, replace or cancel. |
| Spread/liquidity | <=$0.15 AND <=10%; both quote sizes >=5 OR OI >=100 dated within 3 days. |
| Freshness/DTE | Account, clock, underlying and option data <=120 seconds old, no future timestamps; 24 hours to 7 days to expiry. No 0DTE. |
| Kill | Daily equity drawdown >=1% against broker last_equity; plus stale data, account/config mismatch, unknown exposure/order, DB/lease failure, revoked/expired session, manual kill, market/window closed or budget breach. At most 2 broker failures; no blind retries. |
| Existing SPY | Monitor only; exit permission false; automatic closing orders zero. Separate permission and reviewed exit path required. |

**Current SPY blocks every new SPY entry.** With SPY the only allowed underlying,
this session cannot open a trade while that exposure remains. Do not weaken the gate,
invent a hedge, close the position or expand the universe to force a trade. Limits
cap bot submissions, not external broker expiry/exercise behavior.

## Fresh market-open preflight and authorization design

1. With both flags false, verify reviewed/deployed SHA, green CI, Supabase connectivity,
   durable lease/intent/session RPCs and server-only permissions. Reject unresolved
   PAPER intents or UNKNOWN broker states. Recheck official window and integration
   compliance; this document and old snapshots never authorize an order.
2. Fetch current dedicated account fingerprint/status, cash/equity/last_equity/options
   buying power, all positions, all historical/open orders and broker market clock.
   Reject unexpected changes, unknown exposure, blocked account, closed market,
   stale/future data, conflicting orders or missing daily baseline.
3. Refresh underlying features/regime, existing SPY quote/Greeks/DTE/expiration risk,
   and option universe. Rerun agents, Critic, allocator and independent risk. Validate
   signal, strategy, tradability, quantity, limit, liquidity/spread, DTE, concentration,
   cooldown and daily/aggregate/new-risk budgets. Rejected/null proposal => NO_TRADE.
4. Only after separate approval and missing activation-path implementation, create an
   immutable finite PAPER session with these exact limits, fresh equity/time and unique
   session/cycle/proposal/client-order IDs. Verify no overlapping session, available
   durable budget and sufficient expiry margin. Do not reuse a spent ID after restart.
5. Later execution requires ALL: `TRADING_MODE=paper`, `ALPACA_PAPER_TRADE=true`,
   both live flags false, exact `https://paper-api.alpaca.markets`, both execution and
   autonomous flags true, separate valid server-only Phase 2 token, active finite
   session, available budget, open competition/market, fresh risk approval, durable
   intent, atomic claim and safe reconciliation. No Phase 1 token/frontend bypass.
6. Rerun fresh risk after activation. Persist intent, claim, reserve budget, reconcile
   unique client ID, refresh terms/state/session, then atomically budget-gate SUBMITTING.
   Ambiguous submission => GET reconciliation only, never a second POST.
7. A later launcher must disable both flags on completion/kill/error and verify false
   production state. Hard database expiry is the crash backstop, not a substitute for
   the missing environment shutdown wiring. Read-only reconciliation may continue;
   no automatic close/cancel. Any failed gate => NO_TRADE with preserved audit/budget.

## Readiness verdict

- Cycle lease, durable intent, atomic claim, reconciliation and session/budget
  components: verified, with real PostgreSQL races and production SYNTHETIC tests.
- Cadence defect fixed: longer waits now inspect status/authorization every <=60s
  until due. Expiry, revocation, live config, manual kill and stalled/backward clocks
  fail closed. Three 20-minute monitor cycles are tested with advancing fake time.
- **Production activation NOT READY:** startup still rejects enabled flags; the real
  server-only launcher and verified terminal shutdown wiring are absent. This review
  deliberately does not remove that interlock or provision a token.
- **Integration compliance unresolved:** official FAQ permits MCP/CLI or an explained
  SDK approach prioritizing official SDKs. Current custom httpx is not MCP/CLI/official
  SDK. Implement and verify an accepted approach or obtain organizer clarification
  before declaring this requirement satisfied.
- Existing SPY prevents another SPY entry. No selected candidate is approved.

## Exact future permission question

Only after resolving the blockers above:

> Do you authorize one bounded PAPER session on September 3, starting after a fresh
> passing market-open preflight and no later than 18:00 UTC, expiring within 60 minutes,
> with at most three 20-minute-spaced cycles, at most one opening order, zero closing/
> modify/cancel orders, one total order, SPY long calls/puts only, $250/0.5% new-premium
> and $2,000/2% aggregate ceilings, two-position cap, 1% daily drawdown kill and all
> other limits above, current SPY monitor-only, and both execution flags disabled and
> verified at shutdown? No gate may be bypassed; existing SPY may mean zero orders.
> No rollover if the window is missed.

This is proposed wording for later consent, not permission granted or a scheduled run.

## Validation

242 backend tests passed locally (eight new cadence cases), Ruff, Python compilation,
paper/live-endpoint capability audit, tracked/pending secret scan, frontend typecheck/
lint, static safety tests and production build. CI also runs isolated real PostgreSQL
eight-worker claim/session-budget races. Deployment/check references are recorded in PR #3.

SIMULATED PAPER TRADING — NO REAL FUNDS. Hypothetical results, not investment advice.
