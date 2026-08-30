# Alpaca Integration

- Trading base URL is hard-locked to `https://paper-api.alpaca.markets`.
- Market data base URL is hard-locked to `https://data.alpaca.markets`.
- The Basic indicative options feed is the default; OPRA may be selected server-side only when legitimately available.
- Account reads cover account, clock, positions, and open orders.
- Market reads cover assets, latest stock quotes, daily bars, option contracts, and option snapshots.
- The only write is one single-leg, one-contract, buy-to-open DAY limit option order.
- `client_order_id` is deterministic. A timeout triggers a lookup by that ID and never a blind second POST.
- Reconciliation uses order/account/position GET requests only. No automatic cancel, replace, exercise, or close path exists.

