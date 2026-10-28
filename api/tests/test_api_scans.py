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

def test_create_and_get_scan(client: TestClient):
    payload = {
        "name": "Test Scan",
        "cron_expression": "0 0 * * *",
        "targets": ["example.com"],
        "ports": [80, 443],
        "flags": {"check_http": True, "timeout": 30}
    }
    
    post_resp = client.post("/api/scans", json=payload)
    assert post_resp.status_code == 201
    post_data = post_resp.json()
    assert "id" in post_data
    scan_id = post_data["id"]
    
    get_resp = client.get("/api/scans")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    
    # Assert our created scan is in the list
    scan = next((s for s in get_data if s["id"] == scan_id), None)
    assert scan is not None
    assert scan["name"] == payload["name"]
    assert scan["cron_expression"] == payload["cron_expression"]
    assert scan["next_run"] is not None

def test_create_scan_legacy_flags_ignored(client: TestClient):
    scan_request = {
        "name": "Legacy Flags Scan",
        "targets": ["example.com"],
        "ports": [80],
        "flags": {
            "check_tcp": False,
            "delay": 5,
            "spoof_user_agent": True,
            "expected": ["foo"],
            "undesired": ["bar"],
            "rate": 10.0
        }
    }
    
    post_resp = client.post("/api/scans", json=scan_request)
    assert post_resp.status_code == 201
    post_data = post_resp.json()
    
    # We should see the new rate flag kept, but others ignored if we were to return them, 
    # but the API typically just accepts them gracefully.
    assert "id" in post_data

def test_update_scan(client: TestClient):
    payload = {
        "name": "Scan To Update",
        "targets": ["old.com"],
        "ports": [80],
        "flags": {}
    }
    post_resp = client.post("/api/scans", json=payload)
    scan_id = post_resp.json()["id"]
    
    put_payload = {
        "name": "Updated Scan",
        "targets": ["new.com"],
        "ports": [443],
        "flags": {}
    }
    
    put_resp = client.put(f"/api/scans/{scan_id}", json=put_payload)
    assert put_resp.status_code == 200
    put_data = put_resp.json()
    assert put_data["name"] == "Updated Scan"
    assert put_data["targets"] == ["new.com"]
    assert put_data["ports"] == [443]

def test_update_scan_not_found(client: TestClient):
    put_payload = {
        "name": "Updated Scan",
        "targets": ["new.com"],
        "ports": [443],
        "flags": {}
    }
    put_resp = client.put("/api/scans/not-a-uuid", json=put_payload)
    assert put_resp.status_code == 404

def test_delete_scan(client: TestClient):
    payload = {
        "name": "Scan To Delete",
        "targets": ["delete.com"],
        "ports": [80],
        "flags": {}
    }
    post_resp = client.post("/api/scans", json=payload)
    scan_id = post_resp.json()["id"]
    
    del_resp = client.delete(f"/api/scans/{scan_id}")
    assert del_resp.status_code == 204
    
    get_resp = client.get("/api/scans")
    get_data = get_resp.json()
    assert not any(s["id"] == scan_id for s in get_data)

def test_delete_scan_not_found(client: TestClient):
    del_resp = client.delete("/api/scans/not-a-uuid")
    assert del_resp.status_code == 404


def test_patch_scan_idempotent_controls(client: TestClient):
    # Create scan
    post_resp = client.post(
        "/api/scans",
        json={
            "name": "Scan To Patch",
            "cron_expression": "0 * * * *",
            "targets": ["patch.com"],
            "ports": [80],
            "alerts_muted": False,
        },
    )
    assert post_resp.status_code == 201
    scan_id = post_resp.json()["id"]

    # 1. Patch alerts_muted to True
    patch1 = client.patch(f"/api/scans/{scan_id}", json={"alerts_muted": True})
    assert patch1.status_code == 200
    assert patch1.json()["alerts_muted"] is True
    assert patch1.json()["name"] == "Scan To Patch"

    # 2. Patch alerts_muted back to False (idempotent)
    patch2 = client.patch(f"/api/scans/{scan_id}", json={"alerts_muted": False})
    assert patch2.status_code == 200
    assert patch2.json()["alerts_muted"] is False

    # 3. Patch name and is_active
    patch3 = client.patch(f"/api/scans/{scan_id}", json={"name": "Renamed Scan", "is_active": False})
    assert patch3.status_code == 200
    assert patch3.json()["name"] == "Renamed Scan"
    assert patch3.json()["is_active"] is False

    # 4. Non-existent scan returns 404
    patch_404 = client.patch("/api/scans/non-existent-id", json={"alerts_muted": True})
    assert patch_404.status_code == 404

    # 5. Verify HTML GET mute and unmute are removed (return 404 or 405)
    get_mute = client.get(f"/api/scans/{scan_id}/alerts/mute")
    assert get_mute.status_code in (404, 405)
    get_unmute = client.get(f"/api/scans/{scan_id}/alerts/unmute")
    assert get_unmute.status_code in (404, 405)


