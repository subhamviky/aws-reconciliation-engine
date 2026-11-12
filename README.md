# Cloud-Native Payment Reconciliation Engine

> Proves that the cash the settlement platform says should arrive really arrived. Bank-statement
> lines are matched against completed settlements with deterministic, bounded algorithms; what
> cannot be matched becomes an exception that an AI agent triages and deterministic rules decide.

## From spike to frameworks to project

This repository went through three stages. Each one is kept, so the path can be followed.

| Stage | Where | What happened |
|---|---|---|
| **1. Architectural spike** | branch [`spike/v1-original`](https://github.com/subhamviky/aws-reconciliation-engine/tree/spike/v1-original) (tag `spike-v1`) | A serverless spike on AWS (API Gateway, Lambda, SQS, DynamoDB) testing idempotent asynchronous processing, with an agentic layer (LangGraph, Bedrock RAG) planned on top. The serverless patterns held; the open question was how an agent could act on financial records without being trusted with them. |
| **2. Frameworks** | [E2A](https://github.com/subhamviky/e2a-framework) · [A2C · G2C · P0](https://github.com/subhamviky/a2c-framework) · [Capability-Oriented DSA](https://github.com/subhamviky/capability-oriented-dsa) | The answer became E2A's rule (*probabilistic intelligence proposes; deterministic controls authorize, execute and confirm*); bounded, governed algorithms became Capability-Oriented DSA; scaffolding became the AI-DLC pipeline. |
| **3. Completed project** | **`main`** (this branch) | The spike rebuilt by **consuming** those frameworks: scaffolded by the AI-DLC pipeline, matching on governed DSA calls, exception triage on an E2A agent. |

### What changed between the spike and `main`

| In the spike | In `main` | Framework that made the difference |
|---|---|---|
| `POST /payments` with a status change | Real matching of bank lines against the settlement event feed: exact, FIFO, many-to-one, duplicate clusters | DSA `KNAPSACK_01`, bounded `SUBSETS` (truncation is AMBIGUOUS, never "no match"), `LOWER_BOUND`, `UNION_FIND` |
| Conditional locking per record | One DynamoDB transaction per match: every item OPEN at the version read, or nothing changes | E2A conditional commit |
| LangGraph + Bedrock (planned) | One E2A agent behind a simulated model; it only proposes, rules re-validate against current state, execution is conditional and confirmed | E2A `BaseAgent`, `SimulatedLLMService` |
| Not part of the spike | Accepted write-offs and refunds are posted to the settlement ledger exactly once (idempotency key per bank line, retried while pending) | E2A typed outcomes; settlement adjustments API |
| Deployed to one AWS region (ap-south-1) | Terraform tested with a mock provider and **applied to a local moto server in CI**, then smoke-tested through the real Lambda handler | A2C-generated AWS landing zone |

## The project

| Service | Stack | Role |
|---|---|---|
| `reconciliation-service` | Python 3.12, FastAPI on AWS Lambda (Mangum), DynamoDB, SQS + DLQ, EventBridge | Matches bank-statement lines against completed settlements, clusters duplicate payments, triages exceptions, posts accepted write-offs and refunds to the ledger |

**Its place in the landscape:** reads the event feed of [financial-settlement-platform](https://github.com/subhamviky/financial-settlement-platform) (its contract is vendored and checked for drift) and posts adjustments back to its ledger; [order-to-cash-agentic-ai](https://github.com/subhamviky/order-to-cash-agentic-ai) reports the open exceptions to finance users.

## Evidence

Verified in CI (`reconciliation-ci`) on every push: the test suite (DynamoDB and SQS mocked by moto), the contract drift check, Terraform `fmt`/`validate`/`test`, and `terraform apply` + smoke test + `destroy` against a moto server. The three projects also run together in the `landscape-demo` workflow of order-to-cash-agentic-ai. This is an architecture reference implementation: it has not been deployed to an AWS account, and it makes no production claims.

## Branches and tags

| Branch / tag | Purpose |
|---|---|
| `main` | The completed project, built on the framework family. |
| `spike/v1-original` · tag `spike-v1` | The architectural spike, frozen. `spike-v1` is the untouched snapshot. |
| `aidlc/reconciliation-service` | The scaffold exactly as the AI-DLC pipeline generated it. |
