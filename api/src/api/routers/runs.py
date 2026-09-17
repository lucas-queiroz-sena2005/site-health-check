import asyncio
from datetime import datetime, timezone
from typing import Annotated, Any
from collections.abc import AsyncIterable

from fastapi import APIRouter, HTTPException, Query, status, Path, Request, BackgroundTasks
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlmodel import select, desc

from api.models import ScanRun, ScanRunStatus, ExecutionConfig, Scan
from api.database import SessionDep

router = APIRouter(prefix="/runs", tags=["runs"])

class ScanRunResponse(ExecutionConfig):
    id: str
    scan_id: str | None = None
    scan_name: str | None = None
    status: ScanRunStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    metrics_json: dict[str, Any] | None = None

async def run_engine_cli(run_id: str, snapshot: dict[str, Any], request: Request):
    queue = asyncio.Queue()
    request.app.state.log_subscribers[run_id] = queue
    
    try:
        cmd = ["python", "-m", "engine.cli"]
        
        targets = snapshot.get("targets", [])
        if targets:
            cmd.append(",".join(targets))
            
        ports = snapshot.get("ports", [])
        if ports:
            cmd.extend(["-p", ",".join(map(str, ports))])
            
        flags = snapshot.get("flags", {})
        
        # Import the schema to read the metadata
        from api.models import ExecutionFlags
        fields = ExecutionFlags.model_fields
        
        for key, value in flags.items():
            if value is None or key not in fields:
                continue
                
            # Get our custom metadata!
            extra = fields[key].json_schema_extra or {}
            cli_arg = extra.get("cli_arg")
            is_switch = extra.get("is_switch", False)
            
            if not cli_arg:
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
                await queue.put(ServerSentEvent(data={"message": line.decode('utf-8').strip()}, event="log"))
                
        await process.wait()
        await queue.put(ServerSentEvent(data={"message": f"Run finished with code {process.returncode}"}, event="status"))
    except Exception as e:
        await queue.put(ServerSentEvent(data={"message": f"Engine error: {str(e)}"}, event="error"))
    finally:
        await queue.put(None) # EOF marker

@router.post("/launch", status_code=status.HTTP_201_CREATED)
def launch_run(
    config: ExecutionConfig, 
    session: SessionDep,
    request: Request,
    background_tasks: BackgroundTasks
) -> ScanRunResponse:
    snapshot = config.model_dump()
    run = ScanRun(
        execution_config_snapshot_json=snapshot,
        status=ScanRunStatus.PENDING
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    
    background_tasks.add_task(run_engine_cli, run.id, snapshot, request)
    
    return ScanRunResponse(
        id=run.id,
        scan_id=run.scan_id,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        metrics_json=run.metrics_json,
        **snapshot
    )

@router.get("")
def list_runs(
    session: SessionDep,
    scan_id: Annotated[str | None, Query()] = None,
    source: Annotated[str | None, Query(description="scheduled or ad-hoc")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0
) -> list[ScanRunResponse]:
    stmt = select(ScanRun, Scan.name).outerjoin(Scan, ScanRun.scan_id == Scan.id)
    
    if scan_id:
        stmt = stmt.where(ScanRun.scan_id == scan_id)
        
    if source == "scheduled":
        stmt = stmt.where(ScanRun.scan_id != None)
    elif source == "ad-hoc":
        stmt = stmt.where(ScanRun.scan_id == None)
        
    stmt = stmt.order_by(desc(ScanRun.started_at)).offset(offset).limit(limit)
    results = session.exec(stmt).all()
    
    return [
        ScanRunResponse(
            id=r.ScanRun.id,
            scan_id=r.ScanRun.scan_id,
            scan_name=r.name,
            status=r.ScanRun.status,
            started_at=r.ScanRun.started_at,
            finished_at=r.ScanRun.finished_at,
            metrics_json=r.ScanRun.metrics_json,
            **r.ScanRun.execution_config_snapshot_json
        ) for r in results
    ]

@router.get("/{id}/stream", response_class=EventSourceResponse)
async def stream_run_logs(
    id: Annotated[str, Path()], 
    request: Request
) -> AsyncIterable[ServerSentEvent]:
    if id not in request.app.state.log_subscribers:
        request.app.state.log_subscribers[id] = asyncio.Queue()
        
    queue = request.app.state.log_subscribers[id]
    
    yield ServerSentEvent(data={"message": f"Attached to run {id} log stream"}, event="info")
    while True:
        event = await queue.get()
        if event is None:
            break
        yield event

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
    
    return {"results": hosts}


