import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from api.main import app
from api.database import get_session

@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

@pytest.fixture(name="client")
def client_fixture(session: Session):
    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()

def test_launch_run_and_list_runs(client: TestClient):
    # Launch an ad-hoc run
    launch_resp = client.post(
        "/api/runs/launch",
        json={
            "targets": ["10.0.0.1"],
            "ports": [80, 443],
            "flags": {"check_tcp": True}
        }
    )
    assert launch_resp.status_code == 201
    run_data = launch_resp.json()
    assert "id" in run_data
    run_id = run_data["id"]
    assert run_data["status"] == "PENDING"
    assert run_data["targets"] == ["10.0.0.1"]

    # List runs - should not be empty!
    list_resp = client.get("/api/runs?limit=50")
    assert list_resp.status_code == 200
    runs = list_resp.json()
    assert len(runs) >= 1
    found = next((r for r in runs if r["id"] == run_id), None)
    assert found is not None
    assert found["targets"] == ["10.0.0.1"]

def test_launch_scheduled_scan_endpoint(client: TestClient):
    # Create a scheduled scan
    scan_resp = client.post(
        "/api/scans",
        json={
            "name": "Production Scan",
            "cron_expression": "*/5 * * * *",
            "targets": ["192.168.1.1"],
            "ports": [80],
            "flags": {}
        }
    )
    assert scan_resp.status_code == 201
    scan_id = scan_resp.json()["id"]

    # Force launch the scheduled scan
    force_resp = client.post(f"/api/scans/{scan_id}/launch")
    assert force_resp.status_code == 201
    forced_run = force_resp.json()
    assert forced_run["scan_id"] == scan_id
    assert forced_run["scan_name"] == "Production Scan"
    assert forced_run["targets"] == ["192.168.1.1"]

    # List runs with scan_id filter
    filter_resp = client.get(f"/api/runs?scan_id={scan_id}")
    assert filter_resp.status_code == 200
    filtered_runs = filter_resp.json()
    assert len(filtered_runs) == 1
    assert filtered_runs[0]["id"] == forced_run["id"]
