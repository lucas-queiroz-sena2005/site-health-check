# Specification: Shared Schema & Engine JSON Input (`engine_json_contract`)

Status: ready-for-agent  
Related ADR: [ADR 0023](../../adr/0023-control-plane-and-flat-explorer-modernization.md) (Amends [ADR 0016](../../adr/0016-execution-config-schema-sync.md))

---

## 1. Investigative Problem Statement

Today, the boundary between the FastAPI control plane (`api/`) and the scanner subprocess (`engine/`) suffers from an unnecessary **"Object ➔ CLI Strings ➔ argparse ➔ Object"** translation cycle:

1. **Dual, Drifting Flag Models:**
   - `api/src/api/models.py` defines `ExecutionFlags(BaseModel)` with fields: `check_http`, `recursive_san`, `out_of_scope_depth`, `check_virtual_hosts`, `timeout`, `workers`, `rate`.
   - `engine/src/engine/schemas/engine.py` defines `TaskFlags` (`@dataclass`) with fields: `check_http`, `timeout_seconds`, `recursive_san_check`, `check_virtual_hosts`, `out_of_scope_depth`, `rate`, `user_agent`.
   - Notice the naming divergence (`timeout` vs. `timeout_seconds`, `recursive_san` vs. `recursive_san_check`) and missing fields (`workers` only in API; `user_agent` only in Engine).
   - Although `api/pyproject.toml` already declares `engine` as a workspace dependency (`engine = { workspace = true }`), the two packages duplicate their flag definitions.

2. **Pydantic Schema Pollution & Imperative CLI String Reconstruction:**
   - Every field in `ExecutionFlags` carries `json_schema_extra={"cli_arg": "--...", "is_switch": ...}`.
   - `api/src/api/services/runner.py:run_engine_cli()` inspects `ExecutionFlags.model_fields` at runtime to build a `cmd` list (`[sys.executable, "-u", "-m", "engine.cli", ",".join(targets), "-p", ",".join(ports), "--check-http", ...]`).
   - `engine/src/engine/cli.py:main()` then parses those strings with `argparse`, re-expands target ranges and ports, and manually maps `parsed_args.timeout` back to `timeout_seconds` and `parsed_args.recursive_san` back to `recursive_san_check`.

3. **Linux `MAX_ARG_STRLEN` Subprocess Failure Mode:**
   - Because `runner.py` joins all targets into a single positional argument (`",".join(targets)`), any scan with a large list of discrete hostnames/IPs exceeds the Linux per-argument limit (`MAX_ARG_STRLEN` = 128 KB), raising `OSError: [Errno 7] Argument list too long` before the engine process even starts.

---

## 2. Architectural Solution & Rationale

### 2.1 Single Source of Truth for Flag Schemas (`engine.schemas.engine`)
- Define `TaskFlags` (and alias `ExecutionFlags = TaskFlags`) in `engine/src/engine/schemas/engine.py` as a Pydantic `BaseModel` (since `pydantic` is already a declared dependency in `engine/pyproject.toml`).
- Standardize on the canonical field names already persisted in SQLite (`scans.flags_json`, `scan_runs.execution_config_snapshot_json`) and used by the React frontend (`ScanConfigForm.tsx`):
  - `check_http: bool = True`
  - `recursive_san: bool = False`
  - `out_of_scope_depth: int = 0`
  - `check_virtual_hosts: bool = True`
  - `timeout: int = 10`
  - `workers: int = 100`
  - `rate: float = 50.0`
  - `user_agent: str | None = None`
- Strip all `json_schema_extra={"cli_arg": ..., "is_switch": ...}` metadata from the flag fields while preserving human-readable `title` attributes for `GET /api/schemas/schedule`.
- Update `engine/src/engine/engine.py` and `engine/src/engine/probes/http.py` to access `flags.recursive_san` and `flags.timeout` (and support `AliasChoices` for `timeout_seconds` / `recursive_san_check` during validation so any legacy dictionaries or tests construct cleanly).
- Import `ExecutionFlags` in `api/src/api/models.py` directly from `engine.schemas.engine`.

