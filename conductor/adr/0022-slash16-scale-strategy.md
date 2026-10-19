# ADR 0022: /16 Scale Strategy (Engine Memory, API Aggregation, Drill-Down UI)

## Status

Proposed — Roadmap phase 5. Depends on ADR 0017 (deltas) and ADR 0018 (partial runs).

## Context

/16 scans are a real use case. Today a /24 is effortless, but at /16 scale:

- **The CLI builds the whole target list up front.** `expand_target_ranges` turns
  65,534 IPs into 65,534 task dicts, and the old CLI even printed that payload.
- **The engine keeps every `IpState` in memory** until it exits.
- **`GET /api/runs/{id}/results` returns everything** in one response. Void
  aggregation (ADR 0004) compresses unreachable IPs, but thousands of active hosts
  still reach React at once.
- **IPs are probed in address order.** That concentrates load on one subnet or
  switch at a time.

## Decision

1. **Engine — lazy target generation:** targets come from a generator, not a list
   (same spirit as `TargetStreamer` in ADR 0006). The order is shuffled with a cheap
   permutation, so load spreads across subnets.
2. **Engine — bounded memory:** when `-o` is not set, the engine keeps only its dedup
   sets (`seen_tcp`, `seen_http`) and drops each delta after writing it. This is what
   ADR 0017's delta format allows.
3. **API — aggregation endpoint:** `GET /api/runs/{id}/summary?group=24` returns
   per-/24 counters `{cidr, active, void, ghosts, anomalies}`.
   `GET /api/runs/{id}/results?cidr=10.0.5.0/24` returns one block.
4. **Frontend — drill-down above a threshold:** above N hosts (e.g. 1024), the
   dashboard opens on the /24 summary. Clicking a block loads its tree, using the
   existing tree-table (ADR 0014). Below the threshold nothing changes.

## Deferred

- Resume of a crashed run (`--exclude-from` the IPs already ingested). Partial results
  (ADR 0018) cover most of the pain.
- Splitting one run into multiple engine processes per CIDR slice.

## Consequences

- **Positive:** Engine memory becomes independent of the network size, and the
  browser never receives a /16 at once.
- **Negative:** New API surface and a second frontend view level.
- **Negative:** `-o` (aggregated JSON) still needs the full state in memory. It stays
  available for CLI users scanning moderate ranges.

## Final Technical Design (from Conductor Planning)

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
