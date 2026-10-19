# ADR 0005: Saved Views & Read-Time UI Filtering

## Context
We need to decide how search filters and target classifications interact with Job definitions, and how user UI view state (e.g., column selections, Ghost time windows, filters) is persisted.

## Decision

1. **Read-Time Filtering (Universal Jobs)**:
   Job definitions specify the full network target space (e.g., `10.0.0.0/16`). Jobs do NOT filter targets during scanning. Scanning is always universal across the defined scope. All filters (`class:professors`, `status:down`, `tls:expiring`) are applied strictly at read-time when querying the FastAPI backend.

2. **Saved Views in SQLite**:
   UI view states, active filter queries, and custom layouts can be persisted as "Saved Views" in SQLite. This allows SRE team members to share exact dashboard view states via permalinks/URLs.

## Consequences
- **Pros**: The scanning engine remains fast and simple. Jobs don't need complex sub-filtering logic.
- **Cons**: The database must store full scan results, relying on efficient SQLite indexes for read-time filtering performance.
