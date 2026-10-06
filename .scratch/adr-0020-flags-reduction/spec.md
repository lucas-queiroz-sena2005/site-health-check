Status: ready-for-agent

## Problem Statement

The engine currently has several flags (`check_tcp`, `spoof_user_agent`, `expected`, `undesired`, `delay`) that are either non-functional, serve a purpose we reject (stealth/evasion), or are incorrectly implemented (like `delay` just sleeping the worker and bursting). Furthermore, the `check_http` flag exists in models but is currently ignored by the engine logic, meaning HTTP tests run even when the user just wants a rapid TLS topology discovery.

## Solution

Simplify the flags. Remove stealth and unused features (TCP is always checked, honest identification is always used). Introduce a `--rate` global token bucket to pace network traffic safely across all concurrent workers. Make the `--no-check-http` flag actually work so the engine can do high-speed topology discovery without the overhead of HTTP tests.

## User Stories

1. As an operator, I want the engine to enforce a global rate limit on new connections (e.g., 50 req/s), so that my scans do not overwhelm stateful firewalls or load balancers in our own datacenter.
2. As an operator, I want to disable HTTP probing (`--no-check-http`), so that I can rapidly discover IPs and TLS SANs (topology) without waiting for HTTP timeouts.
3. As an operator, I want the engine to honestly identify itself as `site-health-check/1.0`, so that I can easily whitelist it or identify it in server logs.
4. As a standalone user, I want the ability to override the honest User-Agent via a CLI argument `--user-agent` without exposing it to the API, so that I can do one-off manual testing if needed.
5. As a user creating a scan, I want to see a clean, relevant form without non-functional flags (like `spoof_user_agent` or `delay`), so that I'm not confused by broken or deprecated features.

## Implementation Decisions

- **API Models:** `ExecutionFlags` will drop `check_tcp`, `spoof_user_agent`, `expected`, `undesired`, `delay`, and gain `rate` (float, default 50.0). Pydantic v2 `extra` behavior defaults to ignore, so old keys sent by existing saved scans will be silently ignored.
- **Frontend Config Form:** The static schema `EXECUTION_FLAGS_SCHEMA` will be manually updated to mirror the API changes (remove deprecated fields, add `rate`), strictly following ADR 0016's decision for manual UI configuration.
- **CLI & Engine Schemas:** The CLI will drop deprecated flags and accept `--rate` and `--user-agent`. `catcher.py` will be deleted.
- **HTTP Probe:** `probes/http.py` will drop spoofing logic. It will use `flags.user_agent` or default to `site-health-check/1.0`.
- **Token Bucket Rate Limiting:** A global `AsyncTokenBucket` class will be implemented in `engine.py`. `worker` coroutines will `await limiter.acquire()` before making TCP or HTTP requests, enforcing the limit globally per subprocess.
- **`check_http` Enforcement:** The engine will evaluate `task.context.flags.check_http` before proceeding to HTTP routing probes.

## Testing Decisions

- **What makes a good test:** We will only test external observable behavior at the highest seam possible, not the internal implementation of the token bucket.
- **Which modules will be tested:** 
  - `engine.cli` (CLI seam): We will test the engine's external behavior by invoking it via a subprocess.
  - `api.models` (API seam): We will test the FastAPI payloads to ensure old flags don't break the system.
- **Prior Art / Existing Seams:** 
  - We will add an integration test to `engine/tests/test_cli_seam.py`. By running `engine.cli` with `--rate` and `--no-check-http`, we can verify that no HTTP results appear in the NDJSON delta, and that a rate limit restricts execution speed.
  - We will add tests to `api/tests/test_api_scans.py` to ensure that passing legacy flags like `{"delay": 5, "spoof_user_agent": true}` in the JSON payload still successfully creates a scan without throwing 422 Unprocessable Entity.

## Out of Scope

- Dynamic rendering of the frontend form via the API schema. As per ADR 0016, we will manually update `ScanConfigForm.tsx`.
- Tracking SNI-specific certificates for `check_virtual_hosts`. This will be handled in a future ADR (ADR 0021).

## Further Notes

None.
