# Domain Glossary & Terminology

This document defines the shared vocabulary and core concepts (the Domain Model) for the Site Health Check project. Using these terms consistently prevents confusion across the API, Frontend, and Engine.

## Core Concepts (Data)

*   **Job (or Scan Request):** A high-level, human-readable request to check something. It can be a single URL, a massive CIDR block (e.g., `10.0.0.0/8`), or a predefined category (e.g., "all professors"). It exists primarily in the API and Frontend.
*   **Target:** A fully resolved, atomic destination to be checked. For example, the `Job` might be `192.168.1.0/24`, but one resulting `Target` is `192.168.1.5:443`.
*   **Task:** The physical payload (usually JSON) sent to the Message Broker representing exactly one `Target` and the specific instructions (flags) on how to check it.
*   **Result:** The outcome of a `Task` (e.g., Status 200, latency 45ms).
*   **Label (Metadata):** Key-value pairs attached to a `Task` and its `Result` (e.g., `group: students`). This is crucial for eventual Prometheus integration.

## Architectural Modules (The Services)

*   **The API (Configuration Service):** The Python (FastAPI) application. It handles user authentication, CRUD operations on the database (SQLite), and serves data to the Frontend.
*   **The Dispatcher (Splitter / Job Creator):** The module responsible for *Job Expansion*. It takes a high-level `Job`, handles the recursion (parsing CIDR blocks, looking up category members in the DB), and spits out thousands of atomic `Tasks`. 
*   **The Scanner (Execution Engine):** The module responsible *only* for executing network requests. It receives a `Task`, performs the HTTP ping, and returns a `Result`. It knows nothing about databases or CIDR block recursion.
*   **The Broker (RabbitMQ):** The queue that sits between the Dispatcher and the Scanner, holding `Tasks` until a Scanner is ready to process them.

## Architectural Patterns

*   **Hexagonal Architecture (Ports and Adapters):** A pattern where the core business logic (e.g., The Scanner) is completely isolated from the outside world. It defines a "Port" (an interface). "Adapters" are plugged into that port. For example, a `RabbitMQAdapter` feeds tasks from the queue, while a `CLIAdapter` feeds tasks from terminal arguments.
*   **Scatter-Gather (Splitter Pattern):** The pattern of breaking a massive `Job` into atomic `Tasks` (scattering), processing them independently, and writing them back to the database (gathering).
*   **Decompose by Business Capability:** Separating the system into distinct modules based on what they do (e.g., API vs. Dispatcher vs. Scanner).
