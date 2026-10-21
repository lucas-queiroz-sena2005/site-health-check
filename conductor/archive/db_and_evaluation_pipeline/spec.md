# Specification: Database Normalization & Backend Evaluation Pipeline (`db_and_evaluation_pipeline`)

## 1. Overview
This track implements **Track 2 of ADR 0023**: modernizing the backend persistence and evaluation model of Site Health Check. It removes legacy relational abstractions (`TargetGroup`, `ScanTargetGroupLink`), purges `"Void"` sentinel strings, deletes Pydantic `@model_serializer` ORM dictionary hacks, hardens SQLite with WAL mode and foreign-key constraints, and introduces a deterministic, bottom-up Backend Evaluation Pipeline (`api/services/evaluator.py`) that pre-computes finding codes, rollups, and statuses before saving final run state.

---

## 2. Functional Requirements

### 2.1 Database Normalization & Entity Cleanup
1. **Direct `Scan.targets` Storage:**
   - Drop the `TargetGroup` and `ScanTargetGroupLink` models.
   - Add `targets: list[str] = Field(default_factory=list, sa_column=Column(JSON))` directly on `Scan`.
   - Update `init_db()` in `api/src/api/database.py` with SQLite migration logic to add the `targets` column to `scans` table if absent.
   - Refactor `api/src/api/routers/scans.py` endpoints to create and read `targets` directly on `Scan`.
2. **Retire Pydantic `@model_serializer` Hacks:**
   - Remove `@model_serializer(mode='wrap')` from `HostState` and `PortState`.
   - Rename `ports_list` to `ports: list[PortState]` and `http_routing_checks_list` to `http_routing_checks: list[HttpRoutingCheck]`, using standard SQLModel relationship definitions.
3. **Purge "Void" Sentinel Strings:**
   - Eliminate all `ip_address.startswith("Void")` checks and synthetic node manipulation across `runner.py`, `aggregation.py`, and `alerts.py`.
   - Non-responsive targets that never had open ports remain untracked in SQLite, accounted for purely via summary metrics.
4. **Set-Union Domain & Lineage Storage on `HostState`:**
   - Replace scalar `metadata_resolved_from` with:
     - `resolved_domains: list[str] = Field(default_factory=list, sa_column=Column(JSON))`
     - `discovered_from: list[str] = Field(default_factory=list, sa_column=Column(JSON))`
   - In `runner.py`, set-union these lists during delta ingestion so multiple virtual hosts resolving to the same IP never clobber each other.

### 2.2 SQLite Hardening & Ingestion Integrity
1. **WAL & Foreign Keys:**
   - Configure SQLite connection PRAGMAs in `api/src/api/database.py` via SQLAlchemy engine event listeners:
     - `PRAGMA journal_mode=WAL;`
     - `PRAGMA foreign_keys=ON;`
     - `PRAGMA busy_timeout=5000;`
2. **Constraint Enforcement:**
   - Add `UniqueConstraint("port_state_id")` on `TlsCertificate` in `api/src/api/models.py` to guarantee 1:1 integrity with `PortState`.

### 2.3 Pre-Computed Columns
1. **`HttpRoutingCheck`:**
   - `status: str = Field(default="ok")` (`ok | warning | failed`)
   - `finding_code: str | None = None`
2. **`PortState`:**
   - `status: str = Field(default="ok")` (`ok | warning | failed`)
   - `san_count: int = Field(default=0)`
   - `http_check_count: int = Field(default=0)`
   - `worst_http_status: int | None = None`
   - `finding_codes: list[str] = Field(default_factory=list, sa_column=Column(JSON))`
3. **`HostState`:**
   - `status: str = Field(default="ok")` (`ok | warning | failed | ghost`)
   - `depth: int = Field(default=0)`
   - `open_port_count: int = Field(default=0)`
   - `scanned_port_count: int = Field(default=0)`
   - `vhost_count: int = Field(default=0)`
   - `min_tcp_latency_ms: int | None = None`
   - `min_tls_expires_days: int | None = None`
   - `worst_tls_version: str | None = None`
   - `worst_http_status: int | None = None`
   - `finding_codes: list[str] = Field(default_factory=list, sa_column=Column(JSON))`

### 2.4 Deterministic Backend Evaluation Pipeline (`api/services/evaluator.py`)
Implement `evaluate_scan_run(scan_run_id: str, session: Session) -> None` executed at run finalization:
1. **Finding Codes Mapping:**
   - `TCP_CLOSED`: port is closed or unreachable.
   - `TLS_INVALID`: TLS handshake failed or invalid certificate.
   - `TLS_EXPIRED`: `expires_in_days <= 0`.
   - `TLS_EXPIRING_SOON`: `0 < expires_in_days <= scan.tls_warning_days` (default 30).
   - `TLS_DEPRECATED_VERSION`: TLS version < `TLSv1.2` (e.g. `TLSv1.0`, `TLSv1.1`, `SSLv3`).
   - `HTTP_5XX`: `status_code >= 500`.
   - `HTTP_4XX`: `400 <= status_code < 500`.
   - `HTTP_ERROR`: `status_code is None` or connection timeout/abort during HTTP check.
   - `HOST_GHOST`: Host was previously active within the ghost window but had zero open ports in this run.
   - `RUN_ABORTED`: Run terminated prematurely via abort.
2. **Bottom-Up Rollup Logic:**
   - **Level 1 (HTTP Checks):** Assign `status` and `finding_code` to each `HttpRoutingCheck`.
   - **Level 2 (Port / Service):** Roll up HTTP checks and TLS certificate into `PortState`. If any HTTP check has `HTTP_ERROR` / `status_code is None`, service status is `failed`. Precompute `san_count`, `http_check_count`, `worst_http_status`, and aggregated `finding_codes`.
   - **Level 3 (Host / IP):** Roll up services and lineage into `HostState`. Calculate `depth` (from `discovered_from`), `vhost_count` (from `resolved_domains`), `open_port_count`, `min_tcp_latency_ms`, `min_tls_expires_days`, `worst_tls_version`, `worst_http_status`, and host-level `status` and `finding_codes`.

---

## 3. Non-Functional Requirements
- **Performance:** In-place evaluation executes efficiently within SQLite transaction boundaries.
- **Data Integrity:** Strict foreign key cascades (`ON DELETE CASCADE`) and unique constraints ensure no orphan records or duplicate certificate rows.
- **Coverage:** Comprehensive pytest test suite across `api/tests/` with >80% code coverage.

---

## 4. Acceptance Criteria
- [ ] `TargetGroup` and `ScanTargetGroupLink` models removed cleanly without leftover foreign key errors.
- [ ] `Scan` accepts and persists `targets: list[str]` directly.
- [ ] Pydantic `@model_serializer` is deleted from `HostState` and `PortState`.
- [ ] SQLite connection enforces WAL journal mode and foreign keys.
- [ ] `evaluate_scan_run` accurately computes bottom-up finding codes, rollups, and statuses for real and simulated runs.
- [ ] All `ip_address.startswith("Void")` sentinel checks removed from backend codebase.
- [ ] All unit and integration tests in `api/tests/` updated and passing.

---

## 5. Out of Scope
- REST API pagination endpoints for 3 orthogonal tables (`GET /api/runs/{id}/hosts`, `/services`, `/checks`) and dedicated IP drawer endpoint (`GET /api/runs/{id}/hosts/{ip}`) -> **Track 4**.
- `RunManager` background worker service and finding-driven alert triggers -> **Track 3**.
- React frontend explorer tabs and slide-over drawer UI -> **Track 5**.
