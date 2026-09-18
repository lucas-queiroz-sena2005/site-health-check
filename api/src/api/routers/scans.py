from datetime import datetime, timezone
from typing import Any, Annotated
from fastapi import APIRouter, status, HTTPException, Path
from sqlmodel import select
import croniter
from pydantic import BaseModel, ConfigDict

from api.models import Scan, TargetGroup, ScanTargetGroupLink, ExecutionConfig, ScanRun
from api.database import SessionDep

router = APIRouter(prefix="/scans", tags=["scans"])

class ScanCreateRequest(ExecutionConfig):
    name: str
    cron_expression: str | None = None

class ScanResponse(ExecutionConfig):
    id: str
    name: str
    cron_expression: str | None
    is_active: bool
    last_run: datetime | None = None
    next_run: datetime | None = None
    metrics: dict[str, Any] | None = None

@router.post("", status_code=status.HTTP_201_CREATED)
def create_scan(request: ScanCreateRequest, session: SessionDep) -> ScanResponse:
    # 1. Create an ad-hoc target group for these targets
    target_group = TargetGroup(
        name=f"Ad-hoc Target Group for {request.name}",
        is_ad_hoc=True,
        targets_json=request.targets
    )
    session.add(target_group)
    
    # 2. Create the scan
    scan = Scan(
        name=request.name,
        cron_expression=request.cron_expression,
        ports_json=request.ports,
        flags_json=request.model_dump(exclude={"name", "cron_expression", "targets", "ports"})
    )
    session.add(scan)
    
    session.commit() # Commit to get IDs
    
    # 3. Link them
    link = ScanTargetGroupLink(
        scan_id=scan.id,
        target_group_id=target_group.id
    )
    session.add(link)
    session.commit()
    session.refresh(scan)
    
    next_run = None
    if scan.cron_expression:
        try:
            it = croniter.croniter(scan.cron_expression, datetime.now(timezone.utc))
            next_run = it.get_next(datetime)
        except Exception:
            pass

    return ScanResponse(
        id=scan.id,
        name=scan.name,
        cron_expression=scan.cron_expression,
        is_active=scan.is_active,
        last_run=None,
        next_run=next_run,
        metrics=None,
        targets=request.targets,
        ports=scan.ports_json,
        **scan.flags_json
    )

@router.get("")
def list_scans(session: SessionDep) -> list[ScanResponse]:
    stmt = select(Scan).where(Scan.deleted_at == None)
    scans = session.exec(stmt).all()
    
    responses = []
    for s in scans:
        # Extract targets from target groups
        targets = []
        for tg in s.target_groups:
            targets.extend(tg.targets_json)
        # Get latest run
        run_stmt = select(ScanRun).where(ScanRun.scan_id == s.id).order_by(ScanRun.started_at.desc()).limit(1)
        latest_run = session.exec(run_stmt).first()
        
        last_run = latest_run.started_at if latest_run and latest_run.started_at else None
        metrics = latest_run.metrics_json if latest_run else None
        
        next_run = None
        if s.cron_expression and s.is_active:
            try:
                it = croniter.croniter(s.cron_expression, datetime.now(timezone.utc))
                next_run = it.get_next(datetime)
            except Exception:
                pass
            
        responses.append(ScanResponse(
            id=s.id,
            name=s.name,
            cron_expression=s.cron_expression,
            is_active=s.is_active,
            last_run=last_run,
            next_run=next_run,
            metrics=metrics,
            targets=targets,
            ports=s.ports_json,
            **s.flags_json
        ))
    return responses

@router.put("/{id}")
def update_scan(id: Annotated[str, Path()], request: ScanCreateRequest, session: SessionDep) -> ScanResponse:
    scan = session.get(Scan, id)
    if not scan or scan.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Scan not found")
        
    scan.name = request.name
    scan.cron_expression = request.cron_expression
    scan.ports_json = request.ports
    scan.flags_json = request.model_dump(exclude={"name", "cron_expression", "targets", "ports"})
    session.add(scan)
    
    # Update targets (delete old links, recreate ad-hoc)
    for tg in scan.target_groups:
        if tg.is_ad_hoc:
            session.delete(tg)
    scan.target_groups = []
    
    target_group = TargetGroup(
        name=f"Ad-hoc Target Group for {request.name}",
        is_ad_hoc=True,
        targets_json=request.targets
    )
    session.add(target_group)
    session.commit()
    
    link = ScanTargetGroupLink(
        scan_id=scan.id,
        target_group_id=target_group.id
    )
    session.add(link)
    session.commit()
    session.refresh(scan)
    
    # Re-calculate runs
    run_stmt = select(ScanRun).where(ScanRun.scan_id == scan.id).order_by(ScanRun.started_at.desc()).limit(1)
    latest_run = session.exec(run_stmt).first()
    last_run = latest_run.started_at if latest_run and latest_run.started_at else None
    metrics = latest_run.metrics_json if latest_run else None
    
    next_run = None
    if scan.cron_expression and scan.is_active:
        try:
            it = croniter.croniter(scan.cron_expression, datetime.now(timezone.utc))
            next_run = it.get_next(datetime)
        except Exception:
            pass

    return ScanResponse(
        id=scan.id,
        name=scan.name,
        cron_expression=scan.cron_expression,
        is_active=scan.is_active,
        last_run=last_run,
        next_run=next_run,
        metrics=metrics,
        targets=request.targets,
        ports=scan.ports_json,
        **scan.flags_json
    )

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scan(id: Annotated[str, Path()], session: SessionDep):
    scan = session.get(Scan, id)
    if not scan or scan.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Scan not found")
        
    scan.deleted_at = datetime.now(timezone.utc)
    scan.is_active = False
    session.add(scan)
    session.commit()

