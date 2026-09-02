# Phase 2.5 evidence — pending production verification

## VERIFIED locally

- 181 backend tests passed, including 42 new durable-dispatch tests.
- Ruff, Python compilation, tracked/pending secret scan and paper/live-endpoint audit passed.
- Frontend lint/typecheck and static UI safety checks passed.
- No Alpaca order call was made by this task. Broker outcome tests use httpx MockTransport.

## CONFIGURED in working code, not yet verified in production

- Additive migration 005: one new table and three server-only RPCs.
- Durable immutable intents, atomic claims, irreversible SUBMITTING and GET-only recovery.
- Optional bounded synthetic batch and read-only verification endpoint.
- CI PostgreSQL permission/protocol verification and eight-worker contention check.

## PLANNED / awaiting verification

- Supabase application and access verification (action-time permission confirmation pending).
- Railway/Vercel deployment at the completed commit.
- Production synthetic batch, real expiry/recovery and deployment-restart replay check.
- Fresh read-only historical broker-order count and disabled flag verification.

Synthetic fixtures are not actual Alpaca orders or financial results. No production success is
claimed by this document until the corresponding verification is recorded.
