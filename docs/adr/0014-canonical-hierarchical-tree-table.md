# ADR 0014: Canonical Hierarchical Tree-Table Architecture

## Status

Accepted

## Context

The initial frontend prototype (`frontend-prototype/`) attempted to visualize infrastructure data (Targets -> Classifications -> IPs -> Ports) as a 2D node-graph canvas using React Flow (`@xyflow/react`). However, real-world dense infrastructure CIDRs (e.g., /16 to /24 subnets) generating hundreds or thousands of ports caused severe canvas clutter, erratic edge routing, and poor readability. Navigating through massive topological DAGs proved impractical for operational observability.

## Decision

We establish the **Hierarchical Tree Table** (implemented via `HierarchicalTable` and `RenderTreeNode` in the current `frontend/`) as the canonical dashboard view. 

- This officially supersedes the DAG topology plans outlined in ADR 0007.
- The visual hierarchy strictly follows `GlobalRoot ➔ Target/CIDR ➔ Host ➔ Port ➔ HTTP Check`.
- Nodes are presented in an expandable list, utilizing Multi-Block Status Badges and standard table sorting.

## Consequences

- **Positive:** Massive improvement in rendering performance and data density. Thousands of nodes can be represented compactly without graph-layout algorithm overhead.
- **Positive:** Aligns the UX with standard file-manager and data-grid paradigms, making searching, sorting, and filtering native and intuitive.
- **Negative:** Loses the explicit 2D spatial representation of shared infrastructure components (e.g., cross-linked Load Balancer nodes). This is mitigated by clear parent-child lineage and grouping.
