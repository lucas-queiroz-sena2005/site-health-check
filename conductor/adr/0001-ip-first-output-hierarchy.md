# IP-first output hierarchy

The engine's Result is structured as `IP → Port → Domain`, not `Domain → Result`. Even when the input is a URL (`https://susy.ic.unicamp.br`), the engine resolves the IP first and places all check outcomes under that IP address as the root key.

## Considered options

- **Domain-first** (`Domain → Result`): natural for application monitoring where each URL is a distinct service.
- **IP-first** (`IP → Port → Domain`): natural for infrastructure auditing where multiple domains share physical hosts.

## Why IP-first

In the Unicamp OpenStack environment, many domains resolve to the same IP (sitting behind the same Nginx proxy or Floating IP). Domain-first would produce duplicate, disconnected entries for what is physically one server. IP-first automatically groups them, producing an infrastructure map rather than a URL checklist — which is the primary use case (auditing shadow IT and discovering unregistered services via SAN recursion).

## Consequences

All downstream consumers — the Frontend Results Viewer, the Result Writer, and Prometheus label export — are built around the `IP → Port → Domain` tree. Changing the shape would require migrating all of them simultaneously.
