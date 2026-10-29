# Specification: Reliability, Data Retention & Lifecycle Management (`reliability_and_lifecycle_management`)

## 1. Overview
Harden the scanning engine against OS file descriptor exhaustion (`Errno 24: Too many open files`) on production Linux containers, scope Ghost detection strictly to individual Scheduled Scans (`scan_id`), replace hardcoded SQLite column migrations in `init_db()` with generic SQLModel metadata introspection and fail-fast error handling, and introduce comprehensive data lifecycle management (individual run deletion in History, configurable automatic run retention, and a dedicated `/settings` page with database stats, history purge, and 1-click schema factory reset).

## 2. Functional Requirements

### 2.1 Engine File Descriptor Resilience (`Errno 24` Prevention)
1. **Container `ulimits` Configuration:**
   - Configure `ulimits.nofile` (`soft: 65535`, `hard: 65535`) on the `backend` service in `docker-compose.yml` so rootful Podman/Docker on enterprise Linux (e.g., Rocky Linux) does not default to `1024`.
2. **Self-Healing `RLIMIT_NOFILE` & Worker Clamping (`engine.py`):**
   - At the start of `run_engine()`, query `resource.getrlimit(resource.RLIMIT_NOFILE)` and attempt to raise the soft limit up to `min(hard, 65535)`.
   - If the active OS soft limit is still lower than `workers_count + 250`, clamp `workers_count` to `max(50, soft_limit - 250)` and emit a `WARNING` log so the engine queues probes safely without exhausting file descriptors.
3. **Eager Thread Executor Import & DNS Resilience (`network.py`):**
   - Eagerly import `concurrent.futures.thread` at module import time so Python never fails trying to open `thread.py` mid-scan when FDs are tight.
   - Catch `(socket.gaierror, OSError)` in `resolve_target()` so DNS socket allocation failures return cleanly instead of crashing worker routines.
4. **Explicit `EMFILE` / `ENFILE` Handling (`tcp.py`):**
   - In `check_tcp_and_tls()`, detect `OSError` with `errno.EMFILE` or `errno.ENFILE` ("Too many open files"), log a warning, brief-yield (`await asyncio.sleep(0.05)`), and retry once before failing, preventing silent false-negative `"closed"` ports.

### 2.2 Scan-Scoped Ghost Evaluation & Schedule Deletion Integrity
1. **`scan_id`-Scoped Ghost Baseline (`evaluator.py`):**
   - Only query `historical_active_ip_ports` when `run.scan_id is not None`.
   - Filter `hist_stmt` by `ScanRun.scan_id == run.scan_id`.
   - Result: Cron-triggered runs and "▶ Scan Now" runs (`scan_id != None`) evaluate Ghosts strictly against past completed runs of that same schedule, while generic Ad-Hoc Live Scans (`scan_id is None`) never evaluate Ghosts and never pollute any schedule's baseline.
2. **Hide Ghost Window in Ad-Hoc Live Scan Mode (`ScanConfigForm.tsx`):**
   - Render the `Ghost Window` input only when `mode === 'schedule'`.
3. **Hard-Delete Scheduled Scans with Cascade (`scans.py`):**
   - Update `DELETE /api/scans/{id}` to abort any active runs for that schedule and hard-delete the `Scan` row (`session.delete(scan)`), leveraging SQLite's `ON DELETE CASCADE` on `ScanRun.scan_id` to clear its run history as promised by the UI dialog.
4. **Decouple Cron Trigger Tracking from Run Deletion (`models.py`, `scheduler.py`):**
   - Add `last_triggered_at: datetime | None = None` to `Scan` and update it whenever `scheduler.py` dispatches a scheduled run.
   - In `scheduler.py`, determine the last execution timestamp using `max(scan.last_triggered_at, latest_run.started_at)` so deleting a `ScanRun` from history (or via retention pruning) never causes the scheduler to immediately re-trigger a duplicate run.

### 2.3 Generic Metadata-Driven `init_db()` with Fail-Fast Error Handling
1. **Declarative Column Inspection (`database.py`):**
   - Replace the hardcoded table/column migration blocks in `init_db()` with a generic loop over `SQLModel.metadata.tables` compared against `sqlalchemy.inspect(engine).get_columns(table_name)`.
   - Automatically construct and execute `ALTER TABLE <table_name> ADD COLUMN <col_ddl>` for any missing columns defined in `SQLModel.metadata`.
