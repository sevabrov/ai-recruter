"""Search API schemas (spec §19, §43, §57, §58)."""

from datetime import datetime

from pydantic import Field, field_validator

from app.models.common import (
    SCORED_SIGNALS,
    GeoLocation,
    SearchStage,
    SearchStatus,
    SignalType,
    SourceKind,
)
from app.schemas.common import CamelModel


class GeoLocationSchema(CamelModel):
    country: str | None = None
    region: str | None = None
    city: str | None = None


class SearchCriteriaSchema(CamelModel):
    industry: list[str] = Field(default_factory=list)
    business_types: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    negative_keywords: list[str] = Field(default_factory=list)
    location: GeoLocationSchema = Field(default_factory=GeoLocationSchema)
    languages: list[str] = Field(default_factory=list)
    #: Country and language as requirements rather than as points. Default on:
    #: a search for one country that returns another country is not that search.
    require_location: bool = True
    require_language: bool = True
    must_have: list[SignalType] = Field(default_factory=list)
    nice_to_have: list[SignalType] = Field(default_factory=list)
    signal_weights: dict[SignalType, int] = Field(default_factory=dict)
    sources: list[SourceKind] = Field(default_factory=list)
    #: How many leads to look for. It buys the page budget, so it is also what the
    #: wizard prices. 0 means "whatever the server allows".
    target_leads: int = Field(default=0, ge=0, le=1000)

    @field_validator("signal_weights")
    @classmethod
    def only_scored_signals(cls, weights: dict[SignalType, int]) -> dict[SignalType, int]:
        """
        `activity` is detected but never scored, so it may not carry points.
        The total is *not* enforced here: the wizard already keeps it at 100, and
        rejecting a 99 would block a user mid-flow. The scoring service reports
        the effective maximum instead.
        """
        unscorable = set(weights) - set(SCORED_SIGNALS)
        if unscorable:
            raise ValueError(f"signals cannot be weighted: {sorted(unscorable)}")
        if any(value < 0 or value > 100 for value in weights.values()):
            raise ValueError("signal weights must be between 0 and 100")
        return weights


class SearchProgressSchema(CamelModel):
    queries: int
    queries_completed: int
    urls_discovered: int
    profiles_discovered: int
    profiles_processed: int
    qualified: int
    high_quality: int
    #: Why the rest did not qualify. Defaulted, because searches recorded before
    #: the criteria became gates have no such counters and are still valid history.
    rejected_not_a_person: int = 0
    rejected_country: int = 0
    rejected_language: int = 0
    rejected_signals: int = 0
    percent: int
    stage: SearchStage


class GeneratedQuerySchema(CamelModel):
    id: str
    query: str
    provider: str
    result_count: int
    #: Which language's index this query was put to, if not the default market.
    language: str | None = None


class SearchUsageSchema(CamelModel):
    search_api_calls: int
    pages_analyzed: int
    #: Pages actually fetched and billed, pages served from the scrape cache, and
    #: pages the search's budget refused to pay for (they became snippet leads).
    pages_read: int
    pages_cached: int
    pages_skipped: int
    #: In the plan's own units, counting every request the service served.
    scrape_credits: int
    llm_calls: int
    estimated_cost_eur: float


class SearchSummaryOut(CamelModel):
    """`GET /searches` — enough for the history list and the dashboard."""

    id: str
    name: str
    status: SearchStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    lead_count: int
    high_quality_count: int
    target: str
    country: str | None = None
    sources: list[SourceKind]


class SearchOut(SearchSummaryOut):
    """`GET /searches/:id` — adds everything the progress screen polls for."""

    criteria: SearchCriteriaSchema
    progress: SearchProgressSchema
    usage: SearchUsageSchema
    queries: list[GeneratedQuerySchema]
    error: str | None = None


class CreateSearchIn(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    criteria: SearchCriteriaSchema

    def to_criteria_kwargs(self) -> dict:
        data = self.criteria.model_dump()
        data["location"] = GeoLocation(**data["location"])
        return data


class CreateSearchResponse(CamelModel):
    """Returned immediately; the work happens in a job (spec §39)."""

    search_id: str
    status: SearchStatus


class EstimateIn(CamelModel):
    """`POST /searches/estimate` — the wizard asking what this would cost."""

    criteria: SearchCriteriaSchema


class QueryPreviewOut(CamelModel):
    query: str
    language: str | None = None


class EstimateOut(CamelModel):
    """
    What the search may spend, before it is started (spec §54).

    A ceiling, not a forecast: the same function produces this figure and the
    budget the run is given, so the search cannot exceed what was quoted here.
    """

    queries: list[QueryPreviewOut]
    #: One query is one billed call.
    search_calls: int
    #: The most pages this search may pay to read. 0 means no page is ever paid
    #: for — either no reader is configured, or the limit was removed.
    max_pages: int
    #: …in the reader plan's own units.
    credits: int
    target_leads: int
    #: How many paid pages one lead is assumed to take, which is what turns the
    #: lead target into a budget. Measured, not fixed: see the run's own usage.
    pages_per_lead: int
    max_cost_eur: float
    #: Whether pages are read at all right now, so the UI can say why it is free.
    reads_pages: bool
