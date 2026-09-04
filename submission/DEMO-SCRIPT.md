# ThesisCircuit Final Demo Script

Target duration: **4 minutes 30 seconds**. Record the production application at
`https://thesiscircuit.vercel.app/` at 1920×1080, 100% browser zoom.

## Browser preparation

Open exactly these tabs before recording:

1. `https://thesiscircuit.vercel.app/` — presentation tab; clean browser chrome,
   notifications/bookmarks hidden.
2. `https://github.com/kmt9967/thesiscircuit` — optional closing proof; do not spend
   demo time browsing source.

Do not open Alpaca, Railway, Supabase, Vercel settings, environment variables, or any
credential screen. Refresh the production app once before recording and confirm the
account panel has finished loading.

## Recording walkthrough and narration

### 0:00–0:25 — Hero and problem

**Show:** top of the production dashboard, including the PAPER badges and account card.

**Say:** “Most trading-agent demos celebrate every trade. ThesisCircuit uses a harder
standard: AI strategies compete, risk decides, and sometimes the best trade is no trade.
Every number on this screen comes from the production PAPER pipeline.”

Pause briefly on the permanent PAPER/no-real-funds disclosure so the premise is clear
without audio.

### 0:25–0:50 — Competition account

**Show:** Competition Account card.

**Say:** “This dedicated Alpaca PAPER account started at $100,000. The dashboard reads
the current equity, cash, buying power, position count, and one historical order directly
from the backend.”

Do not narrate the current equity, cash, buying power, P&L, market status, or observation
time as fixed numbers; they are live/read-time values and may change.

### 0:50–1:25 — Strategy Arena

**Navigate:** Strategy → Strategy Arena.

**Say:** “Trend, Range, and Defensive independently evaluate the same timestamped Alpaca
snapshot. Each produces a typed thesis, confidence heuristic, risk budget, and reasons not
to trade. Today all three preserve cash because the recorded evidence does not qualify.”

### 1:25–1:55 — Decision Council

**Navigate:** Strategy → Decision Council.

**Say:** “The Critic attacks each thesis. The MetaAllocator compares the surviving cases,
and the deterministic Risk Officer owns the final vote. NO TRADE is a successful,
auditable outcome—not a missing result.”

### 1:55–2:30 — Actual Alpaca PAPER proof

**Navigate:** Positions → Original Paper Trade.

**Say:** “The system also proved the complete execution path once. Alpaca PAPER accepted
one buy-to-open DAY limit order for one SPY September 4, 2026 $768 call. The limit was
$1.88, the actual fill was $1.84, and planned premium risk was $188. The timeline shows
readiness, approval, submission, broker reconciliation, and execution shutdown.”

These historical values are fixed evidence. State clearly that no additional or closing
order was submitted.

### 2:30–2:55 — Position Watch

**Navigate:** Positions → Current Position.

**Say:** “The existing PAPER position is rendered from Alpaca state. Entry is historical;
current value, unrealized P&L, time-to-expiry, quote freshness, and research recommendation
are read-time values. Closing authority remains disabled.”

Do not hardcode the current mark, position value, P&L, Greeks, recommendation, or time to
expiry in narration.

### 2:55–3:20 — Risk Engine

**Navigate:** Strategy → Risk Engine.

**Say:** “Agent prose cannot authorize an order. Deterministic gates verify the PAPER
endpoint, live-trading block, account state, official window, freshness, liquidity, buying
power, bounded loss, conflicts, duplicate prevention, cooldown, and drawdown. Any blocked
or unknown condition fails closed.”

### 3:20–3:45 — Shadow Desk

**Navigate:** Research → Shadow Desk.

**Say:** “Rejected proposals are still useful evidence. The Shadow Desk measures later
counterfactual outcomes without claiming an Alpaca fill, executable price, or real P&L.
This lets us evaluate decision regret while keeping simulated research separate.”

### 3:45–4:10 — Reliability Architecture

**Navigate:** Research → Architecture.

**Say:** “Cycle leases prevent overlap. Durable intents are persisted before broker
contact. Atomic claims permit one worker, uncertain responses reconcile before retry, and
bounded sessions enforce expiry and order budgets. Terminal outcomes force execution off.”

Point to the production service strip: Alpaca PAPER connected, Supabase healthy, Risk
Engine active, execution disabled, live trading blocked.

### 4:10–4:30 — Close

**Show:** footer disclosure, then return to Overview.

**Say:** “ThesisCircuit does not ask judges to trust an agent’s confidence. It provides the
data, debate, vetoes, broker result, and replay needed to verify every decision. Simulated
PAPER trading only—no real funds.”

## Recording checklist

- Resolution: 1920×1080, 30 fps or higher; export 1080p.
- Browser zoom: 100%; pointer visible; deliberate scrolling with brief pauses.
- Expected duration: 4:20–4:40.
- Hide bookmarks, notifications, personal profile details, and unrelated tabs.
- Never show credentials, environment variables, full account identifiers, or admin UIs.
- Do not claim current P&L is guaranteed, final judging P&L, or a live-money result.
- Do not describe shadow records as submitted orders.
- Confirm both execution statuses visibly read disabled before recording.
