# Specification: ADR 0022 - Slash16 Scale Strategy

## 1. Engine Architecture (Memory & Scale)
- **Round-Robin Generator:** Interleave target blocks (e.g., rotating through `/24` subnets) to naturally load-balance targets.
- **Strict Backpressure:** Implement an `asyncio.Queue(maxsize=1000)` to guarantee bounded memory usage.
- **Cache Persistence:** Deduplication caches (`seen_tcp`, `seen_http`) persist for the full scan duration.

## 2. Database & API Contract
- **Schema Update:** Add an explicit `subrun_id` column to the `HostState` model.
- **Run Metadata:** Remove `run_id` from pure metadata; use `run_id` + `subrun_id` in `HostState`.

## 3. Frontend Representation
- **Canonical Tree Hierarchy:** `GlobalRoot ➔ Subrun Node (e.g. 10.0.0.0/24) ➔ Host ➔ Port`.
- **On-Demand Fetching:** Subrun nodes will display a `[FETCH]` button to load data on request.
