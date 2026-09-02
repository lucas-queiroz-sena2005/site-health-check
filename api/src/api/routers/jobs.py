import asyncio
from datetime import datetime, timezone
from typing import Annotated, Any
from collections.abc import AsyncIterable

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlmodel import select, desc
from pydantic import BaseModel, ConfigDict

from api.models import Job
from api.database import SessionDep

router = APIRouter(prefix="/jobs", tags=["jobs"])

class JobLaunchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    targets: list[str]
    ports: list[int]
    flags: dict[str, Any]

class JobResponse(BaseModel):
    id: str
    schedule_id: str | None = None
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None

@router.post("/launch", status_code=status.HTTP_201_CREATED)
def launch_job(request: JobLaunchRequest, session: SessionDep) -> JobResponse:
    snapshot = {
        "targets": request.targets,
        "ports": request.ports,
        "flags": request.flags,
    }
    job = Job(
        execution_config_snapshot_json=snapshot,
        status="PENDING"
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    
    # In a real app, we'd send to RabbitMQ or asyncio queue here.
    # For MVP, we just record it.
    return JobResponse(
        id=job.id,
        schedule_id=job.schedule_id,
        status=job.status,
        started_at=job.started_at,
        finished_at=job.finished_at
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
            finished_at=j.finished_at
        ) for j in jobs
    ]

@router.get("/{id}/stream", response_class=EventSourceResponse, response_model=None)
async def stream_job_logs(id: str, session: SessionDep) -> AsyncIterable[ServerSentEvent]:
    job = session.get(Job, id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    async def log_generator():
        yield ServerSentEvent(data={"message": f"Attached to job {id} log stream"}, event="info")
        # MVP: Just yield a few fake logs for now
        for i in range(5):
            await asyncio.sleep(1)
            yield ServerSentEvent(data={"message": f"Log line {i+1} from engine"}, event="log")
        yield ServerSentEvent(data={"message": "Job finished"}, event="status")
        
    return log_generator()

