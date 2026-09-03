# ThesisCircuit Demo Script (3–5 minutes)

## 0:00–0:25 — Hook

“Most trading-agent demos celebrate every trade. ThesisCircuit is built around a harder standard: AI strategies compete, risk decides, and sometimes the best trade is no trade.”

Show the dashboard hero and the permanent PAPER disclosure. Point out that the values are live Alpaca paper-account observations, not mock data.

## 0:25–1:05 — Agent arena

Scroll to Strategy Arena. Explain that Trend, Range, and Defensive evaluate the same timestamped Alpaca snapshot independently. Show their decisions and the Council result. Emphasize that a critic actively searches for stale data, weak liquidity, disagreement, and unsupported assumptions.

## 1:05–1:40 — Risk owns authority

Open the risk/decision section. Explain that prose cannot authorize an order. Deterministic gates check PAPER mode and endpoint, account state, market window, freshness, tradability, liquidity, buying power, maximum loss, conflicts, unique order references, session expiry, and budgets. Show a NO TRADE result and its objections.

## 1:40–2:30 — Actual Alpaca PAPER proof

Show the account and order cards. State the exact verified result: one `SPY260904C00768000` long call, quantity one, DAY limit $1.88, filled by Alpaca PAPER at $1.84, with $188 planned maximum premium risk. Show the actual position and audit timeline. Clarify that no second or closing order was submitted.

## 2:30–3:20 — Reliability under failure

Use the architecture slide or repository diagram. Explain that Supabase persists the intent before broker contact; an atomic claim allows one worker; timeouts reconcile by `client_order_id` before retry; cycle locks expire after crashes; UNKNOWN broker states consume budget conservatively. Mention the eight-worker race produced exactly one winner.

## 3:20–4:00 — Bounded autonomy and shutdown

Show system status. Execution and autonomous trading are both disabled. Explain that a bounded server-only session has an expiry and atomic opening/closing/total budgets, and terminal outcomes force both flags off. Synthetic production activation and shutdown generated zero broker calls.

## 4:00–4:25 — Close

“ThesisCircuit does not ask judges to trust an agent’s confidence. It provides the data, debate, vetoes, broker result, and replay needed to verify every decision.”

End on the dashboard disclosure: “SIMULATED PAPER TRADING — NO REAL FUNDS. Results are hypothetical and are not investment advice.”

## Recording checklist

- Hide bookmarks, notifications, account identifiers, and developer secrets.
- Record the production URL, not localhost.
- Keep browser zoom at 100% and text legible.
- Do not show Railway, Supabase, Alpaca credentials, or environment-variable screens.
- Do not imply shadow/counterfactual records were executed.
