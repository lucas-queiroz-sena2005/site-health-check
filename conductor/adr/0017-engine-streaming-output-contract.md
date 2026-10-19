# ADR 0017: Engine Streaming Output Contract (NDJSON Deltas on stdout)

## Status

Accepted — Roadmap phase 1 (implemented together with ADR 0018).

## Context

The engine only produces results when the process exits successfully: `run_engine()`
returns the whole `master_state`, the CLI dumps it with `-o <tmp>.json`, and the API
reads that file after `process.wait()`. Consequences:

- A crash (or abort) after 28 minutes of a /16 scan yields **zero** results.
- stdout mixes human logs, the pretty-printed input payload and the final JSON, so
  the CLI cannot be piped into `jq`/`grep`/`awk`.
- The API cannot ingest progressively, and the frontend can only show logs, never
  partial results.
- For a /16 the full `master_state` must be held in memory until the very end.

We want to keep the IP-first JSON shape (ADR 0001) because the API ingestion and the
frontend `buildTreeData` depend on it deeply.

## Decision

1. **stdout carries data only. stderr carries logs only.**
   All `print()` diagnostics move to `logging` on stderr (`-v` / `-q` control
   verbosity). The input payload is no longer echoed.

2. **stdout is NDJSON: one JSON object per line, emitted as soon as a probe finishes.**
   Every data line is a *partial `IpState`* wrapped in an envelope:

   ```jsonl
   {"type":"host","ip":"10.0.0.1","metadata":{"resolved_from":null,"discovered_from":[]},"ports":{"443":{"tcp_status":"open","tcp_latency_ms":3,"tls_certificate":{...}}}}
   {"type":"host","ip":"10.0.0.1","ports":{"443":{"http_routing_checks":{"susy.ic.unicamp.br":{"status_code":200,...}}}}}
   {"type":"summary","status":"completed","hosts":254,"duration_s":41.2}
   ```

   - A TCP/TLS probe emits the port's TCP/TLS fields only.
   - An HTTP probe emits only `http_routing_checks.<host>` for that port.
   - **Absent key = untouched.** Never emit default values for fields a probe did not
     measure (e.g. an HTTP delta must not carry `tcp_status: "closed"`).
   - The last line is always a single `summary` record
     (`status`: `completed | aborted | failed`).

3. **Merge rule (the contract every consumer implements):** deep-merge objects by key,
   scalars overwrite, `metadata.discovered_from` is a set union. Deltas for the same IP
   touch disjoint keys, so the merge is order-independent.

4. **Folding all deltas yields exactly today's output format.** `-o file.json` keeps
   writing the aggregated IP-keyed JSON (built with the same merge function), so
   existing tooling and the frontend contract don't change.

5. **Exit codes:** `0` completed, `1` fatal error, `130` SIGINT, `143` SIGTERM.
   Any lines already written stay valid in every case.

## Considered Options

- **Node+Edge graph NDJSON:** rejected. Unreadable for large networks and would force
  a full frontend rewrite.
- **Full `IpState` snapshot per line (last write wins):** simpler to consume, but it
  forces the engine to keep every `IpState` in memory forever. Deltas let the engine
  drop state later (ADR 0022).
- **Periodic checkpoint file:** fixes crashes but not progressive ingestion or piping,
  and rewrites a huge file repeatedly.
- **Engine POSTs results to the API:** couples the engine to the API and breaks
  standalone CLI use.

## Consequences

- **Positive:** Crash or abort keeps everything emitted so far. The API can ingest
  while the engine runs. `site-check 10.0.0.0/24 | jq -c 'select(.type=="host")'` works.
- **Positive:** A future Go engine (ADR 0006) only has to honour this line protocol to
  replace the Python engine transparently.
- **Negative:** Consumers must implement the merge rule. The API ingestion becomes
  upserts by natural key (`(run_id, ip)`, `(host_state_id, port)`,
  `(port_state_id, domain)`) instead of plain inserts.
- **Negative:** The API needs two concurrent pipe readers (stdout → ingestion,
  stderr → SSE) so a full pipe can't deadlock the subprocess.
- **Note:** There are no migrations (`SQLModel.metadata.create_all`). Adding the unique
  constraints needed for upserts requires resetting the dev DB, or introducing Alembic.
