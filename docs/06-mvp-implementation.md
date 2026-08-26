# Phase 2: MVP Implementation Plan (React + FastAPI + SQLite)

Based on architectural exploration, this document outlines the Minimum Viable Product (MVP) to transition `site-health-check` from a stateless CLI tool into a stateful Control Plane. 

To prevent over-engineering, we will intentionally skip Prometheus integration and complex Classifications for this initial build. The goal is to establish the core loop of user configuration and execution.

## MVP Scope

1. **Frontend (React + Vite):** A modern, dark-mode Single Page Application (SPA) that acts as the "Control Plane", allowing users to add targets and view the resulting JSON graph/data.
2. **Backend (FastAPI):** A high-performance Python REST API to serve the React app, interact with SQLite, and trigger the CLI Engine.
3. **Database (SQLite):** A lightweight local database to persistently store the list of targets the user wants to scan.
4. **Execution (Cron/Ad-hoc):** The engine is executed strictly by FastAPI (which is triggered by `cron` or UI ad-hoc requests). FastAPI reads the database and passes the instructions directly to the Engine as a JSON payload.

## Proposed Changes

### 1. The Backend (FastAPI)
FastAPI will act as the bridge between the UI and the SQLite database.

*   `src/site_health_check/api/main.py`: The core FastAPI application serving REST endpoints (`GET /targets`, `POST /targets`, `POST /scan/ad-hoc`).
*   `src/site_health_check/api/database.py`: SQLite setup using `sqlite3` or `SQLAlchemy` to store the raw target strings.

### 2. The Frontend (React + Vite)
A new `frontend/` directory at the root of the project to house the React application.

*   `frontend/package.json`: Standard Vite + React scaffolding. Using Vanilla CSS/CSS Modules for styling to maintain strict control over premium aesthetics (dark mode, glassmorphism).
*   `frontend/src/App.jsx`: The main Dashboard. It will have two primary views for the MVP:
    1.  **Target Management:** A simple list/form to add/remove targets from SQLite.
    2.  **Results Viewer:** A view that reads the generated `results.json` from the engine and displays it cleanly (setting the foundation for the future Topology Node Graph).

### 3. Integrating the Engine (The Single-Process asyncio Model)
The existing CLI engine will be refactored to consume from an `asyncio.Queue` instead of a static list.

*   FastAPI acts as the orchestrator. When a Job arrives, FastAPI writes it to SQLite and immediately pushes the Tasks into an in-memory `asyncio.Queue`.
*   **Execution Strategy:** FastAPI spawns the Dispatcher and Scanner as background coroutines running on its own event loop.
    *   **Simplicity:** Zero infrastructure overhead. `uvicorn` runs the entire stack (API + Scanner).
    *   **Golang/RabbitMQ Future-Proofing:** Python's `asyncio.Queue` behaves conceptually exactly like Go's `channels` and RabbitMQ's message queues. Swapping `queue.put()` with `rabbitmq.publish()` in Phase 3 will be a seamless architectural shift. (See ADR 0003).

---

## Architectural Rationale (Tech Stack & Data Contracts)

To ensure this tool remains clean, traceable, and maintainable by backend engineers, the following strict architectural rules apply:

### 1. The Backend (FastAPI)
- **Why:** FastAPI is chosen over Flask because it enforces strict data validation using `Pydantic`.
- **Traceability:** Engineers can instantly read the Pydantic models to know exactly what the frontend JSON payloads look like, without guessing. It also auto-generates Swagger documentation (`/docs`) for easy scripting by SREs.

### 2. The Frontend (React + Vite)
- **Why:** While Vue is structurally cleaner, React is chosen because of its unparalleled ecosystem for complex network visualizations (e.g., `react-flow`).
- **Aesthetics:** The UI will prioritize high information density and utility (like AWS Console or Datadog) rather than flashy consumer styling. It will rely heavily on component traceability (`<TopologyGraph />`, `<ResultMatrix />`).

### 3. The Data Contract (Postel's Law)
We adhere strictly to Postel's Law (*"Be conservative in what you send, be liberal in what you accept"*):
- **Strict Backend:** FastAPI will strictly validate all configuration inputs from the frontend. Invalid configs are rejected instantly to protect the SQLite database.
- **Loose Frontend:** When the React frontend reads the generated `results.json` from the Python Engine, it must be highly resilient. If the Python Engine introduces new keys (e.g., `{"tls_score": "A"}`), the frontend will not crash. It will expect core fields (`ip`, `domain`, `status`) to render the graph, but will dynamically dump any unknown keys into an "Additional Details" view. This allows the Engine to evolve rapidly without breaking the UI.

---
*Note: Once this core loop is flawless, adding Prometheus labels and Classifications will be the next immediate step.*
