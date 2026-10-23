import uuid
from datetime import UTC, datetime
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from api.database import get_session
from api.main import app
from api.models import (
    HostState,
    HttpRoutingCheck,
    PortState,
    ScanRun,
    ScanRunStatus,
    TlsCertificate,
)


@pytest.fixture(name="session")
def session_fixture():
    test_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session):
    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture(name="populated_run")
def populated_run_fixture(session: Session) -> str:
    """Creates a realistic scan run with multiple hosts, open/closed ports, TLS certs, and HTTP checks."""
    run_id = str(uuid.uuid4())
    run = ScanRun(
        id=run_id,
        status=ScanRunStatus.COMPLETED,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        execution_config_snapshot_json={"ghost_window": "7d", "tls_warning_days": 30},
        metrics_json={
            "summary": {
                "active": 2,
                "warning": 1,
                "failed": 0,
                "ghost": 1,
                "void": 5,
                "service_count": 3,
                "http_check_count": 4,
            }
        },
    )
    session.add(run)

    # Host 1: 10.0.0.1 (Seed, depth 0, OK)
    # Open port 80 (HTTP 200, latency 25ms)
    # Open port 443 (HTTP 200, TLS valid, expires 60 days, Issuer Google, 3 SANs, latency 45ms)
    # Closed port 8080 (routine closed void port, status='ok')
    h1 = HostState(
        id=f"{run_id}_10.0.0.1",
        scan_run_id=run_id,
        ip_address="10.0.0.1",
        ip_sort_key="00000000000000000000ffff0a000001",
        subrun_id="example.com",
        resolved_domains=["example.com", "www.example.com"],
        discovered_from=[],
        depth=0,
        status="ok",
        open_port_count=2,
        scanned_port_count=3,
        vhost_count=2,
        min_tcp_latency_ms=25,
        min_tls_expires_days=60,
        worst_tls_version="TLSv1.3",
        worst_http_status=200,
        finding_codes=[],
    )
    session.add(h1)
    session.flush()

    p1_80 = PortState(
        id=f"{h1.id}_80",
        host_state_id=h1.id,
        port_number=80,
        tcp_status="open",
        tcp_latency_ms=25,
        status="ok",
        san_count=0,
        http_check_count=1,
        worst_http_status=200,
        finding_codes=[],
    )
    p1_443 = PortState(
        id=f"{h1.id}_443",
        host_state_id=h1.id,
        port_number=443,
        tcp_status="open",
        tcp_latency_ms=45,
        status="ok",
        san_count=3,
        http_check_count=2,
        worst_http_status=200,
        finding_codes=[],
    )
    p1_8080 = PortState(
        id=f"{h1.id}_8080",
        host_state_id=h1.id,
        port_number=8080,
        tcp_status="closed",
        status="ok",
        finding_codes=["TCP_CLOSED"],
    )
    session.add_all([p1_80, p1_443, p1_8080])
    session.flush()

    cert1 = TlsCertificate(
        id=f"{p1_443.id}_cert",
        port_state_id=p1_443.id,
        valid=True,
        expires_in_days=60,
        issuer="Google Trust Services",
        protocol_version="TLSv1.3",
        domains_discovered_sans_json=["example.com", "api.example.com", "cdn.example.com"],
    )
    session.add(cert1)

    c1_1 = HttpRoutingCheck(
        id=f"{p1_80.id}_c1",
        port_state_id=p1_80.id,
        domain="example.com",
        status="ok",
        status_code=200,
        http_latency_ms=30,
        server_header="nginx/1.24",
    )
    c1_2 = HttpRoutingCheck(
        id=f"{p1_443.id}_c2",
        port_state_id=p1_443.id,
        domain="example.com",
        status="ok",
        status_code=200,
        http_latency_ms=50,
        server_header="nginx/1.24",
    )
    c1_3 = HttpRoutingCheck(
        id=f"{p1_443.id}_c3",
        port_state_id=p1_443.id,
        domain="www.example.com",
        status="ok",
        status_code=301,
        http_latency_ms=40,
        redirects_to_url="https://example.com/",
    )
    session.add_all([c1_1, c1_2, c1_3])

    # Host 2: 10.0.0.100 (Discovered via SAN, depth 1, WARNING)
    # Open port 443 (HTTP 404, TLS expiring soon: 10 days, Issuer Let's Encrypt, latency 120ms)
    h2 = HostState(
        id=f"{run_id}_10.0.0.100",
        scan_run_id=run_id,
        ip_address="10.0.0.100",
        ip_sort_key="00000000000000000000ffff0a000064",
        subrun_id="example.com",
        resolved_domains=["api.example.com"],
        discovered_from=["example.com"],
        depth=1,
        status="warning",
        open_port_count=1,
        scanned_port_count=1,
        vhost_count=1,
        min_tcp_latency_ms=120,
        min_tls_expires_days=10,
        worst_tls_version="TLSv1.2",
        worst_http_status=404,
        finding_codes=["TLS_EXPIRING_SOON", "HTTP_4XX"],
    )
    session.add(h2)
    session.flush()

    p2_443 = PortState(
        id=f"{h2.id}_443",
        host_state_id=h2.id,
        port_number=443,
        tcp_status="open",
        tcp_latency_ms=120,
        status="warning",
        san_count=1,
        http_check_count=1,
        worst_http_status=404,
        finding_codes=["TLS_EXPIRING_SOON", "HTTP_4XX"],
    )
    session.add(p2_443)
    session.flush()

    cert2 = TlsCertificate(
        id=f"{p2_443.id}_cert",
        port_state_id=p2_443.id,
        valid=True,
        expires_in_days=10,
        issuer="Let's Encrypt",
        protocol_version="TLSv1.2",
        domains_discovered_sans_json=["api.example.com"],
    )
    session.add(cert2)

    c2_1 = HttpRoutingCheck(
        id=f"{p2_443.id}_c1",
        port_state_id=p2_443.id,
        domain="api.example.com",
        status="warning",
        status_code=404,
        http_latency_ms=110,
        finding_code="HTTP_4XX",
        server_header="Cloudflare",
    )
    session.add(c2_1)

    # Host 3: 8.8.8.8 (Seed, depth 0, Ghost host)
    # Port 53 closed (historically active -> ghost port outage)
    h3 = HostState(
        id=f"{run_id}_8.8.8.8",
        scan_run_id=run_id,
        ip_address="8.8.8.8",
        ip_sort_key="00000000000000000000ffff08080808",
        subrun_id="8.8.8.8",
        resolved_domains=["dns.google"],
        discovered_from=[],
        depth=0,
        status="ghost",
        open_port_count=0,
        scanned_port_count=1,
        vhost_count=1,
        min_tcp_latency_ms=None,
        min_tls_expires_days=None,
        worst_tls_version=None,
        worst_http_status=None,
        finding_codes=["HOST_GHOST"],
    )
    session.add(h3)
    session.flush()

    p3_53 = PortState(
        id=f"{h3.id}_53",
        host_state_id=h3.id,
        port_number=53,
        tcp_status="closed",
        status="failed",
        finding_codes=["TCP_CLOSED"],
    )
    session.add(p3_53)
    session.commit()

    return run_id


