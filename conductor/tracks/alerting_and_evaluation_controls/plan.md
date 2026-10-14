# Implementation Plan: Alerting System & Scan Evaluation Controls

## Phase 1: Backend Data Models & Evaluation Parameters
- [x] Task: Write Tests for Model & Evaluation Configuration [checkpoint: 696f35a]
  - [x] Write failing test for `Scan` and `ExecutionConfig` accepting `ghost_window`, `tls_warning_days`, and `alert_config`
  - [x] Write failing test for API scan CRUD endpoints with alert and evaluation parameters
- [x] Task: Implement Model & API Contract Updates [checkpoint: 696f35a]
  - [x] Add `ghost_window`, `tls_warning_days`, and `alert_config_json` to `Scan` and `ExecutionConfig` models
  - [x] Update `api/routers/scans.py` and `api/routers/runs.py` schema serialization
- [ ] Task: Phase Verification & Checkpoint (Refer to workflow.md)

## Phase 2: Alert Evaluation & Webhook Dispatch Service
- [ ] Task: Write Tests for Alert Evaluation & Webhook Dispatch
  - [ ] Write failing unit test for Google Chat Cards v2 payload builder (Schedule, Run ID, Triggers, Summary, Button)
  - [ ] Write failing unit test for Slack Block Kit payload builder
  - [ ] Write failing unit test for alert trigger condition evaluator (`failure`, `ghost`, `warning`, `abort`, `healthy`)
  - [ ] Write failing test for `POST /api/alerts/test` endpoint
- [ ] Task: Implement Alert Service & Webhook Integration
  - [ ] Implement `api/services/alerts.py` with provider detection and payload formatters
  - [ ] Hook `evaluate_and_dispatch_alert` into the scan completion lifecycle in `api/services/scheduler.py`
  - [ ] Add `POST /api/alerts/test` endpoint with safe error reporting
  - [ ] Configure `APP_BASE_URL` in `api/config.py` with environment fallback
- [ ] Task: Phase Verification & Checkpoint (Refer to workflow.md)

## Phase 3: Frontend UI Configuration
- [ ] Task: Write Tests for Scan Configuration Form
  - [ ] Write unit test for `ScanConfigForm` rendering evaluation settings (Ghost Window, TLS days) in both modes
  - [ ] Write unit test for `ScanConfigForm` rendering alert checklist and `[ Test Webhook ]` button in schedule mode
- [ ] Task: Implement Frontend UI Changes
  - [ ] Add Evaluation Settings section to `ScanConfigForm`
  - [ ] Add Alert Configuration section with URL input, trigger checklist, and `[ Test Webhook ]` action
  - [ ] Integrate test webhook API mutation with loading and feedback toasts
- [ ] Task: Phase Verification & Checkpoint (Refer to workflow.md)
