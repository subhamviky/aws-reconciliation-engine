# Onboarding

Read: `README.md`, the [solution overview](solution-overview.md), the design document sections 4, 8 and 10, [ADRs](../adr/README.md) 1, 2, 5, 9.

Run locally:

```bash
cd reconciliation-service && poetry install && poetry run pytest -q     # DynamoDB and SQS mocked by moto
RECON_STATE_BACKEND=firestore poetry run pytest -q                       # needs the Firestore emulator
```

Map: `src/reconciliation_service/` (`recon_service.py`, `matcher`, repositories, `routers/`, `agents/`, `lambda_entry.py`), `contracts/`, `reconciliation-service/infra` (AWS) and `infra/gcp`.

Working agreements: one concern per branch; CI green to merge; a regression test for every bug (see review 0003); an ADR for decisions worth explaining; never real data; deploy and scenario workflows live in the assistant repository ([release process](https://github.com/subhamviky/enterprise-finance-genai-assistant/blob/main/docs/engineering/operations/release-process.md)).
