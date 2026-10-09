# Site Health Check: Control Plane & Triage Architecture

As the architecture evolves from a simple CLI tool into an enterprise observability platform, it adopts a "Hospital Triage" metaphor. The system manages infrastructure targets like patients, classifying them into wards (CIDRs), assessing their chronic health, and allowing ad-hoc surgical interventions (custom scans).

## 1. Classifications (The Hospital Wards)

Targets are no longer just raw IP addresses; they are enriched with metadata (tags). 

- **Primary Classification:** A broad category (e.g., `Unicamp Students`, `Professors`).
- **Sub-classification:** More specific tags (e.g., `Physics Dept`, `Critical Infrastructure`).
- **Configurations per Room (IP):** Just as a hospital room has specific life-support monitors, a specific IP or Domain can have customized test configurations (e.g., "Check payload for 'Welcome'", "Expect HTTP 200").

### The Role of SQLite
The React Frontend (Control Plane) manages these classifications. When an admin tags `10.0.0.1` as `priority: critical`, this mapping is saved in the SQLite Database. The Engine reads this SQLite database to know *what* to scan and *how* to tag it in the output.

## 2. Dynamic Scheduling via Prometheus

Does the Engine run every 15 seconds? **No.** The Engine performs the heavy lifting (DNS resolution, TLS SAN spidering) periodically (e.g., hourly).

**Prometheus manages the high-frequency heartbeat.** 
When the Engine finishes its deep scan, it generates a `prometheus-targets.json` file. Crucially, it injects the Classifications as **Prometheus Labels**.

```json
[
  {
    "targets": ["10.0.0.1:443", "physics.unicamp.br"],
    "labels": {
      "classification": "professors",
      "sub_classification": "physics",
      "priority": "critical"
    }
  },
  {
    "targets": ["10.0.5.5:80", "student-blog.unicamp.br"],
    "labels": {
      "classification": "unicamp_students",
      "priority": "low"
    }
  }
]
```

In the `prometheus.yml` configuration file, Prometheus can be instructed to scrape targets at different intervals based on these labels:
- **Rule 1:** If `priority == "critical"`, ping every 15 seconds.
- **Rule 2:** If `priority == "low"`, ping every 2 hours.

This offloads all the complex scheduling and state management to Prometheus, which is heavily optimized for it.

## 3. Ad-Hoc / Surgical Scans (Frontend Triggered)

Sometimes, an SRE needs instant gratification without waiting for the next cron cycle or changing the persistent database configuration.

- **The Scenario:** A new domain is acting up in the "Unicamp Students" block. The SRE wants to run a deep TCP scan *immediately*, but only for this specific investigation.
- **The Execution:** The SRE clicks "Surgical Scan" in the React UI and selects the `Unicamp Students` classification.
- **The Data Flow:** The React UI sends a request to the Flask API. The Flask API spawns a transient, one-off subprocess of the Engine: `site-health-check --target unicamp_students --tcp-only`. 
- **The Result:** The Engine runs instantly and streams the JSON results directly back to the Flask API, which pushes it to the UI via WebSockets or polling. 
- **Database Impact:** This transaction **bypasses the SQLite database**. It is a transient investigation, leaving the persistent hospital charts unmodified. Every ad-hoc scan is timestamped and logged for auditing purposes.
