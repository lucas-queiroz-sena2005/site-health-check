# Specification: Orthogonal REST API for the 3 Tables & IP Drawer (`rest_api_orthogonality`)

## 1. Overview
This track implements **Track 4 of [ADR 0023](../../adr/0023-control-plane-and-flat-explorer-modernization.md)**. It modernizes the Site Health Check REST API to serve the three flat relational views (**Hosts**, **Services**, **HTTP Checks**) and the **IP Detail Drawer** through dedicated, SQL-paginated/sorted endpoints. It establishes database-agnostic IP sorting, finalization pruning toggles, multi-status filtering, and idempotent control plane endpoints.

---

## 2. Functional Requirements

### 2.1 Dedicated Orthogonal Table Endpoints (`api/src/api/routers/runs.py`)
All three endpoints return a standard generic `Page[T]` response: `{"items": list[T], "total": int, "limit": int, "offset": int}`.

1. **`GET /api/runs/{id}/hosts` ➔ `Page[HostRowDTO]`:**
   - **Fields:** `ip_address`, `status`, `depth`, `vhost_count`, `open_port_count`, `scanned_port_count`, `min_tcp_latency_ms`, `min_tls_expires_days`, `worst_tls_version`, `worst_http_status`, `finding_codes`.
   - **Exclusions:** Omits heavy inline arrays (`resolved_domains`, `tls_sans`) to keep table payloads compact.
2. **`GET /api/runs/{id}/services` ➔ `Page[ServiceRowDTO]`:**
   - **Fields:** `ip_address`, `port`, `status`, `depth`, `tcp_latency_ms`, `tls_valid`, `tls_expires_in_days`, `tls_version`, `tls_issuer`, `san_count`, `http_check_count`, `worst_http_status`, `finding_codes`.
   - **Row Grain:** By default, returns open services + ghost port outages (`WHERE tcp_status = 'open' OR status != 'ok'`). Routine never-open closed ports are excluded from the table unless `include_closed=true` is requested.
3. **`GET /api/runs/{id}/checks` ➔ `Page[HttpCheckRowDTO]`:**
   - **Fields:** `ip_address`, `port`, `domain`, `status`, `status_code`, `http_latency_ms`, `redirects_to_url`, `server_header`, `notes`, `finding_code`.

### 2.2 Dedicated On-Demand IP Detail Drawer Endpoint
* **`GET /api/runs/{id}/hosts/{ip}` ➔ `HostDetailDTO`:**
  - Triggered when the user clicks an IP address in column 1 of any table.
  - Returns complete details for that single IP:
    - **Lineage:** `ip_address`, `status`, `depth`, `root_target` (`subrun_id`), `resolved_domains`, `discovered_from`.
    - **Services:** Full list of all probed ports on this IP, including `PortState` and nested `TlsCertificate`.
    - **Checks:** All `HttpRoutingCheck` records on this IP.
    - **SANs:** Deduplicated flat set of all Subject Alternative Names across all certificates on this host.

### 2.3 Shared Query Parameters (`TableQueryParams`)
Shared dependency via `Annotated[TableQueryParams, Depends()]` across all table endpoints:
- **`q` (Deep Text Search):** Substring match in SQL across IP address, `resolved_domains` JSON, issuer, headers, and finding codes.
- **`ip`:** Exact IP or prefix search (`ip_address LIKE :ip%`).
- **`status` (Multi-Select Status):** Supports single or comma-separated status strings matching the UI (`active`/`ok`, `warning`, `failed`, `ghost`), executing `WHERE status IN (...)` in SQL.
- **`port`:** Optional port filter for `/services` and `/checks`.
- **`finding`:** Canonical finding code filter (e.g. `TLS_EXPIRED`).
- **`sort_by` & `sort_dir`:** Sort column and direction (`asc` / `desc`), supporting sorting by `depth`, `ip_address`, latency, and TLS days, using `.nulls_last()` so missing values sort to the bottom.
- **`limit` & `offset`:** Pagination (default limit: 50, max: 500).

### 2.4 Database-Agnostic IP Sorting & IPv6 Readiness
- Add `ip_sort_key: str | None = Field(default=None, index=True)` to `HostState` in `api/src/api/models.py`.
- In `api/src/api/services/runner.py` during ingestion, compute a normalized 32-character hex key (IPv4-mapped hex for IPv4, full 32-hex for IPv6).
- Sorting by IP executes standard SQL `ORDER BY ip_sort_key ASC` with zero engine changes, zero custom database connection hooks, and 100% database agnosticism across SQLite, PostgreSQL, and MySQL.

### 2.5 Run Finalization Pruning Toggles
- Add to `ExecutionConfig` in `api/src/api/models.py`:
  - `prune_void_hosts: bool = Field(default=True, title="Prune Void Hosts on Finalization")`
  - `prune_closed_ports: bool = Field(default=True, title="Prune Routine Closed Ports on Finalization")`
- In `_finalize_run`:
  - Prune void hosts (inactive with 0 open ports) if `prune_void_hosts` is true.
  - Prune routine closed `PortState` records on active hosts (excluding ghost ports) if `prune_closed_ports` is true, after updating `scanned_port_count`.

### 2.6 Run Summary Strip & Tab Badge Counts
- In `evaluator.py`, record `service_count` (open/anomalous services) and `http_check_count` in `ScanRun.metrics_json["summary"]`.
- `GET /api/runs/{id}` returns complete summary metrics and all three tab badge counts in a single metadata call on page load.

### 2.7 Control Plane Modernization & Deprecations
1. **Unified Run Launch (`POST /api/runs`):**
   - Merges `POST /api/runs/launch` and `POST /api/scans/{id}/launch`.
   - If `scan_id` is supplied without explicit targets, loads config from the saved `Scan`.
   - If `targets` are provided, runs ad-hoc or applies runtime overrides.
   - Updates `LiveScanPage.tsx` and `ScheduledScansPage.tsx` to call `POST /api/runs`.
2. **Idempotent Alert Muting:**
   - Add `PATCH /api/scans/{id}` supporting partial updates (including `alerts_muted: bool`, `is_active: bool`, `name: str`).
   - Remove HTML endpoints `GET /api/scans/{id}/alerts/mute` and `/unmute`.
   - In Slack / Google Chat webhook cards (`api/src/api/services/alerts.py`), replace the state-mutating direct mute link with a direct link to the schedule dashboard.
3. **Legacy Cleanups:**
   - Delete dead `aggregation.py` (`"Void (N)"` sentinel strings).
   - Delete `api/src/api/routers/results.py`.
   - Retain `GET /api/runs/{id}/results` as a backward-compatibility bridge until Track 5 replaces `useScanResults.ts`.

---

## 3. Non-Functional Requirements
- **Performance:** Table pagination queries for `/hosts`, `/services`, and `/checks` must execute in < 15ms in SQLite for scan runs up to 10,000 targets.
- **FastAPI Discipline:** Use `Annotated` parameter declarations, explicit Pydantic return models (`Page[T]`), and synchronous `def` path operations for SQLModel queries to avoid event-loop blocking.
- **Type Safety & Testing:** 100% test coverage with unit/integration tests in `api/tests/` for all new endpoints, query filters, sorting, and DTO validations.

---

## 4. Out of Scope
- Frontend React implementation of the 3-tab layout and slide-over drawer (Reserved for **Track 5: `frontend_flat_explorer`**).
- Deletion of `HierarchicalTable` and `buildTree.ts` (Reserved for Track 5).
