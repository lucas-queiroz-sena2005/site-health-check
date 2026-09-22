import asyncio
from collections.abc import AsyncIterable
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, Request, status
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import Field as PydanticField
from sqlmodel import col, desc, select

from api.database import SessionDep
from api.models import ExecutionConfig, ExecutionFlags, Scan, ScanRun, ScanRunStatus

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

def _ingest_results(run_id: str, tmp_path: str, returncode: int) -> None:
    """Sync DB ingestion — runs in a thread via asyncio.to_thread()."""
    import json

    from sqlmodel import Session

    from api.database import engine as db_engine
    from api.models import (
        HostState,
        HttpRoutingCheck,
        PortState,
        ScanRun,
        ScanRunStatus,
        TlsCertificate,
    )

    with Session(db_engine) as session:
        run = session.get(ScanRun, run_id)
        if not run:
            return

        run.finished_at = datetime.now(timezone.utc)

        if returncode != 0:
            run.status = ScanRunStatus.FAILED
            session.commit()
            return

        run.status = ScanRunStatus.COMPLETED
        try:
            with open(tmp_path, "r") as f:
                results = json.load(f)

            for ip, host_data in results.items():
                host_state = HostState(
                    scan_run_id=run_id,
                    ip_address=ip,
                    metadata_resolved_from=host_data.get("metadata", {}).get("resolved_from"),
                    metadata_discovered_from_json=host_data.get("metadata", {}).get("discovered_from", [])
                )
                session.add(host_state)
                session.flush()  # assigns host_state.id without committing

                ports_dict = host_data.get("ports", {})
                for port_str, port_data in ports_dict.items():
                    port_state = PortState(
                        host_state_id=host_state.id,
                        port_number=int(port_str),
                        tcp_status=port_data.get("tcp_status", "closed"),
                        tcp_latency_ms=port_data.get("tcp_latency_ms")
                    )
                    session.add(port_state)
                    session.flush()  # assigns port_state.id without committing

                    tls = port_data.get("tls_certificate")
                    if tls:
                        tls_cert = TlsCertificate(
                            port_state_id=port_state.id,
                            valid=tls.get("valid", False),
                            expires_in_days=tls.get("expires_in_days", 0),
                            issuer=tls.get("issuer"),
                            protocol_version=tls.get("protocol_version"),
                            domains_discovered_sans_json=tls.get("domains_discovered_sans", [])
                        )
                        session.add(tls_cert)

                    routing = port_data.get("http_routing_checks", {})
                    for domain, r_data in routing.items():
                        route = HttpRoutingCheck(
                            port_state_id=port_state.id,
                            domain=domain,
                            status_code=r_data.get("status_code"),
                            http_latency_ms=r_data.get("http_latency_ms"),
                            path_checked=r_data.get("path_checked", "/"),
                            redirects_to_url=r_data.get("redirects_to_url"),
                            server_header=r_data.get("server_header"),
                            notes=r_data.get("notes")
                        )
                        session.add(route)

            # Metrics
            duration = 0.0
            if run.started_at and run.finished_at:
                started_at = run.started_at
                if started_at.tzinfo is None:
                    started_at = started_at.replace(tzinfo=timezone.utc)
                duration = round((run.finished_at - started_at).total_seconds(), 2)
            anomalies = 0
            for ip, host_data in results.items():
                for port_str, port_data in host_data.get("ports", {}).items():
                    if port_data.get("tcp_status") != "open":
                        anomalies += 1
                    tls = port_data.get("tls_certificate")
                    if tls and not tls.get("valid", True):
                        anomalies += 1
                    for domain, r_data in port_data.get("http_routing_checks", {}).items():
                        sc = r_data.get("status_code")
                        if sc and sc >= 400:
                            anomalies += 1

            run.metrics_json = {
                "total_targets_scanned": len(results),
                "scan_duration_seconds": duration,
                "anomalies_found": anomalies
            }
            session.commit()

        except Exception as parse_err:
            run.status = ScanRunStatus.FAILED
            run.metrics_json = {"error": str(parse_err)}
            session.commit()

