---
labels: ["wayfinder:task", "status:closed"]
blocked_by: []
---

# Decision Ticket: API Endpoints

## Question

Based on the finalized database schema, what exact REST API endpoints need to be built in FastAPI to support operations (creating schedules, launching jobs, fetching results)?

**Goal:** Define the exact HTTP methods, routes, and JSON payloads so the backend can begin development.

## Resolution: API Contract

Based on the Schema-Driven UI and Live Operations requirements, FastAPI will implement the following core endpoints:

### 1. Schema-Driven Configuration
* **`GET /api/schemas/schedule`**
  Returns the dynamic JSON Schema describing available scanner features (e.g., boolean toggles for TLS checks, string inputs for custom ports). The frontend uses this to generate the form dynamically when creating a Schedule.

### 2. Scheduled Scans (Management)
* **`GET /api/schedules`**
  Returns all active/inactive cron schedules, used as "Templates" to populate dropdowns on the Live Operations page.
* **`POST /api/schedules`**
  Accepts a payload containing the Schedule Name, Cron expression, Target JSON list, Ports JSON, and Flags JSON. FastAPI parses this and generates the respective rows in `classifications`, `schedules`, and the junction table.

### 3. Live Operations (Scan Now)
* **`POST /api/jobs/launch`**
  Accepts an execution configuration (targets, ports, flags) and instantly creates a `job` in the database, saving the Immutable Snapshot. It sends the payload to the RabbitMQ broker (or asyncio queue for the MVP) for the Go Engine to process.
* **`GET /api/jobs/{id}/stream`**
  A **Server-Sent Events (SSE)** endpoint. FastAPI consumes live CLI-style string logs published by the running engine and streams them one-way to the frontend for a live terminal viewer.

### 4. Unified Target View (Results)
* **`GET /api/jobs/{id}/results`**
  Returns the strict `ip_state_json` tree for a specific job, pre-computed and invalidated by FastAPI's Data Hierarchy rules (ADR 0009). The frontend consumes this to render the Hierarchical Table.

### 5. Scan History (List)
* **`GET /api/jobs`**
  Returns a paginated list of historical jobs, including their pre-calculated `metrics_json` for at-a-glance summaries. Accepts query parameters (`?source=scheduled`, `?source=ad-hoc`, `?schedule_id={id}`) to filter the view.

