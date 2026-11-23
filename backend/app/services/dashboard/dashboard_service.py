"""
Dashboard service (spec §7).

Everything on the dashboard is counted from the workspace's own searches and
leads: the tiles by the database, the charts from one narrow read of the leads
table. An empty workspace shows zeros, not a picture of somebody else's.

There is no earlier period stored to compare with, so no tile carries a delta.
"""

from collections import Counter
from datetime import UTC, datetime, timedelta

from app.models.common import HIGH_QUALITY_THRESHOLD
from app.models.query import LeadPoint
from app.schemas.dashboard import (
    DashboardOut,
    DashboardStat,
    DashboardStats,
    ScoreBucket,
    SourceShare,
    WeeklyPoint,
)
from app.schemas.search import SearchSummaryOut
from app.services.leads.lead_service import LeadService
from app.services.search.search_service import SearchService

RECENT_LIMIT = 5

#: Highest first, as the histogram reads; the top two split at the quality line.
SCORE_BUCKETS: tuple[tuple[int, int], ...] = (
    (90, 100),
    (HIGH_QUALITY_THRESHOLD, 89),
    (70, HIGH_QUALITY_THRESHOLD - 1),
    (50, 69),
    (0, 49),
)

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


class DashboardService:
    def __init__(self, searches: SearchService, leads: LeadService) -> None:
        self.searches = searches
        self.leads = leads

    async def get(self, user_id: str) -> DashboardOut:
        searches = await self.searches.list(user_id)
        stats = await self.leads.stats(user_id)
        points = await self.leads.points(user_id)

        return DashboardOut(
            stats=DashboardStats(
                total_leads=DashboardStat(label="Total leads", value=stats.total),
                high_quality=DashboardStat(label="High quality", value=stats.high_quality),
                searches=DashboardStat(label="Searches", value=len(searches)),
                saved_leads=DashboardStat(label="Saved leads", value=stats.saved),
            ),
            recent_searches=[
                SearchSummaryOut.model_validate(search) for search in searches[:RECENT_LIMIT]
            ],
            source_breakdown=source_breakdown(points),
            score_distribution=score_distribution(points),
            weekly_leads=weekly_leads(points, datetime.now(UTC)),
        )


def source_breakdown(points: list[LeadPoint]) -> list[SourceShare]:
    """Leads per platform, most first. A lead found on two platforms counts on both."""
    counts = Counter(platform for point in points for platform in point.platforms)
    total = sum(counts.values())
    if not total:
        return []
    return [
        SourceShare(platform=platform, share=round(count * 100 / total), leads=count)
        for platform, count in counts.most_common()
    ]


def score_distribution(points: list[LeadPoint]) -> list[ScoreBucket]:
    return [
        ScoreBucket.model_validate(
            {
                "label": f"{low}–{high}" if low else f"< {high + 1}",
                "from": low,
                "to": high,
                "count": sum(1 for point in points if low <= point.score <= high),
            }
        )
        for low, high in SCORE_BUCKETS
    ]


def weekly_leads(points: list[LeadPoint], now: datetime) -> list[WeeklyPoint]:
    """Leads created on each of the last seven days, today last."""
    today = now.astimezone(UTC).date()
    days = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
    counts = Counter(point.created_at.astimezone(UTC).date() for point in points)
    return [WeeklyPoint(day=WEEKDAYS[day.weekday()], count=counts[day]) for day in days]
