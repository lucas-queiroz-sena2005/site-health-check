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

class FakeProcess:
    def __init__(self):
        self.signals: list[int] = []
        self.returncode = None

    def send_signal(self, sig: int):
        self.signals.append(sig)

    def kill(self):
        self.returncode = -9


def test_abort_run_sends_sigterm(client: TestClient):
    import signal

    launch_resp = client.post(
        "/api/runs/launch",
        json={"targets": ["10.0.0.1"], "ports": [80], "flags": {}},
    )
    assert launch_resp.status_code == 201
    run_id = launch_resp.json()["id"]

    process = FakeProcess()
    app.state.run_manager.register_process(run_id, process)
    try:
        abort_resp = client.post(f"/api/runs/{run_id}/abort")
    finally:
        app.state.run_manager.unregister_process(run_id)

    assert abort_resp.status_code == 202
    assert "Abort signal sent" in abort_resp.json()["message"]
    assert process.signals == [signal.SIGTERM]


def test_abort_unknown_run_returns_404(client: TestClient):
    resp = client.post("/api/runs/does-not-exist/abort")
    assert resp.status_code == 404


def test_abort_finished_run_returns_409(client: TestClient, session: Session):
    from api.models import ScanRun, ScanRunStatus

    run = ScanRun(execution_config_snapshot_json={}, status=ScanRunStatus.COMPLETED)
    session.add(run)
    session.commit()

    resp = client.post(f"/api/runs/{run.id}/abort")
    assert resp.status_code == 409


def test_stream_run_logs_delegates_to_run_manager(client: TestClient, session: Session):
    from fastapi.sse import ServerSentEvent
    from api.models import ScanRun, ScanRunStatus

    run_id = "test-stream-endpoint-run"
    run = ScanRun(id=run_id, execution_config_snapshot_json={}, status=ScanRunStatus.COMPLETED)
    session.add(run)
    session.commit()

    app.state.run_manager.publish_log(run_id, ServerSentEvent(data={"msg": "first"}, event="log"))

    with client.stream("GET", f"/api/runs/{run_id}/stream") as response:
        assert response.status_code == 200
        content = "\n".join(response.iter_lines())
        assert "first" in content


def test_unified_create_run_endpoint(client: TestClient):
    # 1. Ad-hoc run launch via POST /api/runs
    resp_adhoc = client.post(
        "/api/runs",
        json={
            "targets": ["10.0.0.1"],
            "ports": [80, 443],
            "flags": {"check_tcp": True},
        },
    )
    assert resp_adhoc.status_code == 201
    run_adhoc = resp_adhoc.json()
    assert run_adhoc["targets"] == ["10.0.0.1"]
    assert run_adhoc["scan_id"] is None

    # Missing targets without scan_id returns 400
    resp_empty = client.post("/api/runs", json={"targets": []})
    assert resp_empty.status_code == 400

    # 2. Create a scheduled scan
    scan_resp = client.post(
        "/api/scans",
        json={
            "name": "Unified Production Scan",
            "cron_expression": "0 0 * * *",
            "targets": ["prod.example.com"],
            "ports": [443],
            "flags": {"check_http": True},
        },
    )
    assert scan_resp.status_code == 201
    scan_id = scan_resp.json()["id"]

    # Launch scheduled scan via POST /api/runs supplying only scan_id
    resp_sched = client.post("/api/runs", json={"scan_id": scan_id})
    assert resp_sched.status_code == 201
    run_sched = resp_sched.json()
    assert run_sched["scan_id"] == scan_id
    assert run_sched["scan_name"] == "Unified Production Scan"
    assert run_sched["targets"] == ["prod.example.com"]
    assert run_sched["ports"] == [443]

    # Launch with runtime overrides
    resp_override = client.post(
        "/api/runs",
        json={"scan_id": scan_id, "targets": ["override.example.com"], "ports": [8443]},
    )
    assert resp_override.status_code == 201
    run_override = resp_override.json()
    assert run_override["targets"] == ["override.example.com"]
    assert run_override["ports"] == [8443]

    # Non-existent scan_id returns 404
    resp_404 = client.post("/api/runs", json={"scan_id": "nonexistent-scan-id"})
    assert resp_404.status_code == 404

