import pytest
from datetime import UTC, datetime, timedelta
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from api.models import (
    HostState,
    HttpRoutingCheck,
    PortState,
    Scan,
    ScanRun,
    ScanRunStatus,
    TlsCertificate,
)
from api.services.evaluator import (
    FINDING_HTTP_4XX,
    FINDING_HTTP_5XX,
    FINDING_HTTP_ERROR,
    FINDING_HOST_GHOST,
    FINDING_TCP_CLOSED,
    FINDING_TLS_DEPRECATED_VERSION,
    FINDING_TLS_EXPIRED,
    FINDING_TLS_EXPIRING_SOON,
    FINDING_TLS_INVALID,
    evaluate_scan_run,
)


@pytest.fixture(name="session")
def session_fixture():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        yield session


def test_http_check_findings_evaluation(session: Session):
    """Level 1: HttpRoutingCheck status and finding codes."""
    run = ScanRun(execution_config_snapshot_json={})
    session.add(run)
    session.commit()

    host = HostState(scan_run_id=run.id, ip_address="10.0.0.1")
    session.add(host)
    session.commit()

    port = PortState(host_state_id=host.id, port_number=443, tcp_status="open")
    session.add(port)
    session.commit()

    check_ok = HttpRoutingCheck(port_state_id=port.id, domain="ok.com", status_code=200)
    check_4xx = HttpRoutingCheck(port_state_id=port.id, domain="warn.com", status_code=404)
    check_5xx = HttpRoutingCheck(port_state_id=port.id, domain="err.com", status_code=502)
    check_timeout = HttpRoutingCheck(port_state_id=port.id, domain="timeout.com", status_code=None)

    session.add_all([check_ok, check_4xx, check_5xx, check_timeout])
    session.commit()

    evaluate_scan_run(run.id, session)

    session.refresh(check_ok)
    session.refresh(check_4xx)
    session.refresh(check_5xx)
    session.refresh(check_timeout)

    assert check_ok.status == "ok"
    assert check_ok.finding_code is None

    assert check_4xx.status == "warning"
    assert check_4xx.finding_code == FINDING_HTTP_4XX

    assert check_5xx.status == "failed"
    assert check_5xx.finding_code == FINDING_HTTP_5XX

    assert check_timeout.status == "failed"
    assert check_timeout.finding_code == FINDING_HTTP_ERROR


def test_port_state_rollups_and_tls_findings(session: Session):
    """Level 2: PortState status, san_count, http_check_count, and TLS finding codes."""
    run = ScanRun(execution_config_snapshot_json={"tls_warning_days": 30})
    session.add(run)
    session.commit()

    host = HostState(scan_run_id=run.id, ip_address="10.0.0.2")
    session.add(host)
    session.commit()

    # Port with closed TCP
    closed_port = PortState(host_state_id=host.id, port_number=22, tcp_status="closed")
    
    # Port with deprecated TLS (TLSv1.0) and expiring certificate
    deprecated_tls_port = PortState(
        host_state_id=host.id,
        port_number=443,
        tcp_status="open",
        tcp_latency_ms=35,
    )
    session.add_all([closed_port, deprecated_tls_port])
    session.commit()

    cert = TlsCertificate(
        port_state_id=deprecated_tls_port.id,
        valid=True,
        expires_in_days=15,  # <= 30 => expiring soon
        protocol_version="TLSv1.0",  # Deprecated
        domains_discovered_sans_json=["a.com", "b.com"],
    )
    http_check = HttpRoutingCheck(
        port_state_id=deprecated_tls_port.id,
        domain="a.com",
        status_code=200,
    )
    session.add_all([cert, http_check])
    session.commit()

    evaluate_scan_run(run.id, session)

    session.refresh(closed_port)
    session.refresh(deprecated_tls_port)

    assert closed_port.status == "failed"
    assert FINDING_TCP_CLOSED in closed_port.finding_codes

    assert deprecated_tls_port.san_count == 2
    assert deprecated_tls_port.http_check_count == 1
    assert deprecated_tls_port.worst_http_status == 200
    assert FINDING_TLS_EXPIRING_SOON in deprecated_tls_port.finding_codes
    assert FINDING_TLS_DEPRECATED_VERSION in deprecated_tls_port.finding_codes
    assert deprecated_tls_port.status == "warning"


def test_host_state_rollups_and_ghost_evaluation(session: Session):
    """Level 3: HostState bottom-up rollups and Ghost classification."""
    # Past run where 10.0.0.99 was active (to simulate ghost host)
    past_time = datetime.now(UTC) - timedelta(days=2)
    past_run = ScanRun(
        execution_config_snapshot_json={},
        started_at=past_time,
        status=ScanRunStatus.COMPLETED,
    )
    session.add(past_run)
    session.commit()

    past_host = HostState(scan_run_id=past_run.id, ip_address="10.0.0.99")
    session.add(past_host)
    session.commit()
    past_port = PortState(host_state_id=past_host.id, port_number=80, tcp_status="open")
    session.add(past_port)
    session.commit()

    # Current run
    current_run = ScanRun(
        execution_config_snapshot_json={"ghost_window": "7d", "tls_warning_days": 30},
        started_at=datetime.now(UTC),
        status=ScanRunStatus.COMPLETED,
    )
    session.add(current_run)
    session.commit()

    # Host 1: Active with multiple ports and lineage
    host_active = HostState(
        scan_run_id=current_run.id,
        ip_address="10.0.0.10",
        resolved_domains=["example.com", "vhost.org"],
        discovered_from=["10.0.0.1"],
    )
    # Host 2: Dead now, but was active 2 days ago -> Ghost
    host_ghost = HostState(
        scan_run_id=current_run.id,
        ip_address="10.0.0.99",
        resolved_domains=[],
        discovered_from=[],
    )
    session.add_all([host_active, host_ghost])
    session.commit()

    port80 = PortState(host_state_id=host_active.id, port_number=80, tcp_status="open", tcp_latency_ms=20)
    port443 = PortState(host_state_id=host_active.id, port_number=443, tcp_status="open", tcp_latency_ms=10)
    port_ghost = PortState(host_state_id=host_ghost.id, port_number=80, tcp_status="closed")
    session.add_all([port80, port443, port_ghost])
    session.commit()

    cert443 = TlsCertificate(
        port_state_id=port443.id,
        valid=True,
        expires_in_days=60,
        protocol_version="TLSv1.3",
        domains_discovered_sans_json=["example.com"],
    )
    check80 = HttpRoutingCheck(port_state_id=port80.id, domain="example.com", status_code=200)
    check443 = HttpRoutingCheck(port_state_id=port443.id, domain="example.com", status_code=500)
    session.add_all([cert443, check80, check443])
    session.commit()

    evaluate_scan_run(current_run.id, session)

    session.refresh(host_active)
    session.refresh(host_ghost)

    # Active host assertions
    assert host_active.depth == 1
    assert host_active.vhost_count == 2
    assert host_active.open_port_count == 2
    assert host_active.scanned_port_count == 2
    assert host_active.min_tcp_latency_ms == 10
    assert host_active.min_tls_expires_days == 60
    assert host_active.worst_tls_version == "TLSv1.3"
    assert host_active.worst_http_status == 500
    assert FINDING_HTTP_5XX in host_active.finding_codes
    assert host_active.status == "failed"

    # Ghost host assertions
    assert host_ghost.open_port_count == 0
    assert host_ghost.status == "ghost"
    assert FINDING_HOST_GHOST in host_ghost.finding_codes
