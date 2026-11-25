# ADR-001: Modular monolith

- Status: Accepted
- Date: 2026-11-03

## Context
FactoryLink needs cohesive transactional flows across procurement, stock, production and quality. Splitting these into microservices would introduce distributed transactions and operational overhead before scale requires it.

## Decision
Use a modular FastAPI monolith backed by PostgreSQL. Background work is delegated to Celery only where asynchronous scheduling is useful.

## Consequences
Business transactions remain within one database transaction. Module boundaries remain logical and testable. Deploy and scale API and worker processes independently without separate business databases.
