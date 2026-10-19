from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from api.database import get_session
from api.main import app
from api.models import AlertConfig, Scan, ScanRun, ScanRunStatus
from api.services.alerts import (
    build_alert_payload,
    build_google_chat_card,
    build_slack_blocks,
    dispatch_webhook,
    evaluate_alert_triggers,
)


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


def test_build_google_chat_card_http():
    summary = {"active": 10, "warning": 1, "failed": 2, "ghost": 1, "void": 240}
    card_payload = build_google_chat_card(
        schedule_name="Production Core Subnet",
        run_id="run-12345",
        timestamp_str="2026-10-14 18:00:00 UTC",
        triggers=["2 Service Failures", "1 Ghost Host"],
        summary_stats=summary,
        table_url="http://localhost:8080/?run=run-12345",
        is_healthy=False,
    )

    assert "cardsV2" in card_payload
    card = card_payload["cardsV2"][0]["card"]
    assert card["header"]["title"] == "Scan: Issues Detected"
    assert card["header"]["subtitle"] == "Production Core Subnet | Run: run-1234"

    # Single section with uniform textParagraph and direct hyperlink (no dead button on HTTP)
    assert len(card["sections"]) == 1
    widgets = card["sections"][0]["widgets"]
    assert len(widgets) == 1
    text = widgets[0]["textParagraph"]["text"]
    assert "Issues Detected" in text
    assert "Active: 10 | Warning: 1 | Failed: 2 | Ghost: 1" in text
    assert "<a href='http://localhost:8080/?run=run-12345'>View Results Table</a>" in text
    assert "buttonList" not in widgets[0]


def test_build_google_chat_card_https():
    summary = {"active": 5, "warning": 0, "failed": 0, "ghost": 0, "void": 0}
    card_payload = build_google_chat_card(
        schedule_name="Daily Health Check",
        run_id="run-999",
        timestamp_str="2026-10-14 18:00:00 UTC",
        triggers=[],
        summary_stats=summary,
        table_url="https://health.example.com/?run=run-999",
        is_healthy=True,
    )

    card = card_payload["cardsV2"][0]["card"]
    assert card["header"]["title"] == "Scan: Healthy"
    assert card["header"]["subtitle"] == "Daily Health Check | Run: run-999"

    widgets = card["sections"][0]["widgets"]
    assert len(widgets) == 2
    button_widget = widgets[1]
    assert "buttonList" in button_widget
    assert (
        button_widget["buttonList"]["buttons"][0]["onClick"]["openLink"]["url"]
        == "https://health.example.com/?run=run-999"
    )


def test_build_slack_blocks():
    summary = {"active": 5, "warning": 0, "failed": 0, "ghost": 0, "void": 0}
    slack_payload = build_slack_blocks(
        schedule_name="Daily Health Check",
        run_id="run-999",
        timestamp_str="2026-10-14 18:00:00 UTC",
        triggers=[],
        summary_stats=summary,
        table_url="http://localhost:8080/?run=run-999",
        is_healthy=True,
    )

    assert "blocks" in slack_payload
    blocks = slack_payload["blocks"]
    assert blocks[0]["type"] == "header"
    assert blocks[0]["text"]["text"] == "Scan: Healthy"

    # Action button
    action_block = next(b for b in blocks if b["type"] == "actions")
    btn = action_block["elements"][0]
    assert btn["url"] == "http://localhost:8080/?run=run-999"


