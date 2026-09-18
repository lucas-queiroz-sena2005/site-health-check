# Data Lifecycle: The Full Loop (Scan Now)

This document traces the exact data schemas as a payload travels from the React Frontend, through FastAPI, down into the Engine, and back up to the user.

## 1. React sends to FastAPI
React sends a unified JSON envelope to trigger a scan.

**Path:** `POST /api/scans`
**Schema:**
```json
{
  "api_metadata": {
    "name": "Manual Subnet Check",
    "cron_expression": null, 
    "classification_name": "Infra"
  },
  "engine_payload": [
    {
      "target": "10.0.0.0/24",
      "ports": [443, 80],
      "flags": {
        "check_tcp": true,
        "check_http": true,
        "recursive_san_check": false
      }
    }
  ]
}
```

## 2. FastAPI writes to Database
FastAPI receives the request and creates a `ScanRun` row in SQLite using **SQLModel** to track the execution.

**Entity:** `ScanRun`
**Schema:**
```python
class ScanRun(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    status: str = "RUNNING" # PENDING, RUNNING, COMPLETED, FAILED
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None
    metrics_json: dict | None = Field(default=None, sa_column=Column(JSON))
```

## 3. FastAPI sends to Engine
FastAPI extracts the inner `engine_payload` array, converts it to a string, and pipes it into the CLI subprocess.

**Command:** `python -m site_health_check.cli -i -`
**Input (stdin) Schema:**
```json
[
  {
    "target": "10.0.0.0/24",
    "ports": [443, 80],
    "flags": { "check_tcp": true, "check_http": true, "recursive_san_check": false }
  }
]
```

## 4. Engine Streams to FastAPI (The Loop Back starts)
As the engine works, it prints logs to `stdout`. FastAPI captures this stream and pushes it to React via **Server-Sent Events (SSE)**.

**Path:** `GET /api/stream/{job_id}`
**Event Schema (SSE):**
```text
data: {"level": "info", "message": "[Worker W-1] Processing 10.0.0.5 on ports [443] (Depth 0)"}
```

## 5. Engine Outputs Final State
When the engine finishes, it dumps the final `HostState` dictionary as a JSON string to `stdout`.

**Engine Output Schema:**
```json
{
  "10.0.0.5": {
    "metadata": { "resolved_from": "10.0.0.5", "discovered_from": [] },
    "ports": {
      "443": {
        "tcp_status": "open",
        "tcp_latency_ms": 45,
        "tls_certificate": {
          "valid": true,
          "days_remaining": 89,
          "domains_discovered_sans": ["example.com"]
        },
        "http_routing_checks": {}
      }
    }
  }
}
```

## 6. FastAPI processes and saves the Output
FastAPI parses the Engine Output JSON, calculates the metrics, and updates the Database.

**Database Update:**
```python
job.status = "COMPLETED"
job.finished_at = datetime.utcnow()
job.metrics_json = {
    "total_targets": 1,
    "total_green": 1,
    "total_red": 0,
    "duration_seconds": 15
}
session.add(job)

# The raw engine output is saved to the Results table for historical diffing
result = Result(job_id=job.id, ip_state_json=engine_output_dict)
session.add(result)
```

## 7. React fetches the Unified Target View
When the user goes to the History Table and clicks the completed job, React fetches the processed results.

**Path:** `GET /api/runs/{id}/results`
**Schema:** (Returns the identical `HostState` JSON dictionary generated in Step 5, which React feeds directly into its Hierarchical Table component).
