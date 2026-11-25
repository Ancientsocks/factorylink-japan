# ADR-003: Organisation-scoped records

- Status: Accepted with production follow-up
- Date: 2026-11-03

## Decision
Each user is associated with an organisation. API handlers scope tenant records to the organisation established by authentication. Supplier access is further constrained to the supplier organisation linked from its purchase orders and documents.

## Consequences
API access tests must include cross-tenant denial cases. PostgreSQL Row-Level Security and an independent access-control review remain required before production; application filters alone are not a formal database security boundary.