def test_get_hosts_endpoint_structure_and_pagination(client: TestClient, populated_run: str):
    """GET /api/runs/{id}/hosts returns Page[HostRowDTO] with valid structure and pagination."""
    resp = client.get(f"/api/runs/{populated_run}/hosts?limit=2&offset=0")
    assert resp.status_code == 200
    data = resp.json()

    assert "items" in data
    assert "total" in data
    assert data["total"] == 3
    assert len(data["items"]) == 2
    assert data["limit"] == 2
    assert data["offset"] == 0

    first_item = data["items"][0]
    expected_fields = [
        "ip_address", "status", "depth", "vhost_count", "open_port_count",
        "scanned_port_count", "min_tcp_latency_ms", "min_tls_expires_days",
        "worst_tls_version", "worst_http_status", "finding_codes"
    ]
    for field in expected_fields:
        assert field in first_item, f"Field {field} missing from HostRowDTO"

    # Verify 404 on non-existent run
    missing_resp = client.get("/api/runs/non-existent-run-id/hosts")
    assert missing_resp.status_code == 404


def test_get_hosts_deep_search_and_filters(client: TestClient, populated_run: str):
    """GET /api/runs/{id}/hosts supports deep search across IP, resolved_domains, finding_codes, and status filters."""
    # Search domain name 'api.example.com' - should match 10.0.0.100 even though domain is not in HostRowDTO
    resp_domain = client.get(f"/api/runs/{populated_run}/hosts?q=api.example.com")
    assert resp_domain.status_code == 200
    items = resp_domain.json()["items"]
    assert len(items) == 1
    assert items[0]["ip_address"] == "10.0.0.100"

    # Search IP prefix '10.0.'
    resp_ip = client.get(f"/api/runs/{populated_run}/hosts?q=10.0.")
    assert resp_ip.status_code == 200
    assert len(resp_ip.json()["items"]) == 2

    # Filter by exact finding code 'HOST_GHOST'
    resp_finding = client.get(f"/api/runs/{populated_run}/hosts?finding=HOST_GHOST")
    assert resp_finding.status_code == 200
    finding_items = resp_finding.json()["items"]
    assert len(finding_items) == 1
    assert finding_items[0]["ip_address"] == "8.8.8.8"

    # Multi-status filter 'warning,ghost'
    resp_multi = client.get(f"/api/runs/{populated_run}/hosts?status=warning,ghost")
    assert resp_multi.status_code == 200
    assert len(resp_multi.json()["items"]) == 2


