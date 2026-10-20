# Implementation Plan: Shared Schema & Engine JSON Input (`engine_json_contract`)

## Phase 1: Unify Flag Schemas Across Engine and API (TDD)
- [ ] Task: Write failing unit tests for unified `TaskFlags` / `ExecutionFlags` schema (Red Phase)
  - [ ] Add schema tests in `engine/tests/test_cli_seam.py` (or `engine/tests/test_schemas.py`) asserting that `TaskFlags` and `api.models.ExecutionFlags` are the identical class, support canonical fields (`timeout`, `recursive_san`, `workers`, `rate`, `check_http`, `check_virtual_hosts`, `out_of_scope_depth`, `user_agent`), accept legacy alias keys (`timeout_seconds`, `recursive_san_check`), and contain no `cli_arg` metadata
- [ ] Task: Implement unified `TaskFlags` (`ExecutionFlags`) in `engine/src/engine/schemas/engine.py` and import in `api/src/api/models.py` (Green & Refactor Phase)
  - [ ] Convert `TaskFlags` in `engine/src/engine/schemas/engine.py` to a Pydantic `BaseModel` with canonical field names, `AliasChoices` for legacy keys, and `ExecutionFlags = TaskFlags` alias
  - [ ] Update `TaskConfig.to_dict()` in `engine/src/engine/schemas/engine.py` so `flags` serializes cleanly into a dictionary
  - [ ] Update `engine/src/engine/engine.py` and `engine/src/engine/probes/http.py` to read `flags.recursive_san` and `flags.timeout`
  - [ ] Replace the duplicate `ExecutionFlags` definition in `api/src/api/models.py` with `from engine.schemas.engine import ExecutionFlags`
- [ ] Task: Phase Verification & Checkpoint (Refer to `workflow.md`)

---

## Phase 2: Engine CLI `--config` / `stdin` JSON Ingestion (TDD)
- [ ] Task: Write failing CLI seam tests for `--config -` (`stdin`) and `--config <file>` JSON ingestion (Red Phase)
  - [ ] Add unit and integration tests in `engine/tests/test_cli_seam.py` verifying that `engine.cli --config -` accepts an `ExecutionConfig`-shaped JSON payload over `stdin` (including multi-target arrays, port lists/ranges, and `check_http: false` / `rate` flags) and emits expected NDJSON output
  - [ ] Add test verifying that `SIGTERM` abort handling works identically when launched via `--config -`
  - [ ] Add test verifying that missing both positional `target` and `--config` exits with a non-zero error code
- [ ] Task: Implement `--config` (`-c`) and `stdin` reader in `engine/src/engine/cli.py` (Green & Refactor Phase)
  - [ ] Update `build_parser()` in `engine/src/engine/cli.py` to make positional `target` optional (`nargs="?"`) and add `-c` / `--config`
  - [ ] Implement single-object JSON loading from `sys.stdin` (when `--config -`) or file path, validating the single `ExecutionConfig` snapshot dict (`targets`, `ports`, `flags`) and converting it into internal tasks via existing target expansion
  - [ ] Preserve existing positional CLI target and flag behavior when `--config` is not passed
- [ ] Task: Phase Verification & Checkpoint (Refer to `workflow.md`)

---

## Phase 3: Zero-Translation Subprocess Dispatch & Delta Integrity Fixes (TDD)
- [ ] Task: Write failing tests for `stdin` JSON dispatch and non-destructive delta ingestion (Red Phase)
  - [ ] Add unit test in `api/tests/test_api_runner.py` mocking `asyncio.create_subprocess_exec` in `run_engine_cli` and asserting it invokes `[sys.executable, "-u", "-m", "engine.cli", "--config", "-"]` with `stdin=asyncio.subprocess.PIPE` and writes the JSON-serialized snapshot to `process.stdin`
  - [ ] Add unit test in `api/tests/test_api_runner.py` verifying that a second vhost HTTP-only delta on an already-open port preserves `tcp_status="open"`, `tcp_latency_ms`, `subrun_id`, and merges `discovered_from` without clobbering existing values or causing `_finalize_run` to purge the active host as Void
  - [ ] Add unit tests in `engine/tests/test_http_redirects.py` verifying that: (a) closed TCP ports skip HTTP probing, (b) cross-IP domain SANs record `discovered_from = state_key`, and (c) same-IP SANs (in-scope vhosts) do not create self-loops in `metadata.discovered_from`
- [ ] Task: Refactor `run_engine_cli` in `api/src/api/services/runner.py` and fix delta emission in `engine/src/engine/engine.py` (Green & Refactor Phase)
  - [ ] Replace the 35-line CLI argument construction loop in `api/src/api/services/runner.py` with `stdin` JSON payload delivery and `process.stdin.close()`
  - [ ] Track `open_tcp` in `engine/src/engine/engine.py` to skip HTTP probes on closed ports, emit `tcp_status="open"` on `skip_tcp` vhost probes, and guard `discovered_from` with `task.context.discovered_from != ip_address`
  - [ ] Update `runner.py:_upsert_delta_sync` to preserve open `tcp_status`, non-null `tcp_latency_ms` / `subrun_id`, and union `discovered_from`
  - [ ] Run full test suite across `engine/tests/` and `api/tests/` to verify zero regressions
- [ ] Task: Phase Verification & Checkpoint (Refer to `workflow.md`)
