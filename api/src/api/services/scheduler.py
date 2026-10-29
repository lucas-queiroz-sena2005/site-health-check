import asyncio
import logging
from datetime import datetime, timedelta, timezone

import croniter
from sqlalchemy import and_, or_
from sqlmodel import Session, col, desc, select

from api.config import settings
from api.database import engine
from api.models import Scan, ScanRun, ScanRunStatus, SystemConfig

logger = logging.getLogger("scheduler")


def prune_expired_runs(session: Session, retention_days: int) -> int:
    """Prunes terminal ScanRuns older than retention_days, cascading to child records."""
    if retention_days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    terminal_statuses = [
        ScanRunStatus.COMPLETED,
        ScanRunStatus.FAILED,
        ScanRunStatus.ABORTED,
    ]
    expired_runs = session.exec(
        select(ScanRun).where(
            col(ScanRun.status).in_(terminal_statuses),
            or_(
                ScanRun.finished_at < cutoff,
                and_(ScanRun.finished_at == None, ScanRun.started_at < cutoff),
            ),
        )
    ).all()
    count = len(expired_runs)
    for run in expired_runs:
        session.delete(run)
    if count > 0:
        session.commit()
    return count


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

                # Get reference start time from either scan.last_triggered_at or the most recent run
                latest_run_stmt = select(ScanRun).where(
                    ScanRun.scan_id == scan.id
                ).order_by(desc(ScanRun.started_at)).limit(1)
                latest_run = session.exec(latest_run_stmt).first()

                ref_candidates: list[datetime] = []
                if scan.last_triggered_at:
                    ref_candidates.append(scan.last_triggered_at)
                if latest_run and latest_run.started_at:
                    ref_candidates.append(latest_run.started_at)

                should_run = False
                if ref_candidates:
                    lr_started = max(ref_candidates)
                    if lr_started.tzinfo is None:
                        lr_started = lr_started.replace(tzinfo=timezone.utc)
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
                    # Never ran or triggered before - check if current minute matches cron expression
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
                    scan.last_triggered_at = datetime.now(timezone.utc)
                    session.add(scan)
                    targets = scan.targets or []
                        
                    snapshot = {
                        "targets": targets,
                        "ports": scan.ports_json or [80, 443],
                        "flags": scan.flags_json or {},
                        "ghost_window": scan.ghost_window,
                        "tls_warning_days": scan.tls_warning_days,
                        "prune_void_hosts": scan.prune_void_hosts,
                        "prune_closed_ports": scan.prune_closed_ports,
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
                    
                    await app_state.run_manager.dispatch_run(
                        run.id, snapshot, scan_id=scan.id
                    )
            except (croniter.CroniterBadCronError, croniter.CroniterBadDateError, ValueError) as e:
                logger.warning(
                    f"Skipping scheduled scan {scan.id} due to invalid cron expression {scan.cron_expression!r}: {e}"
                )
            except Exception as e:
                logger.exception(f"Error checking schedule for scan {scan.id}: {e}", exc_info=True)

async def scheduler_loop(app_state):
    logger.info("Starting scheduled scan background runner...")
    while True:
        try:
            await check_and_run_scheduled_scans(app_state)
            with Session(engine) as session:
                cfg = session.get(SystemConfig, 1)
                if cfg and cfg.retention_days > 0:
                    pruned = prune_expired_runs(session, cfg.retention_days)
                    if pruned > 0:
                        logger.info("Background retention cleanup pruned %d expired run(s)", pruned)
        except Exception as e:
            logger.exception(f"Error in scheduler loop: {e}", exc_info=True)
        await asyncio.sleep(10)
