# Alpaca AI Trading Agents Hackathon — Current Rules

Rechecked on 2026-08-30 PKT from the official Lablab event page, the official Alpaca FAQ posted and pinned by Erika (Alpaca) in LABLAB.AI Discord, and the pinned disclosure.

## Execution-critical rules

September 3, 2026 review: reread the linked official FAQ in full and checked the
official Lablab page. No execution-critical FAQ changes from September 2 were found;
the EOD September 3 versus September 4 09:30 ET wording remains. This does not claim
a fresh sweep of every Discord message. The custom-httpx integration does not yet
demonstrate the MCP/CLI or explained SDK route; see `PHASE-2.6-PREAUTHORIZATION.md`.

September 2, 2026 update: the linked official Alpaca FAQ was reread in full. It now
clarifies that scoring uses portfolio equity as of end-of-day Thursday September 3,
including exercises/assignments for options expiring that day, while retaining the
Friday September 4 9:30 a.m. ET measurement-end language. This does not prohibit the
September 2 controlled options test. Other execution-critical rules below remain
unchanged. This recheck was of the official FAQ; no claim is made here that every
new Discord message was re-inspected.

- PAPER trading only; no real funds are involved.
- All strategies must incorporate options trading.
- Build an autonomous agent using Alpaca Trading API and use MCP or CLI; an official SDK is acceptable when the reason is documented and official SDKs are prioritized.
- The judging account must be a fresh paper account dedicated to the hackathon and start at exactly $100,000.
- Official competition trading begins Monday, August 31, 2026 at 9:30 a.m. ET.
- Official P&L measurement ends Friday, September 4, 2026 at 9:30 a.m. ET; Alpaca evaluates total account equity.
- Do not use a testing account for official P&L measurement.
- Both Alpaca's free indicative options feed and paid OPRA are permitted. OPRA/Algo Trader Plus is not automatically provided.
- The official FAQ says there are no restrictions on options strategies. ThesisCircuit nevertheless permits only premium-bounded or otherwise defined-risk strategies.
- No balance-reset permission was published. ThesisCircuit will not reset the judging account.

## Submission and judging

- Judging combines total-account-equity performance with creativity, autonomy, robustness, technology implementation, and presentation.
- The public event page requires a public GitHub repository, Alpaca paper account ID, project descriptions, cover image, video, slides, and hosted application URL where applicable.
- A one-page write-up must cover AI logic, risk gates, and Alpaca infrastructure.
- A UI is not required by Alpaca's FAQ, but ThesisCircuit provides one for auditable evidence.

## Current timing discrepancy

The event-page header currently renders `Sep 4, 8:00 PM PST`, while its event schedule renders `Sep 4, 8:00 PM Pakistan Standard Time`. The official Alpaca FAQ independently defines the trading measurement window in ET. ThesisCircuit uses the FAQ's ET timestamps for order gating and treats the enrolled Lablab submission UI as authoritative for the submission deadline it displays.

## Disclosures

Paper trading is hypothetical, involves no actual securities transaction or real funds, and does not guarantee future results. Content is not investment advice. Options carry significant risk, and all investments involve risk.

## Official sources

- https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon
- LABLAB.AI Discord channel `official-updates-alpaca-ai-trading-agents-hackathon`
- https://docs.google.com/document/d/13XWsMvW3mFm26xGlBLvdzzJ_eZQ33T4ZrP-vd9eat50/edit
