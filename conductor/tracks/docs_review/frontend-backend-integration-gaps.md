# Frontend vs Backend Integration Gap Analysis

This document outlines the differences between what the frontend expects/mocks and what the backend (FastAPI) provides/expects, based on primary source code analysis.

## 1. Live Scans and Log Streaming
**Where frontend is not utilizing backend features:**
- **Live Scans**: The frontend `LiveScanPage` (`frontend/src/pages/LiveScanPage.tsx`) simulates a live scan by randomly generating console logs (e.g. `[INFO] Resolving DNS...`) in local state using `setInterval`.
- **Backend Capability**: The backend fully supports real live scans. Calling `POST /api/runs/launch` (`api/src/api/routers/runs.py`) starts the background Python engine process. The client can then connect to `GET /api/runs/{id}/stream` to consume real-time Server-Sent Events (SSE) directly from the engine's stdout. The frontend is completely ignoring this API.

## 2. Scan Results and Run History
**Where frontend is not utilizing backend features:**
- **Fetching Results**: The frontend's `useScanResults` hook (`frontend/src/features/scans/api/useScanResults.ts`) ignores the passed `runId` and fetches static mock data from a local file (`/mock-mid-size-result.json`). It even includes a comment noting that the mock engine file requires mapping to match the `HostState[]` format that the API returns. The frontend should instead be hitting `GET /api/runs/{id}/results` or `GET /api/results?run_id=...` which the backend properly supplies (`api/src/api/routers/results.py`, `api/src/api/routers/runs.py`).
- **Initial Run Load**: In `HostTablePage.tsx`, there is a `TODO` to use `fetch('/api/runs?limit=1')` to find the most recent run ID. It currently hardcodes `mock-run-0`. The backend implements `GET /api/runs` exactly for this purpose.

## 3. Scheduled Scans
**Where API lacks features frontend expects:**
- **Update and Delete Scans**: The frontend UI in `ScheduledScansPage.tsx` expects to edit (`handleSaveInline`) and delete (`handleDelete`) scheduled scans. However, the backend's `scans` router (`api/src/api/routers/scans.py`) only implements `POST /api/scans` (create) and `GET /api/scans` (list). There are no `PUT/PATCH /api/scans/{id}` or `DELETE /api/scans/{id}` endpoints.
- **Run Metrics in List**: The frontend's scheduled scan table expects each scan to display `lastRun`, `nextRun`, and `metrics` (such as duration and anomalies found). The backend's `ScanResponse` object (`scans.py`) only returns configuration properties (targets, cron expression, flags) and lacks these operational metrics.

**Where frontend is not utilizing backend features:**
- **List and Create**: The frontend manages the list of scheduled scans entirely in hardcoded local state, despite the backend having fully functional endpoints to create and list them.

## 4. Saved Views
**Where API lacks features frontend expects:**
- **List All Views**: The frontend (`HostTablePage.tsx`) manages standard and user-saved views. It uses `POST /api/views` to create views and `GET /api/views/{id}` to load them from a URL parameter. However, the backend (`api/src/api/routers/views.py`) lacks a `GET /api/views` endpoint to list a user's previously saved views. As a result, the frontend is forced to rely on a hardcoded list of standard views in local state.
- **Delete Views**: The frontend implements a `handleDeleteView` function, but since there is no `DELETE /api/views/{id}` endpoint provided by the backend, it only removes the view from the local React state.
