Status: ready-for-agent

## Problem Statement

When scanning large CIDR blocks (e.g., /16), the engine must keep the entire target list and resulting `IpState`s in memory for the duration of the run. Currently, the engine only returns its results when the process exits successfully, outputting a massive JSON payload at the very end. If a scan crashes or is aborted by the user mid-way through a 30-minute run, all data gathered up to that point is lost. Furthermore, mixing human-readable logs and pretty-printed JSON payloads on `stdout` makes it impossible to pipe engine output to CLI tools like `jq`, or progressively ingest data via the API. From the API and UI perspective, there is no way to stop a running scan; clicking "Cancel" in the UI only detaches the log stream while the engine continues probing.

## Solution

The engine's output contract will be modified to stream partial results (NDJSON deltas) to `stdout` the moment a network probe finishes, and send all logs to `stderr`. The API will concurrently ingest these NDJSON deltas, upserting them into the database while the engine is running. To support stopping a long-running scan, the engine will handle `SIGTERM`/`SIGINT` gracefully by cancelling workers, outputting a final summary line, and exiting cleanly. The API will introduce a new `/api/runs/{id}/abort` endpoint to send this `SIGTERM` to the engine subprocess, marking the `ScanRun` as `ABORTED`. Finally, the frontend will show a true "Stop" button and indicate when a run has "partial results", ensuring that partial runs are not used for historical diffing baselines.

## User Stories

1. As an SRE, I want to see partial scan results in the UI while a long-running scan is executing, so that I don't have to wait 30 minutes to know if the first few targets are responding correctly.
2. As an SRE, I want to be able to stop a running scan from the UI, so that I can cancel a mistaken `/16` scan without it hogging cluster resources or raising datacenter alerts.
3. As a developer using the CLI, I want the engine to output NDJSON deltas to `stdout` and logs to `stderr`, so that I can pipe the output to `jq` for real-time analysis.
4. As a developer using the CLI, I want to hit `Ctrl+C` to abort a local scan and still retain a valid JSON lines file of everything probed up to that point, so that my time isn't wasted by early termination.
5. As an SRE reviewing historical diffs, I want aborted or failed scans to be excluded from the diff baseline, so that unreachable IPs from a cancelled scan are not falsely flagged as "Ghost" nodes in the next scan.
6. As a system operator, if the API server crashes and restarts, I want pending or running scans to be automatically marked as failed, so that the scheduler doesn't permanently skip them on the assumption they are still running.
7. As an API user, I want the Server-Sent Events (SSE) stream to terminate correctly and gracefully when a scan is aborted, so that the frontend doesn't hang waiting for logs that will never arrive.

## Implementation Decisions

- **NDJSON Deltas:** The engine will replace its global `master_state` tracking with immediate `print(json.dumps(...))` to `stdout` for each completed probe. A summary line will always be the last line outputted.
- **Log Routing:** All existing `print` statements used for logging inside the engine will be migrated to the Python `logging` module, configured to output strictly to `stderr`. 
- **Graceful Shutdown:** A signal handler for `SIGINT` and `SIGTERM` will be added to the engine. It will clear the worker queue, cancel active workers, write the aborted `summary` NDJSON line, and exit with code `130` or `143`.
- **API Runner Extraction:** `run_engine_cli` will be moved from `api/routers/runs.py` to `api/services/runner.py`.
- **Concurrent DB Ingestion:** The API will use `asyncio.to_thread` for batched upsert ingestion of the `stdout` pipe, while simultaneously reading `stderr` for SSE streaming. The existing `_ingest_results` logic will be rewritten to upsert by natural key (e.g., `(run_id, ip)`).
- **Process Registry:** The API will track running engine processes in a memory registry (`app.state.processes[run_id]`). The new `POST /api/runs/{id}/abort` endpoint will look up the `Process` handle and issue a `SIGTERM`, falling back to `SIGKILL` after 10 seconds.
- **Terminal Status:** Add `ABORTED` to `ScanRunStatus`. `POST /api/runs/{id}/abort` will yield `202 Accepted`, `404 Not Found`, or `409 Conflict` (if already terminal).
- **Reconciliation:** At API startup, any `ScanRun` in `PENDING` or `RUNNING` state will be updated to `FAILED` with `metrics_json.reason = "api_restart"`.
- **UI Changes:** The current "Cancel" button in LiveScan will be renamed to "Detach". A new "Stop" button will be wired to the abort endpoint. An `ABORTED` status badge will be added, and an explicit "partial results" banner will appear on runs that are not `COMPLETED`.
- **Schema & Defaults:** Historical diff endpoints and default latest run logic will be updated to strictly filter for `COMPLETED` runs only.

## Testing Decisions

The testing strategy will focus on a few key high-level seams to verify behavior without coupling tests to implementation details:

- **Engine CLI Seam:** A subprocess test against `engine.cli` simulating a small scan and sending a `SIGTERM` mid-way. The test will verify that the process exits with `143`, that `stderr` contains logs, and that `stdout` contains valid NDJSON deltas followed by a `status: aborted` summary line.
- **API Abort Endpoint Seam:** An API integration test using the FastAPI `TestClient`. It will launch a scan via `POST /runs/launch`, wait for it to reach `RUNNING`, issue a `POST /runs/{id}/abort`, and verify the final run status becomes `ABORTED` and the process exits.
- **API Ingestion Seam:** Unit tests for the DB ingestion logic. We will mock the `stdout` stream with synthetic NDJSON deltas (including overlapping data for the same IP) and assert that the upsert logic correctly merges the data into `HostState`, `PortState`, `TlsCertificate`, and `HttpRoutingCheck` rows.
- **API Reconciliation Seam:** A test initializing the API with mocked pending/running runs in the DB to ensure they transition to `FAILED`.

## Out of Scope

- Alembic migrations for unique DB constraints. We will reset the dev DB instead since migrations are not yet configured.
- Streaming data over a message broker (e.g. RabbitMQ). This phase assumes the engine remains a local subprocess managed by the API.
- Re-triggering aborted scheduled runs automatically. They will wait for the next cron tick.
- Full multi-process engine splitting per CIDR slice, or crash resume via `--exclude-from`.

## Further Notes

- The unique constraints required for `upsert` ingestion will require the development SQLite database to be rebuilt from scratch as there are no schema migrations in place.
- The Engine's memory footprint reduction is a side-effect of this NDJSON streaming, preparing us nicely for Phase 5 (/16 scale), but we will also implement `--rate` limiting in Phase 3 to properly cap the connection concurrency.
