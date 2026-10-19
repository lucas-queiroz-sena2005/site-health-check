import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from api.database import get_session
from api.main import app
from api.models import AlertConfig, ExecutionConfig, Scan, ScanRun


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


def test_execution_config_defaults():
    cfg = ExecutionConfig()
    assert cfg.ghost_window == "7d"
    assert cfg.tls_warning_days == 30

    custom = ExecutionConfig(ghost_window="24h", tls_warning_days=14)
    assert custom.ghost_window == "24h"
    assert custom.tls_warning_days == 14


def test_alert_config_model():
    alert = AlertConfig(
        webhook_url="https://chat.googleapis.com/v1/spaces/XYZ/messages",
        alert_on_failure=True,
        alert_on_ghost=True,
        alert_on_warning=False,
        alert_on_abort=True,
        alert_on_void=True,
        notify_on_healthy=False,
    )
    assert alert.webhook_url.startswith("https://chat.googleapis.com")
    assert alert.alert_on_warning is False
    assert alert.alert_on_failure is True
    assert alert.alert_on_void is True


def test_scan_model_alert_and_evaluation_fields(session: Session):
    scan = Scan(
        name="Scheduled Production Scan",
        cron_expression="0 * * * *",
        ports_json=[80, 443],
        flags_json={"check_http": True},
        ghost_window="48h",
        tls_warning_days=15,
        alert_config_json={
            "webhook_url": "https://hooks.slack.com/services/T00/B00/X00",
            "alert_on_failure": True,
            "alert_on_ghost": True,
            "alert_on_warning": True,
            "alert_on_abort": True,
            "notify_on_healthy": False,
        },
    )
    session.add(scan)
    session.commit()
    session.refresh(scan)

    assert scan.id is not None
    assert scan.ghost_window == "48h"
    assert scan.tls_warning_days == 15
    assert scan.alert_config_json["webhook_url"] == "https://hooks.slack.com/services/T00/B00/X00"


def test_api_create_and_get_scan_with_alerts(client: TestClient):
    payload = {
        "name": "Alerted Scan",
        "cron_expression": "0 0 * * *",
        "targets": ["10.0.0.0/24"],
        "ports": [443],
        "flags": {"check_http": True},
        "ghost_window": "24h",
        "tls_warning_days": 21,
        "alert_config": {
            "webhook_url": "https://chat.googleapis.com/v1/spaces/ABC",
            "alert_on_failure": True,
            "alert_on_ghost": True,
            "alert_on_warning": True,
            "alert_on_abort": True,
            "notify_on_healthy": True,
        },
    }

    resp = client.post("/api/scans", json=payload)
    assert resp.status_code == 201
    data = resp.json()

    assert data["name"] == "Alerted Scan"
    assert data["ghost_window"] == "24h"
    assert data["tls_warning_days"] == 21
    assert data["alert_config"]["webhook_url"] == "https://chat.googleapis.com/v1/spaces/ABC"
    assert data["alert_config"]["notify_on_healthy"] is True

    # Check GET /api/scans
    get_resp = client.get("/api/scans")
    assert get_resp.status_code == 200
    scans = get_resp.json()
    created = next(s for s in scans if s["id"] == data["id"])
    assert created["ghost_window"] == "24h"
    assert created["tls_warning_days"] == 21
    assert created["alert_config"]["webhook_url"] == "https://chat.googleapis.com/v1/spaces/ABC"


def test_api_update_scan_alert_config(client: TestClient):
    create_payload = {
        "name": "Scan To Modify",
        "targets": ["10.1.1.1"],
        "ports": [80],
        "flags": {},
    }
    create_resp = client.post("/api/scans", json=create_payload)
    scan_id = create_resp.json()["id"]

    update_payload = {
        "name": "Scan With Updated Alerts",
        "targets": ["10.1.1.1"],
        "ports": [80],
        "flags": {},
        "ghost_window": "3d",
        "tls_warning_days": 10,
        "alert_config": {
            "webhook_url": "https://hooks.slack.com/services/111/222/333",
            "alert_on_failure": True,
            "alert_on_ghost": False,
            "alert_on_warning": True,
            "alert_on_abort": False,
            "notify_on_healthy": False,
        },
    }
    put_resp = client.put(f"/api/scans/{scan_id}", json=update_payload)
    assert put_resp.status_code == 200
    put_data = put_resp.json()

    assert put_data["ghost_window"] == "3d"
    assert put_data["tls_warning_days"] == 10
    assert put_data["alert_config"]["webhook_url"] == "https://hooks.slack.com/services/111/222/333"
    assert put_data["alert_config"]["alert_on_ghost"] is False
