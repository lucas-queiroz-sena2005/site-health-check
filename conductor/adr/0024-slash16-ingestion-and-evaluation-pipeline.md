# ADR 0024: /16 Ingestion Pipeline, Batch Ingestion Buffering & Set-Based Evaluation

## Status

Proposed — Active Refactor (Track `evaluator_refactor_and_sql_optimization`). Extends ADR 0004 (Void Aggregation), ADR 0018 (Partial Runs), ADR 0022 (/16 Scale Strategy), and ADR 0023 (Control Plane & Flat Explorer Modernization).

---

## 1. Context & Problem Statement

When scanning large CIDR blocks (e.g., a full `/16` subnet containing 65,536 IPv4 targets), the standalone asynchronous execution engine (`engine/src/engine/engine.py`) completes target generation and TCP/TLS probing across 100 concurrent workers in **seconds**.

However, when launched through the API (`POST /api/runs`), the scan takes an **eternity** (10 to 30+ minutes, or stalls/crashes at finalization).

### Root Cause Analysis

An exhaustive audit of the ORM models (`api/src/api/models.py`), ingestion pipeline (`api/src/api/services/runner.py`), subprocess coordination (`run_manager.py`), database configuration (`database.py`), and post-run evaluation (`evaluator.py`) identified five compounded bottlenecks:

```mermaid
flowchart TD
    Engine["Engine Subprocess (Fast BFS: 10,000 tasks/s)"] -->|stdout NDJSON| Pipe["OS Pipe Buffer (64 KB capacity)"]
    Pipe -->|Blocks when full!| Engine
    Pipe -->|readline()| Ingest["API _ingest_stdout"]
    Ingest -->|1 delta per commit| SyncCommit["_upsert_delta_sync (65,536 SQLite transactions)"]
    SyncCommit -->|Synchronous disk fsync| DB[("SQLite Database")]
    Poll["Frontend Polling GET /api/runs/{id}"] -->|session.get(ScanRun)| SelectIn["ScanRun.hosts lazy='selectin' loads 65k hosts + 131k ports on EVERY poll!"]
    SelectIn --> DB
    SyncCommit -->|Takes ~15-30 min| Eval["evaluator.py evaluate_scan_run"]
    Eval -->|Loads all 65k hosts + ports into RAM| Memory["200,000+ ORM objects in Python Session"]
    Eval -->|IN 65k items| SQLCrash["OperationalError: too many SQL variables"]
    Eval -->|Update then Delete| Churn["Updates 65k void hosts just to DELETE them 1ms later"]
```

#### Bottleneck 1: Unconditional `lazy="selectin"` Cascade on `ScanRun.hosts` and `HostState.ports`
In `api/src/api/models.py`:
- `ScanRun.hosts` is configured with `"lazy": "selectin"`, even though `run.hosts` is **never accessed anywhere in the codebase**.
- `HostState.ports`, `PortState.tls_certificate`, and `PortState.http_routing_checks` also have `"lazy": "selectin"`.
- **Consequence:** Every single call to `session.get(ScanRun, id)` or `select(ScanRun)` across the entire API (`GET /api/runs`, `GET /api/runs/{id}`, `GET /api/runs/{id}/hosts`, `GET /api/runs/{id}/services`, `GET /api/runs/{id}/checks`, `GET /api/runs/{id}/stream`, `_finalize_run`, `evaluate_scan_run`) triggers a **4-level recursive `SELECT ... WHERE id IN (...)` cascade** hydrating all 65,536 `HostState` rows and 131,072 `PortState` rows into Python RAM! While a `/16` scan is running, frontend polling on `GET /api/runs/{id}` repeatedly loads the entire growing scan tree into memory every few seconds.

#### Bottleneck 2: Synchronous Per-Line Database Transactions ($O(N)$ Transactions)
In `runner.py`:
```python
while True:
    line = await process.stdout.readline()
    for ip, data in payload.items():
        await asyncio.to_thread(_upsert_delta_sync, run_id, ip, data)
```
For every single target line emitted by the engine, `_upsert_delta_sync` opens a new `Session(db_engine)`, executes individual `session.get(...)` and `INSERT ... ON CONFLICT DO UPDATE` queries (~6 SQL queries per line = ~393,000 queries for a `/16`), and calls `session.commit()` (65,536 disk flushes).

#### Bottleneck 3: OS Pipe Buffer Exhaustion & Engine Worker Throttling
The OS pipe buffer between the subprocess `stdout` and Python's `asyncio.subprocess` is typically **64 KB**. Because `_ingest_stdout` blocks on `await asyncio.to_thread(_upsert_delta_sync, ...)` for every line, the 64 KB pipe buffer fills in under 100ms, causing `sys.stdout.write(...)` and `sys.stdout.flush()` inside the engine subprocess to block. The asynchronous engine is throttled down to the speed of single-row SQLite disk commits.

