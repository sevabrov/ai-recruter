"""
Storage seam (spec §23).

Phase 2 has no database — but services must never learn that. They depend on
this protocol only, so Phase 3 replaces `InMemoryRepository` with a SQLAlchemy
implementation and nothing above this line changes.

Filtering, sorting and pagination deliberately live in `services/leads`, not
here: the in-memory store cannot push predicates down. When the SQL repository
arrives, those helpers become the WHERE/ORDER BY/LIMIT clause and the service
keeps its signature.
"""

from typing import Protocol

from app.models.job import Job
from app.models.lead import Lead
from app.models.search import Search


class Repository(Protocol):
    # ------------------------------------------------------------- searches
    async def list_searches(self, user_id: str) -> list[Search]: ...

    async def get_search(self, search_id: str) -> Search | None: ...

    async def save_search(self, search: Search) -> None:
        """Insert or replace — searches are updated in place as the job runs."""

    # ---------------------------------------------------------------- leads
    async def list_leads(self, user_id: str) -> list[Lead]: ...

    async def get_lead(self, lead_id: str) -> Lead | None: ...

    async def add_leads(self, leads: list[Lead]) -> None: ...

    async def save_lead(self, lead: Lead) -> None: ...

    # ----------------------------------------------------------------- jobs
    async def list_jobs(self, user_id: str) -> list[Job]: ...

    async def get_job(self, job_id: str) -> Job | None: ...

    async def save_job(self, job: Job) -> None: ...

    # ---------------------------------------------------------------- admin
    async def reset(self) -> None:
        """Drop everything and re-apply the seed (used by the demo reset)."""
