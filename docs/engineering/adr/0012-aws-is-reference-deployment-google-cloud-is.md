# ADR 0012: AWS is the reference deployment; Google Cloud is a second binding of the same code

- **Status:** Accepted
- **Date:** 2026-11 (GCP-01)
- **Deciders:** repository owner

## Context

The engine was built on AWS (Lambda, DynamoDB, SQS, EventBridge) and later run on Google Cloud's free tier.

## Options considered

A) Fork. B) One codebase; the repository and delivery are bound by configuration (`RECON_STATE_BACKEND`, Firestore repository, Pub/Sub push).

## Decision

B. CI runs the whole suite on moto and again on the Firestore emulator, and applies the AWS stack to a moto server then destroys it.

## Consequences

No divergence; the AWS stack was never applied to a real account.
