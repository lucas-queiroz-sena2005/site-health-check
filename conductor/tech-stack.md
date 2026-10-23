# Technology Stack

## Backend
- **Language:** Python
- **Framework:** FastAPI
- **Database:** SQLite (with SQLModel / SQLAlchemy; database-agnostic normalized sorting)
- **API Architecture:** Dedicated flat table DTOs (`Page[T]`, `HostRowDTO`, `ServiceRowDTO`, `HttpCheckRowDTO`, `HostDetailDTO`), SQL-level pagination and multi-status filtering

## Frontend
- **Environment:** Node.js
- **Library:** React
- **UI Components:** `shadcn/ui`

## Execution Engine
- **Language:** Python (Asyncio)

## Deployment & Ops
- **Containerization:** Docker, Podman
- **CI/CD:** GitLab CI/CD
