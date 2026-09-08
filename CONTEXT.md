# Site Health Check

A synthetic prober for Unicamp's OpenStack cloud. It scans domains, IPs, and CIDR ranges for TCP connectivity, TLS validity, and HTTP routing correctness — and recursively discovers additional targets through TLS certificate SANs.

## Language

### Scan inputs

**Target**:
A raw, unresolved address that identifies something to be scanned. Can be a domain name, bare IP, URL, or CIDR range. Resolution (DNS lookup, CIDR expansion into individual IPs) happens downstream; a Target is the input expression, not the resolved result.
_Avoid_: host, destination

**Task**:
The atomic unit of work the Scanner consumes. Represents one expanded, single-address Target together with its ports and flags. A CIDR /24 block produces 254 Tasks. In the current CLI the Task is delivered via an in-process queue; in the distributed architecture it is a RabbitMQ message published by the Dispatcher.
_Avoid_: job, payload, message

**ScanRun**:
A user-submitted scan request from the Frontend (formerly 'Job'). Carries a Target expression, ports, flags, and labels. The Dispatcher expands one ScanRun into many Tasks.
_Avoid_: scan request, job

**Label**:
A key-value pair attached to a Task and passed unchanged through to its Result (e.g., `target_group: professors`). Used to filter and group Results in Prometheus without modifying the Scanner.
_Avoid_: tag, metadata, annotation

**TargetGroup**:
A logical organizational grouping assigned to a Target or range (e.g., `professors`, `datacenter_core`). Helps SREs group, schedule, and run targeted scans across vast infrastructure ranges without typing raw CIDR expressions. Contains an `is_ad_hoc` flag for unsaved groups.
_Avoid_: classification

**Sub-group**:
A specific sub-tag under a TargetGroup (e.g., `physics_dept`, `hypervisors`).
_Avoid_: sub-classification


### Target States

**Ghost**:
An IP address or domain that failed to respond to the current scan, but has a historical record of responding in a previous scan. This indicates a potential outage or infrastructure regression.
_Avoid_: dead node, missing target

**Void Space**:
IP addresses within a scanned CIDR block that did not respond and have no historical record of ever responding. These are typically unassigned IPs or empty subnets.
_Avoid_: empty IPs, unresponsive block

### Scan outputs

**Result**:
The complete outcome of scanning one IP address — its port states, TLS certificates, and HTTP routing check outcomes, keyed by IP. Multiple Targets that resolve to the same IP produce one merged Result, not separate ones.
_Avoid_: report, output

**Unified Target View**:
A merged representation of a target's health built by FastAPI across multiple ScanRun Results.
_Avoid_: global health, merged graph

**Data Hierarchy Invalidation**:
The rule that foundational state changes (e.g., L4 Port Closed) automatically invalidate and hide dependent states (e.g., L7 HTTP data) from older scan runs during merging, preventing misinformation.

**HostState**:
The in-code representation of a Result (formerly 'IpState'). A tree rooted at one IP address, branching to PortStates, each of which may carry a TlsCertificate and a map of HttpRoutingChecks.
_Avoid_: state, record, ip state

**PortState**:
The physical reality of a single port on an IP. Includes `tcp_latency_ms`, which measures the strict socket establishment time (TCP 3-way handshake) independently of application responsiveness.

**HttpRoutingCheck**:
The result of an HTTP test against a specific domain on a port. Includes `http_latency_ms` (Time-to-First-Byte) to measure application responsiveness, `server_header`, and `redirects_to_url` (which captures HTTP 302 Locations for L7 path tracing). Note: To fetch final destination data natively, automatic redirects are currently allowed, so `redirects_to_url` acts as a placeholder for the future Go rewrite.

**resolved_from**:
A metadata field on the HostState indicating the identity of the target. It answers: "What hostname did we type into the DNS resolver to find this IP?"

**discovered_from**:
A metadata field on the HostState representing the graph edge. It lists the originating entities (IPs or Domains) that caused this Target to be queued (e.g., via a SAN or redirect). Distinct from `resolved_from`.

### Services

**Dispatcher**:
The service that receives a ScanRun and expands it into individual Tasks published to the Broker. Never probes the network.
_Avoid_: splitter, job creator

**Scanner**:
The service that consumes Tasks, performs network probes (TCP connect, TLS handshake, HTTP request), and publishes Results. Never reads the database and never expands CIDR blocks.
_Avoid_: execution engine, worker, prober

**API**:
The FastAPI service that accepts Scan requests from the Frontend, persists them to SQLite as ScanRuns, and serves paginated Results. Never probes the network.
_Avoid_: backend, server

**Broker**:
The RabbitMQ instance that decouples the Dispatcher from the Scanner. Holds Tasks until a Scanner worker consumes them, and carries Results back to the Result Writer.
_Avoid_: queue, message bus, transport


## Architectural Decisions Log

- **ADR 0001**: Single Context & Lightweight ADRs.
- **ADR 0002**: Stateless Isolation for Scan Targets (Overlapping target scans permitted).
- **ADR 0003**: Single-Process Monolith MVP (`asyncio.Queue` backend).
- **ADR 0004**: API-Driven Historical Diffing & Void Aggregation (FastAPI on-the-fly diffing, parameterized `?ghost_window=14d`, Void node squashing).
- **ADR 0005**: Saved Views & Read-Time UI Filtering (Universal scan targets, read-time filtering, SQLite saved view states).
- **ADR 0006**: Go Engine Architecture & Pluggable TargetStreamer (Go channel core, `InMemSplitter` for CLI, `RabbitMQConsumer` for distributed).
- **ADR 0007**: Frontend UX, Topology DAG, and Sorting Mechanics (Multi-Block node stats, File-manager sorting, Expandable UX rows, and DAG state).
- **ADR 0008**: Reject L3 Network Tracing (Strictly rely on L7/L4 data to prevent OpenStack DDoS).
- **ADR 0009**: Unified Target Merging & Data Hierarchy Invalidation (FastAPI dynamic merge rules to prevent misinformation).

