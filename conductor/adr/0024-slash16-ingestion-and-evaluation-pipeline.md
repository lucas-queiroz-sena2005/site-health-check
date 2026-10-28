# ADR 0024: /16 Ingestion Pipeline, Batch Ingestion Buffering & Set-Based Evaluation

## Status

Proposed — Active Refactor (Track `evaluator_refactor_and_sql_optimization`). Extends ADR 0004 (Void Aggregation), ADR 0022 (/16 Scale Strategy), and ADR 0023 (Control Plane & Flat Explorer Modernization).

---

## 1. Context & Problem Statement

When scanning large CIDR blocks (e.g., a full `/16` subnet containing 65,536 IPv4 targets), the standalone asynchronous execution engine (`engine/src/engine/engine.py`) has been benchmarked to complete target generation and TCP/TLS probing across 100 concurrent workers in **seconds**.

However, when launched through the API (`POST /api/runs`), the scan takes an **eternity** (10 to 30+ minutes, or times out completely).

### Root Cause Analysis

An exhaustive audit of the ingestion pipeline (`api/src/api/services/runner.py`), subprocess coordination (`run_manager.py`), database configuration (`database.py`), and post-run evaluation (`evaluator.py`) identified four compounded bottlenecks:

```mermaid
flowchart TD
    Engine["Engine Subprocess (Fast BFS: 10,000 tasks/s)"] -->|stdout NDJSON| Pipe["OS Pipe Buffer (64 KB capacity)"]
    Pipe -->|Blocks when full!| Engine
    Pipe -->|readline()| Ingest["API _ingest_stdout"]
    Ingest -->|1 delta per commit| SyncCommit["_upsert_delta_sync (65,536 SQLite transactions)"]
    SyncCommit -->|Synchronous disk fsync| DB[("SQLite Database")]
    SyncCommit -->|Takes ~15-30 min| Eval["evaluator.py evaluate_scan_run"]
    Eval -->|select(HostState) without eager load| NPlusOne["65,536 Lazy SELECT queries on port_states"]
    Eval -->|IN 65k items| SQLCrash["OperationalError: too many SQL variables"]
    Eval -->|Memory allocation| OOM["65,000 ORM dirty objects in session"]
    Eval -->|Pruning| Delete["DELETE 65k void rows previously inserted"]
```

#### Bottleneck 1: Synchronous Per-Line Database Transactions ($O(N)$ Transactions)
In `runner.py`:
```python
while True:
    line = await process.stdout.readline()
    for ip, data in payload.items():
        await asyncio.to_thread(_upsert_delta_sync, run_id, ip, data)
```
For every single target line emitted by the engine, `_upsert_delta_sync` creates an independent `Session(db_engine)`, executes multiple `SELECT` and `INSERT ... ON CONFLICT DO UPDATE` statements, and calls `session.commit()`.
- Even on high-performance NVMe storage, committing a SQLite transaction synchronously takes between 1 ms and 15 ms.
- For 65,536 targets:
  $$65,536 \times 5\text{ ms} \approx 327\text{ seconds } (5.5\text{ minutes})$$
  On typical drives with journal barriers, this reaches **15–30 minutes**.

#### Bottleneck 2: OS Pipe Buffer Exhaustion & Engine Worker Throttling
The operating system pipe buffer between the subprocess `stdout` and Python's `asyncio.subprocess` is typically **64 KB**.
Because `_ingest_stdout` awaits `asyncio.to_thread(_upsert_delta_sync, ...)` synchronously on every line, the ingestion loop processes only ~50–100 lines/second. The engine outputs hundreds of lines per second, filling the 64 KB pipe buffer in under 100 milliseconds.
Once the pipe buffer is full, the engine's `sys.stdout.write(...)` and `sys.stdout.flush()` calls block. The engine's high-performance asynchronous event loop is throttled down to the speed of SQLite single-row disk writes.

#### Bottleneck 3: Ephemeral Void Persistence (Write Churn)
In a typical enterprise `/16` subnet, out of 65,536 IPs, only a small fraction (e.g. 50–500) are active hosts; the remaining ~65,000 are unassigned network silence ("Void Space", per ADR 0004).
Under the current flow:
1. The API commits 65,000 void host rows and 130,000 closed port rows to SQLite during scanning.
2. The evaluator loads all 65,000 void rows, runs rollups, and commits status updates to disk.
3. If `prune_void_hosts` is true (the default), the evaluator immediately deletes all 65,000 void rows from the database.
Over 98% of all database writes during a `/16` scan are completely discarded immediately after completion.

