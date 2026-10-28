# Implementation Plan: evaluator_refactor_and_sql_optimization

## Phase 1: ORM Lazy-Load Hygiene, SQLite Pragmas & Micro-Batched Ingestion (TDD) [checkpoint: fb1f30f]
Eliminate unconditional `lazy="selectin"` cascades on `ScanRun`/`HostState`, configure `PRAGMA synchronous=NORMAL`, and replace per-line synchronous commits with in-batch coalescing and bulk SQLite upserts.

- [x] Task: Write failing TDD tests in `api/tests/test_database.py` and `api/tests/test_api_runner.py` [aec2f54]
  - [x] `PRAGMA synchronous=NORMAL` verification.
  - [x] `session.get(ScanRun, id)` not triggering `SELECT` queries on `host_states` or `port_states`.
  - [x] `_bulk_upsert_deltas_sync` coalescing multiple deltas for the same IP within a single batch (set-union of `resolved_domains` and `discovered_from`, sticky `"open"` TCP status, preserved `subrun_id`).
  - [x] `_ingest_stdout` flushing batches on size threshold (500) and on EOF.
- [x] Task: Update `api/src/api/database.py` to set `PRAGMA synchronous=NORMAL;` and `api/src/api/models.py` to remove unconditional `"lazy": "selectin"` (adding explicit `selectinload` in `get_run_host_detail` in `runs.py`). [f31b566]
- [x] Task: Implement `_bulk_upsert_deltas_sync` and micro-batched `_ingest_stdout` in `api/src/api/services/runner.py`, keeping `_upsert_delta_sync` as a wrapper and using `select(func.count())` in `_finalize_run`. [fb1f30f]
- [x] Task: Phase Verification & Checkpoint (Refer to workflow.md). [fb1f30f]

---

## Phase 2: Functional Core Rule Engine Extraction (TDD) [checkpoint: d20759c]
Extract pure, deterministic evaluation rules into `api/src/api/services/evaluator_rules.py` with zero database dependencies.

- [x] Task: Write failing TDD unit tests in `api/tests/test_evaluator_rules.py` covering all branch combinations for: [7833f22]
  - [x] `evaluate_http_check` (2xx/3xx OK, 4xx WARNING, 5xx FAILED, None ERROR).
  - [x] `evaluate_tls_cert` (invalid, expired, expiring soon within threshold, healthy, deprecated TLS versions SSLv2/SSLv3/TLSv1.0/TLSv1.1 vs TLSv1.2/TLSv1.3).
  - [x] `evaluate_port` (closed routine void, closed historical ghost, error TCP, open healthy/warning/failed).
  - [x] `evaluate_host_status` (open ports rollup, ghost port warning rollup, error TCP failure rollup, 0 open ports ghost vs void).
- [x] Task: Implement `api/src/api/services/evaluator_rules.py` to pass all unit tests. [d20759c]
- [x] Task: Phase Verification & Checkpoint (Refer to workflow.md). [d20759c]

---

## Phase 3: Relational Pushdown & Set-Based Evaluator Refactor (TDD)
Refactor `api/src/api/services/evaluator.py` to delegate set operations to SQLite, use `evaluator_rules.py` for non-void candidate hosts, and eliminate SQLite variable-limit overflows.

- [ ] Task: Write failing TDD tests in `api/tests/test_evaluator.py` for:
  - [ ] Evaluating and pruning $> 35,000$ hosts in a single run (exceeding SQLite's 32,766 bind-parameter limit) without `OperationalError: too many SQL variables`.
  - [ ] Preserving `scanned_port_count` on active hosts after `prune_closed_ports=True` and preserving idempotency when `evaluate_scan_run` is called a second time after pruning.
  - [ ] Preserving open ports for future runs' historical ghost detection and preserving ghost hosts/ports for alerts and UI.
- [ ] Task: Refactor `api/src/api/services/evaluator.py`:
  - [ ] Use SQL subquery for historical active `(ip_address, port_number)` lookup (1 bind variable).
  - [ ] Implement set-based SQL fast-path for pure routine void hosts (count + direct subquery delete when `prune_void_hosts=True`, or bulk SQL `UPDATE` when `prune_void_hosts=False`).
  - [ ] Evaluate non-void / ghost-candidate hosts in chunks of 500 with `selectinload` and `evaluator_rules.py`.
  - [ ] Perform explicit bottom-up SQL subquery deletes (`HttpRoutingCheck` -> `TlsCertificate` -> `PortState` -> `HostState`) and SQL `GROUP BY` / `COUNT` summary aggregation.
- [ ] Task: Phase Verification & Checkpoint (Refer to workflow.md).

---

## Phase 4: End-to-End /16 Scale Benchmark & Full Suite Regression Check
Verify end-to-end `/16` performance and concurrency safety across the entire test suite.

- [ ] Task: Create `api/tests/test_scale_slash16.py` testing full `/16` (65,536 IPs) batched ingestion + evaluation + pruning + historical ghost diffing on a subsequent run, asserting completion in $< 5$ seconds.
- [ ] Task: Run full backend test suite (`.venv/bin/pytest`) and frontend test suite (`npm test`) and verify 100% pass rate.
- [ ] Task: Phase Verification & Checkpoint (Refer to workflow.md).