def test_build_alert_payload_auto_detection():
    summary = {"active": 1, "warning": 0, "failed": 0, "ghost": 0, "void": 0}

    # Google Chat
    gchat_url = "https://chat.googleapis.com/v1/spaces/XYZ/messages"
    p_gchat = build_alert_payload(
        webhook_url=gchat_url,
        schedule_name="Test",
        run_id="1",
        timestamp_str="now",
        triggers=["ok"],
        summary_stats=summary,
        table_url="http://localhost:5173",
        is_healthy=True,
    )
    assert "cardsV2" in p_gchat

    # Slack
    slack_url = "https://hooks.slack.com/services/T1/B2/K3"
    p_slack = build_alert_payload(
        webhook_url=slack_url,
        schedule_name="Test",
        run_id="1",
        timestamp_str="now",
        triggers=["ok"],
        summary_stats=summary,
        table_url="http://localhost:5173",
        is_healthy=True,
    )
    assert "blocks" in p_slack

    # Generic Fallback
    generic_url = "https://example.com/webhook"
    p_generic = build_alert_payload(
        webhook_url=generic_url,
        schedule_name="Test",
        run_id="1",
        timestamp_str="now",
        triggers=["ok"],
        summary_stats=summary,
        table_url="http://localhost:5173",
        is_healthy=True,
    )
    assert "text" in p_generic
    assert "summary" in p_generic


def test_evaluate_alert_triggers():
    alert_cfg = AlertConfig(
        webhook_url="https://chat.googleapis.com/test",
        alert_on_failure=True,
        alert_on_ghost=True,
        alert_on_warning=True,
        alert_on_abort=True,
        notify_on_healthy=False,
    )
    scan = Scan(
        name="Evaluated Scan",
        cron_expression="0 * * * *",
        ports_json=[80],
        flags_json={},
        alert_config_json=alert_cfg.model_dump(),
    )
    run = ScanRun(
        id="run-1",
        status=ScanRunStatus.COMPLETED,
        execution_config_snapshot_json={},
    )

    # 1. Failure trigger
    should_send, triggers, is_healthy = evaluate_alert_triggers(
        alert_config=alert_cfg,
        run_status=run.status,
        summary_stats={"active": 1, "warning": 0, "failed": 2, "ghost": 0, "void": 0},
    )
    assert should_send is True
    assert is_healthy is False
    assert any("Failure" in t for t in triggers)

    # 2. Ghost trigger
    should_send, triggers, is_healthy = evaluate_alert_triggers(
        alert_config=alert_cfg,
        run_status=run.status,
        summary_stats={"active": 1, "warning": 0, "failed": 0, "ghost": 1, "void": 0},
    )
    assert should_send is True
    assert is_healthy is False
    assert any("Ghost" in t for t in triggers)

    # 3. Healthy run with notify_on_healthy=False -> should NOT send
    should_send, triggers, is_healthy = evaluate_alert_triggers(
        alert_config=alert_cfg,
        run_status=run.status,
        summary_stats={"active": 5, "warning": 0, "failed": 0, "ghost": 0, "void": 10},
    )
    assert should_send is False

    # 4. Healthy run with notify_on_healthy=True -> should send
    alert_cfg.notify_on_healthy = True
    should_send, triggers, is_healthy = evaluate_alert_triggers(
        alert_config=alert_cfg,
        run_status=run.status,
        summary_stats={"active": 5, "warning": 0, "failed": 0, "ghost": 0, "void": 10},
    )
    assert should_send is True
    assert is_healthy is True


