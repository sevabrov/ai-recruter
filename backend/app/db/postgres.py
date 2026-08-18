"""
The PostgreSQL repository (Phase 3).

Every method is one short transaction, because that is the unit the callers
actually want: the worker writes progress dozens of times per search and must not
hold a transaction open across a stage, and two searches running at once must not
serialise behind each other.

Three things are worth reading closely:

* `query_leads` is the whole `/leads` screen in one statement — filters as WHERE,
  sort as ORDER BY (always with a tiebreak, so paging cannot repeat or skip a row),
  page as LIMIT/OFFSET, and the total from a COUNT over the same predicate.
* `patch_search` locks the row it is about to update, which closes the window
  where a cancel arriving mid-stage would be overwritten by the worker's next
  progress write.
* `ensure_seeded` is guarded by a marker row, so the demo data is inserted once —
  a workspace someone deliberately emptied stays empty across restarts.
"""

from collections.abc import Sequence

from sqlalchemy import Select, and_, delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.engine import SessionFactory
from app.db.mappers import (
    apply_job,
    apply_lead,
    apply_search,
    note_row,
    to_job,
    to_lead,
    to_search,
)
from app.db.repository import Repository
from app.db.seed import SeedData
from app.db.tables import JobRow, LeadNoteRow, LeadRow, SearchRow, SeedStateRow, UserRow
from app.models.common import (
    HIGH_QUALITY_THRESHOLD,
    SOCIAL_PLATFORMS,
    LeadSort,
    Platform,
    SearchStatus,
)
from app.models.job import Job
from app.models.lead import Lead, LeadNote
from app.models.query import LeadQuery, LeadStats, Page
from app.models.search import Search

log = get_logger(__name__)

#: Marker for "the demo seed has been applied to this database".
SEED_KEY = "demo-workspace"

#: A search in one of these states is finished; the worker must not write over it.
FINISHED_STATUSES = (SearchStatus.CANCELLED.value, SearchStatus.FAILED.value)

#: Tables the demo reset clears. Users survive: the accounts are not demo data.
RESET_TABLES = "lead_notes, leads, jobs, searches, seed_state"


