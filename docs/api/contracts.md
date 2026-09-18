# FastAPI Data Contracts & Routines

This document defines the strict Request/Response JSON schemas and the internal "Routines" (order of operations) FastAPI will execute for each core endpoint. This serves as our functional spec before writing code.

---

## 1. Unified Scan Creator (Ad-Hoc & Scheduled)
**Endpoint:** `POST /api/scans` (scheduled) or `POST /api/runs/launch` (ad-hoc)
**Purpose:** A single endpoint to either launch a scan immediately OR save it as a cron schedule. It strictly separates API metadata from the actual Engine JSON payload.

### Request Schema
```json
{
  "api_metadata": {
    "name": "Physics Dept Security Scan",
    "cron_expression": null, // If null, runs immediately. If "* * * * *", saves as schedule.
    "classification_name": "Physics" // Used by FastAPI to tag results
  },
  "engine_payload": [
    {
      "target": "10.0.0.0/24",
      "ports": [443, 80],
      "flags": {
        "check_tcp": true,
        "check_http": true,
        "recursive_san_check": false
      }
    }
  ]
}
```
*(Note on `engine_payload`: This inner array is the exact `TaskConfig` JSON structure that `engine.py` currently builds internally from CLI arguments. By passing it explicitly, the Engine doesn't need to know about "schedules" or "classifications" at all—it just executes the raw tasks).*

### Routine (FastAPI Internal Logic)
1. **Route by Cron:** Check if `api_metadata.cron_expression` exists.
2. **If Scheduled (Cron provided):**
   - Save the `engine_payload` into the `policies` and `classifications` tables.
   - Create a `Schedule` row linking them.
   - **Return 201 Created:** `{ "schedule_id": "uuid-5678" }`
3. **If Ad-Hoc (Cron is null):**
   - Create a `ScanRun` row in SQLite with `status="RUNNING"`.
   - Spawn the subprocess: `python -m engine.cli <targets> ...`
   - **Return 202 Accepted:** `{ "id": "uuid-1234", "stream_url": "/api/runs/uuid-1234/stream" }`

---

## 2. Real-Time Engine Feed
**Endpoint:** `GET /api/runs/{id}/stream`
**Purpose:** Streams the `stdout` of the CLI subprocess directly to the UI via Server-Sent Events (SSE).

### Routine
1. **Connect:** Accept SSE connection from the frontend via `EventSourceResponse`.
2. **Attach:** Find the running `subprocess` attached to the `scan_run_id`.
3. **Stream:** Read `stdout` line-by-line asynchronously and push to the stream.
4. **Cleanup:** When the subprocess exits (EOF), close the stream.
5. **Post-Processing:** Once closed, FastAPI reads the final output JSON from the CLI, calculates metrics, and updates the `ScanRun` row in DB to `COMPLETED`.
