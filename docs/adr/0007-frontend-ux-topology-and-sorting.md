# 7. Frontend UX, Topology DAG, and Sorting Mechanics

Date: 2026-08-27

## Status

Accepted

## Context

The UI prototype handles heavily nested infrastructural data (Targets -> Pools -> Classifications -> IPs -> Ports -> SANs/HTTP). Visualizing and filtering thousands of nested elements is a primary UX challenge. We need a standardized approach to table layouts, node state management, topology graph generation, and user interactions.

## Decisions

### 1. Multi-Block Deep Status Aggregation
Instead of assigning a single generalized "Status" (e.g., Red/Green) to structural nodes, status is dynamically aggregated bottom-up. Parents natively display discrete interactive block badges (e.g., `[ 5 Active ]`, `[ 2 Failed ]`, `[ 1 Void ]`) representing exactly how many descendants exist in that state.
* **Deep Filtering:** Clicking a specific status badge on a parent instantly applies an inline recursive filter, expanding the node while aggressively pruning out all siblings that do not match the selected status category.

### 2. DAG Cross-Linking in Topology Views
Topology graphs must represent real-world infrastructure sharing (e.g., load balancers serving multiple backend IPs resolving to the same domain).
* When building the layout tree, structural nodes are tracked globally. If multiple parents converge on a shared domain/SAN, the domain node is drawn exactly once (under the first expanded parent).
* Subsequent expansions of sibling parents that share the node render a dashed, animated **cross-link arrow** pointing back to the existing shared node instead of duplicating the node in the layout or clustering edges chaotically.

### 3. Structural Path Compression Protection
Path compression optimizes deep, sparse trees by merging single-child chains (e.g., `IP ➔ Port ➔ SAN`).
* **Rule:** Root structural groupings (`CIDR Target`, `Pool`, `Classification`) are strictly prohibited from participating in path compression. This ensures the foundational semantic structure is never lost (e.g., preventing a confusing merged node like `Ghost Pool ➔ Unreachable ➔ Failed IP`).

### 4. Deep Recursive State Wipes
When a user collapses an expanded node, the UI deeply traverses the nested tree and forcefully wipes the expanded state of all its descendants. This avoids "annoying state saving" where collapsing and re-expanding a root folder unloads a chaotic, deeply-expanded sub-tree onto the screen.

### 5. File-Manager Style Sorting & Contextual Views
* **Table Headers:** Sorting is executed exclusively via interactive column headers (`Resource Path`, `Compressed Type`, `TLS`, `Latency`, `Status`), matching standard OS file managers.
* **Topology:** A dedicated floating configuration panel handles sorting.
* **Saved Views:** Context configurations explicitly encapsulate search regex strings, active status filters, *and* sort directions (e.g., "Critical Outages & Ghosts" defaults to `Status (Descending)`).

### 6. Expandable Rows for Scheduled Scans
To avoid modal fatigue, operational views like Scheduled Scans utilize compact top-level tables. Clicking a row dynamically expands it downward into an inline details panel (showing Config Flags, Logs). 
* Action buttons (Scan Now, Edit, Delete) reside inside the expanded panel.
* Triggering `Edit` seamlessly transitions the expanded details panel into an inline editable form without breaking context.

### 7. Smart Heuristic Classifications
Rather than relying solely on manual DB tags, the frontend automatically categorizes unassigned IPs by running heuristic scans across discovered TLS SANs and HTTP Routing domains (e.g., domains containing `gitlab` fall into `source_control`, `fw`/`vpn` into `network_security`).

## Consequences

* **Positive:** The UX remains highly performant and extremely clean, avoiding "messy graph layouts" and "information overload" despite rendering massive IP trees.
* **Positive:** Users can fluidly slice data by sorting, grouping, and deeply filtering on exact status anomalies.
* **Negative:** Implementing DAG routing in a traditional tree-based node renderer (React Flow custom layouts) requires careful global state tracking (`drawnIds` sets) during layout generation.
