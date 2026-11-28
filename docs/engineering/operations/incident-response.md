# Incident response: reconciliation-service

Severity, roles and the first ten minutes: [platform page](https://github.com/subhamviky/enterprise-finance-genai-assistant/blob/main/docs/engineering/operations/incident-response.md). Symptoms specific here:

| Symptom | Likely cause | Check | Action |
|---|---|---|---|
| A statement stays `QUEUED` | Pub/Sub push or the consumer is failing | `GET /service/v1/lines/{line_id}`; the subscription and its dead-letter | restore push settings; `POST /api/v1/...` is not the fix: wait for redelivery or run the scheduled job |
| The assistant cannot find the current settlement as a candidate | stale open items crowd out the current one (review 0003) | open items per account | run the ops action `close-stale-open-items` (dry run first); confirm resolve consumes the item |
| Exception closed but no adjustment in the ledger | should not happen (R5) | the adjustment id and its reference | SEV-2: reopen, check `resolve_with_adjustment` |
| Adjustment PENDING for long | the ledger is down or refusing | settlement health; the ledger-retry lease | wait for the schedule or `POST /api/v1/ledger/retry`; same key, so safe |
| Dead letters accumulate | poison lines | the DLQ messages | `reconcile` confirms what took effect and replays the rest |
| 409 on accept | a concurrent change | the exception's state | re-read and decide again |
