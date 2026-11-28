# Threat model: reconciliation-service

- **Status:** Draft 2026-11-28, awaiting owner review · STRIDE · Platform model and residual risks: [assistant repository](https://github.com/subhamviky/enterprise-finance-genai-assistant/blob/main/docs/engineering/security/threat-model.md). Synthetic data only.

**Assets:** bank lines, open items, exceptions and their proposals, the idempotency claims, the feed cursor, the ledger-retry lease; the ability to close an exception or ask the ledger for an adjustment.

| # | Threat | Control | Evidence |
|---|---|---|---|
| R1 | **Spoofing** a caller | Cloud Run IAM verifies the Google ID token; user routes require identity (401/403); service routes map callers to `reconciliation.read` or `reconciliation.resolve`; `/health` is the only open route | `routers/identity.py`, design 5.6 |
| R2 | **Tampering**: a line matched twice or half-matched | conditions on `status = OPEN AND version = v` and one transaction for the match | I-1, I-2 |
| R3 | **Tampering**: a duplicate bank line or settlement event | claim per `line_id`; conditional puts for items and lines | I-3, I-8 |
| R4 | **Tampering**: the triage model proposes an unauthorised action | validated when stored and again at accept; beyond-limit proposals refused and replaced by a remittance request | I-5, BR-11 |
| R5 | **Tampering**: a false claim that an adjustment was posted | `resolve` closes only if the ledger holds an adjustment with that id whose reference names the bank line | ADR 0009 |
| R6 | **Repudiation** | the exception keeps the proposal, the verdict and the executed proposal; one JSON log line per request with a correlation id | design 6 |
| R7 | **Information disclosure**: cross-tenant read | tenant on every key; one tenant per deployment (`RECON_TENANT`) | ADR 0010 |
| R8 | **Denial of service**: poison messages or a stuck ledger | dead-letter on a line that can never succeed; a ledger outage leaves the decision stored and the posting PENDING, retried under the same key; a lease keeps retries single | design 10 |
| R9 | **Elevation**: an agent or caller beyond its role | the assistant alone holds `resolve`; O2C holds `read` | ADR 0008 |

Residual: `duplicate_of` reads every line of a tenant (a scale limit); the AWS stack was never applied to a real account; an unused Secrets Manager secret is provisioned (G-4); no penetration test.
