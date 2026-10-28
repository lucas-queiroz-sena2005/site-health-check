# Track Specification: evaluator_refactor_and_sql_optimization

## Overview
This track addresses the critical performance bottleneck identified in ADR 0024, where scanning a `/16` network (65,536 targets) finishes in seconds in the standalone engine but takes an eternity (15+ minutes or fails) when executed through the API.

The track refactors the API ingestion layer and the post-scan evaluation pipeline according to two architectural pillars:
1. **Micro-Batched Ingestion & Zero-Cost Streaming**: Replace per-line synchronous SQLite transactions with buffered micro-batches (500 items / 100ms) and bypass writing transient void hosts to the database when `prune_void_hosts` is true.
2. **Relational Pushdown & Functional Core Decomposition**: Decompose the 371-line `evaluator.py` into pure domain decision rules (`evaluator_rules.py`) and push set-based operations (ghost detection, cascading pruning, metrics grouping) down into the SQLite query planner.

---

## Functional Requirements

### FR-1: High-Throughput Micro-Batched Ingestion (`runner.py`)
- Ingestion of engine `stdout` NDJSON deltas must buffer incoming parsed deltas in memory.
- Ingestion must flush batches to SQLite when the batch size reaches 500 items OR after a 100ms idle window, whichever occurs first.
- A final batch flush must always occur on engine EOF or process termination.
- All upserts within a batch must execute within a single SQLite transaction using `PRAGMA synchronous = NORMAL`.

### FR-2: Stream Void Bypass for /16 Scale
- When `prune_void_hosts` is `True` (default):
  - Prior to or at scan start, load the set of historical active IP addresses (`historical_active_ips`) within the `ghost_window` (a lightweight query returning tens to hundreds of IPs).
  - Deltas with no open ports whose IP is NOT in `historical_active_ips` are not written to SQLite; an in-memory atomic counter tracks void hosts.
  - Deltas with open ports or candidate ghost IPs are persisted via batch upsert.
- When `prune_void_hosts` is `False`, all deltas are batch-upserted to SQLite.

### FR-3: Functional Core Rule Engine (`evaluator_rules.py`)
- Extract pure business logic from `evaluator.py` into independent pure functions:
  - `evaluate_http_check(status_code: int | None) -> tuple[str, str | None]`
  - `evaluate_tls_cert(valid: bool, expires_in_days: int, protocol_version: str | None, tls_warning_days: int) -> list[str]`
  - `evaluate_port_status(tcp_status: str, check_statuses: list[str], tls_findings: list[str], is_ghost: bool) -> tuple[str, list[str]]`
  - `evaluate_host_status(open_port_count: int, is_ghost: bool, port_statuses: list[str], has_error_tcp: bool, has_ghost_port: bool) -> tuple[str, list[str]]`
- Zero database imports or side-effects in `evaluator_rules.py`.

### FR-4: Relational Pushdown & Set-Based SQL Post-Processing (`evaluator.py`)
- Eliminate $N+1$ query traps by loading required entities with eager relationship options (`selectinload`).
- Eliminate Python list parameter passing (`.in_(65000_items)`) to avoid SQLite `SQLITE_MAX_VARIABLE_NUMBER` limits:
  - Ghost detection must use SQL subqueries joining historical completed runs.
  - Pruning must use SQL set-based `DELETE` with cascading constraints or subqueries.
- Calculate summary metrics (`active`, `warning`, `failed`, `ghost`, `void`, `service_count`, `http_check_count`) via SQL aggregations (`GROUP BY` and `COUNT()`).

---

## Non-Functional Requirements & Performance Targets
- **Throughput Target**: Ingest and process a synthetic `/16` scan (65,536 IPs, 99% void) in **under 5 seconds** through the API runner.
- **Database Safety**: Memory usage during ingestion and evaluation must stay strictly bounded ($< 100\text{ MB}$).
- **Contract Compatibility**: Preserve 100% of the existing REST API responses, SSE event formats, finding codes, and test assertions.

---

## Acceptance Criteria
- [ ] All 116+ existing backend unit and integration tests pass without regression.
- [ ] New unit tests achieve 100% test coverage on `evaluator_rules.py`.
- [ ] Synthetic `/16` benchmark finishes ingestion, evaluation, and metrics calculation in $< 5$ seconds without `OperationalError: too many SQL variables`.
- [ ] Pipe buffer between engine and API never blocks under high delta emission rates.
