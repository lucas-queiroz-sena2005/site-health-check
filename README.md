# Site Health Check

This project consists of an interactive frontend prototype and a FastAPI backend API for the Site Health Check dashboard.

## Requirements
- Docker
- Docker Compose (or Podman Compose)

## How to Run

1. Open a terminal in this directory.
2. Run the following command to build and start the application (frontend and backend):
   ```bash
   podman compose up --build -d
   # or: docker compose up --build -d
   ```
3. Open your web browser and navigate to: 
   - **Frontend Prototype**: http://localhost:8080
   - **Backend API**: http://localhost:8000

## API Documentation (FastAPI)

The backend is built with FastAPI, which automatically generates interactive API documentation. While the backend is running, you can access the documentation via:

- **Swagger UI (Interactive)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

From the Swagger UI (`/docs`), you can view all available endpoints, their expected parameters, and even test them directly from your browser.

## Current Status

> **Warning:** The API is currently up and running, but the underlying `engine` is currently incompatible/in-development and will be integrated from an upstream source in the future.

## How to Stop
When you are done testing, you can stop the services by running:
```bash
podman compose down
# or: docker compose down
```