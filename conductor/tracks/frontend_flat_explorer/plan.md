# Implementation Plan: Dumb React Flat Explorer (`frontend_flat_explorer`)

## Phase 1: Typed DTO Contracts, TanStack Query Hooks & Legacy Tree Removal (TDD) [checkpoint: 260aa5a]
- [x] Task: Write failing unit tests for flat explorer API hooks and DTO schemas (Red Phase) 29b20ca
  - [x] Add unit tests in `frontend/src/features/scans/__tests__/useScanResults.test.ts` verifying `useRunDetail`, `useRunHosts`, `useRunServices`, `useRunChecks`, and `useRunHostDetail` construct orthogonal query URLs with `q`, `ip`, `status`, `port`, `finding`, `include_closed`, `sort_by`, `sort_dir`, `limit`, and `offset`
  - [x] Add tests verifying query hooks are disabled when `runId` or `ip` is absent and return typed `Page<T>` and `HostDetailDTO` payloads
- [x] Task: Implement flat DTO types, TanStack Query hooks, and delete legacy tree artifacts (Green & Refactor Phase) 260aa5a
  - [x] Update `frontend/src/features/scans/types/index.ts` with `Page<T>`, `HostRowDTO`, `ServiceRowDTO`, `HttpCheckRowDTO`, `HostDetailDTO`, `PortDetailDTO`, `HttpCheckDetailDTO`, `TlsCertificateDetailDTO`, `TableQueryParams`, and `ScanRunSummary` interfaces, removing `TreeNode` and `TreeNodeStatus`
  - [x] Update `frontend/src/features/scans/api/queryKeys.ts` and `frontend/src/features/scans/api/useScanResults.ts` with `useRunDetail`, `useRunHosts`, `useRunServices`, `useRunChecks`, and `useRunHostDetail`
  - [x] Delete `frontend/src/features/scans/components/HierarchicalTable/` directory, `frontend/src/features/scans/utils/buildTree.ts`, and `frontend/src/features/scans/utils/test-ghost.ts`, and update `frontend/src/features/scans/index.ts`
  - [x] Verify hook unit tests pass
- [x] Task: Phase Verification & Checkpoint (Refer to `workflow.md`) 260aa5a

---

## Phase 2: Three-Tab Flat Relational Explorer, Filter Toolbar & URL State Binding (TDD) [checkpoint: 3e2ebc1]
- [x] Task: Write failing component tests for the 3-Tab Flat Explorer, toolbar filters, and strict leftmost IP column (Red Phase) 139fc99
  - [x] Add tests in `frontend/src/pages/__tests__/HostTablePage.test.tsx` verifying Run Summary strip badges (`Active`, `Warning`, `Failed`, `Ghost`, `Void`) and Tab badge counts (`Hosts`, `Services`, `HTTP Checks`) render from `GET /api/runs/{id}`
  - [x] Add tests verifying `IP Address` is strictly the first column in `Hosts`, `Services`, and `HTTP Checks` tables and is rendered as a clickable link/button
  - [x] Add tests verifying tab switching (`?tab=hosts|services|checks`), multi-status toggle bar, search input (`q`), IP filter chip (`?ip=...`), finding filter, port filter, `include_closed` toggle, sortable column headers, pagination controls, and Saved Views (`/api/views`) synchronize with URL search parameters
  - [x] Add tests verifying `redirects_to_url` in the HTTP Checks table renders directly without client-side IP lookup maps
- [x] Task: Implement 3-Tab Flat Explorer and URL-synchronized filter toolbar in `HostTablePage.tsx` (Green & Refactor Phase) 3e2ebc1
  - [x] Create status/finding badge and cell formatting helpers (status badges for `ok`/`active`, `warning`, `failed`, `ghost`, `void`, latency, TLS expiry/version, HTTP status code)
  - [x] Refactor `frontend/src/pages/HostTablePage.tsx` to replace tree state and `HierarchicalTable` with URL-bound query state (`useSearchParams`), Saved Views integration, orthogonal filter toolbar, and paginated `Hosts`, `Services`, and `HTTP Checks` tables
  - [x] Verify all `HostTablePage` component tests pass
- [x] Task: Phase Verification & Checkpoint (Refer to `workflow.md`) 3e2ebc1

---

## Phase 3: On-Demand Slide-Over IP Detail Drawer & Cross-Tab Drill-Down (TDD) [checkpoint: 3625daa]
- [x] Task: Write failing component tests for IP Detail Drawer and cross-tab navigation (Red Phase) 2355a55
  - [x] Add tests in `frontend/src/pages/__tests__/HostTablePage.test.tsx` asserting clicking an IP in column 1 of any table sets `?drawer=<ip>` and fetches `GET /api/runs/{id}/hosts/{ip}`
  - [x] Add tests verifying `HostDetailDrawer` renders discovery lineage (`depth`, `root_target`, `resolved_domains`, `discovered_from`), services table with TLS certificate details, HTTP checks table, and deduplicated Certificate SAN badges
  - [x] Add tests verifying `"Show in Services"` and `"Show in HTTP Checks"` buttons close the drawer, switch to the target tab, and apply the `?ip=<ip>` filter chip
- [x] Task: Implement `HostDetailDrawer` component and integrate with `HostTablePage.tsx` (Green & Refactor Phase) 3625daa
  - [x] Create `frontend/src/features/scans/components/HostDetailDrawer.tsx` using `shadcn/ui` `Sheet` to display `HostDetailDTO` sections, copy-to-clipboard action, and cross-tab drill-down buttons
  - [x] Wire `HostDetailDrawer` into `frontend/src/pages/HostTablePage.tsx` bound to the `drawer` URL search parameter
  - [x] Verify all drawer and drill-down tests pass
- [x] Task: Phase Verification & Checkpoint (Refer to `workflow.md`) 3625daa

---

## Phase 4: Backend Bridge Retirement, Evaluator Cleanup & Full End-to-End Verification (TDD) [checkpoint: 33467ce]
- [x] Task: Write failing backend tests asserting removal of legacy bridge and launch alias routes (Red Phase) 1833517
  - [x] Update tests in `api/tests/test_api_main.py`, `api/tests/test_api_runs.py`, and `api/tests/test_api_results.py` verifying `GET /api/runs/{id}/results`, `POST /api/runs/launch`, and `POST /api/scans/{id}/launch` are retired from the OpenAPI schema
  - [x] Add/update unit test in `api/tests/test_evaluator.py` verifying `evaluate_scan_run()` and `_finalize_run()` persist `metrics_json` cleanly without redundant overwrite commits
- [x] Task: Remove backend bridge routes, streamline finalization metrics, and run full-stack verification (Green & Refactor Phase) f833248
  - [x] Remove `GET /api/runs/{id}/results` and `@router.post("/launch")` from `api/src/api/routers/runs.py`, and remove `@router.post("/{id}/launch")` from `api/src/api/routers/scans.py`
  - [x] Streamline `metrics_json` assignment between `runner.py:_finalize_run()` and `evaluator.py:evaluate_scan_run()`
  - [x] Execute full backend `pytest` suite, frontend `vitest` suite, and production frontend build (`npm run build`)
- [x] Task: Phase Verification & Checkpoint (Refer to `workflow.md`) 33467ce

---

## Phase: Review Fixes
- [x] Task: Apply review suggestions 260168e

