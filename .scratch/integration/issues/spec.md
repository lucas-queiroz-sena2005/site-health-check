## Problem Statement

The frontend currently uses static mock data, hardcoded state, and simulated API responses (e.g. `setInterval` for SSE) for Live Scans, Scheduled Scans, Scan Results, and Saved Views. The backend (FastAPI) implements most of the required endpoints to serve this data, but the frontend is completely disconnected from them. Certain expected endpoints are also missing from the backend to support the full feature set of the frontend UI (such as updating/deleting scans and listing/deleting views). 

## Solution

We will remove all mock files and simulated logic from the frontend and connect the UI directly to the backend FastAPI endpoints using React Query. We will also implement the missing endpoints in the backend to ensure a 1:1 mapping between the frontend's functional expectations and the backend's capabilities. 

## User Stories

1. As a user, I want to see real-time log outputs during a live scan, so that I know exactly what the scanning engine is doing.
2. As a user, I want to view actual scan results fetched from the database, so that I can see true historical scan data instead of mock targets.
3. As a user, I want to see the most recent scan run loaded by default when I visit the Host Table page, so that I have immediate context of the network state.
4. As a user, I want to create, list, edit, and delete scheduled scans, so that I can fully manage automated recurring scans.
5. As a user, I want to see the last run time, next run time, and run metrics for my scheduled scans, so that I can assess their performance and schedule at a glance.
6. As a user, I want to list all of my previously saved views, so that I can quickly return to a complex filter/sort state I care about.
7. As a user, I want to delete saved views I no longer need, so that my views list stays organized.

## Implementation Decisions

**Backend Changes (FastAPI)**:
- Add `PUT/PATCH /api/scans/{id}` and `DELETE /api/scans/{id}` endpoints to the `scans` router.
- Augment the `ScanResponse` model in the `scans` router to include operational metrics (`last_run`, `next_run`, `metrics` like duration and anomalies), pulling from associated `ScanRun` data.
- Add `GET /api/views` (list user views) and `DELETE /api/views/{id}` endpoints to the `views` router.

**Frontend Changes (React + Vite)**:
- Remove `mock-mid-size-result.json` and `mock-run-0` hardcoded references.
- Update `LiveScanPage.tsx` to connect to `GET /api/runs/{id}/stream` via native `EventSource` (Server-Sent Events) instead of local `setInterval`.
- Update `useScanResults.ts` to fetch from `GET /api/runs/{id}/results` using React Query.
- Update `HostTablePage.tsx` to fetch the initial run ID using `GET /api/runs?limit=1`.
- Update `ScheduledScansPage.tsx` to use React Query mutations against the newly created backend endpoints (`PUT/DELETE /api/scans/{id}`).
- Update the views management in `HostTablePage.tsx` to fetch available views dynamically via `GET /api/views` and delete them via `DELETE /api/views/{id}`.

## Testing Decisions

- **Testing Seams**: The boundary between frontend and backend will be tested using the FastAPI `TestClient` routes.
- **Backend Testing**: Add `pytest` cases for the new `/scans` and `/views` endpoints to ensure they handle CRUD operations correctly and return 404s for non-existent IDs.
- **Frontend Testing**: Ensure React Query hooks handle loading and error states properly when the backend returns data or HTTP errors.

## Out of Scope

- Implementing complex RBAC/authorization for views and scans (assume single-tenant or implicit user for now).
- Updating the actual Python scanning engine logic.

## Further Notes

- The backend `ScanResponse` requires `last_run`, `next_run` logic. `next_run` can be calculated using `croniter` based on the `cron_expression`. `last_run` can be fetched by querying the most recent `ScanRun` for the scan ID.
