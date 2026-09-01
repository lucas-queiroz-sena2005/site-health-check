---
labels: ["wayfinder:prototype", "status:closed"]
---

# Decision Ticket: Frontend UX Layout

## Question

How should the main navigation, dashboard, and topology views be laid out for the open internal tool?

**Goal:** Decide on the high-level layout structure and the specific pages/views required so the Vite/Tailwind frontend prototype can be aligned. We should determine what the user sees when they click "New Scan" and how they view the DAG results.

## Resolution: Frontend Specifications (Table-Only MVP)

The Frontend UX is defined by the following strict specifications for the MVP rewrite:

### 1. Must Haves (UX Requirements)
* **2-Page Application:** The entire UI is stripped down to exactly two pages: `Scheduled Scans` and `Scan Now`.
* **Topology Dropped:** The ReactFlow DAG viewer is officially dropped for the MVP. The UI will solely use the **Hierarchical Table** for data visualization.
* **Cascading Filter State (Table Viewer):** The Table must implement "Inherited State with Local Overrides". 
  * A Global Filter dictates default visibility (e.g., "Show Active Only").
  * Users can apply local filter overrides to specific rows.
* **SAN Pooling:** To prevent visual pollution, large lists of Subject Alternative Names (SANs) under a port will be collapsed into a single `[SAN List]` parent pool row.
* **No IP Pools (Except Void):** Artificial groupings like `[Active Pool]` or `[Ghost Pool]` are removed. IPs render natively under their Target. However, **[Void Space]** explicitly remains as a pool to group non-existent/unresponsive IPs.

### 2. Backend Responsibilities (FastAPI)
* **Auto-Classification:** The Frontend will no longer perform keyword string matching. FastAPI will compute classifications based on payload strings (`postgres`, `firewall`) and attach them as tags to the API response.
* **Dynamic CIDRs:** Targets will be rendered at their native scanned CIDR size (e.g., `/16` or `/32`); the frontend will not forcefully split them into `/24` blocks.

### 3. API Interaction Boundaries
* **GET `/api/jobs/{id}/results`:** Fetches the conflict-free, pre-merged `ip_state_json` tree for the Table.
* **POST `/api/jobs/launch`:** Triggers On-Demand Scans (sending `policy_id` and `classification_id`).
