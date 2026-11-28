# ADR 0002: A match is one transaction: items conditioned on status OPEN and version, the line updated with them

- **Status:** Accepted
- **Date:** 2026 (completed project)
- **Deciders:** repository owner

## Context

Two lines racing for the same open item, or a crash mid-match, must never leave a line half-matched or an item matched twice.

## Options considered

A) Update item then line. B) One `TransactWriteItems` (DynamoDB) or one Firestore transaction containing every item update and the line update, each item conditioned on `status = OPEN AND version = v`.

## Decision

B (invariants I-1 and I-2; `ReconRepository.match`).

## Consequences

The losing line fails its condition and becomes an exception with candidates. A transaction's item limit bounds how many items one match can touch.
