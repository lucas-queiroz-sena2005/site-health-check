# 2. Stateless Isolation for Job Targets

Date: 2026-08-26

## Status

Accepted

## Context

During Phase 2 (FastAPI + SQLite MVP), a user might submit multiple `Job` requests that target the exact same IPs, or target hierarchical subsets (e.g., scanning `professors` which overlaps with `ml-professors`). If both Jobs run simultaneously, the system will generate duplicate `Task`s for the same IP addresses. 

We had to decide whether the API or Dispatcher should attempt to deduplicate these tasks, coalesce them in the database, or use a caching layer to prevent redundant network probes.

## Decision

We will use **Stateless Isolation** for all Jobs and Tasks. 
- The API will not attempt to deduplicate or cache incoming Jobs. Parsing is done fresh on every request.
- The Dispatcher/Scanner will not attempt to coalesce overlapping Tasks or maintain a cooldown cache (like Redis). If two Jobs request a scan of `1.1.1.1` simultaneously, the engine will perform the network probes twice.

## Consequences

*   **Positive:** The data model and database interaction remain extremely simple. We avoid complex SQL race conditions (coalescing) and external dependencies (Redis/memcached).
*   **Positive:** Prometheus handles the grouping naturally via labels, avoiding high-cardinality anti-patterns.
*   **Negative:** Wasted CPU and network bandwidth for perfectly overlapping schedules. Given that this is a synthetic prober in an MVP state, the extra TLS handshakes are considered an acceptable trade-off for architectural simplicity.
