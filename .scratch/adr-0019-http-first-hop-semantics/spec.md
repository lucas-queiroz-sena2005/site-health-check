Status: ready-for-agent

## Problem Statement

When the site health engine encounters an HTTP redirect (301, 302, etc.), it automatically follows it to the final destination. This behavior hides the actual response of the scanned server, breaks discovery boundaries (out of scope depth), and could result in unintentionally probing third-party servers (e.g. login.microsoftonline.com) that are completely out of scope. We want to record exactly what the server answered and use the redirect URL as a potential new discovery target instead of following it blindly.

## Solution

Stop `aiohttp` from automatically following redirects (`allow_redirects=False`). Record the first response from the target. If the response is a redirect (3xx), extract the `Location` header and store it in `redirects_to_url` as an absolute URL. Additionally, enqueue the discovered redirect URL as a new target to scan, subjecting it to the engine's existing `out_of_scope_depth` checks.

## User Stories

1. As an operator scanning a subnet, I want the system to stop after receiving a 3xx redirect from my server, so that I don't inadvertently scan external authentication providers or third-party CDNs.
2. As a network administrator, I want to see the 3xx status code and the `redirects_to_url` in the dashboard, so that I can audit misconfigured L7 routing rules.
3. As a user, I want internal redirects to be added to the discovery queue, so that if a server redirects to another internal service, that service is properly discovered and scanned if it falls within my scope rules.
4. As a user, I want external redirects to be blocked by the engine's depth limit, so that the engine honors the `out_of_scope_depth` configuration.

## Implementation Decisions

- The `engine.probes.http` module's `check_http_routing` will be modified to use `allow_redirects=False`.
- For 3xx responses, `check_http_routing` will extract the `Location` header, resolve it to an absolute URL using `yarl` (or `aiohttp`'s built-in `response.url.join`), and populate the `redirects_to_url` field of the `HttpRoutingCheck` result.
- The `engine.engine` module's worker loop will examine the `http_result` for a `redirects_to_url`. If present, it will extract the hostname and create a new task for that URL, incrementing `current_depth` if the hostname differs from the `parent_ip`. The task will be enqueued subject to the `out_of_scope_depth` limit.
- The schema for `HttpRoutingCheck` already has the `redirects_to_url` field, so no database migration is required.

## Testing Decisions

- What makes a good test: Test that HTTP routing correctly identifies 301/302 statuses without following them, and that the worker loop enqueues the extracted redirect URL subject to depth limits.
- Modules to be tested: `engine.probes.http` and `engine.engine`.
- Prior art: Existing HTTP checks mock the network response. We will need to mock a 301 response with a `Location` header. The worker loop tests mock `check_http_routing`. We will verify that if the mock returns a `redirects_to_url`, a new task is pushed to the queue.
- **Seams**: The two existing seams to be used are:
  1. The `check_http_routing` function boundaries (for unit testing HTTP behavior).
  2. The `engine.engine` loop logic, tested by mocking `check_http_routing` to return a result containing a `redirects_to_url` and asserting that `queue.put()` is called with the correct target and depth values.

## Out of Scope

- Following HTTP redirect chains automatically.
- Validating the content of the redirect destination (unless it is discovered and scanned in a separate task).
- Updating the UI to display `redirects_to_url` (this spec covers the engine/API backend functionality).

## Further Notes

- This implementation satisfies ADR 0019 and serves as a prerequisite for ADR 0021 (DNS-Independent VHost Probing) by preventing `aiohttp` from breaking the IP pinning with its native DNS resolution during redirects.
