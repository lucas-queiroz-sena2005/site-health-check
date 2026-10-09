# 11. Tree Dynamic Compression, Filter Immunity, and Decoupled Details

Date: 2026-09-15

## Status

Accepted

## Context

The UI requires an elegant way to display a highly nested infrastructure tree (CIDR ➔ Host ➔ Port ➔ Checks) while preventing visual clutter. We faced several UX challenges:
1. When nodes are filtered, sparse single-child branches cause unnecessary nesting.
2. Clicking filters on structural nodes (like CIDR) can unexpectedly cause them to compress and lose their identity, breaking the filter toggle UX.
3. The raw JSON `DetailsPanel` was tightly coupled to leaf nodes, meaning inspecting a non-leaf node (like a CIDR or Host) was impossible without breaking the table.
4. "Clear Filter" buttons were ambiguously placed on leaf nodes inheriting filters, leading to confusing UX.

## Decisions

### 1. Dynamic Post-Filter Compression
Instead of compressing the tree *statically* before filtering (which broke when filters pruned children), compression now runs **dynamically after filtering**. If a filter aggressively prunes 2 failed ports and leaves a Host with exactly 1 active port, the UI will dynamically compress the Host and Port into a single row (`IP ➔ Port`) on the fly.

### 2. Filter Immunity (Amended in ADR-0012)
To prevent a node that is acting as the anchor for a filter (e.g., a CIDR node where the user clicked "2 Ghosts") from losing its explicit filter badge and context:
* **Amendment:** Under the Reactive Visual Compression architecture (ADR-0012), the visible compressed row *is* the topmost parent. Therefore, a parent with an explicit filter *can safely compress* with its unfiltered children, because its filter badge and clear button remain perfectly intact and functional on the resulting merged row. We now **only prevent compression if a *child* has an explicit filter**, as compressing it would swallow the child's explicit filter state into the parent.

### 3. Opt-Out Overrides for Inherited Filters
When a parent applies a deep filter to its children, the intermediate non-leaf nodes (e.g., a Host inside a filtered CIDR) now display a "Clear" button. 
* Clicking "Clear" on an *inherited* filter does not delete the parent's filter; instead, it injects an explicit `"all"` filter on the child node. This intelligently "opts out" that specific sub-tree from the parent's filter, revealing its original unfiltered children.

### 4. Omnipotent & Decoupled Details Dimension
The `DetailsPanel` has been completely decoupled from the tree's expansion state (`isExpanded`) and structural depth (`isLeaf`). 
* The details panel is toggled exclusively via a dedicated JSON button `{}` available on *every* node.
* It renders *before* the node's `subRows` to prevent the user from having to scroll past hundreds of expanded children just to read the parent's JSON payload.

## Consequences

* **Positive:** The UI gracefully handles massive sparse trees without burying users in empty nested folders.
* **Positive:** Deeply nested debugging is fully supported on any node at any depth via the decoupled Details button.
* **Positive:** Users can selectively break out of broad CIDR filters to inspect specific anomaly hosts.
* **Supersedes ADR 0007 Rule 3 (Structural Path Compression Protection):** ADR 0007 strictly prohibited `CIDR`, `Pool`, and `Classification` nodes from *ever* compressing. This strict type-based prohibition is now deprecated. The new **Filter Immunity** mechanic implicitly provides this protection (since users typically filter by clicking the root structural node, granting it immunity). If a structural node legitimately naturally slims down to a single child without an explicit filter, it is now permitted to compress dynamically to save space.
