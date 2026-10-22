# Specification: Encapsulated RunManager & Finding-Based Alert Matcher (`run_manager_and_alerts`)

Status: ready-for-agent  
Related ADR: [ADR 0023](../../adr/0023-control-plane-and-flat-explorer-modernization.md) (Implements Track 3)  
Review Retrospective: [review-and-pipeline-retrospective.md](./review-and-pipeline-retrospective.md)

---

## 1. Overview
This track implements **Track 3 of ADR 0023**: modernizing scan run lifecycle management and alert evaluation in Site Health Check.
It encapsulates subprocess process management, abort signals, log ring-buffers, and SSE subscriber distribution into a typed `RunManager` service on `app.state.run_manager`.
It also unifies manual and scheduled scan lifecycles into a single pipeline (`Ingest ➔ Finalize & Evaluate ➔ Match Alerts`) and updates alert evaluation to consume Track 2's deterministic findings and metrics.

---

## 2. Functional Requirements

### 2.1 Encapsulated `RunManager` Service (`api/services/run_manager.py`)
1. **State Encapsulation:**
   - Eliminate loose dictionary state (`app.state.processes`, `app.state.run_logs`, `app.state.log_subscribers`) across `main.py`, `runs.py`, `runner.py`, and `scheduler.py`.
   - Implement `RunManager` class registered on `app.state.run_manager`.
2. **Lifecycle & Process Management:**
   - `dispatch_run(run_id: str, snapshot: dict[str, Any], scan_id: str | None = None) -> asyncio.Task`: Dispatches background run execution.
   - `register_process(run_id: str, process: asyncio.subprocess.Process)`: Tracks active OS subprocess.
   - `unregister_process(run_id: str)`: Cleans up process handle on completion or abort.
   - `abort_run(run_id: str) -> bool`: Sends `SIGTERM` to the active subprocess, marks run as aborted, and returns whether an active process was signalled.
   - `is_active(run_id: str) -> bool`: Returns whether a run is currently executing.
3. **Log Buffering & SSE Fan-Out:**
   - `publish_log(run_id: str, event: ServerSentEvent)`: Stores event in a bounded ring-buffer (`collections.deque(maxlen=1000)`) and broadcasts to registered subscriber queues.
   - `subscribe_logs(run_id: str) -> AsyncGenerator[ServerSentEvent, None]`: Streams historical buffered logs then live events using a bounded `asyncio.Queue(maxsize=100)`. Automatically unregisters queues upon client disconnect.
   - `cleanup_run(run_id: str)`: Evicts subscribers and frees completed buffers.

### 2.2 Unified Run & Alert Execution Pipeline
1. Standardize both manual runs (`POST /api/runs`) and scheduled runs (`scheduler.py`) through the identical 3-step lifecycle:
   - **Step 1 (Ingest):** Subprocess executes `engine.cli --config -` via `stdin`, streaming NDJSON events and writing deltas to SQLite with non-blocking WAL mode.
   - **Step 2 (Finalize & Evaluate):** On subprocess termination, run an atomic finalization transaction executing `evaluator.evaluate_scan_run(run_id, session)` to compute `ScanRun.metrics_json["summary"]`, host statuses, and canonical finding codes.
   - **Step 3 (Match & Dispatch Alerts):** Evaluate alert rules against the evaluated run and dispatch Google Chat / Slack webhooks.

### 2.3 Finding-Driven Alert Matching & Refactored `compute_run_summary`
1. **Simplified Summary:** Replace the redundant nested port/certificate loop in `api/src/api/services/alerts.py:compute_run_summary()` with direct reads from `run.metrics_json["summary"]` (or a single fast `COUNT(*) GROUP BY status` SQL query on `HostState`).
2. **Finding-Driven Evaluation:**
   - Update `evaluate_alert_triggers()` to evaluate `AlertConfig` triggers against `run_status`, summary stats, and canonical `finding_codes` (`TLS_EXPIRED`, `HTTP_5XX`, `HOST_GHOST`, etc.).
   - Enrich webhook payloads with specific finding code summaries.
   - Retain 100% backward compatibility for all existing `AlertConfig` boolean fields.

### 2.4 Router & Lifecycle Refactoring
1. `api/src/api/main.py`: Instantiate `RunManager` during lifespan startup and gracefully terminate any running processes on shutdown.
2. `api/src/api/routers/runs.py`:
   - Delegate abort requests (`POST /api/runs/{id}/abort`) to `run_manager.abort_run(id)`.
   - Stream logs (`GET /api/runs/{id}/stream`) directly from `run_manager.subscribe_logs(id)`.
   - Launch runs using `run_manager.dispatch_run(...)`.
3. `api/src/api/services/scheduler.py`: Use `app_state.run_manager.dispatch_run(...)` for scheduled executions.

---

## 3. Non-Functional Requirements
- **Memory Boundedness:** Log buffers enforced via `deque(maxlen=1000)`; SSE subscriber queues bounded at `maxsize=100`.
- **Concurrency Safety:** Thread-safe process tracking and subscriber queue management under `asyncio`.
- **TDD & High Coverage:** Strict TDD workflow across `api/tests/test_run_manager.py`, `api/tests/test_api_runner.py`, `api/tests/test_alert_service.py`, and `api/tests/test_api_scheduler.py`.

---

## 4. Acceptance Criteria
- [ ] No direct access to `app.state.processes`, `app.state.run_logs`, or `app.state.log_subscribers` in any router or service.
- [ ] `RunManager` service handles process registration, aborts, log buffering, and SSE streaming cleanly.
- [ ] Manual and scheduled scan runs share the exact same `Ingest -> Finalize/Evaluate -> Alert` pipeline.
- [ ] `compute_run_summary()` no longer loops through individual ports and certificates.
- [ ] Webhooks reflect accurate evaluated finding codes and summary counts.
- [ ] Full pytest test suite passes with zero regressions.

---

## 5. Out of Scope
- Engine probe changes (Track 1).
- SQLite table schema migrations (Track 2).
- Orthogonal 3-table paginated REST endpoints and IP drawer endpoints (Track 4).
- React frontend redesign (Track 5).
