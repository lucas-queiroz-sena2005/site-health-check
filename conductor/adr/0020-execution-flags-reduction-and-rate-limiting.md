# ADR 0020: Execution Flags Reduction & Global Rate Limiting

## Status

Accepted — Roadmap phase 3.

## Context

The engine is operated from privileged machines against infrastructure we own.
Several flags exist that either do nothing or serve a purpose we reject:

| Flag | Reality today |
|---|---|
| `check_tcp` | Exposed in CLI/API/UI, **never read by the engine**. |
| `check_http` | Exposed in CLI/API/UI, **never read by the engine**. |
| `--push-url` | CLI only, never used. |
| `spoof_user_agent` | Sends a fake Chrome User-Agent to avoid WAF blocks (disguise). |
| `expected` / `undesired` + `catcher.py` | HTML body assertions. One global string list for every host of a /16 is meaningless in blackbox discovery. |
| `delay` | `sleep` once **per task, per worker**. A task with 1000 ports sleeps once, then opens 1000 connections. 100 workers still burst 100 connections. It also delays recursive SAN tasks. |

## Decision

1. **Remove** `check_tcp` (TCP is the base probe, not optional), `--push-url`,
   `spoof_user_agent`, and `expected`/`undesired` together with `catcher.py`.

2. **Implement** `check_http`: `--no-check-http` gives a TLS/SAN-only mode, much
   faster for topology discovery.

3. **Honest identification instead of disguise.** Every request sends a fixed
   `User-Agent: site-health-check/<version>`. Operators reading nginx/WAF logs can
   identify and whitelist the scanner. A CLI-only `--user-agent` override exists for
   standalone use but is not exposed in the API.

4. **Replace `delay` with `rate`.** `--rate N` caps new connection attempts per second
   globally, across all workers, with a token bucket (`0` = unlimited). It applies to
   every TCP connect and every HTTP request, not per task. `--workers` stays the
   concurrency cap. The goal is to protect stateful middleboxes (conntrack tables,
   firewalls, load balancers), not stealth.

5. **Explicitly rejected:** any traffic disguise or evasion feature (UA rotation,
   jitter for stealth, randomized fingerprints). Identifiable traffic is a feature
   here. This is in line with the "don't hurt our own datacenter" stance of ADR 0008.

## Consequences

- **Positive:** Smaller flag surface (CLI, `ExecutionFlags`, `ScanConfigForm`), and
  every remaining flag actually does something. Load on the network is predictable.
- **Compatibility:** Saved `Scan.flags_json` containing removed keys keep working.
  Pydantic ignores unknown keys, and the runner skips keys that are not in
  `ExecutionFlags`. An old `delay` value is silently dropped.
- **Frontend:** Remove the fields, add `rate`, regenerate the types (ADR 0016).
- **Deferred:** Capturing the HTML `<title>` (useful to spot default pages and
  forgotten panels) is the useful successor to body assertions. It needs a new
  `HttpRoutingCheck` column, so it waits for a migration strategy.