#### Bottleneck 4: Monolithic 371-Line `evaluator.py` & The $N+1$ Lazy Query Trap
`evaluator.py` exhibits classical "Python Notebook Anti-Patterns": treating an RDBMS as a dumb storage array while using procedural Python loops for aggregation and filtering:
1. **$N+1$ Relationship Queries:** `select(HostState)` is executed without `selectinload(HostState.ports)`. Accessing `host.ports` inside the `for host in hosts:` loop issues **65,536 individual `SELECT` queries** against SQLite.
2. **SQLite Parameter Limits Exceeded:** `evaluator.py` extracts 65,000 IP strings into a Python list and constructs `.where(col(HostState.ip_address).in_(host_ips))` and `.where(col(PortState.host_state_id).in_(void_host_ids))`. In SQLite, `SQLITE_MAX_VARIABLE_NUMBER` is capped (999 in legacy SQLite, 32,766 in modern SQLite). Lists exceeding this limit trigger `sqlite3.OperationalError: too many SQL variables` or choke the query compiler.
3. **In-Memory Summary Aggregation:** Seven separate Python list comprehensions (`sum(1 for h in hosts if ...)`) compute summary counts that SQLite can calculate in under 2 milliseconds using `GROUP BY status`.

---

## 2. Decision & Architectural Principles

We adopt four fundamental architectural standards to resolve these bottlenecks across the API ingestion and post-scan evaluation pipeline:

### 2.1 Micro-Batched Ingestion Buffering & SQLite Pragmas

Instead of committing after every line, `_ingest_stdout` will push parsed deltas into an in-memory queue. A background ingestion task flushes deltas to SQLite in **micro-batches** (either every **500 items** or every **100 milliseconds**, whichever threshold is reached first):

```python
async def _flush_batch(run_id: str, batch: list[tuple[str, dict[str, Any]]]):
    await asyncio.to_thread(_bulk_upsert_deltas_sync, run_id, batch)
```

1. **Single Transaction per Batch:** 65,536 items are committed in ~130 transactions instead of 65,536 transactions (reducing transaction overhead by **99.8%**).
2. **SQLite Pragmas in `database.py`:**
   Ensure `PRAGMA synchronous = NORMAL;` is explicitly set alongside `PRAGMA journal_mode = WAL;`.
   *In WAL mode, `synchronous=NORMAL` eliminates per-commit `fsync()` calls to the database file while retaining full ACID compliance against application crashes.*

### 2.2 Stream Void Bypass (Zero-Cost Streaming for /16)

When `prune_void_hosts` is enabled (default `True`):
1. **Historical Ghost Candidates Cache:** Prior to launching the engine, the API queries historical active IP addresses for the target range within `ghost_window` (typically a small set of tens or hundreds of IPs).
2. **Streaming Filter:**
   - If an incoming delta has **at least one open port**, it is an active host $\rightarrow$ buffered for DB upsert.
   - If an incoming delta has **all closed ports**:
     - If `ip in historical_active_ips`, it is a candidate Ghost $\rightarrow$ buffered for DB upsert.
     - Else, it is pure **Void Space** $\rightarrow$ dropped from database ingestion; an in-memory atomic counter (`void_count += 1`) is incremented.
3. If `prune_void_hosts` is disabled (`False`), all deltas are batched and persisted to SQLite.

*Result: During a /16 scan, SQLite writes drop from 195,000 records to ~500 records.*

### 2.3 Relational Pushdown (Set-Based Relational Operations)

We establish the **Relational Pushdown Principle**: *Delegate set operations, filtering, grouping, and cascade deletions to the relational database engine rather than writing Python procedural loops.*

