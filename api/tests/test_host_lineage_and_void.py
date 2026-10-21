import uuid
import pytest
from sqlmodel import Session, select, create_engine, SQLModel
from sqlmodel.pool import StaticPool

from api.models import HostState, ScanRun, ScanRunStatus
from api.services.runner import _finalize_run, _upsert_delta_sync


@pytest.fixture(name="test_engine")
def test_engine_fixture():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine


def test_host_state_has_resolved_domains_and_discovered_from_columns():
    """Verify HostState schema has resolved_domains and discovered_from list columns and dropped legacy scalar fields."""
    assert hasattr(HostState, "resolved_domains"), "HostState must have resolved_domains column"
    assert hasattr(HostState, "discovered_from"), "HostState must have discovered_from column"
    assert not hasattr(HostState, "metadata_resolved_from"), "metadata_resolved_from must be retired"
    assert not hasattr(HostState, "metadata_discovered_from_json"), "metadata_discovered_from_json must be retired"


def test_upsert_delta_sync_merges_resolved_domains_and_discovered_from_set_union(test_engine):
    """Verify that multiple deltas for the same IP merge resolved_domains and discovered_from using set union."""
    from unittest.mock import patch
    with patch("api.services.runner.db_engine", test_engine):
        run_id = str(uuid.uuid4())
        ip = "192.168.1.50"

        with Session(test_engine) as session:
            session.add(ScanRun(id=run_id, status=ScanRunStatus.RUNNING, execution_config_snapshot_json={}))
            session.commit()

        # Delta 1: First vhost resolving to this IP
        delta1 = {
            "metadata": {
                "resolved_from": "vhost1.example.com",
                "discovered_from": ["root-scan"],
            },
            "ports": {
                "443": {"tcp_status": "open", "tcp_latency_ms": 20}
            }
        }
        _upsert_delta_sync(run_id, ip, delta1)

        # Delta 2: Second vhost resolving to the same IP
        delta2 = {
            "metadata": {
                "resolved_from": "vhost2.example.com",
                "discovered_from": ["san-discovery"],
            },
            "ports": {
                "443": {"tcp_status": "open"}
            }
        }
        _upsert_delta_sync(run_id, ip, delta2)

        with Session(test_engine) as session:
            host = session.exec(
                select(HostState).where(HostState.scan_run_id == run_id, HostState.ip_address == ip)
            ).first()

            assert host is not None
            # Both domains must be stored via set union, never overwritten
            assert set(host.resolved_domains) == {"vhost1.example.com", "vhost2.example.com"}
            assert set(host.discovered_from) == {"root-scan", "san-discovery"}


def test_no_void_sentinel_strings_in_db_or_finalization(test_engine):
    """Verify that non-responsive targets are purged without producing synthetic 'Void' sentinel IP strings."""
    from unittest.mock import patch
    with patch("api.services.runner.db_engine", test_engine):
        run_id = str(uuid.uuid4())
        with Session(test_engine) as session:
            run = ScanRun(
                id=run_id,
                status=ScanRunStatus.RUNNING,
                execution_config_snapshot_json={"ghost_window": "7d", "tls_warning_days": 30}
            )
            session.add(run)

            # Insert an inactive host
            dead_host = HostState(
                id=f"{run_id}_10.0.0.99",
                scan_run_id=run_id,
                ip_address="10.0.0.99",
                resolved_domains=["10.0.0.0/24"],
                discovered_from=[]
            )
            session.add(dead_host)
            session.commit()

        _finalize_run(run_id, 0)

        with Session(test_engine) as session:
            hosts = session.exec(select(HostState).where(HostState.scan_run_id == run_id)).all()
            # Non-responsive host must be purged completely
            assert len(hosts) == 0
            # Ensure no synthetic sentinel node like 'Void (1)' was created
            for h in hosts:
                assert not h.ip_address.startswith("Void")


def test_depth_lineage_inference():
    """Verify depth is inferred correctly from discovered_from lineage."""
    h_root = HostState(scan_run_id="run1", ip_address="1.1.1.1", resolved_domains=["example.com"], discovered_from=[])
    assert h_root.depth == 0, "Root host without discovery lineage should have depth 0"

    h_hop = HostState(scan_run_id="run1", ip_address="1.1.1.2", resolved_domains=["sub.example.com"], discovered_from=["example.com"])
    assert h_hop.depth == 1, "Discovered host should have depth 1"