### 2.2 Dual-Mode Engine CLI (`--config <path|->` + Positional CLI Targets)
- Why keep human CLI arguments at all? Being able to run `site-check example.com -p 80,443 --no-check-http` directly from an interactive shell is invaluable for debugging probes without spinning up FastAPI or hand-writing JSON.
- Why add `--config` / `stdin`? Programmatic orchestration (`runner.py`) already holds a structured dictionary (`snapshot` with `targets`, `ports`, `flags`). Passing it over `stdin` (`python -u -m engine.cli --config -`) eliminates CLI stringification, `argparse` flag coupling, and `MAX_ARG_STRLEN` limits while preserving 100% of the OS subprocess isolation and `SIGTERM`/`SIGINT` abort semantics ([ADR 0018](../../adr/0018-scan-run-abort-and-partial-results.md)).
- **Crucial Clarification (Input Formatting Only, Not a Task Splitter):** The `--config` (`-c`) option accepts **strictly one JSON object** representing the scan definition (`{"targets": [...], "ports": [...], "flags": {...}}`). It is purely an input formatting alternative to CLI arguments. We are **not** introducing an external task "splitter" or streaming pre-split tasks; the engine CLI takes this single input object and turns it into internal tasks exactly as it does when parsing CLI arguments.
- Specifically, `engine/src/engine/cli.py` will:
  1. Make the positional `target` argument optional (`nargs="?"`, `default=None`) and add `--config` (`-c`, `type=str`, `default=None`, help="Path to JSON execution config file, or '-' to read from stdin").
  2. When `--config` is provided:
     - Read the single JSON object from `sys.stdin` (if `"-"`), or from the specified file path.
     - Validate the single object against the execution configuration shape (`targets`: list of strings, `ports`: list of ints/strings, `flags`: flag dictionary).
     - Validate and expand each target segment via `validate_and_clean_target` and `expand_target_ranges`, normalize ports via `parse_ports`, validate `flags` via `TaskFlags.model_validate()`, and pass `workers=flags.workers` to `run_engine()`.
  3. When `--config` is omitted:
     - Require positional `target` (exiting with code `1` or parser error if missing) and build `TaskFlags` from `parsed_args` exactly as before.

### 2.3 Zero-Translation Subprocess Dispatch in `runner.py`
- Update `api/src/api/services/runner.py:run_engine_cli()` to spawn:
  ```python
  cmd = [sys.executable, "-u", "-m", "engine.cli", "--config", "-"]
  process = await asyncio.create_subprocess_exec(
      *cmd,
      stdin=asyncio.subprocess.PIPE,
      stdout=asyncio.subprocess.PIPE,
      stderr=asyncio.subprocess.PIPE,
  )
  ```
- Write `json.dumps(snapshot).encode("utf-8")` to `process.stdin`, flush/close `process.stdin`, and proceed with concurrent `stdout` (NDJSON deltas) and `stderr` (SSE logs) ingestion.
- Delete the entire 35-line CLI flag-mapping loop in `runner.py`.

### 2.4 Engine & Ingestor Delta Integrity Fixes (Zero Output Schema Change)
An audit of the prototype's raw engine logs (`dns-google.raw.log` and `google-com.raw.log`) revealed a critical interaction chain between `engine.py` and `runner.py` that must be corrected together to avoid data loss or self-loops:
1. **Track `open_tcp` & Skip HTTP on Closed TCP Ports (`engine.py:101-140`):**
   - *Bug 1 (Bogus HTTP Timeouts on Closed Ports):* Previously, when `check_tcp_and_tls` returned `tcp_status="closed"` (e.g., `8.8.8.8:80`), `engine.py` still executed `check_http_routing`, waiting for an HTTP timeout on a closed port. Worse, because `seen_tcp` recorded all attempted `ip:port` pairs regardless of outcome, subsequent vhost tasks on the same IP saw `skip_tcp=True` and also ran HTTP probes against the closed port.
   - *Bug 2 (VHost Deltas Overwriting Open TCP State & Triggering False Void Deletion):* When a second domain (e.g., SAN `8888.google` on `8.8.8.8:443`) resolved to an already-open `ip:port`, `skip_tcp` was `True`, so `engine.py` emitted a fresh `PortState(tcp_status="closed", tcp_latency_ms=None)` alongside the new HTTP check. `runner.py:_upsert_delta_sync()` then overwrote port 443 in SQLite from `"open"` back to `"closed"`, causing `_finalize_run()` to think `8.8.8.8` had zero open ports and **delete the entire active host as a Void host**!
   - *Safe Fix:*
     - Maintain `open_tcp: set[str]` in `engine.py` (cleared in `run_engine()`). Add `tcp_cache_key` to `open_tcp` only when `tcp_result.tcp_status == "open"`.
     - Only execute the HTTP probe block if `tcp_cache_key in open_tcp` and `task.context.flags.check_http`.
     - When `skip_tcp` is `True` (and `tcp_cache_key in open_tcp`), initialize `local_state.ports[port] = PortState(tcp_status="open")`.
     - In `runner.py:_upsert_delta_sync()`, preserve `"open"` (`tcp_status` never downgrades from `"open"` to `"closed"`), preserve non-null `tcp_latency_ms` and `subrun_id`, and union `discovered_from` lists rather than overwriting them.
