from typing import Any
from fastapi import APIRouter, status
from sqlmodel import select
from pydantic import BaseModel, ConfigDict

from api.models import Schedule, Classification, ScheduleClassificationLink, ExecutionConfig
from api.database import SessionDep

router = APIRouter(prefix="/schedules", tags=["schedules"])

class ScheduleCreateRequest(ExecutionConfig):
    name: str
    cron_expression: str

class ScheduleResponse(ExecutionConfig):
    id: str
    name: str
    cron_expression: str
    is_active: bool

@router.post("", status_code=status.HTTP_201_CREATED)
def create_schedule(request: ScheduleCreateRequest, session: SessionDep) -> ScheduleResponse:
    # 1. Create a classification for these targets
    classification = Classification(
        name=f"Classification for {request.name}",
        targets_json=request.targets
    )
    session.add(classification)
    
    # 2. Create the schedule
    schedule = Schedule(
        name=request.name,
        cron_expression=request.cron_expression,
        ports_json=request.ports,
        flags_json=request.model_dump(exclude={"name", "cron_expression", "targets", "ports"})
    )
    session.add(schedule)
    
    session.commit() # Commit to get IDs
    
    # 3. Link them
    link = ScheduleClassificationLink(
        schedule_id=schedule.id,
        classification_id=classification.id
    )
    session.add(link)
    session.commit()
    session.refresh(schedule)
    
    return ScheduleResponse(
        id=schedule.id,
        name=schedule.name,
        cron_expression=schedule.cron_expression,
        is_active=schedule.is_active,
        targets=request.targets,
        ports=schedule.ports_json,
        **schedule.flags_json
    )

@router.get("")
def list_schedules(session: SessionDep) -> list[ScheduleResponse]:
    stmt = select(Schedule).where(Schedule.deleted_at == None)
    schedules = session.exec(stmt).all()
    
    responses = []
    for s in schedules:
        # Extract targets from classifications
        targets = []
        for c in s.classifications:
            targets.extend(c.targets_json)
            
        responses.append(ScheduleResponse(
            id=s.id,
            name=s.name,
            cron_expression=s.cron_expression,
            is_active=s.is_active,
            targets=targets,
            ports=s.ports_json,
            **s.flags_json
        ))
    return responses
