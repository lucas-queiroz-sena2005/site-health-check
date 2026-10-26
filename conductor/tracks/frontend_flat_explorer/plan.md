# Implementation Plan: Dumb React Flat Explorer (`frontend_flat_explorer`)

## Phase 1: Typed DTO Contracts, TanStack Query Hooks & Legacy Tree Removal (TDD)
- [x] Task: Write failing unit tests for flat explorer API hooks and DTO schemas (Red Phase) 29b20ca
  - [x] Add unit tests in `frontend/src/features/scans/__tests__/useScanResults.test.ts` verifying `useRunDetail`, `useRunHosts`, `useRunServices`, `useRunChecks`, and `useRunHostDetail` construct orthogonal query URLs with `q`, `ip`, `status`, `port`, `finding`, `include_closed`, `sort_by`, `sort_dir`, `limit`, and `offset`
  - [x] Add tests verifying query hooks are disabled when `runId` or `ip` is absent and return typed `Page<T>` and `HostDetailDTO` payloads
- [~] Task: Implement flat DTO types, TanStack Query hooks, and delete legacy tree artifacts (Green & Refactor Phase)
  - [ ] Update `frontend/src/features/scans/types/index.ts` with `Page<T>`, `HostRowDTO`, `ServiceRowDTO`, `HttpCheckRowDTO`, `HostDetailDTO`, `PortDetailDTO`, `HttpCheckDetailDTO`, `TlsCertificateDetailDTO`, `TableQueryParams`, and `ScanRunSummary` interfaces, removing `TreeNode` and `TreeNodeStatus`
  - [ ] Update `frontend/src/features/scans/api/queryKeys.ts` and `frontend/src/features/scans/api/useScanResults.ts` with `useRunDetail`, `useRunHosts`, `useRunServices`, `useRunChecks`, and `useRunHostDetail`
  - [ ] Delete `frontend/src/features/scans/components/HierarchicalTable/` directory, `frontend/src/features/scans/utils/buildTree.ts`, and `frontend/src/features/scans/utils/test-ghost.ts`, and update `frontend/src/features/scans/index.ts`
  - [ ] Verify hook unit tests pass
- [ ] Task: Phase Verification & Checkpoint (Refer to `workflow.md`)

---

## Phase 2: Three-Tab Flat Relational Explorer, Filter Toolbar & URL State Binding (TDD)
- [ ] Task: Write failing component tests for the 3-Tab Flat Explorer, toolbar filters, and strict leftmost IP column (Red Phase)
  - [ ] Add tests in `frontend/src/pages/__tests__/HostTablePage.test.tsx` verifying Run Summary strip badges (`Active`, `Warning`, `Failed`, `Ghost`, `Void`) and Tab badge counts (`Hosts`, `Services`, `HTTP Checks`) render from `GET /api/runs/{id}`
  - [ ] Add tests verifying `IP Address` is strictly the first column in `Hosts`, `Services`, and `HTTP Checks` tables and is rendered as a clickable link/button
  - [ ] Add tests verifying tab switching (`?tab=hosts|services|checks`), multi-status toggle bar, search input (`q`), IP filter chip (`?ip=...`), finding filter, port filter, `include_closed` toggle, sortable column headers, pagination controls, and Saved Views (`/api/views`) synchronize with URL search parameters
  - [ ] Add tests verifying `redirects_to_url` in the HTTP Checks table renders directly without client-side IP lookup maps
- [ ] Task: Implement 3-Tab Flat Explorer and URL-synchronized filter toolbar in `HostTablePage.tsx` (Green & Refactor Phase)
  - [ ] Create status/finding badge and cell formatting helpers (status badges for `ok`/`active`, `warning`, `failed`, `ghost`, `void`, latency, TLS expiry/version, HTTP status code)
  - [ ] Refactor `frontend/src/pages/HostTablePage.tsx` to replace tree state and `HierarchicalTable` with URL-bound query state (`useSearchParams`), Saved Views integration, orthogonal filter toolbar, and paginated `Hosts`, `Services`, and `HTTP Checks` tables
  - [ ] Verify all `HostTablePage` component tests pass
- [ ] Task: Phase Verification & Checkpoint (Refer to `workflow.md`)

---

## Phase 3: On-Demand Slide-Over IP Detail Drawer & Cross-Tab Drill-Down (TDD)
- [ ] Task: Write failing component tests for IP Detail Drawer and cross-tab navigation (Red Phase)
  - [ ] Add tests in `frontend/src/pages/__tests__/HostTablePage.test.tsx` asserting clicking an IP in column 1 of any table sets `?drawer=<ip>` and fetches `GET /api/runs/{id}/hosts/{ip}`
  - [ ] Add tests verifying `HostDetailDrawer` renders discovery lineage (`depth`, `root_target`, `resolved_domains`, `discovered_from`), services table with TLS certificate details, HTTP checks table, and deduplicated Certificate SAN badges
  - [ ] Add tests verifying `"Show in Services"` and `"Show in HTTP Checks"` buttons close the drawer, switch to the target tab, and apply the `?ip=<ip>` filter chip
- [ ] Task: Implement `HostDetailDrawer` component and integrate with `HostTablePage.tsx` (Green & Refactor Phase)
  - [ ] Create `frontend/src/features/scans/components/HostDetailDrawer.tsx` using `shadcn/ui` `Sheet` to display `HostDetailDTO` sections, copy-to-clipboard action, and cross-tab drill-down buttons
  - [ ] Wire `HostDetailDrawer` into `frontend/src/pages/HostTablePage.tsx` bound to the `drawer` URL search parameter
  - [ ] Verify all drawer and drill-down tests pass
- [ ] Task: Phase Verification & Checkpoint (Refer to `workflow.md`)

---

## Phase 4: Backend Bridge Retirement, Evaluator Cleanup & Full End-to-End Verification (TDD)
- [ ] Task: Write failing backend tests asserting removal of legacy bridge and launch alias routes (Red Phase)
  - [ ] Update tests in `api/tests/test_api_main.py`, `api/tests/test_api_runs.py`, and `api/tests/test_api_results.py` verifying `GET /api/runs/{id}/results`, `POST /api/runs/launch`, and `POST /api/scans/{id}/launch` are retired from the OpenAPI schema
  - [ ] Add/update unit test in `api/tests/test_evaluator.py` verifying `evaluate_scan_run()` and `_finalize_run()` persist `metrics_json` cleanly without redundant overwrite commits
- [ ] Task: Remove backend bridge routes, streamline finalization metrics, and run full-stack verification (Green & Refactor Phase)
  - [ ] Remove `GET /api/runs/{id}/results` and `@router.post("/launch")` from `api/src/api/routers/runs.py`, and remove `@router.post("/{id}/launch")` from `api/src/api/routers/scans.py`
  - [ ] Streamline `metrics_json` assignment between `runner.py:_finalize_run()` and `evaluator.py:evaluate_scan_run()`
  - [ ] Execute full backend `pytest` suite, frontend `vitest` suite, and production frontend build (`npm run build`)
- [ ] Task: Phase Verification & Checkpoint (Refer to `workflow.md`)
