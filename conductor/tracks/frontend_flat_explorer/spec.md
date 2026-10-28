# Specification: Dumb React Flat Explorer (`frontend_flat_explorer`)

## 1. Overview
This track implements **Track 5 of [ADR 0023](../../adr/0023-control-plane-and-flat-explorer-modernization.md)**. It replaces the legacy client-side hierarchical tree table (`HierarchicalTable`, `buildTree.ts`, `test-ghost.ts`) with a 3-tab relational explorer (**Hosts**, **Services**, **HTTP Checks**) and an on-demand slide-over **IP Detail Drawer**, backed directly by Track 4's SQL-paginated REST endpoints.

It also completes the retirement of the Track 4 backward-compatibility bridge (`GET /api/runs/{id}/results`) and legacy launch aliases (`POST /api/runs/launch`, `POST /api/scans/{id}/launch`).

---

## 2. Functional Requirements

### 2.1 Dashboard Header, Run Summary Strip & Saved Views (`HostTablePage.tsx`)
- Mounted at the index route `/` with URL search parameter `?run=<runId>` (auto-selecting the latest run via `GET /api/runs?limit=1` when omitted).
- **Top Metadata & Summary Bar (populated from `GET /api/runs/{id}`):**
  - Displays `Run ID`, `scan_name` (or `Ad-hoc Scan`), `total_targets_scanned`, `scan_duration_seconds`, and `RunHistorySheet` trigger.
  - Displays status summary pills from `metrics_json.summary`:
    - `Active` (`summary.active`)
    - `Warning` (`summary.warning`)
    - `Failed` (`summary.failed`)
    - `Ghost` (`summary.ghost`)
    - `Void` (`summary.void`)
- **Saved Views Integration (`/api/views`):**
  - Retains the Saved Views selector (`GET /api/views`, `POST /api/views`, `DELETE /api/views/{id}`, `?view=<id>`), mapping `search` ➔ `q`, `statuses` ➔ `status`, `table_sort_by` ➔ `sort_by`, and `table_sort_dir` ➔ `sort_dir`.

### 2.2 Three-Tab Relational Explorer & Strict Leftmost IP Invariant
Three tabs with badge counts derived from `metrics_json.summary` (Hosts: `active + warning + failed + ghost`; Services: `service_count`; HTTP Checks: `http_check_count`):
- **Visual Invariant:** `IP Address` (`ip_address`) is always the first (leftmost) column in all three tables and is the **only** clickable entity link in table rows. Clicking an IP sets `?drawer=<ip>` without mutating active table filters or pagination.

1. **Hosts Tab (`GET /api/runs/{id}/hosts` ➔ `Page[HostRowDTO]`):**
   - **Sortable Columns:** `ip_address` (default `asc`), `status`, `depth`, `vhost_count`, `open_port_count` (rendered as `open_port_count / scanned_port_count`), `min_tcp_latency_ms`, `min_tls_expires_days`, `worst_tls_version`, `worst_http_status`.
   - **Non-Sortable Column:** `finding_codes` (rendered as canonical finding badges).
2. **Services Tab (`GET /api/runs/{id}/services` ➔ `Page[ServiceRowDTO]`):**
   - **Sortable Columns:** `ip_address` (default `asc`), `port`, `status`, `depth`, `tcp_latency_ms`, `tls_valid`, `tls_expires_in_days`, `tls_version`, `tls_issuer`, `san_count`, `http_check_count`, `worst_http_status`.
   - **Non-Sortable Column:** `finding_codes` (rendered as canonical finding badges).
3. **HTTP Checks Tab (`GET /api/runs/{id}/checks` ➔ `Page[HttpCheckRowDTO]`):**
   - **Sortable Columns:** `ip_address` (default `asc`), `port`, `domain`, `status`, `status_code`, `http_latency_ms`, `redirects_to_url`, `server_header`, `finding_code`.
   - **Non-Sortable Column:** `notes`.
   - **Redirect Rendering:** Renders `redirects_to_url` directly as monospace text without client-side IP lookup maps (per ADR 0023 Section 2.C.4).

