"""
Dashboard API schemas (spec §7).

These are pure view models — a dashboard row is an aggregate, not an entity, so
there is no matching class under `models/`. Phase 3 computes them with SQL
instead of in Python; the shape does not change.
"""

from pydantic import Field

from app.models.common import Platform
from app.schemas.common import CamelModel
from app.schemas.search import SearchSummaryOut


class DashboardStat(CamelModel):
    label: str
    value: int
    #: Change against the previous period; omitted when there is nothing to compare.
    delta: float | None = None
    hint: str | None = None


class DashboardStats(CamelModel):
    total_leads: DashboardStat
    high_quality: DashboardStat
    searches: DashboardStat
    saved_leads: DashboardStat


class SourceShare(CamelModel):
    platform: Platform
    share: int
    leads: int


class ScoreBucket(CamelModel):
    label: str
    # `from` is a Python keyword; the wire name is not.
    from_: int = Field(alias="from")
    to: int
    count: int


class WeeklyPoint(CamelModel):
    day: str
    count: int


class DashboardOut(CamelModel):
    stats: DashboardStats
    recent_searches: list[SearchSummaryOut]
    source_breakdown: list[SourceShare]
    score_distribution: list[ScoreBucket]
    weekly_leads: list[WeeklyPoint]