def test_get_hosts_sorting_ip_depth_and_nulls_last(client: TestClient, populated_run: str):
    """GET /api/runs/{id}/hosts sorts numerically by IP via ip_sort_key and respects NULLS LAST on metrics."""
    # Numerical IP sort: 8.8.8.8 < 10.0.0.1 < 10.0.0.100
    resp_asc = client.get(f"/api/runs/{populated_run}/hosts?sort_by=ip_address&sort_dir=asc")
    assert resp_asc.status_code == 200
    ips_asc = [h["ip_address"] for h in resp_asc.json()["items"]]
    assert ips_asc == ["8.8.8.8", "10.0.0.1", "10.0.0.100"]

    # Sort by depth descending: depth 1 (10.0.0.100) first
    resp_depth = client.get(f"/api/runs/{populated_run}/hosts?sort_by=depth&sort_dir=desc")
    assert resp_depth.status_code == 200
    assert resp_depth.json()["items"][0]["ip_address"] == "10.0.0.100"

    # Sort by min_tcp_latency_ms ASC: 25ms (10.0.0.1) -> 120ms (10.0.0.100) -> NULL (8.8.8.8 placed LAST)
    resp_lat = client.get(f"/api/runs/{populated_run}/hosts?sort_by=min_tcp_latency_ms&sort_dir=asc")
    assert resp_lat.status_code == 200
    lat_ips = [h["ip_address"] for h in resp_lat.json()["items"]]
    assert lat_ips == ["10.0.0.1", "10.0.0.100", "8.8.8.8"]


def test_get_services_endpoint_and_filtering(client: TestClient, populated_run: str):
    """GET /api/runs/{id}/services returns Page[ServiceRowDTO] and hides routine closed ports by default."""
    # Default: open ports (80, 443, 443) + ghost port (53) = 4 rows. Routine closed port 8080 is excluded!
    resp = client.get(f"/api/runs/{populated_run}/services")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    items = data["items"]
    # Verify routine closed port 8080 is NOT present by default
    assert not any(s["port"] == 8080 for s in items)

    # When include_closed=true: routine closed port 8080 appears
    resp_all = client.get(f"/api/runs/{populated_run}/services?include_closed=true")
    assert resp_all.status_code == 200
    assert any(s["port"] == 8080 for s in resp_all.json()["items"])

    # Filter by port=443
    resp_443 = client.get(f"/api/runs/{populated_run}/services?port=443")
    assert resp_443.status_code == 200
    assert all(s["port"] == 443 for s in resp_443.json()["items"])

    # Search issuer 'Google'
    resp_issuer = client.get(f"/api/runs/{populated_run}/services?q=Google")
    assert resp_issuer.status_code == 200
    assert len(resp_issuer.json()["items"]) == 1
    assert resp_issuer.json()["items"][0]["tls_issuer"] == "Google Trust Services"


