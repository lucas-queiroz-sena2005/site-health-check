# `site-health-check` Architecture Specification

## 1. Goal
Design a lightweight, zero-dependency Synthetic Prober tailored for complex, virtualized environments like Unicamp's OpenStack cloud. The engine will handle single URLs, port ranges, and perform deep lower-level metric checks (TLS, Latency, TCP handshakes), acting as an "Infrastructure as Code" (IaC) bridge for observability tools.

---

## 2. Architecture Decisions & Scope Boundaries

### 2.1 In Scope (What it IS)
- **Multi-Protocol Prober:** Checks basic TCP connectivity, HTTP validation, and deep TLS inspection (expiration, cipher suites, SAN extraction).
- **Port Range Scanner:** Natively supports scanning contiguous port ranges (e.g., "8000-8100") or explicit lists (`[8000, 8001]`), which is critical for OpenStack applications utilizing Floating IPs.
- **Explicit Target Routing:** Understands the distinction between DNS resolution and HTTP Host headers to properly navigate reverse proxies (like NGINX).
- **Stateful Logger:** Outputs a single, overwritten `results.json` file representing the current state of all monitors. This allows a separate GUI or external tool to easily parse the latest results.
- **Declarative Orchestration (Future Phase):** Will eventually orchestrate multiple explicit target checks using a declarative YAML configuration file.

### 2.2 Out of Scope (What it IS NOT)
- **NOT a Visual Dashboard:** The tool will *not* generate HTML graphs or a web UI itself.
- **NOT an Alerting Engine:** The tool will *not* send emails, Slack messages, or SMS. Alerting is delegated to external observability tools.
- **NOT a Background Daemon:** The tool runs as a single execution (CLI-first). Continuous execution scheduling is delegated to standard Linux `cron`.

---

## 3. The Core Execution Engine

The architecture is divided into modular components to handle network probing efficiently, with a primary focus on navigating virtualized networks.

### 3.1 Resolving the Virtualized Environment
A traditional ping check is insufficient for this environment. The core engine must implement layered resolution:
- **DNS Resolution:** Translates an FQDN to an IP address.
- **Port Connectivity (TCP):** Validates the specific port (e.g., 443) is open.
- **HTTP/Proxy Validation:** Injects the target FQDN into the HTTP `Host` header to ensure NGINX or the OpenStack VM routes the traffic to the correct internal container.

### 3.2 Component Breakdown
The codebase will be modular to support this workflow:
1.  **`parser.py` (Input Parsing):** Reads explicit target instructions (via CLI or JSON payload) and validates the execution schema.
2.  **`core.py` (The Router):** Orchestrates the checks, spinning up concurrent execution threads (e.g., via `ThreadPoolExecutor`) to scan ranges quickly.
3.  **`operations/` (The Checkers):**
    *   `dns_check.py`: Explicit DNS querying.
    *   `tcp_check.py`: 3-way TCP handshake verification.
    *   `http_check.py`: Full stack verification (DNS + TCP + HTTP Host Header).

---

## 4. Configuration Vision (YAML Orchestration)

While the immediate engine is CLI and JSON-payload driven for explicit targeting, the ultimate goal is a hierarchical YAML configuration that maps targets and templates.

```yaml
monitors:
  # Example: OpenStack Port Range Check (Floating IP)
  - name: "OpenStack Services"
    type: "tcp_range"
    host: "192.168.1.50"
    ports: 
      - "8000-8050"
    track_metrics:
      - "tcp_handshake"
      - "tls_details"
```
