# 04: Saved Views UI State Contract

**What to build:** `POST /views` and `GET /views/{id}` endpoints with their corresponding SQLite `saved_views` storage. This allows the frontend to persist and load UI layouts and read-time filters to share permalinks.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] The `SavedView` SQLModel/Pydantic model is defined to capture filters, columns, and layout states.
- [ ] The SQLite `saved_views` table schema is created.
- [ ] The API maintains one HTTP operation per function (e.g. separate functions for POST and GET).
- [ ] A `POST /views` endpoint successfully writes a valid UI state to the database, utilizing explicit return types.
- [ ] A `GET /views/{id}` endpoint successfully retrieves the stored UI state, using `id: Annotated[int, Path()]` for the path parameter.
- [ ] Missing or invalid view IDs return an appropriate 404 error.
