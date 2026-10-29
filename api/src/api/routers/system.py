import os
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field as PydanticField
from sqlalchemy import func, text
from sqlmodel import Session, select

from api.database import SessionDep, engine, init_db, sqlite_url
from api.models import (
    HostState,
    Scan,
    ScanRun,
    ScanRunStatus,
    SystemConfig,
)
from api.services.scheduler import prune_expired_runs

router = APIRouter(prefix="/system", tags=["system"])


class SystemSettingsResponse(BaseModel):
    retention_days: int
    db_size_bytes: int
    total_runs: int
    total_hosts: int
    total_scans: int


class UpdateSystemSettingsRequest(BaseModel):
    retention_days: int = PydanticField(ge=0, title="Retention Days (0 = keep forever)")


def _get_db_size(session: Session) -> int:
    try:
        clean_url = sqlite_url.replace("sqlite:///", "")
        if os.path.isfile(clean_url):
            return os.path.getsize(clean_url)
        page_count = session.exec(text("PRAGMA page_count;")).one()[0]
        page_size = session.exec(text("PRAGMA page_size;")).one()[0]
        return int(page_count) * int(page_size)
    except Exception:
        return 0


def _build_system_response(session: Session, cfg: SystemConfig) -> SystemSettingsResponse:
    db_size = _get_db_size(session)
    total_runs = session.exec(select(func.count(ScanRun.id))).one() or 0
    total_hosts = session.exec(select(func.count(HostState.id))).one() or 0
    total_scans = session.exec(select(func.count(Scan.id))).one() or 0

    return SystemSettingsResponse(
        retention_days=cfg.retention_days,
        db_size_bytes=db_size,
        total_runs=total_runs,
        total_hosts=total_hosts,
        total_scans=total_scans,
    )


@router.get("/settings", response_model=SystemSettingsResponse)
def get_system_settings(session: SessionDep) -> SystemSettingsResponse:
    cfg = session.get(SystemConfig, 1)
    if not cfg:
        cfg = SystemConfig(id=1, retention_days=0)
        session.add(cfg)
        session.commit()
        session.refresh(cfg)
    return _build_system_response(session, cfg)


@router.put("/settings", response_model=SystemSettingsResponse)
def update_system_settings(
    request_data: UpdateSystemSettingsRequest,
    session: SessionDep,
) -> SystemSettingsResponse:
    cfg = session.get(SystemConfig, 1)
    if not cfg:
        cfg = SystemConfig(id=1, retention_days=request_data.retention_days)
    else:
        cfg.retention_days = request_data.retention_days
        cfg.updated_at = datetime.now(timezone.utc)
    session.add(cfg)
    session.commit()
    session.refresh(cfg)

    # Immediately prune expired runs if retention is enabled
    if cfg.retention_days > 0:
        prune_expired_runs(session, cfg.retention_days)

    return _build_system_response(session, cfg)


@router.post("/purge-runs")
def purge_runs(request: Request, session: SessionDep):
    """Wipes all ScanRun history while preserving Scans, SavedViews, and SystemConfig."""
    run_manager = getattr(request.app.state, "run_manager", None)
    runs = session.exec(select(ScanRun)).all()
    count = len(runs)
    for r in runs:
        if run_manager and run_manager.is_active(r.id):
            run_manager.abort_run(r.id)
        if run_manager and hasattr(run_manager, "unregister_run"):
            run_manager.unregister_run(r.id)
        session.delete(r)
    session.commit()

    try:
        with engine.begin() as conn:
            conn.execute(text("VACUUM;"))
    except Exception:
        pass

    return {
        "message": f"Successfully purged {count} runs",
        "purged_count": count,
    }


@router.post("/reset-db")
def reset_db(request: Request, session: SessionDep):
    """Factory reset: drops all tables, recreates schema, resets SystemConfig, and reclaims disk space."""
    run_manager = getattr(request.app.state, "run_manager", None)
    if run_manager and hasattr(run_manager, "active_runs"):
        for run_id in list(run_manager.active_runs.keys()):
            run_manager.abort_run(run_id)

    from sqlmodel import SQLModel

    SQLModel.metadata.drop_all(engine)
    init_db()

    with Session(engine) as new_session:
        cfg = new_session.get(SystemConfig, 1)
        if not cfg:
            new_session.add(SystemConfig(id=1, retention_days=0))
            new_session.commit()

    try:
        with engine.begin() as conn:
            conn.execute(text("VACUUM;"))
    except Exception:
        pass

    return {"message": "Database reset successfully"}
