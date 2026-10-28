# Implementation Plan: evaluator_refactor_and_sql_optimization

## Phase 1: Database Pragmas & Micro-Batched Ingestion Buffer
Refactor SQLite connection pragmas and convert `runner.py` from synchronous single-line commits to an asynchronous micro-batched ingestion buffer with zero-cost void streaming.

- [ ] Task: Configure `PRAGMA synchronous=NORMAL;` in `api/src/api/database.py` alongside WAL mode.
- [ ] Task: Implement `_bulk_upsert_deltas_sync` in `runner.py` executing batch upserts in a single SQLite transaction.
- [ ] Task: Implement async batch buffering in `_ingest_stdout` with dynamic flush triggers (500 items or 100ms timeout) and guaranteed EOF flush.
- [ ] Task: Implement Stream Void Bypass when `prune_void_hosts` is True:
  - [ ] Query historical active IPs at run initialization.
  - [ ] Filter unassigned inactive IPs into in-memory `void_count` without disk write.
  - [ ] Batch-upsert responsive hosts and ghost candidates.
- [ ] Task: Unit & integration tests for batched ingestion and EOF flush.
- [ ] Task: Phase Verification & Checkpoint (Refer to workflow.md).

---

## Phase 2: Functional Core Rule Engine Decomposition
Decompose the domain logic from `evaluator.py` into pure functions in `evaluator_rules.py` following the Functional Core, Imperative Shell pattern.

- [ ] Task: Create `api/src/api/services/evaluator_rules.py` with pure functions:
  - [ ] `evaluate_http_check(status_code: int | None) -> tuple[str, str | None]`
  - [ ] `evaluate_tls_cert(valid: bool, expires_in_days: int, protocol_version: str | None, tls_warning_days: int) -> list[str]`
  - [ ] `evaluate_port_status(tcp_status: str, check_statuses: list[str], tls_findings: list[str], is_ghost: bool) -> tuple[str, list[str]]`
  - [ ] `evaluate_host_status(...) -> tuple[str, list[str]]`
- [ ] Task: Write comprehensive unit tests in `api/tests/test_evaluator_rules.py` covering all branch combinations and finding codes.
- [ ] Task: Phase Verification & Checkpoint (Refer to workflow.md).

---

## Phase 3: Relational Pushdown & Set-Based SQL Evaluator
Refactor the imperative shell in `evaluator.py` to push set-based queries down to SQLite, eliminate N+1 relationship loads, and eliminate parameter-overflow in `IN (...)` queries.

- [ ] Task: Add eager loading (`selectinload(HostState.ports).selectinload(PortState.http_routing_checks)`) to avoid lazy relationship SELECT queries.
- [ ] Task: Replace Python 65k-item `.in_(host_ips)` with set-based SQL subquery for historical ghost marking.
- [ ] Task: Replace Python in-memory list aggregations with SQL `GROUP BY` and `COUNT()` queries for summary metrics.
- [ ] Task: Replace Python `.in_(void_host_ids)` pruning with set-based SQL `DELETE` queries leveraging foreign key cascades.
- [ ] Task: Verify all existing tests in `api/tests/test_evaluator.py` pass without regression.
- [ ] Task: Phase Verification & Checkpoint (Refer to workflow.md).

---

## Phase 4: /16 Scale Verification & Benchmark
Verify the complete pipeline against a full synthetic `/16` network (65,536 IPs) to ensure sub-5-second completion and rock-solid memory bounds.

- [ ] Task: Create synthetic `/16` scale integration benchmark test in `api/tests/test_scale_slash16.py`.
- [ ] Task: Benchmark API runner completion time with 65,536 targets and verify no SQLite locks, pipe stalls, or parameter errors.
- [ ] Task: Run full backend test suite (`pytest`) and frontend test suite (`npm test`).
- [ ] Task: Phase Verification & Checkpoint (Refer to workflow.md).
