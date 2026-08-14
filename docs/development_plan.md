# Development Plan & Technical Recommendations

This document outlines the CLI-First development path for `site-health-check`. By bypassing the YAML configuration initially, development focuses entirely on building a robust, high-performance Network Execution Engine.

## Phase 1: The CLI Interface
The goal is to build an interface that accepts dynamic network targets without configuration files.

### Technical Recommendations:
- **Zero-Dependency CLI:** Since we want a lightweight prober, do not install heavy CLI frameworks like `Click` or `Typer`. Use Python's built-in `argparse` module in `src/site_health_check/cli.py`.
- **Argument Structure:**
  - `--host`: String (e.g., `192.168.1.50`).
  - `--ports`: String. A comma-separated list or hyphenated range (e.g., `8000-8050,9000`).
  - `--check-tls`: Boolean flag (`action='store_true'`).
  - `--push-url`: String (optional).

### Port Range Expansion Logic (Example Algorithm)
You will need a helper function to convert the `--ports` string into a flat list of integers.
1. Split the string by `,`.
2. For each chunk, if it contains `-`, split by `-` and generate a `range(start, end + 1)`.
3. If no `-`, convert directly to `int`.

---

## Phase 2: The Core Network Probes & Orchestration
This is the heart of the engine, located in `src/site_health_check/core.py`. 

### 2.1 TCP Connectivity & TLS Deep Prober
- **Implementation:** `check_tcp_and_tls()` wraps the raw TCP socket using `context.wrap_socket(sock, server_hostname=host)`. It handles standard network timeouts and deep certificate parsing.

### 2.2 Unified Orchestrator (`scan_target`)
- **Recommendation:** Do not decouple the TCP check from the HTTP check. 
- **Implementation:** `scan_target()` loops through the requested ports. It first calls the TCP/TLS check. It then uses **Smart Protocol Detection** (looking at the TLS result) to dynamically build an `https://` or `http://` URL before firing `requests.get()`. This guarantees the HTTP request actually hits the specific port being audited.

### 2.3 Concurrent Execution (Crucial)
- **Recommendation:** Use Python's built-in `concurrent.futures.ThreadPoolExecutor(max_workers=50)` around the `scan_target` port loop. This allows you to attempt all 50 TCP handshakes simultaneously, finishing the entire scan in under 3 seconds.

---

## Phase 3: State Export & Observability
The engine must export its findings cleanly so external tools (like your future Flask GUI) can consume them.

### 3.1 JSON State Logger
- **Recommendation:** Do not write custom log formats. `scan_target` builds a master Python dictionary during execution nesting HTTP results under specific ports (e.g., `{ "ports": { 8000: {"tcp_status": "UP", "http": {...}} } }`).
- Use the CLI flag `-o results.json` to dump this dictionary cleanly to disk.
