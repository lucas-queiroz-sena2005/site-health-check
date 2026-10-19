# 01: Core Job Submission Contract

**What to build:** A `POST /jobs` endpoint that accepts a scan request (targets, ports, labels), validates it via Pydantic schemas, and persists it to the SQLite `jobs` table using SQLModel.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] The `Job` model is defined according to the project's domain vocabulary using SQLModel/Pydantic.
- [ ] Do NOT use `...` (Ellipsis) as a default value for required fields in the model.
- [ ] The SQLite `jobs` table schema is created and aligned with the model.
- [ ] A `POST /jobs` API endpoint successfully writes a valid request to the database.
- [ ] The API router configuration uses router-level parameters (e.g., `APIRouter(prefix="/jobs", tags=["jobs"])`) rather than setting them in `include_router`.
- [ ] The endpoint returns a 201 Created status along with the newly generated Job ID, and has an explicitly defined return type.
- [ ] The API correctly rejects invalid payloads based on the Pydantic schema constraints.
