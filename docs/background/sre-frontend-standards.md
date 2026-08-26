# SRE Frontend Standards and Design Paradigms

This document outlines the ideal frontend design standards, UI paradigms, and component library choices for Site Reliability Engineering (SRE) and Infrastructure Control Planes. It is specifically tailored for `site-health-check`, an OpenStack network health prober.

## 1. Primary SRE UX & Dashboard Standards

Trusted SRE and DevOps tools (e.g., Grafana, Datadog, Prometheus Web UI, AWS Console, Kibana) rely on specific UI idioms designed to maximize information density and rapid incident response.

### High-Density Data Tables
SRE dashboards prioritize function over whitespace. High-density data tables allow operators to scan hundreds of targets (CIDRs, IPs, Domains) rapidly. 
- **Sticky Headers & Columns**: Essential for maintaining context when scrolling through extensive target lists.
- **Pagination vs. Infinite Scroll**: Virtualized lists (e.g., `@tanstack/react-virtual`) are preferred over pagination for seamless scanning of infrastructure logs or target lists.

### Status Badges (Green/Amber/Red)
Status visualization must be immediate and unmistakable, often relying on the "traffic light" paradigm.
- **Green (Healthy)**: 200 OK, valid TLS, open expected ports.
- **Amber/Yellow (Warning)**: High latency, TLS expiring soon (e.g., < 7 days), retries increasing.
- **Red (Critical/Down)**: Port closed, connection timeout, 5xx HTTP codes, expired TLS.
- **Accessibility**: Ensure status indicators use both color and iconography (e.g., a green checkmark, a red triangle) for colorblind operators.

### Metric Time-Series Sparklines
For a health prober, inline sparklines (micro time-series charts) provide historical context without consuming the space of a full Grafana panel. They are ideal for visualizing latency trends or port flap history directly within table rows.

### Query/Filter Syntax Conventions
Effective infrastructure searching requires more than basic text matching.
- **Key-Value Search Bars**: Implement search bars that support structured querying (e.g., `status:200 port:443 cidr:192.168.1.0/24`). This mimics Kibana's KQL or Datadog's search syntax.
- **PromQL/LogQL Inspiration**: For complex metric querying, providing autocomplete and syntax highlighting in the search bar greatly enhances the UX.

## 2. Network Topology & Target Hierarchy Visualization

Visualizing the hierarchy from CIDR block -> IP node -> Port -> TLS/HTTP status requires robust graph libraries.

### Graph Library Comparison

1. **`@xyflow/react` (formerly React Flow)**
   - **Pros**: Deep integration with React, highly customizable node UIs (can easily embed React components like status badges or mini-charts within nodes).
   - **Cons**: DOM/SVG rendering can suffer performance hits on very large graphs without strict viewport virtualization. Requires external libraries (like Dagre) for auto-layout.
   - **Best For**: Interactive, highly detailed nodes where each IP/Port has a complex React-based UI.

2. **Cytoscape.js**
   - **Pros**: Canvas-based rendering, heavily optimized for massive datasets and complex graph theory algorithms. "Batteries-included" layout engines.
   - **Cons**: Imperative API requires wrapper logic to work smoothly with React state lifecycles. Customizing node UI to match modern React design systems is challenging.
   - **Best For**: Massive scale visualizations of thousands of nodes where topology structure is more important than node-level UI details.

### Auto-Layout Algorithms
- **Dagre**: A directed graph layout algorithm excellent for hierarchical data (e.g., CIDR at the top, branching down to IPs, then Ports). 
- **ELK (Eclipse Layout Kernel)**: Highly configurable and excellent for complex port-and-node structures common in networking.

## 3. Enterprise SRE Component Design Systems

Choosing the right design system accelerates development while adhering to SRE standards.

### PatternFly (Red Hat)
PatternFly is Red Hat's open-source design system, widely used in OpenShift and enterprise SRE tools.
- **Pros**: Built specifically for enterprise IT/SRE. Includes `@patternfly/react-topology`, an out-of-the-box topology visualization library tailored for infrastructure with built-in Dagre/Cola layouts and SRE-styled node components.
- **Cons**: Highly opinionated; customizing away from the "Red Hat look" can be difficult.

### Shadcn UI + Tailwind CSS
A highly popular approach utilizing Radix UI primitives and Tailwind CSS.
- **Pros**: Ultimate flexibility. You own the code for the components, making it easy to create ultra-dense data tables or custom dark modes. Integrates perfectly with tools like TanStack Table.
- **Cons**: Requires more upfront work to build out specialized SRE components (like sparklines or topology wrappers) compared to full-featured enterprise frameworks.

### Ant Design
A comprehensive enterprise-level UI design language.
- **Pros**: Massive ecosystem with incredibly robust, data-heavy components (complex tables, trees, statistics).
- **Cons**: Can be heavy and difficult to override styling (though improved in v5 with CSS-in-JS). 

## 4. Recommendations for `site-health-check`

1. **Component Library**: **Shadcn UI + Tailwind** combined with `@tanstack/react-table` is recommended for the highest flexibility in building dark-mode, high-density data tables with custom SRE status badges.
2. **Network Topology**: Use **`@xyflow/react` (React Flow)** paired with **Dagre** for auto-layout. Since `site-health-check` requires displaying specific status details (TLS, HTTP status) *on* the node, React Flow's DOM-based custom nodes are vastly superior to Cytoscape's canvas for UI fidelity.
3. **Filtering**: Implement a unified, autocomplete-enabled search bar using key-value parsers to filter the high-density tables (e.g., `tls:expired`).

---
**References:**
- PatternFly Topology Docs: https://www.patternfly.org/topology/
- React Flow (`@xyflow/react`): https://reactflow.dev/
- Cytoscape.js: https://js.cytoscape.org/
- Dagre Layout: https://github.com/dagrejs/dagre