### 2.3 Orthogonal Filter Toolbar & Server-Side Pagination
- **URL Search Parameter Binding:**
  - `run`: Active `ScanRun` ID
  - `tab`: `hosts` (default) | `services` | `checks`
  - `q`: Debounced deep text search input
  - `ip`: Exact/prefix IP filter (displayed as a removable `Host: <ip> ×` chip when active)
  - `status`: Multi-toggle status filter bar (`all`, `active`, `warning`, `failed`, `ghost`) serialized as comma-separated values
  - `port`: Optional port filter input (shown on `services` and `checks` tabs)
  - `finding`: Canonical finding code filter dropdown (`TCP_CLOSED`, `TLS_INVALID`, `TLS_EXPIRED`, `TLS_EXPIRING_SOON`, `TLS_DEPRECATED_VERSION`, `HTTP_5XX`, `HTTP_4XX`, `HTTP_ERROR`, `HOST_GHOST`)
  - `include_closed`: Boolean toggle on `services` tab (`include_closed=true`)
  - `sort_by` & `sort_dir`: Active sort column and direction (`asc` | `desc`)
  - `page` & `limit`: Page index (mapped to `offset = page * limit`) and page size (`25`, `50`, `100`)
  - `drawer`: Open IP address for the detail drawer
- Changing any filter or tab resets pagination to the first page while preserving `run` and `drawer` (unless explicitly closed).

### 2.4 On-Demand Slide-Over IP Detail Drawer (`GET /api/runs/{id}/hosts/{ip}` ➔ `HostDetailDTO`)
- Rendered via shadcn/ui `Sheet` (`side="right"`) whenever `?drawer=<ip>` is non-empty.
- **Sections:**
  1. **Header & Discovery Lineage:**
     - `ip_address` (with copy-to-clipboard button), `status` badge, `open_port_count / scanned_port_count` summary, `depth`, `root_target`, `resolved_domains` badges, `discovered_from` breadcrumbs, and host-level `finding_codes`.
     - **Cross-Tab Drill-Down Actions:** `"Show in Services"` (`?tab=services&ip=<ip>&drawer=`) and `"Show in HTTP Checks"` (`?tab=checks&ip=<ip>&drawer=`).
  2. **Services (`services: list[PortDetailDTO]`):**
     - Table/cards displaying `port_number`, `tcp_status`, `status` badge, `tcp_latency_ms`, `tls_certificate` (`valid`, `expires_in_days`, `protocol_version`, `issuer`), `san_count`, `http_check_count`, `worst_http_status`, and `finding_codes`.
  3. **HTTP Checks (`checks: list[HttpCheckDetailDTO]`):**
     - Table/cards displaying `port`, `domain`, `status` badge, `status_code`, `http_latency_ms`, `redirects_to_url`, `server_header`, `notes`, and `finding_code`.
  4. **Certificate SANs (`tls_sans: list[str]`):**
     - Deduplicated badge list of all Subject Alternative Names on the host.

### 2.5 Deprecations & Legacy Cleanup (Frontend & Backend Bridge)
- **Frontend Deletions:**
  - Delete `frontend/src/features/scans/components/HierarchicalTable/` (entire directory).
  - Delete `frontend/src/features/scans/utils/buildTree.ts` and `frontend/src/features/scans/utils/test-ghost.ts`.
  - Remove `TreeNode` and `TreeNodeStatus` from `frontend/src/features/scans/types/index.ts` and replace with TypeScript interfaces matching `Page<T>`, `HostRowDTO`, `ServiceRowDTO`, `HttpCheckRowDTO`, `HostDetailDTO`, and `ScanRunResponse`.
  - Replace `useScanResults.ts` with typed TanStack Query hooks (`useRunDetail`, `useRunHosts`, `useRunServices`, `useRunChecks`, `useRunHostDetail`).
- **Backend Bridge Retirement (Track 4 Cleanup):**
  - Remove `GET /api/runs/{id}/results` from `api/src/api/routers/runs.py`.
  - Remove legacy `@router.post("/launch")` alias from `api/src/api/routers/runs.py` and `@router.post("/{id}/launch")` from `api/src/api/routers/scans.py`, updating `api/tests/test_api_runs.py` and `api/tests/test_api_results.py` accordingly.

