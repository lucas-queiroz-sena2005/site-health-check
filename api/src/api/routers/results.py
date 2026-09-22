import re
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import Session, and_, col, func, select

from api.config import settings
from api.database import get_session
from api.models import HostState, PortState, ScanRun
from api.services.aggregation import aggregate_void_nodes

router = APIRouter(prefix="/results", tags=["results"])

SessionDep = Annotated[Session, Depends(get_session)]

class TargetSummary(BaseModel):
    target: str
    total_ips: int
    active_ips: int

def parse_ghost_window(
    ghost_window: Annotated[
        str | None, 
        Query(description="Time window for ghost aging (e.g., '7d', '24h', '30m')")
    ] = None
) -> timedelta | None:
    window_str = ghost_window if ghost_window is not None else settings.default_ghost_window
    if not window_str:
        return None
    
    match = re.fullmatch(r"^(\d+)([smhd])$", window_str.strip().lower())
    if not match:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid ghost_window format. Must match '<int>[s|m|h|d]' (e.g., '7d', '24h')."
        )
    
    amount, unit = int(match.group(1)), match.group(2)
    units = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
    return timedelta(**{units[unit]: amount})

GhostWindowDep = Annotated[timedelta | None, Depends(parse_ghost_window)]

@router.get("/summary")
def get_results_summary(
    session: SessionDep,
    run_id: str | None = None
) -> list[TargetSummary]:
    statement = (
        select(
            HostState.metadata_resolved_from,
            func.count(col(HostState.id).distinct()).label("total_ips"),
            func.count(col(PortState.id).distinct()).label("active_ports")
        )
        .outerjoin(PortState, and_(
            col(HostState.id) == col(PortState.host_state_id), 
            col(PortState.tcp_status) == "open"
        ))
    )
    
    if run_id is not None:
        statement = statement.where(HostState.scan_run_id == run_id)
        
    statement = statement.group_by(HostState.metadata_resolved_from)
    results = session.exec(statement).all()
    
    summaries = []
    for row in results:
        target, total, active = row
        summaries.append(TargetSummary(
            target=target or "unknown",
            total_ips=total,
            active_ips=active
        ))
    return summaries

@router.get("")
def get_results(
    session: SessionDep,
    ghost_window: GhostWindowDep,
    run_id: str | None = None,
    ip_address: str | None = None,
    resolved_from: str | None = None,
    status: str | None = None
) -> list[HostState]:
    statement = select(HostState)
    if run_id is not None:
        statement = statement.where(HostState.scan_run_id == run_id)
    if ip_address is not None:
        statement = statement.where(HostState.ip_address == ip_address)
    if resolved_from is not None:
        statement = statement.where(HostState.metadata_resolved_from == resolved_from)
        
    if status == "active":
        statement = statement.join(PortState).where(PortState.tcp_status == "open").distinct()
        
    results = session.exec(statement).all()
    
    historical_active_ips = set()
    if ghost_window is not None:
        cutoff = datetime.now(timezone.utc) - ghost_window
        # Find all IPs that had an open port in a run started after the cutoff
        historical_stmt = (
            select(HostState.ip_address)
            .join(PortState, col(HostState.id) == col(PortState.host_state_id))
            .join(ScanRun, col(HostState.scan_run_id) == col(ScanRun.id))
            .where(PortState.tcp_status == "open")
            .where(col(ScanRun.started_at) >= cutoff)
            .distinct()
        )
        # We only care about IPs in the current result set
        current_ips = [r.ip_address for r in results]
        if current_ips:
            historical_stmt = historical_stmt.where(col(HostState.ip_address).in_(current_ips))
            historical_active_ips = set(session.exec(historical_stmt).all())
            
    # Apply void aggregation if we are returning a raw list of results (not explicitly filtering to active-only)
    if status != "active":
        results = aggregate_void_nodes(list(results), historical_active_ips)
        
    return list(results)
