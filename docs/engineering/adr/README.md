# Architecture Decision Records

One record per significant decision (context, options, decision, consequences). Records are not edited to change history: a reversed decision gets a new record that supersedes the old one. These are the decisions of `reconciliation-service`. Platform-wide decisions (free tier, synthetic data, Workload Identity Federation, promotion, the documentation layout) are in the [assistant repository's ADR index](https://github.com/subhamviky/enterprise-finance-genai-assistant/blob/main/docs/engineering/adr/README.md).

Template: [`0000-template.md`](0000-template.md).

| # | Decision | Status |
|---|---|---|
| [0001](0001-process-each-bank-line-under-one-e2a-claim.md) | Process each bank line under one E2A claim with a resumable handler, however it arrives | Accepted |
| [0002](0002-match-is-one-transaction-items-conditioned.md) | A match is one transaction: items conditioned on status OPEN and version, the line updated with them | Accepted |
| [0003](0003-one-open-item-per-settlement-one-line-per-line.md) | One open item per settlement and one line per line_id, by conditional puts | Accepted |
| [0004](0004-matcher-considers-oldest-open-items-first-with.md) | The matcher considers the oldest open items first, with a bounded subset search | Accepted |
| [0005](0005-no-model-output-changes-state-unvalidated.md) | No model output changes state unvalidated; a proposal is validated before it is stored and again before it executes | Accepted |
| [0006](0006-ledger-adjustment-is-posted-once-deterministic.md) | A ledger adjustment is posted once: a deterministic idempotency key and a lease for retries | Accepted |
| [0007](0007-statement-google-cloud-answers-queued-outcome.md) | A statement on Google Cloud answers QUEUED; the outcome is read from the line | Accepted |
| [0008](0008-service-routes-service-v1-for-other-systems.md) | Service routes `/service/v1/...` for other systems, with roles `reconciliation.read` and `reconciliation.resolve` | Accepted |
| [0009](0009-resolving-exception-requires-ledger-show.md) | Resolving an exception requires the ledger to show the adjustment, and consumes the settlement's open item | Accepted |
| [0010](0010-one-tenant-per-deployment-recon-tenant.md) | One tenant per deployment (`RECON_TENANT`) | Accepted (limitation) |
| [0011](0011-dead-letters-are-confirmed-against-store.md) | Dead letters are confirmed against the store before they are replayed | Accepted |
| [0012](0012-aws-is-reference-deployment-google-cloud-is.md) | AWS is the reference deployment; Google Cloud is a second binding of the same code | Accepted |
