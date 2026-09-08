from typing import Any
from fastapi import APIRouter, status
from sqlmodel import select
from pydantic import BaseModel, ConfigDict

from api.models import Scan, TargetGroup, ScanTargetGroupLink, ExecutionConfig
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
    
    return ScanResponse(
        id=scan.id,
        name=scan.name,
        cron_expression=scan.cron_expression,
        is_active=scan.is_active,
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
            
        responses.append(ScanResponse(
            id=s.id,
            name=s.name,
            cron_expression=s.cron_expression,
            is_active=s.is_active,
            targets=targets,
            ports=s.ports_json,
            **s.flags_json
        ))
    return responses
