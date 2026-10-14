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


def test_build_google_chat_card():
    summary = {"active": 10, "warning": 1, "failed": 2, "ghost": 1, "void": 240}
    card_payload = build_google_chat_card(
        schedule_name="Production Core Subnet",
        run_id="run-12345",
        timestamp_str="2026-10-14 18:00:00 UTC",
        triggers=["2 Service Failures", "1 Ghost Host"],
        summary_stats=summary,
        table_url="http://localhost:5173/#/?run_id=run-12345",
        is_healthy=False,
    )

    assert "cardsV2" in card_payload
    card = card_payload["cardsV2"][0]["card"]
    assert "🔴 Alert" in card["header"]["title"]
    assert "Production Core Subnet" in card["header"]["subtitle"]

    # Verify widgets
    widgets = card["sections"][0]["widgets"]
    labels = [w.get("decoratedText", {}).get("topLabel") for w in widgets if "decoratedText" in w]
    assert "Schedule" in labels
    assert "Run ID" in labels
    assert "Trigger" in labels
    assert "Summary" in labels

    # Verify button link
    button_widget = next(w for w in widgets if "buttonList" in w)
    button = button_widget["buttonList"]["buttons"][0]
    assert button["onClick"]["openLink"]["url"] == "http://localhost:5173/#/?run_id=run-12345"


def test_build_slack_blocks():
    summary = {"active": 5, "warning": 0, "failed": 0, "ghost": 0, "void": 0}
    slack_payload = build_slack_blocks(
        schedule_name="Daily Health Check",
        run_id="run-999",
        timestamp_str="2026-10-14 18:00:00 UTC",
        triggers=["All systems operational"],
        summary_stats=summary,
        table_url="http://localhost:5173/#/?run_id=run-999",
        is_healthy=True,
    )

    assert "blocks" in slack_payload
    blocks = slack_payload["blocks"]
    assert blocks[0]["type"] == "header"
    assert "🟢" in blocks[0]["text"]["text"]

    # Action button
    action_block = next(b for b in blocks if b["type"] == "actions")
    btn = action_block["elements"][0]
    assert btn["url"] == "http://localhost:5173/#/?run_id=run-999"


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
