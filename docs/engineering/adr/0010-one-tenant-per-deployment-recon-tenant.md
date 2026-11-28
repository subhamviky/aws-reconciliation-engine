# ADR 0010: One tenant per deployment (`RECON_TENANT`)

- **Status:** Accepted (limitation)
- **Date:** 2026 (completed project)
- **Deciders:** repository owner

## Context

A multi-tenant reconciliation engine was out of scope for the demonstration.

## Options considered

A) Tenant on every key. B) One tenant per deployment, with open items per account.

## Decision

B.

## Consequences

A second customer on the live cloud needs this service made multi-tenant (platform gap G-10).
