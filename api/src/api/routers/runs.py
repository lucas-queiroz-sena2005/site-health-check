import asyncio
from collections.abc import AsyncIterable
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import Field as PydanticField
from sqlalchemy import String, func, or_
from sqlmodel import col, desc, select

from api.database import SessionDep
from api.models import (
    ExecutionConfig,
    ExecutionFlags,
    HostState,
    HttpRoutingCheck,
    PortState,
    Scan,
    ScanRun,
    ScanRunStatus,
    TlsCertificate,
)
from api.schemas import (
    HostDetailDTO,
    HostRowDTO,
    HttpCheckDetailDTO,
    HttpCheckRowDTO,
    Page,
    PortDetailDTO,
    ServiceRowDTO,
    TableQueryParams,
    TlsCertificateDetailDTO,
)

router = APIRouter(prefix="/runs", tags=["runs"])

class LaunchRunRequest(ExecutionConfig):
    scan_id: str | None = PydanticField(default=None, title="Associated Scan ID")

class ScanRunResponse(ExecutionConfig):
    id: str
    scan_id: str | None = None
    scan_name: str | None = None
    status: ScanRunStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    metrics_json: dict[str, Any] | None = None


@router.post("/{id}/abort", status_code=status.HTTP_202_ACCEPTED)
async def abort_run(
    id: Annotated[str, Path()],
    request: Request,
    session: SessionDep,
):
    run_manager = request.app.state.run_manager
    if run_manager.is_active(id):
        aborted = run_manager.abort_run(id)
        if not aborted:
            raise HTTPException(
                status_code=404,
                detail="Process exited before signal could be sent",
            )
        return {"message": "Abort signal sent to engine"}

    run = session.get(ScanRun, id)
    if run and run.status in (
        ScanRunStatus.COMPLETED,
        ScanRunStatus.FAILED,
        ScanRunStatus.ABORTED,
    ):
        raise HTTPException(
            status_code=409, detail=f"Run is already {run.status.value}"
        )
    raise HTTPException(status_code=404, detail="Run process not running locally")


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_run(
    config: LaunchRunRequest,
    session: SessionDep,
    request: Request,
) -> ScanRunResponse:
    scan_name = None
    if config.scan_id:
        scan = session.get(Scan, config.scan_id)
        if not scan or scan.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Scan not found")
        scan_name = scan.name

        targets = config.targets if config.targets else (scan.targets or [])
        if not targets:
            raise HTTPException(status_code=400, detail="Targets cannot be empty")

        fields_set = config.model_fields_set or set()
        ports = config.ports if "ports" in fields_set else (scan.ports_json or [80, 443])
        flags = config.flags.model_dump() if "flags" in fields_set else (scan.flags_json or {})
        ghost_window = config.ghost_window if "ghost_window" in fields_set else scan.ghost_window
        tls_warning_days = config.tls_warning_days if "tls_warning_days" in fields_set else scan.tls_warning_days
        prune_void_hosts = (
            config.prune_void_hosts
            if "prune_void_hosts" in fields_set
            else scan.prune_void_hosts
        )
        prune_closed_ports = (
            config.prune_closed_ports
            if "prune_closed_ports" in fields_set
            else scan.prune_closed_ports
        )
        alert_config = scan.alert_config_json

        snapshot = {
            "targets": targets,
            "ports": ports,
            "flags": flags,
            "ghost_window": ghost_window,
            "tls_warning_days": tls_warning_days,
            "alert_config": alert_config,
            "prune_void_hosts": prune_void_hosts,
            "prune_closed_ports": prune_closed_ports,
        }
    else:
        if not config.targets:
            raise HTTPException(status_code=400, detail="Targets cannot be empty")
        snapshot = config.model_dump(exclude={"scan_id"})

    run = ScanRun(
        scan_id=config.scan_id,
        execution_config_snapshot_json=snapshot,
        status=ScanRunStatus.PENDING,
        started_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    await request.app.state.run_manager.dispatch_run(
        run.id, snapshot, scan_id=config.scan_id
    )

    return ScanRunResponse(
        id=run.id,
        scan_id=run.scan_id,
        scan_name=scan_name,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        metrics_json=run.metrics_json,
        targets=snapshot.get("targets", []),
        ports=snapshot.get("ports", []),
        flags=ExecutionFlags.model_validate(snapshot.get("flags", {})),
        ghost_window=snapshot.get("ghost_window", "7d"),
        tls_warning_days=snapshot.get("tls_warning_days", 30),
    )

@router.get("")
def list_runs(
    session: SessionDep,
    scan_id: Annotated[str | None, Query()] = None,
    source: Annotated[str | None, Query(description="scheduled or ad-hoc")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0
) -> list[ScanRunResponse]:
    stmt = select(ScanRun, Scan.name).outerjoin(Scan, col(ScanRun.scan_id) == Scan.id)
    
    if scan_id:
        stmt = stmt.where(ScanRun.scan_id == scan_id)
        
    if source == "scheduled":
        stmt = stmt.where(ScanRun.scan_id != None)
    elif source == "ad-hoc":
        stmt = stmt.where(ScanRun.scan_id == None)
        
    stmt = stmt.order_by(desc(ScanRun.started_at)).offset(offset).limit(limit)
    results = session.exec(stmt).all()
    
    runs = []
    for row in results:
        if isinstance(row, (tuple, list)) or hasattr(row, '__getitem__'):
            run = row[0]
            scan_name = row[1] if len(row) > 1 else None
        else:
            run = getattr(row, "ScanRun", row)
            scan_name = getattr(row, "name", None)

        if run is None:
            continue

        config = run.execution_config_snapshot_json or {}
        started_at = run.started_at
        if started_at and started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        finished_at = run.finished_at
        if finished_at and finished_at.tzinfo is None:
            finished_at = finished_at.replace(tzinfo=timezone.utc)

        runs.append(
            ScanRunResponse(
                id=run.id,
                scan_id=run.scan_id,
                scan_name=scan_name,
                status=run.status,
                started_at=started_at,
                finished_at=finished_at,
                metrics_json=run.metrics_json,
                targets=config.get("targets", []),
                ports=config.get("ports", []),
                flags=ExecutionFlags.model_validate(config.get("flags", {})),
                ghost_window=config.get("ghost_window", "7d"),
                tls_warning_days=config.get("tls_warning_days", 30),
            )
        )
    return runs

@router.get("/{id}", response_model=ScanRunResponse)
def get_run(
    id: Annotated[str, Path()],
    session: SessionDep
) -> ScanRunResponse:
    run = session.get(ScanRun, id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    config = run.execution_config_snapshot_json or {}
    scan_name = None
    if run.scan_id:
        scan = session.get(Scan, run.scan_id)
        if scan:
            scan_name = scan.name
    started_at = run.started_at
    if started_at and started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    finished_at = run.finished_at
    if finished_at and finished_at.tzinfo is None:
        finished_at = finished_at.replace(tzinfo=timezone.utc)

    return ScanRunResponse(
        id=run.id,
        scan_id=run.scan_id,
        scan_name=scan_name,
        status=run.status,
        started_at=started_at,
        finished_at=finished_at,
        metrics_json=run.metrics_json,
        targets=config.get("targets", []),
        ports=config.get("ports", []),
        flags=ExecutionFlags.model_validate(config.get("flags", {})),
        ghost_window=config.get("ghost_window", "7d"),
        tls_warning_days=config.get("tls_warning_days", 30),
    )

@router.get("/{id}/stream", response_class=EventSourceResponse)
async def stream_run_logs(
    id: Annotated[str, Path()],
    request: Request,
    session: SessionDep,
) -> AsyncIterable[ServerSentEvent]:
    run_manager = request.app.state.run_manager
    run = session.get(ScanRun, id)
    is_finished = run is not None and run.status in (
        ScanRunStatus.COMPLETED,
        ScanRunStatus.FAILED,
        ScanRunStatus.ABORTED,
    )
    async for event in run_manager.subscribe_logs(id, is_finished=is_finished):
        yield event


@router.get("/{id}/hosts", response_model=Page[HostRowDTO])
def get_run_hosts(
    id: Annotated[str, Path()],
    session: SessionDep,
    params: Annotated[TableQueryParams, Depends()],
) -> Page[HostRowDTO]:
    run = session.get(ScanRun, id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    stmt = select(HostState).where(HostState.scan_run_id == id)

    if params.ip:
        stmt = stmt.where(HostState.ip_address.like(f"{params.ip}%"))

    stmt = params.apply_status_filter(stmt, HostState.status)

    if params.finding:
        stmt = stmt.where(col(HostState.finding_codes).contains(f'"{params.finding}"'))

    if params.q:
        q_pattern = f"%{params.q}%"
        stmt = stmt.where(
            or_(
                HostState.ip_address.like(q_pattern),
                col(HostState.resolved_domains).like(q_pattern),
                col(HostState.finding_codes).like(q_pattern),
            )
        )

    total = session.exec(select(func.count()).select_from(stmt.subquery())).one()

    sort_column_map = {
        "ip_address": HostState.ip_sort_key,
        "host": HostState.ip_sort_key,
        "status": HostState.status,
        "depth": HostState.depth,
        "vhost_count": HostState.vhost_count,
        "open_port_count": HostState.open_port_count,
        "scanned_port_count": HostState.scanned_port_count,
        "min_tcp_latency_ms": HostState.min_tcp_latency_ms,
        "latency": HostState.min_tcp_latency_ms,
        "min_tls_expires_days": HostState.min_tls_expires_days,
        "tls": HostState.min_tls_expires_days,
        "tls_expires": HostState.min_tls_expires_days,
        "worst_tls_version": HostState.worst_tls_version,
        "worst_http_status": HostState.worst_http_status,
        "http": HostState.worst_http_status,
    }
    stmt = params.apply_sort_and_paginate(stmt, sort_column_map, HostState.ip_sort_key)
    hosts = session.exec(stmt).all()

    items = [
        HostRowDTO(
            ip_address=h.ip_address,
            status=h.status,
            depth=h.depth,
            vhost_count=h.vhost_count,
            open_port_count=h.open_port_count,
            scanned_port_count=h.scanned_port_count,
            min_tcp_latency_ms=h.min_tcp_latency_ms,
            min_tls_expires_days=h.min_tls_expires_days,
            worst_tls_version=h.worst_tls_version,
            worst_http_status=h.worst_http_status,
            finding_codes=h.finding_codes or [],
        )
        for h in hosts
    ]

    return Page[HostRowDTO](
        items=items,
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


@router.get("/{id}/hosts/{ip}", response_model=HostDetailDTO)
def get_run_host_detail(
    id: Annotated[str, Path()],
    ip: Annotated[str, Path()],
    session: SessionDep,
) -> HostDetailDTO:
    run = session.get(ScanRun, id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    host = session.exec(
        select(HostState).where(HostState.scan_run_id == id, HostState.ip_address == ip)
    ).first()
    if not host:
        raise HTTPException(status_code=404, detail=f"Host '{ip}' not found in run '{id}'")

    ports = session.exec(
        select(PortState)
        .where(PortState.host_state_id == host.id)
        .order_by(PortState.port_number.asc())
    ).all()

    services_dto: list[PortDetailDTO] = []
    checks_dto: list[HttpCheckDetailDTO] = []
    tls_sans_set: set[str] = set()

    for p in ports:
        cert_dto = None
        if p.tls_certificate:
            cert = p.tls_certificate
            cert_dto = TlsCertificateDetailDTO(
                valid=cert.valid,
                expires_in_days=cert.expires_in_days,
                issuer=cert.issuer,
                protocol_version=cert.protocol_version,
                domains_discovered_sans_json=cert.domains_discovered_sans_json or [],
            )
            for san in cert.domains_discovered_sans_json or []:
                if san:
                    tls_sans_set.add(san)

        services_dto.append(
            PortDetailDTO(
                port_number=p.port_number,
                tcp_status=p.tcp_status,
                tcp_latency_ms=p.tcp_latency_ms,
                status=p.status,
                san_count=p.san_count,
                http_check_count=p.http_check_count,
                worst_http_status=p.worst_http_status,
                finding_codes=p.finding_codes or [],
                tls_certificate=cert_dto,
            )
        )

        for c in sorted(p.http_routing_checks or [], key=lambda x: (x.domain or "", x.status_code or 0)):
            checks_dto.append(
                HttpCheckDetailDTO(
                    port=p.port_number,
                    domain=c.domain,
                    status=c.status,
                    status_code=c.status_code,
                    http_latency_ms=c.http_latency_ms,
                    redirects_to_url=c.redirects_to_url,
                    server_header=c.server_header,
                    notes=c.notes,
                    finding_code=c.finding_code,
                )
            )

    return HostDetailDTO(
        ip_address=host.ip_address,
        status=host.status,
        depth=host.depth,
        root_target=host.subrun_id,
        resolved_domains=host.resolved_domains or [],
        discovered_from=host.discovered_from or [],
        open_port_count=host.open_port_count,
        scanned_port_count=host.scanned_port_count,
        vhost_count=host.vhost_count,
        min_tcp_latency_ms=host.min_tcp_latency_ms,
        min_tls_expires_days=host.min_tls_expires_days,
        worst_tls_version=host.worst_tls_version,
        worst_http_status=host.worst_http_status,
        finding_codes=host.finding_codes or [],
        tls_sans=sorted(tls_sans_set),
        services=services_dto,
        checks=checks_dto,
    )


@router.get("/{id}/services", response_model=Page[ServiceRowDTO])
def get_run_services(
    id: Annotated[str, Path()],
    session: SessionDep,
    params: Annotated[TableQueryParams, Depends()],
) -> Page[ServiceRowDTO]:
    run = session.get(ScanRun, id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    stmt = (
        select(PortState, HostState, TlsCertificate)
        .join(HostState, col(PortState.host_state_id) == col(HostState.id))
        .outerjoin(TlsCertificate, col(TlsCertificate.port_state_id) == col(PortState.id))
        .where(HostState.scan_run_id == id)
    )

    if not params.include_closed:
        stmt = stmt.where(PortState.status != "void")

    if params.ip:
        stmt = stmt.where(HostState.ip_address.like(f"{params.ip}%"))

    if params.port is not None:
        stmt = stmt.where(PortState.port_number == params.port)

    stmt = params.apply_status_filter(stmt, PortState.status)

    if params.finding:
        stmt = stmt.where(col(PortState.finding_codes).contains(f'"{params.finding}"'))

    if params.q:
        q_pattern = f"%{params.q}%"
        stmt = stmt.where(
            or_(
                HostState.ip_address.like(q_pattern),
                col(PortState.port_number).cast(String).like(q_pattern),
                col(PortState.finding_codes).like(q_pattern),
                col(TlsCertificate.issuer).like(q_pattern),
                col(TlsCertificate.protocol_version).like(q_pattern),
            )
        )

    total = session.exec(select(func.count()).select_from(stmt.subquery())).one()

    sort_column_map = {
        "ip_address": HostState.ip_sort_key,
        "host": HostState.ip_sort_key,
        "port": PortState.port_number,
        "depth": HostState.depth,
        "status": PortState.status,
        "tcp_latency_ms": PortState.tcp_latency_ms,
        "latency": PortState.tcp_latency_ms,
        "tls_valid": TlsCertificate.valid,
        "tls_expires_in_days": TlsCertificate.expires_in_days,
        "tls": TlsCertificate.expires_in_days,
        "tls_expires": TlsCertificate.expires_in_days,
        "tls_version": TlsCertificate.protocol_version,
        "tls_issuer": TlsCertificate.issuer,
        "issuer": TlsCertificate.issuer,
        "san_count": PortState.san_count,
        "http_check_count": PortState.http_check_count,
        "worst_http_status": PortState.worst_http_status,
        "http": PortState.worst_http_status,
    }
    stmt = params.apply_sort_and_paginate(
        stmt, sort_column_map, HostState.ip_sort_key, PortState.port_number.asc()
    )
    rows = session.exec(stmt).all()

    items = []
    for port, host, cert in rows:
        items.append(
            ServiceRowDTO(
                ip_address=host.ip_address,
                port=port.port_number,
                status=port.status,
                depth=host.depth,
                tcp_latency_ms=port.tcp_latency_ms,
                tls_valid=cert.valid if cert else None,
                tls_expires_in_days=cert.expires_in_days if cert else None,
                tls_version=cert.protocol_version if cert else None,
                tls_issuer=cert.issuer if cert else None,
                san_count=port.san_count,
                http_check_count=port.http_check_count,
                worst_http_status=port.worst_http_status,
                finding_codes=port.finding_codes or [],
            )
        )

    return Page[ServiceRowDTO](
        items=items,
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


@router.get("/{id}/checks", response_model=Page[HttpCheckRowDTO])
def get_run_checks(
    id: Annotated[str, Path()],
    session: SessionDep,
    params: Annotated[TableQueryParams, Depends()],
) -> Page[HttpCheckRowDTO]:
    run = session.get(ScanRun, id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    stmt = (
        select(HttpRoutingCheck, PortState.port_number, HostState.ip_address, HostState.ip_sort_key)
        .join(PortState, col(HttpRoutingCheck.port_state_id) == col(PortState.id))
        .join(HostState, col(PortState.host_state_id) == col(HostState.id))
        .where(HostState.scan_run_id == id)
    )

    if params.ip:
        stmt = stmt.where(HostState.ip_address.like(f"{params.ip}%"))

    if params.port is not None:
        stmt = stmt.where(PortState.port_number == params.port)

    stmt = params.apply_status_filter(stmt, HttpRoutingCheck.status)

    if params.finding:
        stmt = stmt.where(HttpRoutingCheck.finding_code == params.finding)

    if params.q:
        q_pattern = f"%{params.q}%"
        stmt = stmt.where(
            or_(
                HostState.ip_address.like(q_pattern),
                HttpRoutingCheck.domain.like(q_pattern),
                HttpRoutingCheck.redirects_to_url.like(q_pattern),
                HttpRoutingCheck.server_header.like(q_pattern),
                HttpRoutingCheck.notes.like(q_pattern),
                HttpRoutingCheck.finding_code.like(q_pattern),
            )
        )

    total = session.exec(select(func.count()).select_from(stmt.subquery())).one()

    sort_column_map = {
        "ip_address": HostState.ip_sort_key,
        "host": HostState.ip_sort_key,
        "port": PortState.port_number,
        "domain": HttpRoutingCheck.domain,
        "status": HttpRoutingCheck.status,
        "status_code": HttpRoutingCheck.status_code,
        "http_latency_ms": HttpRoutingCheck.http_latency_ms,
        "latency": HttpRoutingCheck.http_latency_ms,
        "redirects_to_url": HttpRoutingCheck.redirects_to_url,
        "redirect": HttpRoutingCheck.redirects_to_url,
        "server_header": HttpRoutingCheck.server_header,
        "server": HttpRoutingCheck.server_header,
        "finding_code": HttpRoutingCheck.finding_code,
        "finding": HttpRoutingCheck.finding_code,
    }
    stmt = params.apply_sort_and_paginate(
        stmt,
        sort_column_map,
        HostState.ip_sort_key,
        PortState.port_number.asc(),
        HttpRoutingCheck.domain.asc(),
    )
    rows = session.exec(stmt).all()

    items = [
        HttpCheckRowDTO(
            ip_address=ip_addr,
            port=port_num,
            domain=check.domain,
            status=check.status,
            status_code=check.status_code,
            http_latency_ms=check.http_latency_ms,
            redirects_to_url=check.redirects_to_url,
            server_header=check.server_header,
            notes=check.notes,
            finding_code=check.finding_code,
        )
        for check, port_num, ip_addr, _ in rows
    ]

    return Page[HttpCheckRowDTO](
        items=items,
        total=total,
        limit=params.limit,
        offset=params.offset,
    )
