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

from api.services.runner import run_engine_cli
import signal

@router.post("/{id}/abort", status_code=status.HTTP_202_ACCEPTED)
async def abort_run(
    id: Annotated[str, Path()], 
    request: Request,
    session: SessionDep
):
    app_state = request.app.state
    if not hasattr(app_state, "processes"):
        raise HTTPException(status_code=404, detail="Run process not found in memory")
        
    process = app_state.processes.get(id)
    if not process:
        run = session.get(ScanRun, id)
        if run and run.status in (ScanRunStatus.COMPLETED, ScanRunStatus.FAILED, ScanRunStatus.ABORTED):
            raise HTTPException(status_code=409, detail=f"Run is already {run.status.value}")
        raise HTTPException(status_code=404, detail="Run process not running locally")
        
    try:
        process.send_signal(signal.SIGTERM)
        
        # Schedule a SIGKILL if it doesn't die in 10s
        async def force_kill():
            await asyncio.sleep(10)
            if process.returncode is None:
                try:
                    process.kill()
                except OSError:
                    pass
        asyncio.create_task(force_kill())
        
        return {"message": "Abort signal sent to engine"}
    except ProcessLookupError:
        raise HTTPException(status_code=404, detail="Process exited before signal could be sent")

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
