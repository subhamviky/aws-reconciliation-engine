# ADR 0003: One open item per settlement and one line per line_id, by conditional puts

- **Status:** Accepted
- **Date:** 2026 (completed project)
- **Deciders:** repository owner

## Context

A settlement event delivered twice must create one expected-cash item; a line sent twice must be one line.

## Options considered

A) Read before write. B) `attribute_not_exists(pk)` conditional puts.

## Decision

B (invariant I-3). The settlement feed cursor moves forward only, by a conditional put on the old position (I-4).

## Consequences

Duplicates are harmless on every path. Two pollers may fetch the same events; each item is created once.
