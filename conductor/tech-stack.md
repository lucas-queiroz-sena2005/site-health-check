# Technology Stack

## Backend
- **Language:** Python
- **Framework:** FastAPI
- **Database:** SQLite (with SQLModel / SQLAlchemy; database-agnostic normalized sorting)
- **API Architecture:** Dedicated flat table DTOs (`Page[T]`, `HostRowDTO`, `ServiceRowDTO`, `HttpCheckRowDTO`, `HostDetailDTO`), SQL-level pagination and multi-status filtering

## Frontend
- **Environment:** Node.js
- **Library:** React (Dumb UI pattern displaying backend DTOs)
- **State & Data Fetching:** TanStack Query, React Router (`useSearchParams` binding)
- **UI Components:** `shadcn/ui` (Base UI Dialog/Sheet primitives, Tailwind CSS)

## Execution Engine
- **Language:** Python (Asyncio)

## Deployment & Ops
- **Containerization:** Docker, Podman
- **CI/CD:** GitLab CI/CD