class PostgresRepository(Repository):
    def __init__(self, session_factory: SessionFactory, seed: SeedData) -> None:
        self._session = session_factory
        self._seed = seed

    # ------------------------------------------------------------- searches
    async def list_searches(self, user_id: str) -> list[Search]:
        async with self._session() as session:
            rows = await session.scalars(
                select(SearchRow)
                .where(SearchRow.user_id == user_id)
                .order_by(SearchRow.created_at.desc(), SearchRow.id.desc())
            )
            return [to_search(row) for row in rows]

    async def get_search(self, search_id: str) -> Search | None:
        async with self._session() as session:
            row = await session.get(SearchRow, search_id)
            return to_search(row) if row else None

    async def save_search(self, search: Search) -> None:
        async with self._session() as session, session.begin():
            row = await session.get(SearchRow, search.id)
            if row is None:
                row = SearchRow()
                session.add(row)
            apply_search(row, search)

    async def patch_search(
        self,
        search_id: str,
        updates: dict[str, object],
        *,
        skip_finished: bool = True,
    ) -> Search | None:
        async with self._session() as session, session.begin():
            row = await session.scalar(
                select(SearchRow).where(SearchRow.id == search_id).with_for_update()
            )
            if row is None:
                return None
            if skip_finished and row.status in FINISHED_STATUSES:
                return None

            updated = to_search(row).model_copy(update=updates)
            apply_search(row, updated)
            return updated

    # ---------------------------------------------------------------- leads
    async def query_leads(self, user_id: str, query: LeadQuery) -> Page:
        where = _conditions(user_id, query)
        offset = max(0, (query.page - 1) * query.page_size)

        async with self._session() as session:
            total = await session.scalar(select(func.count()).select_from(LeadRow).where(*where))
            rows = await session.scalars(
                _ordered(select(LeadRow).where(*where), query.sort)
                .limit(query.page_size)
                .offset(offset)
            )
            return Page(
                items=[to_lead(row) for row in rows],
                total=total or 0,
                page=query.page,
                page_size=query.page_size,
            )

    async def get_lead(self, lead_id: str) -> Lead | None:
        async with self._session() as session:
            row = await session.get(LeadRow, lead_id)
            return to_lead(row) if row else None

    async def add_leads(self, leads: list[Lead]) -> None:
        if not leads:
            return
        async with self._session() as session, session.begin():
            for lead in leads:
                row = await session.get(LeadRow, lead.id)
                if row is None:
                    row = LeadRow()
                    session.add(row)
                apply_lead(row, lead)

    async def save_lead(self, lead: Lead) -> None:
        async with self._session() as session, session.begin():
            row = await session.get(LeadRow, lead.id)
            if row is None:
                row = LeadRow()
                session.add(row)
            apply_lead(row, lead)

    async def add_note(self, lead_id: str, note: LeadNote) -> None:
        async with self._session() as session, session.begin():
            row = await session.get(LeadRow, lead_id)
            if row is None:
                return
            session.add(note_row(lead_id, note))
            row.updated_at = note.created_at

    async def lead_facets(self, user_id: str) -> tuple[list[str], list[Platform]]:
        async with self._session() as session:
            countries = list(
                await session.scalars(
                    select(LeadRow.country)
                    .where(LeadRow.user_id == user_id, LeadRow.country.is_not(None))
                    .distinct()
                    .order_by(LeadRow.country)
                )
            )
            kinds = set(
                await session.scalars(
                    select(func.unnest(LeadRow.platform_kinds))
                    .where(LeadRow.user_id == user_id)
                    .distinct()
                )
            )

        # Enum order, not alphabetical: the filter chips read the same every time.
        return countries, [platform for platform in Platform if platform.value in kinds]

    async def lead_stats(
        self, user_id: str, *, exclude_search_ids: Sequence[str] = ()
    ) -> LeadStats:
        stmt = select(
            func.count().label("total"),
            func.count().filter(LeadRow.score >= HIGH_QUALITY_THRESHOLD).label("high_quality"),
            func.count().filter(LeadRow.saved.is_(True)).label("saved"),
        ).where(LeadRow.user_id == user_id)
        if exclude_search_ids:
            stmt = stmt.where(LeadRow.search_id.not_in(list(exclude_search_ids)))

        async with self._session() as session:
            row = (await session.execute(stmt)).one()
            return LeadStats(total=row.total, high_quality=row.high_quality, saved=row.saved)

    # ----------------------------------------------------------------- jobs
    async def list_jobs(self, user_id: str) -> list[Job]:
        async with self._session() as session:
            rows = await session.scalars(
                select(JobRow)
                .where(JobRow.user_id == user_id)
                .order_by(JobRow.created_at.desc(), JobRow.id.desc())
            )
            return [to_job(row) for row in rows]

    async def get_job(self, job_id: str) -> Job | None:
        async with self._session() as session:
            row = await session.get(JobRow, job_id)
            return to_job(row) if row else None

    async def save_job(self, job: Job) -> None:
        async with self._session() as session, session.begin():
            row = await session.get(JobRow, job.id)
            if row is None:
                row = JobRow()
                session.add(row)
            apply_job(row, job)

    # ------------------------------------------------------------- lifecycle
    async def ping(self) -> bool:
        try:
            async with self._session() as session:
                await session.execute(select(1))
            return True
        except Exception:
            log.warning("database_unreachable", exc_info=True)
            return False

    async def ensure_seeded(self) -> bool:
        async with self._session() as session, session.begin():
            claimed = await session.execute(
                insert(SeedStateRow)
                .values(
                    key=SEED_KEY,
                    searches=len(self._seed.searches),
                    leads=len(self._seed.leads),
                )
                .on_conflict_do_nothing(index_elements=["key"])
            )
            # Nobody else got there first, so this transaction owns the insert.
            if claimed.rowcount == 0:
                return False
            await self._insert_seed(session)

        log.info(
            "seed_applied",
            extra={"searches": len(self._seed.searches), "leads": len(self._seed.leads)},
        )
        return True

    async def reset(self) -> None:
        """
        Back to the seed as it was loaded at startup — including its timestamps, so
        "3 hours ago" is relative to the boot, not to the reset.
        """
        async with self._session() as session, session.begin():
            await session.execute(text(f"TRUNCATE TABLE {RESET_TABLES}"))
            await session.execute(
                insert(SeedStateRow).values(
                    key=SEED_KEY,
                    searches=len(self._seed.searches),
                    leads=len(self._seed.leads),
                )
            )
            await self._insert_seed(session)
        log.info("workspace_reset")

    async def _insert_seed(self, session: AsyncSession) -> None:
        user_id = self._seed.user_id
        if await session.get(UserRow, user_id) is None:
            session.add(UserRow(id=user_id, email="demo@ai-recruiter.local", name="Demo user"))
            await session.flush()

        for search in self._seed.searches:
            session.add(apply_search(SearchRow(), search))
        await session.flush()

        for lead in self._seed.leads:
            session.add(apply_lead(LeadRow(), lead))
            for note in lead.notes:
                session.add(note_row(lead.id, note))

    async def purge(self) -> None:
        """Leave the database empty — no seed, no marker. Used by the test suite."""
        async with self._session() as session, session.begin():
            await session.execute(delete(LeadNoteRow))
            await session.execute(delete(LeadRow))
            await session.execute(delete(JobRow))
            await session.execute(delete(SearchRow))
            await session.execute(delete(SeedStateRow))


