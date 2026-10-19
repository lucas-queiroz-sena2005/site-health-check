# Implementation Plan: Void Counting & DB Pruning on Run Finalization

## Phase 1: Run-Finalization Void Pruning & Metrics Calculation (Backend TDD)
- [x] Task: Write unit and integration tests for finalization void purging and database pruning (5a9d7b7, e8275af)
  - [x] Write test in `api/tests/test_api_runner.py` verifying that `_finalize_run` removes raw non-responsive hosts from SQLite table
  - [x] Write test verifying that active hosts and ghost hosts are preserved in SQLite while void hosts are purged
  - [x] Write test in `api/tests/test_alert_service.py` confirming `compute_run_summary` calculates accurate `void` count in `metrics_json["summary"]`
- [x] Task: Implement void purging in `_finalize_run` and update `compute_run_summary` (d4911ad, d09146f)
  - [x] Implement historical active IP resolution and void host classification in `api/src/api/services/runner.py`
  - [x] Purge individual void `HostState` records (and cascading `PortState` records) from DB without inserting synthetic nodes
  - [x] Update `compute_run_summary` in `api/src/api/services/alerts.py` to record accurate void counts
- [x] Task: Phase Verification & Checkpoint

---

## Phase 2: Void Alert Trigger, Results Endpoint Consistency & Dashboard UI
- [x] Task: Add Void Alert Trigger across backend and frontend (d09146f)
  - [x] Add `alert_on_void` to `AlertConfig` in `api/src/api/models.py` and frontend `types/index.ts`
  - [x] Evaluate `alert_on_void` in `evaluate_alert_triggers` and include void count in alert notifications
  - [x] Add toggle switch in `ScanConfigForm.tsx` and integrate with `ScheduledScansPage.tsx`
- [x] Task: Results Endpoint Consistency & Dashboard UI Integration (0071421)
  - [x] Ensure `get_run_results` in `api/src/api/routers/runs.py` always returns metadata with summary stats
  - [x] Remove `void` from global table filter buttons and filtering logic in `HostTablePage.tsx`
  - [x] Render `Void` count pill unconditionally in dashboard summary header and add void badges in `RenderTreeNode.tsx`
- [x] Task: Phase Verification & Checkpoint

---

## Phase 3: End-to-End System Verification & Regression Testing
- [x] Task: Comprehensive test suite and container validation
  - [x] Execute full pytest test suite across `api/tests` and `engine/tests` (58 passed)
  - [x] Rebuild and update container images (`podman-compose up -d --build`)
  - [x] Verify manual scan scenario: launch scans, verify database row count, and inspect `/api/runs/{id}/results` output
- [x] Task: Phase Verification & Checkpoint
