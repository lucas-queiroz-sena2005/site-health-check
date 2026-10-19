Status: ready-for-agent

## Problem Statement

The core asynchronous engine currently uses raw Python dictionaries to pass targets through the worker queue. This "primitive obsession" creates fragile code that relies on string keys, bypasses static type checking, and makes future extensibility (like adding SNI pinning for ADR 0021) messy. Furthermore, URL parsing and port extraction logic (feature envy) is duplicated and clutters the main engine loop, violating clean code standards.

## Solution

Refactor the engine's internal queue to use a dedicated, statically typed `WorkerTask` dataclass. This schema will encapsulate all required fields (target, ports, flags, lineage tracking) natively. Additionally, abstract the URL parsing and default port logic into a helper function or class method, removing it from the core worker loop entirely.

## User Stories

1. As a developer, I want to use a typed `WorkerTask` object in the engine loop, so that my IDE and typechecker (pyright) can catch missing fields or incorrect types automatically.
2. As an architect planning ADR 0021, I want the queue payload to be an extensible object, so I can easily add strongly-typed SNI and host-header properties in the future.
3. As a developer reading the code, I want URL parsing and HTTP/HTTPS port extraction hidden behind a helper, so that the engine loop remains clean and focused purely on network orchestration.

## Implementation Decisions

- **Schema Addition:** Create a new `@dataclasses.dataclass` called `WorkerTask` in `engine/src/engine/schemas/engine.py`. It will contain fields for `target` (str), `ports` (list[int]), `flags` (TaskFlags), `discovered_from` (str | None), `parent_ip` (str | None), and `depth` (int).
- **Engine Refactor:** Update `engine/src/engine/engine.py` to instantiate `WorkerTask` objects instead of dictionaries when seeding the queue and when appending new discovered tasks (like SANs or redirects). Update the `worker` loop to access attributes (`task.target`) instead of dictionary keys (`task["target"]`).
- **URL Abstraction:** Create a helper (e.g., a classmethod `WorkerTask.from_redirect_url(url, parent_ip, current_depth, flags)`) that encapsulates the `yarl` parsing and port fallback logic (80/443), keeping the engine loop clean of domain logic.

## Testing Decisions

- **What makes a good test:** This is a structural refactor, so success is defined by preserving existing external behavior.
- **Modules to be tested:** `engine.engine` and `engine.schemas.engine`.
- **Addressing Test Review Smells:** The reviewer flagged that our test `test_engine_enqueue_redirect` expects `depth: 0` when enqueueing a redirect, which caused confusion. We will add explicit assertions/tests to clarify that depth is passed exactly as `current_depth` during enqueue, and it is the responsibility of the worker to increment it to `1` *after* popping the task and performing DNS resolution.
- **Prior art / Seams:** We will rely on the existing seams in `engine/tests/test_http_redirects.py` and `engine/tests/test_cli_seam.py`. The only test modifications required will be updating the test setup blocks that currently inject raw dictionaries into the mock `queue` to inject `WorkerTask` objects instead, and clarifying the depth assertions.

## Code Review Follow-ups (Phase 2)
Based on the two-axis code review, we will implement the following final fixes:
1. **Fix Queue Seeding Bug (Spec):** Update `engine.py:async_main()` to properly extract and preserve `parent_ip` and `depth` from the input JSON payload when creating the task.
2. **Rename WorkerTask (Standards - Hard Violation):** Rename `WorkerTask` to `EngineTask` to comply with `CONTEXT.md` terminology, which forbids the term "worker".
3. **Fix Data Clumps & Primitive Obsession (Standards):** 
   - Bundle `flags`, `discovered_from`, `parent_ip`, and `depth` into a dedicated `TaskContext` dataclass.
   - Embed `TaskContext` inside `EngineTask` to explicitly model the lineage domain concept.
4. **Fix Duplicated Code (Standards):** Extract the heavily duplicated 30-line test setup blocks in `test_http_redirects.py` into shared test fixtures or helper functions.

## Out of Scope

- Changing the API ingestion schema (`TaskConfig`). This refactor is strictly for the internal engine queue (`WorkerTask`).
- Refactoring or altering the logic of the HTTP or TCP probes themselves.

## Further Notes

- This refactor directly addresses the "Primitive Obsession" and "Feature Envy" smells flagged during code review and paves the way for the complex vhost probing required in ADR 0021.