2. **Cross-IP `discovered_from` Lineage Without Self-Loops (`engine.py:75-76, 116-120`):**
   - *Bug:* `engine.py:116-120` wiped `discovered_from = None` whenever a SAN was a domain name (`ipaddress.IPv4Address(san)` raised `ValueError`), leaving `metadata.discovered_from` always `[]`.
   - *Self-Loop Hazard:* If a SAN (`8888.google`) discovered on `8.8.8.8` resolves back to the **same IP** (`8.8.8.8`), unconditionally appending `discovered_from="8.8.8.8"` would make `8.8.8.8` claim it was discovered from itself (`discovered_from: ["8.8.8.8"]`), breaking backend depth inference!
   - *Safe Fix:* Always pass `discovered_from = state_key` when queuing a SAN task, and in `scanner_routine` only append `task.context.discovered_from` to `local_state.metadata.discovered_from` when **`task.context.discovered_from != ip_address`** (cross-IP discovery). This requires **zero changes** to the `IpState` / `IpMetadata` output schema and allows the backend to infer discovery `depth` directly from `metadata.discovered_from`.

---

## 3. Acceptance Criteria

1. **Unified Schema:** `ExecutionFlags` in `api.models` and `TaskFlags` in `engine.schemas.engine` reference the exact same class in `engine.schemas.engine`, with zero `cli_arg` / `is_switch` metadata, while supporting legacy `timeout_seconds` and `recursive_san_check` aliases/properties without errors.
2. **Engine JSON Ingestion (`--config -`):** Invoking `python -m engine.cli --config -` with a single JSON object on `stdin` (`{"targets": ["127.0.0.1"], "ports": [80], "flags": {"check_http": false, "rate": 50.0}}`) executes the scan, respects all flags, and emits valid NDJSON deltas + summary on `stdout`.
3. **Standalone CLI Compatibility:** Invoking `python -m engine.cli 127.0.0.1 -p 80 --no-check-http` with positional CLI arguments continues to work identically.
4. **Runner Simplification:** `api/src/api/services/runner.py:run_engine_cli()` spawns `engine.cli --config -` and passes the snapshot over `stdin`, with no flag-loop translation code remaining.
5. **Delta Integrity (Zero Output Schema Change):** Closed TCP ports do not trigger HTTP probes; VHost HTTP-only deltas do not overwrite open `tcp_status`/`tcp_latency_ms` or `subrun_id` in SQLite; cross-IP SAN discoveries record `discovered_from` without self-loops on same-IP vhosts.
6. **Regression Safety:** All unit and integration tests across `engine/tests/` and `api/tests/` pass.

---

## 4. Out of Scope (Deferred to Tracks 2–5)

- Dropping `TargetGroup` / `ScanTargetGroupLink` or renaming `_json` database columns (Track 2).
- Extracting `RunManager` from `app.state` dicts (Track 3).
- Consolidating `/api/runs/launch` and `/api/scans/{id}/launch` REST endpoints (Track 4).
- Migrating the React dashboard to the flat prototype views (Track 5).
