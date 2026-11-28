# API reference

Source: `reconciliation-service/src/reconciliation_service/routers/`. On Cloud Run the service is private and IAM verifies the caller's Google ID token. User routes require an identity; service routes map the calling service account to a grant.

## User routes (`/api/v1`)

| Route | Responses |
|---|---|
| `POST /api/v1/statements` (array of `BankLine`) | 202 `{mode, results}`: `mode` is `sqs` (each result `QUEUED`) or `direct` (each result the outcome, `IN_PROGRESS` or `CONFLICT`) |
| `POST /api/v1/settlements/poll` | `{ingested}`: pull the settlement feed into open items |
| `POST /api/v1/ledger/retry` | `{posted}`: retry PENDING ledger postings |
| `GET /api/v1/lines/{line_id}` | 200 the line (status, matched settlements) · 404 |
| `GET /api/v1/exceptions?status=` | exception cases with candidates and the agent's proposal |
| `POST /api/v1/exceptions/{line_id}/accept` | 200 · 422 refused by the rules · 409 concurrent change |

## Service routes (`/service/v1`, for other systems)

| Route | Grant | Purpose |
|---|---|---|
| `GET /service/v1/exceptions` | `reconciliation.read` | exceptions, filtered by line |
| `GET /service/v1/lines/{line_id}` | `reconciliation.read` | one bank line (what was paid) |
| `POST /service/v1/exceptions/{line_id}/resolve` | `reconciliation.resolve` | close an exception once the ledger shows the adjustment (the body names the adjustment; 200 closed · 404 · 422 not confirmed) |

## Google Cloud entry points

`POST /pubsub/bank-lines` (Pub/Sub push; 204 on success, non-2xx redelivers) and `POST /jobs/scheduled` (the scheduled run: poll, retry, dead-letter pull). `GET /health` needs no identity.

## Guarantees

A line is processed once whichever path it takes; a match is atomic; an adjustment is requested with the key `recon-<tenant>-<line_id>`; `resolve` never closes an exception on the caller's word. Every response carries `X-Correlation-Id`.
