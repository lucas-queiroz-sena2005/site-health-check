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

def test_create_and_get_scan(client: TestClient):
    payload = {
        "name": "Test Scan",
        "cron_expression": "0 0 * * *",
        "targets": ["example.com"],
        "ports": [80, 443],
        "flags": {"check_http": True, "timeout": 30}
    }
    
    post_resp = client.post("/api/scans", json=payload)
    assert post_resp.status_code == 201
    post_data = post_resp.json()
    assert "id" in post_data
    scan_id = post_data["id"]
    
    get_resp = client.get("/api/scans")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    
    # Assert our created scan is in the list
    scan = next((s for s in get_data if s["id"] == scan_id), None)
    assert scan is not None
    assert scan["name"] == payload["name"]
    assert scan["cron_expression"] == payload["cron_expression"]
    assert scan["next_run"] is not None

def test_update_scan(client: TestClient):
    payload = {
        "name": "Scan To Update",
        "targets": ["old.com"],
        "ports": [80],
        "flags": {}
    }
    post_resp = client.post("/api/scans", json=payload)
    scan_id = post_resp.json()["id"]
    
    put_payload = {
        "name": "Updated Scan",
        "targets": ["new.com"],
        "ports": [443],
        "flags": {}
    }
    
    put_resp = client.put(f"/api/scans/{scan_id}", json=put_payload)
    assert put_resp.status_code == 200
    put_data = put_resp.json()
    assert put_data["name"] == "Updated Scan"
    assert put_data["targets"] == ["new.com"]
    assert put_data["ports"] == [443]

def test_update_scan_not_found(client: TestClient):
    put_payload = {
        "name": "Updated Scan",
        "targets": ["new.com"],
        "ports": [443],
        "flags": {}
    }
    put_resp = client.put("/api/scans/not-a-uuid", json=put_payload)
    assert put_resp.status_code == 404

def test_delete_scan(client: TestClient):
    payload = {
        "name": "Scan To Delete",
        "targets": ["delete.com"],
        "ports": [80],
        "flags": {}
    }
    post_resp = client.post("/api/scans", json=payload)
    scan_id = post_resp.json()["id"]
    
    del_resp = client.delete(f"/api/scans/{scan_id}")
    assert del_resp.status_code == 204
    
    get_resp = client.get("/api/scans")
    get_data = get_resp.json()
    assert not any(s["id"] == scan_id for s in get_data)

def test_delete_scan_not_found(client: TestClient):
    del_resp = client.delete("/api/scans/not-a-uuid")
    assert del_resp.status_code == 404
