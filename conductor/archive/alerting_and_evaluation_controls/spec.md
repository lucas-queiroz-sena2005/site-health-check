# Specification: Alerting System & Scan Evaluation Controls

## 1. Overview
Implement an automated alerting system that delivers high-signal, cleanly formatted notifications to **Google Chat** (Cards v2) and **Slack** (Block Kit) when scheduled scans complete with issues. Additionally, decouple and expose the **Ghost Window** and **Warning (TLS expiry) thresholds** per scan so both ad-hoc runs and scheduled scans evaluate health states consistently.

---

## 2. Functional Requirements

### 2.1 Scan Evaluation Configuration (Ad-Hoc & Scheduled Scans)
- **Configurable Ghost Window:**
  - Per-scan/run field `ghost_window: str = "7d"` (e.g. `24h`, `7d`, `30d`).
  - Controls historical lookup window when classifying dead IPs as `Ghost`.
- **Configurable TLS Warning Threshold:**
  - Per-scan/run field `tls_warning_days: int = 30`.
  - Classifies TLS certificates expiring within $\le N$ days as `Warning`.
- **Decoupling:** Evaluation settings are available in both ad-hoc (`live`) and scheduled modes, with sensible defaults.

### 2.2 Alert Configuration (Scheduled Scans Only)
- Stored on the `Scan` entity via a structured JSON field (`alert_config`):
  - `webhook_url: str | None`: Google Chat or Slack webhook URL.
  - `alert_on_failure: bool = True`: Triggers on unreachable host, port closed, or HTTP `5xx`.
  - `alert_on_ghost: bool = True`: Triggers when one or more hosts are classified as `Ghost`.
  - `alert_on_warning: bool = True`: Triggers on TLS certificates expiring $\le$ `tls_warning_days` or invalid certificates.
  - `alert_on_abort: bool = True`: Triggers if the scan run errors out or aborts.
  - `notify_on_healthy: bool = False`: Optional notification when all checks pass.

### 2.3 Dispatch Engine & Provider Formatting
- **Automatic Provider Detection:**
  - `chat.googleapis.com` $\rightarrow$ **Google Chat Cards v2** layout.
  - `hooks.slack.com` $\rightarrow$ **Slack Block Kit** layout.
  - Fallback $\rightarrow$ Standard JSON with formatted markdown text.
- **Message Content:**
  - **Header:** Status banner (`🔴 Alert: Scan Issues Detected` or `🟢 Scan Complete: All Healthy`)
  - **Schedule Name:** Human-readable scan title.
  - **Run ID & Timestamp (UTC)**
  - **Activated Triggers:** High-level list of activated triggers (e.g., `Host Down`, `Ghost Host`, `Expiring TLS Cert`) without individual host clutter.
  - **Summary Stats:** `Active`, `Warning`, `Failed`, `Ghost`, and `Void` counts.
  - **Interactive Button:** `[ View Results Table ]` resolving to `${APP_BASE_URL}/#/?run_id={id}`.
- **Reliability:**
  - Dispatched asynchronously upon scheduled scan completion (`COMPLETED`, `FAILED`, `ABORTED`).
  - Best-effort delivery with a 5s timeout: network failures or invalid webhook URLs are logged without crashing or failing the scan run.

### 2.4 Test Webhook Endpoint
- `POST /api/alerts/test`:
  - Accepts `{ "webhook_url": "..." }`.
  - Dispatches a lightweight verification ping ("🔔 Site Health Check - Webhook Connected Successfully").
  - Returns `{ "success": true }` or `{ "success": false, "error": "..." }`.

### 2.5 Frontend UI (`ScanConfigForm`)
- **Evaluation Settings Section:**
  - Visible in both `live` and `schedule` modes.
  - Inputs for Ghost Window (`7d`) and TLS Warning Threshold (`30` days).
- **Alerts Section:**
  - Visible only in `schedule` mode.
  - Webhook URL input.
  - Trigger checklist checkboxes.
  - `[ Test Webhook ]` button with loading spinner and status feedback toast.

---

## 3. Non-Functional Requirements & Security
- **Decoupled URL Resolution:** Dashboard table URL constructed from `APP_BASE_URL` in `.env` (default `http://localhost:5173`).
- **Zero Engine Bottleneck:** Alert evaluation runs in the background of the API scheduler after results are persisted, adding 0ms latency to probe routines.
- **Payload Safety:** Webhook URLs are validated against `https://` schemas.

---

## 4. Acceptance Criteria
- [ ] `Scan` and `ScanRun` SQLModel schemas persist `ghost_window`, `tls_warning_days`, and `alert_config`.
- [ ] Unit tests verify evaluation of each trigger condition (`failure`, `ghost`, `warning`, `abort`, `healthy`).
- [ ] Unit tests verify payload builders for both Google Chat Cards v2 and Slack Block Kit.
- [ ] API endpoint `POST /api/alerts/test` correctly verifies webhooks.
- [ ] Frontend form displays evaluation controls and alert checklist with `[ Test Webhook ]` action.

---

## 5. Out of Scope
- Multi-destination fan-out (sending to multiple different webhooks from one scan).
- Email / SMS / PagerDuty direct integrations.
- Alert suppression/silence schedules (handled by cron interval).
