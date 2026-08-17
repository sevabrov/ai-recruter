"""
Job service (spec §39–42).

`POST /searches` returns in milliseconds; the search itself runs here. Phase 2
runs jobs as asyncio tasks in the API process — which already gives the property
the spec cares about most (§41): one user's search never blocks another's,
because every job is independent and the stages are concurrent internally.

What in-process jobs do *not* give is horizontal scale or durability across a
restart. That is Phase 7: this class keeps its interface and `_spawn` becomes
`celery_app.send_task("run_search", ...)`.
"""

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from app.core.logging import get_logger
from app.db.repository import Repository
from app.models.job import Job, JobKind, JobStatus
from app.models.search import Search
from app.services.search.pipeline import SearchPipeline
from app.workers.tasks import run_search

log = get_logger(__name__)


class JobService:
    def __init__(
        self,
        repository: Repository,
        pipeline_factory: Callable[[], SearchPipeline],
    ) -> None:
        self.repo = repository
        # A fresh pipeline per job: it carries per-run progress and usage.
        self._pipeline_factory = pipeline_factory
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def enqueue_search(self, search: Search) -> Job:
        job = Job(
            id=f"job_{uuid.uuid4().hex[:12]}",
            kind=JobKind.RUN_SEARCH,
            status=JobStatus.QUEUED,
            search_id=search.id,
            user_id=search.user_id,
        )
        await self.repo.save_job(job)
        self._tasks[job.id] = asyncio.create_task(
            self._execute(job), name=f"run_search:{search.id}"
        )
        return job

    async def cancel_search(self, search_id: str) -> None:
        """
        The pipeline notices the cancelled status at its next checkpoint, so the
        stage it is in finishes cleanly instead of being torn down mid-write.
        """
        for job_id, task in list(self._tasks.items()):
            job = await self.repo.get_job(job_id)
            if job and job.search_id == search_id and not task.done():
                await self._finish(job, JobStatus.CANCELLED)

    async def shutdown(self) -> None:
        pending = [task for task in self._tasks.values() if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    @property
    def running(self) -> int:
        return sum(1 for task in self._tasks.values() if not task.done())

    async def _execute(self, job: Job) -> None:
        job = job.model_copy(
            update={
                "status": JobStatus.RUNNING,
                "attempts": job.attempts + 1,
                "started_at": datetime.now(UTC),
            }
        )
        await self.repo.save_job(job)

        try:
            await run_search(job.search_id or "", pipeline=self._pipeline_factory(), job_id=job.id)
        except asyncio.CancelledError:
            await self._finish(job, JobStatus.CANCELLED)
            raise
        except Exception as error:
            log.exception("job_failed", extra={"job_id": job.id})
            await self._finish(job, JobStatus.FAILED, error=str(error))
        else:
            await self._finish(job, JobStatus.SUCCEEDED)

    async def _finish(self, job: Job, status: JobStatus, error: str | None = None) -> None:
        current = await self.repo.get_job(job.id) or job
        # A cancel that landed while the last stage was finishing wins.
        if current.status is JobStatus.CANCELLED and status is JobStatus.SUCCEEDED:
            return
        await self.repo.save_job(
            current.model_copy(
                update={"status": status, "error": error, "finished_at": datetime.now(UTC)}
            )
        )
