# Technology Stack

## Backend
- **Language:** Python
- **Framework:** FastAPI
- **Database:** SQLite with database-agnostic schema design (WAL mode, `synchronous=NORMAL`, `foreign_keys=ON`; normalized `ip_sort_key` for portable sorting; SQLModel / SQLAlchemy Core multi-row bulk upserts and set-based relational pushdown)
- **Evaluation Architecture:** Pure functional rule core (`evaluator_rules.py`) with 100% test branch coverage separated from relational subquery pushdown engine (`evaluator.py`)
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
