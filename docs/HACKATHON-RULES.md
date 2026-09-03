# Alpaca AI Trading Agents Hackathon — Final Rules Check

Final recheck: September 3, 2026 UTC/PKT. Sources were the full official Lablab event/submission pages, the LABLAB.AI Alpaca official-updates channel and its pins, the general event-updates channel, and the pinned official Alpaca FAQ. No Devpost or unrelated catalog was used.

## Execution-critical rules

- PAPER trading only; no real funds are involved.
- All strategies must incorporate options trading.
- Build an autonomous agent using the Alpaca Trading API and use MCP or CLI. The official FAQ clarifies that an official SDK is acceptable when its use is explained and official SDKs are prioritized.
- The judging account must be a fresh paper account dedicated to the hackathon and start at exactly $100,000.
- Official competition measurement begins Monday, August 31, 2026 at 9:30 a.m. ET.
- Alpaca's FAQ states that the measurement window ends Friday, September 4, 2026 at 9:30 a.m. ET (**13:30 UTC**), based on total account equity. It also notes an end-of-day Thursday, September 3 observation so expiration exercises/assignments can be reflected. ThesisCircuit does not infer permission to trade after the stated Friday cutoff.
- Both Alpaca's free indicative options feed and paid OPRA are permitted. OPRA/Algo Trader Plus is not automatically provided.
- The FAQ says there are no restrictions on options strategies. ThesisCircuit applies the stricter local policy of premium-bounded or defined-risk positions.
- No official balance-reset requirement or permission was found. ThesisCircuit did not reset the judging account.

## Submission deadline and requirements

The latest official LABLAB.AI event-update announcement states: **Friday, September 4 at 5:00 p.m. CEST / 8:00 a.m. PDT**, which is **15:00 UTC / 20:00 PKT**.

This submission cutoff is separate from Alpaca's 13:30 UTC scoring cutoff. The Lablab event header and localized schedule render inconsistent timezone labels, so ThesisCircuit uses the explicit multi-timezone Discord announcement for the submission deadline and the Alpaca FAQ for the scoring cutoff.

The official page/form requires:

- Public GitHub repository
- Project title and short/long descriptions
- Technology/categories and event track
- Alpaca PAPER account ID
- One-page write-up covering AI logic, risk gates, and Alpaca infrastructure
- Cover image, demo video, presentation slides, and hosted application URL where applicable

Judging combines total-account-equity performance with creativity, autonomy, robustness, technology implementation, presentation, and social engagement. A UI is not required by Alpaca's FAQ, but ThesisCircuit provides one for auditable evidence.

## ThesisCircuit compliance

- Dedicated PAPER account began at exactly $100,000.
- Exactly one options opening order was submitted; no additional or closing order was sent.
- The only supported execution base URL is `https://paper-api.alpaca.markets`.
- The official `alpaca-py` SDK is documented and wrapped by typed deterministic application services.
- Current production flags keep execution and autonomy disabled.
- Shadow/counterfactual results are labeled and never presented as broker executions.
- No live brokerage account or live credential was created.

## Disclosures

Paper trading is hypothetical, involves no actual securities transaction or real funds, and does not guarantee future results. Content is not investment advice. Options carry significant risk, and all investments involve risk.

## Official sources

- https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon
- https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon/teqprotech/submission
- LABLAB.AI Discord channel `official-updates-alpaca-ai-trading-agents-hackathon`
- LABLAB.AI Discord channel `updates-alpaca-ai-trading-agents-hackathon`
- https://docs.google.com/document/d/13XWsMvW3mFm26xGlBLvdzzJ_eZQ33T4ZrP-vd9eat50/edit
