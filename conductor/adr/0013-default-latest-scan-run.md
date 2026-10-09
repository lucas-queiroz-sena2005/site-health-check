# 13. Default to Latest Scan Run

Date: 2026-09-17

## Status

Accepted

## Context

The backend results endpoint (`GET /api/results`) was initially designed to accept a `run_id` parameter to filter `HostState` records belonging to a specific scan execution. If `run_id` is omitted, the API naturally defaults to a `select(HostState)` without any scan run constraints, which effectively queries *every historical state* across all runs.

In the dashboard UX, we initially conceptualized a "Unified Global View" as the default state when no `run_id` is selected in the URL. The goal was to provide an aggregated pane of glass representing the latest known state of the entire infrastructure. However, computing a true aggregated view (e.g., using SQL window functions like `ROW_NUMBER() OVER (PARTITION BY ip_address ORDER BY started_at DESC)`) adds significant complexity and overhead to the database query, especially at scale.

## Decisions

### 1. Abandon "Unified Global View"
We will discard the concept of a "Unified Global View" that attempts to stitch together states across disparate scans. Instead, the dashboard will *always* display data belonging to a single, specific `ScanRun`.

### 2. Default to Absolute Latest Scan
If the user navigates to the dashboard without specifying a `run_id` in the URL parameter, the frontend will automatically fetch and select the absolute *latest* `ScanRun` (via `GET /api/runs?limit=1`), regardless of whether it was an ad-hoc or scheduled scan.

## Consequences

* **Positive**: The backend `/api/results` endpoint remains simple, fast, and unchanged (no complex window functions required).
* **Positive**: Users are immediately presented with the freshest data available upon opening the dashboard.
* **Negative**: The user cannot see an aggregated view of *all* their targets at once if those targets were split across multiple different scan schedules. They must view the results of those schedules individually.
