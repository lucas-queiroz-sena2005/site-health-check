# Implementation Plan: Reliability, Data Retention & Lifecycle Management (`reliability_and_lifecycle_management`)

## Phase 1: Engine File Descriptor Resilience (`Errno 24` Prevention) [checkpoint: 23ef3f1]
- [x] Task: Write unit tests for Engine FD resilience, DNS `OSError` handling, and `EMFILE` retry (`engine/tests/test_fd_resilience.py`) [e677d88]
    - [x] Test that `run_engine()` attempts to raise `RLIMIT_NOFILE` soft limit toward hard limit (up to `65535`) and clamps `workers_count` to `max(50, soft_limit - 250)` with a warning when the OS soft limit is constrained
    - [x] Test that `resolve_target()` in `network.py` eagerly imports `concurrent.futures.thread` and catches `OSError` (including `Errno 24`) without crashing the worker routine
    - [x] Test that `check_tcp_and_tls()` in `tcp.py` catches `OSError(errno.EMFILE)` / `OSError(errno.ENFILE)`, logs a warning, retries once after a brief backoff, and does not silently swallow the error at `DEBUG` level
- [x] Task: Implement Engine FD auto-tuning, `docker-compose.yml` `ulimits`, and probe resilience [23ef3f1]
    - [x] Add `ulimits.nofile` (`soft: 65535`, `hard: 65535`) to the `backend` service in `docker-compose.yml`
    - [x] Update `run_engine()` in `engine/src/engine/engine.py` to auto-raise `RLIMIT_NOFILE` and clamp `workers_count` safely against the active soft limit
    - [x] Update `engine/src/engine/operations/network.py` to eagerly import `concurrent.futures.thread` and catch `(socket.gaierror, OSError)`
    - [x] Update `engine/src/engine/probes/tcp.py` to explicitly handle `errno.EMFILE` / `errno.ENFILE` with warning logging and a single retry
- [x] Task: Phase Verification & Checkpoint (Refer to `workflow.md`)

## Phase 2: Generic `init_db()` Metadata Auto-Sync & `scan_id`-Scoped Ghost Evaluation [checkpoint: e3fcc99]
- [x] Task: Write unit tests for generic `init_db()` schema sync and `scan_id`-scoped Ghost evaluation (`api/tests/test_database.py`, `api/tests/test_evaluator.py`) [b24933f]
    - [x] Test that `init_db()` generically inspects `SQLModel.metadata.tables` vs `sqlalchemy.inspect(engine)` to add missing columns across any table (including `scans.prune_void_hosts`, `scans.prune_closed_ports`, `scans.last_triggered_at`, and `system_config`)
    - [x] Test that `init_db()` fails fast by raising `RuntimeError` when an `ALTER TABLE` migration fails instead of silently passing
    - [x] Test in `api/tests/test_evaluator.py` that Ad-Hoc runs (`scan_id=None`) never evaluate Ghosts and never serve as a historical Ghost baseline for subsequent runs
    - [x] Test that Scheduled Scan runs (`scan_id != None`, including "Scan Now" runs) strictly evaluate Ghosts against completed runs with the exact same `scan_id` and ignore runs from other schedules
- [x] Task: Implement generic metadata-driven `init_db()` and `scan_id`-scoped Ghost baseline [e3fcc99]
    - [x] Replace hardcoded column checks in `api/src/api/database.py` (`init_db`) with generic `SQLModel.metadata.tables` + `sqlalchemy.inspect(engine)` column diffing and fail-fast `RuntimeError` handling
    - [x] Update `evaluate_scan_run()` in `api/src/api/services/evaluator.py` to only query `hist_stmt` when `run.scan_id is not None` and filter by `ScanRun.scan_id == run.scan_id`
    - [x] Update existing Ghost test fixtures in `api/tests/test_evaluator.py` and `api/tests/test_scale_slash16.py` to associate a `Scan` (`scan_id`) with scheduled Ghost test runs
- [x] Task: Phase Verification & Checkpoint (Refer to `workflow.md`)

