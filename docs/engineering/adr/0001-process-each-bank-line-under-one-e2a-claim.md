# ADR 0001: Process each bank line under one E2A claim with a resumable handler, however it arrives

- **Status:** Accepted
- **Date:** 2026 (completed project)
- **Deciders:** repository owner

## Context

A bank line can arrive by SQS, by HTTP or by replay, and the processing Lambda or Cloud Run instance can stop at any point.

## Options considered

A) Best-effort processing. B) E2A's `IdempotentConsumer` with a claim on `line_id` and a handler that resumes from the stored state.

## Decision

B (invariant I-8). A repeated delivery replays the stored outcome; two deliveries at once defer the second; an expired claim is taken over and finished.

## Consequences

Safe redelivery on every path. A line that can never succeed (bad JSON, invalid line, same id with different content) is dead-lettered at once with its reason.
