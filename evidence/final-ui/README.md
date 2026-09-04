# Final UI Evidence Plan

The final visual port materially changes the submission story. After the redesign PR is
merged and the same commit is promoted to production, regenerate these sanitized,
read-only screenshots from `https://thesiscircuit.vercel.app/`:

1. Hero and Alpaca PAPER account overview (desktop and mobile)
2. Market intelligence and market-regime state
3. Strategy arena
4. Decision council
5. Current position watch
6. Original verified PAPER trade and audit timeline
7. Risk engine and shadow desk
8. Reliability architecture and permanent safety disclosure

Each capture must retain the visible PAPER/no-real-funds disclosure and omit browser
profiles, credentials, full sensitive account identifiers, and developer tooling. Values
must come from the production Railway API; prototype and placeholder values are not
eligible evidence.

## Classification

- **PLANNED:** production screenshots above, pending merge and production promotion.
- **VERIFIED:** local responsive QA at 1920, 1440, 1366, 1280, 1024, 768, 430,
  390, 360, and 320 CSS pixels, using read-only production API responses.
- **CONFIGURED:** same-origin `/backend/*` proxy to Railway with no browser-exposed
  credential and no write controls.

The existing `evidence/final-submission/production-desktop.png` and
`production-arena.png` remain valid historical evidence for their recorded version, but
they should not be used as the final visual submission after this redesign ships.
