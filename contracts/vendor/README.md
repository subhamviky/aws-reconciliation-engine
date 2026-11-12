# Vendored contracts (consumer copies)

| File | Owner | Source of truth |
|---|---|---|
| `settlement-event.v1.schema.json` | financial-settlement-platform | `contracts/events/settlement-event.v1.schema.json` on its `main` |

This repository consumes the settlement event feed; it never edits the schema here.
The CI job `contract-drift` compares this copy with the owner's `main` and fails on
any difference, so a change in the producer is noticed by the consumer the same day.
To take a new version: copy the owner's file over this one, run the tests, commit.