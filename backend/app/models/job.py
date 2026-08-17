"""
Job model (spec §39–40).

`POST /searches` must return immediately, so the actual work is a job. Phase 2
runs jobs in-process; Phase 7 hands the same records to Celery. The shape is
already what a queue needs: retryable, cancellable, and dead-letterable.
"""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class JobKind(StrEnum):
    RUN_SEARCH = "run_search"
    RUN_QUERY = "run_query"
    EXTRACT_CANDIDATE = "extract_candidate"
    SCORE_CANDIDATE = "score_candidate"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job(BaseModel):
    id: str
    kind: JobKind
    status: JobStatus = JobStatus.QUEUED
    search_id: str | None = None
    user_id: str | None = None
    attempts: int = 0
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    finished_at: datetime | None = None
