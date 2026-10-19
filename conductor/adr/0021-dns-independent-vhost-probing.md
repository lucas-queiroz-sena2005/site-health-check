# ADR 0021: DNS-Independent, SNI-Aware Virtual Host Probing

## Status

Proposed — Roadmap phase 4. Depends on ADR 0017 (output volume is streamed) and
ADR 0020 (`--rate` caps the extra connections).

## Context

`check_virtual_hosts` exists, and the HTTP side is correct: `SingleIPResolver` pins the
connection to the IP while SNI and `Host:` carry the domain. But vhost discovery is
really "vhost via DNS":

1. A SAN found on IP X is resolved with `gethostbyname`, and only the resolved IP is
   probed.
   - A SAN with no DNS record is dropped ("Could not resolve").
   - A SAN whose DNS points elsewhere is never tested on X.
   - These are exactly the internal or forgotten vhosts a blackbox view should reveal.
2. When a SAN resolves back to X, `seen_tcp` skips the TLS handshake. The certificate
   served **for that SNI** is never read. Servers with one certificate per SNI hide
   their other certificates and SANs, so the BFS misses whole branches.
3. Only the first A record is used, and the resolver runs in the default thread pool
   (a bottleneck under SAN expansion).
4. Wildcard SANs are skipped and not recorded anywhere.

## Decision

1. **In-scope vhost probe:** every SAN discovered on `ip:port` enqueues
   `{target: ip, host_header: san}` with no DNS lookup. It is tested on the IP where the
   certificate was seen.
2. **Out-of-scope expansion stays DNS-based:** the SAN is *also* resolved, and if it
   points to a new IP it follows the existing `out_of_scope_depth` rules.
3. **TLS dedup key includes SNI:** `ip:port:sni`. A vhost probe performs an SNI
   handshake, and its SANs feed the BFS.
4. **Guard rails:**
   - `--max-vhosts-per-ip` (default 50): extra SANs are recorded but not probed.
   - Wildcard SANs are recorded in metadata.
   - Async DNS (`aiodns`) returns all A records.

## Open Question

Where do SNI-specific certificates go? `PortState` holds a single `tls_certificate`.
- **A (recommended first):** harvest SANs from SNI certificates for discovery only and
  store nothing new. No schema change.
- **B:** add an optional `tls_certificate` to `HttpRoutingCheck` (one per vhost).
  Additive, but needs a DB column and frontend display.

## Consequences

- **Positive:** Finds vhosts with no DNS record, or whose DNS points elsewhere.
  Recovers certificates hidden behind SNI.
- **Negative:** More probes per IP. The cap and `--rate` keep it bounded.
- **Negative:** Changes BFS semantics. The first runs after rollout will show "new"
  domains in historical diffs.
