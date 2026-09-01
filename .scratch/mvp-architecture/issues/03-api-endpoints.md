---
labels: ["wayfinder:task", "status:closed"]
blocked_by: []
---

# Decision Ticket: API Endpoints

## Question

Based on the finalized database schema, what exact REST API endpoints need to be built in FastAPI to support the frontend operations (creating policies, launching jobs, fetching DAG results)?

**Goal:** Define the exact HTTP methods, routes, and JSON payloads so the backend can begin development.

## Resolution: API Contract

Based on the Schema-Driven UI and Live Operations requirements, FastAPI will implement the following core endpoints:

### 1. Schema-Driven Configuration
* **`GET /api/schemas/policy`**
  Returns the dynamic JSON Schema describing available scanner features (e.g., boolean toggles for TLS checks, string inputs for custom ports). The React frontend uses this to generate the form dynamically.

### 2. Scheduled Scans (Management)
* **`GET /api/schedules`**
  Returns all active/inactive cron schedules, used as "Templates" to populate dropdowns on the Live Operations page.
* **`POST /api/schedules`**
  The "3-in-1 Creator". Accepts a massive payload containing the Schedule Name, Cron expression, Target JSON list, and Policy JSON. FastAPI parses this and generates the respective rows in `policies`, `classifications`, and `schedules`.

### 3. Live Operations (Scan Now)
* **`POST /api/jobs/launch`**
  Accepts a `policy_json` and `targets_json` (either from a selected template or manual override) and instantly creates a `job` in the database, sending the payload to the RabbitMQ broker for the Go Engine to process.
* **`WS /api/jobs/{id}/stream`**
  A **WebSocket** endpoint. FastAPI consumes live CLI-style string logs published by the running Go Engine/Dispatcher via RabbitMQ, and streams them instantly to the React frontend to populate a live terminal viewer.

### 4. Unified Target View (Results)
* **`GET /api/jobs/{id}/results`**
  Returns the strict `ip_state_json` tree for a specific job, pre-computed and invalidated by FastAPI's Data Hierarchy rules (ADR 0009). The frontend consumes this to render the Hierarchical Table.

### 5. Scan History (List)
* **`GET /api/jobs`**
  Returns a paginated list of historical jobs, including their pre-calculated `metrics_json` for at-a-glance summaries. Accepts query parameters (`?source=scheduled`, `?source=ad-hoc`, `?schedule_id={id}`) to filter the view.