2. **Fail-Fast on Incompatible Schema:**
   - Remove the silent `except Exception: pass` block. If an automatic `ALTER TABLE` fails or schema incompatibility persists, log a `CRITICAL` message and raise a `RuntimeError` immediately on startup.

### 2.4 Run History Deletion, Retention Policy & `/settings` Page
1. **Single Run Deletion (`DELETE /api/runs/{id}` in `runs.py`):**
   - Return `409 Conflict` if the run is currently `RUNNING` or `PENDING`.
   - Execute `session.exec(delete(ScanRun).where(ScanRun.id == id))` (triggering SQLite's native C-level `ON DELETE CASCADE` across `HostState`, `PortState`, `TlsCertificate`, and `HttpRoutingCheck`) and call `run_manager.cleanup_run(id)`.
2. **System Settings & Maintenance Endpoints (`routers/system.py`, `models.py`):**
   - Add `SystemConfig` SQLModel table (`id: int = 1`, `retention_days: int = 0`, where `0` = disabled / keep forever by default).
   - `GET /api/system/settings`: Return `retention_days`, `db_size_bytes`, `runs_count`, `scans_count`, and `hosts_count`.
   - `PUT /api/system/settings`: Update `retention_days` (`0 <= retention_days <= 3650`) and immediately prune expired terminal runs if `retention_days > 0`.
   - `POST /api/system/purge-runs`: Abort active runs, delete all `ScanRun` rows (`delete(ScanRun)`), clear `run_manager` buffers, and execute `VACUUM`.
   - `POST /api/system/reset-db`: Abort active runs, clear `run_manager` buffers, execute `SQLModel.metadata.drop_all(engine)` + `SQLModel.metadata.create_all(engine)`, and execute `VACUUM`.
3. **Automated Retention Cleanup (`scheduler.py`):**
   - In `check_and_run_scheduled_scans()`, if `SystemConfig.retention_days > 0`, delete terminal `ScanRun` rows (`COMPLETED`, `FAILED`, `ABORTED`) with `started_at < now - timedelta(days=retention_days)`.

### 2.5 Frontend `/settings` Page, Run History Controls & Minor UI Fixes
1. **Dedicated `/settings` Page (`SettingsPage.tsx`, `router.tsx`, `Header.tsx`):**
   - Add a `Settings` navigation button in `Header.tsx` routing to `/settings`.
   - Display Database & Storage metrics (SQLite file size, total runs, scheduled scans, stored host records).
   - Provide a Data Retention Policy configuration card (`retention_days`, with `0` = Keep Forever).
   - Provide a Danger Zone card with confirmation modals for **Purge All Scan History** (keeps schedules & views) and **Factory Reset Database** (wipes all tables and rebuilds schema from scratch).
2. **Run History Deletion & Target Preview (`RunHistorySheet.tsx`):**
   - Show the actual target string preview (e.g., `143.106.16.128/26, nimbus...`) on each run card in addition to target count.
   - Add a delete button (with confirmation) for non-active runs. If the deleted run equals `selectedRunId`, invoke `onSelectRun(null)` and invalidate `['runs']` so the Dashboard transitions seamlessly to the next latest run.
3. **Minor UI Fixes (`StatusBadge.tsx`, `ScheduledScansPage.tsx`):**
   - Update `FormatTlsExpiry` in `StatusBadge.tsx` so `days <= 0` renders red (`expired`), matching `evaluator_rules.py`.
   - Display Evaluation Settings (`Ghost Window`, `TLS Warning Days`, `Prune Void Hosts`, `Prune Closed Ports`) in the expanded row view of `ScheduledScansPage.tsx`.

## 3. Acceptance Criteria
- All Engine, API, and Frontend unit and integration test suites pass with >80% coverage on touched modules.
- Running a `/16` scan on a container with restricted soft `nofile` limits safely clamps or auto-raises `RLIMIT_NOFILE` without unhandled `Errno 24` tracebacks.
- Ad-Hoc Live Scans never produce Ghost hosts or pollute Scheduled Scan baselines; "▶ Scan Now" and Cron runs evaluate Ghosts strictly within their own `scan_id`.
- `init_db()` generically adds missing columns from `SQLModel.metadata` and fails fast on incompatible DDL.
- Users can delete individual runs in `RunHistorySheet`, configure automatic retention days on `/settings`, purge all run history, or factory-reset the database schema from the browser.

## 4. Out of Scope
- Contextual `ⓘ` info tooltips and in-app documentation overlays (deferred to a dedicated UX/documentation track).
