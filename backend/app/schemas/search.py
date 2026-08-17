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
    must_have: list[SignalType] = Field(default_factory=list)
    nice_to_have: list[SignalType] = Field(default_factory=list)
    signal_weights: dict[SignalType, int] = Field(default_factory=dict)
    sources: list[SourceKind] = Field(default_factory=list)

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
    percent: int
    stage: SearchStage


class GeneratedQuerySchema(CamelModel):
    id: str
    query: str
    provider: str
    result_count: int


class SearchUsageSchema(CamelModel):
    search_api_calls: int
    pages_analyzed: int
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
