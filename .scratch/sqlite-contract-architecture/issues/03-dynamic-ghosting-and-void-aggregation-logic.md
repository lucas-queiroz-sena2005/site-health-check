# 03: Dynamic Ghosting and Void Aggregation Logic

**What to build:** Enhances the `GET /results` endpoint to accept the `?ghost_window=X` parameter. Implements the business logic to dynamically calculate Ghosts and squash contiguous dead IPs into a "Void Node" before returning the JSON payload to the frontend.

**Blocked by:** 02: Basic Result Retrieval Contract

**Status:** ready-for-agent

- [ ] The `GET /results` endpoint accepts an optional ghost window defined as `ghost_window: Annotated[str | None, Query(description="...")] = None`.
- [ ] Internal logic identifies "Ghost" nodes based on historical response data outside the given window.
- [ ] Internal logic correctly identifies "Void Space" (IPs that never responded).
- [ ] A squashing algorithm aggregates blocks of 10 or more contiguous dead/Void IPs into a single "Void Node" object.
- [ ] The aggregated JSON payload is successfully returned by the API and adheres to the unified target view contract.
