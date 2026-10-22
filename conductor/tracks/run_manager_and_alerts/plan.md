# Implementation Plan: Encapsulated RunManager & Finding-Based Alert Matcher (`run_manager_and_alerts`)

## Phase 1: Typed RunManager Service & SSE Ring-Buffer (TDD) [checkpoint: 7d7c7fd]
- [x] Task: Write failing unit tests for RunManager process management, abort coordination, and SSE buffering (Red Phase) e73cc9e
  - [x] Add unit tests in `api/tests/test_run_manager.py` verifying process registration, unregistration, active status checks, and `abort_run()` sending `SIGTERM`
  - [x] Add unit tests verifying `publish_log()` buffering in `deque(maxlen=1000)` and fan-out broadcasting to subscriber queues
  - [x] Add unit tests verifying `subscribe_logs()` historical replay, bounded `asyncio.Queue(maxsize=100)` streaming, and subscriber cleanup on generator termination
- [x] Task: Implement RunManager service in `api/src/api/services/run_manager.py` (Green & Refactor Phase) 1740c84
  - [x] Create `api/src/api/services/run_manager.py` implementing `RunManager` with thread-safe process maps, bounded log buffers, and subscriber lifecycle management
  - [x] Register `app.state.run_manager` during FastAPI lifespan in `api/src/api/main.py` and implement graceful shutdown
  - [x] Verify unit tests pass in `api/tests/test_run_manager.py`
- [x] Task: Phase Verification & Checkpoint (Refer to `workflow.md`) 7d7c7fd

---

## Phase 2: Unified Run Pipeline & Router Migration (TDD)
- [ ] Task: Write failing tests for RunManager.dispatch_run() and router integration (Red Phase)
  - [ ] Add integration tests in `api/tests/test_api_runner.py` verifying that `dispatch_run()` runs background execution, stream logging, finalization via `evaluator.evaluate_scan_run()`, and post-run alert check
  - [ ] Add unit tests in `api/tests/test_api_runs.py` asserting that `POST /api/runs/{id}/abort` delegates to `run_manager.abort_run()` and `GET /api/runs/{id}/stream` consumes `run_manager.subscribe_logs()`
  - [ ] Add unit tests in `api/tests/test_api_scheduler.py` verifying scheduled scan dispatches route through `run_manager.dispatch_run()`
- [ ] Task: Integrate RunManager across runner, router, and scheduler (Green & Refactor Phase)
  - [ ] Implement `RunManager.dispatch_run()` unifying background subprocess orchestration, log capture, and post-finalization alert triggers
  - [ ] Refactor `api/src/api/routers/runs.py` to remove all direct `app.state.processes`, `app.state.run_logs`, and `app.state.log_subscribers` access in favor of `request.app.state.run_manager`
  - [ ] Refactor `api/src/api/services/scheduler.py` to dispatch scheduled scans via `run_manager.dispatch_run()`
  - [ ] Eliminate redundant `run_scheduled_scan_with_alerts` in favor of the unified pipeline
- [ ] Task: Phase Verification & Checkpoint (Refer to `workflow.md`)

---

## Phase 3: Finding-Driven Alert Matching & Summary Simplification (TDD)
- [ ] Task: Write failing tests for finding-driven alert triggers and simplified run summary (Red Phase)
  - [ ] Add tests in `api/tests/test_alert_service.py` asserting `compute_run_summary()` accurately uses `run.metrics_json["summary"]` or fast SQL status counts without iterating individual ports or certificates
  - [ ] Add tests verifying that `evaluate_alert_triggers()` evaluates canonical `finding_codes` (`TLS_EXPIRED`, `HTTP_5XX`, `HOST_GHOST`, etc.) alongside `AlertConfig` boolean triggers
  - [ ] Add tests verifying enriched Google Chat Cards v2 and Slack payload generation displaying specific finding codes
- [ ] Task: Implement finding-driven alert evaluation in `api/src/api/services/alerts.py` (Green & Refactor Phase)
  - [ ] Refactor `compute_run_summary()` in `api/src/api/services/alerts.py` to read pre-computed summary metrics, deleting the legacy port/certificate inspection loop
  - [ ] Update `evaluate_alert_triggers()` to match against canonical finding codes and status aggregates while preserving all boolean triggers
  - [ ] Update webhook payload builders (`build_google_chat_card`, `build_slack_blocks`, `build_alert_payload`) to include finding code summaries
- [ ] Task: Phase Verification & Checkpoint (Refer to `workflow.md`)

---

## Phase 4: Full System Regression & End-to-End Verification
- [ ] Task: Comprehensive test suite verification and regression testing
  - [ ] Execute full pytest test suite across `api/tests/` and `engine/tests/`
  - [ ] Verify manual scan launch, live SSE log streaming, abort handling, and alert trigger dispatch end-to-end
  - [ ] Verify scheduled scan execution via scheduler loop with zero errors
- [ ] Task: Phase Verification & Checkpoint (Refer to `workflow.md`)
