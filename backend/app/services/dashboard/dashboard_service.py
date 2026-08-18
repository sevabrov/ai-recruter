"""
Dashboard service (spec §7).

The seeded aggregates describe a fuller workspace than the seeded entities — the
demo pretends older searches were pruned. Anything the user does on top of that
is counted for real, so the tiles react to their own actions: start a search and
the counts move, save a lead and the saved tile moves with it.

Since Phase 3 the counting is done by the database: three COUNTs in one statement
instead of loading every lead into Python to add them up.
"""

from app.db.seed import SeedData
from app.schemas.dashboard import DashboardOut, DashboardStat, DashboardStats
from app.schemas.search import SearchSummaryOut
from app.services.leads.lead_service import LeadService
from app.services.search.search_service import SearchService

RECENT_LIMIT = 5


class DashboardService:
    def __init__(
        self,
        searches: SearchService,
        leads: LeadService,
        seed: SeedData,
    ) -> None:
        self.searches = searches
        self.leads = leads
        self.seed = seed
        self._seeded_search_ids = {search.id for search in seed.searches}
        self._seeded_saved = sum(1 for lead in seed.leads if lead.saved)

    async def get(self, user_id: str) -> DashboardOut:
        searches = await self.searches.list(user_id)
        # Two aggregates: everything the user added on top of the seed, and the
        # whole workspace (the saved tile counts seeded leads the user saved too).
        own = await self.leads.stats(user_id, exclude_search_ids=sorted(self._seeded_search_ids))
        everything = await self.leads.stats(user_id)

        own_searches = [s for s in searches if s.id not in self._seeded_search_ids]

        base = self.seed.stats
        stats = DashboardStats(
            total_leads=_bump(base["totalLeads"], own.total),
            high_quality=_bump(base["highQuality"], own.high_quality),
            searches=_bump(base["searches"], len(own_searches)),
            saved_leads=_saved(base["savedLeads"], everything.saved, self._seeded_saved),
        )

        return DashboardOut(
            stats=stats,
            recent_searches=[
                SearchSummaryOut.model_validate(search) for search in searches[:RECENT_LIMIT]
            ],
            source_breakdown=self.seed.source_breakdown,
            score_distribution=self.seed.score_distribution,
            weekly_leads=self.seed.weekly_leads,
        )


def _bump(raw: dict, extra: int) -> DashboardStat:
    stat = DashboardStat.model_validate(raw)
    return stat.model_copy(update={"value": stat.value + extra}) if extra else stat


def _saved(raw: dict, saved_now: int, seeded_saved: int) -> DashboardStat:
    """Saving or unsaving moves the tile, so it is visibly wired to the data."""
    stat = DashboardStat.model_validate(raw)
    return stat.model_copy(
        update={
            "value": stat.value - seeded_saved + saved_now,
            "hint": f"{saved_now} saved in this workspace",
        }
    )
