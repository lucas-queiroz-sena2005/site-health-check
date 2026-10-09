# Frontend Codebase & Documentation Audit Report

We conducted an in-depth review comparing the actual state of the frontend codebase in `/home/lucasse/Documents/site-health-check/frontend` against the existing documentation (`CONTEXT.md`, ADRs under `docs/adr/`, architecture docs in `docs/`, and `.scratch/` tickets).

---

## 1. Actual State of Frontend Code vs. Documented Architecture

### A. Real Application (`frontend/`) vs. Legacy Prototype (`frontend-prototype/`)
* **Reality**: The active frontend is a modern TypeScript Single Page Application in `/frontend` built with **React 19.3**, **Vite 8.2**, **Tailwind CSS v4.3**, **@tanstack/react-query v5**, and **Base UI / shadcn** primitives.
* **The Legacy Trap**: The repository still contains `/frontend-prototype`, which is a legacy React 18 prototype centered around `@xyflow/react` (React Flow).
* **Docker / Infra Drift**: `docker-compose.yml` (line 5) and the root `README.md` (lines 3, 18) **still build and point to `./frontend-prototype`** on port `8080` (`container_name: site-health-check-prototype`) rather than `./frontend`. `frontend/` doesn't even contain a `Dockerfile`.

### B. Core UI Architecture: Hierarchical Tree Table vs. DAG Topology
* **Reality**: The primary view (`HostTablePage.tsx`) is a **Hierarchical Tree Table** rendered by custom components (`HierarchicalTable`, `RenderTreeNode`, `DetailsPanel`, `TableContext`). It implements:
  1. **Reactive Visual Tree Compression (ADR 0012)**: Unary child chains are compressed at render time inside `RenderTreeNode.tsx` (`IP ➔ Port ➔ HTTP`) without mutating data structures or IDs.
  2. **Filter Immunity & Opt-out Overrides (ADR 0011 & ADR 0012)**: Prevents parents from losing filter anchors, while child nodes can opt out via inherited clear actions.
  3. **Multi-Block Status Badges**: Dynamic bottom-up status aggregation (`[ Active ]`, `[ Warning ]`, `[ Failed ]`, `[ Ghost ]`, `[ Void ]`) with deep filtering.
  4. **Dynamic Void Node Generation**: `buildTree.ts` calculates `total_hosts - hostNodes.length` to render void space rows.
  5. **Decoupled Details Panel**: Toggleable via a dedicated `{}` button on every row, aggregating cumulative payload cards.
* **Documentation Drift**: ADR 0007 and earlier docs envisioned a visual node canvas using React Flow (`@xyflow/react`) with animated cross-links. That DAG approach was completely abandoned in favor of the hierarchical table.

### C. Frontend-Backend Integration Gaps (Mock vs. Live)
Although FastAPI provides functional backend endpoints, several frontend features are currently operating on mock data:
1. **Results Fetching (`useScanResults.ts:9-16`)**: Ignores `runId` and fetches `/mock-mid-size-result.json` from the public directory instead of hitting `GET /api/results` or `GET /api/runs/{id}/results`.
2. **Latest Run Auto-Selection (`HostTablePage.tsx:121-124`)**: Has a `TODO` to call `GET /api/runs?limit=1` per ADR 0013, but currently hardcodes `mock-run-0`.
3. **Live Scan Streaming (`LiveScanPage.tsx:26-85`)**: Simulates engine logs using local `setInterval` with hardcoded arrays instead of dispatching `POST /api/runs/launch` and streaming SSE logs from `GET /api/runs/{id}/stream`.
4. **Scheduled Scans (`ScheduledScansPage.tsx:35-81`)**: Manages schedules in local React component state instead of querying `GET /api/scans` and `POST /api/scans`.
5. **Saved Views (`HostTablePage.tsx:141-230`)**: Correctly integrates with `POST /api/views` and `GET /api/views/{id}`, but relies on hardcoded default views because the backend lacks `GET /api/views` (list) and `DELETE /api/views/{id}`.

