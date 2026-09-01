import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from site_health_check.api.main import app
from site_health_check.api.database import get_session

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

def test_create_job(client: TestClient):
    response = client.post(
        "/jobs/",
        json={
            "targets": ["google.com", "example.com"],
            "ports": [80, 443],
            "labels": {"team": "sre"}
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert isinstance(data["id"], int)

def test_create_job_invalid(client: TestClient):
    response = client.post(
        "/jobs/",
        json={
            "targets": "google.com", # Should be a list
            "ports": [80, 443],
        },
    )
    assert response.status_code == 422
