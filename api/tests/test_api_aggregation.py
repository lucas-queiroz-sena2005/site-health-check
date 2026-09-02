from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool
import pytest

from api.main import app
from api.database import get_session
from api.models import Job, IpState, PortState

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

def test_void_aggregation_and_ghosting(client: TestClient, session: Session):
    now = datetime.now(timezone.utc)
    
    # Create an old job (8 days ago) - outside default 7d window
    old_job = Job(execution_config_snapshot_json={"targets": ["10.0.0.0/24"], "ports": [80]}, started_at=now - timedelta(days=8), status="FINISHED")
    # Create a recent job (2 days ago) - inside default 7d window
    recent_job = Job(execution_config_snapshot_json={"targets": ["10.0.0.0/24"], "ports": [80]}, started_at=now - timedelta(days=2), status="FINISHED")
    # Create current job
    current_job = Job(execution_config_snapshot_json={"targets": ["10.0.0.0/24"], "ports": [80]}, started_at=now, status="FINISHED")
    
    session.add_all([old_job, recent_job, current_job])
    session.commit()
    
    # IP 1: Active 8 days ago, now dead. Should be VOID because it's outside the 7d window.
    old_ip = IpState(job_id=old_job.id, ip_address="10.0.0.1", metadata_resolved_from="10.0.0.0/24")
    old_ip.ports_list = [PortState(port_number=80, tcp_status="open")]
    
    # IP 2: Active 2 days ago, now dead. Should be GHOST because it's inside the 7d window.
    recent_ip = IpState(job_id=recent_job.id, ip_address="10.0.0.2", metadata_resolved_from="10.0.0.0/24")
    recent_ip.ports_list = [PortState(port_number=80, tcp_status="open")]
    
    session.add_all([old_ip, recent_ip])
    session.commit()
    
    # Current Job IPs:
    # 10.0.0.1 -> dead -> Void
    # 10.0.0.2 -> dead -> Ghost (from recent_job)
    # 10.0.0.3 -> dead -> Void
    # 10.0.0.4 -> active -> Active
    curr_ip1 = IpState(job_id=current_job.id, ip_address="10.0.0.1", metadata_resolved_from="10.0.0.0/24")
    curr_ip1.ports_list = [PortState(port_number=80, tcp_status="closed")]
    
    curr_ip2 = IpState(job_id=current_job.id, ip_address="10.0.0.2", metadata_resolved_from="10.0.0.0/24")
    curr_ip2.ports_list = [PortState(port_number=80, tcp_status="closed")]
    
    curr_ip3 = IpState(job_id=current_job.id, ip_address="10.0.0.3", metadata_resolved_from="10.0.0.0/24")
    curr_ip3.ports_list = [PortState(port_number=80, tcp_status="closed")]
    
    curr_ip4 = IpState(job_id=current_job.id, ip_address="10.0.0.4", metadata_resolved_from="10.0.0.0/24")
    curr_ip4.ports_list = [PortState(port_number=80, tcp_status="open")]
    
    session.add_all([curr_ip1, curr_ip2, curr_ip3, curr_ip4])
    session.commit()
    
    # Request results for the current job with default 7d window
    response = client.get(f"/results?job_id={current_job.id}")
    assert response.status_code == 200
    data = response.json()
    
    # We expect:
    # - 10.0.0.2 (Ghost)
    # - 10.0.0.4 (Active)
    # - "Void (2)" (Squashed 10.0.0.1 and 10.0.0.3)
    assert len(data) == 3
    
    ips = {item["ip_address"] for item in data}
    assert "10.0.0.2" in ips
    assert "10.0.0.4" in ips
    assert "Void (2)" in ips
    
    # Test overriding the window to 10d
    # 10.0.0.1 (8 days ago) now becomes a Ghost too!
    # 10.0.0.3 remains Void (1)
    response_10d = client.get(f"/results?job_id={current_job.id}&ghost_window=10d")
    assert response_10d.status_code == 200
    data_10d = response_10d.json()
    
    assert len(data_10d) == 4
    ips_10d = {item["ip_address"] for item in data_10d}
    assert "10.0.0.1" in ips_10d
    assert "10.0.0.2" in ips_10d
    assert "10.0.0.4" in ips_10d
    assert "Void (1)" in ips_10d
