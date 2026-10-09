# ADR 0015: Server-Sent Events (SSE) Execution Streaming

## Status

Accepted

## Context

Initial specifications (such as `docs/api/contracts.md` and `docs/05-control-plane-architecture.md`) proposed using WebSockets to stream engine execution logs back to the client (`WS /api/jobs/{id}/stream`). Additionally, the MVP architecture (ADR 0003) ran the Scanner engine in-process with FastAPI, piping logs through memory.

With the move to executing the engine as an isolated out-of-process subprocess (`asyncio.create_subprocess_exec`), we needed a reliable way to pipe `stdout` to the React frontend.

## Decision

We will use **Server-Sent Events (SSE)** via `fastapi.sse.EventSourceResponse` at `GET /api/runs/{id}/stream` to stream logs, officially replacing the WebSocket architecture.

## Consequences

- **Positive:** SSE is strictly unidirectional (server-to-client), perfectly matching the semantics of a log stream where the client does not send inputs back to the running engine.
- **Positive:** SSE natively utilizes standard HTTP/2 multiplexing, avoiding the heavy upgrade handshake and proxy configuration issues common with WebSockets.
- **Positive:** Built-in browser reconnection handles transient network drops automatically.
- **Negative:** SSE cannot be used for bidirectional communication (e.g., sending abort signals or interactive terminal inputs to the engine). Abort signals must be handled via a separate standard `POST /api/runs/{id}/abort` endpoint.
