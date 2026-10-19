# Backend Codebase Review & Documentation Comparison Report

I have conducted a thorough review of the FastAPI backend codebase (`api/`), its integration with the engine (`engine/`), the architectural decision records (`docs/adr/`), domain documentation (`CONTEXT.md`), and the API documentation suite (`docs/api/`, `docs/01-06`).

Here is a detailed comparison of the actual state of the backend with what is documented, along with recommendations for ADR amendments, new ADRs, and documentation cleanups.

---

## 1. Actual State of Backend Code vs. Documented Architecture

### A. Execution Engine: Subprocess & SSE vs. In-Process Monolith
- **Documented (ADR 0003, `docs/06-mvp-implementation.md`):** An in-process monolith where FastAPI and the Scanner engine run on the same `asyncio` event loop. Tasks are passed via in-memory `asyncio.Queue` during FastAPI lifespan startup.
- **Documented (`docs/api/contracts.md`, `data_lifecycle.md`):** Ad-hoc scans triggered via `POST /api/scans` return a WebSocket URL (`WS /api/jobs/{id}/stream`), piping JSON to `site_health_check.cli -i -` over `stdin`.
- **Actual Code (`api/src/api/routers/runs.py`):**
  - Uses `POST /api/runs/launch` which dispatches a background task (`asyncio.create_subprocess_exec`) running `python -m engine.cli <targets> -p <ports> <flags>`.
  - Captures `stdout` line-by-line and streams it to the frontend via **Server-Sent Events (SSE)** using `GET /api/runs/{id}/stream` (`EventSourceResponse`).
  - Subprocess flags are dynamically generated from `ExecutionFlags` Pydantic metadata.

### B. Global View vs. Per-Run Scans (ADR 0009 vs. ADR 0013)
- **Documented (ADR 0009, `CONTEXT.md`):** FastAPI merges multiple policies/runs into a "Unified Target View" and enforces "Data Hierarchy Invalidation" (L4 port closed hides older L7 HTTP data).
- **Documented (ADR 0013 - 2026-09-17):** Explicitly **abandons** the "Unified Global View" and multi-run merging. The dashboard always views a single `ScanRun` (defaulting to the latest run).
- **Actual Code (`api/src/api/routers/results.py`, `runs.py`):** The backend does *not* implement cross-run merging or hierarchy invalidation. Results are filtered by `run_id` (or all rows if omitted). However, `CONTEXT.md` and ADR 0009 were never updated to reflect that ADR 0013 superseded ADR 0009.

### C. Historical Diffing & Void Aggregation (ADR 0004 vs. ADR 0012)
- **Documented (ADR 0004):** FastAPI squashes contiguous blocks of 10 or more dead/unassigned IPs into a single aggregate Void Node (e.g., `10.0.0.50-10.0.0.200 (Void)`).
- **Documented (ADR 0012 Section 3):** Dynamic Void node generation was moved into the React frontend (`buildTree.ts` calculates `total_hosts - hostNodes.length` and injects a Void row).
- **Actual Code (`api/src/api/services/aggregation.py`):** Backend aggregation does not check for contiguous blocks of 10+. Instead, it groups all dead IPs under a parent domain/CIDR into `Void (<count>)`. Furthermore, `aggregation.py` is currently broken with legacy field names (see Section 4).

### D. Deep Architecture vs. Router Implementation (`docs/api/behavior.md`)
- **Documented (`docs/api/behavior.md`):** Describes a "Deep Module" named `ScanOperations` implementing ports and adapters (`ScanRunnerPort`, `SubprocessAdapter`, `InMemoryMockAdapter`), isolating route handlers from database and subprocess logic. It also describes tables named `Policies`, `Classifications`, and `Schedules`.
- **Actual Code:** No `ScanOperations`, `ScanRunnerPort`, or adapter classes exist. Routers (`runs.py`, `scans.py`, `results.py`) directly execute SQLModel queries and subprocess calls. The database tables are `Scan`, `TargetGroup`, `ScanTargetGroupLink`, `ScanRun`, and `HostState`.

### E. Backend Result Ingestion Gap
- **Actual Code (`api/src/api/routers/runs.py:run_engine_cli`):** When `python -m engine.cli` finishes, the process stdout is streamed as SSE logs, but:
  - `ScanRun.status` is never updated from `PENDING` to `COMPLETED` or `FAILED`.
  - `started_at`, `finished_at`, and `metrics_json` are never set.
  - The CLI's output JSON is never parsed or inserted into `HostState` / `PortState` tables.
  - Consequently, `GET /api/runs/{id}/results` returns empty data for launched runs unless manually seeded.

---

## 2. ADRs Requiring Amendments or Status Updates

1. **ADR 0003: Single Process MVP Architecture**
   - **Action:** Mark as **Superseded**.
   - **Reason:** The in-process `asyncio.Queue` monolith (running Scanner inside FastAPI lifespan) was replaced by out-of-process subprocess execution (`python -m engine.cli`) with SSE log streaming.
2. **ADR 0009: Unified Target Merging & Data Hierarchy Invalidation**
   - **Action:** Mark as **Superseded / Deprecated** by ADR 0013.
   - **Reason:** ADR 0013 ("Default to Latest Scan Run") explicitly abandoned cross-run unified merging. ADR 0009 remains marked "Accepted" without any notice indicating it was superseded.
