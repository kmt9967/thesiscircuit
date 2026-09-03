# Shadow / counterfactual outcomes

Shadows record rejected but well-formed option proposals. They are never Alpaca orders.
Hypothetical entry is the observed ask; a subsequent observed bid marks liquidation value:
`(later_bid - entry_ask) * 100`. No fees, guaranteed size or fills are implied.

Position/shadow observations are retrieved separately from fresh entry candidates. When the
market is closed, the latest legitimate timestamped snapshot may mark an older shadow, but
cannot authorize execution. Future-dated quotes, observations older than 72 hours, marks before
entry, or at/after contract expiry are excluded. Missing valid data means no mark, not zero P&L.

Elapsed horizon is measured from entry to the QUOTE timestamp, never the retrieval timestamp.
At least 60 minutes is required for scoring. A later snapshot is labelled a later observation,
not an exact 60-minute return. For scoring, the first observed completed horizon per shadow is
fixed; duplicate cycles cannot inflate the sample count or cherry-pick a later profitable mark.
The dashboard can show the latest mark with its timestamp; scoring uses the fixed first sample.

Positive hypothetical P&L = missed opportunity / regret; negative = avoided hypothetical loss.
This describes the rejected trade, not causality or the correctness of the risk limit.
Actual account equity and competition P&L remain separate. No simulated replay data is inserted
into production shadow tables. Historical options paths and exact-horizon historical quote
retrieval are not implemented; do not claim a full backtest.