#### Bottleneck 4: SQLite Variable Overflow (`too many SQL variables`) in `evaluator.py`
`evaluator.py` extracts all 65,536 IP strings and void host IDs into Python lists and passes them into `.where(col(HostState.ip_address).in_(host_ips))` and `.where(col(PortState.host_state_id).in_(void_host_ids))`.
In SQLite, `SQLITE_MAX_VARIABLE_NUMBER` is capped (999 in older builds, 32,766 in modern builds). Passing 65,536 parameters triggers `sqlite3.OperationalError: too many SQL variables`.

#### Bottleneck 5: Updating 65,000 Void Rows in Python Only to Immediately Delete Them
In a typical `/16` scan where 99% of IPs are unassigned network silence ("Void Space", per ADR 0004):
1. `_finalize_run` loads all 65,536 `HostState` rows into a Python list just to compute `len(hosts)`.
2. `evaluate_scan_run` loads all 65,536 `HostState` and 131,072 `PortState` objects into Python, marks 65,000 of them as `status = 'void'`, and commits 195,000 row updates to disk.
3. Immediately after committing those updates, `prune_void_hosts` deletes all 195,000 rows from the database.

---

## 2. Decision & Architectural Principles

### 2.1 Remove Unconditional `lazy="selectin"` from ORM Models (`models.py`)
1. Remove `"lazy": "selectin"` from `ScanRun.hosts`, `HostState.ports`, `PortState.tls_certificate`, and `PortState.http_routing_checks` in `models.py` (defaulting to standard lazy loading `"select"`).
2. Use explicit `selectinload(...)` in queries **only** when child relationships are actually traversed (`evaluator.py` when evaluating non-void hosts, and `get_run_host_detail` in `runs.py`).
3. In `_finalize_run`, compute `initial_targets_count` via `select(func.count()).select_from(HostState).where(HostState.scan_run_id == run_id)` instead of loading all `HostState` objects into memory.

### 2.2 In-Batch Delta Coalescing & Bulk Upsert (`runner.py`, `database.py`)
Why we **do not** drop void deltas during streaming:
- During a scan, the same IP can receive multiple deltas at different times (e.g., an initial closed-port probe on `10.0.0.50` carrying `subrun_id="10.0.0.0/24"`, followed later by a TLS SAN or HTTP redirect discovery on another port or virtual host). Dropping the initial delta during streaming would lose lineage (`subrun_id`, `resolved_domains`, `scanned_port_count`), miscount `total_targets_scanned`, and break partial run inspection on abort (ADR 0018).

Instead, we preserve **100% streaming data fidelity** while achieving sub-second throughput via **Micro-Batched Bulk Upserts**:
1. **Asynchronous Batch Buffer in `_ingest_stdout`:**
   - Drain `process.stdout` non-stop and accumulate `(ip, data)` items into a batch buffer.
   - Flush when `len(batch) >= 500` OR `100ms` has elapsed since the batch started, plus a guaranteed final flush on EOF.
2. **In-Batch Coalescing & Bulk SQL Upsert (`_bulk_upsert_deltas_sync`):**
   - Coalesce multiple deltas for the same IP within the batch in memory (set-union of `resolved_domains` and `discovered_from`, sticky `"open"` TCP status).
   - Fetch existing `HostState` and `PortState` rows for the batch using a **single** `SELECT ... WHERE id IN (...)` query (bounded to $\le 500$ IDs, well within SQLite variable limits).
   - Execute bulk `insert(HostState).values(host_rows).on_conflict_do_update(...)` and bulk `insert(PortState).values(port_rows).on_conflict_do_update(...)` inside a **single SQLite transaction** per batch.
   - Keep `_upsert_delta_sync(run_id, ip, data)` as a backward-compatible single-item wrapper delegating to `_bulk_upsert_deltas_sync(run_id, [(ip, data)])`.
3. **SQLite Pragmas (`database.py`):**
   - Configure `PRAGMA synchronous = NORMAL;` alongside `PRAGMA journal_mode = WAL;` and `PRAGMA busy_timeout = 5000;`.
   - Keeping batch transactions under 500 items ($\approx 5\text{ ms}$ per commit) prevents write-lock starvation when concurrent scans or HTTP write requests execute simultaneously.

### 2.3 Functional Core, Imperative Shell (FCIS) Decomposition (`evaluator_rules.py`)
Extract pure, stateless domain evaluation functions into `api/src/api/services/evaluator_rules.py`:
- `evaluate_http_check(status_code: int | None) -> tuple[str, str | None]`
- `evaluate_tls_cert(valid: bool, expires_in_days: int, protocol_version: str | None, tls_warning_days: int) -> tuple[list[str], int | None]`
- `evaluate_port(tcp_status: str, check_statuses: list[str], check_findings: list[str], tls_findings: list[str], was_historically_open: bool) -> tuple[str, list[str], bool]`
- `evaluate_host_status(open_port_count: int, open_port_statuses: list[str], has_error_port: bool, has_ghost_port: bool, was_ip_historically_active: bool, initial_findings: list[str]) -> tuple[str, list[str]]`

