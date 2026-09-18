import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from api.models import Scan, TargetGroup, ScanTargetGroupLink, ScanRun, ScanRunStatus
from api.services.scheduler import check_and_run_scheduled_scans

class DummyAppState:
    def __init__(self):
        self.log_subscribers = {}
        self.run_logs = {}

@pytest.mark.asyncio
async def test_scheduler_triggers_due_scan(monkeypatch):
    test_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(test_engine)
    monkeypatch.setattr("api.services.scheduler.engine", test_engine)

    # Mock run_engine_cli so it doesn't actually launch a subprocess in test
    called_runs = []
    async def mock_run_engine_cli(run_id, snapshot, app_state):
        called_runs.append(run_id)

    monkeypatch.setattr("api.services.scheduler.run_engine_cli", mock_run_engine_cli)

    app_state = DummyAppState()

    with Session(test_engine) as session:
        # Create an active scan with */5 * * * *
        scan = Scan(
            name="Periodic Scan",
            cron_expression="*/5 * * * *",
            ports_json=[80],
            flags_json={}
        )
        session.add(scan)
        tg = TargetGroup(name="TG1", targets_json=["10.0.0.1"])
        session.add(tg)
        session.commit()

        link = ScanTargetGroupLink(scan_id=scan.id, target_group_id=tg.id)
        session.add(link)

        # Pretend a run occurred 6 minutes ago
        past_time = datetime.now(timezone.utc) - timedelta(minutes=6)
        old_run = ScanRun(
            scan_id=scan.id,
            execution_config_snapshot_json={},
            status=ScanRunStatus.COMPLETED,
            started_at=past_time,
            finished_at=past_time + timedelta(seconds=2)
        )
        session.add(old_run)
        session.commit()

    # Run check_and_run_scheduled_scans
    await check_and_run_scheduled_scans(app_state)

    # Verify a new run was created and triggered
    assert len(called_runs) == 1
    new_run_id = called_runs[0]

    with Session(test_engine) as session:
        new_run = session.get(ScanRun, new_run_id)
        assert new_run is not None
        assert new_run.scan_id == scan.id
        assert new_run.status == ScanRunStatus.PENDING
        assert new_run.started_at is not None
