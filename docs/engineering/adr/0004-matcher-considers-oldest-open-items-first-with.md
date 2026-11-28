# ADR 0004: The matcher considers the oldest open items first, with a bounded subset search

- **Status:** Accepted
- **Date:** 2026 (completed project)
- **Deciders:** repository owner

## Context

Candidates must be tried in a defined order and the search for a combination of items must be bounded.

## Options considered

A) Newest first. B) Exact, then FIFO, then a bounded subset-sum (DSA `SUBSET_SUM`), with duplicate detection by DSA `GROUP_BY_KEYS`.

## Decision

B. `Matcher.decide`; nearest candidates by DSA `LOWER_BOUND` for exceptions.

## Consequences

Predictable behaviour and bounded work. A side effect found later: if open items are never consumed the oldest ones crowd out the current one (platform review 0003). `duplicate_of` reads every line of a tenant (G-5), a scale limit.
