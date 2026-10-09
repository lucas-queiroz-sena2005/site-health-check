# ADR 0019: HTTP Redirects — First-Hop Semantics

## Status

Accepted — Roadmap phase 2. Supersedes the `redirects_to_url` placeholder note in
`CONTEXT.md` ("automatic redirects are currently allowed ... placeholder for the future
Go rewrite").

## Context

aiohttp follows redirects by default. As a result:
- `HttpRoutingCheck.status_code` stores the status of the *final* hop, possibly on
  another host.
- `redirects_to_url` is never populated.
- A `302 → https://login.microsoftonline.com/...` looks like a healthy `200` on the
  scanned IP.

## Decision

- Requests use `allow_redirects=False`.
- `status_code` is the status of the **first response from the scanned IP:port/vhost**.
- For 3xx responses, `redirects_to_url` = the `Location` header resolved to an
  absolute URL.
- We record **one hop only**. Native following of the chain by the HTTP client is rejected.
- Instead, the extracted `redirects_to_url` is enqueued as a new discovery task, subject to the engine's standard `out_of_scope_depth` tracking logic, just like SANs.

## Consequences

- **Positive:** The dashboard shows what the scanned server actually answers. The
  L7 path-tracing data (ADR 0007) finally exists. It is also cheaper: no extra
  requests to third-party hosts.
- **Negative:** Hosts that used to show `200` will show `301/302` once. The first
  historical diff after the rollout will flag those status changes.
- The anomaly metric (`status_code >= 400`) is unaffected.
