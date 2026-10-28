import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from api.models import Scan, ScanRun, ScanRunStatus
from api.services.scheduler import check_and_run_scheduled_scans
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool


from api.services.run_manager import RunManager


class DummyAppState:
    def __init__(self):
        self.run_manager = RunManager()

@pytest.mark.asyncio
async def test_scheduler_triggers_due_scan(monkeypatch, no_engine_subprocess):
    test_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(test_engine)
    monkeypatch.setattr("api.services.scheduler.engine", test_engine)

    app_state = DummyAppState()

    with Session(test_engine) as session:
        # Create an active scan with */5 * * * *
        scan = Scan(
            name="Periodic Scan",
            cron_expression="*/5 * * * *",
            targets=["10.0.0.1"],
            ports_json=[80],
            flags_json={}
        )
        session.add(scan)
        session.commit()

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
        scan_id = scan.id

    # Run check_and_run_scheduled_scans
    await check_and_run_scheduled_scans(app_state)
    await asyncio.sleep(0)  # let the create_task()'d run start

    # Verify a new run was created and triggered
    assert len(no_engine_subprocess) == 1
    new_run_id = no_engine_subprocess[0]

    with Session(test_engine) as session:
        new_run = session.get(ScanRun, new_run_id)
        assert new_run is not None
        assert new_run.scan_id == scan_id
        assert new_run.status == ScanRunStatus.PENDING
        assert new_run.started_at is not None


@pytest.mark.asyncio
async def test_scheduler_dispatches_via_run_manager(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    from api.services.run_manager import RunManager

    test_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(test_engine)
    monkeypatch.setattr("api.services.scheduler.engine", test_engine)

    app_state = MagicMock()
    app_state.run_manager = MagicMock(spec=RunManager)
    app_state.run_manager.dispatch_run = AsyncMock()

    with Session(test_engine) as session:
        scan = Scan(
            name="Production Periodic",
            cron_expression="* * * * *",
            targets=["10.0.0.2"],
            ports_json=[443],
            flags_json={}
        )
        session.add(scan)
        session.commit()
        scan_id = scan.id

    await check_and_run_scheduled_scans(app_state)
    await asyncio.sleep(0)

    assert app_state.run_manager.dispatch_run.called
    args, kwargs = app_state.run_manager.dispatch_run.call_args
    assert kwargs.get("scan_id") == scan_id or (len(args) >= 3 and args[2] == scan_id)



def test_settings_timezone_resolution(monkeypatch):
    from zoneinfo import ZoneInfo
    from api.config import Settings

    # Default is UTC
    s = Settings(timezone="UTC")
    assert s.get_tz() == ZoneInfo("UTC")

    # Valid custom timezone
    s_sp = Settings(timezone="America/Sao_Paulo")
    assert s_sp.get_tz() == ZoneInfo("America/Sao_Paulo")

    # Fallback to UTC on invalid timezone
    s_invalid = Settings(timezone="NonExistent/InvalidZone")
    assert s_invalid.get_tz() == ZoneInfo("UTC")


@pytest.mark.asyncio
async def test_scheduler_respects_custom_timezone(monkeypatch, no_engine_subprocess):
    from zoneinfo import ZoneInfo
    test_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(test_engine)
    monkeypatch.setattr("api.services.scheduler.engine", test_engine)
    monkeypatch.setattr("api.services.scheduler.settings.timezone", "America/Sao_Paulo")

    tz = ZoneInfo("America/Sao_Paulo")
    now_local = datetime.now(tz)
    # Cron for current minute in local time
    cron_now = f"{now_local.minute} {now_local.hour} * * *"

    app_state = DummyAppState()

    with Session(test_engine) as session:
        scan = Scan(
            name="Timezone Aware Scan",
            cron_expression=cron_now,
            ports_json=[80],
            flags_json={}
        )
        session.add(scan)
        session.commit()

    await check_and_run_scheduled_scans(app_state)
    await asyncio.sleep(0)

    assert len(no_engine_subprocess) == 1


@pytest.mark.asyncio
async def test_scheduler_handles_malformed_cron_gracefully(monkeypatch):
    from unittest.mock import MagicMock

    test_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(test_engine)
    monkeypatch.setattr("api.services.scheduler.engine", test_engine)

    mock_logger = MagicMock()
    monkeypatch.setattr("api.services.scheduler.logger", mock_logger)

    app_state = DummyAppState()

    with Session(test_engine) as session:
        scan = Scan(
            name="Corrupted Cron Scan",
            cron_expression="not a valid cron",
            targets=["10.0.0.1"],
            ports_json=[80],
            flags_json={},
        )
        session.add(scan)
        session.commit()

    await check_and_run_scheduled_scans(app_state)

    # Should log a warning, NOT logger.exception
    assert mock_logger.warning.called
    assert not mock_logger.exception.called


