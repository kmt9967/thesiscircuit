# Security

## Non-negotiable controls

- Only Alpaca's paper endpoint is accepted.
- Live-trading and order-submission flags must both be false; startup otherwise fails.
- Phase 0 exposes analysis/replay endpoints only and implements no broker order method.
- Secrets live in local ignored files or platform secret stores, never Git.
- Logs redact keys, secrets, tokens, account IDs, database URLs, and authorization headers.
- Supabase row-level security is enabled by default; service-role access is backend-only.
- Preview deployments must not receive production credentials.

## Reporting

Open a private GitHub security advisory once the public repository exists. Do not include credentials, account IDs, private URLs, or exploitable proof in public issues.

## Operational checklist

Run `python scripts/safety_audit.py` and the full test suite before each deployment. Treat any safety-audit failure as a release blocker.