---

## 2. ADRs in Need of Amendment

### 1. ADR 0007: `0007-frontend-ux-topology-and-sorting.md` (Needs Significant Amendment)
* **Status**: Currently marked `Accepted`.
* **Discrepancies**:
  * **Section 2 (DAG Cross-Linking in Topology Views via React Flow)**: Never implemented in production `frontend/`. React Flow was dropped in favor of the hierarchical tree table.
  * **Section 3 (Structural Path Compression Protection)**: Prohibited CIDR / Target nodes from compressing. This rule was **explicitly superseded by ADR 0011 and ADR 0012**, which permit structural nodes to compress dynamically if they reduce to a single child.
  * **Section 5 (File-Manager Style Sorting)**: Mentions a "dedicated floating configuration panel" in topology views; in the real app, sorting is embedded directly in table headers.
  * **Section 7 (Smart Heuristic Classifications)**: Auto-grouping IPs based on SANs and HTTP domains was **explicitly discarded for MVP by ADR 0010**.
* **Recommendation**: Amend ADR 0007's status to **`Partially Superseded / Amended`**. Add explicit cross-references linking Sections 2, 3, and 7 to ADR 0010, ADR 0011, and ADR 0012.

### 2. ADR 0009: `0009-unified-target-merging.md` (Needs Supersession Note)
* **Status**: Proposes FastAPI merging scan runs dynamically into a "Unified Target View" with data hierarchy invalidation.
* **Discrepancy**: **ADR 0013 (`0013-default-latest-scan-run.md`) explicitly abandoned this**:
  > *"1. Abandon 'Unified Global View': We will discard the concept of a 'Unified Global View' that attempts to stitch together states across disparate scans. Instead, the dashboard will always display data belonging to a single, specific ScanRun."*
* **Recommendation**: Mark ADR 0009 as **`Superseded by ADR 0013`** (or `Deferred`), and update `CONTEXT.md` accordingly.

### 3. ADR 0005: `0005-saved-views-and-read-time-filtering.md` (Needs Clarification)
* While valid, it does not document the URL schema (`?run=<id>&view=<id>`) or how fallback views should behave in the absence of a backend listing endpoint (`GET /api/views`).

---

## 3. Recommended New ADRs for Recent Architecture & Patterns

### ADR Candidate 1: Canonical Hierarchical Tree-Table Architecture
* **Context**: `frontend-prototype` attempted a 2D node-graph canvas using React Flow (`@xyflow/react`). However, dense infrastructure CIDRs (/16 to /24) with hundreds of ports caused canvas clutter, erratic edge routing, and poor readability.
* **Decision**: Establish the **Hierarchical Tree Table** (`HierarchicalTable`) as the canonical dashboard view. Codify the visual tree hierarchy (`GlobalRoot ➔ Target/CIDR ➔ Host ➔ Port ➔ HTTP Check`), sorting semantics, and marquee text overflow patterns.

### ADR Candidate 2: Server-Sent Events (SSE) for Real-Time Execution Streaming
* **Context**: Early documentation (`docs/api/contracts.md`, `docs/05-control-plane-architecture.md`) specified WebSockets (`WS /api/jobs/{id}/stream`).
* **Decision**: Backend and frontend architecture transitioned to **Server-Sent Events (SSE)** via `fastapi.sse.EventSourceResponse` at `GET /api/runs/{id}/stream`. Document why SSE was chosen over WebSockets (unidirectional log feed, native HTTP/2 multiplexing, automatic reconnection, stateless connection lifecycle).

### ADR Candidate 3: Execution Config Schema Synchronization (Backend Pydantic -> UI Forms)
* **Context**: The backend exposes `GET /api/schemas/schedule` (auto-generated from Pydantic `ExecutionConfig`), yet `ScanConfigForm.tsx` currently maintains a duplicate hardcoded `EXECUTION_FLAGS_SCHEMA`.
* **Decision**: Formalize whether the frontend form should dynamically render from the OpenAPI/JSON schema endpoint or maintain a type-safe static schema mapped to Pydantic field names.

