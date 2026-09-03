import asyncio
from datetime import datetime, timezone
from typing import Annotated, Any
from collections.abc import AsyncIterable

from fastapi import APIRouter, HTTPException, Query, status, Path, Request, BackgroundTasks
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlmodel import select, desc

from api.models import Job, JobStatus, ExecutionConfig
from api.database import SessionDep

router = APIRouter(prefix="/jobs", tags=["jobs"])

class JobResponse(ExecutionConfig):
    id: str
    schedule_id: str | None = None
    status: JobStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    metrics_json: dict[str, Any] | None = None

async def run_engine_cli(job_id: str, snapshot: dict[str, Any], request: Request):
    queue = asyncio.Queue()
    request.app.state.log_subscribers[job_id] = queue
    
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
        await queue.put(ServerSentEvent(data={"message": f"Job finished with code {process.returncode}"}, event="status"))
    except Exception as e:
        await queue.put(ServerSentEvent(data={"message": f"Engine error: {str(e)}"}, event="error"))
    finally:
        await queue.put(None) # EOF marker

@router.post("/launch", status_code=status.HTTP_201_CREATED)
def launch_job(
    config: ExecutionConfig, 
    session: SessionDep,
    request: Request,
    background_tasks: BackgroundTasks
) -> JobResponse:
    snapshot = config.model_dump()
    job = Job(
        execution_config_snapshot_json=snapshot,
        status=JobStatus.PENDING
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    
    background_tasks.add_task(run_engine_cli, job.id, snapshot, request)
    
    return JobResponse(
        id=job.id,
        schedule_id=job.schedule_id,
        status=job.status,
        started_at=job.started_at,
        finished_at=job.finished_at,
        metrics_json=job.metrics_json,
        **snapshot
    )

@router.get("")
def list_jobs(
    session: SessionDep,
    schedule_id: Annotated[str | None, Query()] = None,
    source: Annotated[str | None, Query(description="scheduled or ad-hoc")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0
) -> list[JobResponse]:
    stmt = select(Job)
    
    if schedule_id:
        stmt = stmt.where(Job.schedule_id == schedule_id)
        
    if source == "scheduled":
        stmt = stmt.where(Job.schedule_id != None)
    elif source == "ad-hoc":
        stmt = stmt.where(Job.schedule_id == None)
        
    stmt = stmt.order_by(desc(Job.started_at)).offset(offset).limit(limit)
    jobs = session.exec(stmt).all()
    
    return [
        JobResponse(
            id=j.id,
            schedule_id=j.schedule_id,
            status=j.status,
            started_at=j.started_at,
            finished_at=j.finished_at,
            metrics_json=j.metrics_json,
            **j.execution_config_snapshot_json
        ) for j in jobs
    ]

@router.get("/{id}/stream", response_class=EventSourceResponse)
async def stream_job_logs(
    id: Annotated[str, Path()], 
    request: Request
) -> AsyncIterable[ServerSentEvent]:
    # No blocking DB call here! We just subscribe to the existing queue.
    # If the queue doesn't exist, it might mean the job is already done or invalid,
    # but we'll create one just in case the engine is spinning up slowly.
    if id not in request.app.state.log_subscribers:
        request.app.state.log_subscribers[id] = asyncio.Queue()
        
    queue = request.app.state.log_subscribers[id]
    
    yield ServerSentEvent(data={"message": f"Attached to job {id} log stream"}, event="info")
    while True:
        event = await queue.get()
        if event is None:
            break
        yield event

@router.get("/{id}/results")
def get_job_results(
    id: Annotated[str, Path()],
    session: SessionDep
) -> dict[str, Any]:
    # Placeholder for the strict ip_state_json tree return (Issue 03)
    # The actual implementation of results tree is in `/results` router, but this is a specific job tree.
    from sqlmodel import select
    from api.models import IpState
    
    job = session.get(Job, id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    stmt = select(IpState).where(IpState.job_id == id)
    ips = session.exec(stmt).all()
    
    # Return as per spec: a list of serialized IpState models
    return {"results": ips}