def test_get_checks_endpoint_and_filtering(client: TestClient, populated_run: str):
    """GET /api/runs/{id}/checks returns Page[HttpCheckRowDTO] with domain, status code, and header search."""
    resp = client.get(f"/api/runs/{populated_run}/checks")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert data["total"] == 4
    items = data["items"]

    first_check = items[0]
    expected_fields = [
        "ip_address", "port", "domain", "status", "status_code",
        "http_latency_ms", "redirects_to_url", "server_header", "notes", "finding_code"
    ]
    for field in expected_fields:
        assert field in first_check

    # Search 'Cloudflare' server header
    resp_cf = client.get(f"/api/runs/{populated_run}/checks?q=Cloudflare")
    assert resp_cf.status_code == 200
    assert len(resp_cf.json()["items"]) == 1
    assert resp_cf.json()["items"][0]["domain"] == "api.example.com"

    # Filter status=warning (HTTP 404)
    resp_warn = client.get(f"/api/runs/{populated_run}/checks?status=warning")
    assert resp_warn.status_code == 200
    assert len(resp_warn.json()["items"]) == 1
    assert resp_warn.json()["items"][0]["status_code"] == 404


def test_get_host_detail_drawer_endpoint(client: TestClient, populated_run: str):
    """GET /api/runs/{id}/hosts/{ip} returns HostDetailDTO with lineage, all services, checks, and deduplicated SANs."""
    # Test Host 1 (10.0.0.1)
    resp = client.get(f"/api/runs/{populated_run}/hosts/10.0.0.1")
    assert resp.status_code == 200
    data = resp.json()

    assert data["ip_address"] == "10.0.0.1"
    assert data["status"] == "ok"
    assert data["depth"] == 0
    assert data["root_target"] == "example.com"
    assert data["resolved_domains"] == ["example.com", "www.example.com"]
    assert data["discovered_from"] == []
    assert data["open_port_count"] == 2
    assert data["scanned_port_count"] == 3
    assert data["vhost_count"] == 2

    # Deduplicated SANs from certs
    assert sorted(data["tls_sans"]) == ["api.example.com", "cdn.example.com", "example.com"]

    # All probed services on this host (including closed port 8080)
    ports = data["services"]
    assert len(ports) == 3
    port_numbers = [p["port_number"] for p in ports]
    assert sorted(port_numbers) == [80, 443, 8080]

    # Verify nested TLS cert on port 443
    p443 = next(p for p in ports if p["port_number"] == 443)
    assert p443["tls_certificate"] is not None
    assert p443["tls_certificate"]["issuer"] == "Google Trust Services"
    assert p443["tls_certificate"]["protocol_version"] == "TLSv1.3"

    # All HTTP routing checks on this host
    checks = data["checks"]
    assert len(checks) == 3
    domains = [c["domain"] for c in checks]
    assert "example.com" in domains
    assert "www.example.com" in domains

    # Test Host 2 (10.0.0.100 - discovered at depth 1)
    resp_h2 = client.get(f"/api/runs/{populated_run}/hosts/10.0.0.100")
    assert resp_h2.status_code == 200
    data_h2 = resp_h2.json()
    assert data_h2["ip_address"] == "10.0.0.100"
    assert data_h2["status"] == "warning"
    assert data_h2["depth"] == 1
    assert data_h2["discovered_from"] == ["example.com"]
    assert data_h2["tls_sans"] == ["api.example.com"]
    assert len(data_h2["services"]) == 1
    assert len(data_h2["checks"]) == 1
    assert data_h2["checks"][0]["status_code"] == 404


def test_get_host_detail_drawer_404_cases(client: TestClient, populated_run: str):
    """GET /api/runs/{id}/hosts/{ip} returns 404 when run or host IP does not exist."""
    # Non-existent run
    resp_run = client.get("/api/runs/nonexistent-run-id/hosts/10.0.0.1")
    assert resp_run.status_code == 404
    assert "Run not found" in resp_run.json()["detail"]

    # Non-existent host IP in existing run
    resp_host = client.get(f"/api/runs/{populated_run}/hosts/192.168.1.99")
    assert resp_host.status_code == 404
    assert "not found" in resp_host.json()["detail"]
