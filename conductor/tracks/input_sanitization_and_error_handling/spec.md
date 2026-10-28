# Specification: Input Sanitization & Error Handling Workflow (`input_sanitization_and_error_handling`)

## 1. Overview
This track introduces pragmatic, non-rigid input sanitization and structured error handling across both the backend (FastAPI, Pydantic, SQLModel) and the frontend (React, Vite, TanStack Query).

The core objectives are:
1. **Hygiene & Validation:** Prevent invalid cron expressions, garbage port/target strings, and malformed settings from reaching the database or execution engine, while preserving existing valid workflows (such as port ranges `8080-8090` and CIDR blocks `192.168.1.0/24`).
2. **"Wait-Before-Leaving" Interaction Model:** Enforce an interaction pattern where clicking an action ("Create Schedule", "Save Changes", "Launch Live Scan", "Scan Now") waits for the backend response first. If an error occurs, the user stays on their editing view with all inputs preserved, and a human-readable bottom alert banner clearly explains what went wrong.
3. **Zero Regression & Stability:** Avoid model-inheritance traps on `ExecutionConfig` and `SystemExit` traps in `engine.parsing`, ensuring all 108 existing backend tests and 41 frontend tests continue to pass without regression.

---

## 2. Predicted Instabilities, Overreaches & UX Safeguards

1. **`ExecutionConfig` Inheritance Safeguard:**
   - `ScanResponse`, `ScanRunResponse`, and `LaunchRunRequest` all inherit from `ExecutionConfig`.
   - `ExecutionConfig()` is instantiated with empty defaults (`targets=[]`, `ports=[]`) in unit tests, DB snapshot deserialization, and `POST /api/runs` with `{"scan_id": "..."}` (where targets are loaded from the stored `Scan`).
   - **Rule:** `ExecutionConfig` must permit empty default lists `[]` when no items are passed, sanitizing and validating individual items when present. Non-empty `targets` (`min_length=1`) is enforced specifically on `ScanCreateRequest` and `ScanUpdateRequest` (when `targets` is provided), while `POST /api/runs` retains its existing `HTTP 400 ("Targets cannot be empty")` check when resolved targets are empty.
2. **Engine `@exit_on_error` (`SystemExit`) Safeguard:**
   - `engine.parsing.parse_ports` is decorated with `@exit_on_error`, which calls `sys.exit(1)` (`SystemExit`) on `ValueError`. Calling it directly inside FastAPI would crash the server worker.
   - **Rule:** Backend port validation must use a pure helper (without `sys.exit`) that validates integer ports (`1..65535`) and hyphenated port ranges (`"8080-8090"` where `1 <= start <= end <= 65535`).
3. **Preserving Port Ranges (`8080-8090`) & CIDR Suffixes (`/24`):**
   - **Rule:** Do not use naive `parseInt()` on port strings or naive `/` splitting on targets. Preserve valid range strings (`"8080-8090"`) in both frontend and backend (`ScanUpdateRequest.ports` updated to `list[str | int] | None`), and use `engine.parsing.validate_and_clean_target` so domain paths (`https://example.com/path` ➔ `example.com`) are stripped without harming CIDR suffixes (`192.168.1.0/24`).
4. **Empty `webhook_url: ""` Coercion:**
   - `DEFAULT_NEW_SCAN` sends `webhook_url: ""`.
   - **Rule:** Coerce empty or whitespace-only `webhook_url` strings to `None` before validating `^https?://.+`.
5. **Live Scan Confirmation Modal UX:**
   - If a launch fails on `LiveScanPage`, keeping the `"Confirm Live Scan"` popup open would block the user from editing the form behind the modal backdrop.
   - **Rule:** Await `POST /api/runs` while showing `"Launching..."` in the confirmation dialog. On success, close the dialog and attach to the SSE stream. On error, close the confirmation popup, do **not** start terminal streaming, and display the human-readable error in the bottom alert banner directly on `ScanConfigForm` so the user can immediately fix the fields.
