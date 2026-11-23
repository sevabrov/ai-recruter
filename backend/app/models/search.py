"""
Search domain model (spec §24, §43, §54).

A `Search` is the whole record of one run: what the user asked for, how far the
worker has got, what it cost and which queries it fired. `GET /searches/:id`
returns exactly this, which is why the frontend never has to invent progress.
"""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.models.common import (
    DEFAULT_SIGNAL_WEIGHTS,
    SCORED_SIGNALS,
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


class Importance(StrEnum):
    """How much a requirement matters. Points follow from it (see `balanced`)."""

    #: A gate: a candidate who does not visibly meet it is refused. Also scored.
    REQUIRED = "required"
    HIGH = "high"
    NORMAL = "normal"


#: Relative share of the 100 points per importance level.
IMPORTANCE_SHARE: dict[Importance, int] = {
    Importance.REQUIRED: 3,
    Importance.HIGH: 2,
    Importance.NORMAL: 1,
}

#: Requirement ids that name one of the built-in signals. Those are judged by the
#: built-in means (the page reader's observations, the keyword vocabulary, the
#: country match); any other id is a requirement written for this one search.
PRESET_IDS: frozenset[str] = frozenset(signal.value for signal in SignalType)


class Requirement(BaseModel):
    """
    One thing that makes a candidate right for *this* search.

    The product recruits for any role, so what counts is written per search —
    "Python", "Django", "middle or senior" for a developer search; the seven
    built-in signals (network marketing, beauty, recruiting…) for a search for
    distributors. Each is judged on the candidate's own profile with a quote, and
    the score is the backend's arithmetic over these, never a model's number.
    """

    #: Stable within the search. A built-in signal's value ("mlm", "location") for
    #: the presets; anything else ("r1") for a requirement of the client's own.
    id: str = Field(min_length=1, max_length=40)
    #: In the client's language. Empty for a preset: the interface names it.
    label: str = Field(default="", max_length=80)
    #: What counts as meeting it — what the judge is told to look for.
    description: str = Field(default="", max_length=300)
    #: Words that show it on a profile, for judging without a model.
    terms: list[str] = Field(default_factory=list, max_length=10)
    importance: Importance = Importance.NORMAL
    #: Points a fully confident match is worth. `balanced` keeps the total at 100.
    weight: int = Field(default=0, ge=0, le=100)

    @property
    def required(self) -> bool:
        return self.importance is Importance.REQUIRED

    @property
    def is_preset(self) -> bool:
        return self.id in PRESET_IDS


def balanced(requirements: list["Requirement"]) -> list["Requirement"]:
    """
    The same requirements with points shared out by importance, summing to 100.

    The client chooses how much each thing matters, not how many points it gets:
    a list of numbers that has to add up to 100 was the least-used screen of the
    old wizard. `activity` stays at 0 — it is shown, never scored (spec §37).
    """
    scored = [r for r in requirements if r.id != SignalType.ACTIVITY]
    shares = [IMPORTANCE_SHARE[r.importance] for r in scored]
    total = sum(shares)
    if not total:
        return [r.model_copy(update={"weight": 0}) for r in requirements]
    points = [100 * share // total for share in shares]
    # Whole points that still add up: the remainder goes to the most important.
    for index in sorted(range(len(points)), key=lambda i: -shares[i])[: 100 - sum(points)]:
        points[index] += 1
    by_id = {r.id: weight for r, weight in zip(scored, points, strict=True)}
    return [r.model_copy(update={"weight": by_id.get(r.id, 0)}) for r in requirements]


#: "Any European country". Russia and Belarus are left out on purpose: nobody
#: hiring "from Ukraine or Europe" means them, and a search that returned them
#: would be answering a question nobody asked.
EUROPE: frozenset[str] = frozenset(
    {
        "Albania", "Austria", "Belgium", "Bosnia and Herzegovina", "Bulgaria", "Croatia",
        "Cyprus", "Czechia", "Denmark", "Estonia", "Finland", "France", "Germany", "Greece",
        "Hungary", "Iceland", "Ireland", "Italy", "Kosovo", "Latvia", "Lithuania",
        "Luxembourg", "Malta", "Moldova", "Montenegro", "Netherlands", "North Macedonia",
        "Norway", "Poland", "Portugal", "Romania", "Serbia", "Slovakia", "Slovenia", "Spain",
        "Sweden", "Switzerland", "Ukraine", "United Kingdom",
    }
)  # fmt: skip

#: Spellings a page or a model may use for a country the lists above name otherwise.
COUNTRY_ALIASES: dict[str, str] = {
    "czech republic": "Czechia",
    "uk": "United Kingdom",
    "great britain": "United Kingdom",
    "england": "United Kingdom",
    "the netherlands": "Netherlands",
    "holland": "Netherlands",
    "republic of moldova": "Moldova",
    "macedonia": "North Macedonia",
}

#: Regions a brief may name instead of a list of countries.
REGIONS: dict[str, frozenset[str]] = {"europe": EUROPE}

#: When a region is asked for and no country in it is, queries are aimed at these:
#: the largest markets, so the search asks somewhere rather than everywhere.
REGION_FOCUS: dict[str, tuple[str, ...]] = {
    "europe": ("Poland", "Germany", "Spain", "Italy"),
}

#: How many countries one search writes queries for. Each is another set of calls.
MAX_FOCUS_COUNTRIES = 4


def canonical_country(name: str | None) -> str:
    """One spelling per country, so "Czech Republic" on a page matches "Czechia"."""
    cleaned = " ".join((name or "").split())
    return COUNTRY_ALIASES.get(cleaned.casefold(), cleaned)


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
    #: What makes a candidate right for this search, written for it. None for a
    #: search recorded before requirements existed: those are read from
    #: `must_have` / `signal_weights` by `effective_requirements`.
    requirements: list[Requirement] | None = Field(default=None, max_length=12)
    #: Several countries, in the order they matter ("Ukraine or Poland"). When set,
    #: `location.country` is left empty: queries are written for each of the first
    #: few, and a candidate from any of them is in the right place.
    countries: list[str] = Field(default_factory=list, max_length=12)
    #: A region accepted as a whole ("europe"). Queries still go to named countries —
    #: the ones above, or the region's largest — because a query written for
    #: "Europe" matches no profile: people write their city and country.
    region: str = Field(default="", max_length=20)
    #: How many leads this search is being asked for. It is the client's own
    #: spending control: the page budget is derived from it, the wizard prices it
    #: before anything runs, and the search stops once it is met. 0 means "use
    #: whatever the server allows".
    target_leads: int = Field(default=0, ge=0, le=1000)

    def allowed_countries(self) -> frozenset[str]:
        """Every country a candidate may be in; empty means anywhere."""
        allowed = {canonical_country(name) for name in self.countries if name}
        if self.location.country:
            allowed.add(canonical_country(self.location.country))
        allowed |= REGIONS.get(self.region, frozenset())
        return frozenset(allowed)

    def in_allowed_place(self, country: str | None) -> bool | None:
        """True / False when the country is known, None when there is nothing to check."""
        allowed = self.allowed_countries()
        if not allowed or not country:
            return None
        return canonical_country(country).casefold() in {name.casefold() for name in allowed}

    def place_label(self) -> str:
        """The asked-for place in words, for refusal details."""
        names = [self.location.country] if self.location.country else list(self.countries)
        if self.region:
            names.append(self.region.capitalize())
        return " / ".join(name for name in names if name)

    def focus_countries(self) -> list[str]:
        """The countries queries are written for, most important first."""
        if self.location.country:
            return [self.location.country]
        focus = [name for name in self.countries if name]
        for name in REGION_FOCUS.get(self.region, ()):
            if name not in focus:
                focus.append(name)
        return focus[:MAX_FOCUS_COUNTRIES]

    def effective_requirements(self) -> list[Requirement]:
        """
        The requirements this search is judged and scored by.

        A search written before requirements existed is read the way it was run:
        each scored signal with its points, a must-have as a requirement. The
        arithmetic is therefore unchanged for every recorded search.
        """
        if self.requirements is not None:
            return list(self.requirements)
        weights = {**DEFAULT_SIGNAL_WEIGHTS, **self.signal_weights}
        derived = [
            Requirement(
                id=signal.value,
                weight=weights.get(signal, 0),
                importance=Importance.REQUIRED if signal in self.must_have else Importance.NORMAL,
            )
            for signal in SCORED_SIGNALS
            if weights.get(signal, 0) > 0 or signal in self.must_have
        ]
        if SignalType.ACTIVITY in self.must_have:
            derived.append(
                Requirement(id=SignalType.ACTIVITY.value, importance=Importance.REQUIRED)
            )
        return derived

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
    #: Posts whose author was judged: they live on the author's row (or lead), not
    #: as refusals of their own — so discovery's arithmetic has to count them.
    posts_merged: int = 0
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
    #: The country this query was written for, when the search asks for several.
    country: str | None = None


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
