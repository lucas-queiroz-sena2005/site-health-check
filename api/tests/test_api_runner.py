import uuid
import pytest
from sqlmodel import Session, select, create_engine, SQLModel
from sqlmodel.pool import StaticPool
from api.models import HostState, PortState, HttpRoutingCheck, TlsCertificate
from api.services.runner import _upsert_delta_sync
from unittest.mock import patch

@pytest.fixture(name="test_engine")
def test_engine_fixture():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine

def test_upsert_delta_sync_inserts_and_updates(test_engine):
    with patch("api.services.runner.db_engine", test_engine):
        # We test that _upsert_delta_sync correctly merges overlapping data (ON CONFLICT DO UPDATE)
        run_id = str(uuid.uuid4())
        ip = "192.168.1.100"
        
        # Delta 1: partial data (just TCP open)
        delta1 = {
            "metadata": {"resolved_from": "test.local", "discovered_from": ["initial"]},
            "ports": {
                "443": {
                    "tcp_status": "open",
                    "tcp_latency_ms": 15
                }
            }
        }
        
        _upsert_delta_sync(run_id, ip, delta1)
        
        with Session(test_engine) as session:
            host = session.exec(select(HostState).where(HostState.scan_run_id == run_id, HostState.ip_address == ip)).first()
            assert host is not None
            assert host.metadata_resolved_from == "test.local"
            
            ports = session.exec(select(PortState).where(PortState.host_state_id == host.id)).all()
            assert len(ports) == 1
            assert ports[0].port_number == 443
            assert ports[0].tcp_status == "open"
            assert ports[0].tcp_latency_ms == 15
            
        # Delta 2: overlapping data with new HTTP routing checks and TLS
        delta2 = {
            "metadata": {"resolved_from": "test.local", "discovered_from": ["initial", "second"]},
            "ports": {
                "443": {
                    "tcp_status": "open",
                    "tcp_latency_ms": 16, # updated latency
                    "tls_certificate": {
                        "valid": True,
                        "expires_in_days": 30,
                        "issuer": "Test CA",
                        "protocol_version": "TLSv1.3",
                        "domains_discovered_sans": ["test.local"]
                    },
                    "http_routing_checks": {
                        "test.local": {
                            "status_code": 200,
                            "http_latency_ms": 45,
                            "path_checked": "/",
                            "server_header": "nginx"
                        }
                    }
                }
            }
        }
        
        _upsert_delta_sync(run_id, ip, delta2)
        
        with Session(test_engine) as session:
            host = session.exec(select(HostState).where(HostState.scan_run_id == run_id, HostState.ip_address == ip)).first()
            assert host.metadata_discovered_from_json == ["initial", "second"]
            
            ports = session.exec(select(PortState).where(PortState.host_state_id == host.id)).all()
            assert len(ports) == 1 # still 1 port
            port = ports[0]
            assert port.tcp_latency_ms == 16 # updated
            
            tls = session.exec(select(TlsCertificate).where(TlsCertificate.port_state_id == port.id)).first()
            assert tls is not None
            assert tls.issuer == "Test CA"
            assert tls.valid is True
            
            routes = session.exec(select(HttpRoutingCheck).where(HttpRoutingCheck.port_state_id == port.id)).all()
            assert len(routes) == 1
            assert routes[0].domain == "test.local"
            assert routes[0].status_code == 200