### ADR Candidate 4: Modern Frontend Tech Stack & Design System Baseline
* **Context**: `docs/06-mvp-implementation.md` originally prescribed Vanilla CSS / CSS Modules and `App.jsx`.
* **Decision**: Formalize the adoption of **React 19**, **Vite**, **Tailwind CSS v4**, **Base UI / Radix primitives**, **TanStack Query**, and dark-mode CSS variable token architecture.

---

## 4. Non-ADR Documents: Outdated, Legacy, or Missing

| Document | Current Issue / Inconsistency | Action Required |
| :--- | :--- | :--- |
| **`CONTEXT.md`** | 1. ADR log stops at ADR 0009; missing ADR 0010, 0011, 0012, 0013.<br>2. ADR 0001 is listed as `Single Context & Lightweight ADRs`, but file is `0001-ip-first-output-hierarchy.md`.<br>3. Glossary still defines `Unified Target View` and `Data Hierarchy Invalidation`, which ADR 0013 abandoned. | Update Architectural Decisions Log to list ADRs 0001–0013 accurately; deprecate/clarify "Unified Target View" definition. |
| **Root `README.md`** | References `frontend-prototype` running on port 8080; zero instructions for running or installing `frontend/`. | Update to document `frontend/` (`bun dev` or `npm run dev`), port mapping, and build workflow. |
| **`docker-compose.yml`** | Still builds `./frontend-prototype` as `site-health-check-prototype` on port 8080. | Update service to build `./frontend` and add a `Dockerfile` to `frontend/`. |
| **`frontend/README.md`** | Untouched default Vite template boilerplate (`# React + TypeScript + Vite`). | Replace with project-specific frontend documentation (features, routing, state, testing). |
| **`docs/01-architecture.md`** | States tool is strictly CLI-first, *"NOT a Visual Dashboard"* and *"NOT a Background Daemon"*. | Add an update header explaining that Phase 2 introduced the FastAPI control plane and React UI. |
| **`docs/05-control-plane-architecture.md`** | Mentions "Flask API" spawning subprocesses, pushing data via WebSockets, and claims ad-hoc scans bypass SQLite. | Update to reflect FastAPI, SSE streaming, and SQLite `ScanRun` persistence. |
| **`docs/06-mvp-implementation.md`** | Mentions Vanilla CSS / CSS Modules, `App.jsx`, reading static `results.json`, and `react-flow` components (`<TopologyGraph />`). | Mark as historical MVP specification or update to reflect current implementation. |
| **`docs/api/contracts.md`** | Specifies WebSocket `WS /api/jobs/{id}/stream` and a `POST /api/scans` payload structure that differs from current `ExecutionConfig` and SSE endpoint. | Update contracts to match `api/src/api/routers/runs.py` and `scans.py`. |
| **`frontend-prototype/`** | Outdated prototype directory still in repo root, causing confusion with Docker and docs. | Move to `docs/archive/` or delete, and decouple from `docker-compose.yml`. |

---

### Summary Checklist for Follow-up Actions
- [ ] Amend ADR 0007 (annotate superseded sections: React Flow DAG, CIDR compression block, Heuristic Classifications).
- [ ] Amend ADR 0009 (mark as superseded/deferred by ADR 0013).
- [ ] Draft new ADR for **Hierarchical Tree Table UI Paradigm** and **SSE Log Streaming**.
- [ ] Sync `CONTEXT.md` (add ADR 0010–0013, fix ADR 0001 name, update vocabulary).
- [ ] Update `docker-compose.yml` and root `README.md` to point to `frontend/` instead of `frontend-prototype/`.
- [ ] Wire up real backend endpoints in `frontend/src` (`useScanResults`, `LiveScanPage`, `ScheduledScansPage`).
