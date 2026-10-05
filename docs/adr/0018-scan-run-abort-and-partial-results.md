# ADR 0018: ScanRun Abort Lifecycle & Partial Results Policy

## Status

Accepted — Roadmap phase 1 (implemented together with ADR 0017).

## Context

Once a ScanRun starts, nothing can stop it. The engine subprocess handle is a local
variable inside `run_engine_cli`, and the LiveScan "Cancel" button only closes the SSE
connection in the browser while the engine keeps running. ADR 0015 already reserved
`POST /api/runs/{id}/abort` but never defined it.

Other related gaps:
- If the API restarts, runs stay `RUNNING` forever and the scheduler never triggers
  that Scan again, because it skips scans with an active run.
- When a run fails, everything it computed is thrown away.

## Decision

1. **New terminal status `ABORTED`.** Terminal set: `COMPLETED | FAILED | ABORTED`.

2. **`POST /api/runs/{id}/abort`**
   - `202` if the run is `PENDING`/`RUNNING`, `404` if the run is unknown, `409` if it
     is already terminal.
   - The API keeps a registry `app.state.processes[run_id] -> Process`. It sends
     `SIGTERM` and escalates to `SIGKILL` after a 10 s grace period.
   - The run ends as `ABORTED` whenever an abort was requested, whatever the exit code.

3. **Engine graceful stop.** On `SIGTERM`/`SIGINT` the engine stops dequeuing tasks,
   cancels in-flight workers, writes the `summary` line with `status: "aborted"`,
   flushes stdout and exits `143`/`130`. Terminal users get the same behaviour
   with Ctrl+C.

4. **Partial results are kept.** Thanks to ADR 0017 the data is already ingested.
   `ABORTED` and `FAILED` runs keep their rows, and `metrics_json.partial = true`.

5. **Reconciliation.** At API startup, runs still `PENDING`/`RUNNING` become `FAILED`
   with `metrics_json.reason = "api_restart"`. At API shutdown, every registered engine
   process is terminated.

6. **Runner extraction.** `run_engine_cli` moves from `routers/runs.py` to
   `services/runner.py`. Today `scheduler.py` imports it from a router, which is
   backwards.

## Consequences

- **Positive:** Long /16 runs can be stopped from the UI. A crash no longer means
  zero data.
- **Important:** Partial runs must **not** serve as a baseline for historical diffing
  (ADR 0004). Otherwise unreached IPs show up as false "ghosts". The default
  "latest run" (ADR 0013) must mean *latest `COMPLETED` run*. The dashboard shows a
  "partial results" banner when the user explicitly opens an `ABORTED`/`FAILED` run.
- **Frontend:**
  - A real **Stop** button while scanning, wired to the abort endpoint.
  - The current "Cancel" is renamed **Detach**, since it only closes the log stream.
  - New `ABORTED` badge in the run lists.
  - Regenerate the OpenAPI types (ADR 0016).
- **Negative:** The process registry lives in memory, so abort only works in the
  single API process that spawned the engine. When a Broker is introduced, abort
  becomes a control message instead.
- **Scheduler:** An aborted scheduled run does not retrigger. The next run happens at
  the next cron tick.
