# Implementation Plan: Database Normalization & Backend Evaluation Pipeline (`db_and_evaluation_pipeline`)

## Phase 1: SQLite Hardening, Model Normalization & TargetGroup Retirement (TDD) [checkpoint: 7c556d8]
- [x] Task: Write failing unit tests for schema changes, WAL configuration, foreign key cascades, and direct `Scan.targets` (Red Phase) 0113e7f
  - [x] Test SQLite PRAGMA configuration (`journal_mode=WAL`, `foreign_keys=ON`, `busy_timeout=5000`) in `api/tests/test_database.py`
  - [x] Test `UniqueConstraint("port_state_id")` enforcement on `TlsCertificate`
  - [x] Test direct `Scan.targets` JSON storage and absence of `TargetGroup` / `ScanTargetGroupLink`
  - [x] Test removal of `@model_serializer` on `HostState` and `PortState`, ensuring standard attribute and relationship access
- [x] Task: Implement model updates, SQLite PRAGMAs, and scan router adjustments (Green & Refactor Phase) 05df7e8
  - [x] Configure engine event listeners in `api/src/api/database.py` for WAL mode, foreign keys, and busy timeout
  - [x] Drop `TargetGroup` & `ScanTargetGroupLink`, add `targets` JSON column to `Scan`, add SQLite migration in `init_db()`
  - [x] Refactor `api/src/api/routers/scans.py` to create, read, and serialize `targets` directly on `Scan`
  - [x] Remove `@model_serializer` and rename relationships (`ports`, `http_routing_checks`) in `api/src/api/models.py`
- [x] Task: Phase Verification & Checkpoint (Refer to `workflow.md`) 7c556d8

---

## Phase 2: HostState Lineage Set-Union & Void Sentinel Purge (TDD)
- [x] Task: Write failing tests for set-union domain/lineage storage and complete removal of Void sentinels (Red Phase) 0a83a50
  - [x] Test `runner.py` delta ingestion merging `resolved_domains` and `discovered_from` without clobbering existing vhost probes
  - [x] Test that non-responsive targets never produce `"Void (X)"` sentinel strings in SQLite or API responses
  - [x] Test `depth` lineage inference from `discovered_from` (0 for root target, >= 1 for SAN/redirect hops)
- [x] Task: Implement `resolved_domains` / `discovered_from` and purge Void sentinels (Green & Refactor Phase) 88c5d9a
  - [x] Replace `metadata_resolved_from` on `HostState` with `resolved_domains: list[str]` and `discovered_from: list[str]`
  - [x] Update `_upsert_delta_sync` in `api/src/api/services/runner.py` to perform set-union on `resolved_domains` and `discovered_from`
  - [x] Eliminate all `ip_address.startswith("Void")` checks and synthetic node logic across `runner.py`, `aggregation.py`, and `alerts.py`
  - [x] Refactor legacy assertions in `api/tests/` that assert dictionary indexing or Void sentinel strings
- [ ] Task: Phase Verification & Checkpoint (Refer to `workflow.md`)

---

## Phase 3: Deterministic Backend Evaluation Pipeline (`evaluator.py`) (TDD)
- [ ] Task: Write failing tests for canonical finding codes, bottom-up rollups, and run evaluation (Red Phase)
  - [ ] Test canonical finding code generation (`TCP_CLOSED`, `TLS_INVALID`, `TLS_EXPIRED`, `TLS_EXPIRING_SOON`, `TLS_DEPRECATED_VERSION`, `HTTP_5XX`, `HTTP_4XX`, `HTTP_ERROR`, `HOST_GHOST`, `RUN_ABORTED`)
  - [ ] Test Level 1 HTTP check evaluation (`status`, `finding_code`)
  - [ ] Test Level 2 `PortState` rollups (`san_count`, `http_check_count`, `worst_http_status`, `finding_codes`, status `failed` if `HTTP_ERROR`)
  - [ ] Test Level 3 `HostState` rollups (`depth`, `vhost_count`, `open_port_count`, latency/tls/http rollups, host-level `status` and `finding_codes`)
  - [ ] Test end-to-end `evaluate_scan_run(scan_run_id, session)` execution on run completion
- [ ] Task: Implement `api/src/api/services/evaluator.py` and hook into run finalization (Green & Refactor Phase)
  - [ ] Add pre-computed columns to `HttpRoutingCheck`, `PortState`, and `HostState` in `api/src/api/models.py`
  - [ ] Implement bottom-up evaluation algorithms in `api/src/api/services/evaluator.py`
  - [ ] Hook `evaluate_scan_run` into `_finalize_run` in `api/src/api/services/runner.py` within an atomic transaction
- [ ] Task: Phase Verification & Checkpoint (Refer to `workflow.md`)

---

## Phase 4: Full Test Suite Migration & System Regression Verification
- [ ] Task: Update legacy test suite and verify end-to-end regression
  - [ ] Execute full pytest suite across `api/tests/` and `engine/tests/`
  - [ ] Clean up any remaining legacy fixtures or assertions expecting old serializer schemas
  - [ ] Verify database initialization and migrations across fresh and existing SQLite databases
- [ ] Task: Phase Verification & Checkpoint (Refer to `workflow.md`)
