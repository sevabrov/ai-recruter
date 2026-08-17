"""
Search service.

Owns the lifecycle of a search and the ownership check that goes with it: every
lookup is scoped to the caller (spec §55), so a search that belongs to somebody
else is indistinguishable from one that does not exist.
"""

# `list` is a method name here, so annotations must stay lazy to keep the builtin.
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.core.errors import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.db.repository import Repository
from app.models.common import SearchStage, SearchStatus
from app.models.search import Search, SearchCriteria, SearchProgress
from app.workers.job_service import JobService

log = get_logger(__name__)


class SearchService:
    def __init__(self, repository: Repository, jobs: JobService) -> None:
        self.repo = repository
        self.jobs = jobs

    async def list(self, user_id: str) -> list[Search]:
        return await self.repo.list_searches(user_id)

    async def get(self, user_id: str, search_id: str) -> Search:
        search = await self.repo.get_search(search_id)
        if search is None or search.user_id != user_id:
            raise NotFoundError(f"Search {search_id} not found", search_id=search_id)
        return search

    async def create(self, user_id: str, name: str, criteria: SearchCriteria) -> Search:
        """
        Returns as soon as the record exists (spec §39). The queries, the web
        search and the scoring all happen in the job that is enqueued here.
        """
        search = Search(
            id=f"srch_{uuid.uuid4().hex[:12]}",
            user_id=user_id,
            name=name.strip(),
            status=SearchStatus.QUEUED,
            created_at=datetime.now(UTC),
            started_at=datetime.now(UTC),
            target=criteria.target_label(),
            country=criteria.location.country,
            sources=list(criteria.sources),
            criteria=criteria,
            progress=SearchProgress(stage=SearchStage.QUEUED),
        )
        await self.repo.save_search(search)
        job = await self.jobs.enqueue_search(search)
        log.info("search_created", extra={"search_id": search.id, "job_id": job.id})
        return search

    async def cancel(self, user_id: str, search_id: str) -> Search:
        search = await self.get(user_id, search_id)
        if not search.is_running:
            raise ConflictError(
                f"Search {search_id} is {search.status.value} and cannot be cancelled",
                status=search.status.value,
            )

        cancelled = search.model_copy(
            update={"status": SearchStatus.CANCELLED, "completed_at": datetime.now(UTC)}
        )
        # Store the decision first: the pipeline reads it at its next checkpoint
        # and stops without clobbering this record.
        await self.repo.save_search(cancelled)
        await self.jobs.cancel_search(search_id)
        log.info("search_cancelled", extra={"search_id": search_id})
        return cancelled
