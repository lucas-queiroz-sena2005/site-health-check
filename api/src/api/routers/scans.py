from datetime import datetime, timezone
from typing import Annotated, Any

import croniter
from fastapi import APIRouter, HTTPException, Path, Request, status
from sqlmodel import desc, select

from api.config import settings
from api.database import SessionDep
from api.models import (
    AlertConfig,
    ExecutionConfig,
    ExecutionFlags,
    Scan,
    ScanRun,
    ScanRunStatus,
)
from api.routers.runs import ScanRunResponse

router = APIRouter(prefix="/scans", tags=["scans"])

from pydantic import BaseModel

class ScanCreateRequest(ExecutionConfig):
    name: str
    cron_expression: str | None = None
    alert_config: AlertConfig | None = None
    alerts_muted: bool = False

class ScanUpdateRequest(BaseModel):
    name: str | None = None
    cron_expression: str | None = None
    is_active: bool | None = None
    targets: list[str] | None = None
    ports: list[int] | None = None
    flags: ExecutionFlags | None = None
    ghost_window: str | None = None
    tls_warning_days: int | None = None
    alert_config: AlertConfig | None = None
    alerts_muted: bool | None = None

class ScanResponse(ExecutionConfig):
    id: str
    name: str
    cron_expression: str | None
    is_active: bool
    last_run: datetime | None = None
    next_run: datetime | None = None
    metrics: dict[str, Any] | None = None
    alert_config: AlertConfig | None = None
    alerts_muted: bool = False

def _build_scan_response(
    scan: Scan, session: SessionDep, targets: list[str] | None = None
) -> ScanResponse:
    if targets is None:
        targets = scan.targets or []

    run_stmt = (
        select(ScanRun)
        .where(ScanRun.scan_id == scan.id)
        .order_by(desc(ScanRun.started_at))
        .limit(1)
    )
    latest_run = session.exec(run_stmt).first()

    last_run = latest_run.started_at if latest_run and latest_run.started_at else None
    if last_run and last_run.tzinfo is None:
        last_run = last_run.replace(tzinfo=timezone.utc)
    metrics = latest_run.metrics_json if latest_run else None

    next_run = None
    if scan.cron_expression and scan.is_active:
        try:
            tz = settings.get_tz()
            it = croniter.croniter(scan.cron_expression, datetime.now(tz))
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
        targets=targets,
        ports=scan.ports_json,
        flags=ExecutionFlags.model_validate(scan.flags_json),
        ghost_window=scan.ghost_window,
        tls_warning_days=scan.tls_warning_days,
        alert_config=(
            AlertConfig.model_validate(scan.alert_config_json)
            if scan.alert_config_json
            else None
        ),
        alerts_muted=scan.alerts_muted,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_scan(request: ScanCreateRequest, session: SessionDep) -> ScanResponse:
    scan = Scan(
        name=request.name,
        cron_expression=request.cron_expression,
        targets=request.targets,
        ports_json=request.ports,
        flags_json=request.flags.model_dump(),
        ghost_window=request.ghost_window,
        tls_warning_days=request.tls_warning_days,
        alert_config_json=(
            request.alert_config.model_dump() if request.alert_config else None
        ),
        alerts_muted=request.alerts_muted,
    )
    session.add(scan)
    session.commit()
    session.refresh(scan)

    return _build_scan_response(scan, session, targets=scan.targets)


@router.get("")
def list_scans(session: SessionDep) -> list[ScanResponse]:
    stmt = select(Scan).where(Scan.deleted_at == None)
    scans = session.exec(stmt).all()
    return [_build_scan_response(s, session) for s in scans]


@router.put("/{id}")
def update_scan(
    id: Annotated[str, Path()], request: ScanCreateRequest, session: SessionDep
) -> ScanResponse:
    scan = session.get(Scan, id)
    if not scan or scan.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Scan not found")

    scan.name = request.name
    scan.cron_expression = request.cron_expression
    scan.targets = request.targets
    scan.ports_json = request.ports
    scan.flags_json = request.flags.model_dump()
    scan.ghost_window = request.ghost_window
    scan.tls_warning_days = request.tls_warning_days
    scan.alert_config_json = (
        request.alert_config.model_dump() if request.alert_config else None
    )
    scan.alerts_muted = request.alerts_muted
    session.add(scan)
    session.commit()
    session.refresh(scan)

    return _build_scan_response(scan, session, targets=scan.targets)


@router.patch("/{id}", response_model=ScanResponse)
def patch_scan(
    id: Annotated[str, Path()],
    request: ScanUpdateRequest,
    session: SessionDep,
) -> ScanResponse:
    scan = session.get(Scan, id)
    if not scan or scan.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Scan not found")

    fields_set = request.model_fields_set
    if "name" in fields_set and request.name is not None:
        scan.name = request.name
    if "cron_expression" in fields_set:
        scan.cron_expression = request.cron_expression
    if "is_active" in fields_set and request.is_active is not None:
        scan.is_active = request.is_active
    if "targets" in fields_set and request.targets is not None:
        scan.targets = request.targets
    if "ports" in fields_set and request.ports is not None:
        scan.ports_json = request.ports
    if "flags" in fields_set and request.flags is not None:
        scan.flags_json = request.flags.model_dump()
    if "ghost_window" in fields_set and request.ghost_window is not None:
        scan.ghost_window = request.ghost_window
    if "tls_warning_days" in fields_set and request.tls_warning_days is not None:
        scan.tls_warning_days = request.tls_warning_days
    if "alert_config" in fields_set:
        scan.alert_config_json = (
            request.alert_config.model_dump() if request.alert_config else None
        )
    if "alerts_muted" in fields_set and request.alerts_muted is not None:
        scan.alerts_muted = request.alerts_muted

    session.add(scan)
    session.commit()
    session.refresh(scan)

    return _build_scan_response(scan, session, targets=scan.targets)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scan(id: Annotated[str, Path()], session: SessionDep):
    scan = session.get(Scan, id)
    if not scan or scan.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Scan not found")
        
    scan.deleted_at = datetime.now(timezone.utc)
    scan.is_active = False
    session.add(scan)
    session.commit()

@router.post("/{id}/launch", status_code=status.HTTP_201_CREATED)
async def launch_scheduled_scan(
    id: Annotated[str, Path()],
    session: SessionDep,
    request: Request,
) -> ScanRunResponse:
    from api.routers.runs import LaunchRunRequest, create_run

    return await create_run(LaunchRunRequest(scan_id=id), session, request)

