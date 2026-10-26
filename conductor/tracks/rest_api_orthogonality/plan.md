# Implementation Plan: Orthogonal REST API for the 3 Tables & IP Drawer (`rest_api_orthogonality`)

## Phase 1: DB-Agnostic Sort Key, Pruning Toggles & Evaluator Summary Counters (TDD) [checkpoint: d2102c2]
- [x] Task: Write failing unit tests for `ip_sort_key`, finalization pruning toggles, and summary counters (Red Phase) 8dd6d95
  - [x] Add unit tests in `api/tests/test_models.py` (and `test_database.py`) verifying `HostState.ip_sort_key` calculation for IPv4 and IPv6-mapped hex strings
  - [x] Add unit tests in `api/tests/test_api_runner.py` asserting `_finalize_run` prunes void hosts when `prune_void_hosts=True` and routine closed ports when `prune_closed_ports=True`, preserving ghost ports
  - [x] Add unit tests in `api/tests/test_evaluator.py` asserting `evaluate_scan_run()` calculates and populates `service_count` and `http_check_count` in `metrics_json["summary"]`
- [x] Task: Implement `ip_sort_key`, pruning toggles, and evaluator summary counters (Green & Refactor Phase) d2102c2
  - [x] Add `ip_sort_key` column to `HostState` and add `prune_void_hosts` and `prune_closed_ports` to `ExecutionConfig` in `api/src/api/models.py`
  - [x] Update `_upsert_delta_sync` and `_finalize_run` in `api/src/api/services/runner.py` to compute `ip_sort_key` and execute conditional pruning
  - [x] Update `evaluate_scan_run()` in `api/src/api/services/evaluator.py` to record `service_count` and `http_check_count` in `metrics_json["summary"]`
  - [x] Verify all tests pass in `api/tests/`
- [x] Task: Phase Verification & Checkpoint (Refer to `workflow.md`) d2102c2

---

## Phase 2: Dedicated Orthogonal Table Endpoints & DTOs (Hosts, Services, Checks) (TDD) [checkpoint: f0dfe98]
- [x] Task: Write failing tests for `/hosts`, `/services`, `/checks` and query filter engine (Red Phase) 2b9cb33
  - [x] Add tests in `api/tests/test_api_runs_tables.py` for `GET /api/runs/{id}/hosts` verifying `Page[HostRowDTO]` structure, field values, and pagination
  - [x] Add tests for `GET /api/runs/{id}/services` verifying `Page[ServiceRowDTO]`, open services + ghost port inclusion, and `include_closed=true` parameter
  - [x] Add tests for `GET /api/runs/{id}/checks` verifying `Page[HttpCheckRowDTO]` and field mappings
  - [x] Add tests for `TableQueryParams`: deep search `q` across IP/domains/issuer/findings, `ip` prefix, multi-status `status=warning,failed`, `port`, `finding`, `sort_by` with `ip_sort_key` and `depth`, and `.nulls_last()`
- [x] Task: Implement DTOs, query filter engine, and table endpoints (Green & Refactor Phase) f0dfe98
  - [x] Create Pydantic DTO models (`Page[T]`, `HostRowDTO`, `ServiceRowDTO`, `HttpCheckRowDTO`) and `TableQueryParams` dependency in `api/src/api/schemas/tables.py` and `api/src/api/schemas/common.py`
  - [x] Implement `GET /api/runs/{id}/hosts` with SQL pagination and deep search
  - [x] Implement `GET /api/runs/{id}/services` with open/ghost filtering and `include_closed` flag
  - [x] Implement `GET /api/runs/{id}/checks` with domain and routing check filtering
  - [x] Verify all table tests pass in `api/tests/test_api_runs_tables.py`
- [x] Task: Phase Verification & Checkpoint (Refer to `workflow.md`) f0dfe98

---

## Phase 3: Dedicated On-Demand IP Detail Drawer Endpoint (TDD) [checkpoint: 92f29ae]
- [x] Task: Write failing unit tests for the IP Detail Drawer endpoint (Red Phase) 4ede254
  - [x] Add tests in `api/tests/test_api_runs_tables.py` asserting `GET /api/runs/{id}/hosts/{ip}` returns `HostDetailDTO` with discovery lineage, full services list with TLS certificates, HTTP checks, and deduplicated SANs
  - [x] Add tests verifying 404 behavior for non-existent run ID or IP address
- [x] Task: Implement IP Detail Drawer endpoint in `api/src/api/routers/runs.py` (Green & Refactor Phase) 92f29ae
  - [x] Define `HostDetailDTO` schema including nested service details, HTTP checks, and unique SAN list in `api/src/api/schemas/tables.py`
  - [x] Implement `GET /api/runs/{id}/hosts/{ip}` route handler in `api/src/api/routers/runs.py`
  - [x] Verify drawer unit tests pass
- [x] Task: Phase Verification & Checkpoint (Refer to `workflow.md`) 92f29ae

---

