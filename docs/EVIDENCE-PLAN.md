# Phase 1 Evidence Plan

Sanitized artifacts live under `evidence/phase-1/`. Evidence never contains keys, secrets, passwords, full account identifiers, or unsanitized browser profiles.

- VERIFIED: direct read-only platform responses, tests, deployed HTTP status, Alpaca-reported order/fill/position state, Supabase rows, and UI rendering.
- CONFIGURED: settings whose platform configuration is verified but which do not themselves prove an event occurred.
- PLANNED: execution-window-dependent evidence not yet created.

Keep readiness receipts separate from actual order evidence. The September 2 readiness
snapshot proves 18 passing disabled-state gates, not submission. Only after an actual
Alpaca response may order/fill/position artifacts be marked VERIFIED.

The completed September 2 proof is now VERIFIED in
`evidence/phase-1/2026-09-02-completed-execution.json` and the completion report.
Earlier readiness-only files are retained as historical checkpoints, not current status.
