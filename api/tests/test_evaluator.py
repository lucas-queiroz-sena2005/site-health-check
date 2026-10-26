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
    run = ScanRun(execution_config_snapshot_json={"tls_warning_days": 30, "prune_closed_ports": False})
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

    assert closed_port.status == "void"
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


def test_active_host_void_port_vs_ghost_port_and_summary(session: Session):
    """Void closed ports on active hosts must not fail the host, while historically open closed ports trigger ghost warning, and evaluate_scan_run writes metrics_json['summary']."""
    past_time = datetime.now(UTC) - timedelta(days=1)
    past_run = ScanRun(
        execution_config_snapshot_json={},
        started_at=past_time,
        status=ScanRunStatus.COMPLETED,
    )
    session.add(past_run)
    session.commit()

    # In the past run, 10.0.0.51 had BOTH port 80 and port 443 open
    past_host = HostState(scan_run_id=past_run.id, ip_address="10.0.0.51")
    session.add(past_host)
    session.commit()
    session.add_all([
        PortState(host_state_id=past_host.id, port_number=80, tcp_status="open"),
        PortState(host_state_id=past_host.id, port_number=443, tcp_status="open"),
    ])
    session.commit()

    run = ScanRun(
        execution_config_snapshot_json={"ghost_window": "7d", "tls_warning_days": 30},
        started_at=datetime.now(UTC),
        status=ScanRunStatus.COMPLETED,
    )
    session.add(run)
    session.commit()

    # Host A (10.0.0.50): port 80 open (HTTP 200), port 443 closed (never historically open -> void port)
    host_a = HostState(scan_run_id=run.id, ip_address="10.0.0.50")
    # Host B (10.0.0.51): port 80 open (HTTP 200), port 443 closed (WAS historically open -> ghost port!)
    host_b = HostState(scan_run_id=run.id, ip_address="10.0.0.51")
    session.add_all([host_a, host_b])
    session.commit()

    pa_80 = PortState(host_state_id=host_a.id, port_number=80, tcp_status="open")
    pa_443 = PortState(host_state_id=host_a.id, port_number=443, tcp_status="closed")
    pb_80 = PortState(host_state_id=host_b.id, port_number=80, tcp_status="open")
    pb_443 = PortState(host_state_id=host_b.id, port_number=443, tcp_status="closed")
    session.add_all([pa_80, pa_443, pb_80, pb_443])
    session.commit()

    session.add_all([
        HttpRoutingCheck(port_state_id=pa_80.id, domain="10.0.0.50", status_code=200),
        HttpRoutingCheck(port_state_id=pb_80.id, domain="10.0.0.51", status_code=200),
    ])
    session.commit()

    evaluate_scan_run(run.id, session, void_count=10)

    session.refresh(host_a)
    session.refresh(host_b)
    session.refresh(run)

    # Host A: healthy active host; void port 443 does not fail the host
    assert host_a.status == "ok"
    assert FINDING_TCP_CLOSED not in host_a.finding_codes

    # Host B: port 443 was historically open and is now closed -> ghost warning
    assert host_b.status == "warning"
    assert FINDING_HOST_GHOST in host_b.finding_codes

    # Summary persisted on ScanRun.metrics_json
    assert run.metrics_json is not None
    assert run.metrics_json["summary"]["active"] == 1
    assert run.metrics_json["summary"]["warning"] == 1
    assert run.metrics_json["summary"]["failed"] == 0
    assert run.metrics_json["summary"]["ghost"] == 0
    assert run.metrics_json["summary"]["void"] == 10


def test_evaluator_summary_service_and_check_counts(session: Session):
    """Verify that evaluate_scan_run computes service_count and http_check_count in metrics_json['summary']."""
    run = ScanRun(
        execution_config_snapshot_json={"ghost_window": "7d", "tls_warning_days": 30},
        started_at=datetime.now(UTC),
        status=ScanRunStatus.COMPLETED,
    )
    session.add(run)
    session.commit()

    # Host 1: 2 open ports, 1 closed routine port
    h1 = HostState(scan_run_id=run.id, ip_address="10.0.0.1")
    session.add(h1)
    session.commit()
    p1 = PortState(host_state_id=h1.id, port_number=80, tcp_status="open")
    p2 = PortState(host_state_id=h1.id, port_number=443, tcp_status="open")
    p3 = PortState(host_state_id=h1.id, port_number=8080, tcp_status="closed")
    session.add_all([p1, p2, p3])
    session.commit()

    # Add HTTP checks on open ports
    c1 = HttpRoutingCheck(port_state_id=p1.id, domain="example.com", status_code=200)
    c2 = HttpRoutingCheck(port_state_id=p2.id, domain="example.com", status_code=200)
    c3 = HttpRoutingCheck(port_state_id=p2.id, domain="api.example.com", status_code=200)
    session.add_all([c1, c2, c3])
    session.commit()

    summary = evaluate_scan_run(run.id, session, void_count=0)

    # service_count: count of open services + ghost port outages (here 2 open ports p1, p2)
    assert summary["service_count"] == 2
    # http_check_count: count of all L7 routing checks (here 3 checks c1, c2, c3)
    assert summary["http_check_count"] == 3


