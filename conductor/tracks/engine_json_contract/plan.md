# Implementation Plan: Shared Schema & Engine JSON Input (`engine_json_contract`)

## Phase 1: Unify Flag Schemas Across Engine and API (TDD) [checkpoint: 30145f3]
- [x] Task: Write failing unit tests for unified `TaskFlags` / `ExecutionFlags` schema (Red Phase) af761f7
  - [x] Add schema tests in `engine/tests/test_cli_seam.py` (or `engine/tests/test_schemas.py`) asserting that `TaskFlags` and `api.models.ExecutionFlags` are the identical class, support canonical fields (`timeout`, `recursive_san`, `workers`, `rate`, `check_http`, `check_virtual_hosts`, `out_of_scope_depth`, `user_agent`), accept legacy alias keys (`timeout_seconds`, `recursive_san_check`), and contain no `cli_arg` metadata
- [x] Task: Implement unified `TaskFlags` (`ExecutionFlags`) in `engine/src/engine/schemas/engine.py` and import in `api/src/api/models.py` (Green & Refactor Phase) 30145f3
  - [x] Convert `TaskFlags` in `engine/src/engine/schemas/engine.py` to a Pydantic `BaseModel` with canonical field names, `AliasChoices` for legacy keys, and `ExecutionFlags = TaskFlags` alias
  - [x] Update `TaskConfig.to_dict()` in `engine/src/engine/schemas/engine.py` so `flags` serializes cleanly into a dictionary
  - [x] Update `engine/src/engine/engine.py` and `engine/src/engine/probes/http.py` to read `flags.recursive_san` and `flags.timeout`
  - [x] Replace the duplicate `ExecutionFlags` definition in `api/src/api/models.py` with `from engine.schemas.engine import ExecutionFlags`
- [x] Task: Phase Verification & Checkpoint (Refer to `workflow.md`) 30145f3

---

## Phase 2: Engine CLI `--config` / `stdin` JSON Ingestion (TDD) [checkpoint: bd06252]
- [x] Task: Write failing CLI seam tests for `--config -` (`stdin`) and `--config <file>` JSON ingestion (Red Phase) aeb6580
  - [x] Add unit and integration tests in `engine/tests/test_cli_seam.py` verifying that `engine.cli --config -` accepts an `ExecutionConfig`-shaped JSON payload over `stdin` (including multi-target arrays, port lists/ranges, and `check_http: false` / `rate` flags) and emits expected NDJSON output
  - [x] Add test verifying that `SIGTERM` abort handling works identically when launched via `--config -`
  - [x] Add test verifying that missing both positional `target` and `--config` exits with a non-zero error code
- [x] Task: Implement `--config` (`-c`) and `stdin` reader in `engine/src/engine/cli.py` (Green & Refactor Phase) bd06252
  - [x] Update `build_parser()` in `engine/src/engine/cli.py` to make positional `target` optional (`nargs="?"`) and add `-c` / `--config`
  - [x] Implement single-object JSON loading from `sys.stdin` (when `--config -`) or file path, validating the single `ExecutionConfig` snapshot dict (`targets`, `ports`, `flags`) and converting it into internal tasks via existing target expansion
  - [x] Preserve existing positional CLI target and flag behavior when `--config` is not passed
- [x] Task: Phase Verification & Checkpoint (Refer to `workflow.md`) bd06252

---

## Phase 3: Zero-Translation Subprocess Dispatch & Delta Integrity Fixes (TDD)
- [x] Task: Write failing tests for `stdin` JSON dispatch and non-destructive delta ingestion (Red Phase) 3f38661
  - [ ] Add unit test in `api/tests/test_api_runner.py` mocking `asyncio.create_subprocess_exec` in `run_engine_cli` and asserting it invokes `[sys.executable, "-u", "-m", "engine.cli", "--config", "-"]` with `stdin=asyncio.subprocess.PIPE` and writes the JSON-serialized snapshot to `process.stdin`
  - [ ] Add unit test in `api/tests/test_api_runner.py` verifying that a second vhost HTTP-only delta on an already-open port preserves `tcp_status="open"`, `tcp_latency_ms`, `subrun_id`, and merges `discovered_from` without clobbering existing values or causing `_finalize_run` to purge the active host as Void
  - [ ] Add unit tests in `engine/tests/test_http_redirects.py` verifying that: (a) closed TCP ports skip HTTP probing, (b) cross-IP domain SANs record `discovered_from = state_key`, and (c) same-IP SANs (in-scope vhosts) do not create self-loops in `metadata.discovered_from`
- [x] Task: Refactor `run_engine_cli` in `api/src/api/services/runner.py` and fix delta emission in `engine/src/engine/engine.py` (Green & Refactor Phase) 161f1c1
  - [ ] Replace the 35-line CLI argument construction loop in `api/src/api/services/runner.py` with `stdin` JSON payload delivery and `process.stdin.close()`
  - [ ] Track `open_tcp` in `engine/src/engine/engine.py` to skip HTTP probes on closed ports, emit `tcp_status="open"` on `skip_tcp` vhost probes, and guard `discovered_from` with `task.context.discovered_from != ip_address`
  - [ ] Update `runner.py:_upsert_delta_sync` to preserve open `tcp_status`, non-null `tcp_latency_ms` / `subrun_id`, and union `discovered_from`
  - [ ] Run full test suite across `engine/tests/` and `api/tests/` to verify zero regressions
- [ ] Task: Phase Verification & Checkpoint (Refer to `workflow.md`)
