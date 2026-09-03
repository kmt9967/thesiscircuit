# ThesisCircuit: competing theses, accountable decisions

ThesisCircuit uses a dedicated $100,000 Alpaca PAPER account. All results are simulated and
hypothetical, with no real funds and no investment advice. Options can lose their full premium.

The backend calls Alpaca's Trading API for account/clock/position/order state and its Market Data
API for stock minute bars, options contracts, quotes and Greeks. The current options feed is
`indicative`: quotes are modified and trades delayed, not OPRA-equivalent execution guarantees.
See [Alpaca snapshots](https://docs.alpaca.markets/us/reference/optionsnapshots).

The production integration uses Alpaca's official pinned **alpaca-py 0.44.0** SDK for account,
clock, position, order, asset, options-contract, stock-bar, stock-quote and option-snapshot
operations. A narrow compatibility adapter preserves the already-tested Pydantic parsing,
durable intent and reconciliation layers. The SDK is configured with `paper=True`, exact
paper/data hosts, redirects disabled, ten-second timeouts and its retry counter forced to zero.
The sole SDK submission call remains behind the database-fenced dispatcher; uncertainty is
resolved by client-order-ID reads and never by a second submission.

The actual infrastructure proof used one `SPY260904C00768000` long call. Alpaca PAPER filled
one contract at $1.84 after a $1.88 DAY limit submission with $188 planned maximum premium
risk. The final September 3 22:47 UTC read reported $100,397.94 equity, one position, zero
open orders and one historical order. Those are timestamped broker observations, not shadow
returns or a claim about Alpaca's final judging snapshot.

This SDK choice follows the official FAQ: MCP or CLI are permitted, and an SDK is permitted
when the engineering reason is explained and official SDKs are prioritized. The reason is
that ThesisCircuit needs a deterministic in-process transaction boundary between Supabase's
atomic intent/session gate and the one broker call. MCP is therefore documented as an optional
read-only agent tool, not falsely claimed as the execution mechanism. The historical Phase 1
trade proved one paper fill; its one-time authorization remains retired.

Three deterministic strategy agents produce long-call/long-put proposals or NO_TRADE from
minute-bar features and regime classification. A Critic challenges each thesis. MetaAllocator
balances signal/regime fit, liquidity, historical score, premium efficiency and objections.
Independent deterministic risk gates can veto every proposal. No AI can change those limits.

Bounded, leased research cycles refresh state, produce proposals, audit risk, record rejected
counterfactuals and review actual positions. Supabase retains the complete decision chain.
The Vercel dashboard separates actual Alpaca PAPER equity/P&L from shadow outcomes. Shadow
ask-entry/later-bid marks explain avoided hypothetical losses and missed opportunities without
pretending they were orders. Shrunken agent scores prevent a lucky sample from dominating.

Autonomous execution requires a separate server-only token, both execution gates, a matching
immutable bounded session, fresh final risk checks and the durable coordinator. The activation
launcher has no browser or frontend route. Every completion, expiry, kill, unknown broker state,
dispatcher failure or competition-window closure drives both local gates false and uses a
single-environment Railway project token to persist and read back both encrypted variables as
false. No session is authorized by this implementation work; resting production remains NO ORDER.

Final-submission preparation performed read-only production checks only. Execution and
autonomous trading remain disabled, the existing position was not changed or closed, and no
additional broker order was submitted.