1. **Set-Based Ghost Detection:**
   Replace the 65,000-parameter `IN (...)` Python query with a set-based SQL subquery:
   ```sql
   UPDATE host_states
   SET status = 'ghost'
   WHERE scan_run_id = :run_id
     AND open_port_count = 0
     AND ip_address IN (
       SELECT DISTINCT h2.ip_address
       FROM host_states h2
       JOIN scan_runs r2 ON h2.scan_run_id = r2.id
       WHERE r2.status = 'COMPLETED'
         AND r2.id != :run_id
         AND r2.started_at >= :cutoff
         AND h2.open_port_count > 0
     );
   ```
2. **Set-Based Cascading Pruning:**
   Pruning void hosts and closed ports will execute as direct SQL `DELETE` queries with subqueries, leveraging `ON DELETE CASCADE`:
   ```sql
   DELETE FROM host_states
   WHERE scan_run_id = :run_id AND status = 'void';
   ```
3. **Set-Based Metrics Aggregation:**
   Metrics summaries will be aggregated via `GROUP BY`:
   ```sql
   SELECT status, COUNT(*) FROM host_states WHERE scan_run_id = :run_id GROUP BY status;
   ```

### 2.4 Functional Core, Imperative Shell (FCIS) in `evaluator.py`

Decompose the monolithic 371-line `evaluator.py` into distinct, single-responsibility modules:

1. **`evaluator_rules.py` (Functional Core):**
   Pure, deterministic business logic functions without side-effects or database dependencies:
   - `evaluate_http_check(status_code: int | None) -> tuple[str, str | None]`
   - `evaluate_tls_cert(valid: bool, expires_in_days: int, protocol_version: str | None, tls_warning_days: int) -> list[str]`
   - `evaluate_port_status(tcp_status: str, check_statuses: list[str], tls_findings: list[str]) -> str`
   - Fully unit-testable in microseconds with 100% test isolation.
2. **`evaluator_service.py` (Imperative Shell):**
   Coordinates database interaction:
   - Eagerly loads required records using `selectinload(HostState.ports).selectinload(PortState.http_routing_checks)`.
   - Applies the pure rule engine.
   - Executes set-based updates and SQL aggregations.

---

## 3. Recommended Standards & References

To prevent the recurrence of Jupyter-notebook-style antipatterns and procedural SQL loops, the team should reference the following engineering standards:

1. **Thinking in Sets & Relational Algebra:**
   - *Joe Celko's "SQL for Smarties: Advanced SQL Programming"* (specifically Chapter 1: Thinking in Sets vs. Procedural Loops / RBAR "Row-By-Agonizing-Row").
   - *C.J. Date, "Database Design and Relational Theory: Normal Forms and All That Jazz"*.
2. **Functional Core, Imperative Shell (FCIS):**
   - Gary Bernhardt's Architecture Standard: *Boundaries* (separating pure domain calculations from stateful I/O boundaries).
   - [Martin Fowler on Anemic Domain Model vs Pure Domain Functions](https://martinfowler.com/bliki/AnemicDomainModel.html).
3. **High-Performance SQLite Production Practices:**
   - [SQLite WAL Mode Official Guide](https://sqlite.org/wal.html) (explaining concurrency and `synchronous = NORMAL`).
   - [SQLite Query Limits](https://sqlite.org/limits.html) (`SQLITE_MAX_VARIABLE_NUMBER`).
4. **Reactive Streams & Backpressure Management:**
   - Martin Kleppmann, *Designing Data-Intensive Applications* (Chapter 11: Stream Processing, Bounded Buffers, and Backpressure).

---

## 4. Consequences

### Positive
- **Instantaneous Engine Throughput:** Subprocess pipe buffer remains drained; `/16` scans complete through the API at the native engine speed (~seconds for network probes).
- **Sub-Second Database Finalization:** Total ingestion and evaluation time drops from 15+ minutes to **under 2 seconds** for a `/16`.
- **Zero Risk of Parameter Overflow:** Eliminates `too many SQL variables` crashes forever.
- **Maintainable & Clean Codebase:** `evaluator.py` is decomposed into small, pure, independently verifiable rule functions.

### Negative / Trade-offs
- Micro-batching requires managing a flush buffer and handling final EOF flush when the engine subprocess terminates.
- Bypassing void host DB writes during streaming means ad-hoc SQL inspection during an active scan will not show inactive targets in the database until summary metrics are updated. (This matches ADR 0004 and ADR 0023, where Void Space is purely aggregate network silence).
