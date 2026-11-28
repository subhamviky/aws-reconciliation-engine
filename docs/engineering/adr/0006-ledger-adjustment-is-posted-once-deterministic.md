# ADR 0006: A ledger adjustment is posted once: a deterministic idempotency key and a lease for retries

- **Status:** Accepted
- **Date:** 2026 (completed project)
- **Deciders:** repository owner

## Context

Accepting an exception posts an adjustment to settlement-service; the ledger can be down, and two retry jobs can overlap.

## Options considered

A) Fire and forget. B) `Idempotency-Key: recon-<tenant>-<line_id>`, the decision stored with the posting PENDING when the ledger is down, retried by the schedule under the same key, and a lease `ledger-retry#<tenant>` so two retries never run at once.

## Decision

B (invariants I-6 and I-7).

## Consequences

The ledger absorbs the retries (it replays the key); at most one retry job posts at a time.