## Phase 3: Backend Run Deletion, Schedule Hard-Delete, Retention Policy & System Reset API
- [~] Task: Write unit tests for Run Deletion, Schedule Cascade Delete, Cron Trigger Tracking, Retention Cleanup, and System Maintenance endpoints (`api/tests/test_system_and_lifecycle.py`)
    - [ ] Test `DELETE /api/runs/{id}`: returns `409 Conflict` on active (`RUNNING`/`PENDING`) runs, and `204 No Content` on terminal runs while cascading deletion to `HostState`, `PortState`, `TlsCertificate`, and `HttpRoutingCheck` and cleaning up `RunManager` buffers
    - [ ] Test `DELETE /api/scans/{id}`: hard-deletes the `Scan` and cascades deletion to all associated `ScanRun` records
    - [ ] Test `scheduler.py`: tracks `Scan.last_triggered_at` so deleting the latest `ScanRun` of an active schedule does not cause an immediate duplicate re-trigger
    - [ ] Test `GET /api/system/settings` and `PUT /api/system/settings` (`retention_days` persistence and immediate pruning of expired terminal runs)
    - [ ] Test `POST /api/system/purge-runs` (wipes all `ScanRun` history while preserving `Scan`, `SavedView`, and `SystemConfig`) and `POST /api/system/reset-db` (`drop_all` + `create_all` + `VACUUM`)
- [ ] Task: Implement Backend Lifecycle Models, Endpoints, and Scheduler Retention
    - [ ] Add `last_triggered_at: datetime | None = None` to `Scan` and create `SystemConfig` (`id: int = 1`, `retention_days: int = 0`) in `api/src/api/models.py`
    - [ ] Implement `DELETE /api/runs/{id}` in `api/src/api/routers/runs.py`
    - [ ] Update `DELETE /api/scans/{id}` in `api/src/api/routers/scans.py` to abort active runs for the schedule and hard-delete the `Scan` row
    - [ ] Update `api/src/api/services/scheduler.py` to persist `scan.last_triggered_at`, evaluate cron against `max(scan.last_triggered_at, latest_run.started_at)`, and prune expired terminal runs when `SystemConfig.retention_days > 0`
    - [ ] Create `api/src/api/routers/system.py` (`GET /api/system/settings`, `PUT /api/system/settings`, `POST /api/system/purge-runs`, `POST /api/system/reset-db`) and register it in `api/src/api/main.py`
- [ ] Task: Phase Verification & Checkpoint (Refer to `workflow.md`)

## Phase 4: Frontend `/settings` Page, Run History Deletion & UI Consistency Fixes
- [ ] Task: Write frontend unit tests for `/settings`, Run History deletion, and UI consistency fixes (`frontend/src/pages/__tests__/SettingsPage.test.tsx`, `frontend/src/pages/__tests__/ScheduledScansPage.test.tsx`, `frontend/src/features/scans/__tests__/StatusBadge.test.tsx`)
    - [ ] Test `SettingsPage.tsx`: displays storage stats, saves `retention_days`, and triggers Purge History / Factory Reset DB confirmation flows
    - [ ] Test `RunHistorySheet.tsx`: renders target string previews on run cards, deletes non-active runs via `DELETE /api/runs/{id}`, and resets `selectedRunId` to `null` if the currently viewed run is deleted
    - [ ] Test `ScanConfigForm.tsx` hides `Ghost Window` when `mode === 'live'` and shows it when `mode === 'schedule'`
    - [ ] Test `FormatTlsExpiry` in `StatusBadge.tsx` renders `0d` as red `expired 0d`, and `ScheduledScansPage.tsx` displays evaluation settings in the expanded row view
- [ ] Task: Implement `SettingsPage.tsx`, `RunHistorySheet.tsx` enhancements, and UI fixes
    - [ ] Create `frontend/src/pages/SettingsPage.tsx` and wire `/settings` into `frontend/src/app/router.tsx` and `frontend/src/components/layout/Header.tsx`
    - [ ] Update `frontend/src/features/scans/components/RunHistorySheet.tsx` with target string preview and per-run Delete button + active run fallback
    - [ ] Update `frontend/src/components/scans/ScanConfigForm.tsx` to hide `Ghost Window` in `live` mode
    - [ ] Update `frontend/src/features/scans/components/StatusBadge.tsx` (`days <= 0` expired) and `frontend/src/pages/ScheduledScansPage.tsx` (expanded Evaluation Settings section)
- [ ] Task: Phase Verification & Checkpoint (Refer to `workflow.md`)
