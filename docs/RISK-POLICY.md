# Phase 1 Risk Policy

The deterministic engine rejects unless all 17 gates pass: paper mode, paper endpoint, active account, server execution gate, fresh quote, tradable option, one-contract size, sufficient buying power, unique client order ID, no conflicting order, no existing position, DAY limit order, maximum loss at or below $250, official options/window rule, open market, daily drawdown below 1%, and live trading disabled.

An LLM cannot approve or override a rejected proposal. ThesisCircuit uses a long call for the first proof because its theoretical loss is bounded by premium paid. Naked short options, uncovered calls, unlimited-risk strategies, market orders, batch orders, and autonomous loops are excluded.

