# Unified Target Merging & Data Hierarchy Invalidation

## Status

Superseded by ADR 0013 (Abandon Unified Global View).

FastAPI will merge the latest `ip_state_json` across multiple policies for the same target to build a "Unified Target View", but it will enforce strict "Data Hierarchy Invalidation" where recent foundational failures (e.g., Port Closed) actively hide older dependent data (e.g., HTTP 200 OK) to prevent misinformation.

## Context

Different policies (e.g., hourly HTTP checks vs weekly Deep Port Scans) produce fragmented results. If a user wants to view the overall health of a Classification, they need a merged graph. However, simply overlaying JSON results causes "misinformation"—for example, an old HTTP scan might say a site is up, but a recent fast port scan says the port is now closed. 

## Decision

1. **Recency Wins:** The most recent job data overwrites older data for the *same* layer.
2. **Data Hierarchy Invalidation:** If a recent job indicates a foundational failure (like a closed L4 port), FastAPI must invalidate and hide any older L7 data (like HTTP or TLS) for that target. We cannot guarantee its correctness if the port is closed.
3. **Live Re-calculation:** Dynamic properties like TLS expiration validity are calculated live at query time based on the current date, rather than returning the raw stale string from the original job result.

## Consequences

- The FastAPI backend takes on the computational load of merging JSON results and applying invalidation rules dynamically at read-time.
- The frontend receives a clean, conflict-free DAG payload and does not have to worry about data hierarchy logic.
