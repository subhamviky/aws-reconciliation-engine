# Data classification: reconciliation-service

All data is synthetic ([platform rule](https://github.com/subhamviky/enterprise-finance-genai-assistant/blob/main/docs/engineering/security/data-classification.md)). If it were real:

| Data | Where | Classification | Retention here | Protection |
|---|---|---|---|---|
| Bank statement lines (amount, payer account, reference) | DynamoDB (AWS) or Firestore (GCP) | Restricted (financial) | until teardown | private service; tenant on every key |
| Open items (expected cash per settlement) | same store | Confidential | until matched or consumed | conditional writes |
| Exception cases, the agent's proposal, the verdict | same store | Confidential | until teardown | audit trail of the decision |
| Idempotency claims, feed cursor, ledger-retry lease | same store | Internal | until teardown | |
| Queue and dead-letter messages | SQS or Pub/Sub | Restricted | 24 h retention on Pub/Sub | DLQ reviewed by `reconcile` |
| Logs | Cloud Logging / CloudWatch | Internal | default | ids and statuses only |

Handling: no real data; the triage model sees line and candidate facts only because they are synthetic.
