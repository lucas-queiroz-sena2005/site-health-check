import pytest
from api.database import get_session
from api.main import app
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool


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

def test_create_and_get_saved_view(client: TestClient):
    payload = {
        "name": "My Custom View",
        "search": "10.0.0.0/24",
        "statuses": ["active", "ghost"],
        "table_sort_by": "latency",
        "table_sort_dir": "asc"
    }
    
    # POST
    post_resp = client.post("/api/views", json=payload)
    assert post_resp.status_code == 201
    
    post_data = post_resp.json()
    assert "id" in post_data
    assert isinstance(post_data["id"], str)
    
    view_id = post_data["id"]
    
    # GET
    get_resp = client.get(f"/api/views/{view_id}")
    assert get_resp.status_code == 200
    
    get_data = get_resp.json()
    assert get_data["id"] == view_id
    assert get_data["name"] == payload["name"]

def test_get_saved_view_not_found(client: TestClient):
    get_resp = client.get("/api/views/not-a-uuid")
    assert get_resp.status_code == 404
    assert get_resp.json() == {"detail": "View not found"}

def test_list_saved_views(client: TestClient):
    # Empty initially
    resp = client.get("/api/views")
    assert resp.status_code == 200
    assert resp.json() == []

    payload1 = {"name": "View 1"}
    payload2 = {"name": "View 2"}
    client.post("/api/views", json=payload1)
    client.post("/api/views", json=payload2)

    resp = client.get("/api/views")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    names = [v["name"] for v in data]
    assert "View 1" in names
    assert "View 2" in names

def test_delete_saved_view(client: TestClient):
    payload = {"name": "Delete Me"}
    post_resp = client.post("/api/views", json=payload)
    view_id = post_resp.json()["id"]

    del_resp = client.delete(f"/api/views/{view_id}")
    assert del_resp.status_code == 204

    get_resp = client.get(f"/api/views/{view_id}")
    assert get_resp.status_code == 404

def test_delete_saved_view_not_found(client: TestClient):
    del_resp = client.delete("/api/views/not-a-uuid")
    assert del_resp.status_code == 404
    assert del_resp.json() == {"detail": "View not found"}
