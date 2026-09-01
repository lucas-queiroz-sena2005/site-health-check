# FastAPI Backend: Architectural Behavior & Internal Logic

This document exhaustively defines the internal behavior, state machines, concurrency models, and structural design patterns of the FastAPI backend for the Site Health Check tool. It serves as the definitive reference for how the API operates underneath the hood.

---

## 1. Deep Module Architecture (Ports & Adapters)

In accordance with strict Codebase Design principles, the FastAPI backend rejects the "shallow router" anti-pattern (where HTTP route handlers directly execute SQL queries and spawn subprocesses). Instead, the backend is built around a **Deep Module** named `ScanOperations`.

### 1.1 The Interface (Leverage)
The API Routers interact with `ScanOperations` through a highly constrained, simple interface:
- `start_ad_hoc_scan(payload: ScanPayload) -> JobID`
- `save_schedule(payload: SchedulePayload) -> ScheduleID`
- `stream_logs(job_id: JobID) -> AsyncGenerator`
- `get_historical_results() -> PaginatedJobs`

The routers know absolutely nothing about SQLModel, SQLite, or Subprocesses. They simply validate incoming JSON using Pydantic and delegate to the interface.

### 1.2 The Implementation (Locality)
The `ScanOperations` module contains massive implementation depth. It handles:
- **Transaction Management:** Beginning, committing, and rolling back SQLite transactions.
- **Concurrency Management:** Spawning and tracking asynchronous subprocesses.
- **Data Transformation:** Parsing raw engine JSON output into aggregated metrics.

### 1.3 The Seam (External Dependencies)
The core business logic (scanning targets) is delegated to an external CLI engine. This represents a structural **Seam**. To keep `ScanOperations` testable, it does not import `subprocess` directly. Instead, it relies on an injected **Adapter**:
- **`ScanRunnerPort` (Protocol):** Defines the contract for running a scan.
- **`SubprocessAdapter`:** The production adapter that uses `asyncio.create_subprocess_exec` to run `site-check -i -`.
- **`InMemoryMockAdapter`:** A testing adapter that instantly yields fake logs, allowing the entire FastAPI test suite to run in milliseconds without ever touching the network.

---

## 2. The Job Lifecycle State Machine

When a manual "Scan Now" operation is triggered, the `Job` entity transitions through a strict state machine tracked in the SQLite database.

### 2.1 PENDING
- **Trigger:** The FastAPI route `POST /api/scans` is hit.
- **Action:** `ScanOperations` validates the payload. A `Job` row is created in SQLite with `status="PENDING"`.
- **Exit Condition:** Database transaction commits successfully.

### 2.2 RUNNING
- **Trigger:** The `Job` row is successfully committed.
- **Action:** FastAPI updates the row to `status="RUNNING"`. The `SubprocessAdapter` is invoked. The CLI engine process is spawned, and its PID is temporarily stored in FastAPI's memory state to prevent duplicate runs and allow for forceful aborts.
- **Exit Condition:** The subprocess exits naturally, or is forcefully killed.

### 2.3 COMPLETED
- **Trigger:** The subprocess exits with Return Code `0`.
- **Action:** FastAPI reads the final JSON output string from the engine. It parses the payload, calculates the `metrics_json` (e.g., `total_green`, `total_red`), updates the `Job` row, and inserts the full raw JSON into the `Results` table.
- **Exit Condition:** Terminal state.

### 2.4 FAILED / ABORTED
- **Trigger:** The subprocess exits with a non-zero Return Code, the FastAPI application receives a `SIGTERM` while a job is running, or a user explicitly requests an abort.
- **Action:** FastAPI catches the exception or signal. It immediately kills the subprocess (if active), updates the `Job` row to `status="FAILED"`, and writes the stack trace or kill reason to the `metrics_json` error field.
- **Exit Condition:** Terminal state.

---

## 3. Concurrency & Subprocess Streaming

FastAPI is fundamentally an asynchronous framework built on `asyncio`. However, spawning synchronous subprocesses or executing heavy SQLite queries can block the event loop, causing the entire API to freeze.

### 3.1 Non-Blocking Engine Execution
To avoid event loop blocking, the `SubprocessAdapter` utilizes `asyncio.create_subprocess_exec`. This allows FastAPI to yield control back to the event loop while the OS handles the actual execution of the CLI tool. 

FastAPI writes the complex multi-target JSON payload directly to the subprocess's `stdin` via an `asyncio.StreamWriter`, completely bypassing temporary files on disk and preventing race conditions if two users trigger scans concurrently.

