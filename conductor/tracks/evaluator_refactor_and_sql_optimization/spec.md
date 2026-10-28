# Track Specification: evaluator_refactor_and_sql_optimization

## Overview
This track resolves the `/16` API execution and evaluation bottlenecks identified in ADR 0024 while strictly preserving all historical ghost-detection invariants, multi-delta lineage merges, partial run abort safety, and SQLite concurrency guarantees.

---

## Functional Requirements

### FR-1: ORM Relationship Loading Hygiene & SQLite Pragmas (`models.py`, `database.py`)
- Remove unconditional `"lazy": "selectin"` from `ScanRun.hosts`, `HostState.ports`, `PortState.tls_certificate`, and `PortState.http_routing_checks` so routine queries (`session.get(ScanRun, id)`, `GET /api/runs`, `GET /api/runs/{id}/hosts`) do not recursively load the entire 65k-host object graph into RAM.
- Configure `PRAGMA synchronous = NORMAL;` alongside `PRAGMA journal_mode = WAL;` and `PRAGMA busy_timeout = 5000;` in `database.py`.

### FR-2: Micro-Batched Ingestion with In-Batch Delta Coalescing (`runner.py`)
- Buffer incoming engine `stdout` NDJSON deltas in `_ingest_stdout` and flush in micro-batches (every **500 deltas** or **100ms**, whichever comes first) with a guaranteed EOF flush.
- Implement `_bulk_upsert_deltas_sync(run_id, batch)`:
  - Coalesce multiple deltas for the same IP within a batch in memory (preserving set-union of `resolved_domains` and `discovered_from`, `subrun_id`, and sticky `"open"` TCP status).
  - Query existing `HostState` and `PortState` rows for the batch using a single bounded `SELECT ... WHERE id IN (...)` query per table.
  - Perform bulk `INSERT ... ON CONFLICT DO UPDATE` within a single SQLite transaction per batch.
  - Preserve `_upsert_delta_sync(run_id, ip, data)` as a backward-compatible wrapper delegating to `_bulk_upsert_deltas_sync(run_id, [(ip, data)])`.
- Do **not** drop void deltas during streaming so that multi-delta lineage merges, `total_targets_scanned`, `scanned_port_count`, and partial-run abort states remain 100% accurate.
- In `_finalize_run`, compute `initial_targets_count` via `select(func.count()).select_from(HostState).where(HostState.scan_run_id == run_id)` before pruning.

### FR-3: Functional Core Rule Engine (`evaluator_rules.py`)
- Extract pure, stateless evaluation functions with zero database dependencies:
  - `evaluate_http_check(status_code: int | None) -> tuple[str, str | None]`
  - `evaluate_tls_cert(valid: bool, expires_in_days: int, protocol_version: str | None, tls_warning_days: int) -> tuple[list[str], int | None]`
  - `evaluate_port(tcp_status: str, check_statuses: list[str], check_findings: list[str], tls_findings: list[str], was_historically_open: bool) -> tuple[str, list[str], bool]`
  - `evaluate_host_status(open_port_count: int, open_port_statuses: list[str], has_error_port: bool, has_ghost_port: bool, was_ip_historically_active: bool, initial_findings: list[str]) -> tuple[str, list[str]]`

### FR-4: Relational Pushdown & Set-Based Evaluator (`evaluator.py`)
- **Historical Active Query**: Replace `.where(col(HostState.ip_address).in_(host_ips))` (which fails on $>32,766$ IPs) with a SQL subquery `select(HostState.ip_address).where(HostState.scan_run_id == scan_run_id)`.
- **Set-Based Fast-Path for Pure Routine Void Hosts**:
  - Identify hosts in `scan_run_id` that have ports, have zero non-closed ports (`tcp_status != 'closed'`), have zero TLS/HTTP rows, and are not in `historical_active_ips`.
  - When `prune_void_hosts=True`, count and delete these pure void hosts and their ports via SQL subqueries without hydrating them into Python or updating them first.
  - When `prune_void_hosts=False`, update their status and rollups via set-based SQL `UPDATE` statements.
- **Chunked Eager Evaluation for Non-Void / Candidate Hosts**:
  - Load active, error, 0-port, and ghost-candidate hosts in chunks of 500 with explicit `selectinload` on `ports`, `tls_certificate`, and `http_routing_checks`.
  - Compute `scanned_port_count = max(host.scanned_port_count or 0, len(host.ports))` **before** pruning routine closed ports.
- **Explicit Bottom-Up Subquery Pruning**:
  - Delete child tables (`HttpRoutingCheck`, `TlsCertificate`, `PortState`, `HostState`) explicitly using SQL `IN (SELECT ...)` subqueries so pruning is 100% safe even when `PRAGMA foreign_keys` is `OFF` (such as in unit test fixtures) and never exceeds SQLite parameter limits.
  - Never prune open ports (needed by future runs for ghost detection) or ghost hosts/ports (needed by UI and alerts).

---

## Non-Functional Requirements & Acceptance Criteria
- [ ] Strict TDD execution (Red $\rightarrow$ Green $\rightarrow$ Refactor) for every phase.
- [ ] All 116+ existing backend tests and all frontend tests pass with zero regressions.
- [ ] Synthetic `/16` (65,536 IPs) ingestion + evaluation benchmark completes in $< 5$ seconds with zero `too many SQL variables` or `database is locked` errors.