def test_api_test_webhook_endpoint(client: TestClient):
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.is_success = True
        mock_post.return_value = mock_resp

        # Valid Google Chat test
        resp = client.post(
            "/api/alerts/test",
            json={"webhook_url": "https://chat.googleapis.com/v1/spaces/AAA/messages"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

        mock_post.assert_called_once()


def test_api_test_webhook_failure(client: TestClient):
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 404
        mock_resp.is_success = False
        mock_resp.text = "Space not found"
        mock_post.return_value = mock_resp

        resp = client.post(
            "/api/alerts/test",
            json={"webhook_url": "https://chat.googleapis.com/v1/spaces/INVALID/messages"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "404" in data["error"] or "Space not found" in data["error"]


def test_compute_run_summary_with_real_models(session: Session):
    from api.models import HostState, HttpRoutingCheck, PortState, Scan, ScanRun, ScanRunStatus, TlsCertificate
    from api.services.alerts import compute_run_summary, evaluate_and_dispatch_alert

    scan = Scan(
        name="Nightly Scan",
        cron_expression="0 0 * * *",
        ports_json=[80, 443],
        flags_json={},
        alert_config_json={
            "webhook_url": "https://chat.googleapis.com/test",
            "alert_on_failure": True,
            "alert_on_warning": True,
        },
    )
    session.add(scan)
    session.commit()
    session.refresh(scan)

    run = ScanRun(
        scan_id=scan.id,
        status=ScanRunStatus.COMPLETED,
        execution_config_snapshot_json={"ghost_window": "7d", "tls_warning_days": 30},
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    # 1. Active Host (port 80 open)
    host1 = HostState(scan_run_id=run.id, ip_address="10.0.0.1")
    session.add(host1)
    session.flush()
    p1 = PortState(host_state_id=host1.id, port_number=80, tcp_status="open")
    session.add(p1)

    # 2. Host with warning (TLS expiring in 10 days <= 30)
    host2 = HostState(scan_run_id=run.id, ip_address="10.0.0.2")
    session.add(host2)
    session.flush()
    p2 = PortState(host_state_id=host2.id, port_number=443, tcp_status="open")
    session.add(p2)
    session.flush()
    tls = TlsCertificate(port_state_id=p2.id, valid=True, expires_in_days=10)
    session.add(tls)

    # 3. Host with failure (HTTP 500)
    host3 = HostState(scan_run_id=run.id, ip_address="10.0.0.3")
    session.add(host3)
    session.flush()
    p3 = PortState(host_state_id=host3.id, port_number=80, tcp_status="open")
    session.add(p3)
    session.flush()
    http_check = HttpRoutingCheck(port_state_id=p3.id, domain="example.com", status_code=500)
    session.add(http_check)

    session.commit()

    # Compute summary directly using database ORM objects
    summary = compute_run_summary(
        session=session,
        run=run,
        ghost_window_str="7d",
        tls_warning_days=30,
    )
    assert summary["active"] == 1
    assert summary["warning"] == 1
    assert summary["failed"] == 1
    assert summary["ghost"] == 0


def test_compute_run_summary_counts_void_hosts(session: Session):
    from api.models import HostState, PortState, ScanRun, ScanRunStatus
    from api.services.alerts import compute_run_summary

    run = ScanRun(
        status=ScanRunStatus.COMPLETED,
        execution_config_snapshot_json={"ghost_window": "7d", "tls_warning_days": 30},
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    # Add 1 active host and 1 synthetic void host
    h_active = HostState(scan_run_id=run.id, ip_address="10.0.0.1")
    session.add(h_active)
    session.flush()
    session.add(PortState(host_state_id=h_active.id, port_number=80, tcp_status="open"))

    h_void = HostState(
        scan_run_id=run.id,
        ip_address="Void (255)",
        metadata_resolved_from="10.0.0.0/24",
        metadata_discovered_from_json=["void_aggregated"],
    )
    session.add(h_void)
    session.commit()

    summary = compute_run_summary(session=session, run=run)
    assert summary["active"] == 1
    assert summary["void"] == 255


def test_get_results_summary_returns_persisted_summary(client: TestClient, session: Session):
    from api.models import HostState, PortState, ScanRun, ScanRunStatus

    run = ScanRun(
        status=ScanRunStatus.COMPLETED,
        execution_config_snapshot_json={"ghost_window": "7d", "tls_warning_days": 30},
        metrics_json={
            "summary": {"active": 4, "warning": 1, "failed": 0, "ghost": 1, "void": 20}
        },
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    resp = client.get(f"/api/results/summary?run_id={run.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == run.id
    assert data["summary"] == {"active": 4, "warning": 1, "failed": 0, "ghost": 1, "void": 20}

