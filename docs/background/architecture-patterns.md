# Architecture Patterns & Mental Models

Reference material for understanding the structural decisions behind `site-health-check`. These are the mental models used during design; they are not domain terms (those live in `CONTEXT.md`).

---

## Hexagonal Architecture (Ports & Adapters)

The Scanner's core probing logic is completely isolated from the outside world. It defines a "Port" (an interface), and "Adapters" are plugged into that port:

- **`RabbitMQAdapter`** — feeds Tasks from the queue (distributed phase)
- **`CLIAdapter`** — feeds Tasks from terminal arguments (current phase)

This means the Scanner engine is reusable across both CLI and distributed deployments without modification.

---

## Scatter-Gather (Splitter Pattern)

The pattern of breaking a massive Job into atomic Tasks (scattering), processing them independently, and writing their Results back to the database (gathering).

```
Job (1 CIDR /24)
    └── Dispatcher
            ├── Task → Scanner → Result
            ├── Task → Scanner → Result
            └── Task × 254 → ...
```

---

## IP-First Output Hierarchy

The output is always structured as `IP → Port → Domain`, not `Domain → Result`. Even if the input was a URL like `https://susy.ic.unicamp.br`, the engine resolves the IP first and places all results under that IP.

**Why**: Multiple domains may resolve to the same IP (OpenStack reverse proxy). IP-first ensures they are automatically grouped, creating an infrastructure map rather than a disconnected list of URL checks.

---

## Hospital Triage Metaphor (Control Plane Phase)

Targets are managed like hospital patients:
- **Wards** = CIDR blocks / classifications (e.g., `students`, `professors`)
- **Chronic monitoring** = periodic deep scans (hourly, via cron/Prometheus)
- **Surgical scans** = ad-hoc, one-off investigations triggered from the Frontend without modifying the persistent database

---

## SAN Recursive Discovery (BFS)

When the Scanner finds a TLS certificate, it extracts all Subject Alternative Names (SANs) and re-queues each non-wildcard SAN as a new Task. This is an internal breadth-first search loop that stays self-contained within one Scanner instance. It discovers "shadow" domains — services active on the infrastructure that are not formally documented.
