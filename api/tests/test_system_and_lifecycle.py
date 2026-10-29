import os
import uuid
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from api.database import get_session, init_db
from api.main import app
from api.models import (
    EntityStatus,
    HostState,
    HttpRoutingCheck,
    PortState,
    Scan,
    ScanRun,
    ScanRunStatus,
    SystemConfig,
    TlsCertificate,
)
from api.services.scheduler import check_and_run_scheduled_scans, prune_expired_runs


@pytest.fixture(name="lifecycle_engine")
def lifecycle_engine_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        cfg = session.get(SystemConfig, 1)
        if not cfg:
            session.add(SystemConfig(id=1, retention_days=0))
            session.commit()
    return engine


@pytest.fixture(name="client")
def client_fixture(lifecycle_engine, monkeypatch):
    monkeypatch.setattr("api.database.engine", lifecycle_engine)
    monkeypatch.setattr("api.routers.system.engine", lifecycle_engine)
    monkeypatch.setattr("api.services.scheduler.engine", lifecycle_engine)

    def override_get_session():
        with Session(lifecycle_engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    # Mock RunManager on app.state
    mock_run_manager = MagicMock()
    mock_run_manager.is_active.return_value = False
    mock_run_manager.abort_run.return_value = True
    mock_run_manager.unregister_run = MagicMock()
    mock_run_manager.dispatch_run = AsyncMock()
    app.state.run_manager = mock_run_manager

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_delete_run_not_found(client: TestClient):
    """DELETE /api/runs/{id} returns 404 when run does not exist."""
    res = client.delete("/api/runs/non-existent-id")
    assert res.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in res.json()["detail"].lower()


def test_delete_run_conflict_when_active(client: TestClient, lifecycle_engine):
    """DELETE /api/runs/{id} returns 409 Conflict when run is RUNNING or PENDING."""
    with Session(lifecycle_engine) as session:
        run = ScanRun(
            id="active-run-1",
            status=ScanRunStatus.RUNNING,
            execution_config_snapshot_json={},
            started_at=datetime.now(timezone.utc),
        )
        session.add(run)
        session.commit()

    res = client.delete("/api/runs/active-run-1")
    assert res.status_code == status.HTTP_409_CONFLICT
    assert "active run" in res.json()["detail"].lower()


def test_delete_run_cascades_terminal_run_and_children(client: TestClient, lifecycle_engine):
    """DELETE /api/runs/{id} returns 204 and cascades deletion to Host, Port, TLS, and HTTP checks."""
    run_id = "terminal-run-1"
    with Session(lifecycle_engine) as session:
        run = ScanRun(
            id=run_id,
            status=ScanRunStatus.COMPLETED,
            execution_config_snapshot_json={},
            started_at=datetime.now(timezone.utc) - timedelta(hours=1),
            finished_at=datetime.now(timezone.utc),
        )
        session.add(run)
        session.flush()

        host = HostState(id="h1", scan_run_id=run_id, ip_address="10.0.0.1")
        session.add(host)
        session.flush()

        port = PortState(id="p1", host_state_id=host.id, port_number=443, tcp_status="open")
        session.add(port)
        session.flush()

        cert = TlsCertificate(id="c1", port_state_id=port.id, valid=True, expires_in_days=30)
        check = HttpRoutingCheck(id="chk1", port_state_id=port.id, domain="example.com", status_code=200)
        session.add_all([cert, check])
        session.commit()

    res = client.delete(f"/api/runs/{run_id}")
    assert res.status_code == status.HTTP_204_NO_CONTENT

    with Session(lifecycle_engine) as session:
        assert session.get(ScanRun, run_id) is None
        assert session.get(HostState, "h1") is None
        assert session.get(PortState, "p1") is None
        assert session.get(TlsCertificate, "c1") is None
        assert session.get(HttpRoutingCheck, "chk1") is None


def test_delete_scan_hard_deletes_and_cascades(client: TestClient, lifecycle_engine):
    """DELETE /api/scans/{id} hard-deletes the Scan row and cascades deletion to all runs and child entities."""
    scan_id = "sched-to-delete"
    run_id = "sched-run-1"
    with Session(lifecycle_engine) as session:
        scan = Scan(
            id=scan_id,
            name="Schedule To Delete",
            targets=["10.0.0.0/24"],
            ports_json=[80],
            flags_json={},
        )
        session.add(scan)
        session.flush()

        run = ScanRun(
            id=run_id,
            scan_id=scan_id,
            status=ScanRunStatus.COMPLETED,
            execution_config_snapshot_json={},
            started_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        session.add(run)
        session.flush()

        host = HostState(id="h-sched", scan_run_id=run_id, ip_address="10.0.0.5")
        session.add(host)
        session.commit()

    res = client.delete(f"/api/scans/{scan_id}")
    assert res.status_code == status.HTTP_204_NO_CONTENT

    with Session(lifecycle_engine) as session:
        assert session.get(Scan, scan_id) is None
        assert session.get(ScanRun, run_id) is None
        assert session.get(HostState, "h-sched") is None


def test_scheduler_tracks_last_triggered_at_and_decouples_history_deletion(lifecycle_engine, monkeypatch):
    """Scheduler tracks Scan.last_triggered_at so deleting past runs does not re-trigger schedule immediately."""
    from unittest.mock import AsyncMock

    monkeypatch.setattr("api.services.scheduler.engine", lifecycle_engine)
    mock_app_state = MagicMock()
    mock_app_state.run_manager.dispatch_run = AsyncMock()

    now = datetime.now(timezone.utc)
    with Session(lifecycle_engine) as session:
        scan = Scan(
            id="cron-decoupled-scan",
            name="Decoupled Cron Scan",
            cron_expression="* * * * *",  # Every minute
            is_active=True,
            targets=["10.0.0.1"],
            ports_json=[80],
            flags_json={},
            last_triggered_at=now,  # Already triggered this minute
        )
        session.add(scan)
        session.commit()

    # Even with 0 past runs in history, last_triggered_at prevents immediate duplicate firing
    import asyncio
    asyncio.run(check_and_run_scheduled_scans(mock_app_state))
    assert mock_app_state.run_manager.dispatch_run.call_count == 0


def test_prune_expired_runs_retention_policy(lifecycle_engine):
    """prune_expired_runs deletes terminal runs older than retention_days and preserves active/recent runs."""
    now = datetime.now(timezone.utc)
    with Session(lifecycle_engine) as session:
        # Run 1: Completed 10 days ago (expired if retention=7)
        r1 = ScanRun(
            id="old-run",
            status=ScanRunStatus.COMPLETED,
            started_at=now - timedelta(days=10),
            finished_at=now - timedelta(days=10),
            execution_config_snapshot_json={},
        )
        # Run 2: Completed 2 days ago (not expired)
        r2 = ScanRun(
            id="recent-run",
            status=ScanRunStatus.COMPLETED,
            started_at=now - timedelta(days=2),
            finished_at=now - timedelta(days=2),
            execution_config_snapshot_json={},
        )
        # Run 3: Running for 8 days (active runs must never be pruned)
        r3 = ScanRun(
            id="active-old-run",
            status=ScanRunStatus.RUNNING,
            started_at=now - timedelta(days=8),
            execution_config_snapshot_json={},
        )
        session.add_all([r1, r2, r3])
        session.commit()

        pruned = prune_expired_runs(session, retention_days=7)
        assert pruned == 1

        assert session.get(ScanRun, "old-run") is None
        assert session.get(ScanRun, "recent-run") is not None
        assert session.get(ScanRun, "active-old-run") is not None


def test_system_settings_get_and_put(client: TestClient, lifecycle_engine):
    """GET and PUT /api/system/settings return and update retention_days and trigger pruning."""
    # GET settings
    get_res = client.get("/api/system/settings")
    assert get_res.status_code == status.HTTP_200_OK
    data = get_res.json()
    assert "retention_days" in data
    assert data["retention_days"] == 0
    assert "total_runs" in data

    # Insert an old run
    with Session(lifecycle_engine) as session:
        old_run = ScanRun(
            id="run-to-expire",
            status=ScanRunStatus.COMPLETED,
            started_at=datetime.now(timezone.utc) - timedelta(days=40),
            finished_at=datetime.now(timezone.utc) - timedelta(days=40),
            execution_config_snapshot_json={},
        )
        session.add(old_run)
        session.commit()

    # PUT settings to 30 days -> should immediately prune run-to-expire
    put_res = client.put("/api/system/settings", json={"retention_days": 30})
    assert put_res.status_code == status.HTTP_200_OK
    assert put_res.json()["retention_days"] == 30

    with Session(lifecycle_engine) as session:
        assert session.get(ScanRun, "run-to-expire") is None
        cfg = session.get(SystemConfig, 1)
        assert cfg.retention_days == 30


def test_system_purge_runs(client: TestClient, lifecycle_engine):
    """POST /api/system/purge-runs wipes all ScanRuns and children but preserves Scans and SystemConfig."""
    with Session(lifecycle_engine) as session:
        scan = Scan(id="preserved-scan", name="Keep Me", targets=["10.0.0.1"], ports_json=[80], flags_json={})
        session.add(scan)
        run = ScanRun(
            id="purge-run-1",
            scan_id="preserved-scan",
            status=ScanRunStatus.COMPLETED,
            execution_config_snapshot_json={},
        )
        session.add(run)
        session.commit()

    res = client.post("/api/system/purge-runs")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["purged_count"] >= 1

    with Session(lifecycle_engine) as session:
        assert session.get(Scan, "preserved-scan") is not None
        assert session.get(ScanRun, "purge-run-1") is None
        assert session.get(SystemConfig, 1) is not None


def test_system_reset_db(client: TestClient, lifecycle_engine):
    """POST /api/system/reset-db resets entire schema and recreates initial default state."""
    with Session(lifecycle_engine) as session:
        scan = Scan(id="to-be-dropped", name="Drop Me", targets=["10.0.0.1"], ports_json=[80], flags_json={})
        session.add(scan)
        session.commit()

    res = client.post("/api/system/reset-db")
    assert res.status_code == status.HTTP_200_OK
    assert "reset successfully" in res.json()["message"].lower()

    with Session(lifecycle_engine) as session:
        assert session.get(Scan, "to-be-dropped") is None
        cfg = session.get(SystemConfig, 1)
        assert cfg is not None
        assert cfg.retention_days == 0
