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
    #: What the client wrote, in their own words, before it became criteria. Kept
    #: so a re-run starts from the description rather than from fields nobody typed.
    brief: str = Field(default="", max_length=4000)
    #: Who is searching: their brand and role ("лідерка MIHI в Іспанії"). Context
    #: for outreach drafts — never a search term, or the search finds their own team.
    about_me: str = Field(default="", max_length=500)
    #: Brands the wanted people distribute, spelled the way the market spells them.
    #: The single best search term there is: a brand name is what a distributor puts
    #: in a bio and what nobody else does. Each one is asked on every chosen platform.
    brands: list[str] = Field(default_factory=list, max_length=10)
    industry: list[str] = Field(default_factory=list)
    business_types: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    negative_keywords: list[str] = Field(default_factory=list)
    location: GeoLocation = Field(default_factory=GeoLocation)
    languages: list[str] = Field(default_factory=list)
    #: Geography and language as requirements rather than as points (spec §32).
    #: A search for Ukraine that returns a distributor in Croatia is not a search
    #: for Ukraine, so both default to on.
    require_location: bool = True
    require_language: bool = True
    #: …and what to do when the profile simply does not say.
    #:
    #: "This person is in Romania" and "we could not tell" are different answers,
    #: and treating them the same emptied a search: of 24 candidates refused in one
    #: measured run, 19 went on geography and exactly *one* of those was actually
    #: somewhere else. An Instagram profile whose page will not open and whose
    #: two-line description names no city is not evidence of the wrong country.
    #:
    #: So unknown passes by default and the missing signal costs its own points.
    #: True is the strict reading — only what can be confirmed survives — which is
    #: worth having when precision matters more than volume.
    require_confirmed_location: bool = False
    require_confirmed_language: bool = False
    must_have: list[SignalType] = Field(default_factory=list)
    nice_to_have: list[SignalType] = Field(default_factory=list)
    #: Points per signal. The backend owns the arithmetic (spec §37).
    signal_weights: dict[SignalType, int] = Field(
        default_factory=lambda: dict(DEFAULT_SIGNAL_WEIGHTS)
    )
    sources: list[SourceKind] = Field(default_factory=list)
    #: Queries the client wrote themselves, run ahead of the generated ones and
    #: never dropped to make room for a template (spec §29). Somebody who knows
    #: their market can write `site:instagram.com "#млмукраина"` in one line; no
    #: template is going to guess it. 380 characters is the provider's own limit.
    custom_queries: list[str] = Field(default_factory=list, max_length=20)
    #: How many leads this search is being asked for. It is the client's own
    #: spending control: the page budget is derived from it, the wizard prices it
    #: before anything runs, and the search stops once it is met. 0 means "use
    #: whatever the server allows".
    target_leads: int = Field(default=0, ge=0, le=1000)

    def target_label(self) -> str:
        """The short human label the UI shows next to a search name."""
        parts = [" / ".join(self.business_types), " / ".join(self.industry)]
        return " · ".join(part for part in parts if part) or "Unspecified target"


class SearchProgress(BaseModel):
    """
    What the worker has done so far, and — since the criteria became gates — what
    it turned away. A search that looked at forty candidates and produced two
    leads has to be able to say which requirement the other thirty-eight failed,
    or the number reads as a broken tool rather than as a strict one.
    """

    queries: int = 0
    queries_completed: int = 0
    urls_discovered: int = 0
    profiles_discovered: int = 0
    profiles_processed: int = 0
    qualified: int = 0
    high_quality: int = 0
    #: Discovered on a platform the client did not ask to look at. Counted at
    #: discovery, before anything is read — `site:` is a request, not a guarantee.
    rejected_off_source: int = 0
    #: The reader failed on the address — nothing was read, so nothing was judged.
    rejected_unreadable: int = 0
    rejected_not_a_person: int = 0
    rejected_country: int = 0
    rejected_language: int = 0
    rejected_signals: int = 0
    percent: int = 0
    stage: SearchStage = SearchStage.QUEUED


class GeneratedQuery(BaseModel):
    id: str
    query: str
    provider: str
    result_count: int = 0
    #: The language this query is written in, as the provider's code. A search for
    #: Ukrainian speakers asks in Ukrainian, and the index it is asked against is
    #: chosen per query for the same reason (spec §29).
    language: str | None = None


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
