# `site-health-check` Architecture Specification

## 1. Goal
Design a lightweight, zero-dependency Synthetic Prober. It handles single URLs and port ranges, performs deep lower-level metrics checks (TLS, Latency, TCP handshakes), and acts as an "Infrastructure as Code" (IaC) bridge for observability tools.

---

## 2. Architecture Decisions & Scope Boundaries

### 2.1 In Scope (What it IS)
- **Multi-Protocol Prober:** Checks basic TCP connectivity, HTTP validation, and deep TLS inspection (expiration, cipher suites).
- **Port Range Scanner:** Natively supports scanning contiguous port ranges (e.g., "8000-8100") or explicit lists (`[8000, 8001]`), which is critical for OpenStack applications.
- **YAML Orchestrator:** Reads declarative configuration files utilizing the Template & Target mapping pattern to prevent boilerplate.
- **Stateful Logger:** Outputs a single, overwritten `results.json` file representing the current state of all monitors. This allows a separate Flask GUI or external tool to easily parse the latest results.
- **Generic Webhook Bridge:** Can optionally push execution results (UP/DOWN) to generic webhooks (`push_url`), supporting Uptime Kuma and other observability tools.

### 2.2 Out of Scope (What it IS NOT)
- **NOT a Visual Dashboard:** The tool will *not* generate HTML graphs or a web UI itself. A separate Flask application will be built to read the `results.json`.
- **NOT an Alerting Engine:** The tool will *not* send emails, Slack messages, or SMS. Alerting is delegated to external observability tools.
- **NOT a Background Daemon:** The tool will run as a single execution (CLI-first). Continuous execution scheduling is delegated to standard Linux `cron`.

---

## 3. Configuration Design (`config.yml`)

The configuration utilizes a hierarchical design. Variables defined at the top level are inherited by specific targets.

```yaml
monitors:
  # Example 1: Generic HTTP/TLS Check
  - name: "Unicamp Portal"
    default_push_url: "http://observability.local/api/push/generic"
    consults:
      - base_url: "https://example.com"
        track_metrics:
          - "tls_details"
          - "latency"
        paths:
          - path: "/login"
            push_url: "http://observability.local/api/push/login"
            request_payload_file: "secrets/login.json"

  # Example 2: OpenStack Port Range Check
  - name: "OpenStack Services"
    type: "tcp_range"
    host: "192.168.1.50"
    ports: 
      - "8000-8050"   # Supports string ranges
      - 9000          # Supports explicit lists/integers
    track_metrics:
      - "tcp_handshake"
      - "tls_details"
      - "http_status"
```
