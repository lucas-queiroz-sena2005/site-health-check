# Specification: Void Aggregation on Run Finalization

## Overview
When scanning CIDR subnets (e.g. `143.106.1.1/24`) where targets fail to respond, the engine probes every address and inserts closed `HostState` records. On a clean database (or when addresses have no historical activity), these non-responsive addresses represent **Void Space** rather than **Ghosts**.

This track implements **run-finalization void aggregation and database pruning** in the backend runner (`_finalize_run`). Upon scan completion, all individual non-responsive, non-ghost `HostState` rows (and their associated closed `PortState` rows) are purged from SQLite and replaced by a single synthetic `HostState(ip_address="Void (N)", metadata_resolved_from=parent)` per parent target/CIDR.

---

## Functional Requirements

1. **Run Finalization Aggregation & DB Pruning (`runner.py`)**:
   - In `_finalize_run`, before or during metrics computation:
     - Identify all `HostState` records for the completed `scan_run_id`.
     - Query `historical_active_ips` using the run's configured `ghost_window` (defaulting to `7d`) against completed runs within the cutoff.
     - Classify hosts:
       - **Active**: Has at least one port with `tcp_status == "open"` (retained in DB).
       - **Ghost**: No open ports, but `ip_address` is in `historical_active_ips` (retained in DB).
       - **Void**: No open ports and not in `historical_active_ips`.
     - For all **Void** hosts:
       - Group by parent `metadata_resolved_from` (e.g., `"143.106.1.1/24"`).
       - Delete individual void `HostState` rows and their cascading `PortState` records from SQLite.
       - For each parent with void hosts, insert a single synthetic `HostState`:
         - `scan_run_id = run.id`
         - `ip_address = f"Void ({count})"`
         - `metadata_resolved_from = parent`
         - `metadata_discovered_from_json = ["void_aggregated"]`
         - `ports_list = []`

2. **Metrics & Summary Accuracy (`alerts.py` & `runner.py`)**:
   - Update `compute_run_summary` so the `void` key in `run.metrics_json["summary"]` accurately reflects the total number of void hosts aggregated (e.g., `void: 256`), instead of being hardcoded to 0.

3. **Results Endpoints Consistency (`runs.py` & `results.py`)**:
   - Ensure `GET /api/runs/{id}/results` and `GET /api/results` return consistent results:
     - For completed runs, queries directly read the pruned, aggregated states from the database.
     - For active/in-progress runs (or edge cases where finalization hasn't run), apply `aggregate_void_nodes` dynamically so unfinalized data is never served raw to the client.

4. **Frontend Compatibility (`buildTree.ts`)**:
   - Zero breaking changes to the frontend.
   - When a parent has only void children: a single CIDR Target node is created containing child `Void (256)`, showing `void: 256` and `ghost: 0`.
   - When a parent has active and void children: active hosts and the synthetic `Void (N)` row are displayed cleanly under the parent CIDR.

---

## Non-Functional Requirements
- **Database Hygiene & Performance**: Eliminates thousands of dead `HostState` and `PortState` rows from SQLite upon completion of large subnet scans.
- **Integrity & Cascade**: Pruning cleanly deletes orphaned child records (`PortState`, `HttpRoutingCheck`, `TlsCertificate`).

---

## Acceptance Criteria
1. When scanning `143.106.1.1/24` on a clean DB, exactly **1** `HostState` row (`Void (256)`) remains in the database for that run upon completion.
2. `GET /api/runs/{id}/results` returns `results` containing `[{"ip_address": "Void (256)", "metadata": {"resolved_from": "143.106.1.1/24"}}]`.
3. In the frontend tree, `143.106.1.1/24` displays `Void (256)` with `void: 256` and `ghost: 0`.
4. If a subnet contains 1 active host, 1 ghost host, and 254 void hosts, the DB retains 3 rows (`143.106.1.X`, `143.106.1.Y`, and `Void (254)`).
5. All backend pytest test suites (`api/tests`, `engine/tests`) pass.

---

## Out of Scope
- Modifying engine target streaming logic.
- Redesigning alert notification Card layouts.
