import asyncio
import logging
from datetime import UTC, datetime

import croniter
from sqlmodel import Session, col, desc, select

from api.config import settings
from api.database import engine
from api.models import Scan, ScanRun, ScanRunStatus

logger = logging.getLogger("scheduler")


async def check_and_run_scheduled_scans(app_state):
    tz = settings.get_tz()
    with Session(engine) as session:
        stmt = select(Scan).where(
            Scan.is_active == True,
            Scan.deleted_at == None,
            Scan.cron_expression != None
        )
        scans = session.exec(stmt).all()
        now = datetime.now(tz)
        
        for scan in scans:
            if not scan.cron_expression:
                continue
                
            try:
                # Check for active running or pending runs for this scan
                active_run_stmt = select(ScanRun).where(
                    ScanRun.scan_id == scan.id,
                    col(ScanRun.status).in_([ScanRunStatus.PENDING, ScanRunStatus.RUNNING])
                )
                if session.exec(active_run_stmt).first():
                    continue

                # Get the most recent run
                latest_run_stmt = select(ScanRun).where(
                    ScanRun.scan_id == scan.id
                ).order_by(desc(ScanRun.started_at)).limit(1)
                latest_run = session.exec(latest_run_stmt).first()
                
                should_run = False
                if latest_run and latest_run.started_at:
                    lr_started = latest_run.started_at
                    if lr_started.tzinfo is None:
                        lr_started = lr_started.replace(tzinfo=UTC)
                    lr_started_tz = lr_started.astimezone(tz)
                    # Prevent running multiple times in the same minute
                    if (now - lr_started_tz).total_seconds() < 55:
                        continue
                    it = croniter.croniter(scan.cron_expression, lr_started_tz)
                    next_run = it.get_next(datetime)
                    if next_run.tzinfo is None:
                        next_run = next_run.replace(tzinfo=tz)
                    if now >= next_run:
                        should_run = True
                else:
                    # Never ran before - check if current minute matches cron expression
                    if croniter.croniter.match(scan.cron_expression, now):
                        should_run = True
                    else:
                        it = croniter.croniter(scan.cron_expression, now)
                        prev_run = it.get_prev(datetime)
                        if prev_run.tzinfo is None:
                            prev_run = prev_run.replace(tzinfo=tz)
                        if (now - prev_run).total_seconds() < 60:
                            should_run = True
                            
                if should_run:
                    logger.info(f"Triggering scheduled scan: {scan.name} ({scan.id})")
                    targets = scan.targets or []
                        
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
                        started_at=datetime.now(UTC)
                    )
                    session.add(run)
                    session.commit()
                    session.refresh(run)
                    
                    await app_state.run_manager.dispatch_run(
                        run.id, snapshot, scan_id=scan.id
                    )
            except Exception as e:
                logger.exception(f"Error checking schedule for scan {scan.id}: {e}", exc_info=True)

async def scheduler_loop(app_state):
    logger.info("Starting scheduled scan background runner...")
    while True:
        try:
            await check_and_run_scheduled_scans(app_state)
        except Exception as e:
            logger.exception(f"Error in scheduler loop: {e}", exc_info=True)
        await asyncio.sleep(10)
