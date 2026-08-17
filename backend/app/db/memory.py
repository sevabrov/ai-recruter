"""
In-memory repository (Phase 2).

Good enough for a single API process and honest about what it is: state lives
until the container restarts. Reads hand out deep copies so a caller cannot
mutate stored state by accident — the same isolation a real transaction gives,
which is what keeps the service layer portable to Phase 3.
"""

import asyncio

from app.db.repository import Repository
from app.db.seed import SeedData, load_seed
from app.models.job import Job
from app.models.lead import Lead
from app.models.search import Search


class InMemoryRepository(Repository):
    def __init__(self, seed: SeedData) -> None:
        self._lock = asyncio.Lock()
        self._searches: dict[str, Search] = {}
        self._leads: dict[str, Lead] = {}
        self._jobs: dict[str, Job] = {}
        self._seed = seed
        self._apply_seed()

    @classmethod
    def seeded(cls, user_id: str) -> "InMemoryRepository":
        return cls(load_seed(user_id))

    def _apply_seed(self) -> None:
        self._searches = {s.id: s.model_copy(deep=True) for s in self._seed.searches}
        self._leads = {lead.id: lead.model_copy(deep=True) for lead in self._seed.leads}
        self._jobs = {}

    # ------------------------------------------------------------- searches
    async def list_searches(self, user_id: str) -> list[Search]:
        async with self._lock:
            found = [s for s in self._searches.values() if s.user_id == user_id]
        return sorted(
            (s.model_copy(deep=True) for s in found),
            key=lambda s: s.created_at,
            reverse=True,
        )

    async def get_search(self, search_id: str) -> Search | None:
        async with self._lock:
            found = self._searches.get(search_id)
            return found.model_copy(deep=True) if found else None

    async def save_search(self, search: Search) -> None:
        async with self._lock:
            self._searches[search.id] = search.model_copy(deep=True)

    # ---------------------------------------------------------------- leads
    async def list_leads(self, user_id: str) -> list[Lead]:
        async with self._lock:
            found = [lead for lead in self._leads.values() if lead.user_id == user_id]
        return [lead.model_copy(deep=True) for lead in found]

    async def get_lead(self, lead_id: str) -> Lead | None:
        async with self._lock:
            found = self._leads.get(lead_id)
            return found.model_copy(deep=True) if found else None

    async def add_leads(self, leads: list[Lead]) -> None:
        async with self._lock:
            for lead in leads:
                self._leads[lead.id] = lead.model_copy(deep=True)

    async def save_lead(self, lead: Lead) -> None:
        async with self._lock:
            self._leads[lead.id] = lead.model_copy(deep=True)

    # ----------------------------------------------------------------- jobs
    async def list_jobs(self, user_id: str) -> list[Job]:
        async with self._lock:
            found = [job for job in self._jobs.values() if job.user_id == user_id]
        return sorted(found, key=lambda job: job.created_at, reverse=True)

    async def get_job(self, job_id: str) -> Job | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def save_job(self, job: Job) -> None:
        async with self._lock:
            self._jobs[job.id] = job.model_copy(deep=True)

    # ---------------------------------------------------------------- admin
    async def reset(self) -> None:
        async with self._lock:
            self._apply_seed()
