# Site Health Check

This project consists of an interactive frontend and a FastAPI backend API for the Site Health Check dashboard.

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
   - **Frontend**: http://localhost:8080
   - **Backend API**: http://localhost:8000

## API Documentation (FastAPI)

The backend is built with FastAPI, which automatically generates interactive API documentation. While the backend is running, you can access the documentation via:

- **Swagger UI (Interactive)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

From the Swagger UI (`/docs`), you can view all available endpoints, their expected parameters, and even test them directly from your browser.

## Current Status

> **Warning:** The API is currently up and running, but the underlying `engine` is currently incompatible/in-development and will be integrated from an upstream source in the future.

## Starting the Backend Only

If you only want to work on the backend API without spinning up the frontend, run:
```bash
podman compose up backend --build -d
# or: docker compose up backend --build -d
```

## How to Clean

To completely clean the project and remove all containers, volumes, and dangling images:
```bash
podman compose down -v --rmi all
# or: docker compose down -v --rmi all
```

If you are developing locally with Python, you can clean your Poetry virtual environments by running:
```bash
rm -rf api/.venv engine/.venv
```

## Poetry & Local Development

This project uses [Poetry](https://python-poetry.org/) for Python dependency management. The `api` module explicitly depends on the `engine` module via a local path dependency.

If you want to run or test the code natively (without Docker):
1. Navigate to the `engine` directory and run `poetry install`.
2. Navigate to the `api` directory and run `poetry install`.

**Note:** If you add a new dependency to `api` (`poetry add <package>`), make sure you run it from within the `api/` directory.

## How to Stop
When you are done testing, you can stop the services by running:
```bash
podman compose down
# or: docker compose down
```