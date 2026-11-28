# Teardown: reconciliation-service

Platform order and verification: [teardown](https://github.com/subhamviky/enterprise-finance-genai-assistant/blob/main/docs/engineering/operations/teardown-and-exit.md). From this repository: export the last scenario summary; `terraform destroy` in `reconciliation-service/infra/gcp` (Cloud Run, topics and subscriptions, scheduler job, service accounts, Firestore collections); delete the repository variables. The AWS stack needs no teardown: it was applied only to a local moto server.