async def run_engine_cli(run_id: str, snapshot: dict[str, Any], app_state: Any):
    tmp_path = None
    import os

    if not hasattr(app_state, "log_subscribers"):
        app_state.log_subscribers = {}
    if not hasattr(app_state, "run_logs"):
        app_state.run_logs = {}

    app_state.run_logs.setdefault(run_id, [])
    app_state.log_subscribers.setdefault(run_id, [])

    async def broadcast(event: ServerSentEvent | None):
        if event is not None:
            app_state.run_logs.setdefault(run_id, []).append(event)
        subscribers = app_state.log_subscribers.get(run_id, [])
        for q in list(subscribers):
            await q.put(event)

    try:
        import tempfile

        from sqlmodel import Session

        from api.database import engine as db_engine
        from api.models import ScanRun, ScanRunStatus

        with Session(db_engine) as session:
            run = session.get(ScanRun, run_id)
            if run:
                run.status = ScanRunStatus.RUNNING
                if not run.started_at:
                    run.started_at = datetime.now(timezone.utc)
                session.add(run)
                session.commit()

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name

        cmd = ["python", "-u", "-m", "engine.cli"]
        
        targets = snapshot.get("targets", [])
        if targets:
            cmd.append(",".join(targets))
            
        ports = snapshot.get("ports", [])
        if ports:
            cmd.extend(["-p", ",".join(map(str, ports))])
            
        flags = snapshot.get("flags", {})
        if isinstance(flags, dict) and "flags" in flags:
            flags = flags["flags"]
        
        # Import the schema to read the metadata
        from api.models import ExecutionFlags
        fields = ExecutionFlags.model_fields
        
        for key, value in flags.items():
            if value is None or key not in fields:
                continue
                
            extra = fields[key].json_schema_extra or {}
            if not isinstance(extra, dict):
                continue
            cli_arg = extra.get("cli_arg")
            is_switch = extra.get("is_switch", False)
            
            if not isinstance(cli_arg, str):
                continue
                
            if is_switch and isinstance(value, bool):
                if value:
                    cmd.append(cli_arg)
                else:
                    cmd.append(cli_arg.replace("--", "--no-"))
            elif isinstance(value, list):
                for item in value:
                    cmd.extend([cli_arg, str(item)])
            else:
                cmd.extend([cli_arg, str(value)])
                
        cmd.extend(["-o", tmp_path])
                
        # Run the dynamically built command
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
        
        if process.stdout:
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                await broadcast(ServerSentEvent(data={"message": line.decode('utf-8').strip()}, event="log"))
                
        await process.wait()
        await broadcast(ServerSentEvent(data={"message": f"Run finished with code {process.returncode if process.returncode is not None else 1}"}, event="status"))

        # DB ingestion runs in a thread so the event loop stays free
        await asyncio.to_thread(_ingest_results, run_id, tmp_path, process.returncode if process.returncode is not None else 1)

    except Exception as e:
        await broadcast(ServerSentEvent(data={"message": f"Engine error: {e!s}"}, event="error"))
        from sqlmodel import Session

        from api.database import engine as db_engine
        from api.models import ScanRun, ScanRunStatus
        with Session(db_engine) as session:
            run = session.get(ScanRun, run_id)
            if run:
                run.status = ScanRunStatus.FAILED
                run.finished_at = datetime.now(timezone.utc)
                session.commit()
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
        await broadcast(None) # EOF marker

@router.post("/launch", status_code=status.HTTP_201_CREATED)
async def launch_run(
    config: LaunchRunRequest, 
    session: SessionDep,
    request: Request,
) -> ScanRunResponse:
    snapshot = config.model_dump(exclude={"scan_id"})
    run = ScanRun(
        scan_id=config.scan_id,
        execution_config_snapshot_json=snapshot,
        status=ScanRunStatus.PENDING,
        started_at=datetime.now(timezone.utc)
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    
    asyncio.create_task(run_engine_cli(run.id, snapshot, request.app.state))
    
    # Retrieve scan name if scan_id is present
    scan_name = None
    if run.scan_id:
        scan = session.get(Scan, run.scan_id)
        if scan:
            scan_name = scan.name

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
        flags=ExecutionFlags.model_validate(snapshot.get("flags", {}))
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
        runs.append(
            ScanRunResponse(
                id=run.id,
                scan_id=run.scan_id,
                scan_name=scan_name,
                status=run.status,
                started_at=run.started_at,
                finished_at=run.finished_at,
                metrics_json=run.metrics_json,
                targets=config.get("targets", []),
                ports=config.get("ports", []),
                flags=ExecutionFlags.model_validate(config.get("flags", {}))
            )
        )
    return runs

@router.get("/{id}/stream", response_class=EventSourceResponse)
async def stream_run_logs(
    id: Annotated[str, Path()], 
    request: Request
) -> AsyncIterable[ServerSentEvent]:
    app_state = request.app.state
    if not hasattr(app_state, "log_subscribers"):
        app_state.log_subscribers = {}
    if not hasattr(app_state, "run_logs"):
        app_state.run_logs = {}

    # Register queue BEFORE replaying history.
    # Without this, broadcast(None) can fire between replay and registration,
    # leaving queue.get() hanging forever.
    queue: asyncio.Queue[ServerSentEvent | None] = asyncio.Queue()
    app_state.log_subscribers.setdefault(id, []).append(queue)
    historical = list(app_state.run_logs.get(id, []))

    try:
        yield ServerSentEvent(data={"message": f"Attached to run {id} log stream"}, event="info")

        for past_event in historical:
            yield past_event

        # If run finished before we registered, broadcast(None) was missed.
        # DB check catches that edge case.
        from sqlmodel import Session

        from api.database import engine as db_engine
        from api.models import ScanRun, ScanRunStatus
        with Session(db_engine) as session:
            run = session.get(ScanRun, id)
            if run and run.status in (ScanRunStatus.COMPLETED, ScanRunStatus.FAILED):
                while not queue.empty():
                    event = queue.get_nowait()
                    if event is not None:
                        yield event
                return

        while True:
            event = await queue.get()
            if event is None:
                break
            yield event
    finally:
        subscribers = app_state.log_subscribers.get(id, [])
        if queue in subscribers:
            subscribers.remove(queue)

@router.get("/{id}/results")
def get_run_results(
    id: Annotated[str, Path()],
    session: SessionDep
) -> dict[str, Any]:
    from sqlmodel import select

    from api.models import HostState
    
    run = session.get(ScanRun, id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
        
    stmt = select(HostState).where(HostState.scan_run_id == id)
    hosts = session.exec(stmt).all()
    
    return {
        "results": hosts,
        "metadata": run.metrics_json or {}
    }