def test_scan_cron_expression_validation(client: TestClient):
    base_payload = {
        "name": "Cron Validation Scan",
        "targets": ["example.com"],
        "ports": [80, 443],
        "flags": {},
    }

    # Invalid cron expressions must return 422
    for bad_cron in ["daily", "* * *", "invalid", "0 0 * * * *", "60 25 * * *"]:
        resp = client.post("/api/scans", json={**base_payload, "cron_expression": bad_cron})
        assert resp.status_code == 422, f"Expected 422 for cron '{bad_cron}', got {resp.status_code}"
        assert "cron" in resp.text.lower()

    # Valid 5-field cron expressions succeed and strip whitespace
    resp_valid = client.post(
        "/api/scans", json={**base_payload, "cron_expression": "  */15 * * * *  "}
    )
    assert resp_valid.status_code == 201
    scan_data = resp_valid.json()
    assert scan_data["cron_expression"] == "*/15 * * * *"
    scan_id = scan_data["id"]

    # Empty or whitespace cron_expression coerces to None
    resp_empty_cron = client.patch(f"/api/scans/{scan_id}", json={"cron_expression": "   "})
    assert resp_empty_cron.status_code == 200
    assert resp_empty_cron.json()["cron_expression"] is None

    # Invalid cron on PATCH and PUT must return 422
    resp_bad_patch = client.patch(f"/api/scans/{scan_id}", json={"cron_expression": "bad-cron"})
    assert resp_bad_patch.status_code == 422

    resp_bad_put = client.put(
        f"/api/scans/{scan_id}", json={**base_payload, "cron_expression": "bad-cron"}
    )
    assert resp_bad_put.status_code == 422


def test_scan_name_and_non_empty_targets_ports_validation(client: TestClient):
    # Empty name returns 422
    resp_empty_name = client.post(
        "/api/scans",
        json={"name": "   ", "targets": ["example.com"], "ports": [80]},
    )
    assert resp_empty_name.status_code == 422

    # Empty targets on schedule creation returns 422
    resp_empty_targets = client.post(
        "/api/scans",
        json={"name": "Valid Name", "targets": [], "ports": [80]},
    )
    assert resp_empty_targets.status_code == 422

    # Empty ports on schedule creation returns 422
    resp_empty_ports = client.post(
        "/api/scans",
        json={"name": "Valid Name", "targets": ["example.com"], "ports": []},
    )
    assert resp_empty_ports.status_code == 422


def test_target_sanitization_and_validation(client: TestClient):
    # Schemes and domain paths are auto-cleaned; CIDR and IP ranges preserved
    resp = client.post(
        "/api/scans",
        json={
            "name": "Target Clean Scan",
            "targets": [
                "  https://example.com/login/path  ",
                "http://sub.domain.org/",
                "192.168.1.0/24",
                "10.0.0.1-10.0.0.50",
            ],
            "ports": [80, 443],
        },
    )
    assert resp.status_code == 201
    assert resp.json()["targets"] == [
        "example.com",
        "sub.domain.org",
        "192.168.1.0/24",
        "10.0.0.1-10.0.0.50",
    ]

    # Invalid targets are rejected with 422
    for bad_target in ["999.999.999.999", "example.com:8080", "not_a_valid_target"]:
        bad_resp = client.post(
            "/api/scans",
            json={"name": "Bad Target", "targets": [bad_target], "ports": [80]},
        )
        assert bad_resp.status_code == 422, f"Expected 422 for target '{bad_target}'"


