# 02: Basic Result Retrieval Contract

**What to build:** A `GET /results` endpoint and the `results`/`ip_states` SQLite tables. It fetches basic paginated `IpState` results (like L4 TCP state and TLS certificates), proving the backend can store and retrieve the atomic scanner outcomes using SQLModel.

**Blocked by:** 01: Core Job Submission Contract

**Status:** ready-for-agent

- [ ] The `IpState`, `PortState`, `TlsCertificate`, and `HttpRoutingCheck` SQLModel/Pydantic models are defined.
- [ ] The SQLite tables corresponding to the results hierarchy are created.
- [ ] A `GET /results` endpoint fetches and successfully returns stored scanner outcomes.
- [ ] Basic pagination is implemented, and the query parameters use `Annotated[int, Query(...)]`.
- [ ] The return type is explicitly defined as `list[IpState]` (do not use `RootModel`).
- [ ] The results are correctly serialized as JSON via FastAPI leveraging Pydantic Rust serialization.
