# Implementation Plan: Alerting System & Scan Evaluation Controls

## Phase 1: Backend Data Models & Evaluation Parameters [checkpoint: 696f35a]
- [x] Task: Write Tests for Model & Evaluation Configuration [checkpoint: 696f35a]
  - [x] Write failing test for `Scan` and `ExecutionConfig` accepting `ghost_window`, `tls_warning_days`, and `alert_config`
  - [x] Write failing test for API scan CRUD endpoints with alert and evaluation parameters
- [x] Task: Implement Model & API Contract Updates [checkpoint: 696f35a]
  - [x] Add `ghost_window`, `tls_warning_days`, and `alert_config_json` to `Scan` and `ExecutionConfig` models
  - [x] Update `api/routers/scans.py` and `api/routers/runs.py` schema serialization
- [x] Task: Phase Verification & Checkpoint [checkpoint: 696f35a]

## Phase 2: Alert Evaluation & Webhook Dispatch Service [checkpoint: 81ee000]
- [x] Task: Write Tests for Alert Evaluation & Webhook Dispatch [checkpoint: 81ee000]
  - [x] Write failing unit test for Google Chat Cards v2 payload builder (Schedule, Run ID, Triggers, Summary, Button)
  - [x] Write failing unit test for Slack Block Kit payload builder
  - [x] Write failing unit test for alert trigger condition evaluator (`failure`, `ghost`, `warning`, `abort`, `healthy`)
  - [x] Write failing test for `POST /api/alerts/test` endpoint
- [x] Task: Implement Alert Service & Webhook Integration [checkpoint: 81ee000]
  - [x] Implement `api/services/alerts.py` with provider detection and payload formatters
  - [x] Hook `evaluate_and_dispatch_alert` into the scan completion lifecycle in `api/services/scheduler.py`
  - [x] Add `POST /api/alerts/test` endpoint with safe error reporting
  - [x] Configure `APP_BASE_URL` in `api/config.py` with environment fallback
- [x] Task: Phase Verification & Checkpoint [checkpoint: 81ee000]

## Phase 3: Frontend UI Configuration [checkpoint: d4ed637]
- [x] Task: Write Tests for Scan Configuration Form [checkpoint: d4ed637]
  - [x] Write unit test for `ScanConfigForm` rendering evaluation settings (Ghost Window, TLS days) in both modes
  - [x] Write unit test for `ScanConfigForm` rendering alert checklist and `[ Test Webhook ]` button in schedule mode
- [x] Task: Implement Frontend UI Changes [checkpoint: d4ed637]
  - [x] Add Evaluation Settings section to `ScanConfigForm`
  - [x] Add Alert Configuration section with URL input, trigger checklist, and `[ Test Webhook ]` action
  - [x] Integrate test webhook API mutation with loading and feedback toasts
- [x] Task: Phase Verification & Checkpoint [checkpoint: d4ed637]