3. **ADR 0004: API-Driven Historical Diffing & Void Aggregation**
   - **Action:** Amend.
   - **Reason:** 
     - Clarify that backend void aggregation groups all non-active, non-ghost IPs by parent target into `Void (N)` rather than finding contiguous subnet blocks of 10+.
     - Clarify the division of responsibilities with ADR 0012 (which introduced frontend dynamic Void node generation in `buildTree.ts`).

---

## 3. New ADRs Recommended for Recent Architectural Patterns

1. **ADR: Subprocess Engine Execution & Server-Sent Events (SSE) Streaming**
   - **Context:** Transition from the single-process `asyncio.Queue` MVP (ADR 0003) to subprocess isolation.
   - **Decision:** FastAPI executes `python -m engine.cli` via `asyncio.create_subprocess_exec`, streaming real-time stdout logs to clients via SSE (`EventSourceResponse` at `GET /api/runs/{id}/stream`). Engine crashes or heavy CPU loads cannot block or segfault the FastAPI event loop.
2. **ADR: Pydantic-Driven CLI Argument Generation & Schema Reflection**
   - **Context:** Keeping CLI arguments, API validation models, and Frontend dynamic form generation in sync without manual duplication.
   - **Decision:** Use Pydantic's `json_schema_extra` on `ExecutionFlags` (e.g. `cli_arg`, `is_switch`) to dynamically translate API request JSON into CLI flags. Expose `GET /api/schemas/schedule` (`ExecutionConfig.model_json_schema()`) so the UI dynamically generates input forms.
3. **ADR: Relational Schema for Scheduled Scans and Target Groups**
   - **Context:** Representing recurring scan policies and target groupings in SQLite.
   - **Decision:** Adopt `Scan`, `TargetGroup`, and `ScanTargetGroupLink` (M:N junction). When a user creates a scan via `POST /api/scans`, an ad-hoc `TargetGroup` is automatically created and linked.

---

## 4. Non-ADR Documents: Outdated, Legacy, or Missing

### A. `CONTEXT.md` (Repo Root)
- **Outdated ADR Log:** Only lists ADRs 0001 through 0009. ADRs 0010, 0011, 0012, and 0013 are completely omitted.
- **Mismatched Title:** Lists ADR 0001 as "Single Context & Lightweight ADRs", but `docs/adr/0001-ip-first-output-hierarchy.md` is titled "IP-first output hierarchy".
- **Deprecated Concepts:** Still defines `Unified Target View` and `Data Hierarchy Invalidation` as core domain concepts despite ADR 0013 discarding them.
- **Premature Distributed Concepts:** Services section defines `Dispatcher`, `Scanner`, and `Broker` (RabbitMQ) as if currently operational, whereas the current system operates via the API subprocess wrapper.

### B. `docs/api/behavior.md`, `contracts.md`, and `data_lifecycle.md`
- **Status:** **Entirely Outdated / Speculative.**
- `behavior.md` describes an imaginary `ScanOperations` port/adapter architecture and non-existent DB tables (`Policies`, `Classifications`, `Schedules`).
- `contracts.md` documents `POST /api/scans` as an ad-hoc runner returning WebSockets (`WS /api/jobs/{id}/stream`), and stdin JSON piping.
- `data_lifecycle.md` uses outdated models (`Job`, `IpState`, `Result`).
- **Recommendation:** Rewrite these documents to accurately document:
  - `POST /api/runs/launch` (ad-hoc execution) and `GET /api/runs/{id}/stream` (SSE).
  - `POST /api/scans` and `GET /api/scans` (scheduled scans).
  - `GET /api/results` (with `ghost_window` and `run_id` parameters).
  - `POST /api/views` and `GET /api/views/{id}`.
  - Actual SQLModel tables (`ScanRun`, `Scan`, `TargetGroup`, `HostState`, `PortState`, `TlsCertificate`, `HttpRoutingCheck`, `SavedView`).

### C. `docs/01-architecture.md`, `05-control-plane-architecture.md`, `06-mvp-implementation.md`
- `01-architecture.md`: Early phase spec ("NOT a Visual Dashboard... NOT a Background Daemon... ThreadPoolExecutor"). Should be tagged as legacy/historical.
- `05-control-plane-architecture.md`: Mentions "Flask API" instead of FastAPI, Prometheus target JSON scraping for scheduling, and claims ad-hoc scans bypass SQLite.
- `06-mvp-implementation.md`: References outdated file paths (`src/site_health_check/api/main.py`), disk-based `results.json` parsing by frontend, and ADR 0003 in-memory queue model.

### D. `api/README.md`
- References obsolete endpoint `/api/jobs/launch` (actual is `/api/runs/launch`).
- Local run command uses `src.api.main:app` instead of `api.main:app`.

### E. Codebase Bug in `api/src/api/services/aggregation.py`
- Lines 36–42 instantiate `HostState(job_id=None, metadata_discovered_from=["void_aggregated"])`.
- In `api/models.py`, `HostState` has `scan_run_id` (not `job_id`) and `metadata_discovered_from_json` (not `metadata_discovered_from`). This causes runtime validation errors when aggregating void nodes.

### F. Broken Backend Test Suite (`api/tests/`)
- `test_api_jobs.py`, `test_api_results.py`, and `test_api_aggregation.py` all import legacy models (`Job`, `IpState`, `JobStatus`) and hit obsolete paths (`/api/jobs/launch`, `/results`). The test suite fails to run and needs updating to current models and endpoints.
