"""
Job inspection (spec §21's `api/jobs.py`, §56).

Not used by the UI — this is the operator's window into concurrent searches:
which jobs ran, how many attempts they took and why one failed. Phase 7 answers
the same shape from Celery's result backend.
"""

from datetime import datetime

from fastapi import APIRouter

from app.api.deps import ContainerDep, UserDep
from app.core.errors import NotFoundError
from app.models.job import JobKind, JobStatus
from app.schemas.common import CamelModel

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobOut(CamelModel):
    id: str
    kind: JobKind
    status: JobStatus
    search_id: str | None = None
    attempts: int
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class JobsOut(CamelModel):
    running: int
    items: list[JobOut]


@router.get("", response_model=JobsOut, response_model_exclude_none=True)
async def list_jobs(container: ContainerDep, user_id: UserDep) -> JobsOut:
    jobs = await container.repository.list_jobs(user_id)
    return JobsOut(
        running=container.jobs.running,
        items=[JobOut.model_validate(job) for job in jobs],
    )


@router.get("/{job_id}", response_model=JobOut, response_model_exclude_none=True)
async def get_job(job_id: str, container: ContainerDep, user_id: UserDep) -> JobOut:
    job = await container.repository.get_job(job_id)
    if job is None or job.user_id != user_id:
        raise NotFoundError(f"Job {job_id} not found", job_id=job_id)
    return JobOut.model_validate(job)
