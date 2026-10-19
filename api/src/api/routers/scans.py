import asyncio
from datetime import datetime, timezone
from typing import Annotated, Any

import croniter
from fastapi import APIRouter, BackgroundTasks, HTTPException, Path, Request, status
from fastapi.responses import HTMLResponse
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
    ScanTargetGroupLink,
    TargetGroup,
)
from api.routers.runs import ScanRunResponse, run_engine_cli
from api.services.alerts import dispatch_mute_status_notification
from api.services.scheduler import run_scheduled_scan_with_alerts

router = APIRouter(prefix="/scans", tags=["scans"])

class ScanCreateRequest(ExecutionConfig):
    name: str
    cron_expression: str | None = None
    alert_config: AlertConfig | None = None
    alerts_muted: bool = False

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
        targets = []
        for tg in scan.target_groups:
            targets.extend(tg.targets_json)

    run_stmt = (
        select(ScanRun)
        .where(ScanRun.scan_id == scan.id)
        .order_by(desc(ScanRun.started_at))
        .limit(1)
    )
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
    # 1. Create an ad-hoc target group for these targets
    target_group = TargetGroup(
        name=f"Ad-hoc Target Group for {request.name}",
        is_ad_hoc=True,
        targets_json=request.targets,
    )
    session.add(target_group)

    # 2. Create the scan
    scan = Scan(
        name=request.name,
        cron_expression=request.cron_expression,
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

    session.commit()  # Commit to get IDs

    # 3. Link them
    link = ScanTargetGroupLink(
        scan_id=scan.id,
        target_group_id=target_group.id,
    )
    session.add(link)
    session.commit()
    session.refresh(scan)

    return _build_scan_response(scan, session, targets=request.targets)


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
    scan.ports_json = request.ports
    scan.flags_json = request.flags.model_dump()
    scan.ghost_window = request.ghost_window
    scan.tls_warning_days = request.tls_warning_days
    scan.alert_config_json = (
        request.alert_config.model_dump() if request.alert_config else None
    )
    scan.alerts_muted = request.alerts_muted
    session.add(scan)

    # Update targets (delete old links, recreate ad-hoc)
    for tg in scan.target_groups:
        if tg.is_ad_hoc:
            session.delete(tg)
    scan.target_groups = []

    target_group = TargetGroup(
        name=f"Ad-hoc Target Group for {request.name}",
        is_ad_hoc=True,
        targets_json=request.targets,
    )
    session.add(target_group)
    session.commit()

    link = ScanTargetGroupLink(
        scan_id=scan.id,
        target_group_id=target_group.id,
    )
    session.add(link)
    session.commit()
    session.refresh(scan)

    return _build_scan_response(scan, session, targets=request.targets)


@router.post("/{id}/alerts/mute", response_model=ScanResponse)
def mute_scan_alerts(
    id: Annotated[str, Path()],
    session: SessionDep,
) -> ScanResponse:
    scan = session.get(Scan, id)
    if not scan or scan.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Scan not found")
    scan.alerts_muted = True
    session.add(scan)
    session.commit()
    session.refresh(scan)
    return _build_scan_response(scan, session)


@router.post("/{id}/alerts/unmute", response_model=ScanResponse)
def unmute_scan_alerts(
    id: Annotated[str, Path()],
    session: SessionDep,
) -> ScanResponse:
    scan = session.get(Scan, id)
    if not scan or scan.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Scan not found")
    scan.alerts_muted = False
    session.add(scan)
    session.commit()
    session.refresh(scan)
    return _build_scan_response(scan, session)


@router.get("/{id}/alerts/mute", response_class=HTMLResponse)
def get_mute_scan_alerts(
    id: Annotated[str, Path()],
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> HTMLResponse:
    scan = session.get(Scan, id)
    if not scan or scan.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Scan not found")
    was_muted = scan.alerts_muted
    scan.alerts_muted = True
    session.add(scan)
    session.commit()
    if not was_muted:
        background_tasks.add_task(dispatch_mute_status_notification, scan, True)
    unmute_url = f"/api/scans/{scan.id}/alerts/unmute"
    dashboard_url = f"{settings.app_base_url}/scheduled-runs"
    html_content = (
        "<!DOCTYPE html>"
        "<html>"
        "<head><title>Alerts Muted</title><meta name='viewport' content='width=device-width, initial-scale=1'></head>"
        "<body style='font-family: system-ui, -apple-system, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; background: #f8fafc; color: #0f172a;'>"
        "<div style='background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 24px 32px; max-width: 480px; text-align: center; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);'>"
        "<h2 style='margin: 0 0 12px; font-size: 20px;'>Alerts Muted</h2>"
        f"<p style='margin: 0 0 20px; color: #475569; font-size: 15px;'>Automated alerts for schedule <strong>{scan.name}</strong> have been turned off.</p>"
        "<div style='display: flex; gap: 12px; justify-content: center;'>"
        f"<a href='{unmute_url}' style='display: inline-block; padding: 8px 16px; background: #0f172a; color: white; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 14px;'>Turn Back On</a>"
        f"<a href='{dashboard_url}' style='display: inline-block; padding: 8px 16px; background: #e2e8f0; color: #0f172a; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 14px;'>Open Dashboard</a>"
        "</div>"
        "</div>"
        "</body>"
        "</html>"
    )
    return HTMLResponse(content=html_content)


@router.get("/{id}/alerts/unmute", response_class=HTMLResponse)
def get_unmute_scan_alerts(
    id: Annotated[str, Path()],
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> HTMLResponse:
    scan = session.get(Scan, id)
    if not scan or scan.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Scan not found")
    was_muted = scan.alerts_muted
    scan.alerts_muted = False
    session.add(scan)
    session.commit()
    if was_muted:
        background_tasks.add_task(dispatch_mute_status_notification, scan, False)
    mute_url = f"/api/scans/{scan.id}/alerts/mute"
    dashboard_url = f"{settings.app_base_url}/scheduled-runs"
    html_content = (
        "<!DOCTYPE html>"
        "<html>"
        "<head><title>Alerts Active</title><meta name='viewport' content='width=device-width, initial-scale=1'></head>"
        "<body style='font-family: system-ui, -apple-system, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; background: #f8fafc; color: #0f172a;'>"
        "<div style='background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 24px 32px; max-width: 480px; text-align: center; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);'>"
        "<h2 style='margin: 0 0 12px; font-size: 20px;'>Alerts Active</h2>"
        f"<p style='margin: 0 0 20px; color: #475569; font-size: 15px;'>Automated alerts for schedule <strong>{scan.name}</strong> are now active.</p>"
        "<div style='display: flex; gap: 12px; justify-content: center;'>"
        f"<a href='{mute_url}' style='display: inline-block; padding: 8px 16px; background: #dc2626; color: white; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 14px;'>Mute Alerts</a>"
        f"<a href='{dashboard_url}' style='display: inline-block; padding: 8px 16px; background: #e2e8f0; color: #0f172a; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 14px;'>Open Dashboard</a>"
        "</div>"
        "</div>"
        "</body>"
        "</html>"
    )
    return HTMLResponse(content=html_content)

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
    scan = session.get(Scan, id)
    if not scan or scan.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Scan not found")
        
    targets = []
    for tg in scan.target_groups:
        targets.extend(tg.targets_json)
        
    snapshot = {
        "targets": targets,
        "ports": scan.ports_json or [80, 443],
        "flags": scan.flags_json or {},
        "ghost_window": scan.ghost_window,
        "tls_warning_days": scan.tls_warning_days,
        "alert_config": scan.alert_config_json,
    }
    
    run = ScanRun(
        scan_id=scan.id,
        execution_config_snapshot_json=snapshot,
        status=ScanRunStatus.PENDING,
        started_at=datetime.now(timezone.utc)
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    
    asyncio.create_task(run_scheduled_scan_with_alerts(run.id, snapshot, request.app.state))
    
    return ScanRunResponse(
        id=run.id,
        scan_id=run.scan_id,
        scan_name=scan.name,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        metrics_json=run.metrics_json,
        targets=targets,
        ports=scan.ports_json or [80, 443],
        flags=ExecutionFlags.model_validate(scan.flags_json or {}),
        ghost_window=scan.ghost_window,
        tls_warning_days=scan.tls_warning_days,
    )

