# ADR 0011: Dead letters are confirmed against the store before they are replayed

- **Status:** Accepted
- **Date:** 2026 (completed project)
- **Deciders:** repository owner

## Context

A message in the DLQ may already have taken effect (a crash after the commit).

## Options considered

A) Replay everything. B) `reconcile` checks the store: remove the dead letter if it took effect, replay if not.

## Decision

B (`BankLineConsumer.reconcile`; the scheduled run also pulls the dead-letter subscription on Google Cloud).

## Consequences

No duplicate effect from replay; some dead letters need a human decision.
