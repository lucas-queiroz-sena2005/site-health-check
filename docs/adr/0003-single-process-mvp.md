# 3. Single Process MVP Architecture

Date: 2026-08-26

## Status

Accepted

## Context

For Phase 2 (MVP), we need to introduce the FastAPI control plane and SQLite database, while transitioning the Scanner from a one-shot CLI execution to a long-running worker. 

We had to decide between running the API and Scanner in completely separate processes (which requires early adoption of RabbitMQ or complex SQLite locking configurations) versus a single-process Monolith.

## Decision

We will use a **Single Process (Monolithic) MVP**.
- FastAPI and the Scanner engine will run in the exact same Python process, governed by a single `asyncio` event loop.
- The Dispatcher and Scanner will be spawned as background tasks during FastAPI's lifespan startup event.
- Tasks will be passed between the API, Dispatcher, and Scanner using in-memory `asyncio.Queue` primitives, perfectly mimicking the channel semantics of RabbitMQ/Go, but without the infrastructure overhead.

## Consequences

*   **Positive:** Zero infrastructure required. `python main.py` runs the entire stack.
*   **Positive:** SQLite connection pooling and locking are handled safely within a single process.
*   **Positive:** The `asyncio.Queue` semantics map 1:1 to RabbitMQ AMQP queues, making the Phase 3 (Distributed) refactor completely trivial.
*   **Negative:** If the Scanner encounters a fatal memory leak or segmentation fault, it will crash the FastAPI web server. (Acceptable for MVP).
