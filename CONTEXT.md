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

**Job**:
A user-submitted scan request from the Frontend. Carries a Target expression (which may be a CIDR block, IP range, or category name), ports, flags, and labels. The Dispatcher expands one Job into many Tasks. Does not exist in the current CLI phase.
_Avoid_: scan request

**Label**:
A key-value pair attached to a Task and passed unchanged through to its Result (e.g., `target_group: professors`). Used to filter and group Results in Prometheus without modifying the Scanner.
_Avoid_: tag, metadata, annotation

**Classification**:
A logical organizational grouping assigned to a Target or range (e.g., `professors`, `datacenter_core`). Helps SREs group, schedule, and run targeted scans across vast infrastructure ranges without typing raw CIDR expressions.

**Sub-classification**:
A specific sub-tag under a Classification (e.g., `physics_dept`, `hypervisors`).


### Scan outputs

**Result**:
The complete outcome of scanning one IP address — its port states, TLS certificates, and HTTP routing check outcomes, keyed by IP. Multiple Targets that resolve to the same IP produce one merged Result, not separate ones.
_Avoid_: report, output

**IpState**:
The in-code representation of a Result. A tree rooted at one IP address, branching to PortStates, each of which may carry a TlsCertificate and a map of HttpRoutingChecks.
_Avoid_: state, record

### Services

**Dispatcher**:
The service that receives a Job and expands it into individual Tasks published to the Broker. Never probes the network.
_Avoid_: splitter, job creator

**Scanner**:
The service that consumes Tasks, performs network probes (TCP connect, TLS handshake, HTTP request), and publishes Results. Never reads the database and never expands CIDR blocks.
_Avoid_: execution engine, worker, prober

**API**:
The FastAPI service that accepts Job requests from the Frontend, persists them to SQLite, and serves paginated Results. Never probes the network.
_Avoid_: backend, server

**Broker**:
The RabbitMQ instance that decouples the Dispatcher from the Scanner. Holds Tasks until a Scanner worker consumes them, and carries Results back to the Result Writer.
_Avoid_: queue, message bus, transport
