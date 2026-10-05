import uuid
from unittest.mock import patch
from datetime import datetime, timezone
from sqlmodel import Session, create_engine, SQLModel
from sqlmodel.pool import StaticPool
from fastapi.testclient import TestClient
from api.models import ScanRun, ScanRunStatus
from api.main import app

def test_startup_reconciliation():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    
    # Insert orphaned scans simulating a hard crash
    with Session(engine) as session:
        run1 = ScanRun(id=str(uuid.uuid4()), status=ScanRunStatus.RUNNING, started_at=datetime.now(timezone.utc), execution_config_snapshot_json={})
        run2 = ScanRun(id=str(uuid.uuid4()), status=ScanRunStatus.PENDING, started_at=datetime.now(timezone.utc), execution_config_snapshot_json={})
        run3 = ScanRun(id=str(uuid.uuid4()), status=ScanRunStatus.COMPLETED, started_at=datetime.now(timezone.utc), execution_config_snapshot_json={})
        session.add_all([run1, run2, run3])
        session.commit()
        
    with patch("api.main.db_engine", engine):
        with TestClient(app):
            # Entering the TestClient context manager triggers the FastAPI lifespan events
            pass
            
    # Verify that RUNNING and PENDING became FAILED, while COMPLETED remained intact
    with Session(engine) as session:
        r1 = session.get(ScanRun, run1.id)
        assert r1.status == ScanRunStatus.FAILED
        assert r1.metrics_json is not None
        assert r1.metrics_json.get("reason") == "api_restart"
        
        r2 = session.get(ScanRun, run2.id)
        assert r2.status == ScanRunStatus.FAILED
        
        r3 = session.get(ScanRun, run3.id)
        assert r3.status == ScanRunStatus.COMPLETED
