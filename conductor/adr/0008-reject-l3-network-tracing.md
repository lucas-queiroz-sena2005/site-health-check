# ADR 0008: Reject L3 Network Tracing

**Status:** Accepted

## Context
During the design of the engine's topology discovery capabilities, we considered implementing L3 Network Tracing (Traceroute via ICMP or UDP TTL expiration) to explicitly map out the router and switch hops between the prober and the target. This would provide a deep, physical graph of the network.

## Decision
We will **not** implement L3 Network Tracing, nor will we use aggressive port-scanning or packet-flooding techniques.

The engine will strictly rely on Transport (L4) and Application (L7) layer relationships to build its graph—specifically TLS Subject Alternative Names (SANs) and HTTP Redirect chains.

## Consequences
- **Security & Stability (Positive):** Because the engine runs concurrently from within the Unicamp OpenStack datacenter, running hundreds of concurrent traceroutes would act as an internal DDoS attack, triggering security alarms and potentially creating a performance death spiral on the core routers. Sticking to standard TCP/HTTP requests avoids this.
- **Topology (Negative):** We lose visibility into the physical routing infrastructure (middleboxes, load balancers without proxy headers, etc.). The graph we build will be purely logical (Service A redirects to Service B) rather than physical (Packet went through Switch C).