6. **Stale Mutation Error Cleanup:**
   - **Rule:** Clear error state (`mutation.reset()`) whenever opening/closing the Create Schedule modal, switching inline Edit Schedule rows, or modifying form fields.

---

## 3. Functional Requirements

### 3.1 Backend Input Sanitization & Schema Validation
All updates apply to [`api/src/api/routers/scans.py`](file:///home/lucasse/Documents/site-health-check/api/src/api/routers/scans.py), [`api/src/api/routers/runs.py`](file:///home/lucasse/Documents/site-health-check/api/src/api/routers/runs.py), [`api/src/api/routers/views.py`](file:///home/lucasse/Documents/site-health-check/api/src/api/routers/views.py), and [`api/src/api/models.py`](file:///home/lucasse/Documents/site-health-check/api/src/api/models.py).

1. **Cron Expression Validation:**
   - In `ScanCreateRequest` and `ScanUpdateRequest`:
     - Strip leading and trailing whitespace; coerce empty string `""` to `None`.
     - If non-null, validate using `croniter.is_valid(expr)` and ensure 5 space-separated fields.
     - Reject invalid expressions with HTTP 422: `"Invalid cron expression format (expected 5 fields, e.g. '0 0 * * *')"`.
2. **Scan Name Validation:**
   - In `ScanCreateRequest` and `ScanUpdateRequest`:
     - Strip whitespace; reject empty names with HTTP 422: `"Scan name cannot be empty"`.
3. **Target Sanitization & Validation:**
   - In `ExecutionConfig` and `ScanUpdateRequest`:
     - Trim whitespace and discard blank entries.
     - Use `engine.parsing.validate_and_clean_target` on each target item to strip accidental `http://` or `https://` prefixes and trailing domain paths while validating Domain, IPv4, IP range (`10.0.0.1-10.0.0.50`), or CIDR syntax.
     - Reject invalid targets with HTTP 422 and the specific human-readable message from `validate_and_clean_target`.
   - In `ScanCreateRequest` and `ScanUpdateRequest` (when `targets` is provided):
     - Require at least 1 target (`"At least one target must be specified"`).
4. **Port Sanitization & Validation:**
   - Update `ScanUpdateRequest.ports` to `list[str | int] | None = None` to match `ExecutionConfig`.
   - Validate each port entry (without `@exit_on_error`):
     - Pure integer or numeric string (`80`, `"443"`): convert to `int` and check `1 <= port <= 65535`.
     - Hyphenated range string (`"8080-8090"`): verify `1 <= start <= end <= 65535`.
     - Reject invalid ports with HTTP 422: `"Port numbers must be between 1 and 65535 (or a valid range like '8080-8090')"`.
   - In `ScanCreateRequest` and `ScanUpdateRequest` (when `ports` is provided):
     - Require at least 1 port (`"At least one port must be specified"`).
5. **Evaluation, Flags & Alert Settings Sanitization:**
   - `ghost_window`: validate format matching `^\d+[smhd]$` (e.g. `7d`, `24h`, `30m`).
   - `tls_warning_days`: enforce `ge=0, le=3650`.
   - `AlertConfig.webhook_url`: strip whitespace, coerce `""` to `None`, and if non-null require `^https?://.+`.
6. **Saved Views Sanitization (`SavedViewCreate`):**
   - `name`: strip whitespace, enforce `min_length=1`.
   - `table_sort_dir`: if non-null, validate matching `^(asc|desc)$`.

### 3.2 Frontend "Wait-Before-Leaving" Interaction Model & UI Fixes
1. **API Error Extractor ([`frontend/src/lib/utils.ts`](file:///home/lucasse/Documents/site-health-check/frontend/src/lib/utils.ts)):**
   - Implement `extractApiErrorMessage(response: Response, fallback: string): Promise<string>` that parses FastAPI string details (`{"detail": "..."}`) and Pydantic validation arrays (`{"detail": [{"loc": [...], "msg": "..."}]}`), stripping Pydantic's `"Value error, "` prefix so messages read naturally in human language.
2. **Bottom Alert Banner & Input Safeguards ([`ScanConfigForm.tsx`](file:///home/lucasse/Documents/site-health-check/frontend/src/components/scans/ScanConfigForm.tsx)):**
   - Accept `isSubmitting?: boolean` and `errorMessage?: string | null` props.
   - Render a prominent **bottom alert banner** directly above the footer buttons whenever `errorMessage` is non-null.
   - Fix misleading target placeholder from `10.0.0.1-50` to `10.0.0.1-10.0.0.50`.
   - Clamp numeric flag steppers (`out_of_scope_depth >= 0`, `timeout >= 1`, `workers >= 1`, `rate >= 0.1`) and `tls_warning_days >= 0` so buttons cannot step into invalid negative numbers.
   - Disable `"▶ Launch Live Scan"` when `form.targets` is empty or `isScanning` / `isSubmitting` is true.
3. **Create & Edit Schedule Workflows ([`ScheduledScansPage.tsx`](file:///home/lucasse/Documents/site-health-check/frontend/src/pages/ScheduledScansPage.tsx)):**
   - Clicking "Create Schedule" or "Save Changes" disables the button (`"Creating..."` / `"Saving..."`) and awaits the backend response.
   - **On Error:** Stay in the Create modal or inline Edit view, preserve all form inputs, and display the human-readable error in the bottom alert banner.
   - **On Success:** Close the modal / exit edit mode and invalidate the `scans` query.
   - Reset mutation error state when opening/closing the modal or switching inline edit rows.
4. **Ad-Hoc Live Scan & "Scan Now" Workflows ([`LiveScanPage.tsx`](file:///home/lucasse/Documents/site-health-check/frontend/src/pages/LiveScanPage.tsx), [`ScheduledScansPage.tsx`](file:///home/lucasse/Documents/site-health-check/frontend/src/pages/ScheduledScansPage.tsx)):**
   - **Live Scan:** Clicking `"Launch Scan"` in the confirmation dialog shows `"Launching..."` and awaits `POST /api/runs`. On success, closes the dialog and connects to the SSE stream. On error, closes the confirmation dialog, does not start terminal streaming, and displays the bottom alert banner on `ScanConfigForm` with all inputs intact.
   - **"Scan Now":** Clicking `"Launch Scan"` in the Force Scheduled Scan dialog awaits `POST /api/runs`. On error, keeps the dialog open and renders a bottom alert banner inside the dialog without navigating away.

### 3.3 Backend Scheduler Resilience ([`api/src/api/services/scheduler.py`](file:///home/lucasse/Documents/site-health-check/api/src/api/services/scheduler.py))
- Catch `croniter.CroniterBadCronError` specifically and log a concise warning (`logger.warning(...)`) instead of full stack traces.

---

## 4. Acceptance Criteria

1. **Cron, Target & Port Validation:**
   - Invalid cron expressions (`"daily"`, `"* * *"`) return HTTP 422 with a clean human-readable message.
   - Targets with `http://` or `https://` are auto-cleaned; invalid targets return HTTP 422; CIDR blocks (`192.168.1.0/24`) and IP ranges (`10.0.0.1-10.0.0.50`) work seamlessly.
   - Numeric ports (`80`, `443`) and port ranges (`"8080-8090"`) succeed; out-of-range or garbage ports (`0`, `70000`, `"abc"`) return HTTP 422 without triggering `SystemExit`.
2. **Wait-Before-Leaving & Bottom Error Banner:**
   - Create/Edit Schedule errors keep the user on the form with inputs intact and render the bottom alert banner above the action buttons.
   - Live Scan launch errors close the confirmation overlay, do not trigger terminal streaming/countdown, and render the bottom alert banner on the form.
   - Re-opening modals or switching rows clears stale error banners.
3. **Zero Regressions:**
   - All 108 existing backend tests and 41 existing frontend tests pass alongside the new test cases.
