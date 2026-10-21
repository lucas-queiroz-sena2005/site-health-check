import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

import api.models as models
from api.database import engine


@pytest.fixture(name="db_session")
def db_session_fixture():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with test_engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys = ON;"))
    SQLModel.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        yield session


def test_sqlite_pragmas():
    """Verify that the application SQLite engine configures WAL mode, foreign keys, and busy_timeout."""
    with Session(engine) as session:
        fk = session.execute(text("PRAGMA foreign_keys;")).scalar()
        assert fk == 1, "Foreign keys should be enabled (PRAGMA foreign_keys=ON)"

        timeout = session.execute(text("PRAGMA busy_timeout;")).scalar()
        assert timeout is not None and timeout >= 5000, "Busy timeout should be at least 5000ms"

        journal_mode = session.execute(text("PRAGMA journal_mode;")).scalar()
        assert str(journal_mode).lower() in ("wal", "memory"), "Journal mode should be WAL"


def test_target_group_retired():
    """Verify TargetGroup and ScanTargetGroupLink models are retired and deleted from api.models."""
    assert not hasattr(models, "TargetGroup"), "TargetGroup model should be retired and deleted"
    assert not hasattr(models, "ScanTargetGroupLink"), "ScanTargetGroupLink model should be retired and deleted"


def test_scan_direct_targets_storage(db_session: Session):
    """Verify Scan accepts targets: list[str] directly without TargetGroup indirection."""
    scan = models.Scan(
        name="Direct Target Scan",
        targets=["192.168.1.0/24", "example.com"],
        ports_json=[80, 443],
        flags_json={},
    )
    db_session.add(scan)
    db_session.commit()
    db_session.refresh(scan)
    assert scan.targets == ["192.168.1.0/24", "example.com"]


def test_tls_certificate_unique_port_state_id(db_session: Session):
    """Verify UniqueConstraint('port_state_id') prevents duplicate certificates per port."""
    run = models.ScanRun(execution_config_snapshot_json={})
    db_session.add(run)
    db_session.commit()

    host = models.HostState(scan_run_id=run.id, ip_address="1.1.1.1")
    db_session.add(host)
    db_session.commit()

    port = models.PortState(host_state_id=host.id, port_number=443)
    db_session.add(port)
    db_session.commit()

    cert1 = models.TlsCertificate(port_state_id=port.id, valid=True, expires_in_days=30)
    db_session.add(cert1)
    db_session.commit()

    cert2 = models.TlsCertificate(port_state_id=port.id, valid=False, expires_in_days=0)
    db_session.add(cert2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_no_model_serializer_dict_wrappers():
    """Verify that HostState and PortState do not use @model_serializer mode='wrap' dictionary hacks."""
    assert "serialize_model" not in models.HostState.__dict__, "@model_serializer should be removed from HostState"
    assert "serialize_model" not in models.PortState.__dict__, "@model_serializer should be removed from PortState"

    run = models.ScanRun(execution_config_snapshot_json={})
    host = models.HostState(scan_run_id=run.id, ip_address="1.1.1.1")
    port = models.PortState(host_state_id=host.id, port_number=80)
    check = models.HttpRoutingCheck(port_state_id=port.id, domain="example.com")

    port.http_routing_checks = [check]
    assert isinstance(port.http_routing_checks, list)

    host.ports = [port]
    assert isinstance(host.ports, list)
