from fastapi import APIRouter
from site_health_check.api.models import Job, JobCreate, JobResponse
from site_health_check.api.database import SessionDep

router = APIRouter(prefix="/jobs", tags=["jobs"])

@router.post("", status_code=201)
def create_job(job_in: JobCreate, session: SessionDep) -> JobResponse:
    job = Job(
        targets=job_in.targets,
        ports=job_in.ports,
        labels=job_in.labels,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    assert job.id is not None
    return JobResponse(id=job.id)