### 2.4 Relational Pushdown & Set-Based Evaluation (`evaluator.py`)
Refactor `evaluate_scan_run` to eliminate all parameter-limit overflows, $N+1$ queries, and unnecessary Python object hydration while preserving every invariant needed by future runs and alerts:

1. **Historical Active Set via SQL Subquery (1 Bind Variable):**
   Query historical active `(ip_address, port_number)` pairs within `ghost_window` using a subquery:
   ```python
   current_ips_subq = select(HostState.ip_address).where(HostState.scan_run_id == scan_run_id)
   hist_stmt = (
       select(HostState.ip_address, PortState.port_number)
       .join(PortState, col(HostState.id) == col(PortState.host_state_id))
       .join(ScanRun, col(HostState.scan_run_id) == col(ScanRun.id))
       .where(PortState.tcp_status == "open")
       .where(col(ScanRun.started_at) >= cutoff)
       .where(ScanRun.status == ScanRunStatus.COMPLETED)
       .where(col(ScanRun.id) != scan_run_id)
       .where(col(HostState.ip_address).in_(current_ips_subq))
       .distinct()
   )
   ```
2. **Set-Based Fast-Path for Pure Routine Void Hosts:**
   A host in `scan_run_id` is a *Pure Routine Void Host* if and only if:
   - It has at least one `PortState` row and **zero** ports with `tcp_status != 'closed'` (no `open` or `error` ports),
   - It has **zero** `HttpRoutingCheck` and **zero** `TlsCertificate` rows, and
   - Its `ip_address` is **not** in `historical_active_ips`.
   For these ~65,000 pure void hosts:
   - If `prune_void_hosts=True`: Count them via SQL `SELECT COUNT(*)` and delete their `PortState` and `HostState` rows directly via SQL subqueries **without loading them into Python or updating them first**.
   - If `prune_void_hosts=False`: Bulk-update their `HostState` (`status='void'`, `open_port_count=0`, `scanned_port_count`, `vhost_count`, `finding_codes=[]`) and `PortState` (`status='void'`, `finding_codes=['TCP_CLOSED']`) via set-based SQL `UPDATE` statements.
3. **Chunked Eager-Loaded Evaluation for Active / Error / Ghost-Candidate Hosts:**
   - Load only the remaining candidate hosts (hosts with open/error ports, TLS/HTTP checks, 0 ports, or in `historical_active_ips`) in chunks of 500 using explicit `selectinload(HostState.ports).selectinload(PortState.tls_certificate)` and `selectinload(HostState.ports).selectinload(PortState.http_routing_checks)`.
   - Compute Level 1 (`HttpRoutingCheck`), Level 2 (`PortState`), and Level 3 (`HostState`) rollups (including `scanned_port_count = max(host.scanned_port_count or 0, len(host.ports))` **before** any closed-port pruning!).
4. **Explicit Bottom-Up Subquery Pruning (Safe Regardless of `PRAGMA foreign_keys`):**
   - Delete child rows explicitly using SQL `IN (SELECT ...)` subqueries (`HttpRoutingCheck` $\rightarrow$ `TlsCertificate` $\rightarrow$ `PortState` $\rightarrow$ `HostState`).
   - Preserves all open ports (`tcp_status == 'open'`) required by future runs for historical ghost detection, and preserves all ghost hosts/ports (`status == 'ghost'`) required by the UI and alert webhooks.

---

## 3. Recommended Standards & References

1. **Thinking in Sets & Relational Algebra:**
   - *Joe Celko's "SQL for Smarties: Advanced SQL Programming"* (Thinking in Sets vs. RBAR "Row-By-Agonizing-Row").
   - *C.J. Date, "Database Design and Relational Theory"*.
2. **Functional Core, Imperative Shell (FCIS):**
   - Gary Bernhardt, *Boundaries* (isolating pure deterministic domain rules from stateful I/O shells).
3. **High-Performance SQLite Production Practices:**
   - [SQLite WAL Mode Official Guide](https://sqlite.org/wal.html) (`journal_mode=WAL` + `synchronous=NORMAL`).
   - [SQLite Query Limits](https://sqlite.org/limits.html) (`SQLITE_MAX_VARIABLE_NUMBER`).
4. **Stream Processing & Backpressure Management:**
   - Martin Kleppmann, *Designing Data-Intensive Applications* (Micro-batching and bounded pipe buffers).
