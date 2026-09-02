from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool
import pytest

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

def test_create_and_get_saved_view(client: TestClient):
    payload = {
        "name": "My Custom View",
        "search": "10.0.0.0/24",
        "statuses": ["active", "ghost"],
        "table_sort_by": "latency",
        "table_sort_dir": "asc"
    }
    
    # POST
    post_resp = client.post("/views", json=payload)
    assert post_resp.status_code == 201
    
    post_data = post_resp.json()
    assert "id" in post_data
    assert isinstance(post_data["id"], str)
    
    view_id = post_data["id"]
    
    # GET
    get_resp = client.get(f"/views/{view_id}")
    assert get_resp.status_code == 200
    
    get_data = get_resp.json()
    assert get_data["id"] == view_id
    assert get_data["name"] == payload["name"]

def test_get_saved_view_not_found(client: TestClient):
    get_resp = client.get("/views/not-a-uuid")
    assert get_resp.status_code == 404
    assert get_resp.json() == {"detail": "View not found"}

