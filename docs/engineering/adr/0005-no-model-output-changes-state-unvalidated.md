# ADR 0005: No model output changes state unvalidated; a proposal is validated before it is stored and again before it executes

- **Status:** Accepted
- **Date:** 2026 (completed project)
- **Deciders:** repository owner

## Context

The triage agent proposes what to do with an exception; a model can be wrong or manipulated.

## Options considered

A) Execute the proposal. B) `ReconciliationService.validate` checks it when it is stored and again at `accept`; a refused proposal is recorded with its reason and replaced by a remittance request.

## Decision

B (invariant I-5, business rules BR-10 to BR-12). A model proposal beyond the write-off limit is refused by `validate`.

## Consequences

The agent can only suggest. A human or service must accept, and acceptance re-validates against current data.