### 2.6 Component Decomposition & Table Primitives (Composition & Reuse)
- **Goal:** Refactor the monolithic `HostTablePage.tsx` into modular, reusable components adhering to React composition standards, eliminating duplication across the 3 relational tables.
- **Requirements:**
  1. **Reusable Table Primitives (`frontend/src/features/scans/components/table/`):**
     - `<SortableHead>`: Reusable table column header with sort indicators (`▲`/`▼`) and accessible click handling.
     - `<IpAddressCell>`: Strict leftmost IP column cell with button and drawer opening callback.
     - `<FindingBadgeList>`: Shared component for rendering canonical finding badge lists.
     - `<EmptyTableState>`: Standardized table empty state row with parameterized colSpan.
  2. **Dedicated Table Views (`frontend/src/features/scans/components/table/`):**
     - `<HostsTable>`: Renders the Hosts tab table using shared primitives.
     - `<ServicesTable>`: Renders the Services tab table using shared primitives.
     - `<ChecksTable>`: Renders the HTTP Checks tab table using shared primitives.
  3. **Modular Page Sections (`frontend/src/features/scans/components/`):**
     - `<RunSummaryHeader>`: Header strip with Run ID, status badge, live polling text, summary counters, and history sheet.
     - `<ScanFilterToolbar>`: Global toolbar with Saved Views, debounced search, status toggle pills, IP chip, and port/finding filters.
     - `<TablePaginationBar>`: Standardized pagination footer with rows-per-page selection and page navigation.
  4. **Custom URL State Hook (`frontend/src/features/scans/hooks/useTableUrlState.ts`):**
     - Extracts URL parameter synchronization, query object construction, and tab switching outside of UI rendering.
  5. **HostTablePage Orchestrator (`frontend/src/pages/HostTablePage.tsx`):**
     - Reduced to a concise orchestrator component (~80-120 LOC) composing the layout sections and managing drawer integration.

---

## 3. Non-Functional Requirements
- **Dumb UI Invariant:** Zero status evaluation or rollup math in React; all statuses (`ok`, `warning`, `failed`, `ghost`, `void`) and `finding_codes` render directly from API responses.
- **Type Safety & Build Integrity:** `npm run build` (`tsc -b && vite build`), `vitest`, and `pytest` must pass with zero errors.

---

## 4. Acceptance Criteria
- [ ] Navigating to `/?run=<id>` renders the Run Summary banner, Saved Views bar, and 3-tab Flat Explorer (`Hosts`, `Services`, `HTTP Checks`).
- [ ] `IP Address` is strictly the leftmost column in all three tables and opens the slide-over IP Detail Drawer (`?drawer=<ip>`).
- [ ] Drawer fetches `GET /api/runs/{id}/hosts/{ip}` on demand and supports `"Show in Services"` and `"Show in HTTP Checks"` drill-down actions.
- [ ] Sorting, multi-status filtering, search (`q`), IP chip filtering (`ip`), port filtering (`port`), finding code filtering (`finding`), and pagination execute via the backend endpoints and sync with URL query params.
- [ ] `HierarchicalTable/`, `buildTree.ts`, `test-ghost.ts`, `GET /api/runs/{id}/results`, `POST /api/runs/launch`, and `POST /api/scans/{id}/launch` are completely removed.
- [ ] Table headers, leftmost IP cells, finding badge lists, and empty states are extracted into reusable primitives (`frontend/src/features/scans/components/table/`).
- [ ] Tab tables (`HostsTable`, `ServicesTable`, `ChecksTable`), filter toolbar, summary header, and pagination are decomposed into dedicated components.
- [ ] `HostTablePage.tsx` is reduced from a ~1,085 LOC monolith to a concise orchestrator (~80-120 LOC).
- [ ] All frontend (`vitest`, `tsc -b`) and backend (`pytest`) test suites pass.
