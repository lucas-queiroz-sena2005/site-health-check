# Implementation Plan: Input Sanitization & Error Handling Workflow (`input_sanitization_and_error_handling`)

## Phase 1: Backend Sanitization, Validation & Scheduler Resilience (TDD) [checkpoint: 4b791cb]
- [x] Task: Write failing backend tests for cron, target, port, and setting validation while guarding against inheritance regressions (Red Phase) 72cb140
  - [x] Add unit tests in `api/tests/test_api_scans.py` asserting invalid cron expressions (`"daily"`, `"* * *"`, `"invalid"`) return HTTP 422 with a human-readable message, while valid 5-field cron expressions (`0 0 * * *`, `*/15 * * * *`) and `None`/`""` succeed
  - [x] Add unit tests asserting empty scan names or empty scan targets/ports on `POST /api/scans` and `PUT /api/scans/{id}` return HTTP 422
  - [x] Add unit tests asserting targets with `http://` or `https://` prefixes and domain paths (`https://example.com/login`) are auto-cleaned to `example.com`, while CIDR blocks (`192.168.1.0/24`) and IP ranges (`10.0.0.1-10.0.0.50`) are preserved and invalid targets (`"999.999.999.999"`, `"example.com:8080"`) return HTTP 422
  - [x] Add unit tests asserting valid integer ports (`80`, `443`) and port range strings (`"8080-8090"`) succeed on both create (`POST`), replace (`PUT`), and partial update (`PATCH`), while invalid ports (`0`, `70000`, `"abc"`, `"9000-8000"`) return HTTP 422 without triggering `SystemExit`
  - [x] Add unit tests asserting `ghost_window` must match `^\d+[smhd]$`, `tls_warning_days >= 0`, and `alert_config.webhook_url` coerces `""` to `None` while rejecting invalid non-HTTP strings
  - [x] Add unit tests in `api/tests/test_api_scheduler.py` verifying `check_and_run_scheduled_scans` catches `CroniterBadCronError` and logs a concise warning without unhandled tracebacks
- [x] Task: Implement backend validators, sanitizers, and scheduler resilience (Green & Refactor Phase) 4b791cb
  - [x] Keep `ExecutionConfig` default `targets=[]` and `ports=[]` permissive so `ExecutionConfig()`, `ScanResponse`, `ScanRunResponse`, and `POST /api/runs` (`{"scan_id": "..."}` and `{"targets": []}` returning 400) remain 100% backward-compatible
  - [x] Implement pure target & port sanitization/validation helpers in `api/src/api/models.py` (reusing `engine.parsing.validate_and_clean_target` and validating port integers/ranges without `@exit_on_error`)
  - [x] Add `ghost_window`, `tls_warning_days`, and `AlertConfig.webhook_url` validators in `api/src/api/models.py`
  - [x] Add `name`, `cron_expression`, and non-empty `targets`/`ports` validators on `ScanCreateRequest` and `ScanUpdateRequest` (updating `ScanUpdateRequest.ports` to `list[str | int] | None`) in `api/src/api/routers/scans.py`
  - [x] Add `name` and `table_sort_dir` validators on `SavedViewCreate` in `api/src/api/routers/views.py`
  - [x] Update `api/src/api/services/scheduler.py` to catch `croniter.CroniterBadCronError` with `logger.warning`
  - [x] Run `.venv/bin/pytest api/` and verify all 108 existing tests + new tests pass
- [x] Task: Phase Verification & Checkpoint (Refer to `workflow.md`) 4b791cb

---

## Phase 2: Frontend "Wait-Before-Leaving" Interaction Pattern, Bottom Alert Banner & UI Polish (TDD)
- [x] Task: Write failing frontend tests for API error extraction, bottom alert banners, and wait-before-leaving behavior (Red Phase) 54a7004
  - [x] Add unit tests in `frontend/src/lib/__tests__/utils.test.ts` for `extractApiErrorMessage` verifying FastAPI string details and Pydantic 422 validation error arrays are converted into clean human-readable messages (stripping `"Value error, "` prefixes)
  - [x] Add component tests in `frontend/src/pages/__tests__/ScheduledScansPage.test.tsx` verifying:
    - [x] Clicking "Create Schedule" or "Save Changes" disables the submit button and waits for the server response
    - [x] On server error (e.g. 422 invalid cron or target), the dialog/edit view stays open, user inputs are preserved, and the bottom alert banner displays the human-readable error above the action buttons
    - [x] Re-opening the Create modal or switching inline edit rows clears any stale error banner
    - [x] On server success, the modal/edit view closes and the table updates
  - [x] Add component tests in `frontend/src/pages/__tests__/LiveScanPage.test.tsx` verifying:
    - [x] The `"▶ Launch Live Scan"` button is disabled when targets are empty
    - [x] When `POST /api/runs` fails, the confirmation dialog closes so the form is not blocked, terminal streaming does not start, and the bottom alert banner renders on `ScanConfigForm` with inputs intact
- [~] Task: Implement error extraction utility, bottom alert banners, and "Wait-Before-Leaving" workflows (Green & Refactor Phase)
  - [ ] Implement `extractApiErrorMessage` in `frontend/src/lib/utils.ts`
  - [ ] Update `ScanConfigForm.tsx`:
    - [ ] Accept `isSubmitting?: boolean` and `errorMessage?: string | null` props and render the bottom alert banner directly above the footer buttons
    - [ ] Fix target placeholder from `10.0.0.1-50` to `10.0.0.1-10.0.0.50`
    - [ ] Clamp numeric flag steppers (`out_of_scope_depth >= 0`, `timeout >= 1`, `workers >= 1`, `rate >= 0.1`) and `tls_warning_days >= 0`
    - [ ] Disable `"▶ Launch Live Scan"` when targets are empty or `isSubmitting`/`isScanning` is true
    - [ ] In live mode, await `onSave(form)` inside the confirmation dialog before closing so `"Launching..."` is shown during the request
  - [ ] Update `ScheduledScansPage.tsx` to use `extractApiErrorMessage`, await mutations, keep modals/edit views open on error, pass `errorMessage` and `isSubmitting` to `ScanConfigForm`, reset mutation errors on modal toggle/row change, and show errors inside the `"Force Scheduled Scan"` dialog if `"Scan Now"` fails
  - [ ] Update `LiveScanPage.tsx` to use `extractApiErrorMessage`, surface launch errors in `ScanConfigForm`'s bottom alert banner without entering the finished/redirect terminal state, and check `res.ok` on `handleStop`
  - [ ] Run `cd frontend && env -u LD_LIBRARY_PATH npx vitest run` and verify all existing + new frontend tests pass
- [ ] Task: Phase Verification & Checkpoint (Refer to `workflow.md`)

---

## Phase 3: Full End-to-End Verification & Regression Safety
- [ ] Task: Full stack test suite and build verification
  - [ ] Run full backend `pytest` suite (`.venv/bin/pytest api/ engine/`)
  - [ ] Run full frontend `vitest` suite (`cd frontend && env -u LD_LIBRARY_PATH npx vitest run`)
  - [ ] Run production frontend build (`cd frontend && env -u LD_LIBRARY_PATH npm run build`)
- [ ] Task: Phase Verification & Checkpoint (Refer to `workflow.md`)
