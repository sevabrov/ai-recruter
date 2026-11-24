"""Search API schemas (spec §19, §43, §57, §58)."""

from datetime import datetime

from pydantic import Field, field_validator

from app.models.common import (
    SCORED_SIGNALS,
    GeoLocation,
    Platform,
    SearchStage,
    SearchStatus,
    SignalType,
    SourceKind,
)
from app.models.rejection import RejectionReason
from app.models.search import DEFAULT_EXCLUDED_COUNTRIES, Importance
from app.schemas.common import CamelModel


class GeoLocationSchema(CamelModel):
    country: str | None = None
    region: str | None = None
    city: str | None = None


class RequirementSchema(CamelModel):
    """One thing that makes a candidate right for this search (see `Requirement`)."""

    id: str = Field(min_length=1, max_length=40)
    label: str = Field(default="", max_length=80)
    description: str = Field(default="", max_length=300)
    terms: list[str] = Field(default_factory=list, max_length=10)
    importance: Importance = Importance.NORMAL
    weight: int = Field(default=0, ge=0, le=100)


class SearchCriteriaSchema(CamelModel):
    #: The client's own description of the search, as typed.
    brief: str = Field(default="", max_length=4000)
    #: Who is searching. Context for outreach, never a search term.
    about_me: str = Field(default="", max_length=500)
    #: Brands the wanted people distribute. Each is asked on every chosen platform.
    brands: list[str] = Field(default_factory=list, max_length=10)
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
    #: …and whether a profile that says nothing about it is refused too. Off by
    #: default: "we could not tell" is not "somewhere else", and treating the two
    #: as one answer emptied a search.
    require_confirmed_location: bool = False
    require_confirmed_language: bool = False
    must_have: list[SignalType] = Field(default_factory=list)
    nice_to_have: list[SignalType] = Field(default_factory=list)
    signal_weights: dict[SignalType, int] = Field(default_factory=dict)
    sources: list[SourceKind] = Field(default_factory=list)
    #: Queries the client wrote themselves. Run first and never dropped by the
    #: query cap; 380 characters is what the search provider accepts.
    custom_queries: list[str] = Field(default_factory=list, max_length=20)
    #: Several countries, most important first; `location.country` is then empty.
    countries: list[str] = Field(default_factory=list, max_length=12)
    #: A region accepted as a whole ("europe").
    region: str = Field(default="", max_length=20)
    #: What makes a candidate right for this search. Absent for a search recorded
    #: before requirements existed; those are read from the signal fields.
    requirements: list[RequirementSchema] | None = Field(default=None, max_length=12)
    #: How many leads to look for. It buys the page budget, so it is also what the
    #: wizard prices. 0 means "whatever the server allows".
    target_leads: int = Field(default=0, ge=0, le=1000)
    #: Countries never searched and never accepted. Russia and Belarus by default.
    excluded_countries: list[str] = Field(
        default_factory=lambda: list(DEFAULT_EXCLUDED_COUNTRIES), max_length=50
    )

    @field_validator("custom_queries")
    @classmethod
    def queries_the_provider_accepts(cls, queries: list[str]) -> list[str]:
        """
        Blank lines are the wizard's, not the client's — the input keeps one around
        while it is being typed in. Over-long queries are rejected rather than
        truncated: a query cut in half is a different question.
        """
        cleaned = [" ".join(query.split()) for query in queries]
        kept = [query for query in cleaned if query]
        if any(len(query) > 380 for query in kept):
            raise ValueError("a query may be at most 380 characters")
        return kept

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
    rejected_off_source: int = 0
    #: The reader failed on the address, so nothing was read and nothing judged.
    rejected_unreadable: int = 0
    rejected_not_a_person: int = 0
    rejected_country: int = 0
    rejected_language: int = 0
    rejected_signals: int = 0
    posts_merged: int = 0
    percent: int
    stage: SearchStage


class GeneratedQuerySchema(CamelModel):
    id: str
    query: str
    provider: str
    result_count: int
    #: Which language's index this query was put to, if not the default market.
    language: str | None = None
    #: Which country it was written for, when the search asks for several.
    country: str | None = None
    #: Which page of results it asked for; 0 is the first.
    page: int = 0


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


class MissingSignalOut(CamelModel):
    """A required signal a judged candidate did not show."""

    id: str
    label: str = ""


class RejectedCandidateOut(CamelModel):
    """One candidate the run turned away (`GET /searches/:id/rejected`)."""

    id: str
    url: str
    platform: Platform
    reason: RejectionReason
    detail: str
    #: `detail` as a code and its facts, for the interface's language. Empty on
    #: refusals recorded before codes existed.
    detail_code: str = ""
    detail_params: dict[str, str] = Field(default_factory=dict)
    #: Whether the page itself was opened. False means the refusal rests on the
    #: search result alone, which is where a missed lead would be.
    read: bool
    name: str
    title: str
    snippet: str
    query: str
    #: What the search result alone supported, 0–100. Absent when the candidate
    #: was refused before anything was computed for it.
    promise: int | None = None
    #: On a refused post: the author's profile, when the run followed it, and what
    #: became of them — "lead" or the reason they were refused.
    author_url: str | None = None
    author_name: str = ""
    author_outcome: str | None = None
    #: For `missing_signals`: the required signals that were not shown.
    missing: list[MissingSignalOut] = Field(default_factory=list)
    #: The posts this candidate was found through.
    found_via: list[str] = Field(default_factory=list)
    created_at: datetime


class RejectedOut(CamelModel):
    """
    The other half of a search result.

    `by_reason` is counted over the whole run, never over `items`: a screen that
    says "38 refused" while listing 20 must get the 38 from the database, or it is
    quoting its own truncation back at the client.
    """

    items: list[RejectedCandidateOut]
    total: int
    by_reason: dict[RejectionReason, int] = Field(default_factory=dict)
    #: Refusals decided without the page ever being opened.
    unseen: int = 0


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


class ParseBriefIn(CamelModel):
    """`POST /searches/parse` — the client's description of a search, in their words."""

    text: str = Field(min_length=1, max_length=4000)
    #: The interface language, so the suggested search name reads in it.
    locale: str = Field(default="uk", max_length=8)


class ParseBriefOut(CamelModel):
    name: str
    criteria: SearchCriteriaSchema
    #: "openai" or "rules". The rules read only countries, languages, known brands
    #: and a lead count, so the screen says when they were the ones that answered.
    parser: str


class EstimateIn(CamelModel):
    """`POST /searches/estimate` — the wizard asking what this would cost."""

    criteria: SearchCriteriaSchema


class EstimateWarningOut(CamelModel):
    """One likely problem: `wizard.review.warning.<code>` in the frontend catalogue."""

    code: str
    params: dict[str, str] = Field(default_factory=dict)


class QueryPreviewOut(CamelModel):
    query: str
    language: str | None = None
    country: str | None = None


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
    #: What a search like this usually costs (judging measured per lead, not its
    #: ceiling). Never above `max_cost_eur`.
    expected_cost_eur: float = 0.0
    #: Whether any chosen platform is read by the paid reader, so the UI can say
    #: why pages are free.
    reads_pages: bool
    #: Whether some chosen platforms are read by our own browser, for free.
    browser_pages: bool = False
    #: The most candidates a model may judge against the requirements (0 = free).
    max_judgements: int = 0
    #: What these criteria are likely to do to the result, before it is paid for.
    #: Codes, not sentences: the wording belongs to the interface language.
    warnings: list[EstimateWarningOut] = Field(default_factory=list)
