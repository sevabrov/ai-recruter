"""
Storage seam (spec §23).

Services depend on this protocol, never on SQLAlchemy: `app/services/` contains no
import from `app/db/` beyond this file and the models it speaks. Phase 3 filled it
in with PostgreSQL (`postgres.py`); if the store ever changes again, this is the
only contract a replacement has to satisfy.

Phase 2 answered the lead queries by loading every row and filtering in Python,
because an in-memory dict cannot push predicates down. A database can, so
`query_leads`, `lead_facets` and `lead_stats` take the question instead of handing
back the whole table — the filters became WHERE clauses, the sort became ORDER BY
and the page became LIMIT/OFFSET.
"""

from typing import Protocol

from app.models.common import Platform
from app.models.job import Job
from app.models.lead import Lead, LeadNote
from app.models.query import LeadPoint, LeadQuery, LeadStats, Page
from app.models.rejection import RejectedCandidate, RejectionReason
from app.models.scrape import ScrapeRecord, SourceReliability
from app.models.search import Search


class Repository(Protocol):
    # ------------------------------------------------------------- searches
    async def list_searches(self, user_id: str) -> list[Search]: ...

    async def get_search(self, search_id: str) -> Search | None: ...

    async def save_search(self, search: Search) -> None:
        """Insert or replace — searches are updated in place as the job runs."""

    async def patch_search(
        self,
        search_id: str,
        updates: dict[str, object],
        *,
        skip_finished: bool = True,
    ) -> Search | None:
        """
        Apply `updates` to a stored search inside one transaction, with the row
        locked for the duration.

        This is how the worker writes progress without racing the user's cancel:
        read-modify-write across two transactions can resurrect a search that was
        cancelled in between. Returns None when the search is gone — or, with
        `skip_finished`, when it is already cancelled or failed — which tells the
        pipeline to stop.
        """

    # ----------------------------------------------------------- rejections
    async def add_rejections(self, rejections: list[RejectedCandidate]) -> None:
        """Store what a finished run turned away, alongside what it kept."""

    async def list_rejections(
        self,
        search_id: str,
        *,
        reason: RejectionReason | None = None,
        limit: int = 500,
    ) -> tuple[list[RejectedCandidate], dict[RejectionReason, int]]:
        """
        One search's refused candidates, and how many of each reason there are.

        The counts are over the whole run, never over the page returned: a screen
        that says "38 refused" and lists 20 of them has to get the 38 from the
        database, or it is quoting its own truncation back at the user.
        """

    # ---------------------------------------------------------------- leads
    async def query_leads(self, user_id: str, query: LeadQuery) -> Page: ...

    async def get_lead(self, lead_id: str) -> Lead | None: ...

    async def add_leads(self, leads: list[Lead]) -> None: ...

    async def save_lead(self, lead: Lead) -> None:
        """
        Insert or replace the lead's own columns. Notes are *not* written here:
        they are appended through `add_note`, so a stale copy of a lead can never
        delete a note somebody added meanwhile.
        """

    async def add_note(self, lead_id: str, note: LeadNote) -> None: ...

    async def lead_facets(self, user_id: str) -> tuple[list[str], list[Platform]]:
        """Countries and platforms actually present, for the filter menus."""

    async def lead_stats(self, user_id: str) -> LeadStats: ...

    async def lead_points(self, user_id: str) -> list[LeadPoint]:
        """Every lead's platforms, score and creation time, for the dashboard charts."""

    # ----------------------------------------------------------------- jobs
    async def list_jobs(self, user_id: str) -> list[Job]: ...

    async def get_job(self, job_id: str) -> Job | None: ...

    async def save_job(self, job: Job) -> None: ...

    # --------------------------------------------------------- scrape cache
    async def get_scrape(self, canonical_url: str) -> ScrapeRecord | None:
        """The last recorded read of this page, however long ago (spec §53)."""

    async def save_scrape(self, record: ScrapeRecord) -> None:
        """Insert or replace the entry for `record.canonical_url`."""

    async def source_reliability(self) -> list[SourceReliability]:
        """
        Per-platform counts of what reading actually yielded — the answer to
        Milestone 5's "record which sources consistently provide usable content".
        """

    # ------------------------------------------------------------- lifecycle
    async def ping(self) -> bool:
        """Whether the store answers — reported by `GET /health`."""

    async def ensure_owner(self, user_id: str) -> None:
        """Create the workspace owner's row if it does not exist yet."""
