# ADR 0009: Resolving an exception requires the ledger to show the adjustment, and consumes the settlement's open item

- **Status:** Accepted
- **Date:** 2026-11 (GCP-02 Phase A and the fix in Phase B)
- **Deciders:** repository owner

## Context

The GenAI assistant posts an approved write-off to the ledger directly; reconciliation must close the exception without trusting the claim.

## Options considered

A) Close on request. B) `resolve_with_adjustment` closes the exception only if the ledger holds an adjustment with that id whose reference names the bank line, and then consumes the settlement's open item.

## Decision

B. The second half was a defect fix: before it, closed exceptions left their open items OPEN (platform review 0003).

## Consequences

No system believes another's claim. Existing stale items were closed by a one-off dry-run-first script.
