# ADR 0004: API-Driven Historical Diffing & Void Aggregation

## Context
When scanning massive CIDR blocks (e.g., `/16`), the vast majority of IPs will not respond. Returning 65,000 "dead" JSON objects would crash the React frontend. Furthermore, the system must distinguish between IPs that have *never* existed ("Void Space") and IPs that recently stopped responding ("Ghosts").

## Decision

1. **On-the-fly Diffing (Dumb Scanner)**: 
   The Python execution engine (Scanner) remains completely stateless and historical-blind. It only records what it sees *now*. The FastAPI backend is solely responsible for calculating the historical diff (Active vs Ghost vs Void) on-the-fly when the React frontend queries the `/results` endpoint.
2. **Parameterized Ghost Aging**:
   The definition of a "Ghost" is not hardcoded. The React frontend will pass a time window parameter (e.g., `?ghost_window=14d`). If an IP hasn't responded within that window, FastAPI downgrades it from a Ghost back into Void Space.
3. **Dynamic Void Node Aggregation**:
   FastAPI will not return individual dead IPs. For any contiguous block of 10 or more dead/unassigned IPs, FastAPI will squash them into a single aggregate "Void Node" in the JSON response (e.g., `10.0.0.50-10.0.0.200 (Void)`). This preserves bandwidth and browser rendering performance while still accurately representing the fragmented subnet topology.

## Consequences
- **Pros**: The Python Scanner remains incredibly fast and simple. The UI gains a "time machine" slider (by adjusting `ghost_window`) to dynamically resurrect old Ghosts.
- **Cons**: The database queries in FastAPI will be slightly heavier, as they must join against historical scan records to calculate Ghost status dynamically. SQLite indexes on target/timestamp will be critical.
