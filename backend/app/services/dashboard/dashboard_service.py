"""
Dashboard service (spec §7).

The seeded aggregates describe a fuller workspace than the seeded entities — the
demo pretends older searches were pruned. Anything the user does on top of that
is counted for real, so the tiles react to their own actions: start a search and
the counts move, save a lead and the saved tile moves with it.

Phase 3 replaces the Python arithmetic with SQL aggregates over the same numbers.
"""

from app.db.seed import SeedData
from app.models.common import HIGH_QUALITY_THRESHOLD
from app.schemas.dashboard import DashboardOut, DashboardStat, DashboardStats
from app.schemas.search import SearchSummaryOut
from app.services.leads.lead_service import LeadQuery, LeadService
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
        page = await self.leads.list(user_id, LeadQuery(page_size=10_000, include_archived=True))
        leads = page.items

        own_searches = [s for s in searches if s.id not in self._seeded_search_ids]
        own_leads = [lead for lead in leads if lead.search_id not in self._seeded_search_ids]
        saved_now = sum(1 for lead in leads if lead.saved)

        base = self.seed.stats
        stats = DashboardStats(
            total_leads=_bump(base["totalLeads"], len(own_leads)),
            high_quality=_bump(
                base["highQuality"],
                sum(1 for lead in own_leads if lead.score >= HIGH_QUALITY_THRESHOLD),
            ),
            searches=_bump(base["searches"], len(own_searches)),
            saved_leads=_saved(base["savedLeads"], saved_now, self._seeded_saved),
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
