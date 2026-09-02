# Risk decision — PLANNED APPROVAL / VERIFIED REJECTION

The 17-gate deterministic engine returned `REJECTED` during the production preflight.

Failed gates:

- `execution_gate`: `EXECUTION_ENABLED=false`
- `fresh_data`: weekend quote was not current enough
- `hackathon_rules`: official P&L window had not opened
- `market_state`: market was closed

All remaining gates passed, including PAPER mode, PAPER endpoint, active account, tradability, one-contract size, buying power, unique client reference, no conflicting order, no position, supported order type, bounded loss, drawdown, and live-trading disabled.

An APPROVED artifact cannot exist until every gate passes inside the official window.