### 3.2 Server-Sent Events (SSE) Streaming
For the "Live Operations" feed on the UI, FastAPI streams the CLI engine's logs in real-time.
- **Why SSE over WebSockets?** The log feed is strictly one-way (Server -> Client). WebSockets require heavy duplex handshakes and complex reconnect logic. SSE is natively supported by the browser's `EventSource` API, automatically handles connection drops/reconnects, and uses standard HTTP chunked transfer encoding.
- **The Stream Generator:** When `GET /api/stream/{job_id}` is called, FastAPI returns an `EventSourceResponse`. Internally, this response consumes an asynchronous generator. The generator reads the subprocess `stdout` using `await process.stdout.readline()`.
- **Client Disconnects:** If the user closes their browser tab, the `EventSourceResponse` detects the broken pipe. FastAPI catches the `ClientDisconnect` exception and safely terminates the generator, avoiding memory leaks. (Note: Disconnecting the log stream *does not* kill the background scanning job. The job continues to run until completion).

---

## 4. Database Integrity & The 3-in-1 Schedule Builder

The system uses `SQLModel` to bridge Pydantic schemas and SQLAlchemy tables.

### 4.1 Synchronous SQLite Operations
Because `aiosqlite` adds unnecessary overhead for simple operations, we use standard synchronous SQLite drivers. To prevent blocking the FastAPI event loop during heavy writes, all `ScanOperations` database commits are executed within FastAPI's threadpool (`def` routes instead of `async def` routes for purely DB-bound operations, as per the FastAPI codebase-design skill).

### 4.2 The 3-in-1 Schedule Creation
The UX specifies a unified interface for scheduling scans, but the backend normalizes this into three distinct tables (`Policies`, `Classifications`, and `Schedules`).
When `POST /api/scans` is called with a `cron_expression`:
1. **Transaction Start:** `ScanOperations` opens a single DB transaction.
2. **Policy Hashing:** The engine payload is hashed. If an identical `Policy` exists, it is reused. Otherwise, a new `Policy` row is created.
3. **Classification Hashing:** The targets array is hashed. If identical, it is reused. Otherwise, a new `Classification` row is created.
4. **Schedule Linking:** A `Schedule` row is created, acting as the M:N junction between the Policy and Classification, storing the CRON string.
5. **Commit:** If any step fails, the entire transaction rolls back, preventing orphaned Classifications or Policies.

---

## 5. Result Merging & Data Hierarchy (ADR 0009)

When the frontend requests historical data via `GET /api/jobs/{id}/results`, FastAPI does not just blindly return the JSON. It enforces the rules defined in **ADR 0009 (Unified Target Merging & Data Hierarchy Invalidation)**.

### 5.1 The L4 over L7 Rule
FastAPI parses the raw output JSON. If the Engine reported that Port 443 TCP is `CLOSED` (an L4 failure), but an older cached scan or a fragmented job reported HTTP data for that same IP, FastAPI explicitly scrubs the HTTP data from the final output it serves to the frontend.
This prevents "misinformation" where the UI shows an active HTTP directory structure for a server that is currently powered off.

### 5.2 Aggregation Rollups
To populate the `total_green` and `total_red` columns in the UI's History Table, FastAPI performs an aggregation sweep immediately after the subprocess exits.
- **Green:** IP has at least one open port and responded to standard probes.
- **Red:** IP timed out on all ports, or returned L4 TCP Reset.
These aggregate integers are saved to the `metrics_json` column. When the frontend calls `GET /api/jobs`, it receives these tiny aggregate integers rather than having to download 50MB of raw JSON to count the statuses client-side.

---

## 6. Future-Proofing: The Transition to Go and RabbitMQ

The Subprocess Architecture is not a technical debt hack; it is a deliberate stepping stone. 
By strictly isolating the `ScanRunnerPort` behind the `ScanOperations` Deep Module, the FastAPI backend is already architecturally prepared for the future Go rewrite.

When the Go Engine is ready:
1. We write a new `RabbitMQAdapter` that satisfies the `ScanRunnerPort`.
2. Instead of calling `subprocess.exec`, the adapter publishes the JSON payload to a RabbitMQ queue.
3. Instead of reading `process.stdout`, the adapter subscribes to a RabbitMQ log exchange for that `job_id` and yields the incoming messages to the exact same `EventSourceResponse`.

The FastAPI routes, the React frontend, and the Database layer will not require a single line of code changed. The transition will be entirely invisible to the rest of the stack.
