# Cloud-Native Payment Reconciliation Engine

> `main` is built by **consuming** the E2A framework family: the AI-DLC pipeline scaffolds the
> service (P0 + G2C + A2C), matching runs on governed Capability-Oriented DSA calls, and an E2A
> agent proposes resolutions for exceptions that deterministic rules authorize, execute and confirm.

| Service | Stack | Role |
|---|---|---|
| `reconciliation-service` | Python 3.12, FastAPI on AWS Lambda (Mangum), DynamoDB, SQS + DLQ, EventBridge | Matches bank-statement lines against completed settlements (exact, FIFO, many-to-one), clusters duplicate payments, triages exceptions |

Infrastructure is Terraform, tested with a mock provider and applied to a local moto server in CI
(`reconciliation-ci`). Requirements and the step-by-step guide live in the private hub (`reconciliation/`).

## Branches and tags

| Branch / tag | Purpose |
|---|---|
| `main` | Framework-consumption build. |
| `spike/v1-original` · tag `spike-v1` | Snapshot of the original spike (Phase 1 on AWS, Phase 2 LangGraph + Bedrock). Frozen. |
| `aidlc/reconciliation-service` | The untouched AI-DLC scaffold, as generated. |

## Framework family

[E2A](https://github.com/subhamviky/e2a-framework) ·
[A2C · G2C · P0](https://github.com/subhamviky/a2c-framework) ·
[Capability-Oriented DSA](https://github.com/subhamviky/capability-oriented-dsa)