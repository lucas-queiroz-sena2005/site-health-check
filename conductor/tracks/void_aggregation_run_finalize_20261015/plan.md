# Implementation Plan: Void Aggregation on Run Finalization

## Phase 1: Run-Finalization Void Aggregation & DB Pruning (Backend TDD)
- [ ] Task: Write failing unit and integration tests for finalization void aggregation and database pruning
  - [ ] Write test in `api/tests/test_api_runner.py` verifying that `_finalize_run` on a clean DB removes raw non-responsive hosts and inserts a synthetic `HostState` with `ip_address="Void (N)"`
  - [ ] Write test verifying that active hosts and ghost hosts are preserved in SQLite while void hosts are purged
  - [ ] Write test in `api/tests/test_alert_service.py` confirming `compute_run_summary` calculates accurate `void` count in `metrics_json["summary"]`
- [ ] Task: Implement void aggregation and pruning in `_finalize_run` and update `compute_run_summary`
  - [ ] Implement historical active IP resolution and void host classification in `api/src/api/services/runner.py`
  - [ ] Purge individual void `HostState` records (and cascading `PortState` records) and insert synthetic `HostState(ip_address="Void (N)", ...)`
  - [ ] Update `compute_run_summary` in `api/src/api/services/alerts.py` to record accurate void counts
- [ ] Task: Phase Verification & Checkpoint (Refer to workflow.md)

---

## Phase 2: Results Endpoint Consistency & Dynamic Fallback (Backend TDD)
- [ ] Task: Write failing tests for `GET /api/runs/{id}/results` returning aggregated void nodes
  - [ ] Write test in `api/tests/test_api_runs.py` verifying `GET /api/runs/{id}/results` returns synthetic `Void (N)` records for finalized runs
  - [ ] Write test verifying dynamic void aggregation fallback for in-progress or unfinalized runs
- [ ] Task: Update `get_run_results` in `api/src/api/routers/runs.py`
  - [ ] Ensure `get_run_results` cleanly returns the pruned synthetic void nodes and applies fallback aggregation if unfinalized hosts are present
  - [ ] Align query parameter handling (`ghost_window`) between `runs.py` and `results.py`
- [ ] Task: Phase Verification & Checkpoint (Refer to workflow.md)

---

## Phase 3: End-to-End System Verification & Regression Testing
- [ ] Task: Comprehensive test suite and container validation
  - [ ] Execute full pytest test suite across `api/tests` and `engine/tests`
  - [ ] Rebuild and update container images (`docker compose up -d --build`)
  - [ ] Verify manual scan scenario: launch `143.106.1.1/24`, verify database row count, and inspect `/api/runs/{id}/results` output
- [ ] Task: Phase Verification & Checkpoint (Refer to workflow.md)
