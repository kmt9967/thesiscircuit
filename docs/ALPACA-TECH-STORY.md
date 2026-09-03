# ThesisCircuit: competing theses, accountable decisions

ThesisCircuit uses a dedicated $100,000 Alpaca PAPER account. All results are simulated and
hypothetical, with no real funds and no investment advice. Options can lose their full premium.

The backend calls Alpaca's Trading API for account/clock/position/order state and its Market Data
API for stock minute bars, options contracts, quotes and Greeks. The current options feed is
`indicative`: quotes are modified and trades delayed, not OPRA-equivalent execution guarantees.
See [Alpaca snapshots](https://docs.alpaca.markets/us/reference/optionsnapshots).

The implementation uses custom asynchronous **httpx** clients with strict Pydantic models.
It does NOT use alpaca-py as its core, and does NOT claim MCP or CLI execution. The historical
Phase 1 trade proved one paper fill; its one-time authorization is retired. Phase 2 is read-only.

Three deterministic strategy agents produce long-call/long-put proposals or NO_TRADE from
minute-bar features and regime classification. A Critic challenges each thesis. MetaAllocator
balances signal/regime fit, liquidity, historical score, premium efficiency and objections.
Independent deterministic risk gates can veto every proposal. No AI can change those limits.

Bounded, leased research cycles refresh state, produce proposals, audit risk, record rejected
counterfactuals and review actual positions. Supabase retains the complete decision chain.
The Vercel dashboard separates actual Alpaca PAPER equity/P&L from shadow outcomes. Shadow
ask-entry/later-bid marks explain avoided hypothetical losses and missed opportunities without
pretending they were orders. Shrunken agent scores prevent a lucky sample from dominating.

Future autonomous execution requires separate server-only authorization, both execution gates,
fresh final risk checks and a bounded server coordinator. Phase 2.5 implements an isolated durable
intent/claim/dispatcher library with synthetic-only production verification. There is no browser
execution toggle. Until a bounded activation is separately authorized, all research remains NO ORDER.
