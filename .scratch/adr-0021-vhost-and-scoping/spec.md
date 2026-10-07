Status: ready-for-agent

## Problem Statement

Site Health Check needs a safe, scalable way to discover hidden virtual hosts (SNI origin mapping) and explore redirect chains across networks. The current scoping logic (`--out-of-scope-depth`) is vague, conflates network boundaries with hop depth, and could accidentally scan huge unrelated networks (like AWS or Cloudflare CDN IPs) via SAN discovery, leading to WAF bans or false positives. Additionally, expanding large CIDR ranges (like `/16`) in memory for scoping violates the bounded memory limits defined in ADR 22.

## Solution

The engine's CLI arguments and targeting logic will be redesigned to use explicit whitelists, blacklists, and short-flag combo filtering (`-rsv`) to provide maximum precision over network exploration. 

DNS-independent SNI probing (Vhost probing) will be separated from DNS Expansion. Mathematical, memory-efficient scoping checks will be introduced so the engine can safely evaluate whether a discovered target is authorized, without expanding massive target arrays in memory. If no whitelist is provided, the engine will safely default to allowing all targets, restricted only by blacklists.

## User Stories

1. As a security engineer, I want to use the `-v` flag to find hidden origin virtual hosts on an IP without using DNS, so that I can bypass CDN obfuscation.
2. As a sysadmin, I want to define strict whitelists of CIDR blocks, so that the scanner never accidentally probes external infrastructure like AWS or Cloudflare.
3. As a prober, I want to follow HTTP redirects across network boundaries up to 5 hops (`-r --dr 5`), so that I can fully map SSO authentication chains.
4. As a prober, I want the depth limits for Redirects and SANs to be tracked independently (`--dr` vs `--ds`), so that I don't accidentally crawl an entire certificate SAN graph just because I followed an SSO redirect.
5. As the scanner engine, I want to parse whitelists and blacklists as mathematical `IPv4Network` objects, so that verifying targets in a /16 range is O(1) and consumes virtually no memory, adhering to ADR 22.
6. As a user running a basic ad-hoc scan without scoping flags, I want the engine to allow scanning any target it discovers, unless explicitly caught by a `--blacklist`, so that ad-hoc usage isn't hindered by strict bounds checks.
7. As a prober, I want to supply exact domain strings in the whitelist, so that I can safely follow CNAMEs into PaaS/CDNs without whitelisting the entire cloud provider's IP range.

## Implementation Decisions

- Modified Modules: `engine.cli` (argparse), `engine.schemas.engine` (TaskFlags), `engine.engine` (worker loop boundaries).
- Removed Flags: `--out-of-scope-depth` and `--recursive-san`.
- Added Flags:
  - `--whitelist`: List of IPs, CIDRs, or domains. Defaults to allowing everything if omitted.
  - `--blacklist`: List of IPs, CIDRs, or domains. Overrides whitelist.
  - `-r`: Boolean short-flag to follow Redirects (Strictly In-Scope).
  - `-R`: Boolean short-flag to follow Redirects (Allows Out-of-Scope).
  - `-s`: Boolean short-flag to discover SANs (Strictly In-Scope).
  - `-S`: Boolean short-flag to discover SANs (Allows Out-of-Scope).
  - `-v`: Boolean short-flag to force Vhost origin probing (DNS bypass).
  - `--dr`: Max hop depth for redirects (Default: 3).
  - `--ds`: Max hop depth for SANs (Default: 1).
- **ScopeValidator utility**: A new class in `engine.parsing` (or similar) that holds sets of exact domains/IPs, and lists of `ipaddress.IPv4Network` objects. It provides a simple `is_in_scope(target)` method with O(1) bounds-checking for IPs.
- **Vhost DNS Bypass**: Inside `engine.engine.scanner_routine`, tasks flagged by `-v` (origin vhost probes) will bypass the `resolve_target` DNS step and the Scope Validator, executing the HTTP probe directly against the known IP with the specific Host header.

## Testing Decisions

Testing will rely on three primary seams across the application, preferring high-level behavior over internal implementation details:

1. **The CLI Seam (`engine/tests/test_cli_seam.py`)**: Use the existing subprocess pattern to pass the new `-rsv` combo flags and verify that the engine initializes properly without argparse errors and serializes the `TaskFlags` correctly into the JSON payload.
2. **The Worker Loop Seam (`engine/tests/test_http_redirects.py`)**: Use the existing `run_worker_with_task` pattern to inject a task into `scanner_routine`. Mock `resolve_target` to return an out-of-scope IP and assert whether the worker drops the target or continues scanning based on the `-r` / `-s` flags provided.
3. **The Validator Logic**: Unit testing `ScopeValidator` directly to ensure that `10.0.5.50` passes `10.0.0.0/16` but drops when blacklisted by `10.0.5.0/24`. Also tests that an empty whitelist allows everything.

## Out of Scope

- Modifying the frontend UI or API aggregation layers to display the new flags.
- Changing the TLS parsing logic that actually extracts the SANs (the extraction is already present, this spec only focuses on the routing and scoping of those extracted SANs).

## Further Notes

- By removing the automatic `expand_target_ranges` array allocation for scoping, we align the architecture with the bounded-memory requirements defined in ADR 0022.