def test_port_sanitization_and_validation(client: TestClient):
    # Numeric strings normalized to int and hyphenated ranges preserved on POST, PUT, PATCH
    resp = client.post(
        "/api/scans",
        json={
            "name": "Port Range Scan",
            "targets": ["example.com"],
            "ports": [80, "443", "8080-8090"],
        },
    )
    assert resp.status_code == 201
    scan_id = resp.json()["id"]
    assert resp.json()["ports"] == [80, 443, "8080-8090"]

    patch_resp = client.patch(
        f"/api/scans/{scan_id}",
        json={"ports": ["8443", "9000-9005"]},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["ports"] == [8443, "9000-9005"]

    # Invalid ports return 422 without SystemExit
    for bad_ports in [[0], [70000], ["abc"], ["9000-8000"], ["100-70000"]]:
        bad_resp = client.post(
            "/api/scans",
            json={"name": "Bad Port", "targets": ["example.com"], "ports": bad_ports},
        )
        assert bad_resp.status_code == 422, f"Expected 422 for ports {bad_ports}"


def test_settings_and_webhook_validation(client: TestClient):
    base = {"name": "Settings Scan", "targets": ["example.com"], "ports": [80]}

    # Invalid ghost_window
    for bad_gw in ["7days", "-5m", "abc", ""]:
        r = client.post("/api/scans", json={**base, "ghost_window": bad_gw})
        assert r.status_code == 422

    # Negative tls_warning_days
    r_tls = client.post("/api/scans", json={**base, "tls_warning_days": -1})
    assert r_tls.status_code == 422

    # Empty webhook_url coerces to None
    r_empty_wh = client.post(
        "/api/scans",
        json={**base, "alert_config": {"webhook_url": "   "}},
    )
    assert r_empty_wh.status_code == 201
    assert r_empty_wh.json()["alert_config"]["webhook_url"] is None

    # Invalid webhook_url returns 422
    r_bad_wh = client.post(
        "/api/scans",
        json={**base, "alert_config": {"webhook_url": "not-a-url"}},
    )
    assert r_bad_wh.status_code == 422


def test_void_pruning_settings_persistence_and_response(client: TestClient):
    # Default is True
    resp_default = client.post(
        "/api/scans",
        json={"name": "Default Prune Scan", "targets": ["example.com"], "ports": [80]},
    )
    assert resp_default.status_code == 201
    data_default = resp_default.json()
    assert data_default["prune_void_hosts"] is True
    assert data_default["prune_closed_ports"] is True
    scan_id = data_default["id"]

    # Explicitly disabling void pruning persists to database and is returned
    resp_false = client.post(
        "/api/scans",
        json={
            "name": "No Prune Scan",
            "targets": ["example.com"],
            "ports": [80],
            "prune_void_hosts": False,
            "prune_closed_ports": False,
        },
    )
    assert resp_false.status_code == 201
    data_false = resp_false.json()
    assert data_false["prune_void_hosts"] is False
    assert data_false["prune_closed_ports"] is False
    no_prune_id = data_false["id"]

    # Verify GET /api/scans returns persisted values
    resp_list = client.get("/api/scans")
    assert resp_list.status_code == 200
    scans_by_id = {s["id"]: s for s in resp_list.json()}
    assert scans_by_id[no_prune_id]["prune_void_hosts"] is False
    assert scans_by_id[no_prune_id]["prune_closed_ports"] is False

    # PATCH updates void pruning flags
    patch_resp = client.patch(
        f"/api/scans/{no_prune_id}",
        json={"prune_void_hosts": True},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["prune_void_hosts"] is True
    assert patch_resp.json()["prune_closed_ports"] is False

    # PUT updates both flags
    put_resp = client.put(
        f"/api/scans/{scan_id}",
        json={
            "name": "Updated Prune Scan",
            "targets": ["example.com"],
            "ports": [443],
            "prune_void_hosts": False,
            "prune_closed_ports": True,
        },
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["prune_void_hosts"] is False
    assert put_resp.json()["prune_closed_ports"] is True

