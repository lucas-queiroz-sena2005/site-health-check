import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from api.main import app
from api.database import get_session
from api.models import Job, IpState, PortState, TlsCertificate, HttpRoutingCheck

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
    job = Job(execution_config_snapshot_json={"targets": ["google.com"]}, status="FINISHED")
    session.add(job)
    session.commit()
    session.refresh(job)

    http_check = HttpRoutingCheck(
        domain="google.com",
        status_code=200,
        http_latency_ms=120,
    )
    
    tls_cert = TlsCertificate(
        valid=True,
        expires_in_days=30,
        domains_discovered_sans=["google.com"]
    )
    
    port_state = PortState(
        port_number=443,
        tcp_status="open",
        tcp_latency_ms=25,
        tls_certificate=tls_cert,
        http_routing_checks_list=[http_check]
    )
    
    ip_state = IpState(
        job_id=job.id,
        ip_address="8.8.8.8",
        metadata_resolved_from="google.com",
        metadata_discovered_from=[],
        ports_list=[port_state]
    )
    
    session.add(ip_state)
    session.commit()

    response = client.get("/results")
    assert response.status_code == 200
    data = response.json()
    
    print("DATA: ", data)
    assert len(data) == 1
    assert data[0]["ip_address"] == "8.8.8.8"
    assert data[0]["metadata"]["resolved_from"] == "google.com"
    
    # Assert dictionary structure for ports
    assert "443" in data[0]["ports"]
    port_443 = data[0]["ports"]["443"]
    assert port_443["tcp_status"] == "open"
    assert port_443["tls_certificate"]["valid"] is True
    
    # Assert dictionary structure for http_routing_checks
    assert "google.com" in port_443["http_routing_checks"]
    http_res = port_443["http_routing_checks"]["google.com"]
    assert http_res["status_code"] == 200

