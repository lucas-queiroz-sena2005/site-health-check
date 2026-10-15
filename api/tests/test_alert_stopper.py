from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from api.database import get_session
from api.main import app
from api.models import AlertConfig, Scan, ScanRun, ScanRunStatus
from api.services.alerts import evaluate_and_dispatch_alert


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


def test_scan_model_alerts_muted_default_and_persistence(session: Session):
    scan = Scan(
        name="Test Scan",
        cron_expression="0 * * * *",
        ports_json=[80, 443],
        flags_json={},
    )
    session.add(scan)
    session.commit()
    session.refresh(scan)

    assert hasattr(scan, "alerts_muted")
    assert scan.alerts_muted is False

    scan.alerts_muted = True
    session.add(scan)
    session.commit()
    session.refresh(scan)
    assert scan.alerts_muted is True


@pytest.mark.asyncio
async def test_evaluate_and_dispatch_alert_respects_alerts_muted(session: Session):
    alert_cfg = AlertConfig(
        webhook_url="https://chat.googleapis.com/test",
        alert_on_failure=True,
    )
    scan = Scan(
        name="Muted Scan",
        cron_expression="0 * * * *",
        ports_json=[80],
        flags_json={},
        alert_config_json=alert_cfg.model_dump(),
        alerts_muted=True,
    )
    session.add(scan)
    session.commit()
    session.refresh(scan)

    run = ScanRun(
        scan_id=scan.id,
        status=ScanRunStatus.COMPLETED,
        execution_config_snapshot_json={},
        metrics_json={"summary": {"active": 0, "warning": 0, "failed": 2, "ghost": 0, "void": 0}},
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    with patch("api.services.alerts.dispatch_webhook", new_callable=AsyncMock) as mock_dispatch:
        mock_dispatch.return_value = (True, None)
        await evaluate_and_dispatch_alert(run.id, session)
        mock_dispatch.assert_not_called()


def test_idempotent_mute_and_unmute_api(client: TestClient, session: Session):
    scan = Scan(
        name="API Scan",
        cron_expression="0 * * * *",
        ports_json=[80],
        flags_json={},
        alerts_muted=False,
    )
    session.add(scan)
    session.commit()
    session.refresh(scan)

    # 1. First mute call
    resp1 = client.post(f"/api/scans/{scan.id}/alerts/mute")
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["alerts_muted"] is True

    # 2. Repeated mute call (idempotency check: MUST NOT invert)
    resp2 = client.post(f"/api/scans/{scan.id}/alerts/mute")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["alerts_muted"] is True

    # 3. Unmute call
    resp3 = client.post(f"/api/scans/{scan.id}/alerts/unmute")
    assert resp3.status_code == 200
    data3 = resp3.json()
    assert data3["alerts_muted"] is False

    # 4. Repeated unmute call (idempotency check)
    resp4 = client.post(f"/api/scans/{scan.id}/alerts/unmute")
    assert resp4.status_code == 200
    data4 = resp4.json()
    assert data4["alerts_muted"] is False


def test_get_web_action_mute_and_unmute_endpoints(client: TestClient, session: Session):
    scan = Scan(
        name="Web Action Scan",
        cron_expression="0 * * * *",
        ports_json=[80],
        flags_json={},
        alerts_muted=False,
    )
    session.add(scan)
    session.commit()
    session.refresh(scan)

    # GET action for single-click chat navigation without SPA loading
    resp_mute = client.get(f"/api/scans/{scan.id}/alerts/mute")
    assert resp_mute.status_code == 200
    assert "text/html" in resp_mute.headers.get("content-type", "")
    assert "muted" in resp_mute.text.lower() or "turned off" in resp_mute.text.lower()

    session.refresh(scan)
    assert scan.alerts_muted is True

    resp_unmute = client.get(f"/api/scans/{scan.id}/alerts/unmute")
    assert resp_unmute.status_code == 200
    assert "text/html" in resp_unmute.headers.get("content-type", "")
    assert "active" in resp_unmute.text.lower() or "resumed" in resp_unmute.text.lower() or "turned on" in resp_unmute.text.lower()

    session.refresh(scan)
    assert scan.alerts_muted is False


def test_build_google_chat_card_includes_mute_action():
    from api.services.alerts import build_google_chat_card

    payload = build_google_chat_card(
        schedule_name="Gitlab",
        run_id="run-1234",
        timestamp_str="now",
        triggers=[],
        summary_stats={"active": 1, "warning": 0, "failed": 0, "ghost": 0, "void": 0},
        table_url="http://localhost:8080/?run=run-1234",
        is_healthy=True,
        mute_url="http://localhost:8080/api/scans/scan-123/alerts/mute",
    )
    card = payload["cardsV2"][0]["card"]
    text = card["sections"][0]["widgets"][0]["textParagraph"]["text"]
    assert "View Results Table" in text
    assert "Turn Off Alerts" in text
    assert "http://localhost:8080/api/scans/scan-123/alerts/mute" in text


def test_build_slack_blocks_includes_mute_action():
    from api.services.alerts import build_slack_blocks

    payload = build_slack_blocks(
        schedule_name="Gitlab",
        run_id="run-1234",
        timestamp_str="now",
        triggers=[],
        summary_stats={"active": 1, "warning": 0, "failed": 0, "ghost": 0, "void": 0},
        table_url="http://localhost:8080/?run=run-1234",
        is_healthy=True,
        mute_url="http://localhost:8080/api/scans/scan-123/alerts/mute",
    )
    blocks = payload["blocks"]
    action_block = next(b for b in blocks if b["type"] == "actions")
    urls = [el["url"] for el in action_block["elements"]]
    assert "http://localhost:8080/api/scans/scan-123/alerts/mute" in urls


def test_build_mute_status_payload():
    from api.services.alerts import build_mute_status_payload

    # Muted payload
    p_muted = build_mute_status_payload(
        webhook_url="https://chat.googleapis.com/test",
        schedule_name="Production Scan",
        is_muted=True,
        unmute_url="http://localhost:8080/api/scans/scan-1/alerts/unmute",
    )
    assert "cardsV2" in p_muted
    card_muted = p_muted["cardsV2"][0]["card"]
    assert "Alerts Muted" in card_muted["header"]["title"]
    assert "Turn Back On" in card_muted["sections"][0]["widgets"][0]["textParagraph"]["text"]

    # Resumed payload
    p_resumed = build_mute_status_payload(
        webhook_url="https://chat.googleapis.com/test",
        schedule_name="Production Scan",
        is_muted=False,
        mute_url="http://localhost:8080/api/scans/scan-1/alerts/mute",
    )
    card_resumed = p_resumed["cardsV2"][0]["card"]
    assert "Alerts Active" in card_resumed["header"]["title"]


@pytest.mark.asyncio
async def test_dispatch_mute_status_notification():
    from api.services.alerts import dispatch_mute_status_notification

    scan = Scan(
        id="scan-xyz",
        name="Critical Service",
        cron_expression="0 * * * *",
        ports_json=[80],
        flags_json={},
        alert_config_json={"webhook_url": "https://chat.googleapis.com/test"},
        alerts_muted=True,
    )

    with patch("api.services.alerts.dispatch_webhook", new_callable=AsyncMock) as mock_dispatch:
        mock_dispatch.return_value = (True, None)
        success = await dispatch_mute_status_notification(scan, is_muted=True)
        assert success is True
        mock_dispatch.assert_called_once()
        args, kwargs = mock_dispatch.call_args
        assert "https://chat.googleapis.com/test" in args
        assert "cardsV2" in args[1]

