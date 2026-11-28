# SLOs: reconciliation-service

Defined once for the platform in [the assistant repository](https://github.com/subhamviky/enterprise-finance-genai-assistant/blob/main/docs/engineering/operations/slo-and-error-budget.md) (`landscape/observability`). Here: 99% of requests not 5xx and 95% within 1 s over 28 days (no model is in the request path of the API; the triage agent runs in the consumer). Fast-burn alert on each. Traffic is a few dozen requests per scenario run, so the percentages swing; they show the mechanism.

Reconciliation-specific signals worth watching (not objectives): the number of open items per account (a growing number means items are not being consumed, review 0003), the dead-letter subscription depth, and the ledger-retry backlog (PENDING postings).
