# 12. Reactive Visual Tree Compression

Date: 2026-09-16

## Status

Accepted

## Context

Our initial approach to tree compression (defined in ADR-0011) was to compress the tree *dynamically after filtering*. However, the implementation of this relied on a utility script (`compressTree.ts`) that manually traversed the tree, mutated node IDs (e.g., creating fake IDs like `host->port`), duplicated properties, and merged payloads into a single node before passing it to React for rendering.

This object-mutating approach proved to be a React anti-pattern. It broke the natural component lifecycle and caused synchronization bugs when explicit filters were applied or cleared (as the fake IDs no longer matched the true node IDs expected by the filter state hooks). It also made it difficult to access the `rawPayload` of child nodes within a compressed row.

## Decisions

### 1. Reactive Visual Compression
We shifted to **Reactive Visual Compression** handled entirely inside the `<RenderTreeNode>` React component. The tree data structure remains pure and 1:1 with the backend topology. 

Instead of pre-compressing the data, the component natively walks down unary (single-child) chains at render time using a `while` loop. It dynamically aggregates the `label`, `type`, `latencyMs`, and `tlsInfo` of the children and visually applies them to the parent row, effectively skipping the rendering of intermediate `<TableRow>` elements.

### 2. Cumulative Node Details
When rendering a compressed row, the visual compression loop now dynamically aggregates the `rawPayload` of every node in the chain. It packs each node's payload into a single object keyed by type (`host_details`, `port_details`, `http_details`, etc). The `<DetailsPanel>` parses this pattern into distinct UI cards, giving the user access to the true cumulative data of the entire chain.

### 3. Dynamic Void Node Generation
To ensure missing IPs ("Void Space") are structurally visible in the tree (rather than just numeric badge counts on the target), we introduced dynamic Void node generation in `buildTree.ts`. By calculating `total_hosts - hostNodes.length` from the Target metadata, the parser natively injects a `Void` node as a child of the Target. This allows the tree to natively render a distinct row for missing IPs and cleanly bubble up void stats without relying on mock or fake root nodes.

## Consequences

* **Positive:** The tree data structure remains pure, eliminating manual O(N) traversals and state-sync bugs.
* **Positive:** Filters now interact exclusively with true node IDs, making the React state highly predictable.
* **Positive:** The `DetailsPanel` can natively access and display the deep context of compressed branches.
