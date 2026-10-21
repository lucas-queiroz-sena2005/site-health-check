import pytest
from api.database import get_session
from api.main import app
from api.models import HostState, HttpRoutingCheck, PortState, ScanRun, ScanRunStatus, TlsCertificate
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

def test_get_results(client: TestClient, session: Session):
    # Setup Data
    job = ScanRun(execution_config_snapshot_json={"targets": ["google.com"]}, status=ScanRunStatus.COMPLETED)
    session.add(job)
    session.commit()
    session.refresh(job)

    ip_state = HostState(
        scan_run_id=job.id,
        ip_address="8.8.8.8",
        resolved_domains=["google.com"],
        discovered_from=[],
    )
    session.add(ip_state)
    session.flush()
    
    port_state = PortState(
        host_state_id=ip_state.id,
        port_number=443,
        tcp_status="open",
        tcp_latency_ms=25,
    )
    session.add(port_state)
    session.flush()
    
    tls_cert = TlsCertificate(
        port_state_id=port_state.id,
        valid=True,
        expires_in_days=30,
        domains_discovered_sans_json=["google.com"]
    )
    session.add(tls_cert)
    
    http_check = HttpRoutingCheck(
        port_state_id=port_state.id,
        domain="google.com",
        status_code=200,
        http_latency_ms=120,
    )
    session.add(http_check)
    session.commit()

    response = client.get("/api/results")
    assert response.status_code == 200
    data = response.json()
    
    print("DATA: ", data)
    assert len(data) == 1
    assert data[0]["ip_address"] == "8.8.8.8"
    assert data[0]["resolved_domains"] == ["google.com"]
    
    # Assert relational models maintain direct object hierarchy without dict wrappers
    session.refresh(ip_state)
    assert len(ip_state.ports) == 1
    port_443 = ip_state.ports[0]
    assert port_443.port_number == 443
    assert port_443.tcp_status == "open"
    assert port_443.tls_certificate.valid is True
    assert len(port_443.http_routing_checks) == 1
    assert port_443.http_routing_checks[0].domain == "google.com"
    assert port_443.http_routing_checks[0].status_code == 200

def test_host_state_subrun_id(session: Session):
    job = ScanRun(execution_config_snapshot_json={"targets": ["10.0.0.0/24"]}, status=ScanRunStatus.COMPLETED)
    session.add(job)
    session.commit()
    session.refresh(job)

    ip_state = HostState(
        scan_run_id=job.id,
        subrun_id="10.0.0.0/24",
        ip_address="10.0.0.5",
    )
    session.add(ip_state)
    session.commit()
    session.refresh(ip_state)

    assert ip_state.subrun_id == "10.0.0.0/24"

def test_get_results_by_subrun(client: TestClient, session: Session):
    job = ScanRun(execution_config_snapshot_json={"targets": ["10.0.0.0/16"]}, status=ScanRunStatus.COMPLETED)
    session.add(job)
    session.commit()
    session.refresh(job)

    ip_state1 = HostState(
        scan_run_id=job.id,
        subrun_id="10.0.0.0/24",
        ip_address="10.0.0.5",
    )
    ip_state2 = HostState(
        scan_run_id=job.id,
        subrun_id="10.0.1.0/24",
        ip_address="10.0.1.5",
    )
    session.add_all([ip_state1, ip_state2])
    session.commit()

    port_state = PortState(
        host_state_id=ip_state1.id,
        port_number=443,
        tcp_status="open",
        tcp_latency_ms=25,
    )
    session.add(port_state)
    session.commit()

    response = client.get(f"/api/results?run_id={job.id}&subrun_id=10.0.0.0/24")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["ip_address"] == "10.0.0.5"

