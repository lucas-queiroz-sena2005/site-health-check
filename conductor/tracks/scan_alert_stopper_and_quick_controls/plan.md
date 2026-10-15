# Implementation Plan: Scan Alert Stopper & Quick Controls

## Phase 1: Backend Data Model, Stopper Gatekeeper & Idempotent API
- [ ] Task: Write Tests for Alert Mute Model & Idempotent Endpoints
  - [ ] Write failing test for `Scan.alerts_muted` field and serialization in `ScanResponse`
  - [ ] Write failing test for `evaluate_and_dispatch_alert` halting early when `scan.alerts_muted is True`
  - [ ] Write failing tests for `POST /api/scans/{id}/alerts/mute` and `POST /api/scans/{id}/alerts/unmute` confirming idempotent execution
  - [ ] Write failing tests for lightweight `GET` web action endpoints returning minimal HTML confirmation without frontend SPA dependencies
- [ ] Task: Implement Alert Mute Model & API Endpoints
  - [ ] Add `alerts_muted: bool = False` to `Scan` in `api/src/api/models.py` and update schemas
  - [ ] Add early stopper check in `evaluate_and_dispatch_alert` in `api/src/api/services/alerts.py`
  - [ ] Implement `POST` and `GET` mute/unmute endpoints with idempotent state validation in `api/src/api/routers/scans.py`
- [ ] Task: Phase Verification & Checkpoint

## Phase 2: Chat Card Mute Links & Automated Chat Confirmation
- [ ] Task: Write Tests for Card Actions & Webhook Confirmation Messages
  - [ ] Write unit tests for `build_google_chat_card` and `build_slack_blocks` rendering "Turn Off Alerts" action link
  - [ ] Write unit test for automated chat notification dispatched when alerts are muted or resumed
  - [ ] Write unit test verifying concurrent clicks in chat do not invert state
- [ ] Task: Implement Card Actions & Webhook Confirmation Dispatch
  - [ ] Update alert payload builders in `api/src/api/services/alerts.py` to include the mute action link
  - [ ] Implement automated webhook confirmation dispatch upon mute/unmute
- [ ] Task: Phase Verification & Checkpoint

## Phase 3: Frontend Dashboard Integration (Zero Page Reload)
- [ ] Task: Write Tests for Schedule Table & In-Place Stopper Controls
  - [ ] Write tests for `ScheduledScansPage` rendering the "Alerts" column (`Bell` when active, `BellOff` when muted, empty if no triggers)
  - [ ] Write tests for the in-place stopper button toggling status without route change or page reload
- [ ] Task: Implement Schedule View Column & In-Place Stopper Button
  - [ ] Add "Alerts" table column with `Bell` and `BellOff` icons in `ScheduledScansPage.tsx`
  - [ ] Add stopper button between "Edit Schedule" and "Delete" in the expanded actions panel
  - [ ] Connect stopper button to TanStack React Query mutation for instant, in-place cache updates
- [ ] Task: Phase Verification & Checkpoint
