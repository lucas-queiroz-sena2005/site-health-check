# Specification: Scan Alert Stopper & Quick Controls

## Overview
Provide an in-place alert stopper mechanism that allows operators to mute and unmute automated alerts for any scheduled scan without modifying the scan's trigger configuration. The feature includes:
1. Instant, in-place toggle controls and visual status indicators (Bell / Crossed Bell) in the Scheduled Scans dashboard with zero page reloads.
2. Direct one-click mute/unmute action links in chat cards with idempotent state handling (preventing race conditions from multiple users clicking) and automatic chat confirmation.

---

## Functional Requirements

### 1. Data Model & Alert Gatekeeper
- Add `alerts_muted: bool = Field(default=False)` to the `Scan` SQLModel and update `ScanResponse` schema.
- In `evaluate_and_dispatch_alert`, check `scan.alerts_muted`. If `True`, halt evaluation immediately before evaluating triggers, keeping all configured triggers and webhook settings completely intact.

### 2. Idempotent Backend API & Lightweight Action Endpoints
- **RESTful Endpoints** (for frontend & API clients):
  - `POST /api/scans/{id}/alerts/mute`: Idempotently sets `alerts_muted = True`. If already muted, returns current state with no inverted toggle.
  - `POST /api/scans/{id}/alerts/unmute`: Idempotently sets `alerts_muted = False`.
- **Fast Web Action Endpoints** (for single-click execution from chat):
  - `GET /api/scans/{id}/alerts/mute` and `GET /api/scans/{id}/alerts/unmute`:
    - Immediately executes the mute/unmute action upon request.
    - Dispatches an automated confirmation message to the scan's configured chat webhook (e.g. *"Alerts for schedule '{schedule_name}' have been muted. [ Turn Back On ]"*).
    - Returns an ultra-lightweight HTML response (< 1KB) with status and a toggle link, without forcing the user to load the heavy React application.

### 3. Chat Card Integration
- In Google Chat Cards v2 and Slack Block Kit:
  - Add an action link underneath the results link: `Turn Off Alerts for this Schedule` pointing to the fast mute endpoint.
  - When muted, the follow-up confirmation card sent to chat displays:
    - Status: `Alerts Muted for {schedule_name}`
    - Link: `Turn Back On` (pointing to the fast unmute endpoint).
  - **Idempotency Guarantee**: Because mute and unmute are separate explicit actions, concurrent clicks by different users will never toggle state inversely.

### 4. Schedule View Table & In-Place Stopper (Zero Page Reload)
- In `ScheduledScansPage.tsx`:
  - **New "Alerts" Table Column**:
    - If scan has no triggers configured $\rightarrow$ Empty.
    - If scan has triggers configured and active $\rightarrow$ `Bell` icon (Alerts Active).
    - If scan has triggers configured and muted $\rightarrow$ `BellOff` icon (Alerts Muted).
  - **Stopper Button**:
    - Positioned between "Edit Schedule" and "Delete" in the expanded row actions.
    - Displays current status: "Mute Alerts" (when active) or "Resume Alerts" (when muted).
    - Uses React Query mutation: Updates the scan in-place with instant UI feedback and zero page reloads or route navigation.

---

## Acceptance Criteria
- [ ] Muting a scan suppresses all alert notifications while keeping scan runs and schedules active.
- [ ] Concurrent clicks on "Turn Off" from multiple users in chat keep alerts muted without accidentally re-enabling them.
- [ ] Chat link executes immediately and returns a lightweight confirmation without loading the React SPA bundle.
- [ ] Schedule view displays `Bell` or `BellOff` appropriately, and the in-place stopper button toggles mute status with zero page reload.
- [ ] All unit and integration tests pass with >80% coverage.

---

## Out of Scope
- Google Cloud Console two-way interactive bot app registration (uses direct lightweight action links).
- Per-trigger granular muting (muting acts as a master stopper for the scan's webhook output).
