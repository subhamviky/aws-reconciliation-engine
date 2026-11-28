# ADR 0007: A statement on Google Cloud answers QUEUED; the outcome is read from the line

- **Status:** Accepted
- **Date:** 2026-11 (GCP-01)
- **Deciders:** repository owner

## Context

On Cloud Run, bank lines cross Pub/Sub and are processed by push delivery, not inline.

## Options considered

A) Process inline. B) Publish to `recon-bank-lines`; `PubSubPushDelivery` feeds the same `IdempotentConsumer`; the caller polls `GET /service/v1/lines/{line_id}`.

## Decision

B, with a dead-letter topic after repeated failures and a scheduled job that pulls it.

## Consequences

No always-on worker. Callers that need the result must poll (G-7); the cloud scenario polls for up to two minutes.