def test_evaluator_assigns_entity_status_void_and_ghost(session: Session):
    """Routine closed ports get status='void', historically open closed ports get status='ghost',
    and inactive non-ghost hosts get status='void'."""
    from api.models import EntityStatus

    past_time = datetime.now(UTC) - timedelta(days=2)
    past_run = ScanRun(
        execution_config_snapshot_json={},
        started_at=past_time,
        status=ScanRunStatus.COMPLETED,
    )
    session.add(past_run)
    session.commit()

    # Past run: 10.0.0.2 had port 443 open
    past_host = HostState(scan_run_id=past_run.id, ip_address="10.0.0.2")
    session.add(past_host)
    session.commit()
    session.add(PortState(host_state_id=past_host.id, port_number=443, tcp_status="open"))
    session.commit()

    # Current run with pruning disabled to inspect evaluated statuses in DB
    run = ScanRun(
        execution_config_snapshot_json={
            "ghost_window": "7d",
            "tls_warning_days": 30,
            "prune_void_hosts": False,
            "prune_closed_ports": False,
        },
        started_at=datetime.now(UTC),
        status=ScanRunStatus.COMPLETED,
    )
    session.add(run)
    session.commit()

    # Host 1: Active host with 1 open port and 1 routine closed port (never historically open)
    h1 = HostState(scan_run_id=run.id, ip_address="10.0.0.1")
    # Host 2: Ghost host with closed port 443 (was historically open)
    h2 = HostState(scan_run_id=run.id, ip_address="10.0.0.2")
    # Host 3: Inactive non-ghost host with closed port 80 (never historically open -> VOID host)
    h3 = HostState(scan_run_id=run.id, ip_address="10.0.0.3")
    session.add_all([h1, h2, h3])
    session.commit()

    p1_open = PortState(host_state_id=h1.id, port_number=80, tcp_status="open")
    p1_closed = PortState(host_state_id=h1.id, port_number=8080, tcp_status="closed")
    p2_ghost = PortState(host_state_id=h2.id, port_number=443, tcp_status="closed")
    p3_void = PortState(host_state_id=h3.id, port_number=80, tcp_status="closed")
    session.add_all([p1_open, p1_closed, p2_ghost, p3_void])
    session.commit()

    evaluate_scan_run(run.id, session)

    session.refresh(h1)
    session.refresh(h2)
    session.refresh(h3)
    session.refresh(p1_open)
    session.refresh(p1_closed)
    session.refresh(p2_ghost)
    session.refresh(p3_void)

    # Port statuses
    assert p1_open.status == EntityStatus.OK
    assert p1_closed.status == EntityStatus.VOID, "Routine closed port must have status='void'"
    assert p2_ghost.status == EntityStatus.GHOST, "Historically open closed port must have status='ghost'"
    assert FINDING_HOST_GHOST in p2_ghost.finding_codes
    assert p3_void.status == EntityStatus.VOID

    # Host statuses
    assert h1.status == EntityStatus.OK
    assert h2.status == EntityStatus.GHOST
    assert FINDING_HOST_GHOST in h2.finding_codes
    assert h3.status == EntityStatus.VOID, "Inactive non-ghost host must have status='void'"


def test_evaluator_unified_pruning_pipeline(session: Session):
    """evaluate_scan_run directly performs pruning of void hosts and routine closed ports when configured."""
    from api.models import EntityStatus

    past_time = datetime.now(UTC) - timedelta(days=2)
    past_run = ScanRun(
        execution_config_snapshot_json={},
        started_at=past_time,
        status=ScanRunStatus.COMPLETED,
    )
    session.add(past_run)
    session.commit()

    past_host = HostState(scan_run_id=past_run.id, ip_address="10.0.0.2")
    session.add(past_host)
    session.commit()
    session.add(PortState(host_state_id=past_host.id, port_number=443, tcp_status="open"))
    session.commit()

    # Current run with prune_void_hosts=True and prune_closed_ports=True (defaults)
    run = ScanRun(
        execution_config_snapshot_json={
            "ghost_window": "7d",
            "prune_void_hosts": True,
            "prune_closed_ports": True,
        },
        started_at=datetime.now(UTC),
        status=ScanRunStatus.COMPLETED,
    )
    session.add(run)
    session.commit()

    h1 = HostState(scan_run_id=run.id, ip_address="10.0.0.1")
    h2 = HostState(scan_run_id=run.id, ip_address="10.0.0.2")
    h3 = HostState(scan_run_id=run.id, ip_address="10.0.0.3")
    session.add_all([h1, h2, h3])
    session.commit()

    p1_open = PortState(host_state_id=h1.id, port_number=80, tcp_status="open")
    p1_closed = PortState(host_state_id=h1.id, port_number=8080, tcp_status="closed")
    p2_ghost = PortState(host_state_id=h2.id, port_number=443, tcp_status="closed")
    p3_void = PortState(host_state_id=h3.id, port_number=80, tcp_status="closed")
    session.add_all([p1_open, p1_closed, p2_ghost, p3_void])
    session.commit()

    summary = evaluate_scan_run(run.id, session)

    # 1. Void host h3 should be pruned
    remaining_hosts = session.exec(select(HostState).where(HostState.scan_run_id == run.id)).all()
    remaining_ips = {h.ip_address for h in remaining_hosts}
    assert "10.0.0.3" not in remaining_ips, "Void host 10.0.0.3 must be pruned"
    assert "10.0.0.1" in remaining_ips
    assert "10.0.0.2" in remaining_ips, "Ghost host 10.0.0.2 must NOT be pruned"

    # 2. Routine closed port p1_closed should be pruned, ghost port p2_ghost preserved
    remaining_ports = session.exec(select(PortState)).all()
    port_numbers_by_host = {(p.host_state_id, p.port_number) for p in remaining_ports}
    assert (h1.id, 8080) not in port_numbers_by_host, "Routine closed port 8080 must be pruned"
    assert (h1.id, 80) in port_numbers_by_host
    assert (h2.id, 443) in port_numbers_by_host, "Ghost port 443 must NOT be pruned"

    # 3. Summary reflects correct counts
    assert summary["active"] == 1
    assert summary["ghost"] == 1
    assert summary["void"] == 1
    assert summary["service_count"] == 2  # 10.0.0.1:80 (open) + 10.0.0.2:443 (ghost)


