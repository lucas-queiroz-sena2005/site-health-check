Status: ready-for-agent

## Problem Statement

The user needs to define the SQLite database structure and the corresponding API contracts for interactions between the FastAPI backend and the React frontend. Without a formal contract, there is a risk of field drift and integration issues between the Scanner results, the database, and the frontend views.

## Solution

Implement a contract-first architecture for the `site-health-check` project. This involves formally defining the data models (Job, Target, Result, Unified Target View, Ghost, Void Space) and their corresponding SQLite schema and FastAPI endpoints. This ensures both backend and frontend agree on the exact shape of the data, specifically accommodating the read-time filtering, dynamic ghost ageing, and void node aggregation described in the architectural decisions.

## User Stories

1. As a frontend developer, I want a well-defined API contract for submitting Jobs, so that I know exactly what fields (targets, ports, flags, labels) are required.
2. As a frontend developer, I want a well-defined API contract for querying Results, so that I can render the topology DAG correctly.
3. As a user, I want to submit a Job with a CIDR block, so that the system scans the entire range.
4. As a user, I want to filter results by `ghost_window`, so that I can see historically responsive IPs that are currently down.
5. As a frontend rendering engine, I want contiguous dead IPs to be squashed into a single Void Node, so that rendering performance remains high for massive CIDR blocks.
6. As a user, I want to save my current UI view state (filters, columns), so that I can share a permalink with my team.
7. As an SRE, I want to load a Saved View via a permalink, so that I see the exact same layout and filtered results as my colleague.
8. As a backend developer, I want the SQLite schema to efficiently index Job targets and timestamps, so that read-time filtering and dynamic ghost calculation are performant.

## Implementation Decisions

- **Contract-First API Design**: OpenAPI/Pydantic schemas will be defined as the single source of truth for all interactions between the React frontend and FastAPI backend.
- **SQLite Schema & ORM**:
  - We will use **SQLModel** as the ORM to bridge Pydantic and SQLAlchemy seamlessly.
  - `jobs`: Stores user-submitted scan requests (target expression, ports, labels).
  - `results` / `ip_states`: Stores the atomic outcomes from the Scanner (L4 TCP state, TLS certificates, L7 HTTP routing).
  - `saved_views`: Stores UI state for read-time filtering.
- **API Endpoints**:
  - `POST /jobs`: Submit a new scan request.
  - `GET /results`: Fetch paginated scan results. Implements dynamic Ghost calculation (using `?ghost_window=X`) and Void Node squashing.
  - `POST /views` / `GET /views/{id}`: Save and retrieve UI view states.
  - *FastAPI Best Practices:* All parameters will use `Annotated` (e.g. `Annotated[int, Query()]`), all routes will declare explicit return types to leverage Rust serialization, and standard synchronous `def` functions will be used unless the logic is strictly non-blocking async.

## Testing Decisions

- **Good Tests**: Tests will verify the external behavior of the API contracts without relying on the internal SQLite implementation details. We will test the API endpoints directly (using a test client) to ensure they respect the defined Pydantic schemas.
- **Modules Tested**: FastAPI routing layer, Pydantic validation, SQLite persistence layer (SQLModel), and the dynamic Ghost/Void aggregation logic.
- **Seams**: 
  - **Highest Seam**: The HTTP API boundaries. We will spin up the FastAPI app with an in-memory SQLite database and issue real HTTP requests to validate the contracts and aggregation logic.
  - **Internal Seam**: The Ghost/Void calculation logic will be isolated into a pure function/service layer, allowing for unit tests of the aggregation logic without needing a full HTTP context.

## Out of Scope

- The Go Engine / Scanner implementation.
- The RabbitMQ / Broker integration.
- The actual React frontend implementation (this spec only covers the contract and backend support).

## Further Notes

This spec synthesizes the `CONTEXT.md` vocabulary (Target, Job, Result, Ghost, Void Space) and the decisions from ADRs 0004 and 0005.