# ------------------------------------------------------------------ predicates
def _conditions(user_id: str, query: LeadQuery) -> list:
    where = [LeadRow.user_id == user_id]

    if not query.include_archived:
        where.append(LeadRow.archived.is_(False))
    if query.search_id:
        where.append(LeadRow.search_id == query.search_id)
    if query.saved_only:
        where.append(LeadRow.saved.is_(True))
    if query.min_score is not None:
        where.append(LeadRow.score >= query.min_score)
    if query.statuses:
        where.append(LeadRow.status.in_([status.value for status in query.statuses]))
    if query.countries:
        where.append(LeadRow.country.in_(query.countries))
    if query.platforms:
        # Any of them: asking for Instagram or LinkedIn means either will do.
        where.append(LeadRow.platform_kinds.overlap([p.value for p in query.platforms]))
    if query.signals:
        # All of them (spec §17): MLM *and* leadership means both were detected.
        where.append(LeadRow.detected_signals.contains([s.value for s in query.signals]))
    if query.has_email:
        where.append(and_(LeadRow.email.is_not(None), LeadRow.email != ""))
    if query.has_social:
        where.append(LeadRow.platform_kinds.overlap([p.value for p in SOCIAL_PLATFORMS]))

    needle = (query.query or "").strip()
    if needle:
        where.append(_haystack().ilike(f"%{_escape(needle)}%", escape="\\"))

    return where


def _haystack():
    """One free-text field over the columns the search box is expected to match."""
    return func.concat_ws(
        " ",
        LeadRow.name,
        LeadRow.headline,
        LeadRow.company,
        LeadRow.city,
        LeadRow.country,
        LeadRow.summary,
    )


def _escape(needle: str) -> str:
    """`%` and `_` typed into the search box are literals, not wildcards."""
    return needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _ordered(stmt: Select, sort: LeadSort) -> Select:
    # Every order ends in the primary key: without a total order, LIMIT/OFFSET is
    # free to return the same row on two different pages.
    if sort is LeadSort.NAME_ASC:
        return stmt.order_by(func.lower(LeadRow.name), LeadRow.id)
    if sort is LeadSort.NEWEST:
        return stmt.order_by(LeadRow.created_at.desc(), LeadRow.id)
    return stmt.order_by(LeadRow.score.desc(), func.lower(LeadRow.name), LeadRow.id)
