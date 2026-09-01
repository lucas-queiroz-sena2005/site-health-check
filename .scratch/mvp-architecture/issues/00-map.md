---
labels: ["wayfinder:map"]
---

# Map: MVP Architecture Specification

## Destination

A finalized, build-ready architectural spec for the database structure, scheduling logic, and frontend UX of the `site-health-check` MVP.

## Notes

- **Domain:** Network Mapping & Synthetic Prober
- **Constraints/Preferences:** 
  - MVP will stick to SQLite.
  - Open internal tool (no user logins or RBAC).
  - Scheduling will use default cron expressions.
  - Target classifications/groupings must be flexible so the applying team can define their own tags.

## Decisions so far

- [01-database-schema.md](file:///home/crow/Projects/site-health-check/.scratch/mvp-architecture/issues/01-database-schema.md): SQLAlchemy schema defined with Junction Tables (Option 1) for M:N scheduling. Enforces governance via Immutable Snapshots, Soft Deletes, and Blast Radius limits.
- [02-frontend-ux.md](file:///home/crow/Projects/site-health-check/.scratch/mvp-architecture/issues/02-frontend-ux.md): Frontend specified as a global shell with a Hierarchical Table viewer (Topology DAG dropped for MVP). FastAPI handles Auto-Classification. SANs are pooled to prevent pollution.
- [03-api-endpoints.md](file:///home/crow/Projects/site-health-check/.scratch/mvp-architecture/issues/03-api-endpoints.md): FastAPI contract defined. Implements Schema-Driven dynamic forms, 3-in-1 Schedule creation, and WebSocket streaming for Live Operations logs.

## Not yet specified

- The exact payload format for passing tasks to the RabbitMQ Broker (Dispatcher -> Scanner).
- How the frontend DAG (Directed Acyclic Graph) will physically render (e.g., which graph library to use).
- Specific API filtering parameters (e.g., `?ghost_window=14d`).

## Out of scope

- Role-Based Access Control (RBAC) and user authentication.
- Transitioning to PostgreSQL (post-MVP).
