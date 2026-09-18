# ADR 0016: Execution Config Schema Synchronization (Static Generation)

## Status

Accepted

## Context

The FastAPI backend uses Pydantic models (e.g., `ExecutionFlags`) to validate incoming scan requests and dynamically translate them into CLI arguments for the engine subprocess. The React frontend needs to render forms (`ScanConfigForm.tsx`) that allow users to configure these flags when launching or scheduling a scan.

We must decide how to keep the frontend form schema synchronized with the backend Pydantic schema to prevent drift and missing features.

## Decision

For the MVP, we will adopt a **Static Type Generation** approach rather than dynamically rendering the form at runtime via `GET /api/schemas/schedule`. 

- The backend will expose its schema, but the frontend developer will use standard tooling (e.g., OpenAPI to TypeScript generators) to build static TypeScript interfaces and Zod validation schemas.
- The UI form will be manually built against these static schemas.

## Consequences

- **Positive:** Highly predictable UI behavior. Form layouts, grouping, and tooltips can be custom-designed in React without writing complex dynamic JSON-schema rendering logic.
- **Positive:** Complete type safety at build time.
- **Negative:** Requires a build/generation step to sync the schema whenever backend flags change. The frontend will not automatically sprout new form fields without a redeploy.
