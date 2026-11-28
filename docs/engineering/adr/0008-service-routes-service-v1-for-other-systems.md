# ADR 0008: Service routes `/service/v1/...` for other systems, with roles `reconciliation.read` and `reconciliation.resolve`

- **Status:** Accepted
- **Date:** 2026-11 (SI-01, GCP-01)
- **Deciders:** repository owner

## Context

O2C and the GenAI assistant need to read exceptions and lines; the user routes require a user token.

## Options considered

A) Reuse the user routes. B) Separate service routes: `GET /service/v1/exceptions`, `GET /service/v1/lines/{line_id}` (read), `POST /service/v1/exceptions/{line_id}/resolve` (resolve), each with its own grant.

## Decision

B. Callers are Google service accounts checked by Cloud Run IAM and mapped to grants by E2A.

## Consequences

Least privilege per caller: the assistant holds read and resolve, O2C read only.
