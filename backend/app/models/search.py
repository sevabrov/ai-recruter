"""
Search domain model (spec §24, §43, §54).

A `Search` is the whole record of one run: what the user asked for, how far the
worker has got, what it cost and which queries it fired. `GET /searches/:id`
returns exactly this, which is why the frontend never has to invent progress.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.models.common import (
    DEFAULT_SIGNAL_WEIGHTS,
    GeoLocation,
    SearchStage,
    SearchStatus,
    SignalType,
    SourceKind,
)

RUNNING_STATUSES = (
    SearchStatus.QUEUED,
    SearchStatus.SEARCHING,
    SearchStatus.EXTRACTING,
    SearchStatus.SCORING,
)


class SearchCriteria(BaseModel):
    industry: list[str] = Field(default_factory=list)
    business_types: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    negative_keywords: list[str] = Field(default_factory=list)
    location: GeoLocation = Field(default_factory=GeoLocation)
    languages: list[str] = Field(default_factory=list)
    must_have: list[SignalType] = Field(default_factory=list)
    nice_to_have: list[SignalType] = Field(default_factory=list)
    #: Points per signal. The backend owns the arithmetic (spec §37).
    signal_weights: dict[SignalType, int] = Field(
        default_factory=lambda: dict(DEFAULT_SIGNAL_WEIGHTS)
    )
    sources: list[SourceKind] = Field(default_factory=list)

    def target_label(self) -> str:
        """The short human label the UI shows next to a search name."""
        parts = [" / ".join(self.business_types), " / ".join(self.industry)]
        return " · ".join(part for part in parts if part) or "Unspecified target"


class SearchProgress(BaseModel):
    queries: int = 0
    queries_completed: int = 0
    urls_discovered: int = 0
    profiles_discovered: int = 0
    profiles_processed: int = 0
    qualified: int = 0
    high_quality: int = 0
    percent: int = 0
    stage: SearchStage = SearchStage.QUEUED


class GeneratedQuery(BaseModel):
    id: str
    query: str
    provider: str
    result_count: int = 0


class SearchUsage(BaseModel):
    """
    Per-search cost tracking from day one (spec §54).

    `pages_analyzed` is how many candidate pages the stage handled; `pages_read` is
    how many of them were actually fetched and billed, `pages_cached` how many came
    from the scrape cache (§53), and `pages_skipped` how many the search's page
    budget refused to pay for — those still became leads, from their search snippet.
    Keeping the four apart is what makes the cost a measurement: a second identical
    search analyses the same pages and pays for none of them.

    `scrape_credits` is in the plan's own units and counts every request the service
    served, a timeout included — it maps onto the provider's dashboard rather than
    onto how many pages we ended up using.
    """

    search_api_calls: int = 0
    pages_analyzed: int = 0
    pages_read: int = 0
    pages_cached: int = 0
    pages_skipped: int = 0
    scrape_credits: int = 0
    llm_calls: int = 0
    estimated_cost_eur: float = 0.0


class Search(BaseModel):
    id: str
    user_id: str
    name: str
    status: SearchStatus = SearchStatus.DRAFT

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None

    lead_count: int = 0
    high_quality_count: int = 0
    target: str = ""
    country: str | None = None
    sources: list[SourceKind] = Field(default_factory=list)

    criteria: SearchCriteria
    progress: SearchProgress = Field(default_factory=SearchProgress)
    usage: SearchUsage = Field(default_factory=SearchUsage)
    queries: list[GeneratedQuery] = Field(default_factory=list)
    error: str | None = None

    @property
    def is_running(self) -> bool:
        return self.status in RUNNING_STATUSES