## Phase 4: Run Launch Consolidation, Idempotent Alerts & Legacy Cleanup (TDD) [checkpoint: 5cd0f8c]
- [x] Task: Write failing unit tests for unified launch, `PATCH /scans/{id}`, and webhook links (Red Phase) 60a8a81
  - [x] Add tests in `api/tests/test_api_runs.py` for `POST /api/runs` supporting both ad-hoc execution configs and `scan_id` schedule loading
  - [x] Add tests in `api/tests/test_api_scans.py` for `PATCH /api/scans/{id}` updating `alerts_muted` and schedule fields
  - [x] Add tests in `api/tests/test_alert_service.py` asserting webhook notification cards link to dashboard and do not include state-mutating GET mute URLs
- [x] Task: Implement unified launch, `PATCH /scans/{id}`, and remove legacy routes (Green & Refactor Phase) 5cd0f8c
  - [x] Consolidate run creation into `POST /api/runs` in `api/src/api/routers/runs.py`
  - [x] Implement `PATCH /api/scans/{id}` in `api/src/api/routers/scans.py` and delete HTML `GET /api/scans/{id}/alerts/mute` & `/unmute`
  - [x] Update webhook builders in `api/src/api/services/alerts.py` to point action links to `{app_base_url}/scheduled-runs`
  - [x] Delete `api/src/api/routers/results.py` and `api/src/api/services/aggregation.py` (preserving `GET /api/runs/{id}/results` bridge)
  - [x] Update frontend callers in `LiveScanPage.tsx` and `ScheduledScansPage.tsx` to use `POST /api/runs` and `PATCH /api/scans/{id}`
- [x] Task: Phase Verification & Checkpoint (Refer to `workflow.md`) 5cd0f8c

---

## Phase 5: Full Regression Testing & End-to-End System Verification [checkpoint: 3457081]
- [x] Task: Comprehensive test suite verification and regression testing 3457081
  - [x] Execute full pytest test suite across `api/tests/` and `engine/tests/`
  - [x] Verify OpenAPI documentation and JSON schema generation (`/openapi.json`) for all new endpoints
  - [x] Verify manual scan launch, live SSE log streaming, table pagination, drawer inspection, and alert muting end-to-end
- [x] Task: Phase Verification & Checkpoint (Refer to `workflow.md`) 3457081

---

## Phase 6: Review Fixes & Base Model Simplifications (TDD)
- [ ] Task: Write failing unit tests for `EntityStatus` (`void`/`ghost`), unified evaluator pruning, `status=active` normalization, and SQLite `ip_sort_key` migration (Red Phase)
  - [ ] Add unit tests in `api/tests/test_evaluator.py` asserting routine closed ports receive `status == "void"`, historically open closed ports receive `status == "ghost"` (with `HOST_GHOST`), and inactive non-ghost hosts receive `status == "void"`
  - [ ] Add unit tests in `api/tests/test_api_runs_tables.py` verifying that when `prune_closed_ports=False`, `evaluate_scan_run()` + `GET /api/runs/{id}/services` (default `include_closed=false`) excludes `status == "void"` ports so `total == summary["service_count"]`, and `status=active` filter normalizes to `"ok"` across `/hosts`, `/services`, and `/checks`
  - [ ] Add unit tests in `api/tests/test_database.py` asserting `init_db()` migrates legacy `host_states` tables by adding `ip_sort_key`, and `compute_ip_sort_key()` is shared across `models.py` and `runner.py`
  - [ ] Add unit tests in `api/tests/test_api_runs_tables.py` verifying sorting by all DTO columns (`tls_valid`, `san_count`, `http_check_count`, `redirects_to_url`, `server_header`, `finding_code`)
- [ ] Task: Implement `EntityStatus`, unified evaluator pruning, `compute_ip_sort_key`, and `TableQueryParams` helpers (Green & Refactor Phase)
  - [ ] Define `EntityStatus(str, Enum)` (`ok`, `warning`, `failed`, `ghost`, `void`) and `compute_ip_sort_key(ip: str)` in `api/src/api/models.py`, and add `"ip_sort_key"` to `new_host_cols` in `api/src/api/database.py`
  - [ ] Consolidate historical ghost-window lookup, `EntityStatus.VOID` / `EntityStatus.GHOST` assignment, and conditional `prune_void_hosts` / `prune_closed_ports` deletion into `evaluate_scan_run()` in `api/src/api/services/evaluator.py`, removing the duplicated historical query and classification loop from `_finalize_run()` in `api/src/api/services/runner.py`
  - [ ] Add `apply_status_filter()` (normalizing `"active"` to `"ok"`) and `apply_sort_and_paginate()` methods to `TableQueryParams` in `api/src/api/schemas/tables.py`, and refactor `get_run_hosts`, `get_run_services` (`WHERE status != 'void'`), and `get_run_checks` in `api/src/api/routers/runs.py`
  - [ ] Remove redundant `POST /api/scans/{id}/alerts/mute` & `/unmute` routes and unused imports in `api/src/api/routers/scans.py`
  - [ ] Verify all automated tests and live range checks pass
- [ ] Task: Phase Verification & Checkpoint (Refer to `workflow.md`)
